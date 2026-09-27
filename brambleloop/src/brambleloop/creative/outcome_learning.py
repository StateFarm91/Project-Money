"""Which kinds of originality create demand: concept attributes joined to outcomes (#89).

Requirement 89: after launch, connect concept attributes to real outcomes -- impressions,
CTR, favourites, conversion, reviews, repeat purchase, support burden and contribution -- and
learn which kinds of originality create demand. Do not equate novelty with success.

The join is the machinery and it runs today; the outcomes are the gate and they do not exist
today. So the module's honest answer on an empty warehouse is a table of concepts with every
outcome `UNMEASURED`, each with its reason and the n it needs.

**Novelty is measured and never rewarded.** Each concept's novelty is its distance to the
nearest other concept (`creative.concept.distance`), which is a structural fact. The check
here asks one question of it -- do the more novel concepts earn more per visit than the less
novel ones? -- and reports the answer either way. Nothing in this module scores a concept
higher *for* being novel: a finding that novel concepts outperform is a finding about this
shop's buyers, and a finding that they do not is equally useful and is reported as loudly.
"""
from __future__ import annotations

MEASURED = "measured"
UNMEASURED = "UNMEASURED"

# Concepts per attribute value before a value is compared: one concept is one product.
MIN_CONCEPTS_PER_VALUE = 3
# Concepts in each half of the novelty split.
MIN_CONCEPTS_PER_GROUP = 3
# Visits before a rate is read (growth.loops.MEASURED_SAMPLE).
MIN_VISITS = 200
# Orders before contribution, review, repeat or support rates are read
# (commerce.benchmarks.MIN_ORDERS_FOR_REFUND_RATE).
MIN_ORDERS = 20

ATTRIBUTES: tuple[str, ...] = ("form", "construction", "motif", "feeling", "recipient",
                               "occasion", "make_lane")


def _unmeasured(why: str, needs: str) -> dict:
    return {"status": UNMEASURED, "value": None, "why": why, "needs": needs}


def _measured(value, **extra) -> dict:
    return {"status": MEASURED, "value": value, **extra}


def _concept_for(slug: str, concepts: list) -> object | None:
    exact = next((c for c in concepts if c.key == slug), None)
    if exact is not None:
        return exact
    return next((c for c in concepts if slug.startswith(c.key)), None)


def _novelty(concepts: list) -> dict[str, float | None]:
    from .concept import nearest

    if len(concepts) < 2:
        return {c.key: None for c in concepts}
    return {c.key: round(nearest(c, concepts)[1], 4) for c in concepts}


def outcomes_by_concept(db, concepts: list | None = None) -> list[dict]:
    """One row per concept: its attributes, its novelty and every outcome on record."""
    from sqlalchemy import select

    from ..core.models import ListingOutcome, Order, SupportCase

    if concepts is None:
        from .audit import catalogue_concepts

        concepts = catalogue_concepts()
    novelty = _novelty(concepts)
    rows = {c.key: {"concept": c.key, "novelty": novelty.get(c.key),
                    **{a: getattr(c, a) for a in ATTRIBUTES},
                    "palette": c.palette_story,
                    "impressions": 0, "visits": 0, "favourites": None, "orders": 0,
                    "revenue_cad": 0.0, "contribution_cad": 0.0, "reviews": 0,
                    "repeat_orders": 0, "support_cases": 0, "outcome_periods": 0}
            for c in concepts}

    with db.session() as s:
        for o in s.scalars(select(ListingOutcome)):
            c = _concept_for(o.product_slug, concepts)
            if c is None:
                continue
            r = rows[c.key]
            r["impressions"] += o.impressions
            r["visits"] += o.visits
            r["outcome_periods"] += 1
            if o.favourites is not None:
                r["favourites"] = (r["favourites"] or 0) + o.favourites
        for order in s.scalars(select(Order).where(Order.refunded == False)):  # noqa: E712
            c = _concept_for(order.product_slug, concepts)
            if c is None:
                continue
            r = rows[c.key]
            r["orders"] += 1
            r["revenue_cad"] += order.revenue_cad or 0.0
            r["contribution_cad"] += order.contribution_cad or 0.0
            r["reviews"] += 1 if order.reviewed else 0
            r["repeat_orders"] += 1 if order.is_repeat else 0
        for case in s.scalars(select(SupportCase)):
            c = _concept_for(case.product_slug or "", concepts) if case.product_slug else None
            if c is not None:
                rows[c.key]["support_cases"] += 1
    return list(rows.values())


def _metrics(rows: list[dict]) -> dict:
    impressions = sum(r["impressions"] for r in rows)
    visits = sum(r["visits"] for r in rows)
    orders = sum(r["orders"] for r in rows)
    fav = [r["favourites"] for r in rows if r["favourites"] is not None]
    out: dict[str, dict] = {}
    out["impressions"] = (_measured(impressions, n=len(rows)) if any(
        r["outcome_periods"] for r in rows) else _unmeasured(
        "no listing outcome recorded for these concepts", "a Stats export per listing"))
    out["ctr"] = (_measured(round(visits / impressions, 5), n=impressions)
                  if impressions >= MIN_VISITS else _unmeasured(
                      f"{impressions} impressions against a floor of {MIN_VISITS}",
                      f"n >= {MIN_VISITS} impressions"))
    out["favourites"] = (_measured(sum(fav), n=len(fav)) if fav else _unmeasured(
        "no favourite count recorded", "favourites from the Stats export"))
    out["conversion"] = (_measured(round(orders / visits, 5), n=visits)
                         if visits >= MIN_VISITS else _unmeasured(
                             f"{visits} visits against a floor of {MIN_VISITS}",
                             f"n >= {MIN_VISITS} visits"))
    if orders < MIN_ORDERS:
        why = f"{orders} order(s) against a floor of {MIN_ORDERS}"
        for k in ("reviews", "repeat", "support_burden", "contribution"):
            out[k] = _unmeasured(why, f"n >= {MIN_ORDERS} orders")
    else:
        out["reviews"] = _measured(round(sum(r["reviews"] for r in rows) / orders, 4),
                                   n=orders)
        out["repeat"] = _measured(round(sum(r["repeat_orders"] for r in rows) / orders, 4),
                                  n=orders)
        out["support_burden"] = _measured(
            round(sum(r["support_cases"] for r in rows) / orders, 4), n=orders)
        contribution = sum(r["contribution_cad"] for r in rows)
        out["contribution"] = _measured(round(contribution, 2), n=orders)
    if visits >= MIN_VISITS and orders >= MIN_ORDERS:
        out["contribution_per_visit"] = _measured(
            round(sum(r["contribution_cad"] for r in rows) / visits, 4), n=visits)
    else:
        out["contribution_per_visit"] = _unmeasured(
            f"{visits} visits and {orders} orders against floors of {MIN_VISITS} and "
            f"{MIN_ORDERS}", f"n >= {MIN_VISITS} visits and >= {MIN_ORDERS} orders")
    return out


def by_attribute(rows: list[dict]) -> dict:
    """Every attribute value's outcomes, refused below the concept minimum."""
    out: dict[str, dict] = {}
    for attr in ATTRIBUTES:
        values: dict[str, list[dict]] = {}
        for r in rows:
            values.setdefault(str(r[attr]), []).append(r)
        out[attr] = {}
        for value, group in sorted(values.items()):
            with_outcomes = [g for g in group if g["outcome_periods"] or g["orders"]]
            if len(with_outcomes) < MIN_CONCEPTS_PER_VALUE:
                out[attr][value] = {"status": UNMEASURED, "concepts": len(group),
                                    "with_outcomes": len(with_outcomes),
                                    "why": (f"{len(with_outcomes)} concept(s) with outcomes "
                                            f"against a floor of {MIN_CONCEPTS_PER_VALUE}"),
                                    "needs": f"n >= {MIN_CONCEPTS_PER_VALUE} concepts"}
            else:
                out[attr][value] = {"status": MEASURED, "concepts": len(with_outcomes),
                                    "metrics": _metrics(with_outcomes)}
    return out


def novelty_check(rows: list[dict]) -> dict:
    """Do high-novelty concepts outperform low-novelty ones? Reported, never rewarded."""
    scored = [r for r in rows if r["novelty"] is not None
              and r["visits"] >= 1 and (r["outcome_periods"] or r["orders"])]
    base = {"novelty_is_rewarded": False,
            "rule": ("novelty is a measured structural distance and is never a score. This "
                     "check reports whether the more novel half earned more per visit; the "
                     "answer is a fact about buyers, in either direction (#89)")}
    if len(scored) < 2 * MIN_CONCEPTS_PER_GROUP:
        return {**base, "status": UNMEASURED, "high_novelty_outperforms": None,
                "why": (f"{len(scored)} concept(s) with outcomes against a floor of "
                        f"{2 * MIN_CONCEPTS_PER_GROUP} ({MIN_CONCEPTS_PER_GROUP} per half)"),
                "needs": f"n >= {2 * MIN_CONCEPTS_PER_GROUP} concepts with outcomes"}
    scored.sort(key=lambda r: (r["novelty"], r["concept"]))
    half = len(scored) // 2
    low, high = scored[:half], scored[len(scored) - half:]
    groups = {}
    for name, group in (("low", low), ("high", high)):
        visits = sum(r["visits"] for r in group)
        orders = sum(r["orders"] for r in group)
        groups[name] = {"concepts": [r["concept"] for r in group], "visits": visits,
                        "orders": orders,
                        "novelty_range": [group[0]["novelty"], group[-1]["novelty"]]}
        if visits < MIN_VISITS or orders < MIN_ORDERS:
            return {**base, "status": UNMEASURED, "high_novelty_outperforms": None,
                    "groups": groups,
                    "why": (f"the {name}-novelty half has {visits} visits and {orders} "
                            f"orders against floors of {MIN_VISITS} and {MIN_ORDERS}"),
                    "needs": f"n >= {MIN_VISITS} visits and >= {MIN_ORDERS} orders per half"}
        groups[name]["contribution_per_visit"] = round(
            sum(r["contribution_cad"] for r in group) / visits, 4)
    outperforms = (groups["high"]["contribution_per_visit"]
                   > groups["low"]["contribution_per_visit"])
    useful = sorted(r["concept"] for r in high if r["visits"] and (
        r["contribution_cad"] / r["visits"]) >= groups["low"]["contribution_per_visit"])
    return {**base, "status": MEASURED, "high_novelty_outperforms": outperforms,
            "groups": groups, "useful_originality": useful,
            "note": ("useful_originality lists the high-novelty concepts that also earned at "
                     "least the low-novelty half's contribution per visit: originality that "
                     "created demand, rather than originality")}


def learn(db, concepts: list | None = None) -> dict:
    """The daily pass: the join, the per-attribute table and the novelty check."""
    rows = outcomes_by_concept(db, concepts)
    with_outcomes = [r for r in rows if r["outcome_periods"] or r["orders"]]
    novelty = novelty_check(rows)
    attrs = by_attribute(rows)
    measured_values = sum(1 for a in attrs.values() for v in a.values()
                          if v["status"] == MEASURED)
    status = MEASURED if (measured_values or novelty["status"] == MEASURED) else UNMEASURED
    return {
        "status": status,
        "why": ("" if status == MEASURED else
                "no concept has outcomes above the minimums: nothing is live, so no buyer "
                "has told us which originality they want" if not with_outcomes else
                "outcomes exist but no attribute value reaches the minimum n"),
        "concepts": len(rows), "concepts_with_outcomes": len(with_outcomes),
        "overall": _metrics(with_outcomes) if with_outcomes else None,
        "by_attribute": attrs, "novelty": novelty,
        "minimums": {"concepts_per_value": MIN_CONCEPTS_PER_VALUE,
                     "concepts_per_novelty_half": MIN_CONCEPTS_PER_GROUP,
                     "visits": MIN_VISITS, "orders": MIN_ORDERS},
        "rows": rows,
    }
