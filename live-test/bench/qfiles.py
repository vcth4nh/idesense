"""The tracked questions and keys of the agent benchmark: the export from the challenge sets, the loaders, the check.

    python3 -m bench.qfiles export <set file> ...      (run from live-test)
    python3 -m bench.qfiles check [-data]
    python3 -m bench.qfiles rescore <runs folder>

A question is QUESTIONS/<name>.md: the task text of the control arm (`sets.prompt`) with the placeholder `{root}` for
the path of the checkout, and a final newline. `load_question` gives the text with no final newline; the runner
replaces `{root}` and adds the sentence of the arm. A key is KEYS/<name>.json (JSON with 2 spaces of indent and a
final newline) with the fields KEY_FIELDS:

    {"question": "<name>", "old_ids": ["<challenge id>", ...], "product": "beets", "pin": "<pin of products.json>",
     "tree": "beets", "family": "impls", "lang": "python", "symbol": "<key record id>", "name": "<symbol name>",
     "answer": {"required": ["<path>:<line>", ...], "forbidden": [...], "not_counted": [...]},
     "pick": {"sample": "<hard, random or control>", "rule": "<note of the challenge>"},
     "key_file": "<key file below BENCH/keys>", "source": "<how the key file was made>"}

`answer` is `sets.answer` of the view of the key record (`bench.score` reads it), each list sorted by path and line;
`source` comes from the name of the key file (SOURCES). A key holds positions, names and classes, no source text.

A NAME is lowercase. `name_of` gives the lowercase challenge id when it holds the lowercase symbol name as a whole
word (no letter, digit or `_` next to it); else `<tree>-<family>-<container>.<name>` in lowercase, with `-plant-` of
the tree written as `-plant` and with no container part for a symbol with no container.

`export` reads the challenges of the set files in their order and writes one question for each group of
challenges with an equal question text and an equal answer. The name of a group is `name_of` of its first challenge
in the order (it holds the symbol name, then by id); `old_ids` lists each challenge id of the group, sorted; the
other fields come from the last challenge of the group (the newest choice). Two groups with one name are ordered by
`symbol`: the second gets the suffix `-2`, the third `-3`. A name that does not match NAME is a ValueError.

`check` with no data root: each question has a key and each key has a question, each file name matches NAME, no two
file names of a folder are equal in lowercase, each key has the fields KEY_FIELDS, its `question` is its file name
and its `pin` is the pin of the product in products.json. With `data` (the data root): each `answer` equals
`sets.answer` of a fresh key record of `key_file`, and each answer line is a line of its file in the master tree
`TREES/<tree>/`. The command prints each problem and the count, and exits 0 only with no problem.

`rescore` reads each stored `run.json` of each batch folder below the runs folder (BENCH/runs). A set-aside try
(`<run id>.invalid-<k>`, `<run id>.api-error-<k>`) is not read, and a folder with no run folder is no batch. The
question of a run is its field `question`, or for an old record the question whose `old_ids` hold its `challenge`.
A run with no `answer` is `no_answer`; a run whose question has no tracked key is `unknown`. For each other run,
`score.score` of the stored answer with the tracked key and the files of the master manifest is `equal` when the
fields COMPARED equal the fields of the stored score, else `different`. The command prints the counts of each batch,
then one line for each `different` and each `unknown` run.
"""
import argparse
import fnmatch
import json
import os
import re
import sys

from bench import score
from bench import sets
from common import settings, trees

HERE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS = os.path.join(HERE, "questions")
KEYS = os.path.join(HERE, "keys")
PRODUCTS_FILE = os.path.join(settings.live_test_root(), "real-products", "products.json")
NAME = re.compile(r"[a-z0-9][a-z0-9_.-]*")
KEY_FIELDS = ("question", "old_ids", "product", "pin", "tree", "family", "lang", "symbol", "name", "answer", "pick",
              "key_file", "source")
# The name of a key file below BENCH/keys/<tree>/ -> how the keys of the file were made.
SOURCES = (("symbols.jsonl", "name resolution of the Go compiler library (go/types)"),
           ("unique*.jsonl", "token scan of a unique name, proven by a second scan and a run-time trace"),
           ("hierarchy.jsonl", "reflection in the interpreter of the product"),
           ("plant.jsonl", "planted name: the state of the tree before the rename"),
           ("callers.jsonl", "calls of the syntax tree, proven by SSA (Go) or by a trace (Python)"),
           ("dyncallers.jsonl", "run-time trace of the test suite"))
SET_ASIDE = re.compile(r"\.(?:invalid|api-error)-[0-9]+$")
COMPARED = ("tp", "fp", "miss", "ignored", "exact", "outside", "listed")
STATUSES = ("equal", "different", "unknown", "no_answer")


def pins() -> dict[str, str]:
    """{product folder: pin} of products.json."""
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        return {p["folder"]: p["pin"] for p in json.load(f)["products"]}


def source_of(keys_file: str) -> str:
    base = os.path.basename(keys_file)
    for pattern, text in SOURCES:
        if fnmatch.fnmatchcase(base, pattern):
            return text
    raise ValueError(f"{keys_file}: no source text for this key file name")


def _holds(cid: str, name: str) -> bool:
    """True when the lowercase id holds the lowercase name as a whole word."""
    return re.search(r"(?<![a-z0-9_])" + re.escape(name.lower()) + r"(?![a-z0-9_])", cid.lower()) is not None


def name_of(ch: dict, record: dict) -> str:
    if _holds(ch["id"], record["name"]):
        return ch["id"].lower()
    symbol = ".".join(p for p in (record["container"], record["name"]) if p)
    return f"{ch['tree'].replace('-plant-', '-plant')}-{ch['family']}-{symbol}".lower()


def key_of(ch: dict, record: dict, pin: str) -> dict:
    """The tracked key of one challenge (module text), with its own id as `old_ids`."""
    return {"question": name_of(ch, record), "old_ids": [ch["id"]], "product": ch["product"], "pin": pin,
            "tree": ch["tree"], "family": ch["family"], "lang": record["lang"], "symbol": record["id"],
            "name": record["name"], "answer": sets.answer(ch, record),
            "pick": {"sample": ch["sample"], "rule": ch["note"]}, "key_file": ch["keys"],
            "source": source_of(ch["keys"])}


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def export(set_files: list[str], questions_dir: str = QUESTIONS, keys_dir: str = KEYS) -> list[str]:
    """Write the questions and keys of the challenges of the set files (module text); return the names, sorted."""
    pin = pins()
    groups: dict[tuple[str, str], list] = {}  # (question text, answer) -> [(challenge, record, key), ...]
    for path in set_files:
        for ch in sets.load(path):
            record = sets.record_of(ch)
            key = key_of(ch, record, pin[ch["product"]])
            text = sets.prompt(ch, record, "{root}")
            groups.setdefault((text, json.dumps(key["answer"])), []).append((ch, record, key))
    by_name: dict[str, list] = {}
    for (text, _), members in groups.items():
        first = min(members, key=lambda m: (not _holds(m[0]["id"], m[1]["name"]), m[0]["id"]))
        name = name_of(first[0], first[1])
        key = dict(members[-1][2], question=name, old_ids=sorted({m[0]["id"] for m in members}))
        by_name.setdefault(name, []).append((key, text))
    os.makedirs(questions_dir, exist_ok=True)
    os.makedirs(keys_dir, exist_ok=True)
    names = []
    for name, items in by_name.items():
        items.sort(key=lambda item: (item[0]["symbol"], json.dumps(item[0], sort_keys=True)))
        for k, (key, text) in enumerate(items, 1):
            final = name if k == 1 else f"{name}-{k}"
            if not NAME.fullmatch(final):
                raise ValueError(f"the question name {final!r} does not match {NAME.pattern}")
            key["question"] = final
            _write(os.path.join(questions_dir, final + ".md"), text + "\n")
            _write(os.path.join(keys_dir, final + ".json"), json.dumps(key, indent=2, ensure_ascii=False) + "\n")
            names.append(final)
    return sorted(names)


def _stems(folder: str, ext: str) -> list[str]:
    if not os.path.isdir(folder):
        return []
    return sorted(name[:-len(ext)] for name in os.listdir(folder) if name.endswith(ext))


def names(keys_dir: str = KEYS) -> list[str]:
    """The names of the tracked keys, sorted."""
    return _stems(keys_dir, ".json")


def load_question(name: str, questions_dir: str = QUESTIONS) -> str:
    """The question text, with no final newline."""
    with open(os.path.join(questions_dir, name + ".md"), encoding="utf-8") as f:
        text = f.read()
    return text[:-1] if text.endswith("\n") else text


def load_key(name: str, keys_dir: str = KEYS) -> dict:
    return score.load_key(os.path.join(keys_dir, name + ".json"))


def by_old_id(keys_dir: str = KEYS) -> dict[str, str]:
    """{old challenge id: question name} of the `old_ids` of each key."""
    return {old: name for name in names(keys_dir) for old in load_key(name, keys_dir)["old_ids"]}


def tree_files(tree: str) -> set[str]:
    """The paths of the master manifest `TREES/<tree>.manifest`."""
    return set(trees._manifest_files(os.path.join(trees.TREES, tree + ".manifest")))


def _line_count(path: str) -> int | None:
    """The count of the lines of the file (a last line with no newline counts), or None when there is no file."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return None
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def _data_problems(label: str, key: dict) -> list[str]:
    """The problems of a key against the data root: the answer of a fresh key record, the lines of the tree."""
    ch = {"id": key["question"], "product": key["product"], "tree": key["tree"], "family": key["family"],
          "keys": key["key_file"], "key_id": key["symbol"], "sample": key["pick"]["sample"],
          "note": key["pick"]["rule"]}
    out = []
    try:
        if sets.answer(ch, sets.record_of(ch)) != key["answer"]:
            out.append(f"{label}: the answer differs from the view of {key['key_file']}")
    except (OSError, ValueError, KeyError) as e:
        out.append(f"{label}: no fresh key record ({type(e).__name__}: {e})")
    counts = {}
    for field in ("required", "forbidden", "not_counted"):
        for entry in key["answer"][field]:
            path, _, line = entry.rpartition(":")
            if path not in counts:
                counts[path] = _line_count(os.path.join(trees.TREES, key["tree"], path))
            if counts[path] is None:
                out.append(f"{label}: {entry} is no file of the tree {key['tree']}")
            elif int(line) > counts[path]:
                out.append(f"{label}: {entry} is after the last line ({counts[path]}) of the tree {key['tree']}")
    return out


def check(data: bool = False, questions_dir: str = QUESTIONS, keys_dir: str = KEYS) -> list[str]:
    """The problems of the question and key folders (module text); [] when there is none."""
    problems = []
    questions, keys = _stems(questions_dir, ".md"), _stems(keys_dir, ".json")
    for folder, ext, stems in ((questions_dir, ".md", questions), (keys_dir, ".json", keys)):
        where = os.path.basename(folder)
        lower: dict[str, list[str]] = {}
        for stem in stems:
            if not NAME.fullmatch(stem):
                problems.append(f"{where}/{stem}{ext}: the name does not match {NAME.pattern}")
            lower.setdefault(stem.lower(), []).append(stem + ext)
        for files in lower.values():
            if len(files) > 1:
                problems.append(f"{where}/{' and '.join(sorted(files))}: one name in lowercase")
    where_q, where_k = os.path.basename(questions_dir), os.path.basename(keys_dir)
    problems += [f"{where_q}/{stem}.md: no key" for stem in questions if stem not in keys]
    problems += [f"{where_k}/{stem}.json: no question" for stem in keys if stem not in questions]
    pin = pins()
    for stem in keys:
        label = f"{where_k}/{stem}.json"
        try:
            key = load_key(stem, keys_dir)
        except (OSError, ValueError) as e:
            problems.append(f"{label}: no JSON key ({type(e).__name__}: {e})")
            continue
        if not isinstance(key, dict) or set(key) != set(KEY_FIELDS):
            problems.append(f"{label}: the fields are not {', '.join(KEY_FIELDS)}")
            continue
        if key["question"] != stem:
            problems.append(f"{label}: the question is {key['question']}, not the file name")
        if key["pin"] != pin.get(key["product"]):
            problems.append(f"{label}: the pin {key['pin']} is not the pin {pin.get(key['product'])} of products.json")
        if data:
            problems += _data_problems(label, key)
    return problems


def _rescored(runs_root: str):
    """(batch, run folder, question, status, stored score, new score) of each stored run (module text)."""
    old, keys, files = by_old_id(KEYS), {}, {}
    for batch in sorted(os.listdir(runs_root)):
        folder = os.path.join(runs_root, batch)
        if not os.path.isdir(folder):
            continue
        for run in sorted(os.listdir(folder)):
            path = os.path.join(folder, run, "run.json")
            if SET_ASIDE.search(run) or not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
            name = rec.get("question") or old.get(rec.get("challenge"))
            if rec.get("answer") is None:
                yield batch, run, name or rec.get("challenge"), "no_answer", None, None
                continue
            if name and name not in keys:
                try:
                    keys[name] = load_key(name, KEYS)
                except FileNotFoundError:
                    keys[name] = None
            key = keys.get(name)
            if key is None:
                yield batch, run, name or rec.get("challenge"), "unknown", None, None
                continue
            if key["tree"] not in files:
                files[key["tree"]] = tree_files(key["tree"])
            sites = set()
            for entry in rec["answer"]:
                path, _, line = entry.rpartition(":")
                sites.add((path, int(line)))
            new = score.score(key, sites, files[key["tree"]], rec.get("invalid") or [])
            stored = rec.get("score") or {}
            yield (batch, run, name, "equal" if all(stored.get(k) == new[k] for k in COMPARED) else "different",
                   stored, new)


def _counts(results) -> dict:
    out = {}
    for batch, _, _, status, _, _ in results:
        out.setdefault(batch, dict.fromkeys(STATUSES, 0))[status] += 1
    return out


def rescore(runs_root: str) -> dict:
    """{batch: {"equal": n, "different": n, "unknown": n, "no_answer": n}} of the stored runs (module text)."""
    return _counts(_rescored(runs_root))


def _compared(s: dict) -> str:
    return " ".join(f"{k}={s.get(k)}" for k in COMPARED)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m bench.qfiles", description=__doc__.splitlines()[0],
                                     allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="write the questions and keys of the challenge sets")
    exp.add_argument("sets", nargs="+", help="challenge set files (JSONL)")
    chk = sub.add_parser("check", help="check the tracked questions and keys")
    chk.add_argument("-data", action="store_true", help="also check against the data root")
    res = sub.add_parser("rescore", help="score the stored runs again with the tracked keys")
    res.add_argument("runs", help="the runs folder of the data root")
    args = parser.parse_args(argv)
    if args.command == "rescore":
        results = list(_rescored(args.runs))
        counts = _counts(results)
        width = max([len("batch")] + [len(batch) for batch in counts])
        print(f"{'batch':<{width}}  " + "  ".join(f"{status:>9}" for status in STATUSES))
        for batch, row in counts.items():
            print(f"{batch:<{width}}  " + "  ".join(f"{row[status]:>9}" for status in STATUSES))
        for batch, run, name, status, stored, new in results:
            if status == "different":
                print(f"different {batch}/{run} ({name}): stored {_compared(stored)}; now {_compared(new)}")
            elif status == "unknown":
                print(f"unknown {batch}/{run} ({name})")
        return 0
    if args.command == "export":
        written = export(args.sets, QUESTIONS, KEYS)
        print(f"{len(written)} questions in {QUESTIONS} and {KEYS}")
        return 0
    problems = check(args.data, QUESTIONS, KEYS)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem{'' if len(problems) == 1 else 's'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
