"""Python answer keys: a token scan of unique names, and the class hierarchy by reflection.

    python3 -m benchlib.pykeys unique -root <tree> -python <interpreter> -modules <a,b> -out <keys.jsonl>
        [-min-required <n>]
    python3 -m benchlib.pykeys hierarchy -root <tree> -python <interpreter> -packages <a,b> -out <keys.jsonl>

(run from live-test/agent-bench). The work with the product interpreter runs in a child process of that
interpreter; this process needs only the standard library.

Positions: `file` is relative to the tree root, with forward slashes. `line` is 1-based. `col` is 1-based
and counts UTF-16 code units (the unit of the IDE plugin). A `decl` points at the name token of the `def`
or the `class`. The scan reads each `.py` file that is not below `.venv`, `.git` or `node_modules`.

Ids: `py:<module>.<Class>.<name>` for a method, `py:<module>.<name>` for a function, and
`py:<module>.<qualname>` for a class. The module path comes from the file path (no `.py`, no `__init__`).

`unique` makes one record (`source: scan`) for each function or method whose name
(a) has exactly one `def` in the tree, (b) is not in `library_attrs`, (c) is in no string literal (also a
docstring), (d) is bound in no other way: no parameter, keyword argument, assignment target (`self.<name> =`
too), class, import alias, `global`, `except ... as`, or match capture, and (e) has 12 characters or more.
The name also must not start and end with two underscores, must not name a module of the tree or a part
of an imported module path, must not be imported from a module outside the tree, and its `def` must not be
inside a function. Each other code occurrence of the name is `required` (`why: use`): a call, an attribute
access, or the name as a value. The `def`, the import lines and the comments are `dnc`. `-min-required <n>`
keeps only the records with n required lines or more.

`hierarchy` makes one record of kind `class` (`source: reflection`, no sites) for each class of the tree that
the import of the packages loads. Its `implementers` with `class: required` are all subclasses that the tree
defines (transitive, from `__subclasses__()`). An `ast` scan of the tree files finds each `class` statement
that reflection did not see (a class in a function, a class of a module that failed to import, a class of a
file that no package holds). Such a statement is an implementer with `class: dnc` of each record with the
name of one of its bases (the last identifier of the base expression), and of each record that has an
implementer of that name, until no entry is added. The first record is
`{"id": "_meta", "skipped": [...], "dynamic": [...], "unseen": n}`: `skipped` lists the modules that failed to
import, `dynamic` the classes of the tree with no source position (made at run time), `unseen` counts the
class statements that reflection did not see. `load_keys` users skip the `_meta` record by its id.
"""
import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tokenize

from benchlib import keys

SKIP_DIRS = (".venv", ".git", "node_modules")
MIN_LEN = 12
CHILD_TIMEOUT = 1800

_WORD = re.compile(r"\w+")
# A backslash escape in the text of a string token; replaced by two spaces, so the offsets do not move.
_ESCAPE = re.compile(r"\\[^\n]")
_FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", None)


def _py_files(root: str) -> list[tuple[str, str]]:
    """(path, path relative to the root with forward slashes) of each scanned `.py` file, sorted."""
    out = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name.endswith(".py"):
                path = os.path.join(folder, name)
                out.append((path, os.path.relpath(path, root).replace(os.sep, "/")))
    return out


def _read(path: str) -> str:
    with tokenize.open(path) as f:
        return f.read()


def _module_parts(rel: str) -> list[str]:
    parts = rel[:-3].split("/")
    return parts[:-1] if parts[-1] == "__init__" else parts


def _utf16_col(line: str, c: int) -> int:
    """1-based UTF-16 column of the 0-based code point column `c` of `line`."""
    return c + 1 if line.isascii() else len(line[:c].encode("utf-16-le")) // 2 + 1


def _text_words(text: str, string: bool):
    """(word, offset) of each word of a comment or a string token. In a string, a word that a backslash escape
    hides (`"\\nname"`) also counts."""
    found = [(m.group(), m.start()) for m in _WORD.finditer(text)]
    if string and "\\" in text:
        seen = set(found)
        found += [w for w in ((m.group(), m.start()) for m in _WORD.finditer(_ESCAPE.sub("  ", text)))
                  if w not in seen]
    return found


def _occurrences(text: str):
    """Yield (word, line, col, in, prev) for each NAME token, and for each word in a comment or a string.

    `in` is `code`, `comment` or `string`. `prev` (code only) is `import` in an import statement, else `.`,
    `def` or `class` for that previous token, else empty. `col` is 1-based in UTF-16 code units.
    """
    lines = text.split("\n")
    prev = None
    first = None  # the first token of the current statement
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        kind = tok.type
        if kind == tokenize.NAME:
            # `import` and `from` after a colon start a statement (`if x: import y`); no expression has them there.
            if first is None or (tok.string in ("import", "from") and prev.type == tokenize.OP and prev.string == ":"):
                first = tok
            if first.type == tokenize.NAME and first.string in ("import", "from"):
                where = "import"
            elif prev is not None and prev.type == tokenize.OP and prev.string == ".":
                where = "."
            elif prev is not None and prev.type == tokenize.NAME and prev.string in ("def", "class"):
                where = prev.string
            else:
                where = ""
            row, col = tok.start
            yield tok.string, row, _utf16_col(lines[row - 1], col), "code", where
            prev = tok
        elif kind == tokenize.COMMENT or kind == tokenize.STRING or (_FSTRING_MIDDLE and kind == _FSTRING_MIDDLE):
            in_ = "comment" if kind == tokenize.COMMENT else "string"
            row, col = tok.start
            for word, offset in _text_words(tok.string, in_ == "string"):
                newlines = tok.string.count("\n", 0, offset)
                if newlines:
                    line, c = row + newlines, offset - tok.string.rfind("\n", 0, offset) - 1
                else:
                    line, c = row, col + offset
                yield word, line, _utf16_col(lines[line - 1], c), in_, ""
            if kind != tokenize.COMMENT:
                if first is None:
                    first = tok
                prev = tok
        elif kind == tokenize.NEWLINE or (kind == tokenize.OP and tok.string == ";"):
            first, prev = None, tok
        elif kind not in (tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER):
            if first is None:
                first = tok
            prev = tok


def ident_sites(root: str, name: str) -> list[dict]:
    """Each occurrence of the identifier `name` in the `.py` files of the tree, in code, comments and strings."""
    out = []
    for path, rel in _py_files(root):
        text = _read(path)
        if name not in text:
            continue
        found = {(line, col, in_, prev) for word, line, col, in_, prev in _occurrences(text) if word == name}
        out += [{"file": rel, "line": line, "col": col, "in": in_, "prev": prev} for line, col, in_, prev in sorted(found)]
    return out


class _Bindings(ast.NodeVisitor):
    """The `def`s of one file, and the names that the file binds in another way."""

    def __init__(self):
        self.defs = []  # (name, container, nested)
        self.bound = set()
        self.modparts = set()  # the parts of the module paths of the import statements
        self.imported = []  # (module, level, name) of `from module import name`
        self.scope = []  # ("class" | "def", name)

    def _def(self, node):
        nested = any(kind == "def" for kind, _ in self.scope)
        self.defs.append((node.name, ".".join(name for _, name in self.scope), nested))
        self.scope.append(("def", node.name))
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _def

    def visit_ClassDef(self, node):
        self.bound.add(node.name)
        self.scope.append(("class", node.name))
        self.generic_visit(node)
        self.scope.pop()

    def visit_arg(self, node):
        self.bound.add(node.arg)
        self.generic_visit(node)

    def visit_keyword(self, node):
        if node.arg:
            self.bound.add(node.arg)
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bound.add(node.id)

    def visit_Attribute(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bound.add(node.attr)
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            self.modparts.update(alias.name.split("."))
            if alias.asname:
                self.bound.add(alias.asname)

    def visit_ImportFrom(self, node):
        if node.module:
            self.modparts.update(node.module.split("."))
        for alias in node.names:
            if alias.asname:
                # The uses under the other name are no occurrence of the name.
                self.bound.update((alias.name, alias.asname))
            else:
                self.imported.append((node.module or "", node.level, alias.name))

    def _names(self, node):
        self.bound.update(node.names)

    visit_Global = visit_Nonlocal = _names

    def _name(self, node):
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    visit_ExceptHandler = visit_MatchAs = visit_MatchStar = _name
    visit_TypeVar = visit_ParamSpec = visit_TypeVarTuple = _name

    def visit_MatchMapping(self, node):
        if node.rest:
            self.bound.add(node.rest)
        self.generic_visit(node)

    def visit_MatchClass(self, node):
        self.bound.update(node.kwd_attrs)
        self.generic_visit(node)


def _parse(path: str, rel: str):
    text = _read(path)
    try:
        return text, ast.parse(text, filename=rel)
    except SyntaxError as e:
        raise ValueError(f"{rel}: {e}") from e


def unique_name_keys(root: str, library_attrs: set[str]) -> list[dict]:
    """One key record (`source: scan`) for each function or method with a unique name (see the module text)."""
    files = _py_files(root)
    tree_modules, module_names = set(), set()
    for _, rel in files:
        parts = _module_parts(rel)
        tree_modules.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
        module_names.update(rel[:-3].split("/"))
    count, where, bound, outside, texts = {}, {}, set(), set(), {}
    for path, rel in files:
        text, tree = _parse(path, rel)
        texts[rel] = text
        visitor = _Bindings()
        visitor.visit(tree)
        for name, container, nested in visitor.defs:
            count[name] = count.get(name, 0) + 1
            where[name] = (rel, container, nested)
        bound |= visitor.bound | visitor.modparts
        outside.update(name for module, level, name in visitor.imported if level == 0 and module not in tree_modules)
    candidates = {name for name, n in count.items()
                  if n == 1 and len(name) >= MIN_LEN and not (name.startswith("__") and name.endswith("__"))
                  and not where[name][2] and name not in library_attrs and name not in bound
                  and name not in module_names and name not in outside}
    found = {name: [] for name in candidates}
    in_string = set()
    for rel, text in texts.items():
        for word, line, col, in_, prev in _occurrences(text):
            if in_ == "string":
                in_string.add(word)
            elif word in found:
                found[word].append((rel, line, col, in_, prev))
    records = []
    for name in sorted(candidates - in_string):
        rel, container, _ = where[name]
        module = ".".join(_module_parts(rel))
        rid = "py:" + ".".join(p for p in (module, container, name) if p)
        sites, decls = [], []
        for file, line, col, in_, prev in sorted(set(found[name])):
            if in_ == "comment":
                cls, why = "dnc", "comment"
            elif prev == "def":
                cls, why = "dnc", "decl"
                decls.append({"file": file, "line": line, "col": col})
            elif prev == "import":
                cls, why = "dnc", "import"
            else:
                cls, why = "required", "use"
            sites.append({"file": file, "line": line, "col": col, "class": cls, "why": why})
        if len(decls) != 1:
            raise ValueError(f"{rid}: {len(decls)} def name tokens for one def")
        records.append({"id": rid, "lang": "python", "kind": "method" if container else "function", "name": name,
                        "container": container, "decl": decls[0], "family": [rid], "sites": sites,
                        "implementers": [], "external": [], "source": "scan"})
    return records


# The child process of the product interpreter. It imports the packages and each module below their folders,
# and writes one JSON object to its first stdout (the imported code prints to stderr). argv[1] is a JSON
# object: mode ("attrs" or "hierarchy"), packages, root (or null).
_CHILD = r'''
import importlib, inspect, json, os, sys
out = os.fdopen(os.dup(1), "w", encoding="utf-8")
os.dup2(2, 1)
sys.stdout = sys.stderr
args = json.loads(sys.argv[1])
packages, root = args["packages"], args["root"]
if root:
    sys.path.insert(0, root)
skipped = []


def load(name):
    try:
        importlib.import_module(name)
        return True
    except KeyboardInterrupt:
        raise
    except BaseException as e:  # also SystemExit, and the Skipped of pytest.importorskip
        skipped.append({"module": name, "error": type(e).__name__})
        return False


def submodules(name):
    found = set()
    for base in list(getattr(sys.modules[name], "__path__", [])):
        for folder, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d.isidentifier())
            rel = os.path.relpath(folder, base)
            parts = [] if rel == "." else rel.split(os.sep)
            for f in files:
                stem = f[:-3]
                if f.endswith(".py") and stem.isidentifier():
                    found.add(".".join([name] + parts + ([] if stem == "__init__" else [stem])))
    found.discard(name)
    return sorted(found)


for package in packages:
    if load(package):
        for module in submodules(package):
            load(module)


def subclasses(cls):
    try:
        return type.__subclasses__(cls)
    except TypeError:
        return []


def all_classes():
    seen, stack, out = set(), [object], []
    while stack:
        cls = stack.pop()
        if id(cls) not in seen:
            seen.add(id(cls))
            out.append(cls)
            stack.extend(subclasses(cls))
    return out


def module_of(cls):
    try:
        return cls.__module__ if isinstance(cls.__module__, str) else None
    except Exception:
        return None


if args["mode"] == "attrs":
    def of_tree(name):
        return name is not None and any(name == p or name.startswith(p + ".") for p in packages)

    names = set()
    for name, module in list(sys.modules.items()):
        if module is not None and not of_tree(name):
            try:
                names.update(dir(module))
            except Exception:
                pass
    for cls in all_classes():
        if of_tree(module_of(cls)):
            continue
        try:
            names.update(dir(cls))
            annotations = vars(cls).get("__annotations__")
            if isinstance(annotations, dict):
                names.update(annotations)
        except Exception:
            pass
    result = {"attrs": sorted(n for n in names if isinstance(n, str))}
else:
    top = os.path.realpath(root)
    excluded = tuple(os.path.join(top, d) + os.sep for d in (".venv", ".git", "node_modules"))

    def in_tree(path):
        path = os.path.realpath(path)
        return path.startswith(top + os.sep) and not path.startswith(excluded)

    classes = []
    for cls in all_classes():
        module = sys.modules.get(module_of(cls))
        path = getattr(module, "__file__", None)
        if isinstance(path, str) and in_tree(path):
            classes.append(cls)
    index = {id(cls): i for i, cls in enumerate(classes)}
    rows = []
    for cls in classes:
        row = {"module": cls.__module__, "qualname": cls.__qualname__, "name": cls.__name__}
        try:
            path = os.path.realpath(inspect.getsourcefile(cls))
            lnum = inspect.getsourcelines(cls)[1]
            if in_tree(path):
                row["file"], row["lnum"] = path, lnum
            else:
                row["error"] = "SourceOutsideTree"
        except Exception as e:
            row["error"] = type(e).__name__
        seen, stack = set(), list(subclasses(cls))
        while stack:
            sub = stack.pop()
            if id(sub) not in seen:
                seen.add(id(sub))
                stack.extend(subclasses(sub))
        row["subs"] = sorted(index[i] for i in seen if i in index)
        rows.append(row)
    result = {"skipped": skipped, "classes": rows}
out.write(json.dumps(result))
out.flush()
os._exit(0)
'''


def _run_child(python: str, mode: str, packages: list[str], root: str | None) -> dict:
    arg = json.dumps({"mode": mode, "packages": packages, "root": root})
    # An empty working folder: the interpreter puts it first on sys.path, and the imported code may write there.
    with tempfile.TemporaryDirectory(prefix="pykeys-") as cwd:
        proc = subprocess.run([python, "-B", "-c", _CHILD, arg], cwd=cwd, capture_output=True, text=True,
                              timeout=CHILD_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"{python} ({mode}) exited {proc.returncode}:\n{proc.stderr[-4000:]}")
    return json.loads(proc.stdout)


def library_attrs(python: str, modules: list[str]) -> set[str]:
    """Run `python`, import the modules and each module below their package folders, and return each attribute
    name of each class that is not of these modules (also the builtin types), and each attribute name of each
    other loaded module."""
    return set(_run_child(python, "attrs", modules, None)["attrs"])


def _class_tokens(text: str) -> dict[str, list[tuple[int, int]]]:
    """(line, col) of each class name token (the name after `class`) of a file, by name, in file order."""
    out = {}
    for word, line, col, in_, prev in _occurrences(text):
        if in_ == "code" and prev == "class":
            out.setdefault(word, []).append((line, col))
    return out


def _class_name_pos(tokens: dict, lnum: int, name: str) -> tuple[int, int] | None:
    """The first class name token `name` at line `lnum` or after it."""
    return next((pos for pos in tokens.get(name, []) if pos[0] >= lnum), None)


def _base_name(node) -> str | None:
    """The last identifier of a base expression: `plugins.BeetsPlugin` and `Generic[T]` give their class name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return None


class _ClassStatements(ast.NodeVisitor):
    """Each `class` statement of a file: (name, line of `class`, enclosing scope as (kind, name), base names)."""

    def __init__(self):
        self.found = []
        self.scope = []

    def _def(self, node):
        self.scope.append(("def", node.name))
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _def

    def visit_ClassDef(self, node):
        bases = {name for name in map(_base_name, node.bases) if name}
        self.found.append((node.name, node.lineno, list(self.scope), bases))
        self.scope.append(("class", node.name))
        self.generic_visit(node)
        self.scope.pop()


def _unseen_classes(root: str, seen: set[tuple[str, int, int]]) -> list[tuple[dict, set[str]]]:
    """A `dnc` implementer entry and the base names of each `class` statement of the tree whose name token is no
    position in `seen`: a class in a function, a class of a module that failed to import, a class of a file that
    no package holds. The id is `py:<module>.<enclosing defs and classes>.<Class>`."""
    out = []
    for path, rel in _py_files(root):
        text, tree = _parse(path, rel)
        visitor = _ClassStatements()
        visitor.visit(tree)
        if not visitor.found:
            continue
        tokens = _class_tokens(text)
        module = ".".join(_module_parts(rel))
        for name, lineno, scope, bases in visitor.found:
            line, col = _class_name_pos(tokens, lineno, name)
            if (rel, line, col) not in seen:
                rid = "py:" + ".".join(p for p in [module] + [n for _, n in scope] + [name] if p)
                out.append(({"id": rid, "file": rel, "line": line, "col": col, "class": "dnc"}, bases))
    return out


def hierarchy_keys(python: str, root: str, packages: list[str]) -> list[dict]:
    """The `_meta` record, then one record of kind `class` for each loaded class of the tree (see the module text)."""
    root = os.path.abspath(root)
    data = _run_child(python, "hierarchy", packages, root)
    top = os.path.realpath(root)
    scans, places, dynamic = {}, [], []
    for row in data["classes"]:
        place = None
        if "lnum" in row:
            rel = os.path.relpath(row["file"], top).replace(os.sep, "/")
            if rel not in scans:
                scans[rel] = _class_tokens(_read(row["file"]))
            pos = _class_name_pos(scans[rel], row["lnum"], row["name"])
            if pos is None:
                row["error"] = "NoClassNameToken"
            else:
                rid = "py:" + ".".join(p for p in (".".join(_module_parts(rel)), row["qualname"]) if p)
                place = {"id": rid, "file": rel, "line": pos[0], "col": pos[1]}
        if place is None:
            dynamic.append({"name": row["module"] + "." + row["qualname"], "error": row["error"]})
        places.append(place)
    records = {}
    for row, place in zip(data["classes"], places):
        if place is None:
            continue
        subs = [places[i] for i in row["subs"] if places[i] is not None]
        rec = records.get(place["id"])
        if rec is None:
            qualname = row["qualname"]
            rec = records[place["id"]] = {
                "id": place["id"], "lang": "python", "kind": "class", "name": row["name"],
                "container": qualname.rsplit(".", 1)[0] if "." in qualname else "",
                "decl": {"file": place["file"], "line": place["line"], "col": place["col"]},
                "family": [place["id"]], "sites": [], "implementers": [], "external": [], "source": "reflection"}
        for sub in subs:
            entry = {**sub, "class": "required"}
            if sub["id"] != place["id"] and entry not in rec["implementers"]:
                rec["implementers"].append(entry)
    # A class statement that reflection did not see is a dnc implementer of each record with the name of one of
    # its bases, and of each record with an implementer of that name; repeat for chains of unseen classes.
    unseen = _unseen_classes(root, {(r["decl"]["file"], r["decl"]["line"], r["decl"]["col"]) for r in records.values()})
    names = {rid: {i["id"].rsplit(".", 1)[-1] for i in rec["implementers"]} for rid, rec in records.items()}
    added = True
    while added:
        added = False
        for entry, bases in unseen:
            for rid, rec in records.items():
                if (rec["name"] in bases or names[rid] & bases) and entry not in rec["implementers"]:
                    rec["implementers"].append(entry)
                    names[rid].add(entry["id"].rsplit(".", 1)[-1])
                    added = True
    for rec in records.values():
        rec["implementers"].sort(key=lambda s: (s["file"], s["line"], s["col"], s["id"]))
    meta = {"id": "_meta", "skipped": sorted(data["skipped"], key=lambda s: s["module"]),
            "dynamic": sorted(dynamic, key=lambda d: d["name"]), "unseen": len(unseen)}
    return [meta] + [records[rid] for rid in sorted(records)]


def required_lines(record: dict) -> int:
    """The count of the source lines of the record that score as required."""
    return sum(1 for cls in keys.line_classes(record).values() if cls.startswith("required"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m benchlib.pykeys")
    commands = parser.add_subparsers(dest="command", required=True)
    unique = commands.add_parser("unique", help="unique-name keys from a token scan")
    hierarchy = commands.add_parser("hierarchy", help="class keys from reflection")
    for sub, listed in ((unique, "-modules"), (hierarchy, "-packages")):
        sub.add_argument("-root", required=True, help="tree root")
        sub.add_argument("-python", required=True, help="interpreter of the product")
        sub.add_argument(listed, required=True, help="comma-separated module names")
        sub.add_argument("-out", required=True, help="JSONL key file")
    unique.add_argument("-min-required", type=int, default=0,
                        help="keep only the records with at least this count of required lines")
    args = parser.parse_args(argv)
    start = time.monotonic()
    if args.command == "unique":
        attrs = library_attrs(args.python, args.modules.split(","))
        records = unique_name_keys(args.root, attrs)
        total = len(records)
        records = [r for r in records if required_lines(r) >= args.min_required]
        print(f"unique: {len(records)} records ({total} before -min-required {args.min_required}), "
              f"{len(attrs)} library attribute names, {time.monotonic() - start:.1f} s")
    else:
        records = hierarchy_keys(args.python, args.root, args.packages.split(","))
        meta = records[0]
        print(f"hierarchy: {len(records) - 1} records, {len(meta['skipped'])} skipped modules, "
              f"{len(meta['dynamic'])} dynamic classes, {meta['unseen']} unseen class statements, "
              f"{time.monotonic() - start:.1f} s")
    keys.save_keys(args.out, records)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
