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
            "worker_started_at": iso(self.worker_started_at),
            "worker_last_tick": iso(self.worker_last_tick),
            "worker_restarts": self.worker_restarts,
            "scheduler_last_tick": iso(self.scheduler_last_tick),
            "scheduler_last_enqueued": list(self.scheduler_last_enqueued),
            "last_error": self.last_error,
        }


STATE = RunnerState()

_IDLE_SLEEP = float(os.environ.get("BRAMBLELOOP_IDLE_SLEEP", "2.0"))
_SCHEDULER_INTERVAL = float(os.environ.get("BRAMBLELOOP_SCHEDULER_INTERVAL", "60"))


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
