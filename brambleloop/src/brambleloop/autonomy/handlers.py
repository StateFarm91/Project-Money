"""Job handlers for the autonomy package, registered on the runtime's handler registry.

All three are GREEN: they read durable rows and write company memory, the timeline, lessons,
idempotent jobs and deduplicated owner actions. None publishes, activates, spends or
messages anyone. Every write is keyed, so a handler re-run after its worker was killed and
its lease reclaimed leaves exactly the rows a single run would have left.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..runtime.worker import JobContext, handlers
from . import charters, kpis, memory, orchestrator
from .generators import morning_window

# #187: every runnable job type has a band somebody decided. The orchestrator is liveness --
# "is the company actually working" is the system's claim about itself, the same band as
# ops.heartbeat / ops.health. Reviews and the brief are housekeeping. WIRING REQUEST: move
# these three literals into swarm.orchestrate.JOB_BANDS; until then they are declared here,
# at import, before anything can enqueue them.
from ..swarm import orchestrate as _swarm

for _jt, _kind in (("autonomy.orchestrate", "truth_defect"),
                   ("autonomy.department_review", "housekeeping"),
                   ("autonomy.morning_handoff", "housekeeping")):
    _swarm.JOB_BANDS.setdefault(_jt, _kind)


def _now(ctx: JobContext) -> datetime:
    """The job's clock: `inputs.now` lets a simulation advance time; otherwise wall time."""
    raw = (ctx.job.inputs or {}).get("now")
    if raw:
        try:
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


@handlers.register(orchestrator.ORCHESTRATE_JOB)
def handle_orchestrate(ctx: JobContext) -> dict:
    report = orchestrator.tick(ctx.db, ctx.queue, now=_now(ctx))
    return {"ran": True, "enqueued": report["created"],
            "missions": [m["key"] for m in report["missions"]],
            "approvals": [a["requirement_key"] for a in report["approvals"]],
            "states": {k: v.get("state") for k, v in report["departments"].items()},
            "errors": report["errors"], "reconciled": report["reconciled"]}


def _lesson(ctx: JobContext, dept: str, subject: str, statement: str, evidence_ref: str,
            now: datetime) -> bool:
    """A routed Lesson row (consumed by improve.consume / Learn), deduplicated on evidence."""
    from ..core.models import Lesson

    with ctx.db.session() as s:
        if s.scalar(select(Lesson.id).where(Lesson.evidence_ref == evidence_ref)) is not None:
            return False
        s.add(Lesson(origin_cell=dept[:40], subject=subject[:80], statement=statement,
                     evidence_ref=evidence_ref[:200], confidence="observed",
                     routed_to=["learn", dept]))
    memory.remember(ctx.db, f"lesson:{evidence_ref}"[:200], kind="lesson", department=dept,
                    subject=subject, state="routed",
                    body={"statement": statement, "routed_to": ["learn", dept]},
                    sources=[evidence_ref], now=now)
    memory.record_event(ctx.db, f"lesson:{evidence_ref}"[:200], kind="lesson.routed",
                        department=dept, summary=f"{subject}: {statement}"[:500],
                        refs=[evidence_ref], at=now)
    return True


@handlers.register("autonomy.department_review")
def handle_department_review(ctx: JobContext) -> dict:
    """Measure one department's KPIs, persist the snapshot, route lessons on regression."""
    now = _now(ctx)
    dept = (ctx.job.inputs or {}).get("department")
    if dept not in charters.BY_KEY:
        from ..core.resilience import PermanentError

        raise PermanentError(f"unknown department {dept!r}")
    reading = kpis.compute(ctx.db, dept, now=now)
    previous = memory.recall(ctx.db, kind="kpi_snapshot", department=dept, limit=1)
    snap_key = f"kpi:{dept}:{(ctx.job.inputs or {}).get('mission') or ctx.job.id}"[:200]
    memory.remember(ctx.db, snap_key, kind="kpi_snapshot", department=dept,
                    subject=f"{charters.BY_KEY[dept].name} KPIs", state="measured",
                    body=reading, sources=[f"jobs:{ctx.job.id}", *reading["sources"]],
                    now=now)
    lessons = 0
    if reading["guardrails"]["tripped"]:
        lessons += _lesson(ctx, dept, "guardrail tripped",
                           "KPIs VOID: " + "; ".join(reading["guardrails"]["breaches"][:3]),
                           f"company_memory:{snap_key}:guardrail", now)
    if previous and previous[0]["key"] != snap_key:
        before = previous[0]["body"].get("counted", {})
        after = reading["counted"]
        if after.get("defects", 0) > before.get("defects", 0):
            lessons += _lesson(
                ctx, dept, "defect dead letters rising",
                f"{dept}: defect dead letters {before.get('defects', 0)} -> "
                f"{after['defects']} between snapshots",
                f"company_memory:{snap_key}:defects", now)
        if before.get("useful_distinct", 0) > 0 and after.get("useful_distinct", 0) == 0 \
                and after.get("finished", 0) > 0:
            lessons += _lesson(
                ctx, dept, "useful output stopped",
                f"{dept}: {after['finished']} job(s) finished with no useful output after "
                f"{before['useful_distinct']} useful in the previous window",
                f"company_memory:{snap_key}:useful", now)
    memory.record_event(ctx.db, f"kpi:{snap_key}", kind="kpi.measured", department=dept,
                        actor="coo",
                        summary=(f"{charters.BY_KEY[dept].name}: "
                                 + ", ".join(f"{k}={v['status']}:{v['value']}"
                                             for k, v in reading["kpis"].items())),
                        refs=[f"company_memory:{snap_key}"], at=now)
    return {"ran": True, "department": dept, "snapshot": snap_key, "generated": 1,
            "kpis": {k: v["status"] for k, v in reading["kpis"].items()},
            "lessons_routed": lessons}


def build_brief(db, *, now: datetime, hours: int = 12) -> dict:
    """The morning handoff (F-896): what changed while nobody was watching."""
    from ..core import models as m
    from ..core.models import Job, JobStatus

    since = now - timedelta(hours=hours)
    with db.session() as s:
        done = list(s.execute(select(Job.id, Job.job_type, Job.inputs, Job.outputs)
                              .where(Job.status == JobStatus.DONE,
                                     Job.finished_at >= since)).all())
        dead = list(s.execute(select(Job.id, Job.job_type, Job.last_error)
                              .where(Job.status == JobStatus.DEAD,
                                     Job.finished_at >= since)).all())
        cost_rows, cost_sum = s.execute(
            select(func.count(), func.coalesce(func.sum(m.CostEntry.amount_cad), 0.0))
            .where(m.CostEntry.at >= since)).one()
        incidents = list(s.execute(select(m.Incident.id, m.Incident.severity,
                                          m.Incident.summary)
                                   .where(m.Incident.at >= since)
                                   .order_by(m.Incident.id.desc()).limit(10)).all())
        owner = list(s.execute(select(m.OwnerAction.id, m.OwnerAction.action,
                                      m.OwnerAction.requirement_key)
                               .where(m.OwnerAction.done == False)  # noqa: E712
                               .order_by(m.OwnerAction.id.desc()).limit(10)).all())
        owner_total = s.scalar(select(func.count()).select_from(m.OwnerAction).where(
            m.OwnerAction.done == False)) or 0  # noqa: E712
    by_dept: dict[str, dict] = {}
    for r in done:
        d = kpis.job_department(r.job_type, r.inputs) or "unassigned"
        e = by_dept.setdefault(d, {"completed": 0, "useful": 0, "generated": 0})
        e["completed"] += 1
        e["useful"] += 0 if kpis.did_no_work(r.outputs) else 1
        e["generated"] += 1 if (r.inputs or {}).get("source") == "autonomy" else 0
    missions = memory.recall(db, kind="mission", since=since, limit=500)
    blocks = [b for b in memory.recall(db, kind="block", state="active", limit=50)]
    return {
        "window": {"from": since.isoformat(), "to": now.isoformat(), "hours": hours},
        "completed_by_department": by_dept,
        "completed_total": len(done),
        "missions": {"total": len(missions),
                     "by_outcome": {st: sum(1 for x in missions if x["state"] == st)
                                    for st in ("queued", "useful", "noop", "failed")}},
        "dead_letters": [{"job_id": r.id, "job_type": r.job_type,
                          "error": (r.last_error or "")[:160]} for r in dead[:10]],
        "spend": {"amount_cad": round(float(cost_sum), 4), "rows": int(cost_rows),
                  "basis": "measured" if cost_rows else "unknown",
                  "note": ("sum of cost_entries in the window" if cost_rows else
                           "no cost_entries rows in the window; not rendered as CA$0.00")},
        "incidents": [{"id": i.id, "severity": i.severity, "summary": i.summary[:160]}
                      for i in incidents],
        "decisions_needed": {"open_owner_actions": int(owner_total),
                             "top": [{"id": o.id, "action": o.action[:200],
                                      "key": o.requirement_key} for o in owner]},
        "blocked_departments": [{"department": b["department"],
                                 "reason": b["body"].get("reason")} for b in blocks],
        "sources": ["jobs", "cost_entries", "incidents", "owner_actions", "company_memory"],
    }


@handlers.register("autonomy.morning_handoff")
def handle_morning_handoff(ctx: JobContext) -> dict:
    now = _now(ctx)
    day = morning_window(now)
    brief = build_brief(ctx.db, now=now)
    key = f"brief:{day}"
    memory.remember(ctx.db, key, kind="morning_brief", department="executive",
                    subject=f"Morning brief {day}", state="ready", body=brief,
                    sources=brief["sources"], now=now)
    memory.record_event(ctx.db, f"brief:{day}", kind="brief.ready", department="executive",
                        summary=(f"Morning brief {day}: {brief['completed_total']} jobs "
                                 f"completed, {brief['missions']['total']} missions, "
                                 f"{brief['decisions_needed']['open_owner_actions']} owner "
                                 f"decisions open"),
                        refs=[f"company_memory:{key}"], at=now)
    return {"ran": True, "brief": key, "generated": 1,
            "completed_total": brief["completed_total"]}
