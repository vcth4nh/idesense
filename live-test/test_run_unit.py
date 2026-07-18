#!/usr/bin/env python3
"""Unit tests for run.py's offline logic (no IDE calls).

Run: python3 -m unittest test_run_unit -v   (from live-test/)

Covers the bless error gate (#82): structured {"error": ...} tool payloads
must not silently replace a previously non-error expected row.
"""
import unittest

from run import _result_has_error, _result_is_structured_error, _structured_error_bless_refusals


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


if __name__ == "__main__":
    unittest.main()
