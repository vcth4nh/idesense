"""Unit tests of bench/qfiles.py: the export of the tracked questions and keys, the check and the rescore.

A temporary data root holds the key file caddy/symbols.jsonl with fake key records, the master tree caddy and its
manifest, and two set files. The question and key folders are temporary too. No test reads BENCH.
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from bench import qfiles
from bench import sets as challenges
from common import trees

GO_A = "package caddytls\n" + "".join(f"// line {n}\n" for n in range(2, 13))   # 12 lines
GO_B = "package other\n\nfunc x() {}\n"
with open(qfiles.PRODUCTS_FILE, encoding="utf-8") as _f:
    PIN = {p["folder"]: p["pin"] for p in json.load(_f)["products"]}["caddy"]


def site(line, cls="required", why="use", file="a.go", rel="self"):
    return {"file": file, "line": line, "col": 1, "class": cls, "why": why, "rel": rel}


def record(rid, kind, name, container, sites=(), implementers=(), decl_file="a.go"):
    return {"id": rid, "lang": "go", "kind": kind, "name": name, "container": container,
            "decl": {"file": decl_file, "line": 1, "col": 6}, "family": [rid], "sites": list(sites),
            "implementers": list(implementers), "source": "go/types", "external": []}


# A required line with a decoy (a.go:5), a forbidden line, a dnc line.
R_CA = record("go:example.com/m/caddytls.CA", "interface", "CA", "",
              [site(3), site(5), site(5, "forbidden", "decoy"), site(7, "forbidden", "decoy"),
               site(8, "dnc", "comment")])
R_VALIDATOR = record("go:example.com/m.Validator", "interface", "Validator", "",
                     implementers=[{"id": "go:example.com/m.T", "file": "a.go", "line": 10, "col": 6}])
R_RUN = record("go:example.com/m.App.Run", "method", "Run", "App", [site(4), site(6, "forbidden", "string")])
R_RUN_OTHER = record("go:example.com/other.App.Run", "method", "Run", "App", [site(3, file="b.go")], decl_file="b.go")


def challenge(cid, family, rec, sample="hard", note="test", tree="caddy"):
    return {"id": cid, "product": "caddy", "tree": tree, "family": family, "keys": "caddy/symbols.jsonl",
            "key_id": rec["id"], "sample": sample, "note": note}


CH_CA = challenge("caddy-refs-CA", "refs", R_CA, note="interface `CA` of `caddytls`")
CH_CONTROL = challenge("caddy-impls-control", "impls", R_VALIDATOR, "control", "seeded choice among 10 interfaces")
CH_RUN = challenge("caddy-refs-App.Run", "refs", R_RUN, note="first choice")
CH_RUN_CONTROL = challenge("caddy-refs-control", "refs", R_RUN, "control", "newest choice")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def jsonl(path, items):
    write(path, "".join(json.dumps(item) + "\n" for item in items))


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class DataRoot(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp(prefix="qfiles-test-")
        self.addCleanup(shutil.rmtree, d)
        self.d = d
        jsonl(os.path.join(d, "keys", "caddy", "symbols.jsonl"), [R_CA, R_VALIDATOR, R_RUN, R_RUN_OTHER])
        write(os.path.join(d, "trees", "caddy", "a.go"), GO_A)
        write(os.path.join(d, "trees", "caddy", "b.go"), GO_B)
        write(os.path.join(d, "trees", "caddy.manifest"), "".join(f"{'0' * 64}  {p}\n" for p in ("a.go", "b.go")))
        for target, name, value in ((challenges, "KEYS", os.path.join(d, "keys")),
                                    (challenges, "TREES", os.path.join(d, "trees")),
                                    (trees, "TREES", os.path.join(d, "trees")),
                                    (qfiles, "QUESTIONS", os.path.join(d, "tracked", "questions")),
                                    (qfiles, "KEYS", os.path.join(d, "tracked", "keys"))):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.questions, self.keys = qfiles.QUESTIONS, qfiles.KEYS
        self.set1, self.set2 = os.path.join(d, "one.jsonl"), os.path.join(d, "two.jsonl")
        jsonl(self.set1, [CH_CA, CH_CONTROL, CH_RUN])
        jsonl(self.set2, [CH_RUN_CONTROL, CH_CA])

    def export(self, *set_files):
        return qfiles.export(list(set_files or (self.set1, self.set2)), self.questions, self.keys)

    def key_path(self, name):
        return os.path.join(self.keys, name + ".json")

    def edit_key(self, name, **change):
        key = read_json(self.key_path(name))
        key.update(change)
        write(self.key_path(name), json.dumps(key, indent=2) + "\n")


class KeyTest(unittest.TestCase):
    def test_key_of_gives_the_tracked_format(self):
        key = qfiles.key_of(CH_CA, R_CA, "v2.11.7")
        self.assertEqual({
            "question": "caddy-refs-ca", "old_ids": ["caddy-refs-CA"], "product": "caddy", "pin": "v2.11.7",
            "tree": "caddy", "family": "refs", "lang": "go", "symbol": "go:example.com/m/caddytls.CA", "name": "CA",
            "answer": {"required": ["a.go:3", "a.go:5"], "forbidden": ["a.go:7"], "not_counted": ["a.go:8"]},
            "pick": {"sample": "hard", "rule": "interface `CA` of `caddytls`"}, "key_file": "caddy/symbols.jsonl",
            "source": "name resolution of the Go compiler library (go/types)"}, key)
        self.assertEqual(list(qfiles.KEY_FIELDS), list(key))

    def test_source_comes_from_the_name_of_the_key_file(self):
        for keys_file, word in (("beets/unique-used.jsonl", "token scan"), ("beets/unique.jsonl", "token scan"),
                                ("beets/hierarchy.jsonl", "reflection"), ("caddy-plant-2/plant.jsonl", "planted"),
                                ("beets/callers.jsonl", "syntax tree"), ("caddy/dyncallers.jsonl", "run-time trace"),
                                ("caddy/symbols.jsonl", "go/types")):
            self.assertIn(word, qfiles.source_of(keys_file), keys_file)
        with self.assertRaisesRegex(ValueError, "other.jsonl"):
            qfiles.source_of("caddy/other.jsonl")

    def test_name_of(self):
        self.assertEqual("caddy-refs-ca", qfiles.name_of(CH_CA, R_CA))
        self.assertEqual("caddy-refs-app.run", qfiles.name_of(CH_RUN, R_RUN))
        # A control id holds no symbol name: the tree, the family, the container and the name.
        self.assertEqual("caddy-impls-validator", qfiles.name_of(CH_CONTROL, R_VALIDATOR))
        self.assertEqual("caddy-refs-app.run", qfiles.name_of(CH_RUN_CONTROL, R_RUN))
        planted = dict(record("plant:go:caddy-plant-2:Replacer.GetString", "method", "Resolve", "Replacer"))
        self.assertEqual("caddy-plant2-refs-replacer.resolve",
                         qfiles.name_of(challenge("caddy-plant2-refs", "refs", planted, tree="caddy-plant-2"), planted))
        # The id must hold the name as a whole word: `add` in `caddy` does not count.
        add = record("go:example.com/m.Add", "interface", "Add", "")
        self.assertEqual("caddy-impls-add", qfiles.name_of(challenge("caddy-impls-control", "impls", add), add))


class ExportTest(DataRoot):
    def test_export_writes_one_question_for_equal_text_and_answer(self):
        names = self.export()
        self.assertEqual(["caddy-impls-validator", "caddy-refs-app.run", "caddy-refs-ca"], names)
        self.assertEqual(sorted(n + ".md" for n in names), sorted(os.listdir(self.questions)))
        self.assertEqual(sorted(n + ".json" for n in names), sorted(os.listdir(self.keys)))
        run = read_json(self.key_path("caddy-refs-app.run"))
        self.assertEqual(["caddy-refs-App.Run", "caddy-refs-control"], run["old_ids"])
        self.assertEqual({"sample": "control", "rule": "newest choice"}, run["pick"], "the last choice of the sets")
        self.assertEqual(["caddy-refs-CA"], read_json(self.key_path("caddy-refs-ca"))["old_ids"])
        self.assertEqual(["caddy-impls-control"], read_json(self.key_path("caddy-impls-validator"))["old_ids"])
        self.assertEqual(names, qfiles.names(self.keys))

    def test_key_file_is_json_with_two_spaces_and_a_final_newline(self):
        self.export()
        with open(self.key_path("caddy-refs-ca"), encoding="utf-8") as f:
            text = f.read()
        key = json.loads(text)
        self.assertEqual(json.dumps(key, indent=2, ensure_ascii=False) + "\n", text)
        self.assertEqual(qfiles.key_of(CH_CA, R_CA, PIN), key)
        self.assertEqual(key, qfiles.load_key("caddy-refs-ca", self.keys))

    def test_question_file_is_the_prompt_with_the_root_placeholder(self):
        self.export()
        with open(os.path.join(self.questions, "caddy-refs-ca.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(challenges.prompt(CH_CA, R_CA, "{root}") + "\n", text)
        self.assertTrue(text.startswith("The repository at {root} is a checkout of the project caddy. "), text)
        self.assertIn("`caddytls`", text)
        for word in ("/srv", "/home", self.d, "ws/"):
            self.assertNotIn(word, text)
        self.assertEqual(text[:-1], qfiles.load_question("caddy-refs-ca", self.questions))

    def test_two_questions_with_one_name_get_a_suffix_by_symbol(self):
        """`caddy-refs-App.Run` of another package has another text: a second question with the same name."""
        set3 = os.path.join(self.d, "three.jsonl")
        jsonl(set3, [challenge("caddy-refs-App.Run", "refs", R_RUN_OTHER)])
        names = self.export(set3, self.set1)
        self.assertEqual(["caddy-impls-validator", "caddy-refs-app.run", "caddy-refs-app.run-2", "caddy-refs-ca"],
                         names)
        self.assertEqual(R_RUN["id"], read_json(self.key_path("caddy-refs-app.run"))["symbol"])
        second = read_json(self.key_path("caddy-refs-app.run-2"))
        self.assertEqual((R_RUN_OTHER["id"], "caddy-refs-app.run-2"), (second["symbol"], second["question"]))

    def test_names_by_old_id_and_tree_files(self):
        self.export()
        self.assertEqual({"caddy-refs-CA": "caddy-refs-ca", "caddy-impls-control": "caddy-impls-validator",
                          "caddy-refs-App.Run": "caddy-refs-app.run", "caddy-refs-control": "caddy-refs-app.run"},
                         qfiles.by_old_id(self.keys))
        self.assertEqual({"a.go", "b.go"}, qfiles.tree_files("caddy"))


class CheckTest(DataRoot):
    def setUp(self):
        super().setUp()
        self.export()

    def test_check_of_a_correct_folder_is_empty(self):
        self.assertEqual([], qfiles.check(False, self.questions, self.keys))
        self.assertEqual([], qfiles.check(True, self.questions, self.keys))

    def test_check_reports_each_problem(self):
        os.unlink(self.key_path("caddy-impls-validator"))
        shutil.copy(self.key_path("caddy-refs-ca"), self.key_path("caddy-refs-x"))
        shutil.copy(self.key_path("caddy-refs-ca"), self.key_path("Caddy-refs-CA"))
        self.edit_key("caddy-refs-app.run", pin="v0.0.1")
        self.edit_key("caddy-refs-x", question="caddy-refs-y")
        problems = qfiles.check(False, self.questions, self.keys)
        expected = ["caddy-impls-validator.md: no key", "caddy-refs-x.json: no question",
                    "Caddy-refs-CA.json: the name", "Caddy-refs-CA.json and caddy-refs-ca.json: one name in lowercase",
                    f"caddy-refs-app.run.json: the pin v0.0.1 is not the pin {PIN} of products.json",
                    "caddy-refs-x.json: the question is caddy-refs-y"]
        for text in expected:
            self.assertEqual(1, sum(text in p for p in problems), (text, problems))
        # Caddy-refs-CA.json also has no question, and its `question` is caddy-refs-ca.
        self.assertEqual(len(expected) + 2, len(problems), problems)

    def test_check_reports_a_key_with_another_field(self):
        self.edit_key("caddy-refs-ca", note="a text")
        self.assertEqual(["keys/caddy-refs-ca.json: the fields are not " + ", ".join(qfiles.KEY_FIELDS)],
                         qfiles.check(False, self.questions, self.keys))

    def test_check_data_reports_another_answer_and_a_line_that_the_tree_does_not_have(self):
        key = read_json(self.key_path("caddy-refs-ca"))
        answer = dict(key["answer"], required=key["answer"]["required"] + ["a.go:13", "zz.go:1"])
        self.edit_key("caddy-refs-ca", answer=answer)
        self.assertEqual([], qfiles.check(False, self.questions, self.keys))
        self.assertEqual(["keys/caddy-refs-ca.json: the answer differs from the view of caddy/symbols.jsonl",
                          "keys/caddy-refs-ca.json: a.go:13 is after the last line (12) of the tree caddy",
                          "keys/caddy-refs-ca.json: zz.go:1 is no file of the tree caddy"],
                         qfiles.check(True, self.questions, self.keys))

    def test_cli_check_prints_the_count(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, qfiles.main(["check"]))
        self.assertEqual("0 problems\n", out.getvalue())
        os.unlink(self.key_path("caddy-refs-ca"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(1, qfiles.main(["check", "-data"]))
        self.assertEqual(["questions/caddy-refs-ca.md: no key", "1 problem"], out.getvalue().splitlines())


if __name__ == "__main__":
    unittest.main()
