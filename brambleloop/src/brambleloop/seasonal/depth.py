"""Turning an ecosystem gap into a brief somebody can actually start.

Requirement 288: do not reduce an event to one blanket. The coverage matrix already measures
depth against the departments an event spans rather than against a product count, because six
Christmas products say nothing about whether five of them are blankets. What it could not do
is say what to *do* about a gap, and a gap report that produces no work is a report.

The missing step is deterministic, which is why it is here rather than waiting on a model.
A department implies forms; a form implies a size and therefore a make lane; a lane is either
still launchable for this event or it is not; and a department whose forms are all past their
launch window is next season's work, not this season's. None of that is a creative judgement.
What a model adds is the idea -- and it adds it to a brief that already knows the shape, the
speed and the deadline, which is the difference between commissioning work and hoping.

The honest limit, stated rather than left implicit: a brief is not a product, and this module
never counts briefs as coverage. Coverage moves when something is built.
"""
from __future__ import annotations

from datetime import date

from ..creative.family import FORM_SIZE, LANE_ORDER, ROLES
from .calendar import EVENT_DEPARTMENTS, coverage_matrix, lane_feasibility

# Which concept forms serve each department. A department is a place in a buyer's life; a
# form is a thing that can be made. The map between them is the part a brief needs and the
# part a gap report leaves out.
DEPARTMENT_FORMS: dict[str, tuple[str, ...]] = {
    "garments": ("fitted_garment", "draped_garment"),
    "blankets": ("rectangle_throw",),
    "stockings": ("stocking",),
    "ornaments": ("ornament", "garland", "wreath"),
    "home_decor": ("pillow", "wall_hanging", "runner", "basket", "coaster"),
    "bags": ("bag", "pouch"),
    "hats": ("hat", "scarf"),
    "seasonal_gift": ("toy", "ornament", "pouch", "coaster", "sphere"),
}

# The lane a form implies before anything is engineered. Size is the honest proxy: a tiny
# object is a quick make and a large one is not, whatever the brief hopes.
SIZE_LANE: dict[str, str] = {"tiny": "QUICK", "small": "SHORT", "medium": "MEDIUM",
                             "large": "LONG"}


class DepthRefused(ValueError):
    """A brief for a department that is not a gap, or for an event that has none."""


def implied_lane(form: str) -> str:
    return SIZE_LANE[FORM_SIZE.get(form, "large")]


def _roles_for(form: str) -> list[str]:
    return [r.key for r in ROLES if form in r.forms]


def department_brief(*, event: str, department: str, days_away: int, samples: int = 0,
                     today: date | None = None) -> dict:
    """What to build for one uncovered department, and whether there is still time.

    Refuses a department the event does not span: a brief for stockings at Easter is work
    invented to fill a queue, which is how a never-idle loop stops meaning anything.
    """
    spans = EVENT_DEPARTMENTS.get(event)
    if spans is not None and department not in spans:
        raise DepthRefused(
            f"{event} does not span {department}; a brief for it would be work invented to "
            f"fill a queue rather than a gap anybody has")
    forms = DEPARTMENT_FORMS.get(department)
    if not forms:
        raise DepthRefused(f"no forms are mapped to {department!r}, so nothing can be briefed")

    verdicts = {row["lane"]: row for row in lane_feasibility(days_away, samples=samples,
                                                             today=today)}
    options, closed = [], []
    for form in forms:
        lane = implied_lane(form)
        row = verdicts[lane]
        entry = {"form": form, "implied_lane": lane, "verdict": row["verdict"],
                 "meaning": row["meaning"],
                 "latest_optimistic_launch": row["latest_optimistic_launch"],
                 "fills_family_roles": _roles_for(form)}
        (options if row["verdict"] in ("comfortable", "tight", "high_risk")
         else closed).append(entry)

    options.sort(key=lambda o: (("comfortable", "tight", "high_risk").index(o["verdict"]),
                                LANE_ORDER.index(o["implied_lane"])))
    startable = [o for o in options if o["verdict"] in ("comfortable", "tight")]

    return {
        "event": event,
        "department": department,
        "days_away": days_away,
        "startable_now": startable,
        "only_with_hurry": [o for o in options if o["verdict"] == "high_risk"],
        "past_the_window": closed,
        "recommended": startable[0] if startable else None,
        "calibrated": samples > 0,
        "note": (
            f"every form serving {department} is past its launch window for this {event}; "
            f"this is next season's gap, and treating it as this season's work would spend "
            f"the runway that is left on something nobody can buy in time"
            if not options else
            f"{len(startable)} form(s) can still be launched for this {event}"
            if startable else
            f"no form serving {department} is comfortable; what remains needs hurry rather "
            f"than a new plan"),
    }


def depth_plan(*, today: date | None = None,
               covered: dict[str, tuple[str, ...]] | None = None,
               samples: int = 0, limit: int = 12) -> dict:
    """Every ecosystem gap, thinnest event first, as briefs rather than as a count (#288).

    A brief is not a product. Nothing here moves coverage; coverage moves when something is
    built, and a queue that counted its own briefs would report depth it does not have.
    """
    matrix = coverage_matrix(today, covered=covered)

    briefs, next_season = [], []
    for row in matrix["rows"]:
        for department in row["gaps"]:
            if department not in DEPARTMENT_FORMS:
                continue
            brief = department_brief(event=row["event"], department=department,
                                     days_away=row["days_away"], samples=samples,
                                     today=today)
            (briefs if brief["startable_now"] or brief["only_with_hurry"]
             else next_season).append(brief)

    briefs.sort(key=lambda b: (0 if b["startable_now"] else 1, b["days_away"]))

    return {
        "today": matrix["today"],
        "ecosystem_depth": matrix["ecosystem_depth"],
        "thinnest_event": matrix["thinnest"],
        "briefs": briefs[:limit],
        "brief_count": len(briefs),
        "next_season": [{"event": b["event"], "department": b["department"],
                         "why": b["note"]} for b in next_season],
        "calibrated": samples > 0,
        "note": ("Gaps are departments an event spans and the catalogue does not answer. "
                 "These are briefs, not products: nothing here counts as coverage, and "
                 "depth moves when something is built (#288)."),
    }
