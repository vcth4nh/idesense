"""The caller audit: call `ide_call_hierarchy` for the targets of a caller key, with no agent, and score each tree.

    python3 -m audit.callers callers -url <mcp url> -project <path> -keys <callers.jsonl> -calls <calls.jsonl>
        -out <jsonl> (-n N [-seed S] | -ids FILE)
    python3 -m audit.callers dyn -url <mcp url> -project <path> -keys <dyncallers.jsonl> -calls <calls.jsonl>
        -out <jsonl> [-ids FILE]

`callers`: for each record, one call of `ide_call_hierarchy` at the `decl` position, `direction: callers`,
`maxDepth: 2`. Each node of levels 1 and 2 is scored two times: `raw` (the line of the node as the tool gives it)
and `mapped` (the declaration line of the outermost function of the calls file that holds the node line: a
closure, a lambda or a nested function becomes its outer function). The records are those of the `-ids` file (one
key id for each line, in the order of the file), or `n` records of a seeded sample (`sample`).

`dyn`: for each record (those of the `-ids` file, or each record with a caller that the run-time trace proves):
`ide_call_hierarchy` at the `decl` with `maxDepth: 1` (`hierarchy`), and `ide_find_usages` at the `decl`, all
pages (`usages`). Each node or usage row counts as the outermost function that holds its line. A usage row in no
function is no answer line: it counts in `usage_marks["in no function"]`.

The score is `keyrecord.score`: a `dnc` line is ignored. A node or a row with an absolute path is outside the tree.
An absent or unreadable key, calls or `-ids` file, an id of the `-ids` file that the key file does not hold, and a
URL with a fleet IDE port give one line and exit 2, with no call to the IDE.
Both commands hold the lock of the benchmark IDEs (exit 2 when another holder has it, with no call to the IDE),
and wait until the IDE is in smart mode (exit 4 after `READY_TIMEOUT` seconds, with no result file). They read
`serverInfo.version` before the first call and after the last row. When the two versions differ, the command
writes the file, prints one line and exits 4. At its start, a command prints the warnings of
`live-test/manifest.json` (`common.manifest.warn`; a difference never stops it), and after the first version read
it writes `<out without .jsonl>.manifest.json` next to the output (`common.manifest.write`, with `plugin` and
`files`). The first line of the output is `{"id": "_meta", "version_start", "version_end", "project", "keys", "n"}`
(`dyn`: no `keys`). Each other line is the row of one record:

- `callers`: `{"id", "levels", "property", "truncated", "kinds", "deeper", "notes", "warnings", "raw", "mapped"}`,
  or `{"id", "levels", "property", "error"}` when the tool gave no tree. `raw` and `mapped` are `{"tp", "fp",
  "miss", "exact", "miss_sites": [[file, line, level, lit, configs], ...], "fp_sites": [[file, line], ...]}`.
  `kinds` counts the node kinds (and `outside-tree`: a node with no tree file and line); `deeper` counts the nodes
  below level 2.
- `dyn`: `{"id", "name", "dynamic", "hierarchy_nodes" | "hierarchy_error", "usage_rows", "usage_marks",
  "usage_notes" | "usages_error", "hierarchy", "usages"}`. `hierarchy` and `usages` are `{"tp", "fp", "miss",
  "ignored", "exact", "miss_proof": {proof: n}, "miss_sites": [[file, line], ...], "fp_sites": [[file, line],
  ...]}`. `miss_sites` has each missed line and `fp_sites` has each false line: `audit.verdict` needs both lists.
  The `-ids` file of `dyn` has one key id for each line, as for `callers`.
"""
import argparse
import collections
import json
import os
import random
import sys

from common import keyrecord as keys
from common import manifest
from common.lock import Busy, ide_lock
from common.mcp import READY_POLL, READY_TIMEOUT, McpClient, McpError, wait_ready

HIERARCHY = "ide_call_hierarchy"
USAGES = "ide_find_usages"
EXIT_BUSY = 2
EXIT_INPUT = 2
EXIT_NOT_READY = 4


def outer_of(calls: list[dict]):
    """A function `(file, line) -> line | None`: the declaration line of the outermost function of `calls` that
    holds the line. Only a top function counts: a record whose `top` is absent or equals its `decl`."""
    spans = collections.defaultdict(list)
    for c in calls:
        if c.get("id") == "_meta":
            continue
        if (c.get("top") or c["decl"]) == c["decl"]:
            spans[c["decl"]["file"]].append((c["decl"]["line"], c["end"]))

    def outer(file: str, line: int) -> int | None:
        best = None
        for first, last in spans.get(file, ()):
            if first <= line <= last and (best is None or first < best):
                best = first
        return best

    return outer


def _in_tree(file, line) -> bool:
    return isinstance(file, str) and isinstance(line, int) and not file.startswith("/")


def _error(e: McpError, width: int) -> str:
    return f"{e.kind}: {str(e)[:width]}"


def _walk(nodes, level: int, outer, raw: set, mapped: set, kinds: collections.Counter) -> int:
    """Add the tree line of each node of levels 1 and 2 to `raw` and its mapped line to `mapped`, and count the
    kinds. The level-2 nodes are the `children` of a level-1 node. Return the count of the nodes below level 2."""
    deeper = 0
    for node in nodes or []:
        if level > 2:
            deeper += 1
            continue
        kinds[node.get("kind")] += 1
        f, ln = node.get("file"), node.get("line")
        if _in_tree(f, ln):
            raw.add((f, ln))
            m = outer(f, ln)
            mapped.add((f, m if m is not None else ln))
        else:
            kinds["outside-tree"] += 1
        deeper += _walk(node.get("children"), level + 1, outer, raw, mapped, kinds)
    return deeper


def audit_callers(client: McpClient, records: list[dict], calls: list[dict]) -> list[dict]:
    """One row for each record (see the module text)."""
    outer = outer_of(calls)
    rows = []
    for r in records:
        d = r["decl"]
        row = {"id": r["id"], "levels": r.get("levels"), "property": r.get("property", False)}
        try:
            res = client.call(HIERARCHY, {"file": d["file"], "line": d["line"], "column": d["col"],
                                          "direction": "callers", "maxDepth": 2})
        except McpError as e:
            row["error"] = _error(e, 200)
            rows.append(row)
            continue
        raw, mapped, kinds = set(), set(), collections.Counter()
        deeper = _walk(res.get("calls"), 1, outer, raw, mapped, kinds)
        row["truncated"], row["kinds"], row["deeper"] = res.get("truncated"), dict(kinds), deeper
        row["notes"], row["warnings"] = res.get("notes"), res.get("warnings")
        site_of = {(s["file"], s["line"]): s for s in r["sites"]}
        for label, answer in (("raw", raw), ("mapped", mapped)):
            sc = keys.score(answer, r)
            miss = sorted(k for k, s in site_of.items() if s["class"] == "required" and k not in answer)
            fp = sorted(k for k in answer if k not in site_of)
            row[label] = {"tp": sc["tp"], "fp": sc["fp"], "miss": sc["miss"], "exact": sc["exact"],
                          "miss_sites": [[f, ln, site_of[(f, ln)].get("level"), bool(site_of[(f, ln)].get("lit")),
                                          site_of[(f, ln)].get("configs")] for f, ln in miss],
                          "fp_sites": [[f, ln] for f, ln in fp]}
        rows.append(row)
    return rows


def _hierarchy_lines(client: McpClient, pos: dict, outer, row: dict) -> set:
    res = client.call(HIERARCHY, {**pos, "direction": "callers", "maxDepth": 1})
    got = set()
    for node in res.get("calls") or []:
        f, ln = node.get("file"), node.get("line")
        if _in_tree(f, ln):
            m = outer(f, ln)
            got.add((f, m if m is not None else ln))
    row["hierarchy_nodes"] = len(res.get("calls") or [])
    return got


def _usage_lines(client: McpClient, pos: dict, outer, row: dict) -> set:
    usages, first = client.call_all_pages(USAGES, pos, "usages")
    got, marks = set(), collections.Counter()
    for u in usages:
        f, ln = u.get("file"), u.get("line")
        marks[u.get("match") or "-"] += 1
        if _in_tree(f, ln):
            m = outer(f, ln)
            if m is not None:
                got.add((f, m))
            else:
                marks["in no function"] += 1
    row["usage_rows"], row["usage_marks"] = len(usages), dict(marks)
    row["usage_notes"] = len(first.get("notes") or [])
    return got


def audit_dyn(client: McpClient, records: list[dict], calls: list[dict]) -> list[dict]:
    """One row for each record (see the module text)."""
    outer = outer_of(calls)
    rows = []
    for r in records:
        d = r["decl"]
        row = {"id": r["id"], "name": f"{r['container']}.{r['name']}", "dynamic": r["dynamic"]}
        pos = {"file": d["file"], "line": d["line"], "column": d["col"]}
        answers = {}
        for label, lines in (("hierarchy", _hierarchy_lines), ("usages", _usage_lines)):
            try:
                answers[label] = lines(client, pos, outer, row)
            except McpError as e:
                row[f"{label}_error"] = _error(e, 160)
        site = {(s["file"], s["line"]): s for s in r["sites"]}
        for label, got in answers.items():
            sc = keys.score(got, r)
            miss = sorted(k for k, s in site.items() if s["class"] == "required" and k not in got)
            row[label] = {"tp": sc["tp"], "fp": sc["fp"], "miss": sc["miss"], "ignored": sc["ignored"],
                          "exact": sc["exact"],
                          "miss_proof": dict(collections.Counter(site[k].get("proof") for k in miss)),
                          "miss_sites": [list(k) for k in miss],
                          "fp_sites": [list(k) for k in sorted(k for k in got if k not in site)]}
        rows.append(row)
    return rows


AUDITS = {"callers": audit_callers, "dyn": audit_dyn}


def sample(records: list[dict], n: int, seed: int) -> list[dict]:
    """The seeded sample: the records sorted by id, shuffled with the seed, the first n, sorted by id."""
    recs = sorted(records, key=lambda r: r["id"])
    random.Random(seed).shuffle(recs)
    return sorted(recs[:n], key=lambda r: r["id"])


def pick(records: list[dict], ids: list[str]) -> list[dict]:
    """The records of the ids, in the order of the ids. ValueError for an id that no record has."""
    by_id = {r["id"]: r for r in records}
    absent = [i for i in ids if i not in by_id]
    if absent:
        raise ValueError(f"{len(absent)} ids are not in the key file, for example {absent[0]}")
    return [by_id[i] for i in ids]


def traced(records: list[dict]) -> list[dict]:
    """The records of a `dyn` key with a caller that the run-time trace proves."""
    return [r for r in records if r["dynamic"]["trace"] >= 1]


def run_file(kind: str, client: McpClient, records: list[dict], calls: list[dict], path: str,
             keys_file: str, manifest_path: str | None = None, calls_file: str | None = None
             ) -> tuple[str, list[dict]] | None:
    """Wait for smart mode, run the audit `kind` (`callers` or `dyn`) and write its file. Return the server
    version and the rows. None when the audit stops: the IDE is not in smart mode after `READY_TIMEOUT` seconds
    (no file), or the server version after the last row differs from the version at the start (the file has
    both versions). With `manifest_path`, the recorded manifest (with the SHA-256 of `keys_file` and `calls_file`)
    goes there after the first version read."""
    reason = wait_ready(client, READY_TIMEOUT, READY_POLL)
    if reason is not None:
        print(f"The IDE is not in smart mode after {READY_TIMEOUT:.0f} s ({reason}). No result file.", file=sys.stderr)
        return None
    version = client.server_version()
    if manifest_path:
        manifest.write(manifest_path, plugin=version,
                       files={f: manifest.file_sha256(f) for f in (keys_file, calls_file) if f})
    rows = AUDITS[kind](client, records, calls)
    try:
        version_end = client.server_version()
    except McpError as e:
        version_end = f"unknown ({e})"
    meta = {"id": "_meta", "version_start": version, "version_end": version_end, "project": client.project_path}
    if kind == "callers":
        meta["keys"] = keys_file
    meta["n"] = len(records)
    with open(path, "w", encoding="utf-8") as out:
        for line in [meta] + rows:
            out.write(json.dumps(line) + "\n")
    if version_end != version:
        print(f"The server version changed during the audit: {version} at the start, {version_end} at the end.",
              file=sys.stderr)
        return None
    return version, rows


def callers_text(version: str, rows: list[dict]) -> str:
    """The text of the totals. `empty tree` counts the trees with no node at level 1 or 2."""
    ok = [r for r in rows if "error" not in r]
    lines = [f"plugin {version} | records {len(ok)} | errors {len(rows) - len(ok)} | empty tree "
             f"{sum(1 for r in ok if not r['kinds'])} | truncated {sum(1 for r in ok if r['truncated'])}"]
    for label in ("raw", "mapped"):
        parts = [r[label] for r in ok]
        miss = [m for p in parts for m in p["miss_sites"]]
        total = {k: sum(p[k] for p in parts) for k in ("tp", "fp", "miss", "exact")}
        lines.append(f"{label:>6}: exact {total['exact']} of {len(ok)} | tp {total['tp']} fp {total['fp']} "
                     f"miss {total['miss']} | miss at level 1: {sum(1 for m in miss if m[2] == 1)}, level 2: "
                     f"{sum(1 for m in miss if m[2] == 2)}, of these only through a literal: "
                     f"{sum(1 for m in miss if m[3])}")
    return "\n".join(lines)


def dyn_text(version: str, rows: list[dict]) -> str:
    """The line of each record and the totals (tp/fp/miss)."""
    def tfm(row, label):
        return "ERR" if label not in row else "%d/%d/%d" % tuple(row[label][k] for k in ("tp", "fp", "miss"))

    lines = [f"{r['name']:<48} key static {r['dynamic']['static']:>2} trace {r['dynamic']['trace']:>2} "
             f"possible {r['dynamic']['possible']:>2} | hierarchy {tfm(r, 'hierarchy')} | usages {tfm(r, 'usages')}"
             f" marks {r.get('usage_marks')}" for r in rows]
    lines.append(f"plugin {version} | records {len(rows)} (tp/fp/miss)")
    for label in ("hierarchy", "usages"):
        parts = [r[label] for r in rows if label in r]
        total = {k: sum(p[k] for p in parts) for k in ("tp", "fp", "miss", "ignored", "exact")}
        proof = collections.Counter()
        for p in parts:
            proof.update(p["miss_proof"])
        lines.append(f"{label:>9}: exact {total['exact']} of {len(rows)} | tp {total['tp']} fp {total['fp']} "
                     f"miss {total['miss']} (ignored {total['ignored']}) | absent by proof: static "
                     f"{proof['static']}, trace {proof['trace']}, static+trace {proof['static+trace']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m audit.callers", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for kind, help_text in (("callers", "ide_call_hierarchy, 2 levels, against a caller key"),
                            ("dyn", "ide_call_hierarchy (1 level) and ide_find_usages against a dyncallers key")):
        p = sub.add_parser(kind, help=help_text)
        p.add_argument("-url", required=True, help="MCP URL of a benchmark IDE")
        p.add_argument("-project", required=True, help="project_path: the tree that the IDE has open")
        p.add_argument("-keys", required=True, help="key file (JSONL)")
        p.add_argument("-calls", required=True, help="the calls file of the tree (JSONL)")
        p.add_argument("-out", required=True, help="output file (JSONL)")
        p.add_argument("-ids", help="a file with one key id for each line")
        if kind == "callers":
            p.add_argument("-n", type=int, help="sample size (with no -ids)")
            p.add_argument("-seed", type=int, default=1)
    args = parser.parse_args(argv)
    if args.command == "callers" and (args.ids is None) == (args.n is None):
        parser.error("callers: give -n or -ids")
    try:
        records = [r for r in keys.load_keys(args.keys) if r["id"] != "_meta"]
        if args.ids is not None:
            with open(args.ids, encoding="utf-8") as f:
                ids = [line.strip() for line in f if line.strip()]
            try:
                records = pick(records, ids)
            except ValueError as e:
                raise ValueError(f"{args.ids}: {e}") from None
        elif args.command == "callers":
            records = sample(records, args.n, args.seed)
        else:
            records = traced(records)
        calls = keys.load_keys(args.calls)
        client = McpClient(args.url, args.project)
    except (OSError, ValueError) as e:
        print(f"{e}. No call to the IDE.", file=sys.stderr)
        return EXIT_INPUT
    manifest.warn()
    try:
        with ide_lock(f"audit.callers {args.command} {args.out}"):
            done = run_file(args.command, client, records, calls, args.out, args.keys,
                            manifest_path=os.path.splitext(args.out)[0] + ".manifest.json", calls_file=args.calls)
    except Busy as e:
        print(f"{e}. No call to the IDE.", file=sys.stderr)
        return EXIT_BUSY
    if done is None:
        return EXIT_NOT_READY
    print((callers_text if args.command == "callers" else dyn_text)(*done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
