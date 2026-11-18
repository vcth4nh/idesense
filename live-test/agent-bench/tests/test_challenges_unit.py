import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import contextlib
import io
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

    def test_refs_view_reads_an_optional_use_as_required(self):
        """An optional use (a member outside the coupled family) is a use of the symbol: the refs view equals the
        refs view of the same record with the use required. The rename view keeps it dnc."""
        plain = record([site(1, rel="self"), site(2, rel="super"), site(3, rel="sub"), site(4, rel="sibling"),
                        site(4, "forbidden", "decoy", col=9), site(5, "forbidden", "decoy"), site(6, "dnc", "decl")])
        split = json.loads(json.dumps(plain))
        for s in split["sites"]:
            if s.get("rel") in ("super", "sub", "sibling"):
                s.update({"class": "dnc", "optional": True})
        split["coupled"] = [split["id"]]
        self.assertEqual(lines(challenges.view(challenge("refs"), plain)),
                         lines(challenges.view(challenge("refs"), split)))
        self.assertEqual("required", lines(challenges.view(challenge("refs"), split))[("a.go", 2)])
        self.assertEqual({("a.go", 1): "required", ("a.go", 2): "dnc", ("a.go", 3): "dnc"},
                         {k: v for k, v in lines(challenges.view(challenge("rename"), split)).items()
                          if k[1] in (1, 2, 3)})

    def test_rename_view_makes_forbidden_dnc_on_a_line_with_only_an_optional_use(self):
        """A rename can change an optional use and need not: a decoy on its line is no error. A line with a
        required site, or with a dnc site that is not optional, keeps its decoy."""
        def optional(line):
            return dict(site(line, "dnc", rel="super"), optional=True)

        rec = record([site(1), optional(2), site(2, "forbidden", "decoy", col=9),
                      optional(3), site(3, col=5), site(3, "forbidden", "decoy", col=9),
                      site(4, "forbidden", "decoy"), site(5, "dnc", "comment"), site(5, "forbidden", "decoy", col=9)])
        before = json.dumps(rec, sort_keys=True)
        got = challenges.view(challenge("rename"), rec)
        self.assertEqual({("a.go", 1): "required", ("a.go", 2): "dnc", ("a.go", 3): "required+decoy",
                          ("a.go", 4): "forbidden", ("a.go", 5): "forbidden"}, lines(got))
        self.assertEqual(before, json.dumps(rec, sort_keys=True))

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


M = "go:example.com/m"
VALIDATOR = "go:github.com/caddyserver/caddy/v2.Validator"
PROVISION = "go:github.com/caddyserver/caddy/v2/modules/caddyhttp.App.Provision"
GO_ALL, WIN, MAC = ("linux", "windows", "darwin"), ("windows",), ("darwin",)


def gsite(line, cls="required", why="use", configs=GO_ALL, rel=None, col=1, optional=False):
    s = dict(site(line, cls, why, rel=rel, col=col), configs=list(configs))
    if optional:
        s["optional"] = True
    return s


def run(n, start=1, **kw):
    """Go sites on the lines start .. start+n-1 of a.go."""
    return [gsite(start + i, **kw) for i in range(n)]


def decoys(n, **kw):
    return run(n, start=1000, cls="forbidden", why="decoy", **kw)


def iface(name, lacking, having, names=("Run",), partial=0, dnc=0, rid=None):
    """An interface record, its interface method records, and a method record for each method of each
    implementer that has its own methods. The first `partial` implementers of the lacking ones have the first
    method name only."""
    rid = rid or f"{M}.{name}"
    imps, out = [], []
    for i in range(lacking + having):
        tid = f"{rid}T{i}"
        imps.append({"id": tid, "file": "t.go", "line": i + 1, "col": 6, "class": "required"})
        own = names if i >= lacking else names[:1] if i < partial else ()
        out += [record(kind="method", name=n, container=f"{name}T{i}", rid=f"{tid}.{n}") for n in own]
    imps += [{"id": f"{rid}D{i}", "file": "t.go", "line": 90 + i, "col": 6, "class": "dnc"} for i in range(dnc)]
    out.append(record(kind="interface", name=name, container="", rid=rid, implementers=imps))
    return out + [record(kind="iface_method", name=n, container=name, rid=f"{rid}.{n}") for n in names]


def renamable(name, family=5, coupled=2, required=10, sibling=0, optional=0, external=(), kind="method"):
    """A method of the container `R` with a family and a coupled family; `sibling` of the required lines are
    uses of a sibling, and `optional` more lines are optional uses."""
    rid = f"{M}.R.{name}"
    fam = [rid] + [f"{M}.F{i}.{name}" for i in range(family - 1)]
    sites = run(required - sibling) + run(sibling, 100, rel="sibling") + run(optional, 200, cls="dnc", rel="super",
                                                                            optional=True)
    rec = record(sites, kind=kind, name=name, container="R", rid=rid, external=external)
    return dict(rec, family=sorted(fam), coupled=sorted(fam[:coupled]))


def caddy_fixture():
    """The caddy records: candidates and near misses of each caddy rule."""
    out = []
    # structure: SA (3 required), SB and SC (5), SD and SE (9); Validator (20) and SF (30, a dnc implementer) are
    # excluded, SG has only 2 implementers with no method of their own.
    out += iface("SA", 3, 0, names=("Run", "Stop"), partial=1) + iface("SB", 3, 2) + iface("SC", 3, 2)
    out += iface("SD", 3, 6) + iface("SE", 3, 6) + iface("Validator", 3, 17, names=("Validate",), rid=VALIDATOR)
    out += iface("SF", 3, 27, dnc=1) + iface("SG", 2, 1, names=("Run", "Stop")) + iface("Itwo", 0, 2)
    # decoys: 8 or more required lines and 50 or more forbidden lines of the refs view.
    out += [record(run(8) + decoys(50), rid=f"{M}.D.Dm1", name="Dm1", container="D"),
            record(run(9) + decoys(55), rid=f"{M}.D.Dm2", name="Dm2", container="D"),
            record(run(8) + decoys(50), rid=f"{M}.D.DmExt", name="DmExt", container="D", external=[f"{M}.X"]),
            record(run(7) + decoys(60), rid=f"{M}.D.DmFew", name="DmFew", container="D"),
            record(run(10) + decoys(49) + [gsite(1, "forbidden", "decoy", col=9)], rid=f"{M}.D.DmDec", name="DmDec",
                   container="D"),
            record(run(7) + [gsite(8, rel="sibling")] + decoys(50), rid=f"{M}.D.DmSib", name="DmSib", container="D"),
            record(run(8) + decoys(50), rid=f"{M}.Dt1", kind="type", name="Dt1", container=""),
            record(run(8) + decoys(50), rid=f"{M}.Di1", kind="interface", name="Di1", container=""),
            record(run(8) + decoys(50), rid=f"{M}.Df1", kind="func", name="Df1", container="")]
    # build: Ba and Bb have 4 off-Linux lines (a decoy of Ba on line 1 has Linux); Bc has 2 and 5 other lines (line
    # 20 has a required Linux site, line 30 is a sibling use); Bd, Be and Bf are near misses.
    out += [record(run(4, configs=WIN) + [gsite(1, "forbidden", "decoy", col=9)], rid=f"{M}.Ba", kind="type", name="Ba",
                   container=""),
            record(run(4, configs=MAC) + run(6, 10), rid=f"{M}.Bb", kind="type", name="Bb", container=""),
            record(run(2, configs=WIN) + run(4, 10) + [gsite(20), gsite(20, col=9, configs=WIN)]
                   + [gsite(30, rel="sibling", configs=WIN)], rid=f"{M}.Bc", kind="func", name="Bc", container=""),
            record(run(1, configs=WIN) + run(9, 10), rid=f"{M}.Bd", kind="func", name="Bd", container=""),
            record(run(2, configs=WIN) + run(4, 10), rid=f"{M}.Be", kind="func", name="Be", container=""),
            record(run(3) + decoys(5, configs=WIN), rid=f"{M}.Bf", kind="func", name="Bf", container="")]
    # rename: the fixed record, a record of the same name in another package, Ra and Rb, and near misses.
    out += [record(run(3), rid=PROVISION, name="Provision"),
            record(run(3), rid="go:github.com/caddyserver/caddy/v2/modules/caddyevents.App.Provision", name="Provision"),
            renamable("Ra", sibling=5), renamable("Rb", family=19, coupled=3, required=12), renamable("Rc", family=4),
            renamable("Rd", family=20), renamable("Re", coupled=1), renamable("Rf", required=9),
            renamable("Rg", external=[f"{M}.X.Rg"]), renamable("Rh", kind="iface_method"),
            renamable("Ro", required=9, optional=1)]
    # random: candidates with 3 required lines and near misses with 2.
    for kind, name, container in (("method", "M", "X"), ("func", "F", ""), ("type", "T", ""),
                                  ("iface_method", "Im", "I")):
        for n in (1, 2, 3, "two"):
            rid = f"{M}.{container + '.' if container else ''}{name}{n}"
            out.append(record(run(2 if n == "two" else 3), rid=rid, kind=kind, name=f"{name}{n}",
                              container=container))
    return out


CADDY_NEAR_MISSES = {f"{M}.X.Mtwo", f"{M}.Ftwo", f"{M}.Ttwo", f"{M}.I.Imtwo", f"{M}.Itwo", f"{M}.SF"}


def prec(rid, kind, required, dnc=0):
    """A Python record of beets/unique-used.jsonl with `required` uses and `dnc` import lines."""
    parts = rid[3:].split(".")
    sites = [site(i, file="a.py") for i in range(1, required + 1)]
    sites += [site(100 + i, "dnc", "import", file="a.py") for i in range(dnc)]
    return record(sites, kind=kind, name=parts[-1], container=parts[-2] if kind == "method" else "", rid=rid,
                  lang="python")


def hier_class(rid, named, plain, part=0, dnc=0):
    """A class of beets/hierarchy.jsonl and its class statement lines: `named` lines hold the class name as a
    whole word, `part` lines hold it as a part of a word, `plain` lines do not hold it; `dnc` more subclasses
    name it."""
    name = rid.rsplit(".", 1)[1]
    file = f"sub/{name.lower()}.py"
    lines = ([f"class {name}N{i}(base.{name}):" for i in range(named)]
             + [f"class {name}P{i}({name}Base):" for i in range(part)]
             + [f"class {name}O{i}(Mid):" for i in range(plain)] + [f"class {name}D{i}({name}):" for i in range(dnc)])
    imps = [{"id": f"py:beets.sub.{name}{i}", "file": file, "line": i + 1, "col": 7,
             "class": "dnc" if i >= named + part + plain else "required"} for i in range(len(lines))]
    return record(kind="class", name=name, container="", rid=rid, implementers=imps), file, lines


def plant(n, container, original, required):
    rec = record([site(i, file="p.py") for i in range(1, required + 1)], kind="method", name="apply",
                 container=container, rid=f"plant:python:beets-plant-{n}:{container}.{original}", lang="python")
    return dict(rec, source="plant", original=original)


def main_fixture(root, reverse=False, drop=(), replace=None, extra=None):
    """A keys root, an audit root and a trees root in which each rule of `main_set` has known candidates.
    `drop` removes key records by id, `replace` puts another record in the place of an id, `extra` adds records
    to a file (path relative to `root`)."""
    def put(rel, rs, head=()):
        rs = [r for r in rs + (extra or {}).get(rel, []) if r["id"] not in drop]
        if rel.startswith("keys/"):
            rs = [(replace or {}).get(r["id"], r) for r in rs]
        jsonl(os.path.join(root, rel), list(head) + (list(reversed(rs)) if reverse else rs))

    keys_root, audit_root, trees_root = (os.path.join(root, p) for p in ("keys", "audit", "trees"))
    put("keys/caddy/symbols.jsonl", caddy_fixture())
    put("keys/beets/unique-used.jsonl", [
        prec("py:beets.util.long_one", "function", 12), prec("py:beets.util.long_two", "function", 12),
        prec("py:test.helper.longer", "function", 20), prec("py:beets.test.helper.longest", "function", 25),
        prec("py:beets.g.G.gap1", "method", 5), prec("py:beets.g.G.gap2", "method", 6),
        prec("py:beets.g.G.gap3", "method", 4, dnc=3), prec("py:beets.g.G.nogap", "method", 9),
        prec("py:beets.r.A.m1", "method", 3), prec("py:beets.r.A.m2", "method", 3),
        prec("py:beets.r.A.m3", "method", 3), prec("py:beets.r.A.m4", "method", 3),
        prec("py:beets.r.A.m0", "method", 2, dnc=1), prec("py:beets.r.f1", "function", 3),
        prec("py:beets.r.f0", "function", 2)])
    classes =[hier_class("py:beets.q.Model", 2, 10), hier_class("py:beets.q.Wide", 0, 2, part=8),
               hier_class("py:beets.q.Edge", 3, 9), hier_class("py:beets.q.Small", 0, 9),
               hier_class("py:beets.q.Dnc", 0, 9, dnc=3), hier_class("py:beets.q.Huge", 20, 40),
               hier_class("py:test.helper.TestCase", 5, 45), hier_class("py:beets.test.helper.Helper", 0, 49),
               hier_class("py:beets.test.h.Big", 13, 37), hier_class("py:beets.r.C3", 0, 3),
               hier_class("py:beets.r.C2", 0, 2)]
    put("keys/beets/hierarchy.jsonl", [rec for rec, _, _ in classes], head=[{"id": "_meta", "skipped": []}])
    for _, file, lines_ in classes:
        write(os.path.join(trees_root, "beets", file), "\n".join(lines_) + "\n")
    plants = {1: [plant(1, "Pa", "x", 5), plant(1, "Pb", "x", 7), plant(1, "Pc", "x", 7)],
              2: [plant(2, "Qa", "x", 6), plant(2, "Qb", "x", 4), plant(2, "Qc", "x", 3)],
              3: [plant(3, "Ra", "x", 8), plant(3, "Ra", "y", 5)]}
    for n, recs in plants.items():
        put(f"keys/beets-plant-{n}/plant.jsonl", recs)
    disagree = {"beets-unique-all": ["py:beets.g.G.gap1", "py:beets.g.G.gap1", "py:beets.g.G.gap2",
                                     "py:beets.g.G.gap3", "py:beets.util.long_one"],
                "beets-plant-1": ["plant:python:beets-plant-1:Pc.x"],
                "beets-plant-2": ["plant:python:beets-plant-2:Qa.x", "plant:python:beets-plant-2:Qb.x"],
                "beets-plant-3": ["plant:python:beets-plant-3:Ra.x", "plant:python:beets-plant-3:Ra.y"]}
    for folder, ids in disagree.items():
        put(f"audit/{folder}/disagreements.jsonl", [{"id": rid, "tool": f"tool{i}"} for i, rid in enumerate(ids)])
    write(os.path.join(trees_root, "caddy", "a.go"), "package m\n")
    for tree in ("caddy", "beets", "beets-plant-1", "beets-plant-2", "beets-plant-3"):
        write(os.path.join(trees_root, tree + ".manifest"), "")
    return keys_root, audit_root, trees_root


SEEDS = range(1, 9)


def by_word(chs, product, word):
    """The challenges of a product whose note starts with the word."""
    return [ch for ch in chs if ch["product"] == product and ch["note"].split(":")[0] == word]


def required_count(ch, rec):
    return sum(1 for cls in keys.line_classes(challenges.view(ch, rec)).values() if cls in challenges.REQUIRED)


class MainSetTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        self.roots = main_fixture(os.path.join(self.d, "one"))

    def sets(self):
        """The main set of each seed of SEEDS."""
        return [challenges.main_set(seed, *self.roots) for seed in SEEDS]

    def key_ids(self, chs, product, word):
        return [ch["key_id"] for ch in by_word(chs, product, word)]

    def test_caddy_structure_takes_the_two_fewest_and_the_most(self):
        chs = challenges.main_set(1, *self.roots)
        self.assertEqual([f"{M}.SA", f"{M}.SB", f"{M}.SD"], self.key_ids(chs, "caddy", "structure"))
        for ch in by_word(chs, "caddy", "structure"):
            self.assertEqual(("impls", "hard", "caddy", "caddy/symbols.jsonl"),
                             (ch["family"], ch["sample"], ch["tree"], ch["keys"]))
        self.assertEqual(["caddy-impls-SA", "caddy-impls-SB", "caddy-impls-SD"],
                         [ch["id"] for ch in by_word(chs, "caddy", "structure")])

    def test_caddy_decoys_takes_a_method_and_a_type(self):
        for chs in self.sets():
            method, typ = self.key_ids(chs, "caddy", "decoys")
            self.assertIn(method, (f"{M}.D.Dm1", f"{M}.D.Dm2"))
            self.assertIn(typ, (f"{M}.Dt1", f"{M}.Di1"))
            self.assertEqual({"refs"}, {ch["family"] for ch in by_word(chs, "caddy", "decoys")})

    def test_caddy_build_takes_the_most_off_linux_lines_then_a_seeded_pick(self):
        for chs in self.sets():
            first, second = self.key_ids(chs, "caddy", "build")
            self.assertEqual(f"{M}.Ba", first)
            self.assertIn(second, (f"{M}.Bb", f"{M}.Bc"))

    def test_caddy_rename_takes_provision_then_a_seeded_method(self):
        for chs in self.sets():
            fixed, second = by_word(chs, "caddy", "rename")
            self.assertEqual((PROVISION, "caddy-rename-App.Provision", "rename"),
                             (fixed["key_id"], fixed["id"], fixed["family"]))
            self.assertIn(second["key_id"], (f"{M}.R.Ra", f"{M}.R.Rb"))

    def test_caddy_random_takes_six_by_kind(self):
        for chs in self.sets():
            hard = {ch["key_id"] for ch in chs if ch["product"] == "caddy" and ch["sample"] == "hard"}
            picks = by_word(chs, "caddy", "random")
            self.assertEqual({"random"}, {ch["sample"] for ch in picks})
            records = {r["id"]: r for r in keys.load_keys(os.path.join(self.roots[0], "caddy", "symbols.jsonl"))}
            self.assertEqual([("refs", "method"), ("refs", "method"), ("refs", "func"), ("refs", "type"),
                              ("refs", "iface_method"), ("impls", "interface")],
                             [(ch["family"], records[ch["key_id"]]["kind"]) for ch in picks])
            for ch in picks:
                self.assertNotIn(ch["key_id"], hard | CADDY_NEAR_MISSES)
                self.assertGreaterEqual(required_count(ch, records[ch["key_id"]]), 3)

    def test_beets_structure_reads_the_class_lines(self):
        for chs in self.sets():
            first, second, third = self.key_ids(chs, "beets", "structure")
            self.assertEqual({"py:beets.q.Model", "py:beets.q.Wide"}, {first, second})
            self.assertEqual("py:test.helper.TestCase", third)
            self.assertEqual({("impls", "beets/hierarchy.jsonl", "beets")},
                             {(ch["family"], ch["keys"], ch["tree"]) for ch in by_word(chs, "beets", "structure")})

    def test_beets_plant_takes_the_most_required_lines_of_each_tree_and_one_disagreement(self):
        chs = challenges.main_set(1, *self.roots)
        got = [(ch["id"], ch["tree"], ch["keys"], ch["key_id"], ch["family"]) for ch in by_word(chs, "beets", "plant")]
        self.assertEqual([
            ("beets-plant1-refs-Pb", "beets-plant-1", "beets-plant-1/plant.jsonl", "plant:python:beets-plant-1:Pb.x",
             "refs"),
            ("beets-plant2-refs-Qa", "beets-plant-2", "beets-plant-2/plant.jsonl", "plant:python:beets-plant-2:Qa.x",
             "refs"),
            ("beets-plant3-refs-Ra", "beets-plant-3", "beets-plant-3/plant.jsonl", "plant:python:beets-plant-3:Ra.x",
             "refs")], got)
        gap = [ch for ch in by_word(chs, "beets", "ide-gap") if ch["tree"] != "beets"]
        self.assertEqual([("beets-plant3-refs-Ra-2", "beets-plant-3", "plant:python:beets-plant-3:Ra.y", "hard")],
                         [(ch["id"], ch["tree"], ch["key_id"], ch["sample"]) for ch in gap])

    def test_beets_long_takes_the_most_required_lines_outside_test_code(self):
        chs = challenges.main_set(1, *self.roots)
        self.assertEqual(["py:beets.util.long_one"], self.key_ids(chs, "beets", "long"))

    def test_beets_ide_gap_takes_a_disagreement_with_five_required_lines(self):
        for chs in self.sets():
            gap = [ch for ch in by_word(chs, "beets", "ide-gap") if ch["tree"] == "beets"]
            self.assertEqual(1, len(gap))
            self.assertIn(gap[0]["key_id"], ("py:beets.g.G.gap1", "py:beets.g.G.gap2"))
            self.assertEqual(("refs", "beets/unique-used.jsonl"), (gap[0]["family"], gap[0]["keys"]))

    def test_beets_random_takes_three_methods_a_function_and_two_classes(self):
        for chs in self.sets():
            hard = {ch["key_id"] for ch in chs if ch["product"] == "beets" and ch["sample"] == "hard"}
            picks = by_word(chs, "beets", "random")
            self.assertEqual(["beets/unique-used.jsonl"] * 4 + ["beets/hierarchy.jsonl"] * 2, [ch["keys"] for ch in picks])
            self.assertEqual(["refs"] * 4 + ["impls"] * 2, [ch["family"] for ch in picks])
            records = {r["id"]: r for rel in ("beets/unique-used.jsonl", "beets/hierarchy.jsonl")
                       for r in keys.load_keys(os.path.join(self.roots[0], rel))}
            self.assertEqual(["method"] * 3 + ["function", "class", "class"],
                             [records[ch["key_id"]]["kind"] for ch in picks])
            for ch in picks:
                self.assertNotIn(ch["key_id"], hard | {"py:beets.r.A.m0", "py:beets.r.f0", "py:beets.r.C2"})
                self.assertGreaterEqual(required_count(ch, records[ch["key_id"]]), 3)

    def test_same_seed_and_another_record_order_give_the_same_set(self):
        again = main_fixture(os.path.join(self.d, "two"), reverse=True)
        for seed in SEEDS:
            self.assertEqual(challenges.main_set(seed, *self.roots), challenges.main_set(seed, *again))

    def test_fifteen_challenges_for_each_product_each_with_a_prompt(self):
        chs = challenges.main_set(1, *self.roots)
        self.assertEqual(30, len({ch["id"] for ch in chs}))
        with mock.patch.object(challenges, "TREES", self.roots[2]):
            for product in ("caddy", "beets"):
                mine = [ch for ch in chs if ch["product"] == product]
                self.assertEqual((6, 9), (sum(ch["sample"] == "random" for ch in mine),
                                          sum(ch["sample"] == "hard" for ch in mine)))
                for ch in mine:
                    self.assertEqual(list(challenges.FIELDS), list(ch))
                    word = ch["note"].split(":")[0]
                    self.assertIn(word, ("random",) if ch["sample"] == "random" else
                                  ("structure", "decoys", "build", "rename", "plant", "long", "ide-gap"))
                    rec = challenges.record_of(ch, self.roots[0])
                    self.assertGreaterEqual(required_count(ch, rec), 1, ch["id"])
                    self.assertIn(rec["name"], challenges.prompt(ch, rec, ROOT))

    def test_too_few_candidates_name_the_rule(self):
        cases = [({f"{M}.SB", f"{M}.SC", f"{M}.SD", f"{M}.SE"}, "caddy structure"),
                 ({"plant:python:beets-plant-2:Qb.x", "plant:python:beets-plant-3:Ra.y"}, "beets plant"),
                 ({"py:beets.r.C3", "py:beets.q.Edge", "py:beets.q.Small", "py:beets.q.Dnc", "py:beets.q.Huge",
                   "py:beets.test.helper.Helper", "py:beets.test.h.Big"}, "beets random")]
        for i, (drop, rule) in enumerate(cases):
            roots = main_fixture(os.path.join(self.d, f"drop{i}"), drop=drop)
            with self.assertRaisesRegex(LookupError, rule):
                challenges.main_set(1, *roots)

    def test_a_record_with_no_required_line_names_the_rule(self):
        only_optional = record([gsite(1, "dnc", rel="super", optional=True), gsite(2, "dnc", "comment")],
                               rid=PROVISION, name="Provision")
        roots = main_fixture(os.path.join(self.d, "dnc"), replace={PROVISION: only_optional})
        with self.assertRaisesRegex(LookupError, "caddy rename.*no required line"):
            challenges.main_set(1, *roots)

    def test_overlap_go_family_members_are_no_candidates(self):
        """Fix round 1, case 1: a Go method or interface method whose family holds a chosen record, or whose id
        is in the family of a chosen record, is no candidate."""
        provision = dict(record(run(3), rid=PROVISION, name="Provision"), family=[f"{M}.I.Im2", PROVISION])
        im1 = record(run(3), rid=f"{M}.I.Im1", kind="iface_method", name="Im1", container="I")
        roots = main_fixture(os.path.join(self.d, "go"), replace={PROVISION: provision,
                                                                  im1["id"]: dict(im1, family=[im1["id"], PROVISION])})
        kinds = {r["id"]: r["kind"] for r in keys.load_keys(os.path.join(roots[0], "caddy", "symbols.jsonl"))}
        for seed in SEEDS:
            chs = challenges.main_set(seed, *roots)
            [pick] = [ch["key_id"] for ch in by_word(chs, "caddy", "random") if kinds[ch["key_id"]] == "iface_method"]
            self.assertIn(pick, (f"{M}.I.Im3", f"{M}.R.Rh"))

    def test_overlap_impls_subclasses_and_base_classes_are_no_candidates(self):
        """Fix round 1, case 2: an impls candidate that is an implementer of a chosen impls record, or that has a
        chosen impls record as an implementer, is no candidate. This holds also inside one rule."""
        def with_impl(rec, rid, file="t.go"):
            return dict(rec, implementers=rec["implementers"] + [
                {"id": rid, "file": file, "line": 1, "col": 7, "class": "required"}])

        caddy = {r["id"]: r for r in caddy_fixture()}
        huge, edge = hier_class("py:beets.q.Huge", 20, 40)[0], hier_class("py:beets.q.Edge", 3, 9)[0]
        replace = {f"{M}.SC": with_impl(caddy[f"{M}.SC"], f"{M}.SA"), f"{M}.SD": with_impl(caddy[f"{M}.SD"], f"{M}.SG"),
                   huge["id"]: with_impl(huge, "py:beets.q.Model", "sub/huge.py"),
                   edge["id"]: with_impl(edge, "py:beets.r.C3", "sub/edge.py")}
        roots = main_fixture(os.path.join(self.d, "impls"), replace=replace,
                             drop={"py:beets.q.Small", "py:beets.q.Dnc", "py:beets.test.helper.Helper"})
        for seed in SEEDS:
            chs = challenges.main_set(seed, *roots)
            self.assertEqual([f"{M}.SA", f"{M}.SB", f"{M}.SD"], self.key_ids(chs, "caddy", "structure"))
            [interface] = [ch["key_id"] for ch in by_word(chs, "caddy", "random") if ch["family"] == "impls"]
            self.assertIn(interface, (f"{M}.SE", VALIDATOR))
            classes = {ch["key_id"] for ch in by_word(chs, "beets", "random") if ch["family"] == "impls"}
            self.assertIn(classes, ({"py:beets.q.Edge", "py:beets.test.h.Big"}, {"py:beets.r.C3", "py:beets.test.h.Big"}))

    def test_overlap_natural_record_of_a_chosen_planted_method_is_no_candidate(self):
        """Fix round 1, case 3: a record of beets/unique-used.jsonl with the container and the original name of a
        chosen planted record is no candidate, also of a rule of the most. A planted record that no rule chose
        excludes nothing."""
        extra = {"keys/beets/unique-used.jsonl": [prec("py:beets.p.Pb.x", "method", 30),
                                                  prec("py:beets.p.Qb.x", "method", 20),
                                                  prec("py:beets.p.Ra.y", "method", 9)],
                 "audit/beets-unique-all/disagreements.jsonl": [{"id": "py:beets.p.Ra.y", "tool": "tool9"}]}
        roots = main_fixture(os.path.join(self.d, "plant"), extra=extra)
        for seed in SEEDS:
            chs = challenges.main_set(seed, *roots)
            self.assertEqual(["py:beets.p.Qb.x"], self.key_ids(chs, "beets", "long"))
            gap = [ch["key_id"] for ch in by_word(chs, "beets", "ide-gap") if ch["tree"] == "beets"]
            self.assertIn(gap, (["py:beets.g.G.gap1"], ["py:beets.g.G.gap2"], ["py:beets.util.long_one"]))
            self.assertFalse({"py:beets.p.Pb.x", "py:beets.p.Ra.y"} & {ch["key_id"] for ch in chs})

    def test_the_fixed_rename_survives_a_rule_that_comes_before_it_in_the_brief(self):
        """Fix round 1: the rename rule runs before the decoys rule, so `App.Provision` is never excluded. A
        decoys method in its family is then no candidate."""
        dm1 = next(r for r in caddy_fixture() if r["id"] == f"{M}.D.Dm1")
        roots = main_fixture(os.path.join(self.d, "fixed"), replace={dm1["id"]: dict(dm1, family=[dm1["id"], PROVISION])})
        for seed in SEEDS:
            chs = challenges.main_set(seed, *roots)
            self.assertEqual(PROVISION, by_word(chs, "caddy", "rename")[0]["key_id"])
            self.assertEqual(f"{M}.D.Dm2", self.key_ids(chs, "caddy", "decoys")[0])

    def test_cli_main_writes_the_set_and_show_reads_the_key_root(self):
        path = os.path.join(self.d, "main.jsonl")
        keys_root, audit_root, trees_root = self.roots
        with mock.patch.multiple(challenges, KEYS=keys_root, AUDIT=audit_root, TREES=trees_root):
            self.assertEqual(0, challenges.main(["main", "-out", path, "-seed", "2"]))
        self.assertEqual(sorted(challenges.main_set(2, *self.roots), key=lambda ch: ch["id"]), challenges.load(path))
        out = io.StringIO()
        with mock.patch.object(challenges, "TREES", trees_root), contextlib.redirect_stdout(out):
            self.assertEqual(0, challenges.main(["show", "-set", path, "-root", trees_root, "-keys", keys_root]))
        self.assertEqual(30, sum(1 for line in out.getvalue().splitlines() if line.startswith("== ")))


if __name__ == "__main__":
    unittest.main()
