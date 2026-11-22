"""One user of the benchmark IDEs at a time.

`ide_lock(what)` holds an exclusive `flock` on the lock file (default `<data root>/state/lock`) while the block
runs, and writes `{"pid", "what", "since"}` into the file. A second `ide_lock` on the same file, also in the same
process, raises `Busy` at once, with the pid and the `what` text of the holder. The system frees the lock when the
holder closes the file or ends.
"""
import contextlib
import datetime
import fcntl
import json
import os

from common import settings


class Busy(Exception):
    """Another holder has the lock."""


def _holder(fd: int) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        held = json.loads(os.read(fd, 1 << 16))
        return f"pid {held['pid']} ({held['what']}, since {held['since']})"
    except (ValueError, TypeError, KeyError):
        return "a holder that has not written its record yet"


@contextlib.contextmanager
def ide_lock(what: str, path: str | None = None):
    path = path or os.path.join(settings.data_root(), "state", "lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Busy(f"the benchmark IDEs are in use: {path} is held by {_holder(fd)}") from None
        since = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        os.ftruncate(fd, 0)
        os.write(fd, (json.dumps({"pid": os.getpid(), "what": what, "since": since}) + "\n").encode("utf-8"))
        yield
    finally:
        os.close(fd)
