"""The version pins of the live tests: a reference, with a low-effort check and no stop.

    python3 -m common.manifest machine      (run from live-test; prints the `ides` section of this machine)

`live-test/manifest.json` (PATH) holds the versions that a result depends on:

    {"ides": {"<Toolbox folder>": {"version": "2026.3", "build": "263.7307.211"}, ...},
     "agent": {"name": "claude-code", "version": "2.1.326"},
     "image": {"base": "ubuntu:24.04", "node": {"version", "sha256"}, "go": {"version", "sha256"},
               "uv": {"version", "sha256"}},
     "models": ["claude-haiku-5-5", "claude-opus-5-5"]}

The instruments use the IDEs of this machine. The manifest is only a reference: a difference between the manifest
and this machine prints a warning line, and no instrument stops, fails or changes its exit code for it.

- `ides`: the six fleet IDEs (`suite.fleet.IDES`), by their folder in the Toolbox apps folder (`settings.ide_apps()`,
  the variable BENCH_APPS). The benchmark IDEs (GoLand, PyCharm) use the same installs. To update the section, copy
  the output of the command `machine`.
- `agent`, `image`: the build arguments of the product image (`bench.images.build`; `bench/image/Dockerfile` has no
  version default). `image.base` names the base image; with a digest (`ubuntu:24.04@sha256:<digest>`, from
  `docker image inspect ubuntu:24.04 --format '{{index .RepoDigests 0}}'`) it pins one image. `node`, `go` and `uv`
  are the versions and the SHA-256 of the archives that the build downloads.
- `models`: the models of the tracked plans.

The manifest holds no plugin version (an instrument gets it from its option or from the IDE) and no product pin (the
product pins are in `live-test/real-products/products.json`).

`warn()` prints each line of `warnings(load(), machine_ides())` as `manifest: <text>`: an IDE of the manifest whose
version or build differs on this machine, or that this machine does not have. A manifest or an apps folder that it
cannot read gives one line. `warn` never raises. `runner batch`, the `run` commands of the audits and a live run of
the suite call it at their start.

`recorded(**extra)` is the record of one result: the pins of the manifest, `machine_ides` (the IDEs of this machine),
`repository` (`commit`: HEAD of the repository, `dirty`: a tracked file differs from HEAD) and the values of the
caller. `write(path, **extra)` writes it as JSON:
- `runner batch`: `<batch folder>/manifest.json` at each start, with `plugin`, `plan_models`, `image_ids`,
  `slots_root`, `login` and `questions` (see `bench.runner`). A later start of the batch writes it again with the
  values of that start: the record describes the last start.
- `audit.symbols run`: `<out>/manifest.json`; `audit.callers callers` and `dyn`: `<out without .jsonl>.manifest.json`
  next to the result file; `audit.verdict run`: one `<out>/manifest.json` for all its audits. Each has `plugin`
  and `files` (the SHA-256 of the key files and the calls files).

`recorded` and `write` never raise either: a value that they cannot read is `unknown (<error>)` or null, and a write
error prints one line.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

from common import settings
from suite import fleet

PATH = os.path.join(settings.live_test_root(), "manifest.json")


def load(path: str = PATH) -> dict:
    """The manifest. OSError when there is no file, ValueError when it is no JSON object."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: no JSON object")
    return data


def _is_fleet(data_directory: str) -> bool:
    """True for the `dataDirectoryName` of a fleet IDE: its selector and a version (as in `fleet.parse_ide_process`)."""
    return any(data_directory.startswith(ide.selector) and data_directory[len(ide.selector):][:1].isdigit()
               for ide in fleet.IDES.values())


def machine_ides(apps: str | None = None) -> dict:
    """{"<folder>": {"version", "build"}} of each fleet IDE in the apps folder (default `settings.ide_apps()`), from
    `<apps>/<folder>/product-info.json`. A folder with no readable file is left out; an apps folder that does not
    exist gives {}."""
    apps = settings.ide_apps() if apps is None else apps
    try:
        names = sorted(os.listdir(apps))
    except OSError:
        return {}
    found = {}
    for name in names:
        try:
            with open(os.path.join(apps, name, "product-info.json"), encoding="utf-8") as f:
                info = json.load(f)
            if _is_fleet(info["dataDirectoryName"]):
                found[name] = {"version": info["version"], "build": info["buildNumber"]}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return found


def warnings(tracked: dict, machine: dict) -> list[str]:
    """One line for each IDE of the manifest whose version or build differs on the machine, or that the machine
    does not have. An IDE of the machine that the manifest does not list gives no line."""
    lines = []
    for name, pin in sorted(tracked["ides"].items()):
        have = machine.get(name)
        if have is None:
            lines.append(f"{name}: {pin['version']} (build {pin['build']}) in the manifest, not on this machine")
        elif (have["version"], have["build"]) != (pin["version"], pin["build"]):
            lines.append(f"{name}: {pin['version']} (build {pin['build']}) in the manifest, {have['version']} "
                         f"(build {have['build']}) on this machine")
    return lines


def warn(out=None) -> None:
    """Print each warning as `manifest: <text>` to `out` (default: stderr). Never raises."""
    try:
        try:
            lines = warnings(load(PATH), machine_ides())
        except Exception as e:  # each problem of the check is one line, never a stop
            lines = [f"no check ({type(e).__name__}: {e})"]
        for line in lines:
            print(f"manifest: {line}", file=out or sys.stderr)
    except Exception:
        pass


def _git(*args: str) -> str:
    return subprocess.run(["git", "--no-optional-locks", "-C", settings.repo_root(), *args], capture_output=True,
                          text=True, check=True, timeout=60).stdout.strip()


def repository() -> dict:
    """{"commit": HEAD, "dirty": a tracked file differs from HEAD}; null values when git gives no answer."""
    try:
        return {"commit": _git("rev-parse", "HEAD"), "dirty": bool(_git("status", "--porcelain", "-uno"))}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def recorded(**extra) -> dict:
    """The pins of the manifest, the values of this machine and `extra` (module text). Never raises."""
    try:
        record = load(PATH)
    except Exception as e:
        record = {"manifest_error": f"{type(e).__name__}: {e}"}
    try:
        record["machine_ides"] = machine_ides()
    except Exception as e:
        record["machine_ides"] = f"unknown ({type(e).__name__}: {e})"
    record["repository"] = repository()
    record.update(extra)
    return record


def file_sha256(path: str) -> str | None:
    """The SHA-256 of a file; None when it cannot be read."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def write(path: str, **extra) -> None:
    """Write `recorded(**extra)` to `path`. Never raises: a write error prints one line."""
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(recorded(**extra), f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(path + ".tmp", path)
    except Exception as e:
        try:
            print(f"manifest: cannot write {path} ({type(e).__name__}: {e})", file=sys.stderr)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m common.manifest", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("machine", help="print the ides section of this machine (the fleet IDEs of the apps folder)")
    parser.parse_args(argv)
    print(json.dumps(machine_ides(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
