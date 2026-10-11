"""W4-PRODUCT: the Launch-0 catalogue-floor proposal is prepared, measured and NOT launched.

W4-LAUNCHREADY engineered three products (Nordic Forest Relief Baby Blanket, Diamond Lattice
Placemat Pair, Housewarming Key Basket) so Launch-0 could reach launch.readiness's floor of
MIN_LISTINGS_TO_OPEN = 8, and raised the Launch-0 cap 5 -> 8 on its branch. The cap is an
owner decision (D-FB-9), so here the three are a proposal: buildable and gate-checked now,
outside every Launch-0 scope until `products.launch0.CATALOGUE_FLOOR_APPROVED` is True.

These tests recompute the deterministic gates on the proposal (Product Truth, certification,
the first customer's document areas, listing identity, price plan, creative cohort, SEO
truth) and pin that nothing about Launch-0 moved. The stitch-key tests pin the renderer defect
the key basket exposed (94fe81b).

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_product_catalogue_floor_proposal.py
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
from brambleloop.runtime import pipeline  # noqa: E402

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


def test_the_proposal_is_not_launched_until_the_owner_approves():
    assert l0.CATALOGUE_FLOOR_APPROVED is False
    assert l0.PROPOSED_SLUGS == NEW
    assert len(l0.LAUNCH0_SLUGS) == 5, l0.LAUNCH0_SLUGS
    scope = l0.launch_scope_slugs()
    for slug in NEW:
        assert slug not in l0.LAUNCH0_SLUGS and slug not in scope, slug
        assert l0.candidate_for_cir(slug) is None, slug
        assert l0.launch_price(slug) is None, slug          # no Launch-0 price outside scope
    assert not set(l0.PROPOSED_BUILDERS) & set(l0.BUILDERS)
    assert "nordic-forest-mosaic-throw-baby" not in pipeline.ENGINEERED


def test_approval_reaches_the_floor_exactly():
    # What the one-line approval produces, computed rather than flipped.
    assert len(l0._CORE_LAUNCH0_SLUGS + l0.PROPOSED_SLUGS) == MIN_LISTINGS_TO_OPEN == 8
    assert not set(l0._CORE_LAUNCH0_SLUGS) & set(l0.PROPOSED_SLUGS)


def test_every_proposed_product_passes_product_truth_and_certifies():
    for slug in NEW:
        cand = l0.proposed_candidate(slug)
        truth = l0.product_truth(cand)
        assert truth["passes_gates"], (slug, truth["gates"])
        assert truth["aspiration"]["physically_calibrated"] is False   # never claimed
        for v in cand.variants:
            cir = l0.cir_for(v.build)
            assert cir.slug == slug, (slug, cir.slug)
            assert certify(cir).granted, slug


def test_the_release_chain_would_build_the_same_pattern_the_registry_does():
    # One product, one slug (PT-11): what the chain's `_engineered_cir` builds on approval is
    # the proposal's own CIR, fingerprint for fingerprint.
    for slug in NEW:
        cir = l0.cir_for(l0.proposed_candidate(slug).variants[0].build)
        route = pipeline.ENGINEERED.get(slug) or pipeline.PROPOSED_ENGINEERED.get(slug)
        if route and route.startswith("launch0:"):
            eng = l0.cir_for(route.partition(":")[2])
        else:
            eng = pipeline._engineered_cir(slug)
        assert eng is not None and eng.fingerprint == cir.fingerprint, slug


def test_listing_identity_is_a_product_type_the_cir_names():
    for slug in NEW:
        cand = l0.proposed_candidate(slug)
        for v in cand.variants:
            cir = l0.cir_for(v.build)
            assert cand.listing.kind in fc.product_type_words_in_cir(cir), (
                slug, cand.listing.kind, fc.product_type_words_in_cir(cir))


def test_prices_are_sourced_and_decided_inside_their_plan():
    for slug in NEW:
        cand = l0.proposed_candidate(slug)
        assert cand.price.basis == l0.SOURCED
        plan = l0.price_plan(cand)
        low, high = plan["band_cad"]
        price = plan["price_cad"]
        assert price <= high and (price >= low or price == plan["proposed_cad"]), plan


def test_childrens_audience_is_decided_for_the_baby_blanket():
    # Assigned today by EXTRA_CHILDRENS_ASSIGNMENTS; the candidate agrees with it, so approval
    # cannot give one product two audiences (`_cir_audience_map` raises on that).
    assert l0.childrens_decision("nordic-forest-mosaic-throw-baby") == (
        l0.ASSIGNED, ("baby_blanket", "under_3"))
    baby = l0.proposed_candidate("nordic-forest-mosaic-throw-baby")
    assert (baby.subcategory, baby.audience) == ("baby_blanket", "under_3")
    for slug in ("mosaic-placemat-pair", "housewarming-key-basket"):
        assert l0.proposed_candidate(slug).subcategory is None, slug
        assert not l0.child_words_in(l0.cir_for(
            l0.proposed_candidate(slug).variants[0].build).title), slug


def test_documents_pass_the_first_customer_document_areas():
    areas = ("final_pdf", "terminology", "counts_and_construction",
             "licence_and_safety_statements")
    for slug in NEW:
        cir = l0.cir_for(l0.proposed_candidate(slug).variants[0].build)
        gate = {c.area: c for c in fc.gate_product(cir).checks}
        for area in areas:
            assert gate[area].state == fc.PASS, (slug, area, gate[area].detail)


def test_the_engineered_proposals_survive_the_unchanged_jury_only_as_needs_taste():
    from brambleloop.creative import audit, jury

    r = audit.audit_launch0_engineered(proposed=True)
    assert r["cohort"]["name"] == "launch0_engineered_proposed"
    assert r["audited"] == ["nordic-forest-mosaic-throw-baby", "housewarming-key-basket"]
    assert r["survivors"] == r["audited"], r["verdicts"]
    for v in r["verdicts"].values():
        assert v["decision"] == jury.NEEDS_TASTE, v
    # The Launch-0 cohort itself is untouched by the proposal.
    assert audit.audit_launch0_engineered()["audited"] == [
        "nursery-nesting-baskets", "hexagon-coaster-set"]


def test_the_builder_proposal_is_a_creative_survivor():
    from brambleloop.creative import audit

    survivors = audit.audit_catalogue()["survivors"]
    assert "mosaic-placemat-pair" in survivors, survivors


def test_every_proposed_tag_and_title_word_is_traceable_to_the_product():
    from brambleloop.seo import strategy

    for slug in NEW:
        tags = strategy.TAGS[slug]
        assert len(tags) == 13 and len(set(tags)) == 13, (slug, tags)
        assert all(len(t) <= 20 for t in tags), (slug, [t for t in tags if len(t) > 20])
        assert len(strategy.TITLES[slug]) <= 140, slug
        family_phrases = {p for fam in strategy.FAMILIES[slug] for p in fam["phrases"]}
        assert set(tags) <= family_phrases, (slug, set(tags) - family_phrases)


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
