"""The verdict of an audit: pass, fail or wait, from a tracked list of accepted disagreements.

    python3 -m audit.verdict check -name NAME (-symbols DIR -keys FILE | -callers FILE | -dyn FILE) [-accepted DIR]
    python3 -m audit.verdict propose -name NAME (-symbols DIR -keys FILE | -callers FILE | -dyn FILE) [-accepted DIR]
    python3 -m audit.verdict run -url-goland URL -url-pycharm URL -out <data root>/audit/<build> [-accepted DIR]

A disagreement line is one symbol and one tool for which the answer of the IDE differs from the key:

    {"audit": "caddy-symbols", "tool": "ide_find_usages", "symbol": "<key id>", "miss": [["f.go", 3]], "fp": [],
     "marked": [], "errors": []}

`miss`, `fp` and `marked` are `[file, line]` pairs, and `errors` the texts of the tool errors; each list is sorted
and always present. `marked` holds the answer lines that the audit counts as marked: a marked false line of a usages
result (`extra["marked_fp"]` of `results.jsonl`, the union over the repeats). The caller audits count no line as
marked, so their `marked` list is empty. An error result is a disagreement as a missed line is. The lines come from
the result of an audit:

- `from_symbols`: `results.jsonl` of `audit.symbols run`, through `symbols.disagreements` (one line for each
  record of `disagreements.jsonl`).
- `from_callers`: a file of `audit.callers callers`, the `mapped` comparison: one line for each row with an error
  or with a `mapped` score that is not exact. The tool is `ide_call_hierarchy`.
- `from_dyn`: a file of `audit.callers dyn`: `hierarchy` gives `ide_call_hierarchy`, `usages` gives
  `ide_find_usages`.

`from_callers` and `from_dyn` refuse a row (ValueError) when the length of its list `miss_sites` or `fp_sites`
differs from its count `miss` or `fp`: the audit left a line out of the list (a `forbidden` site, or two sites on
one line), and the line of the row would hide a change. The three readers refuse (ValueError) a result with a row
that is no JSON object with an `id`, a result whose `_meta` has a `version_start` that differs from its
`version_end` (the server version changed during the run), and a result with no record. `from_symbols` refuses
(NotReady, a ValueError) a result that holds an `index_not_ready` result: the IDE was in dumb mode during the audit.
`read_result` gives the found lines and the audited ids of a result: the result ids of `results.jsonl` for
`symbols`, the row ids for `callers` and `dyn`. It refuses (ValueError) a result that has not the form of its kind,
for example a `dyn` file given as a `callers` result.

The accepted list of a product is `<accepted>/<product>.jsonl` (default: the folder `accepted/` next to this file):
one disagreement line with a `cause` for each line, sorted by (`audit`, `tool`, `symbol`). The product of an audit
is the product of its tree (`caddy-plant-1` -> `caddy`). `cause` is the name of an entry of
`<accepted>/causes.json`, or null when nobody has named the cause yet:

    {"<name>": {"text": "...", "issue": <number or null>, "permitted": "<YYYY-MM-DD>" or null}}

`text` is a text with one or more characters. `issue` is the number of the issue (a whole number), or null;
`permitted` is the date on which the owner of the repository permitted the cause (`YYYY-MM-DD`, a real date), or
null. `read_causes` refuses (ValueError) a cause with no such field or with another value. `read_accepted` refuses
(ValueError) an accepted line with no text `audit`, `tool` or `symbol`, a `cause` that is no text and not null, or
a list of another form. A file that does not exist counts as an empty list.

`verdict(found, accepted, causes, audited)` compares the whole lines with no `cause` (the order in a list does not
count). `audited` is the set of the ids that the result audited; with None, each symbol of `found` and of
`accepted` counts as audited.
- `new`: a line of `found` that the accepted list does not hold (a changed line is new). Any new line: `fail`.
- `not_audited`: an accepted line whose `symbol` the result did not audit, for example a line of a record that a
  sample run did not pick. With no new line, such a line gives `wait`, never `pass`.
- `gone`: an accepted line of an audited symbol that `found` does not hold. A maintainer can remove it; it never
  changes the result.
- With no new line: an accepted line that stays and has no cause (`no_cause`), or a cause that `causes.json` does
  not hold or that has no permission (`no_permission`, the cause names): `wait`. Else `pass`.

`check` prints the verdict of one audit and exits 0 (pass), 1 (fail) or 3 (wait). The first line has the counts;
then one line for each `new`, `gone` and `not audited` line. `propose` writes the accepted list of the product: the
lines of the other audits stay, a line of this audit whose symbol the result did not audit stays as it is (with its
cause), and the other lines of this audit become the found lines. A line that stays keeps its cause; a new line
gets the cause null. Both print one line and exit 2 for an unknown name, an input of another kind, or an input that
they cannot read: also a result that `read_result` refuses, an accepted file that `read_accepted` refuses, and a
causes file that `read_causes` refuses (`propose` reads no causes file).

`audits.json` (next to this file) is the list of the audits of a full run. Each entry has the fields `name`,
`tree`, `kind` (`symbols`, `callers` or `dyn`), `keys` and `calls` (paths relative to `<data root>/keys/`; `calls`
is null for `symbols`), and the options `n`, `seed`, `repeats` and `ids` (null when the kind has no such option):
- `symbols`: `n`, `seed` and `repeats` of `audit.symbols run`;
- `callers`: the key ids `ids` (in their order), or a seeded sample of `n` records;
- `dyn`: the key ids `ids`, or with null each record with a caller that the run-time trace proves.

`run` holds the lock of the benchmark IDEs (exit 2 when another holder has it, with no call to the IDE), and runs
each audit of `audits.json` on the IDE of its product (GoLand for caddy, PyCharm for beets) at the slot path of
its tree. At its start, `run` prints the warnings of `live-test/manifest.json` (`common.manifest.warn`; a
difference never stops it). With the lock, before it makes the `-out` folder, it reads `serverInfo.version` of
each IDE. When an IDE that an audit of the list uses gives no version (for example no IDE listens at the URL), `run`
prints one line and exits 2 at once, with no `-out` folder. An IDE that no audit uses gets the version
`unknown (<error>)`. It writes one `<out>/manifest.json` before the first audit (`common.manifest.write`, with
`plugin`: {product: `serverInfo.version` of its IDE}, and `files`: {path below `<data root>/keys/`: SHA-256}). A
`symbols` audit writes the folder `<out>/<name>/`, another audit the file `<out>/<name>.jsonl`. Then `run` prints
the verdict of each audit and one total line, and writes `<out>/verdict.json`: `{"result": <total>, "audits":
[{"name", "verdict": {"result", "new", "gone", "not_audited", "no_cause", "no_permission"}}, ...]}`. A `symbols`
result that `from_symbols` refuses with NotReady gives that audit the result `wait` and the field `reason` (the text
of the refusal, with the count of the `index_not_ready` results), never `fail` or `pass`; its lists are empty. The
total is `fail` when an audit fails, else `wait` when an audit waits, else `pass`; the exit code is that of `check`
for the total. `run` refuses an `-out` folder that exists and an input that is absent (exit 2). When an audit stops
before its end (the IDE stays in dumb mode at the start, or the server version changes during an audit), `run`
exits 4 with no verdict. When `run` cannot read a result, the accepted list or the causes file (see `check`), it
prints one line and exits 2 with no verdict.
"""
import argparse
import datetime
import json
import os
import re
import sys

from audit import callers
from audit import symbols
from common import keyrecord as keys
from common import manifest, settings, trees
from common.lock import Busy, ide_lock
from common.mcp import McpClient, McpError

HERE = os.path.dirname(os.path.abspath(__file__))
AUDITS_FILE = os.path.join(HERE, "audits.json")
ACCEPTED = os.path.join(HERE, "accepted")
HIERARCHY = callers.HIERARCHY
USAGES = callers.USAGES
DYN_TOOLS = (("hierarchy", HIERARCHY), ("usages", USAGES))
LISTS = ("miss", "fp", "marked", "errors")
KINDS = ("symbols", "callers", "dyn")
FIELDS = ("name", "tree", "kind", "keys", "calls", "n", "seed", "repeats", "ids")
OPTIONS = {"symbols": ("n", "seed", "repeats"), "callers": ("n", "seed"), "dyn": ()}
URL_OPTIONS = {"caddy": "url_goland", "beets": "url_pycharm"}
EXIT = {"pass": 0, "fail": 1, "wait": 3}
EXIT_INPUT = 2
EXIT_BUSY = 2
EXIT_STOPPED = 4


def _pair(entry) -> list:
    return [entry["file"], entry["line"]] if isinstance(entry, dict) else list(entry[:2])


def _line(name: str, tool: str, symbol: str, miss=(), fp=(), marked=(), errors=()) -> dict:
    return {"audit": name, "tool": tool, "symbol": symbol, "miss": sorted(_pair(m) for m in miss),
            "fp": sorted(_pair(f) for f in fp), "marked": sorted(_pair(m) for m in marked), "errors": sorted(errors)}


def _key(line: dict) -> str:
    """The whole line with no `cause`, as a text; the lists are sorted."""
    bare = {k: sorted(v) if k in LISTS else v for k, v in line.items() if k != "cause"}
    return json.dumps(bare, sort_keys=True)


def read_lines(path: str) -> list[dict]:
    """The JSON object lines of a file; [] when the file does not exist. ValueError for a line that is no JSON
    object."""
    if not os.path.exists(path):
        return []
    lines = []
    with open(path, encoding="utf-8") as f:
        for n, text in enumerate(f, 1):
            if not text.strip():
                continue
            try:
                line = json.loads(text)
            except ValueError as e:
                raise ValueError(f"{path}:{n}: no JSON ({e})") from None
            if not isinstance(line, dict):
                raise ValueError(f"{path}:{n}: the line is no JSON object")
            lines.append(line)
    return lines


class NotReady(ValueError):
    """A `symbols` result with an `index_not_ready` result: the IDE was in dumb mode during the audit."""


def _rows(path: str) -> list[dict]:
    """The records of a result file, with no `_meta`. ValueError for a row that is no object with an `id`, for a
    `_meta` whose server version changed during the run, and for a file with no record."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, text in enumerate(f, 1):
            if not text.strip():
                continue
            row = json.loads(text)
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError(f"{path}:{n}: the row is no JSON object with an id")
            rows.append(row)
    meta = next((row for row in rows if row["id"] == "_meta"), {})
    if meta.get("version_start") != meta.get("version_end"):
        raise ValueError(f"{path}: the server version changed during the run ({meta.get('version_start')} at the "
                         f"start, {meta.get('version_end')} at the end); run the audit again")
    rows = [row for row in rows if row["id"] != "_meta"]
    if not rows:
        raise ValueError(f"{path}: the result has no record")
    return rows


def from_symbols(name: str, results_dir: str, keys_file: str, host_config: str = "linux") -> list[dict]:
    """One line for each record and tool of `symbols.disagreements`, with the marked false lines of the results.
    NotReady for a result that holds an `index_not_ready` result."""
    results = _rows(os.path.join(results_dir, "results.jsonl"))
    not_ready = sum(1 for res in results if symbols.NOT_READY in (res["error"] or ""))
    if not_ready:
        raise NotReady(f"{results_dir}: the IDE was not ready for {not_ready} calls; run the audit again")
    by_id = {r["id"]: r for r in keys.load_keys(keys_file) if r["id"] != "_meta"}
    absent = sorted({res["id"] for res in results} - set(by_id))
    if absent:
        raise ValueError(f"{len(absent)} result ids are not in {keys_file}, for example {absent[0]}")
    marked: dict[tuple[str, str], set] = {}
    for res in results:
        for file, line, _ in res["extra"].get("marked_fp", []):
            marked.setdefault((res["id"], res["tool"]), set()).add((file, line))
    return [_line(name, d["tool"], d["id"], d["miss"], d["fp"], marked.get((d["id"], d["tool"]), ()), d["errors"])
            for d in symbols.disagreements(results, by_id, host_config)]


def _sites(results_file: str, row: dict, label: str) -> tuple[list, list]:
    """The missed and the false sites of the part `label` of a row. ValueError when the length of a list differs
    from its count (`miss`, `fp`): the audit left a line out of the list (a `forbidden` site, or two sites on one
    line), and the line of the row would hide a change."""
    part = row[label]
    for count in ("miss", "fp"):
        if len(part[f"{count}_sites"]) != part[count]:
            raise ValueError(f"{results_file}: the row {row['id']} has {len(part[f'{count}_sites'])} lines in "
                             f"{label}.{count}_sites and {label}.{count} {part[count]}")
    return part["miss_sites"], part["fp_sites"]


def from_callers(name: str, results_file: str) -> list[dict]:
    """One line for each row with an error or with a `mapped` score that is not exact. ValueError for a list that
    does not fit its count (`_sites`)."""
    out = []
    for row in _rows(results_file):
        if "error" in row:
            out.append(_line(name, HIERARCHY, row["id"], errors=[row["error"]]))
        elif not row["mapped"]["exact"]:
            out.append(_line(name, HIERARCHY, row["id"], *_sites(results_file, row, "mapped")))
    return out


def from_dyn(name: str, results_file: str) -> list[dict]:
    """One line for each row and tool with an error or with a score that is not exact. ValueError for a row of
    the old script, which wrote no missed lines (no `miss_sites`), and for a list that does not fit its count
    (`_sites`)."""
    out = []
    for row in _rows(results_file):
        for label, tool in DYN_TOOLS:
            if f"{label}_error" in row:
                out.append(_line(name, tool, row["id"], errors=[row[f"{label}_error"]]))
            elif not row[label]["exact"]:
                if "miss_sites" not in row[label]:
                    raise ValueError(f"{results_file}: the row {row['id']} has no {label}.miss_sites: a file of the "
                                     f"old script, with no missed lines")
                out.append(_line(name, tool, row["id"], *_sites(results_file, row, label)))
    return out


def _all_symbols(found: list[dict], accepted: list[dict]) -> set[str]:
    return {line["symbol"] for line in found + accepted}


def verdict(found: list[dict], accepted: list[dict], causes: dict, audited: set[str] | None = None) -> dict:
    """See the module text. `audited`: the ids that the result audited; None counts each symbol of `found` and of
    `accepted` as audited."""
    audited = _all_symbols(found, accepted) if audited is None else audited
    found_keys = {_key(line) for line in found}
    held = {_key(line) for line in accepted}
    new = [line for line in found if _key(line) not in held]
    not_audited = [line for line in accepted if line["symbol"] not in audited]
    gone = [line for line in accepted if line["symbol"] in audited and _key(line) not in found_keys]
    stay = [line for line in accepted if _key(line) in found_keys]
    no_cause = [line for line in stay if line.get("cause") is None]
    no_permission = sorted({line["cause"] for line in stay if line.get("cause") is not None
                            and (causes.get(line["cause"]) or {}).get("permitted") is None})
    result = "fail" if new else "wait" if no_cause or no_permission or not_audited else "pass"
    return {"result": result, "new": new, "gone": gone, "not_audited": not_audited, "no_cause": no_cause,
            "no_permission": no_permission}


def propose(found: list[dict], accepted: list[dict], name: str, audited: set[str] | None = None) -> list[dict]:
    """The accepted list after a new result of the audit `name` (see the module text), sorted. `audited` as in
    `verdict`."""
    audited = _all_symbols(found, [line for line in accepted if line["audit"] == name]) if audited is None else audited
    old_cause = {_key(line): line.get("cause") for line in accepted if line["audit"] == name}
    lines = [line for line in accepted if line["audit"] != name or line["symbol"] not in audited]
    lines += [{**line, "cause": old_cause.get(_key(line))} for line in found]
    return sorted(lines, key=lambda line: (line["audit"], line["tool"], line["symbol"]))


def accepted_file(folder: str, tree: str) -> str:
    return os.path.join(folder, trees.product_of(tree) + ".jsonl")


def _pairs(value) -> bool:
    return isinstance(value, list) and all(isinstance(p, list) and len(p) == 2 and isinstance(p[0], str)
                                           and isinstance(p[1], int) for p in value)


def _accepted_line(line: dict) -> bool:
    errors = line.get("errors", [])
    return (all(isinstance(line.get(field), str) for field in ("audit", "tool", "symbol"))
            and isinstance(line.get("cause"), (str, type(None)))
            and all(_pairs(line.get(field, [])) for field in ("miss", "fp", "marked"))
            and isinstance(errors, list) and all(isinstance(e, str) for e in errors))


def read_accepted(path: str) -> list[dict]:
    """The lines of an accepted file (`read_lines`). ValueError for a line with no text `audit`, `tool` or `symbol`,
    a `cause` that is no text and not null, a list `miss`, `fp` or `marked` that is no list of [file, line] pairs, or
    a list `errors` that is no list of texts."""
    lines = read_lines(path)
    for n, line in enumerate(lines, 1):
        if not _accepted_line(line):
            raise ValueError(f"{path}:{n}: the line is no disagreement line with a cause (module text of "
                             f"audit/verdict.py)")
    return lines


def _date(value) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def read_causes(folder: str) -> dict:
    """`<folder>/causes.json`; {} when the file does not exist. ValueError for a file that is no JSON object of
    objects, and for a cause whose `text` is no text with one or more characters, whose `issue` is no whole number
    and not null, or whose `permitted` is no date `YYYY-MM-DD` and not null."""
    path = os.path.join(folder, "causes.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        try:
            causes = json.load(f)
        except ValueError as e:
            raise ValueError(f"{path}: no JSON ({e})") from None
    if not isinstance(causes, dict) or not all(isinstance(cause, dict) for cause in causes.values()):
        raise ValueError(f"{path}: the file is no JSON object of cause objects")
    for name, cause in causes.items():
        if not all(field in cause for field in ("text", "issue", "permitted")):
            raise ValueError(f"{path}: the cause {name} needs the fields text, issue and permitted")
        if not isinstance(cause["text"], str) or not cause["text"]:
            raise ValueError(f"{path}: the text of the cause {name} is no text with one or more characters")
        if cause["issue"] is not None and (not isinstance(cause["issue"], int) or isinstance(cause["issue"], bool)):
            raise ValueError(f"{path}: the issue of the cause {name} is no whole number and not null")
        if cause["permitted"] is not None and not _date(cause["permitted"]):
            raise ValueError(f"{path}: permitted of the cause {name} is no date YYYY-MM-DD and not null")
    return causes


def _relative(entry: dict, field: str) -> None:
    path = entry[field]
    if not isinstance(path, str) or os.path.isabs(path) or ".." in path.split("/"):
        raise ValueError(f"{entry['name']}: {field} must be a path relative to <data root>/keys/, not {path!r}")


def load_audits(path: str) -> list[dict]:
    """The entries of an audits file (see the module text). ValueError for a bad entry."""
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)
    names = set()
    for e in entries:
        if set(e) != set(FIELDS):
            raise ValueError(f"{e.get('name')}: the fields must be {', '.join(FIELDS)}")
        if e["name"] in names:
            raise ValueError(f"{e['name']}: the name is not unique")
        names.add(e["name"])
        trees.product_of(e["tree"])
        if e["kind"] not in KINDS:
            raise ValueError(f"{e['name']}: kind {e['kind']!r} is not one of {', '.join(KINDS)}")
        _relative(e, "keys")
        if e["kind"] != "symbols":
            _relative(e, "calls")
        elif e["calls"] is not None:
            raise ValueError(f"{e['name']}: a symbols audit has no calls file")
        if e["ids"] is not None and (e["kind"] == "symbols" or not isinstance(e["ids"], list)):
            raise ValueError(f"{e['name']}: ids must be null for symbols, else null or a list of key ids")
        wanted = OPTIONS[e["kind"]] if e["ids"] is None else ()
        for option in ("n", "seed", "repeats"):
            if (option in wanted) != isinstance(e[option], int):
                raise ValueError(f"{e['name']}: {option} must be {'an integer' if option in wanted else 'null'}")
    return entries


def _entries() -> dict[str, dict]:
    return {e["name"]: e for e in load_audits(AUDITS_FILE)}


def read_result(kind: str, name: str, path: str, keys_file: str | None = None) -> tuple[list[dict], set[str]]:
    """The found lines of the result of an audit of the kind, and the ids that the result audited (the result ids
    of `results.jsonl` in the folder `path` for `symbols`, the row ids of the file `path` for `callers` and `dyn`).
    ValueError for a result that the readers refuse or that has not the form of the kind."""
    rows_file = os.path.join(path, "results.jsonl") if kind == "symbols" else path
    try:
        audited = {row["id"] for row in _rows(rows_file)}
        if kind == "symbols":
            return from_symbols(name, path, keys_file), audited
        return (from_callers if kind == "callers" else from_dyn)(name, path), audited
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"{rows_file}: no result of a {kind} audit ({type(e).__name__}: {e})") from None


def _found(args, entry: dict) -> tuple[list[dict], set[str]]:
    kind = "symbols" if args.symbols else "callers" if args.callers else "dyn"
    if kind != entry["kind"]:
        raise ValueError(f"{entry['name']} is a {entry['kind']} audit, and the input is a {kind} result")
    if kind == "symbols" and not args.keys:
        raise ValueError("-symbols needs -keys")
    return read_result(kind, entry["name"], args.symbols or args.callers or args.dyn, args.keys)


def verdict_text(name: str, found: list[dict], v: dict) -> str:
    if "reason" in v:
        return f"{name}: {v['result']} | {v['reason']}"
    lines = [f"{name}: {v['result']} | lines {len(found)}, new {len(v['new'])}, gone {len(v['gone'])}, not audited "
             f"{len(v['not_audited'])}, no cause {len(v['no_cause'])}, no permission: "
             f"{', '.join(v['no_permission']) or '-'}"]
    lines += [f"  new  {json.dumps(line, ensure_ascii=False)}" for line in v["new"]]
    lines += [f"  gone {json.dumps(line, ensure_ascii=False)}" for line in v["gone"]]
    lines += [f"  not audited {json.dumps(line, ensure_ascii=False)}" for line in v["not_audited"]]
    return "\n".join(lines)


def _write_lines(path: str, lines: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _check_or_propose(args) -> int:
    try:
        entries = _entries()
        if args.name not in entries:
            raise ValueError(f"{args.name}: no such audit in {AUDITS_FILE}")
        entry = entries[args.name]
        found, audited = _found(args, entry)
        path = accepted_file(args.accepted, entry["tree"])
        accepted = read_accepted(path)
        causes = read_causes(args.accepted) if args.command == "check" else {}
    except (ValueError, OSError) as e:
        print(e, file=sys.stderr)
        return EXIT_INPUT
    if args.command == "check":
        v = verdict(found, [line for line in accepted if line["audit"] == args.name], causes, audited)
        print(verdict_text(args.name, found, v))
        return EXIT[v["result"]]
    lines = propose(found, accepted, args.name, audited)
    old = {_key(line) for line in accepted if line["audit"] == args.name and line["symbol"] in audited}
    not_audited = sum(1 for line in accepted if line["audit"] == args.name and line["symbol"] not in audited)
    kept = sum(1 for line in found if _key(line) in old)
    _write_lines(path, lines)
    print(f"{args.name}: {len(found)} lines (kept {kept}, new {len(found) - kept}, removed {len(old) - kept}, "
          f"not audited {not_audited}) in {path}")
    return 0


def select(entry: dict, records: list[dict]) -> list[dict]:
    """The records of a `callers` or `dyn` entry."""
    if entry["ids"] is not None:
        return callers.pick(records, entry["ids"])
    if entry["kind"] == "callers":
        return callers.sample(records, entry["n"], entry["seed"])
    return callers.traced(records)


def _prepare(args, root: str) -> tuple[list[dict], dict, dict]:
    """The entries, the slots and the records of each callers and dyn entry, before the first call. ValueError
    for an input that is absent."""
    entries = load_audits(AUDITS_FILE)
    slots = trees.load_slots(os.path.join(root, "trees", "slots.json"))
    for url in (args.url_goland, args.url_pycharm):
        McpClient(url, "")
    records = {}
    for e in entries:
        if e["tree"] not in slots:
            raise ValueError(f"{e['name']}: the tree {e['tree']} has no slot")
        for field in ("keys", "calls"):
            if e[field] is not None and not os.path.isfile(os.path.join(root, "keys", e[field])):
                raise ValueError(f"{e['name']}: no file {e[field]} below <data root>/keys/")
        if e["kind"] != "symbols":
            key_file = os.path.join(root, "keys", e["keys"])
            records[e["name"]] = select(e, [r for r in keys.load_keys(key_file) if r["id"] != "_meta"])
    return entries, slots, records


def _versions(args, entries: list[dict]) -> dict[str, str]:
    """{product: the server version of its IDE}, before the first write. McpError when an IDE that an audit of the
    list uses gives no version; an IDE that no audit uses gets `unknown (<error>)`."""
    used = {trees.product_of(e["tree"]) for e in entries}
    plugin = {}
    for product, option in URL_OPTIONS.items():
        url = getattr(args, option)
        try:
            plugin[product] = McpClient(url, "").server_version()
        except McpError as e:
            if product in used:
                raise McpError(e.kind, f"{url}: the IDE of {product} gives no server version ({e})") from None
            plugin[product] = f"unknown ({e})"
    return plugin


def _run_audits(args, root: str, entries: list[dict], slots: dict, records: dict, plugin: dict) -> bool:
    """Run each audit. False when one stops before its end."""
    os.makedirs(args.out)
    files = sorted({e[field] for e in entries for field in ("keys", "calls") if e[field] is not None})
    manifest.write(os.path.join(args.out, "manifest.json"), plugin=plugin,
                   files={f: manifest.file_sha256(os.path.join(root, "keys", f)) for f in files})
    for e in entries:
        url = getattr(args, URL_OPTIONS[trees.product_of(e["tree"])])
        project = slots[e["tree"]]["path"]
        key_file = os.path.join(root, "keys", e["keys"])
        print(f"== {e['name']} ({e['kind']}, {e['tree']})", file=sys.stderr)
        if e["kind"] == "symbols":
            code = symbols.run_folder(keys_file=key_file, url=url, project=project, n=e["n"], seed=e["seed"],
                                      repeats=e["repeats"], outside=symbols.OUTSIDE,
                                      out=os.path.join(args.out, e["name"]))
        else:
            calls = keys.load_keys(os.path.join(root, "keys", e["calls"]))
            done = callers.run_file(e["kind"], McpClient(url, project), records[e["name"]], calls,
                                    os.path.join(args.out, e["name"] + ".jsonl"), key_file)
            code = 0 if done is not None else callers.EXIT_NOT_READY
        if code != 0:
            print(f"{e['name']}: the audit stopped with exit code {code}. No verdict.", file=sys.stderr)
            return False
    return True


def _found_of(entry: dict, out: str, root: str) -> tuple[list[dict], set[str]]:
    path = os.path.join(out, entry["name"] + ("" if entry["kind"] == "symbols" else ".jsonl"))
    return read_result(entry["kind"], entry["name"], path, os.path.join(root, "keys", entry["keys"]))


def _run(args) -> int:
    manifest.warn()
    root = settings.data_root()
    try:
        entries, slots, records = _prepare(args, root)
    except (ValueError, OSError) as e:
        print(f"{e}. No call to the IDE.", file=sys.stderr)
        return EXIT_INPUT
    if os.path.exists(args.out):
        print(f"{args.out} exists. Use a new -out folder.", file=sys.stderr)
        return EXIT_INPUT
    try:
        with ide_lock(f"audit.verdict run {args.out}"):
            try:
                plugin = _versions(args, entries)
            except McpError as e:
                print(f"{e}. No result folder.", file=sys.stderr)
                return EXIT_INPUT
            if not _run_audits(args, root, entries, slots, records, plugin):
                return EXIT_STOPPED
    except Busy as e:
        print(f"{e}. No call to the IDE.", file=sys.stderr)
        return EXIT_BUSY
    try:
        causes = read_causes(args.accepted)
        audits, texts = [], []
        for e in entries:
            try:
                found, audited = _found_of(e, args.out, root)
            except NotReady as reason:
                v = {"result": "wait", "reason": str(reason), "new": [], "gone": [], "not_audited": [],
                     "no_cause": [], "no_permission": []}
                texts.append(verdict_text(e["name"], [], v))
                audits.append({"name": e["name"], "verdict": v})
                continue
            accepted = [line for line in read_accepted(accepted_file(args.accepted, e["tree"]))
                        if line["audit"] == e["name"]]
            v = verdict(found, accepted, causes, audited)
            texts.append(verdict_text(e["name"], found, v))
            audits.append({"name": e["name"], "verdict": v})
    except (ValueError, OSError) as e:
        print(f"{e}. No verdict.", file=sys.stderr)
        return EXIT_INPUT
    for text in texts:
        print(text)
    results = [a["verdict"]["result"] for a in audits]
    total = "fail" if "fail" in results else "wait" if "wait" in results else "pass"
    with open(os.path.join(args.out, "verdict.json"), "w", encoding="utf-8") as f:
        json.dump({"result": total, "audits": audits}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"total: {total} | audits {len(results)}: pass {results.count('pass')}, fail {results.count('fail')}, "
          f"wait {results.count('wait')}")
    return EXIT[total]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m audit.verdict", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (("check", "print the verdict of one audit result"),
                               ("propose", "write the found lines of one audit result into the accepted list")):
        p = sub.add_parser(command, help=help_text)
        p.add_argument("-name", required=True, help="the name of the audit in audits.json")
        inputs = p.add_mutually_exclusive_group(required=True)
        inputs.add_argument("-symbols", metavar="DIR", help="the folder of results.jsonl of audit.symbols run")
        inputs.add_argument("-callers", metavar="FILE", help="a file of audit.callers callers")
        inputs.add_argument("-dyn", metavar="FILE", help="a file of audit.callers dyn")
        p.add_argument("-keys", help="the key file of -symbols (JSONL)")
        p.add_argument("-accepted", default=ACCEPTED, help="the folder of the accepted lists and causes.json")
    run = sub.add_parser("run", help="run each audit of audits.json, then print the verdicts")
    run.add_argument("-url-goland", required=True, help="MCP URL of the benchmark GoLand (caddy)")
    run.add_argument("-url-pycharm", required=True, help="MCP URL of the benchmark PyCharm (beets)")
    run.add_argument("-out", required=True, help="a new output folder, for example <data root>/audit/<build>")
    run.add_argument("-accepted", default=ACCEPTED, help="the folder of the accepted lists and causes.json")
    args = parser.parse_args(argv)
    return _run(args) if args.command == "run" else _check_or_propose(args)


if __name__ == "__main__":
    sys.exit(main())
