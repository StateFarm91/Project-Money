"""Marketplace Insights, recorded by the owner from Shop Manager (#236, #37).

Marketplace Insights is a Shop Manager surface with no endpoint in Etsy's OpenAPI document
(`intel.etsy_surfaces`, marketplace_insights). Nothing here fetches it and nothing here
renders the page: the owner opens it in their own browser, reads a keyword's figures, and
records them through `POST /api/insights/snapshot`. That is how a seller reads their own
dashboard, not automation around it (B-268).

Every row carries `basis = owner_recorded_shop_manager` and who recorded it. They are Etsy's
figures as a person read them on a date, and they are never merged into anything that reads
as this company's own measurement -- in particular they are not the API index's counts the
SERP laboratory records, which are a different number from a different system.

The store is also #37's "store every query/result snapshot so the same keyword is not
wastefully re-queried": `intel.insights_budget` reads it and skips keywords already recorded.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

BASIS = "owner_recorded_shop_manager"
TRENDS = ("up", "down", "flat", "unknown")
# A keyword recorded within this many days is not worth asking again.
REQUERY_AFTER_DAYS = 90


class InsightsRefused(ValueError):
    """A reading that cannot say what was read, by whom, or when."""


def _norm(keyword: str) -> str:
    return " ".join(str(keyword or "").lower().split())


def _count(value, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise InsightsRefused(f"{name}={value!r} is not a count") from exc
    if n < 0:
        raise InsightsRefused(f"{name} cannot be negative")
    return n


def record(db, *, keyword: str, search_count=None, listing_count=None,
           related_terms: list | None = None, trend_direction: str = "unknown",
           geography: str = "", observed_on: str | date | None = None,
           recorded_by: str = "") -> dict:
    """Store one owner-read Insights snapshot. Refuses a reading with nothing in it."""
    from ..core.models import InsightsSnapshot

    keyword = _norm(keyword)
    if not keyword:
        raise InsightsRefused("a snapshot with no keyword is not about anything")
    if not str(recorded_by or "").strip():
        raise InsightsRefused("recorded_by is required: a figure nobody owns is a rumour")
    searches = _count(search_count, "search_count")
    listings = _count(listing_count, "listing_count")
    terms = [_norm(t) for t in (related_terms or []) if _norm(t)]
    if searches is None and listings is None and not terms:
        raise InsightsRefused("no search count, listing count or related term was given; "
                              "an empty reading would look like a keyword nobody searches")
    trend = str(trend_direction or "unknown").strip().lower()
    if trend not in TRENDS:
        raise InsightsRefused(f"trend_direction {trend!r} is not one of {TRENDS}")

    if isinstance(observed_on, date):
        day = observed_on
    elif observed_on:
        try:
            day = date.fromisoformat(str(observed_on)[:10])
        except ValueError as exc:
            raise InsightsRefused(f"observed_on {observed_on!r} is not an ISO date") from exc
    else:
        day = datetime.now(timezone.utc).date()
    when = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    if when > datetime.now(timezone.utc) + timedelta(days=1):
        raise InsightsRefused("a reading cannot have been made in the future")

    with db.session() as s:
        row = InsightsSnapshot(keyword=keyword, search_count=searches,
                               listing_count=listings, related_terms=terms,
                               trend_direction=trend, geography=str(geography or "").strip(),
                               observed_on=when, recorded_by=str(recorded_by).strip()[:80],
                               basis=BASIS)
        s.add(row)
        s.flush()
        rid = row.id
    return {"id": rid, "keyword": keyword, "search_count": searches,
            "listing_count": listings, "related_terms": terms, "trend_direction": trend,
            "geography": str(geography or "").strip(), "observed_on": day.isoformat(),
            "recorded_by": str(recorded_by).strip()[:80], "basis": BASIS}


def snapshots(db) -> list[dict]:
    from sqlalchemy import desc, select

    from ..core.models import InsightsSnapshot

    with db.session() as s:
        rows = list(s.scalars(select(InsightsSnapshot)
                              .order_by(desc(InsightsSnapshot.observed_on))))
        return [{"id": r.id, "keyword": r.keyword, "search_count": r.search_count,
                 "listing_count": r.listing_count, "related_terms": list(r.related_terms or []),
                 "trend_direction": r.trend_direction, "geography": r.geography,
                 "observed_on": (r.observed_on if r.observed_on.tzinfo else
                                 r.observed_on.replace(tzinfo=timezone.utc)).date().isoformat(),
                 "recorded_by": r.recorded_by, "basis": r.basis} for r in rows]


def queried_keywords(db, *, within_days: int = REQUERY_AFTER_DAYS,
                     today: date | None = None) -> set[str]:
    """Keywords with a snapshot recent enough that asking again would be waste (#37)."""
    today = today or datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=within_days)
    return {row["keyword"] for row in snapshots(db)
            if date.fromisoformat(row["observed_on"]) >= cutoff}


def insights_recorded(db) -> bool:
    """Whether at least one owner-recorded Insights snapshot exists. The gate's condition."""
    from sqlalchemy import func, select

    from ..core.models import InsightsSnapshot

    with db.session() as s:
        return bool(s.scalar(select(func.count(InsightsSnapshot.id))) or 0)
