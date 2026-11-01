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
    beds = ("Cat Basket Bed", "Cosy Pet Bed", "Kitten Nest", "Dog Basket")
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
