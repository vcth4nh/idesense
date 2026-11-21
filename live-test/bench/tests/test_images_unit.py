import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

from bench import images as image
from common import trees

HERE = os.path.dirname(os.path.abspath(__file__))
ENTRY = os.path.join(HERE, "..", "image", "entry.sh")
RULE_GOLAND = ("IMPORTANT: When applicable, prefer using goland-idesense MCP tools for code navigation "
               "and refactoring.\n")
# The stand-in for `claude`: it writes its folder, its arguments and the names of its environment.
FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_CLAUDE_LOG"], "w", encoding="utf-8") as f:
    json.dump({"cwd": os.getcwd(), "argv": sys.argv[1:], "env": sorted(os.environ)}, f)
"""
SLOTS = ("a1b2", "c3d4", "e5f6")


def write(root, rel, text, mode=0o644):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, mode)


def files_below(root):
    found = []
    for dirpath, _, names in os.walk(root):
        for name in names:
            found.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(found)


class TmpTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name


class ContextTest(TmpTestCase):
    def test_context_leaves_out_instruction_files(self):
        tree = os.path.join(self.tmp, "tree")
        left_out = ["CLAUDE.md", "docs/AGENTS.md", "GEMINI.md", "pkg/sub/CLAUDE.md", ".claude/x",
                    ".claude/skills/s/SKILL.md", ".idea/y", ".venv/z", ".cursor/rules/r.mdc", ".cursorrules",
                    ".github/copilot-instructions.md", "sub/.claude/settings.json"]
        kept = ["main.go", "docs/guide.md", ".github/workflows/ci.yml", ".gitignore"]
        for rel in left_out + kept:
            write(tree, rel, f"text of {rel}\n")
        manifest = os.path.join(self.tmp, "tree.manifest")
        trees.write_manifest(tree, left_out + kept, manifest)
        dst = os.path.join(self.tmp, "ctx", "tree")

        copied = image.copy_context_tree(tree, manifest, dst)

        self.assertEqual(sorted(kept), sorted(copied))
        self.assertEqual(sorted(kept), files_below(dst))
        for rel in left_out:
            self.assertTrue(image.left_out(rel), rel)
        for rel in kept:
            self.assertFalse(image.left_out(rel), rel)

    def test_context_uses_manifest_files_only(self):
        tree = os.path.join(self.tmp, "tree")
        write(tree, "a.txt", "alpha\n")
        write(tree, "run.sh", "#!/bin/sh\n", 0o755)
        write(tree, "sub/م.txt", "beta\n")
        write(tree, "extra.txt", "not in the manifest\n")
        write(tree, "build/out.bin", "made after the manifest\n")
        manifest = os.path.join(self.tmp, "tree.manifest")
        trees.write_manifest(tree, ["a.txt", "run.sh", "sub/م.txt"], manifest)
        dst = os.path.join(self.tmp, "ctx", "tree")

        copied = image.copy_context_tree(tree, manifest, dst)

        self.assertEqual(["a.txt", "run.sh", "sub/م.txt"], sorted(copied))
        self.assertEqual(["a.txt", "run.sh", "sub/م.txt"], files_below(dst))
        self.assertEqual(0o755, stat.S_IMODE(os.stat(os.path.join(dst, "run.sh")).st_mode))
        with open(os.path.join(dst, "sub/م.txt"), encoding="utf-8") as f:
            self.assertEqual("beta\n", f.read())

    def test_context_refuses_file_that_differs_from_manifest(self):
        tree = os.path.join(self.tmp, "tree")
        write(tree, "a.txt", "alpha\n")
        manifest = os.path.join(self.tmp, "tree.manifest")
        trees.write_manifest(tree, ["a.txt"], manifest)
        write(tree, "a.txt", "alpha, changed\n")

        with self.assertRaises(RuntimeError):
            image.copy_context_tree(tree, manifest, os.path.join(self.tmp, "ctx", "tree"))

    def test_context_puts_each_tree_at_its_slot_path(self):
        masters = os.path.join(self.tmp, "masters")
        slots = {}
        for n, tree in enumerate(image.tree_names("caddy")):
            write(masters, f"{tree}/main.go", f"package main // {tree}\n")
            write(masters, f"{tree}/AGENTS.md", "instructions\n")
            trees.write_manifest(os.path.join(masters, tree), ["main.go", "AGENTS.md"],
                                 os.path.join(masters, tree + ".manifest"))
            slots[tree] = {"slot": f"{n}0aa", "path": f"{trees.SLOTS_ROOT}/{n}0aa/caddy", "product": "caddy"}
        ctx = os.path.join(self.tmp, "ctx")

        image.make_context("caddy", ctx, masters, slots)

        self.assertEqual(["00aa", "10aa", "20aa", "30aa"], sorted(os.listdir(os.path.join(ctx, "ws"))))
        for n, tree in enumerate(image.tree_names("caddy")):
            self.assertEqual(["main.go"], files_below(os.path.join(ctx, "ws", f"{n}0aa", "caddy")), tree)
        self.assertEqual(["Dockerfile", "aids", "entry.sh", "ws"], sorted(os.listdir(ctx)))
        self.assertEqual({tree: {"slot": e["slot"], "path": e["path"]} for tree, e in slots.items()},
                         image.image_slots("caddy", slots))


class EntryTest(TmpTestCase):
    def setUp(self):
        super().setUp()
        self.init = os.path.join(self.tmp, "home", ".init")
        os.makedirs(self.init)
        self.entry = os.path.join(self.init, "entry.sh")
        shutil.copy2(ENTRY, self.entry)
        image.write_aids(os.path.join(self.init, "aids"), "goland-idesense")
        self.ws = os.path.join(self.tmp, "ws")
        for slot in SLOTS:
            write(self.ws, f"{slot}/caddy/main.go", f"package main // {slot}\n")
        self.tree = os.path.join(self.ws, SLOTS[0], "caddy")
        bin_dir = os.path.join(self.tmp, "bin")
        write(bin_dir, "claude", FAKE_CLAUDE, 0o755)
        self.path = f"{bin_dir}:/usr/bin:/bin"
        self.log = os.path.join(self.tmp, "claude.json")

    def run_entry(self, env, args=(), entry=None):
        full = {"PATH": self.path, "BENCH_SLOTS_ROOT": self.ws, "BENCH_INIT": self.init,
                "FAKE_CLAUDE_LOG": self.log, **env}
        return subprocess.run([entry or self.entry, *args], env=full, capture_output=True, text=True, timeout=30)

    def claude_call(self):
        with open(self.log, encoding="utf-8") as f:
            return json.load(f)

    def assert_nothing_removed(self, label):
        self.assertFalse(os.path.exists(self.log), label)
        self.assertEqual(sorted(SLOTS), sorted(os.listdir(self.ws)), label)
        self.assertTrue(os.path.exists(self.entry), label)

    def assert_started_in_slot(self, args):
        call = self.claude_call()
        self.assertEqual(self.tree, call["cwd"])
        self.assertEqual(list(args), call["argv"])
        self.assertEqual([], [name for name in call["env"] if name.startswith("BENCH")])
        self.assertEqual([SLOTS[0]], os.listdir(self.ws))
        self.assertFalse(os.path.lexists(self.init))

    def test_entry_refuses_unknown_slot(self):
        os.makedirs(os.path.join(self.ws, "0000"))
        for slot in ("nope", "", ".", "..", "zzzz", "A1B2", "a1b2/caddy", "../ws/a1b2", "a1b", "0000"):
            result = self.run_entry({"BENCH_SLOT": slot})
            self.assertEqual(2, result.returncode, slot)
            self.assertFalse(os.path.exists(self.log), slot)
            self.assertTrue(os.path.exists(self.entry), slot)
            self.assertEqual(sorted(SLOTS + ("0000",)), sorted(os.listdir(self.ws)), slot)
        os.rmdir(os.path.join(self.ws, "0000"))
        result = self.run_entry({})
        self.assertEqual(2, result.returncode)
        self.assert_nothing_removed("no BENCH_SLOT")

    def test_entry_refuses_unknown_aid(self):
        result = self.run_entry({"BENCH_SLOT": SLOTS[0], "BENCH_AID": "skills"})
        self.assertEqual(2, result.returncode)
        self.assert_nothing_removed("unknown aid")
        self.assertEqual(["main.go"], files_below(self.tree))

    def test_entry_refuses_to_run_outside_its_init_folder(self):
        result = self.run_entry({"BENCH_SLOT": SLOTS[0]}, entry=ENTRY)
        self.assertEqual(2, result.returncode)
        self.assert_nothing_removed("the script of the repository")

    def test_entry_installs_skill(self):
        args = ["-p", "two words", "--json-schema", '{"type": "object"}', ""]
        result = self.run_entry({"BENCH_SLOT": SLOTS[0], "BENCH_AID": "skill"}, args)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_started_in_slot(args)
        skill = os.path.join(self.tree, ".claude", "skills", "idesense")
        self.assertEqual(files_below(image.SKILL_SRC), files_below(skill))
        for rel in files_below(image.SKILL_SRC):
            with open(os.path.join(image.SKILL_SRC, rel), "rb") as a, open(os.path.join(skill, rel), "rb") as b:
                self.assertEqual(a.read(), b.read(), rel)
        self.assertFalse(os.path.exists(os.path.join(self.tree, "CLAUDE.md")))

    def test_entry_writes_rule(self):
        result = self.run_entry({"BENCH_SLOT": SLOTS[0], "BENCH_AID": "rule"}, ["--version"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_started_in_slot(["--version"])
        with open(os.path.join(self.tree, "CLAUDE.md"), encoding="utf-8") as f:
            self.assertEqual(RULE_GOLAND, f.read())
        self.assertFalse(os.path.exists(os.path.join(self.tree, ".claude")))

    def test_entry_default_aid_is_none(self):
        result = self.run_entry({"BENCH_SLOT": SLOTS[0], "BENCH_OTHER": "x"}, ["mcp", "list"])

        self.assertEqual(0, result.returncode, result.stderr)
        self.assert_started_in_slot(["mcp", "list"])
        self.assertEqual(["main.go"], files_below(self.tree))


class ParseTest(unittest.TestCase):
    GO_OUT = ("ok  \texample.com/a\t1.2s\n"
              "?   \texample.com/b\t[no test files]\n"
              "--- FAIL: TestX (0.00s)\n"
              "    --- FAIL: TestX/sub (0.00s)\n"
              "--- FAIL: TestY (0.01s)\n"
              "FAIL\n"
              "FAIL\texample.com/c\t0.3s\n"
              "ok  \texample.com/d\t(cached)\n"
              "--- FAIL: TestZ (0.00s)\n"
              "FAIL\n"
              "FAIL\texample.com/e\t0.1s\n")

    def test_go_test_counts(self):
        self.assertEqual({"ok": 2, "FAIL": 2}, image.go_test_counts(self.GO_OUT))

    def test_go_failed_packages(self):
        self.assertEqual([("example.com/c", ["TestX", "TestY"]), ("example.com/e", ["TestZ"])],
                         image.go_failed_packages(self.GO_OUT))

    def test_split_caddy_run(self):
        out = (self.GO_OUT + "@@gate rc 1\n"
               "@@gate rerun example.com/c\nok  \texample.com/c\t0.2s\n@@gate rerun-rc 0\n"
               "@@gate rerun example.com/e\n--- FAIL: TestZ (0.00s)\n")
        first, rc, reruns = image.split_caddy_run(out)
        self.assertEqual(self.GO_OUT, first)
        self.assertEqual(1, rc)
        self.assertEqual([("example.com/c", "ok  \texample.com/c\t0.2s\n", 0),
                          ("example.com/e", "--- FAIL: TestZ (0.00s)\n", 1)], reruns)
        self.assertEqual(("cut off", 1, []), image.split_caddy_run("cut off"))

    def test_caddy_flake_passes_and_two_failures_fail(self):
        expected = {"ok": 4, "FAIL": 0}
        out = (self.GO_OUT + "@@gate rc 1\n"
               "@@gate rerun example.com/c\nok  \texample.com/c\t0.2s\n@@gate rerun-rc 0\n"
               "@@gate rerun example.com/e\nok  \texample.com/e\t0.1s\n@@gate rerun-rc 0\n")
        ok, detail = image.caddy_tests_result(out, 0, expected)
        self.assertTrue(ok, detail)
        self.assertIn("4 ok, 0 FAIL", detail)
        self.assertIn("(flake: example.com/c, TestX, TestY) (flake: example.com/e, TestZ)", detail)

        out = (self.GO_OUT + "@@gate rc 1\n"
               "@@gate rerun example.com/c\nok  \texample.com/c\t0.2s\n@@gate rerun-rc 0\n"
               "@@gate rerun example.com/e\n--- FAIL: TestZ (0.00s)\nFAIL\texample.com/e\t0.1s\n@@gate rerun-rc 1\n")
        ok, detail = image.caddy_tests_result(out, 0, expected)
        self.assertFalse(ok, detail)
        self.assertIn("(failed two times: example.com/e, TestZ)", detail)

        clean = "ok  \texample.com/a\t1s\n@@gate rc 0\n"
        self.assertTrue(image.caddy_tests_result(clean, 0, {"ok": 1, "FAIL": 0})[0])
        self.assertFalse(image.caddy_tests_result(clean, 124, {"ok": 1, "FAIL": 0})[0])

    def test_pytest_counts(self):
        out = ("....F..s\n"
               "FAILED test/ui/commands/test_completion.py::CompletionTest::test_completion - AssertionError\n"
               "1 failed, 2680 passed, 164 skipped, 123 warnings, 8 subtests passed in 45.64s\n")
        self.assertEqual({"passed": 2680, "failed": 1, "skipped": 164, "errors": 0},
                         image.pytest_counts(out))
        self.assertEqual(["test/ui/commands/test_completion.py::CompletionTest::test_completion"],
                         image.pytest_failed(out))
        self.assertIsNone(image.pytest_counts("no summary line\n"))


if __name__ == "__main__":
    unittest.main()
