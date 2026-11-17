"""Unit tests of ide/bench-ide.sh: the argument and guard logic, without an IDE.

Each test points BENCH_ROOT, BENCH_APPS and HOME at a temporary folder with a fake app (a launcher
that only writes a marker file) and puts a fake `ss` first on PATH. No test launches a real IDE,
reads the fleet config, or calls a port.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

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
        self.home = os.path.join(self.tmp, "home")
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
        self.project = os.path.join(self.root, "trees", "p")
        os.makedirs(self.project)
        os.makedirs(os.path.join(self.root, "ide"))
        self.ide_dir = os.path.join(self.root, "ide", "goland")

    def run_script(self, *args, **extra_env):
        env = dict(os.environ)
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
            for command in ("start", "dry-run", "status", "stop"):
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
        r = self.run_script("dry-run", "goland", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for key in ("config", "system", "plugins", "log"):
            self.assertIn("-Didea.%s.path=%s/%s\n" % (key, self.ide_dir, key), r.stdout)
        self.assertIn(os.path.join(self.apps, "goland", "bin", "goland.sh"), r.stdout)
        self.assertIn("GOLAND_VM_OPTIONS", r.stdout)
        self.assertIn(os.path.join(self.ide_dir, "ide.vmoptions"), r.stdout)
        self.assertIn("29374", r.stdout)
        self.assertIn(self.project, r.stdout)
        self.assertIn("serverMode", r.stdout)
        fleet_plugins = os.path.join(self.home, ".local", "share", "JetBrains", "GoLand2026.2")
        self.assertIn(os.path.join(fleet_plugins, "mise"), r.stdout)
        self.assertNotIn(os.path.join(fleet_plugins, "idesense"), r.stdout)
        self.assertIn("missing.zip is absent: start refuses", r.stdout)
        self.assert_not_launched()
        self.assertFalse(os.path.exists(self.ide_dir), "dry-run made a folder")

    def test_dry_run_refuses_a_listening_port(self):
        write(os.path.join(self.fake_bin, "ss"),
              "#!/bin/sh\necho 'LISTEN 0 511 127.0.0.1:29374 0.0.0.0:*'\n", 0o755)
        r = self.run_script("dry-run", "goland", self.project)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("listens", r.stderr)


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
            self.assertRegex(before, r'\bours_by_(cmdline|launch) "\$\w+" && kill\s$', line)
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


if __name__ == "__main__":
    unittest.main()
