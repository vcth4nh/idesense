"""The fleet IDEs of the live-test harness.

Which IDE serves which language, which process is the fleet instance of an
IDE, and which projects that IDE opens at its next start. Linux only (/proc).
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Ide:
    key: str
    port: int
    selector: str  # -Didea.paths.selector without the version, e.g. "GoLand"
    launcher: str  # script in <app>/bin
    languages: tuple[str, ...]


IDES: dict[str, Ide] = {
    ide.key: ide
    for ide in (
        Ide("intellij", 29170, "IntelliJIdea", "idea.sh", ("java", "kotlin")),
        Ide("pycharm", 29172, "PyCharm", "pycharm.sh", ("python",)),
        Ide("webstorm", 29173, "WebStorm", "webstorm.sh", ("javascript", "typescript")),
        Ide("goland", 29174, "GoLand", "goland.sh", ("go",)),
        Ide("phpstorm", 29175, "PhpStorm", "phpstorm.sh", ("php",)),
        Ide("rustrover", 29178, "RustRover", "rustrover.sh", ("rust",)),
    )
}

PORT_BY_LANG: dict[str, int] = {lang: ide.port for ide in IDES.values() for lang in ide.languages}


def ide_url(ide: Ide) -> str:
    return f"http://127.0.0.1:{ide.port}/mcp/streamable-http"


@dataclass(frozen=True)
class IdeProcess:
    pid: int
    launcher: Path
    config_dir: Path
    env: dict[str, str]
    cwd: str


def parse_ide_process(ide: Ide, pid: int, cmdline: list[str], exe: str, environ: bytes,
                      cwd: str, user_home: str) -> IdeProcess | None:
    """The fleet instance of `ide`, or None when the process is something else.

    The fleet instance runs `serverMode` with the default configuration folder;
    a project path can follow `serverMode`. A throwaway instance with its own
    -Didea.config.path is not the fleet.
    """
    prefix = f"-Didea.paths.selector={ide.selector}"
    selector = next((a.split("=", 1)[1] for a in cmdline
                     if a.startswith(prefix) and a[len(prefix):len(prefix) + 1].isdigit()), None)
    if selector is None or "serverMode" not in cmdline:
        return None
    if any(a.startswith("-Didea.config.path=") for a in cmdline):
        return None
    env = dict(item.split("=", 1) for item in os.fsdecode(environ).split("\0") if "=" in item)
    return IdeProcess(pid, Path(exe).parents[2] / "bin" / ide.launcher,
                      Path(user_home) / ".config" / "JetBrains" / selector, env, cwd)


def find_ide_process(ide: Ide) -> IdeProcess | None:
    """The running fleet instance of `ide`, or None when it is not up."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = os.fsdecode((entry / "cmdline").read_bytes().rstrip(b"\0")).split("\0")
            proc = parse_ide_process(ide, int(entry.name), cmdline, os.readlink(entry / "exe"),
                                     (entry / "environ").read_bytes(), os.readlink(entry / "cwd"),
                                     str(Path.home()))
        except OSError:
            continue  # the process ended, or it belongs to another user
        if proc is not None:
            found.append(proc)
    if len(found) > 1:
        raise RuntimeError(f"{len(found)} {ide.key} fleet processes run: pids {[p.pid for p in found]}")
    return found[0] if found else None


def rewrite_recent_projects(xml_text: str, wanted: list[str], user_home: str) -> str:
    """Return recentProjects.xml with exactly the `wanted` project paths marked as open.

    A bare `<ide>.sh serverMode` start opens every project whose entry has
    opened="true". Write the result only while the IDE is down.
    """
    root = ET.fromstring(xml_text)
    projects = root.find(".//option[@name='additionalInfo']/map")
    if projects is None:
        raise ValueError("no project map (option 'additionalInfo')")
    missing = list(wanted)
    for entry in projects.findall("entry"):
        meta = entry.find("value/RecentProjectMetaInfo")
        if meta is None:
            continue
        path = entry.get("key", "").replace("$USER_HOME$", user_home)
        if path in missing:
            missing.remove(path)
            meta.set("opened", "true")
        else:
            meta.attrib.pop("opened", None)
    for path in missing:
        key = "$USER_HOME$" + path[len(user_home):] if path.startswith(user_home + "/") else path
        value = ET.SubElement(ET.SubElement(projects, "entry", {"key": key}), "value")
        ET.SubElement(value, "RecentProjectMetaInfo", {"opened": "true"})
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


_PROBE_PATH = "/nonexistent/idesense-open-projects-probe"


def open_projects(url: str, post) -> list[str] | None:
    """The project paths that the IDE has open, or None when the server does not answer.

    The server lists its open projects in the error payload of a call that
    names an unknown project. `post` has the signature of run.post_jsonrpc.
    An entry with a "workspace" key is a module folder of a project, not a
    project (ProjectResolver.kt, collectAvailableProjectEntries).
    """
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "ide_index_status", "arguments": {"project_path": _PROBE_PATH}}}
    result = post(url, request, timeout=5.0)
    if not isinstance(result, dict) or "transport_error" in result or "jsonrpc_error" in result:
        return None
    return [p["path"] for p in result.get("available_projects", []) if "workspace" not in p]


def _stop(proc: IdeProcess, timeout: float, key: str) -> str | None:
    """SIGTERM, then wait until the process is gone. Never SIGKILL: the IDE must save its state."""
    try:
        os.kill(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return None
    deadline = time.monotonic() + timeout
    while Path(f"/proc/{proc.pid}").exists():
        if time.monotonic() >= deadline:
            return f"{key} did not stop in {timeout:.0f} s"
        time.sleep(0.2)
    return None


def _start(proc: IdeProcess) -> None:
    """Start the IDE as it ran before: same launcher, environment and working directory.

    `setsid --fork` makes the IDE a child of init, not of this harness. A child
    of the harness would stay in /proc as a zombie after its end, and a later
    `_stop` in the same harness run would wait for it until the timeout.
    """
    subprocess.run(["setsid", "--fork", str(proc.launcher), "serverMode"], cwd=proc.cwd, env=proc.env, check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def set_open_projects(ide: Ide, wanted: list[str], post, url: str | None = None, log=print,
                      stop_timeout: float = 90.0, start_timeout: float = 300.0) -> str | None:
    """Make `wanted` the open projects of the IDE. None on success, else one error line.

    The plugin has no tool that opens or closes a project, so a change is a
    restart: stop the IDE, mark the wanted projects in recentProjects.xml,
    start the IDE, and wait until the server lists exactly those projects.
    """
    url = url or ide_url(ide)
    now = open_projects(url, post)
    if now is None:
        return f"cannot reach {url}: start the IDE first"
    if set(now) == set(wanted):
        return None
    proc = find_ide_process(ide)
    if proc is None:
        return f"no {ide.key} fleet process found"
    recent = proc.config_dir / "options" / "recentProjects.xml"
    home = proc.env.get("HOME") or str(Path.home())
    try:
        # Prove the rewrite while the IDE still runs: an error after the stop would leave the IDE down.
        rewrite_recent_projects(recent.read_text(), wanted, home)
    except (OSError, ET.ParseError, ValueError) as e:
        return f"cannot rewrite {recent}: {e}"
    command = f"{proc.launcher} serverMode"
    log(f"[{ide.key}] restart for a project switch. Start command: {command}")
    err = _stop(proc, stop_timeout, ide.key)
    if err is not None:
        return err
    tmp = recent.with_name(f".{recent.name}.tmp.{os.getpid()}")
    tmp.write_text(rewrite_recent_projects(recent.read_text(), wanted, home))
    os.replace(tmp, recent)
    _start(proc)
    deadline = time.monotonic() + start_timeout
    while True:
        now = open_projects(url, post)
        if now is not None and set(now) == set(wanted):
            return None
        if time.monotonic() >= deadline:
            return (f"{ide.key} did not open {wanted} in {start_timeout:.0f} s (open now: {now}). "
                    f"Start command: {command}")
        time.sleep(5)
