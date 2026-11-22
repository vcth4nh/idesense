import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from keygen import pykeys

HERE = os.path.dirname(os.path.abspath(__file__))
BENCHDIR = os.path.dirname(os.path.dirname(HERE))
PLUGIN_DIR = os.path.join(BENCHDIR, "keygen", "pytest_plugin")
ROOT = os.path.join(HERE, "fixtures", "pkg")
PRICE = "py:shop.models.Leaf.compute_total_price"
RECEIPT = "py:shop.models.format_receipt_line"
LAZY = "py:shop.models.Lazy.lazy_total_amount"


def site(file, line, col, cls, why):
    return {"file": file, "line": line, "col": col, "class": cls, "why": why}


def by_name(records):
    return {r["name"]: r for r in records}


class IdentSitesTest(unittest.TestCase):
    def test_ident_sites_classifies_occurrences(self):
        self.assertEqual([
            {"file": "shop/models.py", "line": 22, "col": 9, "in": "code", "prev": "def"},
            {"file": "shop/service.py", "line": 7, "col": 7, "in": "comment", "prev": ""},
            {"file": "shop/service.py", "line": 8, "col": 18, "in": "code", "prev": "."},
            {"file": "shop/service.py", "line": 10, "col": 16, "in": "code", "prev": "."},
            {"file": "shop/service.py", "line": 15, "col": 17, "in": "code", "prev": "."},
            {"file": "tests/test_shop.py", "line": 7, "col": 19, "in": "code", "prev": "."},
            {"file": "tests/test_shop.py", "line": 26, "col": 23, "in": "code", "prev": "."},
        ], pykeys.ident_sites(ROOT, "compute_total_price"))
        receipt = pykeys.ident_sites(ROOT, "format_receipt_line")
        self.assertEqual({"file": "shop/service.py", "line": 3, "col": 25, "in": "code", "prev": "import"},
                         receipt[1])
        self.assertEqual({"file": "shop/service.py", "line": 30, "col": 28, "in": "string", "prev": ""},
                         pykeys.ident_sites(ROOT, "render_summary_text")[1])
        self.assertEqual([{"file": "shop/models.py", "line": 17, "col": 7, "in": "code", "prev": "class"},
                          {"file": "shop/models.py", "line": 21, "col": 12, "in": "code", "prev": ""},
                          {"file": "shop/models.py", "line": 74, "col": 21, "in": "code", "prev": ""}],
                         pykeys.ident_sites(ROOT, "Middle"))

    def test_import_after_colon_or_semicolon_is_an_import(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for rel, text in (("a.py", "def one_line_import_target():\n    return 1\n"),
                          ("b.py", "if True: from a import one_line_import_target\n"
                                   "x = 1; from a import one_line_import_target\n"
                                   "one_line_import_target()\n")):
            with open(os.path.join(d, rel), "w", encoding="utf-8") as f:
                f.write(text)
        self.assertEqual(["def", "import", "import", ""],
                         [s["prev"] for s in pykeys.ident_sites(d, "one_line_import_target")])

    def test_col_counts_utf16_code_units(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        text = ("def unicode_target_method():\n    return 1\n\n\n"
                "x = \"\U0001F600\"; y = unicode_target_method()  # unicode_target_method\n")
        with open(os.path.join(d, "m.py"), "w", encoding="utf-8") as f:
            f.write(text)
        # U+1F600 is one code point and two UTF-16 code units: the columns after it on line 5 are one more.
        self.assertEqual([{"file": "m.py", "line": 1, "col": 5, "in": "code", "prev": "def"},
                          {"file": "m.py", "line": 5, "col": 15, "in": "code", "prev": ""},
                          {"file": "m.py", "line": 5, "col": 42, "in": "comment", "prev": ""}],
                         pykeys.ident_sites(d, "unicode_target_method"))
        [rec] = pykeys.unique_name_keys(d, set())
        self.assertEqual({"file": "m.py", "line": 1, "col": 5}, rec["decl"])
        self.assertEqual([("m.py", 1, 5, "dnc"), ("m.py", 5, 15, "required"), ("m.py", 5, 42, "dnc")],
                         [(s["file"], s["line"], s["col"], s["class"]) for s in rec["sites"]])


class UniqueNameTest(unittest.TestCase):
    def test_unique_name_method_gets_exact_sites(self):
        recs = by_name(pykeys.unique_name_keys(ROOT, set()))
        self.assertEqual({
            "id": PRICE, "lang": "python", "kind": "method", "name": "compute_total_price", "container": "Leaf",
            "decl": {"file": "shop/models.py", "line": 22, "col": 9}, "family": [PRICE],
            "sites": [site("shop/models.py", 22, 9, "dnc", "decl"),
                      site("shop/service.py", 7, 7, "dnc", "comment"),
                      site("shop/service.py", 8, 18, "required", "use"),
                      site("shop/service.py", 10, 16, "required", "use"),
                      site("shop/service.py", 15, 17, "required", "use"),
                      site("tests/test_shop.py", 7, 19, "required", "use"),
                      site("tests/test_shop.py", 26, 23, "required", "use")],
            "implementers": [], "external": [], "source": "scan"}, recs["compute_total_price"])
        self.assertEqual({
            "id": RECEIPT, "lang": "python", "kind": "function", "name": "format_receipt_line", "container": "",
            "decl": {"file": "shop/models.py", "line": 57, "col": 5}, "family": [RECEIPT],
            "sites": [site("shop/models.py", 57, 5, "dnc", "decl"),
                      site("shop/service.py", 3, 25, "dnc", "import"),
                      site("shop/service.py", 19, 13, "required", "use"),
                      site("shop/service.py", 26, 28, "required", "use"),
                      site("tests/test_shop.py", 2, 31, "dnc", "import"),
                      site("tests/test_shop.py", 15, 12, "required", "use")],
            "implementers": [], "external": [], "source": "scan"}, recs["format_receipt_line"])
        # A property access is a use.
        self.assertEqual([site("shop/models.py", 29, 9, "dnc", "decl"), site("shop/service.py", 50, 17, "required", "use")],
                         recs["total_weight"]["sites"])

    def test_name_that_is_a_library_attribute_is_rejected(self):
        with mock.patch.dict(os.environ, {"PYTHONPATH": ROOT}):
            attrs = pykeys.library_attrs(sys.executable, ["shop"])
        # Attributes of builtin types and of the loaded library modules are in the set, the names of the tree are not.
        self.assertTrue({"removeprefix", "items", "update", "wraps"} <= attrs)
        self.assertFalse({"compute_total_price", "format_receipt_line", "render_summary_text"} & attrs)
        self.assertIn("removeprefix", by_name(pykeys.unique_name_keys(ROOT, set())))
        names = by_name(pykeys.unique_name_keys(ROOT, attrs))
        self.assertNotIn("removeprefix", names)
        self.assertIn("compute_total_price", names)

    def test_name_in_string_or_kwarg_is_rejected(self):
        names = by_name(pykeys.unique_name_keys(ROOT, set()))
        # In a string literal; a keyword argument name; a parameter name; an assigned attribute.
        for name in ("render_summary_text", "apply_discount_rate", "shipping_estimate", "cache_lookup_key"):
            self.assertNotIn(name, names)
            self.assertEqual(1, sum(1 for s in pykeys.ident_sites(ROOT, name) if s["prev"] == "def"))

    def test_short_name_is_rejected(self):
        names = by_name(pykeys.unique_name_keys(ROOT, set()))
        self.assertNotIn("describe", names)
        self.assertNotIn("total_price", names)  # 11 characters
        self.assertIn("total_weight", names)  # 12 characters

    def test_dunder_and_nested_names_are_rejected(self):
        names = by_name(pykeys.unique_name_keys(ROOT, set()))
        self.assertNotIn("__fixture_hook__", names)
        self.assertNotIn("nested_helper_function", names)

    def test_name_with_two_defs_is_rejected(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for rel, text in (("a.py", "def shared_long_name():\n    return 1\n"),
                          ("b.py", "class K:\n    def shared_long_name(self):\n        return 2\n"),
                          ("c.py", "import a\nprint(a.shared_long_name())\n")):
            with open(os.path.join(d, rel), "w", encoding="utf-8") as f:
                f.write(text)
        self.assertEqual([], pykeys.unique_name_keys(d, set()))


def impl(rid, file, line, col, cls):
    return {"id": rid, "file": file, "line": line, "col": col, "class": cls}


EXTRA_LEAF = impl("py:shop.broken_extra.ExtraLeaf", "shop/broken_extra.py", 6, 7, "dnc")
LOCAL_LEAF = impl("py:shop.models.make_local_leaf.LocalLeaf", "shop/models.py", 74, 11, "dnc")
LOCAL_TWIG = impl("py:shop.models.make_local_leaf.LocalTwig", "shop/models.py", 77, 11, "dnc")


class HierarchyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recs = pykeys.hierarchy_keys(sys.executable, ROOT, ["shop"])
        cls.classes = {r["id"]: r for r in cls.recs[1:]}

    def test_hierarchy_lists_transitive_subclasses(self):
        self.assertEqual("_meta", self.recs[0]["id"])
        meta = self.recs[0]
        self.assertEqual([{"module": "shop.broken_extra", "error": "ModuleNotFoundError"},
                          {"module": "shop.stops_at_import", "error": "StopImport"}], meta["skipped"])
        self.assertEqual(["shop.models.Dynamic"], [d["name"] for d in meta["dynamic"]])
        self.assertEqual({"py:shop.models." + name for name in (
                              "Base", "Middle", "Leaf", "Other", "Lazy", "BaseRecord", "ChildRecord", "GrandRecord",
                              "ExtraRecord", "MergedRecord", "Pair", "LabeledPair", "Box", "IntBox")}
                         | {"py:shop.service.Cache"}, set(self.classes))
        base = dict(self.classes["py:shop.models.Base"])
        required = [i for i in base.pop("implementers") if i["class"] == "required"]
        self.assertEqual({
            "id": "py:shop.models.Base", "lang": "python", "kind": "class", "name": "Base", "container": "",
            "decl": {"file": "shop/models.py", "line": 12, "col": 7}, "family": ["py:shop.models.Base"],
            "sites": [], "external": [], "source": "reflection"}, base)
        self.assertEqual([impl("py:shop.models.Middle", "shop/models.py", 17, 7, "required"),
                          impl("py:shop.models.Leaf", "shop/models.py", 21, 7, "required"),
                          impl("py:shop.models.Other", "shop/models.py", 39, 7, "required")], required)
        self.assertEqual([impl("py:shop.models.Leaf", "shop/models.py", 21, 7, "required")],
                         [i for i in self.classes["py:shop.models.Middle"]["implementers"] if i["class"] == "required"])
        self.assertEqual([], self.classes["py:shop.models.Leaf"]["implementers"])

    def test_hierarchy_marks_local_class_as_dnc_implementer(self):
        # LocalLeaf(Middle) is a class in a function: no import makes it. It is a dnc implementer of Middle (its
        # base name) and of Base (Middle is an implementer of Base).
        self.assertIn(LOCAL_LEAF, self.classes["py:shop.models.Middle"]["implementers"])
        self.assertIn(LOCAL_LEAF, self.classes["py:shop.models.Base"]["implementers"])
        self.assertEqual([], self.classes["py:shop.models.Other"]["implementers"])

    def test_hierarchy_marks_class_of_skipped_module_as_dnc(self):
        self.assertIn({"module": "shop.broken_extra", "error": "ModuleNotFoundError"}, self.recs[0]["skipped"])
        self.assertEqual(EXTRA_LEAF, self.classes["py:shop.models.Base"]["implementers"][0])
        self.assertNotIn(EXTRA_LEAF, self.classes["py:shop.models.Middle"]["implementers"])

    def test_hierarchy_dnc_chain_through_unseen_classes(self):
        # LocalTwig(LocalLeaf): LocalLeaf has no record, but it is a dnc implementer of Middle and of Base.
        self.assertEqual([impl("py:shop.models.Leaf", "shop/models.py", 21, 7, "required"), LOCAL_LEAF, LOCAL_TWIG],
                         self.classes["py:shop.models.Middle"]["implementers"])
        self.assertEqual([EXTRA_LEAF, impl("py:shop.models.Middle", "shop/models.py", 17, 7, "required"),
                          impl("py:shop.models.Leaf", "shop/models.py", 21, 7, "required"),
                          impl("py:shop.models.Other", "shop/models.py", 39, 7, "required"), LOCAL_LEAF, LOCAL_TWIG],
                         self.classes["py:shop.models.Base"]["implementers"])
        # StopImport (its module stops at import), ExtraLeaf, LocalLeaf, LocalTwig.
        self.assertEqual(4, self.recs[0]["unseen"])

    def required(self, name):
        return [i["id"].rsplit(".", 1)[-1] for i in self.classes["py:shop.models." + name]["implementers"]
                if i["class"] == "required"]

    def test_hierarchy_lists_typeddict_subclasses(self):
        if sys.version_info < (3, 12):
            self.skipTest("a TypedDict class has no __orig_bases__ before Python 3.12")
        # The bases of a TypedDict class are (dict,): its declared bases (__orig_bases__) make the relation.
        self.assertEqual(["ChildRecord", "GrandRecord", "MergedRecord"], self.required("BaseRecord"))
        self.assertEqual(["GrandRecord"], self.required("ChildRecord"))
        self.assertEqual(["MergedRecord"], self.required("ExtraRecord"))
        self.assertEqual([impl("py:shop.models.MergedRecord", "shop/models.py", 102, 7, "required")],
                         self.classes["py:shop.models.ExtraRecord"]["implementers"])
        self.assertEqual([], self.required("GrandRecord"))

    def test_hierarchy_lists_namedtuple_and_generic_subclasses(self):
        # The same lists as __subclasses__() alone gives.
        self.assertEqual(["LabeledPair"], self.required("Pair"))
        self.assertEqual(["IntBox"], self.required("Box"))
        self.assertEqual([], self.required("IntBox"))


class TracePluginTest(unittest.TestCase):
    def test_trace_plugin_logs_callers(self):
        if importlib.util.find_spec("pytest") is None:
            self.skipTest("pytest is absent for " + sys.executable)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        targets, out = os.path.join(d, "targets.json"), os.path.join(d, "trace.jsonl")
        with open(targets, "w", encoding="utf-8") as f:
            json.dump([{"id": PRICE, "file": "shop/models.py", "line": 22},
                       {"id": RECEIPT, "file": "shop/models.py", "line": 57},
                       {"id": LAZY, "file": "shop/models.py", "line": 69}], f)
        env = dict(os.environ, PYTHONPATH=PLUGIN_DIR, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               "-p", "trace_plugin", "--trace-targets=" + targets, "--trace-out=" + out,
                               "tests"],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        with open(out, encoding="utf-8") as f:
            logged = [json.loads(line) for line in f]
        # The caller of format_receipt_line is the call site, not the wrapper of its decorator; the caller of the
        # cached property is the attribute access, not functools. Line 26 runs while os.path is ntpath.
        self.assertEqual([{"id": LAZY, "caller_file": "tests/test_shop.py", "caller_line": 33},
                          {"id": PRICE, "caller_file": "shop/service.py", "caller_line": 8},
                          {"id": PRICE, "caller_file": "shop/service.py", "caller_line": 10},
                          {"id": PRICE, "caller_file": "tests/test_shop.py", "caller_line": 7},
                          {"id": PRICE, "caller_file": "tests/test_shop.py", "caller_line": 26},
                          {"id": RECEIPT, "caller_file": "shop/service.py", "caller_line": 19},
                          {"id": RECEIPT, "caller_file": "tests/test_shop.py", "caller_line": 15}], logged)

    def test_trace_plugin_refuses_a_target_with_no_function(self):
        if importlib.util.find_spec("pytest") is None:
            self.skipTest("pytest is absent for " + sys.executable)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        targets, out = os.path.join(d, "targets.json"), os.path.join(d, "trace.jsonl")
        with open(targets, "w", encoding="utf-8") as f:
            json.dump([{"id": PRICE, "file": "shop/models.py", "line": 23},
                       {"id": RECEIPT, "file": "shop/absent.py", "line": 1}], f)
        env = dict(os.environ, PYTHONPATH=PLUGIN_DIR, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               "-p", "trace_plugin", "--trace-targets=" + targets, "--trace-out=" + out,
                               "tests"],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(4, proc.returncode, proc.stdout + proc.stderr)  # usage error
        self.assertIn("shop/models.py:23", proc.stdout + proc.stderr)
        self.assertIn("no file shop/absent.py", proc.stdout + proc.stderr)
        self.assertFalse(os.path.exists(out))


class CliTest(unittest.TestCase):
    def test_cli_writes_jsonl(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        out = os.path.join(d, "unique.jsonl")
        env = dict(os.environ, PYTHONPATH=ROOT)
        proc = subprocess.run([sys.executable, "-B", "-m", "keygen.pykeys", "unique", "-root", ROOT,
                               "-python", sys.executable, "-modules", "shop", "-out", out],
                              cwd=BENCHDIR, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        with open(out, encoding="utf-8") as f:
            ids = [json.loads(line)["id"] for line in f]
        self.assertIn(PRICE, ids)
        self.assertNotIn("py:shop.models.Leaf.removeprefix", ids)
        self.assertEqual(sorted(ids), ids)

    def test_min_required_filters_records(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        env = dict(os.environ, PYTHONPATH=ROOT)
        names = {}
        for n in ("0", "1", "2"):
            out = os.path.join(d, n + ".jsonl")
            proc = subprocess.run([sys.executable, "-B", "-m", "keygen.pykeys", "unique", "-root", ROOT,
                                   "-python", sys.executable, "-modules", "shop", "-out", out, "-min-required", n],
                                  cwd=BENCHDIR, env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(0, proc.returncode, proc.stderr)
            with open(out, encoding="utf-8") as f:
                names[n] = {json.loads(line)["name"] for line in f}
        # Required lines: compute_total_price 5, format_receipt_line 3, total_weight 1, test_price_direct 0.
        self.assertTrue({"compute_total_price", "format_receipt_line", "total_weight", "test_price_direct"} <= names["0"])
        self.assertTrue({"compute_total_price", "format_receipt_line", "total_weight"} <= names["1"])
        self.assertNotIn("test_price_direct", names["1"])
        self.assertTrue({"compute_total_price", "format_receipt_line"} <= names["2"])
        self.assertNotIn("total_weight", names["2"])
        self.assertTrue(names["2"] < names["1"] < names["0"])


if __name__ == "__main__":
    unittest.main()
