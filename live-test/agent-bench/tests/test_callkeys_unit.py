import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from benchlib import callkeys, keys, pykeys

HERE = os.path.dirname(os.path.abspath(__file__))
BENCHDIR = os.path.dirname(HERE)

# A small tree. Each use of compute_total_price shows one rule of `in` and `lit`.
CORE = [
    "import functools",  # 1
    "",
    "",
    "def compute_total_price(amount):",  # 4
    "    return amount + 1",
    "",
    "",
    "def direct_caller_func(value):",  # 8
    "    return compute_total_price(value)",  # 9: a call in a body
    "",
    "",
    "def value_user_func():",  # 12
    "    return compute_total_price",  # 13: a value
    "",
    "",
    "module_level_total = compute_total_price(1)",  # 16: module level
    "",
    "",
    "class PriceBasket:",  # 19
    "    basket_default = compute_total_price(2)",  # 20: class body
    "",
    "    @property",
    "    def total_weight_amount(self):",  # 23
    "        return 3",
    "",
    "    @functools.lru_cache(maxsize=compute_total_price(0))",  # 26: decorator of a method
    "    def method_with_reader(self):",  # 27
    "        return self.total_weight_amount",  # 28: property read
    "",
    "",
    "def defaults_holder(first=compute_total_price(3)):",  # 31: default of a module-level def
    "    def inner_with_default(second=compute_total_price(4)):",  # 32: default of a nested def
    "        return second",
    "    return inner_with_default",
    "",
    "",
    "def outer_with_closures():",  # 37
    "    pick = lambda: compute_total_price(5)",  # 38: lambda
    "    def nested_level_one():",  # 39
    "        def nested_level_two():",  # 40
    "            return compute_total_price(6)",  # 41: nested def of a nested def
    "        return nested_level_two",
    "    return pick, nested_level_one",
    "",
    "",
    "def decorated_inside_outer():",  # 46
    "    @compute_total_price",  # 47: decorator of a nested def
    "    def wrapped_local_func():",  # 48
    "        return 7",
    "    return wrapped_local_func",
    "",
    "",
    'x = "\U0001F600"; y = compute_total_price(8)',  # 53: a character above U+FFFF before the name
    "",
    "",
    "def generator_function_one():",  # 56
    "    yield compute_total_price(9)",  # 57
    "",
    "",
    "async def async_function_one():",  # 60
    "    return 10",
]
DECOR = [
    "import pytest",
    "",
    "handlers = []",
    "",
    "",
    '@pytest.mark.parametrize("a", [1])',
    "@handlers[0]",
    "@staticmethod",
    "def decorated_many_ways(a):",  # 9
    "    return a",
]
WORDS = [
    "def short_helper():  # short_helper in a comment",
    '    return "short_helper and short_helper"',
    "",
    "",
    "short_helper()",
]
PLANTED = [
    "class FirstKind:",
    "    def refresh_totals(self):",  # 2
    "        return 1",
    "",
    "",
    "class SecondKind:",
    "    def refresh_totals(self):",  # 7
    "        return 2",
    "",
    "",
    "def drive_both_kinds(a, b):",  # 11
    "    return a.refresh_totals() + b.refresh_totals()",  # 12
]
PRICE = "py:shop.core.compute_total_price"
WEIGHT = "py:shop.core.PriceBasket.total_weight_amount"


def write_tree(root, files):
    for rel, lines in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def col(lines, line, word, nth=0):
    """The 1-based column of the nth `word` on an ASCII line."""
    text = lines[line - 1]
    i = -1
    for _ in range(nth + 1):
        i = text.index(word, i + 1)
    return i + 1


def at(file, line, column):
    return {"file": file, "line": line, "col": column}


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = callkeys.main(argv)
    return code, out.getvalue(), err.getvalue()


class PyCallsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        write_tree(cls.root, {"shop/core.py": CORE, "shop/decor.py": DECOR, "shop/words.py": WORDS})
        cls.unique = pykeys.unique_name_keys(cls.root, set())
        cls.records = callkeys.pycalls(cls.root, cls.unique)
        cls.by_name = {r["name"]: r for r in cls.records}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)

    def use(self, line, word, call, read, in_line, lit, column=None):
        c = column if column is not None else col(CORE, line, word)
        return {"file": "shop/core.py", "line": line, "col": c, "call": call, "read": read,
                "in": None if in_line is None else at("shop/core.py", *in_line), "lit": lit}

    def test_uses_of_a_function_follow_the_in_and_lit_rules(self):
        name = "compute_total_price"
        decl = at("shop/core.py", 4, 5)
        self.assertEqual({
            "id": PRICE, "lang": "python", "kind": "function", "name": name, "container": "", "decl": decl,
            "end": 5, "top": decl, "decorators": [], "generator": False, "async": False, "mentions": 12,
            "uses": [
                self.use(9, name, True, False, (8, 5), False),  # a call in a body
                self.use(13, name, False, True, (12, 5), False),  # a value
                self.use(16, name, True, False, None, False),  # module level
                self.use(20, name, True, False, None, False),  # class body
                self.use(26, name, True, False, None, False),  # decorator of a method
                self.use(31, name, True, False, None, False),  # default value of a module-level def
                self.use(32, name, True, False, (31, 5), False),  # default value of a nested def: the outer body
                self.use(38, name, True, False, (37, 5), True),  # lambda
                self.use(41, name, True, False, (37, 5), True),  # nested def: the outermost def
                self.use(47, name, False, True, (46, 5), False),  # decorator of a nested def: the outer body
                self.use(53, name, True, False, None, False, column=15),  # U+1F600 is two UTF-16 code units
                self.use(57, name, True, False, (56, 5), False),
            ]}, self.by_name[name])

    def test_property_method_and_read(self):
        decl = at("shop/core.py", 23, 9)
        self.assertEqual({
            "id": WEIGHT, "lang": "python", "kind": "method", "name": "total_weight_amount",
            "container": "PriceBasket", "decl": decl, "end": 24, "top": decl, "decorators": ["property"],
            "generator": False, "async": False, "mentions": 1,
            "uses": [self.use(28, "total_weight_amount", False, True, (27, 9), False)]},
            self.by_name["total_weight_amount"])
        reader = self.by_name["method_with_reader"]
        self.assertEqual(("method", "PriceBasket", "py:shop.core.PriceBasket.method_with_reader", [], 0),
                         (reader["kind"], reader["container"], reader["id"], reader["uses"], reader["mentions"]))
        self.assertEqual(["functools.lru_cache"], reader["decorators"])

    def test_nested_defs_have_the_outermost_def_as_top_and_no_id(self):
        def fields(name):
            r = self.by_name[name]
            return r["id"], r["kind"], r["decl"], r["top"], r["end"], r["uses"]

        self.assertEqual(("", "function", at("shop/core.py", 32, 9), at("shop/core.py", 31, 5), 33, []),
                         fields("inner_with_default"))
        self.assertEqual(("", "function", at("shop/core.py", 39, 9), at("shop/core.py", 37, 5), 42, []),
                         fields("nested_level_one"))
        self.assertEqual(("", "function", at("shop/core.py", 40, 13), at("shop/core.py", 37, 5), 41, []),
                         fields("nested_level_two"))
        self.assertEqual(["compute_total_price"], self.by_name["wrapped_local_func"]["decorators"])
        self.assertEqual(at("shop/core.py", 46, 5), self.by_name["wrapped_local_func"]["top"])

    def test_generator_async_and_decorator_texts(self):
        gen, coro = self.by_name["generator_function_one"], self.by_name["async_function_one"]
        self.assertEqual((True, False), (gen["generator"], gen["async"]))
        self.assertEqual((False, True, at("shop/core.py", 60, 11)), (coro["generator"], coro["async"], coro["decl"]))
        self.assertFalse(self.by_name["outer_with_closures"]["generator"])
        self.assertEqual(["pytest.mark.parametrize", "?", "staticmethod"],
                         self.by_name["decorated_many_ways"]["decorators"])

    def test_mentions_count_code_and_strings_but_not_comments_or_def_tokens(self):
        helper = self.by_name["short_helper"]
        # One call and two words in a string; the comment and the def name token do not count.
        self.assertEqual(("", 3, []), (helper["id"], helper["mentions"], helper["uses"]))
        self.assertEqual(1, self.by_name["inner_with_default"]["mentions"])
        self.assertEqual(0, self.by_name["direct_caller_func"]["mentions"])

    def test_mentions_come_from_one_pass_over_the_files(self):
        with mock.patch.object(pykeys, "_occurrences", wraps=pykeys._occurrences) as occurrences:
            callkeys.pycalls(self.root, self.unique)
        self.assertEqual(3, occurrences.call_count)

    def test_records_are_sorted_by_decl(self):
        self.assertEqual(
            ["compute_total_price", "direct_caller_func", "value_user_func", "total_weight_amount",
             "method_with_reader", "defaults_holder", "inner_with_default", "outer_with_closures",
             "nested_level_one", "nested_level_two", "decorated_inside_outer", "wrapped_local_func",
             "generator_function_one", "async_function_one", "decorated_many_ways", "short_helper"],
            [r["name"] for r in self.records])


class PyCallsSourcesTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)

    def test_plant_record_gives_the_id_and_only_its_required_sites(self):
        write_tree(self.root, {"p.py": PLANTED})
        first, second = col(PLANTED, 12, "refresh_totals"), col(PLANTED, 12, "refresh_totals", 1)
        rid = "plant:python:t:FirstKind.refresh_totals"
        plant = {"id": rid, "lang": "python", "kind": "method", "name": "refresh_totals", "container": "FirstKind",
                 "decl": at("p.py", 2, 9), "family": [rid],
                 "sites": [{**at("p.py", 2, 9), "class": "dnc", "why": "decl"},
                           {**at("p.py", 12, first), "class": "required", "why": "use"},
                           {**at("p.py", 12, second), "class": "forbidden", "why": "decoy"}],
                 "implementers": [], "external": [], "source": "plant", "original": "refresh_first"}
        records = callkeys.pycalls(self.root, pykeys.unique_name_keys(self.root, set()) + [plant])
        by_decl = {(r["decl"]["line"], r["decl"]["col"]): r for r in records}
        self.assertEqual(rid, by_decl[(2, 9)]["id"])
        self.assertEqual([{**at("p.py", 12, first), "call": True, "read": False, "in": at("p.py", 11, 5),
                           "lit": False}], by_decl[(2, 9)]["uses"])
        self.assertEqual(("", [], 2), (by_decl[(7, 9)]["id"], by_decl[(7, 9)]["uses"], by_decl[(7, 9)]["mentions"]))
        self.assertEqual("py:p.drive_both_kinds", by_decl[(11, 5)]["id"])

    def test_lambda_at_module_level_is_lit_with_in_null(self):
        write_tree(self.root, {"l.py": ["def lambda_target_name():", "    return 1", "",
                                        "holder = lambda: lambda_target_name()"]})
        [rec] = callkeys.pycalls(self.root, pykeys.unique_name_keys(self.root, set()))
        self.assertEqual([{**at("l.py", 4, 18), "call": True, "read": False, "in": None, "lit": True}], rec["uses"])

    def test_site_with_no_node_is_unknown(self):
        write_tree(self.root, {"u.py": ["def lonely_function_name():", "    return 1", "# lonely_function_name"]})
        rid = "py:u.lonely_function_name"
        record = {"id": rid, "lang": "python", "kind": "function", "name": "lonely_function_name", "container": "",
                  "decl": at("u.py", 1, 5), "family": [rid],
                  "sites": [{**at("u.py", 1, 5), "class": "dnc", "why": "decl"},
                            {**at("u.py", 3, 3), "class": "required", "why": "use"}],
                  "implementers": [], "external": [], "source": "scan"}
        [rec] = callkeys.pycalls(self.root, [record])
        self.assertEqual([{**at("u.py", 3, 3), "call": False, "read": False, "in": None, "lit": False,
                           "unknown": True}], rec["uses"])

    def test_file_that_does_not_parse_stops_the_command(self):
        write_tree(self.root, {"ok.py": ["def fine_function_name():", "    return 1"],
                               "pkg/bad.py": ["def broken(:", "    return 1"]})
        with self.assertRaises(callkeys.CallKeysError) as cm:
            callkeys.pycalls(self.root, [])
        self.assertIn("pkg/bad.py", str(cm.exception))

    def test_key_record_with_no_def_at_its_decl_stops_the_command(self):
        write_tree(self.root, {"m.py": ["def fine_function_name():", "    return 1"]})
        record = {"id": "py:m.fine_function_name", "decl": at("m.py", 1, 1), "sites": []}
        with self.assertRaises(callkeys.CallKeysError) as cm:
            callkeys.pycalls(self.root, [record])
        self.assertIn("py:m.fine_function_name", str(cm.exception))

    def test_cli_gives_equal_bytes_for_two_runs(self):
        tree = os.path.join(self.root, "tree")
        write_tree(tree, {"shop/core.py": CORE, "shop/words.py": WORDS})
        unique = os.path.join(self.root, "unique.jsonl")
        keys.save_keys(unique, pykeys.unique_name_keys(tree, set()))
        outs = []
        for n in ("1", "2"):
            out = os.path.join(self.root, f"calls{n}.jsonl")
            code, stdout, _ = run_main(["pycalls", "-root", tree, "-unique", unique, "-out", out])
            self.assertEqual(0, code)
            # 15 defs; 10 with an id (no nested def, no name in a string); 13 uses: 3 call false, 5 in null, 2 lit
            # true, 0 unknown.
            self.assertIn("pycalls: 15 records, 10 with an id, 13 uses: 3 call false, 5 in null, 2 lit true, "
                          "0 unknown", stdout)
            with open(out, "rb") as f:
                outs.append(f.read())
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(PRICE, json.loads(outs[0].decode("utf-8").splitlines()[0])["id"])

    def test_cli_reports_an_error_with_exit_code_2(self):
        write_tree(self.root, {"bad.py": ["def broken(:"]})
        unique = os.path.join(self.root, "unique.jsonl")
        write_jsonl(unique, [])
        code, _, stderr = run_main(["pycalls", "-root", self.root, "-unique", unique,
                                    "-out", os.path.join(self.root, "calls.jsonl")])
        self.assertEqual(2, code)
        self.assertIn("bad.py", stderr)


# Hand-written calls files for `make`. Each function starts at its own line and spans 6 lines.

def pos(line, file="m.py", column=5):
    return {"file": file, "line": line, "col": column}


def use(line, in_line=None, call=True, read=False, lit=False, file="m.py", in_file="m.py", **extra):
    return {"file": file, "line": line, "col": 9, "call": call, "read": read,
            "in": None if in_line is None else pos(in_line, in_file), "lit": lit, **extra}


def py(name, line, uses=(), rid=None, kind="function", container="", top=None, decorators=(), generator=False,
       is_async=False, mentions=0, file="m.py"):
    decl = pos(line, file)
    return {"id": "py:m." + name if rid is None else rid, "lang": "python", "kind": kind, "name": name,
            "container": container, "decl": decl, "end": line + 5, "top": top or decl,
            "decorators": list(decorators), "generator": generator, "async": is_async, "mentions": mentions,
            "uses": list(uses)}


def gouse(line, in_line=None, call=True, lit=False, file="m.go", in_file="m.go"):
    return {"file": file, "line": line, "col": 2, "call": call,
            "in": None if in_line is None else pos(in_line, in_file, 6), "lit": lit, "configs": ["linux"]}


def go(name, line, uses=(), rid=None, file="m.go", configs=("linux", "windows")):
    return {"id": "go:m." + name if rid is None else rid, "lang": "go", "kind": "func", "name": name,
            "container": "", "decl": pos(line, file, 6), "end": line + 5, "configs": list(configs),
            "uses": list(uses)}


def sym(rid, family=None, external=(), whys=("use",)):
    return {"id": rid, "lang": "go", "kind": "func", "name": rid.rsplit(".", 1)[-1], "container": "",
            "decl": pos(1, "m.go", 6), "family": family or [rid],
            "sites": [{"file": "m.go", "line": 90 + i, "col": 2, "class": "required", "why": why, "configs": []}
                      for i, why in enumerate(whys)],
            "implementers": [], "external": list(external), "source": "go/types"}


def caller_site(line, level, lit=False, plant=False, cls="required", why="caller", file="m.py", column=5, **extra):
    return {"file": file, "line": line, "col": column, "class": cls, "why": why, "level": level, "lit": lit,
            "plant": plant, **extra}


# A test file: a function in it whose name starts with `test` is a test function.
T = "test_m.py"

# Scenario of the Python key tests: X has the level-1 callers A, B and C. A also calls B (B is at both levels:
# level 1) and is called by D, which is open (a value use at module level); so A is no target. B is called by E, a
# test function with no use (id "", no mention); so B is a target too. C is a test function with no use. O calls
# nothing and has no use: it is open (`uncalled`).
PLANT_B = "plant:python:t:K.caller_b"
SCENARIO = [
    py("target_func", 10, [use(21, 20), use(31, 30, lit=True), use(32, 30), use(61, 60, lit=True, file=T, in_file=T)]),
    py("caller_a", 20, [use(33, 30), use(41, 40)]),
    py("caller_b", 30, [use(51, 50, lit=True, file=T, in_file=T)], rid=PLANT_B),
    py("open_d", 40, [use(3, None, call=False, read=True)]),
    py("test_leaf_e", 50, rid="", file=T),
    py("test_caller_c", 60, file=T),
    py("other_o", 70),
]


class CausesTest(unittest.TestCase):
    def test_each_python_cause_alone(self):
        # The test function `test_holder` calls each function that needs a use to be no `uncalled`.
        def called(line):
            return [use(line, 10, in_file=T)]

        calls = [
            py("test_holder", 10, file=T),
            py("no_key", 20, called(14), rid="", mentions=2),
            py("value", 30, [use(11, 10, call=False, read=True, in_file=T)]),
            py("outside", 40, [use(3, None)]),
            py("unknown", 50, [use(12, 10, unknown=True, in_file=T)]),
            py("nested", 60, called(15), top=pos(10, T)),
            py("decorator", 70, called(16), decorators=["app.route", "staticmethod"]),
            py("generator", 80, called(17), generator=True),
            py("coroutine", 90, called(18), is_async=True),
            py("__enter__", 100, called(19)),
            py("test_leaf", 110, rid="", file=T),
            py("allowed", 120, called(20), decorators=["functools.lru_cache", "pytest.mark.parametrize",
                                                       "staticmethod", "abc.abstractmethod", "mock.patch.object"]),
            py("prop", 130, [use(13, 10, call=False, read=True, in_file=T)], decorators=["property"]),
            py("uncalled", 140),
        ]
        causes = callkeys.open_causes(calls)
        self.assertEqual({
            (T, 10, 5): [], ("m.py", 20, 5): ["no-key"], ("m.py", 30, 5): ["value"],
            ("m.py", 40, 5): ["outside"], ("m.py", 50, 5): ["unknown"], ("m.py", 60, 5): ["nested"],
            ("m.py", 70, 5): ["decorator"], ("m.py", 80, 5): ["generator"], ("m.py", 90, 5): ["generator"],
            ("m.py", 100, 5): ["implicit"], (T, 110, 5): [], ("m.py", 120, 5): [],
            ("m.py", 130, 5): [], ("m.py", 140, 5): ["uncalled"]}, causes)
        self.assertEqual("uncalled", callkeys.CAUSES["python"][-1])
        self.assertNotIn("uncalled", callkeys.CAUSES["go"])

    def test_uncalled_needs_no_use_and_no_test_function(self):
        """A test function: the name starts with `test`, and the base name of the file matches `test_*.py` or
        `*_test.py`. The cause applies to a record with an id and to a record with the id "", and `no-key` does
        not change."""
        cases = [
            (py("plain_function", 10), ["uncalled"]),
            (py("plain_no_id", 20, rid=""), ["uncalled"]),
            (py("mentioned_no_id", 30, rid="", mentions=1), ["no-key", "uncalled"]),
            (py("test_named_only", 40), ["uncalled"]),  # m.py is no test file
            (py("helper", 10, file="test_m.py"), ["uncalled"]),  # the name does not start with `test`
            (py("test_in_prefix_file", 20, file="test_m.py"), []),
            (py("test_in_suffix_file", 30, rid="", file="pkg/m_test.py"), []),
            (py("testcase_runner", 40, kind="method", container="K", file="tests/test_m.py"), []),
            (py("test_in_test_folder", 50, file="test_dir/m.py"), ["uncalled"]),  # the base name counts
            (py("test_other_suffix", 60, file="test_m.pyi"), ["uncalled"]),
            (py("test_called", 70, [use(3, None)], file="test_m.py"), ["outside"]),
        ]
        causes = callkeys.open_causes([rec for rec, _ in cases])
        for rec, expected in cases:
            self.assertEqual(expected, causes[(rec["decl"]["file"], rec["decl"]["line"], 5)], rec["name"])

    def test_unknown_use_of_pycalls_is_also_a_value_outside_the_functions(self):
        unknown = {**use(5, None, call=False), "unknown": True}
        self.assertEqual(["value", "outside", "unknown"], callkeys.open_causes([py("f", 10, [unknown])])[("m.py", 10, 5)])

    def test_decorator_with_another_expression_is_open(self):
        self.assertEqual(["decorator"],
                         callkeys.open_causes([py("test_f", 10, decorators=["?"], file=T)])[(T, 10, 5)])

    def test_each_go_cause_alone(self):
        calls = [
            go("Holder", 10),
            go("init", 20, [gouse(11, 10)], rid=""),
            go("Value", 30, [gouse(12, 10, call=False)]),
            go("Outside", 40, [gouse(3, None)]),
            go("Family", 50),
            go("External", 60),
            go("Unproven", 70),
            go("StringSite", 80),
            go("Variant", 90),
            go("Variant", 5, file="m_windows.go", configs=("windows",)),
            go("NoSymbols", 100),
            go("main", 110, rid=""),
        ]
        symbols = [sym("go:m.Holder"), sym("go:m.init"), sym("go:m.Value"), sym("go:m.Outside"),
                   sym("go:m.Family", family=["go:m.Family", "go:m.Iface.Family"]),
                   sym("go:m.External", external=["fmt.Stringer"]),
                   sym("go:m.Unproven", whys=("use", "unproven")), sym("go:m.StringSite", whys=("string",)),
                   sym("go:m.Variant")]
        self.assertEqual({
            ("m.go", 10, 6): [], ("m.go", 20, 6): ["no-key"], ("m.go", 30, 6): ["value"],
            ("m.go", 40, 6): ["outside"], ("m.go", 50, 6): ["interface"], ("m.go", 60, 6): ["interface"],
            ("m.go", 70, 6): ["unproven"], ("m.go", 80, 6): ["unproven"], ("m.go", 90, 6): ["variants"],
            ("m_windows.go", 5, 6): ["variants"], ("m.go", 100, 6): ["no-symbols"], ("m.go", 110, 6): []},
            callkeys.open_causes(calls, symbols))


class MakeTest(unittest.TestCase):
    def test_target_with_two_levels(self):
        records, stats = callkeys.make_keys(SCENARIO)
        self.assertEqual(["py:m.target_func", PLANT_B], [r["id"] for r in records])
        self.assertEqual({
            "id": "py:m.target_func", "lang": "python", "kind": "function", "name": "target_func", "container": "",
            "decl": pos(10), "family": ["py:m.target_func"], "implementers": [], "external": [], "source": "calls",
            "depth": 2, "property": False, "plant": False, "levels": {"1": 3, "2": 2},
            "sites": [
                {**pos(10), "class": "dnc", "why": "decl"},
                caller_site(20, 1),
                caller_site(30, 1, plant=True),  # also a caller of A: the lowest level; one use is no lit
                caller_site(40, 2),  # open, but a level-2 caller need not be closed
                caller_site(50, 2, lit=True, file=T),
                caller_site(60, 1, lit=True, file=T),
            ]}, records[0])
        # B: its only caller is the test function E, which has no caller.
        self.assertEqual({"1": 1, "2": 0}, records[1]["levels"])
        self.assertTrue(records[1]["plant"])
        self.assertEqual([{**pos(30), "class": "dnc", "why": "decl"}, caller_site(50, 1, lit=True, file=T)],
                         records[1]["sites"])
        self.assertEqual({"functions": 7, "closed": 5, "targets": 2}, {k: stats[k] for k in ("functions", "closed", "targets")})
        self.assertEqual({"value": 1, "outside": 1, "uncalled": 1}, {k: v for k, v in stats["causes"].items() if v})
        self.assertEqual(({3: 1, 1: 1}, {2: 1, 0: 1}), (dict(stats["level1"]), dict(stats["level2"])))

    def test_recursion_is_not_asked(self):
        calls = [py("recursive_one", 10, [use(11, 10), use(21, 20, file=T, in_file=T)]),
                 py("test_caller_f", 20, file=T)]
        [rec] = callkeys.make_keys(calls)[0]
        self.assertEqual({"1": 1, "2": 0}, rec["levels"])
        self.assertEqual([{**pos(10), "class": "dnc", "why": "decl"}, caller_site(20, 1, file=T)], rec["sites"])

    def test_open_level_one_caller_makes_no_target(self):
        calls = [py("target", 10, [use(21, 20)]), py("open_caller", 20, [use(3, None)])]
        self.assertEqual([], callkeys.make_keys(calls)[0])

    def test_uncalled_level_one_caller_makes_no_target(self):
        """A non-test function with no use can have a caller through `getattr`: it is open, so a function that it
        calls is no target. The same caller as a test function makes a target."""
        calls = [py("target", 10, [use(21, 20)]), py("plain_caller", 20)]
        self.assertEqual([], callkeys.make_keys(calls)[0])
        calls = [py("target", 10, [use(21, 20, file=T, in_file=T)]), py("test_caller", 20, file=T)]
        self.assertEqual(["py:m.target"], [r["id"] for r in callkeys.make_keys(calls)[0]])

    def test_property_target(self):
        calls = [py("prop_target", 10, [use(21, 20, call=False, read=True, file=T, in_file=T)], kind="method",
                    container="K", decorators=["property"]),
                 py("test_reader", 20, file=T)]
        [rec] = callkeys.make_keys(calls)[0]
        self.assertEqual((True, "method", "K", {"1": 1, "2": 0}),
                         (rec["property"], rec["kind"], rec["container"], rec["levels"]))

    def test_go_leaf_caller_and_variants_of_a_level_two_caller(self):
        calls = [
            go("Target", 10, [gouse(21, 20), gouse(31, 30)]),
            go("CallerOne", 20, [gouse(41, 40)], configs=("linux",)),
            go("init", 30, rid=""),
            go("Variant", 40, configs=("linux",)),
            go("Variant", 5, file="m_windows.go", configs=("windows",)),
        ]
        symbols = [sym("go:m.Target"), sym("go:m.CallerOne"), sym("go:m.Variant")]
        [rec] = callkeys.make_keys(calls, symbols)[0]
        self.assertEqual(("go:m.Target", "go", "func", False, {"1": 2, "2": 1}),
                         (rec["id"], rec["lang"], rec["kind"], rec["property"], rec["levels"]))
        self.assertEqual([
            {**pos(10, "m.go", 6), "class": "dnc", "why": "decl"},
            caller_site(20, 1, file="m.go", column=6, configs=["linux"]),
            caller_site(30, 1, file="m.go", column=6, configs=["linux", "windows"]),  # init: a leaf
            caller_site(40, 2, cls="dnc", why="variant", file="m.go", column=6, configs=["linux"]),
            caller_site(5, 2, cls="dnc", why="variant", file="m_windows.go", column=6, configs=["windows"]),
        ], rec["sites"])

    def test_symbols_are_required_for_go_and_refused_for_python(self):
        with self.assertRaises(callkeys.CallKeysError):
            callkeys.make_keys([go("Target", 10)])
        with self.assertRaises(callkeys.CallKeysError):
            callkeys.make_keys(SCENARIO, [])

    def test_in_with_no_record_stops_the_command(self):
        with self.assertRaises(callkeys.CallKeysError) as cm:
            callkeys.make_keys([py("target", 10, [use(21, 20)])])
        self.assertIn("m.py:20:5", str(cm.exception))

    def test_cli_writes_keys_that_load_and_score(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        calls, out = os.path.join(d, "calls.jsonl"), os.path.join(d, "keys.jsonl")
        write_jsonl(calls, SCENARIO)
        code, stdout, _ = run_main(["make", "-calls", calls, "-out", out])
        self.assertEqual(0, code)
        self.assertIn("make: 7 functions, 5 closed, 2 targets", stdout)
        self.assertIn("open causes: no-key 0, value 1, outside 1, unknown 0, nested 0, decorator 0, generator 0, "
                      "implicit 0, uncalled 1", stdout)
        rec = keys.load_keys(out)[0]
        self.assertEqual("py:m.target_func", rec["id"])
        exact = {("m.py", n) for n in (20, 30, 40)} | {(T, 50), (T, 60)}
        self.assertTrue(keys.score(exact, rec)["exact"])
        self.assertEqual((5, 0, 0, 1, True), tuple(keys.score(exact | {("m.py", 10)}, rec)[k]
                                                   for k in ("tp", "fp", "miss", "ignored", "exact")))
        absent = keys.score(exact - {("m.py", 40)}, rec)
        self.assertEqual((4, 0, 1, False), (absent["tp"], absent["fp"], absent["miss"], absent["exact"]))
        other = keys.score(exact | {("m.py", 70)}, rec)
        self.assertEqual((5, 1, 0, False), (other["tp"], other["fp"], other["miss"], other["exact"]))

    def test_cli_refuses_symbols_for_python_and_needs_them_for_go(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        pyfile, gofile, symfile = (os.path.join(d, n) for n in ("py.jsonl", "go.jsonl", "sym.jsonl"))
        write_jsonl(pyfile, SCENARIO)
        write_jsonl(gofile, [go("Target", 10)])
        write_jsonl(symfile, [sym("go:m.Target")])
        out = os.path.join(d, "keys.jsonl")
        self.assertEqual(2, run_main(["make", "-calls", pyfile, "-symbols", symfile, "-out", out])[0])
        self.assertEqual(2, run_main(["make", "-calls", gofile, "-out", out])[0])
        self.assertEqual(0, run_main(["make", "-calls", gofile, "-symbols", symfile, "-out", out])[0])
        self.assertEqual([], keys.load_keys(out))


class TraceTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        self.calls = os.path.join(self.d, "calls.jsonl")
        self.keys = os.path.join(self.d, "keys.jsonl")
        write_jsonl(self.calls, SCENARIO)
        self.assertEqual(0, run_main(["make", "-calls", self.calls, "-out", self.keys])[0])

    def check(self, trace_lines):
        trace = os.path.join(self.d, "trace.jsonl")
        write_jsonl(trace, [{"id": i, "caller_file": f, "caller_line": n} for i, f, n in trace_lines])
        return run_main(["tracecheck", "-keys", self.keys, "-calls", self.calls, "-trace", trace,
                         "-ids", "py:m.target_func"])

    def test_targets_lists_the_target_and_each_level_one_caller(self):
        ids = os.path.join(self.d, "ids.txt")
        with open(ids, "w", encoding="utf-8") as f:
            f.write("py:m.target_func\n" + PLANT_B + "\n")
        out = os.path.join(self.d, "targets.json")
        self.assertEqual(0, run_main(["targets", "-keys", self.keys, "-ids", "@" + ids, "-out", out])[0])
        with open(out, encoding="utf-8") as f:
            targets = json.load(f)
        # B is a level-1 caller of X and a target: one time. E is the level-1 caller of B.
        self.assertEqual([{"id": f"m.py:{n}", "file": "m.py", "line": n} for n in (10, 20, 30)]
                         + [{"id": f"{T}:{n}", "file": T, "line": n} for n in (50, 60)], targets)

    def test_targets_refuses_an_unknown_id(self):
        out = os.path.join(self.d, "targets.json")
        code, _, stderr = run_main(["targets", "-keys", self.keys, "-ids", "py:m.absent", "-out", out])
        self.assertEqual(2, code)
        self.assertIn("py:m.absent", stderr)

    def test_key_and_external_sites_pass(self):
        code, stdout, _ = self.check([
            ("m.py:10", "m.py", 21),  # in A: a caller of X
            ("m.py:10", "m.py", 32),  # in B
            ("m.py:20", "m.py", 41),  # in D: a caller of A
            (f"{T}:60", "/usr/lib/python3/unittest/case.py", 5),  # C has no caller: external is allowed
            (f"{T}:60", ".venv/lib/python3.12/site-packages/_pytest/python.py", 7),
        ])
        self.assertEqual(0, code, stdout)
        self.assertEqual([
            "m.py:10:5 level 0: key 2, external 0, outside 0, callers reached 2 of 3",
            "m.py:20:5 level 1: key 1, external 0, outside 0, callers reached 1 of 2",
            "m.py:30:5 level 1: key 0, external 0, outside 0, callers reached 0 of 1",
            "test_m.py:60:5 level 1: key 0, external 2, outside 0, callers reached 0 of 0",
            "tracecheck: 4 functions, 5 sites: key 3, external 2, outside 0; trace lines of other ids: 0",
        ], stdout.splitlines())

    def test_outside_sites_fail(self):
        code, stdout, _ = self.check([
            ("m.py:10", "m.py", 21),
            ("m.py:10", "m.py", 41),  # in D: no caller of X
            ("m.py:10", "m.py", 3),  # in no function
            ("m.py:99", "m.py", 21),  # another id
        ])
        self.assertEqual(1, code, stdout)
        self.assertIn("m.py:10:5 level 0: key 1, external 0, outside 2, callers reached 1 of 3", stdout)
        self.assertIn("outside m.py:3 (calls m.py:10:5)", stdout)
        self.assertIn("outside m.py:41 (calls m.py:10:5)", stdout)
        self.assertIn("trace lines of other ids: 1", stdout)

    def test_external_site_of_a_function_with_callers_fails(self):
        code, stdout, _ = self.check([("m.py:30", ".venv/lib/python3.12/site-packages/x.py", 7)])
        self.assertEqual(1, code, stdout)
        self.assertIn("m.py:30:5 level 1: key 0, external 1, outside 0, callers reached 0 of 1", stdout)


class ModuleTest(unittest.TestCase):
    def test_module_runs_as_a_command(self):
        proc = subprocess.run([sys.executable, "-B", "-m", "benchlib.callkeys", "make", "-h"], cwd=BENCHDIR,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("-symbols", proc.stdout)


if __name__ == "__main__":
    unittest.main()
