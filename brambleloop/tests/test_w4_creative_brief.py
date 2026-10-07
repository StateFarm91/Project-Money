"""W4-CREATIVE: emotional design briefs feed the creative gate; the gate is not weaker.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w4_creative_brief.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.creative import audit  # noqa: E402
from brambleloop.creative import emotional_brief as EB  # noqa: E402
from brambleloop.creative import jury  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402
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


def _bad(**kw) -> Concept:
    base = dict(key="known-bad", title="Known Bad Throw",
                premise="A diamond lattice motif worked in the cottage palette across 120 "
                        "stitches.",
                pod="home_decor", form="rectangle_throw", construction="flat_rows",
                motif="diamond-lattice", palette_story="cottage", recipient="self",
                occasion="everyday", feeling="cosy", function="", make_lane="QUICK")
    base.update(kw)
    return Concept(**base)


def test_gate_thresholds_unchanged():
    assert jury.CLONE_THRESHOLD == 0.25 and jury.FIELD_SPREAD_MINIMUM == 0.45
    assert [n for n, _ in jury.CRITICS] == ["sameness", "genericness", "emotional_appeal",
                                           "derivative", "thumbnail", "complexity",
                                           "shopping_window"]


def test_known_bad_candidates_still_rejected():
    cases = [_bad(),  # the exact legacy shape: no function
             _bad(function="a nice throw for the sofa every day"),  # default triple
             _bad(recipient="host", occasion="housewarming", function="nice")]  # 1 word
    assert cases
    for c in cases:
        v = jury.judge(c)
        assert v.decision == jury.REJECTED, (c.function, v.decision)
        assert any(f.critic == "emotional_appeal" for f in v.findings)


def test_raw_generator_reading_is_preserved():
    report = audit.audit_catalogue()
    raw = report["raw_generator"]
    assert report["products_audited"] == 11 == len(CATALOGUE)
    assert raw["survivors"] == [] and raw["rejected"] == 11
    assert raw["autopsy"]["deaths_by_critic"] == {"emotional_appeal": 11}


def test_briefed_catalogue_survives_only_as_needs_taste():
    report = audit.audit_catalogue()
    survivors = report["survivors"]
    assert len(survivors) >= 6, survivors
    assert set(survivors) == set(report["briefs"]["briefed"])
    for key in survivors:
        assert report["decisions"][key] == jury.NEEDS_TASTE  # never APPROVED without eyes
    assert report["cohort"]["generator_version"].startswith("builder@")
    assert "+briefs@" in report["cohort"]["generator_version"]


def test_title_imagery_conflicts_are_held_and_still_fail():
    report = audit.audit_catalogue()
    held = report["briefs"]["held"]
    assert set(held) == set(EB.HELD), held
    for key in held:
        assert report["decisions"][key] == jury.REJECTED
    assert EB.title_conflicts("Autumn Oak Overlay Mosaic Throw", "fir-and-star") == ["oak"]
    assert EB.title_conflicts("Heart Motif Garland", "heart-row") == []


def test_validator_refuses_dishonest_or_default_briefs():
    design = CATALOGUE["cloudline-baby-blanket"]
    good = EB.CATALOGUE_BRIEFS["cloudline-baby-blanket"]
    kw = dict(motif=design.motif, title=design.title,
              declared=EB.declared_by_slug(design.slug))
    assert EB.validate(good, **kw) == []
    bad = {
        "default": replace(good, recipient="self", occasion="everyday", feeling="cosy"),
        "social_proof": replace(good, moment=good.moment + " Loved by thousands of buyers."),
        "copy": replace(good, function="makes a great gift that new parents will love"),
        "foreign_imagery": replace(good, premise="A raised diamond lattice scattered with "
                                                 "tiny stars across the whole blanket."),
        "wrong_motif": replace(good, premise="A cabled border in cream and ink frames the "
                                             "whole blanket edge to edge."),
        "contradicts_name": replace(good, occasion="christmas"),
        "no_gifting": replace(good, gifting=""),
        "thin_function": replace(good, function="keeps warm"),
        "one_sense": replace(good, sensory=("raised diamond lattice ridges",)),
    }
    assert bad
    for name, brief in bad.items():
        assert EB.validate(brief, **kw), f"{name} was accepted"


def test_new_candidates_are_original_and_survive():
    catalogue, _ = audit.briefed_catalogue_concepts()
    result = EB.audit_candidates(catalogue)
    assert result["proposed"] == len(EB.NEW_CANDIDATES) >= 8
    assert result["refused_at_brief"] == {}
    assert len(result["survivors"]) >= 6, result["decisions"]
    concepts, _ = EB.candidate_concepts()
    assert concepts
    from brambleloop.creative.concept import nearest
    for c in concepts:
        near, d = nearest(c, catalogue)
        assert d >= jury.CLONE_THRESHOLD, (c.key, near.key if near else None, d)
        assert result["decisions"][c.key] in (jury.NEEDS_TASTE, jury.REJECTED)
        assert "no CIR" in c.provenance


def test_dashboard_reads_the_same_reading():
    from brambleloop.app import dashboard_truth

    report = audit.audit_catalogue()
    s = dashboard_truth.creative_survivors(None)
    assert s["count"] == len(report["survivors"]) >= 6
    assert s["audited"] == 11


# ---------------------------------------------------------------------------
# r2: the whole pre-engineering gate, not only the jury


def _fixture_cards():
    """A labelled TEST FIXTURE standing in for observed listings (never written anywhere)."""
    from brambleloop.creative import blinded

    card = blinded.from_listing({"listing_ref": "fixture-1", "pod": "blankets",
                                 "title": "Cozy Granny Square Baby Blanket Pattern",
                                 "product_type": "pattern", "price_cad": 18.0})
    return [card]


def test_candidates_fail_no_deterministic_check():
    from datetime import date

    r = EB.gate_candidates(today=date(2026, 10, 7))
    assert r["refused_at_brief"] == {}, r["refused_at_brief"]
    assert r["judged"] == len(EB.NEW_CANDIDATES) >= 8
    rows = r["candidates"]
    assert rows
    for key, row in rows.items():
        assert row["failed"] == [], (key, row["reasons"])
        assert row["decision"] == "waiting" and row["engineer"] is False, key
        assert set(row["waiting_on"]) <= {"image_vision", "benchmark_observation"}, key
        assert "jury" in row["unmeasured"] and "premise_thumbnail" in row["unmeasured"]


def test_without_the_design_brief_the_same_gate_refuses():
    from datetime import date

    from brambleloop.creative.preengineering import gate_concept

    catalogue, _ = audit.briefed_catalogue_concepts()
    concepts, _ = EB.candidate_concepts()
    assert concepts
    for c in concepts:
        v = gate_concept(None, c, brief={}, catalogue=catalogue, today=date(2026, 10, 7))
        assert v["decision"] == "refused" and "premise_thumbnail" in v["failed"], c.key


def test_needs_taste_clears_only_on_a_recorded_judgement():
    """What clears needs_taste: a judged board (fixture values, never stored)."""
    from datetime import date

    from brambleloop.creative.preengineering import gate_concept

    catalogue, _ = audit.briefed_catalogue_concepts()
    concepts = {c.key: c for c in EB.candidate_concepts()[0]}
    base = concepts["heart-row-ring-pillow"]
    brief = EB.GATE_BRIEFS[base.key].to_brief()
    cards = _fixture_cards()
    assert cards

    def run(**taste):
        return gate_concept(None, replace(base, **taste), brief=brief, catalogue=catalogue,
                            benchmark=cards, today=date(2026, 10, 7))

    assert run()["decision"] == "waiting"
    assert run(thumbnail_reads_small=True, craft_impression=4.0)["decision"] == "passed"
    assert run(thumbnail_reads_small=True, craft_impression=3.0)["decision"] == "refused"
    assert run(thumbnail_reads_small=False, craft_impression=4.5)["decision"] == "refused"
    # Nothing in the design process writes the taste fields.
    assert concepts
    for c in concepts.values():
        assert c.thumbnail_reads_small is None and c.craft_impression is None


def test_gate_brief_honesty():
    concepts = {c.key: c for c in EB.candidate_concepts()[0]}
    pillow = concepts["heart-row-ring-pillow"]
    assert EB.gate_brief_problems(pillow) == []
    lying = replace(EB.GATE_BRIEFS[pillow.key],
                    storyboard="round pillow covered in oak leaves and stars, rings tied on")
    saved = EB.GATE_BRIEFS[pillow.key]
    EB.GATE_BRIEFS[pillow.key] = lying
    try:
        assert any("Product Truth" in p for p in EB.gate_brief_problems(pillow))
    finally:
        EB.GATE_BRIEFS[pillow.key] = saved


def test_demand_is_cited_never_invented():
    from datetime import date

    r = EB.gate_candidates(today=date(2026, 10, 7))
    rows = r["candidates"]
    assert rows
    for key, row in rows.items():
        for f in row["demand"]:  # vacuity-ok: a candidate with no finding has none
            assert f["grade"] in ("observed", "proxy") and len(f["digest"]) == 10, key
    # A candidate with no matching finding carries none: unmeasured, not zero.
    assert rows["teacher-chevron-pencil-roll"]["demand"] == []
    assert r["engineering_queue"][0] == "first-christmas-stocking"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
