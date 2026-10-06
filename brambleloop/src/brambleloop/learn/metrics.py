"""The Learn department's own operating reading: queue, metrics, calendar, experiments (F-799).

Master v0.24 F-799: Learn is a first-class department with its own queue, metrics, experiments,
assets, calendar, knowledge graph and durable state, under the same RUN/GROW/IMPROVE contract as
the other departments. The queue (`learn_gaps`), graph (`learn_nodes`/`learn_edges`), assets
and durable lesson state already existed; this is the rest, all derived from rows:

* **metrics** -- gaps queued and covered, coverage, the age of the oldest queued gap, lessons by
  state. Age is read from the source rows a gap's evidence names (`PatternVersion.created_at`,
  `SupportCase.at`); a gap whose sources cannot be dated has age `None` and is counted as such,
  never as zero.
* **calendar** -- the queued gaps in the order the department should work them (most sources
  first, then oldest), placed into weekly review slots at a fixed capacity. A plan, labelled
  `basis: "planned"`; it publishes nothing and dates nothing a customer sees.
* **experiments** -- `improvements` rows on the `learn` improvement cell (`improve.cells`), the
  same propose/test/promote/monitor loop every department's cell runs.

`improve.measure.measure_learn` turns coverage into the `learn` cell's capability point, so the
nightly IMPROVE loop measures Learn like every other department. Read-only; never raises from
`summary`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Lessons the department plans to take to review per week. A planning constant: it orders and
# spaces work, it never approves or publishes anything.
WEEKLY_LESSON_CAPACITY = 2
CALENDAR_WEEKS = 6
SOURCES = ["learn_gaps", "learn_lessons", "learn_nodes", "learn_edges", "pattern_versions",
           "support_cases", "improvements"]


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _first_seen(s, evidence) -> datetime | None:
    from ..core.models import PatternVersion, SupportCase

    stamps = []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        if item.get("pattern_version_id") is not None:
            pv = s.get(PatternVersion, item["pattern_version_id"])
            if pv is not None and pv.created_at is not None:
                stamps.append(_aware(pv.created_at))
        if item.get("support_case_id") is not None:
            case = s.get(SupportCase, item["support_case_id"])
            if case is not None and case.at is not None:
                stamps.append(_aware(case.at))
    return min(stamps) if stamps else None


def department_metrics(db, *, now: datetime | None = None) -> dict:
    """Queue, coverage, age and lesson metrics, read from rows."""
    from sqlalchemy import select

    from .models import LearnEdge, LearnGap, LearnNode, Lesson
    from .service import eligible

    now = _aware(now) or datetime.now(timezone.utc)
    with db.session() as s:
        gaps = list(s.scalars(select(LearnGap).order_by(LearnGap.topic)))
        lessons = list(s.scalars(select(Lesson)))
        nodes = len(s.scalars(select(LearnNode.key)).all())
        edges = len(s.scalars(select(LearnEdge.key)).all())
        queued = []
        for g in gaps:
            if g.state != "QUEUED":
                continue
            seen = _first_seen(s, g.evidence)
            queued.append({"topic": g.topic, "sources": len(g.evidence or []),
                           "first_seen": seen.isoformat() if seen else None,
                           "age_hours": (round((now - seen).total_seconds() / 3600, 1)
                                         if seen else None)})
        by_state: dict[str, int] = {}
        approved = 0
        for row in lessons:
            ok = eligible(row)
            state = "APPROVED" if ok else (row.state if row.state != "APPROVED" else "STALE")
            by_state[state] = by_state.get(state, 0) + 1
            approved += ok
    covered = sum(g.state == "COVERED" for g in gaps)
    dated = [q["age_hours"] for q in queued if q["age_hours"] is not None]
    return {
        "gaps_total": len(gaps), "gaps_queued": len(queued), "gaps_covered": covered,
        "coverage": round(covered / len(gaps), 4) if gaps else None,
        "oldest_queued_age_hours": max(dated) if dated else None,
        "queued_undated": len(queued) - len(dated),
        "lessons_by_state": by_state, "lessons_approved": approved,
        "graph": {"nodes": nodes, "edges": edges},
        "decision": "QUEUE" if queued else "WATCH",
        "queued": queued,
    }


def calendar(db, *, now: datetime | None = None, metrics: dict | None = None) -> dict:
    """Queued gaps placed into weekly review slots, most-evidenced and oldest first."""
    now = _aware(now) or datetime.now(timezone.utc)
    m = metrics or department_metrics(db, now=now)
    order = sorted(m["queued"], key=lambda q: (-q["sources"], q["first_seen"] or "~",
                                               q["topic"]))
    monday = (now + timedelta(days=(7 - now.weekday()) % 7 or 7)).date()
    slots = []
    for i, gap in enumerate(order[:WEEKLY_LESSON_CAPACITY * CALENDAR_WEEKS]):
        week = monday + timedelta(weeks=i // WEEKLY_LESSON_CAPACITY)
        slots.append({"week_of": week.isoformat(), "topic": gap["topic"],
                      "sources": gap["sources"], "work": "draft lesson for review"})
    return {"basis": "planned", "capacity_per_week": WEEKLY_LESSON_CAPACITY,
            "slots": slots, "unscheduled": max(0, len(order) - len(slots)),
            "note": "a plan for the editor; nothing is generated or published by it"}


def experiments(db) -> dict:
    """Improvement-cell experiments on the `learn` cell, by state."""
    from sqlalchemy import select

    from ..core.models import Improvement

    with db.session() as s:
        rows = list(s.scalars(select(Improvement).where(Improvement.cell == "learn")
                              .order_by(Improvement.id)))
        out = [{"id": r.id, "state": r.state, "hypothesis": r.hypothesis,
                "baseline": r.baseline_value} for r in rows]
    by_state: dict[str, int] = {}
    for r in out:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
    return {"cell": "learn", "by_state": by_state, "items": out[-10:]}


def summary(db, *, now: datetime | None = None) -> dict:
    """The department reading (provider shape). Never raises; empty is UNKNOWN, not zero."""
    try:
        now = _aware(now) or datetime.now(timezone.utc)
        m = department_metrics(db, now=now)
        out = {"metrics": {k: v for k, v in m.items() if k != "queued"},
               "calendar": calendar(db, now=now, metrics=m),
               "experiments": experiments(db), "sources": SOURCES,
               "as_of": now.isoformat(), "items": m["queued"][:50]}
        if not m["gaps_total"]:
            out.update(status="UNKNOWN", basis="unknown",
                       reason="no LearnGap row yet: learn.scan has found no pattern or support "
                              "source, so coverage is unknowable rather than zero")
        else:
            out.update(status="OK" if not m["gaps_queued"] else "DEGRADED", basis="measured",
                       reason=f"{m['gaps_covered']} of {m['gaps_total']} source-backed gaps "
                              f"covered by an approved lesson")
        return out
    except Exception as exc:  # noqa: BLE001 - a provider reports, it does not crash the page
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": SOURCES,
                "reason": f"learn metrics unreadable: {type(exc).__name__}: {str(exc)[:200]}"}
