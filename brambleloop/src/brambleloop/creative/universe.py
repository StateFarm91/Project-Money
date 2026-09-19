"""The seasonal creative universe: cells to generate against, and coverage of them.

Requirements 105, 113, 114, 119, 121, 122. One idea runs through all six: *generate against
explicit cells and measure the cells*, because the alternative is generating against a keyword
and measuring a count.

"Christmas crochet patterns" as a brief produces what the phrase suggests, which is the
commodity. The same December contains a stocking for a mantel, a tree skirt, a teacher gift
that must cost under fifteen dollars, a nursery keepsake somebody keeps for thirty years, a
table setting, a pet's first Christmas and a front door. Those are different products for
different people, and the only reason a catalogue ends up with six variations on a blanket is
that nothing ever asked which cell each one was for.

So four grids, and a rule about each.

**The universe is a taxonomy per occasion (#105), not a keyword.** Forms, motifs, emotions,
recipients, rooms, skill levels, make times, price bands and gifting narratives — and
Christmas alone has to span all of them rather than four of them well.

**The recipient × context matrix is where demand discovery actually happens (#113).** A cell
nobody has a product for is a question, and it is a better question than any keyword tool
produces because it is phrased as a person in a room.

**The skill portfolio is segmentation, not difficulty (#114).** A wave that is entirely
flagship work has no beginner entry and no impulse purchase; one that is entirely quick makes
has nothing anybody keeps. Both are portfolios that look busy.

**Diversity is measured before exploitation (#119).** A tournament dominated by one
construction has explored one construction, however many concepts it contained — and the
count is the number that makes it look like exploration.

Revenue between holidays is the same problem seen along the calendar: the four-season programs
(#121) and the non-holiday occasions (#122) exist because a shop that only sells in December
is closed for eleven months and calls it seasonality.
"""
from __future__ import annotations

from dataclasses import dataclass

# #113's own list, and it is deliberately a mix of people and places: "a teacher" and "the
# front door" are both cells somebody shops for, and neither is reachable from a keyword.
CONTEXTS: dict[str, str] = {
    "adult_self_use": "bought for oneself, which is most of what sells and least of what is designed",
    "host_gift": "taken to somebody's house, so it must survive being judged on arrival",
    "child": "for a child to own and use",
    "baby_nursery": "for a very small person, and for the adult photographing the room",
    "teacher": "a small, sincere, inexpensive gift given in public",
    "coworker": "affectionate and not too personal",
    "pet_owner": "for the animal, bought by the person",
    "family_tradition": "brought out every year, so it must age well",
    "stocking_stuffer": "small, cheap, and chosen last",
    "table_setting": "seen by everybody at once, for three hours",
    "fireplace": "the mantel, which is the most photographed shelf in the house",
    "tree": "hung, seen from every angle, stored eleven months",
    "front_door": "the only thing the neighbours see",
    "kitchen": "used, washed, and worn out on purpose",
    "bedroom": "quiet, personal, rarely photographed",
    "office": "on a desk somebody else can see",
    "cottage": "a second home, styled more than lived in",
    "party": "used once, loudly",
}

# #114. Three, because two is a binary and four is a gradient nobody can tell apart.
SKILL_LEVELS: dict[str, str] = {
    "beginner_quick_win": "finishable in an evening by somebody who has made two things",
    "intermediate": "the middle of the market, and where most of the money is",
    "advanced_heirloom": "worth the year it takes, and the reason somebody follows a designer",
}

# A wave outside these shares is a portfolio that looks busy. Ranges rather than targets: the
# useful signal is "there is no beginner product at all", not "beginners are 22%".
HEALTHY_SKILL_SHARE: dict[str, tuple[float, float]] = {
    "beginner_quick_win": (0.20, 0.45),
    "intermediate": (0.35, 0.60),
    "advanced_heirloom": (0.10, 0.30),
}

# #121: seasons as programs independent of any named holiday, because a shop that only sells
# in December is closed for eleven months and calls it seasonality.
FOUR_SEASON_PROGRAMS: dict[str, tuple[str, ...]] = {
    "spring": ("garden_floral", "home_refresh", "seasonal_wardrobe"),
    "summer": ("cottage_beach", "outdoor_entertaining", "seasonal_wardrobe"),
    "fall": ("harvest_woodland", "home_refresh", "seasonal_wardrobe"),
    "winter": ("cozy_winter_neutral", "home_refresh", "seasonal_wardrobe"),
}

PROGRAM_MEANING: dict[str, str] = {
    "garden_floral": "growing things, before anything has actually grown",
    "cottage_beach": "the holiday somebody is about to take or remembering",
    "harvest_woodland": "abundance and woodland, without a single pumpkin being required",
    "cozy_winter_neutral": "winter with no holiday attached, which is most of winter",
    "home_refresh": "the urge to change a room, which arrives four times a year",
    "outdoor_entertaining": "eating outside, and everything that needs",
    "seasonal_wardrobe": "what somebody wears when the weather turns",
}

# #122: evergreen and event demand that does not wait for a holiday.
NON_HOLIDAY_OCCASIONS: dict[str, str] = {
    "birthday": "the only occasion every customer has every year",
    "baby_shower": "bought by somebody who is not the parent, to be admired publicly",
    "nursery": "a room decorated once, thoroughly, by somebody with strong opinions",
    "wedding": "high budget, long lead time, enormous emotional weight",
    "housewarming": "a gift for a room the giver has not seen",
    "teacher_gift": "small, sincere, given in public, twice a year",
    "graduation": "a keepsake bought at a moment nobody repeats",
    "pet_gift": "affection for an animal, expressed by purchase",
    "hostess_gift": "the thing you bring, chosen in a hurry, judged on arrival",
    "family_keepsake": "made to be inherited, which changes every material decision",
}

# #105: the departments an occasion's universe must span. Christmas is listed long on purpose
# -- the requirement singles it out, and a Christmas represented by four departments is a
# Christmas with four chances.
UNIVERSE: dict[str, tuple[str, ...]] = {
    "christmas": ("stocking", "ornament", "tree_skirt", "advent", "garland", "wreath",
                  "table_setting", "pillow", "blanket", "amigurumi", "wearable",
                  "gift_wrap", "pet", "door", "kitchen", "keepsake"),
    "halloween": ("ornament", "garland", "door", "table_setting", "amigurumi", "pillow",
                  "wearable", "pet", "party", "keepsake"),
    "easter": ("ornament", "basket", "amigurumi", "table_setting", "garland", "wearable",
               "keepsake", "kitchen"),
    "valentines": ("ornament", "amigurumi", "pillow", "table_setting", "keepsake",
                   "wearable"),
    "thanksgiving": ("table_setting", "garland", "pillow", "blanket", "door", "kitchen"),
    "mothers_day": ("wearable", "bag", "keepsake", "kitchen", "pillow", "table_setting"),
}

# #119: the axes a tournament must vary along. Breadth in one axis is not breadth.
DIVERSITY_AXES: tuple[str, ...] = (
    "form", "function", "emotional_tone", "construction", "motif_family", "recipient",
    "make_time")

# Above this share of a tournament on one value of one axis, the tournament explored that
# value rather than the axis.
DOMINANCE_ALARM = 0.40


class UniverseRefused(ValueError):
    """A cell that does not exist, or a wave measured by count."""


def cells(occasion: str) -> list[dict]:
    """Every department × context cell for one occasion (#105, #113).

    A queue rather than a description. A cell with no product is a question phrased as a
    person in a room, which is a better question than any keyword tool produces.
    """
    if occasion not in UNIVERSE:
        raise UniverseRefused(
            f"{occasion!r} has no universe: {sorted(UNIVERSE)}. An occasion generated from a "
            f"keyword produces what the keyword suggests, which is the commodity (#105)")
    return [{"occasion": occasion, "department": department, "context": context,
             "context_meaning": CONTEXTS[context]}
            for department in UNIVERSE[occasion]
            for context in CONTEXTS]


def coverage(occasion: str, have: list[tuple[str, str]]) -> dict:
    """Which cells this company has an answer for, and which are still questions."""
    all_cells = {(c["department"], c["context"]) for c in cells(occasion)}
    owned = {(d, c) for d, c in have if (d, c) in all_cells}
    invalid = [(d, c) for d, c in have if (d, c) not in all_cells]
    if invalid:
        raise UniverseRefused(
            f"{invalid[:3]} are not cells of the {occasion} universe")

    by_department: dict[str, int] = {}
    for department, _ in owned:
        by_department[department] = by_department.get(department, 0) + 1
    empty_departments = [d for d in UNIVERSE[occasion] if d not in by_department]

    return {
        "occasion": occasion,
        "cells": len(all_cells),
        "covered": len(owned),
        "depth": round(len(owned) / len(all_cells), 4) if all_cells else 0.0,
        "departments_with_nothing": empty_departments,
        "by_department": dict(sorted(by_department.items(), key=lambda kv: -kv[1])),
        "note": ("Depth is coverage of cells, not a product count. Six Christmas products "
                 "say nothing about whether five of them are blankets, and the department "
                 "with nothing in it is where the next question is (#105, #113)."),
    }


def skill_portfolio(levels: list[str]) -> dict:
    """Is this wave segmented, or is it all one kind of work? (#114)

    Skill level is market segmentation rather than difficulty. A wave of only flagships has
    no impulse purchase and no beginner entry; a wave of only quick makes has nothing anybody
    keeps. Both look busy.
    """
    unknown = [l for l in levels if l not in SKILL_LEVELS]
    if unknown:
        raise UniverseRefused(f"{sorted(set(unknown))} are not skill levels: "
                              f"{sorted(SKILL_LEVELS)}")
    total = len(levels)
    counts = {level: levels.count(level) for level in SKILL_LEVELS}
    shares = {level: (counts[level] / total if total else 0.0) for level in SKILL_LEVELS}

    gaps = []
    for level, (low, high) in HEALTHY_SKILL_SHARE.items():
        share = shares[level]
        if share < low:
            gaps.append({"level": level, "share": round(share, 3), "want_at_least": low,
                         "absent": counts[level] == 0,
                         "meaning": SKILL_LEVELS[level]})
        elif share > high:
            gaps.append({"level": level, "share": round(share, 3), "want_at_most": high,
                         "absent": False, "meaning": SKILL_LEVELS[level]})
    return {
        "products": total,
        "counts": counts,
        "shares": {k: round(v, 3) for k, v in shares.items()},
        "gaps": gaps,
        "segmented": not gaps,
        "note": ("A wave of only flagship work has no beginner entry and no impulse "
                 "purchase; one of only quick makes has nothing anybody keeps. Both look "
                 "busy (#114)."),
    }


@dataclass(frozen=True)
class Entrant:
    """One concept in a tournament, along the axes diversity is measured on."""

    key: str
    form: str
    function: str
    emotional_tone: str
    construction: str
    motif_family: str
    recipient: str
    make_time: str

    def axis(self, name: str) -> str:
        return getattr(self, name)


def diversity(entrants: list[Entrant]) -> dict:
    """Did this tournament explore, or produce many versions of one thing? (#119)

    Measured per axis, because breadth in one axis is not breadth — and the concept count is
    exactly the number that makes a narrow tournament look wide.
    """
    if not entrants:
        return {"measurable": False,
                "reason": "an empty tournament has explored nothing, which is not diversity"}

    axes = {}
    dominated = []
    for axis in DIVERSITY_AXES:
        values: dict[str, int] = {}
        for e in entrants:
            value = e.axis(axis)
            values[value] = values.get(value, 0) + 1
        top_value = max(values, key=values.get)
        share = values[top_value] / len(entrants)
        axes[axis] = {"distinct": len(values), "top_value": top_value,
                      "top_share": round(share, 3),
                      "dominated": share > DOMINANCE_ALARM}
        if share > DOMINANCE_ALARM:
            dominated.append(axis)

    return {
        "measurable": True,
        "entrants": len(entrants),
        "axes": axes,
        "dominated_axes": dominated,
        "explored": not dominated,
        "note": (f"{dominated} are dominated by one value: this tournament explored those "
                 f"values rather than those axes, and the entrant count is the number that "
                 f"makes it look otherwise (#119)"
                 if dominated else
                 "no axis is dominated by a single value"),
    }


def between_holidays(season: str) -> dict:
    """What the company should be selling when no holiday is close (#121, #122)."""
    if season not in FOUR_SEASON_PROGRAMS:
        raise UniverseRefused(f"{season!r} is not a season: {sorted(FOUR_SEASON_PROGRAMS)}")
    return {
        "season": season,
        "programs": [{"key": p, "meaning": PROGRAM_MEANING[p]}
                     for p in FOUR_SEASON_PROGRAMS[season]],
        "occasions": [{"key": k, "meaning": v} for k, v in NON_HOLIDAY_OCCASIONS.items()],
        "note": ("Independent of any named holiday. A shop that only sells in December is "
                 "closed for eleven months and calls it seasonality (#121, #122)."),
    }
