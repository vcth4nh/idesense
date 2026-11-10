"""Real products of the live-test harness: the product table, the pin guard and the snapshot forms."""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fleet

FOLDER_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class Product:
    folder: str  # submodule folder below live-test/real-products/
    ide: str  # key of fleet.IDES
    repo: str
    pin: str  # tag name, for people; the gitlink is the pin
    license: str
    tier: str  # "core" or "optional"
    request_timeout: float = 60.0
    ready_timeout: float = 900.0


def load_products(path: Path) -> list[Product]:
    """Read products.json. A missing file is an empty table; a bad table raises ValueError."""
    if not path.is_file():
        return []
    table = json.loads(path.read_text())
    if not isinstance(table, dict) or not isinstance(table.get("products"), list):
        raise ValueError(f"{path}: no 'products' list")
    out: list[Product] = []
    for row in table["products"]:
        folder = row.get("folder")
        if not isinstance(folder, str) or not FOLDER_RE.match(folder):
            raise ValueError(f"bad folder name {folder!r}")
        if any(p.folder == folder for p in out):
            raise ValueError(f"duplicate folder '{folder}'")
        for key in ("ide", "repo", "pin", "license", "tier"):
            if key not in row:
                raise ValueError(f"{folder}: missing '{key}'")
        if row["ide"] not in fleet.IDES:
            raise ValueError(f"{folder}: unknown ide '{row['ide']}'")
        if row["tier"] not in ("core", "optional"):
            raise ValueError(f"{folder}: tier must be core or optional")
        out.append(Product(folder, row["ide"], row["repo"], row["pin"], row["license"], row["tier"],
                           float(row.get("requestTimeoutSeconds", 60.0)),
                           float(row.get("readyTimeoutSeconds", 900.0))))
    return out


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


def checkout_state(repo_root: Path, rel_path: str) -> str:
    """State of a product checkout: "ok", "missing", "pin mismatch: …" or "modified: …".

    The gitlink in the index of the plugin repository is the pin.
    """
    checkout = repo_root / rel_path
    if not (checkout / ".git").exists():
        return "missing"
    index_entry = _git(repo_root, "ls-files", "-s", "--", rel_path).split()
    if len(index_entry) < 2 or index_entry[0] != "160000":
        return f"pin mismatch: no gitlink for {rel_path}"
    gitlink = index_entry[1]
    head = _git(checkout, "rev-parse", "HEAD").strip()
    if head != gitlink:
        return f"pin mismatch: HEAD {head[:12]} != gitlink {gitlink[:12]}"
    modified = _git(checkout, "status", "--porcelain", "--untracked-files=no").splitlines()
    if modified:
        return f"modified: {len(modified)} tracked file(s)"
    return "ok"


# Result fields that never reach a product snapshot: `preview`, `context` and
# `documentation` quote product source text or prose; `nextCursor` and `stale`
# belong to one call. The pagination and cap fields stay: they are what a
# product pins.
PRODUCT_DROP_FIELDS = {"preview", "context", "documentation", "nextCursor", "stale"}

COMPARE_MODES = ("exact", "ordered", "shape")

# Keys whose list value is a result list.
COUNTED_LISTS = {
    "usages", "references", "implementations", "subtypes", "supertypes", "classes", "symbols", "files",
    "matches", "hierarchy", "calls", "children", "supers", "topUsages", "candidates", "problems",
}

_SHAPE_FIELDS = ("hasMore", "totalCollected", "offset", "pageSize", "truncated", "usageCount", "error")


def _count_lists(node: Any, counts: dict[str, int]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in COUNTED_LISTS and isinstance(value, list):
                counts[key] = counts.get(key, 0) + len(value)
            _count_lists(value, counts)
    elif isinstance(node, list):
        for item in node:
            _count_lists(item, counts)


def snapshot_form(mode: str, normalized: Any) -> Any:
    """The part of a normalized product result that its compare mode pins.

    `exact` and `ordered` keep the result; only `topUsages` becomes its item
    count, because the tool keeps the first five results of a parallel search.
    `shape` keeps the item count of each result list at any depth, plus the
    pagination and cap fields of the top level. A result that a page size or a
    cap cuts is in arrival order, so its content cannot be pinned.
    """
    if mode not in COMPARE_MODES:
        raise ValueError(f"unknown compare mode {mode!r}")
    if mode != "shape":
        if isinstance(normalized, dict) and isinstance(normalized.get("topUsages"), list):
            return {**normalized, "topUsages": len(normalized["topUsages"])}
        return normalized
    counts: dict[str, int] = {}
    _count_lists(normalized, counts)
    out: dict[str, Any] = {"counts": counts}
    if isinstance(normalized, dict):
        for key, value in normalized.items():
            if key in _SHAPE_FIELDS or key.endswith("Truncated"):
                out[key] = value
    return out


def repeated_items(source: Any, page: Any) -> int:
    """How many items of `page` are also in `source`, over the result lists of the top level."""
    if not isinstance(source, dict) or not isinstance(page, dict):
        return 0
    repeated = 0
    for key in COUNTED_LISTS:
        if isinstance(source.get(key), list) and isinstance(page.get(key), list):
            seen = {json.dumps(item, sort_keys=True) for item in source[key]}
            repeated += sum(json.dumps(item, sort_keys=True) in seen for item in page[key])
    return repeated
