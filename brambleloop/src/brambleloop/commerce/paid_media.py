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


def may_scale(state: CampaignState, caps: Caps) -> tuple[bool, str]:
    """Section 11: scale only on profitable evidence."""
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
