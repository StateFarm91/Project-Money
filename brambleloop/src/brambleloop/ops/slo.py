"""Service-level objectives for the always-on company, computed from durable state (F-923, F-924).

v1.1 says the company keeps working when every development chat is closed and the owner's PC
is off. "Working" is not "the container answers HTTP" -- `ops.health` already says that in its
first paragraph -- so the objectives here are about *work happening on time*, measured from
rows the production processes write anyway, never from a variable in this process:

* ``command_center_availability`` (F-923): the owner surface answered an **external** probe.
  Only a probe written by something outside the web container counts. The web process's own
  heartbeat proves the process exists, which is a proxy, and a proxy is never reported as a
  measurement: with no external probe rows the objective is UNKNOWN, never 100 %.
* ``scheduler_freshness`` (F-924): the scheduler kept enqueuing. Read from the scheduler's
  self-heartbeat rows when they exist (WIRING REQUEST, lane A), otherwise from the cadence
  jobs the scheduler itself creates (``jobs.idempotency_key LIKE 'cadence:%'``) -- a durable
  trace every tick leaves, with the 15-minute ``infra_heartbeat`` cadence guaranteeing one at
  least every quarter hour.
* ``cadence_freshness`` (F-924): each scheduled cadence completed within twice its period.
* ``queue_latency`` (F-924): due work was started promptly.
* ``recovery_time`` (F-924): platform incidents closed quickly.
* ``department_heartbeat`` / ``department_useful_work`` (F-890, F-924, directive section 2):
  each department attempted work recently, and the share of the hours it was expected to work
  in which it completed *useful* work (`runtime.pipeline.did_no_work` is the judge, and the
  self-observing heartbeat/health jobs never count as useful).

Every objective carries a target, an error budget and the budget consumed. No data is
UNKNOWN, never zero and never "met". A breach raises an incident through
`ops.incident_lifecycle` -- the stored notification system the Command Center reads -- and an
objective that recovers closes its incident with the reading that closed it. Nothing here
sends e-mail, SMS or anything else off the box.

Two tables are defined here because nothing else holds the facts: ``ops_runtime_samples``
(heartbeats and external probes, append-only, pruned after 35 days) and ``ops_leases`` (a
database lease that works on SQLite and Postgres, used to keep a single active scheduler when
web/worker/scheduler are split into services). Both are created lazily on first use, so the
module works before `core.db.create_all` is wired to import it (WIRING REQUEST).
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base

OK, DEGRADED, BLOCKED, UNKNOWN = "OK", "DEGRADED", "BLOCKED", "UNKNOWN"
MET, AT_RISK, BREACHED = "MET", "AT_RISK", "BREACHED"

# Share of the error budget consumed at which an objective that is still met reads AT_RISK.
AT_RISK_BUDGET_SHARE = 0.75
# An availability reading over fewer than this share of its intervals is not a reading.
MIN_COVERAGE = 0.5
INTERVAL_S = 300
SAMPLE_RETENTION_DAYS = 35

# A scheduler self-heartbeat older than this means the scheduler loop is not running. The
# embedded scheduler ticks every 60 s (`BRAMBLELOOP_SCHEDULER_INTERVAL`); ten minutes is ten
# missed ticks, which is a condition, not a blip.
SCHEDULER_HEARTBEAT_STALE_S = 10 * 60
# Without heartbeats the evidence is the newest cadence job. `infra_heartbeat` opens a new
# window every 15 minutes, so two missed windows plus slack is a scheduler that has stopped.
SCHEDULER_CADENCE_STALE_S = 35 * 60
# Due work nobody has started in this long, with no job started either, is a stalled worker.
WORKER_STALL_S = 15 * 60
# Queue latency objective: a due job starts within this long.
QUEUE_LATENCY_TARGET_S = 15 * 60
# Recovery objective: a platform incident closes within this long.
RECOVERY_TARGET_S = 60 * 60
# A cadence is fresh when it completed within (factor x period) + grace.
CADENCE_FRESH_FACTOR = 2.0
CADENCE_GRACE_S = 15 * 60
# A department has a heartbeat when it attempted any work within max(this, 2 x its fastest
# cadence period).
DEPARTMENT_HEARTBEAT_MIN_S = 2 * 60 * 60

# Signature families this module raises. `slo.` is the prefix reconciled on every check.
SIG_BREACH = "slo.breach:"
SIG_SCHEDULER_STALE = "slo.scheduler_stale"
SIG_WORKER_STALLED = "slo.worker_stalled"
PLATFORM_INCIDENT_PREFIXES = ("health:", "slo.")

# Self-observation is real completed work and never evidence about the business
# (`ops.health.SELF_OBSERVING_JOB_TYPES`, imported lazily to keep this module light).
_SELF_OBSERVING_FALLBACK = frozenset({"ops.heartbeat", "ops.health"})


# ---------------------------------------------------------------------------
# Durable state


class RuntimeSample(Base):
    """One heartbeat or probe. Append-only; `prune_samples` removes rows past retention."""

    __tablename__ = "ops_runtime_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)        # heartbeat | probe
    component: Mapped[str] = mapped_column(String(48), index=True)   # scheduler, worker, ...
    instance: Mapped[str] = mapped_column(String(120), default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class OpsLease(Base):
    """A named lease with an expiry. The single-active-scheduler guard for a split topology."""

    __tablename__ = "ops_leases"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    holder: Mapped[str | None] = mapped_column(String(120), nullable=True)
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class _Scope:
    """Run a function in a session whether handed a `Database` or an open `Session`.

    A `Database` gets its own committed transaction; a `Session` is used as-is and only
    flushed, because its transaction belongs to the caller (the Command Center's request).
    """

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        if hasattr(self.db, "session") and callable(getattr(self.db, "session")) \
                and not hasattr(self.db, "execute"):
            self._cm = self.db.session()
            self.s = self._cm.__enter__()
        else:
            self._cm = None
            self.s = self.db
        _ensure_tables(self.s)
        return self.s

    def __exit__(self, *exc):
        if self._cm is not None:
            return self._cm.__exit__(*exc)
        if exc[0] is None:
            self.s.flush()
        return False


_ENSURED: set[int] = set()


def _ensure_tables(session) -> None:
    """Create this module's tables if `create_all` has not (it does once wired)."""
    try:
        bind = session.get_bind()
    except Exception:  # noqa: BLE001 - no bind means nothing to create against
        return
    engine = getattr(bind, "engine", bind)
    if id(engine) in _ENSURED:
        return
    from sqlalchemy import inspect

    try:
        names = set(inspect(session.connection()).get_table_names())
        for table in (RuntimeSample.__table__, OpsLease.__table__):
            if table.name not in names:
                table.create(bind=session.connection(), checkfirst=True)
        _ENSURED.add(id(engine))
    except Exception:  # noqa: BLE001 - a read path must never fail on DDL; reads see no rows
        pass


def _tables_present(session) -> bool:
    from sqlalchemy import inspect

    try:
        names = set(inspect(session.connection()).get_table_names())
    except Exception:  # noqa: BLE001
        return False
    return RuntimeSample.__tablename__ in names


def record_heartbeat(db, component: str, *, instance: str = "", ok: bool = True,
                     detail: dict | None = None, now: datetime | None = None) -> None:
    """A process saying it is alive and what it last did. Cheap: one INSERT."""
    if not component:
        raise ValueError("a heartbeat names the component it is for")
    with _Scope(db) as s:
        s.add(RuntimeSample(at=_now(now), kind="heartbeat", component=component[:48],
                            instance=(instance or "")[:120], ok=bool(ok),
                            detail=detail or {}))


def record_probe(db, component: str, *, ok: bool, latency_ms: float | None = None,
                 detail: dict | None = None, instance: str = "",
                 now: datetime | None = None) -> None:
    """An outside-in observation (the watchdog fetching the Command Center's /health)."""
    with _Scope(db) as s:
        s.add(RuntimeSample(at=_now(now), kind="probe", component=component[:48],
                            instance=(instance or "")[:120], ok=bool(ok),
                            latency_ms=latency_ms, detail=detail or {}))


def prune_samples(db, *, older_than_days: int = SAMPLE_RETENTION_DAYS,
                  now: datetime | None = None) -> int:
    from sqlalchemy import delete

    cutoff = _now(now) - timedelta(days=older_than_days)
    with _Scope(db) as s:
        res = s.execute(delete(RuntimeSample).where(RuntimeSample.at < cutoff))
        return int(res.rowcount or 0)


# ---- leases ---------------------------------------------------------------


def acquire_lease(db, name: str, holder: str, *, ttl_s: int = 180,
                  now: datetime | None = None) -> bool:
    """Take or renew `name` for `holder`. True only when this holder now owns it.

    One conditional UPDATE (free or expired or already mine), then -- if the row does not
    exist -- one INSERT against the primary key. Either the database lets exactly one writer
    win, or it raises and this returns False. No read-then-write window.
    """
    from sqlalchemy import or_, update
    from sqlalchemy.exc import IntegrityError

    if not name or not holder:
        raise ValueError("a lease needs a name and a holder")
    now = _now(now)
    expires = now + timedelta(seconds=ttl_s)
    with _Scope(db) as s:
        res = s.execute(
            update(OpsLease).where(
                OpsLease.name == name,
                or_(OpsLease.holder.is_(None), OpsLease.expires_at <= now,
                    OpsLease.holder == holder))
            .values(holder=holder, expires_at=expires,
                    acquired_at=now)
            .execution_options(synchronize_session=False))
        if res.rowcount == 1:
            return True
        if s.get(OpsLease, name) is not None:
            return False
        try:
            with s.begin_nested():
                s.add(OpsLease(name=name, holder=holder, acquired_at=now, expires_at=expires,
                               detail={}))
            return True
        except IntegrityError:
            return False


def release_lease(db, name: str, holder: str) -> bool:
    from sqlalchemy import update

    with _Scope(db) as s:
        res = s.execute(update(OpsLease).where(OpsLease.name == name,
                                               OpsLease.holder == holder)
                        .values(holder=None, expires_at=None)
                        .execution_options(synchronize_session=False))
        return res.rowcount == 1


def lease_state(db, name: str, *, now: datetime | None = None) -> dict | None:
    now = _now(now)
    with _Scope(db) as s:
        row = s.get(OpsLease, name)
        if row is None:
            return None
        exp = _aware(row.expires_at)
        return {"name": row.name, "holder": row.holder,
                "acquired_at": _aware(row.acquired_at).isoformat() if row.acquired_at else None,
                "expires_at": exp.isoformat() if exp else None,
                "live": bool(row.holder and exp and exp > now)}


# ---------------------------------------------------------------------------
# Objectives


@dataclass(frozen=True)
class SLO:
    key: str
    requirement: str
    objective: str
    target: float
    window_hours: int
    severity: str          # incident severity on breach

    def to_dict(self) -> dict:
        return {"key": self.key, "requirement": self.requirement, "objective": self.objective,
                "target": self.target, "window_hours": self.window_hours,
                "breach_severity": self.severity}


SLOS: dict[str, SLO] = {s.key: s for s in (
    SLO("command_center_availability", "F-923",
        "the owner Command Center answered an external probe in 99.5% of 5-minute intervals",
        0.995, 30 * 24, "P2"),
    SLO("scheduler_freshness", "F-924",
        "the scheduler was fresh (recent self-heartbeat or cadence enqueue) in 99% of "
        "5-minute intervals", 0.99, 24, "P1"),
    SLO("cadence_freshness", "F-924",
        "95% of scheduled cadences completed within twice their period", 0.95, 0, "P2"),
    SLO("queue_latency", "F-924",
        "95% of jobs started within 15 minutes of becoming due", 0.95, 24, "P2"),
    SLO("recovery_time", "F-924",
        "90% of platform incidents closed within 60 minutes", 0.90, 7 * 24, "P2"),
    SLO("department_heartbeat", "F-924/F-890",
        "every department attempted work within max(2h, 2x its fastest cadence)", 1.0, 0, "P2"),
    SLO("department_useful_work", "F-924/F-890",
        "each department completed useful work in at least half of the hours its cadences "
        "expected it to work", 0.5, 24, "P3"),
)}


def error_budget(sli: float | None, target: float) -> dict:
    """The budget arithmetic every objective shares. `sli=None` is UNKNOWN, not zero."""
    if sli is None:
        return {"state": UNKNOWN, "budget_total": round(1 - target, 6),
                "budget_consumed_share": None, "budget_remaining_share": None}
    total = 1.0 - target
    burned = max(0.0, 1.0 - sli)
    if total <= 0:
        consumed = 0.0 if burned <= 0 else math.inf
    else:
        consumed = burned / total
    if sli < target:
        state = BREACHED
    elif consumed >= AT_RISK_BUDGET_SHARE:
        state = AT_RISK
    else:
        state = MET
    return {"state": state, "budget_total": round(total, 6),
            "budget_consumed_share": (None if math.isinf(consumed) else round(consumed, 4)),
            "budget_remaining_share": (None if math.isinf(consumed)
                                       else round(max(0.0, 1.0 - consumed), 4))}


def _result(key: str, sli: float | None, *, basis: str, reason: str, measure: dict,
            sources: list[str], state_override: str | None = None) -> dict:
    slo = SLOS[key]
    budget = error_budget(sli, slo.target)
    if state_override:
        budget["state"] = state_override
    return {**slo.to_dict(), "sli": None if sli is None else round(sli, 6), "basis": basis,
            **budget, "reason": reason, "measure": measure, "sources": sources}


def _interval_series(stamps: list[datetime], start: datetime, end: datetime,
                     stale_s: float) -> tuple[int, int]:
    """(fresh, total) 5-minute interval ends in [start, end] whose newest stamp is recent."""
    stamps = sorted(stamps)
    total = fresh = 0
    t = start + timedelta(seconds=INTERVAL_S)
    i, latest = 0, None
    while t <= end:
        while i < len(stamps) and stamps[i] <= t:
            latest = stamps[i]
            i += 1
        total += 1
        if latest is not None and (t - latest).total_seconds() <= stale_s:
            fresh += 1
        t += timedelta(seconds=INTERVAL_S)
    return fresh, total


# ---- F-923 ----------------------------------------------------------------

AVAILABILITY_COMPONENT = "command_center"


def availability(s, now: datetime) -> dict:
    from sqlalchemy import select

    slo = SLOS["command_center_availability"]
    start = now - timedelta(hours=slo.window_hours)
    rows = []
    proxy = None
    if _tables_present(s):
        rows = [(_aware(at), ok) for at, ok in s.execute(
            select(RuntimeSample.at, RuntimeSample.ok)
            .where(RuntimeSample.kind == "probe",
                   RuntimeSample.component == AVAILABILITY_COMPONENT,
                   RuntimeSample.at >= start, RuntimeSample.at <= now)).all()]
        proxy = s.scalar(select(RuntimeSample.at).where(
            RuntimeSample.kind == "heartbeat", RuntimeSample.component == "web")
            .order_by(RuntimeSample.at.desc()).limit(1))
    sources = ["ops_runtime_samples(kind=probe, component=command_center)"]
    proxy_note = ({"web_process_heartbeat_latest": _aware(proxy).isoformat(),
                   "basis": "proxy: process liveness, not reported as availability"}
                  if proxy else None)
    if not rows:
        return _result("command_center_availability", None, basis="unknown",
                       reason=("no external probe of the Command Center is recorded. The web "
                               "process answering itself is not availability, so this is "
                               "UNKNOWN rather than 100% (the watchdog cron in "
                               "CLOUD_HOSTING_PLAN.md writes these rows)"),
                       measure={"probes": 0, "proxy": proxy_note}, sources=sources)
    buckets: dict[int, bool] = {}
    for at, ok in rows:
        b = int((at - start).total_seconds() // INTERVAL_S)
        # Strict on purpose: an interval with any failed probe is down. A lenient rule
        # ("any success") would overstate availability, and this objective must not.
        buckets[b] = buckets.get(b, True) and bool(ok)
    first = min(at for at, _ in rows)
    span_start = max(start, first - timedelta(seconds=INTERVAL_S))
    total = max(1, int(math.ceil((now - span_start).total_seconds() / INTERVAL_S)))
    up = sum(1 for v in buckets.values() if v)
    observed = len(buckets)
    coverage = min(1.0, observed / total)
    sli = up / observed
    measure = {"intervals_up": up, "intervals_observed": observed,
               "intervals_in_span": total, "coverage": round(coverage, 4),
               "span_start": span_start.isoformat(), "proxy": proxy_note}
    if coverage < MIN_COVERAGE:
        return _result("command_center_availability", sli, basis="measured",
                       reason=(f"probes cover {coverage:.0%} of the intervals since probing "
                               f"began; under {MIN_COVERAGE:.0%} is not a reading, so the "
                               f"objective is UNKNOWN and missing intervals are not counted "
                               f"as up"),
                       measure=measure, sources=sources, state_override=UNKNOWN)
    return _result("command_center_availability", sli, basis="measured",
                   reason=f"{up}/{observed} observed intervals answered", measure=measure,
                   sources=sources)


# ---- F-924: scheduler and worker liveness ---------------------------------


def _cadence_job_stamps(s, since: datetime, until: datetime) -> list[datetime]:
    from sqlalchemy import select

    from ..core.models import Job

    return [_aware(t) for (t,) in s.execute(
        select(Job.created_at).where(Job.idempotency_key.like("cadence:%"),
                                     Job.created_at >= since,
                                     Job.created_at <= until)).all()]


def _heartbeat_stamps(s, component: str, since: datetime, until: datetime) -> list[datetime]:
    from sqlalchemy import select

    if not _tables_present(s):
        return []
    return [_aware(t) for (t,) in s.execute(
        select(RuntimeSample.at).where(RuntimeSample.kind == "heartbeat",
                                       RuntimeSample.component == component,
                                       RuntimeSample.at >= since,
                                       RuntimeSample.at <= until)).all()]


def scheduler_staleness(s, now: datetime) -> dict:
    """Is the scheduler alive right now? `stale` is None when there is no evidence at all."""
    from sqlalchemy import func, select

    from ..core.models import Job

    newest_hb = None
    if _tables_present(s):
        newest_hb = _aware(s.scalar(select(func.max(RuntimeSample.at)).where(
            RuntimeSample.kind == "heartbeat", RuntimeSample.component == "scheduler")))
    if newest_hb is not None:
        age = (now - newest_hb).total_seconds()
        return {"stale": age > SCHEDULER_HEARTBEAT_STALE_S, "age_s": round(age),
                "threshold_s": SCHEDULER_HEARTBEAT_STALE_S,
                "source": "ops_runtime_samples(component=scheduler)",
                "latest": newest_hb.isoformat()}
    newest_job = _aware(s.scalar(select(func.max(Job.created_at)).where(
        Job.idempotency_key.like("cadence:%"))))
    if newest_job is None:
        return {"stale": None, "age_s": None, "threshold_s": SCHEDULER_CADENCE_STALE_S,
                "source": "jobs(idempotency_key LIKE 'cadence:%')", "latest": None,
                "reason": "the scheduler has never enqueued a cadence and writes no "
                          "heartbeat: no evidence either way"}
    age = (now - newest_job).total_seconds()
    return {"stale": age > SCHEDULER_CADENCE_STALE_S, "age_s": round(age),
            "threshold_s": SCHEDULER_CADENCE_STALE_S,
            "source": "jobs(idempotency_key LIKE 'cadence:%')",
            "latest": newest_job.isoformat()}


def worker_stall(s, now: datetime) -> dict:
    """Due work waiting with no job started recently: the queue is not being drained."""
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus

    due_cut = now - timedelta(seconds=WORKER_STALL_S)
    oldest_due = _aware(s.scalar(select(func.min(Job.run_after)).where(
        Job.status.in_([JobStatus.PENDING, JobStatus.FAILED]), Job.run_after <= due_cut)))
    last_start = _aware(s.scalar(select(func.max(Job.started_at))))
    hb = _heartbeat_stamps(s, "worker", now - timedelta(seconds=WORKER_STALL_S), now)
    started_recently = (last_start is not None
                        and (now - last_start).total_seconds() <= WORKER_STALL_S)
    if oldest_due is None:
        return {"stalled": False, "reason": "no work has been due for longer than "
                f"{WORKER_STALL_S // 60} minutes", "source": "jobs"}
    stalled = not started_recently
    return {"stalled": stalled,
            "oldest_due_waiting_s": round((now - oldest_due).total_seconds()),
            "last_job_started_at": last_start.isoformat() if last_start else None,
            "worker_heartbeats_in_window": len(hb),
            "reason": ("due work is waiting and no job has started in "
                       f"{WORKER_STALL_S // 60} minutes" if stalled else
                       "due work is waiting but jobs are being started (busy, not stalled)"),
            "source": "jobs(run_after, started_at)"}


def scheduler_freshness(s, now: datetime) -> dict:
    slo = SLOS["scheduler_freshness"]
    start = now - timedelta(hours=slo.window_hours)
    hb = _heartbeat_stamps(s, "scheduler", start - timedelta(hours=1), now)
    if hb:
        stamps, stale_s = hb, SCHEDULER_HEARTBEAT_STALE_S
        source = "ops_runtime_samples(kind=heartbeat, component=scheduler)"
    else:
        stamps = _cadence_job_stamps(s, start - timedelta(hours=1), now)
        stale_s = SCHEDULER_CADENCE_STALE_S
        source = "jobs(idempotency_key LIKE 'cadence:%').created_at"
    if not stamps:
        return _result("scheduler_freshness", None, basis="unknown",
                       reason="no scheduler heartbeat and no cadence job in the window",
                       measure={"intervals": 0}, sources=[source])
    first = min(stamps)
    span_start = max(start, first)
    fresh, total = _interval_series(stamps, span_start, now, stale_s)
    if total == 0:
        return _result("scheduler_freshness", None, basis="unknown",
                       reason="evidence began less than one interval ago",
                       measure={"intervals": 0}, sources=[source])
    return _result("scheduler_freshness", fresh / total, basis="measured",
                   reason=f"fresh in {fresh}/{total} five-minute intervals",
                   measure={"fresh_intervals": fresh, "intervals": total,
                            "stale_after_s": stale_s, "span_start": span_start.isoformat()},
                   sources=[source])


# ---- F-924: cadences ------------------------------------------------------


def _cadences() -> list[tuple[str, str, str, int]]:
    try:
        from ..runtime.worker import CADENCES

        return list(CADENCES)
    except Exception:  # noqa: BLE001 - without the schedule there is nothing to judge
        return []


def _suspended(db_like, now) -> set[str]:
    try:
        from ..swarm.orchestrate import suspended_job_types

        return set(suspended_job_types(db_like, now=now))
    except Exception:  # noqa: BLE001
        return set()


def cadence_freshness(s, now: datetime) -> dict:
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus

    cadences = _cadences()
    if not cadences:
        return _result("cadence_freshness", None, basis="unknown",
                       reason="the cadence schedule could not be read",
                       measure={}, sources=["runtime.worker.CADENCES"])
    first_seen = _aware(s.scalar(select(func.min(Job.created_at)).where(
        Job.idempotency_key.like("cadence:%"))))
    if first_seen is None:
        return _result("cadence_freshness", None, basis="unknown",
                       reason="no cadence has ever been enqueued", measure={},
                       sources=["jobs"])
    done = {jt: _aware(t) for jt, t in s.execute(
        select(Job.job_type, func.max(Job.finished_at))
        .where(Job.status == JobStatus.DONE).group_by(Job.job_type)).all()}
    suspended = _suspended(_SessionDb(s), now)
    fresh, stale, not_due = [], [], []
    for name, _agent, job_type, period in cadences:
        allowed = CADENCE_FRESH_FACTOR * period + CADENCE_GRACE_S
        if job_type in suspended:
            not_due.append({"cadence": name, "why": "suspended by the thrash breaker"})
            continue
        if (now - first_seen).total_seconds() < allowed:
            not_due.append({"cadence": name, "why": "the system has not run long enough"})
            continue
        last = done.get(job_type)
        age = None if last is None else (now - last).total_seconds()
        row = {"cadence": name, "job_type": job_type, "period_s": period,
               "last_done": last.isoformat() if last else None,
               "age_s": None if age is None else round(age)}
        (fresh if age is not None and age <= allowed else stale).append(row)
    eligible = len(fresh) + len(stale)
    if eligible == 0:
        return _result("cadence_freshness", None, basis="unknown",
                       reason="no cadence has been scheduled long enough to be judged",
                       measure={"not_yet_judged": len(not_due)},
                       sources=["jobs", "runtime.worker.CADENCES"])
    return _result("cadence_freshness", len(fresh) / eligible, basis="measured",
                   reason=f"{len(fresh)}/{eligible} cadences fresh",
                   measure={"fresh": len(fresh), "stale": stale[:40],
                            "stale_count": len(stale), "not_yet_judged": len(not_due)},
                   sources=["jobs(status=done, finished_at)", "runtime.worker.CADENCES"])


# ---- F-924: queue latency ---------------------------------------------------


def queue_latency(s, now: datetime) -> dict:
    from sqlalchemy import select

    from ..core.models import Job

    slo = SLOS["queue_latency"]
    start = now - timedelta(hours=slo.window_hours)
    lat = []
    for created, run_after, started in s.execute(
            select(Job.created_at, Job.run_after, Job.started_at)
            .where(Job.started_at.is_not(None), Job.started_at >= start,
                   Job.started_at <= now)).all():
        created, run_after, started = _aware(created), _aware(run_after), _aware(started)
        due = run_after if run_after is not None and run_after <= started else created
        lat.append(max(0.0, (started - max(due, created)).total_seconds()))
    if not lat:
        return _result("queue_latency", None, basis="unknown",
                       reason="no job started in the window", measure={"jobs": 0},
                       sources=["jobs"])
    lat.sort()
    within = sum(1 for v in lat if v <= QUEUE_LATENCY_TARGET_S)

    def pct(p):
        return round(lat[min(len(lat) - 1, int(math.ceil(p * len(lat))) - 1)])

    return _result("queue_latency", within / len(lat), basis="measured",
                   reason=f"{within}/{len(lat)} started within "
                          f"{QUEUE_LATENCY_TARGET_S // 60} min of due",
                   measure={"jobs": len(lat), "p50_s": pct(0.5), "p95_s": pct(0.95),
                            "max_s": round(lat[-1])},
                   sources=["jobs(created_at, run_after, started_at)"])


# ---- F-924: recovery time ---------------------------------------------------


def recovery_time(s, now: datetime) -> dict:
    from sqlalchemy import or_, select

    from ..core.models import Incident

    slo = SLOS["recovery_time"]
    start = now - timedelta(hours=slo.window_hours)
    rows = list(s.scalars(select(Incident).where(
        or_(*[Incident.signature.like(f"{p}%") for p in PLATFORM_INCIDENT_PREFIXES]),
        Incident.at >= start - timedelta(days=7))))
    durations, open_late = [], 0
    for inc in rows:
        d = inc.detail or {}
        first = d.get("first_seen") or _aware(inc.at).isoformat()
        try:
            first_dt = _aware(datetime.fromisoformat(first))
        except ValueError:
            continue
        if inc.resolved:
            try:
                res = _aware(datetime.fromisoformat(d.get("resolved_at") or ""))
            except ValueError:
                continue
            if res >= start:
                durations.append((res - first_dt).total_seconds())
        elif (now - first_dt).total_seconds() > RECOVERY_TARGET_S:
            open_late += 1
    n = len(durations) + open_late
    if n == 0:
        return _result("recovery_time", None, basis="unknown",
                       reason="no platform incident opened or closed in the window, so "
                              "recovery time has not been observed",
                       measure={"incidents": 0}, sources=["incidents"])
    within = sum(1 for v in durations if v <= RECOVERY_TARGET_S)
    return _result("recovery_time", within / n, basis="measured",
                   reason=f"{within}/{n} platform incidents closed within "
                          f"{RECOVERY_TARGET_S // 60} min ({open_late} still open past it)",
                   measure={"closed": len(durations), "open_past_target": open_late,
                            "max_closed_minutes": (round(max(durations) / 60, 1)
                                                   if durations else None)},
                   sources=["incidents(signature LIKE 'health:%' OR 'slo.%')"])


# ---- departments ----------------------------------------------------------

# Job-type prefix -> department (F-890's eleven). The prefix is what the work *is*; the agent
# column names who ran it, which several departments share (orchestrator runs half the list).
DEPARTMENT_OF_PREFIX: dict[str, str] = {
    "plan": "executive", "portfolio": "executive", "swarm": "executive",
    "scale": "executive", "launch": "executive", "build": "executive", "chain": "executive",
    "intel": "intelligence", "radar": "intelligence", "culture": "intelligence",
    "mjs": "intelligence", "teardown": "intelligence", "seasonal": "intelligence",
    "creative": "product_design", "assets": "product_design",
    "gate": "product_truth", "physical": "product_truth", "release": "product_truth",
    "visual": "visual",
    "etsy": "store_commerce", "listing": "store_commerce", "commerce": "store_commerce",
    "store": "store_commerce",
    "support": "customer_support",
    "finance": "finance",
    "growth": "growth", "ads": "growth",
    "improve": "learn", "learn": "learn",
    "ops": "platform", "model": "platform",
}
DEPARTMENTS = ("executive", "intelligence", "product_design", "product_truth", "visual",
               "store_commerce", "customer_support", "finance", "growth", "learn", "platform")


def department_of(job_type: str) -> str | None:
    return DEPARTMENT_OF_PREFIX.get((job_type or "").split(".", 1)[0])


def _self_observing() -> frozenset[str]:
    try:
        from .health import SELF_OBSERVING_JOB_TYPES

        return SELF_OBSERVING_JOB_TYPES
    except Exception:  # noqa: BLE001
        return _SELF_OBSERVING_FALLBACK


def _did_no_work():
    try:
        from ..runtime.pipeline import did_no_work

        return did_no_work, "runtime.pipeline.did_no_work"
    except Exception:  # noqa: BLE001 - judged conservatively without it
        def fallback(outputs: dict) -> bool:
            return (outputs or {}).get("ran") is False
        return fallback, "fallback: outputs.ran is False"


def departments(s, now: datetime) -> tuple[dict, dict, list[dict]]:
    """(department_heartbeat result, department_useful_work result, per-department rows)."""
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus

    slo = SLOS["department_useful_work"]
    window_s = slo.window_hours * 3600
    start = now - timedelta(seconds=window_s)
    cadences = _cadences()
    selfobs = _self_observing()
    judge, judge_src = _did_no_work()

    expected_runs: dict[str, float] = {d: 0.0 for d in DEPARTMENTS}
    fastest: dict[str, int] = {}
    for _name, _agent, job_type, period in cadences:
        dept = department_of(job_type)
        if dept is None or job_type in selfobs:
            continue
        expected_runs[dept] += window_s / period
        fastest[dept] = min(fastest.get(dept, period), period)

    last_attempt: dict[str, datetime] = {}
    for jt, t in s.execute(select(Job.job_type, func.max(Job.started_at))
                           .where(Job.started_at.is_not(None))
                           .group_by(Job.job_type)).all():
        dept = department_of(jt)
        t = _aware(t)
        if dept and t and (dept not in last_attempt or t > last_attempt[dept]):
            last_attempt[dept] = t

    useful_hours: dict[str, set[int]] = {d: set() for d in DEPARTMENTS}
    done_counts: dict[str, int] = {d: 0 for d in DEPARTMENTS}
    for jt, finished, outputs in s.execute(
            select(Job.job_type, Job.finished_at, Job.outputs)
            .where(Job.status == JobStatus.DONE, Job.finished_at >= start,
                   Job.finished_at <= now)).all():
        dept = department_of(jt)
        if dept is None or jt in selfobs:
            continue
        done_counts[dept] += 1
        try:
            empty = judge(outputs or {})
        except Exception:  # noqa: BLE001
            empty = False
        if not empty:
            useful_hours[dept].add(int((_aware(finished) - start).total_seconds() // 3600))

    rows, alive, judged_hb, attain = [], 0, 0, []
    for dept in DEPARTMENTS:
        hb_window = max(DEPARTMENT_HEARTBEAT_MIN_S, 2 * fastest.get(dept, 0))
        last = last_attempt.get(dept)
        has_hb = last is not None and (now - last).total_seconds() <= hb_window
        expected_hours = min(slo.window_hours, int(math.ceil(expected_runs[dept])))
        useful = len(useful_hours[dept])
        row = {"department": dept, "last_attempt": last.isoformat() if last else None,
               "heartbeat_window_s": hb_window, "heartbeat": has_hb if last else None,
               "completed_jobs_window": done_counts[dept], "useful_hours": useful,
               "expected_hours": expected_hours,
               "useful_hours_pct": (round(useful / slo.window_hours, 4)),
               "attainment": (round(min(1.0, useful / expected_hours), 4)
                              if expected_hours else None)}
        if expected_hours and not any(done_counts.values()):
            # Nothing at all completed in the window: there is no reading, so no department
            # is judged (UNKNOWN, never 0% and never a breach on an empty database).
            row["state"] = UNKNOWN
            row["attainment"] = None
            row["reason"] = "no job completed in the window across the whole company"
        elif expected_hours:
            ebud = error_budget(row["attainment"], slo.target)
            row.update({"state": ebud["state"],
                        "budget_consumed_share": ebud["budget_consumed_share"]})
            attain.append(row["attainment"])
        else:
            row["state"] = UNKNOWN
            row["reason"] = "no cadence schedules this department; event-driven only"
        if last is not None or expected_hours:
            judged_hb += 1
            alive += 1 if has_hb else 0
        rows.append(row)

    sources = ["jobs(job_type, started_at, finished_at, outputs)",
               "runtime.worker.CADENCES", judge_src]
    if judged_hb == 0 or not last_attempt:
        hb = _result("department_heartbeat", None, basis="unknown",
                     reason="no department has ever attempted work", measure={},
                     sources=sources)
    else:
        silent = [r["department"] for r in rows
                  if (r["last_attempt"] or r["expected_hours"]) and not r["heartbeat"]]
        hb = _result("department_heartbeat", alive / judged_hb, basis="measured",
                     reason=(f"{alive}/{judged_hb} departments attempted work recently"
                             + (f"; silent: {', '.join(silent)}" if silent else "")),
                     measure={"silent": silent}, sources=sources)
    if not any(done_counts.values()):
        uw = _result("department_useful_work", None, basis="unknown",
                     reason="no department completed any job in the window",
                     measure={}, sources=sources)
    elif not attain:
        uw = _result("department_useful_work", None, basis="unknown",
                     reason="no department has a cadence to be judged against",
                     measure={}, sources=sources)
    else:
        worst = min(attain)
        below = [r["department"] for r in rows if r.get("state") == BREACHED]
        uw = _result("department_useful_work", worst, basis="measured",
                     reason=("the SLI is the worst department's attainment"
                             + (f"; below target: {', '.join(below)}" if below else "")),
                     measure={"below_target": below,
                              "mean_attainment": round(sum(attain) / len(attain), 4)},
                     sources=sources)
    return hb, uw, rows


# ---------------------------------------------------------------------------
# Composition


class _SessionDb:
    """A `Database`-shaped view of an open session (same transaction, never committed)."""

    def __init__(self, session):
        self._s = session
        try:
            self.engine = session.get_bind()
        except Exception:  # noqa: BLE001
            self.engine = None

    def session(self):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield self._s
        return _cm()


def evaluate(db, *, now: datetime | None = None) -> dict:
    """Every objective plus the two point-in-time liveness detectors. Read-only."""
    now = _now(now)
    with _Scope(db) as s:
        out: dict[str, dict] = {}
        for key, fn in (("command_center_availability", availability),
                        ("scheduler_freshness", scheduler_freshness),
                        ("cadence_freshness", cadence_freshness),
                        ("queue_latency", queue_latency),
                        ("recovery_time", recovery_time)):
            try:
                out[key] = fn(s, now)
            except Exception as exc:  # noqa: BLE001 - one broken reader is UNKNOWN, not a 500
                out[key] = _result(key, None, basis="unknown",
                                   reason=f"could not be computed: {type(exc).__name__}: "
                                          f"{str(exc)[:200]}", measure={}, sources=[])
        try:
            hb, uw, dept_rows = departments(s, now)
        except Exception as exc:  # noqa: BLE001
            why = f"could not be computed: {type(exc).__name__}: {str(exc)[:200]}"
            hb = _result("department_heartbeat", None, basis="unknown", reason=why,
                         measure={}, sources=[])
            uw = _result("department_useful_work", None, basis="unknown", reason=why,
                         measure={}, sources=[])
            dept_rows = []
        out["department_heartbeat"], out["department_useful_work"] = hb, uw
        try:
            sched = scheduler_staleness(s, now)
        except Exception as exc:  # noqa: BLE001
            sched = {"stale": None, "reason": f"{type(exc).__name__}: {exc}"[:200]}
        try:
            worker = worker_stall(s, now)
        except Exception as exc:  # noqa: BLE001
            worker = {"stalled": None, "reason": f"{type(exc).__name__}: {exc}"[:200]}
    return {"as_of": now.isoformat(), "slos": out, "departments": dept_rows,
            "scheduler": sched, "worker": worker}


def check(db, *, now: datetime | None = None) -> dict:
    """Evaluate and raise/restate/close incidents. The only side effect is incident rows.

    Run by the watchdog (outside the main container) and by an in-process cadence; both are
    safe together because `open_or_restate` keys on the signature.
    """
    from . import incident_lifecycle as life

    now = _now(now)
    report = evaluate(db, now=now)
    opened, restated = [], []
    breached: dict[str, dict] = {}
    for key, r in report["slos"].items():
        if r["state"] == BREACHED:
            breached[f"{SIG_BREACH}{key}"] = r
    for row in report["departments"]:
        if row.get("state") == BREACHED:
            breached[f"{SIG_BREACH}department_useful_work:{row['department']}"] = {
                "breach_severity": "P3",
                "reason": (f"{row['department']} completed useful work in "
                           f"{row['useful_hours']} of {row['expected_hours']} expected hours"),
                "sli": row["attainment"], "target": SLOS["department_useful_work"].target}
    sched, worker = report["scheduler"], report["worker"]
    with _Scope(db) as s:
        for sig, r in breached.items():
            _row, new = life.open_or_restate(
                s, signature=sig, severity=r.get("breach_severity", "P2"),
                summary=f"SLO breached: {sig[len(SIG_BREACH):]} -- {r.get('reason', '')}",
                detail={"sli": r.get("sli"), "target": r.get("target"),
                        "reason": r.get("reason")}, now=now)
            (opened if new else restated).append(sig)
        if sched.get("stale"):
            _row, new = life.open_or_restate(
                s, signature=SIG_SCHEDULER_STALE, severity="P1",
                summary=(f"the scheduler has not been seen for {sched.get('age_s')}s "
                         f"(threshold {sched.get('threshold_s')}s, source "
                         f"{sched.get('source')}): no cadence is being enqueued, so the "
                         f"company is not starting new work"),
                detail=dict(sched), now=now)
            (opened if new else restated).append(SIG_SCHEDULER_STALE)
        if worker.get("stalled"):
            _row, new = life.open_or_restate(
                s, signature=SIG_WORKER_STALLED, severity="P1",
                summary=f"the queue is not draining: {worker.get('reason')}",
                detail=dict(worker), now=now)
            (opened if new else restated).append(SIG_WORKER_STALLED)
        still = set(breached)
        if sched.get("stale"):
            still.add(SIG_SCHEDULER_STALE)
        if worker.get("stalled"):
            still.add(SIG_WORKER_STALLED)

        def _why(inc) -> str:
            if inc.signature == SIG_SCHEDULER_STALE:
                return (f"scheduler seen again {sched.get('age_s')}s ago via "
                        f"{sched.get('source')}")
            if inc.signature == SIG_WORKER_STALLED:
                return f"queue draining again: {worker.get('reason')}"
            key = inc.signature[len(SIG_BREACH):]
            r = report["slos"].get(key)
            if r is not None:
                return f"objective {r['state']}: sli={r['sli']} target={r['target']}"
            return "objective no longer breached on the latest evaluation"

        closed = life.reconcile(s, "slo.", lambda inc: inc.signature in still,
                                resolution=_why, now=now)
    report["incidents"] = {"opened": opened, "restated": restated,
                           "resolved": closed["resolved"]}
    return report


def _overall(report: dict) -> tuple[str, str]:
    states = [r["state"] for r in report["slos"].values()]
    if report["scheduler"].get("stale") or report["worker"].get("stalled"):
        return DEGRADED, "the scheduler is stale or the queue is not draining"
    if any(st == BREACHED for st in states):
        return DEGRADED, "one or more objectives are breached"
    if all(st == UNKNOWN for st in states):
        return UNKNOWN, "no objective has enough durable evidence to be judged"
    return OK, "every judged objective is met (UNKNOWN ones are listed as such)"


def summary(db) -> dict:
    """Lane I provider for the Command Center (contract: status/as_of/basis/items/sources)."""
    try:
        report = evaluate(db)
    except Exception as exc:  # noqa: BLE001 - never raise on the owner's page
        return {"status": UNKNOWN, "as_of": None, "basis": "unknown", "items": [],
                "sources": [], "reason": f"SLO evaluation failed: {type(exc).__name__}"}
    status, why = _overall(report)
    items: list[dict] = [{"kind": "slo", **r} for r in report["slos"].values()]
    items.append({"kind": "scheduler_liveness", **report["scheduler"]})
    items.append({"kind": "worker_liveness", **report["worker"]})
    items.extend({"kind": "department", **row} for row in report["departments"])
    sources = sorted({src for r in report["slos"].values() for src in r.get("sources", [])})
    try:
        from ..gateway import failover

        fo = failover.status(db)
        items.append({"kind": "model_failover", **fo})
        sources.append("audit_log(action=model.attempt|model.probe)")
    except Exception as exc:  # noqa: BLE001
        items.append({"kind": "model_failover", "status": UNKNOWN,
                      "reason": f"failover status unavailable: {type(exc).__name__}"})
    try:
        from ..autonomy import status as autonomy_status  # lane A, may not exist yet

        auto = autonomy_status.summary(db)
        items.append({"kind": "autonomy_departments", "status": auto.get("status", UNKNOWN),
                      "as_of": auto.get("as_of"), "count": len(auto.get("items") or [])})
        sources.extend(auto.get("sources") or [])
    except Exception:  # noqa: BLE001 - absence is tolerated by contract
        items.append({"kind": "autonomy_departments", "status": UNKNOWN,
                      "reason": "brambleloop.autonomy.status not built or failed"})
    measured = any(r["basis"] == "measured" for r in report["slos"].values())
    return {"status": status, "as_of": report["as_of"],
            "basis": "measured" if measured else "unknown", "reason": why, "items": items,
            "sources": sources,
            "definitions": [s.to_dict() for s in SLOS.values()]}


# ---------------------------------------------------------------------------
# The watchdog: run outside the main container (Railway cron service), or by hand.


def probe_url(url: str, *, timeout: float = 10.0, fetch=None) -> dict:
    """GET `url` once. `fetch(url, timeout) -> (status, body_bytes)` is injectable for tests."""
    import time

    started = time.time()
    try:
        if fetch is None:
            import urllib.request

            with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
                status, _body = resp.status, resp.read(2048)
        else:
            status, _body = fetch(url, timeout)
        ok = 200 <= int(status) < 300
        err = "" if ok else f"HTTP {status}"
    except Exception as exc:  # noqa: BLE001 - an unreachable surface is the reading
        status, ok, err = None, False, f"{type(exc).__name__}: {str(exc)[:160]}"
    return {"ok": ok, "status": status, "error": err,
            "latency_ms": round((time.time() - started) * 1000, 1)}


def watchdog(db, *, url: str | None, instance: str = "watchdog", fetch=None,
             now: datetime | None = None) -> dict:
    """One watchdog pass: probe the Command Center, heartbeat, check, prune. Idempotent."""
    now = _now(now)
    probe = None
    if url:
        probe = probe_url(url, fetch=fetch)
        record_probe(db, AVAILABILITY_COMPONENT, ok=probe["ok"],
                     latency_ms=probe["latency_ms"], instance=instance,
                     detail={"status": probe["status"], "error": probe["error"]}, now=now)
    record_heartbeat(db, "watchdog", instance=instance, now=now,
                     detail={"probed": bool(url)})
    report = check(db, now=now)
    pruned = prune_samples(db, now=now)
    return {"probe": probe, "incidents": report["incidents"],
            "status": _overall(report)[0], "pruned": pruned}


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - process entrypoint
    import json
    import sys

    from ..core.db import Database

    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] not in ("watchdog", "evaluate"):
        print("usage: python -m brambleloop.ops.slo watchdog|evaluate", file=sys.stderr)
        return 2
    db = Database()
    if args[0] == "evaluate":
        print(json.dumps(summary(db), default=str, indent=2))
        return 0
    url = (os.environ.get("BRAMBLELOOP_PUBLIC_HEALTH_URL") or "").strip() or None
    out = watchdog(db, url=url, instance=os.environ.get("RAILWAY_SERVICE_NAME", "watchdog"))
    print(json.dumps(out, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
