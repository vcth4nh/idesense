#!/usr/bin/env python3
"""Unit tests for fleet.py (no IDE contact). Run from live-test/."""
import os
import shutil
import signal
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import fleet

GOLAND = fleet.IDES["goland"]
CMD = ["/opt/tb/apps/goland/jbr/bin/java", "-classpath", "x.jar", "-Xmx2048m",
       "-Djb.vmOptionsFile=/home/u/.config/JetBrains/GoLand2026.2/goland64.vmoptions",
       "-Didea.paths.selector=GoLand2026.2", "-Didea.platform.prefix=GoLand",
       "com.intellij.idea.Main", "serverMode"]
FIX = "/home/u/dev/idesense/live-test/fixtures/go"
CADDY = "/home/u/dev/idesense/live-test/real-products/caddy"
FIX_KEY = "$USER_HOME$/dev/idesense/live-test/fixtures/go"
CADDY_KEY = "$USER_HOME$/dev/idesense/live-test/real-products/caddy"
RECENT = f"""<application>
  <component name="RecentProjectsManager">
    <option name="additionalInfo">
      <map>
        <entry key="$APPLICATION_CONFIG_DIR$/projects/GoLandWorkspace">
          <value><RecentProjectMetaInfo frameTitle="GoLandWorkspace" hidden="true" projectWorkspaceId="ws1" /></value>
        </entry>
        <entry key="{FIX_KEY}">
          <value>
            <RecentProjectMetaInfo frameTitle="go" opened="true" projectWorkspaceId="ws2">
              <option name="build" value="GO-262.8665.336" />
            </RecentProjectMetaInfo>
          </value>
        </entry>
      </map>
    </option>
    <option name="lastOpenedProject" value="{FIX_KEY}" />
  </component>
</application>"""


def opened(xml_text):
    return {e.get("key"): e.find("value/RecentProjectMetaInfo").get("opened")
            for e in ET.fromstring(xml_text).iter("entry")}


class IdeTableTest(unittest.TestCase):
    def test_port_by_lang_matches_the_fleet(self):
        self.assertEqual({"python": 29172, "java": 29170, "kotlin": 29170, "javascript": 29173,
                          "typescript": 29173, "go": 29174, "php": 29175, "rust": 29178}, fleet.PORT_BY_LANG)

    def test_run_uses_the_same_table(self):
        import run
        self.assertIs(fleet.PORT_BY_LANG, run.PORT_BY_LANG)

    def test_ide_url(self):
        self.assertEqual("http://127.0.0.1:29174/mcp/streamable-http", fleet.ide_url(GOLAND))


class ParseIdeProcessTest(unittest.TestCase):
    def parse(self, cmd=CMD):
        return fleet.parse_ide_process(GOLAND, 4242, cmd, "/opt/tb/apps/goland/jbr/bin/java",
                                       b"PATH=/usr/bin\0HOME=/home/u\0", "/home/u", "/home/u")

    def test_fleet_process(self):
        p = self.parse()
        self.assertEqual(4242, p.pid)
        self.assertEqual(Path("/opt/tb/apps/goland/bin/goland.sh"), p.launcher)
        self.assertEqual(Path("/home/u/.config/JetBrains/GoLand2026.2"), p.config_dir)
        self.assertEqual({"PATH": "/usr/bin", "HOME": "/home/u"}, p.env)
        self.assertEqual("/home/u", p.cwd)

    def test_fleet_process_that_was_started_with_a_project_path(self):
        # The cold-start recipe is `<ide>.sh serverMode <project path>`; the path follows `serverMode`.
        self.assertEqual(4242, self.parse(CMD + [FIX]).pid)

    def test_other_ide_is_not_matched(self):
        self.assertIsNone(self.parse([a.replace("GoLand", "PyCharm") for a in CMD]))

    def test_other_edition_with_the_same_name_prefix_is_not_matched(self):
        self.assertIsNone(self.parse([a.replace("GoLand2026.2", "GoLandCE2026.2") for a in CMD]))

    def test_instance_with_its_own_config_path_is_not_the_fleet(self):
        self.assertIsNone(self.parse(CMD[:3] + ["-Didea.config.path=/run/user/1000/tw/config"] + CMD[3:]))

    def test_instance_without_server_mode_is_not_matched(self):
        self.assertIsNone(self.parse(CMD[:-1]))


class RewriteRecentProjectsTest(unittest.TestCase):
    def test_adds_an_entry_for_a_new_project(self):
        out = fleet.rewrite_recent_projects(RECENT, [FIX, CADDY], "/home/u")
        self.assertEqual({"$APPLICATION_CONFIG_DIR$/projects/GoLandWorkspace": None,
                          FIX_KEY: "true", CADDY_KEY: "true"}, opened(out))

    def test_closes_a_project_that_is_not_wanted(self):
        both = fleet.rewrite_recent_projects(RECENT, [FIX, CADDY], "/home/u")
        out = fleet.rewrite_recent_projects(both, [FIX], "/home/u")
        self.assertEqual({"$APPLICATION_CONFIG_DIR$/projects/GoLandWorkspace": None,
                          FIX_KEY: "true", CADDY_KEY: None}, opened(out))

    def test_keeps_the_other_data_of_an_entry(self):
        out = fleet.rewrite_recent_projects(RECENT, [FIX], "/home/u")
        self.assertIn('projectWorkspaceId="ws2"', out)
        self.assertIn('value="GO-262.8665.336"', out)

    def test_matches_an_entry_key_without_the_home_macro(self):
        out = fleet.rewrite_recent_projects(RECENT.replace(FIX_KEY, FIX), [FIX], "/home/u")
        self.assertEqual({"$APPLICATION_CONFIG_DIR$/projects/GoLandWorkspace": None, FIX: "true"}, opened(out))


def answers(*results):
    it = iter(results)
    last = [None]

    def post(url, request, timeout=60.0):
        last[0] = next(it, last[0])
        return last[0]
    return post


def projects(*paths):
    return {"error": "project_not_found", "available_projects": [{"name": Path(p).name, "path": p} for p in paths]}


class OpenProjectsTest(unittest.TestCase):
    def test_reads_the_paths_from_the_error_payload(self):
        self.assertEqual([FIX, CADDY], fleet.open_projects("http://x", answers(projects(FIX, CADDY))))

    def test_module_folders_of_a_project_are_not_projects(self):
        # ProjectResolver.kt lists each module content root as one more entry, with a "workspace" key.
        payload = projects(FIX, CADDY)
        payload["available_projects"].insert(1, {"name": "go.main", "path": FIX + "/src/main", "workspace": "go"})
        self.assertEqual([FIX, CADDY], fleet.open_projects("http://x", answers(payload)))

    def test_server_that_does_not_answer(self):
        self.assertIsNone(fleet.open_projects("http://x", answers({"transport_error": "Connection refused"})))


class SetOpenProjectsTest(unittest.TestCase):
    def proc(self):
        cfg = Path(tempfile.mkdtemp())
        (cfg / "options").mkdir()
        (cfg / "options" / "recentProjects.xml").write_text(RECENT)
        return fleet.IdeProcess(4242, Path("/opt/tb/apps/goland/bin/goland.sh"), cfg, {"HOME": "/home/u"}, "/home/u")

    def test_no_restart_when_the_set_is_already_open(self):
        with mock.patch.object(fleet, "find_ide_process") as find:
            self.assertIsNone(fleet.set_open_projects(GOLAND, [CADDY, FIX], answers(projects(FIX, CADDY)), log=lambda s: None))
        find.assert_not_called()

    def test_restart_with_the_new_set(self):
        proc = self.proc()
        with mock.patch.object(fleet, "find_ide_process", return_value=proc), \
             mock.patch.object(fleet, "_stop", return_value=None) as stop, \
             mock.patch.object(fleet, "_start") as start, mock.patch.object(fleet.time, "sleep"):
            err = fleet.set_open_projects(GOLAND, [FIX, CADDY], answers(projects(FIX), None, projects(FIX, CADDY)),
                                          log=lambda s: None)
        self.assertIsNone(err)
        stop.assert_called_once()
        start.assert_called_once_with(proc)
        self.assertEqual("true", opened((proc.config_dir / "options" / "recentProjects.xml").read_text())[CADDY_KEY])

    def test_reports_the_start_command_when_the_ide_does_not_come_back(self):
        with mock.patch.object(fleet, "find_ide_process", return_value=self.proc()), \
             mock.patch.object(fleet, "_stop", return_value=None), mock.patch.object(fleet, "_start"), \
             mock.patch.object(fleet.time, "sleep"):
            err = fleet.set_open_projects(GOLAND, [FIX, CADDY], answers(projects(FIX), None), log=lambda s: None,
                                          start_timeout=0.0)
        self.assertIn("/opt/tb/apps/goland/bin/goland.sh serverMode", err)

    def test_stop_error_is_returned_and_nothing_is_written(self):
        proc = self.proc()
        with mock.patch.object(fleet, "find_ide_process", return_value=proc), \
             mock.patch.object(fleet, "_stop", return_value="goland did not stop in 90 s"), \
             mock.patch.object(fleet, "_start") as start:
            err = fleet.set_open_projects(GOLAND, [FIX, CADDY], answers(projects(FIX)), log=lambda s: None)
        self.assertEqual("goland did not stop in 90 s", err)
        start.assert_not_called()
        self.assertEqual(RECENT, (proc.config_dir / "options" / "recentProjects.xml").read_text())


class StartStopTest(unittest.TestCase):
    """Real processes: a small shell script stands in for <ide>.sh."""

    def launch(self, body):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        script, out = d / "fake-ide.sh", d / "out.txt"
        script.write_text("#!/bin/sh\n" + body)
        script.chmod(0o755)
        env = {"PATH": os.environ["PATH"], "FLEET_TEST": "yes", "OUT": str(out)}
        fleet._start(fleet.IdeProcess(0, script, d, env, str(d)))
        deadline = time.monotonic() + 5
        while not (out.is_file() and out.read_text().endswith("\n")):
            self.assertLess(time.monotonic(), deadline, "the fake IDE did not start")
            time.sleep(0.02)
        return d, script, out.read_text()

    def running(self, body):
        d, script, text = self.launch(body)
        pid = int(text)
        self.addCleanup(lambda: Path(f"/proc/{pid}").exists() and os.kill(pid, signal.SIGKILL))
        return fleet.IdeProcess(pid, script, d, {}, str(d))

    def test_start_passes_the_argument_the_environment_and_the_working_directory(self):
        d, _, text = self.launch('echo "$1 $FLEET_TEST $(pwd)" > "$OUT"\n')
        self.assertEqual(f"serverMode yes {d}\n", text)

    def test_process_that_start_made_can_be_stopped_by_the_same_harness(self):
        proc = self.running('echo $$ > "$OUT"\nexec sleep 60\n')
        self.assertIsNone(fleet._stop(proc, 5.0, "demo"))
        self.assertFalse(Path(f"/proc/{proc.pid}").exists())

    def test_stop_reports_a_process_that_ignores_the_signal(self):
        proc = self.running('trap "" TERM\necho $$ > "$OUT"\nexec sleep 60\n')
        self.assertEqual("demo did not stop in 1 s", fleet._stop(proc, 1.0, "demo"))
        self.assertTrue(Path(f"/proc/{proc.pid}").exists())


if __name__ == "__main__":
    unittest.main()
