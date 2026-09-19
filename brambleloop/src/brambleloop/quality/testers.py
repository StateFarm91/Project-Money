"""Physical testing as a scheduled resource, because it is the only one that cannot be hurried.

Requirement 43. Everything else this company does scales with money or attention. A tester
crochets at a human speed, and a Class C garment takes them weeks — so testing is the one
constraint where wanting it faster changes nothing, and it is therefore the one most likely to
be discovered late.

The specific failure is seasonal and it is arithmetic. A Christmas product needs a tested
sample before it certifies, the sample takes as long as the object takes, and the person who
scheduled the launch date was thinking about the launch date. By the time anybody asks whether
a tester is free, the answer no longer matters — the runway is gone either way.

Three things follow.

**Demand is forecast from the calendar, not from the queue.** A queue of test requests tells
you what has already been asked for. The seasonal calendar tells you what is about to be, and
the difference is the whole lead time.

**One tester's availability is a single point of failure, and the map says so.** A network of
four people where one does every garment is a network of one for garments, and it reads as
four on any count.

**A tester who has not finished anything is not capacity.** Reliability is what they completed
against what they accepted — not their enthusiasm, and not how long ago they signed up.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

# Risk classes that need a physical sample before release, from the existing quality gates.
NEEDS_SAMPLE: tuple[str, ...] = ("B", "C")

# How long a tester realistically takes, as a multiple of the customer make-time estimate.
# Above one because a tester also writes up what went wrong, which is the point of them.
TESTER_TIME_MULTIPLE = 1.3

# Below this completion rate a tester is a hope rather than capacity.
RELIABLE_AT = 0.7

# A specialty carried by fewer than this many reliable testers is a single point of failure.
BUS_FACTOR_ALARM = 2


class TesterRefused(ValueError):
    """Capacity claimed for somebody who has not demonstrated it."""


@dataclass(frozen=True)
class Tester:
    ref: str
    specialties: tuple[str, ...]
    accepted: int = 0
    completed: int = 0
    hours_per_week: float = 6.0

    @property
    def reliability(self) -> float:
        return (self.completed / self.accepted) if self.accepted else 0.0

    @property
    def reliable(self) -> bool:
        # Never having been asked is not reliability, and it is not unreliability either.
        return self.accepted >= 2 and self.reliability >= RELIABLE_AT

    def to_dict(self) -> dict:
        return {"ref": self.ref, "specialties": list(self.specialties),
                "accepted": self.accepted, "completed": self.completed,
                "reliability": round(self.reliability, 3), "reliable": self.reliable,
                "hours_per_week": self.hours_per_week,
                "basis": ("too few assignments to say" if self.accepted < 2 else
                          "completed against accepted")}


@dataclass
class Demand:
    """One product that will need a tested sample before it can be released."""

    product_slug: str
    risk_class: str
    specialty: str
    make_hours: float
    needed_by: date

    def tester_days(self) -> int:
        """Calendar days a tester needs, at a tester's pace rather than an ideal one."""
        hours = self.make_hours * TESTER_TIME_MULTIPLE
        return max(1, int(round(hours / 6.0 * 7)))

    def must_start_by(self) -> date:
        return self.needed_by - timedelta(days=self.tester_days())


def forecast(demands: list[Demand], *, today: date | None = None) -> dict:
    """What testing is about to be needed, ordered by when it has to start.

    Forecast from the calendar rather than from the request queue: a queue tells you what has
    already been asked for, and the whole lead time lives in the difference.
    """
    today = today or date.today()
    rows = []
    for d in demands:
        if d.risk_class not in NEEDS_SAMPLE:
            continue
        start = d.must_start_by()
        rows.append({
            "product_slug": d.product_slug, "risk_class": d.risk_class,
            "specialty": d.specialty, "tester_days": d.tester_days(),
            "needed_by": d.needed_by.isoformat(), "must_start_by": start.isoformat(),
            "days_until_start": (start - today).days,
            "already_late": start < today,
        })
    rows.sort(key=lambda r: r["days_until_start"])
    late = [r for r in rows if r["already_late"]]
    return {
        "demands": rows,
        "late": late,
        "tester_days_required": sum(r["tester_days"] for r in rows),
        "note": ("Testing is the one constraint where wanting it faster changes nothing, "
                 "which is why it is the one discovered late. Forecast from the calendar, "
                 "not from the request queue (#43)."),
    }


def capacity(testers: list[Tester], demands: list[Demand], *,
             today: date | None = None, horizon_days: int = 90) -> dict:
    """Whether the people available can absorb what is coming, by specialty."""
    today = today or date.today()
    horizon = today + timedelta(days=horizon_days)

    reliable = [t for t in testers if t.reliable]
    by_specialty: dict[str, list[Tester]] = {}
    for t in reliable:
        for specialty in t.specialties:
            by_specialty.setdefault(specialty, []).append(t)

    needed: dict[str, int] = {}
    for d in demands:
        if d.risk_class in NEEDS_SAMPLE and d.needed_by <= horizon:
            needed[d.specialty] = needed.get(d.specialty, 0) + d.tester_days()

    rows = []
    for specialty, days in sorted(needed.items()):
        people = by_specialty.get(specialty, [])
        available_days = sum(int(t.hours_per_week / 6.0 * horizon_days) for t in people)
        rows.append({
            "specialty": specialty,
            "tester_days_needed": days,
            "tester_days_available": available_days,
            "reliable_testers": [t.ref for t in people],
            "covered": available_days >= days,
            "bus_factor": len(people),
            "single_point_of_failure": len(people) < BUS_FACTOR_ALARM,
        })

    fragile = [r["specialty"] for r in rows if r["single_point_of_failure"]]
    uncovered = [r["specialty"] for r in rows if not r["covered"]]
    return {
        "horizon_days": horizon_days,
        "reliable_testers": len(reliable),
        "unproven_testers": [t.ref for t in testers if not t.reliable],
        "by_specialty": rows,
        "single_points_of_failure": fragile,
        "uncovered_specialties": uncovered,
        "schedulable": not uncovered and not fragile,
        "note": ("A network of four where one person does every garment is a network of one "
                 "for garments, and it counts as four (#43)."
                 if fragile else
                 "no specialty rests on a single tester"),
    }


def assign(tester: Tester, demand: Demand) -> dict:
    """Give a tester a job, refusing the two assignments that waste the runway."""
    if demand.specialty not in tester.specialties:
        raise TesterRefused(
            f"{tester.ref} does not test {demand.specialty!r}: {list(tester.specialties)}. "
            f"An assignment outside a specialty is a slow way to discover that")
    if not tester.reliable and tester.accepted >= 2:
        raise TesterRefused(
            f"{tester.ref} has completed {tester.completed} of {tester.accepted} "
            f"assignments. Capacity is what somebody finished, not what they accepted")
    return {"tester": tester.ref, "product_slug": demand.product_slug,
            "specialty": demand.specialty,
            "tester_days": demand.tester_days(),
            "must_start_by": demand.must_start_by().isoformat(),
            "note": ("an unproven tester is allowed a first assignment; that is how they "
                     "stop being unproven" if tester.accepted < 2 else "")}


def from_db(db, *, today: date | None = None) -> dict:
    """The live picture from recorded physical tests."""
    from sqlalchemy import select

    from ..core.models import PhysicalTest

    with db.session() as s:
        rows = list(s.scalars(select(PhysicalTest)))

    by_ref: dict[str, dict] = {}
    for r in rows:
        entry = by_ref.setdefault(r.tester_ref or "unnamed",
                                  {"accepted": 0, "completed": 0})
        entry["accepted"] += 1
        if r.passed:
            entry["completed"] += 1

    testers = [Tester(ref=ref, specialties=(), accepted=v["accepted"],
                      completed=v["completed"]) for ref, v in sorted(by_ref.items())]
    return {
        "testers": [t.to_dict() for t in testers],
        "count": len(testers),
        "note": ("no physical test has been recorded, so there is no tester network yet and "
                 "every Class B and C product is unreleasable rather than delayed"
                 if not testers else
                 f"{len(testers)} tester(s) with recorded assignments"),
    }
