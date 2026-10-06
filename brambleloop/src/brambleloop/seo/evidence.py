"""The keyword evidence store: what is known about each search phrase, and how it is known.

Sources read (all existing tables; nothing here makes a network call):

| source                      | table / reader                         | basis      | use                    |
|-----------------------------|----------------------------------------|------------|------------------------|
| Etsy Stats export (owner)   | operating_readings kind attribution.stats | measured | shop-level term outcome |
| Marketplace Insights (owner)| insights_snapshots                     | measured   | demand (owner-read)    |
| API marketplace search      | serp_snapshots.total_count             | measured   | proxy:competition      |
| Benchmark listing titles    | benchmark_listings.title               | observed   | buyer language present |
| keywords table              | keywords (est_demand/est_competition)  | modelled   | planning estimate      |
| query templates             | commerce.search.build_query_set        | modelled   | planning estimate      |

`measured` means Etsy produced the number (read by the owner or by the API). Even then it is
labelled with its `use`: a result count measures supply in the API index; reading it as
"competition" is a proxy and is stored as `proxy:competition`, never as a measurement of rank.
A template phrase's demand/competition are hand-set constants and are `modelled` -- nothing that
reads this store may present them as evidence of demand (F-020).

Every row has a content fingerprint, so `ingest` is idempotent: re-reading unchanged sources
adds nothing.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .models import MEASURED, MODELLED, OBSERVED, UNKNOWN, SeoKeywordEvidence, ensure_tables
from ._db import session

STATS_KIND = "attribution.stats"   # runtime.release.ATTRIBUTION_KIND (not imported: heavy)


def _fp(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _aware(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _row(phrase, metric, value, basis, use, source, ref, observed_at, detail=None) -> dict:
    phrase = " ".join((phrase or "").lower().split())
    return {"phrase": phrase, "metric": metric,
            "value": None if value is None else float(value), "basis": basis, "use": use,
            "source": source, "source_ref": str(ref), "observed_at": _aware(observed_at),
            "detail": detail or {},
            "fingerprint": _fp(phrase, metric, value, basis, source, str(ref))}


def _collect_stats(s) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    out = []
    for r in s.scalars(select(OperatingReading).where(OperatingReading.kind == STATS_KIND)):
        joined = (r.payload or {}).get("joined") or {}
        ref = f"operating_readings:{r.id}:{r.period_key}"
        for t in joined.get("terms") or []:
            term = t.get("term")
            if not term:
                continue
            for metric in ("impressions", "visits", "orders", "revenue_cad"):
                if t.get(metric) is None:
                    continue   # unmeasured stays absent, never zero
                out.append(_row(term, f"stats_{metric}", t[metric], MEASURED,
                                "shop_level_term_outcome", "etsy_stats_export", ref, r.at,
                                {"scope": "shop-level: the Stats export does not split a "
                                          "search term by listing"}))
    return out


def _collect_insights(s) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import InsightsSnapshot

    out = []
    for r in s.scalars(select(InsightsSnapshot)):
        ref = f"insights_snapshots:{r.id}"
        detail = {"recorded_by": r.recorded_by, "row_basis": r.basis,
                  "trend": r.trend_direction}
        if r.search_count is not None:
            out.append(_row(r.keyword, "insights_search_count", r.search_count, MEASURED,
                            "demand", "marketplace_insights_owner_recorded", ref,
                            r.observed_on, detail))
        if r.listing_count is not None:
            out.append(_row(r.keyword, "insights_listing_count", r.listing_count, MEASURED,
                            "proxy:competition", "marketplace_insights_owner_recorded", ref,
                            r.observed_on, detail))
    return out


def _collect_serp(s) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import SerpSnapshot

    out = []
    for r in s.scalars(select(SerpSnapshot)):
        if r.total_count is None:
            continue
        out.append(_row(r.query, "api_index_result_count", r.total_count, MEASURED,
                        "proxy:competition", "etsy_api_marketplace_search",
                        f"serp_snapshots:{r.id}", r.captured_at,
                        {"basis": r.basis, "note": "API index count, not the rendered "
                                                   "etsy.com search page"}))
    return out


def _collect_benchmark_language(s, phrases: list[str]) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    titles = [((r.title or "").lower(), r.id, r.last_seen)
              for r in s.scalars(select(BenchmarkListing))]
    if not titles:
        return []
    out = []
    for phrase in sorted(set(phrases)):
        hits = [t for t in titles if phrase in t[0]]
        if hits:
            out.append(_row(phrase, "benchmark_title_hits", len(hits), OBSERVED,
                            "buyer_language_present", "benchmark_listings",
                            ",".join(str(h[1]) for h in hits[:20]),
                            max((h[2] for h in hits if h[2]), default=None),
                            {"titles_read": len(titles)}))
    return out


def _collect_keyword_table(s) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import Keyword

    out = []
    for r in s.scalars(select(Keyword)):
        out.append(_row(r.phrase, "keyword_est_demand", r.est_demand, MODELLED,
                        "planning_estimate", "keywords_table", f"keywords:{r.id}",
                        r.updated_at, {"note": "est_* columns carry no recorded provenance"}))
    return out


def _collect_templates(queries_by_slug: dict[str, list]) -> list[dict]:
    out = []
    for slug, queries in sorted(queries_by_slug.items()):
        for q in queries:
            basis = OBSERVED if q.observed else MODELLED
            out.append(_row(q.phrase, "template_demand", q.demand, basis, "planning_estimate",
                            "commerce.search.build_query_set", f"{slug}:{q.family}", None,
                            {"competition": q.competition, "provenance": q.provenance}))
    return out


def collect(db, *, queries_by_slug: dict[str, list] | None = None) -> list[dict]:
    """Every evidence row the current sources support, as dicts (not yet stored)."""
    queries_by_slug = queries_by_slug or {}
    rows: list[dict] = []
    phrases = sorted({q.phrase for qs in queries_by_slug.values() for q in qs})
    collectors = [_collect_stats, _collect_insights, _collect_serp, _collect_keyword_table,
                  lambda s: _collect_benchmark_language(s, phrases)]
    for fn in collectors:
        try:
            with session(db) as s:
                rows += fn(s)
        except Exception:  # noqa: BLE001 - an absent source table is no evidence, not zero
            continue
    rows += _collect_templates(queries_by_slug)
    # Dedup by fingerprint, keep order.
    seen, out = set(), []
    for r in rows:
        if r["fingerprint"] not in seen and r["phrase"]:
            seen.add(r["fingerprint"])
            out.append(r)
    return out


def ingest(db, *, queries_by_slug: dict[str, list] | None = None) -> dict:
    """Store every new evidence row. Idempotent: an unchanged source adds nothing."""
    from sqlalchemy import select

    ensure_tables(db)
    rows = collect(db, queries_by_slug=queries_by_slug)
    added = 0
    with session(db) as s:
        have = set(s.scalars(select(SeoKeywordEvidence.fingerprint)))
        for r in rows:
            if r["fingerprint"] in have:
                continue
            s.add(SeoKeywordEvidence(**r))
            have.add(r["fingerprint"])
            added += 1
    return {"added": added, "seen": len(rows)}


def all_rows(db) -> list[dict]:
    from sqlalchemy import select

    ensure_tables(db)
    with session(db) as s:
        return [{"id": r.id, "phrase": r.phrase, "metric": r.metric, "value": r.value,
                 "basis": r.basis, "use": r.use, "source": r.source,
                 "source_ref": r.source_ref,
                 "observed_at": r.observed_at.isoformat() if r.observed_at else None,
                 "fingerprint": r.fingerprint, "detail": dict(r.detail or {})}
                for r in s.scalars(select(SeoKeywordEvidence).order_by(SeoKeywordEvidence.id))]


def fingerprint(db) -> str:
    """One hash over the stored evidence set; changes exactly when evidence is added."""
    return _fp(sorted(r["fingerprint"] for r in all_rows(db)))


def by_phrase(rows: list[dict]) -> dict[str, dict]:
    """Per phrase: the strongest basis held and the measured figures, labelled."""
    rank = {MEASURED: 3, OBSERVED: 2, MODELLED: 1, UNKNOWN: 0}
    out: dict[str, dict] = {}
    for r in rows:
        e = out.setdefault(r["phrase"], {"phrase": r["phrase"], "basis": UNKNOWN,
                                         "measured": {}, "sources": []})
        if rank.get(r["basis"], 0) > rank.get(e["basis"], 0):
            e["basis"] = r["basis"]
        if r["basis"] == MEASURED:
            e["measured"][r["metric"]] = r["value"]
        src = f"{r['source']}:{r['source_ref']}"
        if src not in e["sources"]:
            e["sources"].append(src)
    for e in out.values():
        m = e["measured"]
        imp, orders = m.get("stats_impressions"), m.get("stats_orders")
        e["vanity"] = bool(imp and orders == 0)
        e["earning"] = bool(orders and orders > 0)
    return out


def basis_counts(rows: list[dict]) -> dict[str, int]:
    counts = {MEASURED: 0, OBSERVED: 0, MODELLED: 0, UNKNOWN: 0}
    for e in by_phrase(rows).values():
        counts[e["basis"]] = counts.get(e["basis"], 0) + 1
    return counts

