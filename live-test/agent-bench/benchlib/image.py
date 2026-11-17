"""Product images of the agent benchmark and their gate.

    python3 -m benchlib.image build <caddy|beets>      (run from live-test/agent-bench)
    python3 -m benchlib.image gate <caddy|beets>

`build` makes the build context in BENCH/scratch/image-ctx/<product>/: image/Dockerfile, image/entry.sh,
`aids/` (the skill folder of the plugin and `rule.txt`) and `ws/<slot id>/<product>/` for the product tree
and its three plant trees, at their slot paths of `trees.load_slots()` (below `trees.SLOTS_ROOT`). A context
tree has the files of the master manifest BENCH/trees/<tree>.manifest minus the agent instruction files of
the product and minus `.idea`, `.venv` and `.git` (see `left_out`), and each copied file has the hash of the
manifest. Then it builds the image idesense-bench-<product>:p2 (image/Dockerfile makes a new repository with
one commit in each tree and warms the caches) and writes BENCH/images/<product>.json with the fields
`image`, `id`, `built`, `claude_version`, `go_version` (caddy) or `python_version` and `uv_version` (beets),
`server_name`, `trees` and `slots` (`{"<tree>": {"slot": "<id>", "path": "<slot path>"}}`).

`gate` starts containers with the container flags of a run (no API key) and prints one line with PASS or
FAIL for each check. It exits 0 only when each check passes. The test output of each tree goes to
BENCH/scratch/image-gate/<product>/<tree>-tests.log.
"""
import datetime
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys

from benchlib import trees

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE_SRC = os.path.normpath(os.path.join(HERE, "..", "image"))
SKILL_SRC = os.path.join(trees.WT, "src", "main", "resources", "skill", "idesense")
CTX_ROOT = os.path.join(trees.BENCH, "scratch", "image-ctx")
GATE_LOGS = os.path.join(trees.BENCH, "scratch", "image-gate")
IMAGES = os.path.join(trees.BENCH, "images")
INIT_IN_IMAGE = "/home/ubuntu/.init"
ENTRY_IN_IMAGE = INIT_IN_IMAGE + "/entry.sh"
GO_MODULE_CACHE = "/home/ubuntu/go/pkg/mod"
CLAUDE_CODE_VERSION = "2.1.326"

# product -> `serverName` of the IDE of the product (IdeProductInfo.IdeProduct GOLAND and PYCHARM).
SERVER_NAMES = {"caddy": "goland-idesense", "beets": "pycharm-idesense"}
# McpToolWindowPanel.getAgentRuleText, with `serverName` of the IDE.
RULE = "IMPORTANT: When applicable, prefer using {server} MCP tools for code navigation and refactoring."

# The container flags of each run (plan, Global Constraints).
CONTAINER_FLAGS = ["--rm", "--user", "1000:1000", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--memory", "6g", "--cpus", "4", "--pids-limit", "1024", "--network", "bridge"]

LEFT_OUT_NAMES = {"CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules"}
LEFT_OUT_DIRS = {".claude", ".cursor", ".idea", ".venv", ".git"}
LEFT_OUT_PATHS = {".github/copilot-instructions.md"}
LANGUAGE_SERVERS = ("gopls", "pyright", "pylsp", "jedi-language-server", "rust-analyzer")
INSTRUCTION_NAMES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules", ".claude", ".cursor", ".idea")
LEAK_WORDS = ("bench", "plant", "idesense")

# The baseline test commands of docs/reviews/real-products/_bench/baselines.md, with the XDG folders below /tmp.
XDG = "XDG_CONFIG_HOME=/tmp/xdg/config XDG_DATA_HOME=/tmp/xdg/data"
TEST_COMMANDS = {
    "caddy": f"{XDG} go test -count=1 -p 1 ./...",
    "beets": ".venv/bin/python -m pytest -q --no-header",
}
# caddy: the host result. A package that fails runs one more time in the same container (so with the
# caddy storage of the first run); when it passes then, it counts as `ok`. The flaky product test
# TestReverseProxySNIPlaceHolder fails mostly when its local CA storage is new (see the task 3 record).
CADDY_EXPECTED = {"ok": 30, "FAIL": 0}
# beets: the image baseline. The host gives 2680 passed, 1 failed, 164 skipped. The image has 15 more skips:
# 13 tests need `ffprobe` (test_embedart 2, test_importer 11), 1 test needs `libgio-2.0` (test_thumbnails),
# and test_completion needs the bash completion script (it fails on the host and skips in the image).
BEETS_EXPECTED = {"passed": 2666, "failed": 0, "skipped": 179, "errors": 0}
BEETS_HOST = "2680 / 1 / 164"
COMMIT = "dev <dev@localhost> 2026-01-01T00:00:00+00:00 dev <dev@localhost> 2026-01-01T00:00:00+00:00 Initial commit"

# The stand-in for `claude` in the gate: the entry script starts it in place of `claude`, and it reports
# the state that `claude` would see. Each section starts with a line `== <name>`.
_LEAK_TESTS = " -o ".join(f"-iname '*{word}*'" for word in LEAK_WORDS)
STAND_IN = f"""#!/bin/bash
echo "== env"
compgen -e | grep '^BENCH' || true
echo "== config"
compgen -e | grep -x CLAUDE_CONFIG_DIR || true
ls -A /home/ubuntu | grep '^\\.claude' || true
echo "== pwd"
pwd -P
echo "== slots"
ls -A {trees.SLOTS_ROOT}
echo "== init"
ls -d {INIT_IN_IMAGE} 2>/dev/null || true
echo "== names"
find /home /opt /tmp \\( -path "$(pwd -P)" -o -path {GO_MODULE_CACHE} \\) -prune -o -type d \\
  \\( {_LEAK_TESTS} \\) -print 2>/dev/null
echo "== aid"
if [ -d .claude ]; then find .claude -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum; fi
if [ -e CLAUDE.md ]; then cat CLAUDE.md; fi
echo "== status"
git status --porcelain
"""


def image_name(product: str) -> str:
    return f"idesense-bench-{product}:p2"


def tree_names(product: str) -> list[str]:
    return [product] + [f"{product}-plant-{n}" for n in (1, 2, 3)]


def rule_text(server: str) -> str:
    return RULE.format(server=server)


def image_slots(product: str, slots: dict | None = None) -> dict:
    """{"<tree>": {"slot": "<id>", "path": "<slot path>"}} for the 4 trees of the product, from `slots`
    (default `trees.load_slots()`). Raise RuntimeError for a tree with no slot or with another path form."""
    slots = trees.load_slots() if slots is None else slots
    found = {}
    for tree in tree_names(product):
        entry = slots.get(tree)
        if not entry:
            raise RuntimeError(f"{tree} has no slot in {trees.SLOTS_FILE}")
        if entry["path"] != f"{trees.SLOTS_ROOT}/{entry['slot']}/{product}":
            raise RuntimeError(f"{tree}: the slot path {entry['path']} is not {trees.SLOTS_ROOT}/<slot id>/{product}")
        found[tree] = {"slot": entry["slot"], "path": entry["path"]}
    return found


def left_out(rel: str) -> bool:
    """True for a path (relative to the tree root) that the image leaves out."""
    parts = rel.split("/")
    return rel in LEFT_OUT_PATHS or parts[-1] in LEFT_OUT_NAMES or any(p in LEFT_OUT_DIRS for p in parts[:-1])


def _manifest_paths(manifest: str) -> list[str]:
    with open(manifest, encoding="utf-8", errors="surrogateescape", newline="\n") as f:
        return [line.rstrip("\n").split("  ", 1)[1] for line in f]


def copy_context_tree(tree: str, manifest: str, dst: str) -> list[str]:
    """Copy the files of the manifest that are not left out from tree to dst; return their paths. Raise
    RuntimeError when a copied file has another hash than the manifest."""
    files = [rel for rel in _manifest_paths(manifest) if not left_out(rel)]
    trees.copy_tree(tree, dst, files)
    differ = [rel for rel in trees.verify_manifest(dst, manifest) if not left_out(rel)]
    if differ:
        raise RuntimeError(f"{dst}: {len(differ)} files differ from {manifest}, for example {differ[0]}")
    return files


def write_aids(dst: str, server: str) -> None:
    """Write dst/skill/idesense/ (a copy of the skill folder of the plugin) and dst/rule.txt (one line)."""
    shutil.copytree(SKILL_SRC, os.path.join(dst, "skill", "idesense"))
    with open(os.path.join(dst, "rule.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(rule_text(server) + "\n")


def make_context(product: str, ctx: str | None = None, trees_root: str = trees.TREES,
                 slots: dict | None = None) -> str:
    """Make the build context of the product (a new folder) and return its path. Each tree goes to
    ws/<slot id>/<product>/, from the master tree and the master manifest below trees_root."""
    ctx = ctx or os.path.join(CTX_ROOT, product)
    if os.path.lexists(ctx):
        shutil.rmtree(ctx)
    os.makedirs(ctx)
    for name in ("Dockerfile", "entry.sh"):
        shutil.copy2(os.path.join(IMAGE_SRC, name), ctx)
    write_aids(os.path.join(ctx, "aids"), SERVER_NAMES[product])
    for tree, entry in image_slots(product, slots).items():
        copy_context_tree(os.path.join(trees_root, tree), os.path.join(trees_root, tree + ".manifest"),
                          os.path.join(ctx, "ws", entry["slot"], product))
    return ctx


_container_seq = itertools.count(1)


def run_container(image: str, args: list[str], env: dict[str, str] | None = None, entrypoint: str | None = None,
                  timeout: float = 120, stdin: str | None = None) -> subprocess.CompletedProcess:
    """Run one container with the container flags; on a timeout kill it and return the exit code 124."""
    name = f"idesense-bench-gate-{os.getpid()}-{next(_container_seq)}"
    cmd = ["docker", "run", "--name", name, *CONTAINER_FLAGS]
    if stdin is not None:
        cmd.append("-i")
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    if entrypoint:
        cmd += ["--entrypoint", entrypoint]
    cmd += [image, *args]
    try:
        return subprocess.run(cmd, input=stdin, capture_output=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True)
        return subprocess.CompletedProcess(cmd, 124, "", f"timeout after {timeout} s")


def bash(image: str, script: str, env: dict[str, str] | None = None,
         timeout: float = 120) -> subprocess.CompletedProcess:
    return run_container(image, ["-c", script], env, "/bin/bash", timeout)


def _first_line(text: str) -> str:
    return (text.strip().splitlines() or [""])[0]


def build(product: str) -> dict:
    slots = image_slots(product)
    ctx = make_context(product, slots=slots)
    name = image_name(product)
    subprocess.run(["docker", "build", "--progress=plain", "--build-arg", f"PRODUCT={product}", "-t", name, ctx],
                   check=True)
    image_id = subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", name], check=True,
                              capture_output=True, text=True).stdout.strip()

    def version(binary: str, *args: str) -> str:
        result = run_container(name, list(args), entrypoint=binary)
        if result.returncode != 0:
            raise RuntimeError(f"{binary} {' '.join(args)}: exit {result.returncode}: {result.stderr.strip()}")
        return _first_line(result.stdout)

    record = {
        "image": name,
        "id": image_id,
        "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "claude_version": version("claude", "--version").split()[0],
    }
    if product == "caddy":
        record["go_version"] = version("go", "version").split()[2].removeprefix("go")
    else:
        record["python_version"] = version("python3", "--version").split()[1]
        record["uv_version"] = version("uv", "--version").split()[1]
    record["server_name"] = SERVER_NAMES[product]
    record["trees"] = tree_names(product)
    record["slots"] = slots

    os.makedirs(IMAGES, exist_ok=True)
    path = os.path.join(IMAGES, product + ".json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
        f.write("\n")
    os.replace(path + ".tmp", path)
    return record


def go_test_counts(out: str) -> dict[str, int]:
    """The count of the package lines `ok` and `FAIL` in the output of `go test`."""
    return {"ok": len(re.findall(r"^ok[ \t]+\S", out, re.M)),
            "FAIL": len(re.findall(r"^FAIL[ \t]+\S", out, re.M))}


def go_failed_packages(out: str) -> list[tuple[str, list[str]]]:
    """[(package, [top-level failed tests])] for each `FAIL <package>` line of `go test -p 1` output."""
    failed, tests = [], []
    for line in out.splitlines():
        m = re.match(r"--- FAIL: (\S+)", line)
        if m:
            tests.append(m.group(1))
            continue
        m = re.match(r"(ok|FAIL|\?)[ \t]+(\S+)", line)
        if m:
            if m.group(1) == "FAIL":
                failed.append((m.group(2), tests))
            tests = []
    return failed


def caddy_gate_run(path: str) -> str:
    """The caddy test script of the gate: the baseline command in path, then each failed package one more
    time in the same container; `split_caddy_run` reads its output."""
    return f"""cd {path}
{XDG} go test -count=1 -p 1 ./... > /tmp/first.log 2>&1
rc=$?
cat /tmp/first.log
echo "@@gate rc $rc"
for p in $(grep -E '^FAIL[[:space:]]+[^[:space:]]' /tmp/first.log | awk '{{print $2}}'); do
  echo "@@gate rerun $p"
  {XDG} go test -count=1 -p 1 "$p" 2>&1
  echo "@@gate rerun-rc $?"
done
"""


def split_caddy_run(out: str) -> tuple[str, int, list[tuple[str, str, int]]]:
    """Split the output of CADDY_GATE_RUN: (first output, first exit code, [(package, output, exit code)])."""
    first, _, rest = out.partition("@@gate rc ")
    rc_text, _, rest = rest.partition("\n")
    reruns = []
    for block in rest.split("@@gate rerun ")[1:]:
        package, _, body = block.partition("\n")
        text, sep, rc = body.rpartition("@@gate rerun-rc ")
        if sep:
            reruns.append((package.strip(), text, int(rc.strip())))
        else:
            reruns.append((package.strip(), body, 1))
    return first, int(rc_text.strip()) if rc_text.strip().isdigit() else 1, reruns


def caddy_tests_result(out: str, returncode: int, expected: dict[str, int] = CADDY_EXPECTED) -> tuple[bool, str]:
    """(PASS?, detail) for the output of `caddy_gate_run`. A failed package whose rerun passes counts as `ok`
    and is named as a flake; a package that fails two times is a FAIL."""
    first, first_rc, reruns = split_caddy_run(out)
    counts, failed = go_test_counts(first), go_failed_packages(first)
    again = {package: (text, rc) for package, text, rc in reruns}
    ok_count, flakes, hard = counts["ok"], [], []
    for package, tests in failed:
        text, rc = again.get(package, ("", 1))
        if rc == 0 and go_test_counts(text) == {"ok": 1, "FAIL": 0}:
            ok_count += 1
            flakes.append(f"{package}, {', '.join(tests)}")
        else:
            hard.append(f"{package}, {', '.join(tests)}")
    final = {"ok": ok_count, "FAIL": len(hard)}
    detail = (f"exit {first_rc}, {final['ok']} ok, {final['FAIL']} FAIL "
              f"(expected {expected['ok']} ok, {expected['FAIL']} FAIL)"
              + (f"; first run {counts['ok']} ok, {counts['FAIL']} FAIL" if failed else "")
              + "".join(f" (flake: {f})" for f in flakes)
              + "".join(f" (failed two times: {h})" for h in hard))
    return returncode == 0 and final == expected and (first_rc == 0 or bool(failed)), detail


def pytest_counts(out: str) -> dict[str, int] | None:
    """passed, failed, skipped and errors from the last summary line of pytest; None with no summary line."""
    for line in reversed(out.splitlines()):
        line = line.strip(" =")
        if not re.search(r" in [0-9.]+s\b", line):
            continue
        found = re.findall(r"(\d+) (passed|failed|skipped|errors?)\b", line)
        if not found:
            continue
        counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        for n, word in found:
            counts["errors" if word.startswith("error") else word] += int(n)
        return counts
    return None


def pytest_failed(out: str) -> list[str]:
    """The test ids of the `FAILED` lines of the pytest summary."""
    return [line[len("FAILED "):].split(" - ", 1)[0] for line in out.splitlines() if line.startswith("FAILED ")]


def _skill_listing(prefix: str) -> list[str]:
    """`sha256sum` lines for the files of the skill folder, below prefix, sorted by path."""
    lines = []
    for dirpath, _, names in os.walk(SKILL_SRC):
        for name in names:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            lines.append((f"{prefix}/{os.path.relpath(path, SKILL_SRC)}", digest))
    return [f"{digest}  {path}" for path, digest in sorted(lines)]


def _sections(text: str) -> dict[str, list[str]]:
    found, current = {}, None
    for line in text.splitlines():
        if line.startswith("== "):
            current = line[3:]
            found[current] = []
        elif current is not None:
            found[current].append(line)
    return found


def _after_entry(image: str, slot: str, aid: str) -> tuple[int, dict[str, list[str]]]:
    """Run the entry script with the stand-in for `claude` first on PATH; return the exit code and the
    sections of the report of the stand-in."""
    r = run_container(image, ["-c", f"mkdir /tmp/x && cat > /tmp/x/claude && chmod 755 /tmp/x/claude && "
                                    f"export PATH=/tmp/x:$PATH && exec {ENTRY_IN_IMAGE} --version"],
                      env={"BENCH_SLOT": slot, "BENCH_AID": aid}, entrypoint="/bin/bash", stdin=STAND_IN)
    return r.returncode, _sections(r.stdout)


def gate(product: str) -> int:
    name = image_name(product)
    slots = image_slots(product)
    results = []

    def check(label: str, ok: bool, detail: str) -> None:
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {label}  {detail}", flush=True)

    logs = os.path.join(GATE_LOGS, product)
    os.makedirs(logs, exist_ok=True)
    for tree in tree_names(product):
        path = slots[tree]["path"]
        if product == "caddy":
            r = bash(name, caddy_gate_run(path), timeout=2400)
        else:
            r = bash(name, f"cd {path} && {TEST_COMMANDS[product]}", timeout=1200)
        with open(os.path.join(logs, f"{tree}-tests.log"), "w", encoding="utf-8") as f:
            f.write(r.stdout + r.stderr)
        if product == "caddy":
            ok, detail = caddy_tests_result(r.stdout, r.returncode)
            check(f"tests {tree}", ok, detail)
        else:
            counts = pytest_counts(r.stdout)
            got = ", ".join(f"{v} {k}" for k, v in counts.items()) if counts else "no summary line"
            failed = pytest_failed(r.stdout)
            check(f"tests {tree}", counts == BEETS_EXPECTED,
                  f"exit {r.returncode}, {got} (image baseline 2666 / 0 / 179 / 0; host: {BEETS_HOST})"
                  + (f"; failed: {', '.join(failed)}" if failed else ""))

    r = run_container(name, ["--version"], env={"BENCH_SLOT": slots[product]["slot"]})
    check("claude --version", r.returncode == 0 and r.stdout.split()[:1] == [CLAUDE_CODE_VERSION],
          f"exit {r.returncode}, {_first_line(r.stdout or r.stderr)!r} (through the entry point)")

    r = bash(name, "id -u")
    check("id -u", r.stdout.strip() == "1000", repr(r.stdout.strip()))

    venv_bins = ":".join(f"{e['path']}/.venv/bin" for e in slots.values())
    r = bash(name, f"PATH=\"$PATH:{venv_bins}\"; for p in {' '.join(LANGUAGE_SERVERS)}; do command -v \"$p\"; done; "
                   "true")
    check("no language server", r.returncode == 0 and not r.stdout.strip(),
          f"{', '.join(LANGUAGE_SERVERS)} on PATH and in .venv/bin: {r.stdout.split() or 'none'}")

    r = bash(name, f"ls -d {trees.BENCH} 2>/dev/null; ls -A {trees.SLOTS_ROOT}")
    found = r.stdout.split()
    expected_slots = sorted(e["slot"] for e in slots.values())
    check("folders", r.returncode == 0 and sorted(found) == expected_slots,
          f"no {trees.BENCH} (so no keys): {trees.BENCH not in found}; slot folders {sorted(found)}")

    find_names = " -o ".join(f"-name {n}" for n in INSTRUCTION_NAMES)
    for tree in tree_names(product):
        path = slots[tree]["path"]
        r = bash(name, f"find {path} \\( {find_names} \\) -print; "
                       f"if [ -e {path}/.github/copilot-instructions.md ]; then echo {path}/.github/copilot-instructions.md; fi")
        check(f"no instruction file {tree}", r.returncode == 0 and not r.stdout.strip(),
              f"found: {r.stdout.split() or 'none'}")

    for tree in tree_names(product):
        r = bash(name, f"cd {slots[tree]['path']} && git rev-list --count HEAD && "
                       "git log -1 --format='%an <%ae> %aI %cn <%ce> %cI %s' && git status --porcelain")
        lines = r.stdout.splitlines()
        commits, commit, status = lines[0:1], lines[1:2], lines[2:]
        check(f"git {tree}", r.returncode == 0 and commits == ["1"] and commit == [COMMIT] and not status,
              f"commits {commits}, {commit}, git status lines {len(status)}")

    aid_files = {"none": [], "skill": _skill_listing(".claude/skills/idesense"),
                 "rule": [rule_text(SERVER_NAMES[product])]}
    for tree in tree_names(product):
        slot, path = slots[tree]["slot"], slots[tree]["path"]
        runs = {aid: _after_entry(name, slot, aid) for aid in aid_files}

        def every(test) -> bool:
            return all(rc == 0 and test(s) for rc, s in runs.values())

        env = sorted({v for _, s in runs.values() for v in s.get("env", [])})
        check(f"entry {tree}: no BENCH variable", every(lambda s: s.get("env") == []),
              f"exit codes {[rc for rc, _ in runs.values()]}, BENCH names: {env or 'none'} (aids none, skill, rule)")
        config = sorted({v for _, s in runs.values() for v in s.get("config", [])})
        check(f"entry {tree}: no Claude Code config", every(lambda s: s.get("config") == []),
              f"CLAUDE_CONFIG_DIR and ~/.claude*: {config or 'none'}")
        pwds = sorted({" ".join(s.get("pwd", [])) for _, s in runs.values()})
        check(f"entry {tree}: tree path is the host slot path", every(lambda s: s.get("pwd") == [path]),
              f"{pwds} (slots.json: {path})")
        left = sorted({" ".join(s.get("slots", [])) for _, s in runs.values()})
        check(f"entry {tree}: one slot folder left, {INIT_IN_IMAGE} removed",
              every(lambda s: s.get("slots") == [slot] and s.get("init") == []), f"slot folders {left}")
        names = sorted({v for _, s in runs.values() for v in s.get("names", [])})
        check(f"entry {tree}: no folder name with {', '.join(LEAK_WORDS)}", every(lambda s: s.get("names") == []),
              f"below /home, /opt, /tmp (not in the tree, not in {GO_MODULE_CACHE}): {names or 'none'}")
        for aid, expected in aid_files.items():
            rc, s = runs[aid]
            check(f"aid {aid} {tree}", rc == 0 and s.get("aid") == expected and s.get("status") == [],
                  f"files as expected: {s.get('aid') == expected}, git status lines {len(s.get('status', []))}")

    failed = results.count(False)
    print(f"gate {product}: {len(results)} checks, {failed} FAIL", flush=True)
    return 0 if failed == 0 else 1


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("build", "gate") or argv[1] not in SERVER_NAMES:
        print("usage: python3 -m benchlib.image build <caddy|beets> | gate <caddy|beets>", file=sys.stderr)
        return 2
    command, product = argv
    if command == "build":
        print(json.dumps(build(product), indent=2))
        return 0
    return gate(product)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
