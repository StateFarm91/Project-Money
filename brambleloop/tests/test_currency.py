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
