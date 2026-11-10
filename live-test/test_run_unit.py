#!/usr/bin/env python3
"""Unit tests for run.py's offline logic (no IDE calls).

Run: python3 -m unittest test_run_unit -v   (from live-test/)

Covers the bless error gate (#82): structured {"error": ...} tool payloads
must not silently replace a previously non-error expected row.
"""
import contextlib
import io
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import fleet
import products
import run
from run import _result_has_error, _result_is_structured_error, _structured_error_bless_refusals
from run import chained_request, order_rows, row_problems, row_snapshot, serialize_input_row, wait_until


class ResultIsStructuredErrorTest(unittest.TestCase):
    def test_structured_tool_errors_detected(self):
        self.assertTrue(_result_is_structured_error({"error": "internal_error", "message": "Wrong offset: -1"}))
        self.assertTrue(_result_is_structured_error({"error": "invalid_arguments", "message": "missing 'query'"}))

    def test_normal_results_not_errors(self):
        self.assertFalse(_result_is_structured_error({"definitions": [], "warnings": None}))
        self.assertFalse(_result_is_structured_error([]))
        self.assertFalse(_result_is_structured_error("text"))
        self.assertFalse(_result_is_structured_error(None))

    def test_harness_level_errors_are_not_structured(self):
        # These stay the business of ERROR_KEYS / _result_has_error.
        self.assertFalse(_result_is_structured_error({"transport_error": "connection refused"}))
        self.assertFalse(_result_is_structured_error({"tool_error_text": "boom"}))
        self.assertFalse(_result_is_structured_error({"jsonrpc_error": {"code": -32600}}))
        self.assertTrue(_result_has_error({"transport_error": "connection refused"}))


class StructuredErrorBlessRefusalsTest(unittest.TestCase):
    ERR = {"error": "internal_error", "message": "Wrong offset: -1"}
    NEG = {"error": "invalid_arguments", "message": "missing 'query'"}
    OK = {"classes": [{"name": "Circle"}]}

    def test_error_replacing_non_error_refused(self):
        refusals = _structured_error_bless_refusals({"find-class-Circle": self.ERR}, {"find-class-Circle": self.OK})
        self.assertEqual(["find-class-Circle"], refusals)

    def test_new_error_row_refused(self):
        refusals = _structured_error_bless_refusals({"find-class-bogus": self.NEG}, {})
        self.assertEqual(["find-class-bogus"], refusals)

    def test_error_replacing_error_allowed(self):
        # Intentional negative probes stay re-blessable without the override.
        refusals = _structured_error_bless_refusals({"find-class-bogus": self.NEG}, {"find-class-bogus": self.ERR})
        self.assertEqual([], refusals)

    def test_non_error_rows_allowed(self):
        refusals = _structured_error_bless_refusals(
            {"a": self.OK, "b": {"usages": []}},
            {"a": self.ERR},
        )
        self.assertEqual([], refusals)

    def test_mixed_rows_only_bad_transitions_refused(self):
        fresh = {"a": self.OK, "b": self.ERR, "c": self.NEG, "d": self.ERR}
        expected = {"a": self.OK, "b": self.OK, "c": self.NEG}  # d is new
        self.assertEqual(["b", "d"], _structured_error_bless_refusals(fresh, expected))


class WaitUntilTest(unittest.TestCase):
    def run_with(self, results, timeout=30.0):
        t, calls = [0.0], []

        def check():
            calls.append(t[0])
            return results[min(len(calls) - 1, len(results) - 1)]

        def sleep(s):
            t[0] += s
        return wait_until(check, timeout, poll_s=5.0, sleep=sleep, clock=lambda: t[0]), calls

    def test_returns_when_the_check_passes(self):
        (err, waited), calls = self.run_with(["dumb mode", "dumb mode", None])
        self.assertEqual((None, 10.0, 3), (err, waited, len(calls)))

    def test_returns_the_last_error_after_the_timeout(self):
        (err, waited), _ = self.run_with(["cannot reach"], timeout=12.0)
        self.assertEqual("cannot reach", err)
        self.assertGreaterEqual(waited, 12.0)

    def test_zero_timeout_checks_one_time(self):
        (err, _), calls = self.run_with(["dumb mode"], timeout=0.0)
        self.assertEqual(("dumb mode", 1), (err, len(calls)))


class OpenProductTest(unittest.TestCase):
    P = products.Product("caddy", "goland", "caddyserver/caddy", "v2.11.7", "Apache-2.0", "core")
    ROOT = Path("/r/live-test")

    def switch(self, error=None):
        calls = []

        def fn(ide, wanted, post, url=None):
            calls.append((ide.key, wanted))
            return error
        return fn, calls

    FIXTURE, PRODUCT = "/r/live-test/fixtures/go", "/r/live-test/real-products/caddy"

    def test_opens_the_product_next_to_the_fixtures(self):
        fn, calls = self.switch()
        with mock.patch.object(run, "check_ready", return_value=None):
            err, _, _, switched = run.open_product(self.ROOT, self.P, switch=fn, current=lambda url, post: [self.FIXTURE])
        self.assertEqual((None, True), (err, switched))
        self.assertEqual([("goland", [self.FIXTURE, self.PRODUCT])], calls)

    def test_product_that_is_open_needs_no_switch(self):
        fn, calls = self.switch()
        with mock.patch.object(run, "check_ready", return_value=None):
            err, _, _, switched = run.open_product(self.ROOT, self.P, switch=fn,
                                                   current=lambda url, post: [self.PRODUCT, self.FIXTURE])
        self.assertEqual((None, False, []), (err, switched, calls))

    def test_switch_error_is_returned_without_a_readiness_wait(self):
        fn, _ = self.switch("goland did not stop in 90 s")
        with mock.patch.object(run, "check_ready") as ready:
            err, _, _, switched = run.open_product(self.ROOT, self.P, switch=fn, current=lambda url, post: [self.FIXTURE])
        self.assertEqual(("goland did not stop in 90 s", True), (err, switched))
        ready.assert_not_called()

    def test_close_products_leaves_the_fixtures(self):
        fn, calls = self.switch()
        self.assertIsNone(run.close_products(self.ROOT, fleet.IDES["intellij"], switch=fn))
        self.assertEqual([("intellij", ["/r/live-test/fixtures/java", "/r/live-test/fixtures/kotlin"])], calls)


U = "ide_find_usages"


class RowSnapshotTest(unittest.TestCase):
    RAW = {"usages": [{"file": "b.go", "line": 2, "column": 1, "preview": "x := y"},
                      {"file": "a.go", "line": 1, "column": 1, "preview": "y()"}],
           "hasMore": False, "totalCollected": 2, "offset": 0, "pageSize": 100, "truncated": False,
           "nextCursor": None, "stale": False}
    SORTED = [{"file": "a.go", "line": 1, "column": 1}, {"file": "b.go", "line": 2, "column": 1}]
    PAGING = {"hasMore": False, "totalCollected": 2, "offset": 0, "pageSize": 100, "truncated": False}

    def test_fixture_snapshot_is_what_it_was(self):
        self.assertEqual({"usages": self.SORTED}, row_snapshot({"id": "u", "tool": U}, self.RAW, "/p", product=False))

    def test_product_exact_keeps_the_pagination_fields_and_drops_the_source_text(self):
        self.assertEqual({"usages": self.SORTED, **self.PAGING},
                         row_snapshot({"id": "u", "tool": U}, self.RAW, "/p", product=True))

    def test_product_ordered_keeps_the_arrival_order(self):
        snap = row_snapshot({"id": "u", "tool": U, "compare": "ordered"}, self.RAW, "/p", product=True)
        self.assertEqual(["b.go", "a.go"], [u["file"] for u in snap["usages"]])

    def test_product_shape(self):
        self.assertEqual({"counts": {"usages": 2}, **self.PAGING},
                         row_snapshot({"id": "u", "tool": U, "compare": "shape"}, self.RAW, "/p", product=True))

    def test_product_snapshot_drops_context_and_documentation(self):
        raw = {"matches": [{"file": "a.go", "line": 1, "column": 1, "context": "a source line", "contextType": "CODE"}],
               "documentation": "prose", "signature": "func A()"}
        self.assertEqual({"matches": [{"file": "a.go", "line": 1, "column": 1, "contextType": "CODE"}],
                          "signature": "func A()"},
                         row_snapshot({"id": "s", "tool": "ide_search_text"}, raw, "/p", product=True))

    def test_harness_errors_pass_through_every_mode(self):
        for mode in ("exact", "ordered", "shape"):
            self.assertEqual({"transport_error": "timed out"},
                             row_snapshot({"id": "u", "tool": U, "compare": mode}, {"transport_error": "timed out"},
                                          "/p", product=True))


def rows(*specs):
    return [dict(s, _stem=s["tool"]) for s in specs]


class SerializeInputRowTest(unittest.TestCase):
    def test_fixture_row_is_unchanged(self):
        self.assertEqual('{"id":"find-class-Circle","tool":"ide_find_class","params":{"query":"Circle"}}',
                         serialize_input_row({"id": "find-class-Circle", "tool": "ide_find_class",
                                              "params": {"query": "Circle"}}))

    def test_product_keys_follow_params_in_a_fixed_order(self):
        row = {"parked": 131, "cursorFrom": "usage-Module-page1", "compare": "shape", "params": {"pageSize": 100},
               "tool": U, "id": "usage-Module-page2"}
        self.assertEqual('{"id":"usage-Module-page2","tool":"ide_find_usages","params":{"pageSize":100},'
                         '"compare":"shape","cursorFrom":"usage-Module-page1","parked":131}', serialize_input_row(row))


class RowProblemsTest(unittest.TestCase):
    CANARY = {"id": "canary-usage-App", "tool": U, "params": {}}
    PAGE1 = {"id": "a", "tool": U, "params": {}, "compare": "shape"}

    def one(self, *specs, product=True):
        problems = row_problems(rows(*specs), product=product)
        self.assertEqual(1, len(problems), problems)
        return problems[0]

    def test_clean_product_rows(self):
        r = rows(self.CANARY, self.PAGE1,
                 {"id": "b", "tool": U, "params": {}, "compare": "shape", "cursorFrom": "a"},
                 {"id": "c", "tool": U, "params": {}, "parked": 131})
        self.assertEqual([], row_problems(r, product=True))

    def test_fixture_rows_cannot_use_product_keys(self):
        self.assertEqual("usage-A: only a product row can have 'compare'",
                         self.one({"id": "usage-A", "tool": U, "params": {}, "compare": "shape"}, product=False))

    def test_fixture_rows_need_no_canary(self):
        self.assertEqual([], row_problems(rows({"id": "usage-A", "tool": U, "params": {}}), product=False))

    def test_bad_compare_mode(self):
        self.assertEqual("x: compare must be one of exact, ordered, shape",
                         self.one(self.CANARY, {"id": "x", "tool": U, "params": {}, "compare": "fuzzy"}))

    def test_cursor_source_must_exist(self):
        self.assertEqual("b: cursorFrom names no row 'zz'",
                         self.one(self.CANARY, {"id": "b", "tool": U, "params": {}, "compare": "shape", "cursorFrom": "zz"}))

    def test_cursor_source_must_have_the_same_tool(self):
        self.assertEqual("b: cursorFrom must name a row of the same tool",
                         self.one(self.CANARY, self.PAGE1, {"id": "b", "tool": "ide_search_text", "params": {},
                                                            "compare": "shape", "cursorFrom": "a"}))

    def test_chained_row_must_be_a_shape_row(self):
        self.assertEqual("b: a chained row must have compare 'shape'",
                         self.one(self.CANARY, self.PAGE1, {"id": "b", "tool": U, "params": {}, "cursorFrom": "a"}))

    def test_chain_of_chains_is_refused(self):
        self.assertEqual("c: cursorFrom must not name a chained row",
                         self.one(self.CANARY, self.PAGE1,
                                  {"id": "b", "tool": U, "params": {}, "compare": "shape", "cursorFrom": "a"},
                                  {"id": "c", "tool": U, "params": {}, "compare": "shape", "cursorFrom": "b"}))

    def test_parked_must_be_an_issue_number(self):
        for bad in (True, 0, "131"):
            self.assertEqual("x: parked must be an issue number",
                             self.one(self.CANARY, {"id": "x", "tool": U, "params": {}, "parked": bad}))

    def test_canary_cannot_be_parked_or_chained(self):
        self.assertEqual("canary-usage-App: a canary row cannot be chained or parked",
                         self.one(dict(self.CANARY, parked=131)))

    def test_product_needs_a_canary_row(self):
        self.assertEqual("no canary row", self.one(self.PAGE1))


class OrderRowsTest(unittest.TestCase):
    def test_canary_rows_first_and_chained_rows_after_their_source(self):
        r = rows({"id": "a-page2", "tool": U, "cursorFrom": "z-page1"}, {"id": "b", "tool": U},
                 {"id": "canary-x", "tool": U}, {"id": "z-page1", "tool": U})
        self.assertEqual(["canary-x", "b", "z-page1", "a-page2"], [x["id"] for x in order_rows(r)])

    def test_chained_row_without_its_source_stays_in_the_run(self):
        r = rows({"id": "b-page2", "tool": U, "cursorFrom": "gone"}, {"id": "a", "tool": U})
        self.assertEqual(["a", "b-page2"], [x["id"] for x in order_rows(r)])


class ChainedRequestTest(unittest.TestCase):
    ROW = {"id": "usage-M-page2", "tool": U, "params": {"pageSize": 100}, "compare": "shape",
           "cursorFrom": "usage-M-page1"}
    NO_CURSOR = "cursor source 'usage-M-page1' returned no nextCursor"

    def test_passes_the_fresh_cursor(self):
        req = chained_request(self.ROW, {"usages": [], "nextCursor": "abc", "hasMore": True}, "/p/caddy")
        self.assertEqual(U, req["params"]["name"])
        self.assertEqual({"pageSize": 100, "cursor": "abc", "project_path": "/p/caddy"}, req["params"]["arguments"])

    def test_source_without_a_next_cursor(self):
        self.assertEqual(self.NO_CURSOR, chained_request(self.ROW, {"usages": [], "nextCursor": None}, "/p/caddy"))

    def test_source_that_failed(self):
        self.assertEqual(self.NO_CURSOR, chained_request(self.ROW, {"transport_error": "timed out"}, "/p/caddy"))


FC = "ide_find_class"
DEMO = products.Product("demo", "goland", "o/demo", "v1", "MIT", "core")
CANARY = {"id": "canary-find-class-App", "tool": FC, "params": {"query": "App"}}
NORMAL = {"id": "find-class-Zed", "tool": FC, "params": {"query": "Zed"}}
PAGE1 = {"id": "usage-App-page1", "tool": U, "params": {"query": "p1", "pageSize": 2}, "compare": "shape"}
PAGE2 = {"id": "usage-App-page2", "tool": U, "params": {"pageSize": 2}, "compare": "shape", "cursorFrom": "usage-App-page1"}
PARKED = {"id": "usage-Bug", "tool": U, "params": {"query": "bug"}, "parked": 131}
PAGING = {"hasMore": False, "totalCollected": 1, "offset": 0, "pageSize": 25, "nextCursor": None, "stale": False}
ANSWERS = {
    "App": {"classes": [{"name": "App", "file": "app.go", "line": 1, "column": 6}], **PAGING},
    "Zed": {"classes": [], **PAGING, "totalCollected": 0},
    "p1": {"usages": [{"file": "a.go", "line": 1, "column": 1, "preview": "x"}, {"file": "a.go", "line": 2, "column": 1, "preview": "y"}],
           "hasMore": True, "totalCollected": 4, "offset": 0, "pageSize": 2, "nextCursor": "CUR", "stale": False, "truncated": True},
    "CUR": {"usages": [{"file": "a.go", "line": 3, "column": 1, "preview": "z"}, {"file": "a.go", "line": 4, "column": 1, "preview": "w"}],
            "hasMore": False, "totalCollected": 4, "offset": 2, "pageSize": 2, "nextCursor": None, "stale": False, "truncated": False},
    "bug": {"error": "internal_error", "message": "boom"},
}


def fake_post(answers):
    seen = []

    def post(url, request, timeout=60.0):
        name, args = request["params"]["name"], dict(request["params"]["arguments"])
        args.pop("project_path")
        seen.append((name, args))
        if name == "ide_index_status":
            return {"isDumbMode": False}
        value = answers[args.get("cursor") or args.get("query")]
        return value() if callable(value) else value
    post.seen = seen
    return post


class ProductRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.snap, self.project = self.tmp / "_snapshots" / "demo", self.tmp / "demo"
        (self.snap / "inputs").mkdir(parents=True)
        (self.snap / "expected").mkdir()
        for tool, specs in ((FC, [CANARY, NORMAL]), (U, [PAGE1, PAGE2, PARKED])):
            (self.snap / "inputs" / f"{tool}.jsonl").write_text("".join(serialize_input_row(s) + "\n" for s in specs))
        self.write_expected(CANARY, NORMAL, PAGE1, PAGE2)

    def write_expected(self, *specs):
        key = {CANARY["id"]: "App", NORMAL["id"]: "Zed", PAGE1["id"]: "p1", PAGE2["id"]: "CUR"}
        for tool in (FC, U):
            lines = [run._serialize_row(s["id"], row_snapshot(s, ANSWERS[key[s["id"]]], str(self.project), product=True))
                     for s in specs if s["tool"] == tool]
            (self.snap / "expected" / f"{tool}.jsonl").write_text("".join(l + "\n" for l in lines))

    def go(self, answers=ANSWERS, tool_filter=None, bless=False, **kw):
        post = fake_post(answers)
        printed = io.StringIO()
        with mock.patch.object(run, "post_jsonrpc", post), contextlib.redirect_stdout(printed):
            result = run.run_language("demo", self.project, self.snap, "http://x", tool_filter, bless, product=DEMO, **kw)
        self.printed = printed.getvalue().splitlines()
        return result, post.seen

    def expected(self):
        return run._load_expected(self.snap)

    def test_green_run_counts_every_row_but_the_parked_one(self):
        self.assertEqual((4, 0), self.go()[0])

    def test_last_line_counts_the_parked_rows(self):
        self.go()
        self.assertIn("  usage-Bug PARKED (#131)", self.printed)
        self.assertEqual("[demo] 4 passed, 0 failed, 1 parked", self.printed[-1])

    def test_parked_row_is_written_to_the_output_file(self):
        self.go()
        output = run._load_expected_by_id(self.snap / "output.jsonl")
        self.assertEqual({"error": "internal_error", "message": "boom"}, output["usage-Bug"])

    def test_canary_rows_run_first(self):
        self.assertEqual((FC, {"query": "App"}), self.go()[1][1])        # index 0 is the readiness call

    def test_chained_row_follows_its_source_with_the_fresh_cursor(self):
        seen = self.go()[1]
        i = seen.index((U, {"query": "p1", "pageSize": 2}))
        self.assertEqual((U, {"pageSize": 2, "cursor": "CUR"}), seen[i + 1])

    def test_failed_canary_stops_the_product(self):
        result, seen = self.go(dict(ANSWERS, App=dict(ANSWERS["App"], classes=[])))
        self.assertEqual((0, 1), result)
        self.assertNotIn((FC, {"query": "Zed"}), seen)
        self.assertIn("[demo] MISCONFIGURED: canary row canary-find-class-App differs", self.printed)
        self.assertFalse((self.snap / "output.jsonl").exists())

    def test_canary_is_retried_until_the_ready_deadline(self):
        wrong = iter([dict(ANSWERS["App"], classes=[])] * 2)
        flaky = dict(ANSWERS, App=lambda: next(wrong, ANSWERS["App"]))
        with mock.patch.object(run.time, "sleep"):
            result, _ = self.go(flaky, ready_deadline=time.monotonic() + 60)
        self.assertEqual((4, 0), result)

    def test_tool_filter_keeps_the_canary_gate(self):
        result, seen = self.go(tool_filter=U)
        self.assertEqual((2, 0), result)
        self.assertIn((FC, {"query": "App"}), seen)
        self.assertNotIn((FC, {"query": "Zed"}), seen)

    def test_chained_row_that_repeats_an_item_fails(self):
        repeat = dict(ANSWERS["CUR"], usages=[ANSWERS["p1"]["usages"][0], ANSWERS["CUR"]["usages"][1]])
        self.assertEqual((3, 1), self.go(dict(ANSWERS, CUR=repeat))[0])
        self.assertIn("  usage-App-page2 FAIL: repeats 1 item(s) of its source page", self.printed)

    def test_source_without_a_cursor_fails_the_chained_row_only(self):
        self.assertEqual((3, 1), self.go(dict(ANSWERS, p1=dict(ANSWERS["p1"], nextCursor=None)))[0])

    def test_canary_without_an_expected_row_does_not_stop_the_sweep(self):
        self.write_expected(NORMAL, PAGE1, PAGE2)
        result, seen = self.go()
        self.assertEqual((3, 1), result)
        self.assertIn((FC, {"query": "Zed"}), seen)

    def test_bless_writes_the_changed_row_and_no_parked_row(self):
        self.go(dict(ANSWERS, Zed=dict(ANSWERS["Zed"], totalCollected=7)), bless=True)
        self.assertEqual(7, self.expected()["find-class-Zed"]["totalCollected"])
        self.assertNotIn("usage-Bug", self.expected())

    def test_bless_is_refused_when_a_canary_differs(self):
        bad = dict(ANSWERS, App=dict(ANSWERS["App"], classes=[]), Zed=dict(ANSWERS["Zed"], totalCollected=7))
        self.assertEqual((0, 1), self.go(bad, bless=True)[0])
        self.assertEqual(0, self.expected()["find-class-Zed"]["totalCollected"])

    def test_bless_needs_blessed_canaries(self):
        self.write_expected(NORMAL, PAGE1, PAGE2)
        self.assertEqual((0, 1), self.go(bless=True)[0])
        self.assertNotIn("canary-find-class-App", self.expected())

    def test_bless_needs_a_canary_row(self):
        (self.snap / "inputs" / f"{FC}.jsonl").write_text(serialize_input_row(NORMAL) + "\n")
        self.write_expected(NORMAL, PAGE1, PAGE2)
        changed = dict(ANSWERS, Zed=dict(ANSWERS["Zed"], totalCollected=7))
        for bless_canary in (False, True):
            self.assertEqual((0, 1), self.go(changed, bless=True, bless_canary=bless_canary)[0])
        self.assertEqual(0, self.expected()["find-class-Zed"]["totalCollected"])

    def test_parked_chained_row_does_not_fail_the_run(self):
        parked_page2 = dict(PAGE2, parked=132)
        (self.snap / "inputs" / f"{U}.jsonl").write_text(
            "".join(serialize_input_row(s) + "\n" for s in (PAGE1, parked_page2, PARKED)))
        self.write_expected(CANARY, NORMAL, PAGE1)
        self.assertEqual((3, 0), self.go(dict(ANSWERS, p1=dict(ANSWERS["p1"], nextCursor=None)))[0])

    def test_bless_canary_writes_the_canary_rows(self):
        self.go(dict(ANSWERS, App=dict(ANSWERS["App"], totalCollected=2)), bless=True, bless_canary=True)
        self.assertEqual(2, self.expected()["canary-find-class-App"]["totalCollected"])


if __name__ == "__main__":
    unittest.main()
