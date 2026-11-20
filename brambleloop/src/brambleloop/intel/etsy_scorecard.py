"""F-549: one evidence-backed Etsy shop scorecard.

Each line comes from the module that owns it and names that source: live listings
(`listings`), Search Visibility findings (open drift incidents), traffic and conversion
(`scale.runrate.observe` on `analytics.metrics` definitions), revenue and margin
(`finance.books`), reviews, service level (`support.service.service_level`), refunds, ad
spend and efficiency (cost entries kind=ads, `analytics.metrics.roas`), policy status
(`gates.platform_policy.policy_stamp`), OAuth/API health (the latest
`etsy.credential_health` reading) and open owner actions. Every line is guarded: an
unreadable source reads UNKNOWN, and a measure with no data reads UNMEASURED, never 0.
Read-only: no Etsy call.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _g(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - one source never blanks the card
        return {"state": "UNKNOWN", "why": f"unreadable: {type(exc).__name__}"}


def _v(x):
    return "UNMEASURED" if x is None else x


def scorecard(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import desc, func, select

    from ..analytics import metrics
    from ..core.models import (AuditLog, CostEntry, Incident, Listing, Order,
                               OwnerAction)

    now = now or datetime.now(timezone.utc)

    def listings():
        with db.session() as s:
            by = dict(s.execute(select(Listing.state, func.count())
                                .group_by(Listing.state)).all())
        from ..core.listing_state import LIVE_ON_ETSY

        return {"live": sum(int(by.get(st, 0)) for st in LIVE_ON_ETSY), "by_state": {k: int(v) for k, v in by.items()},
                "source": "listings"}

    def search_visibility():
        with db.session() as s:
            open_ = [i.signature for i in s.scalars(select(Incident).where(
                Incident.resolved == False)) if (i.signature or "").startswith(  # noqa: E712
                ("taxonomy-drift:", "search", "listing.search"))]
        return {"open_findings": len(open_), "signatures": open_[:10],
                "source": "incidents (taxonomy drift / search)"}

    def traffic():
        from ..scale import runrate

        o = runrate.observe(db)["observed"]
        return {"visits": _v(o.visits), "impressions": _v(o.impressions),
                "ctr": _v(o.ctr), "conversion": _v(o.conversion),
                "source": "listing_outcomes + orders via analytics.metrics"}

    def money():
        from ..finance.books import Books

        pl = Books(db).profit_and_loss()
        return {"net_sales_cad": pl.net_sales_cad, "contribution_margin_cad":
                pl.contribution_margin_cad, "sales_reading": pl.sales_reading,
                "source": "finance.books (30-day window)"}

    def refunds():
        from ..scale import runrate

        return {"refund_rate": _v(runrate.observe(db)["refund_rate"]),
                "source": "orders (voided / booked)"}

    def service():
        from ..support.service import service_level

        sl = service_level(db, now=now)
        return {k: sl.get(k) for k in list(sl)[:8]} | {"source": "support.service"}

    def reviews():
        from ..commerce import reviews as rv
        from ..runtime.commerce_readings import _review_stars

        d = rv.distribution(_review_stars(db))
        return {"reviews": _v(d.get("reviews") or None), "distribution": d,
                "source": "commerce.reviews.distribution over recorded review stars"}

    def ads():
        with db.session() as s:
            spend = float(s.scalar(select(func.coalesce(func.sum(CostEntry.amount_cad), 0.0))
                                   .where(CostEntry.kind == "ads")) or 0.0)
            n = s.scalar(select(func.count()).select_from(CostEntry)
                         .where(CostEntry.kind == "ads")) or 0
            rev = float(s.scalar(select(func.coalesce(func.sum(Order.revenue_cad), 0.0)).where(
                Order.acquisition_source.in_(("etsy_ads", "offsite_ads")))) or 0.0)
        return {"ad_spend_cad": spend if n else "UNMEASURED",
                "roas": _v(metrics.roas(rev, spend) if n else None),
                "source": "cost_entries kind=ads, orders by ad source"}

    def policy():
        from ..gates.platform_policy import policy_stamp

        p = policy_stamp(db)
        return {"current": p["certified_against_current_policy"],
                "stale_sources": p["stale_sources"], "unread_sources": p["unread_sources"],
                "changed_unreviewed": p["changed_unreviewed"],
                "source": "gates.platform_policy"}

    def api_health():
        with db.session() as s:
            row = s.scalar(select(AuditLog).where(AuditLog.action == "etsy.credential_health")
                           .order_by(desc(AuditLog.id)).limit(1))
        if row is None:
            return {"state": "UNMEASURED", "why": "no credential-health reading recorded"}
        d = row.detail or {}
        return {"at": row.at.isoformat(), "ok": d.get("ok"), "state": d.get("state"),
                "source": "etsy.credential_health"}

    def owner_actions():
        with db.session() as s:
            n = s.scalar(select(func.count()).select_from(OwnerAction).where(
                OwnerAction.done == False)) or 0  # noqa: E712
        return {"open": int(n), "source": "owner_actions"}

    return {"as_of": now.isoformat(), "live_listings": _g(listings),
            "search_visibility": _g(search_visibility), "traffic_and_conversion": _g(traffic),
            "revenue_and_margin": _g(money), "reviews": _g(reviews),
            "service": _g(service), "refunds": _g(refunds), "ads": _g(ads),
            "policy": _g(policy), "oauth_api_health": _g(api_health),
            "owner_actions": _g(owner_actions)}
