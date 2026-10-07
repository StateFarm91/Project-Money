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


# ---------------------------------------------------------------------------------------------
# W4-AUTO: per-agent visibility (Rule #1). One row per registered agent: what it is doing now,
# what it last produced (judged by the one useful-work judge), what blocks it, what it will do
# next and when it wakes, its useful/no-op rates and recorded cost. Read-only; never raises.

AGENT_WINDOW_HOURS = 24
AGENT_LOOKBACK_DAYS = 14
UNHEALTHY_DEAD_SHARE = 0.5


def _agent_department(name: str, job_types: list[str]) -> str | None:
    from . import charters

    for ch in charters.CHARTERS:
        if name in ch.agents:
            return ch.key
    seen: dict[str, int] = {}
    for jt in job_types:
        d = charters.department_of(jt)
        if d:
            seen[d] = seen.get(d, 0) + 1
    return max(seen, key=seen.get) if seen else None


def _produced(outputs: dict, job_type: str) -> dict:
    """What a completed job produced or rejected, from its declared work keys (no guessing)."""
    from ..runtime.pipeline import WORK_KEYS

    outputs = outputs or {}
    keys = list(WORK_KEYS.get(job_type) or ())
    produced = {k: outputs.get(k) for k in keys if k in outputs}
    rejected = {k: outputs[k] for k in ("rejected", "refused", "refusals", "not_promoted",
                                        "blocked", "reason") if outputs.get(k)}
    if not produced:
        produced = {k: v for k, v in outputs.items()
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and v}
    trim = lambda d: {k: (v if isinstance(v, (int, float, bool)) or v is None  # noqa: E731
                          else (str(v)[:160])) for k, v in list(d.items())[:8]}
    return {"produced": trim(produced), "rejected": trim(rejected)}


def agents(db, *, now: datetime | None = None) -> dict:
    """Per-agent visibility envelope {status, as_of, basis, items, sources}. Never raises."""
    try:
        return _agents(_db(db), now=now or _now())
    except Exception as exc:  # noqa: BLE001 - a provider never raises
        return _unknown(f"agent status unreadable: {type(exc).__name__}: {exc}"[:300],
                        provider="brambleloop.autonomy.status.agents")


def _agents(db, *, now: datetime) -> dict:
    from ..agents.registry import DEFAULT_AGENTS
    from ..core.models import CostEntry, Job, JobStatus
    from ..runtime.worker import CADENCES
    from . import charters, memory
    from .kpis import did_no_work
    from .models import ensure_tables

    ensure_tables(db)
    since = now - timedelta(hours=AGENT_WINDOW_HOURS)
    back = now - timedelta(days=AGENT_LOOKBACK_DAYS)
    with db.session() as s:
        total_jobs = s.scalar(select(func.count()).select_from(Job)) or 0
        live = list(s.execute(select(Job.id, Job.agent, Job.job_type, Job.status,
                                     Job.started_at, Job.run_after, Job.inputs,
                                     Job.last_error, Job.attempts)
                              .where(Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING,
                                                     JobStatus.FAILED]))).all())
        recent = list(s.execute(select(Job.id, Job.agent, Job.job_type, Job.status,
                                       Job.outputs, Job.finished_at, Job.last_error,
                                       Job.cost_cad)
                                .where(Job.finished_at >= back)
                                .order_by(Job.finished_at.desc()).limit(20000)).all())
        cost_rows = dict(s.execute(select(CostEntry.agent, func.sum(CostEntry.amount_cad))
                                   .where(CostEntry.at >= since)
                                   .group_by(CostEntry.agent)).all())
        cost_any = s.scalar(select(func.count()).select_from(CostEntry)) or 0
    if not total_jobs:
        return _unknown("no jobs have ever been recorded; no agent has run here",
                        provider="brambleloop.autonomy.status.agents")
    last_tick = memory.get(db, "orchestrator:last_tick")
    states = (last_tick or {}).get("body", {}).get("states", {})
    gates: dict = {}
    try:
        from ..build2.executor import gate_states

        gates = gate_states(db)
    except Exception:  # noqa: BLE001
        gates = {}

    items = []
    counts = {"active": 0, "sleeping": 0, "blocked": 0, "unhealthy": 0}
    for a in DEFAULT_AGENTS:
        name = a["name"]
        allowed = list(a.get("allowed_job_types") or [])
        dept = _agent_department(name, allowed)
        mine_live = [r for r in live if r.agent == name]
        running = [r for r in mine_live if getattr(r.status, "value", r.status) == "running"]
        pending = sorted([r for r in mine_live
                          if getattr(r.status, "value", r.status) in ("pending", "failed")],
                         key=lambda r: _aware(r.run_after) or now)
        mine = [r for r in recent if r.agent == name]
        window = [r for r in mine if _aware(r.finished_at) and _aware(r.finished_at) >= since]
        done_w = [r for r in window if getattr(r.status, "value", r.status) == "done"]
        dead_w = [r for r in window if getattr(r.status, "value", r.status) == "dead"]
        useful_w = [r for r in done_w if not did_no_work(r.outputs, r.job_type)]
        last_useful = next((r for r in mine if getattr(r.status, "value", r.status) == "done"
                            and not did_no_work(r.outputs, r.job_type)), None)
        last_any = mine[0] if mine else None
        cadences = [(n, jt, p) for n, ag, jt, p in CADENCES if ag == name]
        nxt = None
        for _n, _jt, p in cadences:
            t = (int(now.timestamp() // p) + 1) * p
            nxt = t if nxt is None else min(nxt, t)
        next_wake = datetime.fromtimestamp(nxt, tz=timezone.utc) if nxt else None
        if pending:
            ra = _aware(pending[0].run_after) or now
            next_wake = min(next_wake, ra) if next_wake else ra
        trigger = ("pending job" if pending else
                   f"cadence {min(cadences, key=lambda c: c[2])[0]}" if cadences else
                   "orchestrator mission / follow-on only")
        blockers = []
        block = memory.active_block(db, dept, now=now) if dept else None
        if block:
            blockers.append({"kind": "department_block",
                             "reason": block["body"].get("reason")})
        ch = charters.BY_KEY.get(dept) if dept else None
        for g in (ch.gates if ch else ()):
            if g in gates and not gates[g].get("open"):
                blockers.append({"kind": "owner_gate", "gate": g,
                                 "what": str(gates[g].get("what") or "")[:160]})
        if dead_w and not useful_w:
            blockers.append({"kind": "dead_letters",
                             "error": (dead_w[0].last_error or "").splitlines()[0][:200]
                             if dead_w[0].last_error else ""})
        n_done = len(done_w)
        useful_rate = round(len(useful_w) / n_done, 4) if n_done else None
        if running:
            state = "active"
        elif block:
            state = "blocked"
        elif window and len(dead_w) / len(window) >= UNHEALTHY_DEAD_SHARE and not useful_w:
            state = "unhealthy"
        else:
            state = "sleeping"
        counts[state] += 1
        cur = running[0] if running else None
        cost = cost_rows.get(name)
        items.append({
            "agent": name, "department": dept,
            "authority": getattr(a.get("authority"), "value", str(a.get("authority"))),
            "state": state,
            "doing_now": (f"{cur.job_type} (job {cur.id})" if cur else None),
            "started_at": (_aware(cur.started_at).isoformat()
                           if cur and cur.started_at else None),
            "current_job": ({"id": cur.id, "job_type": cur.job_type,
                             "reason": str((cur.inputs or {}).get("reason")
                                           or (cur.inputs or {}).get("cadence") or "")[:200]}
                            if cur else None),
            "last_useful_result": ({"job_id": last_useful.id,
                                    "job_type": last_useful.job_type,
                                    "at": _aware(last_useful.finished_at).isoformat(),
                                    **_produced(last_useful.outputs, last_useful.job_type)}
                                   if last_useful else None),
            "last_run": ({"job_id": last_any.id, "job_type": last_any.job_type,
                          "status": getattr(last_any.status, "value", str(last_any.status)),
                          "useful": (getattr(last_any.status, "value", "") == "done"
                                     and not did_no_work(last_any.outputs,
                                                         last_any.job_type)),
                          "at": _aware(last_any.finished_at).isoformat()}
                         if last_any else None),
            "blockers": blockers,
            "next_work": [{"job_id": r.id, "job_type": r.job_type,
                           "run_after": (_aware(r.run_after).isoformat()
                                         if r.run_after else None),
                           "why": str((r.inputs or {}).get("reason")
                                      or (r.inputs or {}).get("cadence") or "")[:160]}
                          for r in pending[:3]],
            "orchestrator_state": states.get(dept) if dept else None,
            "next_wake": next_wake.isoformat() if next_wake else None,
            "trigger": trigger,
            "window_hours": AGENT_WINDOW_HOURS,
            "completed": n_done, "useful": len(useful_w), "noop": n_done - len(useful_w),
            "dead": len(dead_w),
            "useful_rate": useful_rate,
            "noop_rate": round(1 - useful_rate, 4) if useful_rate is not None else None,
            "rates_basis": "measured" if n_done else "unknown",
            "cost_cad_24h": ({"value_cad": round(float(cost), 4), "state": "RECORDED",
                              "display": f"CA${float(cost):.2f} (recorded)"}
                             if cost is not None else
                             {"value_cad": 0.0 if cost_any else None,
                              "state": "RECORDED" if cost_any else "UNKNOWN",
                              "display": "CA$0.00 (recorded)" if cost_any else "UNKNOWN"}),
            "as_of": now.isoformat(),
        })
    items.sort(key=lambda i: (i["department"] or "~", i["agent"]))
    overall = "DEGRADED" if counts["unhealthy"] else "OK"
    return {"status": overall, "as_of": now.isoformat(), "basis": "measured",
            "items": items, "counts": counts,
            "judge": "runtime.pipeline.did_no_work (per-job-type WORK_KEYS)",
            "provider": "brambleloop.autonomy.status.agents",
            "sources": ["jobs", "cost_entries", "company_memory", "worker.CADENCES",
                        "agents.registry.DEFAULT_AGENTS", "build2.executor.gate_states"]}
