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


OTHER = "other"


def benchmark_alias(key: str) -> str:
    """L-3 (review of a14c9ef): a benchmark key embeds a competitor shop's name, so the
    snapshot carries a stable alias (the same key always gives the same alias, so deltas still
    line up) and never the key itself."""
    import hashlib

    return "bm-" + hashlib.sha256(str(key or "").encode()).hexdigest()[:10]


def _own_labels() -> tuple[frozenset, frozenset]:
    """The only values the inner `seasonal` / `product_types` maps may carry: our own seasonal
    event names, and Etsy taxonomy ids (digits) or our own category and pod labels."""
    from ..brand.storefront import SECTIONS
    from ..intel.pods import POD_KEYS
    from ..radar.market import SEASONAL_EVENTS

    seasons = frozenset(e.name for e in SEASONAL_EVENTS)
    types = frozenset(c for sec in SECTIONS for c in sec.categories) | frozenset(POD_KEYS)
    return seasons, types


def _label(value: str, allowed: frozenset, *, digits: bool = False) -> str:
    v = str(value or "")
    if v in allowed or (digits and v.isdigit() and len(v) <= 12):
        return v
    return OTHER


def _aware(v):
    return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)


def snapshot(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel.pods import POD_KEYS

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
    seasons, own_types = _own_labels()
    for (bk, pod), items in sorted(groups.items()):
        prices = [float(x.price_cad) for x in items if (x.price_cad or 0) > 0]
        media = [int(x.media_count or 0) for x in items]
        seasonal: dict[str, int] = {}
        types: dict[str, int] = {}
        for x in items:
            if x.seasonal:
                k = _label(x.seasonal, seasons)
                seasonal[k] = seasonal.get(k, 0) + 1
            if x.product_type:
                k = _label(x.product_type, own_types, digits=True)
                types[k] = types.get(k, 0) + 1
        rows.append({
            "benchmark": benchmark_alias(bk), "pod": _label(pod, frozenset(POD_KEYS)), "listings": len(items),
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
    # L-3: the inner values too -- an alias, our own labels, digits or counts, nothing else.
    seasons, own_types = _own_labels()
    from ..intel.pods import POD_KEYS

    for r in snap["groups"]:
        if not str(r["benchmark"]).startswith("bm-"):
            raise ValueError("snapshot carries a raw benchmark key")
        if r["pod"] not in POD_KEYS and r["pod"] != OTHER:
            raise ValueError("snapshot carries a pod that is not ours")
        bad = [k for k in r["seasonal"] if k not in seasons and k != OTHER] + [
            k for k in r["product_types"]
            if k not in own_types and k != OTHER and not (k.isdigit() and len(k) <= 12)]
        bad += [v for v in list(r["seasonal"].values()) + list(r["product_types"].values())
                if not isinstance(v, int)]
        if bad:
            raise ValueError(f"snapshot carries values outside our own labels: {bad[:5]}")


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


@handlers.register("intel.children_portfolio")
def handle_children_portfolio(ctx: JobContext) -> dict:
    """F-351/F-353/F-358/F-365/F-366: the priority baby & children's family, read daily from
    our own rows and the observed listings (counts only). Writes one reading; CA$0."""
    from ..creative import children
    from .etsy_ops import store_reading

    rep = children.portfolio(ctx.db)
    store_reading(ctx.db, "intel.children_portfolio", rep)
    ctx.audit("intel.children_portfolio", detail={
        "research_gaps": [g["category"] for g in rep["coverage"]["gaps"]],
        "children_in_launch": rep["launch_mix"]["children_in_launch"],
        "propose_collection": rep["architecture"]["propose_collection"]})
    return {"research_gaps": len(rep["coverage"]["gaps"]),
            "researched": rep["coverage"]["researched"],
            "children_in_launch": rep["launch_mix"]["children_in_launch"],
            "propose_collection": rep["architecture"]["propose_collection"],
            "network_calls": 0, "work_done": 1}


# ---- the Research Agent (F-401 / F-429 / F-436; W4-AGENTS W3) -----------------------------

@handlers.register("research.investigate")
def handle_research_investigate(ctx: JobContext) -> dict:
    """Investigate one research task (by id, or open it from the request). CA$0, no network."""
    from ..intel import research, research_agent

    i = dict(ctx.job.inputs or {})
    tid = i.get("task_id")
    if tid is None:
        if not i.get("question"):
            return {"ran": False, "why": "research.investigate needs task_id or a question"}
        try:
            opened = research.open_question(
                ctx.db, question=str(i["question"]), trigger=str(i.get("trigger") or ""),
                decision_ref=str(i.get("decision_ref") or ""), domain=str(i.get("domain") or ""),
                query_terms=i.get("query_terms") or ())
        except research.ResearchRefused as exc:
            return {"ran": False, "why": f"refused: {exc}"}
        tid = opened["task"]
    out = research_agent.investigate(ctx.db, int(tid))
    if out["status"] == research_agent.NOT_OPEN:
        return {"ran": False, "task": tid, "why": "the task is not open", "work_done": 0}
    ctx.audit(research_agent.INVESTIGATED, artifact=f"research_task:{tid}",
              detail={**{k: out[k] for k in ("status", "confidence", "evidence",
                                             "new_internal", "new_sources", "next_test",
                                             "applicability")},
                      "method": out["method"]["chosen"],
                      "blocked_on": out["method"]["blocked_on"]})
    return out


@handlers.register("research.sweep")
def handle_research_sweep(ctx: JobContext) -> dict:
    """F-401 self-trigger: unknowns become tasks, due tasks become investigations."""
    from ..intel import research, research_agent

    found = research.detect_unknowns(ctx.db)
    stale = research_agent.stale_domains_to_research(ctx.db)          # F-404
    found = {**found, "opened": list(found["opened"]) + list(stale["opened"])}
    reopened = research.expire_due(ctx.db)
    due = research_agent.due_for_investigation(ctx.db)
    day = datetime.now(timezone.utc).date().isoformat()
    queued = 0
    for tid in due[:25]:
        job = ctx.enqueue("research_agent", "research.investigate", {"task_id": tid},
                          idempotency_key=f"research.investigate:{tid}:{day}")
        queued += job is not None
    ctx.audit("research.swept", detail={"opened": len(found["opened"]),
                                        "reopened": len(reopened), "due": len(due),
                                        "queued": queued})
    return {"opened": len(found["opened"]), "reopened": len(reopened), "due": len(due),
            "queued": queued, "work_done": len(found["opened"]) + queued}


@handlers.register("research.flag_architecture")
def handle_research_flag(ctx: JobContext) -> dict:
    """F-429: evidence contradicting an assumption is flagged for the weekly review."""
    from ..intel import research, research_agent

    i = dict(ctx.job.inputs or {})
    try:
        out = research_agent.flag_architecture(
            ctx.db, int(i.get("task_id") or 0), assumption=str(i.get("assumption") or ""),
            evidence_refs=i.get("evidence_refs") or (), why=str(i.get("why") or ""))
    except (research.ResearchRefused, ValueError) as exc:
        return {"ran": False, "why": f"refused: {exc}", "work_done": 0}
    return {**out, "changes_nothing": True, "work_done": 1}
