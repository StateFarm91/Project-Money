"""Paid media guard rails (Master Plan section 11).

Section 11 is unusually specific here, and for good reason: advertising is the one part of
this system that can lose money quickly and silently. It requires hard daily, campaign and
monthly caps, a maximum test loss, a maximum CAC, a target contribution or ROAS, and minimum
data thresholds — plus automatic pausing on tracking failure, an unavailable listing, a CAC
breach, a refund anomaly, or the test-loss cap being reached.

All of it is built now, while no campaign exists and no money can be spent. That ordering is
deliberate. Guard rails written after the first campaign are guard rails written by someone
who has already learned what they cost.

Nothing here can start a campaign. There is no ad integration, `authorise_spend` refuses in
shadow mode regardless of the numbers, and the owner has not granted paid-media authority.
What this provides is the arithmetic and the stop conditions, ready and tested, for the day
they do.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..core.models import Phase
from ..gates.policy_knowledge import READINGS
from ..growth.loops import MEASURED_SAMPLE


class PaidMediaNotAuthorised(PermissionError):
    """Advertising was attempted without the owner's authority or outside shadow mode."""


@dataclass(frozen=True)
class Caps:
    """Every ceiling section 11 names. All hard, all enforced before a spend, not after."""

    daily_cad: float
    campaign_cad: float
    monthly_cad: float
    max_test_loss_cad: float
    max_cac_cad: float
    target_contribution_ratio: float = 1.30   # contribution per ad dollar
    min_clicks_before_judging: int = 200
    min_conversions_before_scaling: int = 15

    def validate(self) -> None:
        if not (0 < self.daily_cad <= self.campaign_cad <= self.monthly_cad):
            raise ValueError(
                f"caps must nest: daily ({self.daily_cad}) <= campaign "
                f"({self.campaign_cad}) <= monthly ({self.monthly_cad}). A daily cap above "
                f"the campaign cap is not a cap.")
        if self.max_cac_cad <= 0 or self.max_test_loss_cad <= 0:
            raise ValueError("max CAC and max test loss must both be real, positive numbers")


# The starting position, and it is deliberately small. Section 11: start small, scale only on
# profitable evidence. These are also inert -- no authority exists to spend any of it.
CONSERVATIVE_CAPS = Caps(
    daily_cad=3.00,
    campaign_cad=25.00,
    monthly_cad=60.00,
    max_test_loss_cad=25.00,
    max_cac_cad=6.00,
)


@dataclass
class CampaignState:
    name: str
    spend_today_cad: float = 0.0
    spend_campaign_cad: float = 0.0
    spend_month_cad: float = 0.0
    clicks: int = 0
    conversions: int = 0
    revenue_cad: float = 0.0
    contribution_cad: float = 0.0
    refunds: int = 0
    tracking_healthy: bool = True
    listing_available: bool = True
    paused: bool = False
    day: str = ""

    @property
    def cac_cad(self) -> float | None:
        return (self.spend_campaign_cad / self.conversions) if self.conversions else None

    @property
    def contribution_ratio(self) -> float | None:
        return ((self.contribution_cad / self.spend_campaign_cad)
                if self.spend_campaign_cad else None)

    @property
    def refund_rate(self) -> float:
        return self.refunds / self.conversions if self.conversions else 0.0

    @property
    def test_loss_cad(self) -> float:
        """What the test has cost beyond what it returned."""
        return max(0.0, self.spend_campaign_cad - self.contribution_cad)


@dataclass
class PauseDecision:
    paused: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"paused": self.paused, "reasons": list(self.reasons)}


REFUND_RATE_ALARM = 0.10


def should_pause(state: CampaignState, caps: Caps) -> PauseDecision:
    """Section 11's auto-pause conditions, every one of them.

    Ordered so that the conditions which mean "we cannot see what is happening" come first.
    A campaign running with broken tracking is not a campaign that might be losing money; it
    is a campaign nobody can tell is losing money, which is worse.
    """
    reasons: list[str] = []

    if not state.tracking_healthy:
        reasons.append(
            "TRACKING_FAILURE: conversions cannot be attributed, so every number below is "
            "unreliable. Spending while blind is the one thing a budget cap does not protect "
            "against.")
    if not state.listing_available:
        reasons.append(
            "LISTING_UNAVAILABLE: the ad points at a listing that is not purchasable. Every "
            "click is paid for and none can convert.")

    if state.spend_today_cad >= caps.daily_cad:
        reasons.append(f"DAILY_CAP: CA${state.spend_today_cad:.2f} reached the "
                       f"CA${caps.daily_cad:.2f} daily cap")
    if state.spend_campaign_cad >= caps.campaign_cad:
        reasons.append(f"CAMPAIGN_CAP: CA${state.spend_campaign_cad:.2f} reached the "
                       f"CA${caps.campaign_cad:.2f} campaign cap")
    if state.spend_month_cad >= caps.monthly_cad:
        reasons.append(f"MONTHLY_CAP: CA${state.spend_month_cad:.2f} reached the "
                       f"CA${caps.monthly_cad:.2f} monthly cap")
    if state.test_loss_cad >= caps.max_test_loss_cad:
        reasons.append(f"TEST_LOSS_CAP: the test has lost CA${state.test_loss_cad:.2f} "
                       f"against a CA${caps.max_test_loss_cad:.2f} ceiling")

    # Performance conditions only apply once there is enough data to read them. Pausing a
    # campaign on its third click is as wrong as never pausing it.
    if state.clicks >= caps.min_clicks_before_judging:
        cac = state.cac_cad
        if cac is None:
            reasons.append(
                f"NO_CONVERSIONS: {state.clicks} clicks and nothing bought. The ad is working "
                f"and the offer is not.")
        elif cac > caps.max_cac_cad:
            reasons.append(f"CAC_BREACH: CA${cac:.2f} per customer against a "
                           f"CA${caps.max_cac_cad:.2f} ceiling")
        ratio = state.contribution_ratio
        if ratio is not None and state.conversions >= caps.min_conversions_before_scaling \
                and ratio < caps.target_contribution_ratio:
            reasons.append(
                f"CONTRIBUTION_BELOW_TARGET: {ratio:.2f}x against a target of "
                f"{caps.target_contribution_ratio:.2f}x")

    if state.conversions >= 10 and state.refund_rate >= REFUND_RATE_ALARM:
        reasons.append(
            f"REFUND_ANOMALY: {state.refund_rate:.0%} of ad-driven orders were refunded. "
            f"Buying traffic for a product people return is paying to make the problem bigger.")

    return PauseDecision(paused=bool(reasons), reasons=reasons)


def may_scale(state: CampaignState, caps: Caps,
              organic: "OrganicPeriod | None" = None) -> tuple[bool, str]:
    """Section 11: scale only on profitable evidence -- and only over a listing that has
    proved itself without ads first (#242).

    The organic-first gate comes before the campaign's own numbers. A campaign can be
    profitable on a listing nobody has ever found organically, and scaling it hides a weak
    listing behind paid traffic, which is the exact thing #242 says not to do.
    """
    gate = organic_first_gate(organic)
    if not gate["allowed"]:
        return False, f"organic-first (#242): {gate['reason']}"
    decision = should_pause(state, caps)
    if decision.paused:
        return False, f"cannot scale a campaign that should be paused: {decision.reasons[0]}"
    if state.conversions < caps.min_conversions_before_scaling:
        return False, (f"{state.conversions} conversions is below the "
                       f"{caps.min_conversions_before_scaling} needed to tell a real result "
                       f"from a lucky week")
    ratio = state.contribution_ratio
    if ratio is None or ratio < caps.target_contribution_ratio:
        return False, (f"contribution ratio {ratio if ratio is None else round(ratio, 2)} is "
                       f"below the {caps.target_contribution_ratio:.2f}x target")
    return True, (f"{state.conversions} conversions at {ratio:.2f}x contribution and "
                  f"CA${state.cac_cad:.2f} CAC, all inside caps")


def authorise_spend(state: CampaignState, caps: Caps, amount_cad: float, *,
                    phase: Phase, owner_granted: bool) -> None:
    """The gate every ad dollar passes. Refuses first, arithmetic second.

    Two refusals precede any budget check, and neither can be argued out of with good
    numbers: paid media is a production capability that has not graduated from shadow mode,
    and the owner has not granted paid-media authority. A cap is not permission.
    """
    if phase is not Phase.PRODUCTION:
        raise PaidMediaNotAuthorised(
            f"paid media is a production capability and the system is in {phase.value}. No "
            f"budget makes this allowed; the gate is the phase, not the money.")
    if not owner_granted:
        raise PaidMediaNotAuthorised(
            "the owner has not granted paid-media authority. Section 11 and the authority "
            "matrix both put consequential spend in the owner's hands, and a cap configured "
            "by the system is not the owner's consent.")

    caps.validate()
    decision = should_pause(state, caps)
    if decision.paused or state.paused:
        raise PaidMediaNotAuthorised(
            f"campaign {state.name!r} is paused: {decision.reasons or ['paused earlier']}")
    if state.spend_today_cad + amount_cad > caps.daily_cad:
        raise PaidMediaNotAuthorised(
            f"CA${amount_cad:.2f} would take today's spend to "
            f"CA${state.spend_today_cad + amount_cad:.2f}, past the CA${caps.daily_cad:.2f} "
            f"daily cap")
    if state.spend_campaign_cad + amount_cad > caps.campaign_cad:
        raise PaidMediaNotAuthorised(
            f"CA${amount_cad:.2f} would breach the CA${caps.campaign_cad:.2f} campaign cap")
    if state.spend_month_cad + amount_cad > caps.monthly_cad:
        raise PaidMediaNotAuthorised(
            f"CA${amount_cad:.2f} would breach the CA${caps.monthly_cad:.2f} monthly cap")


def status(state: CampaignState, caps: Caps, *, today: date | None = None) -> dict:
    decision = should_pause(state, caps)
    scalable, why = may_scale(state, caps)
    return {
        "campaign": state.name,
        "as_of": (today or date.today()).isoformat(),
        "spend": {"today_cad": round(state.spend_today_cad, 2),
                  "campaign_cad": round(state.spend_campaign_cad, 2),
                  "month_cad": round(state.spend_month_cad, 2)},
        "caps": {"daily_cad": caps.daily_cad, "campaign_cad": caps.campaign_cad,
                 "monthly_cad": caps.monthly_cad,
                 "max_test_loss_cad": caps.max_test_loss_cad,
                 "max_cac_cad": caps.max_cac_cad},
        "performance": {"clicks": state.clicks, "conversions": state.conversions,
                        "cac_cad": round(state.cac_cad, 2) if state.cac_cad else None,
                        "contribution_ratio": (round(state.contribution_ratio, 3)
                                               if state.contribution_ratio else None),
                        "refund_rate": round(state.refund_rate, 3),
                        "test_loss_cad": round(state.test_loss_cad, 2)},
        "should_pause": decision.to_dict(),
        "may_scale": {"allowed": scalable, "reason": why},
        "live": False,
        "why_not_live": ("no ad integration exists, paid media has not graduated from shadow "
                         "mode, and the owner has not granted paid-media authority"),
    }


# ---------------------------------------------------------------------------
# #242: organic-first proof before heavy ads.

# The organic period a listing must have been measured over before a paid scale decision may
# read its appeal. Both are UNLEARNED defaults with their source named: the visit floor is
# `growth.loops.MEASURED_SAMPLE`, the same floor a loop needs before it counts as evidence;
# the day floor is the requirement's own instruction to respect attribution lag, sized to the
# Offsite Ads attribution window in `gates.policy_knowledge` rather than to a number chosen
# here. Neither is a fact about this shop.
MIN_ORGANIC_VISITS = MEASURED_SAMPLE


def _advertising_rule(rule: str) -> dict:
    reading = READINGS["advertising_rules"]
    for c in reading.conclusions:
        if c.get("rule") == rule:
            return dict(c)
    raise KeyError(f"gates.policy_knowledge has no advertising rule {rule!r}")


def _number_in(text: str, pattern: str, *, what: str) -> float:
    """Read one figure out of a reading's text, or refuse.

    The numbers below come from the reading and are never restated here. A reading whose
    text changed shape makes this refuse loudly rather than fall back to a figure written
    into code before the change.
    """
    import re

    m = re.search(pattern, text)
    if not m:
        raise PaidMediaNotAuthorised(
            f"the advertising reading no longer states {what} in a form this arithmetic can "
            f"read; re-read the reading before forecasting with it")
    return float(m.group(1).replace(",", ""))


def offsite_ads_terms() -> dict:
    """The Offsite Ads fee terms, read from `gates.policy_knowledge` and never hardcoded (#244)."""
    fee = _advertising_rule("offsite_ads_fee")
    mandatory = _advertising_rule("offsite_ads_mandatory_above_threshold")
    text = fee["text"]
    reading = READINGS["advertising_rules"]
    return {
        "standard_fee_rate": _number_in(text, r"(\d+)% of the order total", what="the standard fee") / 100.0,
        "reduced_fee_rate": _number_in(text, r";\s*(\d+)% once", what="the reduced fee") / 100.0,
        "fee_cap_usd": _number_in(text, r"capped at US\$(\d[\d,]*)", what="the per-order cap"),
        "threshold_usd": _number_in(text, r"under US\$(\d[\d,]*)", what="the sales threshold"),
        "attribution_window_days": int(_number_in(text, r"(\d+) days from the click",
                                                  what="the attribution window")),
        "mandatory_above_threshold": "mandatory" in mandatory["text"],
        "source": {"reading": reading.source, "read_on": reading.read_on,
                   "basis": reading.basis, "urls": list(reading.urls)},
    }


MIN_ORGANIC_DAYS = offsite_ads_terms()["attribution_window_days"]


@dataclass(frozen=True)
class OrganicPeriod:
    """A listing's life before any paid traffic touched it. All counts are organic only."""

    days: int
    visits: int
    orders: int
    impressions: int | None = None

    @property
    def conversion(self) -> float | None:
        return self.orders / self.visits if self.visits else None


def organic_first_gate(organic: OrganicPeriod | None,
                       *, min_conversion: float | None = None) -> dict:
    """Whether a paid scale decision may be read over this listing at all (#242).

    Three refusals, in order: no organic period was measured; the period is too short or too
    thin to say what the listing's appeal is; the appeal it shows is weak, and a weak listing
    is not to be hidden behind paid traffic. `min_conversion` is the caller's learned
    baseline for the cell; with none supplied the third test is reported UNMEASURED rather
    than judged against a number invented here.
    """
    if organic is None:
        return {"allowed": False, "status": "UNMEASURED",
                "reason": ("no organic period has been measured for this listing. Paid "
                           "scaling reads the listing's appeal from traffic it did not buy, "
                           "and there is none to read")}
    reasons = []
    if organic.days < MIN_ORGANIC_DAYS:
        reasons.append(f"{organic.days} organic days against a floor of {MIN_ORGANIC_DAYS}, "
                       f"which is the attribution window the platform itself uses; a shorter "
                       f"period cannot separate the listing from its launch")
    if organic.visits < MIN_ORGANIC_VISITS:
        reasons.append(f"{organic.visits} organic visits against a floor of "
                       f"{MIN_ORGANIC_VISITS}: a conversion rate over fewer is a hopeful one")
    if reasons:
        return {"allowed": False, "status": "insufficient_organic_period",
                "reason": "; ".join(reasons),
                "floors": {"days": MIN_ORGANIC_DAYS, "visits": MIN_ORGANIC_VISITS}}
    conversion = organic.conversion or 0.0
    if min_conversion is None:
        appeal = {"status": "UNMEASURED",
                  "why": ("no learned conversion baseline was supplied for this cell, so the "
                          "listing's appeal is measured but not judged; see "
                          "commerce.benchmarks for what a baseline needs")}
    elif conversion < min_conversion:
        return {"allowed": False, "status": "weak_listing",
                "reason": (f"organic conversion {conversion:.2%} is below the cell baseline "
                           f"{min_conversion:.2%}. A weak listing is not to be hidden behind "
                           f"paid traffic; fix the listing, then buy the visits"),
                "organic_conversion": round(conversion, 5)}
    else:
        appeal = {"status": "measured", "organic_conversion": round(conversion, 5),
                  "baseline": min_conversion}
    return {"allowed": True, "status": "organic_proof_present",
            "reason": (f"{organic.days} organic days and {organic.visits} organic visits "
                       f"measured before any paid traffic"),
            "organic_conversion": round(conversion, 5), "appeal": appeal,
            "floors": {"days": MIN_ORGANIC_DAYS, "visits": MIN_ORGANIC_VISITS}}


# ---------------------------------------------------------------------------
# #244: Offsite Ads attribution split in the forecast.


def offsite_ads_forecast(*, orders: int, aov_usd: float, offsite_share: float,
                         trailing_365_sales_usd: float, contribution_rate: float) -> dict:
    """Contribution with and without the Offsite Ads fee, on the platform's own terms (#244).

    `offsite_share` is the share of orders attributed to an Offsite Ad. It is an input
    because it is a measurement, and today it is UNMEASURED: pass what Etsy Stats reports,
    never a guess. The fee terms come from the policy reading, and the mandatory-participation
    threshold is applied because above it the forecast cannot opt out.
    """
    if not 0 <= offsite_share <= 1 or not 0 < contribution_rate <= 1:
        raise ValueError("offsite share and contribution rate are shares between 0 and 1")
    if orders < 0 or aov_usd < 0 or trailing_365_sales_usd < 0:
        raise ValueError("counts and money here are non-negative")
    terms = offsite_ads_terms()
    above = trailing_365_sales_usd >= terms["threshold_usd"]
    rate = terms["reduced_fee_rate"] if above else terms["standard_fee_rate"]
    fee_per_order = min(aov_usd * rate, terms["fee_cap_usd"])
    attributed = orders * offsite_share
    gross_contribution = orders * aov_usd * contribution_rate
    fees = attributed * fee_per_order
    return {
        "orders": orders, "attributed_orders": round(attributed, 2),
        "fee_rate_applied": rate, "fee_per_attributed_order_usd": round(fee_per_order, 2),
        "offsite_fees_usd": round(fees, 2),
        "contribution_before_fees_usd": round(gross_contribution, 2),
        "contribution_after_offsite_fees_usd": round(gross_contribution - fees, 2),
        "participation": ("mandatory" if above and terms["mandatory_above_threshold"]
                          else "optional"),
        "threshold_usd": terms["threshold_usd"],
        "attribution_window_days": terms["attribution_window_days"],
        "terms_source": terms["source"],
        "offsite_share_status": "supplied by caller; UNMEASURED until Etsy Stats reports it",
        "note": ("attributed orders are tracked separately because the fee changes their "
                 "contribution materially; the rate, cap, window and threshold are read from "
                 "the policy reading and not written here (#244)"),
    }


# ---------------------------------------------------------------------------
# #245: Share & Save / direct-link economics.


def share_and_save(*, orders_via_link: int, aov_cad: float, contribution_rate: float,
                   fee_benefit_rate: float | None, programme_source: str = "") -> dict:
    """Net contribution of orders that arrived through the seller's own trackable links (#245).

    The fee benefit is an input, not a constant: this repository holds no reading of the
    programme's current rules, and a rate written here would be a rate remembered rather
    than read. With none supplied the arithmetic refuses and says what it needs -- the
    official programme page, read and recorded in `gates.policy_knowledge`.
    """
    if orders_via_link < 0 or aov_cad < 0 or not 0 < contribution_rate <= 1:
        raise ValueError("orders and order value are non-negative; contribution rate is a share")
    if fee_benefit_rate is None:
        return {
            "measurable": False, "status": "UNMEASURED",
            "why": ("no official Share & Save rate is recorded. The benefit is a programme "
                    "rule and changes; it must be read from the official page into "
                    "gates.policy_knowledge and passed here, never assumed"),
            "needs": ["the programme's current fee benefit, from its official rules"],
        }
    if not 0 <= fee_benefit_rate < 1:
        raise ValueError("a fee benefit is a share of the order between 0 and 1")
    if not programme_source:
        raise ValueError("a fee benefit needs the official source it was read from")
    revenue = orders_via_link * aov_cad
    ordinary = revenue * contribution_rate
    benefit = revenue * fee_benefit_rate
    return {
        "measurable": True, "status": "measured",
        "orders_via_link": orders_via_link, "revenue_cad": round(revenue, 2),
        "contribution_ordinary_cad": round(ordinary, 2),
        "fee_benefit_cad": round(benefit, 2),
        "contribution_via_link_cad": round(ordinary + benefit, 2),
        "uplift_per_order_cad": round(aov_cad * fee_benefit_rate, 2),
        "fee_benefit_rate": fee_benefit_rate, "programme_source": programme_source,
        "note": ("qualified traffic sent through eligible trackable links is compared with "
                 "ordinary marketplace acquisition on net contribution after the fee benefit, "
                 "using only the official rate supplied (#245)"),
    }


def economics_state() -> dict:
    """What the paid-media economics can compute today, and what none of it can do: spend."""
    terms = offsite_ads_terms()
    return {
        "organic_first": {"floors": {"days": MIN_ORGANIC_DAYS, "visits": MIN_ORGANIC_VISITS},
                          "status": organic_first_gate(None)["status"]},
        "offsite_ads": {k: terms[k] for k in ("standard_fee_rate", "reduced_fee_rate",
                                              "fee_cap_usd", "threshold_usd",
                                              "attribution_window_days",
                                              "mandatory_above_threshold")},
        "offsite_terms_source": terms["source"],
        "share_and_save": share_and_save(orders_via_link=0, aov_cad=0.0,
                                         contribution_rate=1.0, fee_benefit_rate=None),
        "can_spend": False,
        "why_not": ("arithmetic only. No function in this module enqueues, schedules or "
                    "authorises ad spend; authorise_spend refuses outside production and "
                    "without the owner's grant, and neither exists"),
    }
