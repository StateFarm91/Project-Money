"""#233/#234: the ladder's shape, the discount that dismantles it, and what a bundle is.

Four of #233's measurements need a customer and there are none, so most of this file is
about the two halves that can be engineered today: where the ladder is broken, and which
discounts remove its bottom rung.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import bundles as B, ladder as L  # noqa: E402


def _full():
    return [{"slug": "e", "tier": L.ENTRY, "price_cad": 5.0},
            {"slug": "p", "tier": L.PREMIUM, "price_cad": 11.0},
            {"slug": "m", "tier": L.MINI, "price_cad": 22.0},
            {"slug": "f", "tier": L.FLAGSHIP, "price_cad": 38.0}]


# --- the ladder's shape -----------------------------------------------------------------------

def test_an_empty_rung_is_a_place_a_buyer_arrives_and_finds_nothing():
    out = L.shape([{"slug": "p", "tier": L.PREMIUM, "price_cad": 11.0}])
    assert out["empty_rungs"] == [L.ENTRY, L.MINI, L.FLAGSHIP]
    assert out["climbable"] is False
    assert "not a gap in a diagram" in out["note"]


def test_a_complete_ladder_is_climbable():
    out = L.shape(_full())
    assert out["empty_rungs"] == []
    assert out["climbable"] is True


def test_a_rung_several_times_the_last_one_is_a_missing_step_wearing_a_price():
    products = [{"slug": "e", "tier": L.ENTRY, "price_cad": 4.0},
                {"slug": "p", "tier": L.PREMIUM, "price_cad": 20.0},
                {"slug": "m", "tier": L.MINI, "price_cad": 22.0},
                {"slug": "f", "tier": L.FLAGSHIP, "price_cad": 40.0}]
    out = L.shape(products)
    step = out["steps"][0]
    assert step["too_big"] is True
    assert step["multiple"] == 5.0
    assert "does not next spend" in step["why"]
    assert out["climbable"] is False


def test_free_content_and_the_repeat_purchase_are_not_counted_as_gaps():
    """One is another requirement's subject and the other is an outcome, not a product."""
    out = L.shape(_full())
    assert L.FREE not in out["empty_rungs"] and L.REPEAT not in out["empty_rungs"]


def test_a_tier_nobody_named_is_refused():
    try:
        L.shape([{"slug": "x", "tier": "vip", "price_cad": 1.0}])
    except L.LadderRefused as exc:
        assert "is not a tier" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented tier joined the ladder")


# --- the discount that dismantles it -------------------------------------------------------------

def test_a_price_on_sale_a_third_of_the_time_is_not_a_price():
    out = L.check_discount(L.ENTRY, full_price_cad=6.0, promo_price_cad=5.0,
                           days_discounted=40, days_live=100)
    assert out["ok"] is False
    assert any("the buyer learns to wait" in r for r in out["reasons"])


def test_the_flagship_is_never_routinely_discounted():
    """It is the one product whose job is to say what this shop is worth."""
    out = L.check_discount(L.FLAGSHIP, full_price_cad=40.0, promo_price_cad=36.0,
                           days_discounted=3, days_live=200)
    assert out["ok"] is False
    assert any("no later full price recovers it" in r for r in out["reasons"])


def test_a_steep_discount_says_the_full_price_was_the_invention():
    out = L.check_discount(L.PREMIUM, full_price_cad=12.0, promo_price_cad=5.0,
                           days_discounted=5, days_live=200)
    assert any("the full price was the invention" in r for r in out["reasons"])


def test_the_depth_and_duration_rules_are_the_promotion_modules_own():
    from brambleloop.commerce import promotion

    assert L.MAX_PROMOTION_DAYS is promotion.MAX_PROMOTION_DAYS
    assert L.STEEP_DISCOUNT_ABOVE is promotion.STEEP_DISCOUNT_ABOVE


def test_a_short_shallow_promotion_on_an_ordinary_rung_passes():
    out = L.check_discount(L.PREMIUM, full_price_cad=12.0, promo_price_cad=10.0,
                           days_discounted=7, days_live=200)
    assert out["ok"] is True


# --- what cannot be measured ------------------------------------------------------------------------

def test_tier_movement_is_unmeasurable_rather_than_zero():
    out = L.movement([])
    assert out["measured"] == 0
    assert "unmeasurable rather than zero" in out["note"]


def test_a_rung_no_buyer_has_stood_on_reports_why_rather_than_a_rate():
    out = L.movement([{"from_tier": L.ENTRY, "to_tier": L.PREMIUM, "buyers": 0, "moved": 0}])
    assert out["movements"][0]["rate"] is None
    assert "no buyer has ever stood on this rung" in out["movements"][0]["why"]


def test_more_movers_than_buyers_is_a_counting_fault():
    try:
        L.movement([{"from_tier": L.ENTRY, "to_tier": L.PREMIUM, "buyers": 3, "moved": 5}])
    except L.LadderRefused as exc:
        assert "counting fault" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an impossible movement was reported")


def test_lifetime_value_needs_a_lifetime():
    assert L.lifetime_value([])["needs"] == ["repeat purchases"]
    once = L.lifetime_value([{"orders": 1, "contribution_cad": 5.0}])
    assert once["measurable"] is False
    assert "average order value with a longer name" in once["why"]
    twice = L.lifetime_value([{"orders": 2, "contribution_cad": 11.0}])
    assert twice["measurable"] is True


# --- #234: what a bundle is ----------------------------------------------------------------------------

def _throw():
    return B.Item("throw", "blankets", "rectangle_throw", 14.0, occasion="Christmas",
                  weight="worsted", collection="winter")


def _pillow():
    return B.Item("pillow", "home_decor", "pillow", 9.0, occasion="Christmas",
                  weight="worsted", collection="winter")


def _hat():
    return B.Item("hat", "hats", "hat", 6.0, occasion="Halloween", weight="bulky")


def test_a_bundle_nobody_would_use_together_is_two_products_in_a_discount():
    out = B.check([_throw(), _hat()], price_cad=17.0)
    assert out["ok"] is False
    assert any("cheapest way to make a catalogue look busy" in r for r in out["reasons"])


def test_affinities_are_facts_about_the_products():
    found = B.affinities(_throw(), _pillow())
    assert set(found) == {"same_occasion", "same_weight", "same_collection", "same_room"}
    assert B.affinities(_throw(), _hat()) == []


def test_a_bundle_across_too_many_departments_is_a_raffle():
    items = [_throw(), _pillow(),
             B.Item("ami", "amigurumi", "sphere", 7.0, occasion="Christmas",
                    weight="worsted", collection="winter"),
             B.Item("stk", "stockings", "stocking", 8.0, occasion="Christmas",
                    weight="worsted", collection="winter")]
    out = B.check(items, price_cad=32.0)
    assert any("a raffle" in r for r in out["reasons"])


def test_a_rounding_error_is_not_a_reason_to_buy_the_set():
    out = B.check([_throw(), _pillow()], price_cad=22.5)
    assert any("rounding error" in r for r in out["reasons"])


def test_a_discount_that_deep_tells_every_buyer_what_the_singles_are_worth():
    out = B.check([_throw(), _pillow()], price_cad=9.0)
    assert any("they will not unlearn it" in r for r in out["reasons"])


def test_a_coherent_bundle_at_a_real_discount_is_worth_testing():
    out = B.check([_throw(), _pillow()], price_cad=19.0)
    assert out["ok"] is True
    assert out["shared_affinities"] == ["same_collection", "same_occasion", "same_room",
                                        "same_weight"]


def test_candidates_are_pairs_ordered_by_what_holds_them_together():
    out = B.candidates([_throw(), _pillow(), _hat()])
    assert [c["slugs"] for c in out["candidates"]] == [["throw", "pillow"]]
    assert out["candidates"][0]["strength"] == 4


def test_a_catalogue_that_bundles_badly_is_a_finding_about_the_catalogue():
    out = B.candidates([_hat()])
    assert out["candidates"] == []
    assert "about the catalogue rather than about bundling" in out["note"]


def test_whether_the_bundle_worked_is_answered_by_the_engine_that_already_refuses():
    """A second implementation of "did the bundle add anything" is a second answer to the
    same question, and the more flattering one gets quoted."""
    from brambleloop.commerce.attribution import Period

    out = B.measure(bundle_slug="winter-set",
                    bundle=Period(slug="winter-set", orders=10, revenue_cad=190.0,
                                  contribution_cad=150.0),
                    components_before=[], components_after=[])
    assert out["measured_by"] == "commerce.attribution.bundle_effect"
    assert "baseline" in out["result"]["reason"]


def test_state_names_who_measures_it():
    assert "refuses without a baseline" in B.state()["measured_by"]
    assert L.state()["unmeasurable_today"]


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
