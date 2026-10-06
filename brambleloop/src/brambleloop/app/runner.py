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
    scheduler_started_at: datetime | None = None
    scheduler_last_enqueued: list[str] = field(default_factory=list)
    last_error: str = ""
    worker_pool: int = 1
    worker_target: int = 1
    worker_target_why: str = ""
    # v1.1 lane A: dedicated lanes (runtime.lanes), e.g. the control lane that keeps the
    # Executive Orchestrator turning while a long render holds the pool.
    lanes: dict = field(default_factory=dict)

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
            "scheduler_started_at": iso(self.scheduler_started_at),
            "scheduler_last_enqueued": list(self.scheduler_last_enqueued),
            "last_error": self.last_error,
            "worker_pool": self.worker_pool,
            "worker_target": self.worker_target,
            "worker_target_why": self.worker_target_why,
            "lanes": {k: dict(v) for k, v in self.lanes.items()},
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


# C-68 (#175): how often a pool worker re-reads whether it is one of the active workers.
_TARGET_REFRESH_SECONDS = float(os.environ.get("BRAMBLELOOP_WORKER_TARGET_REFRESH", "30"))


class _Target:
    """The number of pool workers the latest allocation activates, re-read periodically."""

    def __init__(self, db: Database, pool: int):
        self.db, self.pool = db, pool
        self.value, self.read_at, self.why = 1, 0.0, "not yet read"
        self._lock = threading.Lock()

    def get(self) -> int:
        with self._lock:
            if time.monotonic() - self.read_at >= _TARGET_REFRESH_SECONDS:
                self.read_at = time.monotonic()
                try:
                    from ..swarm.capacity import worker_target

                    t = worker_target(self.db, pool=self.pool)
                    self.value, self.why = int(t["target"]), t["why"]
                except Exception as exc:  # noqa: BLE001 - never stop the pool over a read
                    self.value, self.why = 1, f"target unreadable: {type(exc).__name__}"
                STATE.worker_target = self.value
                STATE.worker_target_why = self.why
            return self.value


def _worker_loop(db: Database, name: str, phase: Phase, stop: threading.Event,
                 index: int = 0, target: "_Target | None" = None) -> None:
    """Claim and run jobs until told to stop.

    Wrapped in its own restart loop. An unhandled exception escaping the worker must not
    silently leave the container serving HTTP with nothing processing the queue -- that is the
    failure mode where the dashboard looks healthy and the company has quietly stopped.

    One of a pool (C-68, #175): worker `index` claims only while it is among the active
    workers the latest allocation justifies (`swarm.capacity.worker_target`). Worker 0 is
    always active, so a quiet period runs one worker and nothing ever runs none.
    """
    if index == 0:
        STATE.worker_name = name
        STATE.worker_started_at = _now()
    if _START_DELAY > 0 and stop.wait(_START_DELAY):
        return
    while not stop.is_set():
        try:
            # rc1-AUTH A1: re-resolve the effective phase per job, not once at boot.
            worker = Worker(db, name, phase=phase, live_phase=True)
            while not stop.is_set():
                if index > 0 and target is not None and index >= target.get():
                    stop.wait(_IDLE_SLEEP * 5)      # dormant: the allocation does not need it
                    continue
                did_work = worker.run_once()
                STATE.worker_last_tick = _now()
                if index == 0:
                    _worker_heartbeat(db, name)
                if not did_work:
                    stop.wait(_IDLE_SLEEP)
        except Exception as e:  # noqa: BLE001
            STATE.worker_restarts += 1
            STATE.last_error = f"{type(e).__name__}: {e}"
            log.exception("embedded worker crashed; restarting")
            stop.wait(min(60.0, 2.0 * STATE.worker_restarts))


def _lane_loop(db: Database, name: str, phase: Phase, stop: threading.Event, lane: str,
               job_types: list[str]) -> None:
    """A dedicated claimer for one lane's job types (runtime.lanes). Restarts like the pool."""
    info = STATE.lanes.setdefault(lane, {})
    info.update(worker=name, job_types=list(job_types), last_tick=None, restarts=0,
                last_error="")
    if _START_DELAY > 0 and stop.wait(_START_DELAY):
        return
    while not stop.is_set():
        try:
            worker = Worker(db, name, phase=phase, job_types=job_types, live_phase=True)
            while not stop.is_set():
                did_work = worker.run_once()
                info["last_tick"] = _now().isoformat()
                if not did_work:
                    stop.wait(_IDLE_SLEEP)
        except Exception as e:  # noqa: BLE001
            info["restarts"] = int(info.get("restarts") or 0) + 1
            info["last_error"] = f"{type(e).__name__}: {e}"[:300]
            log.exception("lane %s worker crashed; restarting", lane)
            stop.wait(min(60.0, 2.0 * info["restarts"]))


# v1.1 lane I W-2: the worker's durable liveness row, at most once a minute.
_WORKER_HEARTBEAT_EVERY_S = 60.0
_last_worker_heartbeat = 0.0


def _worker_heartbeat(db: Database, name: str) -> None:
    global _last_worker_heartbeat
    if time.monotonic() - _last_worker_heartbeat < _WORKER_HEARTBEAT_EVERY_S:
        return
    _last_worker_heartbeat = time.monotonic()
    try:
        from ..ops import slo as _slo

        _slo.record_heartbeat(db, "worker", instance=name)
    except Exception:  # noqa: BLE001 - liveness evidence must never stop the worker
        log.exception("worker heartbeat row not written")


def _scheduler_heartbeat(db: Database, enqueued: list[str]) -> None:
    """v1.1 lane I W-1: the scheduler's durable liveness row after every successful tick."""
    try:
        from ..ops import slo as _slo

        _slo.record_heartbeat(db, "scheduler", instance=f"web-{os.getpid()}",
                              detail={"enqueued": len(enqueued)})
    except Exception:  # noqa: BLE001 - liveness evidence must never stop scheduling
        log.exception("scheduler heartbeat row not written")


def _scheduler_loop(db: Database, stop: threading.Event) -> None:
    STATE.scheduler_started_at = _now()
    if _START_DELAY > 0 and stop.wait(_START_DELAY):
        return
    while not stop.is_set():
        try:
            enqueued = Scheduler(db).tick()
            STATE.scheduler_last_tick = _now()
            STATE.scheduler_last_enqueued = list(enqueued)
            _scheduler_heartbeat(db, list(enqueued))
            if enqueued:
                log.info("enqueued cadences: %s", ", ".join(enqueued))
        except Exception as e:  # noqa: BLE001
            STATE.last_error = f"scheduler: {type(e).__name__}: {e}"
            log.exception("embedded scheduler tick failed")
        stop.wait(_SCHEDULER_INTERVAL)


# ---------------------------------------------------------------------------
# v1.1 lane I W-3: stale-scheduler self-exit. A scheduler thread that has stopped ticking
# while the web thread still answers /health is the failure where the container looks alive
# and the company has stopped. The supervisor exits the process so the platform's restart
# policy replaces it. Deliberately conservative:
#   * only when this process runs the embedded scheduler (start() launched it);
#   * the threshold is generous (15 min against a 60 s interval) and must be observed on two
#     consecutive checks, so one slow tick never kills a working container;
#   * a scheduler that has never ticked is judged from its own start plus the start delay;
#   * opt out with BRAMBLELOOP_SELF_EXIT_ON_STALE=0.
SELF_EXIT_STALE_S = float(os.environ.get("BRAMBLELOOP_SELF_EXIT_STALE_S", str(15 * 60)))
_SUPERVISOR_INTERVAL = float(os.environ.get("BRAMBLELOOP_SUPERVISOR_INTERVAL", "60"))
_exit = os._exit          # replaced in tests


def self_exit_enabled() -> bool:
    return os.environ.get("BRAMBLELOOP_SELF_EXIT_ON_STALE", "1") != "0"


def scheduler_stale(state: RunnerState, now: datetime | None = None,
                    threshold_s: float | None = None) -> tuple[bool, str]:
    """Pure check: is the embedded scheduler stale enough to restart the container?"""
    now = now or _now()
    threshold = SELF_EXIT_STALE_S if threshold_s is None else float(threshold_s)
    if not state.enabled or state.scheduler_started_at is None:
        return False, "no embedded scheduler runs in this process"
    # A tick from before this scheduler started (a previous start() in the same process)
    # is not evidence about this one.
    if state.scheduler_last_tick is None or \
            state.scheduler_last_tick < state.scheduler_started_at:
        age = (now - state.scheduler_started_at).total_seconds()
        if age <= threshold + _START_DELAY:
            return False, f"scheduler started {age:.0f}s ago and has not ticked yet"
        return True, f"scheduler started {age:.0f}s ago and has never ticked"
    age = (now - state.scheduler_last_tick).total_seconds()
    if age <= threshold:
        return False, f"last scheduler tick {age:.0f}s ago"
    return True, f"last scheduler tick {age:.0f}s ago (threshold {threshold:.0f}s)"


def supervise_once(strikes: int, *, now: datetime | None = None) -> int:
    """One supervisor check. Returns the new strike count; exits on the second strike."""
    stale, why = scheduler_stale(STATE, now)
    if not stale:
        return 0
    strikes += 1
    if strikes < 2:
        log.error("scheduler looks stale (%s); exiting if still stale at the next check", why)
        return strikes
    log.critical("embedded scheduler stale (%s); exiting so the platform restarts the "
                 "container", why)
    _exit(1)
    return strikes


def _supervisor_loop(stop: threading.Event) -> None:
    strikes = 0
    while not stop.wait(_SUPERVISOR_INTERVAL):
        try:
            strikes = supervise_once(strikes)
        except Exception:  # noqa: BLE001 - the supervisor never crashes the runner
            log.exception("runner supervisor check failed")


_stop = threading.Event()
_threads: list[threading.Thread] = []


def start(db: Database) -> RunnerState:
    """Start the embedded worker and scheduler. Idempotent within a process."""
    if _threads or os.environ.get("BRAMBLELOOP_EMBEDDED_WORKER", "1") != "1":
        return STATE
    _stop.clear()  # a previous stop() must not silently disarm a fresh start
    # F-299: the environment AND the recorded owner transition; disagreement -> the more
    # restrictive phase plus an incident. Shadow when nothing is recorded.
    from ..core.phase import effective_phase

    phase = effective_phase(db)
    # The PID repeats across containers, so two replicas of an overlapping deploy can both be
    # `web-7`. v1.1 lane A: the queue's per-claim lease token fences that case, so the name
    # format (which the independence certification reads) is unchanged.
    name = os.environ.get("BRAMBLELOOP_WORKER_NAME") or f"web-{os.getpid()}"
    STATE.enabled = True
    from ..swarm.capacity import worker_threads

    pool = worker_threads()
    STATE.worker_pool = pool
    shared = _Target(db, pool)
    loops = [(_worker_loop, (db, name if i == 0 else f"{name}-w{i}", phase, _stop, i, shared))
             for i in range(pool)]
    # v1.1 lane A: dedicated lanes beside the pool (default: the control lane).
    from ..runtime.lanes import partitions
    from ..runtime.worker import handlers as _handlers

    STATE.lanes.clear()
    mode = os.environ.get("BRAMBLELOOP_WORKER_LANES", "control")
    for lane, types in partitions(_handlers.known(), mode).items():
        if lane == "company" or not types:
            continue
        loops.append((_lane_loop, (db, f"{name}-{lane}", phase, _stop, lane, types)))
    extra = [(_scheduler_loop, (db, _stop))]
    if self_exit_enabled():
        extra.append((_supervisor_loop, (_stop,)))
    for i, (target, args) in enumerate(loops + extra):
        t = threading.Thread(target=target, args=args, daemon=True,
                             name=f"brambleloop-{target.__name__}-{i}")
        t.start()
        _threads.append(t)
    log.info("embedded runner started: worker=%s pool=%d phase=%s", name, pool, phase.value)
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
