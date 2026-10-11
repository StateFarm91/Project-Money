"""W4-LAUNCHREADY (branch only): three products join Launch-0 to reach the catalogue floor.

Nordic Forest Relief Baby Blanket, Diamond Lattice Placemat Pair and Housewarming Key Basket
join the first five, so Launch-0 is eight products: the launch.readiness floor
(MIN_LISTINGS_TO_OPEN). Each passes the same gates the first five do. These tests recompute
the deterministic ones (Product Truth, certification, the first customer's document areas,
children's assignment, the listing identity the CIR backs) and pin the one renderer defect the
key basket exposed: a document that spells the slip stitch two ways must define both.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w4_launchready_catalogue_floor.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.gates import first_customer as fc  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.launch.readiness import MIN_LISTINGS_TO_OPEN  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.publish import abbreviations  # noqa: E402
from brambleloop.runtime.pipeline import _engineered_cir  # noqa: E402

NEW = ("nordic-forest-mosaic-throw-baby", "mosaic-placemat-pair", "housewarming-key-basket")
FAILS = 0


def check(name, fn):
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as e:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {e!r}")


def test_launch0_is_eight_products_at_the_floor():
    assert l0.LAUNCH0_SLUGS[-3:] == NEW, l0.LAUNCH0_SLUGS
    assert len(l0.LAUNCH0_SLUGS) == MIN_LISTINGS_TO_OPEN == 8


def test_every_new_product_passes_product_truth_and_certifies():
    for slug in NEW:
        cand = l0.candidate(slug)
        truth = l0.product_truth(cand)
        assert truth["passes_gates"], (slug, truth["gates"])
        assert truth["aspiration"]["physically_calibrated"] is False   # never claimed
        for v in cand.variants:
            cir = l0.cir_for(v.build)
            assert certify(cir).granted, slug
            # The release chain builds the same pattern the registry does (one product, one
            # slug: PT-11).
            eng = _engineered_cir(cir.slug)
            assert eng is not None and eng.fingerprint == cir.fingerprint, slug


def test_listing_identity_is_a_product_type_the_cir_names():
    for slug in NEW:
        cand = l0.candidate(slug)
        for v in cand.variants:
            cir = l0.cir_for(v.build)
            assert cand.listing.kind in fc.product_type_words_in_cir(cir), (
                slug, cand.listing.kind, fc.product_type_words_in_cir(cir))


def test_prices_are_inside_their_plan_and_basis_is_sourced():
    for slug in NEW:
        cand = l0.candidate(slug)
        assert cand.price.basis == l0.SOURCED
        cir_slug = l0.cir_for(cand.variants[0].build).slug
        lp = l0.launch_price(cir_slug)
        assert lp is not None and lp["within_plan_band"], lp


def test_baby_blanket_is_assigned_to_the_childrens_category():
    assert l0.childrens_decision("nordic-forest-mosaic-throw-baby") == (
        l0.ASSIGNED, ("baby_blanket", "under_3"))
    for slug in ("mosaic-placemat-pair", "housewarming-key-basket"):
        assert l0.childrens_decision(slug)[0] == l0.NOT_FOR_CHILDREN, slug


def test_documents_pass_the_first_customer_document_areas():
    areas = ("final_pdf", "terminology", "counts_and_construction",
             "licence_and_safety_statements")
    for slug in NEW:
        cir = l0.cir_for(l0.candidate(slug).variants[0].build)
        gate = {c.area: c for c in fc.gate_product(cir).checks}
        for area in areas:
            assert gate[area].state == fc.PASS, (slug, area, gate[area].detail)


def test_a_key_defines_every_spelling_of_a_stitch_the_document_uses():
    text = ("Join each round with a sl st to the first stitch.\n"
            "Rnd 24: slst in next 72 sts. (72 sts)")
    tokens = {e.token for e in abbreviations.stitch_key(text, "US")}
    assert {"sl st", "slst"} <= tokens, tokens
    # The completeness check against the printed key passes only because both are defined.
    assert abbreviations.undefined_tokens(text, "US", defined=tokens) == []
    assert abbreviations.undefined_tokens(text, "US", defined=tokens - {"sl st"})


def test_a_single_spelling_document_keys_one_entry():
    text = "Join each round with a sl st to the first stitch."
    entries = [e for e in abbreviations.stitch_key(text, "US") if "sl" in e.token]
    assert [e.token for e in entries] == ["sl st"], entries


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
