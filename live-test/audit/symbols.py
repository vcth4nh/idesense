"""Audit: call the plugin tools for the symbols of a key file, and score each answer against its key.

    python3 -m audit.symbols run -keys <jsonl> -url <mcp url> -project <path> -n 200 -seed 1 -repeats 3 -out <dir>
    python3 -m audit.symbols disagreements -results <dir> -keys <jsonl> [-host-config linux]

`run` holds the lock of the benchmark IDEs (`common.lock.ide_lock`) while it runs. When another holder
has the lock, it prints its message and exits 2, with no call to the IDE. `run` refuses a folder that
has `results.jsonl` or `results.jsonl.part` (exit code 2, no call to the IDE). It waits until the IDE
is in smart mode (exit code 4 after `READY_TIMEOUT` seconds, with no result file). It reads
`serverInfo.version` before the first probe and after the last one. It writes `results.jsonl` and
`summary.md` into the folder. When the two versions differ, the first line of
`summary.md` says so and the exit code is 3. `disagreements` reads `results.jsonl` and the key file,
and writes `disagreements.jsonl` and `disagreements.md` (see `disagreements`).

The first line of `results.jsonl` is
`{"id": "_meta", "version_start", "version_end", "url", "project", "seed", "n", "repeats"}`. Each other
line is a result record:

    {"id", "tool", "repeat", "answer": [[file, line], ...], "score": {...}, "extra": {...}, "error": str | None}

- `answer`: the tree lines that the tool gave, sorted. A row outside the tree has no score and counts in
  `extra["outside"]`: a library file (an absolute path, or a URL such as `jar:`), or a relative path
  that starts with one of the `-outside` prefixes (default `.venv/`, `node_modules/`, `vendor/`, `.git/`).
- `score`: the keys of `keys.score` (`tp`, `fp`, `miss`, `ignored`, `precision`, `recall`, `exact`);
  `{}` when `error` is set. A usages score also has `marked_fp` (see "Marks" below).
- `extra["fp"]`, `extra["miss"]`: the lines of the false answers and of the missed key items.
  `extra["fp_rows"]` (usages only): `[file, line, usageType]` for each `fp` line, from the first result
  row at that line (null when the row has no `usageType`).
  `extra["marked_fp"]`, `extra["marks"]` (usages only): see "Marks" below.
  `extra["capped"]` is true when a probe got `CAP` rows or more: the answer can be cut.
- `error`: the text of the error when the tool gave no answer. An error that names `index_not_ready`
  (the IDE was in dumb mode) is counted apart in the summary.

Positions: the `line` and the `col` of each key position (`decl`, a site, an implementer) are 1-based,
and `col` counts UTF-16 code units, the unit of the plugin. The key producers (the Go extractor, the
Python keys) write this unit, so the probes pass `col` as `column` with no conversion.

Audit view of `ide_find_usages` (see `usages_view`): the class of a site has the rename meaning, so
each use of each family member is `required`, with `rel` = `self`, `super`, `sub`, `sibling` or
`embedded` (no `rel` counts as `self`). The audit reads each record through `keys.structural_view`: an
optional use (a member outside the coupled family of a Go key) is `required` there, as in a key with no
`coupled` list. An `embedded` site is a selector or a composite literal key that
names an embedded field of the type of the record; the IDE resolves it to the field, not to the type.
Find Usages lists the `self` uses and, for a method, the uses of the interface methods that it
implements (`super`). So the usages probe scores against a view in which a required site with another
`rel` is `dnc`, and counts those lines apart in `extra["off_contract"]`. A decoy on such a line with no
contract site is `dnc` too: the IDE can list the line for the off-contract use.

Marks (usages only): a usage row can have the field `match` (`BASE`: the row refers to a base declaration;
`DYNAMIC`: only the name matches). A row with no `match` is a sure usage of the symbol. An answer line is
sure when one of its rows has no `match`. Else it is marked, and its mark is the sorted set of the `match`
values of its rows, joined with `+`. A sure line that the view does not require and does not ignore is an
`fp` line. A marked line of that kind is no `fp` line: it is in `extra["marked_fp"]` as `[file, line, mark]`,
and `score["marked_fp"]` is their count. The score leaves these lines out; then `precision` is the sure
required lines / (the sure required lines + `fp`), or None with no such line. `recall` counts all required
lines, sure and marked. `extra["marks"]` is `{mark or "none": {class: n}}` over the answer lines, where the
class comes from the record, not from the view (see `_record_classes`). A result with no `match` in any row
has the score and the extra fields of the audit before the marks, and in addition `score["marked_fp"]` 0,
`extra["marked_fp"]` `[]` and `extra["marks"]` with only the mark `none`.
"""
import argparse
import json
import os
import random
import sys

from common import keyrecord as keys
from common.keyrecord import IMPLEMENTER_CLASSES, REQUIRED, RELS, rel_of
from common.lock import Busy, ide_lock
from common.mcp import READY_POLL, READY_TIMEOUT, McpClient, McpError, wait_ready

USAGES = "ide_find_usages"
IMPLEMENTATIONS = "ide_find_implementations"
DEFINITION = "ide_find_definition"
TOOLS = (USAGES, IMPLEMENTATIONS, DEFINITION)
PAGE_SIZE = 500  # the largest page that the plugin permits (PaginationService.MAX_PAGE_SIZE)
CAP = 5000  # a cursor keeps at most this many results (PaginationService.MAX_CACHED_RESULTS_PER_CURSOR)
DEFINITION_SITES = 5
OUTSIDE = (".venv/", "node_modules/", "vendor/", ".git/")
NOT_READY = "index_not_ready"  # the error code of the plugin in dumb mode (McpExceptions.kt)
EXIT_OLD_RESULTS = 2
EXIT_BUSY = 2
EXIT_VERSION_CHANGED = 3
EXIT_NOT_READY = 4
AUTO_CLASSES = ("absent", "config", "decoy", "error", "flake", "marked", "miss")
NO_MARK = "none"  # the mark of a sure line in `extra["marks"]`
OFF_CONTRACT = ("sub", "sibling", "embedded")


def hardness(record: dict) -> str:
    """`decoys` when the key has a forbidden line, else `easy`.

    A forbidden line is a line that a whole-word scan of the name finds and the key rejects. A line with a
    required site and a decoy is a required line, and the scan is correct there.
    """
    return "decoys" if "forbidden" in keys.line_classes(keys.structural_view(record)).values() else "easy"


def sample(records: list[dict], n: int, seed: int) -> list[dict]:
    """At most n records, stratified by kind and hardness: one record from each stratum in turn, until
    n records or no record is left. The result is sorted by id and does not depend on the input order."""
    strata: dict[tuple[str, str], list[dict]] = {}
    for rec in sorted(records, key=lambda r: r["id"]):
        strata.setdefault((rec["kind"], hardness(rec)), []).append(rec)
    rng = random.Random(seed)
    queues = []
    for key in sorted(strata):
        group = strata[key]
        rng.shuffle(group)
        queues.append(group)
    chosen: list[dict] = []
    while len(chosen) < n and any(queues):
        for queue in queues:
            if queue and len(chosen) < n:
                chosen.append(queue.pop())
    return sorted(chosen, key=lambda r: r["id"])


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def _is_outside(path: str, prefixes: tuple[str, ...]) -> bool:
    return os.path.isabs(path) or "://" in path or path.startswith("jar:") or path.startswith(prefixes)


def _tree_lines(rows: list[dict], prefixes: tuple[str, ...]) -> tuple[set[tuple[str, int]], int]:
    """The (file, line) of each row in the tree, and the count of the rows outside the tree."""
    lines, outside = set(), 0
    for row in rows:
        file, line = row.get("file"), row.get("line")
        if not isinstance(file, str) or not isinstance(line, int):
            raise McpError("tool", f"a result row has no file and line: {json.dumps(row)[:200]}")
        if _is_outside(file, prefixes):
            outside += 1
        else:
            lines.add((file, line))
    return lines, outside


def _listed(lines) -> list[list]:
    return [list(line) for line in sorted(lines)]


def _result(record: dict, tool: str, repeat: int, answer=(), score=None, extra=None, error=None) -> dict:
    return {"id": record["id"], "tool": tool, "repeat": repeat, "answer": _listed(answer),
            "score": score or {}, "extra": extra or {}, "error": error}


def _anchor(pos: dict) -> dict:
    return {"file": pos["file"], "line": pos["line"], "column": pos["col"]}


def _contract(record: dict) -> tuple[str, ...]:
    """The `rel` values of the uses that Find Usages lists for the record."""
    return ("self", "super") if record["kind"] == "method" else ("self",)


def usages_view(record: dict) -> dict:
    """A copy of the record in which a required site whose `rel` is outside the contract set is `dnc`.

    The contract set is `self` and `super` for the kind `method`, and `self` for each other kind.
    A `forbidden` site on a line that has such an off-contract site and no contract site is `dnc` too:
    the IDE can list that line for the off-contract use, so the line is never a false answer.
    The record itself does not change.
    """
    contract = _contract(record)
    sites = []
    off_lines = set()
    for s in record["sites"]:
        if s["class"] == "required" and rel_of(s) not in RELS:
            raise ValueError(f"{record['id']}: unknown rel {rel_of(s)!r} at {s['file']}:{s['line']}")
        if s["class"] == "required" and rel_of(s) not in contract:
            sites.append(dict(s, **{"class": "dnc"}))
            off_lines.add((s["file"], s["line"]))
        else:
            sites.append(s)
    off_lines -= {(s["file"], s["line"]) for s in sites if s["class"] == "required"}
    sites = [dict(s, **{"class": "dnc"}) if s["class"] == "forbidden" and (s["file"], s["line"]) in off_lines
             else s for s in sites]
    return {**record, "sites": sites}


def _off_contract(record: dict, answer: set[tuple[str, int]]) -> dict:
    """For `sub`, `sibling` and `embedded`: the lines with such a required site and no contract site, and
    the count of these lines in the answer. A relation with no line is left out."""
    contract = _contract(record)
    contract_lines = {(s["file"], s["line"]) for s in record["sites"]
                      if s["class"] == "required" and rel_of(s) in contract}
    out = {}
    for rel in OFF_CONTRACT:
        lines = {(s["file"], s["line"]) for s in record["sites"]
                 if s["class"] == "required" and rel_of(s) == rel} - contract_lines
        if lines:
            out[rel] = {"lines": len(lines), "listed": len(lines & answer)}
    return out


def _line_marks(rows: list[dict], answer: set[tuple[str, int]]) -> dict[tuple[str, int], str]:
    """The mark of each marked answer line: the sorted set of the `match` values of its rows, joined with
    `+`. A line with a row with no `match` is sure and has no entry."""
    values: dict[tuple[str, int], set[str]] = {}
    sure = set()
    for row in rows:
        line = (row["file"], row["line"])
        if line not in answer:
            continue
        if row.get("match") is None:
            sure.add(line)
        else:
            values.setdefault(line, set()).add(row["match"])
    return {line: "+".join(sorted(v)) for line, v in values.items() if line not in sure}


def _record_classes(record: dict) -> dict[tuple[str, int], str]:
    """The class of each site line of the record (not of the view) for `extra["marks"]`: the sorted set of
    the `rel` values of its required sites joined with `+`, else `forbidden`, else `dnc`."""
    rels: dict[tuple[str, int], set[str]] = {}
    others: dict[tuple[str, int], set[str]] = {}
    for s in record["sites"]:
        line = (s["file"], s["line"])
        if s["class"] == "required":
            rels.setdefault(line, set()).add(rel_of(s))
        else:
            others.setdefault(line, set()).add(s["class"])
    out = {line: "forbidden" if "forbidden" in classes else "dnc" for line, classes in others.items()}
    out.update({line: "+".join(sorted(r)) for line, r in rels.items()})
    return out


def _marks(record: dict, answer: set[tuple[str, int]], line_marks: dict[tuple[str, int], str]) -> dict:
    """`{mark or "none": {class: n}}` over the answer lines; a line with no site has the class `unknown`."""
    classes = _record_classes(record)
    out: dict[str, dict[str, int]] = {}
    for line in sorted(answer):
        counts = out.setdefault(line_marks.get(line, NO_MARK), {})
        cls = classes.get(line, "unknown")
        counts[cls] = counts.get(cls, 0) + 1
    return out


def _paged_extra(rows: list[dict], outside: int, fp, miss) -> dict:
    extra = {"rows": len(rows), "outside": outside, "fp": _listed(fp), "miss": _listed(miss)}
    if len(rows) >= CAP:
        extra["capped"] = True
    return extra


def probe_usages(client: McpClient, record: dict, repeat: int, outside: tuple[str, ...] = OUTSIDE) -> dict:
    """`ide_find_usages` at the declaration, all pages, scored against the audit view of the key
    (`usages_view`). `fp` and `miss` come from the view. A marked line is no `fp` line (see "Marks" in the
    module text)."""
    try:
        rows, head = client.call_all_pages(USAGES, {**_anchor(record["decl"]), "pageSize": PAGE_SIZE}, "usages")
        answer, out = _tree_lines(rows, outside)
    except McpError as e:
        return _result(record, USAGES, repeat, error=str(e))
    view = usages_view(record)
    classes = keys.line_classes(view)
    required = {line for line, cls in classes.items() if cls in REQUIRED}
    line_marks = _line_marks(rows, answer)
    sure = answer - set(line_marks)
    false = {line for line in answer if line not in required and classes.get(line) != "dnc"}
    fp, marked_fp = false & sure, false - sure
    extra = _paged_extra(rows, out, fp, required - answer)
    first_type: dict[tuple[str, int], str | None] = {}
    for row in rows:
        first_type.setdefault((row["file"], row["line"]), row.get("usageType"))
    extra["fp_rows"] = [[file, line, first_type[(file, line)]] for file, line in sorted(fp)]
    extra["marked_fp"] = [[file, line, line_marks[(file, line)]] for file, line in sorted(marked_fp)]
    extra["marks"] = _marks(record, answer, line_marks)
    extra["off_contract"] = _off_contract(record, answer)
    for field in ("warnings", "notes"):
        if head.get(field):
            extra[field] = head[field]
    score = keys.score(answer - marked_fp, view)
    sure_tp = len(sure & required)
    score["precision"] = _ratio(sure_tp, sure_tp + len(fp))
    score["marked_fp"] = len(marked_fp)
    return _result(record, USAGES, repeat, answer, score, extra)


def probe_implementers(client: McpClient, record: dict, repeat: int,
                       outside: tuple[str, ...] = OUTSIDE) -> dict | None:
    """`ide_find_implementations` at the declaration of an interface or a class, all pages. The answer
    lines are scored against the lines of the `implementers` positions.

    An entry has a `class`: `required` (also when the field is absent) or `dnc` (another interface that
    satisfies the interface of the record). An answer line at a `dnc` entry counts in `ignored`: it is
    no `tp` and no `fp`, and it is no `miss` when it is absent. A line with both classes is `required`.
    """
    if record["kind"] not in ("interface", "class"):
        return None
    for imp in record["implementers"]:
        if imp.get("class", "required") not in IMPLEMENTER_CLASSES:
            raise ValueError(f"{record['id']}: unknown implementer class {imp['class']!r} "
                             f"at {imp['file']}:{imp['line']}")
    try:
        rows, _ = client.call_all_pages(IMPLEMENTATIONS, {**_anchor(record["decl"]), "pageSize": PAGE_SIZE},
                                        "implementations")
        answer, out = _tree_lines(rows, outside)
    except McpError as e:
        return _result(record, IMPLEMENTATIONS, repeat, error=str(e))
    expected = {(imp["file"], imp["line"]) for imp in record["implementers"]
                if imp.get("class", "required") == "required"}
    ignored = {(imp["file"], imp["line"]) for imp in record["implementers"] if imp.get("class") == "dnc"} - expected
    fp_lines, miss_lines = answer - expected - ignored, expected - answer
    tp, fp, miss = len(answer & expected), len(fp_lines), len(miss_lines)
    score = {"tp": tp, "fp": fp, "miss": miss, "ignored": len(answer & ignored), "precision": _ratio(tp, tp + fp),
             "recall": _ratio(tp, tp + miss), "exact": fp == 0 and miss == 0}
    return _result(record, IMPLEMENTATIONS, repeat, answer, score, _paged_extra(rows, out, fp_lines, miss_lines))


def _family_decls(record: dict) -> set[tuple[str, int]]:
    """The declaration lines of the family: the `decl` of the record and its sites with `why: decl`."""
    decls = {(record["decl"]["file"], record["decl"]["line"])}
    decls.update((s["file"], s["line"]) for s in record["sites"] if s["why"] == "decl")
    return decls


def probe_definition(client: McpClient, record: dict, repeat: int,
                     outside: tuple[str, ...] = OUTSIDE) -> dict | None:
    """`ide_find_definition` at up to 5 required sites, spread over the sorted sites. A site is correct
    when the result line is a declaration line of the family. This probe uses the record, not the
    usages view: a site of any `rel` except `embedded` must resolve to a declaration line of the family.
    An `embedded` site names an embedded field, and the IDE resolves it to the field, so it is no probe
    site. With no probe site the probe gives no result (None).

    A tool error at a site is the answer of the IDE for that site: a miss, listed in `extra["site_errors"]`.
    A transport or JSON-RPC error, or an `index_not_ready` error, stops the probe.
    """
    sites = sorted((s for s in record["sites"] if s["class"] == "required" and rel_of(s) != "embedded"),
                   key=lambda s: (s["file"], s["line"], s["col"]))
    if not sites:
        return None
    if len(sites) > DEFINITION_SITES:
        sites = [sites[i * len(sites) // DEFINITION_SITES] for i in range(DEFINITION_SITES)]
    decls = _family_decls(record)
    answer, fp_lines, miss_lines, site_errors = set(), set(), set(), []
    tp = fp = outside_count = 0
    for site in sites:
        here = (site["file"], site["line"])
        try:
            lines, out = _tree_lines([client.call(DEFINITION, _anchor(site))], outside)
        except McpError as e:
            if e.kind != "tool" or NOT_READY in str(e):
                return _result(record, DEFINITION, repeat, error=str(e))
            site_errors.append([site["file"], site["line"], str(e)])
            miss_lines.add(here)
            continue
        if out:
            outside_count += 1
            miss_lines.add(here)
            continue
        line = lines.pop()
        answer.add(line)
        if line in decls:
            tp += 1
        else:
            fp += 1
            fp_lines.add(line)
            miss_lines.add(here)
    score = {"tp": tp, "fp": fp, "miss": len(sites) - tp, "ignored": 0, "precision": _ratio(tp, tp + fp),
             "recall": _ratio(tp, len(sites)), "exact": tp == len(sites)}
    extra = {"sites": len(sites), "outside": outside_count, "fp": _listed(fp_lines), "miss": _listed(miss_lines)}
    if site_errors:
        extra["site_errors"] = site_errors
    return _result(record, DEFINITION, repeat, answer, score, extra)


PROBES = {USAGES: probe_usages, IMPLEMENTATIONS: probe_implementers, DEFINITION: probe_definition}


def probes_for(record: dict) -> list[str]:
    """The tools to audit for a record. A `reflection` key has no site data: only its implementers."""
    tools = []
    sites = record["source"] != "reflection"
    if sites:
        tools.append(USAGES)
    if record["kind"] in ("interface", "class"):
        tools.append(IMPLEMENTATIONS)
    if sites and any(s["class"] == "required" for s in record["sites"]):
        tools.append(DEFINITION)
    return tools


def run_audit(records: list[dict], client: McpClient, repeats: int, out=None, progress=None,
              outside: tuple[str, ...] = OUTSIDE) -> list[dict]:
    """Each probe of each record, `repeats` times; one repeat of all records before the next one.
    Each result goes to the open file `out` as soon as it is known. A probe that gives no result (None)
    is left out: the definition probe of a record whose only required sites are `embedded`."""
    results = []
    records = [keys.structural_view(rec) for rec in records]
    for repeat in range(1, repeats + 1):
        for i, rec in enumerate(records, 1):
            for tool in probes_for(rec):
                res = PROBES[tool](client, rec, repeat, outside)
                if res is None:
                    continue
                results.append(res)
                if out is not None:
                    out.write(json.dumps(res, ensure_ascii=False) + "\n")
                    out.flush()
            if progress and (i % 25 == 0 or i == len(records)):
                errors = sum(1 for r in results if r["error"] is not None)
                progress(f"repeat {repeat}/{repeats}: {i}/{len(records)} symbols, {errors} errors")
    return results


def _outcome(res: dict) -> str:
    """The result with no repeat number. Two repeats differ when their outcomes differ."""
    return json.dumps({k: v for k, v in res.items() if k != "repeat"}, sort_keys=True)


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def summary_rows(results: list[dict], hardness_by_id: dict[str, str]) -> list[dict]:
    """One row for each tool and hardness class, and one row `all` for each tool.

    precision, recall and exact are means over the results with no error (a None ratio is left out).
    errors counts the symbols with an error in a repeat, not_ready the symbols with an `index_not_ready`
    error (they are not in errors), flakes the symbols whose repeats differ. capped counts results.
    off_lines and off_listed (usages only, else None) are the sums of `extra["off_contract"]` over the
    results of the group: the off-contract lines, and those that the answer lists. marked_fp (usages only,
    else None) is the sum of the `extra["marked_fp"]` lines over the results of the group.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for res in results:
        for cls in (hardness_by_id[res["id"]], "all"):
            groups.setdefault((res["tool"], cls), []).append(res)
    order = {tool: i for i, tool in enumerate(TOOLS)}
    rows = []
    for tool, cls in sorted(groups, key=lambda k: (order[k[0]], k[1] == "all", k[1])):
        group = groups[(tool, cls)]
        by_id: dict[str, list[dict]] = {}
        for res in group:
            by_id.setdefault(res["id"], []).append(res)
        ok = [res for res in group if res["error"] is None]
        off = [counts for res in group for counts in res["extra"].get("off_contract", {}).values()]
        rows.append({"tool": tool, "hardness": cls, "symbols": len(by_id),
                     "precision": _mean(res["score"]["precision"] for res in ok),
                     "recall": _mean(res["score"]["recall"] for res in ok),
                     "exact": _mean(1.0 if res["score"]["exact"] else 0.0 for res in ok),
                     "errors": sum(1 for rs in by_id.values()
                                   if any(r["error"] is not None and NOT_READY not in r["error"] for r in rs)),
                     "not_ready": sum(1 for rs in by_id.values()
                                      if any(r["error"] is not None and NOT_READY in r["error"] for r in rs)),
                     "capped": sum(1 for res in group if res["extra"].get("capped")),
                     "off_lines": sum(c["lines"] for c in off) if tool == USAGES else None,
                     "off_listed": sum(c["listed"] for c in off) if tool == USAGES else None,
                     "flakes": sum(1 for rs in by_id.values() if len({_outcome(r) for r in rs}) > 1),
                     "marked_fp": sum(len(res["extra"].get("marked_fp", [])) for res in group)
                     if tool == USAGES else None})
    return rows


def marks_table(results: list[dict]) -> dict[str, dict[str, int]]:
    """The sum of `extra["marks"]` over the usages results of repeat 1: `{mark or "none": {class: n}}`."""
    out: dict[str, dict[str, int]] = {}
    for res in results:
        if res["tool"] != USAGES or res["repeat"] != 1:
            continue
        for mark, counts in res["extra"].get("marks", {}).items():
            into = out.setdefault(mark, {})
            for cls, n in counts.items():
                into[cls] = into.get(cls, 0) + n
    return out


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def summary_text(rows: list[dict], header: list[str], warning: str | None = None,
                 marks: dict[str, dict[str, int]] | None = None) -> str:
    """The text of summary.md. A warning is the first line. With `marks` (see `marks_table`), the table
    "Marks" comes below the main table."""
    lines = ([warning, ""] if warning else []) + [
        "# Audit", "", *header, "",
        "Precision, recall and exact are means over the results with no error. Errors, not_ready and flakes",
        "count symbols: not_ready is an index_not_ready error (dumb mode), not in errors; a flake is a symbol",
        f"whose repeats differ. Capped counts results with {CAP} rows or more. Off_lines counts the usage",
        "lines (sub, sibling and embedded uses) that the usages audit view leaves out, and off_listed those",
        "of them that the answer lists (sums over the results). For usages, the precision counts only the",
        "sure lines (a line with a row with no `match`), and the recall counts all lines. Marked_fp counts",
        "the marked lines (each row has a `match`) that the view does not require and does not ignore. They",
        "are no false answers (sums over the results).", "",
        "| tool | hardness | symbols | precision | recall | exact | errors | not_ready | capped "
        "| off_lines | off_listed | flakes | marked_fp |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        off_lines = "-" if row["off_lines"] is None else row["off_lines"]
        off_listed = "-" if row["off_listed"] is None else row["off_listed"]
        marked_fp = "-" if row["marked_fp"] is None else row["marked_fp"]
        lines.append(f"| {row['tool']} | {row['hardness']} | {row['symbols']} | {_number(row['precision'])} | "
                     f"{_number(row['recall'])} | {_number(row['exact'])} | {row['errors']} | "
                     f"{row['not_ready']} | {row['capped']} | {off_lines} | {off_listed} | {row['flakes']} | "
                     f"{marked_fp} |")
    if marks is not None:
        columns = sorted({cls for counts in marks.values() for cls in counts})
        lines += ["", "## Marks", "",
                  "The usages answer lines of repeat 1, by mark (rows) and by key class (columns). The mark",
                  f"`{NO_MARK}` is a sure line: one of its rows has no `match`. Another mark is the sorted set of",
                  "the `match` values of the rows of the line. The key class comes from the key record, not from",
                  "the audit view: the `rel` values of the required sites of the line, else `forbidden`, else",
                  "`dnc`, else `unknown` (no site).", "",
                  "| " + " | ".join(["mark", *columns]) + " |", "|---|" + "---|" * len(columns)]
        for mark in sorted(marks, key=lambda m: (m != NO_MARK, m)):
            lines.append("| " + " | ".join([mark, *(str(marks[mark].get(c, 0)) for c in columns)]) + " |")
    return "\n".join(lines) + "\n"


def _miss_entries(miss, record: dict, with_rel: bool = False) -> list[dict]:
    """A missed line with the union of the `configs` and the set of the `why` of its required sites, and
    with `with_rel` the set of their `rel` values."""
    by_line: dict[tuple[str, int], list[dict]] = {}
    for s in record["sites"]:
        if s["class"] == "required":
            by_line.setdefault((s["file"], s["line"]), []).append(s)
    out = []
    for file, line in miss:
        sites = by_line.get((file, line), [])
        entry = {"file": file, "line": line, "configs": sorted({c for s in sites for c in s.get("configs", [])}),
                 "why": sorted({s["why"] for s in sites})}
        if with_rel:
            entry["rel"] = sorted({rel_of(s) for s in sites})
        out.append(entry)
    return out


def _fp_entries(fp, record: dict, group: list[dict]) -> list[dict]:
    """A false usage line with its key class (`forbidden`, or `absent` with no site) and its usage type."""
    classes = keys.line_classes(record)
    types: dict[tuple[str, int], str | None] = {}
    for res in group:
        for file, line, usage_type in res["extra"].get("fp_rows", []):
            types.setdefault((file, line), usage_type)
    return [{"file": file, "line": line, "key_class": "forbidden" if classes.get((file, line)) == "forbidden"
             else "absent", "usageType": types.get((file, line))} for file, line in fp]


def disagreements(results: list[dict], records_by_id: dict[str, dict], host_config: str = "linux") -> list[dict]:
    """One record for each symbol and tool with a false answer, a miss, an error or a `marked_fp` line in a
    repeat: `{"id", "tool", "repeats", "flake", "fp", "miss", "errors", "auto"}`. The lines are the union over
    the repeats.

    - usages and definition: a `miss` entry is `{"file", "line", "configs", "why"}` (see `_miss_entries`).
      A usages `miss` entry also has `rel`: the `rel` values of the required sites of the view at the line.
    - usages: an `fp` entry is `{"file", "line", "key_class", "usageType"}`. The usages entries come from
      the audit view (`usages_view`), as in the probe.
    - definition `fp` and implementers `fp` and `miss`: plain `[file, line]`.
    - `auto`, the automatic classes: `config` (each miss has a non-empty `configs` list without the
      host config), `miss` (a miss that is not of the class `config`), `decoy` (an fp at a forbidden
      line), `absent` (an fp with no key site: an fp with `key_class` `absent`, and each plain fp),
      `error`, `flake`, `marked` (a `marked_fp` line, and no fp, no miss and no error; the lines are in
      `extra["marked_fp"]` of the results).
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for res in results:
        groups.setdefault((res["id"], res["tool"]), []).append(res)
    out = []
    for (rid, tool), group in sorted(groups.items()):
        fp = sorted({tuple(line) for res in group for line in res["extra"].get("fp", [])})
        miss = sorted({tuple(line) for res in group for line in res["extra"].get("miss", [])})
        errors = {res["error"] for res in group if res["error"] is not None}
        errors.update(f"{file}:{line}: {text}" for res in group
                      for file, line, text in res["extra"].get("site_errors", []))
        marked = any(res["extra"].get("marked_fp") for res in group)
        if not (fp or miss or errors or marked):
            continue
        flake = len({_outcome(res) for res in group}) > 1
        record = keys.structural_view(records_by_id[rid])
        if tool == USAGES:
            view = usages_view(record)
            miss_out, fp_out = _miss_entries(miss, view, with_rel=True), _fp_entries(fp, view, group)
        elif tool == DEFINITION:
            miss_out, fp_out = _miss_entries(miss, record), _listed(fp)
        else:
            miss_out, fp_out = _listed(miss), _listed(fp)
        by_config = [isinstance(m, dict) and bool(m["configs"]) and host_config not in m["configs"]
                     for m in miss_out]
        auto = set()
        if miss_out and all(by_config):
            auto.add("config")
        if not all(by_config):
            auto.add("miss")
        for entry in fp_out:
            auto.add("decoy" if isinstance(entry, dict) and entry["key_class"] == "forbidden" else "absent")
        if errors:
            auto.add("error")
        if flake:
            auto.add("flake")
        if marked and not (fp or miss or errors):
            auto.add("marked")
        out.append({"id": rid, "tool": tool, "repeats": len(group), "flake": flake, "fp": fp_out,
                    "miss": miss_out, "errors": sorted(errors), "auto": sorted(auto)})
    return out


def disagreements_text(found: list[dict], header: list[str]) -> str:
    """The text of disagreements.md: one row for each tool and automatic class."""
    lines = ["# Disagreements", "", *header, "",
             "A record with two classes is in both rows. Classes: `config` (each miss is only in other build",
             "configurations than the host), `miss`, `decoy` (an fp at a forbidden line), `absent` (an fp with",
             "no key site), `error`, `flake`, `marked` (only marked false lines: no fp, no miss and no error;",
             "the lines are in `extra.marked_fp` of results.jsonl).", "",
             "| tool | class | records | first ids |", "|---|---|---|---|"]
    for tool in TOOLS:
        for cls in AUTO_CLASSES:
            ids = [d["id"] for d in found if d["tool"] == tool and cls in d["auto"]]
            if ids:
                lines.append(f"| {tool} | {cls} | {len(ids)} | {', '.join(f'`{i}`' for i in ids[:5])} |")
    return "\n".join(lines) + "\n"


def _write_lines(path: str, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _run(args) -> int:
    path = os.path.join(args.out, "results.jsonl")
    for old in (path, path + ".part"):
        if os.path.exists(old):
            print(f"{old} exists. Use a new -out folder, or move the old results away.", file=sys.stderr)
            return EXIT_OLD_RESULTS
    records = [r for r in keys.load_keys(args.keys) if r["id"] != "_meta"]
    chosen = sample(records, args.n, args.seed)
    outside = tuple(prefix for prefix in args.outside.split(",") if prefix)
    client = McpClient(args.url, args.project)
    reason = wait_ready(client, READY_TIMEOUT, READY_POLL)
    if reason is not None:
        print(f"The IDE is not in smart mode after {READY_TIMEOUT:.0f} s ({reason}). No result file.", file=sys.stderr)
        return EXIT_NOT_READY
    version_start = client.server_version()
    os.makedirs(args.out, exist_ok=True)
    # The results go to a part file during the run; the _meta record needs the version at the end.
    with open(path + ".part", "w", encoding="utf-8") as out:
        results = run_audit(chosen, client, args.repeats, out, lambda msg: print(msg, file=sys.stderr), outside)
    try:
        version_end = client.server_version()
    except McpError as e:
        version_end = f"unknown ({e})"
    meta = {"id": "_meta", "version_start": version_start, "version_end": version_end, "url": args.url,
            "project": args.project, "seed": args.seed, "n": args.n, "repeats": args.repeats}
    _write_lines(path, [meta] + results)
    os.remove(path + ".part")
    changed = version_start != version_end
    warning = (f"**The server version changed during the run: {version_start} at the start, {version_end} at "
               f"the end.**") if changed else None
    rows = summary_rows(results, {r["id"]: hardness(r) for r in chosen})
    header = [f"- keys: `{args.keys}`", f"- project: `{args.project}`", f"- url: `{args.url}`",
              f"- server version: {version_start} at the start, {version_end} at the end",
              f"- symbols: {len(chosen)} of {len(records)} (n {args.n}, seed {args.seed}), repeats {args.repeats}",
              f"- outside prefixes: {', '.join(outside) or '-'}"]
    with open(os.path.join(args.out, "summary.md"), "w", encoding="utf-8") as f:
        f.write(summary_text(rows, header, warning, marks_table(results)))
    print(f"{len(results)} results in {args.out}", file=sys.stderr)
    if changed:
        print(warning.strip("*"), file=sys.stderr)
        return EXIT_VERSION_CHANGED
    return 0


def _disagreements(args) -> int:
    with open(os.path.join(args.results, "results.jsonl"), encoding="utf-8") as f:
        results = [json.loads(line) for line in f if line.strip()]
    results = [res for res in results if res["id"] != "_meta"]
    by_id = {r["id"]: r for r in keys.load_keys(args.keys) if r["id"] != "_meta"}
    absent = sorted({res["id"] for res in results} - set(by_id))
    if absent:
        print(f"{len(absent)} result ids are not in {args.keys}, for example {absent[0]}", file=sys.stderr)
        return 2
    found = disagreements(results, by_id, args.host_config)
    _write_lines(os.path.join(args.results, "disagreements.jsonl"), found)
    header = [f"- results: `{args.results}`", f"- keys: `{args.keys}`", f"- host config: {args.host_config}",
              f"- records: {len(found)}"]
    with open(os.path.join(args.results, "disagreements.md"), "w", encoding="utf-8") as f:
        f.write(disagreements_text(found, header))
    print(f"{len(found)} disagreements in {args.results}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m audit.symbols", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="call the tools for a sample of the keys; write results.jsonl and summary.md")
    run.add_argument("-keys", required=True, help="key file (JSONL)")
    run.add_argument("-url", required=True, help="MCP URL of a benchmark IDE")
    run.add_argument("-project", required=True, help="project_path: the tree that the IDE has open")
    run.add_argument("-n", type=int, default=200, help="sample size")
    run.add_argument("-seed", type=int, default=1)
    run.add_argument("-repeats", type=int, default=3)
    run.add_argument("-outside", default=",".join(OUTSIDE),
                     help="comma-separated path prefixes that count as outside the tree (default: %(default)s)")
    run.add_argument("-out", required=True, help="output folder")
    dis = sub.add_parser("disagreements", help="write disagreements.jsonl and disagreements.md from results.jsonl")
    dis.add_argument("-results", required=True, help="folder of results.jsonl")
    dis.add_argument("-keys", required=True, help="the key file of the run (JSONL)")
    dis.add_argument("-host-config", default="linux", help="the build configuration of the IDE host")
    args = parser.parse_args(argv)
    if args.command != "run":
        return _disagreements(args)
    try:
        with ide_lock(f"audit.symbols run {args.out}"):
            return _run(args)
    except Busy as e:
        print(f"{e}. No call to the IDE.", file=sys.stderr)
        return EXIT_BUSY


if __name__ == "__main__":
    sys.exit(main())
