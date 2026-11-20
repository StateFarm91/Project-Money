"""#22: what to do when something finally works, and why the answer is rarely one thing.

The interesting tests are the two refusals. Rank is not credibility -- in a catalogue of
three the best seller may have sold twice. And a winner that is the only example of
everything it is has no testable explanation at all, however obvious the reason feels.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import replication as R  # noqa: E402

START = date(2026, 9, 20)


def _field(prices=("10_to_20",) * 6, sewing=("sewn",) * 6, orders=10):
    return [R.Sku(f"s{i}", orders, 20,
                  {"price": prices[i], "sewing": sewing[i], "technique": "granny",
                   "aesthetic": "bright"})
            for i in range(len(prices))]


def _winner(orders=60, weeks=20):
    return R.Sku("win", orders, weeks,
                 {"price": "under_6", "sewing": "no_sew", "technique": "granny",
                  "aesthetic": "bright"})


# --- rank is not credibility -----------------------------------------------------------------

def test_the_best_seller_of_three_may_have_sold_twice():
    tiny = [R.Sku("a", 2, 20, {}), R.Sku("b", 1, 20, {})]
    out = R.is_winner(R.Sku("c", 3, 20, {}), tiny + [R.Sku("c", 3, 20, {})])
    assert out["credible"] is False
    assert any("may have sold twice" in r for r in out["reasons"])
    assert "say nothing about why yet" in out["note"]


def test_a_launch_is_not_a_trend():
    out = R.is_winner(_winner(weeks=1), _field() + [_winner(weeks=1)])
    assert any("a launch is not a trend" in r for r in out["reasons"])


def test_a_lead_under_the_multiple_is_a_good_week():
    field = _field(orders=40)
    out = R.is_winner(_winner(orders=50), field + [_winner(orders=50)])
    assert out["credible"] is False
    assert any("good week rather than a winner" in r for r in out["reasons"])


def test_a_shop_where_only_one_product_sells_is_a_different_finding():
    field = _field(orders=0)
    out = R.is_winner(_winner(), field + [_winner()])
    assert out["credible"] is False
    assert any("more urgent one" in r for r in out["reasons"])


def test_a_catalogue_of_one_has_no_best_seller():
    out = R.is_winner(_winner(), [_winner()])
    assert any("it has a product" in r for r in out["reasons"])


def test_a_credible_winner_is_credible():
    assert R.is_winner(_winner(), _field() + [_winner()])["credible"] is True


# --- why is hard, and saying so is the point ---------------------------------------------------

def test_a_winner_that_is_the_only_example_of_everything_explains_nothing():
    """Every difference is a complete explanation, and at most one of them is the reason."""
    out = R.candidates(_winner(), _field() + [_winner()])
    assert out["attributable"] is False
    assert set(out["confounded"]) == {"price", "sewing"}
    assert "is a story" in out["all"][R.DIMENSIONS.index("price")]["why"]
    assert "The next product is the experiment" in out["note"]


def test_a_dimension_the_catalogue_varies_on_is_testable():
    prices = ("under_6", "under_6", "10_to_20", "10_to_20", "6_to_10", "6_to_10")
    out = R.candidates(_winner(), _field(prices=prices) + [_winner()])
    ranked = [r["dimension"] for r in out["ranked"]]
    assert "price" in ranked
    assert out["attributable"] is True


def test_a_dimension_almost_nothing_differs_on_separates_nothing():
    sewing = ("no_sew",) * 5 + ("sewn",)
    out = R.candidates(_winner(), _field(sewing=sewing) + [_winner()])
    row = out["all"][R.DIMENSIONS.index("sewing")]
    assert row["testable"] is False
    assert "not enough variation" in row["why"]


def test_an_unrecorded_dimension_says_so_rather_than_scoring_zero():
    bare = R.Sku("win", 60, 20, {"price": "under_6"})
    out = R.candidates(bare, _field() + [bare])
    row = out["all"][R.DIMENSIONS.index("video")]
    assert row["testable"] is False
    assert "not recorded for the winner" in row["why"]


def test_it_is_just_better_is_not_a_dimension():
    odd = R.Sku("win", 60, 20, {"vibes": "good"})
    try:
        R.candidates(odd, _field() + [odd])
    except R.ReplicationRefused as exc:
        assert "cannot be tested, so it cannot be recorded as a reason" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an untestable reason was recorded")


# --- adjacent, not cloned -----------------------------------------------------------------------

def test_a_second_colourway_answers_nothing():
    out = R.check_proposal(R.Proposal("p", ("sewing", "price"), ("aesthetic",)), _winner())
    assert out["adjacent"] is False
    assert any("the clone this requirement names" in r for r in out["reasons"])


def test_a_proposal_that_changes_nothing_is_the_same_product():
    out = R.check_proposal(R.Proposal("p", ("sewing",), ()), _winner())
    assert any("sells to the people who already bought it" in r for r in out["reasons"])


def test_a_proposal_that_holds_nothing_is_about_a_different_product():
    out = R.check_proposal(R.Proposal("p", (), ("theme",)), _winner())
    assert any("about a different product" in r for r in out["reasons"])


def test_a_dimension_both_held_and_changed_is_two_plans():
    out = R.check_proposal(R.Proposal("p", ("price",), ("price", "theme")), _winner())
    assert any("it is two plans" in r for r in out["reasons"])


def test_an_adjacent_proposal_says_what_it_tests():
    out = R.check_proposal(R.Proposal("p", ("sewing",), ("theme", "season")), _winner())
    assert out["adjacent"] is True
    assert "what win was about" in out["tests"]


# --- the reallocation ends -------------------------------------------------------------------------

def test_capacity_does_not_move_to_a_rank():
    try:
        R.study(_winner(orders=5), _field(), capacity_share=0.2, starts=START)
    except R.ReplicationRefused as exc:
        assert "rebuilt around a good week" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("capacity moved to a product that had sold five")


def test_substantial_is_not_most():
    try:
        R.study(_winner(), _field() + [_winner()], capacity_share=0.8, starts=START)
    except R.ReplicationRefused as exc:
        assert "Substantial is not most" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("the catalogue was rebuilt around one SKU")


def test_a_study_with_no_end_is_a_permanent_bet_nobody_made():
    try:
        R.study(_winner(), _field() + [_winner()], capacity_share=0.2, starts=START,
                days=400)
    except R.ReplicationRefused as exc:
        assert "permanent reallocation nobody decided to make" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unbounded study was scheduled")


def test_a_study_returns_the_capacity_on_its_end_date_answered_or_not():
    out = R.study(_winner(), _field() + [_winner()], capacity_share=0.3, starts=START,
                  days=30)
    assert out["ends"] == "2026-10-20"
    assert "not a reason to keep the capacity" in out["note"]
    assert out["attributable"] is False  # this winner is confounded, and the study says so


def test_state_names_the_floors_and_the_ceilings():
    out = R.state()
    assert out["winner_floors"]["orders"] == R.MIN_ORDERS
    assert out["study_ceilings"]["capacity_share"] == R.MAX_CAPACITY_SHARE
    assert len(out["dimensions"]) == 11


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
