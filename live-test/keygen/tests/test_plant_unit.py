import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from common import keyrecord as keys
from common import trees
from keygen import plant, pykeys

HERE = os.path.dirname(os.path.abspath(__file__))
BENCHDIR = os.path.dirname(os.path.dirname(HERE))
PY_FIXTURE = os.path.join(HERE, "fixtures", "pkg")
GO_FIXTURE = os.path.join(BENCHDIR, "keygen", "gokeys", "testdata", "mod")
GOKEYS_SRC = os.path.join(BENCHDIR, "keygen", "gokeys")

PRICE, LAZY, WEIGHT = "compute_total_price", "lazy_total_amount", "total_weight"
SHARED = "refresh_totals"

# Added to the copy of the Python fixture: words that hold a planted name only as a part of a longer word, and one
# line with two planted names in code and two in a comment.
EXTRA_PY = (
    "# Fixture of the plant tests: words that hold a planted name only as a part.\n"
    "from shop.models import Lazy, Leaf\n"
    "\n"
    "NOTE = \"compute_total_prices and lazy_total_amounts are other words\"\n"
    "compute_total_price_count = 2\n"
    "\n"
    "\n"
    "def both(leaf, lazy):\n"
    "    return leaf.compute_total_price(1) + lazy.lazy_total_amount  # compute_total_price, lazy_total_amount\n"
)
BOTH_LINE_PLANTED = "    return leaf.refresh_totals(1) + lazy.refresh_totals  # refresh_totals, refresh_totals"

# Added to the copy of the Go fixture: a second method with a unique name, and a line with two planted names.
EXTRA_GO = (
    "package mod\n"
    "\n"
    "// Meter counts; its method Tick has a name that no other object has.\n"
    "type Meter struct{ n int }\n"
    "\n"
    "func (m *Meter) Tick() { m.n++ }\n"
    "\n"
    "func useMeter() int {\n"
    "\tvar m Meter\n"
    "\tvar c Counter\n"
    "\tm.Tick(); c.Incr()\n"
    "\tm.Tick()\n"
    "\treturn m.n + c.n\n"
    "}\n"
)


def site(file, line, col, cls, why):
    return {"file": file, "line": line, "col": col, "class": cls, "why": why}


def all_files(root):
    out = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        out += [os.path.relpath(os.path.join(folder, f), root).replace(os.sep, "/")
                for f in files if not f.endswith(".pyc")]
    return sorted(out)


def make_source(tmp, fixture, extra_rel, extra_text):
    """A source tree: a copy of the fixture with one more file, and its manifest next to it."""
    src = os.path.join(tmp, "src")
    shutil.copytree(fixture, src, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    with open(os.path.join(src, extra_rel), "w", encoding="utf-8") as f:
        f.write(extra_text)
    trees.write_manifest(src, all_files(src), src + ".manifest")
    return src


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


def by_original(records):
    return {r["original"]: r for r in records}


class PythonPlantTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.src = make_source(self.tmp, PY_FIXTURE, "shop/extra_words.py", EXTRA_PY)
        self.dst = os.path.join(self.tmp, "pkg-plant")
        self.out = os.path.join(self.tmp, "plant.jsonl")

    def plant(self, names, shared=SHARED, **kw):
        return plant.make("python", self.src, self.dst, names, shared, self.out, attrs=set(), **kw)

    def assert_refused(self, names, text, shared=SHARED):
        with self.assertRaises(plant.PlantError) as ctx:
            self.plant(names, shared)
        self.assertIn(text, str(ctx.exception))
        self.assertFalse(os.path.lexists(self.dst))
        self.assertFalse(os.path.lexists(self.out))

    def test_plant_python_renames_code_not_strings(self):
        self.plant([PRICE, LAZY])
        # A rename by whole words gives the planted tree: no planted name is in a string, and a longer word
        # that holds a planted name stays.
        word = re.compile(r"\b(?:%s|%s)\b" % (PRICE, LAZY))
        files = all_files(self.src)
        self.assertEqual(files, all_files(self.dst))
        for rel in files:
            self.assertEqual(word.sub(SHARED, read(self.src, rel)), read(self.dst, rel), rel)
        planted = read(self.dst, "shop/extra_words.py").split("\n")
        self.assertEqual("NOTE = \"compute_total_prices and lazy_total_amounts are other words\"", planted[3])
        self.assertEqual("compute_total_price_count = 2", planted[4])
        self.assertEqual(BOTH_LINE_PLANTED, planted[8])
        self.assertIn("\"render_summary_text\"", read(self.dst, "shop/service.py"))
        self.assertEqual([], pykeys.ident_sites(self.dst, PRICE))
        self.assertEqual([], pykeys.ident_sites(self.dst, LAZY))
        self.assertEqual([], [s for s in pykeys.ident_sites(self.dst, SHARED) if s["in"] == "string"])

    def test_plant_key_separates_the_original_methods(self):
        records = self.plant([PRICE, LAZY])
        self.assertEqual(records, keys.load_keys(self.out))
        # The columns on the line with two names come from the planted text, not from the plant arithmetic.
        c1, c2, c3, c4 = (m.start() + 1 for m in re.finditer(SHARED, BOTH_LINE_PLANTED))
        price_id = "plant:python:pkg-plant:Leaf.compute_total_price"
        lazy_id = "plant:python:pkg-plant:Lazy.lazy_total_amount"
        rec = by_original(records)
        self.assertEqual({
            "id": price_id, "lang": "python", "kind": "method", "name": SHARED, "container": "Leaf",
            "decl": {"file": "shop/models.py", "line": 22, "col": 9}, "family": [price_id],
            "sites": [site("shop/extra_words.py", 9, c1, "required", "use"),
                      site("shop/extra_words.py", 9, c2, "forbidden", "decoy"),
                      site("shop/extra_words.py", 9, c3, "dnc", "comment"),
                      site("shop/extra_words.py", 9, c4, "dnc", "comment"),
                      site("shop/models.py", 22, 9, "dnc", "decl"),
                      site("shop/models.py", 69, 9, "dnc", "decl"),
                      site("shop/service.py", 7, 7, "dnc", "comment"),
                      site("shop/service.py", 8, 18, "required", "use"),
                      site("shop/service.py", 10, 16, "required", "use"),
                      site("shop/service.py", 15, 17, "required", "use"),
                      site("tests/test_shop.py", 7, 19, "required", "use"),
                      site("tests/test_shop.py", 26, 23, "required", "use"),
                      site("tests/test_shop.py", 33, 19, "forbidden", "decoy")],
            "implementers": [], "external": [], "source": "plant", "original": PRICE}, rec[PRICE])
        lazy = rec[LAZY]
        self.assertEqual((lazy_id, "Lazy", {"file": "shop/models.py", "line": 69, "col": 9}),
                         (lazy["id"], lazy["container"], lazy["decl"]))
        self.assertEqual([("shop/extra_words.py", 9, c2), ("tests/test_shop.py", 33, 19)],
                         [(s["file"], s["line"], s["col"]) for s in lazy["sites"] if s["class"] == "required"])
        self.assertEqual(6, sum(1 for s in lazy["sites"] if s["class"] == "forbidden"))
        # The line with a use of each method scores as required for each record.
        self.assertEqual("required+decoy", keys.line_classes(rec[PRICE])[("shop/extra_words.py", 9)])
        self.assertEqual("required+decoy", keys.line_classes(lazy)[("shop/extra_words.py", 9)])
        self.assertEqual("forbidden", keys.line_classes(lazy)[("shop/service.py", 8)])

    def test_plant_refuses_non_unique_name(self):
        self.assert_refused([PRICE, "render_summary_text"], "render_summary_text")  # in a string literal
        self.assert_refused([PRICE, "describe"], "describe")  # short name
        self.assert_refused([PRICE, "format_receipt_line"], "format_receipt_line")  # a function, not a method

    def test_plant_refuses_a_shared_name_that_occurs_in_the_tree(self):
        self.assert_refused([PRICE, LAZY], "price_twice", shared="price_twice")  # a function name
        self.assert_refused([PRICE, LAZY], "times", shared="times")  # only a comment word in the fixture

    def test_plant_refuses_two_methods_of_one_class(self):
        self.assert_refused([PRICE, WEIGHT], "Leaf")

    def test_plant_refuses_methods_of_related_classes(self):
        with open(os.path.join(self.src, "shop", "special.py"), "w", encoding="utf-8") as f:
            f.write("from shop.models import Leaf\n\n\nclass Special(Leaf):\n"
                    "    def special_discount_amount(self):\n        return 1\n\n\n"
                    "def use(special):\n    return special.special_discount_amount()\n")
        trees.write_manifest(self.src, all_files(self.src), self.src + ".manifest")
        self.assert_refused([PRICE, "special_discount_amount"], "Special")

    def test_plant_refuses_an_existing_target(self):
        os.makedirs(self.dst)
        with self.assertRaises(plant.PlantError):
            self.plant([PRICE, LAZY])
        self.assertEqual([], os.listdir(self.dst))

    def test_planted_tree_is_a_clean_one_commit_repository(self):
        self.plant([PRICE, LAZY])

        def git(*args):
            return subprocess.run(["git", "-C", self.dst, *args], check=True, capture_output=True,
                                  text=True).stdout

        self.assertEqual("1", git("rev-list", "--count", "HEAD").strip())
        self.assertEqual("bench <bench@localhost>|bench <bench@localhost>|Initial commit",
                         git("log", "-1", "--format=%an <%ae>|%cn <%ce>|%s").strip())
        self.assertEqual("", git("status", "--porcelain"))
        self.assertEqual(all_files(self.src), sorted(git("ls-files").split("\n")[:-1]))
        self.assertEqual([], trees.verify_manifest(self.dst, self.dst + ".manifest"))
        self.assertEqual(all_files(self.src), [line.split("  ", 1)[1] for line in
                                               read(self.tmp, "pkg-plant.manifest").splitlines()])
        # The source tree does not change.
        self.assertEqual([], trees.verify_manifest(self.src, self.src + ".manifest"))
        self.assertFalse(os.path.lexists(os.path.join(self.src, ".git")))

    def test_candidates_lists_unique_methods(self):
        found = plant.candidates("python", self.src, 2, attrs=set())
        self.assertEqual([{"id": "py:shop.models.Leaf.compute_total_price", "name": PRICE, "container": "Leaf",
                           "required_lines": 6, "test_decl": False},
                          {"id": "py:shop.models.Lazy.lazy_total_amount", "name": LAZY, "container": "Lazy",
                           "required_lines": 2, "test_decl": False}], found)

    def test_cli_make_and_candidates(self):
        env = dict(os.environ, PYTHONPATH=self.src)
        proc = subprocess.run([sys.executable, "-B", "-m", "keygen.plant", "candidates", "-lang", "python",
                               "-tree", self.src, "-python", sys.executable, "-modules", "shop", "-min-sites", "3"],
                              cwd=BENCHDIR, env=env, capture_output=True, text=True)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual(["py:shop.models.Leaf.compute_total_price"],
                         [json.loads(line)["id"] for line in proc.stdout.splitlines()])
        proc = subprocess.run([sys.executable, "-B", "-m", "keygen.plant", "make", "-lang", "python",
                               "-src", self.src, "-dst", self.dst, "-names", f"{PRICE},{LAZY}", "-shared", SHARED,
                               "-out", self.out, "-python", sys.executable, "-modules", "shop"],
                              cwd=BENCHDIR, env=env, capture_output=True, text=True)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual({PRICE, LAZY}, set(by_original(keys.load_keys(self.out))))
        proc = subprocess.run([sys.executable, "-B", "-m", "keygen.plant", "make", "-lang", "python",
                               "-src", self.src, "-dst", self.dst, "-names", f"{PRICE},{LAZY}", "-shared", SHARED,
                               "-out", self.out, "-python", sys.executable, "-modules", "shop"],
                              cwd=BENCHDIR, env=env, capture_output=True, text=True)
        self.assertEqual(1, proc.returncode)
        self.assertIn("exists", proc.stderr)


@unittest.skipUnless(shutil.which("go"), "no go toolchain")
class GoPlantTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bin_dir = tempfile.mkdtemp(prefix="plant-gokeys-")
        cls.gokeys = os.path.join(cls.bin_dir, "gokeys")
        subprocess.run(["go", "-C", GOKEYS_SRC, "build", "-o", cls.gokeys, "."], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.bin_dir)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.src = make_source(self.tmp, GO_FIXTURE, "meter.go", EXTRA_GO)
        self.src_keys = self.extract(self.src, "src.jsonl")
        self.dst = os.path.join(self.tmp, "mod-plant")
        self.out = os.path.join(self.tmp, "plant.jsonl")

    def extract(self, tree, name):
        out = os.path.join(self.tmp, name)
        subprocess.run([self.gokeys, "extract", "-tree", tree, "-configs", "linux,windows", "-out", out],
                       check=True, capture_output=True)
        return out

    def plant(self, names, shared):
        return plant.make("go", self.src, self.dst, names, shared, self.out, keys_path=self.src_keys,
                          gokeys=self.gokeys)

    def test_plant_go_key_equals_compiler_key(self):
        records = by_original(self.plant(["Incr", "Tick"], "Advance"))
        compiler = {r["id"]: r for r in keys.load_keys(self.extract(self.dst, "dst.jsonl"))}

        def positions(rec, cls):
            return {(s["file"], s["line"], s["col"]) for s in rec["sites"] if s["class"] == cls}

        for orig, container in (("Incr", "Counter"), ("Tick", "Meter")):
            rec = records[orig]
            self.assertEqual(f"plant:go:mod-plant:{container}.{orig}", rec["id"])
            truth = compiler[f"go:example.com/mod.{container}.Advance"]
            self.assertEqual(truth["decl"], rec["decl"])
            self.assertEqual(positions(truth, "required"), positions(rec, "required"), orig)
            # The compiler calls the declaration of the other planted method forbidden; the plant key calls it dnc.
            other_decls = {(r["decl"]["file"], r["decl"]["line"], r["decl"]["col"])
                           for o, r in records.items() if o != orig}
            self.assertEqual(positions(truth, "forbidden"), positions(rec, "forbidden") | other_decls, orig)
        self.assertEqual(3, sum(1 for s in records["Incr"]["sites"] if s["class"] == "required"))
        self.assertEqual(["linux", "windows"], records["Tick"]["sites"][0]["configs"])
        self.assertNotIn("Incr", read(self.dst, "funcs.go"))

    def test_plant_refuses_non_unique_name(self):
        with self.assertRaises(plant.PlantError) as ctx:
            self.plant(["Incr", "Speak"], "Advance")  # two types have a method Speak
        self.assertIn("Speak", str(ctx.exception))
        with self.assertRaises(plant.PlantError) as ctx:
            self.plant(["Incr", "Tick"], "advance")  # the names keep their export state
        self.assertIn("export", str(ctx.exception))
        with self.assertRaises(plant.PlantError) as ctx:
            self.plant(["Incr", "Tick"], "Compute")  # the shared name occurs in the tree
        self.assertIn("Compute", str(ctx.exception))
        self.assertFalse(os.path.lexists(self.dst))

    def test_candidates_checks_each_occurrence(self):
        found = plant.candidates("go", self.src, 0, keys_path=self.src_keys, gokeys=self.gokeys)
        self.assertEqual([("go:example.com/mod.Counter.Incr", "Counter", 3, False),
                          ("go:example.com/mod.Meter.Tick", "Meter", 2, False)],
                         [(c["id"], c["container"], c["required_lines"], c["test_decl"]) for c in found])


if __name__ == "__main__":
    unittest.main()
