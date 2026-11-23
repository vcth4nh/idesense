"""Trace keys of a Go product: for one target function, each call step on each way to it, at any depth.

    python3 -m keygen.tracekeys make -graph <graph.jsonl> -calls <calls.jsonl> -out <trace.jsonl>
        [-extra <file.json>] [-large <n> [-seed <s>]]

(run from live-test). Positions as in `callkeys`: `file` is relative to the tree root with forward slashes, `line`
and `col` are 1-based. A `decl` is the position of the name token of a declaration. An error stops a command with
exit code 2. Else the exit code is 0.

The file `graph.jsonl` (`gokeys graph`) is the call graph of one build: one GOOS, the GOARCH amd64, and no file
whose name ends with `_test.go`. The trace keys use the build for Linux. The file has one JSON line for each
function declaration of the build, sorted by `decl`, then one line for each named, non-generic interface of the
module, sorted by `id`:

    {"rec": "func", "id": "<key id, or the empty string>", "kind": "func" | "method", "name", "container",
     "decl": {"file", "line", "col"}, "end": <last line>,
     "calls": [{"line", "col", "callee": {"file", "line", "col"} | null,
                "kind": "direct" | "embedded" | "iface" | "other", "lit": bool, "iface": "<id>" | ""}]}
    {"rec": "iface", "id", "name", "decl",
     "methods": [{"id", "name", "decl",
                  "impls": [{"type": "<type id>", "type_decl", "method": {"file", "line", "col"} | null,
                             "own": bool}]}]}

`id`, `kind`, `name`, `container`, `decl` and `end` are those of `gokeys calls`. The calls of a function are sorted
by position, and the entries of one call by callee. An entry is at the identifier that names the called function in
the call expression. A call in a function literal belongs to the function declaration that holds the literal, with
`lit` true. A call after `go` or `defer` has an entry too. The kinds of an entry:

    direct    a call of the function or method that the compiler selects; `callee` is its decl
    embedded  such a call through an embedded field: the callee is the method of the embedded type
    iface     a call of a method of a module interface: one entry for each function that an implementer of the
              interface selects for the method; `iface` is the id of the interface method, "" for a method of an
              unnamed interface
    other     a call that gives no step, with `callee` null: a call of a function value, a call of a method of a
              library interface, and a call of a method of a module interface whose type mentions a type
              parameter. A call with no name of the callee (`getF()()`, the call of a function literal) has its
              entry at its left parenthesis.

A call of a library function, a conversion and a call of a builtin give no entry. `impls` lists the types of the
module that implement the interface: the named types of the package level, the named types of a function body (the
id `go:<package>.<name>@<file>:<line>:<col>`) and the unnamed struct types with an embedded field (the id
`struct@<file>:<line>:<col>`, with `#2` for a second type at the same position). `method` is the decl of the method
that the method set of `*T` selects for the name. It is null when that method is no function of the graph, for
example for a struct that embeds the interface. `own` is true when T declares the method itself.

The limits of the graph. A generic type is no implementer, and a call on a value of a type parameter is no step. An
unnamed struct type that occurs only as a type argument is no implementer. A call in a package-level declaration
(outside each function) is no step.

make: the trace records. A FUNCTION is a line with `rec` `func`. Its key is (`decl.file`, `decl.line`). A STEP is an
entry of the kind `direct`, `embedded` or `iface`, from the function that holds the call (the caller) to the callee.
T is the target. A call inside T is on no way: the trace stops at the first entry into T.

- The complete form: B is the set of the functions that reach T over the steps, with T. N is B.
- The start-set form of an interface method M: the STARTS are the distinct `method` decls of the impls of M. N is
  the set of the functions of B that a walk from the starts over the steps reaches, with no step out of T. N is
  empty when no start reaches T.

`calls.jsonl` is the file of `gokeys calls` for the same tree (its format is in the module text of `callkeys`). The
record of a function in it is the record whose `configs` has `linux`, whose file name does not end with `_test.go`,
and whose decl has the file and the line of the function. `make` writes one JSON line for each trace record:

    {"id": "<id of T>" | "<id of T> from <id of M>", "lang": "go", "kind", "name", "container", "decl",
     "source": "graph", "form": "complete" | "from", "pool": "complete" | "from" | "empty" | "extra" | "large",
     "from": null | {"id", "name", "container": "<interface name>", "decl", "starts": [<decl>, ...],
                     "on_way": <n>, "second_iface": bool},
     "functions": [{"id", "decl", "any": <n>, "direct": <n> | null, "plain": <n> | null}, ...],
     "steps": [{"caller": <decl>, "call": {"file", "line", "col"}, "callee": <decl>,
                "kind": "direct" | "embedded" | "iface", "lit": bool}, ...],
     "required": <n>, "depth": <n>, "cycle": bool, "hops": [...], "partial_iface": bool, "decoys": [<decl>, ...],
     "sites": [{"file", "line", "col", "class": "required", "why": "step"},
               {"file", "line", "col", "class": "dnc", "why": "decl" | "use"}, ...]}

- `kind`, `name`, `container` and `decl` are those of T. `from` is null for the complete form. For the start-set form
  it gives M, the name of its interface, the decls of the starts (sorted), `on_way` (the count of the starts in N)
  and `second_iface` (a start in N has `direct` null).
- `functions`: each function of N except T, sorted by decl, with three distances to T. A distance is the count of
  the steps of the shortest way over the steps among N whose caller is not T, or null when no such way exists.
  `any`: steps of each kind. `direct`: no step `iface`. `plain`: no step `iface`, and a step with `lit` true only as
  the first step (the call that the function itself makes).
- `steps`: each step whose caller and callee are in N, also a step whose caller is T. They are sorted by caller,
  call position and callee. `call` is the position of the entry.
- `required`: the count of the distinct lines of the required sites. `depth`: the largest `any`, 0 with no function.
  `cycle`: the steps among N whose caller is not T have a cycle (a step from a function to itself counts). `hops`:
  the sorted names of `cycle`, `embedded`, `iface` and `lit` that these steps have. `partial_iface`: a call position
  of a function of N other than T has `iface` entries with two callees or more, one callee or more in N and one
  callee or more outside N. `decoys`: the decls, sorted, of the functions outside N with the name of T that a call of
  a function of N has as its callee.
- `sites`, sorted by (file, line, col), one site for each position:
  - `required`, `why` `step`: the call position of each step of `steps` whose caller is not T;
  - `dnc`, `why` `decl`: the decl of T and of each function of N;
  - `dnc`, `why` `use`: each use of T or of a function of N in calls.jsonl with `call` false, with no `linux` in
    `configs`, in a file whose name ends with `_test.go`, with `in` null, or with an `in` that is no function of
    the graph.
  A required site wins over a dnc site on its line (`keyrecord.line_classes`).

The POOLS. `make` writes each record one time, with the first pool that applies, in this order:

    complete  each function with an id whose `functions` count is MIN_FUNCTIONS to MAX_FUNCTIONS (complete form)
    from      each interface method M with STARTS[0] to STARTS[1] starts, where each start is the method of an impl
              with `own` true, and each function T with an id that is no start, with FROM_REQUIRED[0] to
              FROM_REQUIRED[1] required lines (start-set form)
    empty     each such M, and each function T with an id that is no start, that no start reaches, that the file of
              a start declares, and that is the callee of a step whose caller is not T (start-set form, with no
              function, no step and only dnc sites)
    extra     each entry of `-extra`, a JSON list of {"target": "<id>"} (complete form) and
              {"target": "<id>", "from": "<interface method id>"} (start-set form)
    large     with `-large <n>`: the n ids `random.Random(<seed>).sample(<sorted ids>, n)` of the functions with an
              id that no earlier pool wrote as a record id and that have more than LARGE_MIN functions with a
              `plain` of LARGE_DEPTH or less (complete form)

`-seed` is 1 by default. The output gives the count of the functions and of the steps of each kind, the count of the
functions in each size group of SIZE_GROUPS (by the count of `functions` of the complete form), the count of the
records of each pool, the id of each `large` record with its count of functions and its count of functions with a
`plain` of LARGE_DEPTH or less, and the time. Errors: two functions with one decl line, a callee that is no function
of the graph, an `-extra` entry with no function or no interface method of its id, fewer candidates than `-large`,
and a function of a record with no record in calls.jsonl.
"""
import argparse
import collections
import json
import random
import sys
import time

from common import keyrecord as keys

MIN_FUNCTIONS = 5
MAX_FUNCTIONS = 79
# The set maker of bench/sets.py (family trace) uses the same numbers for a start-set question.
STARTS = (6, 30)
FROM_REQUIRED = (8, 40)
LARGE_MIN = 200
LARGE_DEPTH = 20
SIZE_GROUPS = ((1, 9), (10, 19), (20, 39), (40, 79), (80, None))

STEP_KINDS = ("direct", "embedded", "iface")
POOLS = ("complete", "from", "empty", "extra", "large")
HOPS = ("cycle", "embedded", "iface", "lit")


class TraceKeysError(Exception):
    pass


def _key(p: dict) -> tuple[str, int]:
    """The key of a function: the file and the line of its decl."""
    return p["file"], p["line"]


def _pos(p: dict) -> tuple[str, int, int]:
    return p["file"], p["line"], p["col"]


def _group(lo: int, hi: int | None) -> str:
    return f"{lo}+" if hi is None else f"{lo}-{hi}"


def load_graph(path: str) -> tuple[list[dict], list[dict]]:
    """The functions and the interfaces of a graph file, in the order of the file."""
    funcs, ifaces = [], []
    for rec in keys.load_keys(path):
        if rec.get("rec") == "func":
            funcs.append(rec)
        elif rec.get("rec") == "iface":
            ifaces.append(rec)
        else:
            raise TraceKeysError(f"{path}: a line with the rec {rec.get('rec')!r}")
    return funcs, ifaces


class _Graph:
    """The functions of a graph file with their steps, the interface methods, and the records of calls.jsonl."""

    def __init__(self, funcs: list[dict], ifaces: list[dict], calls: list[dict]):
        self.funcs = {}
        for f in funcs:
            k = _key(f["decl"])
            if k in self.funcs:
                raise TraceKeysError(f"two functions with the decl line {k[0]}:{k[1]}")
            self.funcs[k] = f
        self.ids = {f["id"]: k for k, f in self.funcs.items() if f["id"]}
        self.succ = collections.defaultdict(list)  # caller -> [(callee, entry)]
        self.pred = collections.defaultdict(list)  # callee -> [(caller, entry)]
        for k, f in self.funcs.items():
            for c in f["calls"]:
                if c["kind"] not in STEP_KINDS:
                    continue
                v = _key(c["callee"])
                if v not in self.funcs:
                    raise TraceKeysError(f"the call {k[0]}:{c['line']}:{c['col']} has the callee {v[0]}:{v[1]}, "
                                         "which is no function of the graph")
                self.succ[k].append((v, c))
                self.pred[v].append((k, c))
        self.methods = {m["id"]: (i, m) for i in ifaces for m in i["methods"]}
        self.calls = {_key(r["decl"]): r for r in calls
                      if "linux" in r["configs"] and not r["decl"]["file"].endswith("_test.go")}
        self._reverse = {}

    def reverse(self, t: tuple) -> frozenset:
        """B: the functions that reach t over the steps, with t. Each set is computed one time."""
        if t not in self._reverse:
            seen, todo = {t}, [t]
            while todo:
                for u, _ in self.pred[todo.pop()]:
                    if u not in seen:
                        seen.add(u)
                        todo.append(u)
            self._reverse[t] = frozenset(seen)
        return self._reverse[t]

    def forward(self, t: tuple, starts: list[tuple], limit: int | None = None) -> tuple[set, set] | None:
        """N of the start-set form, and its required lines: the functions of B that a walk from the starts reaches,
        with no step out of t. A function on a way to a function of B is in B, so the walk stays in B, and each step
        from a function of N other than t to a function of B is a required step. With a limit, the walk stops and
        gives None when the required lines are more than the limit."""
        b = self.reverse(t)
        seen, lines = {s for s in starts if s in b}, set()
        todo = [s for s in seen if s != t]
        while todo:
            f = todo.pop()
            for v, c in self.succ[f]:
                if v not in b:
                    continue
                lines.add((f[0], c["line"]))
                if limit is not None and len(lines) > limit:
                    return None
                if v not in seen:
                    seen.add(v)
                    if v != t:
                        todo.append(v)
        return seen, lines


def _record_id(target: dict, method_id: str | None) -> str:
    return target["id"] if method_id is None else f"{target['id']} from {method_id}"


def _starts(m: dict) -> list[tuple]:
    """The distinct functions that the impls of the interface method m select, sorted. A null method is no start."""
    return sorted({_key(i["method"]) for i in m["impls"] if i["method"] is not None})


def _distances(g: _Graph, t: tuple, nodes) -> tuple[dict, dict, dict]:
    """`any`, `direct` and `plain` of each function of nodes that has such a way to t (t itself: 0)."""
    def walk(ok) -> dict:
        dist, frontier = {t: 0}, [t]
        while frontier:
            nxt = []
            for v in frontier:
                for u, c in g.pred[v]:
                    if u != t and u in nodes and u not in dist and ok(c):
                        dist[u] = dist[v] + 1
                        nxt.append(u)
            frontier = nxt
        return dist

    any_ = walk(lambda c: True)
    direct = walk(lambda c: c["kind"] != "iface")
    rest = walk(lambda c: c["kind"] != "iface" and not c["lit"])
    plain = {t: 0}
    for f in nodes - {t}:
        ways = [1 + rest[v] for v, c in g.succ[f] if c["kind"] != "iface" and v in rest]
        if ways:
            plain[f] = min(ways)
    return any_, direct, plain


def _has_cycle(nodes, edges: list[tuple]) -> bool:
    """Whether the edges among the nodes have a cycle: a node that no topological order can take."""
    indeg = dict.fromkeys(nodes, 0)
    out = collections.defaultdict(list)
    for u, v in edges:
        out[u].append(v)
        indeg[v] += 1
    todo = [n for n, d in indeg.items() if d == 0]
    done = 0
    while todo:
        done += 1
        for v in out[todo.pop()]:
            indeg[v] -= 1
            if indeg[v] == 0:
                todo.append(v)
    return done < len(indeg)


def _sites(g: _Graph, t: tuple, nodes, way: list[tuple]) -> list[dict]:
    sites = {}
    for f, c, _ in way:
        sites[(f[0], c["line"], c["col"])] = {"file": f[0], "line": c["line"], "col": c["col"], "class": "required",
                                              "why": "step"}
    for k in sorted(nodes | {t}):
        decl = g.funcs[k]["decl"]
        sites.setdefault(_pos(decl), {**decl, "class": "dnc", "why": "decl"})
        rec = g.calls.get(k)
        if rec is None:
            raise TraceKeysError(f"the function {k[0]}:{k[1]} has no record in the calls file (configs with linux, "
                                 "no _test.go file)")
        for u in rec["uses"]:
            if (not u["call"] or "linux" not in u["configs"] or u["file"].endswith("_test.go") or u["in"] is None
                    or _key(u["in"]) not in g.funcs):
                sites.setdefault(_pos(u), {"file": u["file"], "line": u["line"], "col": u["col"], "class": "dnc",
                                           "why": "use"})
    return [sites[p] for p in sorted(sites)]


def _record(g: _Graph, t: tuple, pool: str, method_id: str | None = None) -> dict:
    """The trace record of the target t: the complete form, or the start-set form of the interface method."""
    target = g.funcs[t]
    if method_id is None:
        nodes, starts = g.reverse(t), []
    else:
        starts = _starts(g.methods[method_id][1])
        nodes = frozenset(g.forward(t, starts)[0])
    any_, direct, plain = _distances(g, t, nodes)
    steps = sorted(((f, c, v) for f in nodes for v, c in g.succ[f] if v in nodes),
                   key=lambda s: (s[0], s[1]["line"], s[1]["col"], s[2]))
    way = [s for s in steps if s[0] != t]
    found = {c["kind"] for _, c, _ in way if c["kind"] != "direct"} | {"lit" for _, c, _ in way if c["lit"]}
    if _has_cycle(nodes, [(f, v) for f, _, v in way]):
        found.add("cycle")
    callees = collections.defaultdict(set)  # the callees of each interface call of a function of N other than t
    for f in nodes - {t}:
        for v, c in g.succ[f]:
            if c["kind"] == "iface":
                callees[(f, c["line"], c["col"])].add(v)
    decoys = sorted({v for f in nodes for v, _ in g.succ[f]
                     if v not in nodes and g.funcs[v]["name"] == target["name"]})
    functions = [{"id": g.funcs[k]["id"], "decl": g.funcs[k]["decl"], "any": any_[k], "direct": direct.get(k),
                  "plain": plain.get(k)} for k in sorted(nodes - {t})]
    sites = _sites(g, t, nodes, way)
    frm = None
    if method_id is not None:
        iface, m = g.methods[method_id]
        frm = {"id": m["id"], "name": m["name"], "container": iface["name"], "decl": m["decl"],
               "starts": [g.funcs[s]["decl"] for s in starts], "on_way": sum(1 for s in starts if s in nodes),
               "second_iface": any(direct.get(s) is None for s in starts if s in nodes)}
    return {"id": _record_id(target, method_id), "lang": "go",
            "kind": target["kind"], "name": target["name"], "container": target["container"], "decl": target["decl"],
            "source": "graph", "form": "complete" if method_id is None else "from", "pool": pool, "from": frm,
            "functions": functions,
            "steps": [{"caller": g.funcs[f]["decl"], "call": {"file": f[0], "line": c["line"], "col": c["col"]},
                       "callee": g.funcs[v]["decl"], "kind": c["kind"], "lit": c["lit"]} for f, c, v in steps],
            "required": len({(s["file"], s["line"]) for s in sites if s["class"] == "required"}),
            "depth": max((f["any"] for f in functions), default=0), "cycle": "cycle" in found,
            "hops": [h for h in HOPS if h in found],
            "partial_iface": any(len(vs) >= 2 and vs & nodes and vs - nodes for vs in callees.values()),
            "decoys": [g.funcs[v]["decl"] for v in decoys], "sites": sites}


def make_records(funcs: list[dict], ifaces: list[dict], calls: list[dict], extra: list[dict], large: int = 0,
                 seed: int = 1) -> tuple[list[dict], dict]:
    """The trace records of the pools (see the module text), sorted by id, and the statistics."""
    g = _Graph(funcs, ifaces, calls)
    records = {}

    def add(t: tuple, pool: str, method_id: str | None = None) -> None:
        rid = _record_id(g.funcs[t], method_id)
        if rid not in records:
            records[rid] = _record(g, t, pool, method_id)

    on_way = {k: len(g.reverse(k)) - 1 for k in g.funcs}
    targets = [k for k in sorted(g.funcs) if g.funcs[k]["id"]]
    for t in targets:
        if MIN_FUNCTIONS <= on_way[t] <= MAX_FUNCTIONS:
            add(t, "complete")
    for method_id in sorted(g.methods):
        m = g.methods[method_id][1]
        starts = _starts(m)
        own = {_key(i["method"]) for i in m["impls"] if i["method"] is not None and i["own"]}
        if not (STARTS[0] <= len(starts) <= STARTS[1]) or not own.issuperset(starts):
            continue
        start_set, files = set(starts), {s[0] for s in starts}
        for t in targets:
            if t in start_set:
                continue
            if start_set.isdisjoint(g.reverse(t)):
                if t[0] in files and any(u != t for u, _ in g.pred[t]):
                    add(t, "empty", method_id)
                continue
            walk = g.forward(t, starts, FROM_REQUIRED[1])
            if walk is not None and len(walk[1]) >= FROM_REQUIRED[0]:
                add(t, "from", method_id)
    for e in extra:
        if not isinstance(e, dict) or "target" not in e:
            raise TraceKeysError(f"an -extra entry with no target: {e!r}")
        if e["target"] not in g.ids:
            raise TraceKeysError(f"-extra: no function has the id {e['target']}")
        if e.get("from") is not None and e["from"] not in g.methods:
            raise TraceKeysError(f"-extra: no interface method has the id {e['from']}")
        add(g.ids[e["target"]], "extra", e.get("from"))
    picked = []
    if large:
        candidates = {}
        for rid, k in sorted(g.ids.items()):
            if rid in records or on_way[k] <= LARGE_MIN:
                continue
            plain = _distances(g, k, g.reverse(k))[2]
            n = sum(1 for f, d in plain.items() if f != k and d <= LARGE_DEPTH)
            if n > LARGE_MIN:
                candidates[rid] = n
        if large > len(candidates):
            raise TraceKeysError(f"-large {large}: only {len(candidates)} functions are candidates")
        for rid in random.Random(seed).sample(sorted(candidates), large):
            add(g.ids[rid], "large")
            picked.append({"id": rid, "functions": on_way[g.ids[rid]], "plain": candidates[rid]})
    steps = collections.Counter(c["kind"] for f in funcs for c in f["calls"] if c["kind"] in STEP_KINDS)
    pools = collections.Counter(r["pool"] for r in records.values())
    stats = {"functions": len(g.funcs), "steps": {k: steps[k] for k in STEP_KINDS},
             "sizes": {_group(lo, hi): sum(1 for n in on_way.values() if lo <= n and (hi is None or n <= hi))
                       for lo, hi in SIZE_GROUPS},
             "pools": {p: pools[p] for p in POOLS}, "large": picked}
    return sorted(records.values(), key=lambda r: r["id"]), stats


def _make_lines(stats: dict, seconds: float) -> list[str]:
    return ([f"make: {stats['functions']} functions, steps: "
             + ", ".join(f"{k} {n}" for k, n in stats["steps"].items()),
             "functions on the way of the complete form: " + ", ".join(f"{k} {n}" for k, n in stats["sizes"].items()),
             "records: " + ", ".join(f"{p} {n}" for p, n in stats["pools"].items())]
            + [f"large: {e['id']}: {e['functions']} functions, {e['plain']} with plain {LARGE_DEPTH} or less"
               for e in stats["large"]]
            + [f"time: {seconds:.1f} s"])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m keygen.tracekeys")
    commands = parser.add_subparsers(dest="command", required=True)
    mk = commands.add_parser("make", help="the trace records of a Go call graph")
    mk.add_argument("-graph", required=True, help="graph.jsonl of gokeys graph (Linux)")
    mk.add_argument("-calls", required=True, help="calls.jsonl of gokeys calls for the same tree")
    mk.add_argument("-out", required=True, help="trace.jsonl")
    mk.add_argument("-extra", help='a JSON list of {"target": <id>} and '
                                   '{"target": <id>, "from": <interface method id>}')
    mk.add_argument("-large", type=int, default=0, help="the count of the records of the pool large")
    mk.add_argument("-seed", type=int, default=1, help="the seed of the pool large")
    args = parser.parse_args(argv)
    start = time.monotonic()
    try:
        if args.command == "make":
            funcs, ifaces = load_graph(args.graph)
            extra = []
            if args.extra:
                with open(args.extra, encoding="utf-8") as f:
                    extra = json.load(f)
            records, stats = make_records(funcs, ifaces, keys.load_keys(args.calls), extra, args.large, args.seed)
            keys.save_keys(args.out, records)
            print("\n".join(_make_lines(stats, time.monotonic() - start)))
    except TraceKeysError as e:
        print(f"tracekeys: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
