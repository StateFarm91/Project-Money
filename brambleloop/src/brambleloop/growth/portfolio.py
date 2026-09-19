"""Portfolio roles, concentration, and the failure that would end the target.

Requirements 231, 232, 234, 270. CA$5,000 a month must not require one viral hit, and the way
a catalogue quietly comes to require one is not a decision anybody makes — it is a winner that
grows while nothing else is built, until the portfolio is one product and eleven hobbies.

So every SKU carries a role it was created for, concentration is measured rather than felt, and
the stress test asks the only question that matters: if the best thing here disappeared, would
the target survive?

The roles are not labels applied afterwards. #232's point is that product creation should be
guided by portfolio gaps rather than raw listing count, which only works if a gap is a thing
the system can see — which means the roles have to be declared and counted.
"""
from __future__ import annotations

from dataclasses import dataclass

HERO = "HERO"                 # the traffic and revenue driver
CORE = "CORE"                 # reliable evergreen or seasonal earner
ENTRY = "ENTRY"               # low-friction acquisition product
BUNDLE = "BUNDLE"             # raises order value
CROSS_SELL = "CROSS_SELL"     # attaches to something else
EXPERIMENT = "EXPERIMENT"     # a learning vehicle, expected to mostly fail
RETIRE = "RETIRE"             # a candidate for withdrawal

ROLES: tuple[str, ...] = (HERO, CORE, ENTRY, BUNDLE, CROSS_SELL, EXPERIMENT, RETIRE)

# What a healthy portfolio looks like as shares of the catalogue. Not precise targets — a
# range, because the useful signal is "we have no entry products at all", not "entry is 14%
# and should be 15%".
HEALTHY_SHARE: dict[str, tuple[float, float]] = {
    HERO: (0.05, 0.20),
    CORE: (0.30, 0.60),
    ENTRY: (0.10, 0.25),
    BUNDLE: (0.05, 0.20),
    CROSS_SELL: (0.05, 0.20),
    EXPERIMENT: (0.05, 0.25),
}

# Above this share from one SKU, the portfolio is a single product with dependants.
CONCENTRATION_ALARM = 0.35


class PortfolioRefused(ValueError):
    """A role that does not exist, or a claim the evidence cannot carry."""


@dataclass(frozen=True)
class Position:
    slug: str
    role: str
    revenue_cad: float = 0.0
    orders: int = 0
    family: str = ""

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise PortfolioRefused(
                f"{self.slug}: {self.role!r} is not a portfolio role. Roles are declared so a "
                f"gap is something the system can see, which is what lets product creation "
                f"follow gaps rather than listing count (#232)")


def shape(positions: list[Position]) -> dict:
    """Role mix against the healthy range, and which roles are missing entirely."""
    total = len(positions)
    counts = {role: sum(1 for p in positions if p.role == role) for role in ROLES}
    shares = {role: (counts[role] / total if total else 0.0) for role in ROLES}

    gaps = []
    for role, (low, high) in HEALTHY_SHARE.items():
        share = shares[role]
        if share < low:
            gaps.append({"role": role, "share": round(share, 3), "want_at_least": low,
                         "missing_entirely": counts[role] == 0})
        elif share > high:
            gaps.append({"role": role, "share": round(share, 3), "want_at_most": high,
                         "missing_entirely": False})

    return {
        "skus": total,
        "counts": counts,
        "shares": {k: round(v, 3) for k, v in shares.items()},
        "gaps": sorted(gaps, key=lambda g: -abs(g["share"] - g.get("want_at_least",
                                                                  g.get("want_at_most", 0)))),
        "roles_absent": [r for r in ROLES if r != RETIRE and counts[r] == 0],
    }


def concentration(positions: list[Position]) -> dict:
    """How much of the revenue rests on how little of the catalogue (#231)."""
    earning = [p for p in positions if p.revenue_cad > 0]
    total = sum(p.revenue_cad for p in earning)
    if total <= 0:
        return {"measurable": False,
                "reason": ("no product has earned anything, so concentration is undefined "
                           "rather than zero — an empty portfolio is not a diversified one"),
                "top_1_share": None, "top_5_share": None, "families": 0}

    ranked = sorted(earning, key=lambda p: -p.revenue_cad)
    top1 = ranked[0].revenue_cad / total
    top5 = sum(p.revenue_cad for p in ranked[:5]) / total
    families = len({p.family for p in earning if p.family})
    return {
        "measurable": True,
        "top_1_share": round(top1, 3),
        "top_5_share": round(top5, 3),
        "top_sku": ranked[0].slug,
        "families": families,
        "alarm": top1 >= CONCENTRATION_ALARM,
        "note": (f"{ranked[0].slug} is {top1:.0%} of revenue: this is one product with "
                 f"dependants, not a portfolio"
                 if top1 >= CONCENTRATION_ALARM else
                 "no single product dominates the revenue"),
    }


def stress_test(positions: list[Position], *, target_cad: float = 5000.0) -> dict:
    """Remove the best thing and see whether the target survives (#270).

    Three plausible single failures, because they are the ones that actually happen: the top
    product gets copied or delisted, the top family goes out of fashion, and the season that
    carries the year does not repeat.
    """
    earning = [p for p in positions if p.revenue_cad > 0]
    total = sum(p.revenue_cad for p in earning)
    if total <= 0:
        return {"testable": False,
                "reason": ("nothing has earned anything, so there is no revenue to stress. "
                           "The target does not survive any scenario, including the one where "
                           "nothing goes wrong"),
                "scenarios": []}

    ranked = sorted(earning, key=lambda p: -p.revenue_cad)
    by_family: dict[str, float] = {}
    for p in earning:
        by_family[p.family or "unfamilied"] = by_family.get(
            p.family or "unfamilied", 0.0) + p.revenue_cad
    worst_family = max(by_family, key=by_family.get)

    scenarios = [
        {"scenario": "top SKU lost", "removed": ranked[0].slug,
         "remaining_cad": round(total - ranked[0].revenue_cad, 2)},
        {"scenario": "top family lost", "removed": worst_family,
         "remaining_cad": round(total - by_family[worst_family], 2)},
        {"scenario": "top three lost",
         "removed": ", ".join(p.slug for p in ranked[:3]),
         "remaining_cad": round(total - sum(p.revenue_cad for p in ranked[:3]), 2)},
    ]
    for s in scenarios:
        s["survives_target"] = s["remaining_cad"] >= target_cad
        s["shortfall_cad"] = round(max(0.0, target_cad - s["remaining_cad"]), 2)

    fragile = [s for s in scenarios if not s["survives_target"]]
    return {
        "testable": True,
        "current_cad": round(total, 2),
        "target_cad": target_cad,
        "scenarios": scenarios,
        "fragile_to": [s["scenario"] for s in fragile],
        "note": ("Exploiting a winner stays aggressive; this measures what it would cost to "
                 "lose it, so resilience is part of the confidence rather than an afterthought "
                 "(#270)."),
    }


def positions_from_db(db) -> list[Position]:
    """Read the portfolio from what the warehouse holds.

    Revenue comes from the ledger, so a product with no sales has a role and no earnings —
    which is the true state of every product this company has.
    """
    from sqlalchemy import select

    from ..core.models import LedgerEntry, Product

    with db.session() as s:
        products = list(s.scalars(select(Product)))
        sales = list(s.scalars(select(LedgerEntry).where(LedgerEntry.category == "sale")))

    earned: dict[str, float] = {}
    counted: dict[str, int] = {}
    for entry in sales:
        # `evidence_ref` carries the product where the sale recorded one.
        slug = (entry.evidence_ref or "").split(":")[-1]
        earned[slug] = earned.get(slug, 0.0) + entry.gross_cad
        counted[slug] = counted.get(slug, 0) + 1

    out = []
    for product in products:
        role = (product.detail or {}).get("portfolio_role", EXPERIMENT) \
            if hasattr(product, "detail") else EXPERIMENT
        out.append(Position(slug=product.slug, role=role if role in ROLES else EXPERIMENT,
                            revenue_cad=earned.get(product.slug, 0.0),
                            orders=counted.get(product.slug, 0),
                            family=(product.slug.split("-")[0] if product.slug else "")))
    return out


def report(db, *, target_cad: float = 5000.0) -> dict:
    positions = positions_from_db(db)
    return {
        "shape": shape(positions),
        "concentration": concentration(positions),
        "stress_test": stress_test(positions, target_cad=target_cad),
    }
