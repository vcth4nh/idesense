import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import shutil
import tempfile
import unittest

from benchlib import keys


def site(line, cls, why="use", file="a.go", col=1):
    return {"file": file, "line": line, "col": col, "class": cls, "why": why, "configs": ["linux"]}


def record(sites, rid="go:example.com/m.App.Run"):
    return {"id": rid, "lang": "go", "kind": "method", "name": "Run", "container": "App",
            "decl": {"file": "a.go", "line": 1, "col": 15}, "family": [rid], "sites": sites,
            "implementers": [], "source": "go/types"}


class ScoreTest(unittest.TestCase):
    def test_score_counts_required_forbidden_dnc(self):
        rec = record([site(3, "required"), site(4, "required"), site(5, "forbidden", "decoy"),
                      site(6, "dnc", "comment")])
        answer = {("a.go", 3), ("a.go", 5), ("a.go", 6), ("a.go", 99)}
        s = keys.score(answer, rec)
        self.assertEqual((1, 2, 1, 1), (s["tp"], s["fp"], s["miss"], s["ignored"]))
        self.assertAlmostEqual(1 / 3, s["precision"])
        self.assertAlmostEqual(1 / 2, s["recall"])
        self.assertIs(False, s["exact"])

    def test_line_with_required_and_decoy(self):
        rec = record([site(7, "required", col=3), site(7, "forbidden", "decoy", col=20)])
        self.assertEqual({("a.go", 7): "required+decoy"}, keys.line_classes(rec))
        hit = keys.score({("a.go", 7)}, rec)
        self.assertEqual((1, 0, 0), (hit["tp"], hit["fp"], hit["miss"]))
        self.assertIs(True, hit["exact"])
        absent = keys.score(set(), rec)
        self.assertEqual((0, 0, 1), (absent["tp"], absent["fp"], absent["miss"]))
        self.assertIs(False, absent["exact"])

    def test_exact_ignores_dnc(self):
        rec = record([site(3, "required"), site(1, "dnc", "decl"), site(2, "dnc", "import")])
        with_dnc = keys.score({("a.go", 3), ("a.go", 1), ("a.go", 2)}, rec)
        self.assertEqual((1, 0, 0, 2), (with_dnc["tp"], with_dnc["fp"], with_dnc["miss"], with_dnc["ignored"]))
        self.assertIs(True, with_dnc["exact"])
        self.assertEqual(1.0, with_dnc["precision"])
        without_dnc = keys.score({("a.go", 3)}, rec)
        self.assertEqual(0, without_dnc["ignored"])
        self.assertIs(True, without_dnc["exact"])

    def test_empty_key_gives_none_ratios(self):
        rec = record([])
        s = keys.score(set(), rec)
        self.assertEqual((0, 0, 0, 0), (s["tp"], s["fp"], s["miss"], s["ignored"]))
        self.assertIsNone(s["precision"])
        self.assertIsNone(s["recall"])
        self.assertIs(True, s["exact"])
        wrong = keys.score({("a.go", 9)}, rec)
        self.assertEqual(1, wrong["fp"])
        self.assertEqual(0.0, wrong["precision"])
        self.assertIsNone(wrong["recall"])
        self.assertIs(False, wrong["exact"])

    def test_line_classes_rules(self):
        rec = record([site(1, "required"), site(1, "required", col=9),
                      site(2, "required"), site(2, "dnc", "comment", col=30),
                      site(3, "forbidden", "decoy"), site(3, "dnc", "string", col=30),
                      site(4, "dnc", "decl"),
                      site(5, "required"), site(5, "forbidden", "decoy", col=9), site(5, "dnc", "comment", col=30),
                      site(1, "required", file="b.go")])
        self.assertEqual({("a.go", 1): "required", ("a.go", 2): "required", ("a.go", 3): "forbidden",
                          ("a.go", 4): "dnc", ("a.go", 5): "required+decoy", ("b.go", 1): "required"},
                         keys.line_classes(rec))

    def test_unknown_class_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "do-not-care"):
            keys.line_classes(record([site(1, "do-not-care")]))


class SaveLoadTest(unittest.TestCase):
    def test_save_sorts_by_id_and_round_trips(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        path = os.path.join(d, "keys", "caddy", "refs.jsonl")
        recs = [record([site(3, "required")], "go:m.b"), record([], "go:m.a"),
                record([site(4, "dnc", "comment")], "go:m.c")]
        keys.save_keys(path, recs)
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(3, len(lines))
        self.assertEqual(["go:m.a", "go:m.b", "go:m.c"], [r["id"] for r in keys.load_keys(path)])
        self.assertEqual(sorted(recs, key=lambda r: r["id"]), keys.load_keys(path))
        self.assertEqual(["refs.jsonl"], os.listdir(os.path.dirname(path)))

    def test_save_replaces_the_old_file(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        path = os.path.join(d, "refs.jsonl")
        keys.save_keys(path, [record([], "go:m.a"), record([], "go:m.b")])
        keys.save_keys(path, [record([], "go:m.z")])
        self.assertEqual(["go:m.z"], [r["id"] for r in keys.load_keys(path)])
        self.assertEqual(["refs.jsonl"], os.listdir(d))


if __name__ == "__main__":
    unittest.main()
