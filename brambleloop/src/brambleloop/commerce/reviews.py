"""Reading our own reviews, on a base too small to read.

Requirement 257. Analyse legitimate review themes and the star distribution against listing
conversion and repeat behaviour; find what buyers praise, misunderstand or wish existed; feed
it into design, PDFs, listing claims and support. And, stated outright: never fabricate,
purchase or gate reviews.

The prohibition is the easy half to honour and the easy half to honour badly. Nothing here
writes a review, and the third verb is the one worth being precise about: *gating* is not
buying. It is withholding something the buyer already paid for -- the file, the answer to
their question, the fix for the defect -- until they leave a rating. It does not feel like
buying a review because no money moves, and it is the version a small shop actually commits,
usually by accident, in a support template that says "if this helped, a review would mean a
lot" attached to the thing they were owed anyway.

The analytical half has a harder problem than the rule does, and it is arithmetic. A shop
with three reviews has a rating one bad day away from 3.7, and the first handful dominate the
average for a year. Reporting a star distribution over a base that small is not a light
version of the analysis; it is a number people will act on, and it will move them to redesign
a product over one person's experience. So the distribution is refused below a floor and the
themes are counted separately, because a theme recurring three times is a finding about the
product even when the average is meaningless.

The most useful output is the mapping, not the counting. A theme in the *misunderstood*
category is usually not a product defect at all: it is a disclosure that was missing from the
listing, and `commerce.buyer_trust` already holds the list of disclosures a purchase needs.
Routing a misunderstanding to the design queue rewrites a pattern that was correct; routing it
to the listing fixes the thing that actually happened.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..intel.observe import RECURRING_AT
from .buyer_trust import REQUIRED_DISCLOSURES

# What a review can tell this company, in the requirement's own three categories.
CATEGORIES: dict[str, str] = {
    "praised": "what to keep, and what the listing should say out loud",
    "misunderstood": "what the buyer expected and did not get, which is usually a disclosure",
    "wished_for": "what did not exist, which is a product question rather than a fix",
}

# Which missing disclosure each common misunderstanding points at. A misunderstanding routed
# to the design queue rewrites a pattern that was correct.
MISUNDERSTANDING_TO_DISCLOSURE: dict[str, str] = {
    "expected_a_finished_item": "digital_not_finished",
    "wrong_terminology": "terminology",
    "harder_than_expected": "skill_level",
    "materials_not_owned": "required_materials",
    "did_not_find_the_file": "delivery",
    "did_not_know_how_to_ask": "support",
}

# Below this many reviews a star distribution is one person's bad day with decimal places.
MIN_REVIEWS_FOR_A_DISTRIBUTION = 20

# What may never happen to a review. Structural: nothing in this module writes one, and the
# gating rule is checked against support copy.
NEVER: tuple[str, ...] = (
    "fabricate a review", "purchase a review", "gate a review",
    "condition support on a review", "condition a discount on a review",
    "condition a fix on a review")

# Phrases that turn a support reply into a request for a rating attached to something the
# buyer was already owed.
GATING_PHRASES: tuple[str, ...] = (
    "a review would mean", "leave a review", "if this helped", "five star",
    "5 star", "rate us", "positive review", "update your review")


class ReviewRefused(ValueError):
    """A distribution over too small a base, or a support reply that asks for a rating."""


@dataclass(frozen=True)
class Theme:
    """One recurring thing buyers said, counted rather than quoted."""

    key: str
    category: str
    count: int

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ReviewRefused(f"{self.category!r} is not a category: {sorted(CATEGORIES)}")


def distribution(stars: list[int]) -> dict:
    """The star distribution, or why it may not be read yet.

    Refused below the floor rather than reported with a caveat. A caveat is read once and an
    average is read every week, and the number would move somebody to redesign a product
    over one person's experience.
    """
    bad = [s for s in stars if s not in (1, 2, 3, 4, 5)]
    if bad:
        raise ReviewRefused(f"{bad} are not star ratings")

    if len(stars) < MIN_REVIEWS_FOR_A_DISTRIBUTION:
        return {
            "readable": False, "reviews": len(stars),
            "floor": MIN_REVIEWS_FOR_A_DISTRIBUTION,
            "why": (f"{len(stars)} review(s), below {MIN_REVIEWS_FOR_A_DISTRIBUTION}. A shop "
                    f"with three reviews has a rating one bad day away from 3.7, and the "
                    f"first handful dominate the average for a year. This is not a light "
                    f"version of the analysis -- it is a number people act on"),
            "themes_are_still_readable": (f"a theme recurring {RECURRING_AT} times is a "
                                          f"finding about the product even when the average "
                                          f"is meaningless"),
        }
    counts = {star: stars.count(star) for star in (1, 2, 3, 4, 5)}
    return {
        "readable": True, "reviews": len(stars),
        "counts": counts,
        "mean": round(sum(stars) / len(stars), 2),
        "share_below_four": round(sum(counts[s] for s in (1, 2, 3)) / len(stars), 3),
    }


def route(themes: list[Theme]) -> dict:
    """Where each recurring theme should go, which is usually not the design queue."""
    findings, thin = [], []
    for theme in themes:
        if theme.count < RECURRING_AT:
            thin.append({"theme": theme.key, "count": theme.count,
                         "why": f"below {RECURRING_AT}: one buyer's experience"})
            continue
        if theme.category == "misunderstood":
            disclosure = MISUNDERSTANDING_TO_DISCLOSURE.get(theme.key)
            findings.append({
                "theme": theme.key, "category": theme.category, "count": theme.count,
                "route_to": "listing" if disclosure else "support",
                "disclosure": disclosure,
                "why": ((f"the listing is missing {disclosure!r}: "
                         f"{REQUIRED_DISCLOSURES[disclosure]}. Routing this to the design "
                         f"queue rewrites a pattern that was correct")
                        if disclosure else
                        "a misunderstanding with no disclosure behind it is a support "
                        "question first"),
            })
        elif theme.category == "wished_for":
            findings.append({"theme": theme.key, "category": theme.category,
                             "count": theme.count, "route_to": "product_selection",
                             "why": "what did not exist is a question about what to make next"})
        else:
            findings.append({"theme": theme.key, "category": theme.category,
                             "count": theme.count, "route_to": "listing_claims",
                             "why": "what buyers praise is what the listing should say out "
                                    "loud, and it may say it because they said it first"})
    return {
        "findings": findings, "below_the_floor": thin,
        "note": ("nothing recurs often enough to be a finding yet" if not findings else ""),
    }


def check_support_copy(text: str) -> dict:
    """Whether a support reply asks for a rating attached to something already owed.

    This is the version of the prohibition a small shop actually commits, and it does not
    feel like buying a review because no money moves.
    """
    lowered = text.lower()
    found = sorted({phrase for phrase in GATING_PHRASES if phrase in lowered})
    return {
        "ok": not found,
        "found": found,
        "why": (f"{found} attaches a request for a rating to support the buyer was owed. "
                f"Gating is not buying -- no money moves -- which is exactly why it gets "
                f"written into a template" if found else
                "nothing in this reply asks for a rating"),
        "never": list(NEVER),
    }


def state() -> dict:
    """What reviews may be read for, and what may never be done to them."""
    return {
        "categories": dict(CATEGORIES),
        "misunderstanding_to_disclosure": dict(MISUNDERSTANDING_TO_DISCLOSURE),
        "min_reviews_for_a_distribution": MIN_REVIEWS_FOR_A_DISTRIBUTION,
        "recurring_at": RECURRING_AT,
        "never": list(NEVER),
        "gating_phrases_refused": list(GATING_PHRASES),
        "note": ("Gating is not buying: it is withholding something the buyer already paid "
                 "for until they leave a rating, and it does not feel like buying a review "
                 "because no money moves. A misunderstanding is usually a missing disclosure "
                 "rather than a product defect, and routing it to the design queue rewrites "
                 "a pattern that was correct (#257)."),
    }
