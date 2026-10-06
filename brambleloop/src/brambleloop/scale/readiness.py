"""The scale readiness gate, read from the database before anything scales (#272).

`growth.experiments.scale_readiness` states the six conditions and refuses to call a product
ready while any is unmet. It had no caller, so nothing was ever refused: a capacity decision
or a launch plan could tilt toward distribution for a product whose support load nobody had
measured. This module is the runtime half. It derives each condition from rows, and a
condition with no source is *unmet*, not assumed -- a product whose refund rate has never
been observed has not shown that its refunds are acceptable.

Every scaling or spend decision calls `gate()` first: the weekly capacity decision in
`ops.capacity` does, and `gate()` is the function a launch-planning or paid-media path calls
before it moves money or capacity. It spends nothing and changes nothing; it answers.
"""
from __future__ import annotations

from ..growth.experiments import SCALE_CONDITIONS, scale_readiness

# The acceptable ceilings. Stated so the gate can be argued with rather than discovered.
MAX_REFUND_RATE = 0.05
MAX_SUPPORT_RATE = 0.10

# The scaling actions this gate stands in front of. A rule outside this set moves no capacity
# toward more traffic and needs no readiness.
SCALING_RULES: frozenset[str] = frozenset({"strong_conversion_low_traffic",
                                           "cac_below_allowable"})


def conditions(db, slug: str) -> dict:
    """Each of the six conditions for one product, with the evidence and its source."""
    from sqlalchemy import select

    from ..core.models import Incident, Listing, Order, PatternVersion, Product, SupportCase
    from ..commerce import elasticity

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = None
        if product is not None:
            pv = s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == product.id,
                PatternVersion.certified == True))  # noqa: E712
        stages = list(((pv.certificate or {}) if pv is not None else {}).get("stages_run")
                      or [])
        open_severe = [i.signature for i in s.scalars(select(Incident).where(
            Incident.product_slug == slug, Incident.resolved == False))  # noqa: E712
            if i.severity in ("P0", "P1")]
        from ..commerce import orders_ingest as _oi

        # rc1-ORD2: booked orders only; `_void` are the voided (not countable) ones.
        _held = _oi.held_refs(s)
        orders = _oi.booked_orders(s, select(Order).where(Order.product_slug == slug))
        _void = {o.id for o in orders if not _oi.countable(o, _held)}
        cases = [c for c in s.scalars(select(SupportCase).where(
            SupportCase.product_slug == slug))]
        has_listing = s.scalar(select(Listing).where(Listing.product_slug == slug)) is not None

    evidence: dict[str, dict] = {}
    evidence["product_quality_stable"] = {
        "met": pv is not None and not open_severe,
        "evidence": {"certified": pv is not None, "open_p0_p1": open_severe}}
    if orders:
        support_rate = len(cases) / len(orders)
        refund_rate = len(_void) / len(orders)
        contribution = sum(float(o.contribution_cad or 0.0) for o in orders
                           if o.id not in _void)
        attributed = sum(1 for o in orders if (o.acquisition_source or "unknown") != "unknown")
        evidence["support_load_acceptable"] = {
            "met": support_rate <= MAX_SUPPORT_RATE,
            "evidence": {"support_rate": round(support_rate, 4), "ceiling": MAX_SUPPORT_RATE}}
        evidence["refunds_acceptable"] = {
            "met": refund_rate <= MAX_REFUND_RATE,
            "evidence": {"refund_rate": round(refund_rate, 4), "ceiling": MAX_REFUND_RATE}}
        evidence["contribution_positive_or_bounded"] = {
            "met": contribution > 0,
            "evidence": {"contribution_cad": round(contribution, 2)}}
        holdout = elasticity.holdout_from_db(db, slug)
        promoted = holdout.get("have_promoted", False)
        evidence["attribution_working"] = {
            "met": attributed == len(orders) and (not promoted or holdout["separable"]),
            "evidence": {"orders_with_source": attributed, "orders": len(orders),
                         "promoted_arm": promoted,
                         "holdout_separable": holdout["separable"]}}
    else:
        for key in ("support_load_acceptable", "refunds_acceptable",
                    "contribution_positive_or_bounded", "attribution_working"):
            evidence[key] = {"met": False, "evidence": "UNMEASURED",
                             "why": "no order has been recorded for this product, so the "
                                    "condition has not been shown and is unmet"}
    evidence["creative_certified_truthful"] = {
        "met": bool(has_listing and "asset_truth" in stages),
        "evidence": {"listing": has_listing, "asset_truth_ran": "asset_truth" in stages}}

    flags = {k: bool(evidence[k]["met"]) for k in SCALE_CONDITIONS}
    verdict = scale_readiness(flags)
    return {"slug": slug, **verdict, "evidence": evidence}


def gate(db, slug: str | None = None, *, action: str) -> dict:
    """Refuse a scaling or spend action on anything not ready (#272).

    With `slug`, that product. Without, the catalogue: the action may proceed only for the
    products that pass, and when none does the action is refused whole.
    """
    from sqlalchemy import select

    from ..core.models import Product

    if slug:
        slugs = [slug]
    else:
        with db.session() as s:
            slugs = sorted(p.slug for p in s.scalars(select(Product)))
    results = [conditions(db, x) for x in slugs]
    ready = [r["slug"] for r in results if r["ready"]]
    return {
        "action": action,
        "allowed": bool(ready),
        "ready": ready,
        "not_ready": {r["slug"]: r["unmet"] for r in results if not r["ready"]},
        "products_checked": len(results),
        "note": ("scaling may proceed only for the products listed ready" if ready else
                 f"refused: no product meets all six scale conditions, so '{action}' would "
                 f"multiply whatever is already true, including what nobody has measured"),
    }
