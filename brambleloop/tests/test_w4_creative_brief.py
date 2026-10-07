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


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
