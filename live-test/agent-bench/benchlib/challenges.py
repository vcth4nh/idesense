"""Challenges: one closed list question about one symbol of a pinned tree, its prompt, and the score of an answer.

    python3 -m benchlib.challenges show -set <file> [-root <trees root>] [-slots]   (run from live-test/agent-bench)
    python3 -m benchlib.challenges pilot -out <file> [-seed 1]

A challenge set is a JSONL file with one challenge record for each line:

    {"id": "caddy-refs-CA", "product": "caddy", "tree": "caddy", "family": "refs",
     "keys": "caddy/symbols.jsonl", "key_id": "go:github.com/caddyserver/caddy/v2/modules/caddytls.CA",
     "sample": "hard", "note": "interface `CA` of `caddytls`"}

- family: `refs` (the lines that use the symbol), `rename` (the lines that a rename changes), `impls` (the
  declaration lines of the implementers or subclasses).
- keys: the key file, relative to `BENCH/keys`; key_id: the id of the key record in it.
- sample: `hard`, `random` or `control`. note: how the record was chosen (not shown to the agent).

The score uses a view of the key record (`view`). The answer is the JSON object of `schema`, and
`parse_sites` reads it. Normalisation of an answer entry: white space at the two ends is removed; the form is
`path:line` or `path:line:column` (the column is dropped); an absolute path loses the prefix `root + "/"`;
the path is normalised (`posixpath.normpath`, so a leading `./` goes). Each other entry goes to the `invalid`
list: no line, a line range, a line below 1, a path outside the root (an absolute path not below the root, or
a relative path that leaves it), an entry that is not a string. `score_answer` takes an answer line out of the
score when its path is no file of the master manifest `TREES/<tree>.manifest`, and counts it in `outside`.

The prompt texts are those of the plan, amendment A3. The root of a prompt is a parameter: the runner gives the
slot path of the tree. For Go, the package name comes from the package clause of the declaration file in the
master tree `TREES/<tree>`.

`show` prints for each challenge the id, the line counts of the view, the text scan (`text_scan`, `-` for a Go
`impls` challenge) and the prompt. The prompt root is `<trees root>/<tree>`, or with `-slots` the slot path of
the tree. The text scan always reads the master tree. `pilot` writes the pilot set of 8 challenges (see
`pilot_set`).
"""
import argparse
import json
import os
import posixpath
import random
import re
import sys

from benchlib import keys
from benchlib.audit import IMPLEMENTER_CLASSES, REQUIRED, RELS, _rel

BENCH = "/home/ubuntu/dev/idesense-bench"
KEYS = os.path.join(BENCH, "keys")
TREES = os.path.join(BENCH, "trees")
AUDIT = os.path.join(BENCH, "audit")
FIELDS = ("id", "product", "tree", "family", "keys", "key_id", "sample", "note")
FAMILIES = ("refs", "rename", "impls")
SAMPLES = ("hard", "random", "control")
REFS_RELS = ("self", "super", "sub")
KIND_WORDS = {"func": "function", "function": "function", "type": "type", "interface": "interface",
              "class": "class"}

# The prompt texts (plan, amendment A3, with the fix round 2 sentences of RENAME and IMPLS_GO). `{build}` is BUILD
# for Go and empty for Python.
HEAD = "The repository at {root} is a checkout of the project {product}. Work only with this checkout."
TAIL = 'Answer with JSON only: {"sites": ["<path relative to the repository root>:<line number>", ...]}'
BUILD = " A file counts also when the build for this machine does not compile it."
REFS_METHOD = ("Find each line of this repository that calls or names the method `{name}` of {owner}, which is "
               "declared at {decl}. A line counts when it refers to this method, to a method that overrides or "
               "implements it, or to a method that it overrides or implements. Test code counts.{build} Do not list "
               "the declarations of these methods, import lines, comments or strings.")
REFS_GO_FUNC = ("Find each line of this repository that calls or names the function `{name}` of the package "
                "`{package}`, which is declared at {decl}. Test code counts.{build} Do not list the declaration of "
                "the function itself, import lines, comments or strings.")
REFS_GO_TYPE = ("Find each line of this repository that names the {kind_word} `{name}` of the package `{package}`, "
                "which is declared at {decl}. Test code counts.{build} Do not list the declaration of the "
                "{kind_word} itself, import lines, comments or strings.")
REFS_PY = ("Find each line of this repository that calls or names the {kind_word} `{name}`, which is declared at "
           "{decl}. Test code counts. Do not list the declaration of the {kind_word} itself, import lines, comments "
           "or strings.")
RENAME = ("The method `{name}` of {owner}, which is declared at {decl}, must get a new name. Find each line of this "
          "repository that must change, so that the repository builds and behaves as before in each build "
          "configuration (Linux, Windows, macOS), test code included. Other declarations that must get the new "
          "name with it count, and each line that calls or names one of them. Nothing keeps the old name: do not "
          "add a wrapper or an alias. Do not list comments or strings.")
IMPLS_GO = ("Find each type of this repository that implements the interface `{name}` of the package `{package}`, "
            "which is declared at {decl}. A type counts when the type or a pointer to it implements the interface. "
            "Test code counts. Answer with the line that holds the name of each type in its declaration.")
IMPLS_PY = ("Find each class of this repository that is a direct or indirect subclass of the class `{name}`, which "
            "is declared at {decl}. Test code counts. Answer with the line of each class statement.")
# (family, lang, kind) -> text. Another combination has no text.
TASKS = {("refs", "go", "method"): REFS_METHOD, ("refs", "go", "iface_method"): REFS_METHOD,
         ("refs", "python", "method"): REFS_METHOD, ("refs", "go", "func"): REFS_GO_FUNC,
         ("refs", "go", "type"): REFS_GO_TYPE, ("refs", "go", "interface"): REFS_GO_TYPE,
         ("refs", "python", "function"): REFS_PY, ("refs", "python", "class"): REFS_PY,
         ("rename", "go", "method"): RENAME, ("rename", "go", "iface_method"): RENAME,
         ("rename", "python", "method"): RENAME,
         ("impls", "go", "interface"): IMPLS_GO, ("impls", "python", "class"): IMPLS_PY}

SITE = re.compile(r"(.+?):([0-9]+)(?::[0-9]+)?")
# The package clause of a Go file: the first token after white space and comments (Go specification).
GO_PACKAGE = re.compile(r"﻿?(?:\s+|//[^\n]*|/\*.*?\*/)*package\s+(\w+)", re.S)


def load(path: str) -> list[dict]:
    """The challenge records of a set file. A line that is not a challenge record is a ValueError."""
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            ch = json.loads(line)
            if set(ch) != set(FIELDS) or ch["family"] not in FAMILIES or ch["sample"] not in SAMPLES:
                raise ValueError(f"{path}:{n}: not a challenge record")
            out.append(ch)
    return out


def record_of(ch: dict) -> dict:
    """The key record of the challenge, from `KEYS/<keys>`. KeyError when the file has no record with the id."""
    for rec in keys.load_keys(os.path.join(KEYS, ch["keys"])):
        if rec["id"] == ch["key_id"] and rec["id"] != "_meta":
            return rec
    raise KeyError(ch["key_id"])


def _refs_view(record: dict) -> dict:
    """A required site with `rel` `sibling` or `embedded` becomes `dnc`, and a forbidden site on a line that
    has such a site and no required site becomes `dnc` (the rule of `audit.usages_view`, with `sub` kept)."""
    sites, off_lines = [], set()
    for s in record["sites"]:
        if s["class"] == "required" and _rel(s) not in RELS:
            raise ValueError(f"{record['id']}: unknown rel {_rel(s)!r} at {s['file']}:{s['line']}")
        if s["class"] == "required" and _rel(s) not in REFS_RELS:
            sites.append(dict(s, **{"class": "dnc"}))
            off_lines.add((s["file"], s["line"]))
        else:
            sites.append(s)
    off_lines -= {(s["file"], s["line"]) for s in sites if s["class"] == "required"}
    sites = [dict(s, **{"class": "dnc"}) if s["class"] == "forbidden" and (s["file"], s["line"]) in off_lines
             else s for s in sites]
    return {**record, "sites": sites}


def _impls_view(record: dict) -> dict:
    """One site at the declaration of each implementer, with its class (`required` when the field is absent)."""
    sites = []
    for imp in record["implementers"]:
        cls = imp.get("class", "required")
        if cls not in IMPLEMENTER_CLASSES:
            raise ValueError(f"{record['id']}: unknown implementer class {cls!r} at {imp['file']}:{imp['line']}")
        sites.append({"file": imp["file"], "line": imp["line"], "col": imp["col"], "class": cls, "why": "decl"})
    return {**record, "sites": sites}


def view(ch: dict, record: dict) -> dict:
    """The copy of the key record that the score of the challenge uses. The record itself does not change."""
    if ch["family"] == "refs":
        return _refs_view(record)
    if ch["family"] == "rename":
        if record.get("external"):
            raise ValueError(f"{record['id']}: a rename key needs an empty `external`, it has "
                             f"{len(record['external'])} entries")
        return dict(record)
    if ch["family"] == "impls":
        return _impls_view(record)
    raise ValueError(f"{ch['id']}: unknown family {ch['family']!r}")


def go_package(path: str) -> str:
    """The name in the package clause of a Go file. ValueError when the file has no package clause."""
    with open(path, encoding="utf-8", errors="replace") as f:
        m = GO_PACKAGE.match(f.read())
    if not m:
        raise ValueError(f"{path}: no package clause")
    return m.group(1)


def prompt(ch: dict, record: dict, root: str) -> str:
    """The prompt of the challenge; `root` is the path of the tree in the container. For Go, the package is read
    from the declaration file in the master tree `TREES/<tree>`. ValueError for a family, a language and a kind
    with no text."""
    lang, kind, container = record["lang"], record["kind"], record["container"]
    task = TASKS.get((ch["family"], lang, kind))
    if task is None:
        raise ValueError(f"{record['id']}: no prompt text for the family {ch['family']!r}, the language {lang!r} "
                         f"and the kind {kind!r}")
    if lang == "go":
        package = go_package(os.path.join(TREES, ch["tree"], record["decl"]["file"]))
        owner = f"the {'interface' if kind == 'iface_method' else 'type'} `{package}.{container}`"
    else:
        package, owner = "", f"the class `{container}`"
    text = task.format(name=record["name"], owner=owner, package=package, kind_word=KIND_WORDS.get(kind, ""),
                       decl=f"{record['decl']['file']}:{record['decl']['line']}", build=BUILD if lang == "go" else "")
    return "\n\n".join([HEAD.format(root=root, product=ch["product"]), text, TAIL])


def schema(ch: dict) -> dict:
    """The JSON schema of the answer (the same for each family)."""
    return {"type": "object", "properties": {"sites": {"type": "array", "items": {"type": "string"}}},
            "required": ["sites"], "additionalProperties": False}


def _site(entry, prefix: str) -> tuple[str, int] | None:
    if not isinstance(entry, str):
        return None
    m = SITE.fullmatch(entry.strip())
    if not m or int(m.group(2)) < 1:
        return None
    path = m.group(1)
    if path.startswith("/"):
        if not path.startswith(prefix):
            return None
        path = path[len(prefix):]
    path = posixpath.normpath(path)
    if path in (".", "..") or path.startswith(("../", "/")):
        return None
    return path, int(m.group(2))


def parse_sites(obj, root: str) -> tuple[set[tuple[str, int]], list[str]]:
    """The answer lines `(path relative to the root, line)` of `obj["sites"]`, and the entries that cannot be read
    (a non-string entry as its JSON text). ValueError when `obj` is no object with a list `sites`."""
    if not isinstance(obj, dict) or not isinstance(obj.get("sites"), list):
        raise ValueError("the answer is no JSON object with a list `sites`")
    prefix = root.rstrip("/") + "/"
    sites, invalid = set(), []
    for entry in obj["sites"]:
        site = _site(entry, prefix)
        if site is None:
            invalid.append(entry if isinstance(entry, str) else json.dumps(entry))
        else:
            sites.add(site)
    return sites, invalid


def score_answer(ch: dict, record: dict, sites: set[tuple[str, int]], invalid: list[str]) -> dict:
    """`keys.score` against the view for the answer lines in a file of the manifest `TREES/<tree>.manifest`.
    `outside` counts the other answer lines (for example below `.venv/`, or in a file that the agent made); they
    are not in the score. `invalid` counts the entries that cannot be read, `listed` the scored answer lines."""
    files = set(_manifest_paths(os.path.join(TREES, ch["tree"] + ".manifest")))
    inside = {site for site in sites if site[0] in files}
    out = keys.score(inside, view(ch, record))
    out["invalid"] = len(invalid)
    out["outside"] = len(sites) - len(inside)
    out["listed"] = len(inside)
    return out


def _manifest_paths(path: str) -> list[str]:
    """The paths of a tree manifest (format: `benchlib.trees.write_manifest`)."""
    with open(path, encoding="utf-8", errors="surrogateescape", newline="\n") as f:
        return [line.rstrip("\n").split("  ", 1)[1] for line in f if line.strip()]


def text_scan(ch: dict, record: dict, tree_root: str) -> dict:
    """A whole-word scan of the name over the files of the manifest `<tree_root>.manifest`, scored against the
    view: `lines` is the count of the lines that the scan finds; a `dnc` line counts in no ratio. A symbolic link
    and a file with a NUL byte are not scanned. Lines are counted at `\\n`."""
    word = re.compile(r"(?<!\w)" + re.escape(record["name"]) + r"(?!\w)")
    found = set()
    for rel in _manifest_paths(tree_root + ".manifest"):
        path = os.path.join(tree_root, rel)
        if os.path.islink(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        if b"\0" in data:
            continue
        for n, line in enumerate(data.decode("utf-8", "replace").split("\n"), 1):
            if word.search(line):
                found.add((rel, n))
    s = keys.score(found, view(ch, record))
    return {"lines": len(found), "precision": s["precision"], "recall": s["recall"]}


def _challenge(cid: str, product: str, tree: str, family: str, keys_file: str, record: dict, sample: str,
               note: str) -> dict:
    return dict(zip(FIELDS, (cid, product, tree, family, keys_file, record["id"], sample, note)))


def _unique(records: list[dict], what: str, pred) -> dict:
    hits = [r for r in records if pred(r)]
    if len(hits) != 1:
        raise LookupError(f"{len(hits)} key records for {what}, expected 1")
    return hits[0]


def _in_go_package(record: dict, package: str) -> bool:
    """True when the id `go:<import path>.<container>.<name>` has `package` as the last part of the import path."""
    return record["id"].endswith("/" + package + "." + ".".join(p for p in (record["container"], record["name"]) if p))


def _required_lines(record: dict) -> int:
    """The count of the required lines of the refs view."""
    return sum(1 for cls in keys.line_classes(_refs_view(record)).values() if cls in REQUIRED)


def _seeded(candidates: list[dict], seed: int, what: str) -> tuple[dict, str]:
    if not candidates:
        raise LookupError(f"no key record for {what}")
    chosen = random.Random(seed).choice(sorted(candidates, key=lambda r: r["id"]))
    return chosen, f"seeded choice (seed {seed}) among {len(candidates)} {what}"


def pilot_set(seed: int, keys_root: str = KEYS, audit_root: str = AUDIT) -> list[dict]:
    """The 8 challenges of the pilot. A fixed record is found by its kind, name and container (and the Go
    package); LookupError when it is absent or not unique. A control is a seeded choice from the sorted
    candidates, so the set depends only on the seed and the key files, not on the order of the records."""
    def records(rel: str) -> list[dict]:
        return [r for r in keys.load_keys(os.path.join(keys_root, rel)) if r["id"] != "_meta"]

    caddy, caddy_plant = records("caddy/symbols.jsonl"), records("caddy-plant-2/plant.jsonl")
    beets, beets_hier = records("beets/unique-used.jsonl"), records("beets/hierarchy.jsonl")
    beets_plant = records("beets-plant-2/plant.jsonl")
    with open(os.path.join(audit_root, "beets-unique-all", "disagreements.jsonl"), encoding="utf-8") as f:
        disagree = {json.loads(line)["id"] for line in f if line.strip()}

    def fixed(records_: list[dict], what: str, kind: str, name: str | None, container: str,
              package: str | None = None) -> dict:
        """The one record with the kind, the name (None: each name), the container and the Go package."""
        return _unique(records_, what, lambda r: r["kind"] == kind and name in (None, r["name"])
                       and r["container"] == container and (package is None or _in_go_package(r, package)))

    provision_what, ca_what = "method `Provision` of `caddyhttp.App`", "interface `CA` of `caddytls`"
    fetch_what, plugin_what = "method `_fetch_va_genres` of `LastGenrePlugin`", "class `BeetsPlugin`"
    import_task_what = "the planted record of `ImportTask`"
    provision = fixed(caddy, provision_what, "method", "Provision", "App", "caddyhttp")
    ca = fixed(caddy, ca_what, "interface", "CA", "", "caddytls")
    fetch = fixed(beets, fetch_what, "method", "_fetch_va_genres", "LastGenrePlugin")
    plugin = fixed(beets_hier, plugin_what, "class", "BeetsPlugin", "")
    import_task = fixed(beets_plant, import_task_what, "method", None, "ImportTask")

    counts = {r["id"]: _required_lines(r) for r in caddy_plant}
    most = max(counts.values(), default=0)
    plant = _unique(caddy_plant, f"the planted record with the most required lines ({most})",
                    lambda r: counts[r["id"]] == most)

    impls_control, impls_note = _seeded(
        [r for r in caddy if r["kind"] == "interface"
         and sum(1 for i in r["implementers"] if i.get("class", "required") == "required") >= 10
         and not any(i.get("class") == "dnc" for i in r["implementers"])],
        seed, "interfaces with 10 or more required implementers and no dnc implementer")
    refs_control, refs_note = _seeded(
        [r for r in beets if r["kind"] == "method" and _required_lines(r) >= 3 and r["id"] not in disagree],
        seed, "methods with 3 or more required lines and no disagreement in audit/beets-unique-all")

    return [
        _challenge("caddy-rename-App.Provision", "caddy", "caddy", "rename", "caddy/symbols.jsonl", provision,
                   "hard", provision_what),
        _challenge("caddy-refs-CA", "caddy", "caddy", "refs", "caddy/symbols.jsonl", ca, "hard", ca_what),
        _challenge("caddy-plant2-refs", "caddy", "caddy-plant-2", "refs", "caddy-plant-2/plant.jsonl", plant,
                   "hard", f"the planted record with the most required lines ({most})"),
        _challenge("caddy-impls-control", "caddy", "caddy", "impls", "caddy/symbols.jsonl", impls_control,
                   "control", impls_note),
        _challenge("beets-refs-_fetch_va_genres", "beets", "beets", "refs", "beets/unique-used.jsonl", fetch,
                   "hard", fetch_what),
        _challenge("beets-impls-BeetsPlugin", "beets", "beets", "impls", "beets/hierarchy.jsonl", plugin, "hard",
                   plugin_what),
        _challenge("beets-plant2-refs", "beets", "beets-plant-2", "refs", "beets-plant-2/plant.jsonl", import_task,
                   "hard", import_task_what),
        _challenge("beets-refs-control", "beets", "beets", "refs", "beets/unique-used.jsonl", refs_control,
                   "control", refs_note),
    ]


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _slot_roots() -> dict[str, str]:
    """The slot path of each tree (plan, amendment A1): `trees.load_slots()`. While `benchlib.trees` has no
    `load_slots` (Task 3a), the file `TREES/slots.json` of the same form."""
    from benchlib import trees
    if hasattr(trees, "load_slots"):
        slots = trees.load_slots()
    else:
        with open(os.path.join(TREES, "slots.json"), encoding="utf-8") as f:
            slots = json.load(f)
    return {tree: entry["path"] for tree, entry in slots.items()}


def _show(args) -> int:
    slots = _slot_roots() if args.slots else {}
    for ch in load(args.set):
        record = record_of(ch)
        counts = {"required": 0, "forbidden": 0, "dnc": 0}
        for cls in keys.line_classes(view(ch, record)).values():
            counts["required" if cls in REQUIRED else cls] += 1
        tree = os.path.join(args.root, ch["tree"])
        if ch["family"] == "impls" and record["lang"] == "go":
            # The declaration line of a Go type does not name the interface: the scan measures nothing here.
            numbers = "lines -, precision -, recall -"
        else:
            scan = text_scan(ch, record, tree)
            numbers = (f"lines {scan['lines']}, precision {_number(scan['precision'])}, "
                       f"recall {_number(scan['recall'])}")
        print(f"== {ch['id']}  ({ch['family']}, {ch['sample']}, tree {ch['tree']}, key {ch['key_id']})")
        print(f"view lines: required {counts['required']}, forbidden {counts['forbidden']}, dnc {counts['dnc']}")
        print(f"text scan: {numbers}")
        print("--- prompt")
        print(prompt(ch, record, slots[ch["tree"]] if args.slots else tree))
        print()
    return 0


def _pilot(args) -> int:
    chosen = pilot_set(args.seed)
    keys.save_keys(args.out, chosen)
    print(f"{len(chosen)} challenges in {args.out}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m benchlib.challenges", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show", help="print the view counts, the text scan and the prompt of each challenge")
    show.add_argument("-set", required=True, help="challenge set (JSONL)")
    show.add_argument("-root", default=TREES, help="the folder of the master trees for the text scan, and of the "
                                                   "prompt root with no -slots (default: %(default)s)")
    show.add_argument("-slots", action="store_true", help="the prompt root of a tree is its slot path")
    pilot = sub.add_parser("pilot", help="write the pilot set")
    pilot.add_argument("-out", required=True, help="output file (JSONL)")
    pilot.add_argument("-seed", type=int, default=1)
    args = parser.parse_args(argv)
    return _show(args) if args.command == "show" else _pilot(args)


if __name__ == "__main__":
    sys.exit(main())
