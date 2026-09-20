"""Economics in one reporting currency, with the transaction's own currency preserved.

Requirements 269 and the pricing half of 268. Normalise product economics into a canonical
reporting currency, **preserving** the transaction currency, the platform and payment fees,
the regulatory and conversion fees and the ad fees -- and make pricing decisions on net
contribution rather than sticker price.

The word that does the work is *preserving*. Converting a USD sale into CAD and storing only
the CAD figure destroys the one number that can later be reconciled against a bank statement,
and a books that cannot be reconciled is a books that will be argued with. So every amount
here carries the currency it happened in, the rate used, and the date that rate was taken --
and the rate is an assumption until a settlement statement replaces it, which is stated in
the row rather than in a footnote.

Two fee classes this company will meet that the existing model did not name:

**Currency conversion.** A marketplace converting a buyer's USD into a seller's CAD takes a
spread, and it is charged on the gross rather than the net. It is the fee most often left out
of a margin calculation, because it does not appear as a line item -- it appears as a slightly
worse rate.

**Regulatory operating fees.** Charged in several jurisdictions as a percentage of the order
total. Small, unavoidable, and the kind of thing that turns a thin margin negative without
anybody editing a spreadsheet.

Both default to zero here, and zero is honest: they are stated as assumptions with their
basis, so a margin computed without them says so rather than quietly omitting them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

REPORTING_CURRENCY = "CAD"

# The rate this company reports at until a settlement statement gives a real one. Stated as
# an assumption everywhere it is used, because a converted figure whose rate is invisible is
# indistinguishable from a measured one.
ASSUMED_USD_PER_CAD = 0.715

# Fee classes #269 names. Each is a rate on the gross unless stated, and each defaults to
# zero with its basis recorded -- a margin computed without a fee should say it was computed
# without it rather than look like a margin that included it.
@dataclass(frozen=True)
class FeeSchedule:
    transaction: float = 0.065
    payment_percent: float = 0.030
    payment_flat: float = 0.25
    # A marketplace converting the buyer's currency into the seller's takes a spread. It
    # never appears as a line item; it appears as a slightly worse rate, which is why it is
    # the fee most often missing from a margin.
    currency_conversion: float = 0.0
    # Charged in several jurisdictions as a percentage of the order total.
    regulatory_operating: float = 0.0
    # Advertising, where it applies to the order rather than to the account.
    ad_fee: float = 0.0
    basis: str = "Etsy's published rates; conversion and regulatory fees not yet observed"


DEFAULT_SCHEDULE = FeeSchedule()


class CurrencyRefused(ValueError):
    """A conversion with no rate, or an amount with no currency."""


@dataclass(frozen=True)
class Money:
    """An amount in the currency it actually happened in."""

    amount: float
    currency: str

    def __post_init__(self) -> None:
        if not self.currency or len(self.currency) != 3:
            raise CurrencyRefused(
                f"{self.currency!r} is not a currency code. An amount with no currency "
                f"cannot be reconciled against anything, which is the only thing a recorded "
                f"amount is for")

    def to_dict(self) -> dict:
        return {"amount": round(self.amount, 4), "currency": self.currency}


@dataclass(frozen=True)
class Rate:
    """One exchange rate, with where it came from and when."""

    usd_per_cad: float
    taken_on: date
    measured: bool = False
    source: str = "assumed"

    def to_dict(self) -> dict:
        return {"usd_per_cad": self.usd_per_cad, "taken_on": self.taken_on.isoformat(),
                "measured": self.measured, "source": self.source,
                "note": ("this rate came from a settlement statement"
                         if self.measured else
                         "assumed, and stated as such: a converted figure whose rate is "
                         "invisible is indistinguishable from a measured one")}


def assumed_rate(on: date | None = None) -> Rate:
    return Rate(ASSUMED_USD_PER_CAD, on or date.today(), measured=False, source="assumed")


def to_reporting(money: Money, rate: Rate) -> dict:
    """Convert into the reporting currency, keeping the original.

    Both halves are returned on purpose. Storing only the converted figure destroys the one
    number that can be reconciled against a bank statement, and books that cannot be
    reconciled will be argued with.
    """
    if money.currency == REPORTING_CURRENCY:
        return {"original": money.to_dict(), "reporting": money.to_dict(),
                "rate": None, "converted": False}
    if money.currency != "USD":
        raise CurrencyRefused(
            f"no rate on file for {money.currency}. Converting it with a rate this company "
            f"has not stated would produce a number nobody can check")
    if rate.usd_per_cad <= 0:
        raise CurrencyRefused("an exchange rate must be positive to convert with")
    return {
        "original": money.to_dict(),
        "reporting": Money(round(money.amount / rate.usd_per_cad, 4),
                           REPORTING_CURRENCY).to_dict(),
        "rate": rate.to_dict(),
        "converted": True,
    }


def contribution(price: Money, *, rate: Rate | None = None,
                 schedule: FeeSchedule = DEFAULT_SCHEDULE,
                 expected_sales_per_listing_period: float = 10.0,
                 listing_fee_usd: float = 0.20) -> dict:
    """What is left after every fee class, in the reporting currency and in the original.

    The requirement's closing sentence -- *pricing decisions use net contribution, not
    sticker price* -- is why this returns the net first and the sticker price as context
    rather than the other way round.
    """
    rate = rate or assumed_rate()
    converted = to_reporting(price, rate)
    gross = converted["reporting"]["amount"]

    fees = {
        "transaction": round(gross * schedule.transaction, 4),
        "payment": round(gross * schedule.payment_percent + schedule.payment_flat, 4),
        "currency_conversion": round(gross * schedule.currency_conversion, 4),
        "regulatory_operating": round(gross * schedule.regulatory_operating, 4),
        "ad_fee": round(gross * schedule.ad_fee, 4),
        "listing_amortised": round(
            (listing_fee_usd / rate.usd_per_cad) / max(1.0, expected_sales_per_listing_period),
            4),
    }
    total = round(sum(fees.values()), 4)
    net = round(gross - total, 4)
    unobserved = [name for name in ("currency_conversion", "regulatory_operating", "ad_fee")
                  if not fees[name]]
    return {
        "sticker": converted["original"],
        "gross_reporting": Money(gross, REPORTING_CURRENCY).to_dict(),
        "fees": fees,
        "total_fees": total,
        "net_contribution": Money(net, REPORTING_CURRENCY).to_dict(),
        "take_rate": round(total / gross, 4) if gross else 0.0,
        "rate": converted["rate"],
        "fees_not_yet_observed": unobserved,
        "basis": schedule.basis,
        "why": (f"net contribution is CA${net:.2f} of a CA${gross:.2f} gross, a "
                f"{(total / gross if gross else 0):.1%} take. "
                + (f"{unobserved} are zero because this company has not been charged them "
                   f"yet -- a margin computed without a fee should say so rather than look "
                   f"like one that included it" if unobserved else
                   "every fee class the requirement names is priced")),
    }
