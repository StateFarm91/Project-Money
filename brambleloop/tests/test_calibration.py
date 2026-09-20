"""Forecast against outcome, and the four ways a calibration flatters the model.

Requirement 262. Write the forecast down after the fact and the model is always calibrated
and never right. Decompose a product with a waterfall and whoever chooses the order chooses
the culprit. Penalise optimism and pessimism equally and a year of over-forecasting is erased
by one good month. Score the periods where the shop was not selling and a model nobody
applied reports as catastrophically optimistic.
"""
from __future__ import annotations

import math
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.scale import calibration as C  # noqa: E402
from brambleloop.scale import confidence  # noqa: E402


def _period(n: int, **kw) -> C.Period:
    args = dict(label=f"2026-M{n:02d}", starts_on=date(2026, n, 1), ends_on=date(2026, n, 28))
    args.update(kw)
    return C.Period(**args)


# Terms that multiply to 1000.0 exactly: 20000 * 0.02 * 0.025 * 80 * 1.25 * 1.0 * 1.0
BASE_TERMS = {"qualified_traffic": 20000.0, "ctr": 0.02, "conversion": 0.025,
              "aov_cad": 80.0, "repeat_factor": 1.25, "launch_timing": 1.0,
              "winner_rate_factor": 1.0}


def _forecast(n: int, revenue: float = 1000.0, terms=None, **kw) -> C.Forecast:
    p = kw.pop("period", None) or _period(n)
    args = dict(period=p, made_on=date(2026, n, 1).replace(day=1),
                revenue_cad=revenue, terms=dict(terms if terms is not None else BASE_TERMS))
    args["made_on"] = date(2025, 12, 1)
    args.update(kw)
    return C.Forecast(**args)


def _actual(n: int, revenue: float, terms=None, listings: int = 12, **kw) -> C.Actual:
    p = kw.pop("period", None) or _period(n)
    return C.Actual(period=p, revenue_cad=revenue,
                    terms=dict(terms) if terms else {}, live_listings=listings)


# ---- a forecast is what was written down first ----------------------------


def test_a_forecast_dated_inside_its_own_period_is_refused():
    p = _period(3)
    try:
        C.Forecast(period=p, made_on=date(2026, 3, 15), revenue_cad=1000.0)
    except C.CalibrationRefused as e:
        assert "always well calibrated and never right" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a forecast written during its period was accepted")


def test_a_forecast_dated_after_the_period_is_refused_too():
    p = _period(3)
    try:
        C.Forecast(period=p, made_on=date(2026, 6, 1), revenue_cad=1000.0)
    except C.CalibrationRefused:
        pass
    else:  # pragma: no cover
        raise AssertionError("a hindsight forecast was accepted")


def test_a_forecast_made_the_day_before_is_fine():
    C.Forecast(period=_period(3), made_on=date(2026, 2, 28), revenue_cad=1000.0)


# ---- a period nobody sold in -----------------------------------------------


def test_an_unexposed_period_is_excluded_not_scored():
    """Every period today is this one, and scoring them would crater a model nobody ran."""
    out = C.compare(_forecast(3), _actual(3, 0.0, listings=0))
    assert out["verdict"] == C.NOT_EXPOSED
    assert out["scored"] is False
    assert "unopened shop" in out["why"]


def test_a_history_of_unexposed_periods_caps_nothing():
    pairs = [(_forecast(n), _actual(n, 0.0, listings=0)) for n in (1, 2, 3, 4)]
    cap = C.ceiling(pairs, prior=0.8)
    assert cap["applied"] is False and cap["ceiling"] == 0.8
    assert cap["scored"] == 0


def test_the_same_zero_with_listings_up_is_a_real_miss():
    out = C.compare(_forecast(3), _actual(3, 0.0, listings=12))
    assert out["verdict"] == C.OPTIMISTIC and out["scored"] is True


# ---- direction and magnitude ----------------------------------------------


def test_a_small_miss_in_either_direction_is_accurate():
    assert C.compare(_forecast(3), _actual(3, 1100.0))["verdict"] == C.ACCURATE
    assert C.compare(_forecast(3), _actual(3, 900.0))["verdict"] == C.ACCURATE


def test_optimistic_and_pessimistic_are_named_not_averaged_away():
    over = C.compare(_forecast(3), _actual(3, 400.0))
    under = C.compare(_forecast(3), _actual(3, 1600.0))
    assert over["verdict"] == C.OPTIMISTIC and over["signed_error"] < 0
    assert under["verdict"] == C.PESSIMISTIC and under["signed_error"] > 0


def test_comparing_two_different_periods_is_refused():
    try:
        C.compare(_forecast(3), _actual(4, 900.0))
    except C.CalibrationRefused as e:
        assert "comparing" in str(e)
    else:  # pragma: no cover
        raise AssertionError("mismatched periods were compared")


# ---- the decomposition ----------------------------------------------------


def test_the_contributions_sum_exactly_to_the_total_error():
    actual_terms = dict(BASE_TERMS, conversion=0.020, ctr=0.018)
    revenue = 1.0
    for v in actual_terms.values():
        revenue *= v
    out = C.decompose(_forecast(3), _actual(3, revenue, actual_terms))
    assert out["exact"] is True
    # 1e-5 rather than 0 because the reported figures are rounded to six places for the
    # payload; the arithmetic itself is exact, which is the point of doing it in logs.
    assert abs(sum(out["contributions"].values()) - out["log_total"]) < 1e-5
    assert abs(out["unexplained"]) < 1e-5


def test_the_decomposition_does_not_depend_on_the_order_of_the_terms():
    """A waterfall would; log space cannot, which is why it is log space."""
    actual_terms = dict(BASE_TERMS, conversion=0.020, aov_cad=70.0)
    revenue = 1.0
    for v in actual_terms.values():
        revenue *= v
    forward = C.decompose(_forecast(3), _actual(3, revenue, actual_terms))
    reversed_terms = dict(reversed(list(actual_terms.items())))
    backward = C.decompose(_forecast(3, terms=dict(reversed(list(BASE_TERMS.items())))),
                           _actual(3, revenue, reversed_terms))
    assert forward["contributions"] == backward["contributions"]


def test_an_unmeasured_term_lands_in_unexplained_rather_than_on_conversion():
    partial = {k: v for k, v in BASE_TERMS.items() if k != "winner_rate_factor"}
    partial["conversion"] = 0.020
    revenue = 1.0
    for v in BASE_TERMS.values():
        revenue *= v
    revenue *= (0.020 / 0.025) * 0.5     # a real winner-rate shortfall nobody measured
    out = C.decompose(_forecast(3), _actual(3, revenue, partial))
    assert out["exact"] is False
    assert out["unmeasured_terms"] == ["winner_rate_factor"]
    assert abs(out["unexplained"]) > 0.1
    assert abs(sum(out["contributions"].values()) + out["unexplained"]
               - out["log_total"]) < 1e-5


def test_terms_that_do_not_reconstruct_the_revenue_are_refused():
    try:
        C.decompose(_forecast(3, revenue=5000.0), _actual(3, 900.0, BASE_TERMS))
    except C.CalibrationRefused as e:
        assert "bookkeeping disagreement" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a decomposition of a total its terms do not make was allowed")


def test_every_term_the_requirement_names_is_present():
    for name in ("qualified_traffic", "ctr", "conversion", "aov_cad", "repeat_factor",
                 "launch_timing", "winner_rate_factor"):
        assert name in C.TERMS


def test_a_zero_or_negative_term_is_refused():
    try:
        C.Forecast(period=_period(3), made_on=date(2025, 12, 1), revenue_cad=1000.0,
                   terms=dict(BASE_TERMS, ctr=0.0))
    except C.CalibrationRefused as e:
        assert "multiplicative factor" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a zero factor was accepted")


# ---- the history ----------------------------------------------------------


def test_one_comparison_is_not_a_calibration():
    out = C.calibrate([(_forecast(3), _actual(3, 400.0))])
    assert out["calibrated"] is False and "anecdote" in out["why"]


def test_term_bias_reports_direction_and_unmeasured_is_not_unbiased():
    pairs = [(_forecast(n), _actual(n, 500.0, dict(BASE_TERMS, conversion=0.0125)))
             for n in (1, 2, 3, 4)]
    out = C.calibrate(pairs)
    assert out["calibrated"] is True
    assert out["term_bias"]["conversion"]["reading"] == "forecast too high"
    assert out["term_bias"]["ctr"]["reading"] == "no consistent direction"


def test_unmeasured_terms_say_so_rather_than_reading_as_unbiased():
    pairs = [(_forecast(n), _actual(n, 500.0)) for n in (1, 2, 3, 4)]
    out = C.calibrate(pairs)
    assert out["term_bias"]["conversion"]["bias"] is None
    assert "not the same as unbiased" in out["term_bias"]["conversion"]["reading"]


# ---- the asymmetric, automatic, ratcheting penalty -------------------------


def test_optimism_costs_more_than_pessimism_of_the_same_size():
    over = C.ceiling([(_forecast(n), _actual(n, 500.0)) for n in (1, 2, 3, 4)], prior=1.0)
    under = C.ceiling([(_forecast(n), _actual(n, 1500.0)) for n in (1, 2, 3, 4)], prior=1.0)
    assert over["ceiling"] < under["ceiling"]
    assert under["ceiling"] > 0.8 and over["ceiling"] < 0.4


def test_the_penalty_applies_without_anybody_agreeing_to_it():
    """There is no argument `ceiling` accepts that raises it."""
    cap = C.ceiling([(_forecast(n), _actual(n, 300.0)) for n in (1, 2, 3, 4)], prior=1.0)
    assert cap["applied"] is True and cap["ceiling"] < 0.3


def test_one_good_month_does_not_erase_a_year_of_optimism():
    history = [(_forecast(n), _actual(n, 400.0)) for n in (1, 2, 3, 4, 5, 6)]
    after_one = C.ceiling(history + [(_forecast(7), _actual(7, 1000.0))], prior=1.0)
    only_optimistic = C.ceiling(history, prior=1.0)
    assert after_one["accurate_run"] == 1
    assert after_one["recovery_steps"] == 0
    assert after_one["ceiling"] == only_optimistic["ceiling"]


def test_recovery_needs_a_run_and_arrives_one_step_at_a_time():
    history = [(_forecast(n), _actual(n, 400.0)) for n in (1, 2, 3)]
    run3 = C.ceiling(history + [(_forecast(n), _actual(n, 1000.0)) for n in (4, 5, 6)],
                     prior=1.0)
    run4 = C.ceiling(history + [(_forecast(n), _actual(n, 1000.0)) for n in (4, 5, 6, 7)],
                     prior=1.0)
    assert run3["recovery_steps"] == 1
    assert run4["recovery_steps"] == 2
    assert run4["ceiling"] > run3["ceiling"]


def test_the_ceiling_can_never_exceed_the_prior():
    cap = C.ceiling([(_forecast(n), _actual(n, 1000.0)) for n in (1, 2, 3, 4, 5, 6)],
                    prior=0.4)
    assert cap["ceiling"] <= 0.4


def test_the_ceiling_has_a_floor_rather_than_reaching_zero():
    cap = C.ceiling([(_forecast(n), _actual(n, 1.0)) for n in range(1, 13)], prior=1.0)
    assert cap["ceiling"] == C.CEILING_FLOOR


def test_this_module_produces_a_ceiling_and_never_a_probability():
    cap = C.ceiling([(_forecast(n), _actual(n, 400.0)) for n in (1, 2, 3, 4)], prior=1.0)
    assert "probability" not in cap
    assert "scale.confidence computes the number" in cap["note"]
    assert C.state()["owns"] == "a ceiling on confidence, never a probability"


def test_the_ceiling_binds_the_one_confidence_number_and_only_downward():
    """The integration, checked rather than described: #262 caps #274, never lifts it."""
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/calibration.sqlite")
    db.create_all()
    baseline = confidence.probability(db)["probability"]
    lifted = confidence.probability(db, calibration_ceiling=0.99)
    lowered = confidence.probability(db, calibration_ceiling=0.0)
    assert lifted["probability"] == baseline, "a ceiling raised the number"
    assert lowered["probability"] <= baseline
    if lowered["probability"] < baseline:
        assert "#262" in lowered["capped_by"]


def test_state_says_what_today_actually_looks_like():
    out = C.state()
    assert "nothing is published" in out["today"]
    assert any("no live listings" in r for r in out["refuses"])


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
