"""Pricing Intelligence (Master Plan section 9).

Section 9 asks for six things: a Market Price Scanner, a Price Positioning Agent, a Promotion
Agent, a Price Experiment Agent, a Bundle Economist and a Revenue Optimizer. `pricing.py`
already holds positioning and the fee arithmetic. This holds the rest.

The objective is stated in the plan and is worth repeating because it is counter-intuitive:
**optimise expected contribution profit per visitor, not cheapest price and not gross
revenue.** A cheaper pattern converts better and can still earn less per visitor, and a
higher price can earn more in total while quietly killing the review accumulation a new shop
depends on. So every recommendation here is expressed per visitor, net of fees.

Two things this module will not do, both from section 9 and the Execution Directive. It will
not invent a regular price that was never charged, and it will not run a promotion that a
policy check has not seen. Both are enforced in code rather than left to intent.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from ..radar.market import COMPETITORS
from .pricing import DeceptivePricing, fees

# Below this many observations a difference between two prices is noise. Section 9 calls for
# minimum-data thresholds; this is that threshold for a pricing test.
MIN_OBSERVATIONS_PER_ARM = 200

# A pattern's marginal cost is zero, so a price test's "loss" is the contribution given up
# against the incumbent price, not a cash outlay. Capped anyway.
DEFAULT_MAX_TEST_LOSS_CAD = 25.0


# ---- market price scanner --------------------------------------------------


@dataclass(frozen=True)
class PriceObservation:
    shop: str
    category: str
    price_cad: float
    observed_on: str
    has_video: bool
    discounted_from: float | None = None


@dataclass
class BandReport:
    category: str
    observations: int
    low_cad: float
    median_cad: float
    high_cad: float
    video_premium_cad: float
    discount_prevalence: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"category": self.category, "observations": self.observations,
                "low_cad": round(self.low_cad, 2), "median_cad": round(self.median_cad, 2),
                "high_cad": round(self.high_cad, 2),
                "video_premium_cad": round(self.video_premium_cad, 2),
                "discount_prevalence": round(self.discount_prevalence, 3),
                "notes": list(self.notes)}


def observations_from_competitors(category: str = "mosaic_blanket") -> list[PriceObservation]:
    """Turn the dated competitor profiles into price observations.

    Shops with an unobserved band are skipped rather than counted as zero. A placeholder
    averaged into a market band is worse than a smaller sample, because it looks like data.
    """
    out: list[PriceObservation] = []
    for c in COMPETITORS:
        lo, hi = c.observed_price_band_cad
        if lo <= 0 or hi <= 0:
            continue
        has_video = any("VIDEO" in s.upper() for s in c.format_signals)
        for price in (lo, hi):
            out.append(PriceObservation(
                shop=c.shop, category=category, price_cad=price, observed_on=c.observed_on,
                has_video=has_video,
                discounted_from=_reference_price(c.discount_pattern)))
    return out


def _reference_price(pattern: str | None) -> float | None:
    if not pattern:
        return None
    import re

    m = re.search(r"CA\$?\s*([0-9]+(?:\.[0-9]{1,2})?)", pattern)
    return float(m.group(1)) if m else None


def scan_band(observations: list[PriceObservation], category: str) -> BandReport:
    """What the shelf actually charges, with the discount theatre measured, not copied."""
    rows = [o for o in observations if o.category == category and o.price_cad > 0]
    if not rows:
        return BandReport(category=category, observations=0, low_cad=0.0, median_cad=0.0,
                          high_cad=0.0, video_premium_cad=0.0, discount_prevalence=0.0,
                          notes=["no observations; do not price against an empty shelf"])
    prices = sorted(o.price_cad for o in rows)
    mid = len(prices) // 2
    median = prices[mid] if len(prices) % 2 else (prices[mid - 1] + prices[mid]) / 2

    with_video = [o.price_cad for o in rows if o.has_video]
    without = [o.price_cad for o in rows if not o.has_video]
    premium = ((sum(with_video) / len(with_video)) - (sum(without) / len(without))
               if with_video and without else 0.0)

    discounted = sum(1 for o in rows if o.discounted_from)
    prevalence = discounted / len(rows)

    notes: list[str] = []
    if prevalence >= 0.5:
        notes.append(
            f"{prevalence:.0%} of observed listings display a struck-through reference price. "
            f"We do not match that: section 9 forbids a discount against a price we never "
            f"charged, so we compete on a real number instead.")
    if premium > 0:
        notes.append(f"listings advertising video sit about CA${premium:.2f} higher, which is "
                     f"the price of table stakes rather than a premium we can claim")
    return BandReport(category=category, observations=len(rows), low_cad=prices[0],
                      median_cad=median, high_cad=prices[-1], video_premium_cad=premium,
                      discount_prevalence=prevalence, notes=notes)


# ---- revenue optimizer -----------------------------------------------------


@dataclass
class VisitorEconomics:
    price_cad: float
    conversion: float
    net_per_sale_cad: float
    contribution_per_visitor_cad: float

    def to_dict(self) -> dict:
        return {"price_cad": round(self.price_cad, 2),
                "conversion": round(self.conversion, 5),
                "net_per_sale_cad": round(self.net_per_sale_cad, 4),
                "contribution_per_visitor_cad": round(self.contribution_per_visitor_cad, 5)}


def expected_conversion(price_cad: float, *, reference_price_cad: float,
                        reference_conversion: float, elasticity: float = -1.4) -> float:
    """Constant-elasticity demand around an observed reference point.

    Stated plainly: this is a **model**, not a measurement, and it is only as good as the
    reference point it is anchored to. It exists so that a price recommendation is at least
    internally consistent before there is real data; `run_experiment` replaces it with
    evidence the moment there is any. Anything using this must say it is an estimate.
    """
    if price_cad <= 0 or reference_price_cad <= 0:
        raise ValueError("prices must be positive")
    ratio = price_cad / reference_price_cad
    return max(0.0, min(1.0, reference_conversion * math.pow(ratio, elasticity)))


def contribution_per_visitor(price_cad: float, conversion: float,
                             expected_sales: float = 10.0) -> VisitorEconomics:
    net = fees(price_cad, expected_sales).net_cad
    return VisitorEconomics(price_cad=price_cad, conversion=conversion,
                            net_per_sale_cad=net,
                            contribution_per_visitor_cad=net * conversion)


def optimise_price(*, candidates: list[float], reference_price_cad: float,
                   reference_conversion: float, elasticity: float = -1.4,
                   expected_sales: float = 10.0) -> dict:
    """Pick the price with the highest expected contribution per visitor.

    Deliberately reports the whole curve rather than only the winner. A recommendation that
    hides how flat the curve is invites someone to treat a two-cent difference as a finding.
    """
    if not candidates:
        raise ValueError("no candidate prices")
    curve = []
    for price in sorted(candidates):
        conv = expected_conversion(price, reference_price_cad=reference_price_cad,
                                   reference_conversion=reference_conversion,
                                   elasticity=elasticity)
        curve.append(contribution_per_visitor(price, conv, expected_sales))
    best = max(curve, key=lambda v: v.contribution_per_visitor_cad)
    spread = (best.contribution_per_visitor_cad
              - min(v.contribution_per_visitor_cad for v in curve))
    return {
        "recommended_price_cad": best.price_cad,
        "basis": "expected contribution per visitor, net of Etsy fees",
        "is_estimate": True,
        "curve": [v.to_dict() for v in curve],
        "flatness_warning": (
            "the curve is nearly flat across the candidate range; treat the winner as a "
            "starting point for a test, not a finding"
            if spread < 0.02 else None),
    }


# ---- bundle economist ------------------------------------------------------


@dataclass
class BundleVerdict:
    price_cad: float
    member_total_cad: float
    saving_cad: float
    saving_pct: float
    net_cad: float
    breakeven_attach_rate: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"price_cad": round(self.price_cad, 2),
                "member_total_cad": round(self.member_total_cad, 2),
                "saving_cad": round(self.saving_cad, 2),
                "saving_pct": round(self.saving_pct, 3),
                "net_cad": round(self.net_cad, 2),
                "breakeven_attach_rate": round(self.breakeven_attach_rate, 4),
                "reasons": list(self.reasons)}


MIN_BUNDLE_SAVING_PCT = 0.15


def price_bundle(member_prices_cad: list[float], *, target_saving_pct: float = 0.25,
                 expected_sales: float = 10.0) -> BundleVerdict:
    """Price a collection so the saving is obvious and the economics still work.

    Section 9: a bundle should lift average order value *while preserving obvious customer
    value*. A 6% saving does neither — it is not enough to change a decision and it costs
    margin on every unit. So the floor is real, and a bundle that cannot clear it should not
    exist.

    The breakeven attach rate is the honest question a bundle has to answer: what fraction of
    people who would otherwise have bought one pattern must buy the bundle instead for it to
    be worth offering?
    """
    if len(member_prices_cad) < 2:
        raise DeceptivePricing("a bundle needs at least two real member prices")
    member_total = round(sum(member_prices_cad), 2)
    price = round(member_total * (1 - target_saving_pct), 2)
    saving = round(member_total - price, 2)
    pct = saving / member_total

    reasons: list[str] = []
    if pct < MIN_BUNDLE_SAVING_PCT:
        raise DeceptivePricing(
            f"a {pct:.0%} saving is not a bundle, it is a rounding error. Section 9 requires "
            f"obvious customer value; the floor is {MIN_BUNDLE_SAVING_PCT:.0%}.")

    net_bundle = fees(price, expected_sales).net_cad
    net_single = fees(max(member_prices_cad), expected_sales).net_cad
    breakeven = net_single / net_bundle if net_bundle > 0 else float("inf")

    reasons.append(
        f"saves CA${saving:.2f} ({pct:.0%}) against CA${member_total:.2f} bought separately, "
        f"measured against prices we actually charge")
    reasons.append(
        f"nets CA${net_bundle:.2f} against CA${net_single:.2f} for the single best member, so "
        f"it pays for itself if {breakeven:.0%} of would-be single buyers take it instead")
    return BundleVerdict(price_cad=price, member_total_cad=member_total, saving_cad=saving,
                         saving_pct=pct, net_cad=net_bundle,
                         breakeven_attach_rate=breakeven, reasons=reasons)


# ---- price experiments -----------------------------------------------------


@dataclass
class ExperimentDesign:
    name: str
    product_slug: str
    hypothesis: str
    arms: list[dict]
    min_observations: int
    max_loss_cad: float
    stop_rule: str

    def to_dict(self) -> dict:
        return {"name": self.name, "product_slug": self.product_slug,
                "hypothesis": self.hypothesis, "arms": list(self.arms),
                "min_observations": self.min_observations,
                "max_loss_cad": round(self.max_loss_cad, 2), "stop_rule": self.stop_rule}


def design_price_experiment(product_slug: str, *, control_cad: float,
                            variant_cad: float, today: date | None = None,
                            min_observations: int = MIN_OBSERVATIONS_PER_ARM,
                            max_loss_cad: float = DEFAULT_MAX_TEST_LOSS_CAD
                            ) -> ExperimentDesign:
    """Design the test before running it, including how it is allowed to end.

    The stopping rule is fixed up front on purpose. A test whose stopping rule is decided
    while looking at the results is not a test, it is a way of confirming whatever the
    operator already believed.
    """
    if control_cad <= 0 or variant_cad <= 0:
        raise ValueError("both arms need a real price")
    if abs(variant_cad - control_cad) / control_cad < 0.08:
        raise ValueError(
            f"CA${control_cad:.2f} vs CA${variant_cad:.2f} is under 8% apart; at the sample "
            f"sizes a new shop can reach, a difference that small is unmeasurable")
    today = today or date.today()
    return ExperimentDesign(
        name=f"price:{product_slug}:{today.isoformat()}",
        product_slug=product_slug,
        hypothesis=(f"at CA${variant_cad:.2f} the contribution per visitor beats "
                    f"CA${control_cad:.2f}"),
        arms=[{"arm": "control", "price_cad": control_cad},
              {"arm": "variant", "price_cad": variant_cad}],
        min_observations=min_observations,
        max_loss_cad=max_loss_cad,
        stop_rule=(f"stop when both arms reach {min_observations} visitors, or when the "
                   f"variant's cumulative contribution shortfall reaches "
                   f"CA${max_loss_cad:.2f}, whichever comes first. Do not stop early because "
                   f"a result looks good."),
    )


@dataclass
class ExperimentResult:
    decided: bool
    winner: str | None
    reason: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"decided": self.decided, "winner": self.winner, "reason": self.reason,
                "detail": dict(self.detail)}


def read_experiment(design: ExperimentDesign, observations: dict[str, dict],
                    expected_sales: float = 10.0) -> ExperimentResult:
    """Read a running test against the rule that was fixed before it started.

    `observations` maps arm name to {"visitors": int, "orders": int}.
    """
    arms = {a["arm"]: a for a in design.arms}
    missing = [a for a in arms if a not in observations]
    if missing:
        return ExperimentResult(False, None, f"no data yet for {missing}")

    stats = {}
    for arm, cfg in arms.items():
        obs = observations[arm]
        visitors = max(0, int(obs.get("visitors", 0)))
        orders = max(0, int(obs.get("orders", 0)))
        conv = orders / visitors if visitors else 0.0
        econ = contribution_per_visitor(cfg["price_cad"], conv, expected_sales)
        stats[arm] = {"visitors": visitors, "orders": orders, **econ.to_dict()}

    thin = [a for a, s in stats.items() if s["visitors"] < design.min_observations]
    control, variant = stats["control"], stats["variant"]
    shortfall = ((control["contribution_per_visitor_cad"]
                  - variant["contribution_per_visitor_cad"]) * variant["visitors"])

    if shortfall >= design.max_loss_cad:
        return ExperimentResult(
            True, "control",
            f"variant stopped early: it has given up CA${shortfall:.2f} of contribution, "
            f"which reaches the CA${design.max_loss_cad:.2f} loss cap fixed before the test",
            stats)
    if thin:
        return ExperimentResult(
            False, None,
            f"not enough data in {thin}: below {design.min_observations} visitors a "
            f"difference this size is noise, and calling it now is how a shop convinces "
            f"itself of something untrue",
            stats)

    winner = max(stats, key=lambda a: stats[a]["contribution_per_visitor_cad"])
    lift = (stats[winner]["contribution_per_visitor_cad"]
            - stats["control" if winner == "variant" else "variant"]
            ["contribution_per_visitor_cad"])
    return ExperimentResult(
        True, winner,
        f"{winner} wins on contribution per visitor by CA${lift:.4f} with both arms past "
        f"{design.min_observations} visitors",
        stats)


# ---- promotions ------------------------------------------------------------


ALLOWED_PROMOTION_KINDS = ("launch_window", "collection_bundle", "seasonal_close")


def check_promotion(kind: str, *, price_cad: float, was_price_cad: float | None,
                    ever_charged: bool, duration_days: int) -> list[str]:
    """A promotion has to survive the Policy Gate's rules before it is worth designing.

    The category's standing "50% off" is a permanent sale, which is exactly what makes it
    deceptive: a price that is always discounted is not a discount. So a promotion here has
    to be a real, bounded event against a price genuinely charged outside it.
    """
    problems: list[str] = []
    if kind not in ALLOWED_PROMOTION_KINDS:
        problems.append(f"PROMO_KIND_UNKNOWN: {kind!r} is not an approved promotion type")
    if was_price_cad is not None:
        if not ever_charged:
            problems.append(
                f"PROMO_FAKE_REFERENCE: CA${was_price_cad:.2f} has never been charged, so "
                f"showing it as a was-price is a discount that does not exist")
        elif was_price_cad <= price_cad:
            problems.append("PROMO_REFERENCE_NOT_HIGHER: the reference price implies a "
                            "discount that is not one")
    if duration_days <= 0:
        problems.append("PROMO_NO_END: a promotion without an end date is just the price")
    if duration_days > 21:
        problems.append(
            f"PROMO_TOO_LONG: {duration_days} days is not an event. A price that is almost "
            f"always on sale is the regular price wearing a badge.")
    return problems
