"""What an improvement actually bought, and whether a design used what the company knows.

Requirements 99 and 101. Both are the second half of something already built, and both second
halves are the ones that get skipped — because the first half feels like the work.

**#99.** The department already refuses a change it cannot afford and records what each
hypothesis cost. What it could not do is say what any of them *returned*. That asymmetry is
the normal state of an improvement programme: cost is known on the day and benefit is known
later, so benefit is the number nobody goes back for, and the programme runs for a year on the
assumption that it is working. Realised benefit is therefore measured against the baseline
captured at proposal time — the one thing that makes it a measurement rather than a story —
and a promotion whose metric did not move is recorded as a cost with no return, which is a
real and common outcome rather than a failure of the system.

**#101.** Compounding is already measured by what acted on a lesson rather than by how many
exist. The remaining half is the direction #101 actually cares about: not "was the lesson
used" but "did this new design use what we know". A design that consumed nothing is not
forbidden — the first product in a new territory legitimately has nothing to draw on — but it
is visible, and a catalogue of them means the company is restarting from generic intelligence
every time, which is the thing the requirement is named after.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# A promoted change whose metric has not moved this far either way after the window is
# recorded as having returned nothing. Deliberately the same tolerance the monitor uses to
# revert, so "did not help" and "did not hurt" are judged on one scale.
NEUTRAL_BAND = 0.05

# How long a promoted change gets before its return is read. Shorter and every change looks
# neutral; longer and nothing is ever assessed.
REALISATION_DAYS = 14


class RoiRefused(ValueError):
    """A benefit claimed without the baseline that would make it a measurement."""


@dataclass
class Realised:
    """One promoted change, its baseline, and what production measured afterwards."""

    improvement_id: int
    cell: str
    metric: str
    baseline: float | None
    observed: float | None
    higher_is_better: bool
    cost_cad: float
    age_days: float
    window_days: int

    @property
    def measurable(self) -> bool:
        return self.baseline is not None and self.observed is not None

    @property
    def movement(self) -> float | None:
        if not self.measurable or not self.baseline:
            return None
        delta = (self.observed - self.baseline) / abs(self.baseline)
        return delta if self.higher_is_better else -delta

    def verdict(self) -> str:
        if not self.measurable:
            # A change promoted yesterday has not failed to return anything; it has not been
            # read yet. Collapsing the two would make a young programme look like a bad one.
            return "too_early" if self.age_days < self.window_days else "unmeasured"
        move = self.movement
        if move is None:
            return "unmeasured"
        if move > NEUTRAL_BAND:
            return "returned"
        if move < -NEUTRAL_BAND:
            return "regressed"
        return "no_return"

    def to_dict(self) -> dict:
        return {"improvement_id": self.improvement_id, "cell": self.cell,
                "metric": self.metric, "baseline": self.baseline,
                "observed": self.observed, "cost_cad": round(self.cost_cad, 4),
                "age_days": round(self.age_days, 2),
                "movement": round(self.movement, 4) if self.movement is not None else None,
                "verdict": self.verdict()}


def realised_benefit(db, *, now: datetime | None = None,
                     window_days: int = REALISATION_DAYS) -> dict:
    """What the promoted changes actually returned, against their own baselines (#99).

    Measured against the baseline captured at proposal time, which is the single thing that
    makes this a measurement rather than a story: a benefit read against a number taken
    afterwards is the change compared with itself.

    The sandbox result the promotion itself recorded is deliberately not read as the return.
    It is the number that won the promotion, taken under the conditions that were chosen to
    show the change working; counting it as the realised benefit would make every promotion
    succeed by construction, which is the most comfortable way for an improvement programme
    to stop being a measurement.
    """
    from sqlalchemy import select

    from ..core.models import CapabilityPoint, Improvement
    from .cells import BY_KEY, PROMOTED

    now = now or datetime.now(timezone.utc)

    def _aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    with db.session() as s:
        promoted = [(r.id, r.cell, r.metric, r.baseline_value, r.cost_cad or 0.0,
                     _aware(r.promoted_at or r.at))
                    for r in s.scalars(select(Improvement)) if r.state == PROMOTED]
        history = [(h.cell, _aware(h.at), h.value, (h.detail or {}).get("from", ""))
                   for h in s.scalars(select(CapabilityPoint))]

    rows: list[Realised] = []
    for improvement_id, cell_key, metric, baseline, cost_cad, promoted_at in promoted:
        cell = BY_KEY.get(cell_key)
        if cell is None:
            continue
        own = f"improvement:{improvement_id}"
        after = [(at, value) for c, at, value, source in history
                 if c == cell_key and at >= promoted_at and source != own]
        after.sort()
        rows.append(Realised(
            improvement_id=improvement_id, cell=cell_key, metric=metric,
            baseline=baseline, observed=(after[-1][1] if after else None),
            higher_is_better=cell.higher_is_better, cost_cad=cost_cad,
            age_days=(now - promoted_at).total_seconds() / 86400.0,
            window_days=window_days))

    spent = sum(r.cost_cad for r in rows)
    by = {name: [r.to_dict() for r in rows if r.verdict() == name]
          for name in ("returned", "no_return", "regressed", "unmeasured", "too_early")}
    # Read only the changes old enough to be readable. A hit rate computed over promotions
    # made this morning is a number about the calendar, not about the programme.
    assessed = [r for r in rows if r.verdict() != "too_early"]

    return {
        "window_days": window_days,
        "promotions": len(rows),
        "assessed": len(assessed),
        "spent_cad": round(spent, 4),
        "returned": by["returned"],
        "no_return": by["no_return"],
        "regressed": by["regressed"],
        "unmeasured": by["unmeasured"],
        "too_early": by["too_early"],
        "hit_rate": (round(len(by["returned"]) / len(assessed), 3) if assessed else None),
        "note": ("no promoted change has been assessed yet. Cost is known on the day and "
                 "benefit is known later, so benefit is the number nobody goes back for -- "
                 "which is how a programme runs for a year on the assumption it is working "
                 "(#99)." if not assessed else
                 f"{len(by['returned'])} returned, {len(by['no_return'])} cost without "
                 f"return, {len(by['regressed'])} regressed, {len(by['unmeasured'])} "
                 f"promoted and never measured again"),
    }


def prioritise(candidates: list[dict]) -> dict:
    """Order improvement candidates by expected impact per unit cost (#99).

    Refuses a candidate with no expected effect on anything: "continuous learning is not
    permission to burn unlimited tokens", and the mechanism that makes that real is having to
    say in advance what would count as it having worked.
    """
    rows = []
    for c in candidates:
        expected = c.get("expected_impact")
        cost = float(c.get("cost_cad") or 0.0)
        if expected is None:
            raise RoiRefused(
                f"{c.get('key', 'a candidate')}: say what improvement is expected and on "
                f"which metric. A candidate that cannot say what would count as working "
                f"cannot be prioritised, and cannot be assessed afterwards either")
        rows.append({**c, "cost_cad": cost,
                     "impact_per_cad": (round(float(expected) / cost, 4) if cost > 0
                                        else None)})
    # A free change with real expected impact outranks a paid one: sorted with None first.
    rows.sort(key=lambda r: (r["impact_per_cad"] is not None, -(r["impact_per_cad"] or 0.0)))
    return {"ranked": rows,
            "note": ("Ordered by expected impact per dollar, with free changes first. "
                     "Continuous learning is not permission to burn unlimited tokens (#99).")}


# ---------------------------------------------------------------------------
# #101: did this design use what the company knows?


def design_provenance(db, *, product_slug: str, lesson_ids: tuple[int, ...],
                      brief: str = "") -> dict:
    """Record which accumulated lessons a new design actually drew on.

    A design that consumed nothing is not forbidden: the first product in a new territory
    legitimately has nothing to draw on. It is visible, which is the point — a catalogue of
    them means the company is restarting from generic intelligence every time, and that is
    the thing #101 is named after.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog, Lesson

    with db.session() as s:
        known = {l.id for l in s.scalars(select(Lesson))}
        unknown = sorted(set(lesson_ids) - known)
        if unknown:
            raise RoiRefused(
                f"lessons {unknown} do not exist. A design cannot cite knowledge the "
                f"company does not have")
        row = AuditLog(actor="product_creativity", action="design.provenance",
                       artifact=product_slug,
                       detail={"lesson_ids": list(lesson_ids), "brief": brief,
                               "count": len(lesson_ids)})
        s.add(row)
        s.flush()
        record_id = row.id

    return {"product_slug": product_slug, "lessons_used": list(lesson_ids),
            "count": len(lesson_ids), "record_id": record_id,
            "note": ("this design drew on nothing the company has learned, which is "
                     "legitimate for a first product in a new territory and is the thing to "
                     "watch if it becomes the pattern (#101)"
                     if not lesson_ids else
                     f"drew on {len(lesson_ids)} accumulated lesson(s)")}


def compounding_report(db) -> dict:
    """Whether new designs are standing on what the company knows, or restarting each time."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = [a.detail or {} for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "design.provenance"))]

    if not rows:
        return {"measurable": False,
                "designs": 0,
                "reason": ("no design has recorded what it drew on, so whether the company "
                           "is compounding or restarting cannot be told apart"),
                "note": ""}

    used = [r for r in rows if r.get("count")]
    return {
        "measurable": True,
        "designs": len(rows),
        "designs_using_accumulated_knowledge": len(used),
        "share": round(len(used) / len(rows), 3),
        "mean_lessons_per_design": round(
            sum(r.get("count", 0) for r in rows) / len(rows), 2),
        "note": ("every recorded design drew on nothing the company has learned: that is "
                 "restarting from generic intelligence each time, which is exactly what "
                 "#101 is named after" if not used else
                 f"{len(used)} of {len(rows)} designs cited accumulated knowledge"),
    }
