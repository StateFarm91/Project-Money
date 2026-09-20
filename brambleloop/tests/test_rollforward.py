"""Two capacities, two clocks, and the weeks a single clock throws away.

Requirement 267. The lane-retirement half of this requirement is `seasonal.compression` and
was built with #283-#285; what is tested here is the word *and* in "product and marketing
capacity". Engineering leaves an occasion when its last lane closes. Marketing leaves weeks
later, at the buyer's own last practical make date, and those weeks are the ones that earn
most -- a maker buying a quick gift pattern on the 10th of December is the most motivated
buyer of the year.

The refusals go both ways, which is the part worth testing: leaving early abandons that
window, and arriving late at the next occasion is the same mistake with a different date.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.seasonal import rollforward as A  # noqa: E402
from brambleloop.seasonal.compression import LAUNCH, MERCHANDISE, POST_OCCASION  # noqa: E402


def _standing(name: str, *, days: int, mode: str, lanes=()) -> A.Standing:
    return A.Standing(event=name, event_date=date(2026, 9, 20) + timedelta(days=days),
                      days_away=days, mode=mode, open_lanes=tuple(lanes))


# ---- the two clocks -------------------------------------------------------


def test_engineering_leaves_before_marketing_does():
    """The whole module, in one assertion."""
    merchandising = _standing("Christmas", days=25, mode=MERCHANDISE)
    assert merchandising.holds_engineering is False
    assert merchandising.holds_marketing is True


def test_an_occasion_holds_both_while_a_lane_is_open():
    launching = _standing("Christmas", days=96, mode=LAUNCH, lanes=("QUICK", "SHORT"))
    assert launching.holds_engineering and launching.holds_marketing


def test_an_occasion_past_the_last_make_date_holds_neither():
    done = _standing("Christmas", days=5, mode=POST_OCCASION)
    assert not done.holds_engineering and not done.holds_marketing


def test_the_ledger_names_the_gap_between_the_clocks():
    out = A.ledger(date(2026, 9, 20))
    assert set(out["marketing_only"]) == set(out[A.MARKETING]) - set(out[A.ENGINEERING])
    assert "earn most" in out["note"]


def test_the_real_calendar_today_has_an_occasion_in_the_gap():
    """Thanksgiving is 22 days out: unlaunchable, and still very much buyable."""
    out = A.ledger(date(2026, 9, 20))
    assert out["marketing_only"], out["events"]
    for name in out["marketing_only"]:
        assert name in out[A.MARKETING] and name not in out[A.ENGINEERING]


# ---- leaving too early ----------------------------------------------------


def test_nothing_leaves_an_occasion_that_still_holds_it():
    source = _standing("Christmas", days=96, mode=LAUNCH, lanes=("QUICK", "LONG"))
    target = _standing("Valentine's", days=147, mode=LAUNCH, lanes=("FLAGSHIP",))
    for capacity in A.CAPACITIES:
        out = A.may_roll_forward(source, target, capacity=capacity)
        assert out["may_roll"] is False
        assert "earn most" in out["why"]


def test_marketing_may_not_leave_while_the_buyer_can_still_finish():
    """Engineering has already gone; marketing has not, and that is the point."""
    source = _standing("Thanksgiving (CA)", days=25, mode=MERCHANDISE)
    target = _standing("Christmas", days=96, mode=LAUNCH, lanes=("QUICK", "LONG"))
    assert A.may_roll_forward(source, target, capacity=A.ENGINEERING)["may_roll"] is True
    assert A.may_roll_forward(source, target, capacity=A.MARKETING)["may_roll"] is False


# ---- arriving too late ----------------------------------------------------


def test_engineering_may_not_roll_into_an_occasion_with_no_open_lane():
    source = _standing("Thanksgiving (CA)", days=25, mode=MERCHANDISE)
    target = _standing("Halloween", days=41, mode=MERCHANDISE)
    out = A.may_roll_forward(source, target, capacity=A.ENGINEERING)
    assert out["may_roll"] is False
    assert "same mistake twice" in out["why"]


def test_engineering_may_not_roll_inside_the_preparation_lead():
    source = _standing("Thanksgiving (CA)", days=25, mode=MERCHANDISE)
    target = _standing("Halloween", days=A.LONGEST_PREPARATION_LEAD - 1, mode=LAUNCH,
                       lanes=("QUICK",))
    out = A.may_roll_forward(source, target, capacity=A.ENGINEERING)
    assert out["may_roll"] is False
    assert "after the work they exist to prepare" in out["why"]


def test_marketing_may_not_roll_into_an_occasion_already_past():
    source = _standing("Thanksgiving (CA)", days=5, mode=POST_OCCASION)
    target = _standing("Halloween", days=12, mode=POST_OCCASION)
    out = A.may_roll_forward(source, target, capacity=A.MARKETING)
    assert out["may_roll"] is False
    assert "last practical make date" in out["why"]


def test_marketing_rolls_into_an_occasion_engineering_cannot():
    """Copy and promotion for a listing that already exists need no launch lane."""
    source = _standing("Thanksgiving (CA)", days=5, mode=POST_OCCASION)
    target = _standing("Halloween", days=41, mode=MERCHANDISE)
    assert A.may_roll_forward(source, target, capacity=A.MARKETING)["may_roll"] is True
    assert A.may_roll_forward(source, target, capacity=A.ENGINEERING)["may_roll"] is False


def test_an_occasion_in_the_past_never_receives_anything():
    source = _standing("Thanksgiving (CA)", days=5, mode=POST_OCCASION)
    target = _standing("Labour Day", days=-3, mode=POST_OCCASION)
    for capacity in A.CAPACITIES:
        assert A.may_roll_forward(source, target, capacity=capacity)["may_roll"] is False


def test_rolling_an_occasion_into_itself_is_refused():
    s = _standing("Christmas", days=96, mode=LAUNCH, lanes=("QUICK",))
    try:
        A.may_roll_forward(s, s, capacity=A.ENGINEERING)
    except A.ArbitrageRefused as e:
        assert "to itself" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an occasion rolled capacity to itself")


def test_an_unnamed_capacity_is_refused():
    s = _standing("Christmas", days=96, mode=LAUNCH)
    t = _standing("Valentine's", days=147, mode=LAUNCH, lanes=("FLAGSHIP",))
    try:
        A.may_roll_forward(s, t, capacity="attention")
    except A.ArbitrageRefused:
        pass
    else:  # pragma: no cover
        raise AssertionError("an invented capacity was accepted")


# ---- the plan -------------------------------------------------------------


def test_the_plan_keeps_its_refusals_rather_than_filtering_them():
    """A plan listing only its moves reads the same whether nothing needed moving or
    everything was blocked."""
    plan = A.roll_forward(date(2026, 9, 20))
    for capacity in A.CAPACITIES:
        assert "moves" in plan["capacities"][capacity]
        assert "blocked" in plan["capacities"][capacity]
    assert "rolls forward first" in plan["rule"]


def test_a_roll_forward_prefers_the_soonest_occasion_that_can_repay_it():
    plan = A.roll_forward(date(2026, 9, 20))
    for move in plan["capacities"][A.ENGINEERING]["moves"]:
        assert move["may_roll"] is True


# ---- the curve it cannot draw ---------------------------------------------


def test_the_structural_floor_is_computed_and_the_decay_is_not():
    out = A.demand_curve(date(2026, 12, 25), today=date(2026, 9, 20))
    assert out["past_floor"] is False
    assert out["structural_floor_on"] == "2026-12-04"
    assert out["decay_before_floor"] == A.OBSERVED_DECAY
    assert "point estimate presented as a fact" in out["why_unobserved"]
    assert "impressions and orders" in out["what_would_settle_it"]


def test_past_the_floor_demand_is_zero_by_construction_not_by_measurement():
    out = A.demand_curve(date(2026, 12, 25), today=date(2026, 12, 20))
    assert out["past_floor"] is True
    assert "by construction rather than by measurement" in out["floor_basis"]


def test_state_credits_the_module_that_already_did_most_of_this():
    out = A.state()
    assert "seasonal.compression" in out["already_covered_by"]
    assert "rolls forward first" in out["added_here"]["the_rule"]
    assert "no listing of this shop's has been watched" in out["cannot_see"]


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
