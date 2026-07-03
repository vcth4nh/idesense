#!/usr/bin/env python3
"""Live MCP test harness runner.

Drives HTTP POST requests against running JetBrains IDEs and either diffs the
responses against committed expected.jsonl files (default) or rewrites them
(--bless).

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
    """Read expected.jsonl into an id → result dict. Strict: raises on
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


ERROR_KEYS = ("tool_error_text", "transport_error", "jsonrpc_error")


def _result_has_error(result: Any) -> bool:
    return isinstance(result, dict) and any(k in result for k in ERROR_KEYS)


def run_language(
    lang: str,
    project_path: Path,
    url: str,
    tool_filter: str | None,
    bless: bool,
    bless_errors: bool = False,
    prune: bool = False,
) -> tuple[int, int]:
    """Returns (passed, failed).

    Rows are matched by `id`, not by position. Output and expected both store
    `{"id": ..., "result": ...}` per line so the snapshot survives row
    insertions, reorderings, and `--tool` filtered blesses.
    """
    print(f"[{lang}] {url}")

    err = check_ready(url, str(project_path))
    if err is not None:
        print(f"  PRECHECK: {err}")
        print(f"[{lang}] SKIPPED (precheck failed)")
        return 0, 1

    input_path = project_path / "input.jsonl"
    expected_path = project_path / "expected.jsonl"
    output_path = project_path / "output.jsonl"
    inputs = [
        json.loads(line)
        for line in input_path.read_text().splitlines()
        if line.strip()
    ]

    # Detect duplicate input ids — id-keyed matching requires uniqueness.
    seen: dict[str, int] = {}
    for i, entry in enumerate(inputs):
        eid = entry.get("id")
        if not isinstance(eid, str) or not eid:
            print(f"  ERROR: input row {i + 1} has no id; fix before running.")
            return 0, 1
        if eid in seen:
            print(f"  ERROR: duplicate input id '{eid}' at rows {seen[eid] + 1} and {i + 1}.")
            return 0, 1
        seen[eid] = i

    filtered_inputs = inputs
    if tool_filter:
        filtered_inputs = [e for e in inputs if e["tool"] == tool_filter]
        if not filtered_inputs:
            print(f"  ERROR: --tool '{tool_filter}' matched no inputs.")
            return 0, 1

    try:
        expected_by_id = _load_expected_by_id(expected_path)
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
        # Refuse to bless rows that returned tool/transport errors unless
        # explicitly overridden — otherwise a flaky IDE response gets locked
        # in as truth.
        error_ids = [eid for eid, r in fresh_results.items() if _result_has_error(r)]
        if error_ids and not bless_errors:
            print(f"  ERROR: refusing to bless {len(error_ids)} rows with tool/transport errors:")
            for eid in error_ids[:5]:
                print(f"    {eid}: {fresh_results[eid]}")
            if len(error_ids) > 5:
                print(f"    ... and {len(error_ids) - 5} more")
            print(f"  Use --bless-errors to override.")
            return passed - len(error_ids), len(error_ids)
        # Merge fresh results into existing expected, then write in input order.
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
        new_lines = [
            _serialize_row(e["id"], merged[e["id"]])
            for e in inputs
            if e["id"] in merged
        ]
        _atomic_write(expected_path, "\n".join(new_lines) + ("\n" if new_lines else ""))
        print(f"[{lang}] BLESSED {expected_path}")
    else:
        print(f"[{lang}] {passed} passed, {failed} failed")
    return passed, failed


def check_fixtures(root: Path, langs: list[str]) -> int:
    """Offline validation: no IDE contact. Returns failure count.

    Verifies per-language:
      - input.jsonl: valid JSON, every row has a unique non-empty id.
      - expected.jsonl: parses cleanly via _load_expected_by_id (strict).
      - Orphan expected ids (id in expected but not in input).
      - Anchor sanity: file+line+column probes target an existing file, a
        line within bounds, and a non-whitespace character.
    """
    failures = 0
    for lang in langs:
        lang_dir = root / lang
        input_path = lang_dir / "input.jsonl"
        if not input_path.is_file():
            print(f"[{lang}] no input.jsonl")
            failures += 1
            continue

        inputs: list[dict] = []
        seen: dict[str, int] = {}
        per_lang_fail = 0
        for i, line in enumerate(input_path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[{lang}] input.jsonl:{i}: invalid JSON ({e})")
                per_lang_fail += 1
                continue
            eid = row.get("id")
            if not isinstance(eid, str) or not eid:
                print(f"[{lang}] input.jsonl:{i}: missing/empty id")
                per_lang_fail += 1
                continue
            if eid in seen:
                print(f"[{lang}] input.jsonl:{i}: duplicate id '{eid}' (also row {seen[eid]})")
                per_lang_fail += 1
                continue
            seen[eid] = i
            inputs.append(row)

        # Anchor sanity
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
            char = line_text[col - 1]
            if char.isspace():
                print(f"[{lang}] {entry['id']}: column {col} on line {line_no} of '{file_rel}' is whitespace")
                per_lang_fail += 1

        # Expected.jsonl strict load + orphan check
        expected_path = lang_dir / "expected.jsonl"
        expected: dict[str, Any] = {}
        try:
            expected = _load_expected_by_id(expected_path)
        except ValueError as e:
            print(f"[{lang}] {e}")
            per_lang_fail += 1
        input_ids = {e["id"] for e in inputs}
        orphans = sorted(set(expected) - input_ids)
        for eid in orphans:
            print(f"[{lang}] orphan expected id '{eid}'")
            per_lang_fail += 1
        missing = sorted(input_ids - set(expected))
        for eid in missing:
            print(f"[{lang}] input id '{eid}' has no expected entry — bless needed")
            per_lang_fail += 1

        print(f"[{lang}] {len(inputs)} inputs, {len(expected)} expected, {per_lang_fail} issues")
        failures += per_lang_fail
    return failures


def discover_languages(root: Path, only: str | None) -> list[str]:
    if only is not None:
        if not (root / only / "input.jsonl").is_file():
            print(f"No input.jsonl for language '{only}'", file=sys.stderr)
            sys.exit(1)
        return [only]
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and (d / "input.jsonl").is_file()
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live MCP test harness runner.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  ./run.py                          # diff every language\n"
            "  ./run.py --bless                  # rewrite expected.jsonl\n"
            "  ./run.py --language java          # one language\n"
            "  ./run.py --tool ide_find_definition\n"
            "  ./run.py --url http://127.0.0.1:29170/mcp/streamable-http"
        ),
    )
    parser.add_argument("--language", help="Restrict to one language.")
    parser.add_argument("--tool", help="Restrict to one MCP tool.")
    parser.add_argument("--url", help="Override server URL for the run.")
    parser.add_argument(
        "--bless",
        action="store_true",
        help="Rewrite expected.jsonl from server output instead of diffing.",
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
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    langs = discover_languages(root, args.language)
    if not langs:
        print(f"No fixtures found in {root}", file=sys.stderr)
        return 0

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
            lang, root / lang, url, args.tool, args.bless,
            bless_errors=args.bless_errors, prune=args.prune,
        )
        total_pass += passed
        total_fail += failed

    print(f"ALL: {total_pass} passed, {total_fail} failed")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
