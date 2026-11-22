import contextlib
import io
import json
import os
import random
import shutil
import tempfile
import unittest
from unittest import mock

from audit import callers
from audit.tests.test_symbols_unit import FakeMcp, ToolError, fake
from common import keyrecord as keys
from common import lock

CONFIGS = ["linux", "windows", "darwin"]

# The functions of the tree: only `decl` and `end` (and `top` for a nested Python function) count.
CALLS = [{"decl": {"file": "b.go", "line": 1, "col": 6}, "end": 30},
         {"decl": {"file": "c.go", "line": 1, "col": 6}, "end": 10},
         {"decl": {"file": "d.go", "line": 1, "col": 6}, "end": 20},
         {"decl": {"file": "d.go", "line": 4, "col": 9}, "end": 9, "top": {"file": "d.go", "line": 1, "col": 6}},
         {"decl": {"file": "s.go", "line": 1, "col": 6}, "end": 10},
         {"decl": {"file": "t.go", "line": 1, "col": 6}, "end": 10},
         {"decl": {"file": "p.go", "line": 1, "col": 6}, "end": 10}]


def caller(file, line, level=1, lit=False, proof=None):
    out = {"file": file, "line": line, "col": 6, "class": "required", "why": "caller", "level": level,
           "lit": lit, "plant": False, "configs": CONFIGS}
    if proof is not None:
        out["proof"] = proof
    return out


def target(rid, sites, levels=None, dynamic=None):
    """A caller key record; the target is at `<rid>.go:10:6`, a `dnc` site (recursion)."""
    file = rid + ".go"
    rec = {"id": rid, "lang": "go", "kind": "func", "name": rid, "container": "pkg",
           "decl": {"file": file, "line": 10, "col": 6}, "family": [rid], "implementers": [], "source": "calls",
           "depth": 2, "property": False, "plant": False, "levels": levels or {"1": 1, "2": 0},
           "sites": [{"file": file, "line": 10, "col": 6, "class": "dnc", "why": "decl"}] + sites}
    if dynamic is not None:
        rec["dynamic"] = dynamic
    return rec


def node(file, line, kind="FUNCTION", children=()):
    return {"name": "f", "qualifiedName": "pkg.f", "kind": kind, "file": file, "line": line, "column": 6,
            "enclosingScope": [], "children": list(children)}


def score(tp, fp, miss, miss_sites=(), fp_sites=()):
    return {"tp": tp, "fp": fp, "miss": miss, "exact": fp == 0 and miss == 0, "miss_sites": list(miss_sites),
            "fp_sites": list(fp_sites)}


EXACT = target("x", [caller("b.go", 1)])
LEVEL2 = target("y", [caller("b.go", 1), caller("c.go", 1, level=2)], {"1": 1, "2": 1})
CLOSURE = target("z", [caller("d.go", 1, lit=True)])
BROKEN = target("e", [caller("b.go", 1)])

TREES = {"x.go": [node("b.go", 1), node("/usr/lib/go/src/x.go", 3, kind="METHOD")],
         "y.go": [node("b.go", 1)],
         "z.go": [node("d.go", 5, kind="CLOSURE")],
         "e.go": ToolError({"error": "symbol_not_found", "message": "No symbol at e.go:10:6"})}


def hierarchy_answer(tool, args):
    tree = TREES[args["file"]]
    return tree if isinstance(tree, ToolError) else {"element": {"name": "t"}, "calls": tree, "truncated": False}


class AuditCallersTest(unittest.TestCase):
    def test_four_targets(self):
        server, client = fake(self, hierarchy_answer)
        rows = callers.audit_callers(client, [EXACT, LEVEL2, CLOSURE, BROKEN], CALLS)
        self.assertEqual({"file": "x.go", "line": 10, "column": 6, "direction": "callers", "maxDepth": 2,
                          "project_path": "/bench/trees/caddy"}, server.calls[0]["args"])
        self.assertEqual(["ide_call_hierarchy"] * 4, [c["tool"] for c in server.calls])
        head = {"truncated": False, "deeper": 0, "notes": None, "warnings": None}
        # An exact answer; a node outside the tree counts in `kinds` only.
        self.assertEqual({"id": "x", "levels": {"1": 1, "2": 0}, "property": False, **head,
                          "kinds": {"FUNCTION": 1, "METHOD": 1, "outside-tree": 1},
                          "raw": score(1, 0, 0), "mapped": score(1, 0, 0)}, rows[0])
        # A missed level-2 caller: the miss site has its level, its literal flag and its configs.
        missed = score(1, 0, 1, [["c.go", 1, 2, False, CONFIGS]])
        self.assertEqual({"id": "y", "levels": {"1": 1, "2": 1}, "property": False, **head, "kinds": {"FUNCTION": 1},
                          "raw": missed, "mapped": missed}, rows[1])
        # A closure node at the line of the literal: raw has a false line and a miss; mapped counts the node
        # as its outermost function (d.go:1, not the nested function at d.go:4).
        self.assertEqual({"id": "z", "levels": {"1": 1, "2": 0}, "property": False, **head, "kinds": {"CLOSURE": 1},
                          "raw": score(0, 1, 1, [["d.go", 1, 1, True, CONFIGS]], [["d.go", 5]]),
                          "mapped": score(1, 0, 0)}, rows[2])
        # An error result: no score.
        self.assertEqual({"id": "e", "levels": {"1": 1, "2": 0}, "property": False,
                          "error": "tool: symbol_not_found: No symbol at e.go:10:6"}, rows[3])

    def test_level_two_nodes_are_the_children(self):
        tree = [node("b.go", 1, children=[node("c.go", 1)])]
        _, client = fake(self, lambda tool, args: {"calls": tree, "truncated": True, "notes": ["n"]})
        row = callers.audit_callers(client, [LEVEL2], CALLS)[0]
        self.assertEqual((True, ["n"], {"FUNCTION": 2}), (row["truncated"], row["notes"], row["kinds"]))
        self.assertEqual(score(2, 0, 0), row["mapped"])


DYN = target("m", [caller("s.go", 1, proof="static"), caller("t.go", 1, proof="trace"),
                   {"file": "p.go", "line": 1, "col": 6, "class": "dnc", "why": "possible", "level": 1}],
             dynamic={"static": 1, "trace": 1, "possible": 1, "library": 0})
DYN_FP = target("f", [caller("s.go", 1, proof="static")], dynamic={"static": 1, "trace": 0, "possible": 0, "library": 0})


def usage(file, line, match=None):
    row = {"file": file, "line": line, "column": 3, "usageType": "METHOD_CALL"}
    if match is not None:
        row["match"] = match
    return row


def dyn_answer(tool, args):
    if tool == "ide_call_hierarchy":
        if args["file"] == "m.go":
            return {"calls": [node("s.go", 1)]}
        return {"calls": [node("s.go", 1)] + [node("q.go", n) for n in range(1, 10)]}
    if args["file"] == "f.go":
        return ToolError({"error": "index_not_ready", "message": "dumb mode"})
    return {"usages": [usage("s.go", 4), usage("t.go", 6, "BASE"), usage("p.go", 3, "BASE"), usage("s.go", 40)],
            "hasMore": False, "notes": ["base rows"]}


class AuditDynTest(unittest.TestCase):
    def test_hierarchy_and_usages(self):
        server, client = fake(self, dyn_answer)
        rows = callers.audit_dyn(client, [DYN, DYN_FP], CALLS)
        self.assertEqual({"file": "m.go", "line": 10, "column": 6, "direction": "callers", "maxDepth": 1,
                          "project_path": "/bench/trees/caddy"}, server.calls[0]["args"])
        self.assertEqual({"file": "m.go", "line": 10, "column": 6, "project_path": "/bench/trees/caddy"},
                         server.calls[1]["args"])
        self.assertEqual({"id": "m", "name": "pkg.m", "dynamic": DYN["dynamic"], "hierarchy_nodes": 1,
                          "usage_rows": 4, "usage_marks": {"-": 2, "BASE": 2, "in no function": 1}, "usage_notes": 1,
                          "hierarchy": {"tp": 1, "fp": 0, "miss": 1, "ignored": 0, "exact": False,
                                        "miss_proof": {"trace": 1}, "miss_sites": [["t.go", 1]], "fp_sites": []},
                          "usages": {"tp": 2, "fp": 0, "miss": 0, "ignored": 1, "exact": True, "miss_proof": {},
                                     "miss_sites": [], "fp_sites": []}}, rows[0])

    def test_each_false_line_and_an_error(self):
        _, client = fake(self, dyn_answer)
        row = callers.audit_dyn(client, [DYN_FP], CALLS)[0]
        # The script kept the first 8 false lines; the port keeps each one.
        self.assertEqual([["q.go", n] for n in range(1, 10)], row["hierarchy"]["fp_sites"])
        self.assertEqual(9, row["hierarchy"]["fp"])
        self.assertEqual("tool: index_not_ready: dumb mode", row["usages_error"])
        self.assertNotIn("usages", row)


class SelectTest(unittest.TestCase):
    def test_sample_is_the_seeded_sample_of_the_script(self):
        records = [target(f"r{i}", []) for i in range(20)]
        script = sorted(records, key=lambda r: r["id"])
        random.Random(7).shuffle(script)
        self.assertEqual(sorted(r["id"] for r in script[:5]),
                         [r["id"] for r in callers.sample(list(reversed(records)), 5, 7)])

    def test_pick_keeps_the_order_and_refuses_an_unknown_id(self):
        records = [target("a", []), target("b", [])]
        self.assertEqual(["b", "a"], [r["id"] for r in callers.pick(records, ["b", "a"])])
        with self.assertRaisesRegex(ValueError, "zz"):
            callers.pick(records, ["zz"])


class MainTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        env = mock.patch.dict(os.environ, {"BENCH_ROOT": os.path.join(self.dir, "bench")})
        env.start()
        self.addCleanup(env.stop)
        self.keys = os.path.join(self.dir, "callers.jsonl")
        keys.save_keys(self.keys, [EXACT, LEVEL2, CLOSURE, BROKEN])
        self.calls = os.path.join(self.dir, "calls.jsonl")
        with open(self.calls, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(c) + "\n" for c in CALLS)
        self.out = os.path.join(self.dir, "out.jsonl")

    def args(self, server, command, *more):
        return [command, "-url", server.url, "-project", "/p", "-keys", self.keys, "-calls", self.calls,
                "-out", self.out, *more]

    def lines(self):
        with open(self.out, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_callers_with_an_ids_file(self):
        server = FakeMcp(hierarchy_answer)
        self.addCleanup(server.close)
        ids = os.path.join(self.dir, "ids.txt")
        with open(ids, "w", encoding="utf-8") as f:
            f.write("z\nx\n\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(0, callers.main(self.args(server, "callers", "-ids", ids)))
        lines = self.lines()
        self.assertEqual({"id": "_meta", "version": "2.1.1-dev.12", "project": "/p", "keys": self.keys, "n": 2},
                         lines[0])
        self.assertEqual(["z", "x"], [r["id"] for r in lines[1:]])
        self.assertIn("plugin 2.1.1-dev.12 | records 2 | errors 0", out.getvalue())
        self.assertIn("mapped: exact 2 of 2", out.getvalue())

    def test_callers_with_a_sample(self):
        server = FakeMcp(hierarchy_answer)
        self.addCleanup(server.close)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, callers.main(self.args(server, "callers", "-n", "2", "-seed", "3")))
        self.assertEqual([r["id"] for r in callers.sample([EXACT, LEVEL2, CLOSURE, BROKEN], 2, 3)],
                         [r["id"] for r in self.lines()[1:]])

    def test_dyn_takes_the_records_with_a_traced_caller(self):
        keys.save_keys(self.keys, [DYN, DYN_FP])
        server = FakeMcp(dyn_answer)
        self.addCleanup(server.close)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, callers.main(self.args(server, "dyn")))
        lines = self.lines()
        self.assertEqual({"id": "_meta", "version": "2.1.1-dev.12", "project": "/p", "n": 1}, lines[0])
        self.assertEqual(["m"], [r["id"] for r in lines[1:]])

    def test_a_busy_lock_makes_no_call(self):
        server = FakeMcp(hierarchy_answer)
        self.addCleanup(server.close)
        err = io.StringIO()
        with lock.ide_lock("bench.runner batch b1"), contextlib.redirect_stderr(err):
            self.assertEqual(2, callers.main(self.args(server, "callers", "-n", "2")))
        self.assertIn("bench.runner batch b1", err.getvalue())
        self.assertEqual(0, server.requests)
        self.assertFalse(os.path.exists(self.out))

    def test_dumb_mode_gives_exit_4_and_no_file(self):
        server = FakeMcp(hierarchy_answer)
        self.addCleanup(server.close)
        server.dumb = [True] * 1000
        with mock.patch.object(callers, "READY_TIMEOUT", 0.2), mock.patch.object(callers, "READY_POLL", 0.05), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(4, callers.main(self.args(server, "callers", "-n", "2")))
        self.assertFalse(os.path.exists(self.out))
        self.assertEqual([], [c for c in server.calls if c["method"] == "tools/call"])


if __name__ == "__main__":
    unittest.main()
