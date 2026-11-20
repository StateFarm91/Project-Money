"""What to do when something finally works, and why the answer is rarely one thing.

Requirement 22. When a SKU becomes a statistically credible winner, substantial research and
creative capacity moves temporarily to understanding *why*, across the dimensions the
requirement names -- theme, category, technique, low-sew or no-sew, aesthetic, season, price,
thumbnail, video, buyer intent and bundle opportunity -- and the follow-up is adjacent
controlled experiments rather than more of the same product.

Three things decide whether that produces knowledge or a legend.

**Rank is not credibility.** In a catalogue of eleven, one product is always the best seller,
and in a catalogue of three the best seller may have sold twice. A winner is a SKU with
enough orders over enough weeks to be distinguishable from the rest, and until then the
correct action is to keep selling it and say nothing about why.

**A winner usually differs from the field on every dimension at once, which is exactly why
the why is hard.** It is the only no-sew product, and the only one at CA$6, and the only one
with a photograph taken in daylight. Each of those is a complete explanation and at most one
of them is the reason. So this module ranks candidate explanations by how *distinguishable*
they are -- a dimension where the winner differs and most of the catalogue varies is
testable; a dimension where the winner is the only example of anything is a story. When
everything is confounded it says so and proposes the experiment that would separate them,
rather than naming the most appealing cause.

**Adjacent, not cloned.** The follow-up product must hold the candidate cause and change
something else; a second colourway of the winner tests nothing and sells to the people who
already bought it. A proposal that varies nothing but the palette is refused by name.

And the reallocation ends. "Temporarily" is doing real work in the requirement: capacity
moved to a winner with no end date is a permanent bet on one SKU made by nobody, and it is
how a company with one good product ends up with one product.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# The dimensions the requirement names. Closed, because "it is just better" is not a
# dimension and cannot be tested.
DIMENSIONS: tuple[str, ...] = (
    "theme", "category", "technique", "sewing", "aesthetic", "season", "price",
    "thumbnail", "video", "buyer_intent", "bundle")

# What makes a winner a winner rather than the top row of a short list.
MIN_ORDERS = 30
MIN_WEEKS = 4
# And how far clear of the rest of the catalogue it has to be. A product selling a fifth
# more than the median is a good week, not a finding.
LEAD_MULTIPLE = 2.0

# How much capacity the study may take, and for how long. Both bounded here rather than
# decided each time, because the decision each time is always "a bit more, for a bit longer".
MAX_CAPACITY_SHARE = 0.35
MAX_STUDY_DAYS = 45

# A dimension is only testable if the catalogue varies on it. Below this share of the field
# differing from the winner, the dimension explains everything and distinguishes nothing.
MIN_CONTRAST = 0.20


class ReplicationRefused(ValueError):
    """A winner that is only a rank, a cause that is only a story, or a clone."""


@dataclass(frozen=True)
class Sku:
    """One product, described on the dimensions a winner might differ from it on."""

    slug: str
    orders: int
    weeks_live: int
    traits: dict


def _trait_check(sku: Sku) -> None:
    unknown = sorted(set(sku.traits) - set(DIMENSIONS))
    if unknown:
        raise ReplicationRefused(
            f"{unknown} are not dimensions: {list(DIMENSIONS)}. 'It is just better' cannot "
            f"be tested, so it cannot be recorded as a reason")


def is_winner(sku: Sku, catalogue: list[Sku]) -> dict:
    """Whether this is a credible winner, or merely the top row of a short list."""
    others = sorted((s.orders for s in catalogue if s.slug != sku.slug))
    reasons: list[str] = []

    if sku.orders < MIN_ORDERS:
        reasons.append(
            f"{sku.orders} orders against a floor of {MIN_ORDERS}. In a catalogue of eleven "
            f"one product is always the best seller, and in a catalogue of three the best "
            f"seller may have sold twice")
    if sku.weeks_live < MIN_WEEKS:
        reasons.append(f"{sku.weeks_live} week(s) live against a floor of {MIN_WEEKS}: a "
                       f"launch is not a trend")
    if not others:
        reasons.append("nothing to be clear of: a catalogue of one has no best seller, it "
                       "has a product")
    else:
        middle = others[len(others) // 2]
        if middle == 0:
            reasons.append(
                "the rest of the catalogue has sold nothing, so there is no field to stand "
                "out from. This is a shop with one product that sells, which is a different "
                "finding and a more urgent one")
        elif sku.orders < middle * LEAD_MULTIPLE:
            reasons.append(
                f"{sku.orders} orders against a catalogue median of {middle}: below "
                f"{LEAD_MULTIPLE}x this is a good week rather than a winner")

    return {
        "slug": sku.slug, "credible": not reasons, "reasons": reasons,
        "orders": sku.orders, "weeks": sku.weeks_live,
        "floors": {"orders": MIN_ORDERS, "weeks": MIN_WEEKS, "lead_multiple": LEAD_MULTIPLE},
        "note": ("keep selling it and say nothing about why yet" if reasons else
                 "credible enough to be worth understanding"),
    }


def candidates(winner: Sku, catalogue: list[Sku]) -> dict:
    """Candidate explanations, ranked by how distinguishable each one is.

    The winner usually differs from the field on every dimension at once, and each
    difference is a complete explanation of which at most one is true. So the ranking is by
    contrast -- a dimension where the winner differs and the catalogue genuinely varies can
    be tested; a dimension where the winner is the only example of anything cannot.
    """
    _trait_check(winner)
    field = [s for s in catalogue if s.slug != winner.slug]
    for s in field:
        _trait_check(s)

    rows = []
    for dimension in DIMENSIONS:
        mine = winner.traits.get(dimension)
        if mine is None:
            rows.append({"dimension": dimension, "testable": False, "contrast": None,
                         "why": "not recorded for the winner, so nothing can be said"})
            continue
        known = [s for s in field if dimension in s.traits]
        if not known:
            rows.append({"dimension": dimension, "testable": False, "contrast": None,
                         "why": "not recorded for anything else, so there is no field"})
            continue
        differing = [s for s in known if s.traits[dimension] != mine]
        contrast = len(differing) / len(known)
        testable = contrast >= MIN_CONTRAST and contrast < 1.0
        rows.append({
            "dimension": dimension, "value": mine, "contrast": round(contrast, 3),
            "testable": testable,
            "why": ("" if testable else
                    (f"every other product differs on this, so it explains the winner and "
                     f"everything else equally. The only example of anything is a story"
                     if contrast == 1.0 else
                     f"only {contrast:.0%} of the catalogue differs, below {MIN_CONTRAST:.0%}"
                     f": there is not enough variation here to separate anything")),
        })

    testable = [r for r in rows if r["testable"]]
    testable.sort(key=lambda r: -r["contrast"])
    confounded = [r["dimension"] for r in rows if r.get("contrast") == 1.0]
    return {
        "winner": winner.slug,
        "ranked": testable,
        "all": rows,
        "confounded": confounded,
        "attributable": bool(testable),
        "note": ("nothing here separates: the winner is the only example of everything it "
                 "is, and every dimension explains it completely. The next product is the "
                 "experiment, and it should hold one of these and change the rest"
                 if not testable else
                 f"{len(testable)} dimension(s) the catalogue varies enough to test"),
    }


@dataclass(frozen=True)
class Proposal:
    """A follow-up product: what it keeps from the winner, and what it changes."""

    slug: str
    holds: tuple[str, ...]
    changes: tuple[str, ...]


def check_proposal(proposal: Proposal, winner: Sku) -> dict:
    """Whether this is an adjacent experiment or a clone with a new palette."""
    reasons: list[str] = []
    unknown = sorted((set(proposal.holds) | set(proposal.changes)) - set(DIMENSIONS))
    if unknown:
        raise ReplicationRefused(f"{unknown} are not dimensions: {list(DIMENSIONS)}")

    overlap = sorted(set(proposal.holds) & set(proposal.changes))
    if overlap:
        reasons.append(f"{overlap} are listed as both held and changed, which is not a "
                       f"design, it is two plans")
    if not proposal.holds:
        reasons.append("holds nothing from the winner, so whatever it learns is about a "
                       "different product")
    if not proposal.changes:
        reasons.append(
            "changes nothing. A second colourway of the winner tests nothing and sells to "
            "the people who already bought it")
    elif set(proposal.changes) <= {"aesthetic"}:
        reasons.append(
            "varies only the palette, which is the clone this requirement names. It will "
            "sell a little, to the same people, and answer nothing")

    return {
        "slug": proposal.slug, "adjacent": not reasons, "reasons": reasons,
        "holds": list(proposal.holds), "changes": list(proposal.changes),
        "tests": (f"whether {sorted(proposal.holds)} is what {winner.slug} was about"
                  if not reasons else ""),
    }


def study(winner: Sku, catalogue: list[Sku], *, capacity_share: float,
          starts: date, days: int = MAX_STUDY_DAYS) -> dict:
    """The reallocation itself: how much, for how long, and when it ends.

    "Temporarily" is doing real work in the requirement. Capacity moved to a winner with no
    end date is a permanent bet on one SKU made by nobody, and it is how a company with one
    good product ends up with one product.
    """
    verdict = is_winner(winner, catalogue)
    if not verdict["credible"]:
        raise ReplicationRefused(
            f"{winner.slug} is not a credible winner: {verdict['reasons']}. Moving capacity "
            f"to a rank is how a catalogue is rebuilt around a good week")
    if not 0 < capacity_share <= MAX_CAPACITY_SHARE:
        raise ReplicationRefused(
            f"{capacity_share:.0%} of capacity against a ceiling of "
            f"{MAX_CAPACITY_SHARE:.0%}. Substantial is not most: the rest of the catalogue "
            f"is what the winner will be compared against")
    if not 0 < days <= MAX_STUDY_DAYS:
        raise ReplicationRefused(
            f"{days} days against a ceiling of {MAX_STUDY_DAYS}. A study with no end is a "
            f"permanent reallocation nobody decided to make")

    why = candidates(winner, catalogue)
    return {
        "winner": winner.slug,
        "capacity_share": capacity_share,
        "starts": starts.isoformat(),
        "ends": (starts + timedelta(days=days)).isoformat(),
        "days": days,
        "explanations": why["ranked"],
        "confounded": why["confounded"],
        "attributable": why["attributable"],
        "note": ("capacity returns to the ordinary queue on the end date whether or not the "
                 "question was answered. An unanswered question is a reason to design a "
                 "better experiment, not a reason to keep the capacity"),
    }


def state() -> dict:
    """What counts as a winner here, and what the study is allowed to cost."""
    return {
        "dimensions": list(DIMENSIONS),
        "winner_floors": {"orders": MIN_ORDERS, "weeks": MIN_WEEKS,
                          "lead_multiple": LEAD_MULTIPLE},
        "study_ceilings": {"capacity_share": MAX_CAPACITY_SHARE, "days": MAX_STUDY_DAYS},
        "min_contrast": MIN_CONTRAST,
        "note": ("Rank is not credibility: in a catalogue of three the best seller may have "
                 "sold twice. A winner usually differs from the field on every dimension at "
                 "once, each a complete explanation of which at most one is true, so "
                 "candidate causes are ranked by how distinguishable they are and a "
                 "confounded winner is said to be confounded (#22)."),
    }
