"""One temporary-directory sandbox per test process, removed when the process ends.

**Why this exists (W3-HYG, 2026-10-06).** Lane workers run test files directly
(`PYTHONPATH=src python tests/test_x.py`), not only through `run_tests.sh`, so the harness's
per-run TMPDIR never covered them. Two hundred test files called `tempfile.mkdtemp` (which,
unlike `TemporaryDirectory`, removes nothing) or wrote mkstemp/`NamedTemporaryFile(delete=False)`
files, and the src code they drive writes into `tempfile.gettempdir()` too. /tmp reached
16.7 GB and more than 7,000 entries, about 900 new ones an hour while suites ran, filled the
disk and invalidated a test run.

**The contract.** `install()` -- called once at the top of every test file that creates
temporary files (a static guard in `test_w3_tmp_hygiene.py` refuses a file that does not) --
creates `<TMPDIR>/bl-test-<file>-XXXXXXXX`, points `tempfile.tempdir` AND the `TMPDIR`
environment variable at it (so every `mkdtemp`/`mkstemp`/`gettempdir` in this process and
in every subprocess it starts lands inside it), and removes it:

* on normal exit and on an uncaught exception (`atexit` runs for both);
* on SIGTERM (converted to `SystemExit` so `atexit` still runs) and on Ctrl-C;
* NOT on SIGKILL or `os._exit` -- nothing in-process can. That is what the harness's per-run
  TMPDIR trap in `run_tests.sh` is for: the sandbox lives inside the run's directory, and the
  run removes that whole directory on exit.

It is removed only by the process that created it (a forked child that exits normally does
not delete its parent's sandbox), and it is idempotent: importing it from two test modules in
one process yields one sandbox.

`scoped(prefix)` is the explicit form for code that wants its own directory removed as soon as
a block ends (success or exception), rather than at process exit.
"""
from __future__ import annotations

import atexit
import contextlib
import os
import shutil
import signal
import sys
import tempfile

PREFIX = "bl-test-"

_ROOT: str | None = None
_OWNER_PID: int | None = None
_PREV_TMPDIR: str | None = None


def _name() -> str:
    base = os.path.splitext(os.path.basename(sys.argv[0] if sys.argv and sys.argv[0] else "py"))[0]
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in base)
    return (safe or "py")[:48]


def cleanup() -> None:
    """Remove this process's sandbox. Safe to call more than once."""
    global _ROOT
    root = _ROOT
    if not root or os.getpid() != _OWNER_PID:
        return
    _ROOT = None
    shutil.rmtree(root, ignore_errors=True)
    # Point later temp use (an atexit handler registered before ours) back at the parent.
    tempfile.tempdir = None
    if _PREV_TMPDIR is None:
        os.environ.pop("TMPDIR", None)
    else:
        os.environ["TMPDIR"] = _PREV_TMPDIR


def _on_term(signum, frame):  # pragma: no cover - exercised in a subprocess
    raise SystemExit(128 + signum)


def install() -> str:
    """Create (once) and activate this process's sandbox; return its path."""
    global _ROOT, _OWNER_PID, _PREV_TMPDIR
    if _ROOT is not None and _OWNER_PID == os.getpid():
        return _ROOT
    _PREV_TMPDIR = os.environ.get("TMPDIR")
    tempfile.tempdir = None
    parent = tempfile.gettempdir()
    # tmp-hygiene: ok -- this IS the cleanup path; removed by `cleanup` via atexit/SIGTERM.
    root = tempfile.mkdtemp(prefix=f"{PREFIX}{_name()}-", dir=parent)
    _ROOT, _OWNER_PID = root, os.getpid()
    os.environ["TMPDIR"] = root
    tempfile.tempdir = root
    atexit.register(cleanup)
    try:
        if signal.getsignal(signal.SIGTERM) in (signal.SIG_DFL, None):
            signal.signal(signal.SIGTERM, _on_term)
    except (ValueError, OSError):  # not the main thread: atexit still covers normal exit
        pass
    return root


def root() -> str | None:
    """The active sandbox, or None if `install()` has not run in this process."""
    return _ROOT if _OWNER_PID == os.getpid() else None


@contextlib.contextmanager
def scoped(prefix: str = "bl-scoped-"):
    """A directory removed when the block exits, whether it returns or raises."""
    with tempfile.TemporaryDirectory(prefix=prefix) as path:
        yield path
