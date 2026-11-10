#!/usr/bin/env python3
"""Unit tests for run.py's offline logic (no IDE calls).

Run: python3 -m unittest test_run_unit -v   (from live-test/)

Covers the bless error gate (#82): structured {"error": ...} tool payloads
must not silently replace a previously non-error expected row.
"""
import contextlib
import io
import shutil
import sys
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


class ResolveSuiteTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual("fixtures", run.resolve_suite(None, None, None, offline=False))
        self.assertEqual("all", run.resolve_suite(None, None, None, offline=True))
        self.assertEqual("fixtures", run.resolve_suite(None, "go", None, offline=True))
        self.assertEqual("real-products", run.resolve_suite(None, None, "caddy", offline=False))
        self.assertEqual("all", run.resolve_suite(None, "go", "caddy", offline=False))

    def test_explicit_suite_wins(self):
        self.assertEqual("all", run.resolve_suite("all", None, "caddy", offline=False))
        self.assertEqual("fixtures", run.resolve_suite("fixtures", None, None, offline=True))


class RunProductsTest(unittest.TestCase):
    A = products.Product("alpha", "goland", "o/a", "v1", "MIT", "core")
    B = products.Product("beta", "goland", "o/b", "v1", "MIT", "core")
    C = products.Product("gamma", "pycharm", "o/c", "v1", "MIT", "core", ready_timeout=120.0)

    def go(self, prods, named=False, state="ok", open_error=None, raises=None, bless=False, switched=True,
           close_error=None, **kw):
        self.opened, self.closed, self.ran, self.events, self.calls = [], [], [], [], []

        def open_product(root, p, url=None):
            self.opened.append(p.folder)
            self.events.append(f"open {p.folder}")
            return (open_error, 1.0, 2.0, switched)

        def close_products(root, ide, url=None):
            self.closed.append(ide.key)
            self.events.append(f"close {ide.key}")
            return close_error

        def run_language(name, *a, **kw):
            self.ran.append(name)
            self.calls.append((name, a, kw))
            if raises:
                raise raises
            return (3, 0)

        printed = io.StringIO()
        try:
            with mock.patch.object(run, "open_product", open_product), \
                 mock.patch.object(run, "close_products", close_products), \
                 mock.patch.object(run, "run_language", run_language), \
                 mock.patch.object(products, "checkout_state", lambda repo, rel: state), \
                 contextlib.redirect_stdout(printed):
                return run.run_products(Path("/r/live-test"), prods, named, None, bless, **kw)
        finally:
            self.printed = printed.getvalue().splitlines()

    def test_products_of_one_ide_run_in_turn_and_the_last_one_is_closed(self):
        self.assertEqual((6, 0, 0), self.go([self.A, self.B]))
        self.assertEqual((["alpha", "beta"], ["goland"]), (self.opened, self.closed))

    def test_an_ide_is_closed_before_a_product_of_the_next_ide_opens(self):
        # One product at a time in the whole fleet.
        self.assertEqual((9, 0, 0), self.go([self.A, self.C, self.B]))
        self.assertEqual(["open alpha", "open beta", "close goland", "open gamma", "close pycharm"], self.events)

    def test_missing_checkout_is_skipped_in_a_suite_run(self):
        self.assertEqual((0, 0, 1), self.go([self.A], state="missing"))
        self.assertEqual(([], []), (self.opened, self.closed))
        self.assertEqual(["[alpha] SKIPPED (checkout is missing: "
                          "git submodule update --init --depth 1 live-test/real-products/alpha)"], self.printed)

    def test_missing_checkout_fails_when_the_product_was_named(self):
        self.assertEqual((0, 1, 1), self.go([self.A], named=True, state="missing"))

    def test_pin_mismatch_fails_and_does_not_open_the_product(self):
        mismatch = "pin mismatch: HEAD aaaaaaaaaaaa != gitlink bbbbbbbbbbbb"
        self.assertEqual((0, 1, 0), self.go([self.A], state=mismatch, bless=True))
        self.assertEqual(([], []), (self.opened, self.ran))
        self.assertEqual([f"[alpha] FAIL {mismatch}"], self.printed)

    def test_switch_error_fails_the_product_and_still_closes(self):
        self.assertEqual((0, 1, 0), self.go([self.A], open_error="goland did not stop in 90 s"))
        self.assertEqual(([], ["goland"]), (self.ran, self.closed))
        self.assertEqual(["[alpha] ERROR: goland did not stop in 90 s"], self.printed)

    def test_interrupt_still_closes_the_product(self):
        with self.assertRaises(KeyboardInterrupt):
            self.go([self.A], raises=KeyboardInterrupt())
        self.assertEqual(["goland"], self.closed)

    def test_product_that_was_open_before_the_run_stays_open(self):
        self.assertEqual((3, 0, 0), self.go([self.A], switched=False))
        self.assertEqual([], self.closed)

    def test_close_error_is_one_failure(self):
        self.assertEqual((3, 1, 0), self.go([self.A], close_error="goland did not open [...] in 300 s"))
        self.assertEqual("[goland] ERROR: goland did not open [...] in 300 s", self.printed[-1])

    def test_reports_the_switch_the_readiness_and_the_elapsed_time(self):
        self.go([self.A])
        self.assertEqual("[alpha] goland: switch 1s, ready 2s", self.printed[0])
        self.assertRegex(self.printed[1], r"^\[alpha\] elapsed \d+s$")

    def test_product_run_gets_its_paths_its_url_and_its_readiness_deadline(self):
        before = time.monotonic()
        self.go([self.C], bless=True, bless_errors=True, prune=True, bless_canary=True)
        name, args, kw = self.calls[0]
        self.assertEqual(("gamma", (Path("/r/live-test/real-products/gamma"),
                                    Path("/r/live-test/real-products/_snapshots/gamma"),
                                    "http://127.0.0.1:29172/mcp/streamable-http", None, True)), (name, args))
        deadline = kw.pop("ready_deadline")
        self.assertEqual({"bless_errors": True, "prune": True, "product": self.C, "bless_canary": True}, kw)
        self.assertTrue(before + 120.0 <= deadline <= time.monotonic() + 120.0)

    def test_url_override_reaches_the_product_run(self):
        self.go([self.A], url="http://127.0.0.1:1/mcp")
        self.assertEqual("http://127.0.0.1:1/mcp", self.calls[0][1][2])


class MainSuiteTest(unittest.TestCase):
    A, B = RunProductsTest.A, RunProductsTest.B

    def main(self, *argv, product_result=(3, 0, 0)):
        self.languages, self.product_calls = [], []

        def run_language(lang, *a, **kw):
            self.languages.append(lang)
            return (5, 0)

        def run_products(root, prods, named, tool_filter, bless, **kw):
            self.product_calls.append(([p.folder for p in prods], named, tool_filter, bless, kw))
            return product_result

        printed, errors = io.StringIO(), io.StringIO()
        try:
            with mock.patch.object(sys, "argv", ["run.py", *argv]), \
                 mock.patch.object(run, "discover_languages", lambda root, only: [only or "go"]), \
                 mock.patch.object(run, "run_language", run_language), \
                 mock.patch.object(run, "run_products", run_products), \
                 mock.patch.object(products, "load_products", lambda path: [self.A, self.B]), \
                 contextlib.redirect_stdout(printed), contextlib.redirect_stderr(errors):
                return run.main()
        finally:
            self.printed, self.errors = printed.getvalue().splitlines(), errors.getvalue()

    def test_plain_command_runs_the_fixtures_and_no_product(self):
        self.assertEqual(0, self.main())
        self.assertEqual((["go"], []), (self.languages, self.product_calls))
        self.assertEqual(["fixtures: 5 passed, 0 failed", "ALL: 5 passed, 0 failed"], self.printed)

    def test_product_switch_runs_that_product_and_no_fixture(self):
        self.assertEqual(0, self.main("--product", "beta"))
        self.assertEqual([], self.languages)
        self.assertEqual((["beta"], True), self.product_calls[0][:2])
        self.assertEqual(["real-products: 3 passed, 0 failed, 0 skipped", "ALL: 3 passed, 0 failed"], self.printed)

    def test_suite_all_runs_both_and_prints_the_sums(self):
        self.assertEqual(0, self.main("--suite", "all"))
        self.assertEqual(["go"], self.languages)
        self.assertEqual((["alpha", "beta"], False), self.product_calls[0][:2])
        self.assertEqual(["fixtures: 5 passed, 0 failed", "real-products: 3 passed, 0 failed, 0 skipped",
                          "ALL: 8 passed, 0 failed"], self.printed)

    def test_language_and_product_together_run_both(self):
        self.assertEqual(0, self.main("--language", "php", "--product", "alpha"))
        self.assertEqual((["php"], ["alpha"]), (self.languages, self.product_calls[0][0]))

    def test_unknown_product_is_exit_code_2_and_nothing_runs(self):
        self.assertEqual(2, self.main("--suite", "all", "--product", "nope"))
        self.assertEqual(([], []), (self.languages, self.product_calls))
        self.assertIn("No product 'nope'", self.errors)

    def test_failed_product_gives_exit_code_1(self):
        self.assertEqual(1, self.main("--product", "alpha", product_result=(2, 1, 0)))
        self.assertEqual("ALL: 2 passed, 1 failed", self.printed[-1])

    def test_product_run_gets_the_switches(self):
        self.main("--product", "alpha", "--tool", "ide_find_usages", "--bless", "--bless-canary", "--bless-errors",
                  "--prune", "--url", "http://127.0.0.1:1/mcp")
        self.assertEqual((["alpha"], True, "ide_find_usages", True,
                          {"bless_errors": True, "prune": True, "bless_canary": True, "url": "http://127.0.0.1:1/mcp"}),
                         self.product_calls[0])

    def test_bless_canary_needs_bless_and_a_product_run(self):
        for argv in (["--product", "alpha", "--bless-canary"], ["--bless", "--bless-canary"]):
            with self.assertRaises(SystemExit) as stop:
                self.main(*argv)
            self.assertEqual(2, stop.exception.code)
            self.assertEqual(([], []), (self.languages, self.product_calls))


class ProductOfflineTest(unittest.TestCase):
    CAN = {"id": "canary-def-baseShape", "tool": "ide_find_definition", "params": {"file": "a.go", "line": 1, "column": 9}}
    SOURCE = 'func (b baseShape) Describe() string { return "private text" }\n'

    def make(self, input_rows, expected_rows, source=None):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        snap = root / "_snapshots" / "demo"
        for sub in ("inputs", "expected"):
            (snap / sub).mkdir(parents=True)
        for r in input_rows:
            with (snap / "inputs" / f"{r['tool']}.jsonl").open("a") as f:
                f.write(serialize_input_row(r) + "\n")
        for r in input_rows:
            if r["id"] in expected_rows:
                with (snap / "expected" / f"{r['tool']}.jsonl").open("a") as f:
                    f.write(run._serialize_row(r["id"], expected_rows[r["id"]]) + "\n")
        if source is not None:
            (root / "demo").mkdir()
            (root / "demo" / "a.go").write_text(source)
        return root

    def check(self, root, state=None, **kw):
        self.state_calls = []

        def checkout_state(repo, rel):
            self.state_calls.append((repo, rel))
            return state

        printed = io.StringIO()
        with mock.patch.object(products, "checkout_state", checkout_state), contextlib.redirect_stdout(printed):
            issues = run.check_fixtures(root, ["demo"], **kw)
        self.printed = printed.getvalue().splitlines()
        return issues

    def test_map_shows_the_identifier_and_no_source_line(self):
        root = self.make([self.CAN], {}, source=self.SOURCE)
        text = "\n".join(run._anchor_map_lines("demo", root / "demo", root / "_snapshots" / "demo", product=True))
        self.assertIn("| line:col | probe id | tool | identifier |", text)
        self.assertIn("| 1:9 | canary-def-baseShape | find_definition | `baseShape` |", text)
        self.assertIn("--write-anchors --product demo", text)
        self.assertNotIn("private text", text)

    def test_parked_row_needs_no_expected_row(self):
        parked = {"id": "usage-Bug", "tool": U, "params": {}, "parked": 131}
        root = self.make([self.CAN, parked], {self.CAN["id"]: {"name": "baseShape"}})
        self.assertEqual(0, self.check(root, product=True))

    def test_row_that_is_not_parked_needs_an_expected_row(self):
        row = {"id": "usage-A", "tool": U, "params": {}}
        root = self.make([self.CAN, row], {self.CAN["id"]: {}})
        self.assertEqual(1, self.check(root, product=True))
        self.assertIn("[demo] input id 'usage-A' has no expected entry — bless needed", self.printed)

    def test_expected_row_above_64_kb_is_an_issue(self):
        big = {"structure": "x" * (64 * 1024)}
        root = self.make([self.CAN], {self.CAN["id"]: big})
        self.assertEqual(1, self.check(root, product=True))

    def test_row_problems_are_issues(self):
        bad = {"id": "usage-A", "tool": U, "params": {}, "compare": "fuzzy"}
        root = self.make([self.CAN, bad], {self.CAN["id"]: {}, "usage-A": {}})
        self.assertEqual(1, self.check(root, product=True))
        self.assertIn("[demo] usage-A: compare must be one of exact, ordered, shape", self.printed)

    def test_fixture_suite_refuses_product_keys(self):
        row = {"id": "usage-A", "tool": U, "params": {}, "compare": "shape"}
        root = self.make([row], {"usage-A": {}})
        (root / "_snapshots" / "demo" / "ANCHORS.md").write_text(
            "\n".join(run._anchor_map_lines("demo", root / "demo", root / "_snapshots" / "demo")) + "\n")
        self.assertEqual(1, self.check(root))

    def test_anchors_are_checked_only_for_a_checkout_at_the_pin(self):
        gone = {"id": "def-gone", "tool": "ide_find_definition", "params": {"file": "gone.go", "line": 1, "column": 1}}
        root = self.make([self.CAN, gone], {self.CAN["id"]: {}, "def-gone": {}}, source=self.SOURCE)
        self.assertEqual(0, self.check(root, state="missing", product=True, repo_root=root))
        self.assertIn("[demo] anchors not checked: checkout is missing", self.printed)
        self.assertEqual([(root, "demo")], self.state_calls)
        # At the pin, the absent file and the absent map are one issue each.
        self.assertEqual(2, self.check(root, state="ok", product=True, repo_root=root))

    def test_written_product_map_passes_the_stale_check(self):
        root = self.make([self.CAN], {self.CAN["id"]: {}}, source=self.SOURCE)
        self.assertEqual(1, self.check(root, state="ok", product=True, repo_root=root))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, run.write_anchor_maps(root, ["demo"], product=True))
        self.assertEqual(0, self.check(root, state="ok", product=True, repo_root=root))
        self.assertNotIn("private text", (root / "_snapshots" / "demo" / "ANCHORS.md").read_text())

    def test_product_without_rows_gets_no_map(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, run.write_anchor_maps(root, ["demo"], product=True))
        self.assertEqual([], list(root.iterdir()))


class MainOfflineTest(unittest.TestCase):
    A, B = RunProductsTest.A, RunProductsTest.B

    def main(self, *argv, state="ok"):
        self.checks, self.writes = [], []

        def check_fixtures(root, langs, product=False, repo_root=None):
            self.checks.append((root.name, langs, product, repo_root and repo_root.name))
            return 1 if product else 0

        def write_anchor_maps(root, langs, product=False):
            self.writes.append((root.name, langs, product))
            return 0

        printed = io.StringIO()
        with mock.patch.object(sys, "argv", ["run.py", *argv]), \
             mock.patch.object(run, "discover_languages", lambda root, only: [only or "go"]), \
             mock.patch.object(run, "check_fixtures", check_fixtures), \
             mock.patch.object(run, "write_anchor_maps", write_anchor_maps), \
             mock.patch.object(products, "load_products", lambda path: [self.A, self.B]), \
             mock.patch.object(products, "checkout_state", lambda repo, rel: state), \
             contextlib.redirect_stdout(printed):
            code = run.main()
        self.printed = printed.getvalue().splitlines()
        return code

    def test_check_covers_both_suites_by_default(self):
        self.assertEqual(1, self.main("--check-fixtures"))
        repo = Path(run.__file__).resolve().parent.parent.name
        self.assertEqual([("fixtures", ["go"], False, None), ("real-products", ["alpha", "beta"], True, repo)],
                         self.checks)
        self.assertEqual("ALL: 1 issues", self.printed[-1])

    def test_check_of_one_suite(self):
        self.assertEqual(0, self.main("--check-fixtures", "--suite", "fixtures"))
        self.assertEqual([("fixtures", ["go"], False, None)], self.checks)
        self.main("--check-fixtures", "--product", "beta")
        self.assertEqual([("real-products", ["beta"], True)], [c[:3] for c in self.checks])

    def test_write_anchors_covers_both_suites_by_default(self):
        self.assertEqual(0, self.main("--write-anchors"))
        self.assertEqual([("fixtures", ["go"], False), ("real-products", ["alpha"], True),
                          ("real-products", ["beta"], True)], self.writes)

    def test_product_map_is_not_written_from_a_checkout_that_is_not_at_the_pin(self):
        self.assertEqual(1, self.main("--write-anchors", state="modified: 1 tracked file(s)"))
        self.assertEqual([("fixtures", ["go"], False)], self.writes)
        self.assertIn("[alpha] anchors not written: checkout is modified: 1 tracked file(s)", self.printed)

    def test_missing_checkout_is_a_skip_and_a_failure_only_for_a_named_product(self):
        self.assertEqual(0, self.main("--write-anchors", state="missing"))
        self.assertIn("[beta] anchors not written: checkout is missing", self.printed)
        self.assertEqual(1, self.main("--write-anchors", "--product", "alpha", state="missing"))
        self.assertEqual([], self.writes)


if __name__ == "__main__":
    unittest.main()
