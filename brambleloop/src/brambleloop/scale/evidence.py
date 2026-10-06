"""The confidence model's inputs, read from the database (C-60: #27, #243, #262, #273, #275).

The final audit of 9434c53 found the confidence machinery complete and unfed: the weekly
solve and `/api/scale` passed no `conditions`, so #27's qualitative conditions were always
unmet and the >=75% band could never open whatever happened; the scenario matrix always ran
on the assumed 2% conversion, so "derive required visits from observed conversion" never ran;
nothing passed `calibration_ceiling`, so an optimistic forecast could never lower confidence;
and the CAC split existed only as arithmetic nobody called.

This module is the feed. Every condition is derived from rows, with the evidence it was
derived from, and an underivable condition is unmet with its reason -- never met by default,
never met by a caller's say-so. Thresholds that depend on the data are computed from the data
(#275: "thresholds adapt to actual data rather than being gamed"): the sample a conversion
rate needs grows as the rate falls, because a 0.5% rate needs far more visits than a 5% rate
to be told apart from noise.

Reads only. The one write is `record_forecast`, which stores the model's forecast for the
next period *before* that period starts -- the precondition `scale.calibration` enforces --
so that the period can later be scored against what actually happened.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .runrate import UNMEASURED

FORECAST_KIND = "scale.forecast"

# The two-sided 95% z and the relative precision a conversion rate needs before it counts as
# measured over a "meaningful sample": the interval's half-width within half the rate itself.
Z95 = 1.96
RELATIVE_HALF_WIDTH = 0.5
# Shares of the target a conservative projection and a downside scenario must still reach.
APPROACH_SHARE = 0.8
# A refund rate above this, or any open P0/P1 incident, is not "low severity".
MAX_REFUND_RATE = 0.05
MAX_SUPPORT_PER_ORDER = 0.25
# Seasonal revenue share inside this band is balanced; outside it the business is one of the
# two rather than both.
SEASONAL_BALANCE = (0.2, 0.8)
MIN_ORDERS_FOR_AOV = 30
MIN_SKUS_SELLING = 3
MAX_TOP_SKU_SHARE = 0.5
AD_SOURCES = ("etsy_ads", "offsite_ads", "paid_ads")


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _now(today: date | None) -> datetime:
    if today is None:
        return datetime.now(timezone.utc)
    return datetime(today.year, today.month, today.day, tzinfo=timezone.utc) + timedelta(days=1)


def meaningful_sample(conversion: float | None) -> int | None:
    """Visits a conversion rate needs before it is evidence, computed from the rate itself.

    n >= z^2 (1 - p) / (h^2 p), with h the relative half-width. A threshold fixed at 200
    visits would call a 0.5% rate measured on one order; this one asks for ~3,000 visits at
    0.5% and ~150 at 5%, which is what the arithmetic of a proportion actually requires.
    """
    if conversion is None or conversion <= 0:
        return None
    p = min(conversion, 0.999)
    return int(round((Z95 ** 2) * (1 - p) / ((RELATIVE_HALF_WIDTH ** 2) * p)))


def _window_orders(db, now: datetime, days: int) -> tuple[list, list]:
    from sqlalchemy import select

    from ..core.models import Order

    from ..commerce import orders_ingest as _oi

    with db.session() as s:
        held = _oi.held_refs(s)  # rc1-ORD2: booked orders; refunded = not countable
        rows = [(o.product_slug, _aware(o.at), float(o.revenue_cad or 0.0),
                 float(o.contribution_cad or 0.0), not _oi.countable(o, held),
                 o.acquisition_source, bool(o.is_repeat), o.category or "")
                for o in _oi.booked_orders(s)]
    last = [r for r in rows if r[1] is not None and now - timedelta(days=days) <= r[1] < now]
    prev = [r for r in rows if r[1] is not None
            and now - timedelta(days=2 * days) <= r[1] < now - timedelta(days=days)]
    return last, prev


def _seasonal_slugs() -> set[str]:
    from ..radar.opportunity import POOL

    return {c.slug for c in POOL if c.season}


def derive_conditions(db, got: dict, *, stress: dict | None = None,
                      scenarios: dict | None = None, today: date | None = None,
                      target_cad: float = 5000.0) -> dict:
    """Every #27/#275 qualitative condition, derived from rows, with its evidence.

    `got` is `runrate.observe(db)`'s output. A condition that cannot be derived is False with
    the reason in its evidence: unstated is unmet, and underivable is unstated.
    """
    from sqlalchemy import func, select

    from ..commerce import bundles
    from ..commerce.trust import PROOF_FLOOR
    from ..core.models import Incident, LedgerEntry, PhysicalTest, SupportCase
    from ..growth import loops

    now = _now(today)
    observed = got["observed"]
    live = bool(got["orders_source"]["live"])
    last, prev = _window_orders(db, now, got["window_days"])
    kept = [r for r in last if not r[4]]
    ev: dict[str, dict] = {}
    cond: dict[str, bool] = {}

    # multiple independent sellers: several SKUs, none carrying the month.
    by_sku: dict[str, float] = {}
    for r in kept:
        by_sku[r[0]] = by_sku.get(r[0], 0.0) + r[2]
    total = sum(by_sku.values())
    top_share = (max(by_sku.values()) / total) if total else None
    cond["multiple_independent_sellers"] = bool(
        len(by_sku) >= MIN_SKUS_SELLING and top_share is not None
        and top_share <= MAX_TOP_SKU_SHARE)
    ev["multiple_independent_sellers"] = {
        "skus_selling": len(by_sku), "top_sku_share": top_share,
        "need": {"skus": MIN_SKUS_SELLING, "max_top_share": MAX_TOP_SKU_SHARE}}

    contribution = observed.contribution_cad
    cond["positive_contribution_margin"] = bool(live and contribution is not None
                                                and contribution > 0)
    ev["positive_contribution_margin"] = {"contribution_cad": contribution
                                          if contribution is not None else UNMEASURED,
                                          "orders_source_live": live}

    with db.session() as s:
        open_severe = s.scalar(select(func.count()).select_from(Incident).where(
            Incident.resolved == False, Incident.severity.in_(("P0", "P1")))) or 0  # noqa: E712
        open_policy = s.scalar(select(func.count()).select_from(Incident).where(
            Incident.resolved == False, Incident.signature.like("%policy%"))) or 0  # noqa: E712
        support = [_aware(c.at) for c in s.scalars(select(SupportCase))]
        tests_recent = s.scalar(select(func.count()).select_from(PhysicalTest).where(
            PhysicalTest.passed == True,  # noqa: E712
            PhysicalTest.completed_at >= now - timedelta(days=30))) or 0
        sales_recent = s.scalar(select(func.count()).select_from(LedgerEntry).where(
            LedgerEntry.category == "sale",
            LedgerEntry.at >= now - timedelta(days=30))) or 0
        passed_total = s.scalar(select(func.count()).select_from(PhysicalTest).where(
            PhysicalTest.passed == True)) or 0  # noqa: E712
        sales_total = s.scalar(select(func.count()).select_from(LedgerEntry).where(
            LedgerEntry.category == "sale")) or 0

    def _rate(cases: int, orders: int) -> float | None:
        return (cases / orders) if orders else None

    d = got["window_days"]
    sup_last = sum(1 for a in support if a and now - timedelta(days=d) <= a < now)
    sup_prev = sum(1 for a in support if a and now - timedelta(days=2 * d) <= a
                   < now - timedelta(days=d))
    rate_last, rate_prev = _rate(sup_last, len(last)), _rate(sup_prev, len(prev))
    cond["stable_quality_metrics"] = bool(
        rate_last is not None and rate_prev is not None and rate_last <= rate_prev
        and not open_severe)
    ev["stable_quality_metrics"] = {"support_per_order_last": rate_last,
                                    "support_per_order_previous": rate_prev,
                                    "open_p0_p1": int(open_severe),
                                    "why": ("needs orders in both windows to compare"
                                            if rate_last is None or rate_prev is None else "")}

    loop_rows = loops.from_db(db)
    repeatable = [lp.key for lp in loop_rows if lp.strength == loops.REPEATABLE]
    cond["repeatable_qualified_traffic"] = bool(repeatable)
    ev["repeatable_qualified_traffic"] = {"repeatable_loops": repeatable}

    conversion = observed.conversion
    needed = meaningful_sample(conversion)
    visits = observed.visits
    cond["conversion_over_meaningful_sample"] = bool(
        needed is not None and visits is not None and visits >= needed)
    ev["conversion_over_meaningful_sample"] = {
        "conversion": conversion if conversion is not None else UNMEASURED,
        "visits": visits if visits is not None else UNMEASURED,
        "visits_needed": needed if needed is not None else UNMEASURED,
        "threshold_basis": (f"adaptive: z={Z95} and a relative half-width of "
                            f"{RELATIVE_HALF_WIDTH:.0%} of the observed rate")}

    def _sources(rows) -> set[str]:
        return {r[5] for r in rows if not r[4] and r[5] and r[5] != "unknown"}

    both = sorted(_sources(last) & _sources(prev))
    cond["repeatable_acquisition_channel"] = bool(both)
    ev["repeatable_acquisition_channel"] = {"sources_in_both_windows": both}

    proof_total = int(passed_total) + int(sales_total)
    new_proof = int(tests_recent) + int(sales_recent)
    cond["improving_trust_base"] = bool(proof_total >= PROOF_FLOOR and new_proof > 0)
    ev["improving_trust_base"] = {"proof_total": proof_total, "new_in_30_days": new_proof,
                                  "floor": PROOF_FLOOR}

    cond["no_open_policy_risk"] = bool(live and not open_policy)
    ev["no_open_policy_risk"] = {"open_policy_incidents": int(open_policy),
                                 "observed_over_a_live_shop": live}

    # #27: a scenario whose conservative assumptions still approach the target.
    conservative = None
    if conversion and visits and observed.aov_cad:
        n = visits
        half = Z95 * ((conversion * (1 - conversion) / n) ** 0.5)
        p_low = max(0.0, conversion - half)
        monthly_visits = visits * 30.0 / float(d or 30)
        conservative = round(monthly_visits * p_low * observed.aov_cad, 2)
    trustworthy = (scenarios or {}).get("evidence_supported_paths", 0)
    cond["conservative_scenario_near_target"] = bool(
        conservative is not None and trustworthy
        and conservative >= APPROACH_SHARE * target_cad)
    ev["conservative_scenario_near_target"] = {
        "conservative_monthly_cad": conservative if conservative is not None else UNMEASURED,
        "evidence_supported_paths": trustworthy, "need_share_of_target": APPROACH_SHARE}

    # #275: seasonal/evergreen balance, from where the revenue came from.
    seasonal = _seasonal_slugs()
    seasonal_rev = sum(r[2] for r in kept if r[0] in seasonal)
    share = (seasonal_rev / total) if total else None
    cond["seasonal_evergreen_balance"] = bool(
        share is not None and SEASONAL_BALANCE[0] <= share <= SEASONAL_BALANCE[1])
    ev["seasonal_evergreen_balance"] = {"seasonal_revenue_share":
                                        share if share is not None else UNMEASURED,
                                        "balanced_between": list(SEASONAL_BALANCE)}

    # #275: observed bundle/AOV behaviour.
    attribution = bundles.attribution_from_db(db, today=today)
    measured_bundles = [b["bundle"] for b in attribution.get("bundles", [])
                        if b.get("verdict") not in ("unmeasured", None)]
    cond["observed_bundle_aov"] = bool(len(kept) >= MIN_ORDERS_FOR_AOV and measured_bundles)
    ev["observed_bundle_aov"] = {"orders": len(kept), "need_orders": MIN_ORDERS_FOR_AOV,
                                 "bundles_measured": measured_bundles}

    # #275: stable low defect/refund/support severity.
    refund_rate = got.get("refund_rate")
    support_rate = got.get("support_rate")
    cond["low_defect_refund_severity"] = bool(
        refund_rate is not None and refund_rate <= MAX_REFUND_RATE
        and support_rate is not None and support_rate <= MAX_SUPPORT_PER_ORDER
        and not open_severe)
    ev["low_defect_refund_severity"] = {
        "refund_rate": refund_rate if refund_rate is not None else UNMEASURED,
        "support_rate": support_rate if support_rate is not None else UNMEASURED,
        "open_p0_p1": int(open_severe),
        "limits": {"refund_rate": MAX_REFUND_RATE, "support_per_order": MAX_SUPPORT_PER_ORDER}}

    # #275: downside scenarios that remain near the target.
    stress = stress or {}
    remaining = [s.get("remaining_cad") for s in stress.get("scenarios") or []
                 if isinstance(s.get("remaining_cad"), (int, float))]
    worst = min(remaining) if remaining else None
    cond["downside_near_target"] = bool(
        stress.get("testable") and worst is not None and worst >= APPROACH_SHARE * target_cad)
    ev["downside_near_target"] = {"worst_downside_cad": worst if worst is not None
                                  else UNMEASURED, "need_share_of_target": APPROACH_SHARE,
                                  "testable": bool(stress.get("testable"))}

    met = sorted(k for k, v in cond.items() if v)
    return {"conditions": cond, "evidence": ev, "met": met,
            "unmet": sorted(k for k, v in cond.items() if not v),
            "note": ("derived from rows; an underivable condition is unmet with its reason "
                     "(#27, #275)")}


def scenarios(observed, *, listings: int = 0) -> dict:
    """#273: the matrix on observed conversion when there is one, assumed only when not."""
    from . import target

    conversion = observed.conversion
    if conversion is not None and conversion > 0:
        out = target.matrix(conversion_rate=conversion, basis="observed",
                            sample=int(observed.visits or 0), listings=listings)
        out["conversion_source"] = "observed: runrate.observe over listing_outcomes and orders"
    else:
        out = target.matrix(listings=listings)
        out["conversion_source"] = ("assumed: no conversion has been observed, so required "
                                    "visits rest on the labelled 2% assumption")
    return out


def cac(db, *, today: date | None = None, window_days: int = 30) -> dict:
    """#243's three numbers for the trailing window, from customers, orders and the ledger."""
    from sqlalchemy import select

    from ..core.models import Customer, LedgerEntry, Order
    from .runrate import cac_split

    now = _now(today)
    since = now - timedelta(days=window_days)
    with db.session() as s:
        spend = sum(float(x.expense_cad or 0.0) for x in s.scalars(
            select(LedgerEntry).where(LedgerEntry.category.in_(("ads", "advertising"))))
            if _aware(x.at) and _aware(x.at) >= since)
        fees = sum(float(x.fees_cad or 0.0) for x in s.scalars(
            select(LedgerEntry).where(LedgerEntry.category == "offsite_ads_fee"))
            if _aware(x.at) and _aware(x.at) >= since)
        customers = [c for c in s.scalars(select(Customer))
                     if _aware(c.first_seen_at) and _aware(c.first_seen_at) >= since]
        from ..commerce import orders_ingest as _oi

        orders = [o for o in _oi.countable_orders(s)  # rc1-ORD2
                  if _aware(o.at) and _aware(o.at) >= since]
    any_customers = bool(customers)
    from_ads = sum(1 for c in customers if c.acquisition_source in AD_SOURCES)
    contribution = round(sum(float(o.contribution_cad or 0.0) for o in orders), 2) \
        if orders else None
    split = cac_split(ad_spend_cad=round(spend, 2),
                      new_customers_from_ads=from_ads if any_customers else None,
                      new_customers_all_sources=len(customers) if any_customers else None,
                      contribution_cad=contribution, offsite_fees_cad=round(fees, 2))
    split["window_days"] = window_days
    split["offsite_attributed_orders"] = sum(1 for o in orders if o.offsite_ad_attributed)
    return split


# ---- #262: forecasts recorded before their period, scored after it ------------------------

def _week_bounds(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def record_forecast(db, observed, *, today: date | None = None) -> dict:
    """Write the model's forecast for next week, dated today. Nothing is written without a
    measured run rate: a forecast of an unmeasured shop is not a forecast."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    today = today or date.today()
    if not observed.revenue_cad or observed.orders is None:
        return {"recorded": False, "why": "no measured revenue to forecast from"}
    start, end = _week_bounds(today + timedelta(days=7))
    terms = {}
    if observed.impressions:
        terms["qualified_traffic"] = float(observed.impressions) * 7 / 30
    if observed.ctr:
        terms["ctr"] = observed.ctr
    if observed.conversion:
        terms["conversion"] = observed.conversion
    if observed.aov_cad:
        terms["aov_cad"] = observed.aov_cad
    key = start.isoformat()
    payload = {"period_start": key, "period_end": end.isoformat(),
               "made_on": today.isoformat(),
               "revenue_cad": round(float(observed.revenue_cad) * 7 / 30, 2),
               "terms": terms, "method": "persistence of the trailing 30 days, per week"}
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == FORECAST_KIND, OperatingReading.period_key == key))
        if row is not None:
            return {"recorded": False, "why": "already forecast", "period": key}
        s.add(OperatingReading(kind=FORECAST_KIND, period_key=key, payload=payload))
    return {"recorded": True, "period": key, "forecast": payload}


def calibration(db, *, today: date | None = None) -> dict:
    """Every recorded forecast whose week has ended, scored against the orders it predicted,
    and the ceiling that history puts on confidence (#262)."""
    from sqlalchemy import select

    from ..core.models import Listing, ListingOutcome, OperatingReading, Order
    from . import calibration as cal

    today = today or date.today()
    with db.session() as s:
        forecasts = [dict(r.payload or {}) for r in s.scalars(select(OperatingReading).where(
            OperatingReading.kind == FORECAST_KIND))]
        from ..commerce import orders_ingest as _oi

        _held = _oi.held_refs(s)  # rc1-ORD2: booked orders; refunded = not countable
        orders = [(_aware(o.at).date(), float(o.revenue_cad or 0.0),
                   not _oi.countable(o, _held))
                  for o in _oi.booked_orders(s) if o.at is not None]
        outcomes = [(r.period_start, r.period_end, int(r.impressions or 0),
                     int(r.visits or 0)) for r in s.scalars(select(ListingOutcome))]
        listings = [(_aware(r.created_at).date() if r.created_at else None, r.state)
                    for r in s.scalars(select(Listing))]

    pairs, skipped = [], []
    for f in sorted(forecasts, key=lambda x: x.get("period_start", "")):
        start = date.fromisoformat(f["period_start"])
        end = date.fromisoformat(f["period_end"])
        if end >= today:
            skipped.append({"period": f["period_start"], "why": "the week has not ended"})
            continue
        period = cal.Period(label=f["period_start"], starts_on=start, ends_on=end)
        try:
            forecast = cal.Forecast(period=period, made_on=date.fromisoformat(f["made_on"]),
                                    revenue_cad=float(f["revenue_cad"]),
                                    terms={k: float(v) for k, v in (f.get("terms") or {}).items()
                                           if v and v > 0})
        except cal.CalibrationRefused as e:
            skipped.append({"period": f["period_start"], "why": str(e)})
            continue
        kept = [r for d, r, refunded in orders if start <= d <= end and not refunded]
        revenue = round(sum(kept), 2)
        imp = sum(i for ps, pe, i, _v in outcomes if start.isoformat() <= pe
                  and ps <= end.isoformat())
        vis = sum(v for ps, pe, _i, v in outcomes if start.isoformat() <= pe
                  and ps <= end.isoformat())
        terms = {}
        if imp:
            terms["qualified_traffic"] = float(imp)
        if imp and vis:
            terms["ctr"] = vis / imp
        if vis and kept:
            terms["conversion"] = len(kept) / vis
        if kept:
            terms["aov_cad"] = revenue / len(kept)
        live = sum(1 for created, state in listings
                   if state == "published" and created is not None and created <= end)
        # Only terms both sides measured are decomposed; revenue is always compared.
        common = {k: v for k, v in terms.items() if k in forecast.terms}
        actual = cal.Actual(period=period, revenue_cad=revenue, terms=common,
                            live_listings=live)
        forecast = cal.Forecast(period=period, made_on=forecast.made_on,
                                revenue_cad=forecast.revenue_cad,
                                terms={k: v for k, v in forecast.terms.items() if k in common})
        pairs.append((forecast, actual))

    if not pairs:
        return {"ceiling": None, "applied": False, "scored": 0, "forecasts": len(forecasts),
                "skipped": skipped,
                "why": ("no forecast week has ended with its actuals on file, so there is "
                        "nothing to hold the model to yet; no ceiling is applied")}
    result = cal.ceiling(pairs)
    if not result.get("scored"):
        result["ceiling"] = None
    result["forecasts"] = len(forecasts)
    result["skipped"] = skipped
    return result


def confidence_reading(db, *, today: date | None = None, target_cad: float = 5000.0) -> dict:
    """The whole fed model, for `/api/scale` and anything else that asks outside the weekly
    job: observe, derive, calibrate, then ask `scale.confidence` once with all of it."""
    from ..growth import mix, weekly
    from . import confidence, runrate

    got = runrate.observe(db, today=today)
    observed = got["observed"]
    report = mix.report(db)
    matrix = scenarios(observed, listings=int(observed.listings or 0))
    derived = derive_conditions(db, got, stress=report["stress_test"], scenarios=matrix,
                                today=today, target_cad=target_cad)
    cal = calibration(db, today=today)
    evidence = weekly.portfolio_evidence(db)
    conversion = observed.conversion
    probability = confidence.probability(
        db, target_cad=target_cad, stress=report["stress_test"],
        observed_conversion=conversion or 0.0,
        conversion_sample=(observed.visits or 0) if conversion is not None else 0,
        conditions=derived["conditions"],
        calibration_ceiling=cal.get("ceiling"),
        **evidence)
    return {"probability": probability, "scenarios": matrix, "conditions": derived,
            "calibration": cal, "cac_split": cac(db, today=today)}
