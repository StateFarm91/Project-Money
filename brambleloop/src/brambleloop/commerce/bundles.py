"""Which products belong together, and who is allowed to say whether the bundle worked.

Requirement 234. Continuously identify natural combinations, test them, and track attach
rate, incremental order value, cannibalisation and contribution -- using only mechanisms the
marketplace actually supports, and only when they are profitable.

The measurement half already exists and is not rebuilt here. `commerce.attribution` answers
what a bundle added and what it took, on contribution, against a baseline window, and it
refuses without one: the after-window on its own shows a bundle selling and says nothing
about where its buyers came from. That refusal is the whole value of the measurement, and a
second implementation beside it would be a second answer to the same question -- which, in
practice, means the more flattering one gets quoted.

So this module does the half that was missing: deciding which bundles are worth testing at
all, and refusing the ones that are not.

**"Natural" has to mean something a machine can check.** A bundle nobody would use together
is two products in a discount, and a discount on things a buyer did not want is the cheapest
way to make a catalogue look busy. The tests here are the ones a maker would recognise: the
same occasion, the same yarn weight so one purchase of yarn serves both, a shared collection,
or forms that furnish the same room. Two products that share none of those are not a bundle;
they are a shelf.

**A bundle of one pod is a set; a bundle across four is a raffle.** The coherence that makes
somebody buy it is the same coherence that makes it describable in a title.

**The bundle must be cheaper to want than its parts are to buy, and still contribute.** At
zero marginal cost a digital bundle always looks profitable, so the check that matters is
not margin -- it is whether the discount is deep enough to be a reason and shallow enough
that the parts are still worth listing. A bundle at 5% off is a rounding error with a
listing; one at 60% off has told every buyer what the singles are really worth.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .promotion import STEEP_DISCOUNT_ABOVE

# What makes two products belong together, and how each is checked. Every one is a fact
# about the products rather than a judgement about the buyer.
AFFINITIES: dict[str, str] = {
    "same_occasion": "both are for the same event, so one shopping trip covers both",
    "same_weight": "the same yarn weight, so one purchase of yarn serves both",
    "same_collection": "they were designed as part of one body of work",
    "same_room": "they furnish the same place, so the set reads as a room rather than a list",
    "same_recipient": "both suit the same person, which is how a gift set is chosen",
}

# Forms that furnish the same room, for the `same_room` test. Named rather than inferred,
# because a machine cannot tell a throw from a table runner by looking at the word.
ROOMS: dict[str, tuple[str, ...]] = {
    "living_room": ("rectangle_throw", "pillow", "basket", "wall_hanging", "coaster"),
    "kitchen": ("flat_panel", "runner", "round_disc", "coaster"),
    "bedroom": ("rectangle_throw", "pillow", "basket"),
    "nursery": ("rectangle_throw", "sphere", "basket"),
    "tree": ("ornament", "stocking", "garland"),
}

# How many affinities two products need before they are a bundle rather than a shelf.
MIN_AFFINITIES = 2
# How many pods a bundle may span. Past this the coherence that makes somebody buy it is
# gone, and so is the sentence that would describe it.
MAX_PODS = 2
# How many products a bundle may hold before it is a collection with a different job.
MAX_PRODUCTS = 4
# A discount shallower than this is not a reason to buy the set.
MIN_DISCOUNT = 0.10


class BundleRefused(ValueError):
    """A combination nothing holds together, or a discount that misprices the parts."""


@dataclass(frozen=True)
class Item:
    """One product, described in the terms a bundle is decided on."""

    slug: str
    pod: str
    form: str
    price_cad: float
    occasion: str = ""
    weight: str = ""
    collection: str = ""
    recipient: str = ""


def affinities(a: Item, b: Item) -> list[str]:
    """Every reason these two belong together. Facts, not a judgement about the buyer."""
    found = []
    if a.occasion and a.occasion == b.occasion:
        found.append("same_occasion")
    if a.weight and a.weight == b.weight:
        found.append("same_weight")
    if a.collection and a.collection == b.collection:
        found.append("same_collection")
    if a.recipient and a.recipient == b.recipient:
        found.append("same_recipient")
    for forms in ROOMS.values():
        if a.form in forms and b.form in forms and a.form != b.form:
            found.append("same_room")
            break
    return found


def check(items: list[Item], *, price_cad: float) -> dict:
    """Whether this set is a bundle, and whether its price is a reason to buy it."""
    reasons: list[str] = []
    if len(items) < 2:
        reasons.append("a bundle of one is a product")
    if len(items) > MAX_PRODUCTS:
        reasons.append(f"{len(items)} products against a ceiling of {MAX_PRODUCTS}: past "
                       f"this it is a collection, which has a different job")

    pods = {i.pod for i in items}
    if len(pods) > MAX_PODS:
        reasons.append(
            f"{sorted(pods)} spans {len(pods)} departments. A bundle of one pod is a set and "
            f"a bundle across four is a raffle -- the coherence that makes somebody buy it "
            f"is the same coherence that makes it describable in a title")

    shared: set[str] | None = None
    for a, b in combinations(items, 2):
        pair = set(affinities(a, b))
        shared = pair if shared is None else (shared & pair)
    shared = shared or set()
    if len(shared) < MIN_AFFINITIES:
        reasons.append(
            f"{sorted(shared) or 'nothing'} holds every pair together, against a floor of "
            f"{MIN_AFFINITIES}. A bundle nobody would use together is two products in a "
            f"discount, and a discount on things a buyer did not want is the cheapest way "
            f"to make a catalogue look busy")

    parts = round(sum(i.price_cad for i in items), 2)
    discount = 1 - (price_cad / parts) if parts else 0.0
    if discount < MIN_DISCOUNT:
        reasons.append(f"{discount:.0%} off the parts, below {MIN_DISCOUNT:.0%}: a rounding "
                       f"error with a listing of its own")
    if discount > STEEP_DISCOUNT_ABOVE:
        reasons.append(
            f"{discount:.0%} off the parts, above {STEEP_DISCOUNT_ABOVE:.0%}. A discount "
            f"this deep has told every buyer what the singles are really worth, and they "
            f"will not unlearn it")

    return {
        "slugs": [i.slug for i in items], "ok": not reasons, "reasons": reasons,
        "shared_affinities": sorted(shared),
        "pods": sorted(pods),
        "parts_cad": parts, "price_cad": round(price_cad, 2),
        "discount": round(discount, 3),
        "note": ("worth testing: it holds together and the price is a reason"
                 if not reasons else f"{len(reasons)} reason(s) this is not a bundle"),
    }


def candidates(items: list[Item], *, limit: int = 10) -> dict:
    """Every pair worth testing, strongest affinity first.

    Pairs rather than larger sets on purpose: a pair is the smallest thing that can be
    tested, and a three-product bundle that fails tells you nothing about which pairing was
    wrong.
    """
    found = []
    for a, b in combinations(items, 2):
        shared = affinities(a, b)
        if len(shared) < MIN_AFFINITIES or len({a.pod, b.pod}) > MAX_PODS:
            continue
        found.append({
            "slugs": [a.slug, b.slug], "affinities": shared,
            "strength": len(shared),
            "parts_cad": round(a.price_cad + b.price_cad, 2),
            "suggested_cad": round((a.price_cad + b.price_cad) * (1 - MIN_DISCOUNT * 1.5), 2),
        })
    found.sort(key=lambda c: (-c["strength"], c["slugs"]))
    return {
        "candidates": found[:limit], "considered": len(items),
        "note": ("nothing in this catalogue holds together well enough to bundle, which is "
                 "a finding about the catalogue rather than about bundling"
                 if not found else ""),
    }


def measure(*, bundle_slug: str, bundle, components_before, components_after) -> dict:
    """Delegate to the attribution engine, which already refuses without a baseline.

    Not reimplemented here. A second implementation of "did the bundle add anything" would
    be a second answer to the same question, and in practice the more flattering one gets
    quoted.
    """
    from .attribution import bundle_effect

    result = bundle_effect(bundle_slug, bundle=bundle,
                           components_before=components_before,
                           components_after=components_after)
    return {"measured_by": "commerce.attribution.bundle_effect",
            "result": result.to_dict() if hasattr(result, "to_dict") else result.__dict__}


def state() -> dict:
    """What makes a bundle, and who answers whether it worked."""
    return {
        "affinities": dict(AFFINITIES),
        "rooms": {k: list(v) for k, v in ROOMS.items()},
        "floors": {"affinities": MIN_AFFINITIES, "min_discount": MIN_DISCOUNT},
        "ceilings": {"pods": MAX_PODS, "products": MAX_PRODUCTS,
                     "discount": STEEP_DISCOUNT_ABOVE},
        "measured_by": ("commerce.attribution.bundle_effect, which refuses without a "
                        "baseline window -- the after-window alone shows a bundle selling "
                        "and says nothing about where its buyers came from"),
        "note": ("A bundle nobody would use together is two products in a discount, and a "
                 "discount on things a buyer did not want is the cheapest way to make a "
                 "catalogue look busy. A bundle of one pod is a set; across four it is a "
                 "raffle (#234)."),
    }
