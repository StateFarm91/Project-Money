"""How often each department's evidence goes stale, and the department that is never stale
and never moves.

Requirement 191. Every department defines how often its evidence should be reconsidered,
based on how fast its world changes; fast-moving market and creative signals may update
frequently and stable compiler mathematics need not churn hourly. The orchestrator flags
stale learning, stale benchmarks, and departments whose capability has not measurably
improved over a defined period.

Two things in that decide the module, and the second is the one a freshness check normally
misses.

**Staleness is a property of the world, not of the calendar.** `improve.profiles` and
`improve.bus` both carried a single thirty-day constant, which is the arrangement the
requirement is written against: thirty days is far too slow for a competitor's catalogue and
entirely meaningless for the compiler. So each cell is mapped to a *world speed* — how fast
the thing it measures changes when nobody is looking — and the interval follows from that
rather than from anybody's preference.

The interesting entry is the one with no interval at all. **Compiler mathematics does not go
stale by the passage of time.** A stitch count that was right in March is right in September,
and re-verifying it every night measures the clock. It goes stale when the *code* changes,
which is a fingerprint question, not a date question — the same mechanism `ops.artefacts` uses
for derived files, applied to a department. Giving those cells a very long interval would have
been easier and would have been wrong in a way that only shows up the week somebody changes
the compiler and the nightly sweep reports everything current for another twenty-nine days.

**A freshness SLA measured in "when did we last look" rewards looking.** A department
re-running a scan every hour and learning nothing scores perfectly on recency, and that is the
commonest real state of an improvement programme: busy, current, and flat. The requirement's
third clause is the antidote, so freshness here has *two* clocks — evidence age and capability
movement — and the state worth naming is the one where the first is green and the second is
not. `CHURNING` is a fresh department that has not moved, and it is reported as a problem
rather than as a pass.

Neither clock treats absence as a reading. A department nobody has ever measured is
`never_measured`, not stale: those need opposite fixes — instrument it, versus run it again —
and a sweep that files them together produces a backlog where the second kind buries the
first. Likewise a direction claimed from one measurement is `unmeasured`, because one point
is not a trend and two is barely a line.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .cells import BY_KEY, CELLS

# ---- how fast a world changes ---------------------------------------------

ADVERSARIAL = "adversarial"
MARKET = "market"
OPERATIONAL = "operational"
MATHEMATICAL = "mathematical"

# Hours before evidence of this kind should be reconsidered. `mathematical` has none on
# purpose and is not a very large number: see the module docstring.
WORLD_SPEED: dict[str, tuple[int | None, str]] = {
    ADVERSARIAL: (24, "somebody else is actively changing it -- competitor listings, platform "
                      "policy, search results. A day old is already a description of "
                      "yesterday"),
    MARKET: (72, "buyer behaviour and demand. It moves, but not between breakfast and lunch, "
                 "and re-reading it hourly measures noise"),
    OPERATIONAL: (168, "our own throughput, costs, support load and defect rate. A week is "
                       "the shortest span over which any of these means anything"),
    MATHEMATICAL: (None, "does not go stale with time at all. A stitch count that was right "
                         "in March is right in September; it goes stale when the code "
                         "changes, which is a fingerprint question and not a date one"),
}

# Each cell's world, named rather than inferred. Twelve entries because `improve.cells` has
# twelve; a cell added there without an entry here is refused rather than defaulted, because
# a default interval is exactly the single global constant this requirement exists to remove.
CELL_WORLD: dict[str, str] = {
    "product_creativity": MARKET,
    "pattern_engineering": MATHEMATICAL,
    "quality": OPERATIONAL,
    "market_radar": ADVERSARIAL,
    "pricing": MARKET,
    "creative_assets": OPERATIONAL,
    "seo_search": ADVERSARIAL,
    "growth": MARKET,
    "customer_experience": OPERATIONAL,
    "portfolio": OPERATIONAL,
    "finance": OPERATIONAL,
    "runtime": OPERATIONAL,
}

# How long a capability may sit still before flatness is a finding rather than a short
# window. Longer than the slowest evidence interval on purpose: a department measured weekly
# needs several measurements before "has not improved" means anything.
FLATNESS_WINDOW_DAYS = 28

# Measurements needed before a direction may be claimed at all. One point is a value, two is
# a line through two points, three is the first number that can disagree with the previous
# two -- which is where `improve.profiles` already puts DECLINE_RUN.
MIN_POINTS_FOR_DIRECTION = 3

# How much a capability has to move across the window to count as having moved. Below this it
# is the same number with different noise on it.
MOVEMENT_THRESHOLD = 0.02


class FreshnessRefused(ValueError):
    """A cell with no declared world, or an SLA somebody tried to set at the call site."""


# ---- verdicts -------------------------------------------------------------

FRESH = "fresh"
STALE = "stale"
NEVER_MEASURED = "never_measured"
NOT_TIME_BASED = "not_time_based"
FINGERPRINT_CHANGED = "fingerprint_changed"

IMPROVING = "improving"
DECLINING = "declining"
FLAT = "flat"
UNMEASURED = "unmeasured"

# The combination worth having a word for: on time, and going nowhere.
CHURNING = "churning"
HEALTHY = "healthy"
AT_RISK = "at_risk"


@dataclass(frozen=True)
class Sla:
    """One department's reconsideration interval, and where it comes from."""

    cell: str
    world: str
    hours: int | None
    why: str

    def to_dict(self) -> dict:
        return {"cell": self.cell, "world": self.world, "reconsider_after_hours": self.hours,
                "time_based": self.hours is not None, "why": self.why}


def sla(cell: str) -> Sla:
    """The interval for one cell. There is no argument that loosens it."""
    if cell not in BY_KEY:
        raise FreshnessRefused(f"{cell!r} is not an improvement cell: {sorted(BY_KEY)}")
    world = CELL_WORLD.get(cell)
    if world is None:
        raise FreshnessRefused(
            f"{cell!r} has no declared world speed. A cell without one would take a default "
            f"interval, and a single default interval across every department is the "
            f"arrangement this requirement exists to remove")
    hours, why = WORLD_SPEED[world]
    return Sla(cell=cell, world=world, hours=hours, why=why)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---- clock one: is the evidence current -----------------------------------

def evidence_age(db, cell: str, *, now: datetime | None = None,
                 code_fingerprint: str | None = None,
                 verified_fingerprint: str | None = None) -> dict:
    """Whether this department's last measurement still counts, by its own clock.

    A `mathematical` cell is answered on fingerprints rather than on hours, and if neither
    fingerprint is supplied it reports that it cannot say -- which is true, and better than
    reporting `fresh` because no date has passed.
    """
    from .cells import capability_history

    now = now or datetime.now(timezone.utc)
    spec = sla(cell)
    history = capability_history(db, cell)
    last = history[-1]["at"] if history else None

    if last is None:
        return {"cell": cell, "verdict": NEVER_MEASURED, "sla": spec.to_dict(),
                "last_measured": None,
                "why": ("no capability measurement has ever been recorded for this "
                        "department. That is not staleness -- stale evidence is re-run and "
                        "absent evidence is instrumented, and filing them together buries "
                        "the second kind under the first")}

    age_hours = (now - _aware(datetime.fromisoformat(last))).total_seconds() / 3600.0

    if spec.hours is None:
        if code_fingerprint is None or verified_fingerprint is None:
            return {"cell": cell, "verdict": NOT_TIME_BASED, "sla": spec.to_dict(),
                    "last_measured": last, "age_hours": round(age_hours, 2),
                    "why": ("this department does not go stale with time, and no code "
                            "fingerprint was supplied, so whether it is current is unknown "
                            "rather than yes")}
        changed = code_fingerprint != verified_fingerprint
        return {"cell": cell,
                "verdict": FINGERPRINT_CHANGED if changed else FRESH,
                "sla": spec.to_dict(), "last_measured": last,
                "age_hours": round(age_hours, 2),
                "fingerprint": code_fingerprint, "verified_against": verified_fingerprint,
                "why": ("the code behind this department changed since it was last verified, "
                        "which is the only way its evidence goes stale"
                        if changed else
                        "verified against the current code, and time alone does not "
                        "invalidate it")}

    stale = age_hours > spec.hours
    return {"cell": cell, "verdict": STALE if stale else FRESH, "sla": spec.to_dict(),
            "last_measured": last, "age_hours": round(age_hours, 2),
            "why": (f"{age_hours:.0f}h old against a {spec.hours}h interval: {spec.why}"
                    if stale else
                    f"{age_hours:.0f}h old, inside its {spec.hours}h interval")}


# ---- clock two: has the capability moved ----------------------------------

def capability_movement(db, cell: str, *, now: datetime | None = None,
                        window_days: int = FLATNESS_WINDOW_DAYS) -> dict:
    """Whether the number this department answers for has gone anywhere.

    Direction is read against the cell's own polarity, because half of these metrics are
    better when they fall -- defects, dead letters, support cases per order -- and a module
    that treats every rise as progress congratulates a department for breaking.
    """
    from .cells import capability_history

    now = now or datetime.now(timezone.utc)
    spec = BY_KEY[cell] if cell in BY_KEY else None
    if spec is None:
        raise FreshnessRefused(f"{cell!r} is not an improvement cell")

    cutoff = now - timedelta(days=window_days)
    points = [p for p in capability_history(db, cell)
              if _aware(datetime.fromisoformat(p["at"])) >= cutoff]

    if len(points) < MIN_POINTS_FOR_DIRECTION:
        return {"cell": cell, "verdict": UNMEASURED, "points": len(points),
                "window_days": window_days,
                "why": (f"{len(points)} measurement(s) in {window_days} days. One point is a "
                        f"value and two is a line through two points; "
                        f"{MIN_POINTS_FOR_DIRECTION} is the first number that can disagree "
                        f"with the ones before it")}

    first, last = points[0]["value"], points[-1]["value"]
    raw = last - first
    signed = raw if spec.higher_is_better else -raw
    scale = max(abs(first), 1e-9)
    relative = signed / scale

    if abs(relative) < MOVEMENT_THRESHOLD:
        verdict = FLAT
        why = (f"{first:.4f} to {last:.4f} over {window_days} days is the same number with "
               f"different noise on it, against a {MOVEMENT_THRESHOLD:.0%} threshold")
    elif relative > 0:
        verdict = IMPROVING
        why = f"{first:.4f} to {last:.4f} over {window_days} days, in the better direction"
    else:
        verdict = DECLINING
        why = f"{first:.4f} to {last:.4f} over {window_days} days, in the worse direction"

    return {"cell": cell, "verdict": verdict, "points": len(points),
            "window_days": window_days, "from": first, "to": last,
            "relative_change": round(relative, 4),
            "higher_is_better": spec.higher_is_better, "why": why}


# ---- the two clocks together ----------------------------------------------

def department(db, cell: str, *, now: datetime | None = None,
               code_fingerprint: str | None = None,
               verified_fingerprint: str | None = None) -> dict:
    """One department on both clocks, and the state that only appears when they disagree."""
    age = evidence_age(db, cell, now=now, code_fingerprint=code_fingerprint,
                       verified_fingerprint=verified_fingerprint)
    movement = capability_movement(db, cell, now=now)

    fresh = age["verdict"] in (FRESH,)
    if age["verdict"] == NEVER_MEASURED:
        state, why = AT_RISK, "never measured: there is nothing to be fresh or stale about"
    elif fresh and movement["verdict"] == FLAT:
        state, why = CHURNING, (
            "on time and going nowhere. A department re-measuring inside its interval and "
            "not moving scores perfectly on recency, which is why recency is not the only "
            "clock here -- this is the commonest real state of an improvement programme and "
            "a freshness check alone reports it as healthy")
    elif movement["verdict"] == DECLINING:
        state, why = AT_RISK, "the capability is moving the wrong way"
    elif age["verdict"] in (STALE, FINGERPRINT_CHANGED):
        state, why = AT_RISK, age["why"]
    elif movement["verdict"] == UNMEASURED:
        state, why = AT_RISK, movement["why"]
    else:
        state, why = HEALTHY, "current by its own clock, and moving"

    return {"cell": cell, "state": state, "why": why,
            "evidence": age, "capability": movement}


def sweep(db, *, now: datetime | None = None,
          fingerprints: dict[str, tuple[str, str]] | None = None) -> dict:
    """Every department, and the three things #191 asks the orchestrator to flag."""
    fingerprints = fingerprints or {}
    rows = []
    for spec in CELLS:
        code, verified = fingerprints.get(spec.key, (None, None))
        rows.append(department(db, spec.key, now=now, code_fingerprint=code,
                               verified_fingerprint=verified))

    stale_learning = [r["cell"] for r in rows
                      if r["evidence"]["verdict"] in (STALE, FINGERPRINT_CHANGED)]
    never = [r["cell"] for r in rows if r["evidence"]["verdict"] == NEVER_MEASURED]
    not_improving = [r["cell"] for r in rows
                     if r["capability"]["verdict"] in (FLAT, DECLINING)]
    churning = [r["cell"] for r in rows if r["state"] == CHURNING]

    return {
        "departments": rows,
        "stale_learning": sorted(stale_learning),
        "never_measured": sorted(never),
        "not_improving": sorted(not_improving),
        "churning": sorted(churning),
        "healthy": sorted(r["cell"] for r in rows if r["state"] == HEALTHY),
        "intervals": {spec.key: sla(spec.key).to_dict() for spec in CELLS},
        "note": ("two clocks, because a department that re-measures on time and never moves "
                 "is invisible to one of them. Never-measured is reported apart from stale: "
                 "one is instrumented and the other is re-run"),
    }


def state() -> dict:
    """The SLAs themselves, and why they are not one number."""
    return {
        "requirement": 191,
        "worlds": {k: {"hours": v[0], "why": v[1]} for k, v in WORLD_SPEED.items()},
        "cells": {k: v for k, v in sorted(CELL_WORLD.items())},
        "flatness_window_days": FLATNESS_WINDOW_DAYS,
        "min_points_for_direction": MIN_POINTS_FOR_DIRECTION,
        "movement_threshold": MOVEMENT_THRESHOLD,
        "replaces": ("the single 30-day constant carried separately by improve.profiles and "
                     "improve.bus, which is far too slow for a competitor's catalogue and "
                     "meaningless for the compiler"),
        "refuses": [
            "a cell with no declared world speed, rather than giving it a default interval",
            "a `mathematical` cell reported fresh on the strength of no date having passed",
            "a direction claimed from fewer than three measurements",
            "never-measured filed as stale",
        ],
        "note": ("compiler mathematics is not on a long interval -- it is on no interval. It "
                 "goes stale when the code changes, and a long interval would report it "
                 "current for another month after somebody changed the compiler"),
    }
