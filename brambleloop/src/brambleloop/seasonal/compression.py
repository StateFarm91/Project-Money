"""A major holiday is attacked with faster products as the slow ones close. It is not dropped.

The owner's correction, encoded so it never has to be given again. The make-time interval
work said a 150-hour flagship cannot be finished for this Christmas -- which is true, and
which a careless reader turns into "Christmas is closed". Those are different sentences, and
the difference is the whole commercial year.

**An event is not a product class.** The lead-time engine retires *classes*: a lane whose
optimistic bound has passed is genuinely gone, and building for it anyway spends the runway
that is left on something nobody can buy in time. But the event continues, and the correct
response to a closing lane is to move the capacity it was holding into the fastest lane that
is still open -- not out of the event. So this module can retire QUICK, SHORT, MEDIUM, LONG
and FLAGSHIP one at a time, and it cannot stand down a priority programme while any lane
remains viable. That refusal is a test, not a convention.

**The mix shifts by itself.** Each lane's share of engineering capacity is its runway verdict
weighted by how soon it closes, normalised. A lane that is comfortable but has months of
runway ranks below one that is merely tight and shuts in a fortnight, because the tight one is
the opportunity about to be lost. As the calendar advances, MEDIUM closes and its share moves
to SHORT, then SHORT's to QUICK. Nobody decides that; it falls out of the arithmetic, which is
the point -- a decision that has to be remembered is a decision that gets missed in November.

**Christmas is a taxonomy, not a blanket.** The departments come from the calendar's own
event map and are filtered by which lanes are still open, so what the programme names today
is stockings, ornaments, decor, coasters, garlands, giftables, bags and small amigurumi --
because those are what can still be finished, not because somebody remembered to list them.

**Preparation starts before the launch date, not on it.** Search language, creative assets and
listing copy each have their own lead, counted back from the lane's last optimistic launch. A
product that is ready on its launch date is late: indexing is not instant.

**Next year runs in parallel and capped.** Christmas 2027's flagship work is comfortable today
and should be started -- but it cannot take more than its cap while 2026 lanes are open, and
the cap is enforced rather than intended.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..creative.family import LANE_ORDER
from .calendar import EVENT_DEPARTMENTS, rolling
from .depth import DEPARTMENT_FORMS, department_brief, implied_lane

# Programmes this company treats as commercially top-priority, with the share of engineering
# capacity each reserves while it has any viable lane. Named here so that "is Christmas still
# a priority" is a lookup rather than a judgement somebody makes in a tired week.
PRIORITY_PROGRAMMES: dict[str, float] = {
    "Christmas": 0.45,
}

# The floor a priority programme's reservation may never fall below while any lane is open.
# Without it, a programme whose heavy lanes have closed decays into a rounding error exactly
# when its quick makes are the most sellable thing in the catalogue.
MIN_PRIORITY_SHARE = 0.25

# How much capacity next year's flagship track may take while this year still has open lanes.
NEXT_YEAR_FLAGSHIP_CAP = 0.20

# How viable a lane's runway is, as a weight. Infeasible is zero: the class is retired, which
# is the only thing the lead-time engine is allowed to conclude on its own.
VERDICT_WEIGHT: dict[str, float] = {
    "comfortable": 1.0,
    "tight": 0.75,
    "high_risk": 0.35,
    "infeasible": 0.0,
}

# Days before a lane's last optimistic launch that each preparation stream must start. A
# product ready on its launch date is late, because indexing is not instant and a listing
# nobody can find is not a launch.
PREPARATION_LEADS: dict[str, tuple[int, str]] = {
    "search_language": (28, "map buyer language before the copy is written, or the copy is "
                            "written in ours"),
    "creative_assets": (21, "photography and thumbnails take longer than anybody plans for"),
    "listing_copy": (14, "copy, tags and sections, written against the mapped language"),
    "collection_and_bundles": (10, "a bundle is a decision about what is bought together and "
                                   "has to exist before the traffic does"),
}


# What the programme is doing, which is not the same question as whether a new product can be
# launched. A launch lane closing does not end the occasion: the catalogue that is already
# listed goes on selling until the buyer's own last make date, and the work shifts from
# engineering to merchandising rather than stopping. Conflating those is how a company stops
# working on Christmas in late November, which is the fortnight it earns most of the money.
LAUNCH, MERCHANDISE, POST_OCCASION = "launch", "merchandise", "post_occasion"

# The buyer's last practical purchase date for the fastest lane, read off the collection
# calendar's own milestone: after this even a quick make cannot be finished in time.
LAST_PRACTICAL_MAKE_DAYS = 21


class CompressionRefused(ValueError):
    """A priority programme stood down while it still had a viable lane."""


@dataclass(frozen=True)
class LaneState:
    lane: str
    verdict: str
    meaning: str
    latest_optimistic_launch: date | None
    runway_days: int | None

    @property
    def viable(self) -> bool:
        return VERDICT_WEIGHT.get(self.verdict, 0.0) > 0

    def to_dict(self) -> dict:
        return {"lane": self.lane, "verdict": self.verdict, "meaning": self.meaning,
                "latest_optimistic_launch": (self.latest_optimistic_launch.isoformat()
                                             if self.latest_optimistic_launch else None),
                "runway_days": self.runway_days, "viable": self.viable}


def lane_states(days_away: int, *, samples: int = 0, today: date | None = None,
                skill: str = "intermediate") -> list[LaneState]:
    """Each lane's runway for this event, with how long is left to start it."""
    from .calendar import lane_feasibility

    today = today or date.today()
    out = []
    for row in lane_feasibility(days_away, skill, samples=samples, today=today):
        launch = (date.fromisoformat(row["latest_optimistic_launch"])
                  if row["latest_optimistic_launch"] else None)
        out.append(LaneState(
            lane=row["lane"], verdict=row["verdict"], meaning=row["meaning"],
            latest_optimistic_launch=launch,
            runway_days=((launch - today).days if launch else None)))
    return out


def mix(states: list[LaneState], *, days_away: int) -> dict:
    """How engineering capacity should be split across lanes today.

    Weight is runway viability multiplied by urgency, where urgency rises as a lane approaches
    the last date it can be started. A comfortable lane with three months of runway ranks
    below a tight one that shuts in a fortnight, because the tight one is the opportunity
    about to be lost and the comfortable one will still be there next month.

    This is what makes the shift automatic. As MEDIUM closes its weight becomes zero and the
    normalisation moves that share to SHORT, then SHORT's to QUICK. Nothing decides it.
    """
    weights: dict[str, float] = {}
    for state in states:
        base = VERDICT_WEIGHT.get(state.verdict, 0.0)
        if base <= 0:
            weights[state.lane] = 0.0
            continue
        runway = state.runway_days if state.runway_days is not None else days_away
        # Urgency in [0.5, 1.0]: a lane with no runway left is twice as urgent as one whose
        # window is as wide as the whole horizon.
        urgency = 1.0 - 0.5 * min(1.0, max(0, runway) / max(1, days_away))
        weights[state.lane] = base * urgency

    total = sum(weights.values())
    shares = ({lane: round(w / total, 3) for lane, w in weights.items()} if total
              else {lane: 0.0 for lane in weights})
    open_lanes = [s.lane for s in states if s.viable]
    leading = max(shares, key=shares.get) if total else None
    return {
        "shares": shares,
        "open_lanes": open_lanes,
        "retired_lanes": [s.lane for s in states if not s.viable],
        "leading_lane": leading,
        "note": (
            "every lane for this event has passed its last optimistic launch, so the "
            "programme's work now is next year's rather than this year's"
            if not open_lanes else
            f"capacity leads with {leading}: it is the open lane closest to the last date it "
            f"can be started, and the lanes behind it inherit its share as it closes"),
    }


def retired_classes(states: list[LaneState]) -> list[dict]:
    """Which product classes the lead-time engine has actually retired, with the evidence.

    A retirement is a statement about one class on one date, never about the event. It is
    recorded in those terms so that "the flagship is impossible" cannot be read a fortnight
    later as "Christmas is closed".
    """
    return [{"lane": s.lane, "why": s.meaning,
             "last_optimistic_launch": (s.latest_optimistic_launch.isoformat()
                                        if s.latest_optimistic_launch else None),
             "scope": "this product class for this occasion only"}
            for s in states if not s.viable]


def arenas(event: str, states: list[LaneState], *, days_away: int, samples: int = 0,
           today: date | None = None) -> dict:
    """The departments worth attacking for this event, filtered to lanes still open.

    This is where "Christmas is not blankets" stops being a slogan. The departments come from
    the calendar's own map of what the occasion spans, each form carries the lane its size
    implies, and anything whose lane has retired drops out on its own.
    """
    open_lanes = {s.lane for s in states if s.viable}
    spans = EVENT_DEPARTMENTS.get(event, ())
    pursue, closed = [], []
    for department in spans:
        if department not in DEPARTMENT_FORMS:
            continue
        forms = [{"form": f, "lane": implied_lane(f)} for f in DEPARTMENT_FORMS[department]]
        live = [f for f in forms if f["lane"] in open_lanes]
        if live:
            live.sort(key=lambda f: LANE_ORDER.index(f["lane"]))
            pursue.append({"department": department, "forms": live,
                           "fastest_lane": live[0]["lane"]})
        else:
            closed.append({"department": department,
                           "why": "every form serving it is in a retired lane"})
    pursue.sort(key=lambda d: LANE_ORDER.index(d["fastest_lane"]))
    return {"pursue": pursue, "closed": closed,
            "note": (f"{len(pursue)} department(s) can still be launched for this {event}; "
                     f"the list is what the occasion spans filtered by what can still be "
                     f"finished, not a category somebody remembered")}


def bundles(pursue: list[dict]) -> list[dict]:
    """Where a coordinated collection is commercially useful rather than decorative.

    Two departments sharing a lane can be made, photographed and launched together, which is
    what a bundle actually requires. Departments in different lanes make a bundle whose
    slowest member decides the launch date, and that is how a quick make ends up waiting for
    a throw.
    """
    by_lane: dict[str, list[str]] = {}
    for row in pursue:
        by_lane.setdefault(row["fastest_lane"], []).append(row["department"])
    return [{"lane": lane, "departments": sorted(names),
             "why": ("these share a make lane, so they can be engineered, photographed and "
                     "launched as one thing rather than a bundle waiting on its slowest "
                     "member")}
            for lane, names in sorted(by_lane.items(), key=lambda kv: LANE_ORDER.index(kv[0]))
            if len(names) >= 2]


def preparation(states: list[LaneState], *, today: date | None = None) -> list[dict]:
    """When each preparation stream has to start, counted back from the launch it serves."""
    today = today or date.today()
    out = []
    for state in states:
        if not state.viable or state.latest_optimistic_launch is None:
            continue
        for stream, (lead, why) in PREPARATION_LEADS.items():
            starts = state.latest_optimistic_launch - timedelta(days=lead)
            out.append({"lane": state.lane, "stream": stream, "why": why,
                        "starts_on": starts.isoformat(),
                        "days_until": (starts - today).days,
                        "overdue": starts < today})
    out.sort(key=lambda r: r["starts_on"])
    return out


def reservation(event: str, states: list[LaneState], *, mode: str = LAUNCH) -> dict:
    """The engineering capacity this programme holds, and why it cannot fall to nothing."""
    base = PRIORITY_PROGRAMMES.get(event)
    open_lanes = [s for s in states if s.viable]
    if base is None:
        return {"priority": False, "share": 0.0,
                "why": f"{event} is not a named priority programme"}
    if open_lanes:
        share = max(base, MIN_PRIORITY_SHARE)
    elif mode == MERCHANDISE:
        # Nothing new is engineered and the occasion is at its most sellable. The reservation
        # holds at the floor for promotion, bundling and support, because releasing it here
        # is releasing it in the fortnight that earns the money.
        share = MIN_PRIORITY_SHARE
    else:
        share = 0.0
    return {
        "priority": True,
        "share": round(share, 3),
        "floor": MIN_PRIORITY_SHARE,
        "open_lanes": [s.lane for s in open_lanes],
        "mode": mode,
        "why": ("a priority programme whose heavy lanes have closed keeps its reservation, "
                "because its quick makes are then the most sellable thing in the catalogue "
                "and a decaying reservation is how that gets missed"
                if open_lanes else
                "no new product can be launched in time, and the listed catalogue is at its "
                "most sellable: the reservation holds at the floor for promotion, bundling "
                "and support" if mode == MERCHANDISE else
                "past the buyer's last practical make date, so this year's reservation is "
                "released to next year's programme for this occasion"),
    }


def next_year_track(event: str, *, today: date | None = None, samples: int = 0) -> dict:
    """The flagship work for next year's occasion, started early and capped.

    A flagship needs a year of runway, which is exactly why it is always the thing nobody
    started. It is also exactly why it must not be allowed to eat the capacity of the
    occasion that is three months away.
    """
    today = today or date.today()
    this_year = {e["event"]: date.fromisoformat(e["event_date"])
                 for e in rolling(today)["events"]}
    when = this_year.get(event)
    if when is None:
        return {"event": event, "tracked": False,
                "why": f"{event} is not on the rolling calendar"}
    try:
        next_date = when.replace(year=when.year + 1)
    except ValueError:  # pragma: no cover - 29 February
        next_date = when + timedelta(days=365)

    states = lane_states((next_date - today).days, samples=samples, today=today)
    heavy = [s for s in states if s.lane in ("LONG", "FLAGSHIP") and s.viable]
    return {
        "event": event,
        "tracked": True,
        "event_date": next_date.isoformat(),
        "days_away": (next_date - today).days,
        "lanes": [s.to_dict() for s in states if s.lane in ("LONG", "FLAGSHIP")],
        "may_start": [s.lane for s in heavy],
        "capacity_cap": NEXT_YEAR_FLAGSHIP_CAP,
        "note": ("next year's heavy lanes are open and should be started now -- a flagship "
                 "needs a year of runway, which is why it is always the thing nobody "
                 "started. Capped so it cannot take the capacity of the occasion that is "
                 "three months away"
                 if heavy else
                 "no heavy lane is open even for next year, which would be a calendar fault "
                 "rather than a plan"),
    }


def mode_for(states: list[LaneState], *, days_away: int) -> dict:
    """Whether the programme is launching, merchandising, or finished for this year."""
    if any(s.viable for s in states):
        return {"mode": LAUNCH,
                "what": "engineer and launch into the lanes that are still open",
                "why": "at least one product class can still reach a buyer in time"}
    if days_away >= 0 and days_away >= LAST_PRACTICAL_MAKE_DAYS:
        return {"mode": MERCHANDISE,
                "what": ("promote, bundle and support what is already listed; no new "
                         "product enters the catalogue for this occasion"),
                "why": ("no new listing can be launched and indexed in time, and the "
                        "catalogue that already exists goes on selling until the buyer's "
                        "own last make date. A closed launch lane is not a closed occasion")}
    return {"mode": POST_OCCASION,
            "what": "release the reservation and carry the evidence into next year",
            "why": (f"past the last practical make date ({LAST_PRACTICAL_MAKE_DAYS} days "
                    f"out), after which even a quick make cannot be finished in time")}


def programme(event: str = "Christmas", *, today: date | None = None, samples: int = 0,
              skill: str = "intermediate") -> dict:
    """The whole compression strategy for one occasion, from today to the date itself.

    Answers the only question that matters as a window narrows: given what a buyer can still
    finish, what should this company be building this week?
    """
    today = today or date.today()
    events = {e["event"]: e for e in rolling(today)["events"]}
    state = events.get(event)
    if state is None:
        raise CompressionRefused(f"{event} is not on the rolling calendar")

    days_away = state["days_away"]
    states = lane_states(days_away, samples=samples, today=today, skill=skill)
    the_mix = mix(states, days_away=days_away)
    hunting = arenas(event, states, days_away=days_away, samples=samples, today=today)
    stance = mode_for(states, days_away=days_away)
    held = reservation(event, states, mode=stance["mode"])

    plan = {
        "event": event,
        "event_date": state["event_date"],
        "today": today.isoformat(),
        "days_away": days_away,
        "priority": event in PRIORITY_PROGRAMMES,
        "mode": stance,
        "lanes": [s.to_dict() for s in states],
        "mix": the_mix,
        "retired_classes": retired_classes(states),
        "arenas": hunting["pursue"],
        "closed_arenas": hunting["closed"],
        "bundles": bundles(hunting["pursue"]),
        "preparation": preparation(states, today=today),
        "capacity": held,
        "next_year": next_year_track(event, today=today, samples=samples),
        "calibrated": samples > 0,
    }
    plan["note"] = _headline(plan)
    check(plan)
    return plan


def _headline(plan: dict) -> str:
    open_lanes = plan["mix"]["open_lanes"]
    retired = [r["lane"] for r in plan["retired_classes"]]
    if not open_lanes:
        if plan["mode"]["mode"] == MERCHANDISE:
            return (f"no new product can be launched for this {plan['event']} in time, and "
                    f"the occasion is at its most sellable: the work is promoting, bundling "
                    f"and supporting the catalogue that is already listed. A closed launch "
                    f"lane is not a closed occasion")
        return (f"past the buyer's last practical make date for this {plan['event']}. The "
                f"programme's work is next year's, and that is a conclusion reached one "
                f"product class at a time rather than a decision to skip the occasion")
    return (f"{plan['days_away']} days out: {', '.join(open_lanes)} still have runway and "
            f"{', '.join(retired) or 'nothing'} has been retired. Capacity leads with "
            f"{plan['mix']['leading_lane']} across {len(plan['arenas'])} department(s). A "
            f"retired class is a statement about that class, never about the occasion")


def check(plan: dict) -> None:
    """Refuse the three ways this strategy could quietly become a stand-down."""
    if plan["priority"]:
        open_lanes = plan["mix"]["open_lanes"]
        if plan["mode"]["mode"] == MERCHANDISE and plan["capacity"]["share"] <= 0:
            raise CompressionRefused(
                f"{plan['event']} is in its merchandising window with no reserved capacity. "
                f"This is the fortnight the occasion earns the money, and releasing the "
                f"reservation here releases it exactly then")
        if open_lanes and plan["capacity"]["share"] < MIN_PRIORITY_SHARE:
            raise CompressionRefused(
                f"{plan['event']} is a priority programme with open lanes {open_lanes} and "
                f"a reservation of {plan['capacity']['share']}, below the floor of "
                f"{MIN_PRIORITY_SHARE}. A programme whose heavy lanes closed must not decay "
                f"into a rounding error exactly when its quick makes are the most sellable "
                f"thing in the catalogue")
        if open_lanes and not plan["arenas"]:
            raise CompressionRefused(
                f"{plan['event']} has open lanes {open_lanes} and no department to pursue, "
                f"which means the occasion is being treated as one product class. It is a "
                f"taxonomy: stockings, ornaments, decor, garlands, giftables and small "
                f"amigurumi are not blankets")
    for row in plan["retired_classes"]:
        if row["scope"] != "this product class for this occasion only":
            raise CompressionRefused(
                "a retirement was recorded with a scope wider than one product class. The "
                "lead-time engine may retire a class; nothing in it may retire an occasion")
