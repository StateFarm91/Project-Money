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


# ---------------------------------------------------------------------------
# #237: search-term-to-P&L attribution from an owner-supplied Etsy Stats CSV.
#
# Etsy Stats shows search terms and traffic sources in the seller dashboard and lets the owner
# download them; no API surface this company holds returns them. So the intake is a CSV the
# owner exports and hands over, and this half of the module reads it strictly: a row it
# cannot read is refused with its line number, never coerced, because a search term credited
# with visits it did not have is a keyword strategy built on a typo.

import csv
import io

# The columns a Stats export has to carry, and the headings they are accepted under. Etsy
# renames these between dashboard versions; the aliases are the spellings seen, lower-cased,
# and an export whose heading matches none of them is refused by name rather than guessed.
STATS_COLUMNS: dict[str, tuple[str, ...]] = {
    "term": ("search term", "search_term", "term", "keyword", "query", "traffic source",
             "source"),
    "impressions": ("impressions", "views", "shown"),
    "visits": ("visits", "clicks", "listing visits"),
    "orders": ("orders", "purchases", "sales"),
    "revenue_cad": ("revenue", "revenue (cad)", "revenue_cad", "sales value"),
}
REQUIRED_STATS_COLUMNS: tuple[str, ...] = ("term", "impressions", "visits")


class StatsRefused(ValueError):
    """A Stats export whose shape or rows cannot be read."""


def _header_map(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise StatsRefused("the CSV has no header row")
    lowered = {f.strip().lower(): f for f in fieldnames if f}
    found: dict[str, str] = {}
    for key, aliases in STATS_COLUMNS.items():
        for alias in aliases:
            if alias in lowered:
                found[key] = lowered[alias]
                break
    missing = [k for k in REQUIRED_STATS_COLUMNS if k not in found]
    if missing:
        raise StatsRefused(
            f"the export has no column for {missing}; headings seen: {fieldnames}. Accepted "
            f"headings: { {k: list(v) for k, v in STATS_COLUMNS.items() if k in missing} }")
    return found


def _count(raw: str | None, *, line: int, what: str) -> int:
    text = (raw or "").strip().replace(",", "")
    if text == "":
        raise StatsRefused(f"line {line}: {what} is blank; blank is not zero in a Stats export")
    try:
        value = int(text)
    except ValueError as exc:
        raise StatsRefused(f"line {line}: {what} {raw!r} is not a whole number") from exc
    if value < 0:
        raise StatsRefused(f"line {line}: {what} {value} is negative")
    return value


def _money(raw: str | None, *, line: int) -> float | None:
    text = (raw or "").strip().replace(",", "").replace("CA$", "").replace("$", "")
    if text == "":
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise StatsRefused(f"line {line}: revenue {raw!r} is not a number") from exc
    if value < 0:
        raise StatsRefused(f"line {line}: revenue {value} is negative")
    return value


def parse_stats_csv(text: str) -> list[dict]:
    """Read an owner-exported Etsy Stats CSV into rows, refusing anything malformed (#237).

    Every count is a whole non-negative number, visits never exceed impressions, orders
    never exceed visits, and a term appears once. A row that fails any of these is refused
    with its line number; the rest of the file is not read around it, because a partial read
    of an export is an export somebody will believe is complete.
    """
    reader = csv.DictReader(io.StringIO(text))
    cols = _header_map(reader.fieldnames)
    rows: list[dict] = []
    seen: dict[str, int] = {}
    for n, raw in enumerate(reader, start=2):
        term = (raw.get(cols["term"]) or "").strip()
        if not term:
            raise StatsRefused(f"line {n}: the search term is blank")
        key = term.lower()
        if key in seen:
            raise StatsRefused(f"line {n}: {term!r} already appeared on line {seen[key]}; "
                               f"a term listed twice would be counted twice")
        seen[key] = n
        impressions = _count(raw.get(cols["impressions"]), line=n, what="impressions")
        visits = _count(raw.get(cols["visits"]), line=n, what="visits")
        orders = (_count(raw.get(cols["orders"]), line=n, what="orders")
                  if "orders" in cols else None)
        revenue = _money(raw.get(cols["revenue_cad"]), line=n) if "revenue_cad" in cols else None
        if visits > impressions:
            raise StatsRefused(f"line {n}: {visits} visits from {impressions} impressions; a "
                               f"listing cannot be visited more often than it was shown")
        if orders is not None and orders > visits:
            raise StatsRefused(f"line {n}: {orders} orders from {visits} visits")
        if revenue is not None and orders == 0 and revenue > 0:
            raise StatsRefused(f"line {n}: CA${revenue:.2f} revenue on zero orders")
        rows.append({"term": term, "impressions": impressions, "visits": visits,
                     "orders": orders, "revenue_cad": revenue, "line": n})
    if not rows:
        raise StatsRefused("the export has a header and no rows")
    return rows


def _rate(n, d):
    return round(n / d, 5) if (n is not None and d) else None


def join_stats(rows: list[dict], *, contribution_rate: float | None = None,
               support_by_term: dict[str, int] | None = None,
               repeat_by_term: dict[str, int] | None = None) -> dict:
    """Search terms joined to what they earned, ranked on contribution per visit (#237).

    Keyword strategy optimises profitable customers, not impressions: the ranking here is on
    contribution per visit, and impressions appear only as the denominator of a click-through
    rate. `contribution_rate` is the share of revenue that is contribution for the listings
    these terms point at; with none supplied, contribution is UNMEASURED and the ranking
    falls back to revenue per visit and says so.
    """
    if contribution_rate is not None and not 0 < contribution_rate <= 1:
        raise StatsRefused("a contribution rate is a share between 0 and 1")
    support_by_term = {k.lower(): v for k, v in (support_by_term or {}).items()}
    repeat_by_term = {k.lower(): v for k, v in (repeat_by_term or {}).items()}

    out = []
    for r in rows:
        key = r["term"].lower()
        revenue = r["revenue_cad"]
        contribution = (None if (revenue is None or contribution_rate is None)
                        else round(revenue * contribution_rate, 2))
        out.append({
            "term": r["term"], "impressions": r["impressions"], "visits": r["visits"],
            "orders": r["orders"], "revenue_cad": revenue,
            "contribution_cad": contribution,
            "ctr": _rate(r["visits"], r["impressions"]),
            "conversion": _rate(r["orders"], r["visits"]),
            "revenue_per_visit_cad": _rate(revenue, r["visits"]),
            "contribution_per_visit_cad": _rate(contribution, r["visits"]),
            "support_cases": support_by_term.get(key),
            "repeat_orders": repeat_by_term.get(key),
            "vanity": bool(r["impressions"] and not r["orders"]),
        })

    if contribution_rate is not None and any(x["contribution_per_visit_cad"] is not None for x in out):
        basis, sort_key = "contribution_per_visit_cad", "contribution_per_visit_cad"
    elif any(x["revenue_per_visit_cad"] is not None for x in out):
        basis, sort_key = "revenue_per_visit_cad (contribution UNMEASURED: no rate supplied)", "revenue_per_visit_cad"
    else:
        basis, sort_key = "UNMEASURED: the export carries no revenue, so terms cannot be ranked on what they earned", None

    if sort_key:
        out.sort(key=lambda x: -(x[sort_key] or 0.0))
    return {
        "terms": out, "ranked_on": basis,
        "vanity_terms": [x["term"] for x in out if x["vanity"]],
        "totals": {"impressions": sum(x["impressions"] for x in out),
                   "visits": sum(x["visits"] for x in out),
                   "orders": (sum(x["orders"] or 0 for x in out)
                              if any(x["orders"] is not None for x in out) else None)},
        "note": ("ranked on contribution per visit, never on impressions: a term that is shown "
                 "ten thousand times and sells nothing is listed under vanity_terms, which is "
                 "the list a keyword strategy should be removing from (#237)"),
    }
