"""Content economics (F-825) -- W4-C14.

"Track creation cost, maintenance cost, search traffic, email acquisition, assisted
conversions, support deflection and attributable sales. High-cost/low-value formats are
redesigned or retired."

Per content item (`{slug, format, months_live, creation_cost_cad, maintenance_cad_per_month,
search_visits, email_signups, assisted_conversions, support_deflections,
attributable_sales_cad}`):

* cost = creation + maintenance x months live;
* value = attributable sales, plus each proxy at its *stated* unit value -- email signups,
  assisted conversions and support deflections are worth only what `Assumptions` says, with
  its basis. A proxy whose unit value is not stated contributes UNKNOWN, never 0, and so does
  a missing measurement. Search visits are reported, not valued: traffic is a means, and
  valuing it as well as the sales it produced would count the same buyer twice.

A verdict needs `MIN_MONTHS` live. Then:

* KEEP when the measured value alone already covers the cost (unknown parts can only add);
* REDESIGN when the whole value -- every part known -- is below the cost;
* RETIRE when it is below `RETIRE_RATIO` of the cost, or a redesigned item is still below cost;
* UNKNOWN otherwise: below cost on what is measured, with parts that could close the gap.

Formats are judged the same way over their items' totals, so "high-cost/low-value formats"
is a reading of the books, not a taste. Recommendations only: nothing here unpublishes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

UNKNOWN = "UNKNOWN"
MIN_MONTHS = 3
RETIRE_RATIO = 0.25
PROXIES = ("email_signups", "assisted_conversions", "support_deflections")


@dataclass(frozen=True)
class Assumptions:
    """Unit values for the proxies, each with where it came from. Absent = UNKNOWN."""

    unit_cad: dict = field(default_factory=dict)      # proxy -> CA$ per unit
    basis: dict = field(default_factory=dict)         # proxy -> source of that figure


def _num(v):
    return None if v is None else float(v)


def economics(item: dict, assumptions: Assumptions | None = None) -> dict:
    a = assumptions or Assumptions()
    months = _num(item.get("months_live"))
    create, maint = _num(item.get("creation_cost_cad")), _num(item.get("maintenance_cad_per_month"))
    cost = (None if create is None or maint is None or months is None
            else round(create + maint * months, 2))
    parts, unknown = {}, []
    sales = _num(item.get("attributable_sales_cad"))
    parts["attributable_sales"] = sales
    if sales is None:
        unknown.append("attributable_sales: not measured")
    for p in PROXIES:
        n = _num(item.get(p))
        unit = a.unit_cad.get(p)
        if n is None:
            parts[p] = None
            unknown.append(f"{p}: not measured")
        elif unit is None or not a.basis.get(p):
            parts[p] = None
            unknown.append(f"{p}: {int(n)} measured, unit value not stated with a basis")
        else:
            parts[p] = round(n * float(unit), 2)
    known = round(sum(v for v in parts.values() if v is not None), 2)
    complete = not unknown
    verdict, why = _verdict(cost=cost, known=known, complete=complete, months=months,
                            redesigned=bool(item.get("redesigned")))
    return {"slug": item.get("slug"), "format": item.get("format"), "months_live": months,
            "cost_cad": cost, "value_known_cad": known,
            "value_cad": known if complete else UNKNOWN, "parts": parts,
            "unknown_parts": unknown, "search_visits": item.get("search_visits"),
            "verdict": verdict, "why": why}


def _verdict(*, cost, known, complete, months, redesigned):
    if cost is None or months is None:
        return UNKNOWN, "cost or months live not recorded"
    if months < MIN_MONTHS:
        return UNKNOWN, f"{months:g} of {MIN_MONTHS} months live; too early to judge"
    if known >= cost:
        return "KEEP", f"measured value CA${known} covers cost CA${cost}"
    if not complete:
        return UNKNOWN, (f"measured value CA${known} is below cost CA${cost}, but unmeasured "
                         f"parts could close the gap")
    if known < RETIRE_RATIO * cost or redesigned:
        return "RETIRE", (f"value CA${known} is {known / cost:.0%} of cost CA${cost}"
                          + ("; already redesigned once" if redesigned else ""))
    return "REDESIGN", f"value CA${known} is below cost CA${cost}"


def by_format(items, assumptions: Assumptions | None = None) -> dict:
    rows = [economics(i, assumptions) for i in items or ()]
    formats: dict[str, dict] = {}
    for r in rows:
        f = formats.setdefault(r["format"] or "?", {"items": [], "cost": 0.0, "known": 0.0,
                                                    "complete": True, "months": None})
        f["items"].append(r["slug"])
        if r["cost_cad"] is None or r["months_live"] is None:
            f["cost"] = None
        elif f["cost"] is not None:
            f["cost"] += r["cost_cad"]
        f["known"] += r["value_known_cad"]
        f["complete"] = f["complete"] and not r["unknown_parts"]
        m = r["months_live"]
        f["months"] = m if f["months"] is None or (m is not None and m < f["months"]) else f["months"]
    out = {}
    for name, f in sorted(formats.items()):
        cost = round(f["cost"], 2) if f["cost"] is not None else None
        verdict, why = _verdict(cost=cost, known=round(f["known"], 2), complete=f["complete"],
                                months=f["months"], redesigned=False)
        out[name] = {"items": f["items"], "cost_cad": cost,
                     "value_known_cad": round(f["known"], 2), "verdict": verdict, "why": why}
    return {"items": rows, "formats": out,
            "rule": "UNKNOWN is never 0: an unmeasured or unvalued part keeps a verdict open",
            "note": "recommendations only; nothing here unpublishes or edits content"}
