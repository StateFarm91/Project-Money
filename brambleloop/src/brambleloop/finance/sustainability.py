"""Whether Brambleloop can afford to keep existing at its opening prices (F-321, F-324, F-325,
F-329).

`unit_cost` answers "what did each thing cost to make". This module answers the three
questions that sit on top of it, and the launch gate reads the last:

* **Break-even per product (F-324).** How many sales recover the one-time creation spend,
  kept separate from the recurring margin each sale leaves after it. Expensive, careful
  creation can be rational for a reusable digital product -- but only if somebody divides.
* **Per-listing maintenance (F-321).** Recurring AI/API cost attributable to a live listing:
  what is spent on a product *after* it went live (observation, revalidation, refresh,
  support). Before any listing is live it is UNMEASURED, and stays so.
* **Steady-state forecast (F-325).** Monthly AI/API cost at realistic catalogue sizes,
  sales volumes and support loads, low/base/high, every assumption named. It **refuses**
  when the operational data underneath it is too thin: a precise forecast from four days of
  spend is a number with a decimal point and no meaning.

**How costs are split.** A cost row tagged with a product (`CostEntry.product_slug`) is
*creation* spend if it happened before that product's first live listing and *maintenance*
spend after. Rows with no product are *platform* spend: the cadences, research and
development this system runs regardless of catalogue. That split is by time and tag, not by
guessing from a purpose string, and it is a floor for creation: product work nobody tagged
is in platform spend, not in the product's break-even.

Only AI/API kinds (`llm`, `api`) are counted -- hosting and ads have their own ceilings and
reports, and the Master's question here is inference cost.
"""
from __future__ import annotations
from .listing_costs import cost_basis, basis_summary

import math
from datetime import datetime, timedelta, timezone

AI_KINDS = ("llm", "api")
LIVE_STATES = ("published", "active")

# F-325's refusal floor: below this much cost history, or this many costed calls, the
# forecast refuses rather than extrapolates.
MIN_HISTORY_DAYS = 14
MIN_COST_ROWS = 20
WINDOW_DAYS = 30

# F-329's verdict: in the base case, AI/API cost may take at most this share of monthly
# product contribution. Above it, inference is "threatening product contribution".
MAX_AI_SHARE_OF_CONTRIBUTION = 0.50

# The named scenarios. Every figure here is an ASSUMPTION about the future and is reported
# as one; the measured unit costs they multiply are read from the database.
SCENARIOS: dict[str, dict] = {
    "low": {"catalogue_listings": 10, "sales_per_month": 20, "support_rate": 0.05,
            "new_products_per_month": 1, "platform_factor": 0.5,
            "why": "a small opening catalogue, slow first months, development spend wound "
                   "down to half its current rate"},
    "base": {"catalogue_listings": 25, "sales_per_month": 60, "support_rate": 0.08,
             "new_products_per_month": 3, "platform_factor": 1.0,
             "why": "the planned catalogue at modest traction, platform spend continuing at "
                    "its recorded rate"},
    "high": {"catalogue_listings": 60, "sales_per_month": 200, "support_rate": 0.12,
             "new_products_per_month": 6, "platform_factor": 1.5,
             "why": "a larger catalogue with real traction, heavier observation and support, "
                    "platform spend half again its recorded rate"},
}


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _rows(db):
    """(costs, listings, orders) as plain tuples."""
    from sqlalchemy import select

    from ..core.models import CostEntry, Listing, Order

    with db.session() as s:
        costs = [(_aware(c.at), c.kind or "", float(c.amount_cad or 0.0),
                  c.product_slug or "", c.purpose or "", c.agent or "", cost_basis(c))
                 for c in s.scalars(select(CostEntry))]
        listings = [(l.product_slug, float(l.price_cad or 0.0), l.state or "",
                     bool(l.etsy_listing_id), _aware(l.created_at))
                    for l in s.scalars(select(Listing).where(Listing.state != "withdrawn"))]
        orders = [(o.product_slug, _aware(o.at), float(o.contribution_cad or 0.0),
                   bool(o.refunded), o.fees_basis or "unknown")
                  for o in s.scalars(select(Order))]
    return costs, listings, orders


def _live_since(listings) -> dict[str, datetime]:
    """product -> earliest live listing time (created_at of a live listing: a floor)."""
    out: dict[str, datetime] = {}
    for slug, _price, state, on_etsy, created in listings:
        if state in LIVE_STATES and on_etsy and created is not None:
            out[slug] = min(out.get(slug, created), created)
    return out


def _modelled_contribution(price_cad: float) -> dict:
    """Net contribution per sale at a listed price, from the fee schedule (modelled)."""
    from . import currency as fx

    c = fx.contribution(fx.Money(price_cad, "CAD"))
    return {"per_sale_cad": round(float(c["net_contribution"]["amount"]), 2),
            "basis": "modelled",
            "fees_not_yet_observed": c["fees_not_yet_observed"]}


def split_costs(db) -> dict:
    """AI/API spend split into creation, maintenance and platform, per the module rule."""
    costs, listings, _ = _rows(db)
    live = _live_since(listings)
    creation: dict[str, float] = {}
    maintenance: dict[str, float] = {}
    platform = 0.0
    for at, kind, amount, slug, _purpose, _agent, _basis in costs:
        if kind not in AI_KINDS:
            continue
        if not slug:
            platform += amount
        elif slug in live and at is not None and at >= live[slug]:
            maintenance[slug] = maintenance.get(slug, 0.0) + amount
        else:
            creation[slug] = creation.get(slug, 0.0) + amount
    return {"creation": creation, "maintenance": maintenance, "platform": platform,
            "cost_basis": basis_summary((c[2],c[6]) for c in costs if c[1] in AI_KINDS),
            "live_since": {k: v.isoformat() for k, v in live.items()}}


# ---------------------------------------------------------------------------
# F-321


def listing_maintenance_cost(db, *, now: datetime | None = None) -> dict:
    """Recurring AI/API cost per live listing per month, from spend after it went live."""
    now = now or datetime.now(timezone.utc)
    costs, listings, _ = _rows(db)
    live = _live_since(listings)
    if not live:
        return {"reading": "UNMEASURED", "listings": {}, "per_listing_month_cad": None,
                "why": "no listing is live, so no spend can be attributed to maintaining one. "
                       "Until then per-listing maintenance is inside platform spend"}
    per: dict[str, dict] = {}
    for slug, since in live.items():
        selected = [c for c in costs if c[3] == slug and c[1] in AI_KINDS and c[0] is not None and c[0] >= since]
        spent = sum(c[2] for c in selected)
        months = max((now - since).days, 1) / 30.0
        per[slug] = {"cost_basis": basis_summary((c[2],c[6]) for c in selected), "live_since": since.isoformat(), "spent_cad": round(spent, 4),
                     "per_month_cad": round(spent / months, 4),
                     "months_observed": round(months, 2)}
    monthly = [v["per_month_cad"] for v in per.values()]
    basis = basis_summary((c[2],c[6]) for c in costs if c[3] in live and c[1] in AI_KINDS and c[0] is not None and c[0] >= live[c[3]])
    return {"reading": basis["reading"], "cost_basis": basis, "listings": per,
            "per_listing_month_cad": round(sum(monthly) / len(monthly), 4),
            "note": "cost tagged to the product after its first live listing; product work "
                    "that was not tagged is in platform spend, so this is a floor"}


# ---------------------------------------------------------------------------
# F-324


def break_even(db) -> dict:
    """Sales needed to recover each product's one-time creation spend, per product."""
    costs, listings, orders = _rows(db)
    split = split_costs(db)
    prices: dict[str, float] = {}
    for slug, price, _state, _on, _created in listings:
        if price > 0:
            prices[slug] = max(prices.get(slug, 0.0), price)
    by_product: dict[str, list] = {}
    for slug, _at, contribution, refunded, basis in orders:
        if not refunded:
            by_product.setdefault(slug, []).append((contribution, basis))
    products = sorted(set(split["creation"]) | set(prices))
    out = {}
    for slug in products:
        creation = round(split["creation"].get(slug, 0.0), 4)
        sold = by_product.get(slug) or []
        if sold:
            per_sale = round(sum(c for c, _b in sold) / len(sold), 2)
            basis = ("measured" if all(b == "measured" for _c, b in sold)
                     else "orders, fees modelled")
        elif slug in prices:
            m = _modelled_contribution(prices[slug])
            per_sale, basis = m["per_sale_cad"], "modelled at the listed price"
        else:
            out[slug] = {"creation_cost_cad": creation if creation > 0 else None,
                         "break_even_sales": None, "recovered": None, "reading": "UNKNOWN",
                         "why": "no price and no order: contribution per sale is unknown"}
            continue
        maintenance = round(split["maintenance"].get(slug, 0.0), 4)
        row = {"creation_cost_cad": creation, "contribution_per_sale_cad": per_sale,
               "contribution_basis": basis, "sales_so_far": len(sold),
               "maintenance_cost_so_far_cad": maintenance}
        if creation <= 0:
            # F-324: no AI/API spend tagged to this product is not a product that cost
            # nothing to make -- it is a product whose creation cost nobody attributed. A
            # break-even of 0 sales and `recovered: True` was a number made out of missing
            # data, so the row says UNKNOWN and why instead.
            row.update(creation_cost_cad=None, creation_cost_reading="UNKNOWN",
                       break_even_sales=None, recovered=None, reading="UNKNOWN",
                       why=("no AI/API spend is tagged to this product, so its creation "
                            "cost is unknown (not zero) and break-even cannot be computed; "
                            "untagged product work sits in platform spend"))
        elif per_sale <= 0:
            row.update(break_even_sales=None, recovered=False, reading="NEVER",
                       why="each sale leaves no positive contribution, so no number of "
                           "sales recovers the creation spend")
        else:
            n = math.ceil(creation / per_sale)
            row.update(break_even_sales=n,
                       recovered=len(sold) >= n, reading="computed",
                       why=("one-time creation spend recovered after this many sales; the "
                            "contribution each later sale leaves is recurring margin, less "
                            "per-listing maintenance"))
        out[slug] = row
    return {"products": out,
            "note": ("creation cost is AI/API spend tagged to the product before its first "
                     "live listing -- a floor, since untagged product work sits in platform "
                     "spend. Break-even is creation cost over contribution per sale; it says "
                     "nothing about how many sales will come")}


# ---------------------------------------------------------------------------
# F-325


def forecast(db, *, now: datetime | None = None) -> dict:
    """Steady-state monthly AI/API cost and contribution, low/base/high, or a refusal."""
    now = now or datetime.now(timezone.utc)
    costs, listings, orders = _rows(db)
    ai = [c for c in costs if c[1] in AI_KINDS and c[0] is not None]
    missing: list[str] = []
    first = min((c[0] for c in ai), default=None)
    history_days = (now - first).days if first is not None else 0
    if history_days < MIN_HISTORY_DAYS:
        missing.append(f"cost history: {history_days} days of AI/API spend recorded, "
                       f"{MIN_HISTORY_DAYS} needed")
    if len(ai) < MIN_COST_ROWS:
        missing.append(f"costed calls: {len(ai)} recorded, {MIN_COST_ROWS} needed")
    split = split_costs(db)
    created = [v for v in split["creation"].values() if v > 0]
    if not created:
        missing.append("creation cost: no AI/API spend is tagged to a product, so the cost "
                       "of adding a product is unknown")
    priced = [p for _s, p, _st, _on, _c in listings if p > 0]
    if not priced:
        missing.append("opening prices: no listing has a price, so contribution per sale at "
                       "opening prices is unknown")

    window_start = now - timedelta(days=WINDOW_DAYS)
    window_days = min(WINDOW_DAYS, max(history_days, 1))
    platform_window = sum(a for at, k, a, slug, _p, _g, _basis in ai
                          if not slug and at >= window_start)
    platform_monthly = round(platform_window * 30.0 / window_days, 2)
    support_rows = [a for at, k, a, slug, p, g, _basis in ai
                    if at >= window_start and ("support" in p or g == "support")]
    maintenance = listing_maintenance_cost(db, now=now)

    measured = {
        "history_days": history_days,
        "costed_calls": len(ai),
        "platform_monthly_cad": platform_monthly,
        "creation_cost_per_product_cad": (round(sum(created) / len(created), 4)
                                          if created else None),
        "maintenance_per_listing_month_cad": maintenance["per_listing_month_cad"],
        "support_cost_per_case_cad": (round(sum(support_rows) / len(support_rows), 4)
                                      if support_rows else None),
        "opening_price_mean_cad": round(sum(priced) / len(priced), 2) if priced else None,
    }
    if missing:
        return {
            "status": "INSUFFICIENT_DATA", "scenarios": None, "measured": measured,
            "cost_basis": split["cost_basis"],
            "input_label": "legacy measured key includes recorded/modelled costs; see cost_basis",
            "missing": missing,
            "known_floor_monthly_cad": platform_monthly,
            "why": ("a precise steady-state forecast is refused: the operational data "
                    "underneath it is too thin. The recorded platform exposure is shown as a "
                    "floor, not a forecast"),
        }

    per_sale = _modelled_contribution(measured["opening_price_mean_cad"])
    scenarios = {}
    for name, a in SCENARIOS.items():
        platform = platform_monthly * a["platform_factor"]
        creation = a["new_products_per_month"] * measured["creation_cost_per_product_cad"]
        upkeep = a["catalogue_listings"] * (measured["maintenance_per_listing_month_cad"] or 0.0)
        support = (a["sales_per_month"] * a["support_rate"]
                   * (measured["support_cost_per_case_cad"] or 0.0))
        ai_cost = round(platform + creation + upkeep + support, 2)
        contribution = round(a["sales_per_month"] * per_sale["per_sale_cad"], 2)
        scenarios[name] = {
            "assumptions": {k: v for k, v in a.items() if k != "why"}, "why": a["why"],
            "ai_cost_monthly_cad": ai_cost,
            "components_cad": {"platform": round(platform, 2), "creation": round(creation, 2),
                               "maintenance": round(upkeep, 2), "support": round(support, 2)},
            "contribution_monthly_cad": contribution,
            "net_monthly_cad": round(contribution - ai_cost, 2),
            "ai_share_of_contribution": (round(ai_cost / contribution, 4)
                                         if contribution > 0 else None),
        }
    unmeasured_terms = [t for t, v in (
        ("maintenance_per_listing", measured["maintenance_per_listing_month_cad"]),
        ("support_cost_per_case", measured["support_cost_per_case_cad"])) if v is None]
    return {
        "status": "computed", "scenarios": scenarios, "measured": measured,
        "cost_basis": split["cost_basis"],
        "input_label": "legacy measured key includes recorded/modelled costs; see cost_basis",
        "contribution_per_sale": per_sale,
        "unmeasured_terms": unmeasured_terms,
        "note": ("every scenario figure is a named assumption multiplied by a recorded unit "
                 "cost. " + (f"{unmeasured_terms} are not yet measurable and are carried "
                             f"inside platform spend (costed at 0 separately), which is why "
                             f"platform spend is scaled per scenario" if unmeasured_terms
                             else "")),
    }


# ---------------------------------------------------------------------------
# F-329


def verdict(db, *, now: datetime | None = None) -> dict:
    """Are steady-state economics sustainable at opening prices? The launch gate's input."""
    f = forecast(db, now=now)
    if f["status"] != "computed":
        return {"sustainable": False, "status": f["status"], "forecast": f,
                "why": "launch waits on a forecast that can be computed: " + "; ".join(
                    f["missing"])}
    base, low = f["scenarios"]["base"], f["scenarios"]["low"]
    problems = []
    if base["net_monthly_cad"] <= 0:
        problems.append(f"base case: AI/API cost CA${base['ai_cost_monthly_cad']:.2f}/month "
                        f"exceeds contribution CA${base['contribution_monthly_cad']:.2f}")
    share = base["ai_share_of_contribution"]
    if share is None or share > MAX_AI_SHARE_OF_CONTRIBUTION:
        problems.append(f"base case: AI/API cost takes {share if share is not None else 'all'}"
                        f" of contribution (limit {MAX_AI_SHARE_OF_CONTRIBUTION:.0%})")
    return {
        "sustainable": not problems, "status": "computed", "problems": problems,
        "low_case_needs_owner_top_up": low["net_monthly_cad"] < 0,
        "forecast": f,
        "why": ("steady-state economics are sustainable at opening prices" if not problems
                else "launch is blocked until corrected: " + "; ".join(problems)),
    }
