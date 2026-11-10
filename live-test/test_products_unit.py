#!/usr/bin/env python3
"""Unit tests for products.py (no IDE contact). Run from live-test/."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import products

CADDY = {"folder": "caddy", "ide": "goland", "repo": "caddyserver/caddy", "pin": "v2.11.7",
         "license": "Apache-2.0", "tier": "core"}


def git(cwd, *args):
    subprocess.run(["git", "-c", "protocol.file.allow=always", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=cwd, check=True, capture_output=True)


class LoadProductsTest(unittest.TestCase):
    def load(self, rows):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        (d / "products.json").write_text(json.dumps({"products": rows}))
        return products.load_products(d / "products.json")

    def test_default_timeouts(self):
        p = self.load([CADDY])[0]
        self.assertEqual(("caddy", "goland", "v2.11.7", "core", 60.0, 900.0),
                         (p.folder, p.ide, p.pin, p.tier, p.request_timeout, p.ready_timeout))

    def test_reads_the_timeouts(self):
        p = self.load([dict(CADDY, requestTimeoutSeconds=120, readyTimeoutSeconds=1800)])[0]
        self.assertEqual((120.0, 1800.0), (p.request_timeout, p.ready_timeout))

    def test_unknown_ide_names_the_product(self):
        with self.assertRaisesRegex(ValueError, "caddy: unknown ide 'gland'"):
            self.load([dict(CADDY, ide="gland")])

    def test_duplicate_folder(self):
        with self.assertRaisesRegex(ValueError, "duplicate folder 'caddy'"):
            self.load([CADDY, CADDY])

    def test_folder_must_be_a_plain_name(self):
        for bad in ("_setup", "a/b", "Caddy", ""):
            with self.assertRaises(ValueError):
                self.load([dict(CADDY, folder=bad)])

    def test_tier_must_be_core_or_optional(self):
        with self.assertRaisesRegex(ValueError, "caddy: tier must be core or optional"):
            self.load([dict(CADDY, tier="small")])

    def test_row_without_a_required_key_names_the_key(self):
        with self.assertRaisesRegex(ValueError, "caddy: missing 'pin'"):
            self.load([{k: v for k, v in CADDY.items() if k != "pin"}])

    def test_table_without_a_products_list(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        (d / "products.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "no 'products' list"):
            products.load_products(d / "products.json")

    def test_missing_file_is_an_empty_table(self):
        self.assertEqual([], products.load_products(Path("/nonexistent/products.json")))


class CheckoutStateTest(unittest.TestCase):
    REL = "live-test/real-products/demo"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        up = self.tmp / "upstream"
        up.mkdir()
        git(up, "init", "-q")
        (up / "a.txt").write_text("1\n")
        git(up, "add", "a.txt")
        git(up, "commit", "-qm", "one")
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "submodule", "add", "-q", str(up), self.REL)
        git(self.repo, "commit", "-qm", "add")
        self.sub = self.repo / self.REL

    def state(self):
        return products.checkout_state(self.repo, self.REL)

    def test_clean_checkout_at_the_pin(self):
        self.assertEqual("ok", self.state())

    def test_untracked_files_are_allowed(self):
        (self.sub / ".idea").mkdir()
        (self.sub / ".idea" / "workspace.xml").write_text("<x/>")
        self.assertEqual("ok", self.state())

    def test_missing_checkout(self):
        shutil.rmtree(self.sub)
        self.sub.mkdir()
        self.assertEqual("missing", self.state())

    def test_head_differs_from_the_gitlink(self):
        (self.sub / "b.txt").write_text("2\n")
        git(self.sub, "add", "b.txt")
        git(self.sub, "commit", "-qm", "two")
        self.assertRegex(self.state(), r"^pin mismatch: HEAD [0-9a-f]{12} != gitlink [0-9a-f]{12}$")

    def test_staged_gitlink_is_the_pin(self):
        # "Change a pin": the new commit is checked out in the submodule and its entry is staged, not yet committed.
        (self.sub / "b.txt").write_text("2\n")
        git(self.sub, "add", "b.txt")
        git(self.sub, "commit", "-qm", "two")
        git(self.repo, "add", self.REL)
        self.assertEqual("ok", self.state())

    def test_checkout_that_is_not_a_submodule_of_the_repository(self):
        other = self.repo / "other"
        other.mkdir()
        git(other, "init", "-q")
        (other / "a.txt").write_text("1\n")
        git(other, "add", "a.txt")
        git(other, "commit", "-qm", "one")
        self.assertEqual("pin mismatch: no gitlink for other", products.checkout_state(self.repo, "other"))

    def test_modified_tracked_file(self):
        (self.sub / "a.txt").write_text("changed\n")
        self.assertEqual("modified: 1 tracked file(s)", self.state())


class SnapshotFormTest(unittest.TestCase):
    PAGE = {"usages": [{"file": "a.go", "line": 1, "column": 2, "usageType": "REFERENCE", "enclosingScope": ["F"]},
                       {"file": "b.go", "line": 3, "column": 4, "usageType": "REFERENCE", "enclosingScope": None}],
            "truncated": True, "hasMore": True, "totalCollected": 500, "offset": 0, "pageSize": 2, "warnings": None}

    def test_shape_keeps_counts_and_pagination_fields_only(self):
        self.assertEqual({"counts": {"usages": 2}, "truncated": True, "hasMore": True, "totalCollected": 500,
                          "offset": 0, "pageSize": 2}, products.snapshot_form("shape", self.PAGE))

    def test_shape_counts_the_nodes_of_a_hierarchy(self):
        tree = {"element": {"name": "f", "children": None},
                "calls": [{"name": "a", "children": [{"name": "b", "children": None}, {"name": "c", "children": []}]},
                          {"name": "d", "children": None}],
                "truncated": True}
        self.assertEqual({"counts": {"calls": 2, "children": 2}, "truncated": True}, products.snapshot_form("shape", tree))

    def test_shape_keeps_the_cap_fields_of_explain_symbol(self):
        r = {"symbol": {"name": "Area"}, "supers": [], "implementations": [{"name": "Area"}],
             "implementationsTruncated": False, "usageCount": 3, "usagesTruncated": False,
             "documentationTruncated": None, "topUsages": [{"line": 1}, {"line": 2}], "signature": "func Area()"}
        self.assertEqual({"counts": {"implementations": 1, "supers": 0, "topUsages": 2},
                          "implementationsTruncated": False, "usageCount": 3, "usagesTruncated": False,
                          "documentationTruncated": None}, products.snapshot_form("shape", r))

    def test_shape_counts_the_lines_of_a_file_structure(self):
        # ide_file_structure returns its tree as one text and no list. With no count the row would pin nothing.
        r = {"file": "a.json", "language": "JSON", "structure": "a.json\n\nservers (line 2)\n  srv0 (line 3)"}
        self.assertEqual({"counts": {"structure": 4}}, products.snapshot_form("shape", r))

    def test_shape_of_a_tool_error_keeps_the_error_code(self):
        self.assertEqual({"counts": {}, "error": "scope_matches_no_files"},
                         products.snapshot_form("shape", {"error": "scope_matches_no_files", "message": "x"}))

    def test_exact_and_ordered_replace_top_usages_by_their_count(self):
        r = {"usageCount": 3, "topUsages": [{"line": 1}, {"line": 2}]}
        for mode in ("exact", "ordered"):
            self.assertEqual({"usageCount": 3, "topUsages": 2}, products.snapshot_form(mode, r))

    def test_exact_and_ordered_keep_only_the_first_line_of_a_signature(self):
        r = {"signature": "type CA struct {\nName string `json:\"name\"`\n}", "usageCount": 3}
        for mode in ("exact", "ordered"):
            self.assertEqual({"signature": "type CA struct {", "usageCount": 3}, products.snapshot_form(mode, r))

    def test_signature_of_one_line_stays(self):
        r = {"signature": "func RegisterModule(instance Module)", "usageCount": 3}
        self.assertEqual(r, products.snapshot_form("exact", r))

    def test_exact_keeps_every_other_field(self):
        self.assertEqual(self.PAGE, products.snapshot_form("exact", self.PAGE))

    def test_unknown_mode(self):
        with self.assertRaises(ValueError):
            products.snapshot_form("fuzzy", {})

    def test_repeated_items(self):
        a = {"usages": [{"file": "a.go", "line": 1}, {"file": "a.go", "line": 2}]}
        b = {"usages": [{"line": 2, "file": "a.go"}, {"file": "a.go", "line": 3}]}
        self.assertEqual(1, products.repeated_items(a, b))
        self.assertEqual(0, products.repeated_items(a, {"usages": [{"file": "z.go", "line": 9}]}))
        self.assertEqual(0, products.repeated_items({"error": "x"}, b))


class IdentifierAtTest(unittest.TestCase):
    LINE = "func (b baseShape) Describe() string {"

    def test_identifier_around_the_column(self):
        self.assertEqual("baseShape", products.identifier_at(self.LINE, 9))
        self.assertEqual("baseShape", products.identifier_at(self.LINE, 17))
        self.assertEqual("$scope_1", products.identifier_at("  $scope_1 = 2", 5))

    def test_other_character_is_returned_alone(self):
        self.assertEqual("(", products.identifier_at(self.LINE, 6))

    def test_column_outside_the_line(self):
        self.assertEqual("", products.identifier_at(self.LINE, 99))
        self.assertEqual("", products.identifier_at(self.LINE, 0))


if __name__ == "__main__":
    unittest.main()
