"""The rolling 365-day calendar, and why it is not a set of strike teams.

Requirements 286, 287, 288, 289, 290, 292, 299. #286 is specific about the thing it does not
want: separate one-off Christmas strike teams. The reason is visible in how a shop with strike
teams behaves — Christmas gets attention in October, Easter gets none until March, and the
eleven months between are spent discovering that the window for the next event closed while
everyone was busy with the last one.

A rolling calendar is the alternative: every day, look 30, 60, 90, 120, 180 and 365 days ahead
and ask what each horizon demands *today*. The lead-time engine already computes when a product
must be live; this decides which events are worth having products for at all, and what phase
each one is in right now.

Two things it refuses to do.

**It will not reduce an event to one product (#288).** A Christmas represented by one blanket
is a Christmas with one chance. Each event carries the departments the maker-and-gift ecosystem
actually spans, and coverage is measured against that spread rather than against a count.

**It will not let a flash trend buy flagship engineering (#290).** A trend's half-life decides
how much work it is allowed to justify: many weeks of engineering spent on something that
expires before a customer could finish it is the most expensive possible mistake, because it
costs the window as well as the work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..radar.market import SEASONAL_EVENTS

# The horizons #286 names. Each asks a different question, which is why they are separate.
HORIZONS: tuple[int, ...] = (30, 60, 90, 120, 180, 365)

# What phase an event is in, from furthest out to closest. The phase decides what kind of work
# is useful now; doing research at launch time or creative at ninety days is the waste a
# rolling calendar exists to prevent.
PHASES: tuple[str, ...] = (
    "research", "concept", "engineering", "test", "assets", "launch", "optimise",
    "late_quick_make", "closed",
)

# Half-lives (#290), and the heaviest lane each one may justify. A flash trend that expires
# before a customer could finish the object cannot buy flagship engineering, whatever its
# apparent demand.
HALF_LIVES: dict[str, str] = {
    "flash": "QUICK",
    "short_seasonal": "SHORT",
    "recurring_seasonal": "LONG",
    "multi_season_fashion": "FLAGSHIP",
    "evergreen": "FLAGSHIP",
}

LANE_ORDER: tuple[str, ...] = ("QUICK", "SHORT", "MEDIUM", "LONG", "FLAGSHIP")

# The maker-and-gift ecosystem an event actually spans (#288). Listed per event because a
# Christmas spans nearly everything and a Valentine's does not, and pretending otherwise
# produces a coverage matrix that is mostly empty by construction.
EVENT_DEPARTMENTS: dict[str, tuple[str, ...]] = {
    "Christmas": ("garments", "blankets", "stockings", "ornaments", "home_decor", "bags",
                  "hats", "seasonal_gift"),
    "Halloween": ("ornaments", "home_decor", "seasonal_gift", "bags", "hats"),
    "Thanksgiving (CA)": ("home_decor", "blankets", "seasonal_gift"),
    "Valentine's": ("home_decor", "seasonal_gift", "ornaments"),
    "Easter": ("ornaments", "home_decor", "seasonal_gift", "bags"),
    "Mother's Day": ("garments", "bags", "home_decor", "seasonal_gift"),
}

DEFAULT_DEPARTMENTS: tuple[str, ...] = ("home_decor", "seasonal_gift")


class CalendarRefused(ValueError):
    """A trend asking for more engineering than its half-life can repay."""


@dataclass(frozen=True)
class Horizon:
    days: int
    events: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"days": self.days, "events": list(self.events)}


@dataclass
class EventState:
    """One event, where it is in its cycle, and what that means for work today."""

    name: str
    event_date: date
    days_away: int
    phase: str
    departments: tuple[str, ...]
    heaviest_lane_still_launchable: str | None
    covered_departments: tuple[str, ...] = ()
    strike_team: str = ""
    note: str = ""

    @property
    def coverage_gaps(self) -> tuple[str, ...]:
        return tuple(d for d in self.departments if d not in self.covered_departments)

    def to_dict(self) -> dict:
        return {
            "event": self.name, "event_date": self.event_date.isoformat(),
            "days_away": self.days_away, "phase": self.phase,
            "departments": list(self.departments),
            "covered": list(self.covered_departments),
            "gaps": list(self.coverage_gaps),
            "heaviest_lane_still_launchable": self.heaviest_lane_still_launchable,
            "strike_team": self.strike_team, "note": self.note,
        }


def phase_for(days_away: int) -> str:
    """What kind of work an event deserves today.

    The boundaries come from the lead-time engine's own arithmetic rather than from taste: a
    long make needs roughly a hundred days of runway, so an event a hundred days out is past
    the point where new flagship engineering can start.
    """
    if days_away < 0:
        return "closed"
    if days_away <= 7:
        return "late_quick_make"
    if days_away <= 30:
        return "optimise"
    if days_away <= 60:
        return "launch"
    if days_away <= 90:
        return "assets"
    if days_away <= 120:
        return "test"
    if days_away <= 180:
        return "engineering"
    if days_away <= 270:
        return "concept"
    return "research"


def heaviest_launchable_lane(days_away: int, skill: str = "intermediate",
                             *, samples: int = 0, today: date | None = None) -> str | None:
    """The biggest product a customer could still finish, given today.

    Graded against the *optimistic* bound of the make-time interval rather than the point
    estimate. The difference is not academic: a 90-hour Christmas project reads as impossible
    on a point estimate built from an assumed seven crochet hours a week, and reads as high
    risk once the interval is honest about never having timed a maker. Abandoning a season on
    an assumption cannot be discovered later, because nothing gets built to find out with.
    """
    from .leadtime import LANE_MAX_HOURS, compile_launch
    from .uncertainty import INFEASIBLE

    today = today or date.today()
    if days_away < 0:
        return None
    event_date = today + timedelta(days=days_away)
    for lane in reversed(LANE_ORDER):
        hours = LANE_MAX_HOURS[lane]
        probe = hours if hours != float("inf") else 150.0
        plan = compile_launch("probe", event_date, make_hours=probe, skill=skill,
                              samples=samples)
        if plan.feasibility(today)["verdict"] != INFEASIBLE:
            return lane
    return None


def lane_feasibility(days_away: int, skill: str = "intermediate", *, samples: int = 0,
                     today: date | None = None) -> list[dict]:
    """Every lane's verdict, so a window is read as a gradient rather than a cliff."""
    from .leadtime import LANE_MAX_HOURS, compile_launch

    today = today or date.today()
    event_date = today + timedelta(days=max(0, days_away))
    out = []
    for lane in LANE_ORDER:
        hours = LANE_MAX_HOURS[lane]
        probe = hours if hours != float("inf") else 150.0
        plan = compile_launch("probe", event_date, make_hours=probe, skill=skill,
                              samples=samples)
        graded = plan.feasibility(today)
        out.append({"lane": lane, "probe_hours": probe, "verdict": graded["verdict"],
                    "meaning": graded["meaning"],
                    "days_needed": graded["days_needed"],
                    "latest_optimistic_launch": (plan.latest_optimistic_launch.isoformat()
                                                 if plan.latest_optimistic_launch else None)})
    return out


def rolling(today: date | None = None, *, covered: dict[str, tuple[str, ...]] | None = None,
            strike_teams: dict[str, str] | None = None) -> dict:
    """The whole calendar as it stands today, across every horizon.

    Events are listed once with their true distance, and the horizons index into them. A
    calendar that duplicated an event per horizon would read as six times the work.
    """
    today = today or date.today()
    covered = covered or {}
    strike_teams = strike_teams or {}

    states: list[EventState] = []
    for event in SEASONAL_EVENTS:
        days = (event.event_date - today).days
        # An event that has passed rolls to next year: the calendar is rolling, so Christmas
        # is never zero days away for eleven months.
        if days < 0:
            try:
                next_year = event.event_date.replace(year=event.event_date.year + 1)
            except ValueError:  # pragma: no cover - 29 February
                next_year = event.event_date + timedelta(days=365)
            days = (next_year - today).days
            event_date = next_year
        else:
            event_date = event.event_date

        departments = EVENT_DEPARTMENTS.get(event.name, DEFAULT_DEPARTMENTS)
        states.append(EventState(
            name=event.name, event_date=event_date, days_away=days,
            phase=phase_for(days), departments=departments,
            heaviest_lane_still_launchable=heaviest_launchable_lane(days),
            covered_departments=tuple(covered.get(event.name, ())),
            strike_team=strike_teams.get(event.name, ""),
            note=("this event is inside the window where only quick makes can still reach a "
                  "customer in time" if days <= 30 else "")))

    states.sort(key=lambda s: s.days_away)
    horizons = [Horizon(h, tuple(s.name for s in states if s.days_away <= h))
                for h in HORIZONS]

    return {
        "today": today.isoformat(),
        "horizons": [h.to_dict() for h in horizons],
        "events": [s.to_dict() for s in states],
        "next_event": states[0].to_dict() if states else None,
        "note": ("A rolling calendar rather than strike teams: every event is always some "
                 "number of days away, so none of them is discovered late (#286)."),
    }


def check_half_life(half_life: str, lane: str) -> None:
    """Refuse engineering a trend cannot repay (#290).

    Many weeks of flagship work on something that expires before a customer could finish it
    costs the window as well as the work, which is why this is a refusal rather than a
    ranking penalty.
    """
    if half_life not in HALF_LIVES:
        raise CalendarRefused(
            f"{half_life!r} is not a half-life: {sorted(HALF_LIVES)}. An unclassified trend "
            f"gets whatever effort somebody felt like spending")
    if lane not in LANE_ORDER:
        raise CalendarRefused(f"{lane!r} is not a make lane")

    ceiling = HALF_LIVES[half_life]
    if LANE_ORDER.index(lane) > LANE_ORDER.index(ceiling):
        raise CalendarRefused(
            f"a {half_life} trend may not justify {lane} engineering (ceiling {ceiling}). "
            f"Multi-week work on something that expires before a customer finishes it costs "
            f"the window as well as the work")


def coverage_matrix(today: date | None = None,
                    covered: dict[str, tuple[str, ...]] | None = None) -> dict:
    """Events against departments: where the ecosystem has no Brambleloop answer (#288, #299).

    Depth is measured against the departments an event actually spans, not against a target
    count, because "six Christmas products" says nothing about whether five of them are
    blankets.
    """
    state = rolling(today, covered=covered)
    rows = []
    for event in state["events"]:
        spread = len(event["departments"])
        have = len(event["covered"])
        rows.append({
            "event": event["event"],
            "days_away": event["days_away"],
            "phase": event["phase"],
            "departments": event["departments"],
            "covered": event["covered"],
            "gaps": event["gaps"],
            "depth": round(have / spread, 3) if spread else 0.0,
            "heaviest_lane_still_launchable": event["heaviest_lane_still_launchable"],
        })
    rows.sort(key=lambda r: (r["depth"], r["days_away"]))
    total_spread = sum(len(r["departments"]) for r in rows)
    total_have = sum(len(r["covered"]) for r in rows)
    return {
        "today": state["today"],
        "rows": rows,
        "ecosystem_depth": round(total_have / total_spread, 3) if total_spread else 0.0,
        "thinnest": rows[0]["event"] if rows else None,
        "note": ("Depth is coverage of the departments an event actually spans. Six Christmas "
                 "products say nothing about whether five of them are blankets (#288)."),
    }


# ---------------------------------------------------------------------------
# The collection calendar (#123)
#
# The phase machinery above answers "what kind of work is useful today". This answers the
# harder question: which dated commitments exist, and which have already been missed. A phase
# that has quietly slipped is invisible -- it just becomes the next phase -- and #123 is
# explicit that a missed date is a portfolio failure rather than a scheduling detail.

# Days before the event each milestone falls. Derived from the lead-time engine's own
# arithmetic rather than chosen: a long make needs roughly a hundred days of runway, and every
# date here is that runway divided among the things that must happen inside it.
MILESTONES: tuple[tuple[str, int, str], ...] = (
    ("research_start", 300, "what this occasion wants, before anybody has an idea"),
    ("concept_freeze", 240, "after this the set of concepts stops changing"),
    ("engineering_start", 210, "the CIR work begins"),
    ("physical_test_deadline", 150, "a sample has to be in somebody's hands by now"),
    ("creative_production_deadline", 110, "assets finished, because indexing takes weeks"),
    ("listing_indexing_date", 90, "listed and indexed, not listed"),
    ("promotional_ramp", 60, "the push begins, while there is still time to buy"),
    ("peak_window_opens", 45, "the weeks when people actually buy this"),
    ("last_practical_make_date", 21, "after this a customer cannot finish it in time"),
    ("clearance_or_evergreen", -7, "what happens to it after the occasion passes"),
)


def collection_calendar(event_name: str, event_date: date,
                        today: date | None = None,
                        completed: dict[str, str] | None = None) -> dict:
    """Every dated commitment for one occasion, and which have been missed (#123).

    A missed milestone is reported as a portfolio failure with the reason it matters, not as
    an amber row. The failure mode this exists for is silent: a phase that slips does not
    announce itself, it simply becomes the next phase, and the first visible symptom is a
    product that lists in December.
    """
    today = today or date.today()
    completed = completed or {}

    rows = []
    missed = []
    for key, days_before, why in MILESTONES:
        due = event_date - timedelta(days=days_before)
        done_on = completed.get(key)
        state = ("done" if done_on else
                 "missed" if due < today else
                 "due" if (due - today).days <= 14 else "ahead")
        row = {"milestone": key, "due": due.isoformat(), "days_from_today": (due - today).days,
               "why": why, "state": state, "completed_on": done_on}
        rows.append(row)
        if state == "missed":
            missed.append(row)

    return {
        "event": event_name,
        "event_date": event_date.isoformat(),
        "today": today.isoformat(),
        "milestones": rows,
        "missed": missed,
        "on_schedule": not missed,
        "next_due": next((r for r in rows if r["state"] in ("due", "ahead")), None),
        "note": ("A missed date is a portfolio failure and feeds the retrospective, not an "
                 "amber row. The failure is silent -- a phase that slips does not announce "
                 "itself, it becomes the next phase, and the first visible symptom is a "
                 "product that lists in December (#123)."),
    }
