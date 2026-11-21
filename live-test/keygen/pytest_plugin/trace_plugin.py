"""pytest plugin: log the callers of target functions.

    PYTHONPATH=<WT>/live-test/keygen/pytest_plugin pytest -p trace_plugin \
        --trace-targets=<targets.json> --trace-out=<trace.jsonl>

Give each option and its value as one argument, with `=`. pytest looks for its root folder (and so for the
config of the product) before it knows the options of a plugin: it takes a separate value that is an existing
path as a test path, and a targets file outside the tree then moves the root folder out of the tree.

`--trace-targets` is a JSON list of `{"id", "file", "line"}`. `file` is relative to the pytest root folder (or
absolute), and `line` is the line of the `def` (the line of the name token, the `decl` of a key record). The
plugin finds the function at that line in the ast of the file. Its code object starts at the first decorator
line. The plugin watches the start of each target code object: with `sys.monitoring` (Python 3.12 and later)
each other code object stops its event after its first start; an older Python uses `sys.setprofile`. The
source is not changed. A target with no function at its line stops the run with a usage error.

`--trace-out` gets one JSON line `{"id", "caller_file", "caller_line"}` for each distinct call site of a
target, sorted. The caller is the frame below the target. A wrapper frame does not count, and the frame below
it is the caller: a frame whose closure, or the instance dict of whose `self`, holds the target function or a
wrapper of it (a decorator closure, a decorator class, `functools.cached_property`). `caller_file` is relative
to the pytest root folder with forward slashes, or absolute outside that folder.

Limits: a generator function starts at its first `next()`, so its caller is the frame of that `next()`. A
`cached_property` runs once for each instance, so only its first access is seen. A call in a child process is
not seen. A frame that keeps the target function in an attribute of `self` and calls it is taken as a wrapper.
"""
import ast
import json
import os
import sys
import threading

import pytest

_FREE_TOOL_IDS = (2, 3, 4)  # sys.monitoring.PROFILER_ID, then two ids with no assigned use
# Bound at import: a test of a product can replace os.path (beets: `os.path = ntpath`) while a target runs.
_path = os.path
_SEP = os.sep


def _holds(value, chain) -> bool:
    value = getattr(value, "__func__", value)
    return getattr(value, "__code__", None) in chain


def pytest_addoption(parser):
    group = parser.getgroup("benchtrace", "callers of target functions (trace_plugin)")
    group.addoption("--trace-targets", default=None, help="JSON list of {id, file, line}")
    group.addoption("--trace-out", default=None, help="JSONL output: {id, caller_file, caller_line}")


class Tracer:
    def __init__(self, root: str, targets: list[dict]):
        self.root = _path.realpath(root)
        self.ids = {}  # (real file, first line, name) -> id
        self.codes = {}  # code object -> id or None
        self.real = {}  # co_filename -> real path
        self.hits = set()
        self.tool = None
        missing = []
        trees = {}
        for target in targets:
            path = _path.realpath(_path.join(self.root, target["file"]))
            if not _path.isfile(path):
                missing.append(f"no file {target['file']} below {self.root}")
                continue
            if path not in trees:
                with open(path, "rb") as f:
                    trees[path] = ast.parse(f.read(), filename=path)
            nodes = [n for n in ast.walk(trees[path])
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno == target["line"]]
            if len(nodes) != 1:
                missing.append(f"no single function at {target['file']}:{target['line']}")
                continue
            node = nodes[0]
            first = node.decorator_list[0].lineno if node.decorator_list else node.lineno
            self.ids[(path, first, node.name)] = target["id"]
        if missing:
            raise pytest.UsageError("trace_plugin: " + "; ".join(missing) +
                                    " (give the options as --trace-targets=<file> --trace-out=<file>)")

    def _real(self, filename: str) -> str:
        real = self.real.get(filename)
        if real is None:
            real = self.real[filename] = _path.realpath(filename)
        return real

    def _target(self, code):
        try:
            return self.codes[code]
        except KeyError:
            pass
        tid = self.codes[code] = self.ids.get((self._real(code.co_filename), code.co_firstlineno, code.co_name))
        return tid

    @staticmethod
    def _wrapper(frame, chain) -> bool:
        """True when a free variable of the frame, or an attribute in the instance dict of its `self`, holds a
        function of the chain (the target, then the wrappers below it): a decorator closure, a decorator class,
        or a descriptor such as `functools.cached_property`."""
        code = frame.f_code
        names = code.co_freevars
        has_self = code.co_argcount > 0 and code.co_varnames[0] == "self"
        if not names and not has_self:
            return False
        local = frame.f_locals
        if any(_holds(local.get(name), chain) for name in names):
            return True
        if has_self:
            try:
                attrs = list(vars(local.get("self")).values())
            except TypeError:
                return False
            return any(_holds(value, chain) for value in attrs)
        return False

    def _record(self, tid, frame):
        chain = {frame.f_code}
        caller = frame.f_back
        while caller is not None and self._wrapper(caller, chain):
            chain.add(caller.f_code)
            caller = caller.f_back
        if caller is None:
            return
        path = self._real(caller.f_code.co_filename)
        if path.startswith(self.root + _SEP):
            path = _path.relpath(path, self.root).replace(_SEP, "/")
        self.hits.add((tid, path, caller.f_lineno))

    def _on_start(self, code, offset):
        tid = self._target(code)
        if tid is None:
            return sys.monitoring.DISABLE
        self._record(tid, sys._getframe(1))
        return None

    def _on_profile(self, frame, event, arg):
        if event == "call":
            tid = self._target(frame.f_code)
            if tid is not None:
                self._record(tid, frame)

    def start(self):
        mon = getattr(sys, "monitoring", None)
        if mon is None:
            threading.setprofile(self._on_profile)
            sys.setprofile(self._on_profile)
            return
        free = [t for t in _FREE_TOOL_IDS if mon.get_tool(t) is None]
        if not free:
            raise pytest.UsageError("trace_plugin: no free sys.monitoring tool id")
        self.tool = free[0]
        mon.use_tool_id(self.tool, "trace_plugin")
        mon.register_callback(self.tool, mon.events.PY_START, self._on_start)
        mon.set_events(self.tool, mon.events.PY_START)

    def stop(self):
        if self.tool is None:
            sys.setprofile(None)
            threading.setprofile(None)
            return
        mon = sys.monitoring
        mon.set_events(self.tool, 0)
        mon.register_callback(self.tool, mon.events.PY_START, None)
        mon.free_tool_id(self.tool)
        self.tool = None

    def write(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            for tid, caller_file, caller_line in sorted(self.hits):
                f.write(json.dumps({"id": tid, "caller_file": caller_file, "caller_line": caller_line}) + "\n")


_tracer = None


def pytest_configure(config):
    global _tracer
    targets, out = config.getoption("--trace-targets"), config.getoption("--trace-out")
    if targets is None and out is None:
        return
    if targets is None or out is None:
        raise pytest.UsageError("trace_plugin: give both --trace-targets and --trace-out")
    with open(targets, encoding="utf-8") as f:
        _tracer = Tracer(str(config.rootpath), json.load(f))
    _tracer.start()


def pytest_unconfigure(config):
    global _tracer
    if _tracer is None:
        return
    _tracer.stop()
    _tracer.write(config.getoption("--trace-out"))
    _tracer = None
