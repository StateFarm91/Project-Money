"""F-089: the Physical Truth Dashboard -- one row per Class B/C product.

For every product that needs a real sample before release, the row says who is testing it,
which version, the stage it is at, when it is due, what the sample found, how far the measured
yarn and size were from the twin's prediction, and whether launch is blocked on it.

Sources, both durable:
* the latest `quality.tester_plan` audit (written by the release lane's planning job):
  demands with risk class, needed_by and must_start_by, assignments and unassigned demands;
* `physical_tests` rows: what testers actually made.

A Class B/C product is `launch_blocked` until a sample of it has *passed*. A failed sample is
recorded as a finding, never as a pass, and an unknown stage is never shown as done.
"""
from __future__ import annotations

from datetime import date

from .testers import NEEDS_SAMPLE

PLAN_ACTION = "quality.tester_plan"


def _latest_plan(db) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == PLAN_ACTION)
                       .order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(1))
        return {"detail": dict(row.detail or {}), "at": row.at.isoformat()} if row else {}


def _deltas(measured: dict) -> dict:
    est = measured.get("estimated_metres") or {}
    got = measured.get("measured_metres") or {}
    yarn = {c: round(float(got[c]) / float(est[c]) - 1.0, 3)
            for c in sorted(set(est) & set(got)) if float(est[c] or 0) > 0}
    return {"yarn_by_colour": yarn, "factor": measured.get("factor"),
            "size_agrees": measured.get("size_agrees")}


def _stage(t) -> str:
    if t is None:
        return "not_started"
    if t.completed_at is None:
        return "in_progress"
    if t.passed is True:
        return "passed"
    if t.passed is False:
        return "failed"
    return "completed_unknown"


def dashboard(db, *, today: date | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import PhysicalTest

    today = today or date.today()
    plan = _latest_plan(db)
    d = plan.get("detail") or {}
    demands = {r["product_slug"]: r for r in d.get("demands") or [] if r.get("product_slug")}
    assigned = {a["product_slug"]: a for a in d.get("assignments") or []}
    unassigned = {u["product_slug"]: u for u in d.get("unassigned") or []}
    with db.session() as s:
        tests = list(s.scalars(select(PhysicalTest).order_by(PhysicalTest.id)))
    by_slug: dict[str, list] = {}
    for t in tests:
        by_slug.setdefault(t.product_slug, []).append(t)

    rows = []
    for slug in sorted(set(demands) | set(by_slug)):
        dem = demands.get(slug) or {}
        ts = by_slug.get(slug, [])
        # Review F-9: a demand with no risk class and no test reads "unknown", never a 500.
        risk = dem.get("risk_class") or ((ts[-1].measured or {}).get("risk_class")
                                         if ts else None)
        latest = ts[-1] if ts else None
        passed_any = any(t.passed is True for t in ts)
        if risk is not None and risk not in NEEDS_SAMPLE:
            continue
        m = (latest.measured or {}) if latest else {}
        tester = (latest.tester_ref if latest else None) or (assigned.get(slug) or {}).get("tester")
        due = dem.get("needed_by")
        try:
            overdue = (bool(due) and not passed_any and date.fromisoformat(str(due)) < today)
            due_why = None
        except ValueError:
            overdue, due_why = None, f"needed_by {due!r} is not an ISO date"
        rows.append({
            "product_slug": slug,
            "risk_class": risk or "unknown",
            "version": latest.version if latest else None,
            "tester": tester,
            "assignment": ("recorded" if latest else "planned" if slug in assigned
                           else "unassigned"),
            "unassigned_why": (unassigned.get(slug) or {}).get("why"),
            "stage": _stage(latest),
            "samples": len(ts),
            "due": due,
            "must_start_by": dem.get("must_start_by"),
            "overdue": overdue,
            "overdue_why": due_why,
            "findings": m.get("findings") or [],
            "notes": (latest.notes[:300] if latest and latest.notes else ""),
            "deltas": _deltas(m) if latest else None,
            # Unknown risk is treated as needing a sample: never released by default.
            "launch_blocked": not passed_any,
        })
    blocked = [r["product_slug"] for r in rows if r["launch_blocked"]]
    return {
        "as_of": today.isoformat(),
        "plan_recorded_at": plan.get("at"),
        "rows": rows,
        "summary": {"products": len(rows), "launch_blocked": len(blocked),
                    "passed": sum(1 for r in rows if not r["launch_blocked"]),
                    "unassigned": sum(1 for r in rows if r["assignment"] == "unassigned"),
                    "overdue": sum(1 for r in rows if r["overdue"]),
                    "overdue_unknown": sum(1 for r in rows if r["overdue"] is None)},
        "note": ("no tester plan has been recorded yet; rows come from physical_tests alone"
                 if not plan else
                 "Class B/C products only; launch_blocked until a sample of the product has "
                 "passed (a failed sample is a finding, not a pass)"),
    }
