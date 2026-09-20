"""Visual defects as named classes, and the recurrence that means the fixture is wrong.

Requirement 68. `gates.regression` already does this for the compiler. Visual defects never
got the same treatment, and the reason is worth naming: a compiler defect is a wrong number
and a layout defect is a look, so it feels like taste, and taste does not get a fixture. But
`publish.layout_qa` measures rendered pixels, which means these are reproducible, and
anything reproducible can be fixtured.

The distinction the module exists for: a recurrence after a fixture is a bug in the *fixture*,
not a second bug in the renderer.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.publish import defects as D  # noqa: E402


def _defect(**kw) -> D.VisualDefect:
    args = dict(defect_class=D.CLIPPING, product_slug="autumn-throw",
                reproduces_with="frames/autumn-throw-3.png", found_on="2026-09-20")
    args.update(kw)
    return D.VisualDefect(**args)


# ---- the taxonomy ---------------------------------------------------------


def test_every_class_the_requirement_names_exists():
    for name in ("clipping", "confusing_dimensions", "misleading_visualisation",
                 "weak_hero", "unreadable_chart", "redundant_frames"):
        assert name in D.CLASSES
    assert len(D.CLASSES) == 6


def test_every_class_names_the_checker_that_finds_it():
    assert set(D.DETECTED_BY) == set(D.CLASSES)
    for name, detector in D.DETECTED_BY.items():
        assert "publish." in detector or "gates." in detector, name


def test_a_class_the_taxonomy_does_not_have_is_refused():
    try:
        _defect(defect_class="looks_a_bit_off")
    except D.DefectRefused as e:
        assert "whether anything improved" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the taxonomy grew a class")


# ---- a defect nobody can reproduce ----------------------------------------


def test_a_defect_with_no_reproduction_is_a_memory():
    try:
        _defect(reproduces_with="   ")
    except D.DefectRefused as e:
        assert "memories do not prevent anything" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an irreproducible defect was recorded as one")


def test_a_reproducible_defect_carries_what_reproduces_it():
    out = _defect().to_dict()
    assert out["reproduces_with"].endswith(".png")
    assert out["detected_by"] == D.DETECTED_BY[D.CLIPPING]


# ---- the recurrence rule --------------------------------------------------


def test_a_first_occurrence_asks_for_a_fixture():
    out = D.classify(_defect(), fixtured_classes=set())
    assert out["kind"] == D.FIRST
    assert "capture a regression fixture" in out["action"]


def test_a_recurrence_after_a_fixture_is_a_bug_in_the_fixture():
    out = D.classify(_defect(), fixtured_classes={D.CLIPPING})
    assert out["kind"] == D.RECURRENCE
    assert "bug in the fixture" in out["why"]
    assert "widen the existing fixture" in out["action"]


def test_the_two_are_different_findings_not_the_same_one_twice():
    first = D.classify(_defect(), fixtured_classes=set())
    again = D.classify(_defect(), fixtured_classes={D.CLIPPING})
    assert first["kind"] != again["kind"]
    assert first["action"] != again["action"]


# ---- coverage -------------------------------------------------------------


def test_a_class_with_a_detector_and_no_fixture_is_named():
    out = D.coverage({D.CLIPPING})
    assert out["fixtured"] == 1
    assert len(out["uncovered"]) == 5
    assert "only the second is what 'improve monotonically' means" in out["why"]


def test_full_coverage_says_so():
    out = D.coverage(set(D.CLASSES))
    assert out["uncovered"] == []
    assert "every named class has a fixture" in out["why"]


def test_coverage_refuses_a_class_that_does_not_exist():
    try:
        D.coverage({"vibes"})
    except D.DefectRefused as e:
        assert "are not defect classes" in str(e)
    else:  # pragma: no cover
        raise AssertionError("coverage counted an invented class")


# ---- monotonic is a claim about a count not going down --------------------


def test_monotonic_needs_more_than_one_reading():
    out = D.monotonic([{"at": "a", "fixtured": [D.CLIPPING]}])
    assert out["readable"] is False
    assert "one point is not one" in out["why"]


def test_a_growing_fixture_set_is_monotonic():
    out = D.monotonic([{"at": "a", "fixtured": [D.CLIPPING]},
                       {"at": "b", "fixtured": [D.CLIPPING, D.WEAK_HERO]}])
    assert out["monotonic"] is True
    assert out["fixtured_now"] == sorted([D.CLIPPING, D.WEAK_HERO])


def test_a_fixture_that_stops_running_is_a_regression_nothing_announces():
    out = D.monotonic([{"at": "a", "fixtured": [D.CLIPPING, D.WEAK_HERO]},
                       {"at": "b", "fixtured": [D.CLIPPING]}])
    assert out["monotonic"] is False
    assert out["regressions"][0]["lost"] == [D.WEAK_HERO]
    assert "free to return, and nothing announces it" in out["why"]


def test_monotonic_is_about_fixtures_rather_than_defect_counts():
    """Production finds what production finds; the checkable claim is narrower."""
    out = D.state()
    assert "recurrence_rule" in out
    assert "reproducible can be fixtured" in out["note"]


def test_state_names_why_these_never_got_fixtures_before():
    out = D.state()
    assert out["requirement"] == 68
    assert "it feels like taste" in out["note"]


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
