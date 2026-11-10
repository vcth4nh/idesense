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
from run import wait_until


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


if __name__ == "__main__":
    unittest.main()
