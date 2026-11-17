import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import json
import shutil
import tempfile
import unittest
from unittest import mock

from benchlib import challenges, keys

ROOT = "/home/ubuntu/dev/ws/1a2b/caddy"
HEAD = f"The repository at {ROOT} is a checkout of the project caddy. Work only with this checkout."
TAIL = 'Answer with JSON only: {"sites": ["<path relative to the repository root>:<line number>", ...]}'
BUILD = " A file counts also when the build for this machine does not compile it."
# The declaration file of the test records in the master tree: the package clause after comments, one of them
# with the word `package` at the start of a line.
GO_FILE = "// Doc text.\n//go:build linux\n\n/* a block\npackage wrong\n*/\npackage caddyhttp\n\nfunc Run() {}\n"


def site(line, cls="required", why="use", file="a.go", rel=None, col=1):
    s = {"file": file, "line": line, "col": col, "class": cls, "why": why}
    if rel is not None:
        s["rel"] = rel
    return s


def record(sites=(), kind="method", name="Run", container="App", rid=None, implementers=(), external=(), lang=None):
    rid = rid or f"go:example.com/m.{container + '.' if container else ''}{name}"
    lang = lang or ("python" if kind in ("class", "function") else "go")
    return {"id": rid, "lang": lang, "kind": kind, "name": name,
            "container": container, "decl": {"file": "a.go", "line": 1, "col": 6}, "family": [rid],
            "sites": list(sites), "implementers": list(implementers), "source": "go/types",
            "external": list(external)}


def challenge(family="refs", cid="c1", product="caddy", tree="caddy", sample="hard"):
    return {"id": cid, "product": product, "tree": tree, "family": family, "keys": "caddy/symbols.jsonl",
            "key_id": "go:example.com/m.App.Run", "sample": sample, "note": ""}


def lines(rec):
    return {(f, n): c for (f, n), c in keys.line_classes(rec).items()}


# One case for each prompt text of amendment A3: (family, lang, kind, container).
PROMPT_CASES = [("refs", "go", "method", "App"), ("refs", "go", "iface_method", "Runner"), ("refs", "go", "func", ""),
                ("refs", "go", "type", ""), ("refs", "go", "interface", ""), ("refs", "python", "method", "App"),
                ("refs", "python", "function", ""), ("refs", "python", "class", ""), ("rename", "go", "method", "App"),
                ("rename", "python", "method", "App"), ("impls", "go", "interface", ""),
                ("impls", "python", "class", "")]


class MasterTree(unittest.TestCase):
    """A temporary master trees folder (`challenges.TREES`) with the tree `caddy`: `a.go`, `b/c.go` and its
    manifest."""

    def setUp(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        write(os.path.join(d, "caddy", "a.go"), GO_FILE)
        write(os.path.join(d, "caddy", "b", "c.go"), "package b\n")
        write(os.path.join(d, "caddy.manifest"), "".join(f"{'0' * 64}  {p}\n" for p in ("a.go", "b/c.go")))
        patcher = mock.patch.object(challenges, "TREES", d)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.trees = d

    def task(self, family, kind="method", container="App", lang=None):
        """The task paragraph of the prompt of a record `Run` declared at a.go:1."""
        rec = record(kind=kind, name="Run", container=container, lang=lang)
        return challenges.prompt(challenge(family), rec, ROOT).split("\n\n")[1]


class ViewTest(unittest.TestCase):
    def test_refs_view_makes_sibling_dnc(self):
        rec = record([site(1, rel="self"), site(1, "forbidden", "decoy", col=9),
                      site(2, rel="super"), site(3, rel="sub"), site(4, rel="sibling"),
                      site(4, "forbidden", "decoy", col=9), site(5, rel="embedded"), site(6, "forbidden", "decoy"),
                      site(7, rel="sibling"), site(7), site(7, "forbidden", "decoy", col=20), site(8, "dnc", "comment")])
        before = json.dumps(rec, sort_keys=True)
        got = challenges.view(challenge("refs"), rec)
        self.assertEqual({("a.go", 1): "required+decoy", ("a.go", 2): "required", ("a.go", 3): "required",
                          ("a.go", 4): "dnc", ("a.go", 5): "dnc", ("a.go", 6): "forbidden",
                          ("a.go", 7): "required+decoy", ("a.go", 8): "dnc"}, lines(got))
        self.assertEqual(before, json.dumps(rec, sort_keys=True))
        with self.assertRaisesRegex(ValueError, "cousin"):
            challenges.view(challenge("refs"), record([site(1, rel="cousin")]))

    def test_rename_view_refuses_external(self):
        rec = record([site(1, rel="self"), site(2, rel="sibling"), site(3, rel="embedded")])
        self.assertEqual(rec, challenges.view(challenge("rename"), rec))
        self.assertEqual({("a.go", 1): "required", ("a.go", 2): "required", ("a.go", 3): "required"},
                         lines(challenges.view(challenge("rename"), rec)))
        with self.assertRaisesRegex(ValueError, "external"):
            challenges.view(challenge("rename"), record([site(1)], external=["go:example.com/other.T.Run"]))

    def test_impls_view_uses_implementer_lines(self):
        imps = [{"id": "go:m.B", "file": "b.go", "line": 9, "col": 6, "class": "required"},
                {"id": "go:m.C", "file": "c.go", "line": 4, "col": 6, "class": "dnc"},
                {"id": "go:m.D", "file": "d.go", "line": 2, "col": 6}]
        rec = record([site(3), site(5, "forbidden", "decoy")], kind="interface", name="Runner", container="",
                     implementers=imps)
        got = challenges.view(challenge("impls"), rec)
        self.assertEqual({("b.go", 9): "required", ("c.go", 4): "dnc", ("d.go", 2): "required"}, lines(got))
        s = keys.score({("b.go", 9), ("c.go", 4), ("a.go", 3)}, got)
        self.assertEqual((1, 1, 1, 1), (s["tp"], s["fp"], s["miss"], s["ignored"]))
        self.assertEqual(2, len(rec["sites"]))
        bad = dict(imps[0], **{"class": "forbidden"})
        with self.assertRaisesRegex(ValueError, "forbidden"):
            challenges.view(challenge("impls"), record(kind="interface", container="", implementers=[bad]))


class AnswerTest(MasterTree):
    def test_parse_sites_forms(self):
        read = ["a.go:12", "./a.go:12", f"{ROOT}/a.go:12", "a.go:12:5", " b/c.go:7 ", "b/./c.go:8"]
        bad = ["a.go", "a.go:0", "a.go:3-9", "/etc/passwd:1", "7", "../caddy-plant-1/a.go:3",
               f"{ROOT}-plant-1/a.go:3", f"{ROOT}:3", "a.go:12 (call)", ":12"]
        sites, invalid = challenges.parse_sites({"sites": read + bad + [7, None]}, ROOT)
        self.assertEqual({("a.go", 12), ("b/c.go", 7), ("b/c.go", 8)}, sites)
        self.assertEqual(bad + ["7", "null"], invalid)
        self.assertEqual(({("a.go", 12)}, []), challenges.parse_sites({"sites": [f"{ROOT}/a.go:12"]}, ROOT + "/"))
        for obj in ({}, {"sites": "a.go:12"}, ["a.go:12"], None):
            with self.assertRaises(ValueError):
                challenges.parse_sites(obj, ROOT)

    def test_score_answer_counts_invalid(self):
        rec = record([site(3, rel="self"), site(4, rel="self"), site(5, rel="sibling"), site(6, "forbidden", "decoy")])
        sites, invalid = challenges.parse_sites(
            {"sites": ["a.go:3", "./a.go:3:9", "a.go:5", "a.go:6", "a.go:3-4", "/etc/passwd:1"]}, ROOT)
        s = challenges.score_answer(challenge("refs"), rec, sites, invalid)
        self.assertEqual({"tp": 1, "fp": 1, "miss": 1, "ignored": 1, "precision": 0.5, "recall": 0.5,
                          "exact": False, "invalid": 2, "outside": 0, "listed": 3}, s)
        empty = challenges.score_answer(challenge("refs"), rec, set(), ["x"])
        self.assertEqual((0, 2, 1, 0, 0),
                         (empty["tp"], empty["miss"], empty["invalid"], empty["outside"], empty["listed"]))

    def test_score_answer_moves_non_manifest_paths_to_outside(self):
        rec = record([site(3), site(9, "forbidden", "decoy", file="b/c.go")])
        sites = {("a.go", 3), ("b/c.go", 9), (".venv/lib/x.py", 1), ("new.go", 2), ("b", 1)}
        s = challenges.score_answer(challenge("refs"), rec, sites, ["a.go:3-4"])
        self.assertEqual({"tp": 1, "fp": 1, "miss": 0, "ignored": 0, "precision": 0.5, "recall": 1.0,
                          "exact": False, "invalid": 1, "outside": 3, "listed": 2}, s)


class PromptTest(MasterTree):
    def prompts(self):
        for family, lang, kind, container in PROMPT_CASES:
            rec = record(kind=kind, name="Run", container=container, lang=lang)
            yield f"{family} {lang} {kind}", challenges.prompt(challenge(family), rec, ROOT)

    def test_prompt_names_no_tool(self):
        for case, text in self.prompts():
            for word in ("ide_", "MCP", "IDE", "grep", "plugin", "bench", "plant", "idesense"):
                self.assertNotIn(word, text, case)

    def test_prompt_first_and_last_paragraph_equal_in_each_family(self):
        seen = set()
        for case, text in self.prompts():
            paragraphs = text.split("\n\n")
            self.assertEqual(3, len(paragraphs), case)
            self.assertEqual(HEAD, paragraphs[0])
            self.assertEqual(TAIL, paragraphs[-1])
            self.assertNotIn("\n", paragraphs[1])
            seen.add(case.split()[0])
        self.assertEqual({"refs", "rename", "impls"}, seen)
        self.assertEqual("Find each line of this repository that calls or names the method `Run` of the type "
                         "`caddyhttp.App`, which is declared at a.go:1. A line counts when it refers to this method, "
                         "to a method that overrides or implements it, or to a method that it overrides or "
                         "implements. Test code counts. A file counts also when the build for this machine does not "
                         "compile it. Do not list the declarations of these methods, import lines, comments or "
                         "strings.", self.task("refs"))
        self.assertEqual("The method `Run` of the class `App`, which is declared at a.go:1, must get a new name. Find "
                         "each line of this repository that must change, so that the repository builds and behaves "
                         "as before in each build configuration (Linux, Windows, macOS), test code included. Other "
                         "declarations that must get the new name with it count, and each line that calls or names "
                         "one of them. Nothing keeps the old name: do not add a wrapper or an alias. Do not list "
                         "comments or strings.", self.task("rename", lang="python"))
        self.assertTrue(self.task("rename").endswith(
            "one of them. Nothing keeps the old name: do not add a wrapper or an alias. Do not list comments or "
            "strings."))
        self.assertEqual("Find each type of this repository that implements the interface `Run` of the package "
                         "`caddyhttp`, which is declared at a.go:1. A type counts when the type or a pointer to it "
                         "implements the interface. Test code counts. Answer with the line that holds the name of "
                         "each type in its declaration.", self.task("impls", "interface", ""))
        self.assertEqual("Find each class of this repository that is a direct or indirect subclass of the class `Run`, "
                         "which is declared at a.go:1. Test code counts. Answer with the line of each class "
                         "statement.", self.task("impls", "class", ""))
        self.assertEqual("Find each line of this repository that calls or names the function `Run`, which is declared "
                         "at a.go:1. Test code counts. Do not list the declaration of the function itself, import "
                         "lines, comments or strings.", self.task("refs", "function", ""))

    def test_go_method_owner_has_package_and_type(self):
        self.assertIn("calls or names the method `Run` of the type `caddyhttp.App`, which is declared at a.go:1. ",
                      self.task("refs"))
        self.assertIn("calls or names the method `Run` of the interface `caddyhttp.Runner`, which is declared at "
                      "a.go:1. ", self.task("refs", "iface_method", "Runner"))
        self.assertTrue(self.task("rename").startswith(
            "The method `Run` of the type `caddyhttp.App`, which is declared at a.go:1, must get a new name. "))
        self.assertIn("the method `Run` of the class `App`, which is declared", self.task("refs", lang="python"))
        write(os.path.join(self.trees, "caddy", "a.go"), "// only a comment\n")
        with self.assertRaisesRegex(ValueError, "package clause"):
            self.task("refs")

    def test_python_prompt_has_no_build_sentence(self):
        for case, text in self.prompts():
            if " python " in case:
                self.assertNotIn("does not compile", text, case)
                if case.startswith("refs"):
                    self.assertIn("Test code counts. Do not list the declaration", text, case)
            elif case.startswith("refs"):
                self.assertIn("Test code counts." + BUILD + " Do not list the declaration", text, case)

    def test_go_type_prompt_says_names_not_calls(self):
        for kind in ("type", "interface"):
            task = self.task("refs", kind, "")
            self.assertEqual(f"Find each line of this repository that names the {kind} `Run` of the package "
                             f"`caddyhttp`, which is declared at a.go:1. Test code counts.{BUILD} Do not list the "
                             f"declaration of the {kind} itself, import lines, comments or strings.", task)
            self.assertNotIn("call", task)
        self.assertIn("that calls or names the function `Run` of the package `caddyhttp`, which is declared at "
                      "a.go:1. Test code counts." + BUILD + " Do not list the declaration of the function itself, ",
                      self.task("refs", "func", ""))
        self.assertIn("that calls or names the class `Run`, which is declared", self.task("refs", "class", ""))

    def test_prompt_refuses_a_family_and_kind_with_no_text(self):
        for family, kind in (("rename", "func"), ("impls", "type"), ("refs", "class")):
            with self.assertRaisesRegex(ValueError, "no prompt text"):
                self.task(family, kind, "", lang="go")

    def test_schema(self):
        self.assertEqual({"type": "object", "properties": {"sites": {"type": "array", "items": {"type": "string"}}},
                          "required": ["sites"], "additionalProperties": False}, challenges.schema(challenge()))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class TextScanTest(unittest.TestCase):
    def test_text_scan_ignores_dnc_lines(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        tree = os.path.join(d, "caddy")
        write(os.path.join(tree, "a.go"), "func Run() {\n\n\tRun()\n\tx.Runner()\n\ty.Run\n\t// Runs\n\tz()\n")
        write(os.path.join(tree, "sub", "b.go"), "x\n// Run here\n")
        write(os.path.join(tree, "c.bin"), "Run\0\n")
        write(os.path.join(tree, "not-listed.go"), "Run\n")
        write(tree + ".manifest", "".join(f"{'0' * 64}  {p}\n" for p in ("a.go", "c.bin", "sub/b.go")))
        rec = record([site(1, "dnc", "decl"), site(3), site(5, "forbidden", "decoy"), site(7),
                      site(2, "dnc", "comment", file="sub/b.go")])
        got = challenges.text_scan(challenge("refs"), rec, tree)
        self.assertEqual({"lines": 4, "precision": 0.5, "recall": 0.5}, got)


def jsonl(path, records):
    write(path, "".join(json.dumps(r) + "\n" for r in records))


def impl(i, cls="required"):
    return {"id": f"go:example.com/m.T{i}", "file": "t.go", "line": i, "col": 6, "class": cls}


def fake_keys(root, reverse=False):
    """A small keys root and audit root with the records that the pilot table names, and control candidates."""
    order = (lambda rs: list(reversed(rs))) if reverse else list
    caddy_ids = ("go:github.com/caddyserver/caddy/v2/modules/caddyhttp.App.Provision",
                 "go:github.com/caddyserver/caddy/v2/modules/caddyevents.App.Provision")
    caddy = [record(rid=caddy_ids[0], name="Provision"), record(rid=caddy_ids[1], name="Provision"),
             record(rid="go:github.com/caddyserver/caddy/v2/modules/caddytls.CA", kind="interface", name="CA",
                    container="", implementers=[impl(1)]),
             record(rid="go:example.com/m.I1", kind="interface", name="I1", container="",
                    implementers=[impl(i) for i in range(10)]),
             record(rid="go:example.com/m.I2", kind="interface", name="I2", container="",
                    implementers=[impl(i) for i in range(12)]),
             record(rid="go:example.com/m.I3", kind="interface", name="I3", container="",
                    implementers=[impl(i) for i in range(9)]),
             record(rid="go:example.com/m.I4", kind="interface", name="I4", container="",
                    implementers=[impl(i) for i in range(11)] + [impl(20, "dnc")])]
    jsonl(os.path.join(root, "keys", "caddy", "symbols.jsonl"), order(caddy))
    jsonl(os.path.join(root, "keys", "caddy-plant-2", "plant.jsonl"), order([
        record([site(1), site(2), site(3)], rid="plant:go:caddy-plant-2:App.ShouldEmit", name="Resolve"),
        record([site(1), site(1, col=9), site(2), site(4, "forbidden", "decoy")],
               rid="plant:go:caddy-plant-2:Replacer.GetString", name="Resolve", container="Replacer")]))
    py = "beetsplug.lastgenre.LastGenrePlugin._fetch_va_genres"
    jsonl(os.path.join(root, "keys", "beets", "unique-used.jsonl"), order([
        record([site(1)], rid="py:" + py, name="_fetch_va_genres", container="LastGenrePlugin"),
        record([site(i) for i in range(3)], rid="py:m.A.ok1", name="ok1", container="A"),
        record([site(i) for i in range(4)], rid="py:m.A.ok2", name="ok2", container="A"),
        record([site(1), site(2), site(2, col=9)], rid="py:m.A.few", name="few", container="A"),
        record([site(i) for i in range(5)], rid="py:m.A.dis", name="dis", container="A"),
        record([site(i) for i in range(5)], rid="py:m.f", kind="function", name="f", container="")]))
    jsonl(os.path.join(root, "keys", "beets", "hierarchy.jsonl"), [{"id": "_meta", "skipped": []}] + order([
        record(rid="py:beets.plugins.BeetsPlugin", kind="class", name="BeetsPlugin", container="",
               implementers=[impl(1)]),
        record(rid="py:beets.plugins.Other", kind="class", name="Other", container="")]))
    jsonl(os.path.join(root, "keys", "beets-plant-2", "plant.jsonl"), order([
        record([site(1)], rid="plant:python:beets-plant-2:ImportTask.handle_created", name="apply_changes",
               container="ImportTask"),
        record([site(1)], rid="plant:python:beets-plant-2:TitlecasePlugin.titlecase_fields", name="apply_changes",
               container="TitlecasePlugin")]))
    jsonl(os.path.join(root, "audit", "beets-unique-all", "disagreements.jsonl"),
          [{"id": "py:m.A.dis", "tool": "ide_find_usages"}, {"id": "py:m.A.few", "tool": "ide_find_definition"}])
    return os.path.join(root, "keys"), os.path.join(root, "audit")


class PilotTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)

    def test_pilot_set_is_stable_for_one_seed(self):
        first = challenges.pilot_set(1, *fake_keys(os.path.join(self.d, "one")))
        again = challenges.pilot_set(1, *fake_keys(os.path.join(self.d, "two"), reverse=True))
        self.assertEqual(first, again)
        by_id = {ch["id"]: ch for ch in first}
        self.assertEqual(["beets-impls-BeetsPlugin", "beets-plant2-refs", "beets-refs-_fetch_va_genres",
                          "beets-refs-control", "caddy-impls-control", "caddy-plant2-refs", "caddy-refs-CA",
                          "caddy-rename-App.Provision"], sorted(by_id))
        for ch in first:
            self.assertEqual(list(challenges.FIELDS), list(ch))
        self.assertEqual("go:github.com/caddyserver/caddy/v2/modules/caddyhttp.App.Provision",
                         by_id["caddy-rename-App.Provision"]["key_id"])
        self.assertEqual("plant:go:caddy-plant-2:App.ShouldEmit", by_id["caddy-plant2-refs"]["key_id"])
        self.assertEqual("plant:python:beets-plant-2:ImportTask.handle_created", by_id["beets-plant2-refs"]["key_id"])
        self.assertIn(by_id["caddy-impls-control"]["key_id"], ("go:example.com/m.I1", "go:example.com/m.I2"))
        self.assertIn(by_id["beets-refs-control"]["key_id"], ("py:m.A.ok1", "py:m.A.ok2"))
        self.assertEqual(("caddy-plant-2", "caddy", "refs", "caddy-plant-2/plant.jsonl", "hard"),
                         tuple(by_id["caddy-plant2-refs"][f] for f in ("tree", "product", "family", "keys", "sample")))
        self.assertEqual(("impls", "control"), (by_id["caddy-impls-control"]["family"],
                                                by_id["caddy-impls-control"]["sample"]))
        self.assertTrue(all(ch["note"] for ch in first))

    def test_pilot_refuses_a_record_that_is_not_unique(self):
        keys_root, audit_root = fake_keys(self.d)
        path = os.path.join(keys_root, "caddy", "symbols.jsonl")
        with open(path, encoding="utf-8") as f:
            ca = next(line for line in f if "caddytls.CA" in line)
        with open(path, "a", encoding="utf-8") as f:
            f.write(ca.replace("caddytls.CA", "x/caddytls.CA"))
        with self.assertRaisesRegex(LookupError, "2 key records for interface `CA` of `caddytls`"):
            challenges.pilot_set(1, keys_root, audit_root)

    def test_load_and_record_of(self):
        keys_root, audit_root = fake_keys(self.d)
        path = os.path.join(self.d, "set.jsonl")
        keys.save_keys(path, challenges.pilot_set(1, keys_root, audit_root))
        loaded = challenges.load(path)
        ch = next(c for c in loaded if c["id"] == "beets-impls-BeetsPlugin")
        with mock.patch.object(challenges, "KEYS", keys_root):
            self.assertEqual("BeetsPlugin", challenges.record_of(ch)["name"])
            with self.assertRaises(KeyError):
                challenges.record_of(dict(ch, key_id="_meta"))
        write(path, json.dumps(dict(ch, family="usages")) + "\n")
        with self.assertRaises(ValueError):
            challenges.load(path)


if __name__ == "__main__":
    unittest.main()
