"""Portfolio mix: roles, concentration, and the failure that would end the target.

This sits beside `portfolio.py` rather than inside it, and the distinction is worth stating
because collapsing the two is a mistake this build has already made once. `portfolio.py`
classifies a SKU by how it is *performing* -- star, conversion problem, quality emergency --
and runs the intervention ladder for that class. This module asks a different question, about
the shape of the catalogue rather than the health of a listing: what each product was created
*for*, how much of the revenue rests on how little of it, and whether the CA$5,000 target
survives losing the best thing in it.

Both are needed and neither substitutes for the other. A catalogue of twelve stars with the
same role is a portfolio one trend away from zero, and every one of those SKUs classifies
healthy.

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


# Revenue keys that are not a measured season or a measured channel. An order whose source is
# "unknown" says nothing about which channel to lose, and "evergreen" is not an event.
_NOT_A_SEASON = ("", "none", "evergreen", None)
_NOT_A_CHANNEL = ("", "unknown", None)


def _loss_scenario(name: str, what: str, revenue_by: dict | None, excluded: tuple,
                   total: float) -> dict:
    """Lose the largest measured key of one revenue breakdown, or say it is unmeasured."""
    measured = {k: float(v) for k, v in (revenue_by or {}).items()
                if k not in excluded and float(v or 0) > 0}
    if not measured:
        return {"scenario": name, "testable": False, "reading": "UNMEASURED",
                "why": (f"no revenue is attributed to a {what}, so losing the top one "
                        f"cannot be modelled. Refused rather than estimated")}
    top = max(measured, key=measured.get)
    return {"scenario": name, "testable": True, "removed": top,
            "remaining_cad": round(total - measured[top], 2),
            "share_lost": round(measured[top] / total, 3) if total else None}


def stress_test(positions: list[Position], *, target_cad: float = 5000.0,
                revenue_by_season: dict | None = None,
                revenue_by_channel: dict | None = None) -> dict:
    """Remove the best thing and see whether the target survives (#270).

    Five plausible single failures, because they are the ones that actually happen: the top
    product gets copied or delisted, the top family goes out of fashion, the top three go
    together, the seasonal event that carries the year does not repeat, and the traffic
    channel that brings most buyers changes its rules. The last two are modelled only from
    attributed revenue; with none they are reported UNMEASURED and refused, never estimated.
    """
    earning = [p for p in positions if p.revenue_cad > 0]
    total = sum(p.revenue_cad for p in earning)
    if total <= 0:
        return {"testable": False,
                "reason": ("nothing has earned anything, so there is no revenue to stress. "
                           "The target does not survive any scenario, including the one where "
                           "nothing goes wrong"),
                "scenarios": [],
                "refused": [
                    _loss_scenario("top seasonal event lost", "seasonal event",
                                   revenue_by_season, _NOT_A_SEASON, 0.0),
                    _loss_scenario("top traffic channel lost", "traffic channel",
                                   revenue_by_channel, _NOT_A_CHANNEL, 0.0)]}

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
    refused = []
    for extra in (_loss_scenario("top seasonal event lost", "seasonal event",
                                 revenue_by_season, _NOT_A_SEASON, total),
                  _loss_scenario("top traffic channel lost", "traffic channel",
                                 revenue_by_channel, _NOT_A_CHANNEL, total)):
        if extra["testable"]:
            extra.pop("testable")
            scenarios.append(extra)
        else:
            refused.append(extra)
    for s in scenarios:
        s["survives_target"] = s["remaining_cad"] >= target_cad
        s["shortfall_cad"] = round(max(0.0, target_cad - s["remaining_cad"]), 2)

    fragile = [s for s in scenarios if not s["survives_target"]]
    return {
        "testable": True,
        "current_cad": round(total, 2),
        "target_cad": target_cad,
        "scenarios": scenarios,
        "refused": refused,
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


def diversification_plan(shape_report: dict, concentration_report: dict,
                         stress: dict) -> dict:
    """What to build or grow next so no single loss ends the target (#270).

    Every action is tied to the reading it answers. Actions that depend on revenue are not
    invented while revenue is unmeasured; the catalogue-shape actions still are, because the
    shape is measured from the catalogue itself.
    """
    actions: list[dict] = []
    for role in shape_report.get("roles_absent", []):
        actions.append({"action": f"create a {role} product",
                        "because": f"the catalogue has no {role} product at all",
                        "reading": "measured"})
    for gap in shape_report.get("gaps", []):
        if "want_at_least" in gap and not gap.get("missing_entirely"):
            actions.append({"action": f"add {gap['role']} products",
                            "because": (f"{gap['role']} is {gap['share']:.0%} of the "
                                        f"catalogue against at least "
                                        f"{gap['want_at_least']:.0%}"),
                            "reading": "measured"})
    if concentration_report.get("measurable") and concentration_report.get("alarm"):
        actions.append({"action": (f"build products in other families than "
                                   f"{concentration_report['top_sku']}'s"),
                        "because": concentration_report["note"], "reading": "measured"})
    remedies = {
        "top SKU lost": "grow a second earner in the same role before scaling the first",
        "top family lost": "launch a family unrelated to the top one",
        "top three lost": "widen the earning base beyond three products",
        "top seasonal event lost": "add evergreen CORE products and a second season",
        "top traffic channel lost": ("develop a second acquisition channel (owned surfaces "
                                     "are owner-gated)"),
    }
    for scenario in stress.get("scenarios", []):
        if not scenario.get("survives_target", True):
            actions.append({"action": remedies.get(scenario["scenario"], "diversify"),
                            "because": (f"{scenario['scenario']}: CA$"
                                        f"{scenario['shortfall_cad']:.2f} short of target"),
                            "reading": "measured"})
    unmeasured = [r["scenario"] for r in stress.get("refused", [])]
    if not stress.get("testable"):
        unmeasured = ["revenue concentration"] + unmeasured
    return {"actions": actions, "unmeasured": unmeasured,
            "note": ("Revenue-dependent actions wait for revenue; shape actions do not "
                     "(#270).")}


def revenue_breakdowns(db) -> dict:
    """Attributed revenue by seasonal event and by acquisition channel, from real orders.

    Refunded orders do not count. The season is the product's seasonal event as the pool
    declares it, so an order for an evergreen product carries no season.
    """
    from sqlalchemy import select

    from ..core.models import Order

    try:
        from ..radar.opportunity import POOL

        season_of = {m.slug: (m.season or "") for m in POOL}
    except Exception:  # noqa: BLE001 # pragma: no cover
        season_of = {}
    by_season: dict[str, float] = {}
    by_channel: dict[str, float] = {}
    with db.session() as s:
        for order in s.scalars(select(Order).where(Order.refunded.is_(False))):
            amount = float(order.revenue_cad or 0.0)
            season = season_of.get(order.product_slug, "")
            by_season[season] = by_season.get(season, 0.0) + amount
            by_channel[order.acquisition_source or "unknown"] = (
                by_channel.get(order.acquisition_source or "unknown", 0.0) + amount)
    return {"by_season": by_season, "by_channel": by_channel}


def report(db, *, target_cad: float = 5000.0) -> dict:
    positions = positions_from_db(db)
    breakdowns = revenue_breakdowns(db)
    shaped = shape(positions)
    conc = concentration(positions)
    stress = stress_test(positions, target_cad=target_cad,
                         revenue_by_season=breakdowns["by_season"],
                         revenue_by_channel=breakdowns["by_channel"])
    return {
        "shape": shaped,
        "concentration": conc,
        "stress_test": stress,
        "diversification_plan": diversification_plan(shaped, conc, stress),
    }
