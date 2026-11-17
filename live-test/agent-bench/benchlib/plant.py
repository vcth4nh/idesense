"""Shared-name plant: methods with unique names get ONE new name, and the key comes from the state before the change.

    python3 -m benchlib.plant make -lang go|python -src <tree> -dst <new tree> -names <a,b,c> -shared <name>
        -out <keys.jsonl> [-product caddy|beets] <language options>
    python3 -m benchlib.plant candidates -lang go|python -tree <tree> [-min-sites <n>] <language options>

    language options:  go:     -keys <compiler key of the tree> [-gokeys <binary>]
                       python: -modules <a,b> [-python <interpreter>]

(run from live-test/agent-bench). A tree has its manifest `<tree>.manifest` next to it (benchlib.trees).

A unique-name method:
- python: a record of kind `method` of `pykeys.unique_name_keys(tree, pykeys.library_attrs(python, modules))`.
- go: the one record of kind `method` with the name in the compiler key of the tree (`gokeys extract`). Its family
  is only itself, its `external` list is empty, and it has no `forbidden` site and no site with `why` `string` or
  `unproven`.
- both: each occurrence of the name that the scanner of the language finds (`pykeys.ident_sites`, `gokeys idents`)
  is in code or in a comment and in a file of the manifest. Each code occurrence is a site of the record.

`make` refuses: an existing target folder or target manifest; a name that is not a unique-name method; two
methods of one class or type; (python) two classes where one class is the other, a base of the other, or a base of
one class together with the other (by the base names of the `class` statements); a shared name that occurs in the
tree (code, comment or string), that is not an identifier or is a keyword, or (python) that is a library attribute
name; (python) a name with two leading underscores (name mangling); (go) names with a mix of export states, or a
shared name with another export state. A refusal comes before the copy.

Then `make` copies the files of the manifest of the source tree, renames each code and comment occurrence of each
name to the shared name, scans the planted tree again (each occurrence of the shared name is a renamed position,
and no original name is left), writes `<dst>.manifest`, makes the repository with one commit, runs the preparation
of `-product` (benchlib.trees), and writes one key record for each original method:

    {"id": "plant:<lang>:<dst folder name>:<Container>.<original>", "lang", "kind": "method", "name": <shared>,
     "container", "decl", "family": [<id>], "sites", "implementers": [], "external": [], "source": "plant",
     "original": <original name>}

Sites, at their positions in the planted tree: each code occurrence that was a required site of this method is
`required` / `use` (no `rel`: it counts as `self`); each code occurrence that was a required site of another planted
method is `forbidden` / `decoy`; each other occurrence is `dnc` with the `why` of its source site (`decl`, `import`,
`generated`) or `comment`. A Go site keeps the `configs` of its source site. `col` is 1-based in UTF-16 code units.

Limit: for Go, `make` does not look at embedded fields or library interfaces. The proof (`gokeys extract` on the
planted tree) checks them.
"""
import argparse
import ast
import io
import json
import keyword
import os
import re
import subprocess
import sys
import time
import tokenize

from benchlib import keys, pykeys, trees

GOKEYS = os.path.join(trees.BENCH, "scratch", "gokeys-bin")
GO_KEYWORDS = frozenset(
    "break case chan const continue default defer else fallthrough for func go goto if import interface map "
    "package range return select struct switch type var".split())
_GO_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_WORD_CHAR = re.compile(r"\w")


class PlantError(Exception):
    pass


def _manifest_files(tree: str) -> list[str]:
    path = os.path.normpath(tree) + ".manifest"
    if not os.path.isfile(path):
        raise PlantError(f"no manifest {path}")
    with open(path, encoding="utf-8", errors="surrogateescape", newline="\n") as f:
        return [line.rstrip("\n").split("  ", 1)[1] for line in f if line.strip()]


def _scan(lang: str, tree: str, name: str, gokeys: str) -> list[dict]:
    """Each occurrence of the identifier: {"file", "line", "col", "in": "code"|"comment"|"string", ...}."""
    if lang == "python":
        return pykeys.ident_sites(tree, name)
    proc = subprocess.run([gokeys, "idents", "-tree", tree, "-name", name], capture_output=True, text=True)
    if proc.returncode != 0:
        raise PlantError(f"gokeys idents {name}: exit {proc.returncode}: {proc.stderr.strip()}")
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def is_test_path(rel: str) -> bool:
    """A test file: `*_test.go`, `test_*.py`, `*_test.py`, `conftest.py`, or a file below a folder with `test` in
    its name (`test`, `testdata`, `caddytest`, `beets/test`)."""
    parts = rel.split("/")
    base = parts[-1]
    return (base.endswith(("_test.go", "_test.py")) or base.startswith("test_") or base == "conftest.py"
            or any("test" in part for part in parts[:-1]))


def go_problem(rec: dict) -> str | None:
    """None when the compiler record is a unique-name method (see the module text), else the reason."""
    if rec["kind"] != "method":
        return f"kind {rec['kind']}"
    if rec["family"] != [rec["id"]]:
        return f"a family of {len(rec['family'])}"
    if rec["external"]:
        return "external " + ", ".join(rec["external"])
    for s in rec["sites"]:
        if s["class"] == "forbidden":
            return f"a forbidden site (another object with the name) at {s['file']}:{s['line']}:{s['col']}"
        if s["why"] in ("string", "unproven"):
            return f"a site with why {s['why']} at {s['file']}:{s['line']}:{s['col']}"
    return None


def _occurrence_problem(rec: dict, occ: list[dict], files: set[str]) -> str | None:
    sites = {(s["file"], s["line"], s["col"]) for s in rec["sites"]}
    for o in occ:
        where = f"{o['file']}:{o['line']}:{o['col']}"
        if o["in"] not in ("code", "comment"):
            return f"an occurrence in a {o['in']} at {where}"
        if o["file"] not in files:
            return f"an occurrence at {where}, in a file that is not in the manifest"
        if o["in"] == "code" and (o["file"], o["line"], o["col"]) not in sites:
            return f"a code occurrence at {where} that is no site of the record"
    return None


def _source_records(lang: str, tree: str, names: list[str], attrs, keys_path) -> dict[str, dict]:
    """The unique-name method record of each name in the source tree (the rules without the scanner check)."""
    out = {}
    if lang == "python":
        unique = {r["name"]: r for r in pykeys.unique_name_keys(tree, set(attrs))}
        for name in names:
            rec = unique.get(name)
            if rec is None:
                raise PlantError(f"{name}: not a unique name by the rules of pykeys.unique_name_keys")
            if rec["kind"] != "method":
                raise PlantError(f"{name}: a {rec['kind']}, not a method")
            out[name] = rec
        return out
    if not keys_path:
        raise PlantError("go needs the compiler key of the source tree (-keys)")
    found = {name: [] for name in names}
    for rec in keys.load_keys(keys_path):
        if rec["kind"] == "method" and rec["name"] in found:
            found[rec["name"]].append(rec)
    for name, recs in found.items():
        if len(recs) != 1:
            raise PlantError(f"{name}: {len(recs)} method records with this name in {keys_path}")
        problem = go_problem(recs[0])
        if problem:
            raise PlantError(f"{name}: not a unique-name method: {problem}")
        out[name] = recs[0]
    return out


def _check_names(lang: str, names: list[str], shared: str) -> None:
    if len(names) < 2:
        raise PlantError("give two names or more")
    if len(set(names)) != len(names) or shared in names:
        raise PlantError("each name and the shared name must be different")
    if lang == "python":
        for n in names + [shared]:
            if n.startswith("__"):
                raise PlantError(f"{n}: two leading underscores (name mangling)")
        if not shared.isidentifier() or keyword.iskeyword(shared):
            raise PlantError(f"{shared}: not a Python identifier, or a keyword")
        return
    if not _GO_IDENT.match(shared) or shared in GO_KEYWORDS:
        raise PlantError(f"{shared}: not a Go identifier, or a keyword")
    exported = {n[0].isupper() for n in names}
    if len(exported) != 1:
        raise PlantError("the names have a mix of export states (exported and unexported)")
    if shared[0].isupper() not in exported:
        raise PlantError(f"{shared}: another export state than the names")


def _base_name(node) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return None


def _related_classes(tree: str, files: list[str], containers: set[str]) -> str | None:
    """A class that is (or has as a base, by name, transitively) two of the containers, else None."""
    bases = {}
    for rel in files:
        if rel.endswith(".py"):
            with tokenize.open(os.path.join(tree, rel)) as f:
                text = f.read()
            for node in ast.walk(ast.parse(text, filename=rel)):
                if isinstance(node, ast.ClassDef):
                    bases.setdefault(node.name, set()).update(b for b in map(_base_name, node.bases) if b)
    for name in sorted(set(bases) | containers):
        seen, todo = {name}, [name]
        while todo:
            for base in bases.get(todo.pop(), ()):
                if base not in seen:
                    seen.add(base)
                    todo.append(base)
        both = sorted(seen & containers)
        if len(both) > 1:
            return f"class {name} is or has as a base the planted classes {', '.join(both)}"
    return None


def _u16(text: str) -> int:
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def _index(line: str, col: int) -> int:
    """The str index of the 1-based UTF-16 column `col` of `line`."""
    if line.isascii():
        return col - 1
    units = 0
    for i, ch in enumerate(line):
        if units == col - 1:
            return i
        units += 2 if ord(ch) > 0xFFFF else 1
    return len(line) if units == col - 1 else -1


def _is_word_char(text: str, i: int) -> bool:
    return 0 <= i < len(text) and bool(_WORD_CHAR.match(text[i]))


def _rename(lang: str, root: str, renames: dict[str, list[tuple[int, int, str]]], shared: str) -> dict:
    """Replace each (line, col, original) of each file below root with the shared name. Return the new position
    (line, col) of each old position (file, line, col)."""
    moved = {}
    for rel, items in sorted(renames.items()):
        path = os.path.join(root, rel)
        if os.path.islink(path):
            raise PlantError(f"{rel}: a symbolic link")
        with open(path, "rb") as f:
            data = f.read()
        enc = tokenize.detect_encoding(io.BytesIO(data).readline)[0] if lang == "python" else "utf-8"
        text = data.decode(enc, "surrogateescape")
        if text.encode(enc, "surrogateescape") != data:
            raise PlantError(f"{rel}: the text does not decode and encode to the same bytes ({enc})")
        lines = text.split("\n")
        by_line = {}
        for line, col, orig in items:
            by_line.setdefault(line, []).append((col, orig))
        for line, occ in by_line.items():
            old = lines[line - 1]
            parts, last, shift = [], 0, 0
            for col, orig in sorted(occ):
                i = _index(old, col)
                if i < last or old[i:i + len(orig)] != orig or _is_word_char(old, i - 1) \
                        or _is_word_char(old, i + len(orig)):
                    raise PlantError(f"{rel}:{line}:{col}: the word {orig} is not at this position")
                parts += [old[last:i], shared]
                last = i + len(orig)
                moved[(rel, line, col)] = (line, col + shift)
                shift += _u16(shared) - _u16(orig)
            lines[line - 1] = "".join(parts) + old[last:]
        with open(path, "wb") as f:
            f.write("\n".join(lines).encode(enc, "surrogateescape"))
    return moved


def _site(rel: str, pos: tuple[int, int], cls: str, why: str, source: dict | None) -> dict:
    out = {"file": rel, "line": pos[0], "col": pos[1], "class": cls, "why": why}
    if source is not None and "configs" in source:
        out["configs"] = source["configs"]
    return out


def _records(lang: str, tree_name: str, names: list[str], recs: dict, occs: dict, moved: dict,
             shared: str) -> list[dict]:
    out = []
    for name in names:
        rec = recs[name]
        rid = f"plant:{lang}:{tree_name}:{rec['container']}.{name}"
        sites = []
        for other in names:
            source = {(s["file"], s["line"], s["col"]): s for s in recs[other]["sites"]}
            for o in occs[other]:
                old = (o["file"], o["line"], o["col"])
                s = source.get(old)
                if s is not None and s["class"] == "required":
                    cls, why = ("required", "use") if other == name else ("forbidden", "decoy")
                else:
                    cls, why = "dnc", s["why"] if s is not None else "comment"
                sites.append(_site(o["file"], moved[old], cls, why, s))
        sites.sort(key=lambda s: (s["file"], s["line"], s["col"]))
        d = rec["decl"]
        line, col = moved[(d["file"], d["line"], d["col"])]
        out.append({"id": rid, "lang": lang, "kind": "method", "name": shared, "container": rec["container"],
                    "decl": {"file": d["file"], "line": line, "col": col}, "family": [rid], "sites": sites,
                    "implementers": [], "external": [], "source": "plant", "original": name})
    return out


def _inside(path: str, folder: str) -> bool:
    return os.path.commonpath([path, folder]) == folder


def make(lang: str, src: str, dst: str, names: list[str], shared: str, out: str, *, product: str | None = None,
         attrs=frozenset(), keys_path: str | None = None, gokeys: str = GOKEYS) -> list[dict]:
    """Plant the shared name in a copy of src (see the module text); write and return the key records."""
    src, dst, out = os.path.abspath(src), os.path.abspath(dst), os.path.abspath(out)
    if os.path.lexists(dst) or os.path.lexists(dst + ".manifest"):
        raise PlantError(f"{dst} or {dst}.manifest exists")
    if _inside(dst, src) or _inside(out, src) or _inside(out, dst):
        raise PlantError("the target folder and the key file must be outside the source tree, the key file "
                         "also outside the target folder")
    if product is not None and product not in trees.PRODUCTS:
        raise PlantError(f"unknown product {product}")
    files = _manifest_files(src)
    _check_names(lang, names, shared)
    if lang == "python" and shared in attrs:
        raise PlantError(f"{shared}: an attribute name of a library class or module")
    there = _scan(lang, src, shared, gokeys)
    if there:
        o = there[0]
        raise PlantError(f"{shared} occurs {len(there)} times in the source tree, first at "
                         f"{o['file']}:{o['line']}:{o['col']} ({o['in']})")
    recs = _source_records(lang, src, names, attrs, keys_path)
    occs, file_set = {}, set(files)
    for name in names:
        occs[name] = _scan(lang, src, name, gokeys)
        problem = _occurrence_problem(recs[name], occs[name], file_set)
        if problem:
            raise PlantError(f"{name}: {problem}")
    owners = {}
    for name in names:
        owners.setdefault(recs[name]["id"].rsplit(".", 1)[0], []).append(name)
    for owner, members in owners.items():
        if len(members) > 1:
            raise PlantError(f"{', '.join(members)}: two methods of one class or type ({owner})")
    if lang == "python":
        problem = _related_classes(src, files, {recs[n]["container"].rsplit(".", 1)[-1] for n in names})
        if problem:
            raise PlantError(problem)

    trees.copy_tree(src, dst, files)
    renames = {}
    for name in names:
        for o in occs[name]:
            renames.setdefault(o["file"], []).append((o["line"], o["col"], name))
    moved = _rename(lang, dst, renames, shared)
    expected = {(o["file"], *moved[(o["file"], o["line"], o["col"])], o["in"]) for n in names for o in occs[n]}
    found = {(o["file"], o["line"], o["col"], o["in"]) for o in _scan(lang, dst, shared, gokeys)}
    if found != expected:
        raise PlantError(f"the planted tree differs from the plan: {len(found - expected)} occurrences of {shared} "
                         f"too many, {len(expected - found)} absent")
    for name in names:
        if _scan(lang, dst, name, gokeys):
            raise PlantError(f"{name} is still in the planted tree")
    trees.write_manifest(dst, files, dst + ".manifest")
    trees.commit_and_prepare(dst, files, product)
    records = sorted(_records(lang, os.path.basename(dst), names, recs, occs, moved, shared), key=lambda r: r["id"])
    keys.save_keys(out, records)
    return records


def candidates(lang: str, tree: str, min_sites: int = 0, *, attrs=frozenset(), keys_path: str | None = None,
               gokeys: str = GOKEYS) -> list[dict]:
    """Each unique-name method of the tree with min_sites required lines or more, most lines first."""
    tree = os.path.abspath(tree)
    files = set(_manifest_files(tree))
    if lang == "python":
        recs = [r for r in pykeys.unique_name_keys(tree, set(attrs)) if r["kind"] == "method"]
    else:
        if not keys_path:
            raise PlantError("go needs the compiler key of the tree (-keys)")
        recs = [r for r in keys.load_keys(keys_path) if go_problem(r) is None]
    out = []
    for rec in recs:
        n = pykeys.required_lines(rec)
        if n < min_sites or _occurrence_problem(rec, _scan(lang, tree, rec["name"], gokeys), files):
            continue
        out.append({"id": rec["id"], "name": rec["name"], "container": rec["container"], "required_lines": n,
                    "test_decl": is_test_path(rec["decl"]["file"])})
    out.sort(key=lambda c: (-c["required_lines"], c["id"]))
    return out


def _language_options(args, tree: str) -> dict:
    if args.lang == "go":
        return {"keys_path": args.keys, "gokeys": args.gokeys}
    if not args.modules:
        raise PlantError("python needs -modules (the modules of the tree for library_attrs)")
    python = args.python or os.path.join(tree, ".venv", "bin", "python")
    return {"attrs": pykeys.library_attrs(python, args.modules.split(","))}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m benchlib.plant")
    commands = parser.add_subparsers(dest="command", required=True)
    mk = commands.add_parser("make", help="plant a shared name in a copy of a tree")
    cand = commands.add_parser("candidates", help="list the unique-name methods of a tree")
    for sub in (mk, cand):
        sub.add_argument("-lang", required=True, choices=("go", "python"))
        sub.add_argument("-keys", help="go: the compiler key of the (source) tree, from gokeys extract")
        sub.add_argument("-gokeys", default=GOKEYS, help="go: the gokeys binary")
        sub.add_argument("-python", help="python: the interpreter of the product (default <tree>/.venv/bin/python)")
        sub.add_argument("-modules", help="python: comma-separated modules of the tree, for library_attrs")
    mk.add_argument("-src", required=True, help="source tree (with <src>.manifest)")
    mk.add_argument("-dst", required=True, help="new tree; must not exist")
    mk.add_argument("-names", required=True, help="comma-separated unique method names")
    mk.add_argument("-shared", required=True, help="the shared new name")
    mk.add_argument("-out", required=True, help="JSONL key file of the planted tree")
    mk.add_argument("-product", choices=sorted(trees.PRODUCTS), help="run the preparation of this product")
    cand.add_argument("-tree", required=True)
    cand.add_argument("-min-sites", type=int, default=0, help="the least count of required lines")
    args = parser.parse_args(argv)
    start = time.monotonic()
    try:
        if args.command == "make":
            opts = _language_options(args, args.src)
            records = make(args.lang, args.src, args.dst, args.names.split(","), args.shared, args.out,
                           product=args.product, **opts)
            for rec in records:
                lines = keys.line_classes(rec)
                print(f"{rec['id']}: {sum(1 for c in lines.values() if c.startswith('required'))} required lines, "
                      f"{sum(1 for c in lines.values() if c == 'forbidden')} forbidden lines")
            print(f"plant: {args.dst} ready, {len(records)} records in {args.out}, {time.monotonic() - start:.1f} s")
        else:
            opts = _language_options(args, args.tree)
            for c in candidates(args.lang, args.tree, args.min_sites, **opts):
                print(json.dumps(c))
    except PlantError as e:
        print(f"plant: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
