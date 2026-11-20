"""W4-PRODUCT: D-W5-7 -- the radar and Launch-0 key the same products differently.

The radar scores the baskets and the coaster set as `market-basket-trio` / `hexie-coaster-set`;
Launch-0 sells them as `market-basket-small|medium|large` / `hexagon-coaster-set`. PT-11 routed
radar -> Launch-0 (`LEGACY_DUPLICATES`, `cir.draft`). Nothing routed back, so every reader keyed
on the certified product looked the radar up by the product slug and found nothing: the
teardown product class fell back to the slug, the #168 benchmark challenge filed four of the
seven Launch-0 releases under "uncategorised" (never challenged), and a storefront tile read
UNMEASURED strength instead of the radar prior the product was promoted on.

These tests pin the way back without renaming any key (the rename stays a merchandising
decision, D-W5-7): one exact resolver, used only by product-keyed readers.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_product_registry_keys.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402

FAILS = 0


def check(name, fn):
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as e:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {e!r}")


def test_every_launch0_release_reaches_the_opportunity_it_was_scored_as():
    # trend -> opportunity -> product: every Launch-0 release has a radar concept behind it.
    assert l0.LAUNCH0_SLUGS
    for slug in l0.LAUNCH0_SLUGS:
        variants = l0.candidate(slug).variants
        assert variants, slug
        for v in variants:
            cir_slug = l0.cir_for(v.build).slug
            seed = pipeline.product_seed(cir_slug)
            if cir_slug in l0.NO_RADAR_CONCEPT:      # CAP-1: a recorded non-radar origin
                assert seed is None and l0.NO_RADAR_CONCEPT[cir_slug], cir_slug
                continue
            assert seed is not None, cir_slug
            assert release._seed_for(cir_slug) is not None, cir_slug
    assert l0.radar_concept_for("nordic-forest-mosaic-throw-baby") == \
        "nordic-forest-mosaic-throw"
    assert set(l0.NO_RADAR_CONCEPT) == {"housewarming-key-basket"}


def test_the_aliases_resolve_exactly():
    for size in ("small", "medium", "large"):
        assert l0.radar_concept_for(f"market-basket-{size}") == "market-basket-trio"
        assert pipeline.product_seed(f"market-basket-{size}").category == "basket"
    assert l0.radar_concept_for("nursery-nesting-baskets") == "market-basket-trio"
    assert l0.radar_concept_for("hexagon-coaster-set") == "hexie-coaster-set"
    assert pipeline.product_seed("hexagon-coaster-set").category == "coaster"
    # Exact, never a prefix (PT-01 was a prefix match).
    assert l0.radar_concept_for("market-basket-smallish") is None
    assert l0.radar_concept_for("hexagon-coaster") is None
    assert l0.radar_concept_for("cloudline-baby-blanket") is None    # its own key is the radar's


def test_the_drafting_lookup_stays_exact():
    # `cir.draft` decides on `_seed_for` whether a payload is a new concept for the
    # pre-engineering gate; the alias must not change that decision.
    assert pipeline._seed_for("market-basket-small") is None
    assert pipeline._seed_for("hexagon-coaster-set") is None
    assert pipeline._seed_for("market-basket-trio").slug == "market-basket-trio"


def test_every_retired_alias_is_still_a_radar_concept():
    pool = {s.slug for s in pipeline.POOL}
    for alias, rec in l0.LEGACY_DUPLICATES.items():
        assert alias in pool, alias
        assert rec["superseded_by"], alias
        for target in rec["superseded_by"]:
            assert target in l0.launch_scope_slugs(), target
            assert l0.radar_concept_for(target) == alias, target


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
