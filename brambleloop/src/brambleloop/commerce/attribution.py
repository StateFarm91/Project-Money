"""Did the bundle add revenue, or move it? (#45)

Winner Amplification says: find what sells and build more of it. The failure mode is not that
the adjacent product fails — it is that it succeeds, and the revenue it earns came from the
higher-contribution SKU next to it. Every dashboard improves. Units rise, the new product
looks like a hit, the catalogue looks broader, and contribution is flat or down.

This is hard to see because both halves are true at once. The bundle *did* sell. The buyer
*did* choose it. Nothing failed. The only way to notice is to ask what the displaced product
was earning before the bundle existed, and to insist that the comparison be made on
contribution rather than on revenue — a bundle that sells more at a worse margin is a busier
version of the same business, and busier is what every other metric rewards.

Three numbers, and the order matters. Attach rate says whether the bundle is being chosen.
Incrementality says whether that choice added a customer. Cannibalisation says what it cost
the SKU it sits beside. Declaring a winner on the first is how the third gets discovered a
quarter later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Below this many orders on either side, the comparison is anecdote arithmetic.
MIN_ORDERS = 15

# A bundle taking more than this share of its component's previous volume is displacing
# rather than adding, whatever the top line says.
DISPLACEMENT_ALARM = 0.30


class AttributionRefused(ValueError):
    """A winner declared before the question was askable."""


@dataclass
class Period:
    """One SKU over one window. `baseline` windows are before the bundle existed."""

    slug: str
    orders: int
    revenue_cad: float
    contribution_cad: float
    visits: int = 0

    @property
    def contribution_per_order(self) -> float:
        return self.contribution_cad / self.orders if self.orders else 0.0

    def to_dict(self) -> dict:
        return {"slug": self.slug, "orders": self.orders, "revenue_cad": self.revenue_cad,
                "contribution_cad": self.contribution_cad,
                "contribution_per_order": round(self.contribution_per_order, 2)}


@dataclass
class BundleResult:
    bundle: str
    components: list = field(default_factory=list)
    measurable: bool = False
    reason: str = ""
    attach_rate: float | None = None
    incremental_orders: int | None = None
    cannibalised_orders: int | None = None
    contribution_delta_cad: float | None = None

    def to_dict(self) -> dict:
        return {
            "bundle": self.bundle, "measurable": self.measurable, "reason": self.reason,
            "attach_rate": self.attach_rate,
            "incremental_orders": self.incremental_orders,
            "cannibalised_orders": self.cannibalised_orders,
            "contribution_delta_cad": self.contribution_delta_cad,
            "components": list(self.components),
            "verdict": self._verdict(),
        }

    def _verdict(self) -> str:
        if not self.measurable:
            return "unmeasured"
        if self.contribution_delta_cad is None:
            return "unmeasured"
        if self.contribution_delta_cad <= 0:
            return "displacing"
        if (self.cannibalised_orders or 0) > 0:
            return "incremental_with_displacement"
        return "incremental"


def bundle_effect(bundle_slug: str, *, bundle: Period,
                  components_before: list[Period],
                  components_after: list[Period]) -> BundleResult:
    """What the bundle added, and what it took, measured on contribution.

    `before` is the same SKUs over an equivalent window before the bundle existed. Without it
    the question cannot be asked at all: the after-window on its own shows a bundle selling
    and says nothing about where the buyers came from.
    """
    result = BundleResult(bundle=bundle_slug)
    before = {p.slug: p for p in components_before}
    after = {p.slug: p for p in components_after}

    missing_baseline = [s for s in after if s not in before]
    if not components_before or missing_baseline:
        result.reason = (
            f"no baseline for {missing_baseline or 'the components'}. The after-window alone "
            f"shows a bundle selling and says nothing about where its buyers came from, which "
            f"is the entire question (#45)")
        return result

    total_after_orders = bundle.orders + sum(p.orders for p in after.values())
    if bundle.orders < MIN_ORDERS or total_after_orders < MIN_ORDERS:
        result.reason = (
            f"{bundle.orders} bundle orders against a {MIN_ORDERS} minimum: declaring a "
            f"winner here is anecdote arithmetic, and the displacement it would hide takes a "
            f"quarter to surface")
        return result

    result.measurable = True
    result.attach_rate = round(bundle.orders / total_after_orders, 4)

    lost = 0
    component_rows = []
    for slug, base in sorted(before.items()):
        now = after.get(slug, Period(slug, 0, 0.0, 0.0))
        delta = now.orders - base.orders
        displaced = max(0, -delta)
        lost += displaced
        component_rows.append({
            "slug": slug, "orders_before": base.orders, "orders_after": now.orders,
            "orders_delta": delta,
            "displaced": displaced,
            "share_displaced": (round(displaced / base.orders, 3) if base.orders else None),
            "alarm": bool(base.orders and displaced / base.orders >= DISPLACEMENT_ALARM),
            "contribution_per_order_before": round(base.contribution_per_order, 2),
        })
    result.components = component_rows
    result.cannibalised_orders = lost
    result.incremental_orders = bundle.orders - lost

    contribution_before = sum(p.contribution_cad for p in before.values())
    contribution_after = (bundle.contribution_cad
                          + sum(p.contribution_cad for p in after.values()))
    result.contribution_delta_cad = round(contribution_after - contribution_before, 2)
    return result


def amplification_check(result: BundleResult) -> dict:
    """May Winner Amplification call this a win? (#45)

    Contribution decides. A bundle that raised revenue and lowered contribution has made the
    company busier at the same profit, and busier is what every other metric rewards — which
    is why this has to be a separate, explicit check rather than a number on a dashboard
    beside nine that all went up.
    """
    if not result.measurable:
        return {"may_declare_winner": False, "why": result.reason or "not measurable yet",
                "verdict": "unmeasured"}
    verdict = result.to_dict()["verdict"]
    if result.contribution_delta_cad is not None and result.contribution_delta_cad <= 0:
        return {
            "may_declare_winner": False,
            "verdict": verdict,
            "why": (f"contribution moved {result.contribution_delta_cad:+.2f} CAD while "
                    f"{result.cannibalised_orders} orders moved off the component SKUs. The "
                    f"bundle sold; the buyers were already ours"),
            "contribution_delta_cad": result.contribution_delta_cad,
        }
    alarms = [c["slug"] for c in result.components if c["alarm"]]
    return {
        "may_declare_winner": True,
        "verdict": verdict,
        "why": (f"contribution up {result.contribution_delta_cad:+.2f} CAD with "
                f"{result.incremental_orders} incremental orders"),
        "contribution_delta_cad": result.contribution_delta_cad,
        "displacement_alarms": alarms,
        "note": (f"{alarms} lost at least {DISPLACEMENT_ALARM:.0%} of their volume; the "
                 f"bundle is incremental overall and is still displacing them"
                 if alarms else "no component lost a material share of its volume"),
    }
