"""JSON-RPC client for one MCP server of the IdeSense plugin.

The server has one endpoint, `http://127.0.0.1:<port>/mcp/streamable-http`, and answers each POST
with no session: a tool call needs no `initialize` before it. The wire form is that of
`live-test/run.py`: a `tools/call` request with `project_path` in the arguments, and the JSON
payload in the text of the first content item. `server_version` sends `initialize` only to read
`serverInfo.version`.
"""
import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request

FLEET_PORTS = range(29170, 29179)
PROTOCOL_VERSION = "2025-11-25"  # McpConstants.STREAMABLE_HTTP_MCP_PROTOCOL_VERSION of the plugin
READY_TIMEOUT = 300.0
READY_POLL = 5.0


class McpError(Exception):
    """No usable result. `kind` is `transport` (HTTP or envelope), `jsonrpc` or `tool` (the tool answered
    with an error)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class McpClient:
    def __init__(self, url: str, project_path: str, timeout: float = 120.0):
        if urllib.parse.urlsplit(url).port in FLEET_PORTS:
            raise ValueError(f"{url}: a fleet IDE port (29170 to 29178); use a benchmark IDE")
        self.url = url
        self.project_path = project_path
        self.timeout = timeout
        self._id = 0

    def server_version(self) -> str:
        """`serverInfo.version` from the result of `initialize`."""
        result = self._post("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                           "clientInfo": {"name": "agent-bench-audit", "version": "1"}})
        version = result.get("serverInfo", {}).get("version") if isinstance(result, dict) else None
        if not isinstance(version, str):
            raise McpError("transport", f"transport_error: no serverInfo.version in {json.dumps(result)[:200]}")
        return version

    def call(self, tool: str, params: dict) -> dict:
        """The payload of one tool call. Raise McpError when there is no payload object."""
        result = self._post("tools/call", {"name": tool,
                                           "arguments": {**params, "project_path": self.project_path}})
        content = result.get("content") if isinstance(result, dict) else None
        if not isinstance(content, list) or not content or not isinstance(content[0], dict) \
                or not isinstance(content[0].get("text"), str):
            raise McpError("transport", f"transport_error: no text content in {json.dumps(result)[:200]}")
        text = content[0]["text"]
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            raise McpError("tool", text) from None
        if not isinstance(payload, dict):
            raise McpError("tool", f"payload is a {type(payload).__name__}: {text[:200]}")
        if "error" in payload:
            raise McpError("tool", f"{payload['error']}: {payload.get('message', '')}")
        if result.get("isError") is True:
            raise McpError("tool", text)
        return payload

    def _post(self, method: str, params: dict):
        """The `result` of one JSON-RPC request."""
        self._id += 1
        request = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        req = urllib.request.Request(self.url, data=json.dumps(request).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            raise McpError("transport", f"transport_error: HTTP {e.code} {e.reason}") from None
        except urllib.error.URLError as e:
            raise McpError("transport", f"transport_error: {e.reason}") from None
        except (OSError, http.client.HTTPException) as e:
            raise McpError("transport", f"transport_error: {type(e).__name__}: {e}") from None
        try:
            envelope = json.loads(body)
        except json.JSONDecodeError as e:
            raise McpError("transport", f"transport_error: non-JSON envelope: {e}") from None
        if not isinstance(envelope, dict):
            raise McpError("transport", f"transport_error: envelope is a {type(envelope).__name__}")
        if "error" in envelope:
            raise McpError("jsonrpc", f"jsonrpc_error: {json.dumps(envelope['error'], sort_keys=True)}")
        return envelope.get("result")

    def call_all_pages(self, tool: str, params: dict, list_field: str) -> tuple[list[dict], dict]:
        """All items of a paginated result: follow `nextCursor` while `hasMore` is true.

        The second value is the first page with no list (`warnings` and `notes` are on the first page only).
        """
        page = self.call(tool, params)
        if not isinstance(page.get(list_field), list):
            raise McpError("tool", f"no '{list_field}' list in the result (keys: {sorted(page)})")
        head = {k: v for k, v in page.items() if k != list_field}
        items = list(page[list_field])
        more = {"pageSize": params["pageSize"]} if "pageSize" in params else {}
        while page.get("hasMore"):
            cursor = page.get("nextCursor")
            if not cursor:
                raise McpError("tool", f"hasMore is true with no nextCursor after {len(items)} items")
            page = self.call(tool, {"cursor": cursor, **more})
            if not isinstance(page.get(list_field), list):
                raise McpError("tool", f"no '{list_field}' list on a cursor page (keys: {sorted(page)})")
            items.extend(page[list_field])
        return items, head


def wait_ready(client: McpClient, timeout: float, poll: float, sleep=time.sleep, clock=time.monotonic) -> str | None:
    """None when `ide_index_status` says smart mode, else the last reason after `timeout` seconds."""
    start = clock()
    while True:
        try:
            status = client.call("ide_index_status", {})
            reason = None if status.get("isDumbMode") is False else f"isDumbMode is {status.get('isDumbMode')!r}"
        except McpError as e:
            reason = str(e)
        if reason is None or clock() - start >= timeout:
            return reason
        sleep(poll)
