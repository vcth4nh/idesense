"""Unit tests of bench/score.py, the standalone score script (standard library only)."""
import ast
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from bench import score

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(HERE, "..", "score.py"))
KEY = {"question": "q",
       "answer": {"required": ["a.go:3", "a.go:9"], "forbidden": ["b.go:1"], "not_counted": ["a.go:1"]}}


def write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


class ScoreTest(unittest.TestCase):
    def test_exact(self):
        s = score.score(KEY, {("a.go", 3), ("a.go", 9), ("a.go", 1)})
        self.assertEqual((s["tp"], s["fp"], s["miss"], s["ignored"], s["exact"]), (2, 0, 0, 1, True))

    def test_forbidden_and_unknown_lines_are_false_lines(self):
        s = score.score(KEY, {("a.go", 3), ("b.go", 1), ("c.go", 7)})
        self.assertEqual((s["tp"], s["fp"], s["miss"], s["exact"]), (1, 2, 1, False))

    def test_a_line_outside_the_tree_is_not_a_false_line(self):
        s = score.score(KEY, {("a.go", 3), ("a.go", 9), (".venv/x.py", 2)}, tree_files={"a.go", "b.go"})
        self.assertEqual((s["fp"], s["outside"], s["listed"], s["exact"]), (0, 1, 2, True))

    def test_parse_sites(self):
        sites, invalid = score.parse_sites(
            {"sites": ["a.go:3", "/r/t/a.go:9:4", "/other/a.go:1", "a.go", "../x.go:2", 7]}, "/r/t")
        self.assertEqual(sites, {("a.go", 3), ("a.go", 9)})
        self.assertEqual(len(invalid), 4)
        self.assertEqual(["/other/a.go:1", "a.go", "../x.go:2", "7"], invalid)

    def test_empty_required_gives_no_ratio(self):
        s = score.score({"answer": {"required": [], "forbidden": [], "not_counted": []}}, set())
        self.assertIsNone(s["recall"])
        self.assertTrue(s["exact"])

    def test_score_has_the_fields_of_run_json_in_order(self):
        s = score.score(KEY, {("a.go", 3), ("b.go", 1), (".venv/x.py", 2)}, {"a.go", "b.go"}, ["a.go:3-4", "x"])
        self.assertEqual({"tp": 1, "fp": 1, "miss": 1, "ignored": 0, "precision": 0.5, "recall": 0.5, "exact": False,
                          "invalid": 2, "outside": 1, "listed": 2}, s)
        self.assertEqual(["tp", "fp", "miss", "ignored", "precision", "recall", "exact", "invalid", "outside",
                          "listed"], list(s))

    def test_line_classes(self):
        self.assertEqual({("a.go", 3): "required", ("a.go", 9): "required", ("b.go", 1): "forbidden",
                          ("a.go", 1): "dnc"}, score.line_classes(KEY))
        self.assertEqual({("dir:x/a.go", 4): "required"},
                         score.line_classes({"answer": {"required": ["dir:x/a.go:4"], "forbidden": [],
                                                        "not_counted": []}}))


class AgreementTest(unittest.TestCase):
    """The audit scores with `common.keyrecord.score` (a key record), the benchmark with `bench.score.score` (the
    answer of a tracked key, `sets.answer`). Both formulas give the same counts for the same key and answer."""

    def test_the_two_score_formulas_agree(self):
        from bench import sets
        from common import keyrecord

        def site(file, line, cls="required", why="caller"):
            return {"file": file, "line": line, "col": 6, "class": cls, "why": why}

        # A key record whose view is the record itself (the family `callers`): required, required+decoy, forbidden
        # and dnc lines.
        record = {"id": "go:example.com/m.Run", "lang": "go", "kind": "func", "name": "Run", "container": "",
                  "decl": {"file": "a.go", "line": 1, "col": 6}, "family": ["go:example.com/m.Run"],
                  "implementers": [], "source": "calls",
                  "sites": [site("a.go", 1, "dnc", "decl"), site("a.go", 5), site("a.go", 9), site("b/c.go", 3),
                            site("b/c.go", 3, "forbidden", "decoy"), site("b/c.go", 7, "forbidden", "decoy")]}
        ch = {"id": "c1", "product": "caddy", "tree": "caddy", "family": "callers", "keys": "caddy/callers.jsonl",
              "key_id": record["id"], "sample": "hard", "note": ""}
        key = {"answer": sets.answer(ch, record)}
        exact = {("a.go", 5), ("a.go", 9), ("b/c.go", 3)}
        for what, answer in (("exact", exact), ("a miss", exact - {("a.go", 9)}),
                             ("a false line", exact | {("d.go", 2)}), ("a forbidden line", exact | {("b/c.go", 7)}),
                             ("a not counted line", exact | {("a.go", 1)}), ("no line", set()),
                             ("each kind", {("a.go", 5), ("d.go", 2), ("b/c.go", 7), ("a.go", 1)})):
            with self.subTest(what):
                bench_score = score.score(key, answer)
                self.assertEqual(keyrecord.score(answer, record), {k: bench_score[k] for k in (
                    "tp", "fp", "miss", "ignored", "precision", "recall", "exact")})


class CliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.key = os.path.join(self.tmp, "key.json")
        write(self.key, KEY)

    def answer(self, sites):
        path = os.path.join(self.tmp, f"answer-{len(os.listdir(self.tmp))}.json")
        write(path, {"sites": sites})
        return path

    def main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = score.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_cli(self):
        self.assertEqual(self.main(self.key, self.answer(["a.go:3", "./a.go:9", "a.go:1"]))[0], 0)
        self.assertEqual(self.main(self.key, self.answer(["a.go:3"]))[0], 1)
        self.assertEqual(self.main(self.key, "/no/such/file")[0], 2)

    def test_cli_prints_the_counts_the_missed_lines_and_the_false_lines(self):
        code, out, _ = self.main(self.key, self.answer(["c.go:7", "a.go:3", "b.go:1", "a.go:1", "a.go:3-4"]))
        self.assertEqual(1, code)
        self.assertEqual(["exact=False tp=1 fp=2 miss=1 ignored=1 outside=0 invalid=1", "missed a.go:9",
                          "false b.go:1", "false c.go:7"], out.splitlines())

    def test_cli_errors_exit_2(self):
        bad_json = os.path.join(self.tmp, "bad.json")
        with open(bad_json, "w", encoding="utf-8") as f:
            f.write("{not json")
        no_list = self.answer("a.go:3")
        no_answer = os.path.join(self.tmp, "no-answer.json")
        write(no_answer, {"question": "q"})
        for argv in ([self.key, bad_json], [self.key, no_list], [no_answer, self.answer([])],
                     [self.key, self.answer([]), "--root", os.path.join(self.tmp, "no-checkout")]):
            code, out, err = self.main(*argv)
            self.assertEqual((2, ""), (code, out), argv)
            self.assertTrue(err.startswith("score: "), err)

    def test_cli_root_gives_the_tree_files_and_the_prefix(self):
        checkout = os.path.join(self.tmp, "checkout")
        os.makedirs(checkout)
        for name in ("a.go", "b.go"):
            with open(os.path.join(checkout, name), "w", encoding="utf-8") as f:
                f.write("package a\n")
        subprocess.run(["git", "init", "-q", checkout], check=True)
        subprocess.run(["git", "-C", checkout, "add", "a.go", "b.go"], check=True)
        answer = self.answer([f"{checkout}/a.go:3", "a.go:9", ".venv/lib/x.py:2", "/elsewhere/c.go:1"])
        code, out, _ = self.main(self.key, answer, "--root", checkout)
        self.assertEqual((0, "exact=True tp=2 fp=0 miss=0 ignored=0 outside=1 invalid=1"), (code, out.strip()))
        # With no root, an absolute path is no answer line, and each path counts.
        code, out, _ = self.main(self.key, answer)
        self.assertEqual((1, "exact=False tp=1 fp=1 miss=1 ignored=0 outside=0 invalid=2"),
                         (code, out.splitlines()[0]))

    def test_cli_relative_root_matches_an_absolute_entry_below_it(self):
        checkout = os.path.join(self.tmp, "checkout")
        os.makedirs(checkout)
        with open(os.path.join(checkout, "a.go"), "w", encoding="utf-8") as f:
            f.write("package a\n")
        subprocess.run(["git", "init", "-q", checkout], check=True)
        subprocess.run(["git", "-C", checkout, "add", "a.go"], check=True)
        answer = self.answer([f"{checkout}/a.go:3", "a.go:9"])
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        for root in ("checkout", "./checkout/"):
            code, out, _ = self.main(self.key, answer, "--root", root)
            self.assertEqual((0, "exact=True tp=2 fp=0 miss=0 ignored=0 outside=0 invalid=0"), (code, out.strip()),
                             root)

    def test_script_runs_alone_with_the_standard_library(self):
        with open(SCRIPT, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        modules = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                   for alias in node.names}
        modules |= {node.module.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module}
        self.assertEqual(set(), modules - set(sys.stdlib_module_names))
        self.assertFalse([node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level])
        answer = self.answer(["a.go:3", "a.go:9"])
        result = subprocess.run([sys.executable, "-I", SCRIPT, self.key, answer], capture_output=True, text=True,
                                cwd=self.tmp)
        self.assertEqual((0, "exact=True tp=2 fp=0 miss=0 ignored=0 outside=0 invalid=0\n", ""),
                         (result.returncode, result.stdout, result.stderr))


if __name__ == "__main__":
    unittest.main()
