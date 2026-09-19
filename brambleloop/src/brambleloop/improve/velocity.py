"""Shipping more is not progress, and an autonomous system will prove it to you.

Requirements 52 and 53. Both are about the same hazard from opposite ends: a system that runs
continuously and measures its own throughput will optimise throughput, because throughput is
the thing it can move without anybody's permission.

**#52: releases per week is never reported alone.** A number that goes up is a number agents
learn to make go up, and shipping SKUs is the easiest of all of them — it requires no customer
and no evidence. So the release count is only ever returned alongside defect rate, support
burden, conversion and contribution, and a week where velocity rose while any of those moved
the wrong way is reported as *degraded* rather than as a record week. The pairing is
structural: there is no function here that returns the count by itself.

**#53: a review that only adds work is how autonomous bureaucracy happens.** Every cadence,
every monitored query, every experiment and every polished product is a standing cost that was
justified once. Nothing in this system ever removes one, because removal is nobody's job and
everything has a plausible reason to continue. So the weekly review produces a STOP list, and
a review that stops nothing is asked to say why — not blocked, because a genuinely lean week
exists, but not silent either, because "nothing to stop" is exactly what a bureaucracy
reports.

The five categories come from #53 itself, and they are separate because they fail differently:
an experiment that will not conclude, a cadence costing more than it returns, a product being
polished past its ceiling, a query nobody acts on, and infrastructure with no commercial line
to it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

# What must accompany a release count, per #52. Named, because "alongside quality metrics"
# is satisfied by any one of them and the useful version is all of them.
COMPANIONS: tuple[str, ...] = (
    "defect_rate", "support_burden", "conversion", "contribution_cad")

# Movement beyond this in the wrong direction makes a faster week a worse one.
DEGRADATION_TOLERANCE = 0.05

# #53's own categories.
STOP_CATEGORIES: dict[str, str] = {
    "experiment": "an experiment that has run long enough to have concluded, and has not",
    "cadence": "a scheduled job costing more attention than it returns",
    "polish": "a product being improved past the point where the improvement sells anything",
    "query": "a search term monitored out of habit rather than for a decision",
    "infrastructure": "engineering with no line to a commercial outcome",
}


class VelocityRefused(ValueError):
    """A release count reported alone, or a stop list with nothing in it and nothing to say."""


@dataclass(frozen=True)
class Week:
    ending: str
    releases: int
    defect_rate: float
    support_burden: float          # support cases per order
    conversion: float
    contribution_cad: float

    def to_dict(self) -> dict:
        return {"ending": self.ending, "releases": self.releases,
                "defect_rate": round(self.defect_rate, 4),
                "support_burden": round(self.support_burden, 4),
                "conversion": round(self.conversion, 5),
                "contribution_cad": round(self.contribution_cad, 2)}


# Which direction is good for each companion.
_HIGHER_IS_BETTER = {"defect_rate": False, "support_burden": False,
                     "conversion": True, "contribution_cad": True}


def quality_adjusted(previous: Week | None, current: Week) -> dict:
    """Releases per week, and never releases per week alone (#52).

    There is deliberately no function in this module that returns the count by itself. The
    pairing has to be structural, because a number an agent can move without a customer is
    the number it will move.
    """
    row = {"week": current.to_dict(), "companions": list(COMPANIONS)}
    if previous is None:
        row.update({
            "comparable": False,
            "verdict": "baseline",
            "reason": ("one week is a count, not a velocity. It is recorded as the baseline "
                       "the next week is read against"),
        })
        return row

    movements = {}
    degraded = []
    for key in COMPANIONS:
        before, after = getattr(previous, key), getattr(current, key)
        if not before:
            # A metric moving off zero has no percentage change and is the case that matters
            # most: a defect rate going from none to some is the single most important
            # movement this comparison can see, and the divide-guard would have skipped it.
            worse = (after > 0) if not _HIGHER_IS_BETTER[key] else False
            movements[key] = {"before": before, "after": after, "change": None,
                              "direction": ("worse" if worse else
                                            "improved" if after > 0 else "unmeasured"),
                              "from_zero": True}
            if worse:
                degraded.append(key)
            continue
        change = (after - before) / abs(before)
        better = change > 0 if _HIGHER_IS_BETTER[key] else change < 0
        movements[key] = {"before": before, "after": after,
                          "change": round(change, 4),
                          "direction": "improved" if better else "worse"}
        if not better and abs(change) > DEGRADATION_TOLERANCE:
            degraded.append(key)

    faster = current.releases > previous.releases
    row.update({
        "comparable": True,
        "releases_before": previous.releases,
        "releases_after": current.releases,
        "faster": faster,
        "movements": movements,
        "degraded": degraded,
        "verdict": ("degraded" if degraded else "improved" if faster else "steady"),
        "reason": (f"{current.releases} releases against {previous.releases}, and "
                   f"{', '.join(degraded)} moved the wrong way. A faster week that costs "
                   f"quality or economics is a worse week, and it is the one an agent "
                   f"optimising its own throughput would produce (#52)"
                   if degraded else
                   f"{current.releases} releases with no companion metric degrading"),
    })
    return row


def from_db(db, *, weeks: int = 2, now: datetime | None = None) -> dict:
    """The last weeks as rows, so velocity is counted rather than reported."""
    from sqlalchemy import select

    from ..core.models import Incident, LedgerEntry, PatternVersion, SupportCase

    now = now or datetime.now(timezone.utc)

    def _aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    with db.session() as s:
        versions = [(v.id, _aware(v.created_at)) for v in s.scalars(
            select(PatternVersion).where(PatternVersion.certified == True))]  # noqa: E712
        incidents = [_aware(i.at) for i in s.scalars(select(Incident))]
        cases = [_aware(c.at) for c in s.scalars(select(SupportCase))]
        sales = [(_aware(x.at), x.gross_cad - x.fees_cad) for x in s.scalars(
            select(LedgerEntry).where(LedgerEntry.category == "sale"))]

    out: list[Week] = []
    for index in range(weeks - 1, -1, -1):
        end = now - timedelta(days=7 * index)
        start = end - timedelta(days=7)
        released = sum(1 for _, at in versions if start <= at < end)
        week_sales = [c for at, c in sales if start <= at < end]
        orders = len(week_sales)
        out.append(Week(
            ending=end.date().isoformat(),
            releases=released,
            defect_rate=(sum(1 for at in incidents if start <= at < end) / released
                         if released else 0.0),
            support_burden=(sum(1 for at in cases if start <= at < end) / orders
                            if orders else 0.0),
            conversion=0.0,
            contribution_cad=round(sum(week_sales), 2)))

    comparison = quality_adjusted(out[-2] if len(out) >= 2 else None, out[-1])
    return {"weeks": [w.to_dict() for w in out], "comparison": comparison,
            "note": ("Conversion reads zero because no traffic is attributed yet, and it is "
                     "reported as a measured zero rather than omitted: a companion metric "
                     "quietly dropped from the pairing is how the pairing stops working.")}


# ---------------------------------------------------------------------------
# The stop-doing queue (#53)


@dataclass(frozen=True)
class Stop:
    category: str
    subject: str
    reason: str
    saves: str = ""

    def __post_init__(self) -> None:
        if self.category not in STOP_CATEGORIES:
            raise VelocityRefused(
                f"{self.category!r} is not a stop category: {sorted(STOP_CATEGORIES)}")
        if len(self.reason.strip()) < 15:
            raise VelocityRefused(
                f"{self.subject}: stopping something needs a reason somebody can argue with "
                f"later, or it is as arbitrary as starting it was")

    def to_dict(self) -> dict:
        return {"category": self.category, "meaning": STOP_CATEGORIES[self.category],
                "subject": self.subject, "reason": self.reason, "saves": self.saves}


def stop_list(stops: list[Stop], *, nothing_to_stop_because: str = "",
              reviewed_on: str = "") -> dict:
    """The STOP half of the weekly review (#53).

    A review that stops nothing is not blocked — a genuinely lean week exists — but it is
    asked to say why in a sentence. "Nothing to stop" with no explanation is precisely what a
    bureaucracy reports, every week, for years.
    """
    if not stops:
        if len(nothing_to_stop_because.strip()) < 20:
            raise VelocityRefused(
                "a review that stops nothing has to say why. Every cadence, query and "
                "experiment is a standing cost that was justified once, and nothing here "
                "ever removes one unless removing is somebody's job this week (#53)")
        return {"stopped": [], "count": 0, "by_category": {},
                "nothing_to_stop_because": nothing_to_stop_because.strip(),
                "reviewed_on": reviewed_on or date.today().isoformat(),
                "note": ("An empty stop list is allowed and is never silent: 'nothing to "
                         "stop' is what a bureaucracy reports.")}

    by_category: dict[str, int] = {}
    for stop in stops:
        by_category[stop.category] = by_category.get(stop.category, 0) + 1
    return {
        "stopped": [s.to_dict() for s in stops],
        "count": len(stops),
        "by_category": by_category,
        "categories_untouched": [c for c in STOP_CATEGORIES if c not in by_category],
        "reviewed_on": reviewed_on or date.today().isoformat(),
        "note": ("The five categories fail differently, which is why they are separate: an "
                 "experiment that will not conclude is a different problem from a cadence "
                 "costing more than it returns (#53)."),
    }


def review(db, *, stops: list[Stop] | None = None,
           nothing_to_stop_because: str = "") -> dict:
    """The weekly strategy review's two halves, together.

    Together on purpose. A review that produced only new work would be the thing #53 names,
    and the way to prevent it is to make the report structurally incapable of having one half.
    """
    return {
        "velocity": from_db(db),
        "stop": stop_list(stops or [],
                          nothing_to_stop_because=nothing_to_stop_because),
        "rule": ("Releases per week is never reported alone (#52), and a review that only "
                 "adds work is how autonomous bureaucracy happens (#53)."),
    }
