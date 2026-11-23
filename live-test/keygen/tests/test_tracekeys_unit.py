import contextlib
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from common import keyrecord as keys
from keygen import tracekeys

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_TEST_DIR = os.path.dirname(os.path.dirname(HERE))

I_RUN = "go:m.I.Run"
J_RUN = "go:m.J.Run"


def at(file, line=1, col=6):
    return {"file": file, "line": line, "col": col}


def fn(key, file, line=1, calls=()):
    """A function of the graph. `key` is `Name` or `Type.Name`; the id is `go:m.<key>`."""
    container, _, name = key.rpartition(".")
    return {"rec": "func", "id": f"go:m.{key}", "kind": "method" if container else "func", "name": name,
            "container": container, "decl": at(file, line), "end": line + 5, "calls": list(calls)}


def call(line, col, callee, kind="direct", lit=False, iface_id=""):
    return {"line": line, "col": col, "callee": callee, "kind": kind, "lit": lit, "iface": iface_id}


def use(file, line, col, in_, is_call=True, configs=("linux", "windows", "darwin"), lit=False):
    return {"file": file, "line": line, "col": col, "call": is_call, "in": in_, "lit": lit, "configs": list(configs)}


def calls_of(funcs, uses=None):
    """The records of calls.jsonl for the functions of a graph; `uses` maps a function key to its uses."""
    uses = uses or {}
    return [{"id": f["id"], "lang": "go", "kind": f["kind"], "name": f["name"], "container": f["container"],
             "decl": f["decl"], "end": f["end"], "configs": ["linux", "windows", "darwin"],
             "uses": uses.get(f["id"][len("go:m."):], [])} for f in funcs]


def iface(name, method, starts, decl_file="i.go", more=()):
    """A module interface with one method whose implementers are K<i> with their own method at `starts[i]`."""
    impls = [{"type": f"go:m.K{i}", "type_decl": at(s["file"], 30), "method": s, "own": True}
             for i, s in enumerate(starts, 1)]
    return {"rec": "iface", "id": f"go:m.{name}", "name": name, "decl": at(decl_file),
            "methods": [{"id": f"go:m.{name}.{method}", "name": method, "decl": at(decl_file, 2, 2),
                         "impls": impls + list(more)}]}


# The small graph. Each function is at line 1 of its own file.
D = {k: at(f) for k, f in (("T", "t.go"), ("A", "a.go"), ("B", "b.go"), ("C", "c.go"), ("D", "d.go"),
                           ("E", "e.go"), ("F", "f.go"), ("G", "g.go"), ("U", "u.go"), ("V", "v.go"),
                           ("W.T", "w_t.go"))}


def base_funcs():
    return [
        fn("T", "t.go", calls=[call(2, 2, D["A"])]),  # a step out of the target
        fn("A", "a.go", calls=[call(2, 2, D["T"])]),
        fn("B", "b.go", calls=[call(2, 4, D["A"], "embedded")]),
        fn("C", "c.go", calls=[call(2, 4, D["T"], "iface", iface_id=J_RUN),  # U is a second callee, on no way
                               call(2, 4, D["U"], "iface", iface_id=J_RUN)]),
        fn("D", "d.go", calls=[call(2, 9, D["A"], lit=True)]),
        fn("E", "e.go", calls=[call(2, 2, D["D"]), call(3, 2, D["W.T"]), call(4, 2, None, "other")]),
        fn("F", "f.go", calls=[call(2, 2, D["C"])]),
        fn("G", "g.go", calls=[call(2, 2, D["B"]), call(3, 2, D["G"])]),  # a self recursion: the cycle
        fn("U", "u.go"),
        fn("V", "v.go"),
        fn("W.T", "w_t.go"),  # a function outside the way with the name of the target
    ]


BASE_USES = {
    "T": [use("a.go", 2, 2, D["A"]),
          use("x_test.go", 4, 2, at("x_test.go", 3)),  # X -> T in a test file only
          use("t_windows.go", 5, 2, at("t_windows.go", 3), configs=("windows",)),
          use("k.go", 2, 2, at("k.go"))],  # in no function of the graph
    "A": [use("t.go", 2, 2, D["T"]), use("b.go", 2, 4, D["B"]), use("d.go", 2, 9, D["D"], lit=True),
          use("v.go", 3, 9, D["V"], is_call=False),  # a value use
          use("f.go", 2, 4, D["F"], is_call=False),  # a value use on the line of the step F -> C
          use("a.go", 9, 5, None)],  # a call outside each function
    "D": [use("e.go", 2, 2, D["E"])],
}


def starts_funcs():
    """The small graph with the methods K1.Run .. K6.Run of the interface method I.Run: K1 calls C, K2 calls F."""
    return base_funcs() + [fn("K1.Run", "s1.go", calls=[call(2, 2, D["C"])]),
                           fn("K2.Run", "s2.go", calls=[call(2, 2, D["F"])])] + [
        fn(f"K{i}.Run", f"s{i}.go") for i in range(3, 7)]


STARTS = [at(f"s{i}.go") for i in range(1, 7)]


def by_id(records, rid):
    return next(r for r in records if r["id"] == rid)


def complete(records, key):
    rec = by_id(records, f"go:m.{key}")
    assert rec["form"] == "complete", rec["form"]
    return rec


def decls(functions):
    return [f'{f["decl"]["file"]}:{f["decl"]["line"]}' for f in functions]


def distances(rec, *keys_):
    ids = {f"go:m.{k}": k for k in keys_}
    return {ids[f["id"]]: (f["any"], f["direct"], f["plain"]) for f in rec["functions"] if f["id"] in ids}


def lines(rec, cls):
    return {(s["file"], s["line"]) for s in rec["sites"] if s["class"] == cls}


def dnc_lines(rec):
    return lines(rec, "dnc")


def required_lines(rec):
    return lines(rec, "required")


def make(funcs, ifaces=(), uses=None, extra=(), large=0, seed=1):
    return tracekeys.make_records(funcs, list(ifaces), calls_of(funcs, uses), list(extra), large, seed)


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = tracekeys.main(argv)
    return code, out.getvalue(), err.getvalue()


class CompleteFormTest(unittest.TestCase):
    def setUp(self):
        self.records, self.stats = make(base_funcs(), uses=BASE_USES)

    def test_complete_record_of_a_small_graph(self):
        rec = complete(self.records, "T")
        self.assertEqual(("go:m.T", "go", "func", "T", "", at("t.go"), "graph", "complete", "complete", None),
                         tuple(rec[k] for k in ("id", "lang", "kind", "name", "container", "decl", "source", "form",
                                                "pool", "from")))
        self.assertEqual(["a.go:1", "b.go:1", "c.go:1", "d.go:1", "e.go:1", "f.go:1", "g.go:1"],
                         decls(rec["functions"]))
        self.assertEqual({"A": (1, 1, 1), "B": (2, 2, 2), "D": (2, 2, 2), "E": (3, 3, None), "C": (1, None, None),
                          "G": (3, 3, 3)},
                         distances(rec, "A", "B", "D", "E", "C", "G"))  # (any, direct, plain)
        self.assertEqual((3, True, ["cycle", "embedded", "iface", "lit"], True),
                         (rec["depth"], rec["cycle"], rec["hops"], rec["partial_iface"]))
        self.assertIn(("v.go", 3), dnc_lines(rec))  # value use; x_test.go line is dnc too
        self.assertEqual({("t.go", 1), ("a.go", 1), ("b.go", 1), ("c.go", 1), ("d.go", 1), ("e.go", 1), ("f.go", 1),
                          ("g.go", 1),  # the decls
                          ("x_test.go", 4), ("t_windows.go", 5), ("k.go", 2), ("v.go", 3), ("f.go", 2), ("a.go", 9)},
                         dnc_lines(rec))
        self.assertEqual({("a.go", 2), ("b.go", 2), ("c.go", 2), ("d.go", 2), ("e.go", 2), ("f.go", 2), ("g.go", 2),
                          ("g.go", 3)}, required_lines(rec))
        self.assertEqual(8, rec["required"])
        self.assertEqual([at("w_t.go")], rec["decoys"])
        self.assertEqual({"caller": at("c.go"), "call": at("c.go", 2, 4), "callee": at("t.go"), "kind": "iface",
                          "lit": False}, next(s for s in rec["steps"] if s["caller"] == at("c.go")))
        self.assertEqual(9, len(rec["steps"]))  # the 8 required steps and T -> A; no step to U or to W.T
        self.assertEqual(rec["sites"], sorted(rec["sites"], key=lambda s: (s["file"], s["line"], s["col"])))

    def test_one_line_with_two_steps_is_one_required_line(self):
        t, p, q = at("t.go"), at("p.go"), at("q.go")
        funcs = [fn("T", "t.go"),
                 fn("P", "p.go", calls=[call(2, 2, t)]),
                 fn("Q", "q.go", calls=[call(2, 2, t)]),
                 fn("C", "c.go", calls=[call(2, 4, p, "iface", iface_id=J_RUN),
                                        call(2, 4, q, "iface", iface_id=J_RUN)]),
                 fn("R", "r.go", calls=[call(2, 2, p), call(2, 10, q)])]  # two calls on one line
        rec = by_id(make(funcs, extra=[{"target": "go:m.T"}])[0], "go:m.T")
        self.assertEqual(6, len(rec["steps"]))
        self.assertEqual([at("c.go", 2, 4), at("p.go", 2, 2), at("q.go", 2, 2), at("r.go", 2, 2), at("r.go", 2, 10)],
                         [{k: s[k] for k in ("file", "line", "col")} for s in rec["sites"] if s["class"] == "required"])
        self.assertEqual(4, rec["required"])
        self.assertEqual({("c.go", 2), ("p.go", 2), ("q.go", 2), ("r.go", 2)}, required_lines(rec))
        self.assertFalse(rec["partial_iface"])  # both callees are on a way

    def test_a_step_out_of_the_target_is_kept_and_not_required(self):
        # T -> A is an interface call with a second callee Q outside N: a call inside T makes no partial interface.
        funcs = [fn("T", "t.go", calls=[call(2, 2, at("a.go"), "iface", iface_id=J_RUN),
                                        call(2, 2, at("q.go"), "iface", iface_id=J_RUN)]),
                 fn("A", "a.go", calls=[call(2, 2, at("t.go"))]),
                 fn("Q", "q.go")]
        rec = by_id(make(funcs, extra=[{"target": "go:m.T"}])[0], "go:m.T")
        self.assertIn({"caller": at("t.go"), "call": at("t.go", 2, 2), "callee": at("a.go"), "kind": "iface",
                       "lit": False}, rec["steps"])
        self.assertEqual(({("a.go", 2)}, 1), (required_lines(rec), rec["required"]))
        self.assertNotIn(("t.go", 2), dnc_lines(rec))
        self.assertEqual((False, [], 1, False), (rec["cycle"], rec["hops"], rec["depth"], rec["partial_iface"]))
        score = keys.score({("a.go", 2), ("t.go", 2)}, rec)
        self.assertEqual((1, 1, 0), (score["tp"], score["fp"], score["miss"]))
        # In the small graph too, T -> A is a step of the record and its line is no site.
        base = complete(self.records, "T")
        self.assertIn({"caller": at("t.go"), "call": at("t.go", 2, 2), "callee": at("a.go"), "kind": "direct",
                       "lit": False}, base["steps"])
        self.assertNotIn(("t.go", 2), required_lines(base) | dnc_lines(base))

    def test_two_ways_of_different_length_and_kind(self):
        # X calls T through an interface (1 step), and X -> A -> B -> T is a direct way of 3 steps.
        funcs = [fn("T", "t.go"),
                 fn("X", "x.go", calls=[call(2, 4, at("t.go"), "iface", iface_id=J_RUN), call(3, 2, at("a.go"))]),
                 fn("A", "a.go", calls=[call(2, 2, at("b.go"))]),
                 fn("B", "b.go", calls=[call(2, 2, at("t.go"))])]
        rec = by_id(make(funcs, extra=[{"target": "go:m.T"}])[0], "go:m.T")
        self.assertEqual({"X": (1, 3, 3), "A": (2, 2, 2), "B": (1, 1, 1)}, distances(rec, "X", "A", "B"))
        self.assertEqual((2, False, ["iface"]), (rec["depth"], rec["cycle"], rec["hops"]))

    def test_a_cycle_of_two_functions(self):
        funcs = [fn("T", "t.go"),
                 fn("A", "a.go", calls=[call(2, 2, at("t.go")), call(3, 2, at("b.go"))]),
                 fn("B", "b.go", calls=[call(2, 2, at("a.go"))])]
        rec = by_id(make(funcs, extra=[{"target": "go:m.T"}])[0], "go:m.T")
        self.assertEqual({"A": (1, 1, 1), "B": (2, 2, 2)}, distances(rec, "A", "B"))
        self.assertEqual((2, True, ["cycle"]), (rec["depth"], rec["cycle"], rec["hops"]))
        self.assertEqual({("a.go", 2), ("a.go", 3), ("b.go", 2)}, required_lines(rec))

    def test_a_required_line_wins_over_a_use_on_the_same_line(self):
        rec = complete(self.records, "T")
        self.assertIn({**at("f.go", 2, 2), "class": "required", "why": "step"}, rec["sites"])
        self.assertIn({**at("f.go", 2, 4), "class": "dnc", "why": "use"}, rec["sites"])
        self.assertEqual("required", keys.line_classes(rec)[("f.go", 2)])

    def test_statistics(self):
        self.assertEqual(11, self.stats["functions"])
        self.assertEqual({"direct": 8, "embedded": 1, "iface": 2}, self.stats["steps"])
        # T 7, A 7 (T -> A is a step on the way to A), U 2 (C, F), B 1, C 1, D 1, W.T 1; E, F, G, V 0.
        self.assertEqual({"1-9": 7, "10-19": 0, "20-39": 0, "40-79": 0, "80+": 0}, self.stats["sizes"])
        self.assertEqual({"complete": 2, "from": 0, "empty": 0, "extra": 0, "large": 0}, self.stats["pools"])
        self.assertEqual(["go:m.A", "go:m.T"], sorted(r["id"] for r in self.records))


class StartSetTest(unittest.TestCase):
    def test_start_set_record(self):
        funcs = starts_funcs()
        records, _ = make(funcs, [iface("I", "Run", STARTS)], BASE_USES,
                          extra=[{"target": "go:m.T", "from": I_RUN}, {"target": "go:m.C", "from": I_RUN}])
        rec = by_id(records, f"go:m.T from {I_RUN}")
        self.assertEqual(("from", "extra", at("t.go")), (rec["form"], rec["pool"], rec["decl"]))
        self.assertEqual({"id": I_RUN, "name": "Run", "container": "I", "decl": at("i.go", 2, 2), "starts": STARTS,
                          "on_way": 2, "second_iface": True}, rec["from"])
        # T -> A is no step of the walk: A, and B, D, E, G above it, are in no way from a start.
        self.assertEqual(["c.go:1", "f.go:1", "s1.go:1", "s2.go:1"], decls(rec["functions"]))
        self.assertEqual({("s1.go", 2), ("s2.go", 2), ("f.go", 2), ("c.go", 2)}, required_lines(rec))
        self.assertEqual(4, len(rec["steps"]))
        self.assertEqual({("t.go", 1), ("c.go", 1), ("f.go", 1), ("s1.go", 1), ("s2.go", 1),
                          ("x_test.go", 4), ("t_windows.go", 5), ("k.go", 2)}, dnc_lines(rec))
        # Below C each way is direct: no start needs a second interface call.
        rec_c = by_id(records, f"go:m.C from {I_RUN}")
        self.assertEqual((2, False), (rec_c["from"]["on_way"], rec_c["from"]["second_iface"]))
        self.assertEqual({"K1.Run": (1, 1, 1), "K2.Run": (2, 2, 2)}, distances(rec_c, "K1.Run", "K2.Run"))

    def test_empty_pool_and_its_rule(self):
        funcs = starts_funcs()
        funcs += [fn("Z", "s3.go", 5),  # in the file of a start, with a caller that no start reaches
                  fn("Z2", "s3.go", 8),  # no caller
                  fn("Z4", "s5.go", 5, calls=[call(6, 2, at("s5.go", 5))]),  # only a call of itself
                  fn("Y", "y.go", calls=[call(2, 2, at("s3.go", 5)), call(3, 2, at("w.go"))]),
                  fn("W", "w.go"),  # not in the file of a start
                  fn("Z3", "s4.go", 5)]
        by_id(funcs, "go:m.K4.Run")["calls"].append(call(2, 2, at("s4.go", 5)))  # a start reaches Z3
        uses = {**BASE_USES, "Z": [use("y.go", 2, 2, at("y.go")), use("y.go", 3, 7, at("y.go"), is_call=False)]}
        records, stats = make(funcs, [iface("I", "Run", STARTS)], uses)
        self.assertEqual([f"go:m.Z from {I_RUN}"], [r["id"] for r in records if r["pool"] == "empty"])
        rec = by_id(records, f"go:m.Z from {I_RUN}")
        self.assertEqual(("from", [], [], 0, 0, False, [], False, []),
                         (rec["form"], rec["functions"], rec["steps"], rec["required"], rec["depth"], rec["cycle"],
                          rec["hops"], rec["partial_iface"], rec["decoys"]))
        self.assertEqual((STARTS, 0, False),
                         (rec["from"]["starts"], rec["from"]["on_way"], rec["from"]["second_iface"]))
        self.assertEqual([{**at("s3.go", 5), "class": "dnc", "why": "decl"},
                          {**at("y.go", 3, 7), "class": "dnc", "why": "use"}], rec["sites"])
        self.assertEqual(1, stats["pools"]["empty"])

    def test_from_pool_needs_own_starts_and_its_required_bounds(self):
        starts = [at(f"s{i}.go") for i in range(1, 32)]
        targets = {"T7": 7, "T8": 8, "T40": 40, "T41": 41}
        k1_calls, line, first = [], 2, {}
        for name, n in targets.items():
            first[name] = line
            for _ in range(n):
                k1_calls.append(call(line, 2, at(f"{name.lower()}.go")))
                line += 1
        k1_calls.append(call(first["T40"], 20, at("t40.go")))  # T40: 41 calls on its 40 lines
        k1_calls.sort(key=lambda c: (c["line"], c["col"]))
        funcs = ([fn("K1.Run", "s1.go", calls=k1_calls)] + [fn(f"K{i}.Run", f"s{i}.go") for i in range(2, 32)]
                 + [fn(name, f"{name.lower()}.go") for name in targets])
        own_false = {"type": "go:m.K1x", "type_decl": at("s1.go", 40), "method": starts[0], "own": False}
        no_method = {"type": "go:m.Holder", "type_decl": at("h.go"), "method": None, "own": False}
        k6_promoted = {"type": "go:m.K6", "type_decl": at("s6.go", 30), "method": starts[5], "own": False}
        ifaces = [iface("I", "Run", starts[:6], more=[own_false, no_method]),  # 6 starts, each own
                  iface("J", "Run", starts[:5], "j.go", more=[k6_promoted]),  # 6 starts, K6.Run is no own method
                  iface("L", "Run", starts[:5], "l.go"),  # 5 starts
                  iface("M", "Run", starts[:30], "m.go"),  # 30 starts
                  iface("N", "Run", starts[:31], "n.go")]  # 31 starts
        records, stats = make(funcs, ifaces)
        self.assertEqual(sorted(f"go:m.{t} from go:m.{i}.Run" for t in ("T8", "T40") for i in ("I", "M")),
                         sorted(r["id"] for r in records if r["pool"] == "from"))
        rec = by_id(records, f"go:m.T8 from {I_RUN}")
        self.assertEqual((8, ["s1.go:1"], 1, starts[:6]),
                         (rec["required"], decls(rec["functions"]), rec["from"]["on_way"], rec["from"]["starts"]))
        self.assertEqual(0, stats["pools"]["empty"])


class PoolTest(unittest.TestCase):
    @staticmethod
    def star(target, callers, iface_callers=0):
        """The target and its callers; each caller calls the target, the last `iface_callers` through an interface."""
        t = at(f"{target.lower()}.go")
        out = [fn(target, t["file"])]
        for i in range(callers):
            kind = "iface" if i >= callers - iface_callers else "direct"
            out.append(fn(f"{target}c{i}", f"{target.lower()}c{i}.go", calls=[call(2, 2, t, kind)]))
        return out

    @classmethod
    def setUpClass(cls):
        funcs = []
        for name, n in (("K4", 4), ("K5", 5), ("K79", 79), ("K80", 80), ("L1", 201), ("L3", 201)):
            funcs += cls.star(name, n)
        funcs += cls.star("L2", 201, iface_callers=1)  # 201 functions, 200 on a plain way
        funcs += cls.star("L4", 180)  # 180 + 22 functions, 200 on a plain way of 20 steps or fewer
        prev = at("l4.go")
        for i in range(1, 23):
            funcs.append(fn(f"Chain{i}", f"chain{i}.go", calls=[call(2, 2, prev)]))
            prev = at(f"chain{i}.go")
        cls.funcs = funcs

    def test_pool_bounds_extra_and_large(self):
        records, stats = make(self.funcs, extra=[{"target": "go:m.K80"}, {"target": "go:m.K5"}], large=1)
        pools = {r["id"]: r["pool"] for r in records}
        self.assertEqual({"go:m.K5": "complete", "go:m.K79": "complete", "go:m.K80": "extra"},
                         {k: v for k, v in pools.items() if k.startswith("go:m.K")})
        self.assertEqual([5, 79, 80], [len(by_id(records, f"go:m.K{n}")["functions"]) for n in (5, 79, 80)])
        expected = random.Random(1).sample(["go:m.L1", "go:m.L3"], 1)
        self.assertEqual(expected, [k for k, v in pools.items() if v == "large"])
        self.assertEqual([{"id": expected[0], "functions": 201, "plain": 201}], stats["large"])
        self.assertEqual("complete", by_id(records, expected[0])["form"])
        other = random.Random(7).sample(["go:m.L1", "go:m.L3"], 1)
        self.assertEqual(other, [r["id"] for r in make(self.funcs, large=1, seed=7)[0] if r["pool"] == "large"])
        # A record of an earlier pool is no candidate.
        records = make(self.funcs, extra=[{"target": "go:m.L1"}], large=1)[0]
        self.assertEqual(["go:m.L3"], [r["id"] for r in records if r["pool"] == "large"])
        with self.assertRaises(tracekeys.TraceKeysError):
            make(self.funcs, large=3)

    def test_statistics_of_the_pools(self):
        records, stats = make(self.funcs, extra=[{"target": "go:m.K80"}], large=2)
        self.assertEqual(981, stats["functions"])
        self.assertEqual({"direct": 972, "embedded": 0, "iface": 1}, stats["steps"])
        # K4, K5 and Chain13..Chain21; Chain3..Chain12; Chain1, Chain2; K79; K80, L1, L2, L3, L4.
        self.assertEqual({"1-9": 11, "10-19": 10, "20-39": 2, "40-79": 1, "80+": 5}, stats["sizes"])
        counts = {p: sum(1 for r in records if r["pool"] == p) for p in tracekeys.POOLS}
        self.assertEqual(counts, stats["pools"])
        self.assertEqual({"complete": 19, "from": 0, "empty": 0, "extra": 1, "large": 2}, counts)  # K5, K79, Chain1..17
        self.assertEqual(["go:m.L1", "go:m.L3"], sorted(e["id"] for e in stats["large"]))


class ErrorTest(unittest.TestCase):
    def test_errors(self):
        funcs = base_funcs()
        cases = {
            "no record": (funcs, calls_of(funcs)[1:], []),  # T has no record in calls.jsonl
            "one decl line": (funcs + [fn("T2", "t.go")], calls_of(funcs), []),
            "callee": (funcs + [fn("Q", "q.go", calls=[call(2, 2, at("none.go"))])], calls_of(funcs), []),
            "extra target": (funcs, calls_of(funcs), [{"target": "go:m.None"}]),
            "extra from": (funcs, calls_of(funcs), [{"target": "go:m.T", "from": "go:m.None.Run"}]),
        }
        for name, (f, c, extra) in cases.items():
            with self.subTest(name), self.assertRaises(tracekeys.TraceKeysError):
                tracekeys.make_records(f, [], c, extra)


def target(file, line=1):
    return {"id": f"{file}:{line}", "file": file, "line": line}


class TargetsTest(unittest.TestCase):
    def setUp(self):
        # The records go:m.A, go:m.T (complete) and go:m.T from go:m.I.Run.
        self.records, _ = make(starts_funcs(), [iface("I", "Run", STARTS)], BASE_USES,
                               extra=[{"target": "go:m.T", "from": I_RUN}])
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def test_targets_hold_the_target_and_each_function_once(self):
        # The start-set record has c.go, f.go, s1.go and s2.go, which the complete record of T also has.
        self.assertEqual([target(f) for f in ("a.go", "b.go", "c.go", "d.go", "e.go", "f.go", "g.go", "s1.go",
                                              "s2.go", "t.go")],
                         tracekeys.trace_targets(self.records, ["go:m.T", f"go:m.T from {I_RUN}"]))
        # Sorted by file, then by the line as a number.
        records = [{"id": "r", "decl": at("x.go", 10), "functions": [{"decl": at("x.go", 9)}, {"decl": at("w.go")}]}]
        self.assertEqual([target("w.go"), target("x.go", 9), target("x.go", 10)],
                         tracekeys.trace_targets(records, ["r"]))
        with self.assertRaises(tracekeys.TraceKeysError):
            tracekeys.trace_targets(self.records, ["go:m.None"])

    def test_ids_split_only_at_commas_and_at_line_ends(self):
        keys_file, ids_file, out = (os.path.join(self.dir, n) for n in ("trace.jsonl", "ids.txt", "targets.json"))
        write_jsonl(keys_file, self.records)
        expected = tracekeys.trace_targets(self.records, [f"go:m.T from {I_RUN}", "go:m.A"])
        with open(ids_file, "w", encoding="utf-8") as f:
            f.write(f"go:m.T from {I_RUN}\n\ngo:m.A \n")
        for ids in (f"go:m.T from {I_RUN}, go:m.A", f"@{ids_file}"):
            with self.subTest(ids):
                self.assertEqual((0, f"targets: {len(expected)} functions in {out}\n", ""),
                                 run_main(["targets", "-keys", keys_file, "-ids", ids, "-out", out]))
                with open(out, encoding="utf-8") as f:
                    self.assertEqual(expected, json.load(f))
                os.unlink(out)
        code, _, stderr = run_main(["targets", "-keys", keys_file, "-ids", "go:m.T go:m.A", "-out", out])
        self.assertEqual((2, "tracekeys: no trace record with the id go:m.T go:m.A\n"), (code, stderr))
        missing = os.path.join(self.dir, "none.txt")
        code, _, stderr = run_main(["targets", "-keys", keys_file, "-ids", f"@{missing}", "-out", out])
        self.assertEqual((2, f"tracekeys: {missing}: No such file or directory\n"), (code, stderr))
        self.assertFalse(os.path.exists(out))


ROOT = "/no/such/copy"


def frame(file, line, func="m.F"):
    """A frame of a trace line; a file name with no folder is a file of the copy at ROOT."""
    return {"func": func, "file": file if file.startswith(("/", "<")) else f"{ROOT}/{file}", "line": line}


def stack(target_id, *frames):
    return {"id": target_id, "frames": list(frames)}


def check_funcs():
    """T is the target. A calls T on line 2 and calls a function value on line 4; E calls a function value on line 3;
    M calls A and not T."""
    return [fn("T", "t.go"),
            fn("A", "a.go", calls=[call(2, 2, at("t.go")), call(4, 2, None, "other")]),
            fn("E", "e.go", calls=[call(3, 4, None, "other")]),
            fn("M", "m.go", calls=[call(2, 2, at("a.go"))])]


class TracecheckTest(unittest.TestCase):
    T = "t.go:1"

    def check(self, *lines):
        return tracekeys.tracecheck(check_funcs(), [target("t.go")], list(lines), ROOT)

    def test_each_verdict_of_a_trace_line(self):
        out, code = self.check(
            stack(self.T, frame("/usr/lib/go/src/testing/testing.go", 1934, "testing.tRunner")),  # external
            stack(self.T),  # no frame: external
            stack(self.T, frame("<autogenerated>", 1)),  # only a wrapper: external
            stack(self.T, frame("x_test.go", 4)),  # test
            stack(self.T, frame("a.go", 20)),  # no function holds a.go:20 (A has the lines 1 to 6): package-level
            stack(self.T, frame("a.go", 2)),  # key
            stack(self.T, frame("<autogenerated>", 1, "m.(*K).Run"), frame("a.go", 2)),  # a wrapper, then key
            stack(self.T, frame("a.go", 4)),  # key-line: it wins over the call of a function value on a.go:4
            stack(self.T, frame("e.go", 3)),  # dynamic
            stack(self.T, frame("m.go", 2)),  # missing
            stack("z.go:1", frame("m.go", 2)))  # a trace line of another id
        self.assertEqual(["tracecheck: 1 functions, 10 trace lines: external 3, test 1, package-level 1, key 2, "
                          "key-line 1, dynamic 1, missing 1; trace lines of other ids: 1",
                          "missing m.go:2 (in m.go:1, calls t.go:1)",
                          "key-line a.go:4 (in a.go:1, calls t.go:1, step on line 2)"], out)
        self.assertEqual(1, code)

    def test_a_package_level_frame_is_counted_and_is_no_failure(self):
        out, code = self.check(stack(self.T, frame("a.go", 2)), stack(self.T, frame("a.go", 20)))
        self.assertEqual(["tracecheck: 1 functions, 2 trace lines: external 0, test 0, package-level 1, key 1, "
                          "key-line 0, dynamic 0, missing 0; trace lines of other ids: 0"], out)
        self.assertEqual(0, code)

    def test_a_trace_with_no_frame_in_a_function_gives_exit_1(self):
        for lines in ((), (stack(self.T, frame("x_test.go", 4)), stack(self.T, frame("a.go", 20)))):
            with self.subTest(len(lines)):
                out, code = self.check(*lines)
                self.assertEqual("tracecheck: no trace line has a first frame in a function of the graph", out[-1])
                self.assertEqual(1, code)

    def test_each_listed_line_comes_one_time_with_its_step_lines(self):
        funcs = check_funcs()
        funcs[1]["calls"].append(call(5, 2, at("t.go")))  # a second step A -> T
        out, _ = tracekeys.tracecheck(funcs, [target("t.go")], [
            stack(self.T, frame("a.go", 4), frame("x.go", 1)), stack(self.T, frame("a.go", 4), frame("x.go", 2)),
            stack(self.T, frame("m.go", 2), frame("x.go", 1)), stack(self.T, frame("m.go", 2), frame("x.go", 2))],
            ROOT)
        self.assertEqual(["missing m.go:2 (in m.go:1, calls t.go:1)",
                          "key-line a.go:4 (in a.go:1, calls t.go:1, steps on lines 2, 5)"], out[1:])

    def test_a_frame_below_the_real_path_of_the_root_is_in_the_tree(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        os.mkdir(os.path.join(folder, "copy"))
        os.symlink(os.path.join(folder, "copy"), os.path.join(folder, "link"))
        line = stack(self.T, frame(os.path.join(folder, "copy", "a.go"), 2))
        out, code = tracekeys.tracecheck(check_funcs(), [target("t.go")], [line], os.path.join(folder, "link"))
        self.assertIn("key 1,", out[0])
        self.assertEqual(0, code)

    def test_a_target_that_is_no_function_of_the_graph_is_an_error(self):
        with self.assertRaises(tracekeys.TraceKeysError):
            tracekeys.tracecheck(check_funcs(), [target("t.go", 3)], [], ROOT)

    def test_a_missing_step_gives_exit_1(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        graph, targets, trace = (os.path.join(folder, n) for n in ("graph.jsonl", "targets.json", "stacks.jsonl"))
        write_jsonl(graph, check_funcs())
        with open(targets, "w", encoding="utf-8") as f:
            json.dump([target("t.go")], f)
        args = ["tracecheck", "-graph", graph, "-targets", targets, "-trace", trace, "-root", ROOT]
        write_jsonl(trace, [stack(self.T, frame("a.go", 2))])
        code, stdout, stderr = run_main(args)
        self.assertEqual((0, ""), (code, stderr))
        self.assertIn(", key 1,", stdout)
        write_jsonl(trace, [stack(self.T, frame("a.go", 2)), stack(self.T, frame("m.go", 2))])
        code, stdout, stderr = run_main(args)
        self.assertEqual((1, ""), (code, stderr))
        self.assertEqual("missing m.go:2 (in m.go:1, calls t.go:1)", stdout.splitlines()[-1])


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.graph, self.calls, self.extra, self.out = (os.path.join(self.dir, n) for n in (
            "graph.jsonl", "calls.jsonl", "extra.json", "trace.jsonl"))
        self.funcs, self.ifaces = starts_funcs(), [iface("I", "Run", STARTS)]
        write_jsonl(self.graph, self.funcs + self.ifaces)
        write_jsonl(self.calls, calls_of(self.funcs, BASE_USES))

    def test_load_graph_gives_the_functions_and_the_interfaces(self):
        self.assertEqual((self.funcs, self.ifaces), tracekeys.load_graph(self.graph))

    def test_cli_make_writes_records_sorted_by_id(self):
        with open(self.extra, "w", encoding="utf-8") as f:
            json.dump([{"target": "go:m.T", "from": I_RUN}, {"target": "go:m.U"}], f)
        code, stdout, stderr = run_main(["make", "-graph", self.graph, "-calls", self.calls, "-out", self.out,
                                         "-extra", self.extra])
        self.assertEqual((0, ""), (code, stderr))
        written = keys.load_keys(self.out)
        ids = [r["id"] for r in written]
        self.assertEqual(["go:m.A", "go:m.T", f"go:m.T from {I_RUN}", "go:m.U"], ids)
        self.assertEqual(sorted(ids), ids)
        expected, _ = make(self.funcs, self.ifaces, BASE_USES, [{"target": "go:m.T", "from": I_RUN},
                                                                {"target": "go:m.U"}])
        self.assertEqual(sorted(expected, key=lambda r: r["id"]), written)
        self.assertIn("make: 17 functions, steps: direct 10, embedded 1, iface 2", stdout)
        self.assertIn("functions on the way of the complete form: 1-9 ", stdout)
        self.assertIn("records: complete 2, from 0, empty 0, extra 2, large 0", stdout)
        self.assertIn("time: ", stdout)

    def test_cli_reports_an_error_with_exit_code_2(self):
        with open(self.extra, "w", encoding="utf-8") as f:
            json.dump([{"target": "go:m.None"}], f)
        code, _, stderr = run_main(["make", "-graph", self.graph, "-calls", self.calls, "-out", self.out,
                                    "-extra", self.extra])
        self.assertEqual(2, code)
        self.assertIn("tracekeys: ", stderr)
        self.assertIn("go:m.None", stderr)
        self.assertFalse(os.path.exists(self.out))

    def make_args(self, **paths):
        """The arguments of `make`; a keyword (graph, calls, extra) gives another path to its option."""
        paths = {"graph": self.graph, "calls": self.calls, "extra": self.extra, **paths}
        return ["make", "-out", self.out] + [x for k, v in paths.items() for x in (f"-{k}", v)]

    def test_cli_reports_a_missing_input_file_with_exit_code_2(self):
        with open(self.extra, "w", encoding="utf-8") as f:
            json.dump([], f)
        missing = os.path.join(self.dir, "none.json")
        for option in ("graph", "calls", "extra"):
            with self.subTest(option):
                code, _, stderr = run_main(self.make_args(**{option: missing}))
                self.assertEqual((2, f"tracekeys: {missing}: No such file or directory\n"), (code, stderr))
                self.assertFalse(os.path.exists(self.out))

    def test_cli_reports_bad_json_of_the_extra_file_with_exit_code_2(self):
        with open(self.extra, "w", encoding="utf-8") as f:
            f.write('[{"target": ')
        code, _, stderr = run_main(self.make_args())
        self.assertEqual(2, code)
        self.assertTrue(stderr.startswith(f"tracekeys: {self.extra}: no valid JSON: "), stderr)
        self.assertFalse(os.path.exists(self.out))

    def test_cli_reports_a_line_of_another_rec_and_an_extra_entry_with_no_target(self):
        with open(self.extra, "w", encoding="utf-8") as f:
            json.dump([], f)
        write_jsonl(self.graph, self.funcs + self.ifaces + [{"rec": "other"}])
        self.assertEqual((2, "", f"tracekeys: {self.graph}: a line with the rec 'other'\n"),
                         run_main(self.make_args()))
        write_jsonl(self.graph, self.funcs + self.ifaces)
        with open(self.extra, "w", encoding="utf-8") as f:
            json.dump([{"from": I_RUN}], f)
        self.assertEqual((2, "", f"tracekeys: an -extra entry with no target: {{'from': '{I_RUN}'}}\n"),
                         run_main(self.make_args()))
        self.assertFalse(os.path.exists(self.out))

    def test_module_runs_as_a_command(self):
        proc = subprocess.run([sys.executable, "-B", "-m", "keygen.tracekeys", "make", "-h"], cwd=LIVE_TEST_DIR,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("-graph", proc.stdout)


if __name__ == "__main__":
    unittest.main()
