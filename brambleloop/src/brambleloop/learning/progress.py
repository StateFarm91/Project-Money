"""Proof of improvement, per learning loop, for readback and Mission Control (ENG-LEARN).

For each loop this shows:
- the loop's metric over rolling windows;
- the trend between the earliest and latest measured window;
- which lessons are active, and which a department has actually acted on (`bus.acted_on`);
- before/after comparisons for every promotion or demotion.

The rules:
- A window with fewer than `stats.TREND_MIN_N` observations is UNKNOWN.
- A trend is UNKNOWN unless two measured windows exist.
- "Improving" needs one-sided p < 0.05; anything else is `no_significant_change`.
- A lesson that exists but changed no decision is counted as published, never as applied.
- A loop with no observations says so.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import pattern_lessons, stats
from .store import DerivedLesson, ImageObservation, ensure_tables

WINDOW_DAYS = 14
WINDOWS = 6


def _aware(v):
    if v is not None and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


def image_trend(db, *, now: datetime | None = None, window_days: int = WINDOW_DAYS,
                windows: int = WINDOWS) -> dict:
    """First-pass QA rate (attempt-1 frames accepted) over rolling windows."""
    from sqlalchemy import select

    ensure_tables(db)
    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        rows = [(_aware(o.at), o.outcome) for o in s.scalars(select(ImageObservation).where(
            ImageObservation.attempt == 1,
            ImageObservation.outcome.in_(("accepted", "rejected"))))]
    series = []
    for w in range(windows - 1, -1, -1):
        hi = now - timedelta(days=w * window_days)
        lo = hi - timedelta(days=window_days)
        ins = [o for at, o in rows if lo < at <= hi]
        series.append({"from": lo.date().isoformat(), "to": hi.date().isoformat(),
                       **stats.rate(sum(1 for o in ins if o == "accepted"), len(ins))})
    return {"metric": "first_pass_qa_rate", "series": series,
            "trend": pattern_lessons.trend(series),
            "all_time": stats.rate(sum(1 for _, o in rows if o == "accepted"), len(rows))}


def _lessons(db, loop: str) -> dict:
    from sqlalchemy import select

    with db.session() as s:
        rows = list(s.scalars(select(DerivedLesson).where(DerivedLesson.loop == loop)))
        return {"active": sum(1 for r in rows if r.active),
                "inactive": sum(1 for r in rows if not r.active),
                "statements": [r.statement for r in rows if r.active][:10]}


def promotions(db, *, limit: int = 20) -> list[dict]:
    """Before/after for every promotion and demotion, from its own recorded evidence."""
    from sqlalchemy import select

    from .store import Decision

    ensure_tables(db)
    out = []
    with db.session() as s:
        for d in s.scalars(select(Decision).where(Decision.kind.in_(("promote", "demote")))
                           .order_by(Decision.id.desc()).limit(limit)):
            ev = d.evidence or {}
            if d.kind == "promote":
                before = ev.get("champion") or {}
                after = ev.get("challenger") or {}
            else:
                before = ev.get("baseline") or {}
                after = ev.get("after") or {}
            out.append({"at": _aware(d.at).isoformat(), "scope": d.scope, "kind": d.kind,
                        "arm_id": d.arm_id, "from_arm_id": d.from_arm_id,
                        "basis": ev.get("basis"), "why": ev.get("why"),
                        "before": {"k": before.get("k"), "n": before.get("n")},
                        "after": {"k": after.get("k"), "n": after.get("n")}})
    return out


def summary(db, *, now: datetime | None = None) -> dict:
    """Everything readback and Mission Control show. Pure reads."""
    ensure_tables(db)
    now = now or datetime.now(timezone.utc)
    applied = pattern_lessons.lessons_applied(db)
    fp = pattern_lessons.first_pass_by_family(db, now=now)
    from .commerce_lessons import readings

    real = readings(db)
    return {
        "as_of": now.isoformat(),
        "image": {**image_trend(db, now=now), "lessons": _lessons(db, "image"),
                  "lessons_applied": applied.get("image", {"published": 0, "acted_on": 0}),
                  "promotions": promotions(db)},
        "pattern": {"metric": fp["metric"], "families": fp["families"],
                    "all_time": (fp["families"].get("ALL") or {}).get(
                        "all_time", stats.rate(0, 0)),
                    "trend": (fp["families"].get("ALL") or {}).get(
                        "trend", {"status": stats.UNKNOWN, "why": "no designs observed"}),
                    "lessons": _lessons(db, "pattern"),
                    "lessons_applied": applied.get("pattern", {"published": 0, "acted_on": 0})},
        "commerce": {"real_listings": len(real),
                     "real_visits": sum(r["visits"] for r in real.values()),
                     "real_orders": sum(r["orders"] for r in real.values()),
                     "status": "MEASURED" if real else "UNMEASURED",
                     "lessons": _lessons(db, "commerce"),
                     "lessons_applied": applied.get("commerce",
                                                    {"published": 0, "acted_on": 0})},
    }


def readback(db, *, now: datetime | None = None) -> dict:
    """The projected, payload-free readback row: counts, rates and statuses only."""
    s = summary(db, now=now)

    def last(series):
        m = [w for w in series if w.get("status") == "MEASURED"]
        return m[-1] if m else {"status": stats.UNKNOWN}

    def rate_of(w):
        return w.get("rate") if w.get("status") == "MEASURED" else stats.UNKNOWN

    return {
        "image": {"first_pass_latest": rate_of(last(s["image"]["series"])),
                  "trend": s["image"]["trend"].get("verdict", s["image"]["trend"]["status"]),
                  "active_lessons": s["image"]["lessons"]["active"],
                  "lessons_acted_on": s["image"]["lessons_applied"]["acted_on"],
                  "promotions": sum(1 for p in s["image"]["promotions"]
                                    if p["kind"] == "promote"),
                  "demotions": sum(1 for p in s["image"]["promotions"]
                                   if p["kind"] == "demote")},
        "pattern": {"first_pass_all_time": rate_of(s["pattern"]["all_time"]),
                    "trend": s["pattern"]["trend"].get("verdict",
                                                       s["pattern"]["trend"]["status"]),
                    "families": sorted(k for k in s["pattern"]["families"] if k != "ALL"),
                    "active_lessons": s["pattern"]["lessons"]["active"],
                    "lessons_acted_on": s["pattern"]["lessons_applied"]["acted_on"]},
        "commerce": {"status": s["commerce"]["status"],
                     "real_orders": s["commerce"]["real_orders"],
                     "active_lessons": s["commerce"]["lessons"]["active"]},
        # LEARN-PROOF: benchmark teardown lessons applied per department; UNKNOWN, never 0,
        # where it was not measured (`benchmark_lessons.readback`).
        "benchmark_lessons": _benchmark(db),
    }


def _benchmark(db) -> dict:
    from . import benchmark_lessons

    try:
        return benchmark_lessons.readback(db)
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN
        return {"readable": False, "error_class": type(exc).__name__[:80],
                "ingested": benchmark_lessons.UNKNOWN, "departments": {
                    d: {"applied": benchmark_lessons.UNKNOWN, "why": "readback failed"}
                    for d in benchmark_lessons.DEPARTMENTS}}
