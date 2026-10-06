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

# #187: the three autonomy job types' bands are declared in swarm.orchestrate.JOB_BANDS
# (moved there by the v1.1 integrator wiring).


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
    # Results -> Laura (W3-D): a mission she delegated just closed; wake her review now.
    try:
        from ..laura.executive.loop import results_wake

        report["laura_woken"] = results_wake(ctx.db, ctx.queue, now=_now(ctx))
    except Exception:  # noqa: BLE001 - a failed wake never stops the company loop
        report["laura_woken"] = False
    return {"ran": True, "enqueued": report["created"],
            "missions": [m["key"] for m in report["missions"]],
            "approvals": [a["requirement_key"] for a in report["approvals"]],
            "states": {k: v.get("state") for k, v in report["departments"].items()},
            "errors": report["errors"], "reconciled": report["reconciled"],
            "laura_woken": report.get("laura_woken", False)}


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
    # Audit ddf9c6e H-1/M-1: a review is useful only when it found something the previous
    # one did not (content hash over the reading with timestamps/ids removed) or it routed a
    # lesson. Ten reviews of an unchanged department are one finding, not ten.
    content = kpis.content_hash(reading)
    prev_content = kpis.content_hash(previous[0]["body"]) if previous else None
    new_finding = 1 if content != prev_content else 0
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
    return {"ran": True, "department": dept, "snapshot": snap_key,
            "new_finding": new_finding, "content_hash": content,
            "kpis": {k: v["status"] for k, v in reading["kpis"].items()},
            "lessons_routed": lessons}


def build_brief(db, *, now: datetime, hours: int = 12) -> dict:
    """The morning handoff (F-896): what changed while nobody was watching."""
    from ..core import models as m
    from ..core.models import Job, JobStatus

    since = now - timedelta(hours=hours)
    with db.session() as s:
        # The brief's own runs and the KPI self-reviews measure the company; they are not
        # company work, and counting them made every brief differ from the last (H-1).
        done = [r for r in s.execute(select(Job.id, Job.job_type, Job.inputs, Job.outputs)
                                     .where(Job.status == JobStatus.DONE,
                                            Job.finished_at >= since)).all()
                if r.job_type not in kpis.SELF_MEASUREMENT_TYPES]
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
        e["useful"] += 0 if kpis.did_no_work(r.outputs, r.job_type) else 1
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
    # Audit ddf9c6e H-1: a brief is useful only when its content differs from the last one
    # (the window's timestamps excluded) -- an unchanged company yields an unchanged brief.
    previous = memory.recall(ctx.db, kind="morning_brief", limit=1)
    content = kpis.content_hash({k: v for k, v in brief.items() if k != "window"})
    prev_content = (kpis.content_hash({k: v for k, v in previous[0]["body"].items()
                                       if k != "window"}) if previous else None)
    new_brief = 1 if content != prev_content else 0
    memory.remember(ctx.db, key, kind="morning_brief", department="executive",
                    subject=f"Morning brief {day}", state="ready", body=brief,
                    sources=brief["sources"], now=now)
    memory.record_event(ctx.db, f"brief:{day}", kind="brief.ready", department="executive",
                        summary=(f"Morning brief {day}: {brief['completed_total']} jobs "
                                 f"completed, {brief['missions']['total']} missions, "
                                 f"{brief['decisions_needed']['open_owner_actions']} owner "
                                 f"decisions open"),
                        refs=[f"company_memory:{key}"], at=now)
    return {"ran": True, "brief": key, "new_brief": new_brief, "content_hash": content,
            "completed_total": brief["completed_total"]}


# W3-D: Laura's executive tick handler registers with the runtime here, because this module is
# the one the runtime already imports for the company loop.
from ..laura.executive import handlers as _laura_handlers  # noqa: E402,F401
# W3-D wiring: Visual R&D cycle (lane H) and the accountant period pack (closure K15).
from . import period_packs as _period_packs  # noqa: E402,F401
from . import visual_rnd_job as _visual_rnd_job  # noqa: E402,F401


def _declare_wired_work_keys() -> None:
    """Integrator wiring (W3 K3 via lane D): `listing.outcomes` is now a cadence, and every
    cadence declares its work keys. runtime/pipeline.WORK_KEYS is not lane D's file, so the
    declaration is made here until the requested line lands there (setdefault: the pipeline's
    own declaration wins once it exists)."""
    from ..runtime import pipeline as _pipeline

    _pipeline.WORK_KEYS.setdefault("listing.outcomes",
                                   ("exports_processed", "recorded_listings"))


try:
    _declare_wired_work_keys()
except Exception:  # noqa: BLE001 - pipeline not importable yet; the judge falls back safely
    pass

