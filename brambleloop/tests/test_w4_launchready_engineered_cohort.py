"""W4-LAUNCHREADY: the engineered Launch-0 products are judged by the creative gate.

`creative.audit.audit_catalogue` judges builder designs only, so the nesting baskets and the
coaster set (engineered in products/vessels.py and products/launch0.py) were never judged and
`dashboard_truth.launch_inventory` failed them on `creative_gate_survivor` -- four certified
Launch-0 releases kept out of the opening grid by an audit that had not looked at them. They
are now their own cohort, judged by the unchanged jury. These tests pin that the gate is not
weaker: without a brief they still die, a brief that lies is refused, survival is needs_taste
and never approved, and a cohort that was not read clears nothing.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w4_launchready_engineered_cohort.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.app import dashboard_truth  # noqa: E402
from brambleloop.creative import audit  # noqa: E402
from brambleloop.creative import emotional_brief as EB  # noqa: E402
from brambleloop.creative import jury  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.products.builder import CATALOGUE  # noqa: E402

FAILS = 0


def check(name, fn):
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as e:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {e!r}")


def test_cohort_is_exactly_the_launch0_products_outside_the_builder():
    got = [c.slug for c in audit.engineered_candidates()]
    want = [s for s in l0.LAUNCH0_SLUGS
            if not {l0.cir_for(v.build).slug for v in l0.candidate(s).variants} & set(CATALOGUE)]
    assert got == want, (got, want)
    assert got == ["nursery-nesting-baskets", "hexagon-coaster-set"], got
    # Every engineered candidate has a recorded motif and brief; none is left unjudged.
    assert set(got) == set(audit.ENGINEERED_MOTIF) == set(EB.ENGINEERED_BRIEFS)


def test_briefs_validate_and_survive_only_as_needs_taste():
    r = audit.audit_launch0_engineered()
    assert r["cohort"]["name"] == audit.ENGINEERED_COHORT
    for slug in r["audited"]:
        assert r["states"][slug]["state"] == "briefed", r["states"][slug]
        v = r["verdicts"][slug]
        # Structurally clean is not approved: nothing here can see.
        assert v["decision"] == jury.NEEDS_TASTE, v
        assert set(v["unjudged"]) == {"thumbnail_legibility", "craft_impression"}, v
    assert r["survivors"] == ["nursery-nesting-baskets", "hexagon-coaster-set"]
    variants = sorted(l0.cir_for(v.build).slug for s in r["survivors"]
                      for v in l0.candidate(s).variants)
    assert r["survivor_slugs"] == variants


def test_without_the_brief_the_same_jury_rejects():
    for cand in audit.engineered_candidates():
        literal, why = audit.concept_from_candidate(cand)
        assert literal is not None, why
        v = jury.judge(literal, jury.Context(catalogue=[], techniques=1))
        assert v.decision == jury.REJECTED, (cand.slug, v.to_dict())
        assert any(f.critic == "emotional_appeal" for f in v.findings), v.to_dict()


def test_a_dishonest_brief_is_refused():
    cand = l0.candidate("hexagon-coaster-set")
    good = EB.ENGINEERED_BRIEFS[cand.slug]
    motif = audit.ENGINEERED_MOTIF[cand.slug]
    assert EB.validate(good, motif=motif, title=cand.title) == []
    # Imagery the fabric does not carry.
    starry = replace(good, premise="Four hexagon coasters each carry a raised star on a "
                                   "cream centre under the mugs.")
    assert any("Product Truth" in p for p in EB.validate(starry, motif=motif,
                                                          title=cand.title))
    # The default answer the gate exists to reject.
    default = replace(good, recipient="self", occasion="everyday", feeling="cosy")
    assert EB.validate(default, motif=motif, title=cand.title)
    # Social proof is never design intent.
    proof = replace(good, moment=good.moment + " A bestseller with every guest.")
    assert any("social-proof" in p for p in EB.validate(proof, motif=motif,
                                                          title=cand.title))


def test_a_recolour_of_a_catalogue_design_still_dies_of_sameness():
    catalogue, _ = audit.briefed_catalogue_concepts()
    target = next(c for c in catalogue if c.key == "mosaic-placemat-pair")
    coaster, _state = audit.briefed_engineered(l0.candidate("hexagon-coaster-set"))
    clone = replace(coaster, pod=target.pod, form=target.form,
                    construction=target.construction, motif=target.motif,
                    recipient=target.recipient, occasion=target.occasion,
                    function=target.function, premise=target.premise)
    v = jury.judge(clone, jury.Context(catalogue=catalogue, techniques=1))
    assert v.decision == jury.REJECTED and v.findings[0].critic == "sameness", v.to_dict()


def test_jury_thresholds_unchanged():
    assert jury.CLONE_THRESHOLD == 0.25
    assert [n for n, _ in jury.CRITICS] == ["sameness", "genericness", "emotional_appeal",
                                            "derivative", "thumbnail", "complexity",
                                            "shopping_window"]


def test_alive_slugs_joins_cohorts_and_an_unread_cohort_clears_nothing():
    legacy_only = {"survivors": ["cloudline-baby-blanket"]}
    assert dashboard_truth.alive_slugs(legacy_only) == ["cloudline-baby-blanket"]
    both = {"survivors": ["cloudline-baby-blanket"],
            "launch0_engineered": {"survivor_slugs": ["market-basket-small",
                                                      "cloudline-baby-blanket"]}}
    assert dashboard_truth.alive_slugs(both) == ["cloudline-baby-blanket",
                                                 "market-basket-small"]
    rejected = {"survivors": [], "launch0_engineered": {"survivors": [],
                                                        "survivor_slugs": []}}
    assert dashboard_truth.alive_slugs(rejected) == []


def test_creative_survivors_keeps_the_legacy_count_separate():
    r = dashboard_truth.creative_survivors()
    eng = r["launch0_engineered"]
    # F-188: the legacy KPI still counts the builder cohort only.
    assert r["audited"] == len(CATALOGUE)
    assert not set(eng["survivor_slugs"]) & set(r["survivors"])
    assert set(dashboard_truth.alive_slugs(r)) == set(r["survivors"]) | set(
        eng["survivor_slugs"])


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
