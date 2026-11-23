"""Unit tests of ide/bench-ide.sh: the argument and guard logic, without an IDE.

Each test points BENCH_ROOT, BENCH_APPS and HOME at a temporary folder with a fake app (a launcher
that only writes a marker file) and puts a fake `ss` first on PATH. No test launches a real IDE,
reads the fleet config, or calls a port. The tests of the files that start writes use `prepare`,
which does each step of start before the launch.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
import zipfile

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ide", "bench-ide.sh")


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, mode)


def script_code_lines():
    with open(SCRIPT, encoding="utf-8") as f:
        return [line for line in f.read().splitlines() if not line.lstrip().startswith("#")]


class BenchIdeTestCase(unittest.TestCase):
    def setUp(self):
        # A short path: the script refuses an IDE path of more than 60 characters.
        tmp = tempfile.TemporaryDirectory(dir="/tmp", prefix="bide")
        self.addCleanup(tmp.cleanup)
        self.tmp = os.path.realpath(tmp.name)
        self.root = os.path.join(self.tmp, "bench")
        self.apps = os.path.join(self.tmp, "apps")
        # The data root is below HOME, as the default $HOME/dev/idesense-bench.
        self.home = self.tmp
        self.marker = os.path.join(self.tmp, "launched")
        app = os.path.join(self.apps, "goland")
        write(os.path.join(app, "product-info.json"), '{"dataDirectoryName": "GoLand2026.2"}\n')
        write(os.path.join(app, "bin", "goland64.vmoptions"), "-Xms128m\n-Xmx2048m")
        write(os.path.join(app, "bin", "goland.sh"),
              '#!/bin/sh\n# reads $GOLAND_VM_OPTIONS and $USER_VM_OPTIONS_FILE\n'
              'echo "$@" > "%s"\n' % self.marker, 0o755)
        fleet_plugins = os.path.join(self.home, ".local", "share", "JetBrains", "GoLand2026.2")
        for name in ("mise", "idesense"):
            write(os.path.join(fleet_plugins, name, "lib", "x.jar"), "")
        write(os.path.join(self.home, ".config", "JetBrains", "GoLand2026.2", "options", "other.xml"),
              "<application />\n")
        self.fake_bin = os.path.join(self.tmp, "fakebin")
        write(os.path.join(self.fake_bin, "ss"), "#!/bin/sh\nexit 0\n", 0o755)
        # No test reaches the systemd of the machine: the probe of this fake says "no scope".
        write(os.path.join(self.fake_bin, "systemd-run"), "#!/bin/sh\nexit 1\n", 0o755)
        self.project = os.path.join(self.root, "trees", "p")
        os.makedirs(self.project)
        os.makedirs(os.path.join(self.root, "ide"))
        self.ide_dir = os.path.join(self.root, "ide", "goland")

    def run_script(self, *args, **extra_env):
        env = dict(os.environ)
        env.pop("BENCH_IDE_XMX", None)
        env.update(BENCH_ROOT=self.root, BENCH_APPS=self.apps, HOME=self.home,
                   PATH=self.fake_bin + os.pathsep + env["PATH"],
                   BENCH_PLUGIN_ZIP=os.path.join(self.tmp, "missing.zip"))
        env.update(extra_env)
        return subprocess.run(["bash", SCRIPT, *args], env=env, capture_output=True, text=True,
                              timeout=60)

    def assert_not_launched(self):
        self.assertFalse(os.path.exists(self.marker), "the launcher ran")


class GuardTest(BenchIdeTestCase):
    def test_start_refuses_fleet_port(self):
        for port in ("29170", "29174", "29178"):
            for command in ("start", "prepare", "dry-run", "status", "stop"):
                with self.subTest(port=port, command=command):
                    r = self.run_script(command, "goland", self.project, BENCH_PORT=port)
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertIn("fleet port", r.stderr)
        self.assert_not_launched()
        self.assertFalse(os.path.exists(self.ide_dir))

    def test_start_refuses_path_outside_bench(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        os.symlink(outside, self.ide_dir)
        for command in ("start", "dry-run"):
            with self.subTest(command=command):
                r = self.run_script(command, "goland", self.project)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("not below " + os.path.join(self.root, "ide") + "/", r.stderr)
        self.assert_not_launched()
        self.assertEqual(os.listdir(outside), [])

    def test_start_refuses_project_outside_trees(self):
        elsewhere = os.path.join(self.tmp, "elsewhere", "p")
        os.makedirs(elsewhere)
        link = os.path.join(self.root, "trees", "link")
        os.symlink(elsewhere, link)
        cases = {
            "outside": [elsewhere],
            "symlink out of trees": [link],
            "absent": [os.path.join(self.root, "trees", "absent")],
            "trees itself": [os.path.join(self.root, "trees")],
            "one bad of two": [self.project, elsewhere],
            "none": [],
        }
        for name, projects in cases.items():
            with self.subTest(name):
                r = self.run_script("start", "goland", *projects)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("project", r.stderr)
        self.assert_not_launched()
        self.assertFalse(os.path.exists(self.ide_dir))


class DryRunTest(BenchIdeTestCase):
    def test_dry_run_prints_the_four_paths(self):
        syntax = subprocess.run(["bash", "-n", SCRIPT], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        second = os.path.join(self.root, "trees", "q")
        os.makedirs(second)
        def all_paths():
            return sorted(os.path.join(d, n) for d, ds, fs in os.walk(self.tmp) for n in ds + fs)
        before = all_paths()
        r = self.run_script("dry-run", "goland", self.project, second)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for key in ("config", "system", "plugins", "log"):
            self.assertIn("-Didea.%s.path=%s/%s\n" % (key, self.ide_dir, key), r.stdout)
        self.assertIn(os.path.join(self.apps, "goland", "bin", "goland.sh"), r.stdout)
        self.assertIn("GOLAND_VM_OPTIONS", r.stdout)
        self.assertIn(os.path.join(self.ide_dir, "ide.vmoptions"), r.stdout)
        self.assertIn("29374", r.stdout)
        self.assertIn("  %s\n  %s\n" % (self.project, second), r.stdout)
        command = [line for line in r.stdout.splitlines() if line.startswith("command:")]
        self.assertEqual(len(command), 1, r.stdout)
        self.assertRegex(command[0], r"/goland\.sh serverMode > ")
        self.assertNotIn(os.path.join(self.root, "trees"), command[0])
        fleet_plugins = os.path.join(self.home, ".local", "share", "JetBrains", "GoLand2026.2")
        self.assertIn(os.path.join(fleet_plugins, "mise"), r.stdout)
        self.assertNotIn(os.path.join(fleet_plugins, "idesense"), r.stdout)
        self.assertIn("missing.zip is absent: start refuses", r.stdout)
        self.assert_not_launched()
        self.assertEqual(all_paths(), before, "dry-run made a folder or a file")

    def test_defaults_are_below_home(self):
        root = os.path.join(self.home, "dev", "idesense-bench")
        slot = os.path.join(self.home, "dev", "ws", "3e9c", "caddy")
        os.makedirs(slot)
        project = os.path.join(root, "trees", "p")
        os.makedirs(project)
        apps = os.path.join(self.home, ".local", "share", "JetBrains", "Toolbox", "apps")
        os.makedirs(os.path.dirname(apps), exist_ok=True)
        os.rename(self.apps, apps)
        r = self.run_script("dry-run", "goland", project, slot, BENCH_ROOT="", BENCH_SLOTS="", BENCH_APPS="")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("-Didea.config.path=%s/ide/goland/config\n" % root, r.stdout)
        self.assertIn(os.path.join(apps, "goland", "bin", "goland.sh"), r.stdout)
        self.assertIn("  %s\n  %s\n" % (project, slot), r.stdout)

    def test_dry_run_refuses_a_listening_port(self):
        write(os.path.join(self.fake_bin, "ss"),
              "#!/bin/sh\necho 'LISTEN 0 511 127.0.0.1:29374 0.0.0.0:*'\n", 0o755)
        r = self.run_script("dry-run", "goland", self.project)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("listens", r.stderr)


class ScopeTest(BenchIdeTestCase):
    """start launches the IDE in a systemd scope of its own when the probe of systemd-run exits 0."""

    PROBE = "call [--user] [--scope] [--quiet] [--collect] [--] [true] 0=/dev/null 1=/dev/null 2=/dev/null"

    def fake_systemd_run(self, code):
        """A fake systemd-run first on PATH: it exits with code and writes one line for each call (its arguments
        and the targets of its stdin, stdout and stderr) to the returned file."""
        record = os.path.join(self.tmp, "systemd-run.calls")
        write(os.path.join(self.fake_bin, "systemd-run"),
              '#!/bin/sh\nfds=""\nfor fd in 0 1 2; do fds="$fds $fd=$(readlink /proc/$$/fd/$fd)"; done\n'
              '{ printf call; printf " [%%s]" "$@"; echo "$fds"; } >> "%s"\nexit %d\n' % (record, code), 0o755)
        return record

    def dry_run(self, code):
        record = self.fake_systemd_run(code)
        r = self.run_script("dry-run", "goland", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        command = [line for line in r.stdout.splitlines() if line.startswith("command:")]
        self.assertEqual(len(command), 1, r.stdout)
        with open(record, encoding="utf-8") as f:
            self.assertEqual([self.PROBE], f.read().splitlines(), "the probe is one call with these arguments")
        self.assert_not_launched()
        return command[0]

    def test_dry_run_prints_the_scope_prefix_when_the_probe_exits_0(self):
        command = self.dry_run(0)
        self.assertTrue(command.startswith(
            "command:        systemd-run --user --scope --quiet --collect -- env GOLAND_VM_OPTIONS="), command)
        self.assertRegex(command, r"/goland\.sh serverMode > ")

    def test_dry_run_prints_the_plain_launch_when_the_probe_exits_1(self):
        command = self.dry_run(1)
        self.assertTrue(command.startswith("command:        env GOLAND_VM_OPTIONS="), command)
        self.assertNotIn("systemd-run", command)
        self.assertRegex(command, r"/goland\.sh serverMode > ")


class PrepareTest(BenchIdeTestCase):
    """`prepare` does each step of start before the launch; the tests read the files that it writes."""

    def prepare(self, *names):
        dirs = []
        for name in names:
            d = os.path.join(self.root, "trees", name)
            os.makedirs(d, exist_ok=True)
            dirs.append(d)
        zip_path = os.path.join(self.tmp, "plugin.zip")
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("idesense/lib/idesense.jar", "")
        r = self.run_script("prepare", "goland", *dirs, BENCH_PLUGIN_ZIP=zip_path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_not_launched()
        return dirs

    def options(self, name):
        return ET.parse(os.path.join(self.ide_dir, "config", "options", name)).getroot()

    def key(self, path):
        self.assertTrue(path.startswith(self.home + "/"))
        return "$USER_HOME$" + path[len(self.home):]

    def recent(self):
        """[(key, attributes of RecentProjectMetaInfo, attributes of its frame children)] in file order."""
        root = self.options("recentProjects.xml")
        self.assertEqual(root.tag, "application")
        entries = root.findall("component[@name='RecentProjectsManager']/option[@name='additionalInfo']/map/entry")
        found = []
        for e in entries:
            metas = e.findall("value/RecentProjectMetaInfo")
            self.assertEqual(len(metas), 1, e.get("key"))
            found.append((e.get("key"), metas[0].attrib, [f.attrib for f in metas[0].findall("frame")]))
        return found

    def expected_recent(self, dirs):
        # GoLand 2026.2 opens all projects only when each entry has a frame element.
        return [(self.key(d), {"opened": "true"},
                 [{"x": str(60 + 30 * i), "y": str(60 + 30 * i), "width": "1400", "height": "1000"}])
                for i, d in enumerate(dirs)]

    def test_start_writes_recent_projects_for_each_dir(self):
        dirs = self.prepare("p", "a", "b", "c")
        self.assertEqual(self.recent(), self.expected_recent(dirs))
        # The file is new at each start: a project of an earlier start is not open again.
        dirs = self.prepare("b", "q")
        self.assertEqual(self.recent(), self.expected_recent(dirs))
        plugins = sorted(os.listdir(os.path.join(self.ide_dir, "plugins")))
        self.assertEqual(plugins, ["idesense", "mise"])
        self.assertTrue(os.path.exists(os.path.join(self.ide_dir, "plugins", "idesense", "lib", "idesense.jar")))
        with open(os.path.join(self.ide_dir, "ide.vmoptions"), encoding="utf-8") as f:
            self.assertIn("-Didea.system.path=%s/system\n" % self.ide_dir, f.read())

    def test_start_writes_trust_entries(self):
        dirs = self.prepare("p", "q")
        root = self.options("trusted-paths.xml")
        settings = root.findall(
            "component[@name='Trusted.Paths.Settings']/option[@name='TRUSTED_PATHS']/list/option")
        self.assertEqual([o.get("value") for o in settings], [os.path.join(self.root, "trees")])
        entries = root.findall("component[@name='Trusted.Paths']/option[@name='TRUSTED_PROJECT_PATHS']/map/entry")
        self.assertEqual({e.get("key"): e.get("value") for e in entries}, {self.key(d): "true" for d in dirs})
        # A second start keeps one entry for each dir and adds the new dir.
        dirs += self.prepare("p", "r")[1:]
        root = self.options("trusted-paths.xml")
        entries = root.findall("component[@name='Trusted.Paths']/option[@name='TRUSTED_PROJECT_PATHS']/map/entry")
        self.assertEqual(sorted(e.get("key") for e in entries), sorted(self.key(d) for d in dirs))
        self.assertTrue(all(e.get("value") == "true" for e in entries))


class HeapTest(BenchIdeTestCase):
    """BENCH_IDE_XMX gives the last line -Xmx<value> of the vmoptions file of the instance (default 4096m)."""

    def zip(self):
        path = os.path.join(self.tmp, "plugin.zip")
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("idesense/lib/idesense.jar", "")
        return path

    def vmoptions(self, **env):
        r = self.run_script("prepare", "goland", self.project, BENCH_PLUGIN_ZIP=self.zip(), **env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_not_launched()
        with open(os.path.join(self.ide_dir, "ide.vmoptions"), encoding="utf-8") as f:
            return f.read().splitlines()

    def test_default_heap_is_the_last_line(self):
        lines = self.vmoptions()
        self.assertEqual(["-Xms128m", "-Xmx2048m"], lines[:2], "the copy of the options file of the install")
        self.assertEqual("-Xmx4096m", lines[-1])
        r = self.run_script("dry-run", "goland", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("  -Xmx4096m\n", r.stdout)

    def test_heap_comes_from_the_variable(self):
        self.assertEqual("-Xmx6g", self.vmoptions(BENCH_IDE_XMX="6g")[-1])
        r = self.run_script("dry-run", "goland", self.project, BENCH_IDE_XMX="8192m")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("  -Xmx8192m\n", r.stdout)
        self.assertNotIn("-Xmx4096m", r.stdout)

    def test_bad_heap_value_is_refused_before_any_change(self):
        zip_path = self.zip()
        for value in ("4096", "4G", "-Xmx4g", "4g ", "4g\n-Xms1g", "m"):
            for command in ("start", "prepare", "dry-run"):
                with self.subTest(value=value, command=command):
                    r = self.run_script(command, "goland", self.project, BENCH_IDE_XMX=value,
                                        BENCH_PLUGIN_ZIP=zip_path)
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertIn("BENCH_IDE_XMX", r.stderr)
                    self.assertIn("refused", r.stderr)
        self.assert_not_launched()
        self.assertFalse(os.path.exists(self.ide_dir))


class SlotsRootTest(BenchIdeTestCase):
    """A project dir below the slots root (BENCH_SLOTS) is accepted as one below BENCH_ROOT/trees/."""

    def setUp(self):
        super().setUp()
        self.slots = os.path.join(self.tmp, "ws")
        self.slot = os.path.join(self.slots, "3e9c", "caddy")
        os.makedirs(self.slot)
        self.zip_path = os.path.join(self.tmp, "plugin.zip")
        with zipfile.ZipFile(self.zip_path, "w") as z:
            z.writestr("idesense/lib/idesense.jar", "")

    def key(self, path):
        return "$USER_HOME$" + path[len(self.home):]

    def trust(self):
        root = ET.parse(os.path.join(self.ide_dir, "config", "options", "trusted-paths.xml")).getroot()
        paths = [o.get("value") for o in root.findall(
            "component[@name='Trusted.Paths.Settings']/option[@name='TRUSTED_PATHS']/list/option")]
        entries = root.findall("component[@name='Trusted.Paths']/option[@name='TRUSTED_PROJECT_PATHS']/map/entry")
        return paths, {e.get("key"): e.get("value") for e in entries}

    def test_bench_ide_accepts_project_below_slots_root(self):
        r = self.run_script("dry-run", "goland", self.project, self.slot, BENCH_SLOTS=self.slots)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("  %s\n  %s\n" % (self.project, self.slot), r.stdout)
        self.assertFalse(os.path.exists(self.ide_dir))

        r = self.run_script("prepare", "goland", self.slot, self.project, BENCH_SLOTS=self.slots,
                            BENCH_PLUGIN_ZIP=self.zip_path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_not_launched()
        recent = ET.parse(os.path.join(self.ide_dir, "config", "options", "recentProjects.xml")).getroot()
        keys = [e.get("key") for e in recent.findall(".//option[@name='additionalInfo']/map/entry")]
        self.assertEqual([self.key(self.slot), self.key(self.project)], keys)
        # The trust file covers the slots root, and has an entry for each project dir.
        paths, entries = self.trust()
        self.assertEqual([os.path.join(self.root, "trees"), self.slots], paths)
        self.assertEqual({self.key(self.slot): "true", self.key(self.project): "true"}, entries)

        # A second start keeps one entry for the slots root.
        second = os.path.join(self.slots, "153a", "caddy")
        os.makedirs(second)
        r = self.run_script("prepare", "goland", second, BENCH_SLOTS=self.slots, BENCH_PLUGIN_ZIP=self.zip_path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        paths, entries = self.trust()
        self.assertEqual([os.path.join(self.root, "trees"), self.slots], paths)
        self.assertEqual({self.key(d): "true" for d in (self.slot, self.project, second)}, entries)
        self.assert_not_launched()

    def test_bench_ide_refuses_project_outside_both_roots(self):
        elsewhere = os.path.join(self.tmp, "elsewhere", "p")
        os.makedirs(elsewhere)
        link = os.path.join(self.slots, "link")
        os.symlink(elsewhere, link)
        cases = {
            "outside both roots": ([elsewhere], self.slots),
            "symlink out of the slots root": ([link], self.slots),
            "slots root itself": ([self.slots], self.slots),
            "absent below the slots root": ([os.path.join(self.slots, "absent")], self.slots),
            "one bad of two": ([self.slot, elsewhere], self.slots),
            # An empty BENCH_SLOTS gives the default $HOME/dev/ws, and the slot is not below it.
            "below another slots root": ([self.slot], ""),
        }
        for name, (projects, slots) in cases.items():
            for command in ("start", "prepare", "dry-run"):
                with self.subTest(name, command=command):
                    r = self.run_script(command, "goland", *projects, BENCH_SLOTS=slots,
                                        BENCH_PLUGIN_ZIP=self.zip_path)
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertIn("project dir", r.stderr)
                    self.assertIn("refused", r.stderr)
        self.assert_not_launched()
        self.assertFalse(os.path.exists(self.ide_dir))


class StopTest(BenchIdeTestCase):
    def sleeper(self, *extra):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", *extra])
        self.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait()))
        return p

    def write_pid_file(self, pid):
        write(os.path.join(self.ide_dir, "pid"), "%d\n" % pid)

    def test_stop_uses_recorded_pid_only(self):
        with open(SCRIPT, encoding="utf-8") as f:
            whole = f.read()
        self.assertNotIn("pkill", whole)
        self.assertNotIn("killall", whole)
        mark = os.path.join(self.ide_dir, "system")
        recorded = self.sleeper(mark)
        other = self.sleeper(mark)
        self.write_pid_file(recorded.pid)
        r = self.run_script("stop", "goland")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(recorded.wait(timeout=10), -15)
        self.assertIsNone(other.poll(), "stop signalled a pid that is not in the pid file")
        self.assertFalse(os.path.exists(os.path.join(self.ide_dir, "pid")))

    def test_guard_never_signals_a_foreign_pid(self):
        kill = re.compile(r"(^|[\s;&|(])kill\s")
        lines = [line for line in script_code_lines() if kill.search(line)]
        self.assertTrue(lines, "the script has no kill")
        for line in lines:
            before = line[:kill.search(line).end()]
            self.assertRegex(before, r'\b(ours_by_(cmdline|launch)|recorded_child) "\$\w+"( "\$\w+")? && kill\s$', line)
        code = "\n".join(script_code_lines())
        for name in ("ours_by_cmdline", "ours_by_launch"):
            body = re.search(r"^%s\(\) \{\n(.*?)\n\}" % name, code, re.S | re.M)
            self.assertIsNotNone(body, name)
            self.assertIn('/proc/$1/cmdline', body.group(1), name)
        foreign = self.sleeper()
        self.write_pid_file(foreign.pid)
        r = self.run_script("stop", "goland")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        time.sleep(0.5)
        self.assertIsNone(foreign.poll(), "stop signalled a foreign pid")

    def fake_ide(self, *extra):
        """A fake IDE with one child named dbus-monitor, one child of another name, and a free
        dbus-monitor that is no child of it. Returns the IDE, the three children and the free one."""
        # A script with this file name: Linux names its process after the file, with no renamed system program.
        name = os.path.join(self.tmp, "dbus-monitor")
        write(name, "#!%s\nimport time\ntime.sleep(60)\n" % sys.executable, 0o755)
        spare = os.path.join(self.tmp, "other-child")
        write(spare, "#!%s\nimport time\ntime.sleep(60)\n" % sys.executable, 0o755)
        code = ("import subprocess, sys, time\n"
                "a = subprocess.Popen([sys.argv[1]]); b = subprocess.Popen([sys.argv[2]])\n"
                "print(a.pid, b.pid, flush=True); time.sleep(60)\n")
        mark = os.path.join(self.ide_dir, "system")
        ide = subprocess.Popen([sys.executable, "-c", code, name, spare, mark], stdout=subprocess.PIPE, text=True)
        free = subprocess.Popen([name])
        self.addCleanup(lambda: (free.poll() is None and free.kill(), free.wait()))
        mon, other = map(int, ide.stdout.readline().split())
        for pid in (mon, other):
            self.addCleanup(lambda pid=pid: os.path.exists("/proc/%d" % pid) and os.kill(pid, 9))
        self.addCleanup(lambda: (ide.poll() is None and ide.kill(), ide.wait()))
        self.write_pid_file(ide.pid)
        return ide, mon, other, free

    def gone(self, pid):
        for _ in range(50):
            try:
                with open("/proc/%d/stat" % pid) as f:
                    if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                        return True
            except OSError:
                return True
            time.sleep(0.1)
        return False

    def test_stop_ends_the_dbus_monitor_child_of_the_ide_only(self):
        ide, mon, other, free = self.fake_ide()
        for pid, comm in ((mon, "dbus-monitor"), (free.pid, "dbus-monitor"), (other, "other-child")):
            with open("/proc/%d/comm" % pid) as f:
                self.assertEqual(f.read().strip(), comm, "the setup of the test is wrong")
        r = self.run_script("stop", "goland")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(ide.wait(timeout=10), -15)
        self.assertTrue(self.gone(mon), "the dbus-monitor child of the IDE still runs")
        self.assertTrue(os.path.exists("/proc/%d" % other), "a child of another name got a signal")
        self.assertIsNone(free.poll(), "a dbus-monitor that is no child of the IDE got a signal")


if __name__ == "__main__":
    unittest.main()
