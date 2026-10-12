"""Etsy's fees come from one dated reading, and only read figures enter a take rate.

`commerce.fee_schedule` parses every fee from `gates.policy_knowledge.TOPICS["fees"]`. These
tests pin that every module which used to carry its own copy of a fee now agrees with the
schedule -- the ones that read it and the two that still hold literals -- and that a
SECONDARY or UNKNOWN fee cannot be quoted as part of what selling costs.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import fee_schedule as FS  # noqa: E402
from brambleloop.gates import policy_knowledge as PK  # noqa: E402


def test_every_claim_carries_the_reading_it_was_parsed_from():
    reading = PK.TOPICS["fees"]
    assert set(FS.CLAIMS) == {c["fee"] for c in reading.conclusions}
    for claim in FS.CLAIMS.values():
        assert claim.checked_on == reading.read_on
        assert claim.basis == reading.basis
        assert claim.source_url in reading.urls
        assert claim.evidence in FS.EVIDENCE_GRADES
    assert FS.TRANSACTION.rate == 0.065 and FS.TRANSACTION.evidence == FS.PRIMARY
    assert FS.PAYMENT_PROCESSING.rate == 0.03 and FS.PAYMENT_PROCESSING.amount == 0.25
    assert FS.PAYMENT_PROCESSING.currency == "CAD"
    assert FS.LISTING.amount == 0.20 and FS.LISTING.currency == "USD"


def test_an_unknown_fee_has_no_figure_and_cannot_be_given_one():
    assert FS.REGULATORY_OPERATING.evidence == FS.UNKNOWN
    assert FS.REGULATORY_OPERATING.rate is None and FS.REGULATORY_OPERATING.amount is None
    try:
        FS.FeeClaim(key="x", rate=0.01, amount=None, currency=None, basis="b", source_url="u",
                    checked_on="2026-09-26", evidence=FS.UNKNOWN, conclusion="UNKNOWN")
    except ValueError:
        pass
    else:
        raise AssertionError("an UNKNOWN fee accepted a figure")


def test_secondary_and_unknown_fees_cannot_be_quoted_as_a_take_rate():
    for claim in (FS.CURRENCY_CONVERSION, FS.REGULATORY_OPERATING):
        assert not claim.quotable
        for call in (lambda: claim.component(10.0),
                     lambda: FS.take_rate(10.0, (FS.TRANSACTION, claim))):
            try:
                call()
            except FS.FeeNotQuotable as e:
                assert claim.evidence in str(e)
            else:
                raise AssertionError(f"{claim.key} ({claim.evidence}) was quoted")


def test_the_default_take_rate_is_primary_only_and_names_what_it_left_out():
    out = FS.take_rate(10.0)
    assert out["components"] == {"transaction": 0.65, "payment_processing_canada": 0.55}
    assert out["take_rate"] == 0.12
    assert "regulatory_operating" in out["excluded"]
    assert "currency_conversion" in out["excluded"]
    assert out["read_on"] == PK.TOPICS["fees"].read_on


def test_the_modules_that_read_the_schedule_agree_with_it():
    from brambleloop.commerce import pricing
    from brambleloop.finance import currency
    from brambleloop.launch import readiness

    assert pricing.TRANSACTION_FEE == currency.DEFAULT_SCHEDULE.transaction == FS.TRANSACTION.rate
    assert pricing.PAYMENT_PERCENT == currency.DEFAULT_SCHEDULE.payment_percent \
        == FS.PAYMENT_PROCESSING.rate
    assert pricing.PAYMENT_FLAT_CAD == currency.DEFAULT_SCHEDULE.payment_flat \
        == FS.PAYMENT_PROCESSING.amount
    assert readiness.LISTING_FEE_USD == pricing.LISTING_FEE_USD == FS.LISTING.amount
    assert readiness.LISTING_FEE_CAD == pricing.LISTING_FEE_CAD \
        == FS.listing_fee_cad(currency.ASSUMED_USD_PER_CAD)
    assert "fee_schedule" in currency.DEFAULT_SCHEDULE.basis
    assert pricing.LISTING_RENEWAL_MONTHS == FS.LISTING_RENEWAL_MONTHS == 4


def test_the_literals_still_held_elsewhere_equal_the_schedule():
    """scale.target and integrations.etsy keep literals; they must not drift from the reading."""
    from brambleloop.integrations import etsy
    from brambleloop.scale import target

    assert target.TRANSACTION_FEE_RATE == FS.TRANSACTION.rate
    assert target.PAYMENT_PROCESSING_RATE == FS.PAYMENT_PROCESSING.rate
    assert target.PAYMENT_PROCESSING_FLAT_CAD == FS.PAYMENT_PROCESSING.amount
    assert target.LISTING_FEE_USD == FS.LISTING.amount
    assert etsy.LISTING_FEE_USD == FS.LISTING.amount


def test_the_listing_fee_conversion_refuses_a_nonsense_rate():
    try:
        FS.listing_fee_cad(0)
    except ValueError:
        pass
    else:
        raise AssertionError("converted at a rate of zero")
    assert FS.listing_fee_cad(0.715) == 0.28


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
    print(f"{sum(1 for n in globals() if n.startswith('test_')) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
