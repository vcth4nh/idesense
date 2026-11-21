"""The score of one answer against one tracked key. Standard library only: no data root, no IDE, no container.

    python3 live-test/bench/score.py <key.json> <answer.json> [--root <checkout>]

A key is a file of `bench/keys/`. Its `answer` holds the lines `<path>:<line>` of the question by class: `required`,
`forbidden` and `not_counted`. The answer file is the JSON object `{"sites": ["<path>:<line>", ...]}`.

`parse_sites` reads an answer entry so: white space at the two ends is removed; the form is `path:line` or
`path:line:column` (the column is dropped); an absolute path loses the prefix `root + "/"`; the path is normalised
(`posixpath.normpath`, so a leading `./` goes). Each other entry is invalid: no line, a line range, a line below 1, a
path outside the root (an absolute path not below the root, or a relative path that leaves it), an entry that is not
a string. With no root (None), each absolute path is invalid.

`score` counts each answer line once. A `required` line is a true line (`tp`), a `not_counted` line is `ignored`, and
each other line is a false line (`fp`). `miss` counts the required lines that the answer does not hold. With
`tree_files`, an answer line whose path is no file of the tree is not scored and counts in `outside`; `listed` counts
the scored lines, `invalid` the entries that cannot be read.

`main` prints one line `exact=<bool> tp=<n> fp=<n> miss=<n> ignored=<n> outside=<n> invalid=<n>`, then a line
`missed <path>:<line>` for each missed line and a line `false <path>:<line>` for each false line. With `--root`, the
tree files are the output of `git -C <root> ls-files`, and an absolute path below the root is read as relative.
Exit codes: 0 exact, 1 not exact, 2 error.
"""
import argparse
import json
import posixpath
import re
import subprocess
import sys

SITE = re.compile(r"(.+?):([0-9]+)(?::[0-9]+)?")
CLASSES = {"required": "required", "forbidden": "forbidden", "not_counted": "dnc"}


def load_key(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _site(entry, prefix: str | None) -> tuple[str, int] | None:
    if not isinstance(entry, str):
        return None
    m = SITE.fullmatch(entry.strip())
    if not m or int(m.group(2)) < 1:
        return None
    path = m.group(1)
    if path.startswith("/"):
        if prefix is None or not path.startswith(prefix):
            return None
        path = path[len(prefix):]
    path = posixpath.normpath(path)
    if path in (".", "..") or path.startswith(("../", "/")):
        return None
    return path, int(m.group(2))


def parse_sites(obj, root: str | None) -> tuple[set[tuple[str, int]], list[str]]:
    """The answer lines `(path relative to the root, line)` of `obj["sites"]`, and the entries that cannot be read
    (a non-string entry as its JSON text). ValueError when `obj` is no object with a list `sites`."""
    if not isinstance(obj, dict) or not isinstance(obj.get("sites"), list):
        raise ValueError("the answer is no JSON object with a list `sites`")
    prefix = None if root is None else root.rstrip("/") + "/"
    sites, invalid = set(), []
    for entry in obj["sites"]:
        site = _site(entry, prefix)
        if site is None:
            invalid.append(entry if isinstance(entry, str) else json.dumps(entry))
        else:
            sites.add(site)
    return sites, invalid


def line_classes(key: dict) -> dict[tuple[str, int], str]:
    """`required`, `forbidden` or `dnc` (from `not_counted`) for each line `(path, line)` of the answer of the key."""
    out = {}
    for field, cls in CLASSES.items():
        for entry in key["answer"][field]:
            path, _, line = entry.rpartition(":")
            out[(path, int(line))] = cls
    return out


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def score(key: dict, sites: set[tuple[str, int]], tree_files: set[str] | None = None,
          invalid: list[str] | tuple = ()) -> dict:
    """The score of the answer lines against the key (module text)."""
    inside = sites if tree_files is None else {site for site in sites if site[0] in tree_files}
    classes = line_classes(key)
    tp = fp = ignored = 0
    for line in inside:
        cls = classes.get(line)
        if cls == "required":
            tp += 1
        elif cls == "dnc":
            ignored += 1
        else:
            fp += 1
    miss = sum(1 for line, cls in classes.items() if cls == "required" and line not in inside)
    return {"tp": tp, "fp": fp, "miss": miss, "ignored": ignored,
            "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + miss), "exact": fp == 0 and miss == 0,
            "invalid": len(invalid), "outside": len(sites) - len(inside), "listed": len(inside)}


def _tree_files(root: str) -> set[str]:
    out = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, check=True).stdout
    return {p.decode("utf-8", "surrogateescape") for p in out.split(b"\0") if p}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="score.py", description=__doc__.splitlines()[0])
    parser.add_argument("key", help="a key file of bench/keys/")
    parser.add_argument("answer", help='the answer: {"sites": ["<path>:<line>", ...]}')
    parser.add_argument("--root", help="the checkout of the product at the pin of the key")
    args = parser.parse_args(argv)
    try:
        key = load_key(args.key)
        with open(args.answer, encoding="utf-8") as f:
            sites, invalid = parse_sites(json.load(f), args.root)
        files = None if args.root is None else _tree_files(args.root)
        result = score(key, sites, files, invalid)
        classes = line_classes(key)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.CalledProcessError) as e:
        print(f"score: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(" ".join(f"{k}={result[k]}" for k in ("exact", "tp", "fp", "miss", "ignored", "outside", "invalid")))
    inside = sites if files is None else {site for site in sites if site[0] in files}
    for line in sorted(line for line, cls in classes.items() if cls == "required" and line not in inside):
        print(f"missed {line[0]}:{line[1]}")
    for line in sorted(line for line in inside if classes.get(line) not in ("required", "dnc")):
        print(f"false {line[0]}:{line[1]}")
    return 0 if result["exact"] else 1


if __name__ == "__main__":
    sys.exit(main())
