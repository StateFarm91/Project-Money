"""The weekly growth solve, read from the database and written down (C-48, #24-#28, #45,
#48, #229, #264, #270, #272).

`ops.capacity` used to pass `runrate.constraint` an empty `Observed()` and `/api/growth`
called `loops.constraint({})`, so every weekly review found nothing identifiable and nothing
downstream -- the scale rules, the CA$5K binding constraint, the solver's reallocation -- had
anything to act on. This module assembles one week's reading from rows: the funnel, the
growth-loop terms, the per-visitor ranking, bundle attribution, the launch-cohort holdouts,
the stress test and the confidence score it now feeds, and the scale readiness gate that
stands in front of any scaling tilt.

Every quantity with no source is None in the computation and the string UNMEASURED in the
reading. Nothing here is estimated to fill a gap: a CA$0 company with no customers produces a
reading that says, term by term, what has never been observed.
"""
from __future__ import annotations

from datetime import date

from ..scale.runrate import UNMEASURED, reading as _r

KIND = "growth.weekly"


def period_key(today: date) -> str:
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


def growth_inputs(observed) -> dict:
    """The four terms `loops.constraint` ranks, each measured or None (never zero-for-None)."""
    repeat_rate = None
    if observed.orders and observed.repeat_orders is not None:
        repeat_rate = observed.repeat_orders / observed.orders
    return {"qualified_visits": observed.visits,
            "conversion_rate": observed.conversion,
            "aov_cad": observed.aov_cad,
            "repeat_rate": repeat_rate}


def target_inputs(observed, window_days: int) -> dict:
    """The CA$5K target's terms (#229), scaled to a month, each measured or None."""
    per_month = 30.0 / float(window_days or 30)
    return {"qualified_visits": (observed.visits * per_month
                                 if observed.visits is not None else None),
            "conversion_rate": observed.conversion,
            "aov_cad": observed.aov_cad,
            "orders_per_month": (observed.orders * per_month
                                 if observed.orders is not None else None)}


def portfolio_evidence(db) -> dict:
    """Counts the confidence ladder asks callers for, from orders and customers only."""
    from sqlalchemy import func, select

    from ..core.models import Customer, Order
    from .loops import evidence_summary, from_db
    from .mix import concentration, positions_from_db

    with db.session() as s:
        selling = {o.product_slug for o in s.scalars(select(Order).where(
            Order.refunded.is_(False)))}
        customers = s.scalar(select(func.count()).select_from(Customer)) or 0
        repeat = s.scalar(select(func.count()).select_from(Order).where(
            Order.is_repeat.is_(True))) or 0
    conc = concentration(positions_from_db(db))
    return {
        "selling_skus": len(selling),
        "product_families": len({x.split("-")[0] for x in selling if x}),
        "acquisition_loops": evidence_summary(from_db(db))["with_evidence"],
        "repeat_orders": int(repeat),
        "outside_customers": int(customers),
        "top_sku_revenue_share": (conc["top_1_share"] if conc.get("measurable") else 1.0),
    }


def solve(db, *, today: date | None = None, qa: dict | None = None) -> dict:
    """One week's growth reading. Pure reading plus arithmetic; writes nothing."""
    from ..scale import allocation, confidence, readiness, runrate, target
    from ..commerce import bundles, elasticity
    from . import loops, mix

    today = today or date.today()
    got = runrate.observe(db, today=today)
    observed = got["observed"]

    # #25/#28: the funnel's binding term and the rule it fires, from observation.
    funnel = runrate.constraint(observed, refund_rate=got["refund_rate"],
                                support_rate=got["support_rate"])
    decomposition = runrate.decompose(3000.0, observed=observed)

    # #229: the CA$5K binding constraint, every key passed, None where unmeasured.
    binding = target.binding_constraint(target_inputs(observed, got["window_days"]))

    # #264: the solver's primary and secondary constraints, and the reallocation it recommends.
    solved = loops.constraint(growth_inputs(observed))
    realloc = loops.reallocation(solved)

    # #24: contribution per visitor across SKUs with recorded visits.
    per_visitor = runrate.per_visitor_from_db(db, today=today)

    # #272: the readiness gate stands in front of any tilt toward more traffic.
    scaling = funnel.get("identifiable") and funnel.get("rule") in readiness.SCALING_RULES
    gate = readiness.gate(db, action="capacity tilt toward distribution")
    tilt = funnel if funnel.get("identifiable") else None
    refused_tilt = None
    if scaling and not gate["allowed"]:
        refused_tilt = {"rule": funnel.get("rule"), "why": gate["note"]}
        tilt = None
    plan = allocation.allocate(qa=qa, constraint=tilt) if qa is not None else None

    # #45/#48: bundle attribution and launch-cohort holdouts, before any winner is declared.
    attribution = bundles.attribution_from_db(db, today=today)
    from sqlalchemy import select

    from ..core.models import Cohort, Product

    with db.session() as s:
        cohort_slugs = sorted({c.product_slug for c in s.scalars(select(Cohort))})
        product_slugs = sorted(p.slug for p in s.scalars(select(Product)))
    holdouts = [elasticity.holdout_from_db(db, slug) for slug in cohort_slugs]

    # #270: the stress test feeds the confidence score's resilience rung.
    report = mix.report(db)
    evidence = portfolio_evidence(db)
    conversion = observed.conversion
    # C-60 (#27, #262, #273, #275): the matrix on observed conversion, the qualitative
    # conditions derived from rows, and the forecast-calibration ceiling -- all passed, so the
    # >=75% band can open on evidence and an optimistic model is capped automatically.
    from ..scale import evidence as scale_evidence

    matrix = scale_evidence.scenarios(observed, listings=int(observed.listings or 0))
    derived = scale_evidence.derive_conditions(db, got, stress=report["stress_test"],
                                               scenarios=matrix, today=today)
    calibrated = scale_evidence.calibration(db, today=today)
    probability = confidence.probability(
        db, stress=report["stress_test"],
        observed_conversion=conversion or 0.0,
        conversion_sample=(observed.visits or 0) if conversion is not None else 0,
        conditions=derived["conditions"],
        calibration_ceiling=calibrated.get("ceiling"),
        **evidence)
    resilience = next(r for r in probability["ladder"]
                      if r["layer"] == "portfolio_resilience")

    return {
        "period": period_key(today),
        "as_of": today.isoformat(),
        "observed": {k: _r(v) for k, v in observed.to_dict().items()},
        "refund_rate": _r(got["refund_rate"]),
        "support_rate": _r(got["support_rate"]),
        "sources": got["sources"],
        "unmeasured": got["unmeasured"],
        "orders_source": got["orders_source"],
        "runrate_constraint": funnel,
        "scale_rule": funnel.get("rule") if funnel.get("identifiable") else UNMEASURED,
        "decomposition": decomposition,
        "binding_constraint_5k": binding,
        "growth_constraint": solved,
        "reallocation": realloc,
        "per_visitor": per_visitor,
        "scale_readiness": gate,
        "scale_tilt_refused": refused_tilt,
        "allocation": plan,
        "bundle_attribution": attribution,
        "holdouts": holdouts,
        "holdout_products_without_cohorts": [x for x in product_slugs
                                             if x not in cohort_slugs],
        "stress_test": report["stress_test"],
        "diversification_plan": report["diversification_plan"],
        "confidence": {"probability": probability["probability"],
                       "weakest_critical_layer": probability["weakest_critical_layer"],
                       "capped_by": probability["capped_by"],
                       "resilience_rung": resilience,
                       "conditions_met": derived["met"],
                       "conditions_unmet": derived["unmet"],
                       "calibration_ceiling": calibrated.get("ceiling")},
        # #273: required visits derived from observed conversion wherever it exists.
        "scenarios": {"conversion_source": matrix["conversion_source"],
                      "evidence_supported_paths": matrix["evidence_supported_paths"],
                      "scenarios": [{k: sc[k] for k in ("name", "required_visits",
                                                         "conversion", "contribution_cad")}
                                    for sc in matrix["scenarios"]]},
        "conditions": derived,
        "calibration": calibrated,
        # #243: new-customer CAC, blended CAC and contribution after advertising.
        "cac_split": scale_evidence.cac(db, today=today),
    }


def record(db, payload: dict) -> dict:
    """Write the week's reading, replacing an earlier run in the same ISO week."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == KIND, OperatingReading.period_key == payload["period"]))
        if row is None:
            row = OperatingReading(kind=KIND, period_key=payload["period"])
            s.add(row)
        row.payload = payload
        row.at = datetime.now(timezone.utc)
        s.flush()
        return {"id": row.id, "period": payload["period"]}


def latest(db) -> dict | None:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == KIND)
                       .order_by(OperatingReading.at.desc()).limit(1))
        return dict(row.payload or {}) if row is not None else None
