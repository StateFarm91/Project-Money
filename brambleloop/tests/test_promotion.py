"""#19: promotions measured by what they leave behind, not by what they move.

The requirement's sentence is "measure incremental conversion, AOV and contribution, not
merely revenue lift", and these tests are mostly about the arithmetic that makes the last
word mean something.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import promotion as P  # noqa: E402
from brambleloop.commerce.elasticity import Arm  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402

START = date(2026, 11, 1)


def _promo(full=12.0, promo=9.6, days=20, reason="Black Friday, genuinely time-bounded",
           ever=True):
    return P.propose("lantern-throw", full_price_cad=full, promo_price_cad=promo,
                     starts=START, ends=START + timedelta(days=days), reason=reason,
                     ever_charged_full=ever)


def _arm(key, arm, visits, orders, revenue):
    return Arm(key=key, product_slug="lantern-throw", arm=arm, visits=visits,
               orders=orders, revenue_cad=revenue)


def test_a_promotion_must_end_and_the_end_must_be_a_date():
    """A sale with no end is a price, and a price presented as a sale is a claim about an
    ordinary price the seller has to substantiate."""
    assert _promo().days == 20

    for kwargs, fragment in (
            ({"days": 90}, "is not a promotion"),
            ({"days": 0}, "is not a window"),
            ({"reason": "   "}, "looking for one"),
            ({"promo": 12.0}, "discounts nothing"),
            ({"promo": 4.0}, "repricing rather than a promotion"),
            ({"ever": False}, "never been sold at that price")):
        raised = None
        try:
            _promo(**kwargs)
        except P.PromotionRefused as e:
            raised = e
        assert raised is not None, kwargs
        assert fragment in str(raised), (kwargs, str(raised))


def test_incrementality_is_refused_without_a_full_price_control():
    """Without one, the discounted conversion rate is a fact about people shown a discount."""
    out = P.incrementality(_promo(), full_price_arm=None,
                           discounted_arm=_arm("p", "promoted", 1000, 40, 384.0))
    assert out["measurable"] is False
    assert "cannot sell without one" in out["why_it_matters"]


def test_contribution_compares_net_against_net():
    """The bug this nearly shipped as a finding.

    The first version compared the *gross* full price against the *net* promo price, which
    manufactures a contribution loss out of the fee schedule. It looks exactly like the
    divergence this module exists to warn about, and it is an arithmetic error.
    """
    from brambleloop.commerce.pricing import fees

    promotion = _promo()
    control = _arm("c", "organic", 1000, 30, 360.0)
    promoted = _arm("p", "promoted", 1000, 40, 384.0)
    out = P.incrementality(promotion, full_price_arm=control, discounted_arm=promoted)

    expected = out["contribution_cad"]["at_full_price_on_the_same_traffic"]
    # 30 orders at the full price, net of fees -- not 30 x 12.00.
    assert abs(expected - 30 * fees(12.0).net_cad) < 0.05, expected
    assert expected < 30 * 12.0, "the comparison used a gross price on one side"

    assert out["net_per_order_cad"]["full_price"] == fees(12.0).net_cad
    assert out["net_per_order_cad"]["discounted"] == fees(9.6).net_cad


def test_with_no_marginal_cost_revenue_and_contribution_agree():
    """The qualification that keeps this module from warning about a danger it cannot show.

    For a digital pattern the marginal cost of a sale is nearly zero, so a discount pays
    whenever units rise enough to cover the cut -- and both numbers say so. Implying
    otherwise would be a module manufacturing alarm.
    """
    promotion = _promo()
    control = _arm("c", "organic", 1000, 30, 360.0)

    good = P.incrementality(promotion, full_price_arm=control,
                            discounted_arm=_arm("p", "promoted", 1000, 40, 384.0))
    assert good["revenue_lift_cad"] > 0 and good["contribution_cad"]["change"] > 0
    assert good["verdict"] == "worth repeating"
    assert good["bought_revenue_and_lost_contribution"] is False

    bad = P.incrementality(promotion, full_price_arm=control,
                           discounted_arm=_arm("p", "promoted", 1000, 34, 326.4))
    assert bad["revenue_lift_cad"] < 0 and bad["contribution_cad"]["change"] < 0
    assert bad["verdict"] == "not worth repeating"
    assert "telling you the same thing" in good["when_these_two_diverge"]


def test_the_divergence_appears_once_a_real_per_unit_cost_exists():
    """And it is #31's cost-to-create, amortised over the units the pattern sells.

    Revenue up, contribution down: the case the requirement names, shown where it actually
    occurs rather than asserted where it cannot.
    """
    out = P.incrementality(_promo(), full_price_arm=_arm("c", "organic", 1000, 30, 360.0),
                           discounted_arm=_arm("p", "promoted", 1000, 40, 384.0),
                           unit_cost_cad=6.0)
    assert out["revenue_lift_cad"] > 0
    assert out["contribution_cad"]["change"] < 0
    assert out["bought_revenue_and_lost_contribution"] is True
    assert out["verdict"] == "bought revenue and lost contribution"
    assert "pays for anything" in out["why"]


def test_all_three_numbers_the_requirement_names_are_reported():
    out = P.incrementality(_promo(), full_price_arm=_arm("c", "organic", 1000, 30, 360.0),
                           discounted_arm=_arm("p", "promoted", 1000, 40, 384.0))
    assert set(out["conversion"]) == {"full_price", "discounted", "lift"}
    assert set(out["aov_cad"]) == {"full_price", "discounted", "change"}
    assert set(out["contribution_cad"]) == {
        "at_full_price_on_the_same_traffic", "actual_at_promo_price", "change"}
    # AOV falls when the price falls, which is the point of reporting it separately.
    assert out["aov_cad"]["change"] < 0


def test_a_live_promotion_can_be_ended_rather_than_forgotten():
    promotion = _promo()
    assert P.window(promotion, START - timedelta(days=1))["state"] == "scheduled"
    assert P.window(promotion, START + timedelta(days=5))["state"] == "running"
    over = P.window(promotion, promotion.ends + timedelta(days=1))
    assert over["state"] == "over"
    assert "a sale becomes a price" in over["why"]


def test_catalogue_dependence_is_counted_and_full_price_sales_are_not_assumed():
    """A catalogue with no sales has no full-price sales either, and that is a different
    finding from one that has stopped having them."""
    db = Database("sqlite://")
    db.create_all()
    empty = P.dependence(db)
    assert empty["measurable"] is False
    assert empty["full_price_sales"]["measurable"] is False

    from brambleloop.core.models import Listing

    with db.session() as s:
        for i in range(4):
            s.add(Listing(product_slug=f"p{i}", version="1.0.0", title="t",
                          description="d", price_cad=9.0))
    counted = P.dependence(db)
    assert counted["measurable"] is True
    assert counted["listings"] == 4
    assert counted["conditioned"] is False
    assert counted["full_price_sales"]["measurable"] is False
    assert "no sales has no full-price sales" in counted["full_price_sales"]["reason"]


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
