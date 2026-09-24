"""Embedded worker and scheduler threads for a single-container deployment.

Master Plan section 13 describes web, workers and a scheduler as separate processes, and at
any real scale they should be. They are not separate here yet, for one reason: Railway bills
by the resources a service consumes, three always-on services cost roughly three times one,
and the owner's instruction was explicit that no consequential spend happens without
approval. A company with zero revenue does not get to spend triple on process isolation it
does not yet need.

Nothing about correctness depends on the split. The queue is in Postgres with leases and
idempotency keys, so a worker in this process and a worker in a separate service claim work
identically, and an unclean death of this container is exactly the case the persistence suite
kills and recovers from. Splitting later is a Railway config change and a start command, not
a rewrite -- `worker_entry.py` and `scheduler_entry.py` already exist for that day.

Set `BRAMBLELOOP_EMBEDDED_WORKER=0` to turn these off when the services are split.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..core.db import Database
from ..core.models import Phase
from ..runtime import pipeline  # noqa: F401  -- registers job handlers
from ..runtime.worker import Scheduler, Worker

log = logging.getLogger("brambleloop.runner")


def _disk_facts() -> dict:
    """This container's free space and its own leftover temporary directories.

    Wrapped so a failure to measure the disk can never stop the runner reporting its
    liveness: an unmeasurable disk is reported as an error and read as `unknown`, which is
    what it is, rather than taking the status endpoint down with it.
    """
    from ..ops.health import disk_facts

    try:
        return disk_facts()
    except Exception as exc:  # noqa: BLE001 - measuring the disk must never break status
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}


@dataclass
class RunnerState:
    """What the dashboard needs to answer 'is anything actually running?'"""

    enabled: bool = False
    worker_name: str = ""
    worker_started_at: datetime | None = None
    worker_last_tick: datetime | None = None
    worker_restarts: int = 0
    scheduler_last_tick: datetime | None = None
    scheduler_last_enqueued: list[str] = field(default_factory=list)
    last_error: str = ""

    def to_dict(self) -> dict:
        def iso(d: datetime | None) -> str | None:
            return d.isoformat() if d else None

        alive = False
        if self.worker_last_tick is not None:
            age = (datetime.now(timezone.utc) - self.worker_last_tick).total_seconds()
            alive = age < 120
        return {
            "enabled": self.enabled,
            "worker": self.worker_name,
            "worker_alive": alive,
            "worker_starting": self.starting,
            "worker_started_at": iso(self.worker_started_at),
            "worker_last_tick": iso(self.worker_last_tick),
            "worker_restarts": self.worker_restarts,
            "scheduler_last_tick": iso(self.scheduler_last_tick),
            "scheduler_last_enqueued": list(self.scheduler_last_enqueued),
            "last_error": self.last_error,
            # Measured here because this is the process that owns the disk. A health sweep
            # reading its own filesystem measures whichever machine is answering the
            # request, which in a split deployment is not the container doing the work.
            "disk": _disk_facts(),
        }

    @property
    def starting(self) -> bool:
        """Started, not yet ticked, and not yet late. Distinct from dead.

        The worker waits `_START_DELAY` before its first pass and the scheduler ticks every
        `_SCHEDULER_INTERVAL`, so a freshly deployed container genuinely has no tick to
        report for the first minute and a half. Reporting that as a dead worker means every
        deploy produces a window where `/api/verify` fails, and the operator loop says a
        failing check is the highest-value thing to work on -- so the cost of the false
        alarm is a session chasing a phantom, or worse, "fixing" something that is fine.

        Deliberately bounded, and false the moment the grace expires: a worker that started
        five minutes ago and has still never ticked is dead, and must read as dead. This
        narrows a window; it does not soften the check.
        """
        if self.worker_last_tick is not None or self.worker_started_at is None:
            return False
        age = (datetime.now(timezone.utc) - self.worker_started_at).total_seconds()
        return age < startup_grace_seconds()


def startup_grace_seconds() -> float:
    """How long a just-started runner may legitimately have no tick to report.

    Derived from the runner's own knobs rather than hardcoded, so changing the interval
    cannot silently make the grace wrong in either direction. The margin covers the first
    pass's own work.
    """
    return _START_DELAY + _SCHEDULER_INTERVAL + 30.0


STATE = RunnerState()

_IDLE_SLEEP = float(os.environ.get("BRAMBLELOOP_IDLE_SLEEP", "2.0"))
_SCHEDULER_INTERVAL = float(os.environ.get("BRAMBLELOOP_SCHEDULER_INTERVAL", "60"))

# Become healthy before taking on load. The first thing the scheduler enqueues is a full
# planning cycle, and rendering eleven products' PDFs is CPU-bound work that holds the GIL --
# enough, on a small instance, to starve the health endpoint until the platform gives up and
# marks a perfectly good deployment failed. Serving first and working second is how a
# container is supposed to start.
_START_DELAY = float(os.environ.get("BRAMBLELOOP_RUNNER_START_DELAY", "25"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _worker_loop(db: Database, name: str, phase: Phase, stop: threading.Event) -> None:
    """Claim and run jobs until told to stop.

    Wrapped in its own restart loop. An unhandled exception escaping the worker must not
    silently leave the container serving HTTP with nothing processing the queue -- that is the
    failure mode where the dashboard looks healthy and the company has quietly stopped.
    """
    STATE.worker_name = name
    STATE.worker_started_at = _now()
    if _START_DELAY > 0 and stop.wait(_START_DELAY):
        return
    while not stop.is_set():
        try:
            worker = Worker(db, name, phase=phase)
            while not stop.is_set():
                did_work = worker.run_once()
                STATE.worker_last_tick = _now()
                if not did_work:
                    stop.wait(_IDLE_SLEEP)
        except Exception as e:  # noqa: BLE001
            STATE.worker_restarts += 1
            STATE.last_error = f"{type(e).__name__}: {e}"
            log.exception("embedded worker crashed; restarting")
            stop.wait(min(60.0, 2.0 * STATE.worker_restarts))


def _scheduler_loop(db: Database, stop: threading.Event) -> None:
    if _START_DELAY > 0 and stop.wait(_START_DELAY):
        return
    while not stop.is_set():
        try:
            enqueued = Scheduler(db).tick()
            STATE.scheduler_last_tick = _now()
            STATE.scheduler_last_enqueued = list(enqueued)
            if enqueued:
                log.info("enqueued cadences: %s", ", ".join(enqueued))
        except Exception as e:  # noqa: BLE001
            STATE.last_error = f"scheduler: {type(e).__name__}: {e}"
            log.exception("embedded scheduler tick failed")
        stop.wait(_SCHEDULER_INTERVAL)


_stop = threading.Event()
_threads: list[threading.Thread] = []


def start(db: Database) -> RunnerState:
    """Start the embedded worker and scheduler. Idempotent within a process."""
    if _threads or os.environ.get("BRAMBLELOOP_EMBEDDED_WORKER", "1") != "1":
        return STATE
    _stop.clear()  # a previous stop() must not silently disarm a fresh start
    phase = Phase(os.environ.get("BRAMBLELOOP_PHASE", "shadow"))
    name = os.environ.get("BRAMBLELOOP_WORKER_NAME") or f"web-{os.getpid()}"
    STATE.enabled = True
    for target, args in ((_worker_loop, (db, name, phase, _stop)),
                         (_scheduler_loop, (db, _stop))):
        t = threading.Thread(target=target, args=args, daemon=True,
                             name=f"brambleloop-{target.__name__}")
        t.start()
        _threads.append(t)
    log.info("embedded runner started: worker=%s phase=%s", name, phase.value)
    return STATE


def stop(timeout: float = 5.0) -> None:
    _stop.set()
    for t in _threads:
        t.join(timeout=timeout)
    _threads.clear()
    STATE.enabled = False


def wait_for_tick(timeout: float = 10.0) -> bool:
    """Test helper: block until the embedded worker has completed at least one loop."""
    end = time.time() + timeout
    while time.time() < end:
        if STATE.worker_last_tick is not None:
            return True
        time.sleep(0.05)
    return False
