#!/usr/bin/env python3
"""Unit tests for run.py's offline logic (no IDE calls).

Run: python3 -m unittest test_run_unit -v   (from live-test/)

Covers the bless error gate (#82): structured {"error": ...} tool payloads
must not silently replace a previously non-error expected row.
"""
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


if __name__ == "__main__":
    unittest.main()
