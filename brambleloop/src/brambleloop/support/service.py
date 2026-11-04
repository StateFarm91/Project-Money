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

import math
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


class ReplyAlreadySent(ServiceRefused):
    """A held draft cannot be timed after the buyer response was recorded."""


MEASURED_AS: tuple[str, ...] = ("sent", "draft_ready")


def _nonnegative_number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        minutes = float(value)
    except (OverflowError, ValueError):
        return None
    return minutes if math.isfinite(minutes) and minutes >= 0 else None


def record_response(db, case_id: int, *, minutes: float, from_canonical: bool,
                    measured_as: str = "sent") -> dict:
    """Record how long a case waited, on the case itself.

    Refuses a second recording rather than overwriting: a response time that can be revised
    is a response time somebody will revise, and the revision always goes one way.

    The one sequence that is not a revision is the lifecycle itself (Codex CB2-G08): a reply
    is drafted (`draft_ready`) and later sent (`sent`). Those are two different events, so the
    sent timing is accepted after a draft timing and the draft timing is kept beside it under
    `draft_ready_minutes`. Still refused: the same basis twice, a draft timing after the
    reply was sent, and a sent timing earlier than the draft it delivered.
    """
    from sqlalchemy import select

    from ..core.models import SupportCase
    from .response_watch import _answered

    measured_minutes = _nonnegative_number(minutes)
    if measured_minutes is None:
        raise ServiceRefused("a response time must be a finite non-negative number")
    if measured_as not in MEASURED_AS:
        raise ServiceRefused(f"{measured_as!r} is not a timing basis: {list(MEASURED_AS)}")

    with db.session() as s:
        case = s.scalar(select(SupportCase).where(
            SupportCase.id == case_id).with_for_update())
        if case is None:
            raise ServiceRefused(f"no support case {case_id}")
        detail = dict(case.detail or {})
        if measured_as == "draft_ready" and _answered(case):
            raise ReplyAlreadySent("a sent case cannot receive a later held-draft timing")
        draft_minutes = None
        if "response_minutes" in detail:
            prior_basis = detail.get("response_measured_as", "sent")
            if not (prior_basis == "draft_ready" and measured_as == "sent"):
                raise ServiceRefused(
                    f"case {case_id} already recorded {detail['response_minutes']} minutes "
                    f"({prior_basis}). A response time that can be revised is one somebody "
                    f"will revise, and the revision always goes the same way")
            draft_minutes = _nonnegative_number(detail["response_minutes"])
            if draft_minutes is None:
                raise ServiceRefused("existing draft timing is invalid; reconciliation required")
            if measured_minutes < draft_minutes:
                raise ServiceRefused(
                    f"case {case_id}: a reply sent after {measured_minutes} minutes cannot "
                    f"predate the draft that was ready after {draft_minutes} minutes")
            detail["draft_ready_minutes"] = draft_minutes
            detail["draft_from_canonical"] = bool(detail.get("from_canonical"))
        detail["response_minutes"] = measured_minutes
        detail["from_canonical"] = bool(from_canonical)
        # In shadow mode a reply is drafted and held, so what can be timed is how long the
        # answer took to be ready, not how long the buyer waited. Kept apart below: a draft
        # held in a queue is not a response anybody received.
        detail["response_measured_as"] = measured_as
        case.detail = detail
        out = {"case_id": case_id, "minutes": measured_minutes,
               "from_canonical": bool(from_canonical), "measured_as": measured_as}
        if draft_minutes is not None:
            out["draft_ready_minutes"] = draft_minutes
        return out


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
    all_timed = [(esc, d) for esc, d, _ in recent
                 if _nonnegative_number(d.get("response_minutes")) is not None
                 and d.get("response_measured_as", "sent") in MEASURED_AS]
    # Only a response somebody received is a service level. A draft-ready time is how fast
    # the automation produced an answer, reported beside it and never counted as delivered.
    drafts = [(esc, d) for esc, d in all_timed
              if d.get("response_measured_as") == "draft_ready"]
    timed = [(esc, d) for esc, d in all_timed
             if d.get("response_measured_as", "sent") == "sent"]
    # A held draft is not a delivered response; it remains untimed for the
    # buyer-facing service level, even though draft latency is shown separately.
    untimed = len(recent) - len(timed)

    canonical = [d for esc, d in timed if not esc]
    escalated = [d for esc, d in timed if esc]

    def share(items, limit_minutes: float) -> float | None:
        if not items:
            return None
        inside = [i for i in items if i["response_minutes"] <= limit_minutes]
        return round(len(inside) / len(items), 3)

    draft_canonical = [d for esc, d in drafts if not esc]
    draft_block = {"cases": len(drafts),
                   "canonical_within_target": share(draft_canonical,
                                                    TARGETS["canonical_minutes"]),
                   "note": ("how fast an answer was ready; held in shadow mode, so no buyer "
                            "has received it and it is not a service level")}
    canonical_share = share(canonical, TARGETS["canonical_minutes"])
    escalated_share = share(escalated, TARGETS["escalated_hours"] * 60)
    measured_groups = [(canonical, TARGETS["canonical_minutes"]),
                       (escalated, TARGETS["escalated_hours"] * 60)]
    measured_groups = [(items, limit) for items, limit in measured_groups if items]
    # Use unrounded ratios for the verdict; display rounding must never turn a
    # just-below-floor result into a passing one.
    meets = (all(sum(item["response_minutes"] <= limit for item in items) / len(items)
                 >= SERVICE_FLOOR for items, limit in measured_groups)
             if measured_groups and not untimed else None)

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
        "meets_target": meets,
        "draft_ready": draft_block,
        "floor": SERVICE_FLOOR,
        "note": ("no case in this window has a recorded response time, so there is no "
                 "service level -- which is different from a bad one"
                 if not timed else
                 f"{untimed} case(s) are untimed and are counted as untimed rather than "
                 f"dropped: dropping them measures the cases somebody remembered to time")
                + ". Shares are rounded for display; the target uses unrounded ratios "
                  "and requires complete delivered-response timing.",
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

    # Ledger rows alone do not establish distinct buyers, link support speed to
    # each outcome, or provide a comparison capable of measuring an effect.
    # Report only descriptive row counts and never turn their existence into a
    # causal or associative claim.
    recorded_refunds = 0
    invalid_refunds = 0
    for sale in sales:
        amount = _nonnegative_number(sale.refunds_cad)
        if amount is None:
            invalid_refunds += 1
        elif amount > 0:
            recorded_refunds += 1
    level = service_level(db, days=days)
    return {
        "measurable": False,
        "orders": None,
        "refunds": None,
        "refund_rate": None,
        "sale_rows": len(sales),
        "sale_rows_with_positive_recorded_refunds": recorded_refunds,
        "sale_rows_with_invalid_refunds": invalid_refunds,
        "service_level": level,
        "reason": ("ledger sale rows are not a linked comparison of support response "
                   "speed and refunds, so the impact cannot be measured"),
        "note": ("sale-row counts are descriptive, all-history ledger observations; they "
                 "are not deduplicated order counts or a measured refund rate"),
    }
