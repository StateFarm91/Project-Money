"""The authoritative job board: completion is a fact in the job's own output.

WHY THIS EXISTS. Twice in one session an operator reported a long job as RUNNING when it had
already finished, and both times the cost was real idle time on a company whose whole point
is reducing wall-clock to launch.

  2026-09-24, ~100 minutes. A waiter looped on `pgrep -f "run_tests.sh"` from inside a shell
  whose own command line contained the string `run_tests.sh`. Every waiter matched itself, so
  the loop could never end. Worse than the wait was the false confirmation: `pgrep -c`
  returning 7, then 8, then 9 read as the suite making progress, when it was the waiter count
  rising as waiters were added. The observer was measuring itself and reporting it as the
  thing observed. The suite had finished in about seven minutes and the result sat unread.

  2026-09-24, ~47 minutes. No self-match this time. The suite was launched, other work
  intervened, and the log was simply never re-read. The report said "awaiting the suite"
  while `TOTAL PASSING: 3469 ; suites failing: 0` had been sitting in the file for
  three quarters of an hour.

Different mechanisms, one root: **the report was derived from the watcher's belief rather
than from the job's own evidence.** So this module has one rule, and the rest follows from it:

    COMPLETION COMES FROM THE JOB'S OWN TERMINAL EVIDENCE, NEVER FROM A WATCHER'S STATE.

Three consequences, each aimed at one of the ways the rule has been broken:

  * A job is complete IF AND ONLY IF its own output contains terminal evidence -- a sentinel
    the job writes when it exits. No amount of watcher conviction substitutes. A job with no
    sentinel and no live process is STALLED, which is a third answer the old code could not
    give: it could only say running or finished, so a process that died silently looked
    exactly like one still working.
  * Finishing is not the same as being reported. A job whose sentinel exists but whose
    completion nobody has acknowledged is COMPLETE_UNREPORTED, and it carries its age. That
    state is the 47-minute failure, named, so that it shows up in a status read instead of
    being the absence of one.
  * A liveness probe that can match its own observer is not a liveness probe. `alive()` takes
    the caller's whole process lineage and refuses to count any of it, and the process lister
    is injectable so that the self-match case can be TESTED rather than asserted -- the 2026
    version was argued to be correct and was not.

WHAT THIS DELIBERATELY DOES NOT DO. It does not merge, deploy, or promote anything. It
reports, and it says when a lane is free to be refilled. Integration stays a decision.

WHAT IT CANNOT DO ON ITS OWN, AND WHERE THAT LIVES. Everything here is correct about the
jobs it is handed, and nothing here remembers what those jobs were. The job list is built in
memory by the caller, and on 2026-09-25 the container restarted with four lanes running: the
list went with the process, the `/tmp` logs went with the container, and this module had
nothing to be right about. `registry.py` is the durable half -- it persists where each lane's
evidence lives, not what its state was, and calls `read` below to recompute the verdict. The
one rule is implemented here and only here.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

RUNNING = "running"
COMPLETE = "complete"
COMPLETE_UNREPORTED = "complete_unreported"
FAILED = "failed"
STALLED = "stalled"
NO_SENTINEL = "no_sentinel"
MISSING = "missing"

# A job that finished this long ago and still has not been acknowledged is not merely
# finished -- it is a lane standing idle. Deliberately short: the point is to notice within
# one working step, not within one working day.
UNREPORTED_AFTER_S = 120.0

_EXIT = re.compile(r"^EXIT (\d+)\s*$", re.M)


def lineage(pid: int | None = None) -> set[int]:
    """Every process from `pid` up to init.

    A liveness probe that can match anything in this set is measuring itself or its own
    parents. Returned as a set so callers can exclude it explicitly rather than hoping a
    pattern happens not to match.
    """
    out: set[int] = set()
    cur = pid or os.getpid()
    while cur and cur not in out:
        out.add(cur)
        try:
            status = Path(f"/proc/{cur}/status").read_text()
            cur = int(status.split("PPid:")[1].split()[0])
        except Exception:
            break
    return out


def _proc_table() -> list[tuple[int, str]]:
    """Every (pid, command line) the kernel will show us."""
    rows = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmd = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", "replace")
        except Exception:
            continue
        rows.append((int(entry.name), cmd))
    return rows


def alive(marker: str, *, table=None, exclude: set[int] | None = None) -> list[int]:
    """PIDs whose command line contains `marker`, never counting the caller's own lineage.

    `table` is injectable so the self-match case can be exercised in a test. That matters:
    the version this replaces was correct by argument and wrong in practice, and an argument
    cannot be run in CI.
    """
    rows = _proc_table() if table is None else table
    skip = lineage() if exclude is None else exclude
    return [pid for pid, cmd in rows if marker in cmd and pid not in skip]


@dataclass(frozen=True)
class Job:
    """A long-running job, and where its own evidence lives."""

    name: str
    log: Path
    # What the job writes when it stops. Default matches the `echo "EXIT $?"` convention
    # already used across this repo's background runs.
    terminal: re.Pattern = field(default=_EXIT)
    # An optional headline the job writes, quoted back in the report so a reader sees the
    # RESULT and not merely the fact of completion.
    result: re.Pattern | None = None
    # The string that identifies this job's process. Never the watcher's command line.
    marker: str = ""

    @property
    def ack(self) -> Path:
        return self.log.with_suffix(self.log.suffix + ".reported")


def read(job: Job, *, now: float | None = None, table=None) -> dict:
    """The job's state, computed from its own output. Cheap, read-only, no side effects."""
    now = now or time.time()
    if not job.log.exists():
        return {"job": job.name, "state": MISSING, "evidence": None,
                "why": "the job has written no output at all"}

    text = job.log.read_text(errors="replace")
    end = job.terminal.search(text)

    if end is None:
        running = alive(job.marker, table=table) if job.marker else []
        if running:
            return {"job": job.name, "state": RUNNING, "pids": running,
                    "evidence": None, "bytes": len(text),
                    "why": "no terminal evidence yet and the process is alive"}
        # Nothing alive and no sentinel. That is TWO different facts and this must not
        # collapse them, because collapsing them is the very defect the board exists to
        # catch: a verdict computed from absence of evidence.
        #
        #   The job died mid-run.
        #   The job finished normally but writes a sentinel this Job was not told about.
        #
        # Found immediately on the first real use: logs written by older scripts end
        # `SUITE EXIT 0` rather than `EXIT 0`, and calling those "died without finishing"
        # would have been the board asserting a death it cannot see. If the output looks
        # like it reached an end, say so and say which fact is missing; only an empty or
        # clearly truncated log earns STALLED.
        looks_finished = bool(job.result and job.result.search(text))
        if looks_finished:
            return {"job": job.name, "state": NO_SENTINEL, "evidence": None,
                    "bytes": len(text),
                    "why": ("the output carries a result but no terminal sentinel this job "
                            "recognises, so completion cannot be established from evidence "
                            "-- this is not the same as having died, and the board will not "
                            "guess which")}
        return {"job": job.name, "state": STALLED, "evidence": None, "bytes": len(text),
                "why": ("no terminal evidence, no recognisable result, and no live process: "
                        "the job stopped before finishing")}

    # The exit code is PARSED out of the sentinel, not recognised. It used to be taken only
    # when `job.terminal` was this module's own `_EXIT` object -- an `is` test on a compiled
    # pattern -- so every job told about its own sentinel convention reported exit code 0,
    # and therefore COMPLETE, no matter what it exited with. `SUITE EXIT 1` read as a clean
    # pass. So did the same default pattern recompiled from a durable record, which is how
    # this was found: a lane whose suite failed and whose work was merged came back green
    # from the tool whose entire purpose is not doing that. A failing job that reads COMPLETE
    # is the worst answer this module can give, so the number is read from the sentinel
    # itself, and only a sentinel with no numeric group is treated as a clean stop.
    code = 0
    if end.re.groups:
        try:
            code = int(end.group(1))
        except (TypeError, ValueError):
            code = 0
    headline = None
    if job.result is not None:
        m = job.result.search(text)
        headline = m.group(0) if m else None

    finished_at = job.log.stat().st_mtime
    age = now - finished_at
    acknowledged = job.ack.exists()
    state = FAILED if code else COMPLETE
    if state is COMPLETE and not acknowledged and age >= UNREPORTED_AFTER_S:
        state = COMPLETE_UNREPORTED

    return {"job": job.name, "state": state, "exit_code": code,
            "evidence": headline or end.group(0).strip(),
            "age_s": round(age, 1), "acknowledged": acknowledged,
            "why": ("finished and acknowledged" if acknowledged else
                    "finished; nobody has acted on it yet")}


def acknowledge(job: Job) -> None:
    """Record that this job's completion has been acted on, not merely observed."""
    job.ack.write_text(f"{time.time():.0f}\n")


def board(jobs: list[Job], *, now: float | None = None, table=None) -> dict:
    """Every job at once, with the ones needing attention pulled to the front."""
    rows = [read(j, now=now, table=table) for j in jobs]
    return {
        "rows": rows,
        "needs_attention": [r for r in rows
                            if r["state"] in (COMPLETE_UNREPORTED, FAILED, STALLED,
                                              NO_SENTINEL)],
        "running": [r for r in rows if r["state"] == RUNNING],
        "refillable": [r["job"] for r in rows
                       if r["state"] in (COMPLETE, COMPLETE_UNREPORTED)],
        "rule": ("completion comes from the job's own terminal evidence, never from a "
                 "watcher's state"),
    }
