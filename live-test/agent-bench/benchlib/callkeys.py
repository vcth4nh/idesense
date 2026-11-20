"""Caller keys of two levels: the call uses of each function of a tree, and the exact key records made of them.

    python3 -m benchlib.callkeys pycalls -root <tree> -unique <unique.jsonl> [-plant <plant.jsonl>] -out <calls.jsonl>
    python3 -m benchlib.callkeys make -calls <calls.jsonl> [-symbols <symbols.jsonl>] -out <keys.jsonl>
    python3 -m benchlib.callkeys targets -keys <keys.jsonl> -ids <id,...|@file> -out <targets.json>
    python3 -m benchlib.callkeys tracecheck -keys <keys.jsonl> -calls <calls.jsonl> -trace <trace.jsonl>
        -ids <id,...|@file>
    python3 -m benchlib.callkeys dynmake -calls <calls.jsonl> -symbols <symbols.jsonl> -targets <targets.json>
        -trace <trace.jsonl> -root <folder of the copy> -out <keys.jsonl>

(run from live-test/agent-bench). Positions as in `pykeys`: `file` is relative to the tree root with forward
slashes, `line` is 1-based, `col` is 1-based and counts UTF-16 code units. A `decl` is the position of the name
token of a declaration. `-ids` is a list with commas, or `@<file>` with the ids separated by commas or white
space. An error stops a command with exit code 2.

The file `calls.jsonl` (Go: `gokeys calls`; Python: `pycalls`) has one JSON line for each function declaration of
a tree, sorted by `decl` (file, line, col):

    {"id": "<key id, or the empty string>", "lang": "go" | "python", "kind": "func" | "method" | "function",
     "name", "container", "decl": {"file", "line", "col"}, "end": <last line>,
     "uses": [{"file", "line", "col", "call": bool, "in": {"file", "line", "col"} | null, "lit": bool}]}

`in` is the `decl` of the function declaration whose body holds the use (Python: the OUTERMOST enclosing `def`),
or null. `lit` is true for a use inside a function literal (Go), or inside a lambda or a nested `def` (Python).
Go records and uses also have `configs`. Python records also have `top` (the `decl` of the outermost enclosing
`def`; its own `decl` when it is not nested), `decorators` (the dotted text of each decorator with no call
arguments, `pytest.mark.parametrize`; `"?"` for another expression), `generator` (a `yield` in the body outside
a nested function), `async` and `mentions`, and each Python use also has `read`.

pycalls: one record for each `def` and `async def` of the `.py` files of the tree (`pykeys._py_files`). `kind`:
`method` for a `def` whose nearest enclosing scope is a class body, else `function`. `container`: for a method,
the dotted path of the enclosing scopes as `pykeys` gives it (the class name, `Outer.Inner` for a nested class),
else `""`. `id`: the id of the record of `-unique` or `-plant` whose `decl` is the position of the def, `""` for
each other def. Only a record with an id has uses: one for each `required` site of its key record, from the
`ast.Name` or `ast.Attribute` whose name token is at the site.
- `call`: the node is the `func` of an `ast.Call`. `read`: the node is a load and no `func` of a call.
- `in`: the outermost `def` whose BODY holds the node. A decorator, a default value or an annotation of a `def` is
  outside its body. Null at module level and in a class body outside each `def`.
- `lit`: a lambda or a nested `def` inside that outermost `def` holds the node (a lambda at module level too).
- A site with no such node: `"call": false, "read": false, "in": null, "lit": false, "unknown": true`.
`mentions`: the occurrences of the name in the code and in the string literals of the tree, outside the name
tokens of `def` statements (comments do not count), from one pass over the files. Errors: a file that does not
parse, a key record with no def at its `decl`, two key records with one `decl`.

make: the caller keys of depth `DEPTH`. `-symbols` (the key file of `gokeys extract` for the same tree) is
required for Go and refused for Python. A use COUNTS AS A CALL when `call` is true, or (Python) when the record is
a property (the last part of one decorator is `property` or `cached_property`) and `read` is true. A function is
OPEN for each of these causes, else CLOSED:

    no-key      `id` is "" and the function has a use, or (Python) `mentions` is above 0
    value       a use that does not count as a call
    outside     a use with `in` null
    unknown     (Python) a use with `unknown` true
    nested      (Python) `top` is not `decl`
    decorator   (Python) the first part of a decorator is not in ALLOWED_DECORATORS
    generator   (Python) `generator` or `async` is true
    implicit    (Python) the name starts and ends with two underscores: Python calls such a method with no use of
                its name (`K()` runs `__init__`, `with` runs `__enter__`), so "no use" does not prove "no caller"
    uncalled    (Python) the function has no use and is no test function (`is_test_function`: the name starts with
                `test`, and the base name of the file matches `test_*.py` or `*_test.py`): Python code can call a
                function through `getattr` with a computed name, so "no use" proves "no caller" only for a test
                function, which only the test runner calls
    interface   (Go) the symbols record has a `family` with another id, or a non-empty `external`
    unproven    (Go) the symbols record has a site with `why` `string` or `unproven`
    variants    (Go) two records of calls.jsonl have this `id` (not "")
    no-symbols  (Go) `id` is not "" and the symbols file has no record with it

The CALLERS of a function are the functions at the `in` positions of its uses; each `in` must be the `decl` of a
record. A closed function with no use has no caller in the tree: a Go function (`main`, `init`, a test), or a
Python test function. A function X is a TARGET when X is closed, has an id and one caller or more, and each
caller of X is closed. For each target, in the order of calls.jsonl, `make` writes one key record:

    {"id", "lang", "kind", "name", "container", "decl", "family": [<id>], "implementers": [], "external": [],
     "source": "calls", "depth": 2, "property": bool, "plant": bool, "levels": {"1": <n>, "2": <n>},
     "sites": [...]}

Level 1 holds the callers of X, level 2 the callers of these callers that are no caller of X. X is in no level (a
recursion is not asked), and `levels` gives the count of the functions of each level. One site at the `decl` of
each function C of a level: `{"file", "line", "col", "class": "required", "why": "caller", "level", "lit",
"plant"}`, Go also `configs` (the `configs` of the record of C). `lit`: each use that makes C a caller at its level
has `lit` true. `plant`: the id of C starts with `plant:`. Go: when the id of C has two records or more, the site at
the `decl` of each of these records has the class `dnc` and the `why` `variant`; a record that is no caller takes
the `level` and `lit` of the first caller with this id. One site at the `decl` of X: `"class": "dnc", "why":
"decl"`. The sites are sorted by (file, line, col). `property`: X is a property (false for Go). `plant`: the id of
X starts with `plant:`. `keys.load_keys` reads the file, and `keys.score` scores an answer of declaration lines.

targets: the targets file of `benchlib.trace_plugin` for the chosen key records: X and each level-1 caller, each
one time, `{"id": "<file>:<line>", "file", "line"}` with the `decl` line, sorted by file and line.

tracecheck: the run-time proof of the chosen key records. The traced functions are those of `targets` (level 0 for
X, else 1). For each trace line `{"id", "caller_file", "caller_line"}` of a traced function F, G is the outermost
record of calls.jsonl whose lines `decl.line` to `end` hold `caller_line` in `caller_file`. The verdict:
`external` when `caller_file` is absolute or is in no record (no `decl` and no use in it: a library, the test
runner); else `key` when G is a caller of F; else `outside` (also a line in no function). The output: one line for
each traced function (`decl`, level, the count of each verdict, how many of its callers the `key` sites reached),
the totals with the count of the trace lines of other ids, then each `outside` site. Exit code 1 when a site is
`outside`, or when a function with callers has an `external` site; else 0.

dynmake: the caller keys of one level of the Go methods that a caller can reach through an interface value. The
sources are the static calls, the call sites of the interface methods and a run-time trace. `-calls` must be a Go
calls file, and `-symbols` is the key file of `gokeys extract` for the same tree. `-targets` is the targets file of
`gokeys trace`, a list of `{"id", "file", "line"}`. The record of a target is the one record of calls.jsonl whose
`decl` has this file and line. It is an error when no record or two records have it, or when an id comes two times.
`-trace` is the trace file of the test run in the copy of `gokeys trace`: lines `{"id", "frames": [{"func", "file",
"line"}, ...]}`, where `frames[0]` is the caller of the target. A line with the id of no target is counted and not
used. `-root` is the folder of the copy. A frame is IN THE TREE when its `file` is below `-root`: the two paths as
given (the root made absolute), or the two paths of `os.path.realpath`. Its tree path is the path relative to the
root. The FUNCTION of a frame in the tree is the outermost record whose lines `decl.line` to `end` hold the frame
line in that file. A frame in the tree in no function is counted, and for this command it is not in the tree.

A target T is ELIGIBLE when its open causes are exactly `interface` and its kind is `method`. Each other target is
counted and gets no record. The sets of an eligible target T:

    STATIC    the functions at the `in` of the uses of T with `call` true
    POSSIBLE  the functions that hold a site of the symbols record of T with `rel` `super` and `why` `use` (a call
              or a use of an interface method that T implements); a site in no function is counted
    DIRECT    the functions of the first frames of the trace lines of T, when the first frame is in the tree
    LIBRARY   for a trace line whose first frame is not in the tree: the function of the first later frame in the
              tree; a line with no such frame is counted, and a line with no frame too

THE RULE: each function of DIRECT is in STATIC or in POSSIBLE. The check uses the sets with T itself. A target that
breaks the rule gets no record. The command prints the `decl` of T and of the function, and its exit code is 1
after it wrote the other records. Then T goes out of the four sets: a recursion is not asked. REQUIRED is STATIC
and DIRECT together. A target with no required function is counted and gets no record. For each other eligible
target, in the order of calls.jsonl, `dynmake` writes one key record:

    {"id", "lang": "go", "kind": "method", "name", "container", "decl", "family": [<id>], "implementers": [],
     "external": [], "source": "calls+trace", "depth": 1, "property": false, "plant": false,
     "levels": {"1": <REQUIRED>, "2": 0},
     "dynamic": {"static": <STATIC>, "trace": <DIRECT, not STATIC>, "possible": <POSSIBLE, not REQUIRED>,
                 "library": <LIBRARY, not REQUIRED and not POSSIBLE>},
     "sites": [...]}

`levels` and `dynamic` hold function counts. Each function of the four sets has one site at its `decl`, with the
first class that fits:
- REQUIRED: the caller site of `make` at level 1 (with `configs`), and `"proof"`: `static`, `trace` or
  `static+trace`. `lit` is true when each static use that makes it a caller has `lit` true, and the `func` of each
  of its first frames ends with `.func<digits>` (a nested literal adds parts `.<digits>`: `.func1.2`).
- POSSIBLE: `"class": "dnc", "why": "possible"`.
- LIBRARY: `"class": "dnc", "why": "library"`.
When the id of a REQUIRED function has two records or more, each of these records gets `"class": "dnc", "why":
"variant"`, as in `make`. A record that is not required takes the `lit` and the `proof` of the first required record
with this id. The site at the `decl` of T is `"class": "dnc", "why": "decl"`. The sites are sorted by (file, line,
col). `keys.load_keys` reads the file, and `keys.score` scores it. The output gives the counts of the targets: not
eligible, with a record, that break the rule, with no required function. It also gives the sums of `dynamic` over
the records, the counted cases, the distribution of `dynamic["possible"]` over the records with `dynamic["trace"]` 1
or more, and one line for each pair that breaks the rule.
"""
import argparse
import ast
import collections
import fnmatch
import json
import os
import posixpath
import re
import sys
import tempfile
import time
import unicodedata

from benchlib import keys, pykeys

DEPTH = 2
ALLOWED_DECORATORS = ("staticmethod", "classmethod", "property", "cached_property", "functools", "cache",
                      "lru_cache", "override", "typing", "pytest", "patch", "mock", "unittest", "abc",
                      "abstractmethod")
PROPERTY_DECORATORS = ("property", "cached_property")

TEST_FILES = ("test_*.py", "*_test.py")  # the base name of the file of a Python test function

NO_KEY, VALUE, OUTSIDE = "no-key", "value", "outside"
UNKNOWN, NESTED, DECORATOR, GENERATOR, IMPLICIT = "unknown", "nested", "decorator", "generator", "implicit"
UNCALLED = "uncalled"
INTERFACE, UNPROVEN, VARIANTS, NO_SYMBOLS = "interface", "unproven", "variants", "no-symbols"
CAUSES = {"python": (NO_KEY, VALUE, OUTSIDE, UNKNOWN, NESTED, DECORATOR, GENERATOR, IMPLICIT, UNCALLED),
          "go": (NO_KEY, VALUE, OUTSIDE, INTERFACE, UNPROVEN, VARIANTS, NO_SYMBOLS)}
VERDICTS = ("key", "external", "outside")
# dynmake: the `func` of a frame in a function literal (`pkg.F.func1`, `pkg.(*T).M.func1.2`), the sets that the
# record counts, and the counted cases with their output text.
LIT_FUNC = re.compile(r"\.func[0-9]+(?:\.[0-9]+)*$")
DYN_SETS = ("static", "trace", "possible", "library")
DYN_COUNTED = {"other ids": "trace lines of other ids", "no frame": "trace lines with no frame",
               "no function": "frames in the tree in no function",
               "no tree frame": "library lines with no frame in the tree",
               "site in no function": "possible sites in no function"}
DYN_COUNTS = ("targets", "not eligible", "records", "rule", "no required") + DYN_SETS + tuple(DYN_COUNTED)


class CallKeysError(Exception):
    pass


def _key(p: dict) -> tuple[str, int, int]:
    return p["file"], p["line"], p["col"]


def _where(k: tuple[str, int, int]) -> str:
    return f"{k[0]}:{k[1]}:{k[2]}"


def _write_jsonl(path: str, records: list[dict]) -> None:
    """Write one JSON line for each record, in the given order, in one step (temp file + os.replace)."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


# ---- pycalls


def _parse(path: str, rel: str):
    try:
        text = pykeys._read(path)
        return text, ast.parse(text, filename=rel)
    except (SyntaxError, UnicodeDecodeError, ValueError) as e:
        raise CallKeysError(f"{rel}: the file does not parse: {e}") from e


def _decorator_text(node) -> str:
    """`a.b.c` for `@a.b.c` and `@a.b.c(...)`; `?` for another expression."""
    if isinstance(node, ast.Call):
        node = node.func
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return ".".join([node.id] + parts[::-1]) if isinstance(node, ast.Name) else "?"


def _same_scope(node) -> list:
    """The child nodes of `node` that run when `node` runs: the body of a def or a lambda does not."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return [*node.decorator_list, node.args] + ([node.returns] if node.returns else [])
    if isinstance(node, ast.Lambda):
        return [node.args]
    return list(ast.iter_child_nodes(node))


def _is_generator(node) -> bool:
    todo = list(node.body)
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.Yield, ast.YieldFrom)):
            return True
        todo.extend(_same_scope(n))
    return False


class _Places(ast.NodeVisitor):
    """The defs of one file, and the place of each Name and Attribute node: the outermost def whose body holds it,
    and whether a lambda or a nested def holds it."""

    def __init__(self, lines: list[str]):
        self.lines = lines
        self.defs = []  # (node, kind, container, outermost enclosing def or None)
        self.places = {}  # (line, col) of the name token -> (call, read, outermost def or None, lit)
        self.bodies = []  # the defs and lambdas whose body holds the current node, outermost first
        self.scope = []  # ("class" | "def", name), as pykeys
        self.calls = set()  # id() of the func node of each call (the tree is alive while the visitor runs)

    def _outer(self):
        return self.bodies[0] if self.bodies and not isinstance(self.bodies[0], ast.Lambda) else None

    def _visit_outside(self, node, body: list):
        skip = {id(n) for n in body}
        for child in ast.iter_child_nodes(node):
            if id(child) not in skip:
                self.visit(child)

    def _def(self, node):
        method = bool(self.scope) and self.scope[-1][0] == "class"
        container = ".".join(name for _, name in self.scope) if method else ""
        self.defs.append((node, "method" if method else "function", container, self._outer()))
        self._visit_outside(node, node.body)
        self.bodies.append(node)
        self.scope.append(("def", node.name))
        for stmt in node.body:
            self.visit(stmt)
        self.scope.pop()
        self.bodies.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _def

    def visit_Lambda(self, node):
        self._visit_outside(node, [node.body])
        self.bodies.append(node)
        self.visit(node.body)
        self.bodies.pop()

    def visit_ClassDef(self, node):
        self.scope.append(("class", node.name))
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node):
        self.calls.add(id(node.func))
        self.generic_visit(node)

    def _place(self, node, line: int, offset: int):
        text = self.lines[line - 1]
        c = offset if text.isascii() else len(text.encode("utf-8")[:offset].decode("utf-8", "replace"))
        outer = self._outer()
        call = id(node) in self.calls
        lit = len(self.bodies) > (0 if outer is None else 1)
        self.places[(line, pykeys._utf16_col(text, c))] = (call, isinstance(node.ctx, ast.Load) and not call,
                                                           outer, lit)

    def visit_Name(self, node):
        self._place(node, node.lineno, node.col_offset)

    def visit_Attribute(self, node):
        # The name token of an attribute ends the node.
        self._place(node, node.end_lineno, node.end_col_offset - len(node.attr.encode("utf-8")))
        self.generic_visit(node)


def _scan_file(path: str, rel: str, mentions: collections.Counter):
    """The def records of one file (no id, no uses) and the places of its name tokens; adds to `mentions`."""
    text, tree = _parse(path, rel)
    tokens = []
    for word, line, col, in_, prev in pykeys._occurrences(text):
        if in_ == "code" and prev == "def":
            tokens.append((word, line, col))
        elif in_ != "comment":
            mentions[word] += 1
    visitor = _Places(text.split("\n"))
    visitor.visit(tree)
    defs = sorted(visitor.defs, key=lambda d: (d[0].lineno, d[0].col_offset))
    if [d[0].name for d in defs] != [unicodedata.normalize("NFKC", t[0]) for t in tokens]:
        raise CallKeysError(f"{rel}: the def statements and the def name tokens differ")
    decl = {id(d[0]): {"file": rel, "line": line, "col": col} for d, (_, line, col) in zip(defs, tokens)}
    records = []
    for node, kind, container, outer in defs:
        own = decl[id(node)]
        records.append({"lang": "python", "kind": kind, "name": node.name, "container": container, "decl": own,
                        "end": node.end_lineno, "top": own if outer is None else decl[id(outer)],
                        "decorators": [_decorator_text(d) for d in node.decorator_list],
                        "generator": _is_generator(node), "async": isinstance(node, ast.AsyncFunctionDef)})
    places = {pos: (call, read, None if outer is None else decl[id(outer)], lit)
              for pos, (call, read, outer, lit) in visitor.places.items()}
    return records, places


def _use(site: dict, place) -> dict:
    out = {"file": site["file"], "line": site["line"], "col": site["col"]}
    if place is None:
        return {**out, "call": False, "read": False, "in": None, "lit": False, "unknown": True}
    call, read, in_, lit = place
    return {**out, "call": call, "read": read, "in": in_, "lit": lit}


def pycalls(root: str, key_records: list[dict]) -> list[dict]:
    """The records of calls.jsonl for a Python tree (see the module text), sorted by decl."""
    mentions, found, places = collections.Counter(), [], {}
    for path, rel in pykeys._py_files(root):
        records, places[rel] = _scan_file(path, rel, mentions)
        found += records
    by_decl = {_key(r["decl"]): r for r in found}
    ids = {}
    for rec in key_records:
        k = _key(rec["decl"])
        if k in ids:
            raise CallKeysError(f"{ids[k]['id']} and {rec['id']}: two key records with the decl {_where(k)}")
        if k not in by_decl:
            raise CallKeysError(f"{rec['id']}: no def at its decl {_where(k)}")
        ids[k] = rec
    out = []
    for rec in sorted(found, key=lambda r: _key(r["decl"])):
        key_rec = ids.get(_key(rec["decl"]))
        uses = [] if key_rec is None else sorted(
            (_use(s, places.get(s["file"], {}).get((s["line"], s["col"])))
             for s in key_rec["sites"] if s["class"] == "required"),
            key=_key)
        out.append({"id": "" if key_rec is None else key_rec["id"], **rec, "mentions": mentions[rec["name"]],
                    "uses": uses})
    return out


# ---- make


def is_property(rec: dict) -> bool:
    return any(d.rsplit(".", 1)[-1] in PROPERTY_DECORATORS for d in rec.get("decorators", ()))


def is_test_function(rec: dict) -> bool:
    """A Python test function: the name starts with `test`, and the base name of the file matches TEST_FILES."""
    base = posixpath.basename(rec["decl"]["file"])
    return rec["name"].startswith("test") and any(fnmatch.fnmatchcase(base, p) for p in TEST_FILES)


def _counts_as_call(rec: dict, use: dict, lang: str) -> bool:
    return use["call"] or (lang == "python" and use.get("read", False) and is_property(rec))


def _language(calls: list[dict], symbols) -> str:
    langs = sorted({r["lang"] for r in calls})
    if langs not in (["go"], ["python"]):
        raise CallKeysError(f"the calls file must hold the records of one language, go or python: {langs}")
    if langs[0] == "go" and symbols is None:
        raise CallKeysError("a Go calls file needs -symbols (the key file of gokeys extract for the same tree)")
    if langs[0] == "python" and symbols is not None:
        raise CallKeysError("-symbols is not allowed for a Python calls file")
    return langs[0]


def _index(calls: list[dict]) -> dict:
    by_decl = {}
    for rec in calls:
        k = _key(rec["decl"])
        if k in by_decl:
            raise CallKeysError(f"two records with the decl {_where(k)}")
        by_decl[k] = rec
    for rec in calls:
        for u in rec["uses"]:
            if u["in"] is not None and _key(u["in"]) not in by_decl:
                raise CallKeysError(f"the use {_where(_key(u))} of {_where(_key(rec['decl']))} has `in` "
                                    f"{_where(_key(u['in']))}, and no record has this decl")
    return by_decl


def _causes(rec: dict, lang: str, by_id: dict, symbols: dict) -> list[str]:
    uses, rid = rec["uses"], rec["id"]
    found = set()
    if rid == "" and (uses or (lang == "python" and rec["mentions"] > 0)):
        found.add(NO_KEY)
    if any(not _counts_as_call(rec, u, lang) for u in uses):
        found.add(VALUE)
    if any(u["in"] is None for u in uses):
        found.add(OUTSIDE)
    if lang == "python":
        if any(u.get("unknown") for u in uses):
            found.add(UNKNOWN)
        if rec["top"] != rec["decl"]:
            found.add(NESTED)
        if any(d.split(".", 1)[0] not in ALLOWED_DECORATORS for d in rec["decorators"]):
            found.add(DECORATOR)
        if rec["generator"] or rec["async"]:
            found.add(GENERATOR)
        if rec["name"].startswith("__") and rec["name"].endswith("__"):
            found.add(IMPLICIT)
        if not uses and not is_test_function(rec):
            found.add(UNCALLED)
    elif rid:
        syms = symbols.get(rid, [])
        if not syms:
            found.add(NO_SYMBOLS)
        if any(any(f != rid for f in s["family"]) or s["external"] for s in syms):
            found.add(INTERFACE)
        if any(site["why"] in ("string", "unproven") for s in syms for site in s["sites"]):
            found.add(UNPROVEN)
        if len(by_id[rid]) > 1:
            found.add(VARIANTS)
    return [c for c in CAUSES[lang] if c in found]


def _context(calls: list[dict], symbols):
    lang = _language(calls, symbols)
    by_decl = _index(calls)
    by_id = collections.defaultdict(list)
    for rec in calls:
        if rec["id"]:
            by_id[rec["id"]].append(rec)
    syms = collections.defaultdict(list)
    for rec in symbols or ():
        syms[rec["id"]].append(rec)
    causes = {k: _causes(rec, lang, by_id, syms) for k, rec in by_decl.items()}
    return lang, by_decl, by_id, causes


def open_causes(calls: list[dict], symbols: list[dict] | None = None) -> dict[tuple, list[str]]:
    """The open causes of each function, by its decl (file, line, col); an empty list for a closed function."""
    return _context(calls, symbols)[3]


def callers(rec: dict) -> set[tuple[str, int, int]]:
    """The decls of the functions at the `in` positions of the uses of the record."""
    return {_key(u["in"]) for u in rec["uses"] if u["in"] is not None}


def _caller_site(rec: dict, level: int, lit: bool, lang: str) -> dict:
    d = rec["decl"]
    site = {"file": d["file"], "line": d["line"], "col": d["col"], "class": "required", "why": "caller",
            "level": level, "lit": lit, "plant": rec["id"].startswith("plant:")}
    if lang == "go":
        site["configs"] = rec["configs"]
    return site


def _key_record(x: dict, lang: str, by_decl: dict, by_id: dict) -> dict:
    xk = _key(x["decl"])
    first = callers(x)
    level1 = first - {xk}
    level2 = set().union(*(callers(by_decl[c]) for c in level1)) - first - {xk}
    sites = {}
    for level, members, sources in ((1, level1, [x]), (2, level2, [by_decl[c] for c in level1])):
        for c in sorted(members):
            lit = all(u["lit"] for s in sources for u in s["uses"] if u["in"] is not None and _key(u["in"]) == c)
            sites[c] = _caller_site(by_decl[c], level, lit, lang)
    if lang == "go":
        for c in sorted(level1 | level2, key=lambda c: (sites[c]["level"], c)):
            variants = by_id.get(by_decl[c]["id"], [])  # by_id has no empty id
            if len(variants) < 2:
                continue
            for rec in variants:
                k = _key(rec["decl"])
                if k not in sites:
                    sites[k] = _caller_site(rec, sites[c]["level"], sites[c]["lit"], lang)
                sites[k].update({"class": "dnc", "why": "variant"})
    sites[xk] = {**x["decl"], "class": "dnc", "why": "decl"}
    return {"id": x["id"], "lang": lang, "kind": x["kind"], "name": x["name"], "container": x["container"],
            "decl": x["decl"], "family": [x["id"]], "implementers": [], "external": [], "source": "calls",
            "depth": DEPTH, "property": lang == "python" and is_property(x), "plant": x["id"].startswith("plant:"),
            "levels": {"1": len(level1), "2": len(level2)}, "sites": [sites[k] for k in sorted(sites)]}


def make_keys(calls: list[dict], symbols: list[dict] | None = None) -> tuple[list[dict], dict]:
    """The key record of each target (see the module text), in the order of `calls`, and the counts."""
    lang, by_decl, by_id, causes = _context(calls, symbols)
    closed = {k for k, c in causes.items() if not c}
    records = []
    for rec in calls:
        k = _key(rec["decl"])
        found = callers(rec)
        if k in closed and rec["id"] and found and found <= closed:
            records.append(_key_record(rec, lang, by_decl, by_id))
    counts = collections.Counter(c for found in causes.values() for c in found)
    stats = {"functions": len(calls), "closed": len(closed), "targets": len(records),
             "causes": {c: counts[c] for c in CAUSES[lang]},
             "level1": collections.Counter(r["levels"]["1"] for r in records),
             "level2": collections.Counter(r["levels"]["2"] for r in records)}
    return records, stats


# ---- targets and tracecheck


def _ids(arg: str) -> list[str]:
    if arg.startswith("@"):
        with open(arg[1:], encoding="utf-8") as f:
            arg = f.read()
    return [i for i in re.split(r"[,\s]+", arg) if i]


def _chosen(records: list[dict], ids: list[str]) -> list[dict]:
    by_id = {r["id"]: r for r in records}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise CallKeysError(f"no key record with the id {', '.join(missing)}")
    return [by_id[i] for i in ids]


def traced_functions(records: list[dict], ids: list[str]) -> dict[tuple, int]:
    """The decl of X (level 0) and of each level-1 caller (level 1) of the chosen key records."""
    chosen = _chosen(records, ids)
    out = {_key(r["decl"]): 0 for r in chosen}
    for rec in chosen:
        for s in rec["sites"]:
            if s["why"] == "caller" and s["level"] == 1:
                out.setdefault(_key(s), 1)
    return out


def trace_targets(records: list[dict], ids: list[str]) -> list[dict]:
    lines = sorted({(f, line) for f, line, _ in traced_functions(records, ids)})
    return [{"id": f"{f}:{line}", "file": f, "line": line} for f, line in lines]


def tracecheck(records: list[dict], ids: list[str], calls: list[dict], trace: list[dict]) -> tuple[list[str], int]:
    """The output lines and the exit code of `tracecheck` (see the module text)."""
    traced = traced_functions(records, ids)
    by_decl = {_key(r["decl"]): r for r in calls}
    for k in traced:
        if k not in by_decl:
            raise CallKeysError(f"the traced function {_where(k)} has no record in the calls file")
    spans, known = collections.defaultdict(list), set()
    for rec in calls:
        spans[rec["decl"]["file"]].append((rec["decl"]["line"], rec["end"], _key(rec["decl"])))
        known.add(rec["decl"]["file"])
        known.update(u["file"] for u in rec["uses"])
    by_target_id = {f"{k[0]}:{k[1]}": k for k in traced}
    counts = {k: collections.Counter() for k in traced}
    reached = {k: set() for k in traced}
    outside, other = [], 0
    for t in trace:
        f = by_target_id.get(t["id"])
        if f is None:
            other += 1
            continue
        file, line = t["caller_file"], t["caller_line"]
        if os.path.isabs(file) or file not in known:
            verdict = "external"
        else:
            holders = [(start, k) for start, end, k in spans[file] if start <= line <= end]
            g = min(holders)[1] if holders else None
            verdict = "key" if g in callers(by_decl[f]) else "outside"
            if verdict == "key":
                reached[f].add(g)
            else:
                outside.append((file, line, f))
        counts[f][verdict] += 1
    lines, failed = [], bool(outside)
    for f in sorted(traced, key=lambda k: (traced[k], k)):
        n = len(callers(by_decl[f]))
        failed = failed or bool(n and counts[f]["external"])
        lines.append(f"{_where(f)} level {traced[f]}: " + ", ".join(f"{v} {counts[f][v]}" for v in VERDICTS)
                     + f", callers reached {len(reached[f])} of {n}")
    total = collections.Counter()
    for c in counts.values():
        total.update(c)
    lines.append(f"tracecheck: {len(traced)} functions, {sum(total.values())} sites: "
                 + ", ".join(f"{v} {total[v]}" for v in VERDICTS) + f"; trace lines of other ids: {other}")
    lines += [f"outside {file}:{line} (calls {_where(f)})" for file, line, f in sorted(outside)]
    return lines, 1 if failed else 0


# ---- dynmake


def _spans(calls: list[dict]) -> dict[str, list]:
    spans = collections.defaultdict(list)
    for rec in calls:
        spans[rec["decl"]["file"]].append((rec["decl"]["line"], rec["end"], _key(rec["decl"])))
    return spans


def _holder(spans: dict, file: str, line: int) -> tuple | None:
    """The decl of the outermost record whose lines `decl.line` to `end` hold the line of the file, or None."""
    holders = [(start, k) for start, end, k in spans.get(file, ()) if start <= line <= end]
    return min(holders)[1] if holders else None


def _dyn_targets(targets: list[dict], calls: list[dict]) -> dict[str, tuple]:
    """The decl of the record of each target, by the target id: the one record whose decl has its file and line."""
    by_line = collections.defaultdict(list)
    for rec in calls:
        by_line[(rec["decl"]["file"], rec["decl"]["line"])].append(_key(rec["decl"]))
    out = {}
    for t in targets:
        found = by_line.get((t["file"], t["line"]), [])
        if t["id"] in out:
            raise CallKeysError(f"the target id {t['id']} comes two times")
        if len(found) != 1:
            raise CallKeysError(f"target {t['id']}: {len(found)} records of the calls file have the decl line "
                                f"{t['file']}:{t['line']}, expected 1")
        out[t["id"]] = found[0]
    return out


def _tree_path(file: str, roots: tuple[str, str]) -> str | None:
    """The path of a frame file relative to the copy: below the root as given, or (both resolved) below the real
    root. None for a file outside the copy."""
    given, real = roots
    if file.startswith(given + os.sep):
        return file[len(given) + 1:]
    resolved = os.path.realpath(file)
    return resolved[len(real) + 1:] if resolved.startswith(real + os.sep) else None


def _frame_function(frame: dict, roots: tuple, spans: dict, stats: dict) -> tuple | None:
    """The decl of the function of a frame in the tree, or None. A frame below the root in no function is counted."""
    rel = _tree_path(frame["file"], roots)
    if rel is None:
        return None
    k = _holder(spans, rel, frame["line"])
    if k is None:
        stats["no function"] += 1
    return k


def _trace_sets(lines: list[dict], roots: tuple, spans: dict, stats: dict) -> tuple[dict, set]:
    """DIRECT (the function of each first frame in the tree, with the `func` names of these frames) and LIBRARY (the
    function of the first later frame in the tree, when the first frame is not in the tree) of the trace lines of
    one target."""
    direct, library = collections.defaultdict(list), set()
    for t in lines:
        frames = t["frames"]
        if not frames:
            stats["no frame"] += 1
            continue
        first = _frame_function(frames[0], roots, spans, stats)
        if first is not None:
            direct[first].append(frames[0]["func"])
            continue
        later = next((k for k in (_frame_function(f, roots, spans, stats) for f in frames[1:]) if k is not None), None)
        if later is None:
            stats["no tree frame"] += 1
        else:
            library.add(later)
    return direct, library


def _possible(sym_records: list[dict], spans: dict, stats: dict) -> set:
    """The functions that hold a site with `rel` `super` and `why` `use`; a site in no function is counted."""
    out = set()
    for s in (site for rec in sym_records for site in rec["sites"]):
        if s.get("rel") == "super" and s["why"] == "use":
            k = _holder(spans, s["file"], s["line"])
            if k is None:
                stats["site in no function"] += 1
            else:
                out.add(k)
    return out


def _dyn_record(x: dict, static: set, direct: dict, possible: set, library: set, by_decl: dict,
                by_id: dict) -> dict:
    """The key record of an eligible target X from its four sets (X is in none of them)."""
    required = static | set(direct)
    sites = {c: {**by_decl[c]["decl"], "class": "dnc", "why": "library"} for c in library}
    sites.update({c: {**by_decl[c]["decl"], "class": "dnc", "why": "possible"} for c in possible})
    for c in required:
        lit = (all(u["lit"] for u in x["uses"] if u["call"] and u["in"] is not None and _key(u["in"]) == c)
               and all(LIT_FUNC.search(f) for f in direct.get(c, ())))
        proof = "static+trace" if c in static and c in direct else "static" if c in static else "trace"
        sites[c] = {**_caller_site(by_decl[c], 1, lit, "go"), "proof": proof}
    done = set()
    for c in sorted(required):
        variants = by_id.get(by_decl[c]["id"], [])  # by_id has no empty id
        if len(variants) < 2:
            continue
        for rec in variants:
            k = _key(rec["decl"])
            if k not in required and k not in done:
                sites[k] = {**_caller_site(rec, 1, sites[c]["lit"], "go"), "proof": sites[c]["proof"]}
            done.add(k)
            sites[k].update({"class": "dnc", "why": "variant"})
    xk = _key(x["decl"])
    sites[xk] = {**x["decl"], "class": "dnc", "why": "decl"}
    dynamic = {"static": len(static), "trace": len(set(direct) - static), "possible": len(possible - required),
               "library": len(library - required - possible)}
    return {"id": x["id"], "lang": "go", "kind": "method", "name": x["name"], "container": x["container"],
            "decl": x["decl"], "family": [x["id"]], "implementers": [], "external": [], "source": "calls+trace",
            "depth": 1, "property": False, "plant": False, "levels": {"1": len(required), "2": 0},
            "dynamic": dynamic, "sites": [sites[k] for k in sorted(sites)]}


def dyn_keys(calls: list[dict], symbols: list[dict], targets: list[dict], trace: list[dict],
             root: str) -> tuple[list[dict], dict, list[tuple]]:
    """The key records of `dynmake` (see the module text) in the order of `calls`, the counts (DYN_COUNTS, and
    `spread`: the distribution of `dynamic["possible"]` over the records with `dynamic["trace"]` 1 or more), and
    the pairs (decl of a target, decl of a traced caller) that break the rule."""
    if sorted({r["lang"] for r in calls}) != ["go"]:
        raise CallKeysError("dynmake needs a Go calls file (gokeys calls)")
    _, by_decl, by_id, causes = _context(calls, symbols)
    spans, roots = _spans(calls), (os.path.abspath(root), os.path.realpath(root))
    target_of = _dyn_targets(targets, calls)
    stats = {**{k: 0 for k in DYN_COUNTS}, "targets": len(target_of), "spread": collections.Counter()}
    lines = collections.defaultdict(list)
    for t in trace:
        if t["id"] in target_of:
            lines[target_of[t["id"]]].append(t)
        else:
            stats["other ids"] += 1
    syms = collections.defaultdict(list)
    for rec in symbols:
        syms[rec["id"]].append(rec)
    chosen = set(target_of.values())
    records, breaks = [], []
    for x in calls:
        xk = _key(x["decl"])
        if xk not in chosen:
            continue
        if causes[xk] != [INTERFACE] or x["kind"] != "method":
            stats["not eligible"] += 1
            continue
        static = {_key(u["in"]) for u in x["uses"] if u["call"] and u["in"] is not None}
        possible = _possible(syms[x["id"]], spans, stats)
        direct, library = _trace_sets(lines[xk], roots, spans, stats)
        broken = sorted(set(direct) - static - possible)
        if broken:
            breaks += [(xk, c) for c in broken]
            stats["rule"] += 1
            continue
        direct.pop(xk, None)
        static.discard(xk)
        if not static and not direct:
            stats["no required"] += 1
            continue
        rec = _dyn_record(x, static, direct, possible - {xk}, library - {xk}, by_decl, by_id)
        records.append(rec)
        stats["records"] += 1
        for k in DYN_SETS:
            stats[k] += rec["dynamic"][k]
        if rec["dynamic"]["trace"] >= 1:
            stats["spread"][rec["dynamic"]["possible"]] += 1
    return records, stats, breaks


def _dyn_lines(stats: dict, breaks: list[tuple]) -> list[str]:
    return [f"dynmake: {stats['targets']} targets, {stats['not eligible']} not eligible, {stats['records']} with a "
            f"record, {stats['rule']} breaking the rule, {stats['no required']} with no required function",
            "sums over the records: " + ", ".join(f"{k} {stats[k]}" for k in DYN_SETS),
            "counted: " + ", ".join(f"{text} {stats[k]}" for k, text in DYN_COUNTED.items()),
            f'dynamic["possible"] of the records with trace 1 or more: {_distribution(stats["spread"])}'] + [
        f"rule: the target {_where(x)} has the traced caller {_where(c)}, which is no static caller and holds no "
        "call site of an interface method of the target" for x, c in breaks]


# ---- the commands


def _distribution(counter: collections.Counter) -> str:
    return ", ".join(f"{n}: {counter[n]}" for n in sorted(counter)) or "none"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m benchlib.callkeys")
    commands = parser.add_subparsers(dest="command", required=True)
    py = commands.add_parser("pycalls", help="the calls file of a Python tree")
    py.add_argument("-root", required=True, help="tree root")
    py.add_argument("-unique", required=True, help="the key file of pykeys unique for the tree")
    py.add_argument("-plant", help="the key file of benchlib.plant for the tree")
    py.add_argument("-out", required=True, help="calls.jsonl")
    mk = commands.add_parser("make", help="the caller keys of a calls file")
    mk.add_argument("-calls", required=True, help="calls.jsonl (gokeys calls, or pycalls)")
    mk.add_argument("-symbols", help="go: the key file of gokeys extract for the same tree")
    mk.add_argument("-out", required=True, help="JSONL key file")
    tg = commands.add_parser("targets", help="the targets file of benchlib.trace_plugin")
    tg.add_argument("-keys", required=True, help="the key file of make")
    tg.add_argument("-ids", required=True, help="comma-separated key ids, or @<file>")
    tg.add_argument("-out", required=True, help="targets.json")
    tc = commands.add_parser("tracecheck", help="check a trace of benchlib.trace_plugin against the keys")
    tc.add_argument("-keys", required=True, help="the key file of make")
    tc.add_argument("-calls", required=True, help="the calls file of the keys")
    tc.add_argument("-trace", required=True, help="the trace file of benchlib.trace_plugin")
    tc.add_argument("-ids", required=True, help="comma-separated key ids, or @<file>")
    dm = commands.add_parser("dynmake", help="the caller keys of Go methods through an interface value, from a "
                                             "trace of gokeys trace")
    dm.add_argument("-calls", required=True, help="calls.jsonl of gokeys calls")
    dm.add_argument("-symbols", required=True, help="the key file of gokeys extract for the same tree")
    dm.add_argument("-targets", required=True, help="the targets file of gokeys trace")
    dm.add_argument("-trace", required=True, help="the trace file of the run in the copy (BENCH_TRACE_OUT)")
    dm.add_argument("-root", required=True, help="the folder of the copy of gokeys trace")
    dm.add_argument("-out", required=True, help="JSONL key file")
    args = parser.parse_args(argv)
    start = time.monotonic()
    try:
        if args.command == "pycalls":
            key_records = keys.load_keys(args.unique) + (keys.load_keys(args.plant) if args.plant else [])
            records = pycalls(args.root, key_records)
            _write_jsonl(args.out, records)
            uses = [u for r in records for u in r["uses"]]
            print(f"pycalls: {len(records)} records, {sum(1 for r in records if r['id'])} with an id, "
                  f"{len(uses)} uses: {sum(1 for u in uses if not u['call'])} call false, "
                  f"{sum(1 for u in uses if u['in'] is None)} in null, {sum(1 for u in uses if u['lit'])} lit true, "
                  f"{sum(1 for u in uses if u.get('unknown'))} unknown, {time.monotonic() - start:.1f} s")
        elif args.command == "make":
            symbols = keys.load_keys(args.symbols) if args.symbols else None
            records, stats = make_keys(keys.load_keys(args.calls), symbols)
            _write_jsonl(args.out, records)
            print(f"make: {stats['functions']} functions, {stats['closed']} closed, {stats['targets']} targets "
                  f"(depth {DEPTH})")
            print("open causes: " + ", ".join(f"{c} {n}" for c, n in stats["causes"].items()))
            print(f'levels["1"]: {_distribution(stats["level1"])}')
            print(f'levels["2"]: {_distribution(stats["level2"])}')
        elif args.command == "targets":
            targets = trace_targets(keys.load_keys(args.keys), _ids(args.ids))
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(targets, f, indent=1)
                f.write("\n")
            print(f"targets: {len(targets)} functions in {args.out}")
        elif args.command == "dynmake":
            with open(args.targets, encoding="utf-8") as f:
                targets = json.load(f)
            records, stats, breaks = dyn_keys(keys.load_keys(args.calls), keys.load_keys(args.symbols), targets,
                                              keys.load_keys(args.trace), args.root)
            _write_jsonl(args.out, records)
            print("\n".join(_dyn_lines(stats, breaks)))
            return 1 if breaks else 0
        else:
            lines, code = tracecheck(keys.load_keys(args.keys), _ids(args.ids), keys.load_keys(args.calls),
                                     keys.load_keys(args.trace))
            print("\n".join(lines))
            return code
    except CallKeysError as e:
        print(f"callkeys: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
