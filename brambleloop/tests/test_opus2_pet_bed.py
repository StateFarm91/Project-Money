"""OPUS2: a pet basket bed drafted as a wide, low vessel (construction breadth: pet products).

The radar fallback drafted every `pet` concept as a flat panel, which is right for a snuggle
mat and wrong for a bed. A titled bed or basket in the `pet` category is now the hexagon vessel
at one design size (about 45 cm across, a 10 cm wall); its listing states the compiled
diameter, never a pet's size. Padded, bolstered, hooded, cave or large-dog beds, and beds with a
second object, are a different construction and are refused by name.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_pet_bed.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.creative import fallback_constructions as F  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402


def _concept(title, category="pet"):
    seed = pipeline._seed_for("pet-snuggle-mat")
    geo = pipeline.concept_geometry(seed)
    return pipeline.Concept(slug="pet-bed-fixture", title=title, category=category,
                            stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]],
                            width_stitches=10, rows=4, colors=geo["colors"])


def test_a_titled_pet_bed_routes_to_the_vessel_and_a_mat_stays_flat():
    beds = ("Cat Basket Bed", "Cosy Pet Bed", "Kitten Nest", "Round Cat Bed", "Pet Basket")
    assert beds
    for title in beds:
        assert F.plan(category="pet", title=title)["family"] == F.VESSEL, title
    assert F.plan(category="pet", title="Pet Snuggle Mat")["family"] not in (F.VESSEL,
                                                                            F.REFUSED)
    # The word alone never routes another category to a pet bed.
    assert F.plan(category="home_decor", title="Bed Runner")["family"] != F.VESSEL


def test_padded_shaped_large_or_combined_beds_are_refused_by_name():
    refused = ("Bolster Cat Bed", "Cushioned Pet Bed", "Donut Dog Bed", "Cat Cave Bed",
               "Hooded Kitten Bed", "Large Dog Bed", "XL Pet Bed", "Pet Bed and Blanket",
               "Cat Bed with Pillow", "Pet Bed & Toy")
    assert refused
    for title in refused:
        route = F.plan(category="pet", title=title)
        assert route["family"] == F.REFUSED and route["needs"], title


def test_review_opus2j_j9_j10_j12_only_a_titled_cat_bed_becomes_a_basket():
    # J-9: the bed word must be the head noun; other objects and features are refused.
    not_beds = ("Pet Bed Liner", "Pet Bed Blanket", "Pet Bed Mat", "Pet Bed Cover",
                "Pet Bed Pad", "Dog Bed Topper", "Cat Bed Hammock", "Basket Weave Pet Mat",
                "Basket Weave Pet Blanket", "Nest Toy", "Cat Basket Toy")
    featured = ("Heated Cat Bed", "Waterproof Cat Bed", "Orthopedic Cat Bed", "Window Cat Bed",
                "Raised Edge Cat Bed", "Basket Weave Cat Bed")
    # J-10: no other animal's size is sourced; one design size only.
    animals = ("Dog Bed", "Puppy Bed", "Great Dane Bed", "Hamster Bed", "Bird Nest",
               "Rabbit Basket", "Dog Basket")
    sizes = ("Small Cat Bed", "Medium Cat Bed", "Tiny Kitten Bed", "Mini Cat Bed")
    # J-12: one release is one bed.
    plurals = ("Pet Beds", "Two Cat Beds", "Cat Bed Pair")
    assert not_beds and featured and animals and sizes and plurals
    for title in not_beds:
        assert F.plan(category="pet", title=title)["family"] != F.VESSEL, title
    for title in featured + animals + sizes + plurals:
        route = F.plan(category="pet", title=title)
        assert route["family"] == F.REFUSED and route["needs"], (title, route)


def test_review_opus2k_k7_k8_only_plain_cat_and_pet_words_may_precede_the_bed():
    drafted = ("Cat Basket Bed", "Cosy Pet Bed", "Kitten Nest", "Round Cat Bed", "Pet Basket",
               "Crochet Cat Bed", "Snug Kitty Bed")
    refused = ("German Shepherd Bed", "Golden Retriever Bed", "Lab Bed", "Corgi Bed",
               "Doggy Bed", "Pooch Bed", "Canine Bed", "Guinea-Pig Bed", "Gerbil Bed",
               "Rats Nest", "Birds Nest", "Owl Nest", "Maine Coon Bed", "Little Cat Bed",
               "Huge Cat Bed", "King Size Cat Bed", "Self-Warming Cat Bed", "Thermal Cat Bed",
               "Memory Foam Cat Bed", "Plush Cat Bed", "Cat Sofa Bed", "Cat Hideaway Bed",
               "Cat Carrier Basket", "Cat Litter Basket", "Treat Basket", "Pet Food Basket",
               "Leash Basket", "Doll Bed", "Teddy Bed", "Hen Nest", "Easter Nest", "Egg Basket")
    assert drafted and refused
    for title in drafted:
        assert F.plan(category="pet", title=title)["family"] == F.VESSEL, title
    for title in refused:
        route = F.plan(category="pet", title=title)
        assert route["family"] == F.REFUSED and route["needs"], (title, route)
    # K-8: a non-bed head with no denylist word is never the vessel (pins the `$` anchor).
    for title in ("Cat Bed Runner", "Cat Basket Lid"):
        assert F.plan(category="pet", title=title)["family"] != F.VESSEL, title


def test_review_opus2j_j11_the_size_is_sourced_and_lives_in_products_vessels():
    from brambleloop.products import vessels

    assert vessels.PET_BED_SIZE.across_cm == 48.0 and vessels.PET_BED_SIZE.tall_cm == 10.0
    assert "40-50 cm" in vessels.PET_BED_SIZE_SOURCE and "retrieved 2026-11-01" in \
        vessels.PET_BED_SIZE_SOURCE and "https://" in vessels.PET_BED_SIZE_SOURCE
    assert "thesize" not in vessels.PET_BED_SIZE_SOURCE      # OPUS2K K-9: unverified, dropped
    # OPUS2K K-9: the vessel reads PET_BED_SIZE (not an inlined copy).
    import dataclasses

    real = vessels.PET_BED_SIZE
    vessels.PET_BED_SIZE = dataclasses.replace(real, across_cm=30.0)
    try:
        small = F.vessel(_concept("Cat Basket Bed"))
    finally:
        vessels.PET_BED_SIZE = real
    assert max(r.declared_count for r in small.components[0].rows) < \
        max(r.declared_count for r in F.vessel(_concept("Cat Basket Bed")).components[0].rows)
    cir = F.vessel(_concept("Cat Basket Bed"))
    assert "published cat-bed sizing guidance" in cir.finished_size_note
    points, flats = vessels.hexagon_spans_cm(max(r.declared_count for r in cir.components[0].rows),
                                             cir.gauge)
    assert flats >= 40.0, flats                 # even the flats give the sourced interior


def test_the_bed_compiles_wide_and_low_and_states_its_computed_size():
    cir = F.vessel(_concept("Cat Basket Bed"))
    result = compile_cir(cir)
    assert result.ok, [str(f) for f in result.errors]
    assert cir.components[0].name == "bed"
    assert "pet basket bed" in cir.finished_size_note
    assert "Computed, not yet measured" in cir.finished_size_note
    from brambleloop.products.vessels import diameter_cm

    base = max(r.declared_count for r in cir.components[0].rows)
    across = diameter_cm(base, cir.gauge)
    assert 38.0 <= across <= 52.0, across                # the 45 cm design size, rounded
    import re

    wall_cm = float(re.search(r"walls about (\d+) cm tall", cir.finished_size_note).group(1))
    assert 8.0 <= wall_cm <= 12.0, wall_cm               # low: a pet steps in over it
    basket = F.vessel(_concept("Storage Basket", category="basket"))
    assert max(r.declared_count for r in basket.components[0].rows) < base   # and wider


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
