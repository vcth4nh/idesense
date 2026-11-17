"""Answer keys and the score of an answer against a key.

A key file `BENCH/keys/<product>/<set>.jsonl` has one key record for each line:

    {"id": "go:github.com/caddyserver/caddy/v2.App.Provision", "lang": "go",
     "kind": "method", "name": "Provision", "container": "App",
     "decl": {"file": "caddy.go", "line": 10, "col": 15},
     "family": ["<id>", ...],
     "sites": [{"file": "a.go", "line": 3, "col": 7, "class": "required", "why": "use",
                "configs": ["linux"]}],
     "implementers": [{"id": "<id>", "file": "b.go", "line": 9, "col": 6}],
     "source": "go/types"}

- kind: func, method, iface_method, type, interface, class, function.
- class: required, forbidden, dnc.
- why: use, decl, import, comment, string, decoy, unproven, generated.
- source: go/types, scan, plant, reflection, runtime.
- Paths are relative to the tree root.

The score works on source lines, `(file, line)`, not on sites.
"""
import json
import os
import tempfile

SITE_CLASSES = ("required", "forbidden", "dnc")


def load_keys(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_keys(path: str, records: list[dict]) -> None:
    """Write the records sorted by id. The file changes in one step (temp file + os.replace)."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for rec in sorted(records, key=lambda r: r["id"]):
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def line_classes(record: dict) -> dict[tuple[str, int], str]:
    """One class for each (file, line) of the sites: required, required+decoy, forbidden or dnc.

    A required site wins over a dnc site on the same line, and a forbidden site wins over a dnc site.
    """
    by_line: dict[tuple[str, int], set[str]] = {}
    for site in record["sites"]:
        by_line.setdefault((site["file"], site["line"]), set()).add(site["class"])
    out = {}
    for line, classes in by_line.items():
        unknown = classes.difference(SITE_CLASSES)
        if unknown:
            raise ValueError(f"{record['id']}: unknown site class {sorted(unknown)} at {line[0]}:{line[1]}")
        if "required" in classes:
            out[line] = "required+decoy" if "forbidden" in classes else "required"
        elif "forbidden" in classes:
            out[line] = "forbidden"
        else:
            out[line] = "dnc"
    return out


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def score(answer: set[tuple[str, int]], record: dict) -> dict:
    """Score the answered lines against the key record. A dnc line is ignored."""
    classes = line_classes(record)
    tp = fp = ignored = 0
    for line in answer:
        cls = classes.get(line)
        if cls in ("required", "required+decoy"):
            tp += 1
        elif cls == "dnc":
            ignored += 1
        else:
            fp += 1
    miss = sum(1 for line, cls in classes.items() if cls in ("required", "required+decoy") and line not in answer)
    return {"tp": tp, "fp": fp, "miss": miss, "ignored": ignored,
            "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + miss),
            "exact": fp == 0 and miss == 0}
