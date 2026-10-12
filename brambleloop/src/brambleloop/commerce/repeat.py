"""The repeat purchase engine, in the two halves it actually has (#252).

Requirement 252 asks for two different things and only one of them needs a customer.

**Recommendation is catalogue arithmetic.** Given the product somebody bought first, the
relevant next project is another design in the same category, the matching collection is
the family it belongs to, and the future-season product is whichever seasonal design's buying
window opens next. All three are read from the concept pool this company already maintains,
so they can be computed today for every product in it, and the first buyer's post-purchase
page can carry them on day one rather than after a hundred buyers have taught the system what
it could have read.

**Repeat rate is a measurement.** Thirty, sixty, ninety and one-hundred-and-eighty-day repeat
by first product, category and season is a division with customers in the denominator, and
there are none. The window arithmetic lives here, composed from `commerce.cohorts`, and it
refuses without orders rather than reporting zero -- because a repeat rate of zero is the
worst possible result and an empty table is not a result at all.

One rule the recommendation half keeps that a recommender usually does not: it never
recommends the product the buyer already owns, and never a bundle that contains it. A "you
might also like" pointing at what somebody just paid for is the fastest way to teach the
hundred buyers who matter most that the shop is not paying attention.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from ..radar.market import SEASONAL_EVENTS
from ..radar.opportunity import POOL, ConceptSeed
from . import cohorts

# The horizons the requirement names, in days.
HORIZONS: tuple[int, ...] = (30, 60, 90, 180)

# The three axes a repeat rate is measured on (#252): first product, category, season.
WINDOW_AXES: tuple[str, ...] = ("first_product", "first_category", "first_season")

# How many of each kind of recommendation the post-purchase surface carries. Three, because
# a list a buyer can read without scrolling is a list they read.
PER_KIND = 3


class RepeatRefused(ValueError):
    """A product nobody sells, or a rate with nobody in the denominator."""


def _seed(slug: str) -> ConceptSeed:
    for s in POOL:
        if s.slug == slug or slug.startswith(s.slug + "-"):
            return s
    raise RepeatRefused(f"{slug!r} is not in the concept pool, so nothing can follow it")


def _event_date(name: str | None) -> date | None:
    for e in SEASONAL_EVENTS:
        if e.name == name:
            return e.event_date
    return None


def _contains(bundle: ConceptSeed, slug: str) -> bool:
    """Whether a bundle includes the product, read from its family rather than guessed."""
    return bool(bundle.is_bundle and bundle.family
                and any(m.slug == slug and m.family == bundle.family for m in POOL))


def recommend(first_slug: str, *, today: date | None = None) -> dict:
    """What a buyer of `first_slug` is shown next: a project, a collection, a season."""
    bought = _seed(first_slug)
    today = today or datetime.now(timezone.utc).date()
    others = [s for s in POOL if s.slug != bought.slug]

    # The relevant next project: same category, a design of its own, not the one they own.
    projects = [s for s in others
                if s.category == bought.category and not s.is_bundle]
    # Prefer the same family, then evergreen, then whatever else is in the category.
    projects.sort(key=lambda s: (s.family != bought.family, not s.evergreen, s.slug))

    # The matching collection: the bundle for this family, if one exists, minus any bundle
    # that already contains the product they own.
    collections = [s for s in others if s.is_bundle and s.family == bought.family
                   and not _contains(s, bought.slug)]
    owned_bundle = [s.slug for s in others if _contains(s, bought.slug)]

    # The future-season product: the seasonal design whose window opens soonest after today.
    seasonal = []
    for s in others:
        when = _event_date(s.season)
        if when is None or s.is_bundle:
            continue
        if s.season == bought.season:
            continue   # the season they just bought for is not a future season
        days = (when - today).days
        if days > 0:
            seasonal.append((days, s))
    seasonal.sort(key=lambda t: (t[0], t[1].slug))

    def row(s: ConceptSeed, why: str) -> dict:
        return {"slug": s.slug, "title": s.title, "category": s.category,
                "season": s.season, "family": s.family, "why": why}

    return {
        "first_product": bought.slug,
        "next_project": [row(s, ("same family" if s.family == bought.family else
                                 "same category") + ", a design of its own")
                         for s in projects[:PER_KIND]],
        "matching_collection": [row(s, "the collection this design belongs to")
                                for s in collections[:PER_KIND]],
        "future_season": [row(s, f"buying window opens in {d} days")
                          for d, s in seasonal[:PER_KIND]],
        "never_recommended": [bought.slug] + owned_bundle,
        "basis": "catalogue arithmetic over the concept pool; no purchase data needed or used",
        "note": ("a recommendation pointing at what somebody just paid for is the fastest way "
                 "to teach the hundred buyers who matter most that the shop is not paying "
                 "attention, so the product they own and any bundle containing it are "
                 "excluded by construction"),
    }


def coverage() -> dict:
    """Which products have something to recommend after them, and which are dead ends."""
    dead_ends = []
    rows = {}
    for s in POOL:
        if s.is_bundle:
            continue
        r = recommend(s.slug, today=date(2026, 1, 1))
        kinds = [k for k in ("next_project", "matching_collection", "future_season") if r[k]]
        rows[s.slug] = kinds
        if not kinds:
            dead_ends.append(s.slug)
    return {"products": len(rows), "dead_ends": dead_ends, "by_product": rows,
            "note": ("every product has at least one thing to recommend after it"
                     if not dead_ends else
                     f"{dead_ends} have nothing to recommend after them, which is a "
                     f"catalogue gap rather than a recommender gap")}


# ---------------------------------------------------------------------------
# The measurement half. Composed from cohorts, and refusing without orders.


def _rows_for(orders: list[dict], axis: str, value: str) -> list[dict]:
    """Fold raw order rows into per-customer rows of the shape cohorts.repeat_rate reads."""
    by_customer: dict[str, list[dict]] = {}
    for o in orders:
        by_customer.setdefault(o["customer_ref"], []).append(o)
    rows = []
    for ref, mine in by_customer.items():
        mine = sorted((o for o in mine if not o.get("refunded")),
                      key=lambda o: cohorts._aware(o["at"]))
        if not mine:
            continue
        first = mine[0]
        key = {"first_product": first.get("product_slug"),
               "first_category": first.get("category"),
               "first_season": first.get("season") or "none"}[axis]
        if key != value:
            continue
        rows.append({
            "customer_ref": ref, "orders": len(mine),
            "first_order_at": cohorts._aware(first["at"]),
            "second_order_at": cohorts._aware(mine[1]["at"]) if len(mine) > 1 else None,
            "contribution_cad": sum(float(o.get("contribution_cad", 0.0)) for o in mine),
            "revenue_cad": sum(float(o.get("revenue_cad", 0.0)) for o in mine),
            "categories": sorted({o.get("category") for o in mine if o.get("category")}),
        })
    return rows


def windows(orders: list[dict], *, axis: str, value: str,
            as_of: datetime | None = None) -> dict:
    """30/60/90/180-day repeat rate for one cohort, or the refusal with the reason (#252).

    Each order is {customer_ref, at, product_slug, category, season, contribution_cad,
    revenue_cad, refunded}. No orders is a refusal, not a zero: a repeat rate of zero is the
    worst possible result and an empty table is not a result.
    """
    if axis not in WINDOW_AXES:
        raise RepeatRefused(f"{axis!r} is not a repeat axis: {list(WINDOW_AXES)}")
    if not orders:
        return {
            "measurable": False, "status": "UNMEASURED", "axis": axis, "value": value,
            "why": ("no orders exist. A repeat rate is a division with customers in the "
                    "denominator; without any it is not zero, it is not a number"),
            "needs": ["orders, which need a shop, a listing and a buyer"],
            "horizons_days": list(HORIZONS),
        }
    rows = _rows_for(orders, axis, value)
    result = {f"{h}d": cohorts.repeat_rate(rows, horizon_days=h, as_of=as_of)
              for h in HORIZONS}
    measured = [k for k, v in result.items() if v["measurable"]]
    return {
        "measurable": bool(measured), "status": "measured" if measured else "UNMEASURED",
        "axis": axis, "value": value, "customers": len(rows),
        "floor": cohorts.MIN_COHORT_N, "windows": result,
        "measured_horizons": measured,
        "why": ("" if measured else
                f"{len(rows)} customer(s) in this cohort against a floor of "
                f"{cohorts.MIN_COHORT_N}, or none of them has had a full horizon to repeat in"),
    }


def state(db=None) -> dict:
    """What the engine can do today, and what it cannot, stated separately."""
    cov = coverage()
    out = {
        "recommendation": {"executable": True, "products_covered": cov["products"],
                           "dead_ends": cov["dead_ends"], "kinds": ["next_project",
                                                                     "matching_collection",
                                                                     "future_season"]},
        "measurement": {"executable": False, "status": "UNMEASURED",
                        "horizons_days": list(HORIZONS), "axes": list(WINDOW_AXES),
                        "floor": cohorts.MIN_COHORT_N,
                        "why": "no orders exist; see commerce.cohorts.state for the source gate"},
        "note": ("Recommendation is catalogue arithmetic and runs today for every product in "
                 "the pool. Repeat rate is a measurement with customers in the denominator and "
                 "there are none, so it is UNMEASURED rather than zero (#252)."),
    }
    if db is not None:
        out["cohorts"] = cohorts.state(db)
    return out
