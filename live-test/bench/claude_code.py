"""The code of the agent benchmark that is specific to Claude Code: its arguments, its transcript, its key, its MCP
configuration and the shell text of the connection check. The module imports nothing from `bench.runner`.

`flags` gives the arguments of `claude` of each run (Global Constraints). `mcp_config` gives the value of
MCP_CONFIG_FLAG for one HTTP server. `read_key` reads the key file `settings.secret_file()` (the variable
BENCH_SECRET_FILE). `handshake_script` is the shell text of the connection check of `runner handshake`: the server
name is `$1` and the route URL is `$2`.

The transcript parser (`parse_transcript`) reads the stream-json events of Claude Code: of a `result` event (the last
one) `subtype`, `is_error`, `terminal_reason`, `total_cost_usd`, `num_turns`, `usage`, `modelUsage` and
`structured_output`; of an `assistant` event (also of a subagent) the `tool_use` blocks of `message.content`, with
their `id` and `name`, one time for each block id; of the first `system` event with the subtype `init` the
`name` and `status` of each entry of `mcp_servers`. A tool name stays as the transcript has it (an IDE tool is
`mcp__<server name>__<tool>`; `ToolSearch` and `StructuredOutput` are counted too). A line that is no JSON object and
an event of another type are skipped.
"""
import collections
import json

from common import settings

MCP_CONFIG_FLAG = "--mcp-config"
NO_TOOLS = ("--tools", "")                        # `-no-tools` (the memory probe)
NO_TOOL_SEARCH = "ENABLE_TOOL_SEARCH=false"       # `-variant no-tool-search`
ENV_SCRUB = "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1"  # `-env-scrub`
ANSWER_TOOL = "StructuredOutput"                  # the tool of the answer (`--json-schema`)


class KeyFileError(Exception):
    """The key file is absent, empty or has more than one line. The message never holds the content."""


def flags(prompt: str, model: str, schema: dict) -> list[str]:
    """The arguments of `claude` of each run (Global Constraints). The prompt comes first, before the options with
    more than one value (`--mcp-config`, `--tools`)."""
    return ["-p", prompt, "--model", model, "--effort", "medium", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence", "--permission-mode", "bypassPermissions", "--max-budget-usd", "20",
            "--json-schema", json.dumps(schema, separators=(",", ":")), "--strict-mcp-config"]


def mcp_config(server_name: str, url: str) -> dict:
    """The MCP configuration of a plugin arm: one HTTP server."""
    return {"mcpServers": {server_name: {"type": "http", "url": url}}}


def handshake_script() -> str:
    """The shell text of the connection check: `claude mcp add` of the server `$1` at the URL `$2`, then
    `claude mcp list`."""
    return 'claude mcp add --transport http "$1" "$2" && claude mcp list'


def read_key(path: str | None = None) -> str:
    """The API key: the text of the key file (default: `settings.secret_file()`) without white space at the two
    ends."""
    path = path or settings.secret_file()
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


# ---------------------------------------------------------------- transcript parser (stream-json of Claude Code)

def event(raw) -> dict | None:
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def tool_uses(event: dict | None) -> list[tuple[str | None, str]]:
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
        ev = event(raw)
        if ev is None:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init" and not init:
            init, mcp_status = True, _mcp_status(ev)
        if ev.get("type") == "result":
            result = ev
        for block_id, name in tool_uses(ev):
            if block_id is not None:
                if block_id in seen:
                    continue
                seen.add(block_id)
            names.append(name)
    return {"result": result, "tools": dict(collections.Counter(names)), "first_tools": names[:5],
            "mcp_status": mcp_status}
