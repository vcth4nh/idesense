import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from audit import symbols as audit_symbols
from audit import verdict as audit_verdict
from audit.tests.test_symbols_unit import FakeMcp, definition, page, record, site, usage
from audit.verdict import verdict
from common import keyrecord as keys
from common import lock

A = {"audit": "x", "tool": "t", "symbol": "s1", "miss": [["f", 1]], "fp": [], "errors": []}
B = {**A, "symbol": "s2"}
OK = {"c": {"text": "t", "issue": None, "permitted": "2026-11-22"}}


class VerdictTest(unittest.TestCase):
    def test_pass(self):    self.assertEqual(verdict([A], [{**A, "cause": "c"}], OK)["result"], "pass")
    def test_new_fails(self):
        v = verdict([A, B], [{**A, "cause": "c"}], OK); self.assertEqual((v["result"], v["new"]), ("fail", [B]))
    def test_changed_lines_are_new(self):
        self.assertEqual(verdict([{**A, "miss": [["f", 1], ["f", 2]]}], [{**A, "cause": "c"}], OK)["result"], "fail")
    def test_gone_is_reported_and_passes(self):
        v = verdict([], [{**A, "cause": "c"}], OK); self.assertEqual((v["result"], len(v["gone"])), ("pass", 1))
    def test_no_cause_waits(self):       self.assertEqual(verdict([A], [{**A, "cause": None}], OK)["result"], "wait")
    def test_unknown_cause_waits(self):  self.assertEqual(verdict([A], [{**A, "cause": "zz"}], OK)["result"], "wait")
    def test_no_permission_waits(self):
        self.assertEqual(verdict([A], [{**A, "cause": "c"}], {"c": {"text": "t", "issue": 218, "permitted": None}})["result"], "wait")
    def test_an_accepted_error_passes(self):
        E = {**A, "miss": [], "errors": ["Could not resolve symbol definition"]}
        self.assertEqual(verdict([E], [{**E, "cause": "c"}], OK)["result"], "pass")

    def test_the_order_of_a_list_does_not_count(self):
        two = {**A, "miss": [["f", 1], ["f", 2]]}
        self.assertEqual("pass", verdict([two], [{**two, "miss": [["f", 2], ["f", 1]], "cause": "c"}], OK)["result"])

    def test_one_more_marked_pair_is_new(self):
        one = {**A, "marked": [["f", 3]]}
        v = verdict([{**one, "marked": [["f", 3], ["f", 4]]}], [{**one, "cause": "c"}], OK)
        self.assertEqual(("fail", [{**one, "marked": [["f", 3], ["f", 4]]}]), (v["result"], v["new"]))

    def test_the_lists_of_the_verdict(self):
        v = verdict([A], [{**A, "cause": "zz"}, {**B, "cause": None}], OK)
        self.assertEqual({"result": "wait", "new": [], "gone": [{**B, "cause": None}], "no_cause": [],
                          "no_permission": ["zz"]}, v)


def lines_file(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(line) + "\n" for line in lines)


def result(rid, tool, fp=(), miss=(), error=None, **extra):
    return {"id": rid, "tool": tool, "repeat": 1, "answer": [], "score": {}, "error": error,
            "extra": {"fp": [list(x) for x in fp], "miss": [list(x) for x in miss], **extra}}


SYMBOL = record([site("a.go", 3), site("a.go", 4), site("a.go", 9, "forbidden", "decoy")], rid="go:m.A")
CLEAN = record([site("b.go", 3)], rid="go:m.B")
SYMBOL_RESULTS = [
    {"id": "_meta", "version_start": "v", "version_end": "v"},
    result("go:m.A", "ide_find_usages", fp=[("a.go", 9)], miss=[("a.go", 4)], fp_rows=[["a.go", 9, "REFERENCE"]],
           marked_fp=[["a.go", 7, "BASE"]]),
    result("go:m.A", "ide_find_definition", miss=[("a.go", 4)],
           site_errors=[["a.go", 4, "tool_error: Could not resolve symbol definition"]]),
    result("go:m.B", "ide_find_usages", marked_fp=[["b.go", 8, "DYNAMIC"], ["b.go", 6, "BASE"]])]

CALLER_ROWS = [
    {"id": "_meta", "version": "v", "project": "/p", "keys": "k", "n": 3},
    {"id": "x", "levels": {"1": 1, "2": 0}, "property": False, "error": "tool: symbol_not_found: No symbol"},
    {"id": "y", "mapped": {"tp": 1, "fp": 0, "miss": 0, "exact": True, "miss_sites": [], "fp_sites": []},
     "raw": {"tp": 0, "fp": 1, "miss": 1, "exact": False, "miss_sites": [["d.go", 1, 1, True, ["linux"]]],
             "fp_sites": [["d.go", 5]]}},
    {"id": "z", "raw": {"tp": 0, "fp": 0, "miss": 0, "exact": True, "miss_sites": [], "fp_sites": []},
     "mapped": {"tp": 1, "fp": 1, "miss": 2, "exact": False, "fp_sites": [["q.go", 2]],
                "miss_sites": [["c.go", 9, 2, False, ["linux"]], ["b.go", 1, 1, False, ["linux"]]]}}]


def dyn_part(exact, miss_sites=(), fp_sites=()):
    return {"tp": 1, "fp": len(fp_sites), "miss": len(miss_sites), "ignored": 0, "exact": exact, "miss_proof": {},
            "miss_sites": [list(x) for x in miss_sites], "fp_sites": [list(x) for x in fp_sites]}


DYN_ROWS = [
    {"id": "_meta", "version": "v", "project": "/p", "n": 2},
    {"id": "m", "name": "T.m", "dynamic": {}, "hierarchy_nodes": 1, "usages_error": "tool: index_not_ready: x",
     "hierarchy": dyn_part(False, [("t.go", 1)])},
    {"id": "n", "name": "T.n", "dynamic": {}, "hierarchy_nodes": 1, "usage_rows": 2, "usage_marks": {},
     "usage_notes": 0, "hierarchy": dyn_part(True), "usages": dyn_part(False, fp_sites=[("u.go", 3)])}]


class FromTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def test_from_symbols_makes_one_line_for_each_record_and_tool(self):
        lines_file(os.path.join(self.dir, "res", "results.jsonl"), SYMBOL_RESULTS)
        keys.save_keys(os.path.join(self.dir, "symbols.jsonl"), [SYMBOL, CLEAN, {"id": "_meta"}])
        found = audit_verdict.from_symbols("caddy-symbols", os.path.join(self.dir, "res"),
                                           os.path.join(self.dir, "symbols.jsonl"))
        self.assertEqual([{"audit": "caddy-symbols", "tool": "ide_find_definition", "symbol": "go:m.A",
                           "miss": [["a.go", 4]], "fp": [], "marked": [],
                           "errors": ["a.go:4: tool_error: Could not resolve symbol definition"]},
                          {"audit": "caddy-symbols", "tool": "ide_find_usages", "symbol": "go:m.A",
                           "miss": [["a.go", 4]], "fp": [["a.go", 9]], "marked": [["a.go", 7]], "errors": []},
                          # Only marked lines: the line has the marked pairs.
                          {"audit": "caddy-symbols", "tool": "ide_find_usages", "symbol": "go:m.B",
                           "miss": [], "fp": [], "marked": [["b.go", 6], ["b.go", 8]], "errors": []}], found)
        self.assertEqual(["audit", "tool", "symbol", "miss", "fp", "marked", "errors"], list(found[0]))

    def test_from_symbols_refuses_an_id_that_the_keys_do_not_hold(self):
        lines_file(os.path.join(self.dir, "res", "results.jsonl"), SYMBOL_RESULTS)
        keys.save_keys(os.path.join(self.dir, "symbols.jsonl"), [CLEAN])
        with self.assertRaisesRegex(ValueError, "go:m.A"):
            audit_verdict.from_symbols("s", os.path.join(self.dir, "res"), os.path.join(self.dir, "symbols.jsonl"))

    def test_from_callers_uses_the_mapped_comparison(self):
        path = os.path.join(self.dir, "callers.jsonl")
        lines_file(path, CALLER_ROWS)
        self.assertEqual([{"audit": "c", "tool": "ide_call_hierarchy", "symbol": "x", "miss": [], "fp": [],
                           "marked": [], "errors": ["tool: symbol_not_found: No symbol"]},
                          {"audit": "c", "tool": "ide_call_hierarchy", "symbol": "z", "miss": [["b.go", 1], ["c.go", 9]],
                           "fp": [["q.go", 2]], "marked": [], "errors": []}], audit_verdict.from_callers("c", path))

    def test_from_dyn_gives_a_line_for_each_tool(self):
        path = os.path.join(self.dir, "dyn.jsonl")
        lines_file(path, DYN_ROWS)
        self.assertEqual([{"audit": "d", "tool": "ide_call_hierarchy", "symbol": "m", "miss": [["t.go", 1]], "fp": [],
                           "marked": [], "errors": []},
                          {"audit": "d", "tool": "ide_find_usages", "symbol": "m", "miss": [], "fp": [], "marked": [],
                           "errors": ["tool: index_not_ready: x"]},
                          {"audit": "d", "tool": "ide_find_usages", "symbol": "n", "miss": [], "fp": [["u.go", 3]],
                           "marked": [], "errors": []}], audit_verdict.from_dyn("d", path))

    def test_from_dyn_refuses_a_row_of_the_old_script(self):
        old = json.loads(json.dumps(DYN_ROWS))
        del old[1]["hierarchy"]["miss_sites"]
        path = os.path.join(self.dir, "dyn.jsonl")
        lines_file(path, old)
        with self.assertRaisesRegex(ValueError, "miss_sites"):
            audit_verdict.from_dyn("d", path)


class ProposeTest(unittest.TestCase):
    def test_propose_keeps_a_cause_and_writes_null_for_a_new_line(self):
        other = {**A, "audit": "w", "cause": "c"}
        changed = {**B, "miss": [["f", 1], ["f", 2]]}
        gone = {**A, "symbol": "s0", "cause": "c"}
        new = {**A, "symbol": "s3"}
        accepted = [{**B, "cause": "c"}, other, {**A, "cause": "c"}, gone]
        self.assertEqual([other, {**A, "cause": "c"}, {**changed, "cause": None}, {**new, "cause": None}],
                         audit_verdict.propose([new, changed, A], accepted, "x"))


ENTRIES = [{"name": "caddy-symbols", "tree": "caddy", "kind": "symbols", "keys": "caddy/symbols.jsonl",
            "calls": None, "n": 10, "seed": 1, "repeats": 1, "ids": None},
           {"name": "caddy-plant-1-callers", "tree": "caddy-plant-1", "kind": "callers",
            "keys": "caddy-plant-1/callers.jsonl", "calls": "caddy-plant-1/calls.jsonl", "n": None, "seed": None,
            "repeats": None, "ids": ["z"]}]


class MainTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.root = os.path.join(self.dir, "bench")
        env = mock.patch.dict(os.environ, {"BENCH_ROOT": self.root})
        env.start()
        self.addCleanup(env.stop)
        self.audits = os.path.join(self.dir, "audits.json")
        with open(self.audits, "w", encoding="utf-8") as f:
            json.dump(ENTRIES, f)
        patch = mock.patch.object(audit_verdict, "AUDITS_FILE", self.audits)
        patch.start()
        self.addCleanup(patch.stop)
        self.accepted = os.path.join(self.dir, "accepted")
        self.callers = os.path.join(self.dir, "callers.jsonl")
        lines_file(self.callers, CALLER_ROWS)

    def main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = audit_verdict.main(list(argv))
        return code, out.getvalue()

    def check(self):
        return self.main("check", "-name", "caddy-plant-1-callers", "-callers", self.callers,
                         "-accepted", self.accepted)

    def test_check_gives_fail_then_wait_then_pass(self):
        code, out = self.check()
        self.assertEqual(1, code)
        self.assertIn("caddy-plant-1-callers: fail", out)
        self.assertIn('"symbol": "z"', out)
        self.assertEqual(0, self.main("propose", "-name", "caddy-plant-1-callers", "-callers", self.callers,
                                      "-accepted", self.accepted)[0])
        path = os.path.join(self.accepted, "caddy.jsonl")
        with open(path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f]
        self.assertEqual([("x", None), ("z", None)], [(line["symbol"], line["cause"]) for line in lines])
        self.assertEqual(3, self.check()[0])
        lines_file(path, [{**line, "cause": "c"} for line in lines])
        self.assertEqual(3, self.check()[0])
        with open(os.path.join(self.accepted, "causes.json"), "w", encoding="utf-8") as f:
            json.dump(OK, f)
        self.assertEqual(0, self.check()[0])

    def test_propose_keeps_the_lines_of_another_audit(self):
        other = {**A, "audit": "caddy-symbols", "cause": "c"}
        lines_file(os.path.join(self.accepted, "caddy.jsonl"), [other])
        self.main("propose", "-name", "caddy-plant-1-callers", "-callers", self.callers, "-accepted", self.accepted)
        with open(os.path.join(self.accepted, "caddy.jsonl"), encoding="utf-8") as f:
            lines = [json.loads(line) for line in f]
        self.assertEqual(["caddy-plant-1-callers", "caddy-plant-1-callers", "caddy-symbols"],
                         [line["audit"] for line in lines])
        self.assertEqual(other, lines[2])

    def test_check_refuses_an_unknown_name_and_another_kind(self):
        code, out = self.main("check", "-name", "zz", "-callers", self.callers)
        self.assertEqual((2, True), (code, "zz" in out))
        code, out = self.main("check", "-name", "caddy-symbols", "-callers", self.callers)
        self.assertEqual((2, True), (code, "symbols" in out))
        code, out = self.main("check", "-name", "caddy-symbols", "-symbols", self.dir)
        self.assertEqual((2, True), (code, "-keys" in out))

    def run_setup(self):
        keys.save_keys(os.path.join(self.root, "keys", "caddy", "symbols.jsonl"), [SYMBOL])
        os.makedirs(os.path.join(self.root, "trees"))
        with open(os.path.join(self.root, "trees", "slots.json"), "w", encoding="utf-8") as f:
            json.dump({"caddy": {"slot": "2e57", "path": "/bench/trees/caddy", "product": "caddy"}}, f)
        with open(self.audits, "w", encoding="utf-8") as f:
            json.dump(ENTRIES[:1], f)

        def answer(tool, args):
            if tool == "ide_find_definition":
                return definition("a.go", 1)
            return page([usage("a.go", 3)])

        server = FakeMcp(answer)
        self.addCleanup(server.close)
        return server

    def run_args(self, server, out):
        return ("run", "-url-goland", server.url, "-url-pycharm", server.url, "-out", os.path.join(self.dir, out),
                "-accepted", self.accepted)

    def verdict_file(self, out):
        with open(os.path.join(self.dir, out, "verdict.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_run_with_one_symbols_audit(self):
        server = self.run_setup()
        code, out = self.main(*self.run_args(server, "run1"))
        self.assertEqual(1, code, out)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "run1", "caddy-symbols", "results.jsonl")))
        line = {"audit": "caddy-symbols", "tool": "ide_find_usages", "symbol": "go:m.A", "miss": [["a.go", 4]],
                "fp": [], "marked": [], "errors": []}
        self.assertIn(json.dumps(line), out)
        self.assertIn("total: fail", out)
        self.assertEqual({"result": "fail", "audits": [{"name": "caddy-symbols", "verdict": {
            "result": "fail", "new": [line], "gone": [], "no_cause": [], "no_permission": []}}]},
            self.verdict_file("run1"))
        self.assertEqual({"/bench/trees/caddy"}, {c["args"]["project_path"] for c in server.calls if "args" in c})
        lines_file(os.path.join(self.accepted, "caddy.jsonl"), [{**line, "cause": "c"}])
        with open(os.path.join(self.accepted, "causes.json"), "w", encoding="utf-8") as f:
            json.dump(OK, f)
        code, out = self.main(*self.run_args(server, "run2"))
        self.assertEqual(0, code, out)
        self.assertIn("caddy-symbols: pass", out)
        self.assertIn("total: pass", out)
        self.assertEqual({"result": "pass", "audits": [{"name": "caddy-symbols", "verdict": {
            "result": "pass", "new": [], "gone": [], "no_cause": [], "no_permission": []}}]},
            self.verdict_file("run2"))
        # The folder run2 exists now: no second run into it.
        self.assertEqual(2, self.main(*self.run_args(server, "run2"))[0])

    def test_run_stops_with_exit_4_in_dumb_mode(self):
        server = self.run_setup()
        server.dumb = [True] * 1000
        with mock.patch.object(audit_symbols, "READY_TIMEOUT", 0.2), \
                mock.patch.object(audit_symbols, "READY_POLL", 0.05):
            code, out = self.main(*self.run_args(server, "run1"))
        self.assertEqual(4, code)
        self.assertIn("caddy-symbols: the audit stopped with exit code 4. No verdict.", out)
        self.assertNotIn("total:", out)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "run1", "verdict.json")))

    def test_run_refuses_an_absent_slot_and_a_fleet_port(self):
        server = self.run_setup()
        os.remove(os.path.join(self.root, "trees", "slots.json"))
        code, out = self.main(*self.run_args(server, "run1"))
        self.assertEqual((2, True), (code, "the tree caddy has no slot" in out))
        code, out = self.main("run", "-url-goland", "http://127.0.0.1:29174/mcp/streamable-http", "-url-pycharm",
                              server.url, "-out", os.path.join(self.dir, "run1"))
        self.assertEqual((2, True), (code, "fleet IDE port" in out))
        self.assertEqual(0, server.requests)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "run1")))

    def test_run_refuses_a_busy_lock(self):
        server = self.run_setup()
        with lock.ide_lock("bench.runner batch b1"):
            code, out = self.main(*self.run_args(server, "run1"))
        self.assertEqual(2, code)
        self.assertIn("bench.runner batch b1", out)
        self.assertEqual(0, server.requests)


class TrackedFilesTest(unittest.TestCase):
    def test_the_tracked_audits_file_is_valid(self):
        entries = audit_verdict.load_audits(audit_verdict.AUDITS_FILE)
        self.assertEqual({"symbols", "callers", "dyn"}, {e["kind"] for e in entries})

    def test_no_tracked_audit_repeats_another(self):
        """No two entries with the same kind, tree, keys and ids. No entry with ids next to a full audit of the same
        kind, tree and keys (ids null, and no sample `n`): the full audit covers the ids."""
        entries = audit_verdict.load_audits(audit_verdict.AUDITS_FILE)
        same = [(e["kind"], e["tree"], e["keys"], json.dumps(e["ids"])) for e in entries]
        self.assertEqual(len(same), len(set(same)))
        full = {(e["kind"], e["tree"], e["keys"]) for e in entries if e["ids"] is None and e["n"] is None}
        self.assertEqual([], [e["name"] for e in entries
                              if e["ids"] is not None and (e["kind"], e["tree"], e["keys"]) in full])

    def test_a_bad_entry_is_refused(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        path = os.path.join(d, "audits.json")
        for bad, text in (({"kind": "other"}, "kind"), ({"keys": "/abs/symbols.jsonl"}, "keys"),
                          ({"n": None}, "n"), ({"name": "caddy-plant-1-callers"}, "name"),
                          ({"tree": "zz"}, "zz"), ({"extra": 1}, "fields")):
            with open(path, "w", encoding="utf-8") as f:
                json.dump([{**ENTRIES[0], **bad}, ENTRIES[1]], f)
            with self.assertRaisesRegex(ValueError, text):
                audit_verdict.load_audits(path)

    def test_the_tracked_causes_wait_for_permission(self):
        with open(os.path.join(audit_verdict.ACCEPTED, "causes.json"), encoding="utf-8") as f:
            causes = json.load(f)
        self.assertEqual({"closure-node", "interface-calls-option-off", "other-build-configuration",
                          "other-build-configuration-use", "python-property-callers",
                          "receiver-type-does-not-declare"}, set(causes))
        self.assertEqual({"closure-node": 223, "interface-calls-option-off": 218, "other-build-configuration": 221,
                          "other-build-configuration-use": None, "python-property-callers": 224,
                          "receiver-type-does-not-declare": 220}, {n: c["issue"] for n, c in causes.items()})
        for name, cause in causes.items():
            self.assertEqual({"text", "issue", "permitted"}, set(cause), name)
            self.assertIsNone(cause["permitted"], name)
            self.assertTrue(cause["text"], name)


if __name__ == "__main__":
    unittest.main()
