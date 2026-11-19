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
    """A fake IDE MCP server. It records each request and the body of each answer (`replies`). `initialize`
    gives a server version, `tools/list` gives the permitted tools and the WRITERS, `tools/call` echoes its
    arguments, a notification gets 202 with no body. A `tools/call` with the argument `query` = `slow` waits
    until `release` is set. `call_result` replaces the result of `tools/call`; `call_body` and `call_type`
    replace its whole answer body and its Content-Type."""

    def __init__(self):
        self.requests = []
        self.replies = []
        self.reply_headers = {}
        self.call_result = None
        self.call_body = None
        self.call_type = "application/json"
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
                    echo = {"content": [{"type": "text", "text": json.dumps({"echo": arguments})}], "isError": False}
                    result = fake.call_result or echo
                else:
                    result = {}
                data = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode("utf-8")
                call = method == "tools/call"
                if call and fake.call_body is not None:
                    data = fake.call_body
                fake.replies.append(data)
                self.send_response(200)
                self.send_header("Content-Type", fake.call_type if call else "application/json")
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

    def entry(self, run, instructions=None, upstream=None, **extra):
        return {"run": run, "upstream": upstream or self.fake.url, "project": PROJECT, "instructions": instructions,
                **extra}

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

    # -- the note of a route --

    NOTE = "This list can be incomplete: a text search for the name finds more."

    def noted_route(self, run="run-n"):
        token = proxy.new_token()
        proxy.add_route(self.routes, token, self.entry(run, notes={"ide_find_usages": self.NOTE}))
        return token

    def call_raw(self, name, token):
        """The status and the raw answer body of one `tools/call`."""
        msg = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
               "params": {"name": name, "arguments": {"file": "a.go"}}}
        status, _, body = self.request(f"/r/{token}/mcp", json.dumps(msg).encode("utf-8"),
                                       headers={"Content-Type": "application/json"})
        return status, body

    @staticmethod
    def text_result(value, is_error=False):
        return {"content": [{"type": "text", "text": json.dumps(value)}], "isError": is_error}

    def test_note_is_appended_to_the_notes_of_the_result(self):
        token = self.noted_route()
        payload = {"usages": [{"file": "a.go", "line": 3, "name": "Größe"}], "totalCount": 1,
                   "notes": ["main.Shape.Area (normal.go:21:2) is the base method."]}
        self.fake.call_result = {"content": [{"type": "text", "text": json.dumps(payload)},
                                             {"type": "text", "text": "second block"}],
                                 "isError": False, "_meta": {"k": 1}}
        status, raw = self.call_raw("ide_find_usages", token)
        self.assertEqual(200, status)
        envelope = json.loads(raw)
        text = envelope["result"]["content"][0]["text"]
        expected = {**payload, "notes": payload["notes"] + [self.NOTE]}
        self.assertEqual(json.dumps(expected, separators=(",", ":"), ensure_ascii=False), text)
        self.assertEqual({"jsonrpc": "2.0", "id": 7, "result": {
            "content": [{"type": "text", "text": text}, {"type": "text", "text": "second block"}],
            "isError": False, "_meta": {"k": 1}}}, envelope)
        self.assertEqual(json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), raw)
        [line] = self.log_lines("run-n")
        self.assertEqual((True, False, len(raw)), (line["note_added"], line["is_error"], line["bytes"]))
        self.assertEqual({"ts", "ms", "method", "tool", "arguments", "refused", "is_error", "bytes", "status",
                          "note_added"}, set(line))

    def test_note_makes_the_list_when_notes_is_absent_or_null(self):
        token = self.noted_route()
        for payload in ({"usages": []}, {"usages": [], "notes": None}):
            with self.subTest(payload=payload):
                self.fake.call_result = self.text_result(payload)
                _, raw = self.call_raw("ide_find_usages", token)
                self.assertEqual({"usages": [], "notes": [self.NOTE]},
                                 json.loads(json.loads(raw)["result"]["content"][0]["text"]))
        self.assertEqual([True, True], [line["note_added"] for line in self.log_lines("run-n")])

    def test_answer_with_no_note_passes_byte_for_byte(self):
        noted, null_notes = self.noted_route(), proxy.new_token()
        proxy.add_route(self.routes, null_notes, self.entry("run-z", notes=None))
        payload = {"usages": [{"file": "a.go", "line": 3}]}
        rpc_error = json.dumps({"jsonrpc": "2.0", "id": 7, "error": {"code": -32603, "message": "x"}}).encode("utf-8")
        stream = (b"event: message\ndata: "
                  + json.dumps({"jsonrpc": "2.0", "id": 7, "result": self.text_result(payload)}).encode("utf-8")
                  + b"\n\n")
        cases = [
            ("error result", noted, "ide_find_usages", {"result": self.text_result({"error": "x"}, is_error=True)}),
            ("error payload with no error flag", noted, "ide_find_usages", {"result": self.text_result(
                {"error": "tool_error", "message": "No named element at position."})}),
            ("JSON-RPC error", noted, "ide_find_usages", {"body": rpc_error}),
            ("text that is no JSON", noted, "ide_find_usages", {"result": {
                "content": [{"type": "text", "text": "The index is not ready."}], "isError": False}}),
            ("JSON that is no object", noted, "ide_find_usages", {"result": self.text_result([1, 2])}),
            ("no content", noted, "ide_find_usages", {"result": {"content": [], "isError": False}}),
            ("event stream", noted, "ide_find_usages", {"body": stream, "type": "text/event-stream"}),
            ("tool with no note", noted, "ide_find_class", {"result": self.text_result(payload)}),
            ("route with no notes", self.token, "ide_find_usages", {"result": self.text_result(payload)}),
            ("notes null", null_notes, "ide_find_usages", {"result": self.text_result(payload)}),
        ]
        for what, token, tool, reply in cases:
            with self.subTest(what):
                self.fake.call_result = reply.get("result")
                self.fake.call_body = reply.get("body")
                self.fake.call_type = reply.get("type", "application/json")
                status, raw = self.call_raw(tool, token)
                self.assertEqual((200, self.fake.replies[-1]), (status, raw))
        lines = self.log_lines("run-n") + self.log_lines() + self.log_lines("run-z")
        self.assertEqual(len(cases), len(lines))
        self.assertFalse(any("note_added" in line for line in lines))

    # -- the addition of a route --

    ADD_NOTE = "2 lines come from the name only."
    LOG_KEYS = {"ts", "ms", "method", "tool", "arguments", "refused", "is_error", "bytes", "status"}

    @staticmethod
    def row(file, line, **extra):
        return {"file": file, "line": line, "column": 5, "preview": "x.label", "usageType": "REFERENCE",
                "enclosingScope": ["demo", "run"], **extra}

    def addition(self, form="rows", **change):
        """An addition for a target whose IDE rows are src/core.py:10 and src/use.py:4. Its rows are not in the
        order of their paths, so a test sees the order of the addition."""
        return {"known": [["src/core.py", 10], ["src/use.py", 4]],
                "rows": [self.row("src/zeta.py", 8, match="DYNAMIC"), self.row("src/alpha.py", 2, match="DYNAMIC")],
                "form": form, "field": "nameOnlyMatches", "note": self.ADD_NOTE, **change}

    def added_route(self, run="run-a", add=None, tool="ide_find_usages", **extra):
        token = proxy.new_token()
        proxy.add_route(self.routes, token, self.entry(run, additions={tool: add or self.addition()}, **extra))
        return token

    def usages_payload(self, **change):
        """The object of a usage result with the two rows of the target."""
        return {"usages": [self.row("src/core.py", 10), self.row("src/use.py", 4)], "truncated": False,
                "nextCursor": None, "hasMore": False, "totalCollected": 2, "offset": 0, "pageSize": 100,
                "stale": False, "warnings": [], **change}

    def call_payload(self, token, payload, tool="ide_find_usages"):
        """The object of the result text of one `tools/call` whose IDE result text is `payload`, and the raw body."""
        self.fake.call_result = self.text_result(payload)
        status, raw = self.call_raw(tool, token)
        self.assertEqual(200, status)
        return json.loads(json.loads(raw)["result"]["content"][0]["text"]), raw

    def test_addition_rows_are_appended_to_the_usages(self):
        token = self.added_route()
        got, raw = self.call_payload(token, self.usages_payload())
        rows = self.addition()["rows"]
        expected = self.usages_payload(usages=self.usages_payload()["usages"] + rows, totalCollected=4,
                                       notes=[self.ADD_NOTE])
        self.assertEqual(expected, got)
        self.assertEqual(["src/core.py", "src/use.py", "src/zeta.py", "src/alpha.py"],
                         [u["file"] for u in got["usages"]])
        # Compact JSON text; the added rows have the key order of the route file.
        self.assertEqual(json.dumps(got, separators=(",", ":"), ensure_ascii=False),
                         json.loads(raw)["result"]["content"][0]["text"])
        self.assertEqual(list(self.usages_payload()) + ["notes"], list(got))
        [line] = self.log_lines("run-a")
        self.assertEqual((2, "rows", len(raw)), (line["rows_added"], line["addition"], line["bytes"]))
        self.assertEqual(self.LOG_KEYS | {"rows_added", "addition"}, set(line))

    def test_addition_field_holds_the_rows(self):
        rows = [self.row("src/zeta.py", 8), self.row("src/alpha.py", 2)]
        token = self.added_route(add=self.addition("field", field="byName", rows=rows))
        got, _ = self.call_payload(token, self.usages_payload())
        self.assertEqual(self.usages_payload(byName=rows, notes=[self.ADD_NOTE]), got)
        self.assertEqual((self.usages_payload()["usages"], 2), (got["usages"], got["totalCollected"]))
        [line] = self.log_lines("run-a")
        self.assertEqual((2, "field"), (line["rows_added"], line["addition"]))
        self.assertEqual(self.LOG_KEYS | {"rows_added", "addition"}, set(line))

    def test_addition_note_ends_the_notes(self):
        token = self.added_route()
        absent = self.usages_payload()
        cases = ((absent, [self.ADD_NOTE]), (self.usages_payload(notes=None), [self.ADD_NOTE]),
                 (self.usages_payload(notes=["src/base.py:3 is the base method."]),
                  ["src/base.py:3 is the base method.", self.ADD_NOTE]))
        for payload, notes in cases:
            with self.subTest(notes=payload.get("notes", "absent")):
                got, _ = self.call_payload(token, payload)
                self.assertEqual(notes, got["notes"])
        self.assertEqual([2, 2, 2], [line["rows_added"] for line in self.log_lines("run-a")])

    def test_answer_with_no_addition_passes_byte_for_byte(self):
        def route(**change):
            return self.added_route(run="run-u", add=self.addition(**change))

        added = route()
        no_note = self.addition()
        del no_note["note"]
        all_known = self.addition(known=[["src/core.py", 10], ["src/use.py", 4], ["src/zeta.py", 8],
                                         ["src/alpha.py", 2]])
        no_usages = self.usages_payload()
        del no_usages["usages"]
        payload = self.usages_payload()
        cases = [
            ("no additions on the route", self.token, {"result": self.text_result(payload)}),
            ("an addition for another tool", self.added_route(run="run-u", tool="ide_find_class"),
             {"result": self.text_result(payload)}),
            ("hasMore true", added, {"result": self.text_result(self.usages_payload(hasMore=True))}),
            ("a row of usages outside known", added, {"result": self.text_result(self.usages_payload(
                usages=[self.row("src/core.py", 10), self.row("src/core.py", 11)]))}),
            ("usages empty", added, {"result": self.text_result(self.usages_payload(usages=[]))}),
            ("usages absent", added, {"result": self.text_result(no_usages)}),
            ("the payload has error", added, {"result": self.text_result(self.usages_payload(error="tool_error"))}),
            ("result.isError true", added, {"result": self.text_result(payload, is_error=True)}),
            ("text that is no JSON", added, {"result": {
                "content": [{"type": "text", "text": "The index is not ready."}], "isError": False}}),
            ("notes is a text", added, {"result": self.text_result(self.usages_payload(notes="a text"))}),
            ("an addition with no note", self.added_route(run="run-u", add=no_note),
             {"result": self.text_result(payload)}),
            ("form with another value", route(form="list"), {"result": self.text_result(payload)}),
            ("rows no list", route(rows=self.row("src/zeta.py", 8)), {"result": self.text_result(payload)}),
            ("each row of the addition in usages", self.added_route(run="run-u", add=all_known),
             {"result": self.text_result(self.usages_payload(usages=self.usages_payload()["usages"] + [
                 self.row("src/alpha.py", 2), self.row("src/zeta.py", 8)]))}),
        ]
        for what, token, reply in cases:
            with self.subTest(what):
                self.fake.call_result = reply["result"]
                status, raw = self.call_raw("ide_find_usages", token)
                self.assertEqual((200, self.fake.replies[-1]), (status, raw))
        lines = self.log_lines("run-u") + self.log_lines()
        self.assertEqual(len(cases), len(lines))
        self.assertFalse(any("rows_added" in line or "addition" in line for line in lines))

    def test_addition_row_in_usages_is_left_out(self):
        add = self.addition(known=[["src/core.py", 10], ["src/use.py", 4], ["src/zeta.py", 8]])
        token = self.added_route(add=add)
        usages = self.usages_payload()["usages"] + [self.row("src/zeta.py", 8, column=9)]
        got, _ = self.call_payload(token, self.usages_payload(usages=usages, totalCollected=3))
        self.assertEqual(usages + [add["rows"][1]], got["usages"])
        self.assertEqual(4, got["totalCollected"])
        [line] = self.log_lines("run-a")
        self.assertEqual((1, "rows"), (line["rows_added"], line["addition"]))

    def test_total_collected_that_is_no_int_stays(self):
        token = self.added_route()
        absent = self.usages_payload()
        del absent["totalCollected"]
        got, _ = self.call_payload(token, absent)
        self.assertEqual(4, len(got["usages"]))
        self.assertNotIn("totalCollected", got)
        got, _ = self.call_payload(token, self.usages_payload(totalCollected=True))
        self.assertEqual(4, len(got["usages"]))
        self.assertIs(True, got["totalCollected"])

    def test_route_note_comes_before_the_addition_note(self):
        token = self.added_route(notes={"ide_find_usages": self.NOTE})
        got, _ = self.call_payload(token, self.usages_payload(notes=["src/base.py:3 is the base method."]))
        self.assertEqual(["src/base.py:3 is the base method.", self.NOTE, self.ADD_NOTE], got["notes"])
        self.assertEqual(4, len(got["usages"]))
        [line] = self.log_lines("run-a")
        self.assertEqual((True, 2, "rows"), (line["note_added"], line["rows_added"], line["addition"]))

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
