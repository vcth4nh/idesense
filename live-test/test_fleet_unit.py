#!/usr/bin/env python3
"""Unit tests for fleet.py (no IDE contact). Run from live-test/."""
import os
import shutil
import signal
import subprocess
import tempfile
import threading
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


TRUSTED = f"""<application>
  <component name="Trusted.Paths">
    <option name="TRUSTED_PROJECT_PATHS">
      <map>
        <entry key="$APPLICATION_CONFIG_DIR$/projects/GoLandWorkspace" value="true" />
        <entry key="{FIX_KEY}" value="true" />
      </map>
    </option>
  </component>
  <component name="Trusted.Paths.Settings">
    <option name="TRUSTED_PATHS">
      <list>
        <option value="$USER_HOME$/dev/idesense/live-test" />
      </list>
    </option>
  </component>
</application>"""


def trusted(xml_text):
    """The entries of the map TRUSTED_PROJECT_PATHS of component Trusted.Paths."""
    return {e.get("key"): e.get("value") for e in ET.fromstring(xml_text).findall(
        "component[@name='Trusted.Paths']/option[@name='TRUSTED_PROJECT_PATHS']/map/entry")}


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


class FindIdeProcessTest(unittest.TestCase):
    """The real /proc of the test machine. parse_ide_process is replaced, so no IDE is necessary."""

    def find(self, matches):
        # `matches` processes look like a fleet instance: this test process and one child of it.
        child = subprocess.Popen(["sleep", "30"])
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        pids = [os.getpid(), child.pid][:matches]

        def parse(ide, pid, *rest):
            return fleet.IdeProcess(pid, Path("/x"), Path("/y"), {}, "/") if pid in pids else None

        with mock.patch.object(fleet, "parse_ide_process", parse):
            return fleet.find_ide_process(GOLAND)

    def test_no_fleet_process(self):
        self.assertIsNone(self.find(0))

    def test_one_fleet_process(self):
        self.assertEqual(os.getpid(), self.find(1).pid)

    def test_two_fleet_processes_are_an_error_and_no_process_is_chosen(self):
        with self.assertRaisesRegex(RuntimeError, "2 goland fleet processes run"):
            self.find(2)


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

    def test_file_without_a_project_map_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no project map"):
            fleet.rewrite_recent_projects("<application />", [FIX], "/home/u")

    def test_matches_an_entry_key_without_the_home_macro(self):
        out = fleet.rewrite_recent_projects(RECENT.replace(FIX_KEY, FIX), [FIX], "/home/u")
        self.assertEqual({"$APPLICATION_CONFIG_DIR$/projects/GoLandWorkspace": None, FIX: "true"}, opened(out))


class TrustProjectPathsTest(unittest.TestCase):
    def test_adds_an_entry_for_a_new_path(self):
        out = fleet.trust_project_paths(TRUSTED, [CADDY], "/home/u")
        self.assertEqual("true", trusted(out)[CADDY_KEY])

    def test_second_call_changes_nothing(self):
        once = fleet.trust_project_paths(TRUSTED, [CADDY], "/home/u")
        self.assertEqual(once, fleet.trust_project_paths(once, [CADDY], "/home/u"))

    def test_absent_file_gives_a_new_component(self):
        out = fleet.trust_project_paths(None, [CADDY], "/home/u")
        self.assertEqual({CADDY_KEY: "true"}, trusted(out))
        self.assertEqual("application", ET.fromstring(out).tag)

    def test_file_without_the_component_gives_a_new_component(self):
        settings_only = TRUSTED.replace(TRUSTED[TRUSTED.index('  <component name="Trusted.Paths">'):
                                                TRUSTED.index('  <component name="Trusted.Paths.Settings">')], "")
        out = fleet.trust_project_paths(settings_only, [CADDY], "/home/u")
        self.assertEqual({CADDY_KEY: "true"}, trusted(out))
        self.assertIsNotNone(ET.fromstring(out).find("component[@name='Trusted.Paths.Settings']"))

    def test_keeps_the_other_entries_and_the_settings_component(self):
        out = fleet.trust_project_paths(TRUSTED, [CADDY], "/home/u")
        self.assertEqual({"$APPLICATION_CONFIG_DIR$/projects/GoLandWorkspace": "true", FIX_KEY: "true",
                          CADDY_KEY: "true"}, trusted(out))
        roots = ET.fromstring(out).findall("component[@name='Trusted.Paths.Settings']/option[@name='TRUSTED_PATHS']/list/option")
        self.assertEqual(["$USER_HOME$/dev/idesense/live-test"], [o.get("value") for o in roots])

    def test_path_outside_the_home_folder_keeps_its_absolute_form(self):
        out = fleet.trust_project_paths(TRUSTED, ["/srv/products/caddy"], "/home/u")
        self.assertEqual("true", trusted(out)["/srv/products/caddy"])
        self.assertNotIn("$USER_HOME$/srv", out)


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
        self.addCleanup(shutil.rmtree, cfg)
        (cfg / "options").mkdir()
        (cfg / "options" / "recentProjects.xml").write_text(RECENT)
        launcher = cfg / "goland.sh"
        launcher.write_text("#!/bin/sh\n")
        launcher.chmod(0o755)
        return fleet.IdeProcess(4242, launcher, cfg, {"HOME": "/home/u"}, "/home/u")

    def switch(self, proc, post, stop=None, start=None, **kw):
        """Run a switch with a fake stop and a fake start. Returns (error, stop mock, start mock)."""
        kw.setdefault("start_timeout", 1.0)  # the wait for the IDE has no sleep here: keep a failure short
        with mock.patch.object(fleet, "find_ide_process", return_value=proc), \
             mock.patch.object(fleet, "_stop", side_effect=stop, return_value=None) as stop_mock, \
             mock.patch.object(fleet, "_start", side_effect=start) as start_mock, \
             mock.patch.object(fleet.time, "sleep"):
            err = fleet.set_open_projects(GOLAND, kw.pop("wanted", [FIX, CADDY]), post, log=lambda s: None, **kw)
        return err, stop_mock, start_mock

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
        proc = self.proc()
        err, _, _ = self.switch(proc, answers(projects(FIX), None), start_timeout=0.0)
        self.assertIn(f"{proc.launcher} serverMode", err)

    def test_stop_error_is_returned_and_nothing_is_written(self):
        proc = self.proc()
        with mock.patch.object(fleet, "find_ide_process", return_value=proc), \
             mock.patch.object(fleet, "_stop", return_value="goland did not stop in 90 s"), \
             mock.patch.object(fleet, "_start") as start:
            err = fleet.set_open_projects(GOLAND, [FIX, CADDY], answers(projects(FIX)), log=lambda s: None)
        # The IDE has its signal and can still stop later, so the line gives the start command.
        self.assertEqual(f"goland did not stop in 90 s. If it stops later, start it with: {proc.launcher} serverMode", err)
        start.assert_not_called()
        self.assertEqual(RECENT, (proc.config_dir / "options" / "recentProjects.xml").read_text())

    def test_recent_projects_file_that_cannot_be_rewritten_is_reported_before_the_ide_stops(self):
        for content in ("<application />", "not xml", None):
            proc = self.proc()
            recent = proc.config_dir / "options" / "recentProjects.xml"
            recent.write_text(content) if content is not None else recent.unlink()
            with mock.patch.object(fleet, "find_ide_process", return_value=proc), \
                 mock.patch.object(fleet, "_stop", return_value=None) as stop, \
                 mock.patch.object(fleet, "_start") as start:
                err = fleet.set_open_projects(GOLAND, [FIX, CADDY], answers(projects(FIX)), log=lambda s: None)
            self.assertRegex(err, r"^cannot rewrite .*recentProjects\.xml: ")
            stop.assert_not_called()
            start.assert_not_called()

    def test_project_that_the_caller_did_not_name_is_never_closed(self):
        # A command from another checkout wants its own fixture folder. The IDE has the fleet fixture open.
        other = "/home/u/worktree/live-test/fixtures/go"
        with mock.patch.object(fleet, "find_ide_process", return_value=None) as find:
            err = fleet.set_open_projects(GOLAND, [other], answers(projects(FIX)), log=lambda s: None)
        self.assertIn(f"must not close: {FIX}", err)
        find.assert_not_called()

    def test_project_that_the_caller_named_is_closed(self):
        proc = self.proc()
        recent = proc.config_dir / "options" / "recentProjects.xml"
        recent.write_text(fleet.rewrite_recent_projects(RECENT, [FIX, CADDY], "/home/u"))
        err, stop, _ = self.switch(proc, answers(projects(FIX, CADDY), None, projects(FIX)), wanted=[FIX],
                                   may_close=lambda path: path == CADDY)
        self.assertIsNone(err)
        stop.assert_called_once()
        self.assertEqual({FIX_KEY: "true", CADDY_KEY: None},
                         {k: v for k, v in opened(recent.read_text()).items() if k in (FIX_KEY, CADDY_KEY)})

    def test_server_that_is_not_the_fleet_server_is_never_restarted(self):
        # `--url` of a throwaway IDE: its projects must not make the harness restart the fleet process.
        with mock.patch.object(fleet, "find_ide_process", return_value=None) as find:
            err = fleet.set_open_projects(GOLAND, [FIX, CADDY], answers(projects(FIX)), log=lambda s: None,
                                          url="http://127.0.0.1:29199/mcp/streamable-http")
        self.assertIn("is not the fleet server of goland", err)
        find.assert_not_called()

    def test_ide_is_started_again_when_the_rewrite_fails_after_the_stop(self):
        proc = self.proc()
        with mock.patch.object(fleet.os, "replace", side_effect=PermissionError("no write")):
            err, _, start = self.switch(proc, answers(projects(FIX)))
        start.assert_called_once_with(proc)
        self.assertRegex(err, r"^cannot rewrite .*recentProjects\.xml: no write")

    def test_trust_entry_is_written_between_the_stop_and_the_start(self):
        proc = self.proc()
        path = proc.config_dir / "options" / "trusted-paths.xml"
        path.write_text(TRUSTED)
        seen = {}

        def at_stop(*a):
            seen["stop"] = path.read_text()

        def at_start(*a):
            seen["start"] = path.read_text()
        err, _, _ = self.switch(proc, answers(projects(FIX), None, projects(FIX, CADDY)), trust=[CADDY],
                                stop=at_stop, start=at_start)
        self.assertIsNone(err)
        self.assertEqual(TRUSTED, seen["stop"])
        self.assertEqual("true", trusted(seen["start"])[CADDY_KEY])
        self.assertEqual(["recentProjects.xml", "trusted-paths.xml"], sorted(p.name for p in path.parent.iterdir()))

    def test_absent_trust_file_is_created(self):
        proc = self.proc()
        err, _, _ = self.switch(proc, answers(projects(FIX), None, projects(FIX, CADDY)), trust=[CADDY])
        self.assertIsNone(err)
        self.assertEqual({CADDY_KEY: "true"}, trusted((proc.config_dir / "options" / "trusted-paths.xml").read_text()))

    def test_switch_with_no_trust_leaves_the_trust_file_alone(self):
        proc = self.proc()
        err, _, _ = self.switch(proc, answers(projects(FIX), None, projects(FIX, CADDY)))
        self.assertIsNone(err)
        self.assertFalse((proc.config_dir / "options" / "trusted-paths.xml").exists())

    def test_trust_file_that_cannot_be_rewritten_is_reported_before_the_ide_stops(self):
        proc = self.proc()
        (proc.config_dir / "options" / "trusted-paths.xml").write_text("not xml")
        err, stop, start = self.switch(proc, answers(projects(FIX)), trust=[CADDY])
        self.assertRegex(err, r"^cannot rewrite .*trusted-paths\.xml: ")
        stop.assert_not_called()
        start.assert_not_called()

    def test_failed_trust_write_after_the_stop_keeps_the_old_projects(self):
        proc = self.proc()
        replace = os.replace

        def replace_all_but_the_trust_file(src, dst):
            if Path(dst).name == "trusted-paths.xml":
                raise PermissionError("no write")
            replace(src, dst)
        with mock.patch.object(fleet.os, "replace", side_effect=replace_all_but_the_trust_file):
            err, _, start = self.switch(proc, answers(projects(FIX)), trust=[CADDY])
        start.assert_called_once_with(proc)
        self.assertRegex(err, r"^cannot rewrite .*trusted-paths\.xml: no write. goland runs again with its old projects")
        self.assertEqual(RECENT, (proc.config_dir / "options" / "recentProjects.xml").read_text())

    def test_interrupt_after_the_stop_is_held_back_until_the_ide_is_started(self):
        proc = self.proc()

        def stop(*args):
            os.kill(os.getpid(), signal.SIGINT)  # Ctrl+C while the IDE stops

        with mock.patch.object(fleet, "find_ide_process", return_value=proc), \
             mock.patch.object(fleet, "_stop", side_effect=stop, return_value=None), \
             mock.patch.object(fleet, "_start") as start, mock.patch.object(fleet.time, "sleep"):
            with self.assertRaises(KeyboardInterrupt):
                fleet.set_open_projects(GOLAND, [FIX, CADDY], answers(projects(FIX), None, projects(FIX, CADDY)),
                                        log=lambda s: None)
        start.assert_called_once_with(proc)

    def test_interrupt_that_another_thread_receives_is_held_back_too(self):
        # A signal mask of the main thread would not be sufficient: the kernel gives the signal to any thread.
        proc = self.proc()
        go, sent = threading.Event(), threading.Event()

        def send():
            go.wait(5)
            os.kill(os.getpid(), signal.SIGINT)
            sent.set()

        # The thread starts before the switch, so it has its own signal mask (a new thread copies the mask).
        sender = threading.Thread(target=send)
        sender.start()
        self.addCleanup(sender.join)

        def stop(*args):
            go.set()
            sent.wait(5)

        with mock.patch.object(fleet, "find_ide_process", return_value=proc), \
             mock.patch.object(fleet, "_stop", side_effect=stop, return_value=None), \
             mock.patch.object(fleet, "_start") as start, mock.patch.object(fleet.time, "sleep"):
            with self.assertRaises(KeyboardInterrupt):
                fleet.set_open_projects(GOLAND, [FIX, CADDY], answers(projects(FIX), None, projects(FIX, CADDY)),
                                        log=lambda s: None)
        start.assert_called_once_with(proc)

    def test_sigterm_after_the_stop_is_delivered_after_the_start(self):
        events = []
        before = signal.signal(signal.SIGTERM, lambda signum, frame: events.append("SIGTERM delivered"))
        self.addCleanup(signal.signal, signal.SIGTERM, before)
        mine = signal.getsignal(signal.SIGTERM)

        def stop(*args):
            os.kill(os.getpid(), signal.SIGTERM)  # for example the timeout of a tool that runs the harness

        err, _, _ = self.switch(self.proc(), answers(projects(FIX), None, projects(FIX, CADDY)),
                                stop=stop, start=lambda proc: events.append("start"))
        self.assertIsNone(err)
        self.assertEqual(["start", "SIGTERM delivered"], events)
        self.assertIs(mine, signal.getsignal(signal.SIGTERM))    # the handler of the caller is back

    def test_launcher_that_is_no_executable_file_is_reported_before_the_ide_stops(self):
        # For example an IDE update that replaced the application folder while the IDE ran.
        proc = self.proc()
        proc.launcher.chmod(0o644)
        err, stop, start = self.switch(proc, answers(projects(FIX)))
        self.assertEqual(f"cannot restart goland: launcher {proc.launcher} is not an executable file", err)
        stop.assert_not_called()
        start.assert_not_called()

    def test_missing_setsid_program_is_reported_before_the_ide_stops(self):
        proc = self.proc()
        proc.env["PATH"] = "/nonexistent"
        err, stop, _ = self.switch(proc, answers(projects(FIX)))
        self.assertEqual("cannot restart goland: no `setsid` program on the PATH of the IDE process", err)
        stop.assert_not_called()

    def test_start_error_is_returned_with_the_start_command(self):
        proc = self.proc()
        err, _, _ = self.switch(proc, answers(projects(FIX)), start=OSError("no memory"))
        self.assertEqual(f"cannot start goland: no memory. Start command: {proc.launcher} serverMode", err)


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
