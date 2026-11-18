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
    # F-489 (parallelism efficiency): seconds the active pool workers spent working versus
    # waiting with nothing claimable, summed over workers since this process started. Dormant
    # workers (beyond the allocation's target) are counted in neither: they were not asked
    # to work. Process-local, like every field here; reset on restart.
    busy_seconds: float = 0.0
    idle_seconds: float = 0.0
    # P1 6783107211: worker 0 itself, so liveness can see the handler it is running.
    worker_ref: object = None

    def busy(self, now: datetime | None = None) -> dict | None:
        """The handler worker 0 is running now, with how long it has run; None when idle."""
        cur = getattr(self.worker_ref, "current", None)
        if not cur or not cur.get("started_at"):
            return None
        now = now or datetime.now(timezone.utc)
        started = cur["started_at"]
        started = started if started.tzinfo else started.replace(tzinfo=timezone.utc)
        return {"job_id": cur.get("job_id"), "job_type": cur.get("job_type"),
                "started_at": started.isoformat(),
                "seconds": round((now - started).total_seconds(), 1)}

    def liveness(self, now: datetime | None = None) -> tuple[bool, str]:
        """Is worker 0 alive, and on what evidence.

        P1 6783107211: the tick is written between jobs, so a handler longer than
        `WORKER_TICK_STALE_S` (every night at 00:00Z all ~50 daily cadence windows open at
        once, and one of them runs ~7 min) read as a dead worker. A worker is alive when it
        ticked recently, OR while a handler it is running is within `MAX_HANDLER_SECONDS` --
        the same budget after which the lease system treats a handler as hung and lets it be
        reclaimed. Not weaker than before for a wedged worker: one stuck outside a handler
        (claim, lock, the loop itself) still reads dead after the tick threshold, and a
        handler past its budget reads dead too."""
        now = now or datetime.now(timezone.utc)
        if self.worker_last_tick is not None and \
                (now - self.worker_last_tick).total_seconds() < WORKER_TICK_STALE_S:
            return True, "tick"
        b = self.busy(now)
        if b is not None and b["seconds"] < HANDLER_LONG_S:
            return True, "handler_running"
        if b is not None and b["seconds"] < handler_budget_seconds():
            # review 6785727146 F1: still alive, but degraded -- a handler this long may be
            # hung (a deadlock, a call with no timeout), and nothing else would say so within
            # the hour. Surfaced: /health basis, an advisory /api/verify check, a P2 incident
            # raised once by the scheduler loop (watch_long_handler), a readback WARN.
            return True, "handler_long"
        if b is not None:
            return False, "handler_over_budget"
        return False, "no_tick" if self.worker_last_tick is None else "tick_stale"

    def to_dict(self) -> dict:
        def iso(d: datetime | None) -> str | None:
            return d.isoformat() if d else None

        alive, basis = self.liveness()
        return {
            "enabled": self.enabled,
            "worker": self.worker_name,
            "worker_alive": alive,
            "worker_alive_basis": basis,
            "worker_busy": self.busy(),
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
            "busy_seconds": round(self.busy_seconds, 1),
            "idle_seconds": round(self.idle_seconds, 1),
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


# A tick older than this, with no handler running, is a dead worker. Review 6785727146 F2:
# the environment may only tighten it, never loosen it past 120 s.
_TICK_STALE_CEILING_S = 120.0
WORKER_TICK_STALE_S = min(_TICK_STALE_CEILING_S, float(
    os.environ.get("BRAMBLELOOP_WORKER_TICK_STALE_S", str(_TICK_STALE_CEILING_S))))

# A handler running longer than this is `handler_long`: alive, degraded, and signalled.
HANDLER_LONG_S = 15 * 60.0
LONG_HANDLER_SIGNATURE = "worker0-handler-long"


# Review 6789501427 LOW-2: one row per worker instance, so two replicas overlapping during a
# deploy never resolve each other's incident. A row nobody has restated for this long belongs
# to an instance that stopped (each instance restates its own row every scheduler tick).
LONG_HANDLER_ORPHAN_S = 10 * 60.0


def long_handler_instance(state: "RunnerState | None" = None) -> str:
    """This process's identity for its long-handler incident: worker name @ host."""
    import socket

    st = state or STATE
    return f"{st.worker_name or 'worker'}@{socket.gethostname()}"[:120]


def watch_long_handler(db: Database, state: "RunnerState | None" = None, now=None) -> str:
    """Review 6785727146 F1: raise ONE open, non-halting P2 incident while worker 0's handler
    is `handler_long` or past its budget, and resolve it once that handler is no longer
    running. Called from the scheduler loop, which ticks while the worker is held.

    Review 6789501427: the row is this instance's (`worker0-handler-long:<instance>`), raised
    and restated through `ops.incident_lifecycle.open_or_restate` (so `last_seen` moves every
    tick). An instance resolves only its own row -- or another instance's row nobody has
    restated for `LONG_HANDLER_ORPHAN_S` (its owner stopped). Returns what it did ("raised",
    "kept", "resolved", "none"); never raises."""
    from datetime import datetime as _dt, timezone as _tz

    from sqlalchemy import or_, select

    from ..core.models import Incident, utcnow
    from ..ops.incident_lifecycle import open_or_restate

    st = state or STATE
    try:
        now_ = now or _dt.now(_tz.utc)
        alive, basis = st.liveness(now_)
        b = st.busy(now_)
        long_job = b if basis in ("handler_long", "handler_over_budget") and b else None
        mine = f"{LONG_HANDLER_SIGNATURE}:{long_handler_instance(st)}"[:200]
        done = "none"
        with db.session() as s:
            rows = list(s.scalars(select(Incident).where(
                or_(Incident.signature.like(f"{LONG_HANDLER_SIGNATURE}:%"),
                    Incident.signature == LONG_HANDLER_SIGNATURE),
                Incident.resolved.is_(False))))

            def resolve(row, why):
                row.resolved = True
                row.detail = {**(row.detail or {}), "resolved_at": utcnow().isoformat(),
                              "resolution": why}

            for row in rows:
                if row.signature == LONG_HANDLER_SIGNATURE:
                    # review 6791709875 nit 1: the bare, pre-instance signature (23d5649c ..
                    # 5e6d43e7) can only be left over from a rollback to one of those builds
                    resolve(row, "superseded: the long-handler incident is now per instance")
                    done = "resolved"
                    continue
                if row.signature == mine:
                    if long_job is None or (row.detail or {}).get("job_id") != long_job["job_id"]:
                        resolve(row, "the handler is no longer running")
                        done = "resolved"
                    continue
                seen = (row.detail or {}).get("last_seen")
                try:
                    seen_at = _dt.fromisoformat(seen) if seen else None
                except ValueError:
                    seen_at = None
                if seen_at is not None and seen_at.tzinfo is None:
                    seen_at = seen_at.replace(tzinfo=_tz.utc)
                if seen_at is None or (now_ - seen_at).total_seconds() > LONG_HANDLER_ORPHAN_S:
                    resolve(row, f"its instance stopped restating it for over "
                                 f"{LONG_HANDLER_ORPHAN_S:.0f} s")
                    done = "resolved"
            s.flush()
            if long_job is not None:
                _row, opened = open_or_restate(
                    s, signature=mine, severity="P2", halts_publication=False, now=now_,
                    summary=(f"worker 0 has run {long_job['job_type']} (job "
                             f"{long_job['job_id']}) for {long_job['seconds']:.0f} s, past "
                             f"{HANDLER_LONG_S:.0f} s: possibly hung; it reads dead at "
                             f"{handler_budget_seconds():.0f} s"),
                    detail={"job_id": long_job["job_id"], "job_type": long_job["job_type"],
                            "started_at": long_job["started_at"],
                            "seconds": long_job["seconds"], "basis": basis,
                            "instance": long_handler_instance(st)})
                done = "raised" if opened else "kept"
        return done
    except Exception:  # noqa: BLE001 - the watch must never stop the scheduler
        log.exception("long-handler watch failed")
        return "none"


def handler_budget_seconds() -> float:
    """How long a running handler keeps the worker alive: the lease-renewal cap, past which
    the queue treats the handler as hung (runtime.worker.MAX_HANDLER_SECONDS)."""
    from ..runtime.worker import MAX_HANDLER_SECONDS

    return float(MAX_HANDLER_SECONDS)


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
            worker = Worker(db, name, phase=phase, live_phase=True, refill_on_idle=True)
            if index == 0:
                STATE.worker_ref = worker
            while not stop.is_set():
                if index > 0 and target is not None and index >= target.get():
                    stop.wait(_IDLE_SLEEP * 5)      # dormant: the allocation does not need it
                    continue
                t0 = time.monotonic()
                did_work = worker.run_once()
                STATE.worker_last_tick = _now()
                if index == 0:
                    _worker_heartbeat(db, name)
                if did_work:
                    STATE.busy_seconds += time.monotonic() - t0
                else:
                    t1 = time.monotonic()
                    stop.wait(_IDLE_SLEEP)
                    STATE.idle_seconds += time.monotonic() - t1 + (t1 - t0)
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
            worker = Worker(db, name, phase=phase, job_types=job_types, live_phase=True,
                            refill_on_idle=True)
            while not stop.is_set():
                t0 = time.monotonic()
                did_work = worker.run_once()
                info["last_tick"] = _now().isoformat()
                if did_work:
                    info["busy_seconds"] = round(float(info.get("busy_seconds") or 0.0)
                                                 + time.monotonic() - t0, 1)
                else:
                    stop.wait(_IDLE_SLEEP)
                    info["idle_seconds"] = round(float(info.get("idle_seconds") or 0.0)
                                                 + time.monotonic() - t0, 1)
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
            watch_long_handler(db)
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
    # M-2R: job handlers are about to run in this process, so it may never sign a storefront
    # grant; the signing key leaves the environment before the first handler runs.
    from ..ops import storefront_authority as _sfa

    _sfa.mark_job_process()
    # WS4-3: a standing policy is never signed in a process that runs job handlers.
    from ..ops import standing_policy as _sp

    _sp.mark_job_process()
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
