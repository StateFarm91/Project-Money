"""The culture radar: recording signals, remembering them, and knowing when to stop.

Requirements 133, 140, 144, 145, 147. The radar's hardest requirement is not finding signals —
it is #144, remembering them, because the value of a culture radar is almost entirely in its
second and third years. A radar with no memory rediscovers that retro Halloween recurs every
autumn, every autumn, and it pays full research cost each time to learn something it already
knew.

**A signal is recorded with its protected tokens declared.** Not discovered downstream. The
routing decision is made once, at observation, and every later step is checked against it.

**Momentum is a series, not a number.** #140 asks whether cultural interest leads or lags Etsy
demand, and #145 asks when a window has closed. Both are questions about a curve, so the radar
stores observations over time and derives direction from them rather than storing a mood.

**The exit is as important as the entry (#145).** A trend that is still being produced into
after the window closed costs twice: the work, and the capacity that should have gone to the
next wave. Four independent exit conditions, any one of which is sufficient, because a trend
dies in several different ways and waiting for all of them is waiting.

**No feed is not a quiet radar.** With nothing connected, `sweep()` reports that it has no
source. A culture radar that returns an empty list of trends is indistinguishable from a world
with no culture in it, and the second reading is the one an absent owner would take.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .rights import DIRECT, ORIGINAL, Basis, ProtectedToken, route

# Where a signal came from (#133's own list).
DOMAINS: tuple[str, ...] = (
    "film", "television", "meme", "nostalgia_era", "seasonal_tradition", "viral_aesthetic",
    "music", "sports_culture", "celebrity_aesthetic", "internet_moment")

# Signal lifecycle. `exited` is a real state with a recorded reason, not a deletion, because
# the reason is the thing worth having next year.
OBSERVED = "observed"
TRANSLATED = "translated"
IN_PRODUCTION = "in_production"
LAUNCHED = "launched"
EXITED = "exited"

STATES: tuple[str, ...] = (OBSERVED, TRANSLATED, IN_PRODUCTION, LAUNCHED, EXITED)

# Exit conditions (#145). Any one is sufficient: a trend dies in several different ways and
# waiting for all four is how capacity stays committed to last month's wave.
DECLINE_THRESHOLD = -0.25       # interest down a quarter from its peak
COPYCAT_DENSITY = 3.0           # competitor listings tripled since the baseline observation
MIN_CONVERSION = 0.01           # measured, never assumed
MIN_WINDOW_DAYS = 21            # below this, a customer cannot finish anything substantial


class RadarRefused(Exception):
    """A signal that cannot be recorded, or an exit with no evidence."""


@dataclass(frozen=True)
class Signal:
    key: str
    topic: str
    domain: str
    tokens: tuple[ProtectedToken, ...] = ()
    sources: tuple[str, ...] = ()
    first_seen: str = ""

    def __post_init__(self) -> None:
        if self.domain not in DOMAINS:
            raise RadarRefused(
                f"{self.domain!r} is not a culture domain: {sorted(DOMAINS)}")
        if not self.sources:
            raise RadarRefused(
                f"{self.key}: a signal with no source is a hunch. Next year's agent needs to "
                f"know where this was seen to judge whether it means anything (#144)")


def record(db, signal: Signal, *, basis: Basis | None = None) -> dict:
    """Record a signal and decide, once, what it is allowed to become."""
    from sqlalchemy import select

    from ..core.models import CultureSignal

    routing = route(list(signal.tokens), basis=basis)
    with db.session() as s:
        row = s.scalar(select(CultureSignal).where(CultureSignal.key == signal.key))
        if row is None:
            row = CultureSignal(key=signal.key, first_seen=signal.first_seen
                                or date.today().isoformat())
            s.add(row)
        row.topic = signal.topic
        row.domain = signal.domain
        row.lane = routing.lane
        row.protected_tokens = [t.to_dict() for t in signal.tokens]
        row.basis = routing.basis.to_dict() if routing.basis else None
        row.sources = list(signal.sources)
        row.updated_at = datetime.now(timezone.utc)
        s.flush()
        signal_id = row.id
    return {"id": signal_id, "key": signal.key, "routing": routing.to_dict()}


def observe(db, signal_key: str, *, channel: str, interest: float,
            competitor_listings: int = 0, observed_on: str = "", source: str = "") -> int:
    """Record one momentum reading. A series, because direction is the useful part."""
    from ..core.models import CultureObservation

    if not 0.0 <= interest <= 1.0:
        raise RadarRefused(f"interest {interest!r} is outside 0.0-1.0")
    with db.session() as s:
        row = CultureObservation(
            signal_key=signal_key, channel=channel, interest=float(interest),
            competitor_listings=int(competitor_listings),
            observed_on=observed_on or date.today().isoformat(), source=source)
        s.add(row)
        s.flush()
        return row.id


def _series(db, signal_key: str) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import CultureObservation

    with db.session() as s:
        rows = list(s.scalars(select(CultureObservation).where(
            CultureObservation.signal_key == signal_key).order_by(
                CultureObservation.observed_on, CultureObservation.id)))
        return [{"on": r.observed_on, "channel": r.channel, "interest": r.interest,
                 "listings": r.competitor_listings} for r in rows]


def momentum(db, signal_key: str) -> dict:
    """Direction and distance from peak, from the readings rather than from a feeling."""
    series = _series(db, signal_key)
    if len(series) < 2:
        return {"measurable": False, "observations": len(series),
                "reason": ("one reading is a level, not a momentum. Direction needs two "
                           "points and the whole question here is direction")}
    peak = max(p["interest"] for p in series)
    latest = series[-1]["interest"]
    first_listings = next((p["listings"] for p in series if p["listings"]), 0)
    latest_listings = series[-1]["listings"]
    return {
        "measurable": True,
        "observations": len(series),
        "peak": peak,
        "latest": latest,
        "from_peak": round((latest - peak) / peak, 3) if peak else 0.0,
        "direction": ("rising" if latest > series[-2]["interest"]
                      else "falling" if latest < series[-2]["interest"] else "flat"),
        "copycat_multiple": (round(latest_listings / first_listings, 2)
                             if first_listings else None),
        "series": series,
    }


# ---------------------------------------------------------------------------
# Lead and lag (#140)


def lead_lag(db, signal_key: str, *, culture_channel: str = "search",
             demand_channel: str = "etsy") -> dict:
    """Does cultural interest move before Etsy demand, or after it?

    The whole commercial value of a culture radar rests on the answer being *before*. If a
    topic's cultural peak arrives after its marketplace peak, the radar is reporting the news
    and entering on it is entering at saturation — which is the failure #140 exists to name,
    and it is invisible without both series.
    """
    series = _series(db, signal_key)
    culture = [p for p in series if p["channel"] == culture_channel]
    demand = [p for p in series if p["channel"] == demand_channel]
    if len(culture) < 2 or len(demand) < 2:
        return {"measurable": False,
                "reason": (f"lead-lag needs both series: {len(culture)} {culture_channel} "
                           f"and {len(demand)} {demand_channel} readings. One series cannot "
                           f"lead anything"),
                "culture_readings": len(culture), "demand_readings": len(demand)}

    def peak_date(points):
        top = max(points, key=lambda p: p["interest"])
        return date.fromisoformat(top["on"])

    culture_peak, demand_peak = peak_date(culture), peak_date(demand)
    days = (demand_peak - culture_peak).days
    return {
        "measurable": True,
        "culture_peak": culture_peak.isoformat(),
        "demand_peak": demand_peak.isoformat(),
        "lead_days": days,
        "is_a_leading_indicator": days > 0,
        "note": (f"cultural interest peaked {days} days before marketplace demand, so this "
                 f"channel is worth entering on"
                 if days > 0 else
                 f"cultural interest peaked {abs(days)} days *after* demand: on this topic "
                 f"the radar is reporting the news, and entering on it is entering at "
                 f"saturation (#140)"),
    }


# ---------------------------------------------------------------------------
# Saturation and exit (#145)


def exit_check(db, signal_key: str, *, days_to_event: int | None = None,
               conversion: float | None = None) -> dict:
    """Should capacity move to the next wave? Any one condition is sufficient.

    Conversion is passed rather than assumed, and `None` means unmeasured rather than bad:
    this company has no conversion data, and a check that read that as failure would exit
    every trend on day one.
    """
    reasons: list[dict] = []
    m = momentum(db, signal_key)

    if m["measurable"] and m["from_peak"] <= DECLINE_THRESHOLD:
        reasons.append({"condition": "declining_interest", "from_peak": m["from_peak"],
                        "threshold": DECLINE_THRESHOLD})
    if m.get("copycat_multiple") and m["copycat_multiple"] >= COPYCAT_DENSITY:
        reasons.append({"condition": "copycat_density",
                        "multiple": m["copycat_multiple"], "threshold": COPYCAT_DENSITY})
    if conversion is not None and conversion < MIN_CONVERSION:
        reasons.append({"condition": "poor_conversion", "conversion": conversion,
                        "threshold": MIN_CONVERSION})
    if days_to_event is not None and days_to_event < MIN_WINDOW_DAYS:
        reasons.append({"condition": "insufficient_make_time", "days": days_to_event,
                        "threshold": MIN_WINDOW_DAYS})

    return {
        "signal": signal_key,
        "should_exit": bool(reasons),
        "reasons": reasons,
        "momentum": m,
        "unmeasured": [k for k, v in (("conversion", conversion),
                                      ("days_to_event", days_to_event)) if v is None],
        "note": ("Any one condition is sufficient. A trend dies in several different ways "
                 "and waiting for all four is how capacity stays committed to last month's "
                 "wave (#145)." if reasons else
                 "no exit condition is met; the window is still open on the evidence there is"),
    }


def exit_signal(db, signal_key: str, reason: str, *, lesson: str = "") -> dict:
    """Record the exit, keeping the reason. The reason is the asset (#144, #145)."""
    from sqlalchemy import select

    from ..core.models import CultureSignal

    if len(reason.strip()) < 20:
        raise RadarRefused(
            "an exit with no recorded reason teaches next year's agent nothing, which makes "
            "this the same amount of work again in twelve months")
    with db.session() as s:
        row = s.scalar(select(CultureSignal).where(CultureSignal.key == signal_key))
        if row is None:
            raise RadarRefused(f"no signal {signal_key!r}")
        row.state = EXITED
        row.exit_reason = reason.strip()
        row.outcome = {**(row.outcome or {}), "lesson": lesson.strip(),
                       "exited_on": date.today().isoformat()}
        row.updated_at = datetime.now(timezone.utc)
    return {"signal": signal_key, "state": EXITED, "reason": reason.strip()}


# ---------------------------------------------------------------------------
# Memory (#144) and the honest empty state (#133)


def memory(db, *, recurring_within_days: int = 400) -> dict:
    """What the radar knows, as distinct from what it can currently see.

    The recurrence answer is the one that compounds: a signal first seen roughly a year ago
    and seen again is an annual territory, and knowing that is the difference between
    researching retro Halloween once and researching it every autumn forever.
    """
    from sqlalchemy import select

    from ..core.models import CultureSignal

    with db.session() as s:
        rows = list(s.scalars(select(CultureSignal)))
        signals = [{"key": r.key, "topic": r.topic, "domain": r.domain, "lane": r.lane,
                    "state": r.state, "first_seen": r.first_seen,
                    "protected": len(r.protected_tokens or []),
                    "exit_reason": r.exit_reason,
                    "lesson": (r.outcome or {}).get("lesson", "")} for r in rows]

    today = date.today()
    recurring = []
    for sig in signals:
        if not sig["first_seen"]:
            continue
        age = (today - date.fromisoformat(sig["first_seen"])).days
        if 300 <= age <= recurring_within_days:
            recurring.append(sig["key"])

    by_lane = {ORIGINAL: 0, DIRECT: 0}
    for sig in signals:
        by_lane[sig["lane"]] = by_lane.get(sig["lane"], 0) + 1

    return {
        "signals": len(signals),
        "by_state": {st: sum(1 for x in signals if x["state"] == st) for st in STATES},
        "by_lane": by_lane,
        "recurring_annually": recurring,
        "exited_with_a_lesson": [x["key"] for x in signals if x["exit_reason"]],
        "all": signals,
        "note": ("The value of a culture radar is almost entirely in its second year. A "
                 "radar with no memory rediscovers that retro Halloween recurs every autumn, "
                 "every autumn, at full research cost (#144)."),
    }


def sweep(db, *, feeds: list | None = None) -> dict:
    """What the radar can currently see, and an honest answer when that is nothing.

    An empty list of trends is indistinguishable from a world with no culture in it, and the
    second reading is the one an absent owner would take from a dashboard.
    """
    if not feeds:
        return {
            "scanned": False,
            "reason": ("no culture feed is connected, so nothing was scanned. This is not a "
                       "quiet week: a radar with no source reporting no trends looks exactly "
                       "like a radar with a source and nothing to report"),
            "domains": list(DOMAINS),
            "unmet_requirements": [133, 140],
            "what_would_connect_it": ("a search-interest source and a marketplace demand "
                                      "source, so the lead-lag model has two series rather "
                                      "than one"),
            "memory": memory(db),
        }
    return {"scanned": True, "feeds": [str(f) for f in feeds], "memory": memory(db)}


def ages_out(first_seen: str, *, today: date | None = None) -> timedelta:
    today = today or date.today()
    return timedelta(days=(today - date.fromisoformat(first_seen)).days)
