"""Ads funnel, learning-window discipline, stop/scale and diagnosis routing (F-266, F-269,
F-270, F-271) -- W4-C10.

Decision logic over *reports*, never actions: nothing here pauses, scales or changes a
campaign or an Etsy Ads setting. There is no executor. Each decision is a recommendation the
owner acts on in Etsy, and any increase in budget still passes the ceilings and owner authority
(`ads_readiness.propose`, `paid_media.authorise_spend`).

F-269 Funnel attribution -- `funnel(rows, contribution_per_order_cad=...)` per advertised
listing from ads-report rows (`{slug, spend_cad, impressions, clicks, orders, revenue_cad}`):
spend, impressions, clicks, CTR, CPC, orders/revenue *where accessible*, conversion,
contribution and evidence volume. An inaccessible field (None) stays None and everything
derived from it is None: UNKNOWN is never 0.

F-266 Learning-window discipline -- `guard_change(history, now=..., kind=..., reason=...)`
refuses a strategy/budget/listing change inside `MIN_WINDOW_DAYS` of the last one, unless the
reason is one of `OVERRIDES` (truth, safety, runaway spend, invalid traffic) with an evidence
ref.

F-270 Evidence-aware stop/scale -- `decide(row, caps)`: the hard pauses of
`paid_media.should_pause` come first (tracking, caps, test loss). Then nothing is judged
before adequate exposure (`MIN_IMPRESSIONS`, and the caps' click floor); clicks with no order
at adequate exposure is DIAGNOSE with the budget frozen -- never more budget; scale is only
SCALE_ELIGIBLE (an owner decision) at the caps' conversion floor and contribution target.

F-271 Creative before spend -- `route(row, baseline_ctr=..., baseline_conversion=...)`:
impressions with weak clicks -> creative (hero, title, value); healthy clicks with weak
conversion -> product, listing, trust, price. The remedy is never budget
(`budget_is_remedy` is always False). Baselines are the shop's own organic rates; without one
the route is UNKNOWN.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..commerce.paid_media import CampaignState, Caps, should_pause

UNKNOWN = "UNKNOWN"
MIN_WINDOW_DAYS = 14          # UNLEARNED default: two weekly cycles between strategy changes
OVERRIDES = ("truth", "safety", "runaway_spend", "invalid_traffic")
MIN_IMPRESSIONS = 1000        # UNLEARNED default exposure floor before reading CTR
WEAK = 0.7                    # below 70 % of the shop's own organic rate


def _div(a, b, nd=4):
    return None if a is None or b in (None, 0) else round(a / b, nd)


def funnel(rows, *, contribution_per_order_cad: dict | None = None) -> dict:
    per: dict[str, dict] = {}
    for r in rows or ():
        p = per.setdefault(r["slug"], {"spend_cad": 0.0, "impressions": 0, "clicks": 0,
                                       "orders": 0, "revenue_cad": 0.0, "days": 0,
                                       "orders_known": True, "revenue_known": True})
        p["spend_cad"] += float(r.get("spend_cad") or 0.0)
        p["impressions"] += int(r.get("impressions") or 0)
        p["clicks"] += int(r.get("clicks") or 0)
        p["days"] += 1
        if r.get("orders") is None:
            p["orders_known"] = False
        else:
            p["orders"] += int(r["orders"])
        if r.get("revenue_cad") is None:
            p["revenue_known"] = False
        else:
            p["revenue_cad"] += float(r["revenue_cad"])
    out = {}
    cpo = contribution_per_order_cad or {}
    for slug, p in sorted(per.items()):
        orders = p["orders"] if p["orders_known"] else None
        revenue = round(p["revenue_cad"], 2) if p["revenue_known"] else None
        unit = cpo.get(slug)
        contribution = (round(orders * unit - p["spend_cad"], 2)
                        if orders is not None and unit is not None else None)
        out[slug] = {"spend_cad": round(p["spend_cad"], 2), "impressions": p["impressions"],
                     "clicks": p["clicks"], "ctr": _div(p["clicks"], p["impressions"]),
                     "cpc_cad": _div(p["spend_cad"], p["clicks"], 2),
                     "orders": orders, "revenue_cad": revenue,
                     "conversion": _div(orders, p["clicks"]),
                     "contribution_after_ads_cad": contribution,
                     "evidence": {"report_days": p["days"], "clicks": p["clicks"],
                                  "orders": orders},
                     "unknown": [k for k, v in (("orders", orders), ("revenue", revenue),
                                                ("contribution", contribution)) if v is None]}
    return {"listings": out, "rule": "an inaccessible field is None and so is all it feeds"}


def guard_change(history, *, now: datetime, kind: str, reason: str = "",
                 evidence_ref: str = "") -> dict:
    last = max((h["at"] for h in history or ()), default=None)
    if reason:
        if reason not in OVERRIDES:
            return {"allowed": False, "why": f"{reason!r} is not an override; overrides are "
                                             f"{OVERRIDES}"}
        if not evidence_ref:
            return {"allowed": False, "why": "an override needs its evidence ref"}
        return {"allowed": True, "override": reason, "evidence_ref": evidence_ref,
                "why": f"{reason} overrides the learning window"}
    if last is not None and now - last < timedelta(days=MIN_WINDOW_DAYS):
        left = timedelta(days=MIN_WINDOW_DAYS) - (now - last)
        return {"allowed": False, "next_allowed_at": (last + timedelta(days=MIN_WINDOW_DAYS))
                .isoformat(), "why": f"{kind} change {left.days} day(s) inside the "
                                     f"{MIN_WINDOW_DAYS}-day learning window"}
    return {"allowed": True, "why": "outside the learning window"}


def decide(row: dict, caps: Caps, *, contribution_cad: float | None = None,
           tracking_healthy: bool = True, listing_available: bool = True) -> dict:
    orders = row.get("orders")
    if orders is None:
        return {"decision": UNKNOWN, "budget_change": "none",
                "why": ["orders are not accessible for this listing, so neither stop nor "
                        "scale can be read; no budget change"]}
    state = CampaignState(
        name=row.get("slug", "?"), spend_today_cad=0.0,
        spend_campaign_cad=float(row.get("spend_cad") or 0.0),
        spend_month_cad=float(row.get("spend_cad") or 0.0), clicks=int(row.get("clicks") or 0),
        conversions=int(orders or 0), contribution_cad=float(contribution_cad or 0.0),
        tracking_healthy=tracking_healthy,
        listing_available=listing_available)
    hard = [r for r in should_pause(state, caps).reasons
            if not r.startswith(("NO_CONVERSIONS", "CAC_BREACH", "CONTRIBUTION_BELOW"))]
    if hard:
        return {"decision": "STOP", "budget_change": "none", "why": hard}
    exposed = (int(row.get("impressions") or 0) >= MIN_IMPRESSIONS and
               state.clicks >= caps.min_clicks_before_judging)
    if not exposed:
        return {"decision": "CONTINUE", "budget_change": "none",
                "why": [f"exposure {row.get('impressions')} impressions / {state.clicks} "
                        f"clicks is below {MIN_IMPRESSIONS} / {caps.min_clicks_before_judging}; "
                        f"nothing is judged yet"]}
    if state.conversions == 0:
        return {"decision": "DIAGNOSE", "budget_change": "frozen",
                "why": [f"{state.clicks} clicks and no order: diagnose before any more budget"]}
    ratio = state.contribution_ratio if contribution_cad is not None else None
    if state.conversions >= caps.min_conversions_before_scaling and ratio is not None:
        if ratio >= caps.target_contribution_ratio:
            return {"decision": "SCALE_ELIGIBLE", "budget_change": "owner_decision",
                    "why": [f"{state.conversions} orders at {ratio:.2f}x contribution"]}
        return {"decision": "STOP", "budget_change": "none",
                "why": [f"{ratio:.2f}x contribution against a "
                        f"{caps.target_contribution_ratio:.2f}x target"]}
    return {"decision": "CONTINUE", "budget_change": "none",
            "why": [f"{state.conversions} orders; scale needs "
                    f"{caps.min_conversions_before_scaling} and a measured contribution"]}


def route(row: dict, *, baseline_ctr: float | None, baseline_conversion: float | None) -> dict:
    imp, clicks, orders = int(row.get("impressions") or 0), int(row.get("clicks") or 0), \
        row.get("orders")
    ctr = clicks / imp if imp else None
    conv = (orders / clicks) if orders is not None and clicks else None
    out = {"budget_is_remedy": False, "ctr": None if ctr is None else round(ctr, 4),
           "conversion": None if conv is None else round(conv, 4)}
    if imp < MIN_IMPRESSIONS:
        return {**out, "route": "WAIT", "why": "too few impressions to read clicks"}
    if baseline_ctr is None:
        return {**out, "route": UNKNOWN, "why": "no organic click-through baseline"}
    if ctr < WEAK * baseline_ctr:
        return {**out, "route": "CREATIVE", "fix": ["hero image", "title", "value statement"],
                "why": f"CTR {ctr:.2%} under {WEAK:.0%} of the organic {baseline_ctr:.2%}"}
    if orders is None or baseline_conversion is None:
        return {**out, "route": UNKNOWN, "why": "conversion or its baseline is not accessible"}
    if clicks >= 100 and conv < WEAK * baseline_conversion:
        return {**out, "route": "LISTING", "fix": ["product", "listing", "trust", "price"],
                "why": f"healthy clicks, conversion {conv:.2%} under {WEAK:.0%} of the organic "
                       f"{baseline_conversion:.2%}"}
    return {**out, "route": "HEALTHY", "why": "clicks and conversion are at the organic rate"}
