"""Provider for the Owner Command Center (lane C contract).

`summary(db)`  -- departments with state, last run, next wake, blockers, KPIs; the
                 orchestrator's last tick; overnight work (latest morning brief).
`timeline(db, limit=50)` -- the company timeline (F-927): this package's own events merged
                 with incidents, owner actions, spend and orchestrator-relevant job outcomes,
                 each labelled with its source table.

Both return {"status", "as_of", "basis", "items", "sources", ...} and never raise on an
empty or partial database: anything unreadable is UNKNOWN with a reason.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

STATUSES = ("OK", "DEGRADED", "BLOCKED", "UNKNOWN")
ORCHESTRATOR_STALE_MINUTES = 45


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _db(db):
    """Accept a Database or a SQLAlchemy Session (the contract says Session)."""
    from ..core.db import Database

    if isinstance(db, Database):
        return db
    bind = db.get_bind() if hasattr(db, "get_bind") else None

    class _Wrap(Database):
        def __init__(self, engine):  # noqa: D401 - thin adapter
            from sqlalchemy.orm import sessionmaker

            self.engine = engine
            self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    return _Wrap(bind)


def _unknown(reason: str, **extra) -> dict:
    return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
            "sources": [], "reason": reason, **extra}


def _next_wake(job_types: set[str], now: datetime) -> str | None:
    from ..runtime.worker import CADENCES

    best = None
    for _n, _a, jt, period in CADENCES:
        if jt in job_types:
            nxt = (int(now.timestamp() // period) + 1) * period
            best = nxt if best is None else min(best, nxt)
    # The orchestrator wakes every department at least every fifteen minutes.
    orch = (int(now.timestamp() // 900) + 1) * 900
    best = orch if best is None else min(best, orch)
    return datetime.fromtimestamp(best, tz=timezone.utc).isoformat()


def summary(db, *, now: datetime | None = None) -> dict:
    try:
        return _summary(_db(db), now=now or _now())
    except Exception as exc:  # noqa: BLE001 - a provider never raises
        return _unknown(f"autonomy status unreadable: {type(exc).__name__}: {exc}"[:300])


def _summary(db, *, now: datetime) -> dict:
    from ..core.models import Job, JobStatus
    from ..runtime.worker import CADENCES
    from . import charters, memory
    from .kpis import did_no_work, job_department
    from .models import ensure_tables

    ensure_tables(db)
    since = now - timedelta(hours=24)
    with db.session() as s:
        total_jobs = s.scalar(select(func.count()).select_from(Job)) or 0
        recent = list(s.execute(select(Job.job_type, Job.inputs, Job.outputs, Job.status,
                                       Job.finished_at)
                                .where(Job.finished_at >= since)).all())
        open_rows = list(s.execute(select(Job.job_type, Job.inputs).where(
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED]))).all())
        last_any = dict(s.execute(select(Job.job_type, func.max(Job.finished_at))
                                  .group_by(Job.job_type)).all())
    if not total_jobs:
        return _unknown("no jobs have ever been recorded; the runtime has not run here",
                        departments=[c.key for c in charters.CHARTERS])

    last_tick = memory.get(db, "orchestrator:last_tick")
    tick_at = _aware(datetime.fromisoformat(last_tick["body"]["at"])) if last_tick else None
    states = (last_tick or {}).get("body", {}).get("states", {})
    errors = (last_tick or {}).get("body", {}).get("errors", {})

    gates: dict = {}
    try:
        from ..build2.executor import gate_states

        gates = gate_states(db)
    except Exception:  # noqa: BLE001 - gates unreadable: say so per department
        gates = {}

    items = []
    for ch in charters.CHARTERS:
        mine = [r for r in recent if job_department(r.job_type, r.inputs) == ch.key]
        done = [r for r in mine if getattr(r.status, "value", r.status) == "done"]
        useful = [r for r in done if not did_no_work(r.outputs, r.job_type)]
        dead = [r for r in mine if getattr(r.status, "value", r.status) == "dead"]
        n_open = sum(1 for jt, inp in open_rows if job_department(jt, inp) == ch.key
                     and jt != "autonomy.orchestrate")
        types = {jt for _n, _a, jt, _p in CADENCES if charters.department_of(jt) == ch.key}
        types |= set(ch.generatable)
        last_run = max((_aware(last_any[t]) for t in last_any
                        if charters.department_of(t) == ch.key and last_any[t]),
                       default=None)
        block = memory.active_block(db, ch.key, now=now)
        blockers = []
        if block:
            blockers.append({"kind": "department_block", "reason": block["body"].get("reason"),
                             "owner_action": block["body"].get("owner_action")})
        closed = [g for g in ch.gates if g in gates and not gates[g].get("open")]
        for g in closed:
            blockers.append({"kind": "owner_gate", "gate": g,
                             "what": gates[g].get("what"),
                             "effect": "gated capability parked; READY work continues"})
        if ch.key in errors:
            blockers.append({"kind": "generation_error", "error": errors[ch.key]})
        if block:
            status = "BLOCKED"
        elif ch.key in errors or (dead and not useful):
            status = "DEGRADED"
        elif not mine and not n_open:
            status = "UNKNOWN"
        else:
            status = "OK"
        items.append({
            "department": ch.key, "name": ch.name, "status": status,
            "orchestrator_state": states.get(ch.key),
            "open_jobs": n_open, "completed_24h": len(done), "useful_24h": len(useful),
            "dead_24h": len(dead),
            "last_run": last_run.isoformat() if last_run else None,
            "next_wake": _next_wake(types, now),
            "blockers": blockers,
            "gates_unknown": not gates,
        })

    stale = tick_at is None or (now - tick_at) > timedelta(minutes=ORCHESTRATOR_STALE_MINUTES)
    overall = "OK"
    if stale or any(i["status"] == "DEGRADED" for i in items):
        overall = "DEGRADED"
    briefs = memory.recall(db, kind="morning_brief", limit=1)
    overnight = memory.recall(db, kind="mission", since=now - timedelta(hours=12), limit=500)
    return {
        "status": overall, "as_of": now.isoformat(), "basis": "measured",
        "items": items,
        "orchestrator": {"last_tick": tick_at.isoformat() if tick_at else None,
                         "stale": stale,
                         "stale_after_minutes": ORCHESTRATOR_STALE_MINUTES,
                         "last_created": (last_tick or {}).get("body", {}).get("created")},
        "overnight": {"missions_12h": len(overnight),
                      "by_outcome": {st: sum(1 for m in overnight if m["state"] == st)
                                     for st in ("queued", "useful", "noop", "failed")},
                      "latest_brief": briefs[0] if briefs else None},
        "timeline": timeline(db, limit=20, now=now)["items"],
        "sources": ["jobs", "company_memory", "company_timeline", "worker.CADENCES",
                    "build2.executor.gate_states"],
    }


def timeline(db, limit: int = 50, *, now: datetime | None = None) -> dict:
    try:
        return _timeline(_db(db), limit=limit, now=now or _now())
    except Exception as exc:  # noqa: BLE001
        return _unknown(f"timeline unreadable: {type(exc).__name__}: {exc}"[:300])


SIGNIFICANT_JOB_TYPES = ("store.publish", "store.activate", "gate.certify",
                         "finance.reconcile", "ops.continuity", "ops.offsite_archive",
                         "autonomy.morning_handoff")


def _timeline(db, *, limit: int, now: datetime) -> dict:
    from ..core import models as m
    from . import memory
    from .models import ensure_tables

    ensure_tables(db)
    items = [{**e, "source": "company_timeline"} for e in memory.events(db, limit=limit)]
    with db.session() as s:
        for i in s.scalars(select(m.Incident).order_by(m.Incident.at.desc()).limit(limit)):
            items.append({"at": _aware(i.at).isoformat(), "kind": "incident",
                          "department": "", "severity": i.severity,
                          "summary": (i.summary or i.signature)[:300],
                          "refs": [f"incidents:{i.id}"], "source": "incidents"})
        for o in s.scalars(select(m.OwnerAction).order_by(m.OwnerAction.at.desc())
                           .limit(limit)):
            items.append({"at": _aware(o.at).isoformat(),
                          "kind": "approval.done" if o.done else "approval.open",
                          "department": "", "severity": "decision",
                          "summary": o.action[:300], "refs": [f"owner_actions:{o.id}"],
                          "source": "owner_actions"})
        for c in s.scalars(select(m.CostEntry).where(m.CostEntry.amount_cad > 0)
                           .order_by(m.CostEntry.at.desc()).limit(limit)):
            items.append({"at": _aware(c.at).isoformat(), "kind": "spend",
                          "department": c.department or "", "severity": "info",
                          "summary": f"CA${c.amount_cad:.4f} {c.provider} {c.purpose}"
                                     f" ({c.agent})", "refs": [f"cost_entries:{c.id}"],
                          "source": "cost_entries", "basis": "measured"})
        for j in s.scalars(select(m.Job).where(m.Job.job_type.in_(SIGNIFICANT_JOB_TYPES),
                                                m.Job.finished_at.is_not(None))
                           .order_by(m.Job.finished_at.desc()).limit(limit)):
            st = getattr(j.status, "value", str(j.status))
            items.append({"at": _aware(j.finished_at).isoformat(), "kind": f"job.{st}",
                          "department": "", "severity": "warn" if st == "dead" else "info",
                          "summary": f"{j.job_type} {st}", "refs": [f"jobs:{j.id}"],
                          "source": "jobs"})
    items.sort(key=lambda x: x["at"], reverse=True)
    items = items[:limit]
    if not items:
        return _unknown("no timeline events recorded yet")
    return {"status": "OK", "as_of": items[0]["at"], "basis": "measured", "items": items,
            "sources": ["company_timeline", "incidents", "owner_actions", "cost_entries",
                        "jobs"]}
