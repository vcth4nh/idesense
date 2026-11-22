"""Unit tests of live-test/run.py, the entry command: each test starts it as a process. No test calls an IDE."""
import os
import subprocess
import sys
import unittest

RUN = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "run.py"))


def entry(*argv):
    proc = subprocess.run([sys.executable, "-B", RUN, *argv], capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


class EntryTest(unittest.TestCase):
    def test_options_run_the_suites(self):
        code, out, err = entry("--help")
        self.assertEqual(0, code, err)
        self.assertTrue(out.startswith("usage: run.py [-h] [--suite "), out[:80])

    def test_a_package_and_a_module_run_the_module(self):
        code, out, err = entry("audit", "verdict", "-h")
        self.assertEqual(0, code, err)
        self.assertTrue(out.startswith("usage: python3 -m audit.verdict "), out[:80])

    def test_a_package_with_no_module_prints_one_usage_line(self):
        for argv, modules in ((("audit", "nosuchmodule"), "callers, symbols, verdict"),
                              (("audit", "-h"), "callers, symbols, verdict"),
                              (("audit", "tests"), "callers, symbols, verdict"),
                              (("bench",), "build, claude_code, images, planfile, proxy, qfiles, runner, score, "
                                           "sets, triage")):
            with self.subTest(argv):
                code, out, err = entry(*argv)
                self.assertEqual((2, ""), (code, out), err)
                self.assertEqual(1, len(err.splitlines()), err)
                self.assertIn(f"./run.py {argv[0]} <module> [args]", err)
                self.assertIn(modules, err)
                self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
