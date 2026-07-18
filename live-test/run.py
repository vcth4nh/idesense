#!/usr/bin/env python3
"""Live MCP test harness runner.

Drives HTTP POST requests against running JetBrains IDEs and either diffs the
responses against committed expected/<tool>.jsonl files (default) or rewrites
them (--bless).

Usage:
    ./run.py [--language LANG] [--tool TOOL] [--url URL] [--bless]
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PORT_BY_LANG = {
    "python": 29172,
    "java": 29170,
    "kotlin": 29170,
    "javascript": 29173,
    "typescript": 29173,
    "go": 29174,
    "php": 29175,
    "rust": 29178,
}

DROP_FIELDS = {
    "preview", "nextCursor", "stale", "hasMore", "truncated",
    "totalCollected", "offset", "pageSize",
}

SORTABLE_ARRAYS = {
    "usages", "references", "implementations", "subtypes", "supertypes",
    "classes", "symbols", "files", "matches",
    "problems", "intentions", "buildErrors", "testResults", "hierarchy", "calls",
    "children",
}

def _is_library(file_path: str, project_root: str) -> bool:
    """True if a file ref is library/SDK code (lives outside the project root).

    The plugin returns project files relative to the project root and library /
    SDK files as absolute paths, so absoluteness is the project/library signal.
    We key off the project root we are handed — never off library install
    locations (mise / JDK / /usr / gradle / …), so there is nothing
    host-specific to maintain: a relative path is always project; an absolute
    path is library unless it resolves back under the project root.
    """
    if file_path.startswith("jar:"):
        # Zip/jar entries (jar:///…/src.zip!/java/util/List.java) are always
        # library refs; os.path.isabs is False for URL forms, so check first.
        return True
    if not os.path.isabs(file_path):
        return False
    rel = os.path.relpath(file_path, project_root)
    return rel == os.pardir or rel.startswith(os.pardir + os.sep)


def _sort_key(item: Any) -> tuple:
    if isinstance(item, dict):
        return (
            item.get("file") or "",
            item.get("line") or 0,
            item.get("column") or 0,
            json.dumps(item, sort_keys=True),
        )
    return ("", 0, 0, json.dumps(item, sort_keys=True) if item is not None else "")


def normalize(obj: Any, project_root: str) -> Any:
    """Reduce a tool result to a host- and toolchain-stable snapshot.

    Project files keep their project-relative path + line/column — we control
    those. Library/SDK files are reduced to basename + symbol identity (name,
    qualifiedName, kind): their directory is machine-specific and their
    line/column track the IDE's decompiler, neither of which signals a plugin
    regression. Noisy fields are dropped and known result arrays sorted.
    """
    if isinstance(obj, dict):
        is_lib = isinstance(obj.get("file"), str) and _is_library(obj["file"], project_root)
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in DROP_FIELDS:
                continue
            if k == "file" and isinstance(v, str):
                if is_lib:
                    out[k] = os.path.basename(v)
                elif os.path.isabs(v):
                    out[k] = os.path.relpath(v, project_root)
                else:
                    out[k] = v
                continue
            if is_lib and k in ("line", "column"):
                continue
            if k == "enclosingScope" and isinstance(v, list) and v and v[0] == "/":
                # A FILE node's enclosing *directory*, as a path-segment array:
                # machine-specific and redundant with `file`. (Scope-NAME chains
                # like ['ShapeCollection','Add'] are relative — kept as semantic
                # signal.)
                continue
            v = normalize(v, project_root)
            if k in SORTABLE_ARRAYS and isinstance(v, list):
                v = sorted(v, key=_sort_key)
            out[k] = v
        return out
    if isinstance(obj, list):
        return [normalize(item, project_root) for item in obj]
    return obj


def post_jsonrpc(url: str, request: dict, timeout: float = 60.0) -> Any:
    """POST a JSON-RPC request, return the unwrapped tool result.

    Possible return shapes:
    - parsed JSON dict/list — happy path; the tool's payload
    - {"transport_error": "..."} — HTTP/transport-level failure
    - {"jsonrpc_error": {...}} — JSON-RPC envelope-level error
    - {"tool_error_text": "..."} — text payload that wasn't valid JSON
    """
    data = json.dumps(request).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.URLError as e:
        return {"transport_error": str(e.reason)}
    except (TimeoutError, ConnectionError, OSError) as e:
        return {"transport_error": f"{type(e).__name__}: {e}"}
    try:
        raw = json.loads(body)
    except json.JSONDecodeError as e:
        return {"transport_error": f"non-JSON envelope: {e}"}
    if not isinstance(raw, dict):
        return {"transport_error": f"unexpected envelope type: {type(raw).__name__}"}
    if "error" in raw:
        return {"jsonrpc_error": raw["error"]}
    result = raw.get("result") or {}
    if not isinstance(result, dict):
        return {"transport_error": f"unexpected result type: {type(result).__name__}"}
    content = result.get("content") or []
    if not isinstance(content, list):
        return {"transport_error": f"unexpected content type: {type(content).__name__}"}
    first = content[0] if content else None
    if first is not None and not isinstance(first, dict):
        return {"transport_error": f"unexpected content item type: {type(first).__name__}"}
    text = first.get("text", "") if first else ""
    if not isinstance(text, str):
        return {"transport_error": f"unexpected text type: {type(text).__name__}"}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"tool_error_text": text}


def build_request(input_entry: dict, project_path: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": input_entry["tool"],
            "arguments": {
                **input_entry.get("params", {}),
                "project_path": project_path,
            },
        },
    }


def check_ready(url: str, project_path: str) -> str | None:
    """Return None if ready; otherwise a diagnostic string."""
    req = build_request(
        {"tool": "ide_index_status", "params": {}}, project_path
    )
    result = post_jsonrpc(url, req, timeout=5.0)
    if not isinstance(result, dict):
        return f"unexpected ready-check shape: {result!r}"
    if "transport_error" in result:
        return f"cannot reach {url}: {result['transport_error']}"
    if "tool_error_text" in result:
        return f"unexpected text response: {result['tool_error_text']!r}"
    if "jsonrpc_error" in result:
        return f"jsonrpc error: {result['jsonrpc_error']}"
    if "error" in result:
        return f"{result['error']} — {result.get('message', '')}"
    if result.get("isDumbMode") is True:
        return "project is in dumb mode (still indexing)"
    return None


def diff_lines(expected: Any, actual: Any) -> str:
    e = json.dumps(expected, indent=2, sort_keys=True).splitlines(keepends=True)
    a = json.dumps(actual, indent=2, sort_keys=True).splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(e, a, fromfile="expected", tofile="actual")
    )


def _load_expected_by_id(expected_path: Path) -> dict[str, Any]:
    """Read one expected/<tool>.jsonl into an id → result dict. Strict: raises on
    malformed JSON, missing fields, or duplicate ids — those signal a corrupt
    snapshot, not a soft MISSING.
    """
    if not expected_path.is_file():
        return {}
    out: dict[str, Any] = {}
    for i, line in enumerate(expected_path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{expected_path}:{i}: invalid JSON ({e})")
        if not isinstance(row, dict) or "id" not in row or "result" not in row:
            raise ValueError(f"{expected_path}:{i}: row missing 'id' or 'result' field")
        eid = row["id"]
        if not isinstance(eid, str) or not eid:
            raise ValueError(f"{expected_path}:{i}: 'id' must be a non-empty string")
        if eid in out:
            raise ValueError(f"{expected_path}:{i}: duplicate expected id '{eid}'")
        out[eid] = row["result"]
    return out


def _serialize_row(eid: str, result: Any) -> str:
    return json.dumps({"id": eid, "result": result}, sort_keys=True, separators=(",", ":"))


def _canon_params(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _canon_params(v[k]) for k in sorted(v)}
    if isinstance(v, list):
        return [_canon_params(x) for x in v]
    return v


def serialize_input_row(row: dict) -> str:
    """Canonical input-row serialization: {"id":…,"tool":…,"params":{…}} with
    params keys recursively sorted, compact separators. --check-fixtures
    enforces that every committed input line equals this exactly."""
    obj: dict[str, Any] = {"id": row["id"], "tool": row["tool"]}
    if "params" in row:
        obj["params"] = _canon_params(row["params"])
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _input_files(snap_dir: Path) -> list[Path]:
    return sorted((snap_dir / "inputs").glob("*.jsonl"))


def _load_inputs(snap_dir: Path) -> list[dict]:
    """All input rows across inputs/*.jsonl in (file, row) order, each tagged
    with its source stem under "_stem". Raises ValueError on invalid JSON,
    missing/empty/duplicate id (global), or tool != filename stem."""
    rows: list[dict] = []
    seen: dict[str, str] = {}
    for f in _input_files(snap_dir):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{f}:{i}: invalid JSON ({e})")
            eid = row.get("id")
            if not isinstance(eid, str) or not eid:
                raise ValueError(f"{f}:{i}: missing/empty id")
            if eid in seen:
                raise ValueError(f"{f}:{i}: duplicate id '{eid}' (also at {seen[eid]})")
            seen[eid] = f"{f.name}:{i}"
            if row.get("tool") != f.stem:
                raise ValueError(f"{f}:{i}: tool {row.get('tool')!r} != filename stem {f.stem!r}")
            row["_stem"] = f.stem
            rows.append(row)
    return rows


def _load_expected(snap_dir: Path) -> dict[str, Any]:
    """Merge expected/*.jsonl via the strict per-file loader; duplicate ids
    across files are corruption."""
    out: dict[str, Any] = {}
    for f in sorted((snap_dir / "expected").glob("*.jsonl")):
        part = _load_expected_by_id(f)
        dup = sorted(set(part) & set(out))
        if dup:
            raise ValueError(f"{f}: expected ids duplicated across files: {dup[:5]}")
        out.update(part)
    return out


def _atomic_write(path: Path, content: str) -> None:
    """Write content atomically: temp file + os.replace. Protects against
    SIGINT, crashes, and concurrent writers truncating the snapshot."""
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(content)
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _md_cell(text: str) -> str:
    """Escape a fragment for a Markdown table cell (pipes break the row)."""
    return text.replace("|", "\\|")


def _anchor_map_lines(lang: str, lang_dir: Path, snap_dir: Path,
                      rows: list[dict] | None = None) -> list[str]:
    """Render ANCHORS.md for one language: every probe input mapped to the
    fixture line it anchors, grouped per fixture file, plus query-only probes.
    Pure function of inputs/*.jsonl + fixture sources — byte-deterministic so
    --check-fixtures can regenerate and compare.
    """
    if rows is None:
        rows = _load_inputs(snap_dir)
    by_file: dict[str, list[dict]] = {}
    queries: list[dict] = []
    for r in rows:
        f = (r.get("params") or {}).get("file")
        if isinstance(f, str) and f:
            by_file.setdefault(f, []).append(r)
        else:
            queries.append(r)
    out = [
        f"# Anchor map — {lang}",
        "",
        f"Generated by `./run.py --write-anchors --language {lang}`; do not edit.",
        "Maps every probe input to the fixture line it anchors. `--check-fixtures`",
        "fails when this file is stale.",
    ]
    for f in sorted(by_file):
        out += ["", f"## {f}", "",
                "| line:col | probe id | tool | source |", "|---|---|---|---|"]
        src: list[str] | None = None
        fp = lang_dir / f
        if fp.is_file():
            src = fp.read_text().splitlines()

        def sort_key(r: dict) -> tuple:
            p = r.get("params") or {}
            return (p.get("line") or 0, p.get("column") or 0, r["id"])

        for r in sorted(by_file[f], key=sort_key):
            p = r.get("params") or {}
            line, col = p.get("line"), p.get("column")
            tool = r["tool"].removeprefix("ide_")
            if isinstance(line, int):
                loc = f"{line}:{col}" if isinstance(col, int) else f"{line}"
                text = ""
                if src and 1 <= line <= len(src):
                    text = src[line - 1].strip()
                    if len(text) > 100:
                        text = text[:100] + "…"
                # Backtick-wrap unless the source itself contains a backtick.
                cell = (f"`{_md_cell(text)}`" if text and "`" not in text
                        else (_md_cell(text) or "—"))
            else:
                loc, cell = "—", "—"
            out.append(f"| {loc} | {r['id']} | {tool} | {cell} |")
    if queries:
        out += ["", "## Query-only probes (no file anchor)", "",
                "| probe id | tool | params |", "|---|---|---|"]
        for r in sorted(queries, key=lambda r: r["id"]):
            tool = r["tool"].removeprefix("ide_")
            params = json.dumps(_canon_params(r.get("params", {})),
                                separators=(",", ":"), ensure_ascii=False)
            out.append(f"| {r['id']} | {tool} | `{_md_cell(params)}` |")
    return out


def write_anchor_maps(root: Path, langs: list[str]) -> int:
    for lang in langs:
        snap_dir = root / "_snapshots" / lang
        content = "\n".join(_anchor_map_lines(lang, root / lang, snap_dir)) + "\n"
        _atomic_write(snap_dir / "ANCHORS.md", content)
        print(f"[{lang}] wrote {snap_dir / 'ANCHORS.md'}")
    return 0


ERROR_KEYS = ("tool_error_text", "transport_error", "jsonrpc_error")


def _result_has_error(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    # Existing error keys
    if any(k in result for k in ERROR_KEYS):
        return True
    # Check for structured error in result
    if "error" in result and isinstance(result["error"], dict):
        err = result["error"]
        if isinstance(err, dict) and ("code" in err or "message" in err):
            return True
        # Also, if the error is a string, maybe?
        if isinstance(err, str):
            return True
    return False


def run_language(
    lang: str,
    project_path: Path,
    snap_dir: Path,
    url: str,
    tool_filter: str | None,
    bless: bool,
    bless_errors: bool = False,
    prune: bool = False,
) -> tuple[int, int]:
    """Returns (passed, failed).

    `project_path` is the IDE-indexed fixture project (anchors resolve there);
    snapshots live outside it under `snap_dir` (_snapshots/<lang>/) so their
    text never pollutes the fixture project's word index — IntelliJ inspections
    like unused-class silently give up past a text-occurrence threshold.
    Inputs are per-tool files (inputs/<tool>.jsonl); expected snapshots mirror
    them 1:1 in expected/<tool>.jsonl. Rows are matched by `id`, not by
    position, so the snapshot survives row insertions, reorderings, and
    `--tool` filtered blesses.
    """
    print(f"[{lang}] {url}")

    err = check_ready(url, str(project_path))
    if err is not None:
        print(f"  PRECHECK: {err}")
        print(f"[{lang}] SKIPPED (precheck failed)")
        return 0, 1

    output_path = snap_dir / "output.jsonl"
    try:
        inputs = _load_inputs(snap_dir)
    except ValueError as e:
        print(f"  ERROR: {e}")
        return 0, 1
    if not inputs:
        print(f"  ERROR: no input rows under {snap_dir / 'inputs'}")
        return 0, 1

    filtered_inputs = inputs
    if tool_filter:
        filtered_inputs = [e for e in inputs if e["_stem"] == tool_filter]
        if not filtered_inputs:
            print(f"  ERROR: --tool '{tool_filter}' matched no inputs.")
            return 0, 1

    try:
        expected_by_id = _load_expected(snap_dir)
    except ValueError as e:
        print(f"  ERROR: {e}")
        return 0, 1

    # Process filtered inputs
    fresh_results: dict[str, Any] = {}
    passed = failed = 0
    for entry in filtered_inputs:
        eid = entry["id"]
        request = build_request(entry, str(project_path))
        result = normalize(post_jsonrpc(url, request), str(project_path))
        fresh_results[eid] = result

        if bless:
            print(f"  {eid} BLESS")
            passed += 1
            continue

        if eid not in expected_by_id:
            print(f"  {eid} MISSING (no expected entry for this id — bless?)")
            failed += 1
            continue

        if expected_by_id[eid] == result:
            print(f"  {eid} PASS")
            passed += 1
        else:
            print(f"  {eid} FAIL")
            for line in diff_lines(expected_by_id[eid], result).splitlines():
                print(f"    {line}")
            failed += 1

    # Output reflects only the rows we ran (filtered or full).
    output_lines = [_serialize_row(e["id"], fresh_results[e["id"]]) for e in filtered_inputs]
    _atomic_write(output_path, "\n".join(output_lines) + ("\n" if output_lines else ""))

    # Detect orphan expected rows (ids present in expected but not in input).
    # Only meaningful in full (non-filtered) diff runs.
    input_ids = {e["id"] for e in inputs}
    if not bless and tool_filter is None:
        orphan_ids = sorted(set(expected_by_id) - input_ids)
        for eid in orphan_ids:
            print(f"  ORPHAN expected id '{eid}' has no matching input — remove or rename.")
        failed += len(orphan_ids)

    if bless:
        # Refuse to bless rows that are errors (by our extended definition) unless
        # either --bless-errors is given, or the existing expected is also an error (so error->error)
        # or if there is no existing expected, we still refuse (because new error row) unless --bless-errors.
        refused_error_details = []  # list of (eid, fresh_result, existing_expected)
        for eid, fresh_result in fresh_results.items():
            if _result_has_error(fresh_result):
                existing_expected = expected_by_id.get(eid)
                existing_is_error = _result_has_error(existing_expected) if existing_expected is not None else False
                # If there's no existing expected, we treat it as non-error for the purpose of comparison?
                # Because we want to refuse new error rows unless --bless-errors.
                # So condition to refuse: if not bless_errors and (existing_expected is None or not existing_is_error)
                if not bless_errors and (existing_expected is None or not existing_is_error):
                    refused_error_details.append((eid, fresh_result, existing_expected))

        if refused_error_details:
            print(f"  ERROR: refusing to bless {len(refused_error_details)} rows that would introduce errors:")
            for eid, fresh_result, existing_expected in refused_error_details[:5]:
                if existing_expected is None:
                    print(f"    {eid}: new row is error: {fresh_result}")
                else:
                    print(f"    {eid}: changing from non-error to error: {fresh_result}")
            if len(refused_error_details) > 5:
                print(f"    ... and {len(refused_error_details) - 5} more")
            print(f"  Use --bless-errors to override.")
            # We need to adjust the counts: we are refusing to bless these rows, so they should not be counted as passed.
            # Currently, we have passed counting every row in the bless block (line 463: passed += 1 for each row).
            # We want to subtract the number of rows we are refusing to bless from passed.
            return passed - len(refused_error_details), len(refused_error_details)
        # Merge fresh results into existing expected, then write per-tool
        # files mirroring input-file order.
        merged: dict[str, Any] = dict(expected_by_id)
        merged.update(fresh_results)
        # Detect orphans (would be dropped). Require --prune to discard.
        orphan_ids = sorted(set(merged) - input_ids)
        if orphan_ids and not prune:
            print(f"  ERROR: bless would drop {len(orphan_ids)} orphan expected ids: {orphan_ids[:5]}")
            print(f"  Use --prune to discard them, or restore the input rows.")
            return passed, len(orphan_ids)
        if prune:
            merged = {k: v for k, v in merged.items() if k in input_ids}
        by_stem: dict[str, list[dict]] = {}
        for e in inputs:
            by_stem.setdefault(e["_stem"], []).append(e)
        exp_dir = snap_dir / "expected"
        exp_dir.mkdir(exist_ok=True)
        for stem, stem_rows in by_stem.items():
            if tool_filter and stem != tool_filter:
                continue
            lines = [_serialize_row(e["id"], merged[e["id"]]) for e in stem_rows if e["id"] in merged]
            _atomic_write(exp_dir / f"{stem}.jsonl", "\n".join(lines) + ("\n" if lines else ""))
        if prune and tool_filter is None:
            for f in exp_dir.glob("*.jsonl"):
                if f.stem not in by_stem:
                    f.unlink()
        print(f"[{lang}] BLESSED {exp_dir}/")
    else:
        print(f"[{lang}] {passed} passed, {failed} failed")
    return passed, failed


def check_fixtures(root: Path, langs: list[str]) -> int:
    """Offline validation: no IDE contact. Returns failure count.

    Per language: every inputs/<tool>.jsonl row is valid JSON with a unique
    (global) id, tool == filename stem, rows id-sorted, and each line exactly
    equals its canonical serialization. expected/*.jsonl parse strictly with
    no cross-file duplicate ids; no orphan or missing expected ids. Anchor
    sanity: file+line+column probes target an existing file, an in-bounds
    line, and a non-whitespace character. The committed ANCHORS.md must
    byte-match regeneration from current inputs + sources.
    """
    failures = 0
    for lang in langs:
        lang_dir = root / lang
        snap_dir = root / "_snapshots" / lang
        per_lang_fail = 0
        if not (snap_dir / "inputs").is_dir():
            print(f"[{lang}] no {snap_dir / 'inputs'} directory")
            failures += 1
            continue

        inputs: list[dict] = []
        try:
            inputs = _load_inputs(snap_dir)
        except ValueError as e:
            print(f"[{lang}] {e}")
            per_lang_fail += 1

        for f in _input_files(snap_dir):
            lines = [l for l in f.read_text().splitlines() if l.strip()]
            try:
                rows = [json.loads(l) for l in lines]
            except json.JSONDecodeError:
                continue  # already reported via _load_inputs
            ids = [r.get("id") for r in rows]
            if ids != sorted(ids):
                print(f"[{lang}] {f.name}: rows not id-sorted")
                per_lang_fail += 1
            for i, (line, row) in enumerate(zip(lines, rows), 1):
                canon = serialize_input_row(row) if isinstance(row, dict) and "id" in row and "tool" in row else None
                if canon is not None and line != canon:
                    print(f"[{lang}] {f.name}:{i}: not canonical serialization")
                    per_lang_fail += 1

        for entry in inputs:
            params = entry.get("params", {})
            file_rel = params.get("file")
            line_no = params.get("line")
            col = params.get("column")
            if not (file_rel and isinstance(line_no, int) and isinstance(col, int)):
                continue
            file_path = lang_dir / file_rel
            if not file_path.is_file():
                print(f"[{lang}] {entry['id']}: file '{file_rel}' not found")
                per_lang_fail += 1
                continue
            file_lines = file_path.read_text().splitlines()
            if line_no < 1 or line_no > len(file_lines):
                print(f"[{lang}] {entry['id']}: line {line_no} out of bounds (file has {len(file_lines)} lines)")
                per_lang_fail += 1
                continue
            line_text = file_lines[line_no - 1]
            if col < 1 or col > len(line_text):
                print(f"[{lang}] {entry['id']}: column {col} beyond line length ({len(line_text)})")
                per_lang_fail += 1
                continue
            if line_text[col - 1].isspace():
                print(f"[{lang}] {entry['id']}: column {col} on line {line_no} of '{file_rel}' is whitespace")
                per_lang_fail += 1

        expected: dict[str, Any] = {}
        try:
            expected = _load_expected(snap_dir)
        except ValueError as e:
            print(f"[{lang}] {e}")
            per_lang_fail += 1
        input_ids = {e["id"] for e in inputs}
        for eid in sorted(set(expected) - input_ids):
            print(f"[{lang}] orphan expected id '{eid}'")
            per_lang_fail += 1
        for eid in sorted(input_ids - set(expected)):
            print(f"[{lang}] input id '{eid}' has no expected entry — bless needed")
            per_lang_fail += 1

        if inputs:
            anchors_path = snap_dir / "ANCHORS.md"
            want = "\n".join(_anchor_map_lines(lang, lang_dir, snap_dir, rows=inputs)) + "\n"
            if not anchors_path.is_file() or anchors_path.read_text() != want:
                print(f"[{lang}] ANCHORS.md stale — run --write-anchors")
                per_lang_fail += 1

        print(f"[{lang}] {len(inputs)} inputs, {len(expected)} expected, {per_lang_fail} issues")
        failures += per_lang_fail
    return failures


def discover_languages(root: Path, only: str | None) -> list[str]:
    snaps = root / "_snapshots"
    if only is not None:
        if not (snaps / only / "inputs").is_dir():
            print(f"No inputs/ directory for language '{only}'", file=sys.stderr)
            sys.exit(1)
        return [only]
    if not snaps.is_dir():
        return []
    return sorted(
        d.name
        for d in snaps.iterdir()
        if d.is_dir() and (d / "inputs").is_dir()
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live MCP test harness runner.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  ./run.py                          # diff every language\n"
            "  ./run.py --bless                  # rewrite expected/<tool>.jsonl\n"
            "  ./run.py --language java          # one language\n"
            "  ./run.py --tool ide_find_definition\n"
            "  ./run.py --url http://127.0.0.1:29170/mcp/streamable-http\n"
            "  ./run.py --write-anchors          # regenerate ANCHORS.md anchor maps"
        ),
    )
    parser.add_argument("--language", help="Restrict to one language.")
    parser.add_argument("--tool", help="Restrict to one MCP tool.")
    parser.add_argument("--url", help="Override server URL for the run.")
    parser.add_argument(
        "--bless",
        action="store_true",
        help="Rewrite expected/<tool>.jsonl files from server output instead of diffing.",
    )
    parser.add_argument(
        "--bless-errors",
        action="store_true",
        help="Allow blessing rows that returned tool_error_text / transport_error / jsonrpc_error.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="During --bless, drop expected ids that no longer have a matching input row.",
    )
    parser.add_argument(
        "--check-fixtures",
        action="store_true",
        help="Offline-validate input/expected files (no IDE calls).",
    )
    parser.add_argument(
        "--write-anchors",
        action="store_true",
        help="Regenerate _snapshots/<lang>/ANCHORS.md from inputs + fixture sources (offline).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    langs = discover_languages(root, args.language)
    if not langs:
        print(f"No fixtures found in {root}", file=sys.stderr)
        return 0

    if args.write_anchors:
        return write_anchor_maps(root, langs)

    if args.check_fixtures:
        failures = check_fixtures(root, langs)
        print(f"ALL: {failures} issues")
        return 0 if failures == 0 else 1

    total_pass = total_fail = 0
    for lang in langs:
        if args.url:
            url = args.url
        else:
            port = PORT_BY_LANG.get(lang)
            if port is None:
                print(f"No port mapped for language '{lang}'", file=sys.stderr)
                return 1
            url = f"http://127.0.0.1:{port}/mcp/streamable-http"
        passed, failed = run_language(
            lang, root / lang, root / "_snapshots" / lang, url, args.tool, args.bless,
            bless_errors=args.bless_errors, prune=args.prune,
        )
        total_pass += passed
        total_fail += failed

    print(f"ALL: {total_pass} passed, {total_fail} failed")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
