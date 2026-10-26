"""Market Intelligence: `radar.competitor_snapshot` (market_radar) -- W4-AGENTS batch 4.

A dated, read-only snapshot of the competitor listings this company has ALREADY observed
through its sanctioned sources (`benchmark_listings`, the living market map, #303). It is
demand and merchandising intelligence only:

* aggregates per benchmark and pod -- listing count, newly seen listings, price band
  (min / median / max CA$), share on sale, median gallery size, seasonal mix and product
  types -- and the change since the previous snapshot;
* it stores NO competitor title, description, URL, image, chart or instruction (CLAUDE.md:
  "Competitor research is for demand and merchandising intelligence only"); the payload is
  numbers and the company's own category labels;
* no network call, no model, CA$0; one `operating_readings` row per UTC day.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone

from .worker import JobContext, handlers

READING = "radar.competitor_snapshot"
NEW_WINDOW_DAYS = 7
# The only fields a snapshot may carry. Enforced by `_assert_no_content` and the test.
ALLOWED_KEYS = frozenset({"benchmark", "pod", "listings", "new_7d", "price_min_cad",
                          "price_median_cad", "price_max_cad", "on_sale_share",
                          "median_media", "seasonal", "product_types", "delta"})


def _aware(v):
    return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)


def snapshot(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=NEW_WINDOW_DAYS)
    groups: dict[tuple[str, str], list] = {}
    with db.session() as s:
        for r in s.execute(select(BenchmarkListing.benchmark_key, BenchmarkListing.pod,
                                  BenchmarkListing.price_cad, BenchmarkListing.on_sale,
                                  BenchmarkListing.media_count, BenchmarkListing.seasonal,
                                  BenchmarkListing.product_type,
                                  BenchmarkListing.first_seen)).all():
            groups.setdefault((r.benchmark_key, r.pod or "unclassified"), []).append(r)
    rows = []
    for (bk, pod), items in sorted(groups.items()):
        prices = [float(x.price_cad) for x in items if (x.price_cad or 0) > 0]
        media = [int(x.media_count or 0) for x in items]
        seasonal: dict[str, int] = {}
        types: dict[str, int] = {}
        for x in items:
            if x.seasonal:
                seasonal[x.seasonal] = seasonal.get(x.seasonal, 0) + 1
            if x.product_type:
                types[x.product_type] = types.get(x.product_type, 0) + 1
        rows.append({
            "benchmark": bk, "pod": pod, "listings": len(items),
            "new_7d": sum(1 for x in items if x.first_seen and _aware(x.first_seen) >= since),
            # UNKNOWN, never 0, when no price was observed
            "price_min_cad": round(min(prices), 2) if prices else "UNKNOWN",
            "price_median_cad": round(statistics.median(prices), 2) if prices else "UNKNOWN",
            "price_max_cad": round(max(prices), 2) if prices else "UNKNOWN",
            "on_sale_share": round(sum(1 for x in items if x.on_sale) / len(items), 3),
            "median_media": statistics.median(media) if media else "UNKNOWN",
            "seasonal": dict(sorted(seasonal.items())),
            "product_types": dict(sorted(types.items())),
        })
    return {"at": now.isoformat(), "groups": rows, "listings": sum(r["listings"] for r in rows),
            "copies_competitor_content": False}


def _assert_no_content(snap: dict) -> None:
    for r in snap["groups"]:
        extra = set(r) - ALLOWED_KEYS
        if extra:
            raise ValueError(f"snapshot carries non-aggregate fields {sorted(extra)}")


def _with_delta(snap: dict, prev: dict | None) -> dict:
    before = {(g["benchmark"], g["pod"]): g for g in (prev or {}).get("groups") or []}
    for g in snap["groups"]:
        p = before.get((g["benchmark"], g["pod"]))
        g["delta"] = None if p is None else {
            "listings": g["listings"] - p["listings"],
            "price_median_cad": (round(g["price_median_cad"] - p["price_median_cad"], 2)
                                 if isinstance(g["price_median_cad"], float)
                                 and isinstance(p.get("price_median_cad"), float)
                                 else "UNKNOWN")}
    return snap


@handlers.register("radar.competitor_snapshot")
def handle_competitor_snapshot(ctx: JobContext) -> dict:
    from .etsy_ops import latest_reading, store_reading

    prev = latest_reading(ctx.db, READING)
    snap = _with_delta(snapshot(ctx.db), prev)
    _assert_no_content(snap)
    if not snap["groups"]:
        return {"ran": False, "why": "no competitor listing has been observed yet",
                "network_calls": 0}
    store_reading(ctx.db, READING, snap)
    ctx.audit(READING, detail={"groups": len(snap["groups"]), "listings": snap["listings"]})
    return {"groups": len(snap["groups"]), "listings": snap["listings"],
            "new_7d": sum(g["new_7d"] for g in snap["groups"]), "network_calls": 0,
            "copies_competitor_content": False, "work_done": len(snap["groups"])}
