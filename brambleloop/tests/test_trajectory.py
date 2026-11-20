"""#26: a trajectory made of assumptions, labelled as one.

The requirement's last sentence governs the module -- do not present modeled probabilities
as objective truth -- and it is not a disclaimer to append. A Monte Carlo over unmeasured
inputs produces a distribution of assumptions to four decimal places with a histogram, which
is exactly what makes it persuasive.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.scale import trajectory as T  # noqa: E402

ON = date(2026, 9, 20)


def _inputs(observed=()):
    base = {
        "listing_count": (16, 16, 16),
        "qualified_traffic": (4000, 1000, 12000),
        "ctr": (0.02, 0.005, 0.05),
        "conversion": (0.02, 0.005, 0.05),
        "aov_cad": (12, 6, 25),
        "repeat_rate": (0.1, 0.0, 0.4),
        "organic_growth": (0.05, -0.05, 0.2),
        "paid_cac_cad": (5, 2, 15),
        "product_velocity": (4, 1, 8),
        "winner_rate": (0.1, 0.0, 0.3),
        "retirement_rate": (0.02, 0.0, 0.1),
    }
    return {k: T.Value(p, lo, hi, T.OBSERVED if k in observed else "a guess, written down")
            for k, (p, lo, hi) in base.items()}


# --- no bare probabilities ----------------------------------------------------------------

def test_an_unmeasured_model_states_no_probability_at_all():
    out = T.run(_inputs(), on=ON)
    assert out["kind"] == "assumption_space"
    assert out["probability"] is None
    assert "not a forecast" in out["what_this_is"]


def test_a_measured_model_reports_its_probability_inside_its_provenance():
    every = tuple(T.TERMS)
    out = T.run(_inputs(observed=every), on=ON)
    assert out["kind"] == "forecast"
    p = out["probability"]
    assert 0.0 <= p["of_reaching_target"] <= 1.0
    assert p["assumed_terms"] == []
    assert "never of the world" in p["not_objective"]


def test_the_probability_is_never_returned_as_a_bare_number():
    """A number detaches from its caveat the moment somebody writes it in a summary."""
    out = T.run(_inputs(observed=tuple(T.TERMS)), on=ON)
    assert isinstance(out["probability"], dict)
    assert {"observed_share", "assumed_terms", "not_objective"} <= set(out["probability"])


def test_the_floor_is_a_share_of_the_model_rather_than_a_feeling():
    partly = tuple(list(T.TERMS)[:6])       # 6 of 11 is 54%, below the floor
    out = T.run(_inputs(observed=partly), on=ON)
    assert out["observed_share"] < T.MIN_OBSERVED_SHARE
    assert out["kind"] == "assumption_space"
    mostly = tuple(list(T.TERMS)[:7])       # 7 of 11 is 63%
    assert T.run(_inputs(observed=mostly), on=ON)["kind"] == "forecast"


# --- sensitivity is the real output today ---------------------------------------------------

def test_sensitivity_ranks_what_the_answer_is_hostage_to():
    rows = T.sensitivity(_inputs())
    assert rows[0]["rank"] == 1
    assert rows[0]["spread_cad"] >= rows[-1]["spread_cad"]
    assert {r["term"] for r in rows} == set(T.TERMS)


def test_a_compounding_term_dominates_a_one_off_one():
    """Growth compounds over twelve months; a fixed listing count does not. If the ranking
    said otherwise the model would be wrong rather than the ranking."""
    rows = {r["term"]: r["spread_cad"] for r in T.sensitivity(_inputs())}
    assert rows["organic_growth"] > rows["aov_cad"]
    assert rows["listing_count"] == 0.0   # pinned to one value in this fixture


def test_the_run_carries_its_sensitivity_with_it():
    out = T.run(_inputs(), on=ON)
    assert out["sensitivity"][0]["term"] in T.TERMS
    assert "hostage" in T.sensitivity.__doc__


# --- determinism ------------------------------------------------------------------------------

def test_two_reads_of_the_same_night_agree():
    """The first thing anybody does with a nightly number is compare it to last night's."""
    a = T.run(_inputs(), on=ON)
    b = T.run(_inputs(), on=ON)
    assert a["monthly_revenue_cad"] == b["monthly_revenue_cad"]


def test_a_different_night_is_a_different_draw():
    a = T.run(_inputs(), on=ON)
    b = T.run(_inputs(), on=date(2026, 9, 21))
    assert a["monthly_revenue_cad"] != b["monthly_revenue_cad"]


# --- the inputs -------------------------------------------------------------------------------

def test_a_term_left_out_is_refused_rather_than_assumed_silently():
    inputs = _inputs()
    del inputs["winner_rate"]
    try:
        T.run(inputs, on=ON)
    except T.TrajectoryRefused as exc:
        assert "assumed silently" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a missing term was modelled anyway")


def test_a_term_nobody_named_cannot_join_the_model():
    inputs = _inputs()
    inputs["vibes"] = T.Value(1, 0, 2, "a guess")
    try:
        T.run(inputs, on=ON)
    except T.TrajectoryRefused as exc:
        assert "are not terms" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented term joined the model")


def test_a_point_outside_its_own_range_is_a_typo_that_answers_confidently():
    try:
        T.Value(5, 1, 3, "a guess")
    except T.TrajectoryRefused as exc:
        assert "not a range" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an impossible range was accepted")


def test_a_value_with_no_source_cannot_be_told_from_a_measurement():
    try:
        T.Value(1, 0, 2, "  ")
    except T.TrajectoryRefused as exc:
        assert "whole distinction this module exists to keep" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a sourceless value was accepted")


# --- the nightly cadence's honest output today --------------------------------------------------

def test_the_nightly_run_refuses_and_names_the_constraint_anyway():
    """"Nobody is arriving" does not need a simulation, and it is the half of this
    requirement that can be answered with no data at all."""
    out = T.nightly(None, on=ON)
    assert out["ran"] is False
    assert out["observed_share"] == 0.0
    assert out["primary_constraint"]["identifiable"] is False
    assert sorted(out["terms_needed"]) == sorted(T.TERMS)


def test_state_says_what_the_module_refuses_to_say():
    out = T.state()
    assert out["observed_share_floor"] == T.MIN_OBSERVED_SHARE
    assert "bare probability" in out["never"]
    assert len(out["terms"]) == 11


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
