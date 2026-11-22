"""Unit tests of bench/build.py.

`version_of` runs in a real temporary git repository. The Gradle call and the calls of bench-ide.sh go to a fake
command runner, or (one test) to a fake `gradlew` script in a temporary folder. The data root (BENCH_ROOT) and the
slots file point into a temporary folder. No test runs Gradle, stops or starts an IDE, or calls a port.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from bench import build
from common import lock

VERSION = "2.1.1-bench.abc1234"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@localhost", "-c", "commit.gpgsign=false",
       "-c", "core.hooksPath=/dev/null"]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TempTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = os.path.realpath(tmp.name)
        self.data = os.path.join(self.tmp, "bench")
        env = mock.patch.dict(os.environ, {"BENCH_ROOT": self.data})
        env.start()
        self.addCleanup(env.stop)


class VersionTest(TempTestCase):
    """version_of in a temporary git repository with one commit."""

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.tmp, "repo")
        write(os.path.join(self.repo, "gradle.properties"), "pluginGroup = x\npluginVersion = 2.1.1\n")
        write(os.path.join(self.repo, "src", "a.kt"), "a\n")
        write(os.path.join(self.repo, "live-test", "x.py"), "x\n")
        write(os.path.join(self.repo, "docs", "d.md"), "d\n")
        write(os.path.join(self.repo, ".gitignore"), "build/\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "one")
        self.head = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.run(GIT + ["-C", self.repo, *args], check=True, capture_output=True, text=True).stdout

    def test_version_names_the_commit(self):
        self.assertRegex(self.head, r"^[0-9a-f]{40}$")
        self.assertEqual("2.1.1-bench." + self.head[:7], build.version_of(self.repo))

    def test_change_below_src_is_refused(self):
        cases = {
            "changed": lambda: write(os.path.join(self.repo, "src", "a.kt"), "b\n"),
            "staged": lambda: (write(os.path.join(self.repo, "src", "a.kt"), "b\n"), self.git("add", "src/a.kt")),
            "deleted": lambda: os.remove(os.path.join(self.repo, "src", "a.kt")),
            "moved to live-test": lambda: self.git("mv", "src/a.kt", "live-test/a.kt"),
            "gradle.properties": lambda: write(os.path.join(self.repo, "gradle.properties"), "pluginVersion = 9\n"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                change()
                with self.assertRaises(ValueError) as e:
                    build.version_of(self.repo)
                self.assertNotIn("\n", str(e.exception))
                self.assertIn("src/a.kt" if name != "gradle.properties" else "gradle.properties", str(e.exception))
                self.git("reset", "-q", "--hard")

    def test_change_below_live_test_and_docs_is_accepted(self):
        write(os.path.join(self.repo, "live-test", "x.py"), "y\n")
        write(os.path.join(self.repo, "docs", "d.md"), "e\n")
        self.git("add", "docs/d.md")
        self.assertEqual("2.1.1-bench." + self.head[:7], build.version_of(self.repo))

    def test_untracked_file_below_src_is_refused(self):
        write(os.path.join(self.repo, "src", "New.kt"), "n\n")
        with self.assertRaises(ValueError) as e:
            build.version_of(self.repo)
        self.assertNotIn("\n", str(e.exception))
        self.assertIn("src/New.kt", str(e.exception))

    def test_untracked_file_below_live_test_and_docs_is_accepted(self):
        write(os.path.join(self.repo, "live-test", "new", "y.py"), "y\n")
        write(os.path.join(self.repo, "docs", "new.md"), "n\n")
        self.assertEqual("2.1.1-bench." + self.head[:7], build.version_of(self.repo))

    def test_ignored_file_is_accepted(self):
        write(os.path.join(self.repo, "build", "distributions", "idesense-2.1.1.zip"), "zip")
        self.assertEqual("2.1.1-bench." + self.head[:7], build.version_of(self.repo))

    def test_message_names_five_paths_tracked_changes_first(self):
        write(os.path.join(self.repo, "src", "a.kt"), "b\n")
        for name in ("0.kt", "1.kt", "2.kt", "3.kt", "4.kt"):
            write(os.path.join(self.repo, "src", name), "n\n")
        with self.assertRaises(ValueError) as e:
            build.version_of(self.repo)
        message = str(e.exception)
        self.assertIn("6 file(s)", message)
        self.assertIn("src/a.kt, src/0.kt, src/1.kt, src/2.kt, src/3.kt, ...", message)
        self.assertNotIn("src/4.kt", message)

    def test_no_plugin_version_is_refused(self):
        write(os.path.join(self.repo, "gradle.properties"), "pluginGroup = x\n")
        self.git("commit", "-q", "-am", "two")
        with self.assertRaises(ValueError) as e:
            build.version_of(self.repo)
        self.assertIn("pluginVersion", str(e.exception))

    def test_folder_that_is_not_a_repository_is_refused(self):
        other = os.path.join(self.tmp, "plain")
        write(os.path.join(other, "gradle.properties"), "pluginVersion = 2.1.1\n")
        with self.assertRaises(ValueError):
            build.version_of(other)


class BuildTest(TempTestCase):
    """build with a fake command runner; the repository is a plain temporary folder."""

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.tmp, "repo")
        self.dist = os.path.join(self.repo, "build", "distributions")
        os.makedirs(self.dist)
        self.calls = []
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def gradle(self, code=0, writes=True):
        """A fake runner: records (command, cwd); writes the zip of the version of the command when writes."""
        def run(cmd, cwd=None):
            self.calls.append((cmd, cwd))
            version = cmd[-1].split("=", 1)[1]
            if writes:
                write(os.path.join(self.dist, f"idesense-{version}.zip"), "new " + version)
            return code
        return run

    def test_zip_path_is_below_the_data_root(self):
        self.assertEqual(os.path.join(self.data, "plugin", f"idesense-{VERSION}.zip"), build.zip_path(VERSION))

    def test_gradle_command_has_the_version_and_runs_in_the_repository(self):
        write(os.path.join(self.dist, "idesense-2.1.1-bench.0000000.zip"), "other version")
        path = build.build(self.repo, VERSION, self.gradle())
        self.assertEqual([(["./gradlew", "buildPlugin", f"-PpluginVersion={VERSION}"], self.repo)], self.calls)
        self.assertEqual(build.zip_path(VERSION), path)
        self.assertEqual("new " + VERSION, read(path))
        self.assertEqual([f"idesense-{VERSION}.zip"], os.listdir(os.path.dirname(path)))

    def test_existing_zip_gives_no_gradle_call(self):
        write(build.zip_path(VERSION), "old")
        self.assertEqual(build.zip_path(VERSION), build.build(self.repo, VERSION, self.gradle()))
        self.assertEqual([], self.calls)
        self.assertEqual("old", read(build.zip_path(VERSION)))

    def test_gradle_failure_leaves_no_zip(self):
        # A zip of the same version from an earlier Gradle run is in build/distributions: it is not copied.
        write(os.path.join(self.dist, f"idesense-{VERSION}.zip"), "stale")
        with self.assertRaises(build.BuildError) as e:
            build.build(self.repo, VERSION, self.gradle(code=1, writes=False))
        self.assertNotIn("\n", str(e.exception))
        self.assertIn("exit code 1", str(e.exception))
        self.assertEqual([], self.plugin_files())

    def plugin_files(self):
        folder = os.path.dirname(build.zip_path(VERSION))
        return os.listdir(folder) if os.path.isdir(folder) else []

    def test_no_zip_after_gradle_is_an_error(self):
        write(os.path.join(self.dist, "idesense-2.1.1-bench.0000000.zip"), "other version")
        with self.assertRaises(build.BuildError) as e:
            build.build(self.repo, VERSION, self.gradle(writes=False))
        self.assertIn(os.path.join(self.dist, f"idesense-{VERSION}.zip"), str(e.exception))
        self.assertEqual([], self.plugin_files())

    def test_failed_copy_leaves_no_partial_zip(self):
        def partial(src, dst, **kwargs):
            write(dst, "part")
            raise OSError("disk full")
        with mock.patch.object(build.shutil, "copyfile", partial):
            with self.assertRaises(build.BuildError) as e:
                build.build(self.repo, VERSION, self.gradle())
        self.assertIn("disk full", str(e.exception))
        self.assertEqual([], self.plugin_files())

    def test_interrupted_copy_leaves_no_zip_that_a_later_run_keeps(self):
        def interrupted(src, dst, **kwargs):
            write(dst, "part")
            raise KeyboardInterrupt
        with mock.patch.object(build.shutil, "copyfile", interrupted):
            with self.assertRaises(KeyboardInterrupt):
                build.build(self.repo, VERSION, self.gradle())
        self.assertFalse(os.path.exists(build.zip_path(VERSION)))
        self.assertEqual("new " + VERSION, read(build.build(self.repo, VERSION, self.gradle())))
        self.assertEqual(2, len(self.calls))

    def test_default_runner_runs_gradlew_of_the_repository(self):
        record = os.path.join(self.tmp, "gradlew.args")
        script = ('#!/bin/sh\npwd > "%s"\nprintf "%%s\\n" "$@" >> "%s"\nv="${2#-PpluginVersion=}"\n'
                  'echo "zip $v" > "build/distributions/idesense-$v.zip"\n' % (record, record))
        write(os.path.join(self.repo, "gradlew"), script)
        os.chmod(os.path.join(self.repo, "gradlew"), 0o755)
        path = build.build(self.repo, VERSION)
        self.assertEqual([self.repo, "buildPlugin", f"-PpluginVersion={VERSION}"], read(record).splitlines())
        self.assertEqual(f"zip {VERSION}\n", read(path))


class SlotsTestCase(TempTestCase):
    def setUp(self):
        super().setUp()
        self.slots_file = os.path.join(self.data, "trees", "slots.json")
        patch = mock.patch.object(build, "SLOTS_FILE", self.slots_file)
        patch.start()
        self.addCleanup(patch.stop)
        self.zip = build.zip_path(VERSION)

    def slots(self, *trees, make=True):
        """Write the slots file with an entry for each tree; make the slot folders when make."""
        entries = {}
        for i, tree in enumerate(trees):
            product = tree.split("-")[0]
            path = os.path.join(self.tmp, "ws", "%04x" % i, product)
            if make:
                os.makedirs(path)
            entries[tree] = {"slot": "%04x" % i, "path": path, "product": product}
        write(self.slots_file, json.dumps(entries))
        return {t: e["path"] for t, e in entries.items()}


class StartCommandsTest(SlotsTestCase):
    def test_each_tree_of_a_product_goes_to_the_command_of_its_ide(self):
        paths = self.slots("beets-plant-2", "caddy", "caddy-plant-1", "beets")
        self.assertEqual([
            ["env", f"BENCH_PLUGIN_ZIP={self.zip}", build.SCRIPT, "start", "goland",
             paths["caddy"], paths["caddy-plant-1"]],
            ["env", f"BENCH_PLUGIN_ZIP={self.zip}", build.SCRIPT, "start", "pycharm",
             paths["beets"], paths["beets-plant-2"]],
        ], build.start_commands(self.zip))
        self.assertTrue(os.path.isfile(build.SCRIPT))

    def test_ide_with_no_slot_is_an_error(self):
        self.slots("caddy", "caddy-plant-1")
        with self.assertRaises(ValueError) as e:
            build.start_commands(self.zip)
        self.assertIn("pycharm", str(e.exception))

    def test_no_slots_file_is_an_error(self):
        with self.assertRaises(ValueError) as e:
            build.start_commands(self.zip)
        self.assertIn("goland", str(e.exception))

    def test_absent_slot_folder_is_an_error(self):
        paths = self.slots("caddy", "beets")
        shutil.rmtree(paths["beets"])
        with self.assertRaises(ValueError) as e:
            build.start_commands(self.zip)
        self.assertIn(paths["beets"], str(e.exception))


class MainTest(SlotsTestCase):
    """The command line, with a fake command runner and a fixed version."""

    def setUp(self):
        super().setUp()
        self.paths = self.slots("caddy", "beets")
        patch = mock.patch.object(build, "version_of", return_value=VERSION)
        patch.start()
        self.addCleanup(patch.stop)
        self.calls = []
        self.lock_states = []  # for each call: the `what` of the lock holder, or None when the lock is free

    def lock_state(self):
        try:
            with lock.ide_lock("test"):
                return None
        except lock.Busy:
            return read(os.path.join(self.data, "state", "lock"))

    def main(self, argv, codes=None):
        codes = codes or {}

        def run(cmd, cwd=None):
            self.calls.append(cmd)
            state = self.lock_state()
            self.lock_states.append(state and json.loads(state)["what"])
            if cmd[0] == "./gradlew":
                write(os.path.join(cwd, "build", "distributions", f"idesense-{VERSION}.zip"), "zip")
            return codes.get(len(self.calls), 0)

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = build.main(argv, run)
        return code, out.getvalue(), err.getvalue()

    def test_build_prints_the_zip_path(self):
        code, out, err = self.main([])
        self.assertEqual((0, ""), (code, err))
        self.assertEqual(self.zip, out.splitlines()[-1])
        self.assertEqual("zip", read(self.zip))
        self.assertEqual([["./gradlew", "buildPlugin", f"-PpluginVersion={VERSION}"]], self.calls)
        self.assertEqual([None], self.lock_states, "a build with no -start takes no lock")

    def test_existing_zip_prints_its_path(self):
        write(build.zip_path(VERSION), "old")
        code, out, err = self.main([])
        self.assertEqual((0, "", []), (code, err, self.calls))
        self.assertEqual(self.zip, out.splitlines()[-1])

    def test_start_stops_and_starts_each_ide_under_the_lock(self):
        write(build.zip_path(VERSION), "zip")
        code, out, err = self.main(["-start"])
        self.assertEqual((0, ""), (code, err))
        self.assertEqual([
            [build.SCRIPT, "stop", "goland"],
            ["env", f"BENCH_PLUGIN_ZIP={self.zip}", build.SCRIPT, "start", "goland", self.paths["caddy"]],
            [build.SCRIPT, "stop", "pycharm"],
            ["env", f"BENCH_PLUGIN_ZIP={self.zip}", build.SCRIPT, "start", "pycharm", self.paths["beets"]],
        ], self.calls)
        self.assertEqual([f"bench.build -start {VERSION}"] * 4, self.lock_states)
        self.assertIn(self.zip, out.splitlines())

    def test_start_builds_under_the_lock(self):
        code, out, err = self.main(["-start"])
        self.assertEqual((0, ""), (code, err))
        self.assertEqual(["./gradlew", "buildPlugin", f"-PpluginVersion={VERSION}"], self.calls[0])
        self.assertEqual(5, len(self.calls))
        self.assertEqual([f"bench.build -start {VERSION}"] * 5, self.lock_states)

    def test_busy_lock_starts_nothing(self):
        with lock.ide_lock("bench.runner batch b1"):
            code, out, err = self.main(["-start"])
        self.assertEqual(2, code)
        self.assertEqual([], self.calls)
        self.assertEqual(1, len(err.splitlines()), err)
        self.assertIn("bench.runner batch b1", err)

    def test_no_slot_folder_is_an_error_before_the_build(self):
        os.rmdir(self.paths["beets"])
        code, out, err = self.main(["-start"])
        self.assertEqual(2, code)
        self.assertEqual([], self.calls)
        self.assertEqual(1, len(err.splitlines()), err)

    def test_change_in_the_repository_is_an_error_before_the_build(self):
        with mock.patch.object(build, "version_of", side_effect=ValueError("src/a.kt has a change")):
            code, out, err = self.main(["-start"])
        self.assertEqual((2, []), (code, self.calls))
        self.assertEqual("build: src/a.kt has a change\n", err)

    def test_gradle_failure_is_one_line_and_starts_nothing(self):
        code, out, err = self.main(["-start"], codes={1: 1})
        self.assertEqual(1, code)
        self.assertEqual([["./gradlew", "buildPlugin", f"-PpluginVersion={VERSION}"]], self.calls)
        self.assertEqual(1, len(err.splitlines()), err)
        self.assertFalse(os.path.exists(build.zip_path(VERSION)))

    def test_failed_stop_starts_nothing(self):
        write(build.zip_path(VERSION), "zip")
        code, out, err = self.main(["-start"], codes={1: 1})
        self.assertEqual(1, code)
        self.assertEqual([[build.SCRIPT, "stop", "goland"]], self.calls)
        self.assertEqual(1, len(err.splitlines()), err)
        self.assertIn("stop goland", err)

    def test_failed_start_stops_the_command(self):
        write(build.zip_path(VERSION), "zip")
        code, out, err = self.main(["-start"], codes={2: 1})
        self.assertEqual(1, code)
        self.assertEqual(2, len(self.calls))
        self.assertIn("start goland", err)


if __name__ == "__main__":
    unittest.main()
