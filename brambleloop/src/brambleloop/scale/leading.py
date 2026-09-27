"""The leading-indicator dashboard, and the refusal to call any of it success (#263).

Requirement 263 names ten things to track before revenue arrives -- qualified impressions,
click-through, favourites and cart signals where available, conversion, bundle attach,
email and content traffic, creator traffic, search trend direction, support defects and
release velocity -- and ends with the sentence this module is built around: *avoid declaring
success from leading indicators without orders*.

Each indicator is reported as `measured` with its value and source, or `UNMEASURED` with the
reason and what it needs. None defaults to zero: a zero click-through rate is a listing that
failed, and a listing nobody can see has not failed at anything.

Where the numbers come from:

- **The database**, for what this company records itself: live listings (a listing counts as
  live when it carries an Etsy listing id, the same test the live_listings gate uses, because
  a phase is a statement of intent and a listing id is a listing), orders and support cases
  (`commerce.cohorts` tables, `SupportCase`), and certified releases (`PatternVersion`).
- **`observed`**, for what only the platform or an analytics source knows -- impressions,
  visits, favourites, carts, traffic by channel, a search trend with its provenance. It is
  supplied by the caller from a real export (for example the owner's Etsy Stats CSV through
  `commerce.attribution.parse_stats_csv`); nothing here fetches it, and nothing here invents
  it.

The success verdict is refused without orders, whatever the leading indicators say, and with
orders it points at contribution rather than at the indicators.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..commerce.benchmarks import MIN_ORDERS_FOR_REFUND_RATE
from ..growth.loops import MEASURED_SAMPLE

MEASURED = "measured"
UNMEASURED = "UNMEASURED"

# The ten, in the requirement's order.
INDICATORS: tuple[str, ...] = (
    "qualified_impressions", "ctr", "favourites_and_cart", "conversion", "bundle_attach",
    "email_and_content_traffic", "creator_traffic", "search_trend_direction",
    "support_defects", "release_velocity",
)

# Release velocity is counted over this window. A stated reporting window, not a threshold.
VELOCITY_WINDOW_DAYS = 30

TREND_DIRECTIONS = ("rising", "flat", "falling")


class LeadingRefused(ValueError):
    """An observed value that is not a count, or a trend without a source."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(at: datetime | None) -> datetime | None:
    if at is None:
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _unmeasured(why: str, needs: str) -> dict:
    return {"status": UNMEASURED, "value": None, "why": why, "needs": needs}


def _measured(value, source: str, **extra) -> dict:
    return {"status": MEASURED, "value": value, "source": source, **extra}


def _count(observed: dict, key: str) -> int | None:
    value = observed.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LeadingRefused(f"observed {key!r} must be a non-negative whole count, "
                             f"got {value!r}")
    return value


def _facts(db, now: datetime) -> dict:
    """What this company records itself: listings, orders, support cases, releases."""
    from sqlalchemy import func, select

    from ..core.models import Listing, Order, PatternVersion, SupportCase

    since = now - timedelta(days=VELOCITY_WINDOW_DAYS)
    with db.session() as s:
        live = s.scalar(select(func.count(Listing.id)).where(
            Listing.etsy_listing_id.is_not(None), Listing.etsy_listing_id != "")) or 0
        orders = list(s.scalars(select(Order)))
        cases = s.scalar(select(func.count(SupportCase.id))) or 0
        escalated = s.scalar(select(func.count(SupportCase.id)).where(
            SupportCase.escalated == True)) or 0  # noqa: E712
        releases = [_aware(pv.created_at) for pv in s.scalars(
            select(PatternVersion).where(PatternVersion.certified == True))]  # noqa: E712
        kept = [o for o in orders if not o.refunded]
        order_facts = {
            "orders": len(kept),
            "refunded": len(orders) - len(kept),
            "bundle_or_cross_sell": sum(1 for o in kept if o.cross_sell_of
                                        or "bundle" in (o.product_slug or "")),
        }
    return {"live_listings": live, **order_facts, "support_cases": cases,
            "escalated_cases": escalated,
            "releases_in_window": sum(1 for r in releases if r and r >= since),
            "certified_releases": len(releases)}


def dashboard(db, *, observed: dict | None = None, now: datetime | None = None) -> dict:
    """The ten indicators, each measured or UNMEASURED, and the success verdict refused
    without orders."""
    now = now or _utcnow()
    observed = dict(observed or {})
    facts = _facts(db, now)
    live = facts["live_listings"]
    orders = facts["orders"]
    impressions = _count(observed, "impressions")
    visits = _count(observed, "visits")
    source = str(observed.get("source") or "caller-supplied export")
    out: dict[str, dict] = {}

    not_live = ("no listing is live (none carries an Etsy listing id); impressions, clicks "
                "and favourites are facts about a listing somebody can see")

    # 1. qualified impressions
    if not live:
        out["qualified_impressions"] = _unmeasured(not_live, "a live listing and its Stats")
    elif impressions is None:
        out["qualified_impressions"] = _unmeasured(
            "no impression count was supplied", "the Etsy Stats export for the period")
    else:
        out["qualified_impressions"] = _measured(impressions, source)

    # 2. CTR
    if not live:
        out["ctr"] = _unmeasured(not_live, "a live listing, impressions and visits")
    elif impressions is None or visits is None:
        out["ctr"] = _unmeasured("impressions and visits were not both supplied",
                                 "both counts from the Stats export")
    elif impressions < MEASURED_SAMPLE:
        out["ctr"] = _unmeasured(
            f"{impressions} impressions against a floor of {MEASURED_SAMPLE}: a click-through "
            f"rate over fewer is a hopeful one", f"{MEASURED_SAMPLE - impressions} more "
            f"impressions")
    else:
        if visits > impressions:
            raise LeadingRefused("more visits than impressions is a counting fault")
        out["ctr"] = _measured(round(visits / impressions, 5), source,
                               impressions=impressions, visits=visits)

    # 3. favourites and cart signals, where available
    favourites = _count(observed, "favourites")
    carts = _count(observed, "carts")
    if not live:
        out["favourites_and_cart"] = _unmeasured(not_live, "a live listing")
    elif favourites is None and carts is None:
        out["favourites_and_cart"] = _unmeasured(
            "neither favourites nor cart adds were supplied; the platform shows them only "
            "where it chooses to", "the favourites and cart counts, where Etsy exposes them")
    else:
        out["favourites_and_cart"] = _measured(
            {"favourites": favourites, "carts": carts}, source)

    # 4. conversion: orders over visits
    if visits is None:
        out["conversion"] = _unmeasured("no visit count was supplied",
                                        "visits from the Stats export, and orders")
    elif visits < MEASURED_SAMPLE:
        out["conversion"] = _unmeasured(
            f"{visits} visits against a floor of {MEASURED_SAMPLE}",
            f"{MEASURED_SAMPLE - visits} more visits")
    else:
        out["conversion"] = _measured(round(orders / visits, 5),
                                      f"orders from the database over visits from {source}",
                                      orders=orders, visits=visits)

    # 5. bundle attach
    if orders < MIN_ORDERS_FOR_REFUND_RATE:
        out["bundle_attach"] = _unmeasured(
            f"{orders} order(s) against a floor of {MIN_ORDERS_FOR_REFUND_RATE}; an attach "
            f"rate over fewer is a few people's baskets", "orders")
    else:
        out["bundle_attach"] = _measured(round(facts["bundle_or_cross_sell"] / orders, 4),
                                         "orders table (bundle products and cross-sells)",
                                         orders=orders)

    # 6. email and content traffic; 7. creator traffic
    for key, fields, needs in (
            ("email_and_content_traffic", ("email_visits", "content_visits"),
             "visits by channel from an analytics source that reports email and content"),
            ("creator_traffic", ("creator_visits",),
             "visits attributed to creator links, from the Stats traffic-source export")):
        values = {f: _count(observed, f) for f in fields}
        if all(v is None for v in values.values()):
            out[key] = _unmeasured("no traffic by this channel was supplied", needs)
        else:
            out[key] = _measured(values, source)

    # 8. search trend direction, only with its provenance
    trend = observed.get("search_trend")
    if not trend:
        out["search_trend_direction"] = _unmeasured(
            "no search trend reading was supplied; a direction without the population and "
            "window it describes is a rumour (see radar.provenance)",
            "a trend reading with its source, population and window")
    else:
        direction = str(trend.get("direction") or "")
        if direction not in TREND_DIRECTIONS or not trend.get("source"):
            raise LeadingRefused(f"a search trend needs a direction in {TREND_DIRECTIONS} and "
                                 f"the source it was read from")
        out["search_trend_direction"] = _measured(direction, str(trend["source"]),
                                                  window=trend.get("window"))

    # 9. support defects: cases per order
    if orders < MIN_ORDERS_FOR_REFUND_RATE:
        out["support_defects"] = _unmeasured(
            f"{orders} order(s) against a floor of {MIN_ORDERS_FOR_REFUND_RATE}; "
            f"{facts['support_cases']} support case(s) on record are counted but a rate per "
            f"order over this few is a rumour", "orders")
    else:
        out["support_defects"] = _measured(
            round(facts["support_cases"] / orders, 4), "support_cases and orders tables",
            cases=facts["support_cases"], escalated=facts["escalated_cases"],
            refunded=facts["refunded"], orders=orders)

    # 10. release velocity: certified releases in the window. Internal, so measured today.
    out["release_velocity"] = _measured(
        facts["releases_in_window"], "pattern_versions (certified)",
        window_days=VELOCITY_WINDOW_DAYS, certified_total=facts["certified_releases"])

    measured = [k for k in INDICATORS if out[k]["status"] == MEASURED]
    if orders == 0:
        success = {"claimable": False,
                   "why": ("no orders exist. Leading indicators are evidence that something "
                           "may sell, never that it has; success is not declared from them "
                           "(#263)")}
    else:
        success = {"claimable": True,
                   "why": (f"{orders} order(s) exist, so success is a question about orders "
                           f"and contribution (scale.runrate), and the leading indicators are "
                           f"context for it rather than the answer")}
    return {
        "indicators": {k: out[k] for k in INDICATORS},
        "measured": measured,
        "unmeasured": [k for k in INDICATORS if k not in measured],
        "facts": facts,
        "success": success,
        "note": ("ten leading indicators, each measured with its source or UNMEASURED with its "
                 "reason; none defaults to zero, and success is refused without orders "
                 "(#263)"),
    }
