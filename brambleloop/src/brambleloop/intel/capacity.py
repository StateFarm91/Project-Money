"""Dedicated capacity for the benchmark mission, and the way a reserved team stops being one.

Requirement 302. The spec asks for MJs intelligence capacity *independent of generic market
research*, elastic and uncapped by an arbitrary number, justified by coverage, quality or
latency, and under global spend control. Four clauses, and the first is the one that fails
silently.

Capacity that is merely *allocated* to a mission gets borrowed. Generic research has a busy
week, the MJs specialists are idle at that moment, and the sensible local decision is to move
them — and it is sensible, every time, which is why the mission ends up with an org chart and
no throughput. Nobody decides to defund it. So the floor here is *reserved*: generic work
cannot draw below it, and the refusal names what it would have starved.

Above the floor the capacity is genuinely elastic and the ceiling is money, not headcount.
#302 objects to an arbitrary small number and #188 requires central spend control, and those
are the same requirement seen twice — a constant in the code is the artificial scarcity, and
the budget is the real constraint.

The justification is closed to three reasons, because "we could use more" is not a reason and
it is what an elastic system asks for by default. Coverage, quality and latency are all
measurable, and a fan-out that cannot name which one it is buying is buying none of them.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..swarm.orchestrate import fan_out

# The reserved floor. Small on purpose: a reservation is a promise the company keeps under
# pressure, and a large one is a promise it breaks the first busy week.
MJS_RESERVED_SPECIALISTS = 3

# What a fan-out may be bought with. Each is measurable, which is the point.
JUSTIFICATIONS: dict[str, str] = {
    "coverage": "listings or arenas the mission cannot currently reach at all",
    "quality": "observations that are shallower than the mandate requires",
    "latency": "a change detected later than the seasonal window can absorb",
}

# The mission's own work, kept separate from generic radar work so borrowing is visible.
MISSION_WORK: tuple[str, ...] = (
    "catalogue_coverage", "image_analysis", "category_decomposition",
    "seasonal_response", "quality_assurance")


class CapacityRefused(ValueError):
    """Generic work drawing below the reserved floor, or scale bought with no reason."""


@dataclass
class Allocation:
    reserved: int
    granted: int
    justification: str
    bounded_by: str
    spend_cad: float

    def to_dict(self) -> dict:
        return {"reserved": self.reserved, "granted": self.granted,
                "total": self.reserved + self.granted,
                "justification": self.justification,
                "why": JUSTIFICATIONS.get(self.justification, ""),
                "bounded_by": self.bounded_by,
                "estimated_spend_cad": round(self.spend_cad, 4)}


def reserve_check(*, generic_wants: int, total_specialists: int) -> dict:
    """Refuse a generic allocation that would draw below the mission's floor.

    The refusal exists because the borrowing decision is locally sensible every single time:
    generic research is busy now, the specialists are idle now, and moving them is obviously
    right. It is obviously right often enough that the mission ends up with an org chart and
    no throughput, and nobody ever decided to defund it.
    """
    available = total_specialists - MJS_RESERVED_SPECIALISTS
    if generic_wants > available:
        raise CapacityRefused(
            f"generic research asked for {generic_wants} of {total_specialists} specialists, "
            f"which draws below the {MJS_RESERVED_SPECIALISTS} reserved for the benchmark "
            f"mission. It would starve: {', '.join(MISSION_WORK)}. Borrowing is locally "
            f"sensible every time, which is how a mission ends up with an org chart and no "
            f"throughput (#302)")
    return {"generic_granted": generic_wants,
            "mission_reserved": MJS_RESERVED_SPECIALISTS,
            "spare": available - generic_wants}


def allocate(*, open_work: int, budget_remaining_cad: float, justification: str,
             cost_per_specialist_cad: float = 0.05,
             deadline_pressure: bool = False) -> Allocation:
    """Elastic capacity above the reserved floor, bounded by money rather than a number."""
    if justification not in JUSTIFICATIONS:
        raise CapacityRefused(
            f"{justification!r} is not a justification for scale: {sorted(JUSTIFICATIONS)}. "
            f"'We could use more' is what an elastic system asks for by default, and a "
            f"fan-out that cannot name which of the three it is buying is buying none")

    result = fan_out(open_work=open_work, budget_remaining_cad=budget_remaining_cad,
                     cost_per_specialist_cad=cost_per_specialist_cad,
                     deadline_pressure=deadline_pressure)
    return Allocation(reserved=MJS_RESERVED_SPECIALISTS, granted=result["granted"],
                      justification=justification, bounded_by=result["bounded_by"],
                      spend_cad=result["granted"] * cost_per_specialist_cad)


def describe() -> dict:
    return {
        "reserved_specialists": MJS_RESERVED_SPECIALISTS,
        "mission_work": list(MISSION_WORK),
        "justifications": JUSTIFICATIONS,
        "rule": ("The floor is reserved rather than allocated: generic work cannot draw "
                 "below it. Above the floor capacity is elastic and the ceiling is money, "
                 "not headcount -- a constant in the code is the artificial scarcity #302 "
                 "objects to, and the budget is the real constraint (#188)."),
    }
