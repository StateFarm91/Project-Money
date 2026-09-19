"""What the competitor has not made, and the difference between that and what we have not.

Requirement 216. Alongside the same-arena response lane -- enter the proven market, preserve
the generic characteristics, differentiate honestly -- a benchmark release should also trigger
a *divergent* tournament: adjacent functions, new recipients, transformations, silhouettes,
construction systems, bundles, seasonal stories, collection families. Both lanes run. A shop
with only the incremental lane is a commodity; a shop with only the breakthrough lane has a
studio and no revenue.

The interesting part is a sentence the requirement takes for granted. "What the competitor has
NOT made" is a claim about their catalogue, and making it requires having looked at their
catalogue. With no observed listings, the honest divergence is against *our own* catalogue --
which is a different and much weaker statement, because the thing nobody in the market has
made and the thing we happen not to have made are not the same discovery, and only one of
them is an opportunity.

So every brief this module produces is labelled with what it was diverged from, and the label
is not cosmetic: a brief that says "unserved by the market" when the market was never observed
is the sentence that turns an assumption into a plan.
"""
from __future__ import annotations

from dataclasses import dataclass

from .concept import FORMS, OCCASIONS, RECIPIENTS
from .invention import TRANSFORMATIONS

AGAINST_MARKET, AGAINST_OURSELVES = "observed_market", "our_catalogue_only"

# The axes the requirement names. Each is a way a product can differ that is not "nicer".
AXES: dict[str, str] = {
    "adjacent_function": "the same making, doing a different job",
    "new_recipient": "the same object, for somebody the category ignores",
    "transformation": "the object becomes or contains something else",
    "silhouette": "an outline the grid does not already have",
    "construction_system": "a different way of building it, not a different decoration",
    "bundle": "two objects that are better bought together than apart",
    "seasonal_story": "the same idea carried by an occasion nobody works",
    "collection_family": "a system of objects rather than one object",
}

# Both lanes run, and neither may take the whole company. All-incremental is a commodity shop
# with good margins until somebody else arrives; all-breakthrough is a studio.
MIN_LANE_SHARE = 0.20


class BreakthroughRefused(ValueError):
    """A divergence claimed against a market nobody observed, or a single-lane portfolio."""


@dataclass(frozen=True)
class Brief:
    axis: str
    question: str
    vocabulary: tuple[str, ...]
    diverged_from: str

    @property
    def claims_market_gap(self) -> bool:
        return self.diverged_from == AGAINST_MARKET

    def to_dict(self) -> dict:
        return {"axis": self.axis, "what": AXES[self.axis], "question": self.question,
                "vocabulary": list(self.vocabulary),
                "diverged_from": self.diverged_from,
                "claims_market_gap": self.claims_market_gap}


def observed_market(db) -> dict:
    """What this company has actually seen of anybody else's catalogue. Rows, not belief."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        rows = [{"pod": r.pod, "product_type": r.product_type, "title": r.title}
                for r in s.scalars(select(BenchmarkListing))]
    return {"listings": len(rows),
            "product_types": sorted({r["product_type"] for r in rows if r["product_type"]}),
            "pods": sorted({r["pod"] for r in rows if r["pod"]})}


def _vocabulary(axis: str, seen: set[str]) -> tuple[str, ...]:
    """The unused options along one axis, drawn from the closed vocabularies."""
    if axis == "adjacent_function":
        return tuple(f for f in FORMS if f not in seen)
    if axis == "new_recipient":
        return tuple(r for r in RECIPIENTS if r not in seen)
    if axis == "transformation":
        return tuple(TRANSFORMATIONS)
    if axis == "seasonal_story":
        return tuple(o for o in OCCASIONS if o not in seen)
    if axis == "silhouette":
        return tuple(f for f in FORMS if f not in seen)
    return ()


def diverge(db, *, arena: str, ours: tuple[str, ...] = (),
            their_forms: tuple[str, ...] = ()) -> dict:
    """Briefs for what is not being made in this arena, labelled by what that claim rests on.

    `ours` is what this catalogue already covers; `their_forms` what an observation actually
    recorded. When nothing has been observed, the divergence still runs -- there is useful
    work in knowing what we have not made -- and every brief says so rather than borrowing
    the authority of a market scan that never happened.
    """
    market = observed_market(db)
    against = AGAINST_MARKET if market["listings"] else AGAINST_OURSELVES
    seen = set(ours) | set(their_forms)

    briefs = [
        Brief(axis=axis,
              question=(f"in {arena}: what {question}?"),
              vocabulary=_vocabulary(axis, seen),
              diverged_from=against)
        for axis, question in (
            ("adjacent_function", "job could this making do that this arena does not"),
            ("new_recipient", "buyer does this arena ignore"),
            ("transformation", "could this object become or contain"),
            ("silhouette", "outline is missing from the grid"),
            ("construction_system", "different way of building this exists"),
            ("bundle", "second object is better bought with it than without"),
            ("seasonal_story", "occasion does nobody work here"),
            ("collection_family", "system of objects would this one belong to"),
        )
    ]
    return {
        "arena": arena,
        "diverged_from": against,
        "observed_listings": market["listings"],
        "briefs": [b.to_dict() for b in briefs],
        "note": (
            f"nothing has been observed of anybody else's catalogue, so these are the things "
            f"*we* have not made, not the things the market has not. That is a weaker and "
            f"still useful statement, and calling it a market gap would turn an assumption "
            f"into a plan" if against == AGAINST_OURSELVES else
            f"diverged against {market['listings']} observed listing(s): these are gaps in "
            f"what has actually been seen"),
    }


def check_claim(brief: dict, *, claim: str) -> None:
    """Refuse a brief that describes itself as a market gap without an observed market."""
    unserved = any(word in claim.lower()
                   for word in ("nobody makes", "unserved", "market gap", "no one sells",
                                "nobody sells", "gap in the market"))
    if unserved and brief.get("diverged_from") != AGAINST_MARKET:
        raise BreakthroughRefused(
            f"this brief claims {claim!r} and was diverged against our own catalogue, not an "
            f"observed market. The thing nobody has made and the thing we happen not to have "
            f"made are different discoveries, and only one of them is an opportunity")


def allocate(*, incremental: float, breakthrough: float) -> dict:
    """Both lanes run. Refuse a portfolio that is secretly one lane.

    The drift is always the same direction: incremental work has a visible customer and
    breakthrough work has an argument, so the argument loses every planning round until the
    catalogue is a commodity. A floor is the only version of "maintain both" that survives a
    quarter.
    """
    total = round(incremental + breakthrough, 6)
    if abs(total - 1.0) > 1e-6:
        raise BreakthroughRefused(
            f"the two lanes are {total} of the portfolio; they are the portfolio and must "
            f"sum to one")
    for name, share in (("incremental", incremental), ("breakthrough", breakthrough)):
        if share < MIN_LANE_SHARE:
            raise BreakthroughRefused(
                f"{name} holds {share:.0%} against a floor of {MIN_LANE_SHARE:.0%}. A shop "
                f"with only the incremental lane is a commodity the moment somebody else "
                f"arrives; a shop with only the breakthrough lane is a studio with no "
                f"revenue. #216 asks for both, and a floor is the only version of that which "
                f"survives a quarter")
    return {"incremental": incremental, "breakthrough": breakthrough,
            "floor": MIN_LANE_SHARE,
            "note": ("Both lanes run. Incremental work has a visible customer and "
                     "breakthrough work has an argument, so the argument loses every "
                     "planning round unless something stops it (#216).")}


def state(db) -> dict:
    """The lane's vocabulary and what this company can currently claim about the market."""
    market = observed_market(db)
    return {
        "axes": AXES,
        "observed_listings": market["listings"],
        "can_claim_market_gaps": bool(market["listings"]),
        "lane_floor": MIN_LANE_SHARE,
        "note": ("A divergence against our own catalogue is useful and is not a market gap. "
                 "Nothing here may borrow the authority of a scan that has not happened."),
    }
