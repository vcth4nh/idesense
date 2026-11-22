import contextlib
import io
import json
import os
import random
import shutil
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from audit import symbols as audit
from common import keyrecord as keys
from common import lock, manifest
from common.mcp import McpClient
from common.tests.test_manifest_unit import GOLAND, OTHER, PYCHARM, fake_machine, manifest_file


class ToolError:
    """A tool result with isError true; the text is a JSON body or a plain text."""

    def __init__(self, body):
        self.text = body if isinstance(body, str) else json.dumps(body)


class RpcError:
    def __init__(self, code, message):
        self.code, self.message = code, message


class FakeMcp:
    """A fake MCP server: JSON-RPC by POST on 127.0.0.1, a free port. `answer(tool, arguments)` gives
    a payload dict, a ToolError or an RpcError. `initialize` gives the first of `versions` (the last one
    stays), and `ide_index_status` gives the first of `dumb` (smart mode when the list is empty)."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []
        self.versions = ["2.1.1-dev.12"]
        self.dumb = []
        self.requests = 0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                fake.requests += 1
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                params = body["params"]
                envelope = {"jsonrpc": "2.0", "id": body["id"]}
                if body["method"] == "initialize":
                    fake.calls.append({"method": "initialize", "params": params})
                    version = fake.versions.pop(0) if len(fake.versions) > 1 else fake.versions[0]
                    envelope["result"] = {"protocolVersion": params["protocolVersion"], "capabilities": {},
                                          "serverInfo": {"name": "idesense", "version": version}}
                    return self.reply(envelope)
                if params["name"] == "ide_index_status":
                    out = {"isDumbMode": fake.dumb.pop(0) if fake.dumb else False}
                    envelope["result"] = {"content": [{"type": "text", "text": json.dumps(out)}], "isError": False}
                    return self.reply(envelope)
                fake.calls.append({"method": body["method"], "jsonrpc": body["jsonrpc"], "path": self.path,
                                   "content_type": self.headers["Content-Type"],
                                   "tool": params["name"], "args": params["arguments"]})
                out = fake.answer(params["name"], params["arguments"])
                if isinstance(out, RpcError):
                    envelope["error"] = {"code": out.code, "message": out.message}
                elif isinstance(out, ToolError):
                    envelope["result"] = {"content": [{"type": "text", "text": out.text}], "isError": True}
                else:
                    envelope["result"] = {"content": [{"type": "text", "text": json.dumps(out)}],
                                          "structuredContent": out, "isError": False}
                self.reply(envelope)

            def reply(self, envelope):
                data = json.dumps(envelope).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/mcp/streamable-http"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def fake(test, answer):
    server = FakeMcp(answer)
    test.addCleanup(server.close)
    return server, McpClient(server.url, "/bench/trees/caddy", timeout=10.0)


def site(file, line, cls="required", why="use", col=1, rel=None):
    out = {"file": file, "line": line, "col": col, "class": cls, "why": why, "configs": ["linux"]}
    if rel is not None:
        out["rel"] = rel
    return out


def record(sites, rid="go:m.App.Run", kind="method", implementers=(), family=None, source="go/types"):
    return {"id": rid, "lang": "go", "kind": kind, "name": "Run", "container": "App",
            "decl": {"file": "a.go", "line": 1, "col": 15}, "family": family or [rid], "sites": sites,
            "implementers": list(implementers), "source": source}


def usage(file, line, col=1, usage_type="METHOD_CALL", match=None):
    row = {"file": file, "line": line, "column": col, "preview": "", "enclosingScope": []}
    if usage_type is not None:
        row["usageType"] = usage_type
    if match is not None:
        row["match"] = match
    return row


def definition(file, line, col=1):
    return {"file": file, "line": line, "column": col, "name": "Run", "kind": "METHOD", "preview": ""}


def page(items, cursor=None, field="usages", **more):
    return {field: items, "hasMore": cursor is not None, "nextCursor": cursor, "totalCollected": len(items),
            "offset": 0, "pageSize": 500, "stale": False, **more}


class CallAllPagesTest(unittest.TestCase):
    def test_call_all_pages_follows_cursor(self):
        pages = {None: page([usage("a.go", 3), usage("a.go", 4)], "c2", warnings=["degraded"], notes=["iface"]),
                 "c2": page([usage("b.go", 5), usage("b.go", 6)], "c3"),
                 "c3": page([usage("c.go", 7)])}
        server, client = fake(self, lambda tool, args: pages[args.get("cursor")])
        items, head = client.call_all_pages("ide_find_usages", {"file": "a.go", "line": 1, "column": 15,
                                                                "pageSize": 500}, "usages")
        self.assertEqual([("a.go", 3), ("a.go", 4), ("b.go", 5), ("b.go", 6), ("c.go", 7)],
                         [(u["file"], u["line"]) for u in items])
        self.assertNotIn("usages", head)
        self.assertEqual((["degraded"], ["iface"], "c2"), (head["warnings"], head["notes"], head["nextCursor"]))
        self.assertEqual([None, "c2", "c3"], [c["args"].get("cursor") for c in server.calls])
        first = server.calls[0]
        self.assertEqual({"file": "a.go", "line": 1, "column": 15, "pageSize": 500,
                          "project_path": "/bench/trees/caddy"}, first["args"])
        self.assertEqual(("tools/call", "2.0", "/mcp/streamable-http", "application/json", "ide_find_usages"),
                         (first["method"], first["jsonrpc"], first["path"], first["content_type"], first["tool"]))
        for later in server.calls[1:]:
            self.assertEqual("/bench/trees/caddy", later["args"]["project_path"])
            self.assertEqual(500, later["args"]["pageSize"])

    def test_server_version_sends_initialize(self):
        server, client = fake(self, lambda tool, args: {})
        server.versions = ["2.1.1-dev.12", "2.1.1-dev.13"]
        self.assertEqual("2.1.1-dev.12", client.server_version())
        self.assertEqual("2.1.1-dev.13", client.server_version())
        self.assertEqual(["initialize", "initialize"], [c["method"] for c in server.calls])
        self.assertEqual("2025-11-25", server.calls[0]["params"]["protocolVersion"])

    def test_client_refuses_a_fleet_port(self):
        with self.assertRaisesRegex(ValueError, "fleet"):
            McpClient("http://127.0.0.1:29172/mcp/streamable-http", "/p")


class ProbeTest(unittest.TestCase):
    def test_usages_probe_scores_against_key(self):
        rec = record([site("a.go", 1, "dnc", "decl", 15), site("a.go", 3), site("a.go", 4),
                      site("b.go", 7, col=3), site("b.go", 7, "forbidden", "decoy", 20),
                      site("c.go", 9, "forbidden", "decoy")])
        pages = {None: page([usage("a.go", 3, 5), usage("a.go", 3, 20), usage("c.go", 9),
                             usage("/usr/lib/go/src/fmt/print.go", 10)], "p2", notes=["iface"]),
                 # The second page has a required line: the probe reads all pages before it scores.
                 "p2": page([usage("b.go", 7, 3), usage("jar:///m2/x.jar!/A.class", 1)])}
        server, client = fake(self, lambda tool, args: pages[args.get("cursor")])
        res = audit.probe_usages(client, rec, 2)
        self.assertEqual({"id": "go:m.App.Run", "tool": "ide_find_usages", "repeat": 2, "error": None,
                          "answer": [["a.go", 3], ["b.go", 7], ["c.go", 9]],
                          "score": {**keys.score({("a.go", 3), ("b.go", 7), ("c.go", 9)}, rec), "marked_fp": 0},
                          "extra": {"rows": 6, "outside": 2, "fp": [["c.go", 9]], "fp_rows": [["c.go", 9, "METHOD_CALL"]],
                                    "miss": [["a.go", 4]], "off_contract": {}, "notes": ["iface"],
                                    "marked_fp": [], "marks": {"none": {"self": 2, "forbidden": 1}}}},
                         res)
        self.assertEqual((2, 1, 1, 0), tuple(res["score"][k] for k in ("tp", "fp", "miss", "ignored")))
        self.assertEqual({"file": "a.go", "line": 1, "column": 15, "pageSize": 500,
                          "project_path": "/bench/trees/caddy"}, server.calls[0]["args"])
        self.assertEqual(2, len(server.calls))

    def test_definition_probe_accepts_family_declaration(self):
        rec = record([site("a.go", 1, "dnc", "decl", 15), site("i.go", 5, "dnc", "decl", 2),
                      site("a.go", 3, col=5), site("a.go", 4, col=9), site("b.go", 7, col=3)],
                     family=["go:m.App.Run", "go:m.Runner.Run"])
        targets = {("a.go", 3, 5): definition("i.go", 5, 2), ("a.go", 4, 9): definition("a.go", 1, 15),
                   ("b.go", 7, 3): definition("z.go", 2, 6)}
        server, client = fake(self, lambda tool, args: targets[(args["file"], args["line"], args["column"])])
        res = audit.probe_definition(client, rec, 1)
        self.assertIsNone(res["error"])
        self.assertEqual("ide_find_definition", res["tool"])
        self.assertEqual([["a.go", 1], ["i.go", 5], ["z.go", 2]], res["answer"])
        s = res["score"]
        self.assertEqual((2, 1, 1), (s["tp"], s["fp"], s["miss"]))
        self.assertAlmostEqual(2 / 3, s["precision"])
        self.assertAlmostEqual(2 / 3, s["recall"])
        self.assertIs(False, s["exact"])
        self.assertEqual({"sites": 3, "outside": 0, "fp": [["z.go", 2]], "miss": [["b.go", 7]]}, res["extra"])
        self.assertEqual({"ide_find_definition"}, {c["tool"] for c in server.calls})

    def test_definition_probe_takes_at_most_five_sites(self):
        rec = record([site("a.go", 1, "dnc", "decl", 15)] + [site("a.go", line) for line in range(10, 17)])
        server, client = fake(self, lambda tool, args: definition("a.go", 1, 15))
        res = audit.probe_definition(client, rec, 1)
        self.assertEqual([10, 11, 12, 14, 15], [c["args"]["line"] for c in server.calls])
        self.assertEqual((5, 0, 0, True), tuple(res["score"][k] for k in ("tp", "fp", "miss", "exact")))
        self.assertIsNone(audit.probe_definition(client, record([site("a.go", 1, "dnc", "decl")]), 1))

    def test_implementers_probe_scores_positions(self):
        rec = record([], rid="go:m.Shape", kind="interface",
                     implementers=[{"id": "go:m.Circle", "file": "b.go", "line": 9, "col": 6},
                                   {"id": "go:m.Square", "file": "c.go", "line": 4, "col": 6}])
        server, client = fake(self, lambda tool, args: page(
            [usage("b.go", 9, 6), usage("d.go", 2, 6), usage("/go/pkg/mod/x.go", 3, 6)], field="implementations"))
        res = audit.probe_implementers(client, rec, 1)
        self.assertEqual("ide_find_implementations", res["tool"])
        self.assertEqual([["b.go", 9], ["d.go", 2]], res["answer"])
        s = res["score"]
        self.assertEqual((1, 1, 1, 0.5, 0.5, False),
                         tuple(s[k] for k in ("tp", "fp", "miss", "precision", "recall", "exact")))
        self.assertEqual({"rows": 3, "outside": 1, "fp": [["d.go", 2]], "miss": [["c.go", 4]]}, res["extra"])
        self.assertEqual(500, server.calls[0]["args"]["pageSize"])
        self.assertIsNone(audit.probe_implementers(client, record([site("a.go", 3)]), 1))

    def test_definition_probe_skips_embedded_sites(self):
        rec = record([site("a.go", 1, "dnc", "decl", 15), site("a.go", 3), site("b.go", 5, rel="embedded"),
                      site("b.go", 6, rel="embedded"), site("c.go", 7, rel="sibling")], kind="type")
        server, client = fake(self, lambda tool, args: definition("a.go", 1, 15) if tool == "ide_find_definition"
                              else page([]))
        res = audit.probe_definition(client, rec, 1)
        # A site with no rel (self) and a sibling site are probe sites; the embedded sites are not.
        self.assertEqual([("a.go", 3), ("c.go", 7)], [(c["args"]["file"], c["args"]["line"]) for c in server.calls])
        self.assertEqual((2, 0, 0, True), tuple(res["score"][k] for k in ("tp", "fp", "miss", "exact")))
        self.assertEqual(2, res["extra"]["sites"])
        only = record([site("a.go", 1, "dnc", "decl", 15), site("b.go", 5, rel="embedded")], rid="go:m.T",
                      kind="type")
        self.assertIsNone(audit.probe_definition(client, only, 1))
        # probes_for does not change; the run leaves out the probe that gives no result.
        self.assertEqual(["ide_find_usages", "ide_find_definition"], audit.probes_for(only))
        self.assertEqual(["ide_find_usages"], [r["tool"] for r in audit.run_audit([only], client, 1)])

    def test_implementers_probe_ignores_dnc_entries(self):
        rec = record([], rid="go:m.Shape", kind="interface",
                     implementers=[{"id": "go:m.Circle", "file": "b.go", "line": 9, "col": 6, "class": "required"},
                                   {"id": "go:m.Square", "file": "c.go", "line": 4, "col": 6},
                                   {"id": "go:m.Solid", "file": "i.go", "line": 2, "col": 6, "class": "dnc"},
                                   {"id": "go:m.Flat", "file": "j.go", "line": 7, "col": 6, "class": "dnc"}])
        _, client = fake(self, lambda tool, args: page(
            [usage("b.go", 9, 6), usage("i.go", 2, 6), usage("e.go", 2, 6)], field="implementations"))
        res = audit.probe_implementers(client, rec, 1)
        self.assertEqual([["b.go", 9], ["e.go", 2], ["i.go", 2]], res["answer"])
        # i.go:2 is listed and ignored; j.go:7 is absent and is no miss; c.go:4 (no class) is required.
        self.assertEqual({"tp": 1, "fp": 1, "miss": 1, "ignored": 1, "precision": 0.5, "recall": 0.5,
                          "exact": False}, res["score"])
        self.assertEqual({"rows": 3, "outside": 0, "fp": [["e.go", 2]], "miss": [["c.go", 4]]}, res["extra"])
        bad = record([], rid="go:m.Bad", kind="interface",
                     implementers=[{"id": "go:m.X", "file": "x.go", "line": 1, "col": 6, "class": "forbidden"}])
        with self.assertRaisesRegex(ValueError, "unknown implementer class 'forbidden'"):
            audit.probe_implementers(client, bad, 1)

    def test_probes_for_a_record(self):
        self.assertEqual(["ide_find_usages", "ide_find_definition"], audit.probes_for(record([site("a.go", 3)])))
        self.assertEqual(["ide_find_usages"], audit.probes_for(record([])))
        self.assertEqual(["ide_find_usages", "ide_find_implementations", "ide_find_definition"],
                         audit.probes_for(record([site("a.go", 3)], kind="interface")))
        # A reflection key has no site data: only its implementers are scored.
        self.assertEqual(["ide_find_implementations"],
                         audit.probes_for(record([], kind="class", source="reflection")))

    def test_tool_error_is_recorded_not_raised(self):
        def answer(tool, args):
            if tool == "ide_find_usages":
                return ToolError({"error": "index_not_ready", "message": "The IDE is indexing."})
            if tool == "ide_find_implementations":
                return RpcError(-32601, "Tool not found: ide_find_implementations")
            if args["line"] == 3:
                return ToolError("Could not resolve symbol definition")
            return definition("a.go", 1, 15)

        _, client = fake(self, answer)
        rec = record([site("a.go", 1, "dnc", "decl", 15), site("a.go", 3), site("a.go", 4)], kind="interface")
        res = audit.probe_usages(client, rec, 1)
        self.assertEqual(("index_not_ready: The IDE is indexing.", [], {}, {}),
                         (res["error"], res["answer"], res["score"], res["extra"]))
        res = audit.probe_implementers(client, rec, 1)
        self.assertIn("jsonrpc_error", res["error"])
        self.assertIn("Tool not found", res["error"])
        # A tool error at one site is the answer of the IDE for that site: a miss, not a record error.
        res = audit.probe_definition(client, rec, 1)
        self.assertIsNone(res["error"])
        self.assertEqual((1, 0, 1), tuple(res["score"][k] for k in ("tp", "fp", "miss")))
        self.assertEqual([["a.go", 3, "Could not resolve symbol definition"]], res["extra"]["site_errors"])
        self.assertEqual([["a.go", 3]], res["extra"]["miss"])
        # A transport error is no answer.
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        closed = McpClient(f"http://127.0.0.1:{port}/mcp/streamable-http", "/p", timeout=5.0)
        for probe in (audit.probe_usages, audit.probe_definition):
            res = probe(closed, rec, 1)
            self.assertTrue(res["error"].startswith("transport_error"), res["error"])
            self.assertEqual(([], {}), (res["answer"], res["score"]))

    def test_list_field_absent_is_an_error(self):
        _, client = fake(self, lambda tool, args: {"candidates": []})
        res = audit.probe_usages(client, record([site("a.go", 3)]), 1)
        self.assertIn("usages", res["error"])

    def test_usages_fp_rows_carry_the_usage_type(self):
        rec = record([site("a.go", 3), site("c.go", 9, "forbidden", "decoy")])
        rows = [usage("a.go", 3), usage("c.go", 9, 2, "REFERENCE"), usage("c.go", 9, 20, "METHOD_CALL"),
                usage("d.go", 2, usage_type=None)]
        _, client = fake(self, lambda tool, args: page(rows))
        res = audit.probe_usages(client, rec, 1)
        self.assertEqual([["c.go", 9], ["d.go", 2]], res["extra"]["fp"])
        # The usage type of the first result row at the line; null when the row has none.
        self.assertEqual([["c.go", 9, "REFERENCE"], ["d.go", 2, None]], res["extra"]["fp_rows"])

    def test_outside_prefixes_are_not_scored(self):
        rec = record([site("a.go", 3), site("a.go", 4)])
        rows = [usage("a.go", 3), usage(".venv/lib/x.py", 2), usage("node_modules/x.js", 2),
                usage("vendor/m/a.go", 2), usage(".git/x", 2), usage("gen/x.go", 2)]

        def answer(tool, args):
            if tool == "ide_find_usages":
                return page(rows)
            return definition(".venv/lib/x.py", 9) if args["line"] == 4 else definition("a.go", 1)

        _, client = fake(self, answer)
        res = audit.probe_usages(client, rec, 1)
        self.assertEqual([["a.go", 3], ["gen/x.go", 2]], res["answer"])
        self.assertEqual((4, [["gen/x.go", 2]]), (res["extra"]["outside"], res["extra"]["fp"]))
        res = audit.probe_usages(client, rec, 1, outside=("gen/",))
        self.assertEqual([[".git/x", 2], [".venv/lib/x.py", 2], ["a.go", 3], ["node_modules/x.js", 2],
                          ["vendor/m/a.go", 2]], res["answer"])
        self.assertEqual(1, res["extra"]["outside"])
        # In the definition probe a result below .venv/ is outside: a miss, not a false answer.
        res = audit.probe_definition(client, rec, 1)
        self.assertEqual({"sites": 2, "outside": 1, "fp": [], "miss": [["a.go", 4]]}, res["extra"])
        self.assertEqual((1, 0, 1), tuple(res["score"][k] for k in ("tp", "fp", "miss")))

    def test_capped_at_5000_rows(self):
        rows = [usage("a.go", line) for line in range(1, 5001)]

        def answer(tool, args):
            field = "usages" if tool == "ide_find_usages" else "implementations"
            if args.get("file") == "b.go":
                return page(rows[:4999], field=field)
            i = int(args.get("cursor", "c0")[1:])
            return page(rows[i * 500:(i + 1) * 500], f"c{i + 1}" if i < 9 else None, field=field)

        _, client = fake(self, answer)
        rec = record([site("a.go", 3)], kind="interface")
        small = record([site("b.go", 3)], rid="go:m.Small")
        small["decl"] = {"file": "b.go", "line": 1, "col": 6}
        results = [audit.probe_usages(client, rec, 1), audit.probe_implementers(client, rec, 1),
                   audit.probe_usages(client, small, 1)]
        self.assertEqual([(5000, True), (5000, True), (4999, None)],
                         [(r["extra"]["rows"], r["extra"].get("capped")) for r in results])
        rows_by = {(r["tool"], r["hardness"]): r for r in audit.summary_rows(
            results, {"go:m.App.Run": "easy", "go:m.Small": "easy"})}
        self.assertEqual(1, rows_by[("ide_find_usages", "all")]["capped"])
        self.assertEqual(1, rows_by[("ide_find_implementations", "all")]["capped"])

    def test_key_columns_pass_through(self):
        rec = record([site("a.go", 3, col=1), site("a.go", 4, col=7)], kind="interface")
        rec["decl"]["col"] = 23
        server, client = fake(self, lambda tool, args: definition("a.go", 1) if tool == "ide_find_definition"
                              else page([], field="usages" if tool == "ide_find_usages" else "implementations"))
        for tool in audit.probes_for(rec):
            audit.PROBES[tool](client, rec, 1)
        self.assertEqual([("ide_find_usages", 23), ("ide_find_implementations", 23), ("ide_find_definition", 1),
                          ("ide_find_definition", 7)], [(c["tool"], c["args"]["column"]) for c in server.calls])
        self.assertIn("1-based", audit.__doc__)
        self.assertIn("UTF-16 code units", audit.__doc__)
        self.assertNotIn("code points", audit.__doc__)


class UsagesViewTest(unittest.TestCase):
    def test_usages_view_makes_sibling_sites_dnc(self):
        rec = record([site("a.go", 1, "dnc", "decl", 15), site("a.go", 3, rel="self"),
                      site("b.go", 5, rel="sibling"), site("c.go", 9, "forbidden", "decoy")])
        view = audit.usages_view(rec)
        self.assertEqual({("a.go", 1): "dnc", ("a.go", 3): "required", ("b.go", 5): "dnc", ("c.go", 9): "forbidden"},
                         keys.line_classes(view))
        self.assertEqual(("dnc", "use", "sibling"), tuple(view["sites"][2][k] for k in ("class", "why", "rel")))
        self.assertEqual("required", rec["sites"][2]["class"])  # the record itself does not change
        with self.assertRaisesRegex(ValueError, "unknown rel 'cousin'"):
            audit.usages_view(record([site("a.go", 3, rel="cousin")]))
        # The probe scores against the view: the sibling line is ignored, not a false answer.
        _, client = fake(self, lambda tool, args: page([usage("a.go", 3), usage("b.go", 5)]))
        res = audit.probe_usages(client, rec, 1)
        self.assertEqual({**keys.score({("a.go", 3), ("b.go", 5)}, view), "marked_fp": 0}, res["score"])
        self.assertEqual((1, 0, 0, 1, True), tuple(res["score"][k] for k in ("tp", "fp", "miss", "ignored", "exact")))
        self.assertEqual(([], []), (res["extra"]["fp"], res["extra"]["miss"]))

    def test_usages_view_keeps_super_for_method_only(self):
        sites = [site("a.go", 3, rel="self"), site("i.go", 5, rel="super"), site("b.go", 7, rel="sub")]
        classes = {kind: keys.line_classes(audit.usages_view(record(sites, kind=kind)))
                   for kind in ("method", "iface_method", "func", "type", "interface")}
        self.assertEqual({("a.go", 3): "required", ("i.go", 5): "required", ("b.go", 7): "dnc"}, classes["method"])
        for kind in ("iface_method", "func", "type", "interface"):
            self.assertEqual({("a.go", 3): "required", ("i.go", 5): "dnc", ("b.go", 7): "dnc"}, classes[kind], kind)

    def test_embedded_rel_is_off_contract_for_every_kind(self):
        sites = [site("a.go", 3, rel="self"), site("b.go", 5, rel="embedded"),
                 site("b.go", 5, "forbidden", "decoy", col=20), site("c.go", 7, rel="embedded"),
                 site("a.go", 3, col=9, rel="embedded")]
        _, client = fake(self, lambda tool, args: page([usage("a.go", 3), usage("b.go", 5)]))
        for kind in ("method", "iface_method", "func", "type", "interface", "class", "function"):
            rec = record(sites, kind=kind)
            view = audit.usages_view(rec)
            self.assertEqual({("a.go", 3): "required", ("b.go", 5): "dnc", ("c.go", 7): "dnc"},
                             keys.line_classes(view), kind)
            res = audit.probe_usages(client, rec, 1)
            self.assertEqual((1, 0, 0, 1, True),
                             tuple(res["score"][k] for k in ("tp", "fp", "miss", "ignored", "exact")), kind)
            # a.go:3 has a contract site, so it is no off-contract line.
            self.assertEqual({"embedded": {"lines": 2, "listed": 1}}, res["extra"]["off_contract"], kind)
        rows = audit.summary_rows([res], {rec["id"]: "easy"})
        self.assertEqual((2, 1), (rows[-1]["off_lines"], rows[-1]["off_listed"]))

    def test_usages_view_decoy_on_an_off_contract_line_is_dnc(self):
        decoy = lambda file, line: site(file, line, "forbidden", "decoy", col=20)
        rec = record([site("a.go", 3, rel="self"), decoy("a.go", 3),
                      site("b.go", 5, rel="sub"), decoy("b.go", 5),
                      site("c.go", 7, rel="sibling"), decoy("c.go", 7),
                      site("d.go", 8, rel="sub"), site("d.go", 8, col=9, rel="self"), decoy("d.go", 8),
                      decoy("e.go", 9)], kind="iface_method")
        view = audit.usages_view(rec)
        self.assertEqual({("a.go", 3): "required+decoy", ("b.go", 5): "dnc", ("c.go", 7): "dnc",
                          ("d.go", 8): "required+decoy", ("e.go", 9): "forbidden"}, keys.line_classes(view))
        self.assertEqual(("dnc", "decoy"), (view["sites"][3]["class"], view["sites"][3]["why"]))
        self.assertEqual("forbidden", rec["sites"][3]["class"])  # the record itself does not change
        # A super site is a contract site of a method: the decoy on its line stays forbidden.
        method = audit.usages_view(record([site("i.go", 5, rel="super"), decoy("i.go", 5)]))
        self.assertEqual({("i.go", 5): "required+decoy"}, keys.line_classes(method))
        _, client = fake(self, lambda tool, args: page([usage("a.go", 3), usage("b.go", 5), usage("c.go", 7),
                                                        usage("d.go", 8), usage("e.go", 9)]))
        res = audit.probe_usages(client, rec, 1)
        self.assertEqual((2, 1, 0, 2), tuple(res["score"][k] for k in ("tp", "fp", "miss", "ignored")))
        self.assertEqual([["e.go", 9]], res["extra"]["fp"])
        # The off_contract counts do not change: d.go:8 has a contract site, so it is no off-contract line.
        self.assertEqual({"sub": {"lines": 1, "listed": 1}, "sibling": {"lines": 1, "listed": 1}},
                         res["extra"]["off_contract"])

    def test_site_with_no_rel_counts_as_self(self):
        rec = record([site("a.go", 3), site("a.go", 4), site("b.go", 6, rel="sibling")], kind="func")
        self.assertNotIn("rel", rec["sites"][0])
        self.assertEqual({("a.go", 3): "required", ("a.go", 4): "required", ("b.go", 6): "dnc"},
                         keys.line_classes(audit.usages_view(rec)))
        _, client = fake(self, lambda tool, args: page([usage("a.go", 3)]))
        res = audit.probe_usages(client, rec, 1)
        self.assertEqual(([["a.go", 4]], {"sibling": {"lines": 1, "listed": 0}}),
                         (res["extra"]["miss"], res["extra"]["off_contract"]))
        found = audit.disagreements([res], {rec["id"]: rec})
        self.assertEqual([{"file": "a.go", "line": 4, "configs": ["linux"], "why": ["use"], "rel": ["self"]}],
                         found[0]["miss"])

    def test_off_contract_counts_lines_and_listed(self):
        rec = record([site("a.go", 3, rel="self"), site("a.go", 3, col=9, rel="sub"),
                      site("b.go", 5, rel="sub"), site("b.go", 6, rel="sub"), site("c.go", 7, rel="sibling"),
                      site("d.go", 8, rel="sub"), site("d.go", 8, col=9, rel="sibling")], kind="iface_method")
        plain = record([site("q.go", 3)], rid="go:m.Plain")
        plain["decl"] = {"file": "p.go", "line": 1, "col": 6}

        def answer(tool, args):
            if tool == "ide_find_definition":
                return definition("p.go" if args["file"] == "q.go" else "a.go", 1)
            if args["file"] == "p.go":
                return page([usage("q.go", 3)])
            return page([usage("a.go", 3), usage("b.go", 5), usage("d.go", 8)])

        _, client = fake(self, answer)
        res = audit.probe_usages(client, rec, 1)
        # a.go:3 has a contract site: it is no off-contract line. d.go:8 counts for both relations.
        self.assertEqual({"sub": {"lines": 3, "listed": 2}, "sibling": {"lines": 2, "listed": 1}},
                         res["extra"]["off_contract"])
        self.assertEqual({}, audit.probe_usages(client, plain, 1)["extra"]["off_contract"])
        results = audit.run_audit([rec, plain], client, 1)
        rows = {r["tool"]: r for r in audit.summary_rows(results, {rec["id"]: "easy", plain["id"]: "easy"})
                if r["hardness"] == "all"}
        self.assertEqual((5, 3), (rows["ide_find_usages"]["off_lines"], rows["ide_find_usages"]["off_listed"]))
        self.assertEqual((None, None), (rows["ide_find_definition"]["off_lines"],
                                        rows["ide_find_definition"]["off_listed"]))
        text = audit.summary_text(audit.summary_rows(results, {rec["id"]: "easy", plain["id"]: "easy"}), [])
        self.assertIn("| capped | off_lines | off_listed | flakes |", text)
        self.assertIn("| ide_find_definition | all | 2 | 1.000 | 1.000 | 1.000 | 0 | 0 | 0 | - | - | 0 |", text)


# A usages result of the audit before the marks (caddy, build 2.1.1-bench.5beca97, run audit/5beca97/caddy-all),
# and the sites of its key record. Identifiers, paths and lines only.
OLD_ID = "go:github.com/caddyserver/caddy/v2/modules/caddypki.AuthorityConfig"
OLD_DECL = {"file": "modules/caddypki/ca.go", "line": 459, "col": 6}
OLD_SITES = [("modules/caddypki/acmeserver/acmeserver.go", 170, 30, "required", "use", "self"),
             ("modules/caddypki/ca.go", 222, 44, "required", "use", "self"),
             ("modules/caddypki/ca.go", 259, 4, "forbidden", "decoy", None),
             ("modules/caddypki/ca.go", 457, 4, "dnc", "comment", None),
             ("modules/caddypki/ca.go", 459, 6, "dnc", "decl", None),
             ("modules/caddytls/internalissuer.go", 105, 22, "required", "use", "self")]
OLD_RESULT = {
    "id": OLD_ID, "tool": "ide_find_usages", "repeat": 1,
    "answer": [["modules/caddypki/acmeserver/acmeserver.go", 170], ["modules/caddypki/ca.go", 222],
               ["modules/caddypki/ca.go", 259], ["modules/caddypki/ca.go", 457],
               ["modules/caddytls/internalissuer.go", 105]],
    "score": {"tp": 3, "fp": 1, "miss": 0, "ignored": 1, "precision": 0.75, "recall": 1.0, "exact": False},
    "extra": {"rows": 5, "outside": 0, "fp": [["modules/caddypki/ca.go", 259]], "miss": [],
              "fp_rows": [["modules/caddypki/ca.go", 259, "REFERENCE"]], "off_contract": {}},
    "error": None}
OLD_DISAGREEMENT = {"id": OLD_ID, "tool": "ide_find_usages", "repeats": 1, "flake": False,
                    "fp": [{"file": "modules/caddypki/ca.go", "line": 259, "key_class": "forbidden",
                            "usageType": "REFERENCE"}], "miss": [], "errors": [], "auto": ["decoy"]}


class MarksTest(unittest.TestCase):
    def test_marked_line_at_forbidden_site_is_marked_fp_not_fp(self):
        rec = record([site("a.go", 3), site("c.go", 9, "forbidden", "decoy")])
        _, client = fake(self, lambda tool, args: page([usage("a.go", 3), usage("c.go", 9, match="DYNAMIC")]))
        res = audit.probe_usages(client, rec, 1)
        self.assertEqual([["a.go", 3], ["c.go", 9]], res["answer"])
        self.assertEqual(([], []), (res["extra"]["fp"], res["extra"]["fp_rows"]))
        self.assertEqual([["c.go", 9, "DYNAMIC"]], res["extra"]["marked_fp"])
        s = res["score"]
        self.assertIs(True, s["exact"])
        self.assertEqual((1, 0, 0, 0, 1.0, 1.0, 1),
                         tuple(s[k] for k in ("tp", "fp", "miss", "ignored", "precision", "recall", "marked_fp")))

    def test_line_with_sure_and_marked_row_is_sure(self):
        rec = record([site("a.go", 3), site("c.go", 9, "forbidden", "decoy")])
        rows = [usage("a.go", 3, match="BASE"), usage("a.go", 3, 9),
                usage("c.go", 9, 2, "REFERENCE", match="BASE"), usage("c.go", 9, 20),
                usage("d.go", 2, match="DYNAMIC"), usage("d.go", 2, 7, match="BASE")]
        _, client = fake(self, lambda tool, args: page(rows))
        res = audit.probe_usages(client, rec, 1)
        # c.go:9 has a row with no match: it is a sure line, so it is a false answer.
        self.assertEqual([["c.go", 9]], res["extra"]["fp"])
        self.assertEqual([["c.go", 9, "REFERENCE"]], res["extra"]["fp_rows"])
        # d.go:2 has only marked rows: its mark is the sorted set of its match values.
        self.assertEqual([["d.go", 2, "BASE+DYNAMIC"]], res["extra"]["marked_fp"])
        self.assertEqual({"none": {"self": 1, "forbidden": 1}, "BASE+DYNAMIC": {"unknown": 1}},
                         res["extra"]["marks"])
        s = res["score"]
        self.assertEqual((1, 1, 0, 0.5, False, 1),
                         tuple(s[k] for k in ("tp", "fp", "miss", "precision", "exact", "marked_fp")))

    def test_precision_counts_only_sure_lines(self):
        rec = record([site("a.go", 3), site("a.go", 4), site("b.go", 5), site("b.go", 6), site("b.go", 7),
                      site("d.go", 8), site("c.go", 9, "forbidden", "decoy")])
        rows = [usage("a.go", 3), usage("a.go", 4), usage("c.go", 9),
                usage("b.go", 5, match="BASE"), usage("b.go", 6, match="BASE"), usage("b.go", 7, match="DYNAMIC")]
        _, client = fake(self, lambda tool, args: page(rows))
        res = audit.probe_usages(client, rec, 1)
        s = res["score"]
        self.assertEqual((5, 1, 1, 0, False, 0),
                         tuple(s[k] for k in ("tp", "fp", "miss", "ignored", "exact", "marked_fp")))
        # 2 sure required lines and 1 sure false line.
        self.assertAlmostEqual(2 / 3, s["precision"])
        # The recall counts all 5 listed required lines, sure and marked: 5 of 6.
        self.assertAlmostEqual(5 / 6, s["recall"])
        self.assertEqual([["d.go", 8]], res["extra"]["miss"])
        # With no sure line the precision is None. The recall counts the marked required line.
        _, client = fake(self, lambda tool, args: page([usage("b.go", 5, match="BASE"),
                                                        usage("c.go", 9, match="DYNAMIC")]))
        s = audit.probe_usages(client, rec, 1)["score"]
        self.assertIsNone(s["precision"])
        self.assertAlmostEqual(1 / 6, s["recall"])
        self.assertEqual((1, 0, 1), (s["tp"], s["fp"], s["marked_fp"]))

    def test_marks_table_uses_record_rel(self):
        rec = record([site("a.go", 3, rel="self"), site("i.go", 5, rel="super"), site("b.go", 7, rel="sibling"),
                      site("e.go", 2, rel="self"), site("e.go", 2, col=9, rel="super"),
                      site("c.go", 9, "forbidden", "decoy"), site("g.go", 4, "dnc", "comment")])
        rows = [usage("a.go", 3), usage("i.go", 5, match="BASE"), usage("b.go", 7), usage("e.go", 2, match="BASE"),
                usage("c.go", 9, match="DYNAMIC"), usage("g.go", 4, usage_type="COMMENT"),
                usage("h.go", 1, match="DYNAMIC"), usage("/usr/lib/go/src/x.go", 1, match="BASE")]
        _, client = fake(self, lambda tool, args: page(rows))
        res = audit.probe_usages(client, rec, 1)
        marks = res["extra"]["marks"]
        self.assertEqual(1, marks["BASE"]["super"])
        # The view makes the sibling line dnc; the marks table takes the class from the record.
        self.assertEqual(1, marks["none"]["sibling"])
        # A row outside the tree is no answer line.
        self.assertEqual({"none": {"self": 1, "sibling": 1, "dnc": 1}, "BASE": {"super": 1, "self+super": 1},
                          "DYNAMIC": {"forbidden": 1, "unknown": 1}}, marks)
        self.assertEqual([["c.go", 9, "DYNAMIC"], ["h.go", 1, "DYNAMIC"]], res["extra"]["marked_fp"])
        self.assertEqual((3, 0, 0, 2, 1.0, 2),
                         tuple(res["score"][k] for k in ("tp", "fp", "miss", "ignored", "precision", "marked_fp")))
        # The summary: a column marked_fp (the sum of the lines over the results), and a table Marks below the
        # main table, from the usages results of repeat 1 only.
        results = [res, audit.probe_usages(client, rec, 2)]
        self.assertEqual(marks, audit.marks_table(results))
        rows_by = {(r["tool"], r["hardness"]): r for r in audit.summary_rows(results, {rec["id"]: "decoys"})}
        self.assertEqual(4, rows_by[("ide_find_usages", "all")]["marked_fp"])
        text = audit.summary_text(list(rows_by.values()), [], marks=audit.marks_table(results))
        self.assertIn("| capped | off_lines | off_listed | flakes | marked_fp |", text)
        self.assertIn("| ide_find_usages | all | 1 | 1.000 | 1.000 | 1.000 | 0 | 0 | 0 | 2 | 2 | 0 | 4 |", text)
        self.assertIn("| mark | dnc | forbidden | self | self+super | sibling | super | unknown |", text)
        self.assertIn("| none | 1 | 0 | 1 | 0 | 1 | 0 | 0 |", text)
        self.assertIn("| BASE | 0 | 0 | 0 | 1 | 0 | 1 | 0 |", text)
        self.assertIn("| DYNAMIC | 0 | 1 | 0 | 0 | 0 | 0 | 1 |", text)
        self.assertLess(text.index("| tool | hardness |"), text.index("## Marks"))
        self.assertLess(text.index("| none |"), text.index("| BASE |"))

    def test_no_match_field_gives_old_score(self):
        rec = record([site(f, line, cls, why, col, rel) for f, line, col, cls, why, rel in OLD_SITES],
                     rid=OLD_ID, kind="type")
        rec["decl"] = dict(OLD_DECL)
        rows = [usage(f, line, usage_type="REFERENCE") for f, line in OLD_RESULT["answer"]]
        _, client = fake(self, lambda tool, args: page(rows))
        new = audit.probe_usages(client, rec, 1)
        # The new fields hold their zero values, and the rest equals the old result.
        self.assertEqual((0, []), (new["score"].pop("marked_fp"), new["extra"].pop("marked_fp")))
        self.assertEqual({"none": {"self": 3, "forbidden": 1, "dnc": 1}}, new["extra"].pop("marks"))
        self.assertEqual(OLD_RESULT, new)
        # The old result gives the old disagreement record.
        self.assertEqual([OLD_DISAGREEMENT], audit.disagreements([OLD_RESULT], {OLD_ID: rec}))

    def test_marked_only_record_has_class_marked(self):
        self.assertIn("marked", audit.AUTO_CLASSES)
        only = record([site("a.go", 3), site("c.go", 9, "forbidden", "decoy")], rid="go:m.Only")
        both = record([site("b.go", 3), site("b.go", 9, "forbidden", "decoy")], rid="go:m.Both")
        both["decl"] = {"file": "b.go", "line": 1, "col": 6}
        clean = record([site("k.go", 3)], rid="go:m.Clean")
        clean["decl"] = {"file": "k.go", "line": 1, "col": 6}
        pages = {"a.go": page([usage("a.go", 3), usage("c.go", 9, match="DYNAMIC")]),
                 "b.go": page([usage("b.go", 3), usage("b.go", 9), usage("d.go", 2, match="BASE")]),
                 "k.go": page([usage("k.go", 3)])}
        _, client = fake(self, lambda tool, args: pages[args["file"]])
        results = [audit.probe_usages(client, rec, 1) for rec in (only, both, clean)]
        found = audit.disagreements(results, {r["id"]: r for r in (only, both, clean)})
        # Only marked false lines: the record is listed with the class marked. A record with a false
        # answer has no class marked. A record with no disagreement is not listed.
        self.assertEqual([{"id": "go:m.Both", "tool": "ide_find_usages", "repeats": 1, "flake": False,
                           "fp": [{"file": "b.go", "line": 9, "key_class": "forbidden", "usageType": "METHOD_CALL"}],
                           "miss": [], "errors": [], "auto": ["decoy"]},
                          {"id": "go:m.Only", "tool": "ide_find_usages", "repeats": 1, "flake": False,
                           "fp": [], "miss": [], "errors": [], "auto": ["marked"]}], found)
        text = audit.disagreements_text(found, [])
        self.assertIn("| ide_find_usages | marked | 1 | `go:m.Only` |", text)
        self.assertIn("`marked`", text.split("| tool |")[0])


class RunTest(unittest.TestCase):
    def setUp(self):
        # The lock of `run` goes below a temporary data root.
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        env = mock.patch.dict(os.environ, {"BENCH_ROOT": root})
        env.start()
        self.addCleanup(env.stop)
        self.machine = fake_machine(self, root)  # the IDEs of the host change no output of a test

    def test_run_refuses_a_busy_lock(self):
        d, path = self.keyfile([record([site("a.go", 3)])])
        server, _ = fake(self, lambda tool, args: page([]))
        out = os.path.join(d, "audit")
        err = io.StringIO()
        with lock.ide_lock("bench.runner batch b1"), contextlib.redirect_stderr(err):
            self.assertEqual(2, audit.main(["run", "-keys", path, "-url", server.url, "-project", "/p",
                                            "-n", "10", "-seed", "1", "-repeats", "1", "-out", out]))
        self.assertIn("bench.runner batch b1", err.getvalue())
        self.assertEqual(0, server.requests)
        self.assertFalse(os.path.exists(out))

    def test_run_folder_is_one_run_with_no_lock(self):
        d, path = self.keyfile([record([site("a.go", 3)])])
        server, _ = fake(self, lambda tool, args: definition("a.go", 1) if tool == "ide_find_definition"
                         else page([usage("a.go", 3)]))
        out = os.path.join(d, "audit")
        with lock.ide_lock("audit.verdict run x"), contextlib.redirect_stderr(io.StringIO()):
            code = audit.run_folder(keys_file=path, url=server.url, project="/bench/trees/caddy", n=10, seed=1,
                                    repeats=1, outside=(".venv/", "gen/"), out=out)
        self.assertEqual(0, code)
        with open(os.path.join(out, "results.jsonl"), encoding="utf-8") as f:
            meta = json.loads(f.readline())
        self.assertEqual(("/bench/trees/caddy", 10, 1), (meta["project"], meta["n"], meta["repeats"]))
        with open(os.path.join(out, "summary.md"), encoding="utf-8") as f:
            self.assertIn("- outside prefixes: .venv/, gen/", f.read())

    def test_run_warns_for_a_manifest_difference_and_records_the_manifest(self):
        d, path = self.keyfile([record([site("a.go", 3)])])
        server, _ = fake(self, lambda tool, args: definition("a.go", 1) if tool == "ide_find_definition"
                         else page([usage("a.go", 3)]))
        seen = []
        for out, goland in (("same", GOLAND), ("other", OTHER)):
            manifest_file(self.machine, {"goland": goland, "pycharm": PYCHARM})
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = audit.main(["run", "-keys", path, "-url", server.url, "-project", "/bench/trees/caddy",
                                   "-n", "10", "-seed", "1", "-repeats", "1", "-out", os.path.join(d, out)])
            seen.append((code, [line for line in err.getvalue().splitlines() if line.startswith("manifest: ")]))
        self.assertEqual([(0, []), (0, seen[1][1])], seen)
        self.assertEqual(1, len(seen[1][1]), seen[1][1])
        with open(os.path.join(d, "other", "manifest.json"), encoding="utf-8") as f:
            rec = json.load(f)
        self.assertEqual(("2.1.1-dev.12", {path: manifest.file_sha256(path)}), (rec["plugin"], rec["files"]))
        self.assertEqual(({"goland": OTHER, "pycharm": PYCHARM}, {"goland": GOLAND, "pycharm": PYCHARM}),
                         (rec["ides"], rec["machine_ides"]))

    def keyfile(self, records):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        path = os.path.join(d, "symbols.jsonl")
        keys.save_keys(path, records)
        return d, path

    def test_run_exits_3_when_the_server_version_changes(self):
        d, path = self.keyfile([record([site("a.go", 3)])])
        server, _ = fake(self, lambda tool, args: definition("a.go", 1) if tool == "ide_find_definition"
                         else page([usage("a.go", 3)]))
        server.versions = ["2.1.1-dev.12", "2.1.1-dev.13"]
        out = os.path.join(d, "audit")
        self.assertEqual(3, audit.main(["run", "-keys", path, "-url", server.url, "-project", "/bench/trees/caddy",
                                        "-n", "10", "-seed", "1", "-repeats", "2", "-out", out]))
        with open(os.path.join(out, "results.jsonl"), encoding="utf-8") as f:
            results = [json.loads(line) for line in f]
        self.assertEqual({"id": "_meta", "version_start": "2.1.1-dev.12", "version_end": "2.1.1-dev.13",
                          "url": server.url, "project": "/bench/trees/caddy", "seed": 1, "n": 10, "repeats": 2},
                         results[0])
        self.assertEqual(4, len(results[1:]))
        with open(os.path.join(out, "summary.md"), encoding="utf-8") as f:
            first = f.readline()
        self.assertIn("2.1.1-dev.12", first)
        self.assertIn("2.1.1-dev.13", first)

    def test_run_refuses_old_results(self):
        d, path = self.keyfile([record([site("a.go", 3)])])
        server, _ = fake(self, lambda tool, args: page([]))
        out = os.path.join(d, "audit")
        os.makedirs(out)
        for name in ("results.jsonl", "results.jsonl.part"):
            old = os.path.join(out, name)
            with open(old, "w", encoding="utf-8") as f:
                f.write("old\n")
            self.assertEqual(2, audit.main(["run", "-keys", path, "-url", server.url, "-project", "/p",
                                            "-n", "10", "-seed", "1", "-repeats", "1", "-out", out]))
            with open(old, encoding="utf-8") as f:
                self.assertEqual("old\n", f.read())
            os.remove(old)
        self.assertEqual(0, server.requests)
        self.assertEqual([], os.listdir(out), "no manifest.json")

    def test_run_gives_one_line_for_an_absent_key_file_and_a_fleet_port(self):
        d, path = self.keyfile([record([site("a.go", 3)])])
        server, _ = fake(self, lambda tool, args: page([]))
        out = os.path.join(d, "audit")
        fleet = "http://127.0.0.1:29174/mcp/streamable-http"
        for keys_file, url, text in ((os.path.join(d, "absent.jsonl"), server.url, "absent.jsonl"),
                                     (path, fleet, "fleet IDE port")):
            with self.subTest(text):
                err = io.StringIO()
                with contextlib.redirect_stdout(err), contextlib.redirect_stderr(err):
                    code = audit.main(["run", "-keys", keys_file, "-url", url, "-project", "/p", "-n", "10",
                                       "-seed", "1", "-repeats", "1", "-out", out])
                self.assertEqual((2, 1), (code, len(err.getvalue().splitlines())), err.getvalue())
                self.assertIn(text, err.getvalue())
        self.assertEqual(0, server.requests)
        self.assertFalse(os.path.exists(out))

    def test_wait_ready_polls_until_smart_mode(self):
        server, client = fake(self, lambda tool, args: {})
        server.dumb = [True, True]
        naps, now = [], [0.0]

        def sleep(seconds):
            naps.append(seconds)
            now[0] += seconds

        self.assertIsNone(audit.wait_ready(client, 300, 5, sleep=sleep, clock=lambda: now[0]))
        self.assertEqual([5, 5], naps)
        server.dumb = [True] * 10
        self.assertIn("isDumbMode", audit.wait_ready(client, 12, 5, sleep=sleep, clock=lambda: now[0]))
        self.assertEqual([5, 5, 5, 5, 5], naps)

    def test_run_stops_with_exit_4_in_dumb_mode(self):
        d, path = self.keyfile([record([site("a.go", 3)])])
        server, _ = fake(self, lambda tool, args: page([]))
        server.dumb = [True] * 1000
        out = os.path.join(d, "audit")
        with mock.patch.object(audit, "READY_TIMEOUT", 0.2), mock.patch.object(audit, "READY_POLL", 0.05):
            self.assertEqual(4, audit.main(["run", "-keys", path, "-url", server.url, "-project", "/p",
                                            "-n", "10", "-seed", "1", "-repeats", "1", "-out", out]))
        self.assertFalse(os.path.exists(out))
        self.assertEqual([], [c for c in server.calls if c["method"] == "tools/call"])

    def test_not_ready_error_is_counted_apart(self):
        not_ready = ToolError({"error": "index_not_ready", "message": "IDE is in dumb mode, indexes not available"})

        def answer(tool, args):
            if tool == "ide_find_usages":
                return not_ready
            if tool == "ide_find_implementations":
                return RpcError(-32601, "Tool not found")
            return not_ready if args["line"] == 4 else definition("a.go", 1)

        _, client = fake(self, answer)
        rec = record([site("a.go", 3), site("a.go", 4)], kind="interface")
        results = audit.run_audit([rec], client, 1)
        # index_not_ready at a definition site is no answer of the IDE: it stops the probe.
        self.assertIn("index_not_ready", results[2]["error"])
        rows = {r["tool"]: r for r in audit.summary_rows(results, {rec["id"]: "easy"}) if r["hardness"] == "all"}
        self.assertEqual([(0, 1), (1, 0), (0, 1)],
                         [(rows[t]["errors"], rows[t]["not_ready"]) for t in audit.TOOLS])

    def test_flake_is_counted_when_repeats_differ(self):
        steady = record([site("a.go", 3)], rid="go:m.A.Run")
        flaky = record([site("b.go", 5, col=2), site("c.go", 6, "forbidden", "decoy")], rid="go:m.B.Run")
        flaky["decl"] = {"file": "b.go", "line": 1, "col": 6}
        seen = {"b": 0}

        def answer(tool, args):
            if tool == "ide_find_definition":
                return definition(args["file"], 1, 6 if args["file"] == "b.go" else 15)
            if args["file"] == "a.go":
                return page([usage("a.go", 3)])
            seen["b"] += 1
            return page([usage("b.go", 5)] + ([usage("b.go", 8)] if seen["b"] == 2 else []))

        _, client = fake(self, answer)
        results = audit.run_audit([steady, flaky], client, 3)
        self.assertEqual(12, len(results))
        self.assertEqual([1] * 4 + [2] * 4 + [3] * 4, [r["repeat"] for r in results])
        rows = {(r["tool"], r["hardness"]): r for r in audit.summary_rows(
            results, {"go:m.A.Run": "easy", "go:m.B.Run": "decoys"})}
        self.assertEqual((1, 1, 0), tuple(rows[("ide_find_usages", "decoys")][k]
                                          for k in ("symbols", "flakes", "errors")))
        self.assertEqual(0, rows[("ide_find_usages", "easy")]["flakes"])
        self.assertEqual((2, 1), (rows[("ide_find_usages", "all")]["symbols"],
                                  rows[("ide_find_usages", "all")]["flakes"]))
        self.assertEqual(0, rows[("ide_find_definition", "all")]["flakes"])
        decoys = rows[("ide_find_usages", "decoys")]
        self.assertAlmostEqual((1 + 0.5 + 1) / 3, decoys["precision"])
        self.assertAlmostEqual(1.0, decoys["recall"])
        self.assertAlmostEqual(2 / 3, decoys["exact"])

    def test_run_and_disagreements_commands_write_files(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        good = record([site("a.go", 3)], rid="go:m.A.Run")
        bad = record([site("b.go", 3), site("b.go", 4), site("b.go", 9, "forbidden", "decoy")], rid="go:m.B.Run")
        bad["decl"] = {"file": "b.go", "line": 1, "col": 6}
        keys.save_keys(os.path.join(d, "symbols.jsonl"), [good, bad, {"id": "_meta", "skipped": []}])

        def answer(tool, args):
            if tool == "ide_find_definition":
                return definition(args["file"], 1)
            if args["file"] == "a.go":
                return page([usage("a.go", 3)])
            # gen/ is outside with the -outside option of the command.
            return page([usage("b.go", 3), usage("b.go", 9), usage("gen/x.go", 2)])

        server, _ = fake(self, answer)
        out = os.path.join(d, "audit")
        self.assertEqual(0, audit.main(["run", "-keys", os.path.join(d, "symbols.jsonl"), "-url", server.url,
                                        "-project", "/bench/trees/caddy", "-n", "10", "-seed", "1",
                                        "-repeats", "1", "-outside", ".venv/,gen/", "-out", out]))
        with open(os.path.join(out, "results.jsonl"), encoding="utf-8") as f:
            results = [json.loads(line) for line in f]
        self.assertEqual([("_meta", None), ("go:m.A.Run", "ide_find_usages"), ("go:m.A.Run", "ide_find_definition"),
                          ("go:m.B.Run", "ide_find_usages"), ("go:m.B.Run", "ide_find_definition")],
                         [(r["id"], r.get("tool")) for r in results])
        self.assertEqual(("2.1.1-dev.12", "2.1.1-dev.12"), (results[0]["version_start"], results[0]["version_end"]))
        self.assertEqual(1, results[3]["extra"]["outside"])
        with open(os.path.join(out, "summary.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("# Audit\n"), text[:80])
        self.assertIn("2.1.1-dev.12", text)
        self.assertIn("| tool | hardness | symbols | precision | recall | exact | errors | not_ready | capped "
                      "| off_lines | off_listed | flakes |", text)
        self.assertIn("| ide_find_usages | decoys | 1 | 0.500 | 0.500 | 0.000 | 0 | 0 | 0 | 0 | 0 | 0 |", text)
        self.assertEqual(0, audit.main(["disagreements", "-results", out, "-keys", os.path.join(d, "symbols.jsonl")]))
        with open(os.path.join(out, "disagreements.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual([{"id": "go:m.B.Run", "tool": "ide_find_usages", "repeats": 1, "flake": False,
                           "fp": [{"file": "b.go", "line": 9, "key_class": "forbidden", "usageType": "METHOD_CALL"}],
                           "miss": [{"file": "b.go", "line": 4, "configs": ["linux"], "why": ["use"], "rel": ["self"]}],
                           "errors": [], "auto": ["decoy", "miss"]}], rows)

    def test_the_audit_reads_an_optional_use_as_required(self):
        """An optional use (a member outside the coupled family) is a use for the audit: the results, the
        disagreements and the hardness of a key with optional uses equal those of the same key with the uses
        required."""
        plain = record([site("a.go", 1, "dnc", "decl", 15), site("a.go", 3, rel="self"), site("a.go", 4, rel="super"),
                        site("b.go", 6, rel="sibling"), site("b.go", 6, "forbidden", "decoy", 9),
                        site("c.go", 2, rel="sub")], family=["go:m.App.Run", "go:m.Runner.Run"])
        split = json.loads(json.dumps(plain))
        for s in split["sites"]:
            if s.get("rel") in ("super", "sibling", "sub"):
                s.update({"class": "dnc", "optional": True})
        split["coupled"] = ["go:m.App.Run"]
        self.assertEqual(("easy", "easy"), (audit.hardness(plain), audit.hardness(split)))

        def answer(tool, args):
            if tool == "ide_find_definition":
                return definition("a.go", 1, 15)
            return page([usage("a.go", 3), usage("b.go", 6), usage("d.go", 8)])

        outputs = []
        for rec in (plain, split):
            d, path = self.keyfile([rec])
            server, _ = fake(self, answer)
            out = os.path.join(d, "audit")
            self.assertEqual(0, audit.main(["run", "-keys", path, "-url", server.url, "-project", "/p", "-n", "10",
                                            "-seed", "1", "-repeats", "1", "-out", out]))
            self.assertEqual(0, audit.main(["disagreements", "-results", out, "-keys", path]))
            got = []
            for name in ("results.jsonl", "disagreements.jsonl"):
                with open(os.path.join(out, name), encoding="utf-8") as f:
                    got.append([r for r in map(json.loads, f) if r["id"] != "_meta"])
            outputs.append(got)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(4, outputs[1][0][1]["extra"]["sites"])  # the definition probe reads 4 required sites

    def test_disagreements_classify_against_the_keys(self):
        mix = record([site("a.go", 1, "dnc", "decl", 6), site("a.go", 3), site("a.go", 4),
                      site("a.go", 4, col=9), site("b.go", 6), site("c.go", 9, "forbidden", "decoy")], rid="go:m.Mix")
        mix["sites"][2]["configs"] = ["linux", "windows"]
        mix["sites"][3]["configs"] = ["darwin"]
        del mix["sites"][4]["configs"]
        win = record([site("w_windows.go", 5)], rid="go:m.Win", kind="func")
        win["decl"] = {"file": "w.go", "line": 1, "col": 6}
        win["sites"][0]["configs"] = ["windows"]
        shape = record([], rid="go:m.Shape", kind="interface",
                       implementers=[{"id": "go:m.B", "file": "b.go", "line": 9, "col": 6},
                                     {"id": "go:m.C", "file": "c.go", "line": 4, "col": 6}])
        shape["decl"] = {"file": "s.go", "line": 1, "col": 6}
        d, path = self.keyfile([mix, win, shape])
        seen = {"w": 0}

        def answer(tool, args):
            if tool == "ide_find_definition":
                if args["file"] == "b.go":
                    return ToolError("Could not resolve symbol definition")
                return definition("w.go" if args["file"] == "w_windows.go" else "a.go", 1)
            if tool == "ide_find_implementations":
                return page([usage("b.go", 9), usage("e.go", 2)], field="implementations")
            if args["file"] == "a.go":
                return page([usage("a.go", 3, usage_type="REFERENCE"), usage("c.go", 9),
                             usage("d.go", 2, usage_type=None)])
            if args["file"] == "w.go":
                # Repeat 2 has one more row outside the tree: no false answer, but a flake.
                seen["w"] += 1
                return page([usage(".venv/x.go", 1)] if seen["w"] == 2 else [])
            return page([])

        server, _ = fake(self, answer)
        out = os.path.join(d, "audit")
        self.assertEqual(0, audit.main(["run", "-keys", path, "-url", server.url, "-project", "/p",
                                        "-n", "10", "-seed", "1", "-repeats", "2", "-out", out]))
        self.assertEqual(0, audit.main(["disagreements", "-results", out, "-keys", path]))
        with open(os.path.join(out, "disagreements.jsonl"), encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        # A definition miss has no rel field: each site of the record counts there, whatever its rel.
        no_configs = {"file": "b.go", "line": 6, "configs": [], "why": ["use"]}
        self.assertEqual([
            {"id": "go:m.Mix", "tool": "ide_find_definition", "repeats": 2, "flake": False, "fp": [],
             "miss": [no_configs], "errors": ["b.go:6: Could not resolve symbol definition"],
             "auto": ["error", "miss"]},
            {"id": "go:m.Mix", "tool": "ide_find_usages", "repeats": 2, "flake": False,
             "fp": [{"file": "c.go", "line": 9, "key_class": "forbidden", "usageType": "METHOD_CALL"},
                    {"file": "d.go", "line": 2, "key_class": "absent", "usageType": None}],
             "miss": [{"file": "a.go", "line": 4, "configs": ["darwin", "linux", "windows"], "why": ["use"],
                       "rel": ["self"]},
                      dict(no_configs, rel=["self"])],
             "errors": [], "auto": ["absent", "decoy", "miss"]},
            {"id": "go:m.Shape", "tool": "ide_find_implementations", "repeats": 2, "flake": False,
             "fp": [["e.go", 2]], "miss": [["c.go", 4]], "errors": [], "auto": ["absent", "miss"]},
            {"id": "go:m.Win", "tool": "ide_find_usages", "repeats": 2, "flake": True, "fp": [],
             "miss": [{"file": "w_windows.go", "line": 5, "configs": ["windows"], "why": ["use"], "rel": ["self"]}],
             "errors": [], "auto": ["config", "flake"]}], rows)
        with open(os.path.join(out, "disagreements.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("| tool | class | records | first ids |", text)
        self.assertIn("| ide_find_usages | config | 1 | `go:m.Win` |", text)
        self.assertIn("| ide_find_usages | miss | 1 | `go:m.Mix` |", text)
        self.assertIn("| ide_find_definition | error | 1 | `go:m.Mix` |", text)
        self.assertIn("| ide_find_implementations | absent | 1 | `go:m.Shape` |", text)
        # With the host config windows, the windows-only miss is a plain miss.
        with open(os.path.join(out, "results.jsonl"), encoding="utf-8") as f:
            results = [json.loads(line) for line in f][1:]
        by_id = {r["id"]: r for r in (mix, win, shape)}
        found = {(r["id"], r["tool"]): r["auto"] for r in audit.disagreements(results, by_id, "windows")}
        self.assertEqual(["flake", "miss"], found[("go:m.Win", "ide_find_usages")])


class SampleTest(unittest.TestCase):
    def test_hardness_is_decoys_with_a_forbidden_line(self):
        self.assertEqual("easy", audit.hardness(record([site("a.go", 3), site("a.go", 4, "dnc", "comment")])))
        self.assertEqual("decoys", audit.hardness(record([site("a.go", 3), site("a.go", 5, "forbidden", "decoy")])))
        # A decoy on a required line: a scan of the name finds a required line there.
        self.assertEqual("easy", audit.hardness(record([site("a.go", 3), site("a.go", 3, "forbidden", "decoy", 9)])))

    def test_sample_is_stable_for_a_seed(self):
        def rec(i, kind, decoy):
            sites = [site("a.go", 3)] + ([site("a.go", 4, "forbidden", "decoy")] if decoy else [])
            return record(sites, rid=f"go:m.S{i:02d}", kind=kind)

        recs = ([rec(i, "method", False) for i in range(5)] + [rec(i, "method", True) for i in range(5, 8)]
                + [rec(i, "func", False) for i in range(8, 12)] + [rec(i, "interface", False) for i in range(12, 14)]
                + [rec(14, "interface", True)])
        first = audit.sample(recs, 6, 1)
        shuffled = recs[:]
        random.Random(7).shuffle(shuffled)
        self.assertEqual([r["id"] for r in first], [r["id"] for r in audit.sample(shuffled, 6, 1)])
        self.assertEqual(6, len(first))
        self.assertEqual(sorted(r["id"] for r in first), [r["id"] for r in first])
        self.assertEqual({("method", "easy"), ("method", "decoys"), ("func", "easy"), ("interface", "easy"),
                          ("interface", "decoys")}, {(r["kind"], audit.hardness(r)) for r in first})
        self.assertNotEqual([r["id"] for r in first], [r["id"] for r in audit.sample(recs, 6, 2)])
        self.assertEqual(sorted(r["id"] for r in recs), [r["id"] for r in audit.sample(recs, 100, 1)])


if __name__ == "__main__":
    unittest.main()
