"""The tracked batch plans of the agent benchmark: load, check and expand a plan.

    python3 -m bench.planfile check <plan> ...      (run from live-test)

A plan is a JSON object with the fields FIELDS, for example

    {"rule": "<one sentence: how the questions were chosen>",
     "questions": ["caddy-impls-validator"],
     "arms": [{"arm": "C"}, {"arm": "PS", "aid": "skill"}],
     "models": ["claude-haiku-5-5"],
     "runs": 1}

`load` reads PLANS/<name>.json for a name with no `/`, else the path. An arm entry has the key `arm` (an arm of
`runner.ARMS`) and can have `aid` (of `runner.AIDS`) and `variant` (of `runner.VARIANTS`). `problems` gives each
problem of a plan: a missing or unknown key, a `rule` with no text, a list (`questions`, `arms`, `models`) that is
empty or holds an item two times, a question that is not in `qfiles.names()`, a bad arm entry, a model that is no
text, and `runs` that is no whole number of 1 or more. `expand` gives the run lines of a valid plan: question x model
x arm entry x run number `n` in 1..`runs`, in this order. A run line is `{"question", "arm", "model", "n"}` and the
other keys of the arm entry: the options of `runner run` (`runner batch` runs them).

`check` prints `<plan>: <n> runs` for each valid plan and `<plan>: <problem>` for each problem of another plan, then
the count of the problems. It exits 1 when a plan has a problem.
"""
import argparse
import json
import os
import sys

from bench import qfiles, runner

PLANS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plans")
FIELDS = ("rule", "questions", "arms", "models", "runs")
ARM_FIELDS = ("arm", "aid", "variant")
LISTS = (("questions", "question names"), ("arms", "arm entries"), ("models", "model names"))


def load(path_or_name: str) -> dict:
    """The plan of the file (module text). OSError when there is no file, ValueError when it is no JSON."""
    path = path_or_name if "/" in path_or_name else os.path.join(PLANS, path_or_name + ".json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _arm_problems(entry) -> list[str]:
    if not isinstance(entry, dict) or "arm" not in entry:
        return [f"arms: {entry!r} is no object with the key arm"]
    out = [f"arms: unknown key {k!r} in {entry!r}" for k in entry if k not in ARM_FIELDS]
    for key, known in (("arm", runner.ARMS), ("aid", runner.AIDS), ("variant", runner.VARIANTS)):
        if key in entry and entry[key] not in known:
            out.append(f"arms: unknown {key} {entry[key]!r}")
    return out


def problems(plan: dict) -> list[str]:
    """The problems of the plan (module text); [] for a valid plan."""
    if not isinstance(plan, dict):
        return ["the plan is no JSON object"]
    out = [f"unknown key {k!r}" for k in plan if k not in FIELDS]
    out += [f"no key {k!r}" for k in FIELDS if k not in plan]
    if "rule" in plan and (not isinstance(plan["rule"], str) or not plan["rule"].strip()):
        out.append("rule: no sentence")
    for field, kind in LISTS:
        if field not in plan:
            continue
        items = plan[field]
        if not isinstance(items, list) or not items:
            out.append(f"{field}: no list of one or more {kind}")
            continue
        out += [f"{field}: {item!r} is two times in the list" for k, item in enumerate(items) if item in items[:k]]
        if field == "questions":
            names = set(qfiles.names(qfiles.KEYS))
            out += [f"questions: unknown question {q!r}" for q in items if not isinstance(q, str) or q not in names]
        elif field == "arms":
            out += [problem for entry in items for problem in _arm_problems(entry)]
        else:
            out += [f"models: {m!r} is no model name" for m in items if not isinstance(m, str) or not m]
    runs = plan.get("runs", 1)
    if not isinstance(runs, int) or isinstance(runs, bool) or runs < 1:
        out.append(f"runs {runs!r}: use a whole number of 1 or more")
    return out


def expand(plan: dict) -> list[dict]:
    """The run lines of a valid plan (module text)."""
    return [{"question": question, "arm": entry["arm"], "model": model, "n": n,
             **{k: v for k, v in entry.items() if k != "arm"}}
            for question in plan["questions"] for model in plan["models"] for entry in plan["arms"]
            for n in range(1, plan["runs"] + 1)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m bench.planfile", description=__doc__.splitlines()[0],
                                     allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    chk = sub.add_parser("check", help="print the run count of each plan and its problems", allow_abbrev=False)
    chk.add_argument("plans", nargs="+", help="a plan name (bench/plans/<name>.json) or the path of a plan file")
    args = parser.parse_args(argv)
    count = 0
    for name in args.plans:
        try:
            plan = load(name)
        except (OSError, ValueError) as e:
            found = [f"no plan ({type(e).__name__}: {e})"]
        else:
            found = problems(plan)
        for problem in found:
            print(f"{name}: {problem}")
        if not found:
            print(f"{name}: {len(expand(plan))} runs")
        count += len(found)
    print(f"{count} problem{'' if count == 1 else 's'}")
    return 1 if count else 0


if __name__ == "__main__":
    sys.exit(main())
