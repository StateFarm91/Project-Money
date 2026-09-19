"""Price memory and control cohorts: two names for one discipline.

Requirements 46 and 48. Both exist because the same mistake produces both, and it is the most
natural mistake in commerce: something changed, sales moved, therefore the thing that changed
caused it.

The price version: the price dropped in November and sales rose, so the product is
price-sensitive. It is December that is price-sensitive. A business that learns this lesson
once builds a permanent discount into a category that never needed one, and the discount is
now the regular price.

The traffic version: ads were switched on and conversion improved, so the listing improved.
Paid traffic is differently intentioned traffic, and a conversion rate measured on it is a
statement about the audience, not the page. Scaling on that number buys more of the audience
and none of the improvement.

So an observation carries its confounders as columns — season, traffic source, sale state —
and a comparison between two price points refuses to be made across different ones. Not
warns: refuses. A warning attached to a number is read by the person who wrote it and by
nobody afterwards, and the number travels on alone.

The honest empty state matters here more than almost anywhere else. This company has no sales,
so every function in this module reports that elasticity is unmeasured rather than returning a
coefficient of zero. A zero elasticity is a specific and very wrong claim: it says price does
not matter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Below this, a rate is not a rate. Two orders at CA$12 and one at CA$14 is not a demand curve.
MIN_ORDERS_PER_POINT = 10
MIN_VISITS_PER_POINT = 200

# Two price points closer than this are indistinguishable from noise in a market this size.
MIN_PRICE_SEPARATION = 0.10  # 10% apart

ORGANIC = "organic"
PROMOTED = "promoted"
ARMS: tuple[str, ...] = (ORGANIC, PROMOTED)


class ElasticityRefused(ValueError):
    """A comparison across a confounder, or a conclusion from too little."""


@dataclass(frozen=True)
class PricePoint:
    product_slug: str
    category: str
    price_cad: float
    visits: int
    orders: int
    revenue_cad: float
    contribution_cad: float
    season: str = ""
    traffic_source: str = ""
    on_sale: bool = False
    from_date: str = ""
    to_date: str = ""

    @property
    def conversion(self) -> float:
        return self.orders / self.visits if self.visits else 0.0

    @property
    def readable(self) -> bool:
        return self.orders >= MIN_ORDERS_PER_POINT and self.visits >= MIN_VISITS_PER_POINT

    def to_dict(self) -> dict:
        return {"product": self.product_slug, "category": self.category,
                "price_cad": self.price_cad, "visits": self.visits, "orders": self.orders,
                "conversion": round(self.conversion, 5),
                "contribution_cad": self.contribution_cad,
                "season": self.season, "traffic_source": self.traffic_source,
                "on_sale": self.on_sale, "readable": self.readable}


def record(db, point: PricePoint) -> int:
    """Keep a price point with everything that could explain it away."""
    from ..core.models import PriceObservation

    with db.session() as s:
        row = PriceObservation(
            product_slug=point.product_slug, category=point.category,
            price_cad=point.price_cad, on_sale=point.on_sale,
            regular_price_cad=point.price_cad if not point.on_sale else 0.0,
            traffic_source=point.traffic_source, season=point.season,
            from_date=point.from_date or date.today().isoformat(),
            to_date=point.to_date or date.today().isoformat(),
            visits=point.visits, orders=point.orders, revenue_cad=point.revenue_cad,
            contribution_cad=point.contribution_cad)
        s.add(row)
        s.flush()
        return row.id


def compare(a: PricePoint, b: PricePoint) -> dict:
    """Two price points, and the four reasons this comparison may not be made.

    Refusing rather than warning is the whole design. A warning attached to a number is read
    by the person who wrote it and by nobody afterwards; the number travels on alone and
    arrives somewhere it is treated as a measurement.
    """
    problems: list[str] = []
    if a.season != b.season:
        problems.append(
            f"different seasons ({a.season or 'unset'} vs {b.season or 'unset'}): this would "
            f"read December's willingness to buy as a response to the price")
    if a.traffic_source != b.traffic_source:
        problems.append(
            f"different traffic sources ({a.traffic_source or 'unset'} vs "
            f"{b.traffic_source or 'unset'}): a conversion rate measured on differently "
            f"intentioned traffic is a statement about the audience, not the price")
    if a.category != b.category:
        problems.append("different categories: elasticity is category-specific (#46)")
    for point, label in ((a, "a"), (b, "b")):
        if not point.readable:
            problems.append(
                f"point {label}: {point.orders} orders on {point.visits} visits is below "
                f"{MIN_ORDERS_PER_POINT}/{MIN_VISITS_PER_POINT}; that is not a rate")
    if a.price_cad and b.price_cad:
        separation = abs(a.price_cad - b.price_cad) / max(a.price_cad, b.price_cad)
        if separation < MIN_PRICE_SEPARATION:
            problems.append(
                f"prices are {separation:.0%} apart, below {MIN_PRICE_SEPARATION:.0%}: a "
                f"difference this small is indistinguishable from noise at this volume")

    if problems:
        return {"comparable": False, "problems": problems, "elasticity": None,
                "note": ("Refused rather than flagged. A warning attached to a number is "
                         "read once and the number travels on alone.")}

    # Arc elasticity: symmetric, so which point is "before" does not change the answer.
    dq = (b.orders - a.orders) / ((a.orders + b.orders) / 2)
    dp = (b.price_cad - a.price_cad) / ((a.price_cad + b.price_cad) / 2)
    elasticity = round(dq / dp, 3) if dp else None
    better = a if a.contribution_cad >= b.contribution_cad else b
    return {
        "comparable": True,
        "problems": [],
        "elasticity": elasticity,
        "elastic": elasticity is not None and abs(elasticity) > 1.0,
        "higher_contribution_at_cad": better.price_cad,
        "points": [a.to_dict(), b.to_dict()],
        "note": ("Contribution decides, not revenue and not units: a price that sells more "
                 "at a worse margin is a busier version of the same business."),
    }


def memory(db, category: str = "") -> dict:
    """What this company has actually learned about price, which today is nothing.

    Reported as unmeasured rather than as an elasticity of zero. Zero is not the absence of a
    claim; it is the claim that price does not matter, which is the most expensive thing this
    module could accidentally say.
    """
    from sqlalchemy import select

    from ..core.models import PriceObservation

    with db.session() as s:
        query = select(PriceObservation)
        if category:
            query = query.where(PriceObservation.category == category)
        rows = list(s.scalars(query))

    if not rows:
        return {"measurable": False, "observations": 0,
                "reason": ("no price has been held long enough at a known volume to learn "
                           "anything. This is unmeasured, not inelastic -- an elasticity of "
                           "zero is the claim that price does not matter"),
                "categories": [], "elasticity": None}

    by_category: dict[str, list] = {}
    for r in rows:
        by_category.setdefault(r.category or "uncategorised", []).append(r)

    out = []
    for cat, points in sorted(by_category.items()):
        readable = [p for p in points
                    if p.orders >= MIN_ORDERS_PER_POINT and p.visits >= MIN_VISITS_PER_POINT]
        out.append({"category": cat, "observations": len(points),
                    "readable_points": len(readable),
                    "prices_held": sorted({round(p.price_cad, 2) for p in points}),
                    "measurable": len(readable) >= 2})
    return {"measurable": any(c["measurable"] for c in out), "observations": len(rows),
            "categories": out,
            "note": ("Elasticity is category-specific and needs two readable points held "
                     "under the same season and traffic source (#46).")}


# ---------------------------------------------------------------------------
# Control cohorts (#48)


@dataclass(frozen=True)
class Arm:
    key: str
    product_slug: str
    arm: str
    visits: int
    orders: int
    revenue_cad: float
    spend_cad: float = 0.0
    assisted: int = 0
    direct: int = 0

    def __post_init__(self) -> None:
        if self.arm not in ARMS:
            raise ElasticityRefused(f"{self.arm!r} is not a cohort arm: {list(ARMS)}")

    @property
    def conversion(self) -> float:
        return self.orders / self.visits if self.visits else 0.0

    def to_dict(self) -> dict:
        return {"key": self.key, "product": self.product_slug, "arm": self.arm,
                "visits": self.visits, "orders": self.orders,
                "conversion": round(self.conversion, 5), "revenue_cad": self.revenue_cad,
                "spend_cad": self.spend_cad, "assisted": self.assisted,
                "direct": self.direct}


def record_cohort(db, arm: Arm, *, from_date: str = "", to_date: str = "") -> int:
    from ..core.models import Cohort

    with db.session() as s:
        row = Cohort(key=arm.key, product_slug=arm.product_slug, arm=arm.arm,
                     from_date=from_date or date.today().isoformat(),
                     to_date=to_date or date.today().isoformat(),
                     visits=arm.visits, orders=arm.orders, revenue_cad=arm.revenue_cad,
                     spend_cad=arm.spend_cad, assisted=arm.assisted, direct=arm.direct)
        s.add(row)
        s.flush()
        return row.id


def holdout(organic: Arm | None, promoted: Arm | None) -> dict:
    """Did the listing get better, or did we buy more traffic? (#48)

    Answerable only with both arms. With promoted alone the conversion rate is a fact about
    who was shown the listing, and scaling on it buys more of that audience and none of the
    improvement — which is the specific failure that turns a working ad budget into a
    permanent one.
    """
    if organic is None or promoted is None:
        missing = "organic control" if organic is None else "promoted arm"
        return {"separable": False,
                "reason": (f"no {missing}. A single arm cannot distinguish a listing that "
                           f"improved from traffic that was bought, and the number looks "
                           f"the same either way"),
                "have": [a.to_dict() for a in (organic, promoted) if a is not None]}

    if not organic.visits or not promoted.visits:
        return {"separable": False,
                "reason": "an arm with no visits is not a control, it is an empty row",
                "have": [organic.to_dict(), promoted.to_dict()]}

    lift = promoted.conversion - organic.conversion
    incremental_orders = promoted.orders - round(organic.conversion * promoted.visits)
    cost_per_incremental = (round(promoted.spend_cad / incremental_orders, 2)
                            if incremental_orders > 0 else None)
    return {
        "separable": True,
        "organic": organic.to_dict(),
        "promoted": promoted.to_dict(),
        "conversion_lift": round(lift, 5),
        "incremental_orders": incremental_orders,
        "cost_per_incremental_order_cad": cost_per_incremental,
        "paid_traffic_converts_worse": lift < 0,
        "note": ("Incremental orders are measured against what the organic rate would have "
                 "produced on the same traffic, so the control's own performance is not "
                 "counted as a result of the spend."
                 if incremental_orders > 0 else
                 "the promoted arm produced no orders beyond what the organic rate predicts "
                 "for its traffic: this spend bought visits, not sales"),
    }
