"""A pin set that is genuinely several pins, and a schedule that is not about the event.

Requirement 246. An autonomous Pinterest production system around each validated product:
several genuinely distinct pins, keyword and board mapping, seasonal lead-time scheduling, a
landing destination, creative testing and attribution -- and, stated outright, *avoid spammy
duplicate pins*.

That last instruction is the one with a mechanism behind it, and the mechanism is not about
images. Five pins that differ in crop, text overlay and filter are one pin posted five times,
and they are indistinguishable from five pins to any check that looks at the file. What makes
two pins different is what they are *about*: the finished object, the detail of the fabric,
the work in progress, the thing in a room, the gift it makes, the scale against something
familiar, the yarn itself. Those are seven different reasons to save something, and a set
that uses one reason seven times is the spam the requirement names, whatever it looks like.

So a pin here is an *angle* plus a destination plus a date, and the distinctness rule is a
rule about angles. Nothing in this module produces an image: image generation is a capability
nobody has granted, and a pin plan that pretends otherwise would be a plan for assets that
cannot exist.

**The schedule is about the shopping window, not the occasion.** A pin published the week
before Christmas is a pin published after the decision. The calendar already holds the dated
commitments -- `listing_indexing_date` at ninety days and `promotional_ramp` at sixty, with
indexing taking weeks -- and this module reads them rather than choosing its own, because a
second set of seasonal dates is a second answer to when the work is late.

**A pin with no destination is a leaflet.** Every pin names where it lands, and nothing this
company has is landable yet: there is no shop, no site and no listing. The refusal says so
rather than letting a plan accumulate against a URL nobody has made.

**Amplifying a winner means another angle, not another copy.** The requirement asks for
winner pins to trigger more original variants, and the failure mode is producing the same
successful pin again with a different overlay -- which is the same spam arriving through the
door marked success.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..seasonal.calendar import MILESTONES

# Seven reasons somebody saves a pin. These are what makes two pins different; a crop is not.
ANGLES: dict[str, str] = {
    "finished_object": "the thing, made, photographed plainly",
    "fabric_detail": "what the stitch actually does up close, which is what a maker judges",
    "in_progress": "the work halfway, which is what somebody saves when they intend to try",
    "in_a_room": "the object where it would live, which is how a non-maker sees it",
    "gift_framing": "who it is for and why, which is a different buyer from the maker",
    "scale_reference": "how big it really is, against something familiar",
    "yarn_story": "the colours and the fibre, which is often the actual reason",
}

# What may not stand in for a different angle. Named because each of these is exactly what a
# pin factory produces when asked for five variants.
NOT_A_DIFFERENT_PIN: tuple[str, ...] = (
    "a different crop of the same photograph",
    "the same image with different text over it",
    "the same image with a different filter",
    "the same image at a different aspect ratio",
)

# How many distinct angles a product's pin set should carry before it is a set.
MIN_ANGLES = 3
# And the ceiling: past this the angles start repeating whatever they are called.
MAX_ANGLES = len(ANGLES)

# The calendar's own dated commitments, read rather than restated.
MILESTONE_DAYS: dict[str, int] = {name: days for name, days, _ in MILESTONES}
# Pins go up when the listing is indexed, not when the occasion arrives.
PUBLISH_AT_MILESTONE = "listing_indexing_date"
# Indexing takes weeks, which is why the ramp is later than the publication.
RAMP_AT_MILESTONE = "promotional_ramp"


class PinRefused(ValueError):
    """A set that is one pin repeated, a pin with nowhere to land, or a date after the buyer."""


@dataclass(frozen=True)
class Pin:
    """One pin: what it is about, where it lands, and the words it is filed under."""

    product_slug: str
    angle: str
    destination: str = ""
    keywords: tuple[str, ...] = ()
    board: str = ""

    def __post_init__(self) -> None:
        if self.angle not in ANGLES:
            raise PinRefused(
                f"{self.angle!r} is not an angle: {sorted(ANGLES)}. What makes two pins "
                f"different is what they are about; {NOT_A_DIFFERENT_PIN[0]} is not an "
                f"angle, and neither are the other three ways a pin factory makes five")


def check_set(pins: list[Pin]) -> dict:
    """Whether this is a set of pins or one pin posted several times."""
    reasons: list[str] = []
    angles = [p.angle for p in pins]
    distinct = set(angles)

    if len(distinct) < MIN_ANGLES:
        reasons.append(
            f"{len(distinct)} distinct angle(s) across {len(pins)} pin(s), below "
            f"{MIN_ANGLES}. Five pins that differ in crop, overlay and filter are one pin "
            f"posted five times, and they are indistinguishable from five pins to any check "
            f"that looks at the file")
    repeated = sorted({a for a in angles if angles.count(a) > 1})
    if repeated:
        reasons.append(f"{repeated} appear more than once. A second pin on the same angle is "
                       f"the same reason to save, offered twice")
    if len(pins) > MAX_ANGLES:
        reasons.append(f"{len(pins)} pins against {MAX_ANGLES} reasons anybody has to save "
                       f"one: past this the angles are repeating whatever they are called")

    without_destination = sorted({p.product_slug for p in pins if not p.destination.strip()})
    if without_destination:
        reasons.append(f"{without_destination} have no destination. A pin with nowhere to "
                       f"land is a leaflet")
    without_keywords = [p.angle for p in pins if not p.keywords]
    if without_keywords:
        reasons.append(f"{without_keywords} carry no keywords, so nothing files them and "
                       f"nobody searching finds them")

    return {
        "pins": len(pins), "angles": sorted(distinct), "ok": not reasons,
        "reasons": reasons,
        "unused_angles": sorted(set(ANGLES) - distinct),
        "note": ("a set: every pin is a different reason to save the same object"
                 if not reasons else f"{len(reasons)} reason(s) this is not a set of pins"),
    }


def schedule(*, event_date: date, today: date | None = None) -> dict:
    """When the pins go up, from the calendar's own dated commitments.

    Not the week before the occasion. A pin published then is published after the decision,
    and indexing takes weeks -- which is why the calendar puts listing and indexing ninety
    days out and the promotional ramp at sixty.
    """
    today = today or date.today()
    publish_on = event_date - timedelta(days=MILESTONE_DAYS[PUBLISH_AT_MILESTONE])
    ramp_on = event_date - timedelta(days=MILESTONE_DAYS[RAMP_AT_MILESTONE])
    days_away = (event_date - today).days

    late = today > publish_on
    return {
        "event_date": event_date.isoformat(),
        "days_away": days_away,
        "publish_on": publish_on.isoformat(),
        "ramp_on": ramp_on.isoformat(),
        "late": late,
        "from_calendar": [PUBLISH_AT_MILESTONE, RAMP_AT_MILESTONE],
        "why": (f"pins go up at {PUBLISH_AT_MILESTONE} and the push begins at "
                f"{RAMP_AT_MILESTONE}, because indexing takes weeks and a pin published the "
                f"week before the occasion is published after the decision"
                + (". This one is already late" if late else "")),
    }


def amplify(winner: Pin, existing: list[Pin]) -> dict:
    """What to make next after a pin works, which is never the same pin again.

    The requirement asks for winner pins to trigger more original variants, and the failure
    is producing the successful pin again with a different overlay -- the same spam arriving
    through the door marked success.
    """
    used = {p.angle for p in existing} | {winner.angle}
    remaining = sorted(set(ANGLES) - used)
    return {
        "winner": winner.angle,
        "next_angles": remaining,
        "refuses": list(NOT_A_DIFFERENT_PIN),
        "note": ("every angle is used, so the next thing is supporting content rather than "
                 "another pin: there are only so many reasons to save one object"
                 if not remaining else
                 f"{len(remaining)} reason(s) to save this object that nobody has offered "
                 f"yet. Another copy of the winner is the same spam arriving through the "
                 f"door marked success"),
    }


def state() -> dict:
    """What makes two pins different, and what cannot be done yet."""
    return {
        "angles": dict(ANGLES),
        "not_a_different_pin": list(NOT_A_DIFFERENT_PIN),
        "min_angles": MIN_ANGLES,
        "schedule_from": {"publish": PUBLISH_AT_MILESTONE, "ramp": RAMP_AT_MILESTONE,
                          "source": "seasonal.calendar.MILESTONES"},
        "cannot_do_yet": {
            "images": ("image generation is a capability nobody has granted, so a pin here "
                       "is an angle, a destination and a date rather than a file"),
            "destinations": ("there is no shop, no site and no listing, so nothing is "
                             "landable and every plan would accumulate against a URL nobody "
                             "has made"),
            "attribution": "a pin that nobody has seen has no clicks to attribute",
        },
        "note": ("Five pins that differ in crop, overlay and filter are one pin posted five "
                 "times. What makes two pins different is what they are about, and there are "
                 "seven reasons anybody saves one (#246)."),
    }
