"""Storefront navigation: only categories with at least one legitimate product are public.

Owner decision D-FB-18 item 3: never advertise empty categories publicly. Wearables, Gifts and
Seasonal stay in the long-term category architecture (`ARCHITECTURE`, lane C's
`copy_v2.SECTIONS`, the data model) but are hidden from every generated navigation surface
until each holds at least one product. The canonical logo and banner are never edited because
their artwork shows a category line; that baked-in text is a reported truth finding
(`owner_banner`, gate `nav_categories_truth`), not something a generated surface repeats.

"Legitimate product" = a listing the store's own surface builder counts in that section
(`content.build(db)["sections"]`), i.e. a Launch-0 pattern or a drafted listing for one.
"""
from __future__ import annotations

import re


def architecture() -> list[dict]:
    """Every category the brand plans, populated or not (the long-term data model)."""
    from . import copy_v2

    return [s.to_dict() for s in sorted(copy_v2.SECTIONS, key=lambda s: s.order)]


def _counts(db=None) -> dict[str, int]:
    from . import content

    return {x["slug"]: int(x["listings"] or 0) for x in content.build(db)["sections"].value}


def public_nav(db=None) -> list[dict]:
    """Categories a generated surface may show: architecture order, >= 1 product each."""
    counts = _counts(db)
    return [{**s, "listings": counts.get(s["slug"], 0)} for s in architecture()
            if counts.get(s["slug"], 0) >= 1]


def hidden(db=None) -> list[dict]:
    """Planned categories hidden until populated, with why."""
    counts = _counts(db)
    return [{**s, "listings": counts.get(s["slug"], 0),
             "hidden_because": "no legitimate product yet (D-FB-18 item 3)"}
            for s in architecture() if counts.get(s["slug"], 0) < 1]


def empty_categories_named(text: str, db=None) -> list[str]:
    """Hidden category names that appear in `text` as whole words (for surface checks)."""
    out = []
    for s in hidden(db):
        if re.search(rf"(?<![A-Za-z]){re.escape(s['name'])}(?![A-Za-z])", text, re.I):
            out.append(s["name"])
    return out


def summary(db=None) -> dict:
    return {"public": [s["name"] for s in public_nav(db)],
            "hidden": [s["name"] for s in hidden(db)],
            "architecture": [s["name"] for s in architecture()],
            "rule": "D-FB-18 item 3: public navigation shows only populated categories"}
