"""Etsy Plus credit wallet (F-614) -- W4-C10.

"Track Etsy Plus benefits separately from cash. Official current entitlement is USD $5 Etsy Ads
credit per monthly subscription cycle plus 15 listing/renewal credits; the Canadian shop
currently displays about CA$7.10. Credit expires and does not roll over."

`cycle(start, end, displayed_ads_credit_cad=None)` is one subscription cycle's entitlement:
US$5 of ads credit (`ads_readiness.PLUS_CREDIT_USD_PER_CYCLE`, the one constant) and 15
listing/renewal credits. Its CAD value is the amount the shop *displays* when the owner records
it (owner_reported), otherwise the assumed-FX conversion, labelled ESTIMATED.

`wallet(cycles, ad_spend=..., listing_uses=..., today=...)` keeps credit apart from cash:

* ads spend inside a cycle draws that cycle's ads credit first, and only the excess is cash;
  spend outside every cycle is all cash;
* nothing rolls over: unused ads or listing credit at a cycle's end is reported `expired`,
  never carried into the next cycle;
* a cycle that has not ended reports what is left, and the days until it lapses.

Recording a cycle is not authority to spend: a credit never raises a ceiling (`finance.credits`
states the same rule for every provider credit), and `ads_plan.fund` uses credit only for an
experiment that is already approved.
"""
from __future__ import annotations

from datetime import date

from ..core.fx import ASSUMED_CAD_PER_USD

LISTING_CREDITS_PER_CYCLE = 15


def _ads_usd() -> float:
    from .ads_readiness import PLUS_CREDIT_USD_PER_CYCLE

    return float(PLUS_CREDIT_USD_PER_CYCLE)


def cycle(start: date, end: date, *, displayed_ads_credit_cad: float | None = None) -> dict:
    if end <= start:
        raise ValueError("a cycle ends after it starts")
    usd = _ads_usd()
    if displayed_ads_credit_cad is not None:
        cad, basis = round(float(displayed_ads_credit_cad), 2), "owner_reported"
    else:
        cad, basis = round(usd * ASSUMED_CAD_PER_USD, 2), "ESTIMATED (assumed FX)"
    return {"start": start, "end": end, "ads_credit_usd": usd, "ads_credit_cad": cad,
            "cad_basis": basis, "listing_credits": LISTING_CREDITS_PER_CYCLE}


def wallet(cycles, *, ad_spend=(), listing_uses=(), today: date) -> dict:
    """`ad_spend`: [(date, cad)]; `listing_uses`: [date] (one listing/renewal credit each)."""
    out, cash = [], 0.0
    spend = sorted(ad_spend)
    claimed = [False] * len(spend)
    for c in sorted(cycles, key=lambda c: c["start"]):
        left = c["ads_credit_cad"]
        drawn = cash_in = 0.0
        for i, (d, cad) in enumerate(spend):
            if claimed[i] or not (c["start"] <= d < c["end"]):
                continue
            claimed[i] = True
            take = min(left, float(cad))
            left -= take
            drawn += take
            cash_in += float(cad) - take
        used = sum(1 for d in listing_uses if c["start"] <= d < c["end"])
        ended = today >= c["end"]
        cash += cash_in
        out.append({"start": c["start"].isoformat(), "end": c["end"].isoformat(),
                    "ads_credit_cad": c["ads_credit_cad"], "cad_basis": c["cad_basis"],
                    "ads_credit_drawn_cad": round(drawn, 2),
                    "ads_cash_cad": round(cash_in, 2),
                    "ads_credit_expired_cad": round(left, 2) if ended else 0.0,
                    "ads_credit_left_cad": 0.0 if ended else round(left, 2),
                    "listing_credits_used": min(used, c["listing_credits"]),
                    "listing_uses_paid_in_cash": max(0, used - c["listing_credits"]),
                    "listing_credits_expired": (max(0, c["listing_credits"] - used)
                                                if ended else 0),
                    "days_until_lapse": None if ended else (c["end"] - today).days,
                    "state": "ENDED" if ended else "ACTIVE"})
    outside = sum(float(cad) for (d, cad), k in zip(spend, claimed) if not k)
    cash += outside
    return {"cycles": out, "ads_cash_cad": round(cash, 2),
            "ads_spend_outside_any_cycle_cad": round(outside, 2),
            "rollover": False, "ceilings_changed": 0,
            "rule": "credit is drawn first inside its own cycle and expires at the cycle end; "
                    "it is never cash and never authority to spend"}
