"""Two capacities, two clocks, and the fortnight a single clock throws away.

Requirement 267. Shift product and marketing capacity by time-to-event and make-time; early
season favours complex flagships, late season favours quick makes and giftables; roll capacity
forward before demand collapses.

Most of that already exists. `seasonal.compression` retires lanes one at a time and moves each
closing lane's share into the fastest lane still open, so the early-flagship / late-quick-make
shift falls out of the arithmetic rather than out of anybody remembering it in November, and
`next_year_track` starts next year's flagship under a cap. What is not there is the word
*and* in "product and marketing capacity", and it is not a detail.

**They run on different clocks.** Engineering leaves an occasion when its last lane closes —
when nothing new could be launched, indexed and finished in time. Marketing leaves later,
at the buyer's own last practical make date, because the catalogue already listed goes on
selling until then. Those two dates are weeks apart, and the weeks between them are the ones
that earn most: a maker buying a quick gift pattern on the 10th of December is the most
motivated buyer of the year, and the shop that budgeted one capacity against one calendar has
already moved its attention to February. So this module holds engineering and marketing as
separate ledgers over the same events, and the rule it exists to state is that **engineering
rolls forward first and marketing rolls forward last.**

**Rolling forward is refused in both directions.** Too early abandons the window that earns
most, which is why nothing may leave an occasion while a lane of it is still viable. Too late
is the failure wearing a different hat: capacity moved out of a season that is ending into one
whose own preparation lead has already passed has not been rescued — it has been spent on
being late twice. A receiving occasion has to be able to repay the work, and `PREPARATION_LEADS`
already says what that costs, so the check is arithmetic rather than judgement.

**What this cannot do is see demand fall.** "Before demand collapses" implies a curve, and the
only part of that curve this company can derive today is its hard floor: after the last
practical make date, demand for the occasion is structurally zero, because nobody can finish
the object. Where demand starts falling before that — and it does, because makers do not all
wait for the last possible day — is an observation about buyers, and this shop has never made
it. The floor is computed; the decay is reported as unobserved. Naming a decay date from a
plausible shape would be the same move as a point estimate establishing impossibility, which
`seasonal.uncertainty` exists to refuse.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .calendar import rolling
from .compression import (LAST_PRACTICAL_MAKE_DAYS, LAUNCH, MERCHANDISE, POST_OCCASION,
                          PREPARATION_LEADS, lane_states, mode_for)

ENGINEERING = "engineering"
MARKETING = "marketing"
CAPACITIES: tuple[str, ...] = (ENGINEERING, MARKETING)

# The longest preparation lead any occasion needs before it can be launched into. Capacity
# arriving later than this has arrived after the work it was meant to do.
LONGEST_PREPARATION_LEAD = max(days for days, _ in PREPARATION_LEADS.values())

OBSERVED_DECAY = "unobserved"


class ArbitrageRefused(ValueError):
    """A roll-forward that abandons a live window, or lands on one already closed."""


@dataclass(frozen=True)
class Standing:
    """One occasion's claim on each capacity today."""

    event: str
    event_date: date
    days_away: int
    mode: str
    open_lanes: tuple[str, ...]

    @property
    def holds_engineering(self) -> bool:
        """Only while something new could still be launched into this occasion."""
        return self.mode == LAUNCH

    @property
    def holds_marketing(self) -> bool:
        """Until the buyer's own last make date, which is after the last launch date."""
        return self.mode in (LAUNCH, MERCHANDISE)

    def to_dict(self) -> dict:
        return {"event": self.event, "event_date": self.event_date.isoformat(),
                "days_away": self.days_away, "mode": self.mode,
                "open_lanes": list(self.open_lanes),
                ENGINEERING: self.holds_engineering, MARKETING: self.holds_marketing}


def standings(today: date | None = None, *, samples: int = 0,
              skill: str = "intermediate") -> list[Standing]:
    """Every occasion on the rolling calendar, with what each capacity owes it."""
    today = today or date.today()
    out: list[Standing] = []
    for row in rolling(today)["events"]:
        when = date.fromisoformat(row["event_date"])
        days = row["days_away"]
        states = lane_states(days, samples=samples, today=today, skill=skill)
        out.append(Standing(
            event=row["event"], event_date=when, days_away=days,
            mode=mode_for(states, days_away=days)["mode"],
            open_lanes=tuple(s.lane for s in states if s.viable)))
    return out


def ledger(today: date | None = None, *, samples: int = 0,
           skill: str = "intermediate") -> dict:
    """Both capacities over all occasions, and the gap between the two clocks.

    The gap is the number worth reading: every occasion in `marketing_only` is one that
    engineering has correctly left and that marketing must not leave yet.
    """
    rows = standings(today, samples=samples, skill=skill)
    engineering = [r for r in rows if r.holds_engineering]
    marketing = [r for r in rows if r.holds_marketing]
    marketing_only = [r for r in marketing if not r.holds_engineering]
    return {
        "today": (today or date.today()).isoformat(),
        "events": [r.to_dict() for r in rows],
        ENGINEERING: [r.event for r in engineering],
        MARKETING: [r.event for r in marketing],
        "marketing_only": [r.event for r in marketing_only],
        "note": ("engineering leaves an occasion when its last lane closes; marketing leaves "
                 f"at the buyer's last practical make date, {LAST_PRACTICAL_MAKE_DAYS} days "
                 f"out. The occasions in between are the ones that earn most, and a shop "
                 f"running one capacity on one calendar has already left them"),
    }


def may_roll_forward(source: Standing, target: Standing, *, capacity: str) -> dict:
    """Whether this capacity may move from one occasion to another, and why not.

    Refused in both directions on purpose. Leaving early abandons the window that earns most;
    arriving late is the same mistake with a different date on it.
    """
    if capacity not in CAPACITIES:
        raise ArbitrageRefused(f"{capacity!r} is not a capacity: {list(CAPACITIES)}")
    if source.event == target.event:
        raise ArbitrageRefused("rolling capacity from an occasion to itself")

    holds = source.holds_engineering if capacity == ENGINEERING else source.holds_marketing
    if holds:
        return {"may_roll": False, "capacity": capacity,
                "from": source.event, "to": target.event,
                "why": (f"{source.event} still holds {capacity}: "
                        + (f"lanes {', '.join(source.open_lanes)} are open"
                           if capacity == ENGINEERING else
                           f"it is {source.days_away} days away and the buyer's last "
                           f"practical make date is {LAST_PRACTICAL_MAKE_DAYS} days out")
                        + ". Leaving while the window is live is the expensive half of this "
                          "decision, because the last weeks are the ones that earn most")}

    if target.days_away < 0:
        return {"may_roll": False, "capacity": capacity,
                "from": source.event, "to": target.event,
                "why": f"{target.event} has already happened"}

    if capacity == ENGINEERING:
        if not target.open_lanes:
            return {"may_roll": False, "capacity": capacity,
                    "from": source.event, "to": target.event,
                    "why": (f"{target.event} has no launchable lane left, so engineering "
                            f"arriving there cannot reach a buyer in time either. Moving "
                            f"capacity out of a season that is ending into one that is "
                            f"already late is the same mistake twice")}
        if target.days_away < LONGEST_PREPARATION_LEAD:
            return {"may_roll": False, "capacity": capacity,
                    "from": source.event, "to": target.event,
                    "why": (f"{target.event} is {target.days_away} days away and its longest "
                            f"preparation lead is {LONGEST_PREPARATION_LEAD} days: search "
                            f"language, creative and copy would all land after the work they "
                            f"exist to prepare")}
    elif target.mode == POST_OCCASION:
        return {"may_roll": False, "capacity": capacity,
                "from": source.event, "to": target.event,
                "why": f"{target.event} is past its buyer's last practical make date"}

    return {"may_roll": True, "capacity": capacity,
            "from": source.event, "to": target.event,
            "why": (f"{source.event} no longer holds {capacity} and {target.event} can still "
                    f"repay it: {target.days_away} days away"
                    + (f", lanes {', '.join(target.open_lanes)} open"
                       if capacity == ENGINEERING else ""))}


def roll_forward(today: date | None = None, *, samples: int = 0,
                 skill: str = "intermediate") -> dict:
    """Where each capacity should go today, occasion by occasion, with the refusals kept.

    The refusals are returned rather than filtered because a plan that lists only its moves
    reads identically whether nothing needed moving or everything was blocked.
    """
    rows = standings(today, samples=samples, skill=skill)
    by_capacity: dict[str, dict] = {}
    for capacity in CAPACITIES:
        moves, blocked = [], []
        for source in rows:
            holds = (source.holds_engineering if capacity == ENGINEERING
                     else source.holds_marketing)
            if holds:
                continue
            best = None
            for target in rows:
                if target.event == source.event:
                    continue
                verdict = may_roll_forward(source, target, capacity=capacity)
                if verdict["may_roll"] and (best is None
                                            or target.days_away < best[0].days_away):
                    best = (target, verdict)
            if best is None:
                blocked.append({"from": source.event,
                                "why": ("no occasion on the calendar can still repay this "
                                        "capacity")})
            else:
                moves.append(best[1])
        by_capacity[capacity] = {"moves": moves, "blocked": blocked}
    return {
        "today": (today or date.today()).isoformat(),
        "capacities": by_capacity,
        "rule": ("engineering rolls forward first and marketing rolls forward last, because "
                 "the occasion stops being launchable weeks before it stops being buyable"),
    }


def demand_curve(event_date: date, today: date | None = None) -> dict:
    """The one thing about the demand curve that can be computed, and the rest stated as open.

    The floor is arithmetic: past the buyer's last practical make date nobody can finish the
    object, so demand for the occasion is structurally zero. Where the curve starts bending
    before that is a fact about buyers, and no listing of this shop's has ever been watched
    through a season.
    """
    today = today or date.today()
    days = (event_date - today).days
    floor_on = event_date.toordinal() - LAST_PRACTICAL_MAKE_DAYS
    return {
        "event_date": event_date.isoformat(),
        "days_away": days,
        "structural_floor_on": date.fromordinal(floor_on).isoformat(),
        "past_floor": days < LAST_PRACTICAL_MAKE_DAYS,
        "floor_basis": (f"after {LAST_PRACTICAL_MAKE_DAYS} days out even a quick make cannot "
                        f"be finished in time, so demand is zero by construction rather than "
                        f"by measurement"),
        "decay_before_floor": OBSERVED_DECAY,
        "why_unobserved": ("makers do not all wait for the last possible day, so real demand "
                           "falls before the floor -- but this shop has never watched a "
                           "listing through a season, and a decay date taken from a "
                           "plausible curve is a point estimate presented as a fact"),
        "what_would_settle_it": ("one occasion's daily impressions and orders for a listing "
                                 "that was live through it"),
    }


def state() -> dict:
    """What #267 adds to the compression engine, and what it still cannot see."""
    return {
        "requirement": 267,
        "already_covered_by": {
            "seasonal.compression": ("lane retirement, the early-flagship to late-quick-make "
                                     "shift, priority reservation and next year's track"),
            "seasonal.calendar": "the rolling horizons and each event's launchable lane",
            "seasonal.leadtime": "make-time to launch date, as an interval",
        },
        "added_here": {
            "two_capacities": "engineering and marketing as separate ledgers over one calendar",
            "the_rule": "engineering rolls forward first; marketing rolls forward last",
            "cross_event": ("roll-forward to the next occasion that can still repay the "
                            "work, not only to next year's copy of this one"),
        },
        "refuses": [
            "moving any capacity out of an occasion that still holds it",
            "rolling engineering into an occasion inside its own preparation lead",
            "rolling marketing into an occasion past its last practical make date",
        ],
        "cannot_see": ("where demand starts falling before the structural floor. That is an "
                       "observation about buyers and no listing of this shop's has been "
                       "watched through a season"),
        "longest_preparation_lead_days": LONGEST_PREPARATION_LEAD,
        "last_practical_make_days": LAST_PRACTICAL_MAKE_DAYS,
    }
