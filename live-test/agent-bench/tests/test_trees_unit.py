import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import stat
import tempfile
import unittest

from benchlib import trees


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


if __name__ == "__main__":
    unittest.main()
