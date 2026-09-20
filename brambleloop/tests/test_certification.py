"""#3 stage five: the release gates, run rather than named.

The gates already existed and already decided whether a pattern ships. What did not exist was
a route from a tournament survivor to a certificate, so these tests are about the three
inputs the chain needs and where each one legitimately comes from.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.creative import certification as C  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _priced(db, pod="hats", prices=(8.0, 9.0, 10.0, 45.0)):
    with db.session() as s:
        for i, price in enumerate(prices):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"{pod}{i}",
                                   title="Crochet Hat Pattern", pod=pod, price_cad=price))
    return db


def _concept(form="hat", construction="in_the_round", key="a", pod="hats") -> Concept:
    return Concept(
        key=key, title="Lantern Brim Object",
        premise=("a folded brim that stands proud of the crown so the silhouette reads "
                 "from across a room"),
        pod=pod, form=form, construction=construction, motif="lantern",
        palette_story="ember and soot", recipient="self", occasion="everyday",
        feeling="cosy", function="keeps a head warm and findable after dark",
        make_lane="SHORT", provenance="test")


def test_the_whole_release_chain_runs_rather_than_being_named():
    out = C.release(_priced(_db()), [_concept()])
    detail = out["detail"]["a"]
    assert detail["granted"] is True, detail
    # The gates the funnel names for this stage, actually among the stages run.
    for stage in ("asset_truth", "policy", "reverse", "originality", "confidence"):
        assert stage in detail["stages_run"], detail["stages_run"]
    assert [c.key for c in out["survivors"]] == ["a"]


def test_the_price_is_the_median_of_what_the_market_charges():
    """The median rather than the mean: one bundle at CA$45 moves a mean and does not move
    what a shopper expects to pay."""
    priced = C.observed_price(_priced(_db()), "hats")
    assert priced["measurable"] is True
    assert priced["price_cad"] == 9.5, priced
    assert priced["observed"] == 4


def test_an_unpriced_department_falls_back_to_the_floor_and_says_so():
    """A plausible-looking number would read as evidence. The floor cannot be mistaken for one."""
    from brambleloop.commerce.pricing import MIN_PRICE_CAD

    unpriced = C.observed_price(_db(), "hats")
    assert unpriced["measurable"] is False
    assert unpriced["price_cad"] == MIN_PRICE_CAD
    assert "would read as evidence" in unpriced["why"]


def test_the_hero_is_rendered_from_the_twin_and_never_claims_to_be_a_photograph():
    """Photographic imagery waits on image_generation, and an asset claiming to be one is
    exactly what the asset-truth gate refuses."""
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.creative.prototype import author
    from brambleloop.gates.asset_truth import AssetClass

    cir = author(_concept())
    result = compile_cir(cir)
    hero = C.hero_for(cir, build_twin(cir, result))
    assert hero.asset_class == AssetClass.DIGITAL_TWIN_RENDER
    assert hero.provenance.source == "twin"
    assert hero.is_hero is True
    # Its claims come from the twin, which is what makes them checkable.
    assert hero.depicts_colors == sorted(cir.colors)
    assert hero.claims.finished_width_cm > 0


def test_the_listing_claims_nothing_the_concept_does_not_say():
    """Deterministic copy cannot overclaim, which is the failure the policy gate's proof
    check exists for one level up."""
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.creative.prototype import author
    from brambleloop.gates.policy import check_listing
    from brambleloop.quality.proof import check_claim

    concept = _concept()
    cir = author(concept)
    assert compile_cir(cir).ok
    draft = C.listing_for(concept, cir, 9.5)

    assert len(draft.title) <= 140
    assert len(draft.tags) <= 13
    assert all(len(t) <= 20 for t in draft.tags), draft.tags

    # At the level a freshly compiled pattern reaches, the copy claims nothing above it.
    at_release = {"deterministic_validation": True, "independent_reverse_compilation": True,
                  "physical_tester_example": False, "customer_project": False,
                  "repeat_purchase": False}
    assert check_claim(draft.title, at_release) == []
    assert check_claim(draft.description, at_release) == []
    assert not [f for f in check_listing(draft, cir, proof_states=at_release)
                if f.severity == "ERROR"], [str(f) for f in
                                            check_listing(draft, cir,
                                                          proof_states=at_release)]


def test_a_concept_that_cannot_be_authored_never_reaches_the_chain():
    out = C.release(_priced(_db()), [_concept(form="fitted_garment",
                                              construction="top_down_yoke", key="c")])
    assert out["killed"] == {"c": "unverifiable"}
    assert "no finished size on file" in out["detail"]["c"]["refused"]
    assert out["survivors"] == []


def test_a_refusal_by_the_chain_is_the_chain_working():
    """The stage does not decide. A tournament that certified its own survivors would be
    marking its own homework."""
    source = (ROOT / "src/brambleloop/creative/certification.py").read_text()
    # No path in this module can grant a certificate; it only reads `granted`.
    assert "granted=True" not in source
    assert "certificate.granted" in source
    out = C.release(_priced(_db()), [_concept()])
    assert "marking its own homework" in out["note"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
