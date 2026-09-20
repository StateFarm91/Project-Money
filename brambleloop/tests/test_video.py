"""#248: video modules with one canonical source, and the clip that outlives its pattern.

The instruction with weight in this requirement is "keeping a canonical tutorial", and the
reason is not tidiness. A pattern is corrected, the written instructions are reissued, and
the troubleshooting clip goes on telling people to do the thing that was wrong -- which is
worse than no clip, because it is trusted and it is specific.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.growth import video as V  # noqa: E402
from brambleloop.growth.clusters import QUESTIONS  # noqa: E402
from brambleloop.ops import artefacts as A  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


# --- the canonical tutorial ------------------------------------------------------------------

def test_a_clip_with_no_canonical_source_is_refused():
    out = V.check(V.Module("winter-throw", "reveal", "shorts"))
    assert out["ok"] is False
    assert any("diverge silently" in r for r in out["reasons"])


def test_the_canonical_module_is_the_one_that_needs_no_source():
    out = V.check(V.Module("winter-throw", V.CANONICAL, "youtube"))
    assert out["ok"] is True


def test_a_clip_goes_stale_when_the_design_it_was_cut_from_moves():
    """The same table and the same sentinel as the PDF and the chart: a clip that outlives
    its pattern should be found by the sweep that already runs, not by somebody remembering
    that videos exist."""
    db = _db()
    module = V.Module("winter-throw", "reveal", "shorts", canonical_ref="tut-1")
    with db.session() as s:
        out = V.record(s, module, design_fingerprint=A.fingerprint({"rows": 12}),
                       canonical_fingerprint=A.fingerprint("tut"))
    assert out["artefact_key"] == "video:winter-throw:reveal:shorts"
    assert out["artefact_class"] == "marketing_asset"

    with db.session() as s:
        verdicts = A.check(s, current={"cir:winter-throw": A.fingerprint({"rows": 14}),
                                       "asset:tut-1": A.fingerprint("tut")})
    assert [v.state for v in verdicts] == [A.STALE]
    assert verdicts[0].moved == ("cir:winter-throw",)


# --- repurposing appropriately -----------------------------------------------------------------

def test_a_twelve_minute_explanation_is_not_a_short():
    out = V.check(V.Module("winter-throw", "technique", "shorts"))
    assert out["ok"] is False
    assert any("trailer for nothing" in r for r in out["reasons"])


def test_a_reveal_is_what_a_short_is_actually_for():
    out = V.check(V.Module("winter-throw", "reveal", "shorts", canonical_ref="tut-1"))
    assert out["ok"] is True
    assert out["native_seconds"] == [15, 45]


def test_every_module_names_its_shape_and_where_that_shape_fits():
    for kind, spec in V.MODULES.items():
        low, high = spec["native_seconds"]
        assert 0 < low < high, kind
        assert spec["platforms"], kind
        assert all(p in V.PLATFORMS for p in spec["platforms"]), kind
        assert len(spec["why"].split()) >= 6, kind


def test_a_module_or_platform_nobody_named_is_refused():
    for bad in (("vlog", "youtube"), ("reveal", "tiktok")):
        try:
            V.Module("winter-throw", *bad)
        except V.VideoRefused as exc:
            assert "is not a" in str(exc)
        else:  # pragma: no cover
            raise AssertionError(f"{bad} was accepted")


# --- troubleshooting comes from what was reported -------------------------------------------------

def test_a_troubleshooting_clip_needs_a_problem_makers_actually_had():
    out = V.check(V.Module("winter-throw", "troubleshooting", "youtube",
                           canonical_ref="tut-1", covers="how_to_crochet_a_yacht"))
    assert any("a problem that does not exist" in r for r in out["reasons"])


def test_the_problems_are_the_search_clusters_own():
    assert set(QUESTIONS) >= {"counts_wrong", "sizing_wrong", "yarn_estimate_wrong"}
    out = V.check(V.Module("winter-throw", "troubleshooting", "youtube",
                           canonical_ref="tut-1", covers="counts_wrong"))
    assert out["ok"] is True


def test_a_troubleshooting_clip_must_say_what_it_covers():
    out = V.check(V.Module("winter-throw", "troubleshooting", "youtube",
                           canonical_ref="tut-1"))
    assert any("name the problem it covers" in r for r in out["reasons"])


# --- the plan --------------------------------------------------------------------------------------

def test_the_plan_only_answers_problems_that_recur():
    out = V.plan("winter-throw", canonical_ref="tut-1",
                 reported={"counts_wrong": 7, "support_slow": 1})
    assert out["troubleshooting_for"] == ["counts_wrong"]
    assert all(m["ok"] for m in out["modules"])


def test_nothing_reported_often_enough_is_a_finding_about_the_observation():
    out = V.plan("winter-throw", canonical_ref="tut-1", reported={"counts_wrong": 1})
    assert out["troubleshooting_for"] == []
    assert "about the observation rather than about the product" in out["note"]


def test_a_reported_problem_with_no_question_behind_it_is_refused():
    try:
        V.plan("winter-throw", canonical_ref="tut-1", reported={"vibes": 9})
    except V.VideoRefused as exc:
        assert "are not reported problems" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented problem was planned for")


def test_every_planned_module_is_on_a_platform_its_shape_fits():
    out = V.plan("winter-throw", canonical_ref="tut-1", reported={"counts_wrong": 7})
    for module in out["modules"]:
        assert module["platform"] in V.MODULES[module["kind"]]["platforms"]


# --- what cannot be measured ---------------------------------------------------------------------------

def test_neither_measure_can_be_taken_yet():
    out = V.measurement()
    assert out["measurable"] is False
    assert set(out["measures"]) == {"assisted_conversion", "support_reduction"}
    assert "there are no orders and no cases" in out["why"]


def test_state_says_a_module_is_a_plan_rather_than_a_file():
    out = V.state()
    assert "no video capability" in out["cannot_do_yet"]
    assert "ops.artefacts" in out["recorded_as"]
    assert "worse than no clip" in out["note"]


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
