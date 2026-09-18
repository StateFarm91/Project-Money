"""CA$5,000 a month, decomposed into paths somebody could actually walk.

Requirements 229, 269, 273. The target is a run rate, and a run rate is a product of five
numbers: qualified visits, conversion, average order value, repeat rate and whatever arrives
outside Etsy. Writing "CA$5,000" on a plan does nothing; writing *250 orders at CA$20, which
needs 12,500 qualified visits at a 2% conversion* says what would have to be true.

Two rules keep the arithmetic honest.

**Gross is not contribution.** Etsy takes a listing fee, a transaction fee and payment
processing, and the owner is paid in CAD while the marketplace prices in USD. A scenario that
reaches CA$5,000 gross and CA$3,900 net is a different scenario from one that reaches
CA$5,000 net, and conflating them is how a target gets hit on paper and missed in the bank.
Every scenario carries both.

**A scenario built on an assumed conversion rate is labelled as one.** #273 ends with the line
that matters: the CEO chooses the most evidence-supported path, not the prettiest spreadsheet.
So `required_visits` needs a conversion rate, and the scenario records whether that rate was
observed or assumed, and over what sample. A path that looks easy because its conversion came
from optimism is exactly what this module exists to expose.
"""
from __future__ import annotations

from dataclasses import dataclass

TARGET_CAD_PER_MONTH = 5000.0

# Etsy's published rates. Not our preferences, and not negotiable by us.
LISTING_FEE_USD = 0.20
TRANSACTION_FEE_RATE = 0.065
PAYMENT_PROCESSING_RATE = 0.030
PAYMENT_PROCESSING_FLAT_CAD = 0.25
# Etsy charges the shop in USD while the owner banks in CAD. The rate is an assumption and is
# labelled one everywhere it is used.
USD_PER_CAD = 0.715

# A digital pattern has no cost of goods, so contribution is revenue minus platform fees and
# whatever acquisition costs. That is the whole model, which is why it is worth stating.


@dataclass(frozen=True)
class Fees:
    transaction_cad: float
    processing_cad: float
    listing_cad: float

    @property
    def total_cad(self) -> float:
        return round(self.transaction_cad + self.processing_cad + self.listing_cad, 2)


def fees_on(gross_cad: float, orders: int, *, listings_renewed: int = 0) -> Fees:
    """Platform fees on a month's gross, per Etsy's published rates."""
    transaction = gross_cad * TRANSACTION_FEE_RATE
    processing = gross_cad * PAYMENT_PROCESSING_RATE + orders * PAYMENT_PROCESSING_FLAT_CAD
    listing = listings_renewed * (LISTING_FEE_USD / USD_PER_CAD)
    return Fees(round(transaction, 2), round(processing, 2), round(listing, 2))


@dataclass(frozen=True)
class Scenario:
    """One path to the target, and what would have to be true for it to happen."""

    name: str
    orders_per_month: int
    aov_cad: float
    conversion_rate: float
    conversion_basis: str          # "observed" | "assumed"
    conversion_sample: int
    repeat_share: float
    off_platform_share: float
    ad_spend_cad: float
    refund_rate: float

    @property
    def gross_cad(self) -> float:
        return round(self.orders_per_month * self.aov_cad, 2)

    @property
    def required_visits(self) -> int:
        """Qualified visits the scenario needs. The number that is usually missing.

        Repeat buyers and off-platform sales do not arrive through the same funnel, so only
        the new-on-Etsy share is divided by the conversion rate. Ignoring that overstates the
        traffic requirement and makes every scenario look impossible; ignoring the split
        entirely makes them all look easy.
        """
        if self.conversion_rate <= 0:
            return 0
        new_on_platform = self.orders_per_month * (
            1 - self.repeat_share) * (1 - self.off_platform_share)
        return int(round(new_on_platform / self.conversion_rate))

    def contribution(self, listings_renewed: int = 0) -> dict:
        gross = self.gross_cad
        refunds = round(gross * self.refund_rate, 2)
        fees = fees_on(gross - refunds, self.orders_per_month,
                       listings_renewed=listings_renewed)
        net = round(gross - refunds - fees.total_cad - self.ad_spend_cad, 2)
        return {
            "gross_cad": gross, "refunds_cad": refunds,
            "fees_cad": fees.total_cad, "ad_spend_cad": self.ad_spend_cad,
            "contribution_cad": net,
            "contribution_margin": round(net / gross, 4) if gross else 0.0,
            "reaches_target_gross": gross >= TARGET_CAD_PER_MONTH,
            "reaches_target_contribution": net >= TARGET_CAD_PER_MONTH,
        }

    def to_dict(self, listings_renewed: int = 0) -> dict:
        return {
            "name": self.name,
            "orders_per_month": self.orders_per_month,
            "aov_cad": self.aov_cad,
            "required_visits": self.required_visits,
            "conversion": {
                "rate": self.conversion_rate,
                "basis": self.conversion_basis,
                "sample": self.conversion_sample,
                # The line that stops a pretty spreadsheet winning: a path built on an
                # assumed rate is not comparable to one built on a measured one.
                "trustworthy": self.conversion_basis == "observed"
                               and self.conversion_sample >= 200,
            },
            "repeat_share": self.repeat_share,
            "off_platform_share": self.off_platform_share,
            **self.contribution(listings_renewed),
        }


# The spec's own examples, plus the mixed compositions it asks for. Every conversion rate here
# is `assumed` until the shop has sold anything, and is labelled so on every row.
#
# 2% is a commonly quoted Etsy digital-product conversion rate. It is an industry rule of
# thumb, not this shop's number, and nothing here treats it as evidence.
ASSUMED_CONVERSION = 0.02


def default_scenarios(conversion_rate: float = ASSUMED_CONVERSION,
                      basis: str = "assumed", sample: int = 0) -> list[Scenario]:
    """The scenario matrix (#273), computed rather than tabulated."""
    def s(name: str, orders: int, aov: float, repeat: float = 0.0,
          off: float = 0.0, ads: float = 0.0, refunds: float = 0.01) -> Scenario:
        return Scenario(name, orders, aov, conversion_rate, basis, sample,
                        repeat, off, ads, refunds)

    return [
        s("volume: 250 orders x CA$20", 250, 20.0),
        s("balanced: 200 orders x CA$25", 200, 25.0),
        s("premium: 167 orders x CA$30", 167, 30.0),
        s("premium + bundles: 125 orders x CA$40", 125, 40.0),
        s("balanced with repeat: 200 x CA$25, 30% repeat", 200, 25.0, repeat=0.30),
        s("mixed channel: 200 x CA$25, 25% off-Etsy", 200, 25.0, off=0.25),
        s("paid-assisted: 200 x CA$25 with CA$400 ads", 200, 25.0, ads=400.0),
    ]


def matrix(conversion_rate: float = ASSUMED_CONVERSION, basis: str = "assumed",
           sample: int = 0, listings: int = 0) -> dict:
    """Every path, with the traffic each needs and what it nets."""
    scenarios = [x.to_dict(listings) for x in
                 default_scenarios(conversion_rate, basis, sample)]
    trustworthy = [x for x in scenarios if x["conversion"]["trustworthy"]]
    return {
        "target_cad_per_month": TARGET_CAD_PER_MONTH,
        "scenarios": sorted(scenarios, key=lambda x: x["required_visits"]),
        "evidence_supported_paths": len(trustworthy),
        "fee_model": {
            "transaction_rate": TRANSACTION_FEE_RATE,
            "processing_rate": PAYMENT_PROCESSING_RATE,
            "processing_flat_cad": PAYMENT_PROCESSING_FLAT_CAD,
            "listing_fee_usd": LISTING_FEE_USD,
            "usd_per_cad_assumed": USD_PER_CAD,
        },
        "note": ("Every scenario here rests on an assumed conversion rate until the shop has "
                 "sold something. None of them is evidence, and the most attractive row is "
                 "the one to distrust: it is attractive because its assumptions are, not "
                 "because its path is easier (#273)."
                 if not trustworthy else
                 "Conversion is measured. The evidence-supported paths are the only ones the "
                 "CEO may choose between."),
    }


def binding_constraint(observed: dict) -> dict:
    """Which of the five numbers is furthest from what the target needs (#229).

    Answered as a ratio rather than a gap, because a shortfall of 400 visits and a shortfall
    of 0.4% conversion are not comparable in absolute terms and are directly comparable as
    multiples of where they need to be.
    """
    needed = {
        "qualified_visits": 200 / ASSUMED_CONVERSION,   # the balanced scenario's funnel
        "conversion_rate": ASSUMED_CONVERSION,
        "aov_cad": 25.0,
        "orders_per_month": 200,
    }
    gaps = []
    for key, target in needed.items():
        actual = float(observed.get(key) or 0.0)
        ratio = actual / target if target else 0.0
        gaps.append({"metric": key, "observed": actual, "needed": target,
                     "share_of_needed": round(ratio, 4)})
    gaps.sort(key=lambda g: g["share_of_needed"])
    return {
        "binding": gaps[0]["metric"],
        "gaps": gaps,
        "note": ("Ranked by how far each number is from what the balanced scenario needs, as "
                 "a share rather than a difference, so a traffic gap and a conversion gap "
                 "are comparable."),
    }
