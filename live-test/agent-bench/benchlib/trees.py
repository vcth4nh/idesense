"""Pinned benchmark trees: a copy of a product, a manifest and a repository with one commit.

    python3 -m benchlib.trees make <product>      (run from live-test/agent-bench)
    python3 -m benchlib.trees verify <product>

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
"""
import hashlib
import os
import shutil
import subprocess
import sys

WT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
REAL_PRODUCTS = os.path.join(WT, "live-test", "real-products")
BENCH = "/home/ubuntu/dev/idesense-bench"
TREES = os.path.join(BENCH, "trees")
GIT_AUTHOR = ["-c", "user.name=bench", "-c", "user.email=bench@localhost"]

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

    _git(tree, "init", "-q")
    _git(tree, "add", "-A")
    _git(tree, *GIT_AUTHOR, "commit", "-q", "-m", "Initial commit")
    committed = [os.fsdecode(p) for p in _git(tree, "ls-files", "-z").split(b"\0") if p]
    if set(committed) != set(files):
        raise RuntimeError(f"the commit has {len(committed)} files, the checkout {len(files)}")

    prepare, exclude = PRODUCTS[product]
    with open(os.path.join(tree, ".git", "info", "exclude"), "a", encoding="utf-8") as f:
        f.write("".join(line + "\n" for line in exclude))
    prepare(tree)
    status = _git(tree, "status", "--porcelain").decode("utf-8", "replace")
    if status:
        raise RuntimeError(f"git status in {tree} is not clean after the preparation:\n{status}")
    return tree


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("make", "verify"):
        print("usage: python3 -m benchlib.trees make <product> | verify <product>", file=sys.stderr)
        return 2
    command, name = argv
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
