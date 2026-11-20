"""Working directories that are removed when the work that needed them finishes.

**One call-site pattern, in one place, because the alternative was measured.** On 2026-09-20 a
full test run failed eleven suites on "No space left on device" with no code change behind it:
sixty-four test files called `tempfile.mkdtemp`, which -- unlike `TemporaryDirectory` -- never
removes what it creates, and they had left 37,284 directories and 29 GB in `/tmp`. The fix
there was containment in `run_tests.sh`, which works because a test run ends. Production does
not end. Ten production handlers made the same call on cadences that repeat forever, several
of them writing rendered images, and nothing removed any of them. What has been saving us is
that Railway replaces the container often -- a leak mitigated by an accident of hosting is
still a leak.

**A directory the caller supplied is never deleted.** Every one of those handlers took an
optional `work_dir` from its job inputs -- used by the tests, and by a caller that wants the
artefacts kept afterwards -- and cleaning that up would delete somebody else's files as a
side effect of a defect fix. So the contract is explicit: this owns only the directory it
created itself, and a supplied path is passed through untouched.

**The prefix is not decoration.** `ops.health.TEMP_PREFIXES` counts leftovers by prefix, so a
handler whose directories do survive is attributable to the handler that made them. A new
call site adds its prefix there too, and a test pins that the two agree -- otherwise the disk
signal quietly stops seeing the newest way this system fills a disk.
"""
from __future__ import annotations

import tempfile
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def work_dir(supplied: str | None, *, prefix: str) -> Iterator[str]:
    """A scratch directory for the duration of the block.

    Yields `supplied` unchanged when the caller gave one, and otherwise a fresh temporary
    directory that is removed on the way out -- including when the body raises, which is the
    path that leaked worst: a handler that failed half way through a render left the render
    behind and was then retried.
    """
    if supplied:
        yield supplied
        return
    with tempfile.TemporaryDirectory(prefix=prefix) as path:
        yield path
