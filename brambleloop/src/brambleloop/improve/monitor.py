"""Watching promoted changes in production, with the measurement the department now takes.

Requirements 93 and 99. `cells.monitor` reverts a promoted change automatically when the
metric it moved comes back worse than the sandbox said, and nothing ever called it: every
promotion stayed promoted because nobody was looking, which is a rollback path that exists
on paper. Now that `improve.measure` writes a production reading of each cell every day,
there is something to look with.

Three rules keep the watching honest.

**Only a production reading counts.** The point the promotion wrote for itself is the sandbox
number that won it, and the point the monitor writes is its own last verdict. Reading either
back as the observation would make every promotion hold by construction. So the observation
is the newest capability point for the cell that neither the improvement nor this monitor
wrote, taken after the promotion.

**One verdict per new reading.** `cells.monitor` records a point of its own each time it is
called. Called every night against the same reading, it would fill the history with copies of
one number, and a flat history is what the plateau detector reads as a defect. So the point
each improvement was last judged against is remembered in the audit row, and a night with no
new reading judges nothing.

**A promotion with nothing to read is waiting, not fine.** It is reported as such, with the
cell whose measurement it is waiting for, because "held" and "never looked at" are the two
readings this build keeps refusing to let collapse into one.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .cells import PROMOTED, monitor

ACTION = "improve.monitor"

# Sources a reading may not come from and still count as production evidence.
_NOT_PRODUCTION = ("post-promotion monitoring",)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def last_seen(db) -> dict[str, int]:
    """Which capability point each promotion was last judged against."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
    if row is None:
        return {}
    return {str(k): int(v) for k, v in ((row.detail or {}).get("seen") or {}).items()}


def sweep(db, *, now: datetime | None = None) -> dict:
    """Judge every promoted change against its newest production reading, once per reading."""
    from sqlalchemy import select

    from ..core.models import AuditLog, CapabilityPoint, Improvement

    now = now or datetime.now(timezone.utc)
    seen = last_seen(db)

    with db.session() as s:
        promoted = [(r.id, r.cell, _aware(r.promoted_at or r.at))
                    for r in s.scalars(select(Improvement).where(
                        Improvement.state == PROMOTED).order_by(Improvement.id))]
        points = [(p.id, p.cell, _aware(p.at), p.value, (p.detail or {}).get("from", ""))
                  for p in s.scalars(select(CapabilityPoint).order_by(CapabilityPoint.id))]

    held, reverted, waiting, unchanged = [], [], [], []
    for improvement_id, cell, promoted_at in promoted:
        own = f"improvement:{improvement_id}"
        production = [(pid, at, value) for pid, c, at, value, source in points
                      if c == cell and at >= promoted_at and source != own
                      and source not in _NOT_PRODUCTION]
        if not production:
            waiting.append({"improvement": improvement_id, "cell": cell,
                            "why": (f"no production reading of {cell} since the promotion; "
                                    f"held and never looked at are different, and this is "
                                    f"the second")})
            continue
        point_id, _at, observed = max(production)
        if seen.get(str(improvement_id)) == point_id:
            unchanged.append({"improvement": improvement_id, "cell": cell,
                              "point_id": point_id,
                              "why": "already judged against this reading"})
            continue
        outcome = monitor(db, improvement_id, observed)
        seen[str(improvement_id)] = point_id
        entry = {"improvement": improvement_id, "cell": cell, "point_id": point_id,
                 "observed": observed, "expected": outcome.get("expected"),
                 "action": outcome.get("action")}
        (reverted if outcome.get("action") == "reverted" else held).append(entry)

    detail = {
        "at": now.isoformat(),
        "promoted": len(promoted),
        "judged": len(held) + len(reverted),
        "held": held, "reverted": reverted, "waiting": waiting, "unchanged": unchanged,
        "seen": seen,
        "note": (f"{len(promoted)} promoted change(s): {len(held)} held, {len(reverted)} "
                 f"reverted, {len(waiting)} waiting for a production reading, "
                 f"{len(unchanged)} already judged against the current one"),
    }
    with db.session() as s:
        s.add(AuditLog(actor="improvement", action=ACTION, detail=detail))
    return detail


def state() -> dict:
    return {
        "action": ACTION,
        "reads": "the newest capability point per promoted cell that neither the improvement "
                 "nor this monitor wrote",
        "calls": "improve.cells.monitor, which reverts outside REGRESSION_TOLERANCE",
        "once_per_reading": "the point each promotion was last judged against is remembered",
    }
