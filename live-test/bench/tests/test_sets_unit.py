import contextlib
import io
import json
import os
import random
import re
import shutil
import tempfile
import unittest
from unittest import mock

from bench import score
from bench import sets as challenges
from common import keyrecord as keys

ROOT = "/srv/ws/1a2b/caddy"
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


def callers_record():
    """A key record of `callkeys make` for `Run` at a.go:1: two callers at level 1, one at level 2."""
    def caller(file, line, level):
        return {"file": file, "line": line, "col": 6, "class": "required", "why": "caller", "level": level,
                "lit": False, "plant": False, "configs": ["linux"]}

    rec = record([site(1, "dnc", "decl", col=6), caller("a.go", 5, 1), caller("a.go", 9, 1), caller("b/c.go", 3, 2)],
                 kind="func", container="")
    return dict(rec, source="calls", depth=2, property=False, plant=False, levels={"1": 2, "2": 1})


def dyncallers_record():
    """A key record of `callkeys dynmake` for the method `App.Run` at a.go:1: one static and one traced caller, one
    possible caller."""
    rec = callers_record()
    sites = [dict(s, proof="static" if s["line"] == 5 else "trace") if s["why"] == "caller" else s
             for s in rec["sites"]]
    sites[-1] = {"file": "b/c.go", "line": 3, "col": 6, "class": "dnc", "why": "possible"}
    return dict(rec, kind="method", container="App", id="go:example.com/m.App.Run", source="calls+trace", depth=1,
                levels={"1": 2, "2": 0}, dynamic={"static": 1, "trace": 1, "possible": 1, "library": 0}, sites=sites)


# One case for each prompt text of `bench.sets`: (family, lang, kind, container).
PROMPT_CASES = [("refs", "go", "method", "App"), ("refs", "go", "iface_method", "Runner"), ("refs", "go", "func", ""),
                ("refs", "go", "type", ""), ("refs", "go", "interface", ""), ("refs", "python", "method", "App"),
                ("refs", "python", "function", ""), ("refs", "python", "class", ""), ("rename", "go", "method", "App"),
                ("rename", "python", "method", "App"), ("impls", "go", "interface", ""),
                ("impls", "python", "class", ""), ("callers", "go", "func", ""), ("callers", "go", "method", "App"),
                ("callers", "python", "method", "App"), ("callers", "python", "function", ""),
                ("dyncallers", "go", "method", "App")]


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

    def test_callers_view_is_the_record_itself(self):
        rec = callers_record()
        self.assertIs(rec, challenges.view(challenge("callers"), rec))
        with self.assertRaisesRegex(ValueError, "source"):
            challenges.view(challenge("callers"), dict(rec, source="go/types"))

    def test_dyncallers_view_is_the_record_itself(self):
        rec = dyncallers_record()
        self.assertIs(rec, challenges.view(challenge("dyncallers"), rec))
        for source in ("calls", "go/types"):
            with self.assertRaisesRegex(ValueError, f"calls\\+trace.*{source}"):
                challenges.view(challenge("dyncallers"), dict(rec, source=source))
        with self.assertRaisesRegex(ValueError, "source"):
            challenges.view(challenge("callers"), rec)


class AnswerTest(MasterTree):
    def test_parse_sites_forms(self):
        read = ["a.go:12", "./a.go:12", f"{ROOT}/a.go:12", "a.go:12:5", " b/c.go:7 ", "b/./c.go:8"]
        bad = ["a.go", "a.go:0", "a.go:3-9", "/etc/passwd:1", "7", "../caddy-plant-1/a.go:3",
               f"{ROOT}-plant-1/a.go:3", f"{ROOT}:3", "a.go:12 (call)", ":12"]
        sites, invalid = score.parse_sites({"sites": read + bad + [7, None]}, ROOT)
        self.assertEqual({("a.go", 12), ("b/c.go", 7), ("b/c.go", 8)}, sites)
        self.assertEqual(bad + ["7", "null"], invalid)
        self.assertEqual(({("a.go", 12)}, []), score.parse_sites({"sites": [f"{ROOT}/a.go:12"]}, ROOT + "/"))
        for obj in ({}, {"sites": "a.go:12"}, ["a.go:12"], None):
            with self.assertRaises(ValueError):
                score.parse_sites(obj, ROOT)

    def test_answer_gives_the_lines_of_the_view_by_class(self):
        """A line with a decoy is only required; a dnc line is not counted; each list is sorted by path and line."""
        rec = record([site(10, rel="self"), site(9, rel="self"), site(9, "forbidden", "decoy", col=9),
                      site(5, rel="sibling"), site(6, "forbidden", "decoy"), site(2, "dnc", "comment", file="b/c.go")])
        self.assertEqual({"required": ["a.go:9", "a.go:10"], "forbidden": ["a.go:6"],
                          "not_counted": ["a.go:5", "b/c.go:2"]}, challenges.answer(challenge("refs"), rec))


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
        self.assertEqual({"refs", "rename", "impls", "callers", "dyncallers"}, seen)
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

    def test_callers_prompt_is_the_head_and_the_tail_of_the_language(self):
        """The whole prompt of each combination of the family `callers`: Go function, Go method, Python function,
        Python method, Python property."""
        go_tail = (" Find also each function or method that calls one of these callers. Do not go further than these "
                   "two levels. A call inside a function literal counts for the function or method declaration that "
                   "holds the literal. Test code counts. A file counts also when the build for this machine does not "
                   "compile it. Answer with the line that holds the name of each such function or method in its "
                   "declaration. Do not list `Run` itself.")
        py_tail = (" Find also each function or method that calls one of these callers. Do not go further than these "
                   "two levels. A call inside a lambda or a nested function counts for the outermost function or "
                   "method that holds it. A read of a property is a call of the property. Test code counts. Answer "
                   "with the line of the `def` statement of each such function or method. Do not list `Run` "
                   "itself.")
        beets_head = f"The repository at {ROOT} is a checkout of the project beets. Work only with this checkout."
        py_decl = {"file": "beets/library.py", "line": 7, "col": 9}

        def py_record(kind, container, prop):
            return dict(record(kind=kind, container=container, lang="python"), decl=py_decl, property=prop)

        cases = [
            (challenge("callers"), record(kind="func", container=""), HEAD,
             "Find each function or method of this repository that calls the function `Run` of the package "
             "`caddyhttp`, which is declared at a.go:1." + go_tail),
            (challenge("callers"), record(kind="method", container="App"), HEAD,
             "Find each function or method of this repository that calls the method `Run` of the type "
             "`caddyhttp.App`, which is declared at a.go:1." + go_tail),
            (challenge("callers", product="beets", tree="beets"), py_record("function", "", False), beets_head,
             "Find each function or method of this repository that calls the function `Run`, which is declared at "
             "beets/library.py:7." + py_tail),
            (challenge("callers", product="beets", tree="beets"), py_record("method", "App", False), beets_head,
             "Find each function or method of this repository that calls the method `Run` of the class `App`, "
             "which is declared at beets/library.py:7." + py_tail),
            (challenge("callers", product="beets", tree="beets"), py_record("method", "App", True), beets_head,
             "Find each function or method of this repository that reads the property `Run` of the class `App`, "
             "which is declared at beets/library.py:7." + py_tail),
        ]
        for ch, rec, head, task in cases:
            self.assertEqual(f"{head}\n\n{task}\n\n{TAIL}", challenges.prompt(ch, rec, ROOT), task)
        for kind, lang in (("iface_method", "go"), ("type", "go"), ("interface", "go"), ("class", "python")):
            with self.assertRaisesRegex(ValueError, "no prompt text"):
                self.task("callers", kind, "", lang=lang)

    def test_dyncallers_prompt_is_the_whole_text(self):
        """The family `dyncallers` has one text: a Go method."""
        task = ("Find each function or method of this repository that calls the method `Run` of the type "
                "`caddyhttp.App`, which is declared at a.go:1. A call counts when it names this method. A call of an "
                "interface method counts too, when the interface value can hold a value of this type. List only the "
                "direct callers: do not list the callers of the callers. A call inside a function literal counts for "
                "the function or method declaration that holds the literal. Test code counts. A file counts also "
                "when the build for this machine does not compile it. Answer with the line that holds the name of "
                "each such function or method in its declaration. Do not list `Run` itself.")
        self.assertEqual(f"{HEAD}\n\n{task}\n\n{TAIL}",
                         challenges.prompt(challenge("dyncallers"), dyncallers_record(), ROOT))
        for kind, lang, container in (("func", "go", ""), ("iface_method", "go", "Runner"), ("method", "python", "App"),
                                      ("function", "python", "")):
            with self.assertRaisesRegex(ValueError, "no prompt text"):
                self.task("dyncallers", kind, container, lang=lang)

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

    def test_text_scan_gives_no_numbers_for_a_callers_challenge(self):
        """No tree is read: the root does not exist."""
        got = challenges.text_scan(challenge("callers"), callers_record(), "/nonexistent/caddy")
        self.assertEqual({"lines": None, "precision": None, "recall": None}, got)
        got = challenges.text_scan(challenge("dyncallers"), dyncallers_record(), "/nonexistent/caddy")
        self.assertEqual({"lines": None, "precision": None, "recall": None}, got)


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
        """Overlap case 1: a Go method or interface method whose family holds a chosen record, or whose id
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
        """Overlap case 2: an impls candidate that is an implementer of a chosen impls record, or that has a
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
        """Overlap case 3: a record of beets/unique-used.jsonl with the container and the original name of a
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
        """The rename rule runs before the decoys rule, so `App.Provision` is never excluded. A
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


def csite(file, line, level, lit=False, configs=GO_ALL, cls="required"):
    """A caller site of a key record of `callkeys make`. A site in a Go file has `configs`."""
    s = {"file": file, "line": line, "col": 6, "class": cls, "why": "caller" if cls == "required" else "variant",
         "level": level, "lit": lit, "plant": False}
    if file.endswith(".go"):
        s["configs"] = list(configs)
    return s


def ckey(rid, n1=1, n2=0, container="", decl=None, lit=False, lit2=False, off=None, prop=False, at=None, extra=()):
    """A key record of `callkeys make` for the target `rid`: `n1` level-1 and `n2` level-2 required caller sites on
    their own lines of a file of the record (`at`: a given file, so two records can have equal required lines).
    `lit` and `off` (configs with no linux) go to the first level-1 site, `lit2` to the first level-2 site;
    `extra` adds sites. `decl` is (file, line). `levels` counts the required sites of each level."""
    go = rid.startswith(("go:", "plant:go:"))
    ext, name = (".go" if go else ".py"), rid.rsplit(".", 1)[-1]
    file = at or "calls/" + re.sub(r"\W", "_", rid) + ext
    dfile, dline = decl or ((name.lower() if go else f"beets/{name}") + ext, 1)
    sites = [csite(file, 10 + i, 1, lit=lit and i == 0, configs=off if off and i == 0 else GO_ALL) for i in range(n1)]
    sites += [csite(file, 100 + i, 2, lit=lit2 and i == 0) for i in range(n2)] + list(extra)
    levels = {str(n): sum(1 for s in sites if s["class"] == "required" and s["level"] == n) for n in (1, 2)}
    sites.append({"file": dfile, "line": dline, "col": 6, "class": "dnc", "why": "decl"})
    return {"id": rid, "lang": "go" if go else "python",
            "kind": "method" if container else "func" if go else "function", "name": name, "container": container,
            "decl": {"file": dfile, "line": dline, "col": 6}, "family": [rid], "implementers": [], "external": [],
            "source": "calls", "depth": 2, "property": prop, "plant": rid.startswith("plant:"), "levels": levels,
            "sites": sorted(sites, key=lambda s: (s["file"], s["line"], s["col"]))}


def plant_rec(rid, container, decl):
    """A record of a plant file: only its `decl` counts for `calls_set`."""
    return {"id": rid, "lang": "go" if rid.startswith("plant:go:") else "python", "kind": "method",
            "name": rid.rsplit(".", 1)[-1], "container": container,
            "decl": {"file": decl[0], "line": decl[1], "col": 6}, "source": "plant"}


P1A, P1B = "plant:go:caddy-plant-1:A.Apply", "plant:go:caddy-plant-1:B.Apply"
P2, P3, P3X = "plant:go:caddy-plant-2:C.Apply", "plant:go:caddy-plant-3:D.Apply", "plant:go:caddy-plant-3:E.Apply"
Q1, Q2 = "plant:python:beets-plant-1:K.apply", "plant:python:beets-plant-2:L.apply"
Q3A, Q3B = "plant:python:beets-plant-3:M.apply", "plant:python:beets-plant-3:N.apply"
PB = "py:beets"
# The candidates of the random rules (the closure and property rules can take one of them first).
CADDY_RANDOM = {f"{M}.R1", f"{M}.R2", f"{M}.R3", f"{M}.R4", f"{M}.BuildMac", f"{M}.BuildDnc", f"{M}.ClosureDeep",
                f"{M}.Srv.ClosureA"}
BEETS_RANDOM = {f"{PB}.r.f1", f"{PB}.r.f2", f"{PB}.r.f3", f"{PB}.r.f4", f"{PB}.p.K.prop_b", f"{PB}.n.nested_deep"}


def calls_fixture(root, reverse=False, drop=(), replace=None, extra=None):
    """A keys root and a trees root in which each rule of `calls_set` has known candidates and near misses.
    `drop` removes records by id from each key file, `replace` puts another record in the place of an id, `extra`
    adds records to a key file (path relative to the keys root). Each Go declaration file gets a package clause."""
    def put(rel, rs):
        rs = [(replace or {}).get(r["id"], r) for r in rs + (extra or {}).get(rel, []) if r["id"] not in drop]
        jsonl(os.path.join(root, "keys", rel), list(reversed(rs)) if reverse else rs)
        for r in rs:
            if r["lang"] == "go":
                write(os.path.join(root, "trees", rel.split("/")[0], r["decl"]["file"]), "package m\n")

    # caddy: Wide and WideCopy have the same required lines and a site off Linux; BuildDnc is off Linux only at a
    # dnc site; ClosureDeep has a lit site only at level 2; RNone has no level-1 caller.
    put("caddy/callers.jsonl", [
        ckey(f"{M}.Wide", 5, 45, at="calls/wide.go", off=WIN),
        ckey(f"{M}.WideCopy", 5, 45, at="calls/wide.go", off=WIN),
        ckey(f"{M}.BuildWin", 2, 10, off=WIN), ckey(f"{M}.BuildMac", 1, 5, off=MAC),
        ckey(f"{M}.BuildDnc", 1, 20, extra=[csite("calls/dnc.go", 500, 2, cls="dnc", configs=WIN)]),
        ckey(f"{M}.Srv.ClosureA", 2, 3, container="Srv", lit=True), ckey(f"{M}.ClosureB", 1, 1, lit=True),
        ckey(f"{M}.ClosureNoL2", 1, 0, lit=True), ckey(f"{M}.ClosureBig", 1, 40, lit=True),
        ckey(f"{M}.ClosureTest", 1, 1, lit=True, decl=("closure_test.go", 3)),
        ckey(f"{M}.ClosureDeep", 1, 2, lit2=True),
        *[ckey(f"{M}.R{i}", 1, 2) for i in range(1, 5)],
        ckey(f"{M}.RFewL2", 1, 1), ckey(f"{M}.RBig", 1, 40), ckey(f"{M}.RTest", 1, 2, decl=("r_test.go", 3)),
        ckey(f"{M}.RNone", 0, 0)])
    # caddy-plant-1: two planted targets (A also has a level-1 site at the decl of B: it is no via target), Wide
    # with the id of the rule-1 pick and a level-1 site at a planted decl, a via target, and a level-2 site at a
    # planted decl (no via target).
    put("caddy-plant-1/plant.jsonl", [plant_rec(P1A, "A", ("p1.go", 10)), plant_rec(P1B, "B", ("p1.go", 20))])
    put("caddy-plant-1/callers.jsonl", [
        ckey(P1A, 3, container="A", decl=("p1.go", 10), extra=[csite("p1.go", 20, 1)]),
        ckey(P1B, 5, container="B", decl=("p1.go", 20)),
        ckey(f"{M}.Wide", 5, 45, at="calls/wide.go", off=WIN, extra=[csite("p1.go", 10, 1)]),
        ckey(f"{M}.ViaOne", 1, extra=[csite("p1.go", 10, 1)]),
        ckey(f"{M}.NotVia", 1, 1, extra=[csite("p1.go", 20, 2)])])
    put("caddy-plant-2/plant.jsonl", [plant_rec(P2, "C", ("p2.go", 30))])
    put("caddy-plant-2/callers.jsonl", [
        ckey(P2, 2, container="C", decl=("p2.go", 30)), ckey(f"{M}.ViaOne", 1, extra=[csite("p2.go", 30, 1)]),
        ckey(f"{M}.ViaTwo", 0, 1, extra=[csite("p2.go", 30, 1)])])
    # caddy-plant-3: the planted record D has no level-1 caller (no candidate), E has no key record.
    put("caddy-plant-3/plant.jsonl", [plant_rec(P3, "D", ("p3.go", 40)), plant_rec(P3X, "E", ("p3.go", 50))])
    put("caddy-plant-3/callers.jsonl", [
        ckey(P3, 0, container="D", decl=("p3.go", 40)), ckey(f"{M}.ViaThree", 1, extra=[csite("p3.go", 40, 1)])])
    # beets: nested_test (a test declaration) and nested_big (more than 40 required lines) are candidates of the
    # nested rule; the other test declarations and near misses are no candidates.
    put("beets/callers.jsonl", [
        ckey(f"{PB}.w.wide_one", 5, 40),
        ckey(f"{PB}.p.K.prop_a", 1, 1, container="K", prop=True),
        ckey(f"{PB}.p.K.prop_b", 2, 2, container="K", prop=True),
        ckey(f"{PB}.p.K.prop_nol2", 1, 0, container="K", prop=True),
        ckey(f"{PB}.p.K.prop_test", 1, 1, container="K", prop=True, decl=("test/test_p.py", 3)),
        ckey(f"{PB}.p.K.prop_btest", 1, 1, container="K", prop=True, decl=("beets/test/helper.py", 3)),
        ckey(f"{PB}.n.nested_a", 1, 1, lit=True),
        ckey(f"{PB}.n.nested_test", 1, 1, lit=True, decl=("test/test_n.py", 3)),
        ckey(f"{PB}.n.nested_big", 1, 41, lit=True), ckey(f"{PB}.n.nested_nol2", 1, 0, lit=True),
        ckey(f"{PB}.n.nested_deep", 1, 2, lit2=True),
        *[ckey(f"{PB}.r.f{i}", 1, 2) for i in range(1, 5)],
        ckey(f"{PB}.r.f_few", 1, 1), ckey(f"{PB}.r.f_big", 1, 40),
        ckey(f"{PB}.r.f_test", 1, 2, decl=("test/test_r.py", 3)),
        ckey(f"{PB}.r.f_btest", 1, 2, decl=("beets/test/r.py", 3))])
    # beets-plant-1 has no planted target; beets-plant-3 has two with equal counts.
    put("beets-plant-1/plant.jsonl", [plant_rec(Q1, "K", ("beets/q1.py", 10))])
    put("beets-plant-1/callers.jsonl", [ckey(f"{PB}.v.via_one", 1, extra=[csite("beets/q1.py", 10, 1)])])
    put("beets-plant-2/plant.jsonl", [plant_rec(Q2, "L", ("beets/q2.py", 20))])
    put("beets-plant-2/callers.jsonl", [ckey(Q2, 2, container="L", decl=("beets/q2.py", 20))])
    put("beets-plant-3/plant.jsonl", [plant_rec(Q3A, "M", ("beets/q3.py", 30)),
                                      plant_rec(Q3B, "N", ("beets/q3.py", 40))])
    put("beets-plant-3/callers.jsonl", [
        ckey(Q3A, 3, container="M", decl=("beets/q3.py", 30)), ckey(Q3B, 3, container="N", decl=("beets/q3.py", 40)),
        ckey(f"{PB}.v.via_three", 1, extra=[csite("beets/q3.py", 40, 1)])])
    return os.path.join(root, "keys"), os.path.join(root, "trees")


def picks(chs):
    """(product, class word, tree, key id) of each challenge, in the order of the set."""
    return [(ch["product"], ch["note"].split(":")[0], ch["tree"], ch["key_id"]) for ch in chs]


class CallsSetTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        self.keys, self.trees = calls_fixture(os.path.join(self.d, "one"))

    def sets(self):
        return {seed: challenges.calls_set(seed, self.keys) for seed in SEEDS}

    def test_each_rule_chooses_the_expected_record(self):
        seen = {}
        for seed, chs in self.sets().items():
            got = picks(chs)
            self.assertEqual(20, len(got))
            self.assertEqual([("caddy", "wide", "caddy", f"{M}.Wide"), ("caddy", "build", "caddy", f"{M}.BuildWin")],
                             got[:2])
            self.assertIn(got[2][3], (f"{M}.Srv.ClosureA", f"{M}.ClosureB"))
            self.assertEqual([("caddy", "plant", "caddy-plant-1", P1B), ("caddy", "plant", "caddy-plant-2", P2)],
                             got[3:5])
            self.assertIn(got[5][1:], [("plant", "caddy-plant-1", f"{M}.ViaOne"),
                                       ("plant", "caddy-plant-2", f"{M}.ViaOne"),
                                       ("plant", "caddy-plant-2", f"{M}.ViaTwo"),
                                       ("plant", "caddy-plant-3", f"{M}.ViaThree")])
            self.assertEqual(("beets", "wide", "beets", f"{PB}.w.wide_one"), got[10])
            self.assertIn(got[11][3], (f"{PB}.p.K.prop_a", f"{PB}.p.K.prop_b"))
            self.assertIn(got[12][3], (f"{PB}.n.nested_a", f"{PB}.n.nested_test", f"{PB}.n.nested_big"))
            self.assertEqual([("beets", "plant", "beets-plant-2", Q2), ("beets", "plant", "beets-plant-3", Q3A)],
                             got[13:15])
            self.assertIn(got[15][1:], [("plant", "beets-plant-1", f"{PB}.v.via_one"),
                                        ("plant", "beets-plant-3", f"{PB}.v.via_three")])
            self.assertEqual(["closure", "property", "nested"], [got[2][1], got[11][1], got[12][1]])
            for start, pool in ((6, CADDY_RANDOM), (16, BEETS_RANDOM)):
                product = got[start][0]
                chosen = {p[3] for p in got[start - 6:start]}
                randoms = got[start:start + 4]
                self.assertEqual({(product, "random", product)}, {p[:3] for p in randoms})
                # One seeded sample: the first 4 free candidates, sorted by id, in the shuffle order of the seed.
                order = sorted(pool - chosen)
                random.Random(seed).shuffle(order)
                self.assertEqual(order[:4], [p[3] for p in randoms])
            for ch in chs:
                self.assertEqual(list(challenges.FIELDS), list(ch))
                self.assertEqual(("callers", f"{ch['tree']}/callers.jsonl", "random" if ch["note"].startswith("random")
                                  else "hard"), (ch["family"], ch["keys"], ch["sample"]))
            for i in (2, 5, 6, 11, 12, 15, 16):
                seen.setdefault(i, set()).add(got[i])
        # Each seeded rule gives more than one pick over the seeds.
        for i, values in seen.items():
            self.assertGreater(len(values), 1, i)

    def test_same_seed_and_another_record_order_give_the_same_set(self):
        again, _ = calls_fixture(os.path.join(self.d, "two"), reverse=True)
        sets = self.sets()
        for seed in SEEDS:
            self.assertEqual(sets[seed], challenges.calls_set(seed, again))
        self.assertGreater(len({json.dumps(chs) for chs in sets.values()}), 1)

    def test_via_pick_is_seeded_over_the_via_targets_sorted_by_tree_then_id(self):
        """The via targets of caddy: Wide of caddy-plant-1 is one by its sites, but rule 1 chose its id."""
        pool = [("caddy-plant-1", f"{M}.ViaOne"), ("caddy-plant-2", f"{M}.ViaOne"), ("caddy-plant-2", f"{M}.ViaTwo"),
                ("caddy-plant-3", f"{M}.ViaThree")]
        for seed, chs in self.sets().items():
            via = chs[5]
            self.assertEqual(random.Random(seed).choice(pool), (via["tree"], via["key_id"]))
            self.assertTrue(via["note"].startswith(f"plant: seeded choice (seed {seed}) among 4 via targets "),
                            via["note"])

    def test_notes_start_with_the_class_word_then_the_rule_facts_then_the_levels(self):
        chs = challenges.calls_set(3, self.keys)
        notes = {(ch["tree"], ch["key_id"]): ch["note"] for ch in chs}
        self.assertEqual("wide: most required lines (50); levels 1: 5, 2: 45", notes[("caddy", f"{M}.Wide")])
        self.assertEqual("build: most required lines (12); levels 1: 2, 2: 10", notes[("caddy", f"{M}.BuildWin")])
        self.assertEqual("plant: most required lines (5); levels 1: 5, 2: 0", notes[("caddy-plant-1", P1B)])
        self.assertEqual("plant: most required lines (3); levels 1: 3, 2: 0", notes[("beets-plant-3", Q3A)])
        prop = chs[11]
        levels = {f"{PB}.p.K.prop_a": "1: 1, 2: 1", f"{PB}.p.K.prop_b": "1: 2, 2: 2"}[prop["key_id"]]
        self.assertEqual("property: seeded choice (seed 3) among 2 candidates with property true, 1 or more level-2 "
                         f"callers and no test declaration; levels {levels}", prop["note"])
        free = len(CADDY_RANDOM - {chs[2]["key_id"]})
        for ch in chs[6:10]:
            rec = challenges.record_of(ch, self.keys)
            self.assertEqual(f"random: seeded sample (seed 3) of 4 among {free} candidates with 2 or more level-2 "
                             "callers, 40 or fewer required lines and no test declaration; levels 1: "
                             f"{rec['levels']['1']}, 2: {rec['levels']['2']}", ch["note"])
        for ch in chs:
            self.assertRegex(ch["note"], r"^(wide|build|closure|property|nested|plant|random): "
                                         r"(most required lines \(\d+\)|seeded choice \(seed 3\) among \d+ .+|"
                                         r"seeded sample \(seed 3\) of 4 among \d+ .+); levels 1: \d+, 2: \d+$")

    def test_ids_name_the_tree_and_the_function(self):
        for chs in self.sets().values():
            self.assertEqual(20, len({ch["id"] for ch in chs}))
            for ch in chs:
                rec = challenges.record_of(ch, self.keys)
                name = f"{rec['container']}.{rec['name']}" if rec["kind"] == "method" else rec["name"]
                tree = ch["tree"].replace(f"{ch['product']}-plant-", f"{ch['product']}-plant")
                self.assertEqual(f"{tree}-callers-{name}", ch["id"])
        ids = {ch["id"] for ch in challenges.calls_set(1, self.keys)}
        self.assertLessEqual({"caddy-callers-Wide", "caddy-callers-BuildWin", "caddy-plant1-callers-B.Apply",
                              "caddy-plant2-callers-C.Apply", "beets-callers-wide_one", "beets-plant2-callers-L.apply",
                              "beets-plant3-callers-M.apply"}, ids)

    def test_a_chosen_record_and_a_record_with_its_required_lines_are_no_candidates(self):
        """Wide (the pick of rule 1) and WideCopy (its required lines) have the most required lines of the
        candidates of the build rule. WideCopy with other lines is the build pick."""
        for chs in self.sets().values():
            self.assertEqual(f"{M}.BuildWin", chs[1]["key_id"])
            self.assertNotIn(f"{M}.WideCopy", {ch["key_id"] for ch in chs})
        moved = ckey(f"{M}.WideCopy", 5, 45, at="calls/other.go", off=WIN)
        keys_root, _ = calls_fixture(os.path.join(self.d, "moved"), replace={moved["id"]: moved})
        chs = challenges.calls_set(1, keys_root)
        self.assertEqual([f"{M}.Wide", f"{M}.WideCopy"], [chs[0]["key_id"], chs[1]["key_id"]])

    def test_a_rule_with_no_candidate_names_the_rule(self):
        cases = [({f"{M}.BuildWin", f"{M}.BuildMac"}, "caddy 2a build"),
                 ({f"{M}.Srv.ClosureA", f"{M}.ClosureB"}, "caddy 3a closure"),
                 ({P1A, P1B, P2}, "caddy 4 plant"),
                 ({f"{M}.ViaOne", f"{M}.ViaTwo", f"{M}.ViaThree"}, "caddy 5 plant"),
                 ({f"{M}.R1", f"{M}.R2", f"{M}.R3", f"{M}.R4", f"{M}.BuildMac", f"{M}.ClosureDeep"}, "caddy 6 random"),
                 ({f"{PB}.p.K.prop_a", f"{PB}.p.K.prop_b"}, "beets 2b property"),
                 ({f"{PB}.n.nested_a", f"{PB}.n.nested_test", f"{PB}.n.nested_big"}, "beets 3b nested")]
        for i, (drop, rule) in enumerate(cases):
            keys_root, _ = calls_fixture(os.path.join(self.d, f"drop{i}"), drop=drop)
            with self.assertRaisesRegex(LookupError, f"rule `{rule}`: "):
                challenges.calls_set(1, keys_root)
        keys_root, _ = calls_fixture(os.path.join(self.d, "none"))
        jsonl(os.path.join(keys_root, "caddy", "callers.jsonl"), [ckey(f"{M}.RNone", 0, 0)])
        with self.assertRaisesRegex(LookupError, "rule `caddy 1 wide`: "):
            challenges.calls_set(1, keys_root)

    def test_a_product_with_another_count_than_ten_names_the_rule(self):
        keys_root, _ = calls_fixture(os.path.join(self.d, "nine"), drop={P2})
        with self.assertRaisesRegex(LookupError, "rule `caddy 4 plant`: caddy has 9 challenges, expected 10"):
            challenges.calls_set(1, keys_root)
        third = ckey(P3X, 1, container="E", decl=("p3.go", 50))
        keys_root, _ = calls_fixture(os.path.join(self.d, "eleven"), extra={"caddy-plant-3/callers.jsonl": [third]})
        with self.assertRaisesRegex(LookupError, "rule `caddy 4 plant`: caddy has 11 challenges, expected 10"):
            challenges.calls_set(1, keys_root)

    def test_two_equal_ids_are_a_lookup_error(self):
        twin = ckey("go:example.com/other.Wide", 2, 10, off=WIN)
        keys_root, _ = calls_fixture(os.path.join(self.d, "twin"), replace={f"{M}.BuildWin": twin})
        with self.assertRaisesRegex(LookupError, "rule `caddy 2a build`: .*caddy-callers-Wide"):
            challenges.calls_set(1, keys_root)

    def test_random_skips_a_record_with_the_required_lines_of_an_earlier_record_of_the_sample(self):
        """R2 has the required lines of R1. The sample takes the next record of the shuffle order in its place.
        With only R1 to R4 free, the shuffle order ends after 3 records: LookupError."""
        twin = ckey(f"{M}.R2", 1, 2, at="calls/" + re.sub(r"\W", "_", f"{M}.R1") + ".go")
        keys_root, _ = calls_fixture(os.path.join(self.d, "twin"), replace={twin["id"]: twin})
        for seed in SEEDS:
            chs = challenges.calls_set(seed, keys_root)
            order = sorted(CADDY_RANDOM - {chs[2]["key_id"]})
            random.Random(seed).shuffle(order)
            first = next(i for i in order if i in (f"{M}.R1", f"{M}.R2"))
            expected = [i for i in order if i not in ({f"{M}.R1", f"{M}.R2"} - {first})][:4]
            self.assertEqual(expected, [ch["key_id"] for ch in chs[6:10]])
        keys_root, _ = calls_fixture(os.path.join(self.d, "short"), replace={twin["id"]: twin},
                                     drop={f"{M}.BuildMac", f"{M}.BuildDnc", f"{M}.ClosureDeep", f"{M}.Srv.ClosureA"})
        with self.assertRaisesRegex(LookupError, "rule `caddy 6 random`: 3 of 4 .* among 4 candidates"):
            challenges.calls_set(1, keys_root)

    def test_random_picks_are_no_neighbours_in_the_id_order(self):
        """16 free candidates whose ids differ only in a number: 4 successive seeded choices from a list with one
        record less each time take neighbours; one seeded sample does not (seed 1)."""
        numbered = [ckey(f"{M}.N{i:02d}", 1, 2) for i in range(16)]
        keys_root, _ = calls_fixture(os.path.join(self.d, "numbered"), drop=CADDY_RANDOM,
                                     extra={"caddy/callers.jsonl": numbered})
        chs = challenges.calls_set(1, keys_root)
        ids = sorted(r["id"] for r in numbered)
        positions = sorted(ids.index(ch["key_id"]) for ch in chs[6:10])
        self.assertEqual(4, len(set(positions)))
        self.assertNotEqual(list(range(positions[0], positions[0] + 4)), positions)
        self.assertTrue(chs[6]["note"].startswith("random: seeded sample (seed 1) of 4 among 16 candidates "))

    def test_cli_calls_writes_the_set_that_load_and_show_read(self):
        path = os.path.join(self.d, "calls1.jsonl")
        with mock.patch.object(challenges, "KEYS", self.keys), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(0, challenges.main(["calls", "-out", path, "-seed", "2"]))
        self.assertEqual(sorted(challenges.calls_set(2, self.keys), key=lambda ch: ch["id"]), challenges.load(path))
        out = io.StringIO()
        with mock.patch.object(challenges, "TREES", self.trees), contextlib.redirect_stdout(out):
            self.assertEqual(0, challenges.main(["show", "-set", path, "-root", self.trees, "-keys", self.keys]))
        text = out.getvalue()
        self.assertEqual(20, sum(1 for line in text.splitlines() if line.startswith("== ")))
        self.assertEqual(20, text.count("text scan: lines -, precision -, recall -"))
        self.assertIn("view lines: required 50, forbidden 0, dnc 1", text)
        self.assertIn("calls the function `Wide` of the package `m`, which is declared at wide.go:1.", text)
        self.assertIn("calls the method `Apply` of the type `m.B`, which is declared at p1.go:20.", text)
        self.assertIn("reads the property `prop_", text)


def dkey(container, name, static=1, trace=1, possible=0, at=None):
    """A key record of `callkeys dynmake` for the method `<container>.<name>`: `static` and `trace` required caller
    sites on their own lines of a file of the record (`at`: a given file, so two records can have equal required
    lines), and `possible` dnc sites."""
    rid = f"{M}.{container}.{name}"
    file, dfile = at or f"calls/{container}_{name}.go", f"{name.lower()}.go"
    sites = [{"file": file, "line": 10 + i, "col": 6, "class": "required", "why": "caller", "level": 1, "lit": False,
              "plant": False, "configs": list(GO_ALL), "proof": "static" if i < static else "trace"}
             for i in range(static + trace)]
    sites += [{"file": file, "line": 100 + i, "col": 6, "class": "dnc", "why": "possible"} for i in range(possible)]
    sites.append({"file": dfile, "line": 1, "col": 6, "class": "dnc", "why": "decl"})
    return {"id": rid, "lang": "go", "kind": "method", "name": name, "container": container,
            "decl": {"file": dfile, "line": 1, "col": 6}, "family": [rid], "implementers": [], "external": [],
            "source": "calls+trace", "depth": 1, "property": False, "plant": False,
            "levels": {"1": static + trace, "2": 0},
            "dynamic": {"static": static, "trace": trace, "possible": possible, "library": 0},
            "sites": sorted(sites, key=lambda s: (s["file"], s["line"], s["col"]))}


DUPS = {f"{M}.X.Dup", f"{M}.Y.Dup"}  # one method name
SAMES = {f"{M}.A.Same1", f"{M}.B.Same2"}  # one set of required lines
CALLS2_CANDIDATES = {f"{M}.T.N{i:02d}" for i in range(12)} | DUPS | SAMES | {f"{M}.Z.Edge"}


def calls2_fixture(root, reverse=False, drop=()):
    """A keys root with `caddy/dyncallers.jsonl` (17 candidates and 2 near misses) and a trees root with a package
    clause in each declaration file."""
    recs = [dkey("T", f"N{i:02d}", static=i % 3, trace=1 + i % 2, possible=i % 6) for i in range(12)]
    recs += [dkey("X", "Dup"), dkey("Y", "Dup"), dkey("A", "Same1", at="calls/same.go"),
             dkey("B", "Same2", at="calls/same.go"),
             dkey("Z", "Edge", static=0, trace=1, possible=5),  # the limits of a candidate
             dkey("Z", "NoTrace", static=3, trace=0), dkey("Z", "Many", possible=6)]  # no candidates
    recs = [r for r in recs if r["id"] not in drop]
    jsonl(os.path.join(root, "keys", "caddy", "dyncallers.jsonl"), list(reversed(recs)) if reverse else recs)
    for r in recs:
        write(os.path.join(root, "trees", "caddy", r["decl"]["file"]), "package m\n")
    return os.path.join(root, "keys"), os.path.join(root, "trees")


class CallsTwoSetTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        self.keys, self.trees = calls2_fixture(os.path.join(self.d, "one"))

    def test_seeded_sample_skips_a_chosen_name_and_a_chosen_set_of_required_lines(self):
        sets = set()
        for seed in SEEDS:
            chs = challenges.calls2_set(seed, self.keys)
            order = sorted(CALLS2_CANDIDATES)
            random.Random(seed).shuffle(order)
            first_dup = next(i for i in order if i in DUPS)
            first_same = next(i for i in order if i in SAMES)
            skipped = (DUPS - {first_dup}) | (SAMES - {first_same})
            self.assertEqual([i for i in order if i not in skipped][:10], [ch["key_id"] for ch in chs])
            sets.add(tuple(ch["key_id"] for ch in chs))
        self.assertGreater(len(sets), 1)

    def test_same_seed_and_another_record_order_give_the_same_set(self):
        again, _ = calls2_fixture(os.path.join(self.d, "two"), reverse=True)
        for seed in SEEDS:
            self.assertEqual(challenges.calls2_set(seed, self.keys), challenges.calls2_set(seed, again))

    def test_ids_fields_and_notes(self):
        for ch in challenges.calls2_set(3, self.keys):
            rec = challenges.record_of(ch, self.keys)
            d = rec["dynamic"]
            self.assertEqual(list(challenges.FIELDS), list(ch))
            self.assertEqual({"id": f"caddy-dyncallers-{rec['container']}.{rec['name']}", "product": "caddy",
                              "tree": "caddy", "family": "dyncallers", "keys": "caddy/dyncallers.jsonl",
                              "key_id": rec["id"], "sample": "hard",
                              "note": f"dynamic: seeded sample (seed 3) of 10 among 17 candidates; static "
                                      f"{d['static']}, trace {d['trace']}, possible {d['possible']}"}, ch)

    def test_too_few_records_is_a_lookup_error(self):
        """10 candidates, but the two names and the two sets of required lines leave 8 records."""
        keys_root, _ = calls2_fixture(os.path.join(self.d, "few"), drop={f"{M}.T.N{i:02d}" for i in range(7)})
        with self.assertRaisesRegex(LookupError, r"8 of 10 records for the seeded sample \(seed 1\) among 10 "
                                                 "candidates"):
            challenges.calls2_set(1, keys_root)

    def test_cli_calls2_writes_the_set_that_load_and_show_read(self):
        path = os.path.join(self.d, "calls2.jsonl")
        with mock.patch.object(challenges, "KEYS", self.keys), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(0, challenges.main(["calls2", "-out", path, "-seed", "2"]))
        self.assertEqual(sorted(challenges.calls2_set(2, self.keys), key=lambda ch: ch["id"]), challenges.load(path))
        out = io.StringIO()
        with mock.patch.object(challenges, "TREES", self.trees), contextlib.redirect_stdout(out):
            self.assertEqual(0, challenges.main(["show", "-set", path, "-root", self.trees, "-keys", self.keys]))
        text = out.getvalue()
        self.assertEqual(10, sum(1 for line in text.splitlines() if line.startswith("== ")))
        self.assertEqual(10, text.count("text scan: lines -, precision -, recall -"))
        self.assertEqual(10, text.count("A call of an interface method counts too, when the interface value can hold "
                                        "a value of this type."))
        self.assertRegex(text, r"calls the method `N\d\d` of the type `m\.T`, which is declared at n\d\d\.go:1\.")


if __name__ == "__main__":
    unittest.main()
