"""Etsy Ads learning-test planner (F-264, F-265, F-615) -- W4-C10.

Planning only. Nothing here creates, activates, funds or changes a campaign or an Etsy Ads /
Offsite Ads setting; there is no ads executor in this repository. Every plan is SHADOW and
`executed` is always False. A plan that survives goes nowhere by itself: spend still passes
`ads_readiness.propose` (Finance challenge, hard ceiling, owner item) and, on the day an
executor exists, `commerce.paid_media.authorise_spend` (phase + owner authority + caps).

F-264 Initial learning test: "sufficient budget/duration to learn. Current Etsy guidance
recommends at least US$3-5/day initially and, when practical, promoting all active listings."
`design_learning_test` refuses a plan below the guidance floor (a test that cannot learn is not
a cheaper test, it is a wasted one), shorter than `LEARNING_DAYS`, or with no ready listing;
it promotes every ready listing unless the plan names a reason to narrow, and lists the
listings it left out with the readiness reason.

F-265 Per-listing threshold: "Recognize Etsy's current US$25/day maximum-budget threshold for
per-listing strategies; below it do not pretend visibility/efficient/lower-click-cost controls
are available." Below it the plan's strategy is `etsy_managed`, and asking for a per-listing
strategy is refused rather than recorded as if it applied.

Both thresholds are read from the watched advertising reading (`search_policy.onsite_ads_terms`,
F-291), never restated here; they are UNVERIFIED there (the Etsy Ads help page returns 403),
and the plan carries that status.

F-615 Free credit first: "When an approved Etsy Ads experiment exists, prefer expiring included
credit before incremental owner-funded spend where Etsy billing permits. Never advertise merely
to avoid wasting credit." `fund` draws expiring credit first only for an approved experiment and
only when billing is known to permit it; with no approved experiment it funds nothing, however
much credit is about to expire.

Ceilings: without owner ad authority the conservative caps (`paid_media.CONSERVATIVE_CAPS`)
bind; a plan above them is NEEDS_OWNER_AUTHORITY with the ceiling it would need -- the
guidance floor (US$3/day) is above the conservative CA$3/day cap, and the plan says so rather
than shrinking the test below the point where it learns.
"""
from __future__ import annotations

from ..commerce.paid_media import CONSERVATIVE_CAPS, MIN_ORGANIC_DAYS
from ..core.fx import ASSUMED_CAD_PER_USD

# The learning window is the attribution window (30 days, from the advertising reading via
# paid_media): a shorter test ends before the orders its clicks produce are attributed.
LEARNING_DAYS = MIN_ORGANIC_DAYS
STRATEGIES = ("etsy_managed", "per_listing")
PHASE = "SHADOW"


class PlanRefused(ValueError):
    pass


def _terms() -> dict:
    from ..commerce.search_policy import onsite_ads_terms

    return onsite_ads_terms()


def design_learning_test(*, listings, daily_usd: float, days: int,
                         strategy: str = "etsy_managed", narrow_to=None, narrow_reason="",
                         authority: dict | None = None) -> dict:
    """`listings`: [{slug, ready, why}] from `ads_readiness.readiness` (or a fixture)."""
    t = _terms()
    floor, ctl = t["min_daily_usd"], t["per_listing_controls_min_daily_usd"]
    if strategy not in STRATEGIES:
        raise PlanRefused(f"strategy must be one of {STRATEGIES}")
    if floor is None:
        raise PlanRefused("the learning floor is not in the advertising reading: UNKNOWN, so "
                          "no plan can claim to meet it")
    if daily_usd < floor:
        raise PlanRefused(f"US${daily_usd:.2f}/day is under the US${floor:g}/day guidance "
                          f"floor; a test this small cannot learn (F-264)")
    if int(days) < LEARNING_DAYS:
        raise PlanRefused(f"{days} days is shorter than the {LEARNING_DAYS}-day attribution "
                          f"window; orders from late clicks would fall outside it")
    if strategy == "per_listing" and (ctl is None or daily_usd < ctl):
        raise PlanRefused(f"per-listing strategies need US${ctl:g}/day; at US${daily_usd:.2f} "
                          f"visibility / efficient / lower-click-cost controls are not "
                          f"available and may not be planned (F-265)")
    ready = [x["slug"] for x in listings if x.get("ready")]
    left_out = [{"slug": x["slug"], "why": x.get("why") or "not ready"}
                for x in listings if not x.get("ready")]
    if narrow_to:
        if not narrow_reason:
            raise PlanRefused("promoting fewer than every ready listing needs a stated reason")
        left_out += [{"slug": s, "why": f"narrowed: {narrow_reason}"}
                     for s in ready if s not in set(narrow_to)]
        ready = [s for s in ready if s in set(narrow_to)]
    if not ready:
        raise PlanRefused("no ready listing to promote")
    daily_cad = round(daily_usd * ASSUMED_CAD_PER_USD, 2)
    total_cad = round(daily_cad * int(days), 2)
    a = authority or {"granted": False}
    if a.get("granted"):
        cap_daily = float(a["daily_cap_cad"])
        cap_total = float(a.get("lifetime_cap_cad") or a["daily_cap_cad"] * 30)
        basis = "owner SpendLimit('ads')"
    else:
        cap_daily, cap_total = CONSERVATIVE_CAPS.daily_cad, CONSERVATIVE_CAPS.campaign_cad
        basis = "paid_media.CONSERVATIVE_CAPS (no owner ad authority)"
    over = []
    if daily_cad > cap_daily + 1e-9:
        over.append(f"daily CA${daily_cad:.2f} > CA${cap_daily:.2f} ({basis})")
    if total_cad > cap_total + 1e-9:
        over.append(f"total CA${total_cad:.2f} > CA${cap_total:.2f} ({basis})")
    state = ("NEEDS_OWNER_AUTHORITY" if over and not a.get("granted") else
             "OVER_CEILING" if over else "DESIGNED")
    return {"state": state, "phase": PHASE, "executed": False,
            "listings": ready, "left_out": left_out,
            "promotes_all_ready": not narrow_to,
            "daily_usd": round(daily_usd, 2), "daily_cad": daily_cad, "days": int(days),
            "total_cad": total_cad, "strategy": strategy,
            "per_listing_controls_available": ctl is not None and daily_usd >= ctl,
            "ceiling": {"daily_cad": cap_daily, "total_cad": cap_total, "basis": basis},
            "over_ceiling": over,
            "guidance": {"min_daily_usd": floor, "per_listing_controls_min_daily_usd": ctl,
                         "status": t["status"], "reading": t["reading"]},
            "fx": {"cad_per_usd": ASSUMED_CAD_PER_USD, "basis": "core.fx assumed rate"},
            "next": ("ads_readiness.propose per listing (Finance challenge + owner item); no "
                     "executor exists")}


def fund(*, amount_cad: float, approved_experiment: bool, credit_left_cad: float | None,
         credit_expires_before_end: bool | None, billing_permits_credit: bool | None) -> dict:
    """Split one approved experiment's cost between included credit and owner cash (F-615)."""
    if not approved_experiment:
        return {"credit_cad": 0.0, "cash_cad": 0.0, "funded": False,
                "why": "no approved experiment: credit is never a reason to advertise, so it "
                       "is left to expire if it must"}
    if billing_permits_credit is not True or credit_left_cad is None:
        return {"credit_cad": 0.0, "cash_cad": round(amount_cad, 2), "funded": True,
                "credit_basis": "UNKNOWN",
                "why": ("whether Etsy billing applies the credit to this spend, or how much is "
                        "left, is not verified; the plan assumes none and the owner sees the "
                        "full cash amount")}
    credit = round(min(float(credit_left_cad), float(amount_cad)), 2)
    return {"credit_cad": credit, "cash_cad": round(amount_cad - credit, 2), "funded": True,
            "credit_basis": "owner_reported",
            "why": ("expiring included credit drawn before owner cash" if
                    credit_expires_before_end else "included credit drawn before owner cash")}
