"""A collection is original products sharing one visual idea, not one product recoloured.

v1.4.3 requirement 289, whose last clause is the requirement: collections share a palette and
a story and remain original products, not derivatives. Everything else -- cross-sell, bundles,
price points -- follows from that and is worthless without it.

The failure is not laziness. A derivative is the cheapest way to make a collection look
complete, and it looks complete until a buyer sees the page and reads four names for one
product. So these tests check coherence and originality as opposing constraints, which is
what makes this more than a naming convention.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.creative.concept import Concept  # noqa: E402
from brambleloop.seasonal import collections as C  # noqa: E402

STORY = "cream and spruce"


def _concept(key: str, form: str, construction: str, lane: str, motif: str, *,
             story: str = STORY, occasion: str = "christmas",
             function: str = "warms a room") -> Concept:
    return Concept(
        key=key, title=key.title(),
        premise=f"a {motif} worked across a deep cream field",
        pod="home", form=form, construction=construction, motif=motif,
        palette_story=story, recipient="host", occasion=occasion,
        feeling="nostalgic", function=function, make_lane=lane)


def _healthy() -> C.Collection:
    return C.Collection(
        key="nordic-forest", event="christmas", palette_story=STORY,
        visual_language="a pine forest silhouette",
        members=[
            _concept("throw", "rectangle_throw", "mosaic_overlay", "LONG", "pine forest"),
            _concept("stocking", "stocking", "tapestry", "SHORT", "pine sprig",
                     function="hangs on a mantel"),
            _concept("coaster", "coaster", "mosaic_overlay", "QUICK", "single pine",
                     function="protects a table"),
        ])


# ---- originality ----------------------------------------------------------


def test_a_recolour_cannot_be_a_second_member():
    """The concept engine scores a pure recolour at zero distance because palette is not a
    term in it, and this uses the same arithmetic for the same reason."""
    collection = _healthy()
    collection.members.append(
        _concept("throw-in-red", "rectangle_throw", "mosaic_overlay", "LONG", "pine forest"))

    problems = C.check(collection)

    assert any("COLLECTION_DERIVATIVE" in p for p in problems), problems
    assert any("one product with two names" in p for p in problems)


def test_the_closest_pair_is_reported_rather_than_the_average():
    """One derivative pair makes a collection a derivative collection, and a mean over the
    other pairs hides it."""
    collection = _healthy()
    collection.members.append(
        _concept("throw-again", "rectangle_throw", "mosaic_overlay", "LONG", "pine forest"))

    report = C.assess(collection)

    assert report["closest_pair"] < C.DERIVATIVE_BELOW
    assert report["coherent"] is False


def test_the_same_product_listed_twice_is_caught_separately():
    collection = _healthy()
    collection.members.append(collection.members[0])

    assert any("DUPLICATE_MEMBER" in p for p in C.check(collection))


# ---- coherence ------------------------------------------------------------


def test_a_member_that_does_not_carry_the_palette_is_a_stranger():
    collection = _healthy()
    collection.members.append(
        _concept("gold-pillow", "pillow", "flat_rows", "SHORT", "star",
                 story="red and gold", function="dresses a sofa"))

    problems = C.check(collection)

    assert any("COLLECTION_INCOHERENT" in p for p in problems)
    assert any("recognises across a grid" in p for p in problems)


def test_a_member_for_another_occasion_is_refused():
    collection = _healthy()
    collection.members.append(
        _concept("pumpkin", "basket", "in_the_round", "SHORT", "pumpkin",
                 occasion="halloween", function="holds yarn"))

    assert any("OFF_OCCASION" in p for p in C.check(collection))


def test_two_members_are_a_product_and_its_accessory():
    collection = _healthy()
    collection.members = collection.members[:2]

    problems = C.check(collection)

    assert any("COLLECTION_TOO_SMALL" in p for p in problems)
    assert any("which every product has" in p for p in problems)


# ---- the price ladder -----------------------------------------------------


def test_one_price_point_is_a_range_with_one_thing_in_it():
    collection = C.Collection(
        key="all-quick", event="christmas", palette_story=STORY,
        visual_language="a pine forest silhouette",
        members=[
            _concept("coaster", "coaster", "mosaic_overlay", "QUICK", "single pine",
                     function="protects a table"),
            _concept("ornament", "ornament", "amigurumi_shaping", "QUICK", "small robin",
                     function="hangs on a tree"),
            _concept("garland", "garland", "motif_join", "QUICK", "pine chain",
                     function="dresses a mantel"),
        ])

    problems = C.check(collection)

    assert any("ONE_PRICE_POINT" in p for p in problems)
    assert any("cheap to enter" in p for p in problems)


def test_the_ladder_runs_cheapest_first():
    report = C.assess(_healthy())
    assert [row["lane"] for row in report["price_ladder"]] == ["QUICK", "SHORT", "LONG"]
    assert report["price_points"] == 3


def test_cross_sell_pairs_differ_in_commitment_rather_than_in_colour():
    pairs = C.cross_sell(_healthy())

    assert pairs
    for pair in pairs:
        assert pair["entry_lane"] != pair["upsell_lane"]
    assert ("coaster", "throw") in [(p["entry"], p["upsell"]) for p in pairs]


def test_a_healthy_collection_is_reported_as_one():
    report = C.assess(_healthy())

    assert report["coherent"] is True
    assert report["problems"] == []
    assert "original products sharing one visual idea" in report["note"]


# ---- assembling one --------------------------------------------------------


def test_assembly_drops_derivatives_and_strangers_and_says_which():
    candidates = [
        _concept("throw", "rectangle_throw", "mosaic_overlay", "LONG", "pine forest"),
        _concept("throw-again", "rectangle_throw", "mosaic_overlay", "LONG", "pine forest"),
        _concept("stocking", "stocking", "tapestry", "SHORT", "pine sprig",
                 function="hangs on a mantel"),
        _concept("coaster", "coaster", "mosaic_overlay", "QUICK", "single pine",
                 function="protects a table"),
        _concept("gold-pillow", "pillow", "flat_rows", "SHORT", "star",
                 story="red and gold", function="dresses a sofa"),
    ]

    report = C.assemble("christmas", key="nordic-forest", palette_story=STORY,
                        visual_language="a pine forest silhouette", candidates=candidates)

    assert set(report["members"]) == {"throw", "stocking", "coaster"}
    assert report["rejected"] == ["throw-again"]
    assert report["ineligible"] == ["gold-pillow"]
    assert report["coherent"] is True
    assert "what a recolour does" in report["why_rejected"]


def test_assembly_prefers_lane_breadth_because_that_is_the_constraint_that_binds():
    """A collection of five excellent quick makes is still one price point."""
    candidates = [
        _concept("coaster", "coaster", "mosaic_overlay", "QUICK", "single pine",
                 function="protects a table"),
        _concept("throw", "rectangle_throw", "mosaic_overlay", "LONG", "pine forest"),
        _concept("stocking", "stocking", "tapestry", "SHORT", "pine sprig",
                 function="hangs on a mantel"),
    ]

    report = C.assemble("christmas", key="nordic-forest", palette_story=STORY,
                        visual_language="a pine forest silhouette", candidates=candidates)

    assert report["price_points"] == 3


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
