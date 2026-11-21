import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from common import trees

TREE_NAMES = ["caddy", "caddy-plant-1", "caddy-plant-2", "caddy-plant-3",
              "beets", "beets-plant-1", "beets-plant-2", "beets-plant-3"]


def write(root, rel, text, mode=0o644):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, mode)


class TreeTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name


class ManifestTest(TreeTestCase):
    def make_tree(self):
        root = os.path.join(self.tmp, "tree")
        write(root, "a.txt", "alpha\n")
        write(root, "sub/b.txt", "beta\n")
        write(root, "sub/م.txt", "gamma\n")
        manifest = os.path.join(self.tmp, "tree.manifest")
        trees.write_manifest(root, ["sub/b.txt", "sub/م.txt", "a.txt"], manifest)
        return root, manifest

    def test_manifest_detects_changed_file(self):
        root, manifest = self.make_tree()
        with open(manifest, encoding="utf-8") as f:
            paths = [line.rstrip("\n").split("  ", 1)[1] for line in f]
        self.assertEqual(["a.txt", "sub/b.txt", "sub/م.txt"], paths)
        self.assertEqual([], trees.verify_manifest(root, manifest))
        write(root, "sub/b.txt", "beta, changed\n")
        self.assertEqual(["sub/b.txt"], trees.verify_manifest(root, manifest))

    def test_manifest_detects_absent_file(self):
        root, manifest = self.make_tree()
        os.remove(os.path.join(root, "a.txt"))
        write(root, "extra.txt", "not in the manifest\n")
        self.assertEqual(["a.txt"], trees.verify_manifest(root, manifest))


class CopyTest(TreeTestCase):
    def test_copy_keeps_modes_and_symlinks(self):
        src = os.path.join(self.tmp, "src")
        dst = os.path.join(self.tmp, "dst")
        write(src, "run.sh", "#!/bin/sh\n", 0o755)
        write(src, "data.txt", "data\n", 0o644)
        write(src, "sub/deep.txt", "deep\n", 0o600)
        write(src, "untracked.txt", "not in the list\n")
        os.symlink("data.txt", os.path.join(src, "link"))
        os.symlink("../run.sh", os.path.join(src, "sub", "up"))
        files = ["run.sh", "data.txt", "sub/deep.txt", "link", "sub/up"]

        trees.copy_tree(src, dst, files)

        for rel in ("run.sh", "data.txt", "sub/deep.txt"):
            s, d = os.path.join(src, rel), os.path.join(dst, rel)
            self.assertFalse(os.path.islink(d), rel)
            self.assertEqual(stat.S_IMODE(os.stat(s).st_mode), stat.S_IMODE(os.stat(d).st_mode), rel)
            with open(s, "rb") as fs, open(d, "rb") as fd:
                self.assertEqual(fs.read(), fd.read(), rel)
        self.assertEqual("data.txt", os.readlink(os.path.join(dst, "link")))
        self.assertEqual("../run.sh", os.readlink(os.path.join(dst, "sub", "up")))
        self.assertFalse(os.path.lexists(os.path.join(dst, "untracked.txt")))


class MakeTest(TreeTestCase):
    def test_make_refuses_existing_target(self):
        checkout = os.path.join(self.tmp, "checkout")
        write(checkout, "main.go", "package main\n")
        trees_dir = os.path.join(self.tmp, "trees")
        write(trees_dir, "caddy/marker", "keep\n")

        with self.assertRaises(FileExistsError):
            trees.make("caddy", checkout, trees_dir)

        self.assertEqual(["marker"], os.listdir(os.path.join(trees_dir, "caddy")))
        self.assertFalse(os.path.lexists(os.path.join(trees_dir, "caddy.manifest")))


def git_out(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout


def fake_prepare(tree):
    # As a preparation: a file that the exclude lines must hide from `git status`.
    write(tree, ".idea/modules.xml", "<project />\n")


class SlotIdTest(unittest.TestCase):
    def test_slot_id_is_stable_and_4_hex(self):
        ids = {}
        for tree in TREE_NAMES:
            sid = trees.slot_id(tree)
            self.assertRegex(sid, r"\A[0-9a-f]{4}\Z", tree)
            self.assertEqual(sid, trees.slot_id(tree), tree)
            self.assertEqual(hashlib.sha256(("slot:" + tree).encode("utf-8")).hexdigest()[:4], sid, tree)
            ids[tree] = sid
        self.assertEqual(len(TREE_NAMES), len(set(ids.values())), ids)
        # A pinned value: the id of a tree must not change with the code.
        self.assertEqual("3e9c", trees.slot_id("caddy-plant-2"))

    def test_slot_path_has_product_leaf_and_no_tree_name(self):
        self.assertEqual("/home/ubuntu/dev/ws", trees.SLOTS_ROOT)
        self.assertEqual("/home/ubuntu/dev/idesense-bench/trees/slots.json", trees.SLOTS_FILE)
        for tree in TREE_NAMES:
            product = tree.split("-", 1)[0]
            self.assertEqual(product, trees.product_of(tree), tree)
            path = trees.slot_path(tree)
            self.assertEqual(os.path.join("/home/ubuntu/dev/ws", trees.slot_id(tree), product), path)
            for word in ("plant", "bench", "idesense"):
                self.assertNotIn(word, path, tree)
        self.assertEqual("/r/3e9c/caddy", trees.slot_path("caddy-plant-2", root="/r"))
        for bad in ("", "other", "caddy-plant", "caddy-2", "caddy-plant-x", "caddy/plant-1", "../caddy"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                trees.product_of(bad)


class SlotTest(TreeTestCase):
    """The products get a fake preparation: no `go` or `uv` call."""

    def setUp(self):
        super().setUp()
        self.trees_dir = os.path.join(self.tmp, "trees")
        self.root = os.path.join(self.tmp, "ws")
        self.slots_file = os.path.join(self.trees_dir, "slots.json")
        fake = {"caddy": (fake_prepare, ["/.idea/"]), "beets": (fake_prepare, ["/.idea/", "/.venv/"])}
        patcher = mock.patch.dict(trees.PRODUCTS, fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def master(self, name, files):
        """A master tree with its manifest, and files that are not in the manifest (as .idea, .venv, .git)."""
        tree = os.path.join(self.trees_dir, name)
        for rel, text in files.items():
            write(tree, rel, text)
        write(tree, ".idea/workspace.xml", "<master />\n")
        write(tree, ".venv/bin/python", "#!/bin/sh\n", 0o755)
        write(tree, ".git/marker", "master\n")
        write(tree, "untracked.txt", "not in the manifest\n")
        trees.write_manifest(tree, list(files), tree + ".manifest")
        return tree

    def slot(self, name):
        return trees.make_slot(name, self.trees_dir, self.root, self.slots_file)

    def main(self, *argv):
        with mock.patch.object(trees, "TREES", self.trees_dir), \
                mock.patch.object(trees, "SLOTS_ROOT", self.root), \
                mock.patch.object(trees, "SLOTS_FILE", self.slots_file):
            return trees.main(list(argv))

    def test_slot_copies_manifest_files_and_verifies(self):
        files = {"main.go": "package main\n", "sub/a.go": "package sub\n", "sub/b.txt": "b\n"}
        master = self.master("caddy-plant-2", files)
        self.assertEqual({}, trees.load_slots(self.slots_file))

        self.assertEqual(0, self.main("slot", "caddy-plant-2"))

        sid = trees.slot_id("caddy-plant-2")
        path = os.path.join(self.root, sid, "caddy")
        entry = {"slot": sid, "path": path, "product": "caddy"}
        self.assertEqual({"caddy-plant-2": entry}, trees.load_slots(self.slots_file))
        # The manifest files, the own .git and the .idea of the preparation; nothing else of the master.
        self.assertEqual([sid], os.listdir(self.root))
        self.assertEqual([".git", ".idea", "main.go", "sub"], sorted(os.listdir(path)))
        self.assertEqual(["modules.xml"], os.listdir(os.path.join(path, ".idea")))
        self.assertFalse(os.path.lexists(os.path.join(path, ".git", "marker")))
        self.assertEqual([], trees.verify_manifest(path, master + ".manifest"))
        self.assertEqual(sorted(files), git_out(path, "ls-files").split())
        self.assertEqual("", git_out(path, "status", "--porcelain"))

        # A second slot adds its entry; the atomic write leaves no other file.
        self.master("beets", {"beets/__init__.py": "\n"})
        entry2 = self.slot("beets")
        self.assertEqual({"slot": trees.slot_id("beets"), "product": "beets",
                          "path": os.path.join(self.root, trees.slot_id("beets"), "beets")}, entry2)
        with open(self.slots_file, encoding="utf-8") as f:
            self.assertEqual({"caddy-plant-2": entry, "beets": entry2}, json.load(f))
        self.assertEqual(sorted(["beets", "beets.manifest", "caddy-plant-2", "caddy-plant-2.manifest", "slots.json"]),
                         sorted(os.listdir(self.trees_dir)))

        # A master file that differs from the master manifest: the check of the slot fails, no entry.
        drift = self.master("caddy-plant-1", {"main.go": "package main\n"})
        write(drift, "main.go", "package main // changed\n")
        self.assertEqual(1, self.main("slot", "caddy-plant-1"))
        self.assertNotIn("caddy-plant-1", trees.load_slots(self.slots_file))

    def test_slot_refuses_existing_path(self):
        self.master("caddy", {"main.go": "package main\n"})
        path = trees.slot_path("caddy", self.root)
        write(path, "marker", "keep\n")
        self.assertEqual(2, self.main("slot", "caddy"))
        self.assertEqual(["marker"], os.listdir(path))
        self.assertFalse(os.path.lexists(self.slots_file))

        # The slot folder exists, with another product in it.
        shutil.rmtree(os.path.dirname(path))
        write(os.path.join(os.path.dirname(path), "beets"), "marker", "keep\n")
        self.assertEqual(2, self.main("slot", "caddy"))
        self.assertFalse(os.path.lexists(path))
        shutil.rmtree(os.path.dirname(path))

        # The slot id of the tree is the slot id of another tree in slots.json.
        other = {"other": {"slot": trees.slot_id("caddy"), "path": "/x/y/caddy", "product": "caddy"}}
        write(self.trees_dir, "slots.json", json.dumps(other))
        self.assertEqual(2, self.main("slot", "caddy"))
        self.assertFalse(os.path.lexists(os.path.dirname(path)))
        self.assertEqual(other, trees.load_slots(self.slots_file))

    def test_slot_commit_author_is_dev(self):
        self.master("beets-plant-1", {"beets/__init__.py": "\n", "test/t.py": "\n"})
        entry = self.slot("beets-plant-1")
        self.assertEqual("dev <dev@localhost>|dev <dev@localhost>|Initial commit\n",
                         git_out(entry["path"], "log", "--format=%an <%ae>|%cn <%ce>|%s"))
        self.assertEqual("", git_out(entry["path"], "status", "--porcelain"))
        # `make` keeps its author: commit_and_prepare with no author.
        other = os.path.join(self.tmp, "other")
        write(other, "a.txt", "a\n")
        trees.commit_and_prepare(other, ["a.txt"], None)
        self.assertEqual("bench <bench@localhost>|bench <bench@localhost>|Initial commit\n",
                         git_out(other, "log", "--format=%an <%ae>|%cn <%ce>|%s"))


if __name__ == "__main__":
    unittest.main()
