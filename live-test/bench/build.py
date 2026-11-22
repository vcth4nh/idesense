"""Build the plugin under test, and start the benchmark IDEs with it.

    python3 -m bench.build             (run from live-test)
    python3 -m bench.build -start

The version of the build is `<pluginVersion of gradle.properties>-bench.<the first 7 hex digits of HEAD>`, for
example 2.1.0-bench.5beca97. The serverInfo.version of a benchmark IDE then names the commit of the plugin code. The
command refuses to build when a file outside live-test/ and docs/ has a change (`git status`): a tracked file with a
change, or an untracked file that git does not ignore (Gradle also compiles a new file below src/). A build of
changed plugin sources would get the name of a commit that it is not. Commit or remove the change first.

The command runs `./gradlew buildPlugin -PpluginVersion=<version>` in the root of the repository (or worktree) that
holds this live-test folder. Then it copies build/distributions/idesense-<version>.zip to
BENCH/plugin/idesense-<version>.zip and prints that path. When BENCH/plugin/idesense-<version>.zip exists, the
command keeps it and runs no Gradle.

With -start, the command first finds the slot folders in BENCH/trees/slots.json: the caddy trees for goland, the
beets trees for pycharm (`python3 -m common.trees slot <tree>` makes a slot). A tree with no slot is left out. Then it
takes the lock of the benchmark IDEs (BENCH/state/lock), builds, and for goland and then pycharm runs:

    bench/ide/bench-ide.sh stop <ide>
    env BENCH_PLUGIN_ZIP=<zip> bench/ide/bench-ide.sh start <ide> <slot folder>...

Each command is printed before it runs. A start ends when the IDE lists each slot folder as an open project. A -start
restarts both IDEs also when they already run this version. `bench/ide/bench-ide.sh status <ide>` prints the
serverInfo.version and the open projects of an IDE.

After a failure, the command stops at once and prints one line `build: <reason>` as its last line. Repair the cause
and run the command again: a zip that was copied stays, so the next run builds nothing. When a stop or a start
failed, an IDE can be down; the next -start stops and starts it again.

BENCH is the data root: BENCH_ROOT, default ~/dev/idesense-bench.
"""
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys

from common import settings, trees
from common.lock import Busy, ide_lock

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ide", "bench-ide.sh")
SLOTS_FILE = trees.SLOTS_FILE
IDES = (("goland", "caddy"), ("pycharm", "beets"))  # (benchmark IDE, product of its trees)
FREE_FOLDERS = ("live-test/", "docs/")  # a change below these folders does not change the plugin build
EXIT_CODES = """exit codes:
  0  done
  1  Gradle, the copy of the zip, or a stop or start of an IDE failed
  2  nothing was built or started: a file outside live-test/ and docs/ has a change or is untracked, gradle.properties
     has no pluginVersion, an IDE has no slot folder, a slot folder does not exist, or another holder has the lock"""


class BuildError(Exception):
    """The build or a command of an IDE failed (exit 1)."""


def _run(cmd: list[str], cwd: str | None = None) -> int:
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL).returncode


def _git(repo: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if proc.returncode != 0:
        lines = proc.stderr.strip().splitlines()
        raise ValueError(f"git {' '.join(args)} in {repo}: {lines[0] if lines else f'exit code {proc.returncode}'}")
    return proc.stdout


def _changed_paths(repo: str) -> list[str]:
    """The paths of the tracked files with a change (both paths of a rename or a copy), then the paths of the
    untracked files that git does not ignore."""
    fields = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    tracked, untracked = [], []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if not entry:
            continue
        if entry[:2] == "??":
            untracked.append(entry[3:])
            continue
        tracked.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            tracked.append(fields[i])
            i += 1
    return tracked + untracked


def version_of(repo: str) -> str:
    """`<pluginVersion of gradle.properties>-bench.<7 hex of HEAD>`. ValueError when a tracked file outside
    live-test/ and docs/ has a change, or an untracked file there is not ignored by git."""
    properties = os.path.join(repo, "gradle.properties")
    try:
        with open(properties, encoding="utf-8") as f:
            m = re.search(r"^\s*pluginVersion\s*=\s*(\S+)\s*$", f.read(), re.M)
    except OSError as e:
        raise ValueError(f"cannot read {properties}: {e.strerror}") from None
    if not m:
        raise ValueError(f"{properties} has no line `pluginVersion = <version>`")
    head = _git(repo, "rev-parse", "HEAD").strip()
    changed = [p for p in _changed_paths(repo) if not p.startswith(FREE_FOLDERS)]
    if changed:
        raise ValueError(f"{len(changed)} file(s) outside live-test/ and docs/ have a change or are untracked "
                         f"({', '.join(changed[:5])}{', ...' if len(changed) > 5 else ''}): commit or remove them "
                         f"first, else the build gets the name of commit {head[:7]}, which does not have them")
    return f"{m.group(1)}-bench.{head[:7]}"


def zip_path(version: str) -> str:
    return os.path.join(settings.data_root(), "plugin", f"idesense-{version}.zip")


def build(repo: str, version: str, run=_run) -> str:
    """Build the plugin of version in repo with Gradle and copy the zip to zip_path(version); return that path.
    An existing zip_path(version) is kept, with no Gradle run."""
    target = zip_path(version)
    if os.path.exists(target):
        print(f"{target} exists: no Gradle run", flush=True)
        return target
    cmd = ["./gradlew", "buildPlugin", f"-PpluginVersion={version}"]
    print(f"+ {shlex.join(cmd)}  (in {repo})", flush=True)
    code = run(cmd, cwd=repo)
    if code != 0:
        raise BuildError(f"{shlex.join(cmd)} failed with exit code {code}; no zip was copied")
    source = os.path.join(repo, "build", "distributions", f"idesense-{version}.zip")
    if not os.path.isfile(source):
        raise BuildError(f"Gradle wrote no {source}")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    part = target + ".part"
    try:
        shutil.copyfile(source, part)
        os.replace(part, target)
    except OSError as e:
        if os.path.exists(part):
            os.remove(part)
        raise BuildError(f"cannot copy {source} to {target}: {e}") from None
    return target


def start_commands(zip_file: str) -> list[list[str]]:
    """One bench-ide.sh start command for each benchmark IDE, with the slot folders of the trees of its product.
    ValueError when an IDE has no slot folder or a slot folder does not exist."""
    slots = trees.load_slots(SLOTS_FILE)
    commands = []
    for ide, product in IDES:
        folders = [entry["path"] for _, entry in sorted(slots.items()) if entry.get("product") == product]
        if not folders:
            raise ValueError(f"{SLOTS_FILE}: no slot of a {product} tree for {ide} "
                             f"(python3 -m common.trees slot <tree> makes one)")
        for folder in folders:
            if not os.path.isdir(folder):
                raise ValueError(f"the slot folder {folder} of {SLOTS_FILE} does not exist")
        commands.append(["env", f"BENCH_PLUGIN_ZIP={zip_file}", SCRIPT, "start", ide, *folders])
    return commands


def _ide_command(cmd: list[str], run) -> None:
    print(f"+ {shlex.join(cmd)}", flush=True)
    code = run(cmd)
    if code != 0:
        raise BuildError(f"{shlex.join(cmd)} failed with exit code {code}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m bench.build", description=__doc__, epilog=EXIT_CODES,
                                     formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    parser.add_argument("-start", action="store_true",
                        help="after the build, stop each benchmark IDE and start it with the zip and its slot folders")
    return parser


def main(argv: list[str] | None = None, run=_run) -> int:
    args = _parser().parse_args(argv)
    repo = settings.repo_root()
    try:
        version = version_of(repo)
        commands = start_commands(zip_path(version)) if args.start else []
    except ValueError as e:
        print(f"build: {e}", file=sys.stderr)
        return 2
    try:
        if not args.start:
            print(build(repo, version, run))
            return 0
        with ide_lock(f"bench.build -start {version}"):
            print(build(repo, version, run), flush=True)
            for (ide, _), start in zip(IDES, commands):
                _ide_command([SCRIPT, "stop", ide], run)
                _ide_command(start, run)
    except Busy as e:
        print(f"build: {e}; nothing was built or started", file=sys.stderr)
        return 2
    except BuildError as e:
        print(f"build: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
