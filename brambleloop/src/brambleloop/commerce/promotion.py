"""Promotions measured by what they leave behind, not by what they move.

Requirement 19. Genuine time-bounded sales, coupons and order minimums, only when policy
allows -- and then the sentence that decides the module: *measure incremental conversion,
AOV and contribution, not merely revenue lift.*

Revenue lift is the number that hides a discount's cost. Take twenty percent off and sell
fifteen percent more units: revenue moves one way and the money left over moves the other,
and a promotion judged on the first will be repeated until the catalogue cannot sell without
it -- which is the third thing the requirement forbids.

One honest qualification, because the module would otherwise imply a danger it cannot
demonstrate. For a digital pattern the marginal cost of a sale is nearly zero, so revenue and
contribution largely move *together*: a discount pays whenever units rise enough to cover the
cut, and both numbers say so. They come apart once a real per-order cost exists -- the flat
component of the platform fee, which is modelled here, and the cost to create the pattern
amortised over the units it sells, which is #31 and waits on there being units. So this
reports both and says when they are telling you the same thing, rather than warning about a
divergence this business cannot currently have.

So three machines, and each refuses something.

**A promotion must end, and the end must be a date.** Not a policy, not an intention. A sale
with no end date is a price, and a price presented as a sale is a claim about an ordinary
price the seller has to be able to substantiate. `pricing.check_no_fake_discount` already
refuses a was-price that was never charged; this refuses the other half, which is the
was-price that never stops.

**Incrementality needs a control, and contribution needs both arms.** Without a full-price
arm, the discounted arm's conversion rate is a fact about people who were shown a discount.
`elasticity.holdout` already established this for bought traffic; a promotion is the same
question with a different lever.

**Dependency is measured on the catalogue, not on a feeling.** How much of the catalogue is
on sale, for how long, and whether anything sells at full price. The first two are countable
today; the third needs orders and says so.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# The longest a genuine promotion may run. Matches the policy gate's perpetual-sale rule,
# because they are the same judgement: past this, the discounted price is the ordinary price
# and the struck-through one is decoration.
MAX_PROMOTION_DAYS = 45

# Above this share of the catalogue on sale at once, the catalogue is not running a promotion,
# it is running a lower price list. Set below a half deliberately: at a half, "on sale" stops
# describing anything.
CATALOGUE_DEPENDENCE_ABOVE = 0.30

# A discount steeper than this is not a promotion, it is a repricing, and the was-price stops
# being substantiable as the ordinary price.
STEEP_DISCOUNT_ABOVE = 0.40


class PromotionRefused(ValueError):
    """A promotion that is not time-bounded, not substantiable, or not a promotion."""


@dataclass(frozen=True)
class Promotion:
    """A time-bounded price reduction, with the two dates that make it one."""

    product_slug: str
    full_price_cad: float
    promo_price_cad: float
    starts: date
    ends: date
    reason: str

    @property
    def days(self) -> int:
        return (self.ends - self.starts).days

    @property
    def discount(self) -> float:
        if self.full_price_cad <= 0:
            return 0.0
        return round(1.0 - self.promo_price_cad / self.full_price_cad, 4)

    def to_dict(self) -> dict:
        return {"product": self.product_slug, "full_price_cad": self.full_price_cad,
                "promo_price_cad": self.promo_price_cad, "starts": self.starts.isoformat(),
                "ends": self.ends.isoformat(), "days": self.days,
                "discount": self.discount, "reason": self.reason}


def propose(product_slug: str, *, full_price_cad: float, promo_price_cad: float,
            starts: date, ends: date, reason: str, ever_charged_full: bool) -> Promotion:
    """Build a promotion, or refuse it and say which rule it broke.

    `ever_charged_full` is the substantiation the was-price needs. A promotion against a
    price this shop has never charged is a struck-through number invented to make the real
    one look like a saving, and the whole category does it.
    """
    from .pricing import DeceptivePricing, check_no_fake_discount

    if not reason.strip():
        raise PromotionRefused(
            "a promotion with no stated reason is a price cut looking for one. The reason is "
            "what makes it a campaign that can end rather than a new price")
    if ends <= starts:
        raise PromotionRefused(
            f"a promotion must end after it starts; {starts} to {ends} is not a window")
    days = (ends - starts).days
    if days > MAX_PROMOTION_DAYS:
        raise PromotionRefused(
            f"{days} days is not a promotion. Past {MAX_PROMOTION_DAYS} the discounted price "
            f"is the ordinary price and the struck-through one is decoration, which is the "
            f"claim consumer law requires a seller to substantiate")
    if promo_price_cad >= full_price_cad:
        raise PromotionRefused(
            f"CA${promo_price_cad:.2f} is not below CA${full_price_cad:.2f}, so this "
            f"promotion discounts nothing")

    promotion = Promotion(product_slug, full_price_cad, promo_price_cad, starts, ends, reason)
    if promotion.discount > STEEP_DISCOUNT_ABOVE:
        raise PromotionRefused(
            f"a {promotion.discount:.0%} reduction is a repricing rather than a promotion, "
            f"and the was-price stops being substantiable as the ordinary price at that "
            f"depth")
    try:
        check_no_fake_discount(promo_price_cad, full_price_cad, ever_charged_full)
    except DeceptivePricing as e:
        raise PromotionRefused(str(e)) from e
    return promotion


def incrementality(promotion: Promotion, *, full_price_arm, discounted_arm,
                   unit_cost_cad: float = 0.0) -> dict:
    """What the promotion actually did, measured on contribution rather than on revenue.

    The three numbers the requirement names, and the order matters. Conversion says whether
    more people bought. AOV says whether they bought differently. **Contribution says whether
    the company is better off**, and it is the one a revenue chart cannot show: a discount
    that lifts revenue while lowering contribution looks like a success in every direction
    except the one that pays for anything.
    """
    from .elasticity import holdout

    separable = holdout(full_price_arm, discounted_arm)
    if not separable.get("separable"):
        return {
            "measurable": False,
            "reason": separable.get("reason", ""),
            "why_it_matters": ("without a full-price arm the discounted conversion rate is a "
                               "fact about people who were shown a discount, and repeating "
                               "the promotion on it is how a catalogue learns it cannot sell "
                               "without one"),
        }

    from .pricing import fees

    def _aov(arm):
        return round(arm.revenue_cad / arm.orders, 2) if arm.orders else 0.0

    def _net_per_order(price: float) -> float:
        # The real per-order economics, not price minus a guess. Platform fees carry a flat
        # component as well as a percentage, so each additional order costs something even
        # when the file itself costs nothing to send -- which is the only reason contribution
        # can diverge from revenue for a digital product at all.
        return round(fees(price).net_cad - unit_cost_cad, 4)

    def _contribution(arm, price):
        return round(arm.orders * _net_per_order(price), 2)

    control_aov = _aov(full_price_arm)
    promo_aov = _aov(discounted_arm)
    control_contribution = _contribution(full_price_arm, promotion.full_price_cad)
    promo_contribution = _contribution(discounted_arm, promotion.promo_price_cad)

    # What the control's own rate would have produced on the promoted traffic, so the
    # comparison is like for like rather than a bigger sample beating a smaller one.
    expected_orders = round(full_price_arm.conversion * discounted_arm.visits)
    # Net of fees on both sides. The first version compared the *gross* full price against
    # the net promo price, which manufactures a contribution loss out of the fee schedule --
    # a divergence that looks exactly like the one this module exists to warn about, and is
    # an arithmetic error rather than a finding.
    expected_contribution = round(
        expected_orders * _net_per_order(promotion.full_price_cad), 2)

    revenue_lift = round(discounted_arm.revenue_cad - full_price_arm.revenue_cad, 2)
    contribution_change = round(promo_contribution - expected_contribution, 2)
    bought_revenue_lost_contribution = revenue_lift > 0 and contribution_change < 0

    return {
        "measurable": True,
        "promotion": promotion.to_dict(),
        "conversion": {
            "full_price": round(full_price_arm.conversion, 5),
            "discounted": round(discounted_arm.conversion, 5),
            "lift": separable["conversion_lift"],
        },
        "aov_cad": {"full_price": control_aov, "discounted": promo_aov,
                    "change": round(promo_aov - control_aov, 2)},
        "contribution_cad": {
            "at_full_price_on_the_same_traffic": expected_contribution,
            "actual_at_promo_price": promo_contribution,
            "change": contribution_change,
        },
        "incremental_orders": separable["incremental_orders"],
        "revenue_lift_cad": revenue_lift,
        "bought_revenue_and_lost_contribution": bought_revenue_lost_contribution,
        "net_per_order_cad": {
            "full_price": _net_per_order(promotion.full_price_cad),
            "discounted": _net_per_order(promotion.promo_price_cad),
        },
        "when_these_two_diverge": (
            "for a digital pattern the marginal cost of a sale is nearly zero, so revenue "
            "and contribution move together and a discount is worth it whenever units rise "
            "enough to cover the price cut. They come apart once a real per-order cost "
            "exists -- the flat part of the platform fee, and the cost to create the pattern "
            "amortised over the units it sells (#31). Pass unit_cost_cad to see that, and "
            "until cost-to-create has units to divide by, the honest reading is that these "
            "two numbers are telling you the same thing"),
        "verdict": ("worth repeating" if contribution_change > 0 else
                    "bought revenue and lost contribution"
                    if bought_revenue_lost_contribution else
                    "not worth repeating"),
        "why": (f"contribution moved CA${contribution_change:+.2f} against what the same "
                f"traffic would have produced at full price. Revenue moved "
                f"CA${revenue_lift:+.2f}, and a discount that lifts the second while "
                f"lowering the first looks like a success in every direction except the one "
                f"that pays for anything"),
    }


def dependence(db, *, today: date | None = None) -> dict:
    """Is the catalogue being conditioned to require discounts?

    Two of the three answers are countable today. The third -- whether anything still sells
    at full price -- needs orders, and it is reported as unmeasurable rather than assumed,
    because a catalogue with no sales at all has no full-price sales either and that is not
    the same finding.
    """
    from sqlalchemy import select

    from ..core.models import LedgerEntry, Listing

    today = today or date.today()
    with db.session() as s:
        listings = [{"slug": r.product_slug, "price": r.price_cad} for r in
                    s.scalars(select(Listing))]
        has_orders = bool(s.scalar(select(LedgerEntry.id).limit(1)))

    if not listings:
        return {"measurable": False,
                "reason": ("no listing exists, so what share of the catalogue is discounted "
                           "is not a question this company can answer yet"),
                "full_price_sales": {"measurable": False,
                                     "reason": "no orders exist"}}

    # Shadow mode drafts carry no promotion, so this reads zero by construction today. It is
    # computed from rows rather than asserted so that it stops reading zero by itself.
    on_sale = [row for row in listings if row.get("on_sale")]
    share = round(len(on_sale) / len(listings), 3)
    return {
        "measurable": True,
        "listings": len(listings),
        "on_sale": len(on_sale),
        "share_on_sale": share,
        "threshold": CATALOGUE_DEPENDENCE_ABOVE,
        "conditioned": share > CATALOGUE_DEPENDENCE_ABOVE,
        "full_price_sales": (
            {"measurable": False,
             "reason": ("no order exists, so whether anything sells at full price is "
                        "unknown. A catalogue with no sales has no full-price sales either, "
                        "and that is a different finding from one that has stopped having "
                        "them")}
            if not has_orders else {"measurable": True}),
        "why": (f"{len(on_sale)} of {len(listings)} listings are discounted. Above "
                f"{CATALOGUE_DEPENDENCE_ABOVE:.0%} the catalogue is not running a promotion, "
                f"it is running a lower price list, and 'on sale' stops describing anything"),
    }


def window(promotion: Promotion, today: date) -> dict:
    """Where a live promotion is in its own window, so it can be ended rather than forgotten."""
    if today < promotion.starts:
        return {"state": "scheduled", "days_remaining": promotion.days,
                "why": f"starts {promotion.starts.isoformat()}"}
    if today >= promotion.ends:
        return {"state": "over", "days_remaining": 0,
                "why": (f"ended {promotion.ends.isoformat()}. A promotion left running past "
                        f"its own end date is the mechanism by which a sale becomes a price")}
    return {"state": "running",
            "days_remaining": (promotion.ends - today).days,
            "why": f"ends {promotion.ends.isoformat()}"}
