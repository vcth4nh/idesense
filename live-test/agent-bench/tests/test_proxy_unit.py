"""Unit tests of benchlib/proxy.py with a fake upstream: an `http.server` in a thread on 127.0.0.1.

The proxy runs in the same process on 127.0.0.1, a free port. No test calls an IDE.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import http.client
import json
import re
import socket
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from benchlib import proxy

AGENT_BENCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WRITERS = ("ide_restart", "ide_install_plugin", "ide_refactor_rename", "ide_move_file", "ide_read_file")
PROJECT = "/bench/trees/caddy"


class FakeUpstream:
    """A fake IDE MCP server. It records each request. `initialize` gives a server version, `tools/list`
    gives the permitted tools and the WRITERS, `tools/call` echoes its arguments, a notification gets 202
    with no body. A `tools/call` with the argument `query` = `slow` waits until `release` is set."""

    def __init__(self):
        self.requests = []
        self.reply_headers = {}
        self.slow_started = threading.Event()
        self.release = threading.Event()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append({"body": body, "headers": dict(self.headers.items()), "path": self.path})
                if "id" not in body:
                    self.send_response(202)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                method = body.get("method")
                if method == "initialize":
                    result = {"protocolVersion": "2025-11-25", "capabilities": {},
                              "serverInfo": {"name": "idesense", "version": "9.9.9-test"}}
                elif method == "tools/list":
                    names = proxy.PERMITTED_TOOLS + WRITERS
                    result = {"tools": [{"name": n, "inputSchema": {"type": "object"}} for n in names]}
                elif method == "tools/call":
                    arguments = body["params"]["arguments"]
                    if arguments.get("query") == "slow":
                        fake.slow_started.set()
                        fake.release.wait(10)
                    result = {"content": [{"type": "text", "text": json.dumps({"echo": arguments})}],
                              "isError": False}
                else:
                    result = {}
                data = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                for name, value in fake.reply_headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/mcp/streamable-http"

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ProxyTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="proxy")
        self.addCleanup(tmp.cleanup)
        self.routes = os.path.join(tmp.name, "routes.json")
        self.log_dir = os.path.join(tmp.name, "log")
        self.fake = FakeUpstream()
        self.addCleanup(self.fake.close)
        self.token = proxy.new_token()
        proxy.add_route(self.routes, self.token, self.entry("run-1"))
        self.server = proxy.make_server(self.routes, self.log_dir, "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def entry(self, run, instructions=None, upstream=None):
        return {"run": run, "upstream": upstream or self.fake.url, "project": PROJECT, "instructions": instructions}

    def request(self, path, data=None, method="POST", headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                                     headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def rpc(self, method, params=None, token=None, headers=None):
        msg = {"jsonrpc": "2.0", "id": 7, "method": method}
        if params is not None:
            msg["params"] = params
        status, hdrs, body = self.request(f"/r/{token or self.token}/mcp", json.dumps(msg).encode("utf-8"),
                                          headers={"Content-Type": "application/json", **(headers or {})})
        return status, hdrs, json.loads(body) if body else None

    def log_lines(self, name="run-1"):
        path = os.path.join(self.log_dir, f"{name}.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    # -- the four method rules --

    def test_tools_list_keeps_only_permitted(self):
        status, _, envelope = self.rpc("tools/list")
        self.assertEqual(status, 200)
        names = [t["name"] for t in envelope["result"]["tools"]]
        self.assertEqual(names, list(proxy.PERMITTED_TOOLS))
        self.assertEqual(len(proxy.PERMITTED_TOOLS), 15)
        self.assertEqual(len(self.fake.requests), 1)

    def test_refused_tool_makes_no_upstream_call(self):
        for name in WRITERS:
            status, _, envelope = self.rpc("tools/call", {"name": name, "arguments": {"project_path": "/x"}})
            self.assertEqual(status, 200)
            self.assertEqual(envelope, {"jsonrpc": "2.0", "id": 7, "result": {
                "content": [{"type": "text", "text": f"Tool {name} is not available."}], "isError": True}})
        self.assertEqual(self.fake.requests, [])
        lines = self.log_lines()
        self.assertEqual([line["tool"] for line in lines], list(WRITERS))
        self.assertTrue(all(line["refused"] is True and line["is_error"] is True for line in lines))

    def test_project_path_is_replaced(self):
        self.rpc("tools/call", {"name": "ide_find_usages",
                                "arguments": {"file": "a.go", "line": 3, "column": 5, "project_path": "/etc"}})
        self.rpc("tools/call", {"name": "ide_index_status", "arguments": {}})
        self.rpc("tools/call", {"name": "ide_index_status"})
        sent = [r["body"]["params"]["arguments"] for r in self.fake.requests]
        self.assertEqual(sent, [{"file": "a.go", "line": 3, "column": 5, "project_path": PROJECT},
                                {"project_path": PROJECT}, {"project_path": PROJECT}])

    def test_instructions_added_to_initialize(self):
        token = proxy.new_token()
        proxy.add_route(self.routes, token, self.entry("run-2", instructions="Use the IDE tools."))
        params = {"protocolVersion": "2025-11-25", "capabilities": {},
                  "clientInfo": {"name": "claude-code", "version": "2.1.326"}}
        _, _, with_text = self.rpc("initialize", params, token=token)
        _, _, without = self.rpc("initialize", params)
        self.assertEqual(with_text["result"]["instructions"], "Use the IDE tools.")
        self.assertNotIn("instructions", without["result"])
        self.assertEqual(with_text["result"]["serverInfo"]["version"], "9.9.9-test")
        line = self.log_lines("run-2")[0]
        self.assertEqual(line["client"], {"name": "claude-code", "version": "2.1.326"})
        self.assertEqual(line["server_version"], "9.9.9-test")

    def test_other_method_is_forwarded(self):
        status, _, envelope = self.rpc("ping", {"x": 1})
        self.assertEqual((status, envelope["result"]), (200, {}))
        self.assertEqual(self.fake.requests[0]["body"], {"jsonrpc": "2.0", "id": 7, "method": "ping",
                                                         "params": {"x": 1}})

    def test_notification_gets_202(self):
        body = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode("utf-8")
        status, _, data = self.request(f"/r/{self.token}/mcp", body, headers={"Content-Type": "application/json"})
        self.assertEqual((status, data), (202, b""))
        line = self.log_lines()[0]
        self.assertEqual((line["method"], line["status"], line["bytes"], line["is_error"]),
                         ("notifications/initialized", 202, 0, None))

    def test_headers_forwarded_and_returned(self):
        self.fake.reply_headers = {"Mcp-Session-Id": "up-1"}
        status, hdrs, _ = self.rpc("tools/list", headers={
            "Accept": "application/json, text/event-stream", "Mcp-Session-Id": "s-1",
            "MCP-Protocol-Version": "2025-11-25", "X-Extra": "1", "Origin": "http://example.invalid"})
        self.assertEqual(status, 200)
        self.assertEqual((hdrs["Content-Type"], hdrs["Mcp-Session-Id"]), ("application/json", "up-1"))
        sent = {k.lower(): v for k, v in self.fake.requests[0]["headers"].items()}
        self.assertEqual((sent["content-type"], sent["accept"], sent["mcp-session-id"],
                          sent["mcp-protocol-version"]),
                         ("application/json", "application/json, text/event-stream", "s-1", "2025-11-25"))
        self.assertNotIn("x-extra", sent)
        self.assertNotIn("origin", sent)

    # -- refusals of the HTTP layer --

    def test_unknown_token_404(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode("utf-8")
        for path in (f"/r/{proxy.new_token()}/mcp", "/mcp", f"/r/{self.token}/other", f"/r/{self.token}/mcp/x"):
            self.assertEqual(self.request(path, body)[0], 404, path)
        self.assertEqual(self.fake.requests, [])
        with open(os.path.join(self.log_dir, proxy.UNROUTED_LOG), encoding="utf-8") as f:
            self.assertEqual([json.loads(line)["status"] for line in f], [404] * 4)

    def test_array_body_400(self):
        batch = json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]).encode("utf-8")
        status, _, data = self.request(f"/r/{self.token}/mcp", batch)
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(data))
        self.assertEqual(self.request(f"/r/{self.token}/mcp", b"{not json")[0], 400)
        self.assertEqual(self.fake.requests, [])

    def test_body_above_1mb_413(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest("POST", f"/r/{self.token}/mcp")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(proxy.MAX_BODY + 1))
        conn.endheaders()
        conn.send(b"{")
        self.assertEqual(conn.getresponse().status, 413)
        conn.close()
        self.assertEqual(self.fake.requests, [])

    def test_get_405(self):
        for method in ("GET", "DELETE"):
            status, hdrs, _ = self.request(f"/r/{self.token}/mcp", method=method)
            self.assertEqual((status, hdrs["Allow"]), (405, "POST"), method)
        self.assertEqual(self.fake.requests, [])
        self.assertEqual([line["status"] for line in self.log_lines()], [405, 405])

    def test_upstream_in_route_file_is_checked_again(self):
        token = proxy.new_token()
        with open(self.routes, encoding="utf-8") as f:
            routes = json.load(f)
        routes[token] = self.entry("run-3", upstream="http://127.0.0.1:29170/mcp/streamable-http")
        with open(self.routes, "w", encoding="utf-8") as f:
            json.dump(routes, f)
        with mock.patch.object(proxy.ProxyHandler, "_forward") as forward:
            status, _, envelope = self.rpc("tools/call", {"name": "ide_index_status", "arguments": {}}, token=token)
        forward.assert_not_called()
        self.assertEqual(status, 403)
        self.assertIn("error", envelope)
        line = self.log_lines("run-3")[0]
        self.assertEqual((line["refused"], line["status"]), (True, 403))

    def test_route_with_bad_run_id_is_unrouted(self):
        tokens = {proxy.new_token(): "../escape", proxy.new_token(): None}
        with open(self.routes, encoding="utf-8") as f:
            routes = json.load(f)
        for token, run in tokens.items():
            routes[token] = {**self.entry("x"), "run": run}
        with open(self.routes, "w", encoding="utf-8") as f:
            json.dump(routes, f)
        for token in tokens:
            self.assertEqual(self.rpc("tools/list", token=token)[0], 404)
        self.assertEqual(self.fake.requests, [])
        with self.assertRaises(ValueError):
            proxy.add_route(self.routes, proxy.new_token(), self.entry("../escape"))

    # -- the log --

    def test_log_line_has_no_project_path(self):
        status, _, envelope = self.rpc("tools/call", {"name": "ide_find_usages", "arguments": {
            "file": "a.go", "line": 3, "column": 5, "project_path": "/agent/given"}})
        self.assertEqual(status, 200)
        [line] = self.log_lines()
        self.assertEqual(set(line), {"ts", "ms", "method", "tool", "arguments", "refused", "is_error", "bytes",
                                     "status"})
        self.assertEqual(line["arguments"], {"file": "a.go", "line": 3, "column": 5})
        self.assertEqual((line["method"], line["tool"], line["refused"], line["is_error"], line["status"]),
                         ("tools/call", "ide_find_usages", False, False, 200))
        self.assertEqual(line["bytes"], len(json.dumps(envelope).encode("utf-8")))
        self.assertRegex(line["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00$")
        self.assertIsInstance(line["ms"], int)
        text = json.dumps(line)
        self.assertNotIn("project_path", text)
        self.assertNotIn(PROJECT, text)
        self.assertNotIn("/agent/given", text)

    # -- route file --

    def test_add_route_refuses_fleet_port(self):
        before = open(self.routes, encoding="utf-8").read()
        for port in (29170, 29174, 29178):
            with self.assertRaises(ValueError):
                proxy.add_route(self.routes, proxy.new_token(),
                                self.entry("run-x", upstream=f"http://127.0.0.1:{port}/mcp/streamable-http"))
        self.assertEqual(open(self.routes, encoding="utf-8").read(), before)

    def test_add_route_refuses_other_host(self):
        for url in ("http://localhost:29374/mcp/streamable-http", "http://172.17.0.1:29374/mcp/streamable-http",
                    "http://0.0.0.0:29374/mcp/streamable-http", "https://127.0.0.1:29374/mcp/streamable-http"):
            with self.assertRaises(ValueError, msg=url):
                proxy.add_route(self.routes, proxy.new_token(), self.entry("run-x", upstream=url))

    def test_new_token_and_route_url(self):
        token = proxy.new_token()
        self.assertRegex(token, r"^[0-9a-f]{32}$")
        self.assertNotEqual(token, proxy.new_token())
        self.assertEqual(proxy.route_url("ab"), "http://172.17.0.1:29380/r/ab/mcp")
        self.assertEqual(proxy.route_url("ab", listen="127.0.0.1:29381"), "http://127.0.0.1:29381/r/ab/mcp")

    def test_route_file_change_is_seen(self):
        token = proxy.new_token()
        self.assertEqual(self.rpc("tools/list", token=token)[0], 404)
        proxy.add_route(self.routes, token, self.entry("run-2"))
        self.assertEqual(self.rpc("tools/list", token=token)[0], 200)
        self.assertEqual(len(self.log_lines("run-2")), 1)
        proxy.remove_route(self.routes, token)
        self.assertEqual(self.rpc("tools/list", token=token)[0], 404)
        self.assertEqual(self.rpc("tools/list")[0], 200)

    # -- server --

    def test_slow_call_does_not_block_other_route(self):
        token = proxy.new_token()
        proxy.add_route(self.routes, token, self.entry("run-2"))
        slow = {}
        thread = threading.Thread(target=lambda: slow.setdefault("status", self.rpc(
            "tools/call", {"name": "ide_find_usages", "arguments": {"query": "slow"}})[0]))
        thread.start()
        self.assertTrue(self.fake.slow_started.wait(10))
        status, _, _ = self.rpc("tools/call", {"name": "ide_index_status", "arguments": {}}, token=token)
        self.assertEqual(status, 200)
        self.assertTrue(thread.is_alive())
        self.fake.release.set()
        thread.join(10)
        self.assertEqual(slow["status"], 200)

    def test_upstream_down_502(self):
        token = proxy.new_token()
        proxy.add_route(self.routes, token,
                        self.entry("run-2", upstream=f"http://127.0.0.1:{free_port()}/mcp/streamable-http"))
        status, _, envelope = self.rpc("tools/call", {"name": "ide_index_status", "arguments": {}}, token=token)
        self.assertEqual(status, 502)
        self.assertIn("error", envelope)
        line = self.log_lines("run-2")[0]
        self.assertEqual((line["status"], line["refused"]), (502, False))

    # -- CLI --

    def serve_cli(self, listen):
        return subprocess.Popen([sys.executable, "-B", "-m", "benchlib.proxy", "serve", "-routes", self.routes,
                                 "-log-dir", self.log_dir, "-listen", listen],
                                cwd=AGENT_BENCH, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_serve_refuses_listen_all(self):
        for listen in ("0.0.0.0:29380", "172.17.0.2:29380", "localhost:29380"):
            proc = self.serve_cli(listen)
            out, _ = proc.communicate(timeout=30)
            self.assertEqual(proc.returncode, 2, listen)
            self.assertNotIn("proxy ready", out)

    def test_serve_prints_ready_line(self):
        proc = self.serve_cli("127.0.0.1:0")
        self.addCleanup(proc.wait, 10)
        self.addCleanup(proc.terminate)
        timer = threading.Timer(20, proc.kill)
        timer.start()
        line = proc.stdout.readline()
        timer.cancel()
        match = re.fullmatch(r"proxy ready on 127\.0\.0\.1:(\d+)\n", line)
        self.assertIsNotNone(match, line)
        with urllib.request.urlopen(f"http://127.0.0.1:{match.group(1)}/health", timeout=10) as resp:
            self.assertEqual((resp.status, json.loads(resp.read())), (200, {"ok": True}))


if __name__ == "__main__":
    unittest.main()
