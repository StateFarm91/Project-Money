"""Research M2 (review 6954809399): a watchlist gap's research question answered from evidence
this system already recorded, so gap -> research -> fact -> proposal -> concept_intake runs
unattended.

The question `watchlist._research_question` opens is "is buyer demand in this arena durable
across the watchlist shops, or a passing trend?". Nothing answered it: the Research Agent
writes only `unresolved` findings and, with no internal hit for a pod name, stops the task;
no fetch covers Etsy. The evidence that bears on it is the daily structured comparison
(`intel.watchlist_compare` readings), which records, per day, the arenas that at least
`MIN_SHOPS_FOR_ARENA` uncovered watchlist shops each stock with at least
`MIN_LISTINGS_FOR_ARENA` listings.

What this writes, and nothing more:

* two `internal` sources, both read on the latest day: that day's comparison reading, and the
  run of readings in the window (its citation names every day the arena was corroborated);
* a `fact`: the arena was corroborated by N uncovered watchlist shops in the latest reading;
* a `fact`: the arena was corroborated on K of the M daily readings in the last
  `DURABILITY_WINDOW_DAYS` (durability is what the question asks);
* an `unresolved` finding for what the readings cannot show: whether the listings sell
  (no per-listing sales are recorded), so demand at the sales level stays UNKNOWN;
* the answer, with confidence `medium` only when the arena was corroborated on at least
  `DURABLE_DAYS` distinct days, else `low` (which concept intake's evidence floor refuses,
  so a one-day arena never becomes a concept).

No competitor title, URL, tag or listing text is read or written: only the comparison's own
pod names, shop aliases, counts and dates. A task that is not OPEN is never touched.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

DURABILITY_WINDOW_DAYS = 14
DURABLE_DAYS = 3
ACTION = "research.answered_from_watchlist"


def _readings(db, kind: str, *, until: date) -> list[tuple[str, dict]]:
    """(day, payload) of every reading of `kind` in the window ending `until`, newest first."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    since = (until - timedelta(days=DURABILITY_WINDOW_DAYS - 1)).isoformat()
    with db.session() as s:
        rows = list(s.scalars(select(OperatingReading).where(
            OperatingReading.kind == kind, OperatingReading.period_key >= since,
            OperatingReading.period_key <= until.isoformat()).order_by(
            OperatingReading.period_key.desc())))
        return [(r.period_key, dict(r.payload or {})) for r in rows]


def _corroborated(payload: dict, pod: str) -> list[str] | None:
    for a in payload.get("validated_arenas") or []:
        if a.get("pod") == pod:
            return sorted(str(x) for x in a.get("corroborated_by") or [])
    return None


def answer(db, *, gap_id: int, task_id: int, pod: str, now: datetime | None = None,
           audit=None) -> dict:
    """Answer the gap's OPEN research task from the recorded comparisons, or say why not."""
    from . import research
    from .watchlist import COMPARE_READING, MIN_LISTINGS_FOR_ARENA, MIN_SHOPS_FOR_ARENA

    now = now or datetime.now(timezone.utc)
    research._ensure(db)
    with db.session() as s:
        t = s.get(research.ResearchTask, int(task_id))
        state = t.state if t is not None else None
    if state != research.OPEN:
        return {"answered": False, "task": task_id, "why": f"task is {state}, not open"}
    readings = _readings(db, COMPARE_READING, until=now.date())
    hits = [(day, _corroborated(p, pod)) for day, p in readings]
    hits = [(day, shops) for day, shops in hits if shops]
    if not hits:
        return {"answered": False, "task": task_id,
                "why": f"no recorded comparison corroborates the {pod} arena"}
    latest_day, latest_shops = hits[0]
    if len(latest_shops) < MIN_SHOPS_FOR_ARENA:
        return {"answered": False, "task": task_id,
                "why": "the latest reading does not corroborate the arena"}

    read_on = date.fromisoformat(latest_day)
    s_latest = "S%d" % research.add_source(
        db, task_id, source=COMPARE_READING,
        citation=f"operating_reading:{COMPARE_READING}:{latest_day}#validated_arenas/{pod}",
        retrieval="internal", read_on=read_on)
    # The series is one source, read whole on the latest day: durability is a property of the
    # run of readings, and each day it lists is named in the citation.
    first_day = readings[-1][0]
    s_series = "S%d" % research.add_source(
        db, task_id, source=COMPARE_READING,
        citation=(f"operating_reading:{COMPARE_READING}:{first_day}..{latest_day}"
                  f"#validated_arenas/{pod} (corroborated on: "
                  f"{', '.join(d for d, _ in hits)})"),
        retrieval="internal", read_on=read_on)
    f_now = research.add_finding(
        db, task_id, claim_class="fact", rests_on=[s_latest], confidence="high",
        statement=(f"On {latest_day}, {len(latest_shops)} uncovered watchlist shops "
                   f"({', '.join(latest_shops)}) each listed at least {MIN_LISTINGS_FOR_ARENA} "
                   f"items in the {pod} arena (structured comparison, official API)."))
    days, window = len(hits), len(readings)
    f_durable = research.add_finding(
        db, task_id, claim_class="fact", rests_on=[s_series], confidence="high",
        statement=(f"The {pod} arena was corroborated by at least {MIN_SHOPS_FOR_ARENA} "
                   f"uncovered watchlist shops on {days} of the {window} daily comparisons "
                   f"recorded in the last {DURABILITY_WINDOW_DAYS} days."))
    f_unknown = research.add_finding(
        db, task_id, claim_class="unresolved",
        statement=(f"Whether the {pod} listings sell is UNKNOWN: the comparison records "
                   f"listing counts and dates, not per-listing sales."))
    durable = days >= DURABLE_DAYS
    confidence = "medium" if durable else "low"
    out = research.answer(
        db, task_id, outcome=("durable" if durable else "not yet shown durable"),
        confidence=confidence, now=now,
        effect={"kind": "constraint_established",
                "statement": (f"{pod}: corroborated on {days} of {window} recent daily "
                              f"comparisons ({f_now}, {f_durable})")},
        conclusion={"alternatives": [], "constraints": [
                        f"corroborated by {len(latest_shops)} uncovered watchlist shops on "
                        f"{latest_day}",
                        f"corroborated on {days} of {window} daily comparisons"],
                    "unresolved": [f_unknown], "next_test": {},
                    "applicability": {"pod": pod, "gap": gap_id}})
    detail = {"gap": gap_id, "task": task_id, "pod": pod, "days": days, "window": window,
              "confidence": confidence, "findings": [f_now, f_durable, f_unknown]}
    if audit is not None:
        audit(ACTION, artifact=f"research_task:{task_id}", detail=detail)
    return {"answered": True, **detail, "result": out}
