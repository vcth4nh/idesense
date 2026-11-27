"""The fleet IDEs of the live-test harness.

Which IDE serves which language, which process is the fleet instance of an
IDE, and which projects that IDE opens at its next start. Linux only (/proc).
"""
from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


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
    log_dir: Path
    env: dict[str, str]
    cwd: str


def parse_ide_process(ide: Ide, pid: int, cmdline: list[str], exe: str, environ: bytes,
                      cwd: str, user_home: str) -> IdeProcess | None:
    """The fleet instance of `ide`, or None when the process is something else.

    The fleet instance runs `serverMode` with the default configuration folder;
    a project path can follow `serverMode`. A throwaway instance with its own
    -Didea.config.path is not the fleet. The log folder is the default too.
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
                      Path(user_home) / ".config" / "JetBrains" / selector,
                      Path(user_home) / ".cache" / "JetBrains" / selector / "log", env, cwd)


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


def trust_project_paths(xml_text: str | None, paths: list[str], user_home: str) -> str:
    """Return trusted-paths.xml with an explicit trust entry for each of the `paths`.

    A `serverMode` IDE is not headless, so it checks the trust of a project
    (TrustedProjects.isTrustedCheckDisabled). `None` is a file that does not
    exist. Write the result only while the IDE is down.
    """
    root = ET.Element("application") if xml_text is None else ET.fromstring(xml_text)
    component = root.find("component[@name='Trusted.Paths']")
    if component is None:
        component = ET.SubElement(root, "component", {"name": "Trusted.Paths"})
    option = component.find("option[@name='TRUSTED_PROJECT_PATHS']")
    if option is None:
        option = ET.SubElement(component, "option", {"name": "TRUSTED_PROJECT_PATHS"})
    entries = option.find("map")
    if entries is None:
        entries = ET.SubElement(option, "map")
    for path in paths:
        entry = next((e for e in entries.findall("entry")
                      if e.get("key", "").replace("$USER_HOME$", user_home) == path), None)
        if entry is None:
            key = "$USER_HOME$" + path[len(user_home):] if path.startswith(user_home + "/") else path
            entry = ET.SubElement(entries, "entry", {"key": key})
        entry.set("value", "true")
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


# A switch waits at least (QUIET_ANSWERS - 1) * QUIET_POLL_S seconds before the stop.
QUIET_ANSWERS = 5
QUIET_POLL_S = 5.0
QUIET_TIMEOUT_S = 900.0


def wait_until_quiet(url: str, post, answers: int = QUIET_ANSWERS, poll_s: float = QUIET_POLL_S,
                     timeout_s: float = QUIET_TIMEOUT_S, sleep=time.sleep,
                     clock=time.monotonic) -> tuple[str | None, float]:
    """Wait until `answers` answers of ide_index_status in a row say isDumbMode false.

    A stop while the IDE indexes can damage its index (#308). The IDE leaves dumb mode
    and enters it again between the passes of an open, so one answer is not enough.
    Each other answer (dumb mode, an error, no answer of the server) sets the count back
    to 0. The call names no project: with several projects open, the top-level
    isDumbMode is then true when one project indexes (JsonRpcHandler.kt, AllProjectsTool).
    Returns (an error line or None, the seconds waited)."""
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "ide_index_status", "arguments": {}}}
    start = clock()
    count = 0
    while True:
        result = post(url, request, timeout=5.0)
        count = count + 1 if isinstance(result, dict) and result.get("isDumbMode") is False else 0
        waited = clock() - start
        if count >= answers:
            return None, waited
        if waited >= timeout_s:
            return (f"no {answers} answers of ide_index_status in a row with isDumbMode false "
                    f"in {timeout_s:.0f} s (last answer: {result})"), waited
        sleep(poll_s)


_REBUILD_REQUEST = "Requesting index rebuild for: "


def index_rebuild_requests(log_file: Path, offset: int) -> list[str]:
    """The index names of the lines "Requesting index rebuild for: <name>" after byte `offset` of `log_file`.

    Each name comes one time, in the order of its first line. A file that is now smaller
    than `offset` is a new file (the IDE moves a full idea.log to idea.1.log), so the scan
    reads it from its start. A file that does not exist or cannot be read gives []."""
    try:
        with log_file.open("rb") as f:
            f.seek(offset if f.seek(0, os.SEEK_END) >= offset else 0)
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    names = [line.partition(_REBUILD_REQUEST)[2].strip()
             for line in text.splitlines() if _REBUILD_REQUEST in line]
    return list(dict.fromkeys(names))


# The process name of a child that the IDE starts on Linux to watch the colour scheme of the desktop.
# The child does not end with the IDE: it runs on with a new parent, so each stop would leave one.
_LEFTOVER_CHILD = "dbus-monitor"


def _stat(pid: int) -> tuple[str, int, int] | None:
    """The process name, the parent PID and the start time of a process, or None when it is gone.

    The name can hold spaces and brackets, so the fields of /proc/<pid>/stat start after the last
    ')'. The start time is field 22. A line of another form also gives None: this is a helper of a
    cleanup, and an exception in `_stop` would leave the IDE stopped."""
    try:
        text = os.fsdecode(Path(f"/proc/{pid}/stat").read_bytes())
        head, _, rest = text.rpartition(")")
        fields = rest.split()
        return head.partition("(")[2], int(fields[1]), int(fields[19])
    except (OSError, ValueError, IndexError):
        return None


def _leftover_children(pid: int) -> list[tuple[int, int]]:
    """The PID and the start time of each direct child of `pid` with the name _LEFTOVER_CHILD."""
    try:
        pids = [int(entry.name) for entry in Path("/proc").iterdir() if entry.name.isdigit()]
    except OSError:
        return []
    children = []
    for child in pids:
        stat = _stat(child)
        if stat is not None and stat[:2] == (_LEFTOVER_CHILD, pid):
            children.append((child, stat[2]))
    return children


def _stop_leftover_children(children: list[tuple[int, int]]) -> None:
    """SIGTERM to each child that still runs with the same name and start time.

    A PID with another name or start time is a new process that got the PID again: no signal."""
    for pid, start in children:
        stat = _stat(pid)
        if stat is None or stat[0] != _LEFTOVER_CHILD or stat[2] != start:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


def _stop(proc: IdeProcess, timeout: float, key: str) -> str | None:
    """SIGTERM, then wait until the process is gone. Never SIGKILL: the IDE must save its state.

    When the IDE is gone, its _LEFTOVER_CHILD children get a SIGTERM too. While the IDE runs, they
    are its children, so an IDE that does not stop in the timeout keeps them."""
    children = _leftover_children(proc.pid)
    try:
        os.kill(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        _stop_leftover_children(children)
        return None
    deadline = time.monotonic() + timeout
    while Path(f"/proc/{proc.pid}").exists():
        if time.monotonic() >= deadline:
            return f"{key} did not stop in {timeout:.0f} s"
        time.sleep(0.2)
    _stop_leftover_children(children)
    return None


def _scope_prefix(env: dict[str, str]) -> list[str]:
    """The `systemd-run` prefix for a scope of its own, or [] when systemd cannot give one.

    A probe with the environment of the IDE process decides: no `systemd-run` on its PATH,
    no user manager, a timeout or a non-zero exit all mean no.
    """
    if shutil.which("systemd-run", path=env.get("PATH", os.defpath)) is None:
        return []
    prefix = ["systemd-run", "--user", "--scope", "--quiet", "--collect", "--"]
    try:
        probe = subprocess.run(prefix + ["true"], env=env, timeout=10, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return []
    return prefix if probe.returncode == 0 else []


def _start(proc: IdeProcess) -> None:
    """Start the IDE as it ran before: same launcher, environment and working directory.

    `setsid --fork` makes the IDE a child of init, not of this harness. A child
    of the harness would stay in /proc as a zombie after its end, and a later
    `_stop` in the same harness run would wait for it until the timeout.

    `setsid` does not leave the cgroup of the caller. On a machine with systemd the caller
    is in a user unit, for example the service of a terminal. When systemd-oomd or a stop
    kills that unit, the IDE dies with it. A transient scope takes the IDE out of that unit.
    The start is plain when no scope is possible, or when the scoped start fails once.
    """
    command = ["setsid", "--fork", str(proc.launcher), "serverMode"]
    prefix = _scope_prefix(proc.env)

    def run(cmd: list[str]) -> None:
        subprocess.run(cmd, cwd=proc.cwd, env=proc.env, check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if prefix:
        try:
            run(prefix + command)
            return
        except subprocess.CalledProcessError:
            pass
    run(command)


@contextlib.contextmanager
def _signals_held_back():
    """Deliver a SIGINT or a SIGTERM of this block only when the block has ended.

    Handlers and no signal mask: the kernel can give a signal of the process
    to any thread, and a mask holds for one thread only. Main thread only."""
    seen: list[int] = []
    before = {number: signal.signal(number, lambda signum, frame: seen.append(signum))
              for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for number, handler in before.items():
            signal.signal(number, handler)
        for number in tuple(seen):
            signal.raise_signal(number)


def _start_problem(proc: IdeProcess) -> str | None:
    """Why `_start` cannot work, or None. The switch asks this while the IDE still runs."""
    if not (proc.launcher.is_file() and os.access(proc.launcher, os.X_OK)):
        return f"launcher {proc.launcher} is not an executable file"
    if shutil.which("setsid", path=proc.env.get("PATH", os.defpath)) is None:
        return "no `setsid` program on the PATH of the IDE process"
    return None


def set_open_projects(ide: Ide, wanted: list[str], post, url: str | None = None, log=print,
                      stop_timeout: float = 90.0, start_timeout: float = 300.0,
                      may_close: Callable[[str], bool] = lambda path: False,
                      trust: Sequence[str] = (), quiet_wait=wait_until_quiet,
                      scan=index_rebuild_requests) -> str | None:
    """Make `wanted` the open projects of the IDE. None on success, else one error line.

    The plugin has no tool that opens or closes a project, so a change is a
    restart: stop the IDE, mark the wanted projects in recentProjects.xml,
    give each path of `trust` a trust entry in trusted-paths.xml, start the
    IDE, and wait until the server lists exactly those projects.

    The IDEs are shared, so the switch has five rules. It restarts only the
    fleet server of the IDE, never the server of another `url`. It closes an
    open project only when `may_close` accepts its path; a command from
    another checkout can thus not take the fixture projects from the fleet.
    It proves before the stop what the start needs. It stops the IDE only
    when `quiet_wait` (url, post) finds it quiet: a stop while the IDE
    indexes can damage its index (#308). From the stop to the start it
    holds back the signals that can end the harness, and it starts the IDE
    also after an error: the fleet must not stay without an IDE.
    """
    fleet_url = ide_url(ide)
    url = url or fleet_url
    now = open_projects(url, post)
    if now is None:
        return f"cannot reach {url}: start the IDE first"
    if set(now) == set(wanted):
        return None
    if url != fleet_url:
        return f"{url} is not the fleet server of {ide.key} ({fleet_url}): the harness restarts only a fleet IDE"
    kept = [path for path in now if path not in wanted and not may_close(path)]
    if kept:
        return (f"{ide.key} has projects open that this command must not close: {', '.join(kept)}. "
                "Run the command from the checkout whose fixture projects the IDE has open, "
                "or close these projects by hand")
    proc = find_ide_process(ide)
    if proc is None:
        return f"no {ide.key} fleet process found"
    recent = proc.config_dir / "options" / "recentProjects.xml"
    trusted = proc.config_dir / "options" / "trusted-paths.xml"
    home = proc.env.get("HOME") or str(Path.home())
    # The trust file comes first: when its write fails, recentProjects.xml is not changed.
    rewrites: list[tuple[Path, Callable[[], str]]] = []
    if trust:
        rewrites.append((trusted, lambda: trust_project_paths(
            trusted.read_text() if trusted.exists() else None, list(trust), home)))
    rewrites.append((recent, lambda: rewrite_recent_projects(recent.read_text(), wanted, home)))
    for path, rewrite in rewrites:
        try:
            # Prove the rewrite while the IDE still runs: an error after the stop would leave the IDE down.
            rewrite()
        except (OSError, ET.ParseError, ValueError) as e:
            return f"cannot rewrite {path}: {e}"
    problem = _start_problem(proc)
    if problem is not None:
        return f"cannot restart {ide.key}: {problem}"
    err, waited = quiet_wait(url, post)
    if err is not None:
        return f"{ide.key} did not get quiet: {err}. The harness did not restart {ide.key}"
    # The minimum wait is QUIET_ANSWERS - 1 polls. One poll more means that an answer was not quiet.
    if waited >= QUIET_ANSWERS * QUIET_POLL_S:
        log(f"[{ide.key}] waited {waited:.0f} s for a quiet IDE before the stop")
    command = f"{proc.launcher} serverMode"
    log(f"[{ide.key}] restart for a project switch. Start command: {command}")
    # The scan reads the lines from the stop on: the shutdown and the first seconds of the new start.
    idea_log = proc.log_dir / "idea.log"
    try:
        log_size = idea_log.stat().st_size
    except OSError:
        log_size = 0
    # A Ctrl+C or a SIGTERM between the stop and the start would leave the IDE down, and no
    # harness command can start it again. The signals wait until the IDE is started.
    with _signals_held_back():
        err = _stop(proc, stop_timeout, ide.key)
        if err is not None:
            return f"{err}. If it stops later, start it with: {command}"
        try:
            for path, rewrite in rewrites:
                tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
                tmp.write_text(rewrite())
                os.replace(tmp, path)
        except (OSError, ET.ParseError, ValueError) as e:
            err = f"cannot rewrite {path}: {e}. {ide.key} runs again with its old projects"
        finally:
            try:
                _start(proc)
            except (OSError, subprocess.SubprocessError) as e:
                err = f"cannot start {ide.key}: {e}. Start command: {command}"
    # After the start command: an exception of the scan leaves no IDE stopped.
    rebuilt = scan(idea_log, log_size)
    if rebuilt:
        # The default system folder holds the log folder and the index folder.
        damage = (f"{ide.key} requested an index rebuild at the restart: {', '.join(rebuilt)}. The index of "
                  f"{ide.key} can be damaged (#308). To repair it, stop {ide.key}, remove the folder "
                  f"{proc.log_dir.parent / 'index'}, and start {ide.key}")
        err = damage if err is None else f"{err}. {damage}"
    if err is not None:
        return err
    deadline = time.monotonic() + start_timeout
    while True:
        now = open_projects(url, post)
        if now is not None and set(now) == set(wanted):
            return None
        if time.monotonic() >= deadline:
            return (f"{ide.key} did not open {wanted} in {start_timeout:.0f} s (open now: {now}). "
                    f"Start command: {command}")
        time.sleep(5)
