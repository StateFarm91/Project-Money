"""#269 and #268: one reporting currency with the transaction's own preserved, and the
market the observed language actually describes.

The word doing the work in #269 is *preserving*. Converting a USD sale into CAD and keeping
only the CAD figure destroys the one number that can be reconciled against a bank statement.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import markets as M  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.finance import currency as C  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402

ON = date(2026, 9, 20)


def test_an_amount_with_no_currency_cannot_be_recorded():
    """It cannot be reconciled against anything, which is the only thing a recorded amount
    is for."""
    raised = None
    try:
        C.Money(9.0, "")
    except C.CurrencyRefused as e:
        raised = e
    assert raised is not None
    assert "cannot be reconciled" in str(raised)


def test_the_transaction_currency_survives_the_conversion():
    """Keeping only the converted figure destroys the number a bank statement can be
    checked against."""
    converted = C.to_reporting(C.Money(9.0, "USD"), C.assumed_rate(ON))
    assert converted["original"] == {"amount": 9.0, "currency": "USD"}
    assert converted["reporting"]["currency"] == "CAD"
    assert converted["converted"] is True
    assert converted["rate"]["usd_per_cad"] == C.ASSUMED_USD_PER_CAD

    native = C.to_reporting(C.Money(12.0, "CAD"), C.assumed_rate(ON))
    assert native["converted"] is False
    assert native["rate"] is None


def test_an_assumed_rate_says_it_is_assumed():
    """A converted figure whose rate is invisible is indistinguishable from a measured one."""
    rate = C.assumed_rate(ON)
    assert rate.measured is False
    assert "indistinguishable from a measured one" in rate.to_dict()["note"]

    settled = C.Rate(0.732, ON, measured=True, source="settlement statement")
    assert "came from a settlement statement" in settled.to_dict()["note"]


def test_a_currency_with_no_rate_on_file_is_refused_rather_than_guessed():
    raised = None
    try:
        C.to_reporting(C.Money(9.0, "GBP"), C.assumed_rate(ON))
    except C.CurrencyRefused as e:
        raised = e
    assert raised is not None
    assert "nobody can check" in str(raised)


def test_every_fee_class_the_requirement_names_is_priced_or_named_as_unobserved():
    """A margin computed without a fee should say so rather than look like one that
    included it."""
    out = C.contribution(C.Money(9.0, "USD"), rate=C.assumed_rate(ON))
    assert set(out["fees"]) >= {"transaction", "payment", "currency_conversion",
                                "regulatory_operating", "ad_fee", "listing_amortised"}
    assert out["fees_not_yet_observed"] == ["currency_conversion", "regulatory_operating",
                                            "ad_fee"]
    assert "has not been charged them yet" in out["why"]

    charged = C.contribution(
        C.Money(9.0, "USD"), rate=C.assumed_rate(ON),
        schedule=C.FeeSchedule(currency_conversion=0.025, regulatory_operating=0.0125,
                               basis="observed on a settlement statement"))
    assert charged["fees"]["currency_conversion"] > 0
    assert charged["take_rate"] > out["take_rate"]
    assert charged["fees_not_yet_observed"] == ["ad_fee"]


def test_net_contribution_is_reported_before_the_sticker_price():
    """The requirement's closing sentence: pricing decisions use net contribution."""
    out = C.contribution(C.Money(12.0, "CAD"))
    assert out["net_contribution"]["amount"] < out["gross_reporting"]["amount"]
    assert out["net_contribution"]["currency"] == C.REPORTING_CURRENCY
    assert out["sticker"]["currency"] == "CAD"


# ---- #268 -------------------------------------------------------------------


def test_the_observed_language_is_american_not_canadian_and_not_global():
    """The requirement warns against assuming Canadian behaviour is global. The error
    present here points the other way, which is easier to miss.

    The benchmark is a United States shop, so every term frequency this system has measured
    describes that market. Reading it as Canadian, or as global, is the same mistake with
    the countries swapped.
    """
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        for i in range(5):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"x{i}",
                                   title="t", pod="hats"))
    whose = M.whose_language_is_this(db)
    assert whose["describes_market"] == M.US
    assert whose["measurable"] is True
    assert "not how Canadian buyers search" in whose["why"]
    # And it does not conclude the evidence is worthless, which would be the opposite error.
    assert "not that it is worthless" in whose["not_an_argument_to_ignore_it"]


def test_the_attribution_reads_the_benchmark_rather_than_returning_us():
    """A function whose answer does not depend on its argument is an assertion.

    The first version returned `US` for whatever key it was handed. That was correct about
    the only benchmark that exists and would have been silently wrong about the second one --
    which is the whole of #268: term frequencies getting attributed to a market by
    assumption rather than by observation. So an unregistered benchmark, or one whose market
    nobody established, must come back `unstated` and un-attributable rather than American.
    """
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        for i in range(4):
            s.add(BenchmarkListing(benchmark_key="a_shop_nobody_placed",
                                   listing_ref=f"y{i}", title="t", pod="hats"))

    whose = M.whose_language_is_this(db, benchmark_key="a_shop_nobody_placed")
    assert whose["describes_market"] == benchmarks.UNSTATED_MARKET
    assert whose["measurable"] is True, "four listings were observed"
    assert whose["attributable"] is False, "whose language they are is what is missing"
    assert "guessing it is the error" in whose["why"]


def test_one_market_is_not_a_cross_border_lens_however_many_listings_it_has():
    """438 observations of one shop do not become two markets by being numerous."""
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        for i in range(60):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"z{i}",
                                   title="t", pod="hats"))

    cover = M.coverage(db)
    assert cover["markets_with_a_benchmark"] == [M.US]
    assert cover["is_cross_border"] is False
    assert "against nothing" in cover["why"]
    # And what closes it is a choice, not a capability -- #268 was parked for a day on a
    # credential gate that had been open since the credential was proven by use.
    assert "No new capability, no spend" in cover["what_is_needed"]


def test_the_gate_268_waits_on_counts_markets_and_not_credentials():
    """The park that never expires by itself, stated as the property that catches it."""
    from brambleloop.build2 import executor as E

    gate = E.GATE_BY_KEY["second_market_benchmark"]
    db = Database("sqlite://")
    db.create_all()

    with db.session() as s:
        for i in range(400):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=f"m{i}",
                                   title="t", pod="hats"))
    assert gate.open(db, {}) is False, "one market's listings, however many, are one market"

    second = benchmarks.BenchmarkSpec(
        key="a_uk_shop", shop_name="AUkShop", canonical_url="https://example.invalid/shop/x",
        market="other")
    original = benchmarks.REGISTRY
    try:
        benchmarks.REGISTRY = original + (second,)
        assert gate.open(db, {}) is False, "registering a shop is not observing one"
        with db.session() as s:
            s.add(BenchmarkListing(benchmark_key="a_uk_shop", listing_ref="u1",
                                   title="t", pod="hats"))
        assert gate.open(db, {}) is True
    finally:
        benchmarks.REGISTRY = original


def test_an_unobserved_benchmark_has_no_language_to_attribute():
    db = Database("sqlite://")
    db.create_all()
    whose = M.whose_language_is_this(db)
    assert whose["measurable"] is False
    assert "no language to attribute" in whose["why"]


def test_thanksgiving_is_six_weeks_apart_and_the_calendar_holds_one_of_them():
    """A product merchandised to one is merchandised away from the other."""
    split = M.holiday_split("Thanksgiving (CA)")
    assert split["differs"] is True
    assert "October" in split["dates"][M.CA]
    assert "November" in split["dates"][M.US]
    assert "six weeks apart" in split["why"]

    same = M.holiday_split("Christmas")
    assert same["differs"] is False
    assert "one launch date serves all" in same["why"]


def test_terminology_names_the_stitch_collision_rather_than_a_preference():
    """A US double crochet is a UK treble. A pattern that does not say makes the wrong
    fabric for half its buyers."""
    for market in (M.CA, M.US):
        assert M.terminology_for(market)["terms"] == "US"
    assert M.terminology_for(M.OTHER)["terms"] == "UK"
    assert "a US double crochet is a UK treble" in M.terminology_for(M.CA)["why"]
    assert M.terminology_for(M.US)["both_required"] is True

    raised = None
    try:
        M.terminology_for("Atlantis")
    except M.MarketRefused as e:
        raised = e
    assert raised is not None


def test_the_one_thing_that_does_not_differ_is_stated_rather_than_assumed():
    db = Database("sqlite://")
    db.create_all()
    out = M.lens(db, today=ON)
    assert "same day everywhere" in out["does_not_differ"]["delivery"]
    assert out["currency"]["reporting"] == C.REPORTING_CURRENCY


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
