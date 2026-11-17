"""Filter proxy between a benchmark container and a benchmark IDE.

A plugin arm reaches its IDE only through this proxy, at `http://172.17.0.1:29380/r/<token>/mcp` (the
docker0 address). The route file maps each token to one run:
`{"<token>": {"run": ..., "upstream": <IDE MCP url>, "project": <absolute path>, "instructions": null}}`.
For a POST of one JSON-RPC object on a route, the proxy:

- answers `tools/call` of a tool outside PERMITTED_TOOLS itself (a tool error), with no call to the IDE;
- sets `params.arguments.project_path` of each other `tools/call` to the project of the route;
- keeps only the permitted tools in the answer of `tools/list`;
- sets `result.instructions` of the answer of `initialize` when the route has an `instructions` text;
- forwards each other method with no change.

The proxy forwards the message that it parsed (serialized again), never the raw body, so the IDE reads
the same keys that the proxy checked. The plugin server is stateless: each POST gets one JSON answer,
and a notification gets 202 with no body. It sends no `Mcp-Session-Id` (measured on 2.1.1-bench.5beca97).

Log: one JSON line for each request on a route in `<log-dir>/<run id>.jsonl`. `bytes` is the size of
the answer body that the proxy sends. `is_error` is true for a JSON-RPC error or `result.isError`,
and null when the answer has no JSON body. A request that matches no route gets 404 and a line in
`<log-dir>/_unrouted.jsonl`. The proxy checks the upstream of a route again before each call: a fleet
port or another host in a hand-written route file gets 403, a log line and no call.
"""
import argparse
import datetime
import fcntl
import http.client
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from benchlib import mcp

PERMITTED_TOOLS = (
    "ide_call_hierarchy", "ide_diagnostics", "ide_explain_symbol", "ide_file_structure", "ide_find_class",
    "ide_find_definition", "ide_find_file", "ide_find_implementations", "ide_find_super_methods",
    "ide_find_symbol", "ide_find_usages", "ide_index_status", "ide_search_text", "ide_sync_files",
    "ide_type_hierarchy",
)
DEFAULT_LISTEN = "172.17.0.1:29380"
LISTEN_HOSTS = ("172.17.0.1", "127.0.0.1")
MAX_BODY = 1024 * 1024
UPSTREAM_TIMEOUT = 300
FORWARD_HEADERS = ("Content-Type", "Accept", "Mcp-Session-Id", "MCP-Protocol-Version")
RETURN_HEADERS = ("Content-Type", "Mcp-Session-Id")
UNROUTED_LOG = "_unrouted.jsonl"
ROUTE_PATH = re.compile(r"/r/([^/]+)/mcp")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def new_token() -> str:
    return secrets.token_hex(16)


def route_url(token: str, listen: str = DEFAULT_LISTEN) -> str:
    return f"http://{listen}/r/{token}/mcp"


def upstream_problem(url) -> str | None:
    """Why the proxy must not call this upstream, or None."""
    if not isinstance(url, str):
        return "no upstream URL"
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError as e:
        return f"not a URL: {e}"
    if parts.scheme != "http":
        return f"scheme {parts.scheme!r} is not http"
    if parts.hostname != "127.0.0.1":
        return f"host {parts.hostname!r} is not 127.0.0.1"
    if port in mcp.FLEET_PORTS:
        return f"port {port} is a fleet IDE port (29170 to 29178)"
    return None


def read_routes(routes_file) -> dict:
    """The routes of the file; an absent file has no route."""
    try:
        with open(routes_file, encoding="utf-8") as f:
            routes = json.load(f)
    except FileNotFoundError:
        return {}
    if not isinstance(routes, dict):
        raise ValueError(f"{routes_file}: the route file is a {type(routes).__name__}, not an object")
    return routes


def _update_routes(routes_file, change) -> None:
    """Apply `change(routes)` under the lock file, then write a temporary file and rename it."""
    lock = os.open(routes_file + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        routes = read_routes(routes_file)
        change(routes)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(routes_file)), prefix=".routes-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(routes, f, indent=1, sort_keys=True)
                f.write("\n")
            os.replace(tmp, routes_file)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    finally:
        os.close(lock)


def add_route(routes_file, token: str, entry: dict) -> None:
    """Add or replace the route of `token`. ValueError for an upstream that is not 127.0.0.1 or is a
    fleet port, for a run id that is no plain file name, and for a project that is no absolute path."""
    problem = upstream_problem(entry.get("upstream"))
    if problem:
        raise ValueError(f"route upstream {entry.get('upstream')!r} refused: {problem}")
    if not isinstance(entry.get("run"), str) or not RUN_ID.fullmatch(entry["run"]):
        raise ValueError(f"route run {entry.get('run')!r}: the run id names the log file; use [A-Za-z0-9._-]")
    if not isinstance(entry.get("project"), str) or not os.path.isabs(entry["project"]):
        raise ValueError(f"route project {entry.get('project')!r} is no absolute path")
    _update_routes(routes_file, lambda routes: routes.__setitem__(token, entry))


def remove_route(routes_file, token: str) -> None:
    """Remove the route of `token`; an absent token is no error."""
    _update_routes(routes_file, lambda routes: routes.pop(token, None))


def parse_listen(listen: str) -> tuple[str, int]:
    host, _, port = listen.rpartition(":")
    if host not in LISTEN_HOSTS:
        raise ValueError(f"listen host {host!r} refused: use 172.17.0.1 (docker0) or 127.0.0.1")
    if not port.isdigit() or int(port) > 65535:
        raise ValueError(f"listen port {port!r} is no port number")
    return host, int(port)


class RouteTable:
    """The route file, parsed again when its bytes change. A file of a few routes is read for each
    request: a check of the stat could miss a rename to a file of equal size within one clock tick."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._raw = None
        self._routes = {}

    def get(self, token):
        try:
            with open(self.path, "rb") as f:
                raw = f.read()
        except FileNotFoundError:
            raw = b""
        with self._lock:
            if raw != self._raw:
                self._raw = raw
                try:
                    routes = json.loads(raw) if raw else {}
                    if not isinstance(routes, dict):
                        raise ValueError(f"the route file is a {type(routes).__name__}")
                except ValueError as e:
                    print(f"proxy: route file {self.path} not read, no route is active: {e}",
                          file=sys.stderr, flush=True)
                    routes = {}
                self._routes = routes
            entry = self._routes.get(token)
        # The run id names the log file: an entry with no plain run id is no route.
        if not isinstance(entry, dict) or not isinstance(entry.get("run"), str) or not RUN_ID.fullmatch(entry["run"]):
            return None
        return entry


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def _body(obj) -> bytes:
    """A message body in the compact form of the plugin (no spaces, no ASCII escapes)."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _json(status, envelope, extra=None):
    return status, {"Content-Type": "application/json", **(extra or {})}, _body(envelope)


def _rpc_error(status, request_id, message):
    return _json(status, {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": message}})


def _is_error(body: bytes):
    try:
        envelope = json.loads(body)
    except ValueError:
        return None
    if not isinstance(envelope, dict):
        return None
    result = envelope.get("result")
    return "error" in envelope or (isinstance(result, dict) and result.get("isError") is True)


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # An idle keep-alive connection of a removed container does not hold its thread for ever.
    timeout = 900

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if urllib.parse.urlsplit(self.path).path == "/health":
            self._send(*_json(200, {"ok": True}))
            return
        self._not_post()

    def do_DELETE(self):
        self._not_post()

    def do_POST(self):
        started, ts = time.monotonic(), _now()
        entry = self._route()
        if entry is None:
            self._unrouted(started, ts)
            return
        rec = {"ts": ts, "ms": None, "method": None, "tool": None, "arguments": None, "refused": False,
               "is_error": None, "bytes": 0, "status": None}
        status, headers, body = self._post(entry, rec)
        # The log line comes before the answer: a client that has its answer finds the line.
        rec.update(ms=round((time.monotonic() - started) * 1000), is_error=_is_error(body),
                   bytes=len(body), status=status)
        self._log(entry["run"] + ".jsonl", rec)
        self._send(status, headers, body)

    def _not_post(self):
        started, ts = time.monotonic(), _now()
        entry = self._route()
        if entry is None:
            self._unrouted(started, ts)
            return
        status, headers, body = _rpc_error(405, None, "this route takes only POST")
        headers["Allow"] = "POST"
        self._log(entry["run"] + ".jsonl", {
            "ts": ts, "ms": round((time.monotonic() - started) * 1000), "method": None, "tool": None,
            "arguments": None, "refused": False, "is_error": True, "bytes": len(body), "status": status})
        self._send(status, headers, body)

    def _route(self):
        match = ROUTE_PATH.fullmatch(urllib.parse.urlsplit(self.path).path)
        return self.server.routes.get(match.group(1)) if match else None

    def _unrouted(self, started, ts):
        # The body stays unread, so the connection closes after the answer.
        self.close_connection = True
        status, headers, body = _rpc_error(404, None, "no route")
        self._log(UNROUTED_LOG, {"ts": ts, "ms": round((time.monotonic() - started) * 1000),
                                 "http": self.command, "path": self.path, "status": status})
        self._send(status, headers, body)

    def _post(self, entry, rec):
        """Status, headers and body of the answer to one POST on a route. Fills `rec` for the log."""
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit():
            self.close_connection = True
            return _rpc_error(411, None, "Content-Length is required")
        if int(length) > MAX_BODY:
            self.close_connection = True
            return _rpc_error(413, None, f"the request body is above {MAX_BODY} bytes")
        try:
            msg = json.loads(self.rfile.read(int(length)))
        except ValueError as e:
            return _rpc_error(400, None, f"parse error: {e}")
        if not isinstance(msg, dict):
            return _rpc_error(400, None, "the body must be one JSON-RPC object (no batch)")
        method = msg.get("method")
        rec["method"] = method if isinstance(method, str) else None
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if method == "initialize":
            rec.update(client=params.get("clientInfo"), server_version=None)
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            rec["tool"] = name
            rec["arguments"] = {k: v for k, v in arguments.items() if k != "project_path"}
            if name not in PERMITTED_TOOLS:
                rec["refused"] = True
                return _json(200, {"jsonrpc": "2.0", "id": msg.get("id"), "result": {
                    "content": [{"type": "text", "text": f"Tool {name} is not available."}], "isError": True}})
            msg = {**msg, "params": {**params, "arguments": {**arguments, "project_path": entry.get("project")}}}
        problem = upstream_problem(entry.get("upstream"))
        if problem:
            rec["refused"] = True
            return _rpc_error(403, msg.get("id"), f"the upstream of this route is refused: {problem}")
        try:
            status, headers, body = self._forward(entry["upstream"], _body(msg))
        except (OSError, http.client.HTTPException) as e:
            return _rpc_error(502, msg.get("id"), f"upstream failure: {type(e).__name__}: {e}")
        if status == 200 and method in ("initialize", "tools/list"):
            return self._filter(entry, method, msg.get("id"), rec, status, headers, body)
        return status, headers, body

    def _filter(self, entry, method, request_id, rec, status, headers, body):
        """The answer of `initialize` with the instructions of the route, the answer of `tools/list` with
        only the permitted tools. An answer that the proxy cannot read gets 502 (no unfiltered tool list)."""
        try:
            envelope = json.loads(body)
        except ValueError as e:
            return _rpc_error(502, request_id, f"the upstream answer of {method} is no JSON: {e}")
        if isinstance(envelope, dict) and "error" in envelope:
            return status, headers, body
        result = envelope.get("result") if isinstance(envelope, dict) else None
        if method == "initialize" and isinstance(result, dict):
            info = result.get("serverInfo")
            rec["server_version"] = info.get("version") if isinstance(info, dict) else None
            if isinstance(entry.get("instructions"), str):
                result["instructions"] = entry["instructions"]
        elif method == "tools/list" and isinstance(result, dict) and isinstance(result.get("tools"), list):
            result["tools"] = [t for t in result["tools"]
                               if isinstance(t, dict) and t.get("name") in PERMITTED_TOOLS]
        else:
            return _rpc_error(502, request_id, f"the upstream answer of {method} has no result to read")
        return status, headers, _body(envelope)

    def _forward(self, upstream, data):
        parts = urllib.parse.urlsplit(upstream)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        headers = {name: self.headers[name] for name in FORWARD_HEADERS if self.headers.get(name) is not None}
        conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=UPSTREAM_TIMEOUT)
        try:
            conn.request("POST", path, body=data, headers=headers)
            resp = conn.getresponse()
            body = resp.read()
            back = {name: resp.getheader(name) for name in RETURN_HEADERS if resp.getheader(name) is not None}
            return resp.status, back, body
        finally:
            conn.close()

    def _send(self, status, headers, body):
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _log(self, name, rec):
        line = json.dumps(rec) + "\n"
        with self.server.log_lock, open(os.path.join(self.server.log_dir, name), "a", encoding="utf-8") as f:
            f.write(line)


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, routes_file, log_dir):
        self.routes = RouteTable(routes_file)
        self.log_dir = log_dir
        self.log_lock = threading.Lock()
        os.makedirs(log_dir, exist_ok=True)
        super().__init__(address, ProxyHandler)


def make_server(routes_file, log_dir, host: str, port: int) -> ProxyServer:
    """A proxy server bound to host:port (port 0: a free port). ValueError for another host."""
    parse_listen(f"{host}:{port}")
    return ProxyServer((host, port), routes_file, log_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m benchlib.proxy", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the proxy until it gets a signal")
    serve.add_argument("-routes", required=True, help="route file (JSON object: token -> route)")
    serve.add_argument("-log-dir", required=True, help="folder of the request logs")
    serve.add_argument("-listen", default=DEFAULT_LISTEN, help="host:port; the host is 172.17.0.1 or 127.0.0.1")
    args = parser.parse_args(argv)
    try:
        host, port = parse_listen(args.listen)
    except ValueError as e:
        print(f"proxy: {e}", file=sys.stderr)
        return 2
    server = ProxyServer((host, port), args.routes, args.log_dir)
    print(f"proxy ready on {host}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
