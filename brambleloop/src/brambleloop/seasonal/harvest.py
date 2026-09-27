"""The post-season learning harvest, and the timing it hands to next year's calendar (#298).

Requirement 298: after every major event, analyse which concepts, palettes, categories,
thumbnails, search terms, prices, bundles and channels actually worked, and feed the evidence
into next year's calendar immediately -- including when demand began, peaked and decayed, and
the actual make-time and support signals.

The machinery runs on every passed event and refuses honestly until a season of data exists:

* **An event that has not passed is refused.** Harvesting Christmas in September would be a
  harvest of the plan.
* **A passed event with too few orders is refused per event**, stored with its reason, so
  "Halloween taught nothing" and "nobody looked at Halloween" are different rows.
* **Timing is read from what was recorded** -- the event's own orders by week, and where
  present the season-tagged price observations and event-tagged culture observations -- each
  with its own minimum, and each absent rather than guessed when it is short.

`timing_adjustments(db, event)` is the seam next year's calendar reads. It returns the learned
onset/peak/decay for the most recent measured harvest, and `adjusted_assumptions` turns that
into a lead-time `Assumptions` whose planning buffers are *raised* where buyers were observed
buying earlier than the chain assumed. It never lowers one: one season saying buyers came late
is not evidence enough to launch later, and a shortened buffer is how a window gets missed.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

MEASURED = "measured"
UNMEASURED = "UNMEASURED"
REFUSED = "refused"
NOT_PASSED = "not_passed"

# The window a season is read over: long enough to see a Christmas blanket's onset in
# September, and a short tail to see decay after the day.
SEASON_LEAD_DAYS = 150
SEASON_TAIL_DAYS = 21
# Orders attributed to the event before any harvest is written (the same floor as a refund
# rate, commerce.benchmarks.MIN_ORDERS_FOR_REFUND_RATE).
MIN_EVENT_ORDERS = 20
# Orders in one group (a palette, a channel) before that group is compared.
MIN_GROUP_ORDERS = 5
# Weekly points with a nonzero reading before a curve is read for onset, peak and decay.
MIN_SIGNAL_POINTS = 4
# A week is "in demand" at this share of the peak week.
ONSET_SHARE = 0.25

PRICE_BANDS: tuple[tuple[float, str], ...] = ((6.0, "under_6"), (10.0, "6_to_10"),
                                              (15.0, "10_to_15"), (25.0, "15_to_25"),
                                              (float("inf"), "25_plus"))


class HarvestRefused(ValueError):
    """An event nobody named."""


def _event(name: str):
    from ..radar.market import SEASONAL_EVENTS

    event = next((e for e in SEASONAL_EVENTS if e.name == name), None)
    if event is None:
        raise HarvestRefused(f"{name!r} is not a seasonal event: "
                             f"{[e.name for e in SEASONAL_EVENTS]}")
    return event


def _shift(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # pragma: no cover - 29 February
        return d + timedelta(days=365 * years)


def last_occurrence(event_date: date, today: date) -> date:
    """The most recent occurrence strictly before today."""
    when = event_date
    while when >= today:
        when = _shift(when, -1)
    while _shift(when, 1) < today:
        when = _shift(when, 1)
    return when


def _band(price: float) -> str:
    return next(label for ceiling, label in PRICE_BANDS if price < ceiling)


def _curve(points: dict[int, float], *, what: str) -> dict:
    """Onset, peak and decay from weekly readings keyed by days-before-event (week start)."""
    nonzero = {k: v for k, v in points.items() if v > 0}
    if len(nonzero) < MIN_SIGNAL_POINTS:
        return {"status": UNMEASURED,
                "why": (f"{len(nonzero)} nonzero weekly reading(s) of {what} against a floor "
                        f"of {MIN_SIGNAL_POINTS}"),
                "needs": f"n >= {MIN_SIGNAL_POINTS} weekly readings"}
    ordered = sorted(points.items(), key=lambda kv: -kv[0])   # earliest (most days before) first
    peak_at, peak = max(ordered, key=lambda kv: (kv[1], kv[0]))
    threshold = peak * ONSET_SHARE
    began = next(k for k, v in ordered if v >= threshold)
    after = [k for k, v in ordered if k < peak_at and v < threshold]
    return {"status": MEASURED, "source": what,
            "demand_began_days_before": began, "peak_days_before": peak_at,
            "decayed_days_before": after[0] if after else None,
            "decay_observed": bool(after), "weeks": len(points), "peak_value": peak,
            "onset_share": ONSET_SHARE}


def _weekly(pairs: list[tuple[date, float]], occurrence: date) -> dict[int, float]:
    """Bucket readings into weeks keyed by the week's days-before-event (negative = after)."""
    # Every week of the window is present, so a week nobody bought in reads as zero and
    # decay can be seen; a missing bucket would hide exactly the weeks that show it.
    out: dict[int, float] = {w: 0.0 for w in range((-SEASON_TAIL_DAYS // 7) * 7,
                                                   SEASON_LEAD_DAYS + 1, 7)}
    for when, value in pairs:
        days = (occurrence - when).days
        week = (days // 7) * 7
        out[week] = out.get(week, 0.0) + float(value)
    return out


def _groups(orders: list[dict], key: str) -> dict:
    groups: dict[str, list[dict]] = {}
    for o in orders:
        groups.setdefault(str(o[key] or "unknown"), []).append(o)
    out = {}
    for value, rows in sorted(groups.items()):
        n = len(rows)
        entry = {"orders": n, "revenue_cad": round(sum(r["revenue"] for r in rows), 2),
                 "contribution_cad": round(sum(r["contribution"] for r in rows), 2)}
        if n < MIN_GROUP_ORDERS:
            entry.update({"status": UNMEASURED,
                          "why": f"{n} order(s) against a floor of {MIN_GROUP_ORDERS}"})
        else:
            entry.update({"status": MEASURED,
                          "contribution_per_order": round(entry["contribution_cad"] / n, 2)})
        out[value] = entry
    return out


def harvest(db, event_name: str, *, today: date | None = None,
            occurrence: date | None = None, persist: bool = True) -> dict:
    """What one passed occurrence of one event taught, or why it taught nothing."""
    from sqlalchemy import select

    from ..core.models import (CultureObservation, ListingAsset, Order, PriceObservation,
                               SupportCase)
    from ..creative.audit import catalogue_concepts
    from ..creative.style_learning import tag_asset
    from .leadtime import occasion_for

    event = _event(event_name)
    today = today or date.today()
    occurrence = occurrence or last_occurrence(event.event_date, today)
    base = {"event": event.name, "occurrence": occurrence.isoformat(),
            "today": today.isoformat()}
    if occurrence >= today:
        return {**base, "status": NOT_PASSED,
                "why": (f"{event.name} {occurrence.isoformat()} has not passed; a harvest "
                        f"before the event is a harvest of the plan")}

    start = occurrence - timedelta(days=SEASON_LEAD_DAYS)
    end = occurrence + timedelta(days=SEASON_TAIL_DAYS)
    lo = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    hi = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
    concepts = {c.key: c for c in catalogue_concepts()}

    with db.session() as s:
        orders = []
        for o in s.scalars(select(Order).where(Order.at >= lo, Order.at <= hi,
                                               Order.refunded == False)):  # noqa: E712
            season = (o.detail or {}).get("season") or occasion_for(o.product_slug)
            if season != event.name:
                continue
            at = o.at if o.at.tzinfo else o.at.replace(tzinfo=timezone.utc)
            concept = concepts.get(o.product_slug) or next(
                (c for k, c in concepts.items() if o.product_slug.startswith(k)), None)
            orders.append({
                "slug": o.product_slug, "on": at.date(), "revenue": o.revenue_cad or 0.0,
                "contribution": o.contribution_cad or 0.0, "category": o.category,
                "search_term": o.search_term, "channel": o.acquisition_source,
                "price_band": _band(o.price_cad or 0.0),
                "bundle": ("bundle" if ("bundle" in o.product_slug or o.cross_sell_of)
                           else "single"),
                "concept": (f"{concept.form}/{concept.motif}" if concept else o.product_slug),
                "palette": concept.palette_story if concept else None})
        slugs = sorted({o["slug"] for o in orders})
        heroes = {}
        for a in s.scalars(select(ListingAsset).where(ListingAsset.position == 1)):
            if a.product_slug in slugs:
                heroes[a.product_slug] = tag_asset(a)["style"]
        support = s.scalars(select(SupportCase).where(
            SupportCase.at >= lo, SupportCase.at <= hi)).all()
        support = [c for c in support if c.product_slug in slugs]
        prices = [(p.from_date, p.visits) for p in s.scalars(select(PriceObservation).where(
            PriceObservation.season == event.name)) if p.from_date]
        culture = [(c.observed_on, c.interest) for c in s.scalars(select(CultureObservation))
                   if (c.detail or {}).get("event") == event.name and c.observed_on]

    if len(orders) < MIN_EVENT_ORDERS:
        out = {**base, "status": REFUSED,
               "why": (f"{len(orders)} order(s) attributed to {event.name} "
                       f"{occurrence.isoformat()} between {start} and {end}, against a floor "
                       f"of {MIN_EVENT_ORDERS}. Nothing is learned from a season with no "
                       f"buyers, and nothing is written to next year's calendar"),
               "needs": f"n >= {MIN_EVENT_ORDERS} orders attributed to the event"}
        if persist:
            _store(db, out, timing={})
        return out

    for o in orders:
        o["thumbnail"] = heroes.get(o["slug"], "untagged")

    def in_window(pairs):
        out = []
        for raw, value in pairs:
            try:
                when = date.fromisoformat(str(raw)[:10])
            except ValueError:
                continue
            if start <= when <= end:
                out.append((when, value))
        return out

    timing = {
        "orders": _curve(_weekly([(o["on"], 1) for o in orders], occurrence),
                         what="event orders"),
        "price_observations": (_curve(_weekly(in_window(prices), occurrence),
                                      what="season-tagged visits") if prices else
                               {"status": UNMEASURED, "why": "no season-tagged price "
                                "observation recorded", "needs": "price_observations rows"}),
        "culture": (_curve(_weekly(in_window(culture), occurrence),
                           what="event-tagged culture interest") if culture else
                    {"status": UNMEASURED, "why": "no culture observation tagged with this "
                     "event", "needs": "culture_observations with detail.event"}),
    }
    n = len(orders)
    out = {
        **base, "status": MEASURED, "orders": n,
        "revenue_cad": round(sum(o["revenue"] for o in orders), 2),
        "contribution_cad": round(sum(o["contribution"] for o in orders), 2),
        "worked": {dim: _groups(orders, key) for dim, key in (
            ("concepts", "concept"), ("palettes", "palette"), ("categories", "category"),
            ("thumbnails", "thumbnail"), ("search_terms", "search_term"),
            ("prices", "price_band"), ("bundles", "bundle"), ("channels", "channel"))},
        "timing": timing,
        "support": {"cases": len(support), "per_order": round(len(support) / n, 4), "n": n,
                    "make_time_mentions": sum(
                        1 for c in support
                        if any(w in (c.question or "").lower()
                               for w in ("how long", "hours", "in time", "finish")))},
        "minimums": {"event_orders": MIN_EVENT_ORDERS, "group_orders": MIN_GROUP_ORDERS,
                     "signal_points": MIN_SIGNAL_POINTS},
    }
    if persist:
        _store(db, out, timing=_learned(timing))
    return out


def _learned(timing: dict) -> dict:
    """The timing next year reads: orders first, then the market signals."""
    for source in ("orders", "price_observations", "culture"):
        t = timing.get(source) or {}
        if t.get("status") == MEASURED:
            return {k: t[k] for k in ("source", "demand_began_days_before",
                                      "peak_days_before", "decayed_days_before",
                                      "decay_observed")}
    return {}


def _store(db, out: dict, *, timing: dict) -> None:
    from sqlalchemy import select

    from ..core.models import SeasonHarvest

    with db.session() as s:
        row = s.scalar(select(SeasonHarvest).where(SeasonHarvest.event == out["event"],
                                                   SeasonHarvest.occurrence == out["occurrence"]))
        if row is None:
            row = SeasonHarvest(event=out["event"], occurrence=out["occurrence"],
                                status=out["status"])
            s.add(row)
        row.status = out["status"]
        row.reason = out.get("why", "")
        row.result = {k: v for k, v in out.items() if k not in ("event", "occurrence")}
        row.timing = timing
        row.at = datetime.now(timezone.utc)


def harvest_due(db, *, today: date | None = None) -> dict:
    """The daily pass: harvest every event's most recent passed occurrence not yet measured."""
    from sqlalchemy import select

    from ..core.models import SeasonHarvest
    from ..radar.market import SEASONAL_EVENTS

    today = today or date.today()
    ran, skipped = [], []
    for event in SEASONAL_EVENTS:
        occurrence = last_occurrence(event.event_date, today)
        with db.session() as s:
            done = s.scalar(select(SeasonHarvest).where(
                SeasonHarvest.event == event.name,
                SeasonHarvest.occurrence == occurrence.isoformat(),
                SeasonHarvest.status == MEASURED))
        if done is not None:
            skipped.append({"event": event.name, "occurrence": occurrence.isoformat(),
                            "why": "already harvested"})
            continue
        out = harvest(db, event.name, today=today, occurrence=occurrence)
        ran.append({"event": event.name, "occurrence": out["occurrence"],
                    "status": out["status"], "why": out.get("why", "")})
    return {"today": today.isoformat(), "ran": ran, "skipped": skipped,
            "measured": [r["event"] for r in ran if r["status"] == MEASURED]}


def timing_adjustments(db, event: str) -> dict:
    """The learned timing for one event, for next year's calendar and lead-time chain."""
    from sqlalchemy import select

    from ..core.models import SeasonHarvest

    _event(event)
    with db.session() as s:
        rows = list(s.scalars(select(SeasonHarvest).where(
            SeasonHarvest.event == event).order_by(SeasonHarvest.occurrence.desc())))
    measured = next((r for r in rows if r.status == MEASURED and r.timing), None)
    if measured is None:
        latest = rows[0] if rows else None
        return {"event": event, "status": UNMEASURED,
                "why": (latest.reason if latest is not None and latest.reason else
                        "no harvest of this event has measured timing; the calendar keeps "
                        "its assumed lead times"),
                "needs": f"a harvest with n >= {MIN_EVENT_ORDERS} orders"}
    return {"event": event, "status": MEASURED, "occurrence": measured.occurrence,
            **measured.timing}


def adjusted_assumptions(db, event: str, assumptions=None):
    """Lead-time assumptions with planning buffers raised to the observed buying onset.

    The chain assumes buyers purchase `completion + make + planning` days before the event.
    Where the harvest saw demand begin earlier, each lane's planning buffer is raised by the
    gap, using the lane's smallest make time (the conservative case). Never lowered.
    """
    from .leadtime import DEFAULT, LANE_MAX_HOURS, LANES, effective_make_days

    assumptions = assumptions or DEFAULT
    timing = timing_adjustments(db, event)
    if timing["status"] != MEASURED:
        return assumptions
    onset = int(timing["demand_began_days_before"])
    raised = dict(assumptions.planning_buffer_days)
    changed = False
    for i, lane in enumerate(LANES):
        floor_hours = 0.0 if i == 0 else LANE_MAX_HOURS[LANES[i - 1]]
        make = effective_make_days(floor_hours, "intermediate", assumptions)
        needed = onset - assumptions.completion_buffer_days - make
        if needed > raised[lane]:
            raised[lane] = needed
            changed = True
    return assumptions.measured(planning_buffer_days=raised) if changed else assumptions
