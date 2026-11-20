"""The owner's visibility view (F-287), with traffic sources kept apart (F-289).

One read of everything the Master's Visibility Command Center names: storefront completion,
Search Visibility issues, search readiness, search terms, impressions, clicks, conversion,
Etsy Ads, Offsite Ads, seasonal readiness and real owner actions -- plus the launch verdict's
six questions (F-300), the demand-capture plan (F-275), the first-30-day learning plan
(F-281), the launch-success verdict (F-286) and actionable recommendations (F-288).

The pieces already existed behind separate routes; this module is the one view of them.
Each section is read from its own producer and guarded: a section that cannot be read is
UNKNOWN with the exception type, never a pass and never zero.

Traffic sources (F-289): Etsy organic, Etsy Ads, Offsite Ads and owned/direct are separate
rows with `unattributed` explicit beside them (`finance.sources.table`); a blended total is
never shown without its components.

`summary(db)` follows the Command Center provider contract (`status`, `as_of`, `basis`,
`items`, `sources`) so the Command Center can render it as a department card; `view(db)` is
the full detail behind it. Nothing here writes, contacts a provider or calls a model; it does
not run the (slow) full readiness assessment -- the launch verdict is read from the newest
`launch.assessed` row the daily `launch.readiness` job wrote.
"""
from __future__ import annotations

from datetime import datetime, timezone

STATS_KIND = "attribution.stats"  # runtime.release.ATTRIBUTION_KIND (not imported: heavy)
PROVIDER = "brambleloop.launch.visibility"

SECTIONS: tuple[tuple[str, str], ...] = (
    ("launch_verdict", "Launch verdict (six questions)"),
    ("storefront_completion", "Storefront completion"),
    ("search_visibility_issues", "Search Visibility issues"),
    ("search_readiness", "Search readiness"),
    ("search_terms", "Search terms"),
    ("funnel", "Impressions, clicks, conversion"),
    ("traffic_sources", "Traffic sources (never blended)"),
    ("etsy_ads", "Etsy Ads"),
    ("offsite_ads", "Offsite Ads"),
    ("seasonal_readiness", "Seasonal readiness (Christmas)"),
    ("demand_capture", "Demand-capture plan"),
    ("learning_plan", "First-30-day learning plan"),
    ("launch_success", "Launch success (multi-signal)"),
    ("recommendations", "Actionable recommendations"),
    ("owner_actions", "Owner actions"),
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def latest_stats(db) -> dict | None:
    """The newest ingested Etsy Stats export payload, or None."""
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == STATS_KIND)
                       .order_by(desc(OperatingReading.at), desc(OperatingReading.id)).limit(1))
        return dict(row.payload or {}, reading_id=row.id,
                    at=row.at.isoformat() if row.at else None) if row is not None else None


def _guard(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, with the type only
        return {"state": "UNKNOWN", "why": f"unreadable: {type(exc).__name__}"}


def _launch_verdict(db) -> dict:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "launch.assessed")
                       .order_by(desc(AuditLog.id)).limit(1))
        if row is None:
            return {"state": "UNKNOWN", "why": "launch.readiness has never run"}
        d = dict(row.detail or {})
    if d.get("synthetic_fixture"):
        return {"state": "UNKNOWN", "audit_id": row.id,
                "why": "the newest launch.assessed row is synthetic test evidence"}
    q = d.get("questions")
    return {"state": "PASS" if d.get("ready") is True else "FAIL", "ready": d.get("ready"),
            "assessed_at": row.at.isoformat() if row.at else None, "audit_id": row.id,
            "questions": q or {"why": "this assessment predates the six-question verdict"}}


def _storefront(db) -> dict:
    from ..brand.storefront import build_storefront, check_storefront, opening_grid

    problems = check_storefront(build_storefront(db=db))
    grid = opening_grid(db)
    return {"state": "PASS" if not problems and grid.get("ok") else "FAIL",
            "storefront_problems": problems[:8], "opening_grid_ok": bool(grid.get("ok")),
            "opening_grid_problems": (grid.get("problems") or [])[:6],
            "first_screen": [t["slug"] for t in grid.get("visible") or []]}


def _search_visibility(db) -> dict:
    from ..commerce import search_visibility

    st = search_visibility.state(db)
    return {"state": "MEASURED" if search_visibility.latest_reading_at(db) else "UNMEASURED",
            **{k: st[k] for k in list(st)[:12]}}


def _search_readiness(db) -> dict:
    from ..commerce import ranking_readiness
    from . import demand

    rows = []
    for l in demand._opening_listings(db)[:30]:
        c = ranking_readiness.search_certificate(db, l["slug"], l["version"])
        rows.append({"listing": f"{l['slug']}@{l['version']}", "certificate": c["verdict"]})
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["certificate"]] = counts.get(r["certificate"], 0) + 1
    return {"state": ("PASS" if rows and counts.get("PASS", 0) == len(rows) else
                      "UNMEASURED" if not rows else "FAIL"),
            "certificates": counts, "listings": rows}


def _search_terms(stats: dict | None) -> dict:
    if not stats:
        return {"state": "UNMEASURED", "why": "no Etsy Stats export has been ingested"}
    j = stats.get("joined") or {}
    return {"state": "MEASURED", "period": stats.get("period_key"),
            "ranked_on": j.get("ranked_on"),
            "terms": [{k: t.get(k) for k in ("term", "impressions", "visits", "orders",
                                             "ctr", "conversion", "vanity")}
                      for t in (j.get("terms") or [])[:15]],
            "vanity_terms": (j.get("vanity_terms") or [])[:15]}


def _funnel(db) -> dict:
    from ..scale import leading

    stats = latest_stats(db) or {}
    totals = (stats.get("joined") or {}).get("totals") or {}
    observed = {k: v for k, v in (("impressions", totals.get("impressions")),
                                  ("visits", totals.get("visits"))) if v is not None}
    if observed:
        observed["source"] = f"operating_readings:{STATS_KIND}#{stats.get('reading_id')}"
    d = leading.dashboard(db, observed=observed)
    ind = d["indicators"]
    return {"state": "MEASURED" if any(ind[k]["status"] == "measured" for k in (
                "qualified_impressions", "ctr", "conversion")) else "UNMEASURED",
            "impressions": ind["qualified_impressions"], "clicks_ctr": ind["ctr"],
            "conversion": ind["conversion"], "favourites_and_cart": ind["favourites_and_cart"]}


def _traffic_sources(db) -> dict:
    from ..finance import sources

    t = sources.table(db)
    return {"state": "MEASURED" if t["total_orders"] else "UNMEASURED",
            "channels": t["channels"], "order": list(sources.CHANNELS) + [sources.UNATTRIBUTED],
            "total_orders": t["total_orders"], "unattributed_share": t["unattributed_share"],
            "rule": "every channel is a row; the total is the sum of the rows (F-289)"}


def _ads(db) -> dict:
    from ..growth import ads_readiness

    s = ads_readiness.summary(db)
    return {"state": s.get("status", "UNKNOWN"),
            **{k: s.get(k) for k in ("items", "reason", "basis") if k in s}}


def _offsite(db) -> dict:
    from ..commerce import paid_media
    from ..finance import sources

    t = sources.table(db)
    terms = paid_media.offsite_ads_terms()
    return {"state": "MEASURED" if t["total_orders"] else "UNMEASURED",
            "offsite_orders": t["channels"]["offsite_ads"]["orders"],
            "offsite_revenue_cad": t["channels"]["offsite_ads"]["revenue_cad"],
            "terms": {k: terms.get(k) for k in list(terms)[:8]}}


def _owner_actions(db) -> dict:
    from sqlalchemy import select

    from ..core.models import OwnerAction

    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(OwnerAction.done == False)  # noqa: E712
                              .order_by(OwnerAction.id)))
        items = [{"key": r.requirement_key, "action": r.action, "why": r.reason,
                  "max_cost_cad": r.max_cost_known,  # None = UNKNOWN (W3-WIRE4)
                  "max_cost_basis": r.max_cost_basis or "stated", "minutes": r.minutes,
                  "consequence_of_delay": r.consequence_of_delay} for r in rows[:20]]
    return {"state": "OPEN" if rows else "NONE", "open": len(rows), "items": items}


def view(db) -> dict:
    """Every section, each read from its producer and guarded."""
    from . import demand, recommendations, success

    stats = _guard(lambda: latest_stats(db))
    stats = stats if isinstance(stats, dict) and "state" not in stats else None
    sections = {
        "launch_verdict": _guard(lambda: _launch_verdict(db)),
        "storefront_completion": _guard(lambda: _storefront(db)),
        "search_visibility_issues": _guard(lambda: _search_visibility(db)),
        "search_readiness": _guard(lambda: _search_readiness(db)),
        "search_terms": _search_terms(stats),
        "funnel": _guard(lambda: _funnel(db)),
        "traffic_sources": _guard(lambda: _traffic_sources(db)),
        "etsy_ads": _guard(lambda: _ads(db)),
        "offsite_ads": _guard(lambda: _offsite(db)),
        "seasonal_readiness": _guard(lambda: {"state": "TRACKED",
                                              **demand.christmas_checkpoints(db)}),
        "demand_capture": _guard(lambda: (lambda p: {
            "state": "PASS" if p["complete"] else "FAIL", **p})(demand.capture_plan(db))),
        "learning_plan": _guard(lambda: {"state": "TRACKED", **demand.learning_plan(db)}),
        "launch_success": _guard(lambda: (lambda v: {
            "state": "PASS" if v["success"] else
            ("FAIL" if v["failing"] else "UNMEASURED"), **v})(success.verdict(db))),
        "recommendations": _guard(lambda: (lambda r: {
            "state": r["status"].upper() if r["status"] != "measured" else "MEASURED", **r})(
            recommendations.from_stats(db))),
        "owner_actions": _guard(lambda: _owner_actions(db)),
    }
    return {"as_of": _now(), "sections": sections,
            "labels": dict(SECTIONS),
            "note": ("one owner view of visibility; each section is read from its producer, "
                     "UNKNOWN when unreadable, UNMEASURED when nothing has been observed")}


def summary(db) -> dict:
    """Command Center provider contract: status, as_of, basis, items, sources."""
    _ = db.session  # a bare Session raises AttributeError: the CC retries with the facade
    v = view(db)
    secs = v["sections"]
    items = []
    for key, label in SECTIONS:
        sec = secs.get(key) or {}
        items.append({"key": key, "label": label, "state": sec.get("state", "UNKNOWN"),
                      "why": sec.get("why")})
    verdict = secs["launch_verdict"].get("state")
    unreadable = [i["key"] for i in items if str(i["why"] or "").startswith("unreadable:")]
    if verdict == "UNKNOWN":
        status = "UNKNOWN"
    elif verdict != "PASS":
        status = "BLOCKED"
    elif unreadable:
        status = "DEGRADED"
    else:
        status = "OK"
    return {"status": status, "as_of": v["as_of"], "basis": "measured", "items": items,
            "sources": ["audit_log:launch.assessed", f"operating_readings:{STATS_KIND}",
                        "finance.sources.table", "growth.ads_readiness.summary",
                        "commerce.search_visibility.state", "brand.storefront",
                        "owner_actions", "launch.demand", "launch.success",
                        "launch.recommendations"],
            "provider": PROVIDER, "unreadable": unreadable,
            "reason": (None if status == "OK" else
                       "launch verdict not passing" if status == "BLOCKED" else
                       secs["launch_verdict"].get("why") if status == "UNKNOWN" else
                       f"unreadable sections: {unreadable}"),
            "detail": v}
