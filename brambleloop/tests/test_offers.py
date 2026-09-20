"""#13: the offer is a variable, and a design is not retired on one offer's evidence.

The requirement's last sentence is the one with teeth -- a winning design with a weak offer
should be fixed before being discarded -- so most of these tests are about the retirement
decision and what it is allowed to be a decision about.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import offers as O  # noqa: E402


def _r(offer, **over):
    base = dict(design_slug="hex-coaster", offer=offer, visitors=500, buyers=20,
                revenue_cad=120.0, contribution_cad=90.0)
    base.update(over)
    return O.Result(**base)


# --- retiring a design -----------------------------------------------------------------------

def test_a_design_tried_in_one_shape_has_been_tested_as_an_offer():
    out = O.may_retire("hex-coaster", [_r(O.SINGLE)])
    assert out["may_retire"] is False
    assert "acquired the design's name" in out["note"]
    assert out["try_next"]["offer"] in O.BY_KEY


def test_three_bundles_are_one_offer_tested_three_times():
    """The count is not the question. A mini bundle, a collection and a seasonal bundle are
    the same proposition at three sizes."""
    results = [_r(O.MINI), _r(O.COLLECTION), _r(O.SEASONAL)]
    out = O.may_retire("hex-coaster", results)
    assert out["may_retire"] is False
    assert out["families"] == ["bundled"]
    assert any("three times" in r for r in out["reasons"])


def test_two_genuinely_different_shapes_let_the_design_be_judged():
    out = O.may_retire("hex-coaster", [_r(O.SINGLE), _r(O.MINI)])
    assert out["may_retire"] is True
    assert "can be judged as a design" in out["note"]


def test_an_offer_nobody_bought_enough_of_did_not_lose():
    """It did not run. A thin offer counted as a loss is a design retired on noise."""
    out = O.may_retire("hex-coaster", [_r(O.SINGLE), _r(O.MINI, buyers=2)])
    assert out["may_retire"] is False
    assert any("did not lose; it did not run" in r for r in out["reasons"])


def test_the_next_thing_to_try_is_the_cheapest_shape_it_has_not_worn():
    out = O.may_retire("hex-coaster", [_r(O.SINGLE)])
    untried = out["untried_and_deliverable"]
    assert O.VIDEO not in untried  # cannot be delivered, so it is not a suggestion
    assert out["try_next"]["offer"] == min(
        (O.BY_KEY[k] for k in untried), key=lambda o: o.posture).key


# --- the two measurements ----------------------------------------------------------------------

def test_both_figures_are_reported_and_neither_alone():
    """Whichever one is quoted by itself is the one that was quoted because it looked
    better."""
    m = _r(O.COLLECTION, visitors=300, buyers=3, revenue_cad=84.0,
           contribution_cad=63.0).measures()
    assert m["revenue_per_buyer"] == 28.0
    assert m["contribution_per_visitor"] == 0.21
    assert "flatters" in m["why_both"]


def test_an_unmeasured_offer_is_listed_rather_than_ranked_last():
    """A None sorted as a zero puts the best offer nobody measured at the bottom, and that
    is where it gets discarded from."""
    measured = _r(O.SINGLE, contribution_cad=90.0)
    blind = _r(O.MINI, contribution_cad=None)
    out = O.compare([measured, blind])
    assert [row["offer"] for row in out["ranked"]] == [O.SINGLE]
    assert [row["offer"] for row in out["unmeasured"]] == [O.MINI]
    assert out["best"] == O.SINGLE


def test_nothing_measured_is_not_every_offer_performing_equally():
    out = O.compare([_r(O.SINGLE, contribution_cad=None, visitors=None)])
    assert out["best"] is None
    assert "not the same as every offer performing equally" in out["note"]


def test_the_ranking_is_by_contribution_per_visitor():
    rich_buyers = _r(O.COLLECTION, visitors=1000, buyers=5, revenue_cad=140.0,
                     contribution_cad=105.0)
    steady = _r(O.SINGLE, visitors=1000, buyers=60, revenue_cad=360.0,
                contribution_cad=270.0)
    out = O.compare([rich_buyers, steady])
    assert out["best"] == O.SINGLE
    assert out["ranked"][0]["revenue_per_buyer"] < out["ranked"][1]["revenue_per_buyer"]


# --- what may not be sold ------------------------------------------------------------------------

def test_an_offer_that_cannot_be_delivered_is_named_rather_than_priced():
    video = O.available(O.VIDEO)
    assert video["available"] is False
    assert "is a refund" in video["why"]
    support = O.available(O.BEGINNER)
    assert support["available"] is False
    assert "the promise has no basis" in support["why"]


def test_the_offers_that_can_be_sold_today_need_nothing_outside_this_system():
    today = O.ladder("hex-coaster")["deliverable_today"]
    assert O.SINGLE in today and O.MINI in today
    assert O.VIDEO not in today and O.BEGINNER not in today
    for key in today:
        assert O.BY_KEY[key].needs == ()


def test_an_invented_offer_is_refused():
    try:
        O.Result("hex-coaster", "buy_one_get_one")
    except O.OfferRefused as exc:
        assert "is not an offer" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented offer was recorded")


def test_every_offer_says_what_it_tests():
    for offer in O.OFFERS:
        assert offer.tests and len(offer.tests.split()) >= 5, offer.key
        assert offer.key in O.FAMILIES, offer.key


def test_state_names_the_six_offers_the_requirement_asks_for():
    out = O.state()
    assert {o["offer"] for o in out["offers"]} == {
        O.SINGLE, O.VIDEO, O.MINI, O.COLLECTION, O.BEGINNER, O.SEASONAL}
    assert out["measures"] == ["contribution_per_visitor", "revenue_per_buyer"]


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
