"""Challenges: one closed list question about one symbol of a pinned tree, its prompt, and the score of an answer.

    python3 -m benchlib.challenges show -set <file> [-root <trees root>] [-slots] [-keys <keys root>]
    python3 -m benchlib.challenges pilot -out <file> [-seed 1]
    python3 -m benchlib.challenges main -out <file> [-seed 1]   (run from live-test/agent-bench)

A challenge set is a JSONL file with one challenge record for each line:

    {"id": "caddy-refs-CA", "product": "caddy", "tree": "caddy", "family": "refs",
     "keys": "caddy/symbols.jsonl", "key_id": "go:github.com/caddyserver/caddy/v2/modules/caddytls.CA",
     "sample": "hard", "note": "interface `CA` of `caddytls`"}

- family: `refs` (the lines that use the symbol), `rename` (the lines that a rename changes), `impls` (the
  declaration lines of the implementers or subclasses).
- keys: the key file, relative to `BENCH/keys`; key_id: the id of the key record in it.
- sample: `hard`, `random` or `control`. note: how the record was chosen (not shown to the agent).

The score uses a view of the key record (`view`). In the rename view, a forbidden site on a line with an optional
use and no required site is `dnc`. The answer is the JSON object of `schema`, and
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
the tree. The text scan always reads the master tree. `-keys` sets the folder of the key files. `pilot` writes the
pilot set of 8 challenges (see `pilot_set`), `main` the main set of 30 challenges (see `main_set`).
"""
import argparse
import contextlib
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
# The main set: the id prefixes of test code, and the interface of the pilot that its `structure` rule skips.
TEST_IDS = ("py:test.", "py:beets.test.")
VALIDATOR = "go:github.com/caddyserver/caddy/v2.Validator"
GO_MEMBERS = ("method", "iface_method")  # the Go kinds with a `family` of methods (the overlap rule)
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


def record_of(ch: dict, keys_root: str | None = None) -> dict:
    """The key record of the challenge, from `<keys_root>/<keys>` (default: `KEYS`). KeyError when the file has
    no record with the id."""
    for rec in keys.load_keys(os.path.join(keys_root or KEYS, ch["keys"])):
        if rec["id"] == ch["key_id"] and rec["id"] != "_meta":
            return rec
    raise KeyError(ch["key_id"])


def _refs_view(record: dict) -> dict:
    """A required site with `rel` `sibling` or `embedded` becomes `dnc`, and a forbidden site on a line that
    has such a site and no required site becomes `dnc` (the rule of `audit.usages_view`, with `sub` kept). The
    view starts from `keys.structural_view`: an optional use counts as a use of the symbol."""
    record = keys.structural_view(record)
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


def _rename_view(record: dict) -> dict:
    """A forbidden site on a line that has an optional site and no required site becomes `dnc`: a rename can
    change that line, and need not (the idea of the `sibling` rule of `_refs_view`)."""
    optional = {(s["file"], s["line"]) for s in record["sites"] if s.get("optional")}
    optional -= {(s["file"], s["line"]) for s in record["sites"] if s["class"] == "required"}
    sites = [dict(s, **{"class": "dnc"}) if s["class"] == "forbidden" and (s["file"], s["line"]) in optional
             else s for s in record["sites"]]
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
        return _rename_view(record)
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


def _required_impls(record: dict) -> int:
    """The count of the implementers with class `required` (the default)."""
    return sum(1 for imp in record["implementers"] if imp.get("class", "required") == "required")


def _no_dnc_impl(record: dict) -> bool:
    return not any(imp.get("class") == "dnc" for imp in record["implementers"])


def _rename_lines(record: dict) -> int:
    """The count of the required lines of the record itself (the rename view has the same required lines)."""
    return sum(1 for cls in keys.line_classes(record).values() if cls in REQUIRED)


def _decoy_lines(record: dict) -> int:
    """The count of the forbidden lines of the refs view."""
    return sum(1 for cls in keys.line_classes(_refs_view(record)).values() if cls == "forbidden")


def _off_linux(record: dict) -> tuple[int, int]:
    """The off-Linux lines and the other required lines of the refs view. A required line is off Linux when no
    required site on it has `linux` in `configs`."""
    refs = _refs_view(record)
    required = {line for line, cls in keys.line_classes(refs).items() if cls in REQUIRED}
    linux = {(s["file"], s["line"]) for s in refs["sites"] if s["class"] == "required" and "linux" in s["configs"]}
    off = len(required - linux)
    return off, len(required) - off


def _overlap(family: str, record: dict, chosen_family: str, chosen: dict) -> bool:
    """True when a challenge of the record in `family` asks about the sites of a chosen challenge (fix round 1 of
    the task): two Go methods or interface methods where one is in the `family` of the other; two `impls`
    challenges where one record is an implementer of the other; a natural record with the container and the
    original name of a chosen planted record."""
    if (record["lang"] == chosen["lang"] == "go" and record["kind"] in GO_MEMBERS and chosen["kind"] in GO_MEMBERS
            and (record["id"] in chosen["family"] or chosen["id"] in record["family"])):
        return True
    if family == chosen_family == "impls" and (record["id"] in {imp["id"] for imp in chosen["implementers"]}
                                               or chosen["id"] in {imp["id"] for imp in record["implementers"]}):
        return True
    return (chosen["source"] == "plant" and record["source"] != "plant"
            and (record["container"], record["name"]) == (chosen["container"], chosen["original"]))


def main_set(seed: int, keys_root: str = KEYS, audit_root: str = AUDIT, trees_root: str = TREES) -> list[dict]:
    """The 30 challenges of the main run (plan of phase 3, task 3): for caddy and for beets 9 `hard` and 6
    `random` challenges. The rules run in the order of the plan, except that `caddy rename` runs right after
    `caddy structure`: so no earlier pick can exclude the fixed `App.Provision`. A record that an earlier pick
    chose is no candidate of a later pick, and neither is a record that overlaps an earlier pick of the same
    product (`_overlap`). A seeded pick is `_seeded` over the candidates; a pick of the most or the fewest takes
    the lowest id on a tie. So the set depends only on the seed and the files, not on the order of the records.
    The note starts with the class word of the rule (`random` for a random pick). LookupError with the rule name
    when a rule has too few candidates, or when the view of a chosen record has no required line."""
    def records(rel: str) -> list[dict]:
        return [r for r in keys.load_keys(os.path.join(keys_root, rel)) if r["id"] != "_meta"]

    def disagreeing(folder: str) -> set[str]:
        with open(os.path.join(audit_root, folder, "disagreements.jsonl"), encoding="utf-8") as f:
            return {json.loads(line)["id"] for line in f if line.strip()}

    out, picks, seen = [], [], {}  # picks: (product, family, record) of each challenge so far

    @contextlib.contextmanager
    def rule(name: str):
        try:
            yield
        except LookupError as e:
            raise LookupError(f"rule `{name}`: {e}") from None

    def free(product: str, family: str, candidates: list[dict]) -> list[dict]:
        """The candidates that are no earlier pick of the product and overlap none."""
        return [r for r in candidates if not any(p == product and (r["id"] == o["id"] or _overlap(family, r, f, o))
                                                 for p, f, o in picks)]

    # A chooser takes the free candidates and gives (record, note).
    def seeded(what: str):
        return lambda rest: _seeded(rest, seed, what)

    def extreme(what: str, measure, unit: str, most: bool = True):
        def choose(rest: list[dict]) -> tuple[dict, str]:
            if not rest:
                raise LookupError(f"no key record for {what}")
            best = min(rest, key=lambda r: (-measure(r) if most else measure(r), r["id"]))
            return best, f"the {'most' if most else 'fewest'} {unit} ({measure(best)}) among {len(rest)} {what}"
        return choose

    def fixed(what: str, note: str):
        def choose(rest: list[dict]) -> tuple[dict, str]:
            if not rest:
                raise LookupError(f"no key record for {what}")
            return rest[0], note
        return choose

    def add(product: str, word: str, family: str, keys_file: str, candidates: list[dict], choose,
            tree: str | None = None, plant: int | None = None) -> None:
        record, note = choose(free(product, family, candidates))
        name = ".".join(p for p in (record["container"], record["name"]) if p)
        cid = f"{product}-plant{plant}-refs-{record['container']}" if plant else f"{product}-{family}-{name}"
        seen[cid] = seen.get(cid, 0) + 1
        cid += f"-{seen[cid]}" if seen[cid] > 1 else ""
        ch = _challenge(cid, product, tree or product, family, keys_file, record,
                        "random" if word == "random" else "hard", f"{word}: {note}")
        if not any(cls in REQUIRED for cls in keys.line_classes(view(ch, record)).values()):
            raise LookupError(f"the {family} view of {record['id']} has no required line")
        picks.append((product, family, record))
        out.append(ch)

    caddy_keys = "caddy/symbols.jsonl"
    caddy = records(caddy_keys)
    caddy_lines = {r["id"]: _required_lines(r) for r in caddy}
    methods = {r["id"] for r in caddy if r["kind"] == "method"}
    names: dict[str, set[str]] = {}
    for r in caddy:
        if r["kind"] == "iface_method" and r["id"].endswith("." + r["name"]):
            names.setdefault(r["id"][:-len(r["name"]) - 1], set()).add(r["name"])

    def borrowed(iface: dict) -> int:
        """The required implementers with no method record `<implementer id>.<name>` for a method name."""
        return sum(1 for imp in iface["implementers"] if imp.get("class", "required") == "required"
                   and any(f"{imp['id']}.{n}" not in methods for n in names.get(iface["id"], ())))

    with rule("caddy structure"):
        what = ("interfaces (not `caddy.Validator`) with no dnc implementer and 3 or more required implementers "
                "with no method of their own")
        pool = [r for r in caddy if r["kind"] == "interface" and r["id"] != VALIDATOR and _no_dnc_impl(r)
                and borrowed(r) >= 3]
        for most in (False, False, True):
            add("caddy", "structure", "impls", caddy_keys, pool,
                extreme(what, _required_impls, "required implementers", most))
    # The rename rule comes before the decoys and build rules: a method that one of them chooses could have
    # `App.Provision` in its family. The structure rule chooses interfaces, which cannot exclude it.
    with rule("caddy rename"):
        what = "method `Provision` of `caddyhttp.App`"
        provision = _unique(caddy, what, lambda r: r["kind"] == "method" and r["name"] == "Provision"
                            and r["container"] == "App" and _in_go_package(r, "caddyhttp"))
        add("caddy", "rename", "rename", caddy_keys, [provision], fixed(what, f"the {what}, as in the pilot"))
        add("caddy", "rename", "rename", caddy_keys,
            [r for r in caddy if r["kind"] == "method" and not r["external"] and 5 <= len(r["family"]) <= 19
             and len(r.get("coupled", ())) >= 2 and _rename_lines(r) >= 10],
            seeded("methods with an empty `external`, a family of 5 to 19 members, a coupled family of 2 or more "
                   "members and 10 or more required lines"))
    with rule("caddy decoys"):
        pool = [r for r in caddy if not r["external"] and caddy_lines[r["id"]] >= 8 and _decoy_lines(r) >= 50]
        for kinds, what in ((("method",), "methods"), (("type", "interface"), "types and interfaces")):
            add("caddy", "decoys", "refs", caddy_keys, [r for r in pool if r["kind"] in kinds],
                seeded(f"{what} with an empty `external`, 8 or more required lines and 50 or more decoy lines"))
    with rule("caddy build"):
        off = {r["id"]: _off_linux(r) for r in caddy}
        add("caddy", "build", "refs", caddy_keys, [r for r in caddy if off[r["id"]][0]],
            extreme("records with an off-Linux line", lambda r: off[r["id"]][0], "off-Linux lines"))
        add("caddy", "build", "refs", caddy_keys, [r for r in caddy if off[r["id"]][0] >= 2 and off[r["id"]][1] >= 5],
            seeded("records with 2 or more off-Linux lines and 5 or more other required lines"))
    with rule("caddy random"):
        for kind, count in (("method", 2), ("func", 1), ("type", 1), ("iface_method", 1)):
            for _ in range(count):
                add("caddy", "random", "refs", caddy_keys,
                    [r for r in caddy if r["kind"] == kind and caddy_lines[r["id"]] >= 3],
                    seeded(f"`{kind}` records with 3 or more required lines"))
        add("caddy", "random", "impls", caddy_keys,
            [r for r in caddy if r["kind"] == "interface" and _required_impls(r) >= 3 and _no_dnc_impl(r)],
            seeded("interfaces with 3 or more required implementers and no dnc implementer"))

    hier_keys, used_keys = "beets/hierarchy.jsonl", "beets/unique-used.jsonl"
    hier, used = records(hier_keys), records(used_keys)
    used_lines = {r["id"]: _required_lines(r) for r in used}
    files: dict[str, list[str]] = {}

    def named(record: dict) -> int:
        """The required subclasses whose class statement line holds the class name as a whole word."""
        word = re.compile(r"(?<!\w)" + re.escape(record["name"]) + r"(?!\w)")
        count = 0
        for imp in record["implementers"]:
            if imp.get("class", "required") != "required":
                continue
            if imp["file"] not in files:
                with open(os.path.join(trees_root, "beets", imp["file"]), encoding="utf-8", errors="replace") as f:
                    files[imp["file"]] = f.read().split("\n")
            count += bool(word.search(files[imp["file"]][imp["line"] - 1]))
        return count

    with rule("beets structure"):
        pool = [r for r in hier if _required_impls(r) >= 10 and 4 * named(r) < _required_impls(r)]
        what = "classes with 10 or more required subclasses, fewer than 25 % of them with the name in the class line"
        for _ in range(2):
            add("beets", "structure", "impls", hier_keys, [r for r in pool if not r["id"].startswith(TEST_IDS)],
                seeded(f"{what}, outside test code"))
        add("beets", "structure", "impls", hier_keys,
            [r for r in pool if r["id"].startswith(TEST_IDS) and _required_impls(r) >= 50],
            seeded(f"{what}, in test code and with 50 or more required subclasses"))
    with rule("beets plant"):
        plants = {n: records(f"beets-plant-{n}/plant.jsonl") for n in (1, 2, 3)}
        for n, recs in plants.items():
            add("beets", "plant", "refs", f"beets-plant-{n}/plant.jsonl", recs,
                extreme(f"planted records of beets-plant-{n}", _required_lines, "required lines"), f"beets-plant-{n}",
                n)
        # The tree of the ide-gap pick is known only after the choice.
        audited = {n: disagreeing(f"beets-plant-{n}") for n in (2, 3)}
        gap = {r["id"]: n for n in (2, 3) for r in plants[n] if r["id"] in audited[n]}
        what = "planted records of beets-plant-2 and beets-plant-3 with a disagreement in the audit"
        record, note = extreme(what, _required_lines, "required lines")(
            free("beets", "refs", [r for n in (2, 3) for r in plants[n] if r["id"] in gap]))
        n = gap[record["id"]]
        add("beets", "ide-gap", "refs", f"beets-plant-{n}/plant.jsonl", [record], fixed(what, note),
            f"beets-plant-{n}", n)
    with rule("beets long"):
        add("beets", "long", "refs", used_keys, [r for r in used if not r["id"].startswith(TEST_IDS)],
            extreme(f"records of {used_keys} outside test code", lambda r: used_lines[r["id"]], "required lines"))
    with rule("beets ide-gap"):
        disagree = disagreeing("beets-unique-all")
        add("beets", "ide-gap", "refs", used_keys,
            [r for r in used if r["id"] in disagree and used_lines[r["id"]] >= 5],
            seeded(f"records of {used_keys} with a disagreement in audit/beets-unique-all and 5 or more required "
                   "lines"))
    with rule("beets random"):
        for kind, count in (("method", 3), ("function", 1)):
            for _ in range(count):
                add("beets", "random", "refs", used_keys,
                    [r for r in used if r["kind"] == kind and used_lines[r["id"]] >= 3],
                    seeded(f"`{kind}` records of {used_keys} with 3 or more required lines"))
        for _ in range(2):
            add("beets", "random", "impls", hier_keys,
                [r for r in hier if r["kind"] == "class" and _required_impls(r) >= 3],
                seeded("classes with 3 or more required subclasses"))
    return out


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
        record = record_of(ch, args.keys)
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


def _main(args) -> int:
    chosen = main_set(args.seed, KEYS, AUDIT, TREES)
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
    show.add_argument("-keys", default=KEYS, help="the folder of the key files (default: %(default)s)")
    pilot = sub.add_parser("pilot", help="write the pilot set")
    pilot.add_argument("-out", required=True, help="output file (JSONL)")
    pilot.add_argument("-seed", type=int, default=1)
    main_cmd = sub.add_parser("main", help="write the main set")
    main_cmd.add_argument("-out", required=True, help="output file (JSONL)")
    main_cmd.add_argument("-seed", type=int, default=1)
    args = parser.parse_args(argv)
    return {"show": _show, "pilot": _pilot, "main": _main}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
