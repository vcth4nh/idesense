#!/usr/bin/env python3
"""Unit tests for fleet.py (no IDE contact). Run from live-test/."""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
