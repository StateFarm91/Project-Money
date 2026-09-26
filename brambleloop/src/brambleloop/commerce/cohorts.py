"""Customer cohorts, and the floor beneath which a cohort is a list of people (#11, #12).

Requirement 11 says to treat the first hundred legitimate buyers as a deliberate validation
cohort and to track where each came from, what they searched, what they bought, what it cost
to support them and whether they came back. Requirement 12 says to track the first product,
subsequent purchases, category affinity, time to repeat, order value and lifetime
contribution, and to optimise the last of those rather than single-listing revenue.

Both have said "schema and cohort machinery buildable now" since v1.3, and until this module
nothing existed: `core.models.Cohort` is a *launch* cohort -- an organic or promoted arm of a
listing test (#48) -- and has nothing to do with a person who bought something. The three
tables this module writes (`Customer`, `Order`, `CohortMembership`) are the customer half.

Three rules, and the third is the one that will be argued with.

**A customer is a reference, not a person.** `customer_ref` is whatever the order source
gives us that is stable across orders -- on Etsy, the buyer user id -- and never a name or an
email. Nothing #11 asks to learn needs either.

**A cohort is one axis.** First product, first category, first season, acquisition source. A
customer belongs to one value on each axis and is a row per axis, so a repeat rate is a query
and not a recomputation, and so "buyers whose first product was the mosaic blanket" and
"buyers who arrived from Pinterest" are two cohorts a reader cannot accidentally merge.

**Below `MIN_COHORT_N` a cohort metric is not produced.** Thirty is a stated floor, not a
learned one: with fewer, a single buyer moves the repeat rate by more than three points on
their own, and a rate one person can move is a fact about that person. The metric reports
UNMEASURED with the reason and the shortfall, and never a number with a caveat, because the
caveat is what gets dropped when the number is quoted.

Today every table is empty. This company has no shop, no listing and no order, and reading
Etsy's transaction history into these tables needs the `transactions_r` OAuth scope, which
the owner has not granted and which this module does not request: it is OWNER-GATED, stated
in `TRANSACTIONS_SCOPE`, and the schema is ready for the day it is.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..core.models import CohortMembership, Customer, Order, utcnow
from . import ladder

# Below this many customers a cohort metric is a fact about the people in it. One buyer
# changing their mind moves a rate over 29 by 3.4 points; that is the arithmetic behind
# the number, and it is a floor rather than a learned threshold.
MIN_COHORT_N = 30

# The first hundred are the validation cohort (#11). The number is the requirement's own.
VALIDATION_COHORT_SIZE = 100

AXES: tuple[str, ...] = ("first_product", "first_category", "first_season",
                         "acquisition_source", "validation")

# The scope that would fill these tables from Etsy, and why it is not requested here.
TRANSACTIONS_SCOPE = {
    "scope": "transactions_r",
    "status": "OWNER-GATED",
    "why": ("reading a shop's receipts is the one read scope that exposes buyer identities, "
            "and widening the OAuth grant is the owner's decision under the authority "
            "matrix, not this module's. Nothing here requests it; the schema is ready for "
            "the day it is granted"),
}


class CohortRefused(ValueError):
    """An axis nobody named, an order for nobody, or a metric claimed beneath the floor."""


def _check_axis(axis: str) -> None:
    if axis not in AXES:
        raise CohortRefused(f"{axis!r} is not a cohort axis: {list(AXES)}")


def _aware(at: datetime | None) -> datetime:
    if at is None:
        return utcnow()
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Writing. Nothing calls these today; they exist so the first real order has somewhere to go.


def record_customer(db, customer_ref: str, *, at: datetime | None = None,
                    acquisition_source: str = "unknown", search_term: str = "",
                    first_product_slug: str = "", first_category: str = "",
                    first_season: str = "none", casl_consent: bool = False) -> dict:
    """A buyer's first appearance, and their membership on every axis at once."""
    if not customer_ref or not customer_ref.strip():
        raise CohortRefused("a customer needs a stable reference; an empty one is nobody")
    if "@" in customer_ref:
        raise CohortRefused(
            "a customer reference may not be an email address: the reference is the "
            "platform's stable id, never personal data")

    when = _aware(at)
    with db.session() as s:
        existing = s.scalar(select(Customer).where(Customer.customer_ref == customer_ref))
        if existing is not None:
            return {"customer_id": existing.id, "created": False}

        rank = s.scalar(select(func.count(Customer.id))) or 0
        customer = Customer(
            customer_ref=customer_ref, first_seen_at=when,
            acquisition_source=acquisition_source, search_term=search_term,
            first_product_slug=first_product_slug, first_category=first_category,
            first_season=first_season or "none", casl_consent=casl_consent,
            interests=[first_category] if first_category else [],
        )
        s.add(customer)
        s.flush()
        memberships = {
            "first_product": first_product_slug or "unknown",
            "first_category": first_category or "unknown",
            "first_season": first_season or "none",
            "acquisition_source": acquisition_source or "unknown",
        }
        if rank < VALIDATION_COHORT_SIZE:
            memberships["validation"] = "first_hundred"
        for axis, value in memberships.items():
            s.add(CohortMembership(customer_id=customer.id, axis=axis, value=value,
                                   joined_at=when))
        s.commit()
        return {"customer_id": customer.id, "created": True,
                "memberships": memberships}


def record_order(db, customer_ref: str, external_ref: str, *, product_slug: str,
                 at: datetime | None = None, version: str = "", category: str = "",
                 price_cad: float = 0.0, revenue_cad: float | None = None,
                 contribution_cad: float = 0.0, acquisition_source: str = "unknown",
                 search_term: str = "", offsite_ad_attributed: bool = False,
                 cross_sell_of: str = "", refunded: bool = False) -> dict:
    """One order against a recorded customer. Refuses an order for nobody."""
    if price_cad < 0 or contribution_cad > max(price_cad, revenue_cad or 0.0) + 1e-9:
        raise CohortRefused(
            f"contribution CA${contribution_cad:.2f} above the order's own revenue is a "
            f"bookkeeping fault, not a remarkable margin")
    when = _aware(at)
    with db.session() as s:
        customer = s.scalar(select(Customer).where(Customer.customer_ref == customer_ref))
        if customer is None:
            raise CohortRefused(
                f"no customer {customer_ref!r}: an order belongs to a buyer, and recording "
                f"the order first is how a cohort ends up counting orders it cannot place")
        if s.scalar(select(Order).where(Order.external_ref == external_ref)) is not None:
            return {"created": False, "external_ref": external_ref}
        prior = s.scalar(select(func.count(Order.id)).where(Order.customer_id == customer.id))
        order = Order(
            customer_id=customer.id, external_ref=external_ref, at=when,
            product_slug=product_slug, version=version, category=category,
            price_cad=price_cad,
            revenue_cad=price_cad if revenue_cad is None else revenue_cad,
            contribution_cad=contribution_cad, acquisition_source=acquisition_source,
            search_term=search_term, offsite_ad_attributed=offsite_ad_attributed,
            is_repeat=bool(prior), cross_sell_of=cross_sell_of, refunded=refunded,
        )
        s.add(order)
        if category and category not in (customer.interests or []):
            customer.interests = list(customer.interests or []) + [category]
        s.commit()
        return {"created": True, "order_id": order.id, "is_repeat": order.is_repeat}


# ---------------------------------------------------------------------------
# Reading.


def members(db, axis: str, value: str) -> list[dict]:
    """Every customer in one cohort, with their orders folded in."""
    _check_axis(axis)
    with db.session() as s:
        rows = s.execute(
            select(Customer).join(CohortMembership,
                                  CohortMembership.customer_id == Customer.id)
            .where(CohortMembership.axis == axis, CohortMembership.value == value)
            .order_by(Customer.first_seen_at)).scalars().all()
        out = []
        for c in rows:
            orders = s.execute(select(Order).where(Order.customer_id == c.id)
                               .order_by(Order.at)).scalars().all()
            kept = [o for o in orders if not o.refunded]
            first_at = kept[0].at if kept else None
            second_at = kept[1].at if len(kept) > 1 else None
            out.append({
                "customer_ref": c.customer_ref,
                "first_seen_at": _aware(c.first_seen_at).isoformat(),
                "orders": len(kept),
                "refunded_orders": len(orders) - len(kept),
                "contribution_cad": round(sum(o.contribution_cad for o in kept), 2),
                "revenue_cad": round(sum(o.revenue_cad for o in kept), 2),
                "first_order_at": _aware(first_at) if first_at else None,
                "second_order_at": _aware(second_at) if second_at else None,
                "categories": sorted({o.category for o in kept if o.category}),
            })
        return out


def _unmeasured(why: str, **extra) -> dict:
    return {"measurable": False, "value": None, "status": "UNMEASURED", "why": why, **extra}


def repeat_rate(rows: list[dict], *, horizon_days: int, as_of: datetime | None = None) -> dict:
    """The share of a cohort that bought again within `horizon_days` of its first order.

    Right-censored on purpose: a customer whose first order was twenty days ago cannot have
    failed to repeat within thirty, so they are not in the denominator yet. Counting them
    would read a young cohort as a disloyal one.
    """
    if horizon_days <= 0:
        raise CohortRefused("a repeat horizon needs to be a positive number of days")
    now = _aware(as_of)
    eligible = [r for r in rows if r["first_order_at"] is not None
                and now - r["first_order_at"] >= timedelta(days=horizon_days)]
    if len(eligible) < MIN_COHORT_N:
        return _unmeasured(
            f"{len(eligible)} customer(s) have had {horizon_days} days to repeat, against a "
            f"floor of {MIN_COHORT_N}. One buyer moves a rate over this few by more than "
            f"three points, and a rate one person can move is a fact about that person",
            eligible=len(eligible), floor=MIN_COHORT_N, horizon_days=horizon_days,
            needs=f"{MIN_COHORT_N - len(eligible)} more customer(s) past the horizon")
    repeated = [r for r in eligible if r["second_order_at"] is not None
                and r["second_order_at"] - r["first_order_at"] <= timedelta(days=horizon_days)]
    return {"measurable": True, "status": "measured",
            "value": round(len(repeated) / len(eligible), 4),
            "repeated": len(repeated), "eligible": len(eligible),
            "horizon_days": horizon_days, "floor": MIN_COHORT_N}


def time_to_repeat(rows: list[dict]) -> dict:
    """Median days from first to second order, over the customers who have a second."""
    gaps = sorted((r["second_order_at"] - r["first_order_at"]).days
                  for r in rows if r["second_order_at"] is not None)
    if len(gaps) < MIN_COHORT_N:
        return _unmeasured(
            f"{len(gaps)} repeat buyer(s) against a floor of {MIN_COHORT_N}: a median over "
            f"this few is whichever buyer happened to be in the middle",
            repeat_buyers=len(gaps), floor=MIN_COHORT_N)
    mid = len(gaps) // 2
    median = gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2
    return {"measurable": True, "status": "measured", "value": median,
            "repeat_buyers": len(gaps), "floor": MIN_COHORT_N}


def average_order_value(rows: list[dict]) -> dict:
    orders = sum(r["orders"] for r in rows)
    if len(rows) < MIN_COHORT_N or not orders:
        return _unmeasured(
            f"{len(rows)} customer(s) and {orders} order(s) against a floor of "
            f"{MIN_COHORT_N} customers", customers=len(rows), floor=MIN_COHORT_N)
    revenue = sum(r["revenue_cad"] for r in rows)
    return {"measurable": True, "status": "measured", "value": round(revenue / orders, 2),
            "orders": orders, "floor": MIN_COHORT_N}


def metrics(db, axis: str, value: str, *, as_of: datetime | None = None) -> dict:
    """Everything #12 asks of one cohort, each metric measured or UNMEASURED with its reason."""
    rows = members(db, axis, value)
    ltv = ladder.lifetime_value(
        [{"orders": r["orders"], "contribution_cad": r["contribution_cad"]} for r in rows],
        min_buyers=MIN_COHORT_N)
    if not ltv["measurable"]:
        ltv = {**ltv, "status": "UNMEASURED", "value": None}
    else:
        ltv = {**ltv, "status": "measured", "value": ltv["contribution_per_buyer_cad"]}

    affinity: dict[str, int] = {}
    for r in rows:
        for c in r["categories"]:
            affinity[c] = affinity.get(c, 0) + 1

    return {
        "axis": axis, "value": value, "customers": len(rows), "floor": MIN_COHORT_N,
        "readable": len(rows) >= MIN_COHORT_N,
        "repeat_rate": {f"{h}d": repeat_rate(rows, horizon_days=h, as_of=as_of)
                        for h in (30, 60, 90, 180)},
        "time_to_repeat_days": time_to_repeat(rows),
        "aov_cad": average_order_value(rows),
        "lifetime_contribution": ltv,
        "category_affinity": (dict(sorted(affinity.items(), key=lambda kv: -kv[1]))
                              if len(rows) >= MIN_COHORT_N else
                              _unmeasured("affinity over fewer than the floor is a list of "
                                          "what a few people bought", floor=MIN_COHORT_N)),
        "note": ("" if len(rows) >= MIN_COHORT_N else
                 f"{len(rows)} customer(s) in this cohort. Below {MIN_COHORT_N} every metric "
                 f"here is UNMEASURED with its reason, and none is produced as a number with "
                 f"a caveat, because the caveat is what gets dropped when the number is quoted"),
    }


def state(db) -> dict:
    """What the customer tables hold, which cohorts exist, and what is gated on the owner."""
    with db.session() as s:
        customers = s.scalar(select(func.count(Customer.id))) or 0
        orders = s.scalar(select(func.count(Order.id))) or 0
        occupied = s.execute(
            select(CohortMembership.axis, CohortMembership.value,
                   func.count(CohortMembership.id))
            .group_by(CohortMembership.axis, CohortMembership.value)).all()
    cohorts = [{"axis": a, "value": v, "customers": n, "readable": n >= MIN_COHORT_N}
               for a, v, n in sorted(occupied)]
    return {
        "customers": customers,
        "orders": orders,
        "validation_cohort": {"size": VALIDATION_COHORT_SIZE,
                              "filled": min(customers, VALIDATION_COHORT_SIZE),
                              "complete": customers >= VALIDATION_COHORT_SIZE},
        "axes": list(AXES),
        "floor": MIN_COHORT_N,
        "cohorts": cohorts,
        "readable_cohorts": sum(1 for c in cohorts if c["readable"]),
        "source": TRANSACTIONS_SCOPE,
        "note": ("no customer exists. The tables, the axes and the floor are built; every "
                 "metric they would carry is UNMEASURED, which is different from zero and is "
                 "reported as the first. Filling them from Etsy needs the transactions_r "
                 "scope, which is the owner's decision (#11, #12)"
                 if not customers else
                 f"{customers} customer(s), {orders} order(s), "
                 f"{sum(1 for c in cohorts if c['readable'])} cohort(s) above the floor"),
    }
