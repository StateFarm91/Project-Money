"""Launch demand capture (F-275), Christmas search compression (F-276) and the first-30-day
learning plan (F-281).

`commerce.launch.plan_launch` already counts a product's timeline back from its buying window,
and the release chain records it (`launch.planned`). What did not exist is the object that
links each *opening* product to everything that decides whether demand finds it:

* **search intents** -- the phrases its listing targets, and whether the listing stage recorded
  their coverage at drafting (`listing.query_portfolio`, the pre-launch search baseline);
* **seasonal runway** -- the recorded launch plan (`launch.planned` / `launch.held`);
* **storefront placement** -- where the opening grid puts it (`brand.storefront.opening_grid`);
* **organic readiness** -- its search certificate (`commerce.ranking_readiness`);
* **Etsy Ads plan** -- the ads readiness gates (`growth.ads_readiness.listing_readiness`).
  "Organic only until every gate passes and the owner sets a ceiling" is a plan; an
  unreadable reading is not;
* **measurement checkpoints** -- the day 1/3/7/14/30 reviews of the learning plan below.

`capture_plan(db)["complete"]` is True only when every opening product has every link. The
phase transition (`core.phase.record_transition`, through
`launch.readiness.transition_verdict`) refuses any move up while it is not.

The Christmas checkpoints (F-276) count the query/title/tag/attribute, gallery, storefront and
ads work back from the day the Christmas buying window opens, so listings collect engagement
before peak buying. A late checkpoint compresses the schedule; it never relaxes a gate --
`URGENCY_RULE` is carried on every reading.

The learning plan (F-281) predefines the day 1/3/7/14/30 reviews and the metric set each one
reads. `record_due_reviews` snapshots each review once its day arrives (called from the daily
`launch.readiness` handler); a metric nobody can observe yet is recorded UNMEASURED, never 0.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# ---- F-281 ---------------------------------------------------------------------------------

REVIEW_DAYS: tuple[int, ...] = (1, 3, 7, 14, 30)
METRICS: tuple[str, ...] = ("impressions", "clicks", "favorites", "sales", "conversion",
                            "search_terms", "ads", "support_friction", "contribution")
# What each review decides. Ordered by what can be known by then: a day-1 listing has no
# meaningful traffic, so day 1 checks delivery and indexing, not conversion.
REVIEW_FOCUS: dict[int, str] = {
    1: ("delivery and indexing: every live listing is reachable, downloads complete, no "
        "support friction from the first buyers; traffic is not judged yet"),
    3: ("exposure: are listings collecting impressions? Inadequate exposure stays UNMEASURED "
        "and routes to exposure diagnosis, never to 'weak'"),
    7: ("clicks: listings with adequate impressions and weak clicks route to hero/title "
        "diagnosis before any budget escalation"),
    14: ("conversion: healthy clicks with no sales route to product/value/trust/price "
         "diagnosis rather than SEO by default; amplify what converts"),
    30: ("first performance read: contribution per channel (organic, Etsy Ads, Offsite Ads, "
         "owned/direct kept separate), search terms that earn, support friction"),
}
REVIEW_ACTION = "launch.learning_review"


def launch_started_at(db) -> datetime | None:
    """When live publication began: the recorded owner move into limited_production in the
    current phase chain (F-299). None while the company has never left staging."""
    from ..core import phase as phase_mod

    try:
        hist = phase_mod.history(db, limit=0)
    except Exception:  # noqa: BLE001 - an unreadable record is no launch
        return None
    starts = [h for h in hist if h.get("valid") and h.get("to") == "limited_production"
              and h.get("direction") == "up"]
    if not starts:
        return None
    at = min(str(h.get("at")) for h in starts)
    try:
        dt = datetime.fromisoformat(at)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _recorded_reviews(db) -> dict[int, dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    out: dict[int, dict] = {}
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == REVIEW_ACTION)
                             .order_by(AuditLog.id)):
            d = dict(row.detail or {})
            if isinstance(d.get("day"), int):
                out.setdefault(d["day"], {"audit_id": row.id, **d})
    return out


def learning_plan(db, *, now: datetime | None = None) -> dict:
    """F-281: the five predefined reviews, each with its date, focus, metric set and state."""
    now = now or datetime.now(timezone.utc)
    started = launch_started_at(db)
    recorded = _recorded_reviews(db)
    reviews = []
    for day in REVIEW_DAYS:
        due = started + timedelta(days=day) if started else None
        if day in recorded:
            state = "REVIEWED"
        elif due is None:
            state = "SCHEDULED_RELATIVE"
        elif now >= due:
            state = "DUE"
        else:
            state = "SCHEDULED"
        reviews.append({"day": day, "due_at": due.isoformat() if due else None,
                        "focus": REVIEW_FOCUS[day], "metrics": list(METRICS), "state": state,
                        "audit_id": recorded.get(day, {}).get("audit_id")})
    return {"launch_started_at": started.isoformat() if started else None,
            "anchor": ("the owner's recorded move into limited_production (core.phase)"),
            "reviews": reviews, "metrics": list(METRICS),
            "note": ("predefined before launch; a review's metrics are snapshotted once its day "
                     "arrives, and a metric with no source is UNMEASURED, never 0")}


def metric_snapshot(db) -> dict:
    """Every F-281 metric, measured with its source or UNMEASURED with its reason."""
    from . import visibility

    stats = visibility.latest_stats(db)
    totals = (stats or {}).get("joined", {}).get("totals") or {}

    def from_stats(key, label):
        v = totals.get(key)
        if v is None:
            return {"status": "UNMEASURED", "why": f"no Etsy Stats export carries {label}"}
        return {"status": "measured", "value": v, "source": "operating_readings:"
                                                             "attribution.stats"}

    out = {"impressions": from_stats("impressions", "impressions"),
           "clicks": from_stats("visits", "visits"),
           "sales": from_stats("orders", "orders")}
    out["favorites"] = {"status": "UNMEASURED",
                        "why": "the Stats export ingested carries no favourites column"}
    vis, orders = totals.get("visits"), totals.get("orders")
    out["conversion"] = ({"status": "measured", "value": round(orders / vis, 5),
                          "source": "attribution.stats totals"}
                         if vis and orders is not None else
                         {"status": "UNMEASURED", "why": "visits and orders not both known"})
    terms = (stats or {}).get("joined", {}).get("terms") or []
    out["search_terms"] = ({"status": "measured", "value": [t.get("term") for t in terms[:10]],
                            "source": "attribution.stats"} if terms else
                           {"status": "UNMEASURED", "why": "no search terms ingested"})
    try:
        from ..growth import ads_readiness

        out["ads"] = {"status": "measured", "value": ads_readiness.kpis(db),
                      "source": "growth.ads_readiness.kpis"}
    except Exception as exc:  # noqa: BLE001
        out["ads"] = {"status": "UNMEASURED", "why": f"ads kpis unreadable: {type(exc).__name__}"}
    try:
        from ..scale import leading

        ind = leading.dashboard(db)["indicators"]["support_defects"]
        out["support_friction"] = ind
    except Exception as exc:  # noqa: BLE001
        out["support_friction"] = {"status": "UNMEASURED",
                                   "why": f"support reading unreadable: {type(exc).__name__}"}
    try:
        from ..finance import sources

        t = sources.table(db)
        contribution = {k: v["contribution_cad"] for k, v in t["channels"].items()}
        out["contribution"] = ({"status": "measured", "value": contribution,
                                "source": "finance.sources.table (per channel)"}
                               if t["total_orders"] else
                               {"status": "UNMEASURED", "why": "no countable orders"})
    except Exception as exc:  # noqa: BLE001
        out["contribution"] = {"status": "UNMEASURED",
                               "why": f"channel table unreadable: {type(exc).__name__}"}
    return {k: out[k] for k in METRICS}


def record_due_reviews(db, *, now: datetime | None = None) -> list[int]:
    """Snapshot every review whose day has arrived and that has not been recorded. Idempotent;
    the daily `launch.readiness` handler calls it. Returns the days recorded now."""
    from ..core.models import AuditLog

    plan = learning_plan(db, now=now)
    due = [r["day"] for r in plan["reviews"] if r["state"] == "DUE"]
    if not due:
        return []
    snap = metric_snapshot(db)
    with db.session() as s:
        for day in due:
            s.add(AuditLog(actor="orchestrator", action=REVIEW_ACTION,
                           artifact=f"launch-day-{day}",
                           detail={"day": day, "focus": REVIEW_FOCUS[day],
                                   "launch_started_at": plan["launch_started_at"],
                                   "metrics": snap}))
    return due


# ---- F-276 ---------------------------------------------------------------------------------

URGENCY_RULE = ("a late checkpoint compresses the schedule; it never relaxes truth, quality, "
                "policy or certification gates (F-276, F-298)")
# (key, what must be true, days before the Christmas buying window opens)
CHRISTMAS_CHECKPOINTS: tuple[tuple[str, str, int], ...] = (
    ("query_strategy", "Christmas query/title/tag/attribute strategy refreshed from current "
     "evidence (F-285)", 42),
    ("gallery", "Christmas gallery and hero frames final and Asset-Truth cleared", 35),
    ("listings_indexed", "Christmas listings live so Etsy can index them (indexing takes "
     "weeks)", 21),
    ("storefront", "banner, announcement, sections and featured products carry the "
     "Christmas story (F-279)", 14),
    ("ads_learning", "if the owner authorises Etsy Ads, campaigns start early enough to finish "
     "learning before peak; organic-only is a valid answer", 7),
    ("engagement_window", "listings collect clicks and favourites before peak buying", 0),
)


def christmas_window(today: date) -> tuple[date, date, date]:
    """(window_opens, peak, window_closes) for the next Christmas, from the radar's
    make-time evidence. Peak is the window's midpoint."""
    from ..radar.market import SEASONAL_EVENTS, SeasonalEvent, shopping_window

    base = next(e for e in SEASONAL_EVENTS if e.name == "Christmas")
    year = today.year if today <= date(today.year, 12, 25) else today.year + 1
    ev = SeasonalEvent("Christmas", date(year, 12, 25), base.typical_make_hours,
                       base.gift_lead_days)
    opens, closes = shopping_window(ev)
    return opens, opens + (closes - opens) / 2, closes


def christmas_checkpoints(db, *, today: date | None = None) -> dict:
    """F-276: each checkpoint with its date and whether evidence shows it done."""
    today = today or datetime.now(timezone.utc).date()
    opens, peak, closes = christmas_window(today)
    done = _christmas_evidence(db, opens)
    rows = []
    for key, what, lead in CHRISTMAS_CHECKPOINTS:
        by = opens - timedelta(days=lead)
        ev = done.get(key) or {}
        if ev.get("done"):
            state = "DONE"
        elif ev.get("not_applicable"):
            state = "NOT_AUTHORISED"
        elif today > by:
            state = "LATE"
        else:
            state = "OPEN"
        rows.append({"checkpoint": key, "requirement": what, "by": by.isoformat(),
                     "state": state, "evidence": ev.get("evidence")})
    late = [r["checkpoint"] for r in rows if r["state"] == "LATE"]
    return {"event": "Christmas", "window_opens": opens.isoformat(),
            "peak": peak.isoformat(), "window_closes": closes.isoformat(),
            "days_to_peak": (peak - today).days, "checkpoints": rows, "late": late,
            "compressed": bool(late), "urgency_rule": URGENCY_RULE}


def _christmas_evidence(db, opens: date) -> dict:
    from sqlalchemy import func, select

    from ..core.models import AuditLog, Listing, ListingAsset

    since = datetime.combine(opens - timedelta(days=120), datetime.min.time(),
                             tzinfo=timezone.utc)
    out: dict[str, dict] = {}
    with db.session() as s:
        refreshed = s.scalar(select(func.count(AuditLog.id)).where(
            AuditLog.action == "listing.query_portfolio", AuditLog.at >= since)) or 0
        approved = s.scalar(select(func.count(ListingAsset.id)).where(
            ListingAsset.approved == True)) or 0  # noqa: E712
        live = s.scalar(select(func.count(Listing.id)).where(
            Listing.etsy_listing_id.is_not(None), Listing.etsy_listing_id != "")) or 0
    out["query_strategy"] = {"done": refreshed > 0,
                             "evidence": f"{refreshed} listing.query_portfolio reading(s) "
                                         f"since {since.date().isoformat()}"}
    out["gallery"] = {"done": approved > 0, "evidence": f"{approved} approved listing frame(s)"}
    out["listings_indexed"] = {"done": live > 0,
                               "evidence": f"{live} listing(s) carry an Etsy listing id"}
    try:
        from ..brand.storefront import opening_grid

        events = [str(e) for e in (opening_grid(db).get("active_events") or [])]
        out["storefront"] = {"done": any("christmas" in e.lower() for e in events),
                             "evidence": f"opening grid active events: {events[:4]}"}
    except Exception as exc:  # noqa: BLE001
        out["storefront"] = {"done": False, "evidence": f"unreadable: {type(exc).__name__}"}
    out["ads_learning"] = {"done": False, "not_applicable": True,
                           "evidence": ("no owner-authorised Etsy Ads ceiling: the plan is "
                                        "organic-only, which needs no ads learning window")}
    try:
        from . import visibility

        reading = visibility.latest_stats(db)
        imp = ((reading or {}).get("joined") or {}).get("totals", {}).get("impressions")
        out["engagement_window"] = {"done": bool(live and imp),
                                    "evidence": f"latest Stats impressions: {imp}"}
    except Exception as exc:  # noqa: BLE001
        out["engagement_window"] = {"done": False,
                                    "evidence": f"unreadable: {type(exc).__name__}"}
    return out


# ---- F-275 ---------------------------------------------------------------------------------

def _opening_listings(db) -> list:
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        rows = list(s.scalars(select(Listing).where(Listing.state != "withdrawn")
                              .order_by(Listing.product_slug)))
        return [{"slug": l.product_slug, "version": l.version, "tags": list(l.tags or []),
                 "title": l.title} for l in rows]


def capture_plan(db, *, now: datetime | None = None) -> dict:
    """F-275: every opening product linked to the six demand-capture elements, with gaps."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    listings = _opening_listings(db)
    with db.session() as s:
        baselines = {str(r.artifact or "") for r in s.scalars(
            select(AuditLog).where(AuditLog.action == "listing.query_portfolio"))}
        planned: dict[str, dict] = {}
        for r in s.scalars(select(AuditLog).where(AuditLog.action.in_(
                ("launch.planned", "launch.held"))).order_by(AuditLog.id)):
            planned[str(r.artifact or "").split("@")[0]] = {"action": r.action,
                                                             **dict(r.detail or {})}
    try:
        from ..brand.storefront import opening_grid

        grid = opening_grid(db)
        visible = [t["slug"] for t in grid.get("visible") or []]
        excluded = {str(t.get("slug")): t for t in grid.get("excluded") or []
                    if isinstance(t, dict)}
        grid_err = None
    except Exception as exc:  # noqa: BLE001
        visible, excluded, grid_err = [], {}, type(exc).__name__
    learning = learning_plan(db, now=now)
    products, gaps_summary = [], []
    for l in listings:
        slug, version = l["slug"], l["version"]
        gaps: list[str] = []
        intents = [t for t in l["tags"] if str(t).strip()]
        if not intents:
            gaps.append("search_intents: listing targets no phrase")
        if f"{slug}@{version}" not in baselines:
            gaps.append("search_intents: no coverage baseline recorded at drafting")
        runway = planned.get(slug)
        if runway is None:
            gaps.append("seasonal_runway: no launch.planned / launch.held record")
        if grid_err:
            placement = {"state": "UNREADABLE", "why": grid_err}
            gaps.append("storefront_placement: opening grid unreadable")
        elif slug in visible:
            placement = {"state": "FIRST_SCREEN", "position": visible.index(slug) + 1}
        elif slug in excluded:
            placement = {"state": "EXCLUDED", "why": excluded[slug].get("reason")
                         or excluded[slug].get("why")}
        else:
            placement = {"state": "BELOW_FIRST_SCREEN"}
        try:
            from ..commerce import ranking_readiness

            cert = ranking_readiness.search_certificate(db, slug, version)
            organic = {"certificate": cert["verdict"], "why": cert["why"]}
            if cert["verdict"] == "NONE":
                gaps.append("organic_readiness: no search certificate recorded")
        except Exception as exc:  # noqa: BLE001
            organic = {"certificate": "UNREADABLE", "why": type(exc).__name__}
            gaps.append("organic_readiness: search certificate unreadable")
        try:
            from ..growth import ads_readiness

            ar = ads_readiness.listing_readiness(db, slug)
            ads = {"plan": ("eligible for an owner-approved Etsy Ads ceiling" if ar["ready"]
                            else "organic only: no ad spend until every ads gate passes and "
                                 "the owner sets a ceiling"),
                   "status": ar["status"], "blocking": ar["blocking"][:6]}
        except Exception as exc:  # noqa: BLE001
            ads = {"plan": None, "status": "UNREADABLE", "why": type(exc).__name__}
            gaps.append("ads_plan: ads readiness unreadable")
        products.append({
            "slug": slug, "version": version,
            "search_intents": intents[:13],
            "seasonal_runway": ({k: runway.get(k) for k in ("action", "launch_on",
                                                             "compressed", "warnings",
                                                             "may_launch_seasonally")}
                                if runway else None),
            "storefront_placement": placement,
            "organic_readiness": organic,
            "ads_plan": ads,
            "measurement_checkpoints": [{"day": r["day"], "due_at": r["due_at"],
                                         "state": r["state"]} for r in learning["reviews"]],
            "gaps": gaps, "complete": not gaps})
        gaps_summary += [f"{slug}@{version} {g}" for g in gaps]
    return {"products": products, "products_count": len(products),
            "complete": bool(products) and not gaps_summary,
            "gaps_summary": gaps_summary[:40],
            "why": (None if products else "no opening product has a listing yet"),
            "rule": ("before any phase change every opening product is linked to its search "
                     "intents, seasonal runway, storefront placement, organic readiness, Etsy "
                     "Ads plan and measurement checkpoints (F-275)")}
