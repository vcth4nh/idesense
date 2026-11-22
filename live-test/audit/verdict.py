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

The accepted list of a product is `<accepted>/<product>.jsonl` (default: the folder `accepted/` next to this file):
one disagreement line with a `cause` for each line, sorted by (`audit`, `tool`, `symbol`). The product of an audit
is the product of its tree (`caddy-plant-1` -> `caddy`). `cause` is the name of an entry of
`<accepted>/causes.json`, or null when nobody has named the cause yet:

    {"<name>": {"text": "...", "issue": 218, "permitted": "2026-11-22"}}

`issue` is the number of the issue, or null; `permitted` is the date on which the owner of the repository
permitted the cause, or null. A file that does not exist counts as an empty list.

`verdict(found, accepted, causes)` compares the whole lines with no `cause` (the order in a list does not count):
- `new`: a line of `found` that the accepted list does not hold (a changed line is new). Any new line: `fail`.
- `gone`: an accepted line that `found` does not hold. A maintainer can remove it; it never changes the result.
- With no new line: an accepted line that stays and has no cause (`no_cause`), or a cause that `causes.json` does
  not hold or that has no permission (`no_permission`, the cause names): `wait`. Else `pass`.

`check` prints the verdict of one audit and exits 0 (pass), 1 (fail) or 3 (wait). `propose` writes the accepted
list of the product: the lines of the other audits stay, and the lines of this audit become the found lines. A line
that stays keeps its cause; a new line gets the cause null. Both exit 2 for an unknown name, an input of another
kind, or an input that they cannot read.

`audits.json` (next to this file) is the list of the audits of a full run. Each entry has the fields `name`,
`tree`, `kind` (`symbols`, `callers` or `dyn`), `keys` and `calls` (paths relative to `<data root>/keys/`; `calls`
is null for `symbols`), and the options `n`, `seed`, `repeats` and `ids` (null when the kind has no such option):
- `symbols`: `n`, `seed` and `repeats` of `audit.symbols run`;
- `callers`: the key ids `ids` (in their order), or a seeded sample of `n` records;
- `dyn`: the key ids `ids`, or with null each record with a caller that the run-time trace proves.

`run` holds the lock of the benchmark IDEs (exit 2 when another holder has it, with no call to the IDE), and runs
each audit of `audits.json` on the IDE of its product (GoLand for caddy, PyCharm for beets) at the slot path of
its tree. A `symbols` audit writes the folder `<out>/<name>/`, another audit the file `<out>/<name>.jsonl`. Then
`run` prints the verdict of each audit and one total line, and writes `<out>/verdict.json`:
`{"result": <total>, "audits": [{"name", "verdict": {"result", "new", "gone", "no_cause", "no_permission"}}, ...]}`.
The total is `fail` when an audit fails, else `wait` when an audit waits, else `pass`; the exit code is that of
`check` for the total. `run` refuses an `-out` folder that exists and an input
that is absent (exit 2). When an audit stops before its end (the IDE stays in dumb mode, or the server version
changes during a `symbols` audit), `run` exits 4 with no verdict.
"""
import argparse
import json
import os
import sys

from audit import callers
from audit import symbols
from common import keyrecord as keys
from common import settings, trees
from common.lock import Busy, ide_lock
from common.mcp import McpClient

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
    """The JSON lines of a file; [] when the file does not exist."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [row for row in (json.loads(line) for line in f if line.strip()) if row["id"] != "_meta"]


def from_symbols(name: str, results_dir: str, keys_file: str, host_config: str = "linux") -> list[dict]:
    """One line for each record and tool of `symbols.disagreements`, with the marked false lines of the results."""
    results = _rows(os.path.join(results_dir, "results.jsonl"))
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


def from_callers(name: str, results_file: str) -> list[dict]:
    """One line for each row with an error or with a `mapped` score that is not exact."""
    out = []
    for row in _rows(results_file):
        if "error" in row:
            out.append(_line(name, HIERARCHY, row["id"], errors=[row["error"]]))
        elif not row["mapped"]["exact"]:
            out.append(_line(name, HIERARCHY, row["id"], row["mapped"]["miss_sites"], row["mapped"]["fp_sites"]))
    return out


def from_dyn(name: str, results_file: str) -> list[dict]:
    """One line for each row and tool with an error or with a score that is not exact. ValueError for a row of
    the old script, which wrote no missed lines (no `miss_sites`)."""
    out = []
    for row in _rows(results_file):
        for label, tool in DYN_TOOLS:
            if f"{label}_error" in row:
                out.append(_line(name, tool, row["id"], errors=[row[f"{label}_error"]]))
            elif not row[label]["exact"]:
                part = row[label]
                if "miss_sites" not in part:
                    raise ValueError(f"{results_file}: the row {row['id']} has no {label}.miss_sites: a file of the "
                                     f"old script, with no missed lines")
                out.append(_line(name, tool, row["id"], part["miss_sites"], part["fp_sites"]))
    return out


def verdict(found: list[dict], accepted: list[dict], causes: dict) -> dict:
    """See the module text."""
    found_keys = {_key(line) for line in found}
    held = {_key(line) for line in accepted}
    new = [line for line in found if _key(line) not in held]
    gone = [line for line in accepted if _key(line) not in found_keys]
    stay = [line for line in accepted if _key(line) in found_keys]
    no_cause = [line for line in stay if line.get("cause") is None]
    no_permission = sorted({line["cause"] for line in stay if line.get("cause") is not None
                            and (causes.get(line["cause"]) or {}).get("permitted") is None})
    result = "fail" if new else "wait" if no_cause or no_permission else "pass"
    return {"result": result, "new": new, "gone": gone, "no_cause": no_cause, "no_permission": no_permission}


def propose(found: list[dict], accepted: list[dict], name: str) -> list[dict]:
    """The accepted list after a new result of the audit `name` (see the module text), sorted."""
    old_cause = {_key(line): line.get("cause") for line in accepted if line["audit"] == name}
    lines = [line for line in accepted if line["audit"] != name]
    lines += [{**line, "cause": old_cause.get(_key(line))} for line in found]
    return sorted(lines, key=lambda line: (line["audit"], line["tool"], line["symbol"]))


def accepted_file(folder: str, tree: str) -> str:
    return os.path.join(folder, trees.product_of(tree) + ".jsonl")


def read_causes(folder: str) -> dict:
    path = os.path.join(folder, "causes.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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


def _found(args, entry: dict) -> list[dict]:
    kind = "symbols" if args.symbols else "callers" if args.callers else "dyn"
    if kind != entry["kind"]:
        raise ValueError(f"{entry['name']} is a {entry['kind']} audit, and the input is a {kind} result")
    if kind == "symbols":
        if not args.keys:
            raise ValueError("-symbols needs -keys")
        return from_symbols(entry["name"], args.symbols, args.keys)
    return (from_callers if kind == "callers" else from_dyn)(entry["name"], args.callers or args.dyn)


def verdict_text(name: str, found: list[dict], v: dict) -> str:
    lines = [f"{name}: {v['result']} | lines {len(found)}, new {len(v['new'])}, gone {len(v['gone'])}, no cause "
             f"{len(v['no_cause'])}, no permission: {', '.join(v['no_permission']) or '-'}"]
    lines += [f"  new  {json.dumps(line, ensure_ascii=False)}" for line in v["new"]]
    lines += [f"  gone {json.dumps(line, ensure_ascii=False)}" for line in v["gone"]]
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
        found = _found(args, entry)
    except (ValueError, OSError) as e:
        print(e, file=sys.stderr)
        return EXIT_INPUT
    path = accepted_file(args.accepted, entry["tree"])
    accepted = read_lines(path)
    if args.command == "check":
        v = verdict(found, [line for line in accepted if line["audit"] == args.name], read_causes(args.accepted))
        print(verdict_text(args.name, found, v))
        return EXIT[v["result"]]
    lines = propose(found, accepted, args.name)
    old = {_key(line) for line in accepted if line["audit"] == args.name}
    kept = sum(1 for line in found if _key(line) in old)
    _write_lines(path, lines)
    print(f"{args.name}: {len(found)} lines (kept {kept}, new {len(found) - kept}, removed {len(old) - kept}) "
          f"in {path}")
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


def _run_audits(args, root: str, entries: list[dict], slots: dict, records: dict) -> bool:
    """Run each audit. False when one stops before its end."""
    os.makedirs(args.out)
    for e in entries:
        url = getattr(args, URL_OPTIONS[trees.product_of(e["tree"])])
        project = slots[e["tree"]]["path"]
        key_file = os.path.join(root, "keys", e["keys"])
        print(f"== {e['name']} ({e['kind']}, {e['tree']})", file=sys.stderr)
        if e["kind"] == "symbols":
            code = symbols._run(argparse.Namespace(keys=key_file, url=url, project=project, n=e["n"], seed=e["seed"],
                                                   repeats=e["repeats"], outside=",".join(symbols.OUTSIDE),
                                                   out=os.path.join(args.out, e["name"])))
        else:
            calls = keys.load_keys(os.path.join(root, "keys", e["calls"]))
            done = callers.run_file(e["kind"], McpClient(url, project), records[e["name"]], calls,
                                    os.path.join(args.out, e["name"] + ".jsonl"), key_file)
            code = 0 if done is not None else callers.EXIT_NOT_READY
        if code != 0:
            print(f"{e['name']}: the audit stopped with exit code {code}. No verdict.", file=sys.stderr)
            return False
    return True


def _found_of(entry: dict, out: str, root: str) -> list[dict]:
    if entry["kind"] == "symbols":
        return from_symbols(entry["name"], os.path.join(out, entry["name"]), os.path.join(root, "keys", entry["keys"]))
    reader = from_callers if entry["kind"] == "callers" else from_dyn
    return reader(entry["name"], os.path.join(out, entry["name"] + ".jsonl"))


def _run(args) -> int:
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
            if not _run_audits(args, root, entries, slots, records):
                return EXIT_STOPPED
    except Busy as e:
        print(f"{e}. No call to the IDE.", file=sys.stderr)
        return EXIT_BUSY
    causes = read_causes(args.accepted)
    audits = []
    for e in entries:
        found = _found_of(e, args.out, root)
        accepted = [line for line in read_lines(accepted_file(args.accepted, e["tree"])) if line["audit"] == e["name"]]
        v = verdict(found, accepted, causes)
        print(verdict_text(e["name"], found, v))
        audits.append({"name": e["name"], "verdict": v})
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
