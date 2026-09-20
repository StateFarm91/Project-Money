"""Every number a buyer sees, traced to the one object that knows it.

Requirement 60, whose own example is the whole module: a finished-size card showing 90x122 cm
alongside an unexplained 180 cm marker. The marker is not necessarily *wrong* -- it may be
true of something -- it is unreadable, and unreadable is worse than wrong because nobody can
disagree with it.

The test that matters most is the contradiction one. Two numbers that disagree about the same
axis of the same component are invisible to any check that validates measurements one at a
time, and one at a time is how measurements are usually checked.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.publish import dimensions as D  # noqa: E402


def _canon(**kw) -> D.Canonical:
    args = dict(key="blanket-w", axis=D.WIDTH, component="blanket", value_cm=90.0,
                blocked=D.BLOCKED)
    args.update(kw)
    return D.Canonical(**args)


def _shown(**kw) -> D.Displayed:
    args = dict(where="size card", value_cm=90.0, traces_to="blanket-w",
                axis=D.WIDTH, component="blanket", blocked=D.BLOCKED)
    args.update(kw)
    return D.Displayed(**args)


# ---- a number with no source ----------------------------------------------


def test_the_unexplained_marker_is_caught_by_name():
    out = D.audit([_shown(), D.Displayed(where="marker", value_cm=180.0,
                                         traces_to="nothing-canonical")], [_canon()])
    kinds = [p["kind"] for p in out["problems"]]
    assert "untraceable" in kinds
    assert any("impossible to disagree with" in p["why"] for p in out["problems"])


def test_a_displayed_measurement_must_name_its_source():
    try:
        D.Displayed(where="card", value_cm=90.0, traces_to="  ")
    except D.DimensionRefused as e:
        assert "indistinguishable from a correct one" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a number with no source was accepted")


def test_a_traced_number_that_does_not_match_its_source_is_a_different_number():
    out = D.audit([_shown(value_cm=95.0)], [_canon()])
    kinds = [p["kind"] for p in out["problems"]]
    assert "does_not_match_source" in kinds
    assert any("Gauge variation is the truth gate's business" in p["why"]
               for p in out["problems"])


def test_rounding_inside_the_transcription_tolerance_is_fine():
    out = D.audit([_shown(value_cm=90.0 + D.TRACE_TOLERANCE_CM / 2)], [_canon()])
    assert out["ok"] is True


# ---- a number with no context ---------------------------------------------


def test_a_number_with_no_axis_is_unreadable_rather_than_wrong():
    canonical = D.Canonical(key="k", axis=D.WIDTH, component="blanket", value_cm=90.0,
                            blocked=D.BLOCKED)
    shown = D.Displayed(where="card", value_cm=90.0, traces_to="k")
    # The source supplies the context when the display does not, which is the working case.
    assert D.audit([shown], [canonical])["ok"] is True


def test_context_missing_from_both_display_and_source_is_reported():
    # A canonical measurement always has an axis and component by construction, so the
    # contextless case is a display tracing to nothing -- which is the marker, again.
    out = D.audit([D.Displayed(where="marker", value_cm=180.0, traces_to="ghost")],
                  [_canon()])
    assert out["ok"] is False


def test_a_size_variant_is_required_only_where_the_product_has_variants():
    canonical = _canon(size_variant="")
    shown = _shown()
    assert D.audit([shown], [canonical], has_variants=False)["ok"] is True
    out = D.audit([shown], [canonical], has_variants=True)
    assert any(p["kind"] == "contextless" for p in out["problems"])


def test_an_axis_the_vocabulary_does_not_have_is_refused():
    try:
        _canon(axis="longways")
    except D.DimensionRefused as e:
        assert "is not an axis" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an invented axis was accepted")


def test_a_canonical_measurement_names_its_component():
    try:
        _canon(component="  ")
    except D.DimensionRefused as e:
        assert "name the component" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a measurement of nothing in particular was accepted")


# ---- blocked state --------------------------------------------------------


def test_blocked_state_is_required_because_the_difference_is_material():
    try:
        _canon(blocked="maybe")
    except D.DimensionRefused as e:
        assert "ambiguous rather than approximate" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an unstated blocked state was accepted")


def test_a_card_and_the_geometry_describing_different_states_is_a_problem():
    out = D.audit([_shown(blocked=D.UNBLOCKED)], [_canon(blocked=D.BLOCKED)])
    kinds = [p["kind"] for p in out["problems"]]
    assert "blocked_state_disagrees" in kinds


# ---- the contradiction nobody finds one at a time -------------------------


def test_two_numbers_disagreeing_about_the_same_thing_is_the_headline_defect():
    canonical = [_canon(key="a", value_cm=90.0), _canon(key="b", value_cm=122.0,
                                                        axis=D.LENGTH)]
    displayed = [
        D.Displayed(where="card", value_cm=90.0, traces_to="a", axis=D.WIDTH,
                    component="blanket", blocked=D.BLOCKED),
        D.Displayed(where="hero overlay", value_cm=95.0, traces_to="a", axis=D.WIDTH,
                    component="blanket", blocked=D.BLOCKED),
    ]
    out = D.audit(displayed, canonical)
    contradictions = [p for p in out["problems"] if p["kind"] == "contradiction"]
    assert contradictions
    assert "one at a time is how they are usually checked" in contradictions[0]["why"]
    assert sorted(contradictions[0]["values"]) == [90.0, 95.0]


def test_the_same_number_in_two_places_is_not_a_contradiction():
    displayed = [_shown(where="card"), _shown(where="hero overlay")]
    out = D.audit(displayed, [_canon()])
    assert not [p for p in out["problems"] if p["kind"] == "contradiction"]


def test_the_canonical_object_contradicting_itself_is_reported_first():
    out = D.audit([], [_canon(key="a", value_cm=90.0), _canon(key="b", value_cm=95.0)])
    kinds = [p["kind"] for p in out["problems"]]
    assert "canonical_contradiction" in kinds
    assert any("everything downstream of this is arbitrary" in p["why"].lower()
               for p in out["problems"])


def test_different_axes_of_one_component_are_not_a_contradiction():
    canonical = [_canon(key="w", axis=D.WIDTH, value_cm=90.0),
                 _canon(key="l", axis=D.LENGTH, value_cm=122.0)]
    displayed = [
        D.Displayed(where="card", value_cm=90.0, traces_to="w", axis=D.WIDTH,
                    component="blanket", blocked=D.BLOCKED),
        D.Displayed(where="card", value_cm=122.0, traces_to="l", axis=D.LENGTH,
                    component="blanket", blocked=D.BLOCKED),
    ]
    assert D.audit(displayed, canonical)["ok"] is True


# ---- labels ---------------------------------------------------------------


def test_the_label_is_generated_so_nobody_writes_it_differently_twice():
    label = D.labels_for(_canon(), has_variants=False)
    assert "blanket width" in label and D.BLOCKED in label


def test_state_names_the_check_the_module_exists_for():
    out = D.state()
    assert out["requirement"] == 60
    assert "one at a time" in out["note"]
    assert "cir.geometry" in out["canonical_source"]


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
