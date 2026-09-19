"""Response speed as a conversion advantage, and the refund claim it is not yet allowed to make.

Requirement 18. Two halves that need keeping apart, because the first is measurable today and
the second is the kind of claim a company makes for a year before anybody checks it.

**The measurable half.** A question that can be answered from canonical data -- a stitch count,
a finished size, a yardage, the gauge, which terms the pattern uses -- should be answered in
minutes, because the answer is already known and the only thing between the buyer and it is
whether anybody is awake. A question that cannot be answered safely is escalated, and
escalation has its own slower target rather than being folded into one average that hides it.
One number over both would let a fast automated majority bury a slow escalated minority, and
the escalated minority is where the unhappy buyers are.

**The half that has to wait.** "Fast support reduces refunds and improves reviews" is
plausible, widely believed and unmeasured here, because there are no orders. It is reported as
unmeasurable with the reason, never as zero and never as an assumption with a number attached.

Timings live in the case's existing detail column rather than in a new one. The deployed
database was created with `create_all`, which adds tables and not columns, so a new column
would exist in every test and in no production row -- a measurement that works everywhere
except where it matters.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# What "in minutes" means, per kind of question. Separate targets on purpose: one average over
# both lets a fast automated majority bury the slow escalated minority.
TARGETS: dict[str, float] = {
    "canonical_minutes": 5.0,
    "escalated_hours": 24.0,
}

# The share of in-target responses below which the rung in the trust accelerator fails. Not a
# perfect record: an occasional miss is a weekend, a persistent one is a promise nobody keeps.
SERVICE_FLOOR = 0.90


class ServiceRefused(ValueError):
    """A response time that cannot be true, or one recorded twice."""


def record_response(db, case_id: int, *, minutes: float, from_canonical: bool) -> dict:
    """Record how long a case waited, on the case itself.

    Refuses a second recording rather than overwriting: a response time that can be revised
    is a response time somebody will revise, and the revision always goes one way.
    """
    from ..core.models import SupportCase

    if minutes < 0:
        raise ServiceRefused("a response cannot have taken negative time")

    with db.session() as s:
        case = s.get(SupportCase, case_id)
        if case is None:
            raise ServiceRefused(f"no support case {case_id}")
        detail = dict(case.detail or {})
        if "response_minutes" in detail:
            raise ServiceRefused(
                f"case {case_id} already recorded {detail['response_minutes']} minutes. A "
                f"response time that can be revised is one somebody will revise, and the "
                f"revision always goes the same way")
        detail["response_minutes"] = float(minutes)
        detail["from_canonical"] = bool(from_canonical)
        case.detail = detail
        return {"case_id": case_id, "minutes": float(minutes),
                "from_canonical": bool(from_canonical)}


def service_level(db, *, days: int = 30, now: datetime | None = None) -> dict:
    """How fast support actually was, split by whether the answer was already known.

    A case with no recorded time is counted as untimed rather than as fast or slow. Dropping
    it would compute the service level of the cases somebody remembered to time.
    """
    from sqlalchemy import select

    from ..core.models import SupportCase

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    with db.session() as s:
        rows = [(c.escalated, dict(c.detail or {}),
                 c.at if c.at.tzinfo else c.at.replace(tzinfo=timezone.utc))
                for c in s.scalars(select(SupportCase))]

    recent = [r for r in rows if r[2] >= cutoff]
    timed = [(esc, d) for esc, d, _ in recent if "response_minutes" in d]
    untimed = len(recent) - len(timed)

    canonical = [d for esc, d in timed if not esc]
    escalated = [d for esc, d in timed if esc]

    def share(items, limit_minutes: float) -> float | None:
        if not items:
            return None
        inside = [i for i in items if i["response_minutes"] <= limit_minutes]
        return round(len(inside) / len(items), 3)

    canonical_share = share(canonical, TARGETS["canonical_minutes"])
    escalated_share = share(escalated, TARGETS["escalated_hours"] * 60)
    measured = [s for s in (canonical_share, escalated_share) if s is not None]

    return {
        "window_days": days,
        "cases": len(recent),
        "timed": len(timed),
        "untimed": untimed,
        "canonical": {"cases": len(canonical), "within_target": canonical_share,
                      "target_minutes": TARGETS["canonical_minutes"]},
        "escalated": {"cases": len(escalated), "within_target": escalated_share,
                      "target_hours": TARGETS["escalated_hours"]},
        # Minimum, not average: the worse of the two is the one a buyer experienced.
        "meets_target": (min(measured) >= SERVICE_FLOOR) if measured else None,
        "floor": SERVICE_FLOOR,
        "note": ("no case in this window has a recorded response time, so there is no "
                 "service level -- which is different from a bad one"
                 if not timed else
                 f"{untimed} case(s) are untimed and are counted as untimed rather than "
                 f"dropped: dropping them measures the cases somebody remembered to time"),
    }


def refund_impact(db, *, days: int = 90) -> dict:
    """Whether fast support reduces refunds. Currently: nobody can say, and it says so.

    The claim is plausible and widely believed, which is exactly why it needs a measurement
    rather than a sentence. Reported unmeasurable with the reason instead of as zero.
    """
    from sqlalchemy import select

    from ..core.models import LedgerEntry

    with db.session() as s:
        sales = list(s.scalars(select(LedgerEntry).where(LedgerEntry.category == "sale")))

    if not sales:
        return {
            "measurable": False,
            "orders": 0,
            "reason": ("no orders exist, so the relationship between response speed and "
                       "refunds cannot be measured. It is not zero and it is not assumed: "
                       "it is unmeasured, and the difference matters because this is the "
                       "claim a support department runs on for a year without checking"),
        }

    refunds = [x for x in sales if x.refunds_cad > 0]
    level = service_level(db, days=days)
    return {
        "measurable": True,
        "orders": len(sales),
        "refunds": len(refunds),
        "refund_rate": round(len(refunds) / len(sales), 4),
        "service_level": level,
        "note": ("a refund rate beside a service level is an association and not yet a "
                 "cause. Saying which way it runs needs orders that differ in how fast they "
                 "were answered, which is a comparison this shop cannot make yet"),
    }
