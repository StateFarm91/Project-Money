"""Pricing intelligence (Master Plan sections 9, 34).

Two rules shape everything here.

The category runs a near-universal fake sale: almost every competitor we profiled shows
"50% off" against a struck-through price that is never charged. Section 9 forbids us doing
that, so we cannot win on apparent discount and must price at a real number we can defend.

And a price is not revenue. Etsy takes a transaction fee, a payment-processing percentage and
a flat per-order charge, so the contribution on a CA$4.50 pattern is a different business
from the one the sticker suggests. Every figure this module produces is net of fees, because
a pricing decision made on gross is a decision made on a number that never reaches the bank.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Etsy's published Canadian rates as observed 2026-09-17. Listing fees are per-listing and
# amortised separately; these are the per-sale charges.
TRANSACTION_FEE = 0.065
PAYMENT_PERCENT = 0.030
PAYMENT_FLAT_CAD = 0.25
LISTING_FEE_CAD = 0.20          # USD 0.20, charged per listing and per renewal
LISTING_RENEWAL_MONTHS = 4      # a listing runs four months before it renews

# Regulatory floor: the offer must be a real offer. A reference price we never charged is a
# deceptive discount whatever the category does.
MIN_PRICE_CAD = 3.00


# ---------------------------------------------------------------------------
# The fees this model does not include
# ---------------------------------------------------------------------------
#
# Added 2026-09-25 by the Etsy surface registry work, which found the reason they cannot
# simply be added: `intel/etsy_surfaces.py` records that the string "offsite" appears **zero**
# times in Etsy's published OpenAPI document -- not as an endpoint, not as a setting, and not
# as a fee line on a receipt, a payment or a ledger entry. So the largest fee this shop may
# pay is one that cannot be read back from a settlement, and Etsy's own fee schedule at
# etsy.com/legal/fees is HTTP 403 to every automated request from this environment.
#
# The wrong fix is to pick a rate off a third-party blog and fold it into TRANSACTION_FEE.
# That would turn a figure nobody has verified into a figure that looks measured, and every
# number downstream would inherit the confidence without the evidence. The right fix is to
# make the incompleteness travel with the answer: `fees()` is unchanged and still returns the
# modelled fees, `worst_case_fees()` shows what the same price looks like if the secondary
# rates are right, and `FeeBreakdown.to_dict` carries the names of what is missing so no
# consumer of this module can quote a take rate as complete.

#: (key, what it is, basis, rate if the secondary source is right, when it applies)
UNMODELLED_FEES: tuple[tuple[str, str, str, float, str], ...] = (
    ("offsite_ads",
     "Etsy's fee on an order it attributes to an advert it placed off Etsy",
     "SECONDARY -- third-party reports of 12% or 15%; etsy.com/legal/fees is 403 from here",
     0.15,
     "only on attributed orders, and reportedly compulsory below a revenue threshold"),
    ("regulatory_operating_fee",
     "a country-specific operating fee Etsy charges in some jurisdictions",
     "SECONDARY and contested -- some third-party sources report ~1.15% for Canada and "
     "others report none",
     0.0115,
     "every order, if Canada carries it at all"),
    ("currency_conversion",
     "Etsy's conversion charge when the buyer pays in a currency other than the shop's",
     "SECONDARY -- commonly reported at 2.5%; unreadable from here",
     0.025,
     "orders paid in a currency other than CAD, which for an international pattern shop is "
     "most of them"),
)

#: The single worst case: every unmodelled fee applying at its reported rate at once. It is
#: not a forecast and must never be quoted as one -- offsite attribution and currency
#: conversion will not both apply to every order. It is the floor's floor: if the price
#: survives this, no fee surprise can take it under water.
WORST_CASE_EXTRA_RATE = round(sum(rate for _k, _w, _b, rate, _when in UNMODELLED_FEES), 4)


@dataclass(frozen=True)
class FeeBreakdown:
    price_cad: float
    transaction_fee: float
    payment_fee: float
    listing_amortised: float

    @property
    def total_fees(self) -> float:
        return round(self.transaction_fee + self.payment_fee + self.listing_amortised, 4)

    @property
    def net_cad(self) -> float:
        return round(self.price_cad - self.total_fees, 4)

    @property
    def take_rate(self) -> float:
        return round(self.total_fees / self.price_cad, 4) if self.price_cad else 0.0

    @property
    def unmodelled(self) -> tuple[str, ...]:
        """The fees this breakdown does not contain, by name.

        Carried on the object rather than written in a comment, because a take rate quoted
        without it reads as the whole cost of selling and is not.
        """
        return tuple(k for k, _w, _b, _r, _when in UNMODELLED_FEES)

    def to_dict(self) -> dict:
        return {"price_cad": self.price_cad, "transaction_fee": round(self.transaction_fee, 4),
                "payment_fee": round(self.payment_fee, 4),
                "listing_amortised": round(self.listing_amortised, 4),
                "total_fees": self.total_fees, "net_cad": self.net_cad,
                "take_rate": self.take_rate,
                "unmodelled_fees": list(self.unmodelled),
                "take_rate_is_a_floor": True}


def fees(price_cad: float, expected_sales_per_listing_period: float = 10.0) -> FeeBreakdown:
    """Per-sale fees, with the listing fee amortised over expected sales.

    Amortising matters at this price point. A listing fee spread over ten sales is two cents;
    spread over one sale it is twenty, which is four percent of a CA$4.50 pattern and the
    difference between a viable cheap SKU and a pointless one.
    """
    n = max(1.0, expected_sales_per_listing_period)
    return FeeBreakdown(
        price_cad=round(price_cad, 2),
        transaction_fee=price_cad * TRANSACTION_FEE,
        payment_fee=price_cad * PAYMENT_PERCENT + PAYMENT_FLAT_CAD,
        listing_amortised=LISTING_FEE_CAD / n,
    )


def worst_case_fees(price_cad: float,
                    expected_sales_per_listing_period: float = 10.0) -> dict:
    """The same price with every unmodelled fee applied at its reported rate.

    Returns a dict rather than a `FeeBreakdown` deliberately: a second FeeBreakdown would be
    passed around and eventually quoted as *the* fee model, and these rates are secondary and
    contested. A dict with `basis` on every line resists that.
    """
    modelled = fees(price_cad, expected_sales_per_listing_period)
    extras = [{"key": key, "what": what, "basis": basis, "rate": rate,
               "applies_when": when, "amount_cad": round(price_cad * rate, 4)}
              for key, what, basis, rate, when in UNMODELLED_FEES]
    extra_total = round(sum(e["amount_cad"] for e in extras), 4)
    total = round(modelled.total_fees + extra_total, 4)
    return {
        "price_cad": round(price_cad, 2),
        "modelled": modelled.to_dict(),
        "unmodelled": extras,
        "unmodelled_total_cad": extra_total,
        "worst_case_total_fees_cad": total,
        "worst_case_net_cad": round(price_cad - total, 4),
        "worst_case_take_rate": round(total / price_cad, 4) if price_cad else 0.0,
        "note": "Not a forecast. Offsite attribution and currency conversion will not both "
                "apply to every order. This is the answer to 'what if every uncertain fee "
                "is real at once', and it is the only figure here that cannot be an "
                "understatement.",
    }


@dataclass
class PriceDecision:
    slug: str
    price_cad: float
    floor_cad: float
    ceiling_cad: float
    net_cad: float
    take_rate: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"slug": self.slug, "price_cad": self.price_cad, "floor_cad": self.floor_cad,
                "ceiling_cad": self.ceiling_cad, "net_cad": self.net_cad,
                "take_rate": self.take_rate, "reasons": list(self.reasons),
                "warnings": list(self.warnings)}


class DeceptivePricing(ValueError):
    """A pricing move that would mislead a buyer. Never raised away by configuration."""


def decide_price(slug: str, *, category_band_cad: tuple[float, float],
                 proposed_cad: float, has_video: bool = False,
                 sizes_offered: int = 1, is_bundle: bool = False,
                 bundle_members_cad: list[float] | None = None,
                 expected_sales: float = 10.0) -> PriceDecision:
    """Land on a defensible price inside the observed band, with the reasoning recorded.

    Deliberately conservative about premiums. The category's top sellers charge CA$8.50-14 for
    pattern-plus-video, and we have no reviews. Charging above the band on day one asks a
    buyer to take a risk on an unknown shop at a premium, which is the one thing our position
    cannot support.
    """
    lo, hi = category_band_cad
    reasons: list[str] = []
    warnings: list[str] = []

    price = float(proposed_cad)
    if has_video:
        reasons.append("pattern + video is table stakes in this category, not a premium")
    if sizes_offered > 1:
        reasons.append(f"{sizes_offered} finished sizes from one chart, which no profiled "
                       f"competitor offers")

    if is_bundle:
        members = bundle_members_cad or []
        if len(members) < 2:
            raise DeceptivePricing(
                f"{slug}: a bundle priced without at least two real member prices cannot "
                f"show an honest saving")
        member_total = round(sum(members), 2)
        if price >= member_total:
            raise DeceptivePricing(
                f"{slug}: bundle at CA${price:.2f} is not cheaper than its members bought "
                f"separately (CA${member_total:.2f}); that is not a bundle, it is a markup")
        lo, hi = member_total * 0.55, member_total * 0.9

    if price < MIN_PRICE_CAD:
        warnings.append(f"below the CA${MIN_PRICE_CAD:.2f} floor; fees eat most of it")
        price = MIN_PRICE_CAD
    if price > hi:
        warnings.append(
            f"CA${price:.2f} is above the observed band top of CA${hi:.2f}; with no review "
            f"history a premium price is asking a buyer to take an unrewarded risk")
        price = round(hi, 2)
    if price < lo:
        reasons.append(f"priced below the band floor of CA${lo:.2f} deliberately, to buy "
                       f"early reviews rather than early margin")

    if is_bundle:
        # Computed from the price we actually landed on, not the one we proposed: a saving
        # quoted against a price we then changed is the same lie as a reference price.
        member_total = round(sum(bundle_members_cad or []), 2)
        saving = round(member_total - price, 2)
        reasons.append(
            f"saves CA${saving:.2f} ({saving / member_total:.0%}) against CA${member_total:.2f} "
            f"for the same patterns bought separately -- a real saving against prices we "
            f"actually charge, not a struck-through reference price")

    f = fees(price, expected_sales)
    if f.net_cad < 1.0:
        warnings.append(f"net CA${f.net_cad:.2f} per sale after fees: this SKU earns its "
                        f"place through reviews and cross-sell, not margin")

    # The take rate above is a floor, not the cost of selling. Etsy publishes no API for
    # Offsite Ads -- the word does not appear once in its OpenAPI document, not even as a fee
    # line -- so the largest charge this shop may face cannot be read back from a settlement
    # and cannot be ceilinged in code. The only defence software has is a price that survives
    # it, so the decision says out loud what the worst case does to the margin.
    worst = worst_case_fees(price, expected_sales)
    warnings.append(
        f"take rate {f.take_rate:.1%} excludes {', '.join(f.unmodelled)}; if all three apply "
        f"at their reported rates the take rate is {worst['worst_case_take_rate']:.1%} and "
        f"the net is CA${worst['worst_case_net_cad']:.2f}. Those rates are SECONDARY -- "
        f"etsy.com/legal/fees is 403 to automated readers")
    if worst["worst_case_net_cad"] < 0:
        warnings.append(
            f"CA${price:.2f} does not survive the worst-case fee stack at all "
            f"(net CA${worst['worst_case_net_cad']:.2f}): an attributed order at this price "
            f"would cost money to fulfil")
    return PriceDecision(slug=slug, price_cad=round(price, 2), floor_cad=round(lo, 2),
                         ceiling_cad=round(hi, 2), net_cad=f.net_cad, take_rate=f.take_rate,
                         reasons=reasons, warnings=warnings)


def check_no_fake_discount(price_cad: float, reference_price_cad: float | None,
                           ever_charged: bool) -> None:
    """A struck-through price we never charged is a lie, however normal it is here.

    Section 9 and the Execution Directive both forbid deceptive discounts, and Canadian
    consumer-protection law treats an ordinary-price claim as one the seller must be able to
    substantiate. The whole category does this; it is still not available to us.
    """
    if reference_price_cad is None:
        return
    if not ever_charged:
        raise DeceptivePricing(
            f"cannot display CA${reference_price_cad:.2f} as a was-price: this product has "
            f"never been sold at that price")
    if reference_price_cad <= price_cad:
        raise DeceptivePricing(
            f"reference price CA${reference_price_cad:.2f} is not above the current price "
            f"CA${price_cad:.2f}; displaying it implies a discount that does not exist")


def contribution(price_cad: float, units: int, expected_sales: float = 10.0) -> dict:
    """Contribution for a run of units. Marginal cost of a digital file is zero; fees are not."""
    f = fees(price_cad, expected_sales)
    return {"units": units, "gross_cad": round(price_cad * units, 2),
            "fees_cad": round(f.total_fees * units, 2),
            "contribution_cad": round(f.net_cad * units, 2),
            "net_per_unit_cad": f.net_cad}
