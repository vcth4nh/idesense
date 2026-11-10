"""The fleet IDEs of the live-test harness.

Which IDE serves which language, which process is the fleet instance of an
IDE, and which projects that IDE opens at its next start. Linux only (/proc).
"""
from __future__ import annotations

import os
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

    The fleet instance runs `serverMode` with the default configuration folder.
    A throwaway instance with its own -Didea.config.path is not the fleet.
    """
    prefix = f"-Didea.paths.selector={ide.selector}"
    selector = next((a.split("=", 1)[1] for a in cmdline
                     if a.startswith(prefix) and a[len(prefix):len(prefix) + 1].isdigit()), None)
    if selector is None or cmdline[-1] != "serverMode":
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
