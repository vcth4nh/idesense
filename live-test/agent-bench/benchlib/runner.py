"""One run of the agent benchmark: Claude Code in print mode in a product container answers one challenge.

    python3 -m benchlib.runner run -set <file> -challenge <id> -arm <C|P|PS|PF|PFN|PFR|PFL|PFG|PFI|PFS>
        -model <model> -batch <name> [-aid skill|rule] [-variant instructions|no-tool-search|guide]
        [-stop-after-tools N] [-no-tools] [-env-scrub] [-n <run number>] [-dry-run]  (run from live-test/agent-bench)
    python3 -m benchlib.runner batch -plan <jsonl> -batch <name> [-jobs 2] [-seed 1]
    python3 -m benchlib.runner handshake -product <caddy|beets>

Arms: `C` has no MCP server. `P` has the MCP server of the IDE of the product, through a route of the filter
proxy (`benchlib.proxy`). `PS` is `P` with an aid (`-aid skill` or `-aid rule`, installed by the entry script of
the image). `PF` is `P` with the sentence PF_SENTENCE as its own paragraph before the answer paragraph of the
prompt. `PFN` is `PF`, and its route has the notes of NOTES_FILE for the language of the product (LANGS): the
proxy appends the note of a tool to the `notes` of each result of that tool. `PFR` and `PFL` are `PF`, and their
route has the additions of the challenge (`route_additions`): the proxy adds the name-only rows of ADDITIONS_FILE to
a result of ADDITION_TOOL for the target declaration, and appends the note ADDITION_NOTES of the form. `PFR`
(form `rows`) adds them to `usages`, each with `"match": "DYNAMIC"`. `PFL` (form `field`) puts them in the list
ADDITION_FIELD, and `usages` stays. ADDITIONS_FILE is `{"<challenge id>": {"name": "<attribute name>", "known":
[[file, line], ...], "rows": [<row object>, ...]}}`. `known` holds the positions of the rows that the IDE gives for
the target declaration. A row object has `file`, `line`, `column`, `preview`, `usageType` and `enclosingScope`, and
never `match`. With no usable entry for the challenge, a `PFR` or `PFL` run does not start. `PFG` is `PF` with
PFG_SENTENCE after PF_SENTENCE in the same paragraph, and its route has no notes and no additions. `PFI` is `PF`, and
its route has the note PFG_SENTENCE for ADDITION_TOOL, with no read of NOTES_FILE and no additions. `PFS` is `PF`
with PFS_SENTENCE after PF_SENTENCE in the same paragraph, and its route has no notes and no additions. `-no-tools`
(arm C only) adds `--tools ""` (the memory probe). `-variant instructions` gives the route the text INSTRUCTIONS;
`-variant no-tool-search` sets `ENABLE_TOOL_SEARCH=false` (arms P, PS and PF). `-variant guide` (arms P, PS and PF)
gives the route the text GUIDE_INSTRUCTIONS and changes no other part of the run. `-stop-after-tools N` kills the
container after the N-th `tool_use` block that is not a block of `StructuredOutput` (the adoption probe).
`-env-scrub` (each arm; default off) sets `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`: Claude Code removes credentials
such as ANTHROPIC_API_KEY from the environment of Bash. Claude Code 2.1.326 needs bubblewrap for it.

The root of a run is the slot path of the tree (`trees.load_slots()`, plan amendment A4): the root of the prompt,
the project of the route and the slot that the entry script keeps (`BENCH_SLOT`). The image is the image id of
`IMAGES/<product>.json` (amendment A2: `id`, `server_name`, `slots`); its slot of the tree must equal the slot of
`slots.json`. The docker command: `docker run` with CONTAINER_FLAGS, `--name run-<hex>`, `-e BENCH_SLOT=<slot id>`,
`-e BENCH_AID=<aid or none>`, `-e ANTHROPIC_API_KEY` (the name only: the value is in the environment of the docker
process and never in a command line or a file), the image id, then the arguments of `claude` (CLAUDE_FLAGS). A plugin
arm adds `--mcp-config {"mcpServers": {"<server name>": {"type": "http", "url": "<route url>"}}}`. The route entry
(`proxy.add_route`) has the run, the IDE URL as upstream, the root as project, the instructions, the notes and the
additions of the run. `-dry-run` prints this command as a JSON list, and on stderr one line with the run id, the
arm, the tools of the route notes, and the form and the row count of the route additions. It does nothing else; it
does not read the key.

Run id `<challenge>__<arm>[-<aid>][-<variant>][-no-tools][-stop-<N>][-scrub]__<model>__<n>`, run folder
`RUNS/<batch>/<run id>/` with `transcript.jsonl` (the stdout of the container), `stderr.txt`, `proxy.jsonl` (the
proxy log lines of the route of the run; empty for arm C) and `run.json` (RUN_FIELDS). `run.json` comes last: a
folder with `run.json` holds a finished run, and `run` refuses it.

Guards of each run, in this order:
- a plugin arm needs an answer from the proxy at HEALTH_URL; with no answer `run` exits 2 and starts nothing;
- the key file KEY_FILE (`read_key`); a bad key file exits 2;
- the IDE of the product (direct, not through the proxy): `serverInfo.version` must be PLUGIN_VERSION and
  `ide_index_status` must say smart mode (`audit.wait_ready`, up to READY_TIMEOUT s); else the outcome is
  `invalid` and no container starts;
- the wall-clock limit WALL_LIMIT: the runner kills the container (`docker kill`), the outcome is `timeout`;
- the MCP servers of the init event (`mcp_status`): a plugin arm needs its server with the status CONNECTED, and
  arm C needs an empty list; else the outcome is `invalid` (not for `stopped`, `timeout` and `api_error`). With no
  init event or no `mcp_servers` list, `mcp_status` is null and the outcome does not change;
- after the run: the IDE version and the smart mode again, a proxy log line with status 502 (upstream failure,
  for example an IDE restart) or another `server_version`; each one makes the outcome `invalid` (not for
  `api_error`);
- the key search (`search_key`) in `transcript.jsonl`, `stderr.txt`, `proxy.jsonl` and the text of `run.json`.
  A hit deletes the three files, sets the outcome `key_leak`, keeps only metadata, cost and turns in `run.json`,
  and exits 9. No message names the key;
- the leak words LEAK_WORDS in `transcript.jsonl` (amendment A4): `leak_words` holds the count of each one. A hit
  is no failure.

Outcome: `key_leak`; `invalid` (see above); `timeout`; `stopped` (`-stop-after-tools`); `api_error` (the result
event has the terminal reason `api_error`: the API refused or failed, for example with no key or a revoked key; the
run is no measurement); `budget` (the result event has the subtype `error_max_budget_usd` or the terminal reason
`budget_exhausted`); `no_answer` (no result event, the subtype `error_max_structured_output_retries`, or no readable
`structured_output`); `error` (a result event with `is_error` true or another error subtype, a docker exit code of
DOCKER_ERRORS with no result event, or an exception of the runner); else `ok`. The reason of `error` and
`api_error`: the exception of the runner, else `<subtype> / <terminal_reason> / <api_error_status>: <the first
RESULT_TEXT characters of the result text>` (`-` for a missing part), else (no result event) the docker exit code.
The answer is read only from a result event with the subtype `success` and
`is_error` false: `challenges.parse_sites(structured_output, root)`; `answer` is the sorted site list, `invalid` the
entries that cannot be read, and `score` is `challenges.score_answer`.

The transcript parser (`parse_transcript`) reads the stream-json events of Claude Code: of a `result` event (the last
one) `subtype`, `is_error`, `terminal_reason`, `total_cost_usd`, `num_turns`, `usage`, `modelUsage` and
`structured_output`; of an `assistant` event (also of a subagent) the `tool_use` blocks of `message.content`, with
their `id` and `name`, one time for each block id; of the first `system` event with the subtype `init` the
`name` and `status` of each entry of `mcp_servers`. A tool name stays as the transcript has it (an IDE tool is
`mcp__<server name>__<tool>`; `ToolSearch` and `StructuredOutput` are counted too). A line that is no JSON object and
an event of another type are skipped.

Exit codes of `run`: 0 when `run.json` is written (also with the outcome `invalid`), 1 for the outcome `error`, 2
when no run starts, 9 for a key leak, and
3: the API refused or failed; the run is no measurement (the outcome `api_error`; `run.json` is written).

`batch`: each plan line is a JSON object with the options of `run` without the dash, for example
`{"set": "<file>", "challenge": "caddy-refs-CA", "arm": "PS", "aid": "skill", "model": "claude-opus-5-5", "n": 1}`
(a flag option has the value true). The runs of one challenge and one model are neighbours, in a random order
(`-seed`); the groups keep the order of their first plan line. A run whose folder has `run.json` is skipped, except
a record with the outcome `api_error` that a single `run` left: that folder moves to `<run id>.api-error-<k>/`. A run
with the outcome `invalid` moves to `<run id>.invalid-<k>/` and runs again one time (a second `invalid` run stays). A
run with the exit code 3 (`api_error`) moves to `<run id>.api-error-<k>/` and runs again one time; when the second
try also gives 3, its folder moves too and the batch stops with 3. So an `api_error` run never leaves `run.json` in
its run folder, and the next start of the batch does it again. A run with the exit code 9 (key leak) or 2 (no run
starts, for example the proxy is down) stops the batch too. A stop means: no new run starts, also no second try; a
run of another worker ends normally. The exit code of the batch: 9 before 3, 3 before 2. `-jobs` runs go at the
same time.

`handshake`: with no key, a container of the product image runs `claude mcp add --transport http <server name>
<route url>` and `claude mcp list` (the entry point is `/bin/bash`, so the entry script does not run). It prints
the output and the proxy log lines of the route, and exits 0 when the log has an `initialize` with the status 200.
"""
import argparse
import collections
import datetime
import http.client
import json
import os
import random
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse

from benchlib import audit, challenges, mcp, proxy, trees

BENCH = "/home/ubuntu/dev/idesense-bench"
RUNS = os.path.join(BENCH, "runs")
IMAGES = os.path.join(BENCH, "images")
ROUTES_FILE = os.path.join(BENCH, "proxy", "routes.json")
PROXY_LOG_DIR = os.path.join(BENCH, "proxy", "log")
SLOTS_FILE = trees.SLOTS_FILE
KEY_FILE = "/home/ubuntu/dev/idesense/.local/.api-keys/vcth4nh"
NOTES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "notes.json")

PLUGIN_VERSION = "2.1.1-bench.f4ff0a2"
IDE_URLS = {"caddy": "http://127.0.0.1:29374/mcp/streamable-http",
            "beets": "http://127.0.0.1:29372/mcp/streamable-http"}
LANGS = {"caddy": "go", "beets": "python"}  # the language of a product: its key in NOTES_FILE
HEALTH_URL = "http://172.17.0.1:29380/health"
READY_TIMEOUT = audit.READY_TIMEOUT
WALL_LIMIT = 30 * 60
HANDSHAKE_LIMIT = 120

ARMS = ("C", "P", "PS", "PF", "PFN", "PFR", "PFL", "PFG", "PFI", "PFS")
PLUGIN_ARMS = ("P", "PS", "PF", "PFN", "PFR", "PFL", "PFG", "PFI", "PFS")
PF_ARMS = ("PF", "PFN", "PFR", "PFL", "PFG", "PFI", "PFS")   # the arms with PF_SENTENCE in the prompt
ADDITIONS_FILE = os.path.join(BENCH, "additions.json")
ADDITION_TOOL = "ide_find_usages"
ADDITION_FORMS = {"PFR": "rows", "PFL": "field"}
ADDITION_FIELD = "nameOnlyMatches"
ADDITION_NOTES = {
    "rows": ("{n} rows of `usages` have `match` = `DYNAMIC` and come from the name only: each is an attribute "
             "`{name}` on a value whose type does not declare `{name}`, so the declaration that the row refers to "
             "is not known. Read the code at each of these rows before you count it."),
    "field": ("`nameOnlyMatches` holds {n} lines that are not in `usages` and come from the name only: each is an "
              "attribute `{name}` on a value whose type does not declare `{name}`, so the declaration that the "
              "line refers to is not known. Read the code at each of these lines before you count it."),
}
AIDS = ("skill", "rule")
VARIANTS = ("instructions", "no-tool-search", "guide")
# The container flags of the plan (Global Constraints). No mount, no volume, no host network, no Docker socket.
CONTAINER_FLAGS = ["--rm", "--user", "1000:1000", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--memory", "6g", "--cpus", "4", "--pids-limit", "1024", "--network", "bridge"]
DOCKER_ERRORS = (125, 126, 127)  # docker run: the daemon failed, the command cannot run, the command is absent
PF_SENTENCE = 'Use the IDE tools of the MCP server "{server}" for code navigation in this task.'
PFG_SENTENCE = ("A usage list of the IDE holds the references that the IDE can prove, and it can lack a line. "
                "After a usage list, search the text for the name, and check each line that the list does not "
                "hold.")
PFS_SENTENCE = ("A usage list of the IDE can be incomplete: a call on a value with no known type is absent. "
                "A text search for the name finds such calls.")
INSTRUCTIONS = ("This server gives the code analysis of a JetBrains IDE for the open project: find usages, go to "
                "definition, implementations, type and call hierarchies, symbol and file search. Its results come "
                "from the IDE index and resolve names by their meaning, not by their text.")
GUIDE_INSTRUCTIONS = "Use the tools of this server for code navigation in the open project. " + PFG_SENTENCE
LEAK_WORDS = ("idesense-bench", "-plant-", "BENCH_", "/home/ubuntu/dev/idesense/")
RUN_FIELDS = ("id", "challenge", "arm", "aid", "variant", "no_tools", "stop_after_tools", "env_scrub", "model", "n",
              "image_id", "started", "seconds", "plugin_version_start", "plugin_version_end", "outcome", "reason",
              "exit_code", "cost_usd", "turns", "usage", "model_usage", "tools", "first_tools", "mcp_calls",
              "mcp_status", "answer", "invalid", "score", "leak_words")
# The fields of run.json after a key leak: metadata, cost and turns. Each other field is null.
KEPT_AFTER_LEAK = ("id", "challenge", "arm", "aid", "variant", "no_tools", "stop_after_tools", "env_scrub", "model",
                   "n", "image_id", "started", "seconds", "plugin_version_start", "plugin_version_end", "exit_code",
                   "cost_usd", "turns", "leak_words")
# The status of a connected MCP server in `mcp_servers` of the init event (agent-sdk/mcp.md, "Error handling").
CONNECTED = "connected"
# Outcomes that the MCP server check does not change (the IDE check at the end does not change `api_error`).
KEEP_OUTCOME = ("stopped", "timeout", "api_error")
RESULT_TEXT = 200  # the characters of the result text in the reason of `error` and `api_error`
EXIT_CODES_RUN = """exit codes:
  0: run.json is written (also for the outcome invalid)
  1: the outcome error
  2: no run starts
  3: the API refused or failed; the run is no measurement
  9: a key leak; the files of the run are deleted"""
EXIT_CODES_BATCH = """exit codes:
  0: the runs are done
  2: a run could not start; no new run starts
  3: two API errors in one run; no new run starts
  9: a key leak; no new run starts"""
RUN_FILES = ("transcript.jsonl", "stderr.txt", "proxy.jsonl")


class SetupError(Exception):
    """The run cannot start (exit 2)."""


class KeyFileError(Exception):
    """The key file is absent, empty or has more than one line. The message never holds the content."""


def claude_flags(prompt: str, model: str, schema: dict) -> list[str]:
    """The arguments of `claude` of each run (Global Constraints). The prompt comes first, before the options with
    more than one value (`--mcp-config`, `--tools`)."""
    return ["-p", prompt, "--model", model, "--effort", "medium", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence", "--permission-mode", "bypassPermissions", "--max-budget-usd", "20",
            "--json-schema", json.dumps(schema, separators=(",", ":")), "--strict-mcp-config"]


def read_key(path: str | None = None) -> str:
    """The API key: the text of the key file without white space at the two ends."""
    path = path or KEY_FILE
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
    except FileNotFoundError:
        raise KeyFileError(f"{path}: the key file is absent") from None
    except (OSError, UnicodeDecodeError) as e:
        raise KeyFileError(f"{path}: the key file cannot be read ({type(e).__name__})") from None
    if not text:
        raise KeyFileError(f"{path}: the key file is empty")
    if len(text.splitlines()) > 1:
        raise KeyFileError(f"{path}: the key file has more than one line")
    return text


def search_key(paths, key: str) -> list[str]:
    """The paths (of `paths`) whose bytes hold the key. An absent path is no hit."""
    needle = key.encode("utf-8")
    hits = []
    for path in paths:
        try:
            with open(path, "rb") as f:
                if needle in f.read():
                    hits.append(path)
        except FileNotFoundError:
            continue
    return hits


# ---------------------------------------------------------------- transcript parser (stream-json of Claude Code)

def _event(raw) -> dict | None:
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def _tool_uses(event: dict | None) -> list[tuple[str | None, str]]:
    """The (id, name) of each `tool_use` block of an `assistant` event."""
    if not event or event.get("type") != "assistant":
        return []
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [(b.get("id"), b["name"]) for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("name"), str)]


def _mcp_status(event: dict) -> dict | None:
    """{server name: status} of `mcp_servers` of an init event; None when the field is no list."""
    servers = event.get("mcp_servers")
    if not isinstance(servers, list):
        return None
    return {s["name"]: s.get("status") for s in servers if isinstance(s, dict) and isinstance(s.get("name"), str)}


def parse_transcript(lines) -> dict:
    """`result` (the last result event, or None), `tools` ({name: count}), `first_tools` (the first 5 names in
    order) and `mcp_status` (of the first init event; None with no init event or no `mcp_servers` list) of the
    stream-json lines (str or bytes). See the module text."""
    result, names, seen, mcp_status, init = None, [], set(), None, False
    for raw in lines:
        event = _event(raw)
        if event is None:
            continue
        if event.get("type") == "system" and event.get("subtype") == "init" and not init:
            init, mcp_status = True, _mcp_status(event)
        if event.get("type") == "result":
            result = event
        for block_id, name in _tool_uses(event):
            if block_id is not None:
                if block_id in seen:
                    continue
                seen.add(block_id)
            names.append(name)
    return {"result": result, "tools": dict(collections.Counter(names)), "first_tools": names[:5],
            "mcp_status": mcp_status}


def mcp_problem(arm: str, server: str, status: dict | None) -> str | None:
    """Why the MCP servers of the init event do not fit the arm, or None. No list (None) is no problem."""
    if status is None:
        return None
    if arm not in PLUGIN_ARMS:
        return f"arm {arm} has MCP servers in the init event: {status}" if status else None
    if server not in status:
        return f"the MCP server {server} is not in the init event (servers: {sorted(status)})"
    if status[server] != CONNECTED:
        return f"the MCP server {server} has the status {status[server]!r} in the init event"
    return None


def outcome_of(ended: str, exit_code: int | None, result: dict | None, readable: bool) -> str:
    """The outcome of a container run (before the IDE check and the key search)."""
    if ended in ("timeout", "stopped"):
        return ended
    if result is None:
        return "error" if exit_code in DOCKER_ERRORS else "no_answer"
    if result.get("terminal_reason") == "api_error":
        return "api_error"
    if result.get("subtype") == "error_max_budget_usd" or result.get("terminal_reason") == "budget_exhausted":
        return "budget"
    if result.get("subtype") == "error_max_structured_output_retries":
        return "no_answer"
    if result.get("is_error") is True or result.get("subtype") != "success":
        return "error"
    return "ok" if readable else "no_answer"


def result_reason(result: dict | None, exit_code: int | None) -> str:
    """The reason of the outcomes `error` and `api_error`: `<subtype> / <terminal_reason> / <api_error_status>: <the
    first RESULT_TEXT characters of the result text>`, with `-` for a missing part."""
    if result is None:
        return f"no result event; docker exit code {exit_code}"
    part = lambda value: "-" if value is None or value == "" else str(value)
    text = result.get("result")
    return (f"{part(result.get('subtype'))} / {part(result.get('terminal_reason'))} / "
            f"{part(result.get('api_error_status'))}: {text[:RESULT_TEXT] if isinstance(text, str) and text else '-'}")


# ---------------------------------------------------------------- run setup

def run_id_of(args) -> str:
    arm = "-".join([args.arm] + [p for p in (args.aid, args.variant) if p]
                   + (["no-tools"] if args.no_tools else [])
                   + ([f"stop-{args.stop_after_tools}"] if args.stop_after_tools else [])
                   + (["scrub"] if args.env_scrub else []))
    return f"{args.challenge}__{arm}__{args.model}__{args.n}"


def _check_args(args) -> None:
    if args.arm == "PS" and not args.aid:
        raise SetupError("arm PS needs -aid skill or -aid rule")
    if args.aid and args.arm != "PS":
        raise SetupError(f"-aid is for arm PS only, not for arm {args.arm}")
    if args.variant and args.arm not in ("P", "PS", "PF"):
        raise SetupError(f"-variant is for the arms P, PS and PF, not for arm {args.arm}")
    if args.no_tools and args.arm != "C":
        raise SetupError(f"-no-tools is for arm C only, not for arm {args.arm}")
    if args.n < 1:
        raise SetupError(f"-n {args.n}: the run number starts at 1")
    if args.stop_after_tools is not None and args.stop_after_tools < 1:
        raise SetupError(f"-stop-after-tools {args.stop_after_tools}: use 1 or more")
    for name, value in (("batch", args.batch), ("run id", run_id_of(args))):
        if not proxy.RUN_ID.fullmatch(value):
            raise SetupError(f"{name} {value!r}: use only the characters A-Z a-z 0-9 . _ - (first: a letter or digit)")


def load_image(product: str) -> dict:
    path = os.path.join(IMAGES, product + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            image = json.load(f)
    except (OSError, ValueError) as e:
        raise SetupError(f"{path}: no image record ({type(e).__name__}: {e})") from None
    for field in ("id", "server_name"):
        if not isinstance(image.get(field), str):
            raise SetupError(f"{path}: the image record has no `{field}`")
    return image


def image_problem(image: dict, tree: str, slot: dict) -> str | None:
    """Why the image does not hold the slot of the tree (amendment A2), or None."""
    slots = image.get("slots")
    if not isinstance(slots, dict):
        return "the image record has no `slots` (amendment A2)"
    entry = slots.get(tree)
    if not isinstance(entry, dict) or entry.get("slot") != slot["slot"] or entry.get("path") != slot["path"]:
        return f"the image slot of {tree} is {entry!r}, slots.json has {slot!r}"
    return None


def route_notes(product: str) -> dict:
    """The notes of NOTES_FILE for the language of the product: {tool name: text}."""
    try:
        with open(NOTES_FILE, encoding="utf-8") as f:
            notes = json.load(f)
    except (OSError, ValueError) as e:
        raise SetupError(f"{NOTES_FILE}: no note file ({type(e).__name__}: {e})") from None
    texts = notes.get(LANGS.get(product)) if isinstance(notes, dict) else None
    if not isinstance(texts, dict) or not texts:
        raise SetupError(f"{NOTES_FILE}: no notes for the language {LANGS.get(product)!r} of the product {product!r}")
    return texts


def _addition_problem(item) -> str | None:
    """Why the entry of a challenge in ADDITIONS_FILE is not usable, or None."""
    if not isinstance(item, dict):
        return "no entry object"
    if not isinstance(item.get("name"), str) or not item["name"]:
        return "`name` is no text with one or more characters"
    known, rows = item.get("known"), item.get("rows")
    if not isinstance(known, list) or not all(isinstance(p, list) and len(p) == 2 and proxy._is_site(*p)
                                              for p in known):
        return "`known` is no list of [file, line] pairs"
    if not isinstance(rows, list) or not rows or not all(
            isinstance(r, dict) and proxy._is_site(r.get("file"), r.get("line")) for r in rows):
        return "`rows` is no list of one or more objects with a text `file` and an int `line`"
    return None


def route_additions(challenge_id: str, arm: str) -> dict | None:
    """The additions of the route of a run (module text): {ADDITION_TOOL: addition} for an arm of ADDITION_FORMS,
    None for another arm (with no read of ADDITIONS_FILE)."""
    form = ADDITION_FORMS.get(arm)
    if form is None:
        return None
    try:
        with open(ADDITIONS_FILE, encoding="utf-8") as f:
            items = json.load(f)
    except (OSError, ValueError) as e:
        raise SetupError(f"{ADDITIONS_FILE}: no addition file ({type(e).__name__}: {e})") from None
    item = items.get(challenge_id) if isinstance(items, dict) else None
    problem = _addition_problem(item)
    if problem:
        raise SetupError(f"{ADDITIONS_FILE}: the entry of the challenge {challenge_id!r} is not usable: {problem}")
    rows = [{**row, "match": "DYNAMIC"} for row in item["rows"]] if form == "rows" else item["rows"]
    note = ADDITION_NOTES[form].format(n=len(rows), name=item["name"])
    return {ADDITION_TOOL: {"known": item["known"], "rows": rows, "form": form, "field": ADDITION_FIELD,
                            "note": note}}


def pf_prompt(text: str, server: str, after: str | None = None) -> str:
    """The prompt with PF_SENTENCE as its own paragraph before the answer paragraph. With `after`, the paragraph is
    PF_SENTENCE, a space and `after`."""
    head, sep, tail = text.rpartition("\n\n")
    if not sep or tail != challenges.TAIL:
        raise SetupError("the last paragraph of the prompt is not the answer paragraph")
    paragraph = PF_SENTENCE.format(server=server) + (" " + after if after else "")
    return f"{head}\n\n{paragraph}\n\n{tail}"


def prepare(args) -> dict:
    """The parts of a run: challenge, key record, slot, image, prompt, route token and the docker command."""
    _check_args(args)
    matches = [ch for ch in challenges.load(args.set) if ch["id"] == args.challenge]
    if len(matches) != 1:
        raise SetupError(f"{args.set}: {len(matches)} challenges with the id {args.challenge!r}")
    ch = matches[0]
    record = challenges.record_of(ch)
    product, tree = ch["product"], ch["tree"]
    if product not in IDE_URLS:
        raise SetupError(f"no benchmark IDE for the product {product!r}")
    slot = trees.load_slots(SLOTS_FILE).get(tree)
    if not slot:
        raise SetupError(f"{SLOTS_FILE}: no slot for the tree {tree!r}")
    image = load_image(product)
    server, root = image["server_name"], slot["path"]
    text = challenges.prompt(ch, record, root)
    if args.arm in PF_ARMS:
        text = pf_prompt(text, server, {"PFG": PFG_SENTENCE, "PFS": PFS_SENTENCE}.get(args.arm))
    notes = route_notes(product) if args.arm == "PFN" else None
    if args.arm == "PFI":
        notes = {ADDITION_TOOL: PFG_SENTENCE}
    additions = route_additions(ch["id"], args.arm)
    plugin = args.arm in PLUGIN_ARMS
    token = proxy.new_token() if plugin else None
    name = "run-" + secrets.token_hex(6)
    env = ["-e", f"BENCH_SLOT={slot['slot']}", "-e", f"BENCH_AID={args.aid or 'none'}", "-e", "ANTHROPIC_API_KEY"]
    if args.variant == "no-tool-search":
        env += ["-e", "ENABLE_TOOL_SEARCH=false"]
    if args.env_scrub:
        env += ["-e", "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1"]
    cmd = ["docker", "run", *CONTAINER_FLAGS, "--name", name, *env, image["id"],
           *claude_flags(text, args.model, challenges.schema(ch))]
    if plugin:
        config = {"mcpServers": {server: {"type": "http", "url": proxy.route_url(token)}}}
        cmd += ["--mcp-config", json.dumps(config, separators=(",", ":"))]
    if args.no_tools:
        cmd += ["--tools", ""]
    run_id = run_id_of(args)
    return {"run_id": run_id, "folder": os.path.join(RUNS, args.batch, run_id), "ch": ch, "record": record,
            "product": product, "tree": tree, "slot": slot, "root": root, "image": image, "server": server,
            "plugin": plugin, "token": token, "notes": notes, "additions": additions, "name": name, "cmd": cmd,
            "image_problem": image_problem(image, tree, slot)}


# ---------------------------------------------------------------- IDE, proxy and container

def proxy_healthy(url: str = HEALTH_URL, timeout: float = 5.0) -> bool:
    """True when `GET /health` of the proxy gives 200 with `{"ok": true}` (no HTTP proxy of the environment)."""
    parts = urllib.parse.urlsplit(url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
    try:
        conn.request("GET", parts.path or "/")
        resp = conn.getresponse()
        body = json.loads(resp.read())
        return resp.status == 200 and isinstance(body, dict) and body.get("ok") is True
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        conn.close()


def check_ide(url: str, root: str, timeout: float) -> tuple[str | None, str | None]:
    """The plugin version of the IDE, and why the IDE is not ready (None: smart mode). A direct read-only call."""
    client = mcp.McpClient(url, root)
    try:
        version = client.server_version()
    except mcp.McpError as e:
        return None, str(e)
    return version, audit.wait_ready(client, timeout, audit.READY_POLL)


def _ide_problem(version: str | None, reason: str | None, when: str) -> str | None:
    if version != PLUGIN_VERSION:
        return f"plugin version {version!r} at the {when}, expected {PLUGIN_VERSION}" + (f" ({reason})" if reason else "")
    if reason:
        return f"the IDE is not ready at the {when}: {reason}"
    return None


def _proxy_log_problem(lines: list[dict]) -> str | None:
    """An upstream failure (502) or another plugin version in the proxy log lines of the run, or None."""
    for line in lines:
        if line.get("status") == 502:
            return f"the proxy got no answer from the IDE ({line.get('method')} at {line.get('ts')})"
        if line.get("server_version") not in (None, PLUGIN_VERSION):
            return f"the proxy saw the plugin version {line.get('server_version')!r}"
    return None


def _kill(name: str, proc) -> None:
    """Stop the container `name` (with `--rm`, the daemon removes it) and the docker client."""
    try:
        subprocess.run(["docker", "kill", name], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        proc.kill()
    except ProcessLookupError:
        pass


def run_container(cmd: list[str], env: dict, name: str, transcript: str, stderr_path: str, limit: float,
                  stop_after: int | None) -> tuple[int, float, str]:
    """Run the docker command. Its stdout goes to `transcript` line by line, its stderr to `stderr_path`. Return the
    exit code, the seconds and how it ended: `exit`, `timeout` (killed after `limit` s) or `stopped` (killed after
    the `stop_after`-th tool_use block that is not a block of `StructuredOutput`)."""
    state = {"ended": None}
    lock = threading.Lock()
    start = time.monotonic()
    with open(transcript, "wb") as out, open(stderr_path, "wb") as err:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, env=env)

        def stop(why):
            with lock:
                if state["ended"] is not None:
                    return
                state["ended"] = why
            _kill(name, proc)

        timer = threading.Timer(limit, stop, ("timeout",))
        timer.daemon = True
        timer.start()
        try:
            seen = set()
            for raw in proc.stdout:
                out.write(raw)
                out.flush()
                if stop_after and state["ended"] is None:
                    seen.update(block_id or object() for block_id, name in _tool_uses(_event(raw))
                                if name != "StructuredOutput")
                    if len(seen) >= stop_after:
                        stop("stopped")
            proc.wait()
        finally:
            timer.cancel()
            if proc.poll() is None:
                _kill(name, proc)
                proc.wait()
    return proc.returncode, time.monotonic() - start, state["ended"] or "exit"


# ---------------------------------------------------------------- one run

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _write_json(path: str, obj: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _read_jsonl(path: str) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                event = _event(line)
                if event is not None:
                    out.append(event)
    except FileNotFoundError:
        pass
    return out


def _answer(result: dict | None, root: str):
    """(sites, invalid) of the structured output of a result event of success, or None."""
    if not result or result.get("subtype") != "success" or result.get("is_error") is True:
        return None
    try:
        return challenges.parse_sites(result.get("structured_output"), root)
    except ValueError:
        return None


def _leak_words(path: str) -> dict:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    return {word: text.count(word) for word in LEAK_WORDS}


def run_one(args) -> tuple[int, dict | None]:
    """One run (see the module text): the exit code and the record of run.json (None when no run starts)."""
    try:
        run = prepare(args)
    except (SetupError, OSError, ValueError, KeyError) as e:
        print(f"runner: {args.challenge}: {type(e).__name__}: {e}", file=sys.stderr)
        return 2, None
    if args.dry_run:
        if run["image_problem"]:
            print(f"runner: note: {run['image_problem']}", file=sys.stderr)
        notes = f"; route notes ({LANGS[run['product']]}): {', '.join(sorted(run['notes']))}" if run["notes"] else ""
        add = run["additions"][ADDITION_TOOL] if run["additions"] else None
        added = f"; route additions: {add['form']}, {len(add['rows'])} rows" if add else ""
        print(f"runner: dry run {run['run_id']}: arm {args.arm}{notes}{added}", file=sys.stderr)
        print(json.dumps(run["cmd"], ensure_ascii=False))
        return 0, None
    run_id, folder = run["run_id"], run["folder"]
    problem = run["image_problem"]
    if not problem and os.path.exists(os.path.join(folder, "run.json")):
        problem = f"{folder} has a run.json"
    if not problem and run["plugin"] and not proxy_healthy():
        problem = f"the proxy gives no answer at {HEALTH_URL}"
    if problem:
        print(f"runner: {run_id}: {problem}; no run starts", file=sys.stderr)
        return 2, None
    try:
        key = read_key()
    except KeyFileError as e:
        print(f"runner: {run_id}: {e}; no run starts", file=sys.stderr)
        return 2, None

    os.makedirs(folder, exist_ok=True)
    files = {name: os.path.join(folder, name) for name in RUN_FILES}
    rec = dict.fromkeys(RUN_FIELDS)
    rec.update(id=run_id, challenge=run["ch"]["id"], arm=args.arm, aid=args.aid, variant=args.variant,
               no_tools=args.no_tools, stop_after_tools=args.stop_after_tools, env_scrub=args.env_scrub,
               model=args.model, n=args.n, image_id=run["image"]["id"])
    ide_url, root = IDE_URLS[run["product"]], run["root"]
    version, reason = check_ide(ide_url, root, READY_TIMEOUT)
    rec["plugin_version_start"] = version
    problem = _ide_problem(version, reason, "start")
    if problem:
        rec.update(outcome="invalid", reason=problem)
        _write_json(os.path.join(folder, "run.json"), rec)
        print(f"{run_id}: invalid ({problem})", flush=True)
        return 0, rec

    route_run = f"{run_id}.{run['token'][:8]}" if run["plugin"] else None
    ended, exit_code, error = "exit", None, None
    try:
        if route_run:
            proxy.add_route(ROUTES_FILE, run["token"], {
                "run": route_run, "upstream": ide_url, "project": root,
                "instructions": {"instructions": INSTRUCTIONS, "guide": GUIDE_INSTRUCTIONS}.get(args.variant),
                "notes": run["notes"], "additions": run["additions"]})
        rec["started"] = _now()
        exit_code, seconds, ended = run_container(
            run["cmd"], {**os.environ, "ANTHROPIC_API_KEY": key}, run["name"], files["transcript.jsonl"],
            files["stderr.txt"], WALL_LIMIT, args.stop_after_tools)
        rec["seconds"] = round(seconds, 1)
    except Exception as e:  # each failure of the runner is the outcome `error`, with the route removed
        error = f"{type(e).__name__}: {e}"
    finally:
        if route_run:
            proxy.remove_route(ROUTES_FILE, run["token"])
            log = os.path.join(PROXY_LOG_DIR, route_run + ".jsonl")
            if os.path.exists(log):
                shutil.move(log, files["proxy.jsonl"])
        for path in files.values():
            if not os.path.exists(path):
                open(path, "wb").close()

    rec["exit_code"] = exit_code
    with open(files["transcript.jsonl"], "rb") as f:
        parsed = parse_transcript(f)
    result = parsed["result"] or {}
    answer = _answer(parsed["result"], root)
    rec.update(cost_usd=result.get("total_cost_usd"), turns=result.get("num_turns"), usage=result.get("usage"),
               model_usage=result.get("modelUsage"), tools=parsed["tools"], first_tools=parsed["first_tools"])
    proxy_lines = _read_jsonl(files["proxy.jsonl"])
    rec["mcp_calls"] = sum(1 for line in proxy_lines if line.get("method") == "tools/call")
    if answer is not None:
        sites, invalid = answer
        rec.update(answer=[f"{p}:{n}" for p, n in sorted(sites)], invalid=invalid,
                   score=challenges.score_answer(run["ch"], run["record"], sites, invalid))
    rec["outcome"] = "error" if error else outcome_of(ended, exit_code, parsed["result"], answer is not None)
    rec["reason"] = error or (result_reason(parsed["result"], exit_code)
                              if rec["outcome"] in ("error", "api_error") else None)
    rec["mcp_status"] = parsed["mcp_status"]
    problem = None if rec["outcome"] in KEEP_OUTCOME else mcp_problem(args.arm, run["server"], parsed["mcp_status"])
    if problem:
        rec.update(outcome="invalid", reason=problem)

    version, reason = check_ide(ide_url, root, 0)
    rec["plugin_version_end"] = version
    problem = _ide_problem(version, reason, "end") or _proxy_log_problem(proxy_lines)
    if problem and rec["outcome"] != "api_error":
        rec.update(outcome="invalid", reason=problem)
    rec["leak_words"] = _leak_words(files["transcript.jsonl"])

    hits = search_key(files.values(), key)
    if key in json.dumps(rec, ensure_ascii=False):
        hits.append("run.json")
    if hits:
        for path in files.values():
            if os.path.exists(path):
                os.unlink(path)
        rec = {k: (rec[k] if k in KEPT_AFTER_LEAK else None) for k in RUN_FIELDS}
        rec.update(outcome="key_leak", reason="the key string is in " + ", ".join(os.path.basename(h) for h in hits))
    _write_json(os.path.join(folder, "run.json"), rec)
    print(f"{run_id}: {rec['outcome']}" + (f" ({rec['reason']})" if rec["reason"] else ""), flush=True)
    if rec["outcome"] == "key_leak":
        print(f"runner: {run_id}: KEY LEAK; the files {', '.join(RUN_FILES)} of the run are deleted", file=sys.stderr)
        return 9, rec
    if rec["outcome"] == "api_error":
        return 3, rec
    return (1 if rec["outcome"] == "error" else 0), rec


# ---------------------------------------------------------------- batch

def plan_args(line: dict, batch: str) -> argparse.Namespace:
    """The `run` options of one plan line. SetupError for a line that is no plan line."""
    if not isinstance(line, dict) or {"batch", "dry-run"} & set(line):
        raise SetupError(f"a plan line is a JSON object with the options of run, without batch and dry-run: {line!r}")
    argv = []
    for name, value in line.items():
        if value is True:
            argv.append(f"-{name}")
        elif value is not False and value is not None:
            argv += [f"-{name}", str(value)]
    try:
        return _parser().parse_args(["run", *argv, "-batch", batch])
    except SystemExit:
        raise SetupError(f"the plan line {line!r} has an option that run does not take") from None


def batch_order(runs: list, seed: int) -> list:
    """The runs of one challenge and one model as neighbours, in a random order; the groups in the order of their
    first run."""
    groups: dict[tuple, list] = {}
    for a in runs:
        groups.setdefault((a.challenge, a.model), []).append(a)
    rng = random.Random(seed)
    out = []
    for group in groups.values():
        group = list(group)
        rng.shuffle(group)
        out.extend(group)
    return out


def _set_aside(folder: str, part: str) -> str:
    """Move the run folder to `<folder>.<part>-<k>` (`part`: `invalid` or `api-error`)."""
    k = 1
    while os.path.exists(f"{folder}.{part}-{k}"):
        k += 1
    os.rename(folder, f"{folder}.{part}-{k}")
    return f"{folder}.{part}-{k}"


def _retry_part(code: int, rec: dict | None) -> str | None:
    """The set-aside name part of a run that the batch tries one more time, or None."""
    if code == 3:
        return "api-error"
    return "invalid" if code == 0 and rec and rec["outcome"] == "invalid" else None


def _finished(folder: str) -> bool:
    """True when the run folder has a `run.json`. A record with the outcome `api_error` (a single `run` leaves it)
    is no finished run: its folder is set aside, and the batch does the run again."""
    try:
        with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
            rec = json.load(f)
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        return True
    if isinstance(rec, dict) and rec.get("outcome") == "api_error":
        _set_aside(folder, "api-error")
        return False
    return True


def run_batch(plan: str, batch: str, jobs: int = 2, seed: int = 1) -> int:
    try:
        with open(plan, encoding="utf-8") as f:
            runs = [plan_args(json.loads(line), batch) for line in f if line.strip()]
    except (OSError, ValueError, SetupError) as e:
        print(f"runner: {plan}: {e}", file=sys.stderr)
        return 2
    ids = [run_id_of(a) for a in runs]
    if len(set(ids)) != len(ids):
        print(f"runner: {plan}: two plan lines have the same run id", file=sys.stderr)
        return 2
    todo = [a for a in batch_order(runs, seed) if not _finished(os.path.join(RUNS, batch, run_id_of(a)))]
    print(f"batch {batch}: {len(runs)} runs, {len(runs) - len(todo)} finished before, {len(todo)} to run", flush=True)
    queue, lock, stop, codes, api_reasons = iter(todo), threading.Lock(), threading.Event(), [], []

    def worker():
        while not stop.is_set():
            with lock:
                a = next(queue, None)
            if a is None:
                return
            run_id = run_id_of(a)
            code, rec = run_one(a)
            tries = {"invalid": 1, "api-error": 1}  # one more try for each kind
            part = _retry_part(code, rec)
            while part:
                if part == "invalid" and not tries[part]:
                    break  # the second invalid run stays as the record of the run
                moved = os.path.basename(_set_aside(os.path.join(RUNS, batch, run_id), part))
                if tries[part] and not stop.is_set():
                    tries[part] -= 1
                    print(f"{run_id}: {rec['outcome']}, moved to {moved}; one more run", flush=True)
                    code, rec = run_one(a)
                    part = _retry_part(code, rec)
                    continue
                print(f"{run_id}: {rec['outcome']}, moved to {moved}", flush=True)
                if part == "api-error":
                    with lock:
                        api_reasons.append(rec["reason"])
                break
            with lock:
                codes.append(code)
            if code in (2, 3, 9):
                stop.set()

    threads = [threading.Thread(target=worker) for _ in range(max(1, jobs))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if 9 in codes:
        print(f"batch {batch}: STOPPED after a key leak", file=sys.stderr)
        return 9
    if 3 in codes:
        print(f"batch {batch}: STOPPED after an API error ({api_reasons[0]})", file=sys.stderr)
        return 3
    if 2 in codes:
        print(f"batch {batch}: stopped, a run could not start", file=sys.stderr)
        return 2
    print(f"batch {batch}: {len(codes)} runs done", flush=True)
    return 0


# ---------------------------------------------------------------- handshake

def handshake(product: str) -> int:
    """`claude mcp add` and `claude mcp list` in a container of the product image, with no key (module text)."""
    try:
        image = load_image(product)
        slot = trees.load_slots(SLOTS_FILE).get(product)
        if not slot:
            raise SetupError(f"{SLOTS_FILE}: no slot for the tree {product!r}")
    except (SetupError, OSError, ValueError) as e:
        print(f"runner: {e}", file=sys.stderr)
        return 2
    if not proxy_healthy():
        print(f"runner: the proxy gives no answer at {HEALTH_URL}", file=sys.stderr)
        return 2
    token = proxy.new_token()
    route_run, name, url = f"handshake-{product}.{token[:8]}", "run-" + secrets.token_hex(6), proxy.route_url(token)
    cmd = ["docker", "run", *CONTAINER_FLAGS, "--name", name, "--entrypoint", "/bin/bash", image["id"], "-c",
           'claude mcp add --transport http "$1" "$2" && claude mcp list', "handshake", image["server_name"], url]
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proxy.add_route(ROUTES_FILE, token, {"run": route_run, "upstream": IDE_URLS[product], "project": slot["path"],
                                         "instructions": None})
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=env)
        try:
            output, _ = proc.communicate(timeout=HANDSHAKE_LIMIT)
        except subprocess.TimeoutExpired:
            _kill(name, proc)
            output, _ = proc.communicate()
    except OSError as e:
        print(f"runner: docker does not start: {e}", file=sys.stderr)
        return 2
    finally:
        proxy.remove_route(ROUTES_FILE, token)
    print(f"== claude mcp add, claude mcp list in {image.get('image', '')} {image['id']} (exit {proc.returncode})")
    print(output.decode("utf-8", "replace").rstrip())
    lines = _read_jsonl(os.path.join(PROXY_LOG_DIR, route_run + ".jsonl"))
    print(f"== proxy log of the route ({len(lines)} lines)")
    for line in lines:
        print(json.dumps(line, ensure_ascii=False))
    ok = any(line.get("method") == "initialize" and line.get("status") == 200 for line in lines)
    print(f"== handshake {product}: {'PASS' if ok and proc.returncode == 0 else 'FAIL'}")
    return 0 if ok and proc.returncode == 0 else 1


# ---------------------------------------------------------------- CLI

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m benchlib.runner", description=__doc__.splitlines()[0],
                                     allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="one run", allow_abbrev=False, epilog=EXIT_CODES_RUN,
                         formatter_class=argparse.RawDescriptionHelpFormatter)
    run.add_argument("-set", required=True, help="challenge set (JSONL)")
    run.add_argument("-challenge", required=True)
    run.add_argument("-arm", required=True, choices=ARMS)
    run.add_argument("-model", required=True)
    run.add_argument("-batch", required=True, help="the folder below RUNS")
    run.add_argument("-aid", choices=AIDS)
    run.add_argument("-variant", choices=VARIANTS)
    run.add_argument("-stop-after-tools", type=int, dest="stop_after_tools")
    run.add_argument("-no-tools", action="store_true", dest="no_tools")
    run.add_argument("-env-scrub", action="store_true", dest="env_scrub",
                     help="-e CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1 (no credential in the environment of Bash)")
    run.add_argument("-n", type=int, default=1, help="run number (default 1)")
    run.add_argument("-dry-run", action="store_true", dest="dry_run")
    batch = sub.add_parser("batch", help="the runs of a plan file", allow_abbrev=False, epilog=EXIT_CODES_BATCH,
                           formatter_class=argparse.RawDescriptionHelpFormatter)
    batch.add_argument("-plan", required=True, help="one JSON object with the options of run for each line")
    batch.add_argument("-batch", required=True)
    batch.add_argument("-jobs", type=int, default=2)
    batch.add_argument("-seed", type=int, default=1)
    hs = sub.add_parser("handshake", help="Claude Code in the product image connects through the proxy",
                        allow_abbrev=False)
    hs.add_argument("-product", required=True, choices=sorted(IDE_URLS))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "run":
        return run_one(args)[0]
    if args.command == "batch":
        if not proxy.RUN_ID.fullmatch(args.batch):
            print(f"runner: batch {args.batch!r}: use only the characters A-Z a-z 0-9 . _ -", file=sys.stderr)
            return 2
        return run_batch(args.plan, args.batch, args.jobs, args.seed)
    return handshake(args.product)


if __name__ == "__main__":
    sys.exit(main())
