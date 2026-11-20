"""Paid acquisition economics, as arithmetic that cannot spend (#242, #243, #244, #245).

Organic proof before scaling, allowable CAC from every term, Offsite Ads terms read from the
dated advertising reading rather than typed, Share & Save refused without an official rate --
and no function on any of these paths enqueues, schedules or authorises ad spend.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import paid_media as pm  # noqa: E402
from brambleloop.core.models import Phase  # noqa: E402
from brambleloop.gates.policy_knowledge import READINGS  # noqa: E402
from brambleloop.scale import runrate  # noqa: E402


# ---- #242 organic first ------------------------------------------------------------------


def test_no_organic_period_means_no_paid_scaling():
    gate = pm.organic_first_gate(None)
    assert gate["allowed"] is False and gate["status"] == "UNMEASURED"


def test_the_organic_floors_are_the_attribution_window_and_the_measured_sample():
    assert pm.MIN_ORGANIC_DAYS == pm.offsite_ads_terms()["attribution_window_days"]
    from brambleloop.growth.loops import MEASURED_SAMPLE

    assert pm.MIN_ORGANIC_VISITS == MEASURED_SAMPLE
    short = pm.organic_first_gate(pm.OrganicPeriod(days=pm.MIN_ORGANIC_DAYS - 1,
                                                   visits=pm.MIN_ORGANIC_VISITS, orders=3))
    assert short["allowed"] is False and short["status"] == "insufficient_organic_period"
    thin = pm.organic_first_gate(pm.OrganicPeriod(days=pm.MIN_ORGANIC_DAYS,
                                                  visits=pm.MIN_ORGANIC_VISITS - 1, orders=3))
    assert thin["allowed"] is False


def test_a_weak_listing_is_not_hidden_behind_paid_traffic_and_no_baseline_is_unmeasured():
    period = pm.OrganicPeriod(days=pm.MIN_ORGANIC_DAYS, visits=pm.MIN_ORGANIC_VISITS * 2,
                              orders=1)
    weak = pm.organic_first_gate(period, min_conversion=0.05)
    assert weak["allowed"] is False and weak["status"] == "weak_listing"
    unjudged = pm.organic_first_gate(period)
    assert unjudged["allowed"] is True and unjudged["appeal"]["status"] == "UNMEASURED"


# ---- #243 allowable CAC --------------------------------------------------------------------


def test_the_three_cac_figures_are_kept_apart_and_unmeasured_without_counts():
    out = runrate.cac_split(ad_spend_cad=30.0, new_customers_from_ads=None,
                            new_customers_all_sources=None)
    for key in ("new_customer_cac_cad", "blended_cac_cad", "contribution_after_ads_cad"):
        assert out[key]["status"] == "UNMEASURED"
    zero = runrate.cac_split(ad_spend_cad=30.0, new_customers_from_ads=0,
                             new_customers_all_sources=0)
    assert zero["new_customer_cac_cad"]["value"] is None
    measured = runrate.cac_split(ad_spend_cad=30.0, new_customers_from_ads=3,
                                 new_customers_all_sources=10, contribution_cad=25.0,
                                 offsite_fees_cad=2.0)
    assert measured["new_customer_cac_cad"]["value"] == 10.0
    assert measured["blended_cac_cad"]["value"] == 3.0
    assert measured["contribution_after_ads_cad"]["value"] == -7.0
    try:
        runrate.cac_split(ad_spend_cad=1.0, new_customers_from_ads=5,
                          new_customers_all_sources=2)
    except runrate.RunRateRefused:
        pass
    else:
        raise AssertionError("more ad customers than customers was accepted")


def test_allowable_cac_uses_every_term_and_refuses_a_losing_first_order():
    out = runrate.allowable_cac_risk_adjusted(
        price_cad=10.0, fee_rate=0.12, refund_rate=0.02, discount_rate=0.0,
        cost_of_sale_cad=0.5, expected_repeat_contribution_cad=0.0)
    first = 10.0 * 0.88 * 0.98 - 0.5
    assert abs(out["allowable_cac_cad"] - round(first * (1 - runrate.DEFAULT_SAFETY_MARGIN), 2)) < 0.01
    losing = runrate.allowable_cac_risk_adjusted(
        price_cad=2.0, fee_rate=0.12, refund_rate=0.0, discount_rate=0.5,
        cost_of_sale_cad=5.0, expected_repeat_contribution_cad=0.0)
    assert losing["allowable_cac_cad"] == 0.0 and losing["first_order_negative"] is True


# ---- #244 Offsite Ads, read from the dated reading --------------------------------------------


def test_offsite_terms_come_from_the_advertising_reading_and_cite_it():
    terms = pm.offsite_ads_terms()
    reading = READINGS["advertising_rules"]
    text = next(c["text"] for c in reading.conclusions if c["rule"] == "offsite_ads_fee")
    assert f"{int(terms['standard_fee_rate'] * 100)}%" in text
    assert f"{int(terms['reduced_fee_rate'] * 100)}%" in text
    assert f"US${int(terms['fee_cap_usd'])}" in text
    assert f"{terms['attribution_window_days']} days" in text
    assert terms["source"]["read_on"] == reading.read_on
    assert terms["source"]["basis"] == reading.basis
    src = inspect.getsource(pm.offsite_ads_terms)
    for literal in ("0.15", "0.12", "10000", "10_000", "= 30"):
        assert literal not in src, f"{literal} hardcoded in offsite_ads_terms"


def test_the_forecast_tracks_attributed_orders_and_the_mandatory_threshold():
    terms = pm.offsite_ads_terms()
    under = pm.offsite_ads_forecast(orders=100, aov_usd=10.0, offsite_share=0.2,
                                    trailing_365_sales_usd=terms["threshold_usd"] - 1,
                                    contribution_rate=0.8)
    over = pm.offsite_ads_forecast(orders=100, aov_usd=10.0, offsite_share=0.2,
                                   trailing_365_sales_usd=terms["threshold_usd"],
                                   contribution_rate=0.8)
    assert under["participation"] == "optional" and over["participation"] == "mandatory"
    assert under["fee_rate_applied"] == terms["standard_fee_rate"]
    assert over["fee_rate_applied"] == terms["reduced_fee_rate"]
    assert under["attributed_orders"] == 20.0
    assert under["contribution_after_offsite_fees_usd"] < under["contribution_before_fees_usd"]
    capped = pm.offsite_ads_forecast(orders=1, aov_usd=10_000.0, offsite_share=1.0,
                                     trailing_365_sales_usd=0.0, contribution_rate=0.8)
    assert capped["fee_per_attributed_order_usd"] == terms["fee_cap_usd"]


# ---- #245 Share & Save ---------------------------------------------------------------------


def test_share_and_save_refuses_without_an_official_rate_and_measures_with_one():
    out = pm.share_and_save(orders_via_link=10, aov_cad=10.0, contribution_rate=0.8,
                            fee_benefit_rate=None)
    assert out["measurable"] is False and out["status"] == "UNMEASURED"
    try:
        pm.share_and_save(orders_via_link=10, aov_cad=10.0, contribution_rate=0.8,
                          fee_benefit_rate=0.05)
    except ValueError:
        pass
    else:
        raise AssertionError("a fee benefit without its official source was accepted")
    got = pm.share_and_save(orders_via_link=10, aov_cad=10.0, contribution_rate=0.8,
                            fee_benefit_rate=0.05, programme_source="test fixture source")
    assert got["contribution_via_link_cad"] == 85.0


# ---- nothing here can spend ------------------------------------------------------------------


def test_no_path_enqueues_or_authorises_ad_spend():
    from brambleloop.commerce import attribution, benchmarks, cohorts, kill_table, repeat
    from brambleloop.scale import leading

    for module in (pm, runrate, attribution, benchmarks, cohorts, kill_table, repeat,
                   leading):
        src = inspect.getsource(module)
        assert "enqueue(" not in src, module.__name__
        calls = src.count("authorise_spend(")
        defs = src.count("def authorise_spend(")
        assert calls == defs, f"{module.__name__} calls authorise_spend"
    state = pm.economics_state()
    assert state["can_spend"] is False
    for phase in (Phase.SHADOW, Phase.PRODUCTION):
        try:
            pm.authorise_spend(pm.CampaignState("x"), pm.CONSERVATIVE_CAPS, 1.0,
                               phase=phase, owner_granted=False)
        except pm.PaidMediaNotAuthorised:
            continue
        raise AssertionError(f"spend authorised in {phase} without the owner's grant")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{sum(1 for n in globals() if n.startswith('test_')) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
