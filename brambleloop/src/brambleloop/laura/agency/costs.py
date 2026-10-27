"""What Business Laura costs, per conversation, decision, delegated task and successful outcome
(W4-LAURACEO; ADD-LCEO-06).

The ledger (`cost_entries`) stays the single source of money truth: every model call Laura
makes is billed there by the gateway (agent `laura`, purpose = prompt ref), and every model or
image call a delegated job makes is billed there with that job's id. This module only
*attributes* those rows to Laura's units of work in `laura_cost_events`:

* conversation  one row per Command Center turn: what that turn's call billed (or 0.0 with
                basis `not_called` when no model was called -- a real, measured zero);
* decision      one row per executive tick that asked the model to order its priorities;
* delegation    one row per delegated mission when it is reviewed: the ledger spend
                attributed to its job id;
* outcome       the review verdict (useful / noop / failed) with the same job cost, so the
                cost per *successful* outcome is a query.

A figure that cannot be measured is stored with `measured=False` and reported as UNKNOWN,
never as CA$0.00. References and money only: no question, answer or private text.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

TARGET_MONTH_CAD = (10.0, 15.0)          # ADD-LCEO-06 routine conversation target
LAURA_PURPOSES = ("laura.converse@1", "laura.executive@1", "laura.exec_rank@1")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def record(db, kind: str, ref: str, *, cost_cad: float | None, basis: str, model: str = "",
           purpose: str = "", outcome: str = "", detail: dict | None = None,
           at: datetime | None = None) -> dict:
    from .models import LauraCostEvent, ensure_tables

    ensure_tables(db)
    measured = cost_cad is not None
    with db.session() as s:
        row = LauraCostEvent(kind=kind[:20], ref=ref[:200], cost_cad=float(cost_cad or 0.0),
                             measured=measured, basis=basis[:120], model=(model or "")[:120],
                             purpose=(purpose or "")[:80], outcome=(outcome or "")[:20],
                             detail=dict(detail or {}), at=at or _now())
        s.add(row)
        s.flush()
        return {"id": row.id, "kind": row.kind, "ref": row.ref,
                "cost_cad": round(row.cost_cad, 6) if measured else None,
                "basis": row.basis}


def exists(db, kind: str, ref: str) -> bool:
    from .models import LauraCostEvent, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        return s.scalar(select(LauraCostEvent.id).where(
            LauraCostEvent.kind == kind, LauraCostEvent.ref == ref[:200]).limit(1)) is not None


def job_cost(db, job_id) -> tuple[float | None, int]:
    """(CA$, ledger rows) the ledger attributes to one job. None when the job id is unknown."""
    from ...core.models import CostEntry, Job

    try:
        jid = int(job_id)
    except (TypeError, ValueError):
        return None, 0
    with db.session() as s:
        if s.get(Job, jid) is None:
            return None, 0
        n = s.scalar(select(func.count(CostEntry.id)).where(CostEntry.job_id == jid)) or 0
        total = s.scalar(select(func.coalesce(func.sum(CostEntry.amount_cad), 0.0))
                         .where(CostEntry.job_id == jid)) or 0.0
    return round(float(total), 6), int(n)


def laura_month(db, now: datetime | None = None) -> dict:
    """Laura's own model spend this calendar month, from the ledger, by purpose."""
    from ...core.models import CostEntry

    now = now or _now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with db.session() as s:
        rows = list(s.execute(select(CostEntry.purpose, func.count(CostEntry.id),
                                     func.coalesce(func.sum(CostEntry.amount_cad), 0.0))
                              .where(CostEntry.agent == "laura", CostEntry.at >= start)
                              .group_by(CostEntry.purpose)))
    by = {str(p or ""): {"calls": int(n), "cad": round(float(c), 4)} for p, n, c in rows}
    total = round(sum(v["cad"] for v in by.values()), 4)
    days = max(1, now.day)
    projected = round(total / days * 30, 2)
    return {"month": f"{now:%Y-%m}", "spent_cad": total, "by_purpose": by,
            "projected_month_cad": projected, "target_cad": list(TARGET_MONTH_CAD),
            "within_target": projected <= TARGET_MONTH_CAD[1],
            "source": "cost_entries (agent=laura)"}


def summary(db, *, days: int = 30, now: datetime | None = None) -> dict:
    """Per-unit costs over the window. UNKNOWN (None) where nothing was measured."""
    from .models import LauraCostEvent, ensure_tables

    ensure_tables(db)
    now = now or _now()
    since = now - timedelta(days=days)
    with db.session() as s:
        rows = list(s.scalars(select(LauraCostEvent).where(LauraCostEvent.at >= since)))
        ev = [{"kind": r.kind, "ref": r.ref, "cost": r.cost_cad, "measured": r.measured,
               "outcome": r.outcome} for r in rows]

    def unit(kind: str) -> dict:
        xs = [e for e in ev if e["kind"] == kind]
        meas = [e for e in xs if e["measured"]]
        total = round(sum(e["cost"] for e in meas), 6)
        return {"count": len(xs), "measured": len(meas),
                "unmeasured": len(xs) - len(meas), "total_cad": total if meas else None,
                "per_unit_cad": round(total / len(meas), 6) if meas else None}

    out = {k: unit(k) for k in ("conversation", "decision", "delegation")}
    outcomes = [e for e in ev if e["kind"] == "outcome"]
    useful = [e for e in outcomes if e["outcome"] == "useful"]
    spent = [e for e in outcomes if e["measured"]]
    total_outcome_cost = round(sum(e["cost"] for e in spent), 6)
    out["outcome"] = {
        "reviewed": len(outcomes), "useful": len(useful),
        "noop": sum(1 for e in outcomes if e["outcome"] == "noop"),
        "failed": sum(1 for e in outcomes if e["outcome"] == "failed"),
        "total_cad": total_outcome_cost if spent else None,
        # every reviewed mission's cost is charged to the useful ones: the honest unit price
        "per_successful_outcome_cad": (round(total_outcome_cost / len(useful), 6)
                                       if useful and spent else None),
        "why_unknown": (None if useful and spent else
                        "no successful (useful) delegated outcome has been reviewed yet")}
    return {"window_days": days, "as_of": now.isoformat(), **out,
            "laura_month": laura_month(db, now), "basis": (
                "laura_cost_events attributes cost_entries rows: conversation = the turn's "
                "gateway bill; delegation/outcome = ledger spend with the job's id")}
