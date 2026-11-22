"""Triage of the runs of a batch: measures and flags of each run, tables, paired differences and adoption.

    python3 -m bench.triage report -batch <name> [-out <dir>]   (run from live-test)
    python3 -m bench.triage table -batch <name>

The input is a batch folder `RUNS/<batch>/` of `bench.runner`: one folder for each run, with `run.json`,
`transcript.jsonl` and `proxy.jsonl`. A folder `<run id>.invalid-<k>` or `<run id>.api-error-<k>` is a try that the
batch set aside: it is counted, not read. A folder with no `run.json` is counted as `unfinished`. The module makes no
model call, starts no container and calls no IDE.

Outcomes: an EXCLUDED run is no measurement (counted, in no mean). The score of an ANSWER_OUTCOMES run counts. A
FAILED run has f1, precision and recall 0 and exact False. A `stopped` run (`-stop-after-tools`) is only in the
adoption table, also when it has an answer.

The question of a run is the field `question` of `run.json`. An old record has the field `challenge` and no
`question`: its question is the tracked question whose `old_ids` hold the challenge id (`qfiles.by_old_id`), or the
challenge id itself when no tracked key has it (`load_batch`). The key of a run is the tracked key of its question
(`qfiles.load_key`), and its line classes are `score.line_classes`. The tree root of a question is its slot path
(`trees.load_slots`). A site of an IDE result with an absolute path below the root is made relative to the root, as
`score.parse_sites` does; another site stays as it is. A line that is in no answer list of the key has no class.

`report` writes into `-out` (default `RUNS/<batch>.triage/`):
- `runs.jsonl`: one JSON object for each run, sorted by id: `id`, `question`, `model`, `arm_label`, `n`, `outcome`,
  the measures (`measures`), the flags (`flags`) and `plugin_wrong_control_right` (`batch_flags`). A set of sites is
  a sorted list of `path:line`.
- `summary.md`, with one Markdown table in each section: "Batch" (the run count of each outcome, set aside,
  unfinished, the total cost of the runs), "By question, model and arm" (`summary_rows`), "Paired differences"
  (`paired`: each plugin arm - C, and each arm of PF_BASED (PFN, PFR, PFL, PFG, PFI and PFS) - PF; after the lines
  of the questions of a model, an arm and a base, the line `all` has the means over the questions and, for each
  difference, its mean and its 95 % interval from `bootstrap`), "Adoption" (`adoption_rows`) and "Flags" (for each
  flag the count of the runs where it is true or above 0, and at most FLAG_IDS run ids). The tables give the arms in
  the order of `runner.ARMS` (C, P, PS, PF, PFN, PFR, PFL, PFG, PFI, PFS). Numbers: 3 decimals for scores and
  shares, 4 for USD, 1 for seconds and the means of counts, 0 for tokens; `-` for None.

`table` prints one line for each run: question, arm label, model, n, outcome, tp, fp, miss, exact, USD, turns,
seconds, tool calls, IDE calls.

Exit codes: 0 done; 2 the batch folder does not exist, or a key or a run cannot be read.
"""
import argparse
import collections
import json
import math
import os
import random
import re
import sys

from bench import qfiles, runner, score
from common import trees

RUNS = runner.RUNS
SLOTS_FILE = trees.SLOTS_FILE

# The arms whose labels have the base PF too (`paired`), in the order of runner.ARMS.
PF_BASED = ("PFN", "PFR", "PFL", "PFG", "PFI", "PFS")
EXCLUDED = ("invalid", "api_error", "key_leak")       # no measurement: counted, not in any mean
ANSWER_OUTCOMES = ("ok",)                              # the score of run.json counts
FAILED = ("timeout", "budget", "no_answer", "error")   # a run of the agent with no usable answer: f1 0, exact False
# `stopped` runs are only in the adoption table.
ANCHOR_PHRASES = ("No named element at position", "Could not resolve symbol", "Symbol not found in project files",
                  "File not found")
TEXT_TOOLS = ("Grep",)            # plus a Bash call whose command has the word grep, rg, ag or ack
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")
TEXT_COMMAND = re.compile(r"(?<![\w.-])(?:grep|rg|ag|ack)(?![\w.-])")
SYNC_TOOL = "ide_sync_files"
IDE_PREFIX = "mcp__"
SET_ASIDE = re.compile(r"\.(?:invalid|api-error)-[0-9]+$")
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
TEXT_CHARS = 200     # the characters of `text` of an IDE result
ERROR_TEXTS = 5      # the distinct error texts of a run
FLAG_IDS = 10        # the run ids of a flag in summary.md
BOOTSTRAP = (0.025, 0.975)
FLAGS = ("no_plugin_call", "ide_calls", "ide_tools", "ide_error", "anchor_error", "ide_error_texts",
         "has_more_no_cursor", "ide_forbidden_lines", "answer_repeats_ide_forbidden", "ide_missed_required",
         "answer_miss_not_in_ide", "text_after_ide", "edit_then_ide_no_sync", "plugin_wrong_control_right")
MEANS = ("f1", "precision", "recall", "cost_usd", "seconds", "turns", "tool_calls", "ide_calls", "tokens")
PAIRED = ("f1", "exact", "cost_usd", "seconds", "tool_calls")
DIGITS = {"f1": 3, "precision": 3, "recall": 3, "exact": 3, "adoption": 3, "share": 3, "cost_usd": 4,
          "seconds": 1, "turns": 1, "tool_calls": 1, "ide_calls": 1, "tokens": 0}
NAMES = {"cost_usd": "USD", "tool_calls": "tool calls", "ide_calls": "IDE calls"}


# ---------------------------------------------------------------- runs

def arm_label(rec: dict) -> str:
    """The arm part of the run id (`runner.run_id_of`): `C`, `P`, `PS-rule`, `PF`, `P-instructions`, `C-no-tools`,
    `PS-rule-stop-5`, ..."""
    args = argparse.Namespace(question="", model="", n=0, arm=rec["arm"], aid=rec.get("aid"),
                              variant=rec.get("variant"), no_tools=rec.get("no_tools"),
                              stop_after_tools=rec.get("stop_after_tools"), env_scrub=rec.get("env_scrub"))
    return runner.run_id_of(args).split("__")[1]


def load_batch(batch_dir: str) -> dict:
    """{"runs": the run.json records sorted by id, each with "folder" and "question" (module text); "set_aside": n;
    "unfinished": n}."""
    runs, set_aside, unfinished, old_ids = [], 0, 0, None
    for name in sorted(os.listdir(batch_dir)):
        folder = os.path.join(batch_dir, name)
        if not os.path.isdir(folder):
            continue
        if SET_ASIDE.search(name):
            set_aside += 1
            continue
        path = os.path.join(folder, "run.json")
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except FileNotFoundError:
            unfinished += 1
            continue
        except ValueError as e:
            raise ValueError(f"{path}: {e}") from None
        rec["folder"] = folder
        if not rec.get("question"):
            if old_ids is None:
                old_ids = qfiles.by_old_id(qfiles.KEYS)
            rec["question"] = old_ids.get(rec.get("challenge"), rec.get("challenge"))
        runs.append(rec)
    runs.sort(key=lambda r: r["id"])
    return {"runs": runs, "set_aside": set_aside, "unfinished": unfinished}


def _count(tools: dict | None, pred) -> int | None:
    return None if tools is None else sum(n for name, n in tools.items() if pred(name))


def measures(rec: dict) -> dict:
    """f1, precision, recall, exact (module text: None for EXCLUDED and `stopped`), cost_usd, turns, seconds,
    tool_calls (without StructuredOutput), ide_calls and tokens of `usage`."""
    out = dict.fromkeys(("f1", "precision", "recall", "exact"))
    score, outcome = rec.get("score"), rec.get("outcome")
    if outcome in ANSWER_OUTCOMES and score:
        p, r = score["precision"], score["recall"]
        out.update(f1=2 * p * r / (p + r) if score["tp"] else 0.0, precision=p, recall=r, exact=score["exact"])
    elif outcome in FAILED:
        out.update(f1=0.0, precision=0.0, recall=0.0, exact=False)
    tools, usage = rec.get("tools"), rec.get("usage")
    out.update(cost_usd=rec.get("cost_usd"), turns=rec.get("turns"), seconds=rec.get("seconds"),
               tool_calls=_count(tools, lambda name: name != "StructuredOutput"),
               ide_calls=_count(tools, lambda name: name.startswith(IDE_PREFIX)),
               tokens=sum(usage.get(k) or 0 for k in TOKEN_FIELDS) if isinstance(usage, dict) else None)
    return out


# ---------------------------------------------------------------- transcript

def _events(lines):
    """The JSON objects of the lines (str, bytes or already a dict)."""
    for raw in lines:
        event = raw if isinstance(raw, dict) else runner._event(raw)
        if event is not None:
            yield event


def _blocks(event: dict, kind: str) -> list[dict]:
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict) and b.get("type") == kind] if isinstance(content, list) else []


def _calls(lines) -> list[dict]:
    """Each tool use of the transcript in order, one time for each block id (as `runner.parse_transcript` counts
    them): `index`, `name`, `input` and `result` (the tool_result block with the same id, or None)."""
    calls, seen, results = [], set(), {}
    for event in _events(lines):
        inputs = {b.get("id"): b.get("input") for b in _blocks(event, "tool_use")}
        for block_id, name in runner._tool_uses(event):
            if block_id is not None:
                if block_id in seen:
                    continue
                seen.add(block_id)
            calls.append({"index": len(calls), "id": block_id, "name": name, "input": inputs.get(block_id)})
        for block in _blocks(event, "tool_result"):
            results.setdefault(block.get("tool_use_id"), block)
    for call in calls:
        call["result"] = results.get(call["id"]) if call["id"] is not None else None
    return calls


def _tool(name: str) -> str:
    return name.rsplit("__", 1)[-1]


def _text(content) -> str:
    """The text of a tool result: a string, or the joined `text` parts of a list of blocks."""
    if isinstance(content, list):
        return "".join(b["text"] for b in content
                       if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return content if isinstance(content, str) else ""


def _walk(value, sites: set) -> bool:
    """Add each `(file, line)` of the JSON value to `sites`; True when a key `hasMore` has the value true."""
    more = False
    if isinstance(value, dict):
        line = value.get("line")
        if isinstance(value.get("file"), str) and isinstance(line, int) and not isinstance(line, bool):
            sites.add((value["file"], line))
        more = value.get("hasMore") is True
        for item in value.values():
            more = _walk(item, sites) or more
    elif isinstance(value, list):
        for item in value:
            more = _walk(item, sites) or more
    return more


def _ide_result(call: dict) -> dict:
    out = {"tool": _tool(call["name"]), "input": call["input"], "is_error": None, "sites": set(), "has_more": False,
           "text": None, "index": call["index"], "error": None}
    block = call["result"]
    if block is None:
        return out
    text = _text(block.get("content"))
    out["is_error"] = block.get("is_error") is True
    try:
        value = json.loads(text)
    except ValueError:
        out["text"] = text[:TEXT_CHARS]
        return out
    out["has_more"] = _walk(value, out["sites"])
    if isinstance(value, dict) and isinstance(value.get("error"), str):
        out["error"] = value["error"]
    if out["is_error"] or out["error"] is not None:
        out["text"] = text[:TEXT_CHARS]
    return out


def ide_results(lines) -> list[dict]:
    """One dict for each IDE tool use (`mcp__<server>__<tool>`), in order: `tool`, `input`, `is_error` (None with no
    result), `sites` (the raw `(file, line)` of the result JSON), `has_more`, `text` (the first TEXT_CHARS characters
    of a result that is no JSON, is an error or has a str `error` in its JSON; else None), `index` (among all tool
    uses, 0-based) and `error` (the str `error` of the result JSON, or None)."""
    return [_ide_result(call) for call in _calls(lines) if call["name"].startswith(IDE_PREFIX)]


# ---------------------------------------------------------------- flags

def _site_of(site: tuple[str, int], prefix: str | None) -> tuple[str, int]:
    """The site relative to the root (`score._site`, as parse_sites reads an answer entry), or as it is."""
    if prefix is None:
        return site
    return score._site(f"{site[0]}:{site[1]}", prefix) or site


def _answer(rec: dict) -> set[tuple[str, int]]:
    out = set()
    for entry in rec.get("answer") or []:
        path, _, line = entry.rpartition(":")
        out.add((path, int(line)))
    return out


def _text_search(call: dict) -> bool:
    if call["name"] in TEXT_TOOLS:
        return True
    command = call["input"].get("command") if isinstance(call["input"], dict) else None
    return call["name"] == "Bash" and isinstance(command, str) and TEXT_COMMAND.search(command) is not None


def _edit_then_ide(calls: list[dict]) -> int:
    count, edited = 0, False
    for call in calls:
        if call["name"] in EDIT_TOOLS:
            edited = True
        elif call["name"].startswith(IDE_PREFIX):
            if _tool(call["name"]) == SYNC_TOOL:
                edited = False
            elif edited:
                count += 1
    return count


def _has_cursor(result: dict) -> bool:
    return isinstance(result["input"], dict) and "cursor" in result["input"]


def flags(rec: dict, lines, proxy_lines, key, root: str | None = None) -> dict:
    """The flags of one run (spec 6.8; each value a count unless the name says more): `lines` are the transcript
    lines, `proxy_lines` the proxy log lines (str, bytes or dicts), `key` the tracked key of the question and `root`
    the tree root of the question (None: no site path changes)."""
    calls = _calls(lines)
    ide = [_ide_result(call) for call in calls if call["name"].startswith(IDE_PREFIX)]
    prefix = root.rstrip("/") + "/" if root else None
    listed = {_site_of(site, prefix) for result in ide for site in result["sites"]}
    classes = score.line_classes(key)
    answer = _answer(rec)
    ide_calls = measures(rec)["ide_calls"] or 0
    tools = collections.Counter()
    for name, n in (rec.get("tools") or {}).items():
        if name.startswith(IDE_PREFIX):
            tools[_tool(name)] += n
    errors = [result for result in ide if result["is_error"]]
    refused = sum(1 for line in _events(proxy_lines)
                  if line.get("method") == "tools/call" and line.get("refused") is True)
    forbidden = {site for site in listed if classes.get(site) == "forbidden"}
    missed = ({site for site, cls in classes.items() if cls == "required" and site not in listed}
              if ide_calls else set())
    first = ide[0]["index"] if ide else None
    return {
        "no_plugin_call": rec.get("arm") in runner.PLUGIN_ARMS and rec.get("outcome") not in EXCLUDED and not ide_calls,
        "ide_calls": ide_calls,
        "ide_tools": dict(tools),
        "ide_error": len(errors) + refused,
        "anchor_error": sum(1 for result in ide if (result["is_error"] or result["error"] is not None)
                            and any(phrase in (result["text"] or "") for phrase in ANCHOR_PHRASES)),
        "ide_error_texts": list(dict.fromkeys(result["text"] for result in errors))[:ERROR_TEXTS],
        "has_more_no_cursor": sum(1 for result in ide if result["has_more"] and not any(
            _has_cursor(later) for later in ide if later["index"] > result["index"])),
        "ide_forbidden_lines": forbidden,
        "answer_repeats_ide_forbidden": len(forbidden & answer),
        "ide_missed_required": missed,
        "answer_miss_not_in_ide": len(missed - answer),
        "text_after_ide": 0 if first is None else sum(1 for call in calls
                                                      if call["index"] > first and _text_search(call)),
        "edit_then_ide_no_sync": _edit_then_ide(calls),
    }


def _decided(rec: dict) -> bool:
    return rec.get("outcome") in ANSWER_OUTCOMES + FAILED


def batch_flags(records: list[dict]) -> None:
    """Add `plugin_wrong_control_right` to each record: a plugin arm run with an ANSWER or FAILED outcome is not
    exact, and the same question and model has C runs (label `C`) with an ANSWER or FAILED outcome, each exact."""
    control: dict[tuple, list] = {}
    for rec in records:
        if arm_label(rec) == "C" and _decided(rec):
            control.setdefault((rec["question"], rec["model"]), []).append(measures(rec)["exact"])
    for rec in records:
        c = control.get((rec["question"], rec["model"]))
        rec["plugin_wrong_control_right"] = bool(rec.get("arm") in runner.PLUGIN_ARMS and _decided(rec)
                                                 and measures(rec)["exact"] is False and c and all(c))


# ---------------------------------------------------------------- tables

def _mean(values) -> float | None:
    values = [float(v) for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _plugin_label(label: str) -> bool:
    return label.split("-", 1)[0] in runner.PLUGIN_ARMS


def _arm_order(label: str) -> tuple:
    """The sort key of an arm label: the arm in the order of runner.ARMS (C, P, PS, PF, PFN, PFR, PFL, PFG, PFI,
    PFS), then the label."""
    return runner.ARMS.index(label.split("-", 1)[0]), label


def summary_rows(records) -> list[dict]:
    """One row for each (question, model, arm label), over the runs that are not EXCLUDED and not `stopped`: `runs`,
    `outcomes`, the means of MEANS, the share `exact`, `adoption` (plugin arms: the share of runs with an IDE call;
    else None) and `excluded` (the count of EXCLUDED runs)."""
    groups: dict[tuple, list] = {}
    for rec in records:
        if rec.get("outcome") != "stopped":
            groups.setdefault((rec["question"], rec["model"], arm_label(rec)), []).append(rec)
    rows = []
    for (question, model, label), recs in sorted(groups.items(), key=lambda g: (g[0][:2], _arm_order(g[0][2]))):
        counted = [rec for rec in recs if rec.get("outcome") not in EXCLUDED]
        ms = [measures(rec) for rec in counted]
        row = {"question": question, "model": model, "arm_label": label, "runs": len(counted),
               "outcomes": dict(sorted(collections.Counter(rec["outcome"] for rec in counted).items()))}
        row.update({k: _mean(m[k] for m in ms) for k in MEANS[:3]})
        row["exact"] = _mean(m["exact"] for m in ms)
        row.update({k: _mean(m[k] for m in ms) for k in MEANS[3:]})
        row["adoption"] = _mean([(m["ide_calls"] or 0) > 0 for m in ms]) if _plugin_label(label) else None
        row["excluded"] = len(recs) - len(counted)
        rows.append(row)
    return rows


def paired(records) -> list[dict]:
    """One row for each (model, plugin arm label, base label, question) where the arm and the base both have a run
    that is not EXCLUDED and not `stopped`. The base of each plugin arm label is `C`; a label whose arm is in
    PF_BASED (`PFN<rest>`, `PFR<rest>`, `PFL<rest>`, `PFG<rest>`, `PFI<rest>` or `PFS<rest>`) also has the base
    `PF<rest>`. For each PAIRED measure: `<m>_arm`, `<m>_base` (the means) and `<m>_diff` (arm - base)."""
    rows = {(r["question"], r["model"], r["arm_label"]): r for r in summary_rows(records) if r["runs"]}
    out = []
    for (question, model, label), row in rows.items():
        if not _plugin_label(label):
            continue
        pf_base = label.split("-", 1)[0] in PF_BASED
        for base_label in ["C"] + (["PF" + label[3:]] if pf_base else []):
            base = rows.get((question, model, base_label))
            if base is None:
                continue
            item = {"model": model, "arm_label": label, "base_label": base_label, "question": question}
            for k in PAIRED:
                a, b = row[k], base[k]
                item.update({f"{k}_arm": a, f"{k}_base": b, f"{k}_diff": None if a is None or b is None else a - b})
            out.append(item)
    return sorted(out, key=lambda r: (r["model"], _arm_order(r["arm_label"]), _arm_order(r["base_label"]),
                                      r["question"]))


def bootstrap(values: list[float], seed: int = 1, n: int = 10000) -> tuple[float, float, float]:
    """The mean of `values` (one difference for each question) and the 2.5 % and 97.5 % percentiles (nearest rank)
    of the means of `n` resamples with replacement (`random.Random(seed)`). Fewer than 2 values: no interval."""
    if not values:
        return None, None, None
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, None, None
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(n))
    low, high = (means[max(math.ceil(q * n), 1) - 1] for q in BOOTSTRAP)
    return mean, low, high


def adoption_rows(records) -> list[dict]:
    """One row for each (plugin arm label, model), over the runs that are not EXCLUDED (`stopped` included): `runs`,
    `ide_first` (the runs with an IDE tool in `first_tools`) and `share`."""
    groups: dict[tuple, list] = {}
    for rec in records:
        if rec.get("arm") in runner.PLUGIN_ARMS and rec.get("outcome") not in EXCLUDED:
            groups.setdefault((arm_label(rec), rec["model"]), []).append(rec)
    rows = []
    for (label, model), recs in sorted(groups.items(), key=lambda g: (_arm_order(g[0][0]), g[0][1])):
        hits = sum(1 for rec in recs if any(str(name).startswith(IDE_PREFIX) for name in rec.get("first_tools") or []))
        rows.append({"arm_label": label, "model": model, "runs": len(recs), "ide_first": hits,
                     "share": hits / len(recs)})
    return rows


# ---------------------------------------------------------------- report

def _fmt(value, key: str) -> str:
    return "-" if value is None else f"{value:.{DIGITS[key]}f}"


def _raw(value) -> str:
    return "-" if value is None else str(value)


def _md(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(row) + " |" for row in rows])


def _plain(value):
    """A set of sites as a sorted list of `path:line`."""
    if isinstance(value, set):
        return [f"{path}:{line}" for path, line in sorted(value)]
    return value


def _flagged(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    return bool(value)


def _batch_section(batch: dict) -> str:
    runs = batch["runs"]
    rows = [[outcome, str(n)] for outcome, n in sorted(collections.Counter(r.get("outcome") for r in runs).items())]
    rows += [["runs", str(len(runs))], ["set aside", str(batch["set_aside"])],
             ["unfinished", str(batch["unfinished"])],
             ["total cost (USD)", _fmt(sum(r.get("cost_usd") or 0 for r in runs), "cost_usd")]]
    return _md(["outcome", "runs"], rows)


def _summary_section(records) -> str:
    header = (["question", "model", "arm", "runs", "outcomes", "f1", "precision", "recall", "exact"]
              + [NAMES.get(k, k) for k in MEANS[3:]] + ["adoption", "excluded"])
    rows = [[f"`{r['question']}`", r["model"], r["arm_label"], str(r["runs"]),
             ", ".join(f"{k} {n}" for k, n in r["outcomes"].items()) or "-"]
            + [_fmt(r[k], k) for k in ("f1", "precision", "recall", "exact") + MEANS[3:] + ("adoption",)]
            + [str(r["excluded"])] for r in summary_rows(records)]
    return _md(header, rows)


def _paired_section(records) -> str:
    sides = ("arm", "base", "diff")
    header = ["model", "arm", "base", "question"] + [f"{NAMES.get(k, k)} {side}" for k in PAIRED for side in sides]
    groups: dict[tuple, list] = {}
    for row in paired(records):
        groups.setdefault((row["model"], row["arm_label"], row["base_label"]), []).append(row)
    rows = []
    for (model, label, base), group in groups.items():
        rows += [[model, label, base, f"`{r['question']}`"]
                 + [_fmt(r[f"{k}_{side}"], k) for k in PAIRED for side in sides] for r in group]
        line = [model, label, base, "all"]
        for k in PAIRED:
            mean, low, high = bootstrap([r[f"{k}_diff"] for r in group if r[f"{k}_diff"] is not None])
            line += [_fmt(_mean(r[f"{k}_arm"] for r in group), k), _fmt(_mean(r[f"{k}_base"] for r in group), k),
                     _fmt(mean, k) + ("" if low is None else f" [{_fmt(low, k)}, {_fmt(high, k)}]")]
        rows.append(line)
    return _md(header, rows)


def _adoption_section(records) -> str:
    return _md(["arm", "model", "runs", "IDE tool in first_tools", "share"],
               [[r["arm_label"], r["model"], str(r["runs"]), str(r["ide_first"]), _fmt(r["share"], "share")]
                for r in adoption_rows(records)])


def _flags_section(rows: list[dict]) -> str:
    out = []
    for flag in FLAGS:
        ids = [row["id"] for row in rows if _flagged(row[flag])]
        shown = ", ".join(f"`{i}`" for i in ids[:FLAG_IDS]) + (", ..." if len(ids) > FLAG_IDS else "")
        out.append([flag, str(len(ids)), shown or "-"])
    return _md(["flag", "runs", f"ids (at most {FLAG_IDS})"], out)


def report(batch_dir: str, out_dir: str) -> str:
    """Write `<out_dir>/runs.jsonl` and `<out_dir>/summary.md` (module text); return the path of summary.md."""
    batch = load_batch(batch_dir)
    slots = trees.load_slots(SLOTS_FILE)
    tracked, run_flags = {}, []
    for rec in batch["runs"]:
        name = rec["question"]
        if name not in tracked:
            try:
                tracked[name] = qfiles.load_key(name, qfiles.KEYS)
            except FileNotFoundError:
                raise ValueError(f"{qfiles.KEYS}: no key of the question {name!r} (run {rec['id']})") from None
        key = tracked[name]
        try:
            with open(os.path.join(rec["folder"], "transcript.jsonl"), "rb") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []
        proxy_lines = runner._read_jsonl(os.path.join(rec["folder"], "proxy.jsonl"))
        run_flags.append(flags(rec, lines, proxy_lines, key, (slots.get(key["tree"]) or {}).get("path")))
    batch_flags(batch["runs"])
    rows = []
    for rec, rec_flags in zip(batch["runs"], run_flags):
        rows.append({"id": rec["id"], "question": rec["question"], "model": rec["model"], "arm_label": arm_label(rec),
                     "n": rec.get("n"), "outcome": rec.get("outcome"), **measures(rec), **rec_flags,
                     "plugin_wrong_control_right": rec["plugin_wrong_control_right"]})
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "runs.jsonl"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps({k: _plain(v) for k, v in row.items()}, ensure_ascii=False) + "\n")
    records = batch["runs"]
    text = "\n\n".join([
        f"# Triage of the batch `{os.path.basename(os.path.normpath(batch_dir))}`",
        f"Batch folder `{batch_dir}`.",
        "## Batch", _batch_section(batch),
        "## By question, model and arm", _summary_section(records),
        "## Paired differences",
        "Arm - base, for each question of a model, an arm and a base. The base is C for each plugin arm, and also PF "
        "for PFN, PFR, PFL, PFG, PFI and PFS. The line `all`: the means over the questions; each difference with its "
        "bootstrap mean and 95 % interval over the questions.",
        _paired_section(records),
        "## Adoption", _adoption_section(records),
        "## Flags", _flags_section(rows)]) + "\n"
    path = os.path.join(out_dir, "summary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _table_lines(records: list[dict]) -> list[str]:
    rows = [["question", "arm", "model", "n", "outcome", "tp", "fp", "miss", "exact", "USD", "turns", "seconds",
             "tools", "IDE"]]
    for rec in records:
        score, m = rec.get("score") or {}, measures(rec)
        rows.append([rec["question"], arm_label(rec), rec["model"], _raw(rec.get("n")), _raw(rec.get("outcome"))]
                    + [_raw(score.get(k)) for k in ("tp", "fp", "miss", "exact")]
                    + [_fmt(rec.get("cost_usd"), "cost_usd"), _raw(rec.get("turns")),
                       _fmt(rec.get("seconds"), "seconds"), _raw(m["tool_calls"]), _raw(m["ide_calls"])])
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return ["  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip() for row in rows]


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m bench.triage", description=__doc__.splitlines()[0],
                                     allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="write runs.jsonl and summary.md", allow_abbrev=False)
    rep.add_argument("-batch", required=True, help="the folder below RUNS")
    rep.add_argument("-out", help="output folder (default: RUNS/<batch>.triage)")
    tab = sub.add_parser("table", help="print one line for each run", allow_abbrev=False)
    tab.add_argument("-batch", required=True, help="the folder below RUNS")
    args = parser.parse_args(argv)
    batch_dir = os.path.join(RUNS, args.batch)
    if not os.path.isdir(batch_dir):
        print(f"triage: {batch_dir}: no batch folder", file=sys.stderr)
        return 2
    try:
        if args.command == "table":
            for line in _table_lines(load_batch(batch_dir)["runs"]):
                print(line)
            return 0
        path = report(batch_dir, args.out or os.path.join(RUNS, args.batch + ".triage"))
    except (OSError, ValueError, KeyError) as e:
        print(f"triage: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
