"""A collection is several original products sharing one visual idea, not one product recoloured.

Requirement 289. The sentence that carries the requirement is its last one: collections share
a palette and a story and remain *original products, not derivatives*. Everything else --
cross-sell, bundles, price points -- follows from that and is worthless without it.

The failure is not laziness. It is that a derivative is the cheapest way to make a collection
look complete, and it looks complete right up until a buyer sees the page and reads four names
for one product. A shop with four throws differing in motif and palette has one product and
four listings; a shop with a throw, a stocking, a garland and a set of coasters sharing a
motif has a collection, and the difference is visible in a single screenshot.

So coherence and originality are checked as opposing constraints, which is what makes this
more than a naming convention:

**Members must share the visual language.** A collection whose members share nothing is a
shelf, and the palette and story are the things a buyer recognises across a grid.

**Members must differ structurally.** The concept engine already measures this: `distance()`
deliberately scores a pure recolour at zero, because palette is not a term in it. A member
too close to another member is a derivative wearing a collection name, and it is refused by
the same arithmetic that refuses a duplicate concept in a tournament field.

**A collection needs more than one price point.** Cross-sell is the entire commercial argument
for a collection, and it requires something cheap to enter at and something dearer to move to.
One price point is a range with one thing in it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..creative.concept import Concept, distance
from ..creative.family import LANE_ORDER

# Below this, two members are the same idea. The tournament's own duplicate threshold, used
# here for the same reason: a collection is a field of concepts that happens to be sold
# together, and a field of recolours is a field of recolours whatever it is called.
DERIVATIVE_BELOW = 0.25

# A collection needs at least this many members to be one. Two is a product and its
# accessory, which every product has.
MIN_MEMBERS = 3

# And at least this many distinct make lanes, which is what a price ladder is made of before
# anything is priced.
MIN_PRICE_POINTS = 2


class CollectionRefused(ValueError):
    """A collection of derivatives, of strangers, or at a single price point."""


@dataclass
class Collection:
    key: str
    event: str
    palette_story: str
    visual_language: str          # the motif idea the members share, in words
    members: list[Concept] = field(default_factory=list)


def _lane_ladder(members: list[Concept]) -> list[dict]:
    """The price ladder, in lanes, cheapest first. Lane is the honest proxy before pricing."""
    seen: dict[str, list[str]] = {}
    for member in members:
        seen.setdefault(member.make_lane, []).append(member.key)
    return [{"lane": lane, "members": sorted(keys)}
            for lane, keys in sorted(seen.items(), key=lambda kv: LANE_ORDER.index(kv[0]))]


def check(collection: Collection) -> list[str]:
    """Everything that would make this a collection in name only."""
    problems: list[str] = []
    members = collection.members

    if len(members) < MIN_MEMBERS:
        problems.append(
            f"COLLECTION_TOO_SMALL: {len(members)} member(s) against a minimum of "
            f"{MIN_MEMBERS}. Two is a product and its accessory, which every product has")

    keys = [m.key for m in members]
    if len(keys) != len(set(keys)):
        problems.append("COLLECTION_DUPLICATE_MEMBER: the same product is listed twice")

    for i, a in enumerate(members):
        for b in members[i + 1:]:
            apart = distance(a, b)
            if apart < DERIVATIVE_BELOW:
                problems.append(
                    f"COLLECTION_DERIVATIVE: {a.key} and {b.key} are {apart} apart, below "
                    f"{DERIVATIVE_BELOW}. A collection shares a palette and a story and is "
                    f"made of original products; this pair is one product with two names")

    off_story = [m.key for m in members
                 if m.palette_story.strip().lower()
                 != collection.palette_story.strip().lower()]
    if off_story:
        problems.append(
            f"COLLECTION_INCOHERENT: {off_story} do not carry the collection's palette and "
            f"story, and the palette is what a buyer recognises across a grid")

    off_occasion = [m.key for m in members if m.occasion != collection.event]
    if off_occasion:
        problems.append(
            f"COLLECTION_OFF_OCCASION: {off_occasion} are not for {collection.event}")

    ladder = _lane_ladder(members)
    if len(ladder) < MIN_PRICE_POINTS:
        problems.append(
            f"COLLECTION_ONE_PRICE_POINT: every member is a {ladder[0]['lane']} make. "
            f"Cross-sell is the commercial argument for a collection and it needs somewhere "
            f"cheap to enter and somewhere dearer to move to"
            if ladder else "COLLECTION_EMPTY")
    return problems


def cross_sell(collection: Collection) -> list[dict]:
    """Which pairs a buyer plausibly buys together: same story, different commitment."""
    out = []
    members = sorted(collection.members, key=lambda m: LANE_ORDER.index(m.make_lane))
    for i, cheap in enumerate(members):
        for dear in members[i + 1:]:
            if cheap.make_lane == dear.make_lane:
                continue
            out.append({
                "entry": cheap.key, "entry_lane": cheap.make_lane,
                "upsell": dear.key, "upsell_lane": dear.make_lane,
                "why": (f"{cheap.make_lane.lower()} make as the entry and a "
                        f"{dear.make_lane.lower()} one to move to, sharing "
                        f"{collection.visual_language}"),
            })
    return out


def assess(collection: Collection) -> dict:
    """The collection with its problems named, refusing nothing so a reader can see them."""
    problems = check(collection)
    ladder = _lane_ladder(collection.members)
    spreads = [distance(a, b)
               for i, a in enumerate(collection.members) for b in collection.members[i + 1:]]
    return {
        "collection": collection.key,
        "event": collection.event,
        "visual_language": collection.visual_language,
        "palette_story": collection.palette_story,
        "members": [m.key for m in collection.members],
        "price_ladder": ladder,
        "price_points": len(ladder),
        # Minimum, not mean: one derivative pair makes a collection a derivative collection,
        # and an average over the other pairs hides it.
        "closest_pair": round(min(spreads), 4) if spreads else None,
        "cross_sell": cross_sell(collection),
        "problems": problems,
        "coherent": not problems,
        "note": ("this is a collection: original products sharing one visual idea across "
                 "more than one price point" if not problems else
                 f"{len(problems)} problem(s); a collection in name only is visible to a "
                 "buyer in a single screenshot"),
    }


def assemble(event: str, *, key: str, palette_story: str, visual_language: str,
             candidates: list[Concept]) -> dict:
    """Build the largest coherent collection these candidates support.

    Greedy by lane breadth rather than by score: the constraint that actually binds is the
    price ladder, and a collection of five excellent quick makes is still one price point.
    """
    eligible = [c for c in candidates
                if c.occasion == event
                and c.palette_story.strip().lower() == palette_story.strip().lower()]
    chosen: list[Concept] = []
    for candidate in sorted(eligible, key=lambda c: LANE_ORDER.index(c.make_lane)):
        if any(distance(candidate, member) < DERIVATIVE_BELOW for member in chosen):
            continue
        chosen.append(candidate)

    collection = Collection(key=key, event=event, palette_story=palette_story,
                            visual_language=visual_language, members=chosen)
    report = assess(collection)
    report["rejected"] = [c.key for c in eligible if c not in chosen]
    report["ineligible"] = [c.key for c in candidates if c not in eligible]
    report["why_rejected"] = ("a derivative of a member already chosen: sharing a palette is "
                              "what a collection does and sharing a structure is what a "
                              "recolour does")
    return report
