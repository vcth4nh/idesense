"""The settings of one machine, from the environment. No tracked file holds a value of one machine or one person.

    BENCH_ROOT         the data root (default ~/dev/idesense-bench)
    BENCH_SLOTS        the slots root (default ~/dev/ws)
    BENCH_APPS         the Toolbox apps folder (default ~/.local/share/JetBrains/Toolbox/apps)
    BENCH_SECRET_FILE  the secret file of the login; no default
    BENCH_LOGIN        the login kind: api-key (default) or subscription

A path must be absolute; a relative path is a ValueError that names the variable. An empty variable counts as not
set, as `${BENCH_ROOT:-...}` in bench/ide/bench-ide.sh. `~` is the home folder of the user (HOME). The data root and
the slots root are real paths (`os.path.realpath`): a symbolic link in them is resolved, because the benchmark IDEs
open the real path and the plugin compares project paths as text. No message shows the value of BENCH_SECRET_FILE
or of BENCH_LOGIN: a person can set the secret itself there by mistake.
"""
import os

LOGINS = ("api-key", "subscription")


def _path(name: str, default: str | None, secret: bool = False) -> str:
    value = os.environ.get(name) or None
    if value is None:
        if default is None:
            raise ValueError(f"the environment variable {name} is not set; it has no default")
        value = os.path.join(os.path.expanduser("~"), default)
    if not os.path.isabs(value):
        shown = "" if secret else f"={value!r}"
        raise ValueError(f"{name}{shown}: the path must be absolute")
    return os.path.normpath(value)


def live_test_root() -> str:
    """The folder live-test/, from the place of this file."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def repo_root() -> str:
    return os.path.dirname(live_test_root())


def data_root() -> str:
    return os.path.realpath(_path("BENCH_ROOT", os.path.join("dev", "idesense-bench")))


def slots_root() -> str:
    return os.path.realpath(_path("BENCH_SLOTS", os.path.join("dev", "ws")))


def ide_apps() -> str:
    return _path("BENCH_APPS", os.path.join(".local", "share", "JetBrains", "Toolbox", "apps"))


def secret_file() -> str:
    return _path("BENCH_SECRET_FILE", None, secret=True)


def login() -> str:
    value = os.environ.get("BENCH_LOGIN") or LOGINS[0]
    if value not in LOGINS:
        raise ValueError(f"BENCH_LOGIN has an unknown value: use one of {', '.join(LOGINS)}")
    return value
