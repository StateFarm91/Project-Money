"""Independent review of a reference finding, with an atomic audit record."""
from __future__ import annotations

from sqlalchemy import select, update

from ..core.models import AuditLog, TeardownFinding, utcnow
from .library import ContentRefused, check_derived


class ReviewRefused(ValueError):
    pass


def review_finding(db, finding_id: int, *, reviewer: str, decision: str, reason: str) -> dict:
    if type(finding_id) is not int or finding_id <= 0:
        raise ReviewRefused("invalid finding")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 64:
        raise ReviewRefused("reviewer identity required")
    if decision not in ("reviewed", "rejected"):
        raise ReviewRefused("decision must be reviewed or rejected")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ReviewRefused("reason required")
    reviewer = reviewer.strip()
    try:
        check_derived(reason)
        check_derived(reviewer)
    except ContentRefused as exc:
        raise ReviewRefused(str(exc)) from exc
    with db.session() as s:
        row = s.scalar(select(TeardownFinding).where(TeardownFinding.id == finding_id)
                       .with_for_update())
        if row is None:
            raise ReviewRefused("finding not found")
        if not row.recorded_by:
            raise ReviewRefused("recorder is unknown; independent review cannot be established")
        if row.recorded_by.casefold() == reviewer.casefold():
            raise ReviewRefused("recorder cannot review their own finding")
        if row.review_state != "proposed":
            raise ReviewRefused("finding has already been reviewed")
        changed = s.execute(update(TeardownFinding).where(
            TeardownFinding.id == finding_id, TeardownFinding.review_state == "proposed",
            TeardownFinding.recorded_by == row.recorded_by).values(
                review_state=decision, reviewed_by=reviewer, reviewed_at=utcnow()))
        if changed.rowcount != 1:
            raise ReviewRefused("finding changed while being reviewed")
        s.add(AuditLog(actor=reviewer, action="teardown.finding_reviewed",
                       artifact=f"teardown-finding:{finding_id}",
                       detail={"finding": finding_id, "decision": decision,
                               "reason": reason.strip()}))
        return {"finding": finding_id, "review_state": decision}
