"""Pinned benchmark trees: a copy of a product, a manifest and a repository with one commit.

    python3 -m common.trees make <product>      (run from live-test)
    python3 -m common.trees verify <product>

`make` copies the files that `git ls-files` lists in WT/live-test/real-products/<product> to
BENCH/trees/<product> and writes BENCH/trees/<product>.manifest: one line `<sha256>  <path>`
for each file, sorted by path (the hash of a symbolic link is the hash of its target text).
Then it makes a new repository there with one commit of these files (author
`bench <bench@localhost>`), and prepares the product for its IDE. The files of the preparation
(`.idea`, `.venv`) come after the commit, and `.git/info/exclude` names them, so `git status`
in the tree is clean. `make` refuses an existing tree. A failed `make` leaves its tree: remove
the tree and its manifest before the next `make`.

`verify` prints each path of BENCH/trees/<product>.manifest that is absent or has a different
hash, and exits 0 when there is none.

    python3 -m common.trees slot <tree>         (a tree of BENCH/trees, for example caddy-plant-2)

`slot` makes a copy of the master tree BENCH/trees/<tree> at a neutral path, the slot path
SLOTS_ROOT/<slot id>/<product>: the path has no tree name. It copies only the files of the master
manifest, makes a new repository with one commit (author `dev <dev@localhost>`), prepares the
product as `make` does, checks the slot against the master manifest, and adds the entry of the
tree to SLOTS_FILE. It exits 2 when the slot folder SLOTS_ROOT/<slot id> exists or another tree
of SLOTS_FILE has the slot id. A failed `slot` leaves its slot folder: remove it before the next
`slot`. The master tree and its manifest stay as they are.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

WT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
REAL_PRODUCTS = os.path.join(WT, "live-test", "real-products")
BENCH = "/home/ubuntu/dev/idesense-bench"
TREES = os.path.join(BENCH, "trees")
GIT_AUTHOR = ["-c", "user.name=bench", "-c", "user.email=bench@localhost"]
SLOTS_ROOT = "/home/ubuntu/dev/ws"
SLOTS_FILE = BENCH + "/trees/slots.json"
SLOT_AUTHOR = ["-c", "user.name=dev", "-c", "user.email=dev@localhost"]

# The .idea files of live-test/real-products/_setup/<product>/bootstrap.sh, with the same text.
CADDY_WORKSPACE = """<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="GOROOT" url="file://{goroot}" />
</project>
"""
CADDY_IDEA = {
    "modules.xml": """<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/caddy.iml" filepath="$PROJECT_DIR$/.idea/caddy.iml" />
    </modules>
  </component>
</project>
""",
    "caddy.iml": """<?xml version="1.0" encoding="UTF-8"?>
<module type="WEB_MODULE" version="4">
  <component name="Go" enabled="true" />
  <component name="GoModuleSettings" enabled="true" />
  <component name="NewModuleRootManager">
    <content url="file://$MODULE_DIR$" />
    <orderEntry type="inheritedJdk" />
    <orderEntry type="sourceFolder" forTests="false" />
  </component>
</module>
""",
}
BEETS_IDEA = {
    "modules.xml": """<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="ProjectModuleManager">
    <modules>
      <module fileurl="file://$PROJECT_DIR$/.idea/beets.iml" filepath="$PROJECT_DIR$/.idea/beets.iml" />
    </modules>
  </component>
</project>
""",
    "beets.iml": """<?xml version="1.0" encoding="UTF-8"?>
<module external.system.id="pyproject.toml" type="PYTHON_MODULE" version="4">
  <component name="NewModuleRootManager">
    <content url="file://$MODULE_DIR$">
      <sourceFolder url="file://$MODULE_DIR$" isTestSource="false" />
      <sourceFolder url="file://$MODULE_DIR$/test" isTestSource="true" />
      <excludeFolder url="file://$MODULE_DIR$/.venv" />
    </content>
    <orderEntry type="inheritedJdk" />
    <orderEntry type="sourceFolder" forTests="false" />
  </component>
</module>
""",
}


def _write_idea(tree: str, files: dict[str, str]) -> None:
    idea = os.path.join(tree, ".idea")
    os.makedirs(idea, exist_ok=True)
    for name, text in files.items():
        with open(os.path.join(idea, name), "w", encoding="utf-8") as f:
            f.write(text)


def _prepare_caddy(tree: str) -> None:
    subprocess.run(["go", "mod", "download"], cwd=tree, check=True)
    goroot = subprocess.run(["go", "env", "GOROOT"], cwd=tree, check=True,
                            capture_output=True, text=True).stdout.strip()
    _write_idea(tree, {"workspace.xml": CADDY_WORKSPACE.format(goroot=goroot), **CADDY_IDEA})


def _prepare_beets(tree: str) -> None:
    subprocess.run(["uv", "sync", "--locked", "--python", "3.12", "--quiet"], cwd=tree, check=True)
    _write_idea(tree, BEETS_IDEA)


# product -> (preparation, the lines for .git/info/exclude)
PRODUCTS = {
    "caddy": (_prepare_caddy, ["/.idea/"]),
    "beets": (_prepare_beets, ["/.idea/", "/.venv/", "__pycache__/"]),
}


def _git(repo: str, *args: str) -> bytes:
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True).stdout


def tracked_files(checkout: str) -> list[str]:
    return [os.fsdecode(p) for p in _git(checkout, "ls-files", "-z").split(b"\0") if p]


def copy_tree(src: str, dst: str, files: list[str]) -> None:
    """Copy the files (paths relative to src) to dst, with their modes; a symbolic link stays a link."""
    os.makedirs(dst, exist_ok=True)
    for rel in files:
        s, d = os.path.join(src, rel), os.path.join(dst, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if os.path.islink(s):
            os.symlink(os.readlink(s), d)
        else:
            shutil.copy2(s, d)


def _digest(path: str) -> str:
    h = hashlib.sha256()
    if os.path.islink(path):
        h.update(os.fsencode(os.readlink(path)))
    else:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def write_manifest(root: str, files: list[str], path: str) -> None:
    with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="\n") as f:
        for rel in sorted(files):
            f.write(f"{_digest(os.path.join(root, rel))}  {rel}\n")


def verify_manifest(root: str, path: str) -> list[str]:
    """Return the paths of the manifest that are absent below root or have a different hash."""
    differ = []
    with open(path, encoding="utf-8", errors="surrogateescape", newline="\n") as f:
        for line in f:
            sha, rel = line.rstrip("\n").split("  ", 1)
            try:
                same = _digest(os.path.join(root, rel)) == sha
            except OSError:
                same = False
            if not same:
                differ.append(rel)
    return differ


def make(product: str, checkout: str, trees: str) -> str:
    """Make the pinned tree trees/<product> from the tracked files of checkout; return its path."""
    if product not in PRODUCTS:
        raise ValueError(f"unknown product {product!r}; known: {', '.join(sorted(PRODUCTS))}")
    tree = os.path.join(trees, product)
    if os.path.lexists(tree):
        raise FileExistsError(f"{tree} exists")
    files = tracked_files(checkout)
    copy_tree(checkout, tree, files)
    write_manifest(tree, files, tree + ".manifest")
    commit_and_prepare(tree, files, product)
    return tree


def commit_and_prepare(tree: str, files: list[str], product: str | None, author: list[str] = GIT_AUTHOR) -> None:
    """Make a new repository in tree with one commit of the files (author and committer from the git options
    `author`, by default `bench <bench@localhost>`; message `Initial commit`). With a product of PRODUCTS: then
    add its lines to `.git/info/exclude`, run its preparation, and check that `git status` is clean."""
    _git(tree, "init", "-q")
    _git(tree, "add", "-A")
    _git(tree, *author, "commit", "-q", "-m", "Initial commit")
    committed = [os.fsdecode(p) for p in _git(tree, "ls-files", "-z").split(b"\0") if p]
    if set(committed) != set(files):
        raise RuntimeError(f"the commit has {len(committed)} files, the checkout {len(files)}")
    if product is None:
        return

    prepare, exclude = PRODUCTS[product]
    with open(os.path.join(tree, ".git", "info", "exclude"), "a", encoding="utf-8") as f:
        f.write("".join(line + "\n" for line in exclude))
    prepare(tree)
    status = _git(tree, "status", "--porcelain").decode("utf-8", "replace")
    if status:
        raise RuntimeError(f"git status in {tree} is not clean after the preparation:\n{status}")


class SlotConflict(Exception):
    """The slot folder exists, or another tree has the slot id."""


def product_of(tree: str) -> str:
    """The product of a tree: `caddy` for `caddy` and for `caddy-plant-2`."""
    m = re.fullmatch(r"([a-z]+)(?:-plant-[0-9]+)?", tree)
    if not m or m.group(1) not in PRODUCTS:
        raise ValueError(f"tree {tree!r} is not <product> or <product>-plant-<n> of the products "
                         f"{', '.join(sorted(PRODUCTS))}")
    return m.group(1)


def slot_id(tree: str) -> str:
    return hashlib.sha256(("slot:" + tree).encode("utf-8")).hexdigest()[:4]


def slot_path(tree: str, root: str = SLOTS_ROOT) -> str:
    return os.path.join(root, slot_id(tree), product_of(tree))


def load_slots(path: str = SLOTS_FILE) -> dict:
    """{"<tree>": {"slot": "<id>", "path": "<slot path>", "product": "<product>"}}; {} when there is no file."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _manifest_files(manifest: str) -> list[str]:
    with open(manifest, encoding="utf-8", errors="surrogateescape", newline="\n") as f:
        return [line.rstrip("\n").split("  ", 1)[1] for line in f if line.strip()]


def make_slot(tree: str, trees: str = TREES, root: str = SLOTS_ROOT, slots_file: str = SLOTS_FILE) -> dict:
    """Make the slot of the master tree trees/<tree> (see the module text); return its entry of slots_file."""
    product = product_of(tree)
    master = os.path.join(trees, tree)
    manifest = master + ".manifest"
    if not os.path.isdir(master) or not os.path.isfile(manifest):
        raise FileNotFoundError(f"no master tree {master} with its manifest")
    sid, path = slot_id(tree), slot_path(tree, root)
    slots = load_slots(slots_file)
    others = sorted(t for t, e in slots.items() if t != tree and e.get("slot") == sid)
    if others:
        raise SlotConflict(f"the slot id {sid} of {tree} is the slot id of {', '.join(others)} in {slots_file}")
    if os.path.lexists(os.path.dirname(path)):
        raise SlotConflict(f"the slot folder {os.path.dirname(path)} exists")
    files = _manifest_files(manifest)
    copy_tree(master, path, files)
    commit_and_prepare(path, files, product, SLOT_AUTHOR)
    differ = verify_manifest(path, manifest)
    if differ:
        raise RuntimeError(f"{len(differ)} files of {path} differ from {manifest}, the first: {differ[0]}")
    entry = {"slot": sid, "path": path, "product": product}
    slots[tree] = entry
    tmp = slots_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(slots, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, slots_file)
    return entry


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("make", "verify", "slot"):
        print("usage: python3 -m common.trees make <product> | verify <product> | slot <tree>", file=sys.stderr)
        return 2
    command, name = argv
    if command == "slot":
        try:
            entry = make_slot(name, TREES, SLOTS_ROOT, SLOTS_FILE)
        except SlotConflict as e:
            print(f"trees: {e}", file=sys.stderr)
            return 2
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            print(f"trees: {e}", file=sys.stderr)
            return 1
        print(f"{name}: slot {entry['slot']} at {entry['path']}")
        return 0
    if command == "make":
        try:
            tree = make(name, os.path.join(REAL_PRODUCTS, name), TREES)
        except (ValueError, FileExistsError) as e:
            print(f"trees: {e}", file=sys.stderr)
            return 1
        print(f"{name}: ready {tree}")
        return 0
    differ = verify_manifest(os.path.join(TREES, name), os.path.join(TREES, name + ".manifest"))
    for rel in differ:
        print(rel)
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
