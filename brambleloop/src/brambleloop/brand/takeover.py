"""Seasonal storefront transitions, scheduled from the calendar and reverted by it too.

Requirement 131. Five surfaces -- banner, featured collections, thumbnails, bundles and shop
content -- should turn over ahead of each seasonal buying window, and the requirement is
explicit that they are scheduled from the Collection Calendar rather than whenever somebody
notices the date.

Three things make this more than a to-do list.

**Surfaces do not transition together.** A banner changes early because it is what a returning
visitor sees first and it costs nothing to be early. Thumbnails change late, because a
thumbnail that says December in October is a thumbnail competing against products the buyer
can still finish. Scheduling them on one date is how a shop ends up either premature or late
on everything at once.

**A takeover declares its end at the moment it is planned.** The failure is not the Christmas
banner going up late; it is the Christmas banner still being up in February, which says
nobody is home more loudly than an empty shop does. The end date comes from the same calendar
as the start, so it exists before anybody is busy.

**Brand continuity is what makes the shop feel alive rather than unstable.** A storefront that
changes its wordmark, its palette anchor, its photographic language and its voice every
quarter is not seasonal, it is unrecognisable -- and the timeliness it buys is worth less than
the recognition it spends. So a takeover may change what is shown and not what the shop is,
and the invariants are listed rather than trusted to taste.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..seasonal.calendar import MILESTONES

# What a takeover is allowed to change, and how far ahead of the event each surface turns.
# The lead days are read off the collection calendar's own milestones rather than chosen:
# a banner rides the promotional ramp, thumbnails ride the peak window.
_MILESTONE_DAYS = {name: days for name, days, _ in MILESTONES}


@dataclass(frozen=True)
class Surface:
    key: str
    what: str
    lead_days: int
    why: str


SURFACES: tuple[Surface, ...] = (
    Surface("banner", "shop banner and announcement",
            _MILESTONE_DAYS["promotional_ramp"],
            "what a returning visitor sees first, and the one surface where being early "
            "costs nothing"),
    Surface("featured_collection", "the collection pinned to the front of the shop",
            _MILESTONE_DAYS["listing_indexing_date"],
            "the collection is live and indexed at this point, and featuring it is what "
            "gives it its first traffic -- earlier would feature a page that does not "
            "exist, later wastes the weeks when search is still learning what it is"),
    Surface("bundles", "seasonal bundles and their pricing",
            _MILESTONE_DAYS["promotional_ramp"],
            "a bundle is a decision about what a buyer purchases together, and it needs to "
            "be live before the weeks when they actually buy"),
    Surface("shop_content", "About line, section names, seasonal copy",
            _MILESTONE_DAYS["peak_window_opens"],
            "copy is cheap to change and is read by the cautious buyer, who is the one "
            "deciding whether this shop is still trading"),
    Surface("thumbnails", "seasonal thumbnail treatment across the catalogue",
            _MILESTONE_DAYS["peak_window_opens"],
            "a thumbnail that says December in October competes against products the buyer "
            "can still finish, which is the opposite of what it is for"),
)

SURFACE_BY_KEY: dict[str, Surface] = {s.key: s for s in SURFACES}

# When a takeover ends. Read from the calendar's own tail milestone so the end is as scheduled
# as the start: the Christmas banner still up in February says nobody is home.
ENDS_DAYS_AFTER_EVENT = -_MILESTONE_DAYS["clearance_or_evergreen"]

# What a takeover may never change. A shop that reinvents itself every quarter is not
# seasonal, it is unrecognisable, and the timeliness is worth less than the recognition.
CONTINUITY_INVARIANTS: dict[str, str] = {
    "wordmark": "the shop's name and its setting; a reset wordmark resets the shop",
    "icon_mark": "the loop-and-bramble mark, which is what a returning buyer recognises "
                 "at 40 pixels in a list of favourites",
    "palette_anchor": "the cream ground and pine anchor; seasonal colour is an accent on "
                      "them rather than a replacement for them",
    "photographic_language": "flat daylight, real fabric, no collage and no stock gloss",
    "voice": "plain, specific and unexcited, which is the thing the About page earns trust "
             "with",
    "policy_text": "delivery, returns, licence, support and privacy, which are promises "
                   "rather than decoration",
}


class TakeoverRefused(ValueError):
    """A takeover with no event, no end, or one that changes what the shop is."""


@dataclass
class Takeover:
    event: str
    event_date: date
    surfaces: tuple[str, ...]
    changes: dict[str, str]          # surface -> what it becomes
    changes_invariants: tuple[str, ...] = ()


def schedule(event: str, event_date: date, *, today: date | None = None,
             surfaces: tuple[str, ...] | None = None) -> dict:
    """When each surface turns over for this event, and what is already late.

    Dates come from the collection calendar rather than from a judgement about how much
    warning feels right, which is the difference between a shop that transitions and a shop
    that reacts.
    """
    today = today or date.today()
    keys = surfaces or tuple(s.key for s in SURFACES)
    unknown = [k for k in keys if k not in SURFACE_BY_KEY]
    if unknown:
        raise TakeoverRefused(f"unknown storefront surface(s): {unknown}")

    ends_on = event_date + timedelta(days=ENDS_DAYS_AFTER_EVENT)
    rows = []
    for key in keys:
        surface = SURFACE_BY_KEY[key]
        starts_on = event_date - timedelta(days=surface.lead_days)
        rows.append({
            "surface": key, "what": surface.what, "why": surface.why,
            "lead_days": surface.lead_days,
            "transitions_on": starts_on.isoformat(),
            "reverts_on": ends_on.isoformat(),
            "days_until": (starts_on - today).days,
            "overdue": starts_on < today,
            "reverting_overdue": ends_on < today,
        })
    rows.sort(key=lambda r: r["transitions_on"])

    overdue = [r["surface"] for r in rows if r["overdue"] and not r["reverting_overdue"]]
    stale = [r["surface"] for r in rows if r["reverting_overdue"]]
    return {
        "event": event,
        "event_date": event_date.isoformat(),
        "today": today.isoformat(),
        "ends_on": ends_on.isoformat(),
        "surfaces": rows,
        "overdue": overdue,
        "past_its_revert_date": stale,
        "note": (
            f"this takeover is past its revert date on {len(stale)} surface(s): a seasonal "
            f"storefront left up after the occasion says nobody is home more loudly than an "
            f"empty shop does" if stale else
            f"{len(overdue)} surface(s) are past their transition date" if overdue else
            "every surface has a scheduled date and none has passed"),
    }


def check(takeover: Takeover) -> list[str]:
    """Everything that would make a takeover cost more recognition than it buys."""
    problems: list[str] = []

    if not takeover.event.strip():
        problems.append(
            "TAKEOVER_NOT_SCHEDULED: a takeover with no event is a storefront change "
            "somebody felt like making, and #131 schedules these from the calendar")

    for surface in takeover.surfaces:
        if surface not in SURFACE_BY_KEY:
            problems.append(f"TAKEOVER_UNKNOWN_SURFACE: {surface}")
        elif not takeover.changes.get(surface, "").strip():
            problems.append(
                f"TAKEOVER_SURFACE_EMPTY: {surface} is listed and says nothing, which is a "
                f"plan to change it later rather than a takeover")

    for invariant in takeover.changes_invariants:
        why = CONTINUITY_INVARIANTS.get(invariant)
        problems.append(
            f"TAKEOVER_BREAKS_CONTINUITY: {invariant} -- {why}"
            if why else
            f"TAKEOVER_BREAKS_CONTINUITY: {invariant}")

    return problems


def plan(event: str, event_date: date, changes: dict[str, str], *,
         today: date | None = None, changes_invariants: tuple[str, ...] = ()) -> dict:
    """A scheduled, checked takeover, refused rather than flagged if it breaks continuity."""
    takeover = Takeover(event=event, event_date=event_date,
                        surfaces=tuple(changes), changes=dict(changes),
                        changes_invariants=changes_invariants)
    problems = check(takeover)
    if problems:
        raise TakeoverRefused("; ".join(problems))

    scheduled = schedule(event, event_date, today=today, surfaces=tuple(changes))
    scheduled["changes"] = dict(changes)
    scheduled["continuity_held"] = sorted(CONTINUITY_INVARIANTS)
    return scheduled


def calendar(events: dict[str, date], *, today: date | None = None) -> dict:
    """Every upcoming takeover in one list, soonest transition first."""
    today = today or date.today()
    plans = [schedule(name, when, today=today) for name, when in events.items()]
    plans.sort(key=lambda p: p["surfaces"][0]["transitions_on"] if p["surfaces"] else "")
    return {
        "today": today.isoformat(),
        "takeovers": plans,
        "overdue_surfaces": sum(len(p["overdue"]) for p in plans),
        "past_revert_date": sum(len(p["past_its_revert_date"]) for p in plans),
        "invariants": CONTINUITY_INVARIANTS,
        "note": ("Surfaces transition on different dates on purpose: a banner is early "
                 "because being early costs nothing, and thumbnails are late because one "
                 "saying December in October competes against what the buyer can still "
                 "finish (#131)."),
    }
