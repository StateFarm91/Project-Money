"""Slow-loop commercial calibration for hero imagery (owner D-FB-16 item 5).

impressions -> CTR (visits / impressions) -> favourites -> carts -> purchases -> conversion
(orders / visits) -> refunds / feedback, read from lane K3's `ListingOutcome` rows (credited to
a hero by `ListingOutcome.hero_style` == `VisualHeroVariant.style_key`).

Every stage is MEASURED (with numerator/denominator and the source rows) or UNKNOWN with a
reason -- never 0. A period nobody exported is absent; a stage the export does not carry
(carts, refunds, feedback today) is UNKNOWN until it does (read from `detail` when a writer
adds it).

This evidence outranks the internal judges: `hero.calibrate` compares the incumbent hero
against the hero it replaced and, when the marketplace says it is significantly worse,
OVERTURNS the proxy promotion -- rollback, a lesson, and a lower trust for the proxy judges
of that class (so the next proxy promotion needs a larger margin and counts for less).
"""
from __future__ import annotations

STAGES = ("impressions", "visits", "ctr", "favourites", "favourite_rate", "carts",
          "purchases", "conversion", "refunds", "refund_rate", "feedback")
SOURCE = "listing_outcomes (lane K3 ListingOutcome; hero_style = VisualHeroVariant.style_key)"


def _unknown(why: str) -> dict:
    return {"value": None, "reading": "UNKNOWN", "why": why}


def _measured(value, **extra) -> dict:
    return {"value": value, "reading": "MEASURED", "basis": "measured (marketplace export)",
            **extra}


def outcome_rows(db, *, style_key: str | None = None, product_class: str | None = None,
                 since: str | None = None, until: str | None = None) -> list:
    """ListingOutcome rows for one hero style (or every style of a class). Read-only."""
    from sqlalchemy import inspect, select

    from ...core.models import ListingOutcome
    from . import models as M

    try:
        if "listing_outcomes" not in set(inspect(M.engine(db)).get_table_names()):
            return []
    except Exception:  # noqa: BLE001
        return []
    with M.session(db) as s:
        q = select(ListingOutcome)
        if style_key is not None:
            q = q.where(ListingOutcome.hero_style == style_key)
        elif product_class is not None:
            q = q.where(ListingOutcome.hero_style.like(f"{product_class}:%"))
        rows = list(s.scalars(q.order_by(ListingOutcome.period_start)))
        out = []
        for r in rows:
            if since and (r.period_start or "") < since:
                continue
            if until and (r.period_start or "") >= until:
                continue
            out.append({"id": r.id, "product_slug": r.product_slug,
                        "period_start": r.period_start, "period_end": r.period_end,
                        "impressions": r.impressions, "visits": r.visits,
                        "favourites": r.favourites, "orders": r.orders,
                        "hero_style": r.hero_style, "source": r.source,
                        "detail": dict(r.detail or {})})
        return out


def _sum(rows, key, *, detail=False):
    vals = [(r["detail"].get(key) if detail else r.get(key)) for r in rows]
    vals = [v for v in vals if isinstance(v, int) and not isinstance(v, bool)]
    return sum(vals) if vals else None


def funnel(rows: list[dict]) -> dict:
    """The funnel over ListingOutcome rows. UNKNOWN never 0."""
    if not rows:
        none = "no ListingOutcome row credited to this hero yet (no live listing/export)"
        return {k: _unknown(none) for k in STAGES} | {"periods": 0, "sources": []}
    imp, vis = _sum(rows, "impressions"), _sum(rows, "visits")
    fav, orders = _sum(rows, "favourites"), _sum(rows, "orders")
    carts = _sum(rows, "carts", detail=True)
    refunds = _sum(rows, "refunds", detail=True)
    feedback = _sum(rows, "reviews", detail=True)

    def rate(n, d, name):
        if n is None or not d:
            return _unknown(f"{name}: numerator or denominator not measured")
        return _measured(round(n / d, 4), numerator=n, denominator=d)

    def count(v, name, why):
        return _measured(v) if v is not None else _unknown(f"{name}: {why}")

    return {
        "impressions": count(imp, "impressions", "not in export"),
        "visits": count(vis, "visits", "not in export"),
        "ctr": rate(vis, imp, "CTR"),
        "favourites": count(fav, "favourites", "not in export"),
        "favourite_rate": rate(fav, vis, "favourite rate"),
        "carts": count(carts, "carts", "the Stats export rows carry no cart count yet"),
        "purchases": count(orders, "purchases", "orders not in export"),
        "conversion": rate(orders, vis, "conversion"),
        "refunds": count(refunds, "refunds", "no refund count credited to these periods"),
        "refund_rate": rate(refunds, orders, "refund rate"),
        "feedback": count(feedback, "feedback", "no review count credited to these periods"),
        "periods": len(rows), "sources": sorted({r["source"] for r in rows})[:10],
    }


def commercial_component(rows: list[dict]) -> dict:
    """The objective's `commercial` component: measured CTR x conversion proxy-free reading,
    scaled to 0..1 against the class's own floor -- or UNKNOWN."""
    f = funnel(rows)
    ctr, conv = f["ctr"]["value"], f["conversion"]["value"]
    if ctr is None:
        return {"value": None, "basis": "unknown", "why": "no measured CTR"}
    # A 2% CTR and a 3% conversion are a strong listing on Etsy-scale traffic; saturate there.
    v = min(1.0, ctr / 0.02) * (0.5 + 0.5 * min(1.0, conv / 0.03) if conv is not None else 1.0)
    return {"value": round(v, 4), "basis": "measured (marketplace export)",
            "ctr": ctr, "conversion": conv}
