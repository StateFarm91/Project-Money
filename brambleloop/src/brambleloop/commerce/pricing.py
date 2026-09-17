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

    def to_dict(self) -> dict:
        return {"price_cad": self.price_cad, "transaction_fee": round(self.transaction_fee, 4),
                "payment_fee": round(self.payment_fee, 4),
                "listing_amortised": round(self.listing_amortised, 4),
                "total_fees": self.total_fees, "net_cad": self.net_cad,
                "take_rate": self.take_rate}


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
