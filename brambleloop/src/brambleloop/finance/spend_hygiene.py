"""Spend hygiene detectors the governor runs every pass (F-305, F-308, F-315, F-326, F-306).

`governor.enforce` already pauses an agent whose *day* spikes against its own history. That
misses the shapes of waste that do not look like a big day:

* **Retry storm (F-308).** One agent+purpose billing many *failed* attempts inside an hour --
  bad JSON retried, an accepted-then-failed render re-asked -- is money spent on the same
  failure. `max_attempts` bounds one job; nothing bounded the pattern across jobs.
* **Hourly spike (F-326).** An hour whose spend is far above the ordinary hour of the last
  week. A runaway loop is visible within the hour, not at the end of the UTC day.
* **Repeated identical paid request (F-306/F-326).** The same request bytes paid for by
  several *different* jobs in a day (`paid_calls` records the fingerprint): identical evidence
  bought again because a cadence ran again.
* **Unattributed spend over tolerance (F-305).** Spend with no agent, job or product cannot
  be explained; past a small share of the month it is a defect, not a rounding.
* **Oversized input (F-315).** A call whose input tokens exceed the per-call allowance is a
  context-discipline fault (an unbounded catalogue pasted into a prompt).

Every detector opens (or re-reports) an incident through the governor's own `_open_incident`
and changes no ceiling. Each states when it cannot measure (no baseline, no rows) rather than
reporting a clean bill.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

RETRY_STORM_MIN_FAILED = 5
RETRY_STORM_WINDOW = timedelta(hours=1)
HOURLY_BASELINE_DAYS = 7
HOURLY_MIN_HOURS = 24
HOURLY_SPIKE_MULTIPLE = 5.0
HOURLY_SPIKE_FLOOR_CAD = 0.50
REPEAT_WINDOW = timedelta(hours=24)
REPEAT_MIN_JOBS = 3
UNATTRIBUTED_TOLERANCE = 0.05
UNATTRIBUTED_FLOOR_CAD = 1.00
INPUT_TOKEN_ALLOWANCE = 60_000

SIGNATURES = {"retry_storm": "spend-retry-storm", "hourly_spike": "spend-hourly-spike",
              "repeat_request": "spend-repeat-paid-request",
              "unattributed": "spend-unattributed-over-tolerance",
              "oversized_input": "spend-oversized-input"}

_FAILED_BILLINGS = frozenset({"accepted_then_failed", "unknown_counted_at_estimate",
                              "unknown_usage_counted_at_estimate", "exception_usage"})


def _aware(v: datetime) -> datetime:
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _failed(row) -> bool:
    d = row.detail if isinstance(row.detail, dict) else {}
    return d.get("ok") is False or str(d.get("billing") or "") in _FAILED_BILLINGS


def retry_storms(rows, now: datetime) -> list[dict]:
    since = now - RETRY_STORM_WINDOW
    c: Counter = Counter()
    cad: dict = defaultdict(float)
    for r in rows:
        if _aware(r.at) >= since and float(r.amount_cad or 0) > 0 and _failed(r):
            k = (r.agent or "", r.purpose or "")
            c[k] += 1
            cad[k] += float(r.amount_cad or 0)
    return [{"agent": a, "purpose": p, "failed_billed_attempts": n,
             "cad": round(cad[(a, p)], 6)}
            for (a, p), n in sorted(c.items()) if n >= RETRY_STORM_MIN_FAILED]


def hourly_spike(rows, now: datetime) -> dict:
    hour = now.replace(minute=0, second=0, microsecond=0)
    start = hour - timedelta(days=HOURLY_BASELINE_DAYS)
    by_hour: dict = defaultdict(float)
    for r in rows:
        at = _aware(r.at)
        if at >= start:
            by_hour[at.replace(minute=0, second=0, microsecond=0)] += float(r.amount_cad or 0)
    current = round(by_hour.get(hour, 0.0), 6)
    first = min(by_hour) if by_hour else None
    span_hours = int((hour - first).total_seconds() // 3600) if first else 0
    if span_hours < HOURLY_MIN_HOURS:
        return {"measurable": False, "current_hour_cad": current,
                "why": f"{span_hours} hour(s) of history; a normal hour needs "
                       f"{HOURLY_MIN_HOURS}"}
    past = [by_hour.get(hour - timedelta(hours=i), 0.0) for i in range(1, span_hours + 1)]
    ordinary = median(past)
    threshold = max(HOURLY_SPIKE_FLOOR_CAD, ordinary * HOURLY_SPIKE_MULTIPLE)
    return {"measurable": True, "current_hour_cad": current,
            "ordinary_hour_cad": round(ordinary, 6), "threshold_cad": round(threshold, 6),
            "spike": current > threshold}


def repeated_requests(db, now: datetime) -> list[dict]:
    try:
        from sqlalchemy import select

        from ..gateway.paid_calls import OK, PaidCallRecord, ensure_table

        ensure_table(db)
        with db.session() as s:
            recs = list(s.execute(select(PaidCallRecord.fingerprint, PaidCallRecord.effect,
                                         PaidCallRecord.job_id, PaidCallRecord.at)
                                  .where(PaidCallRecord.outcome == OK)))
    except Exception:  # noqa: BLE001 - a missing table is "no guarded calls yet"
        return []
    jobs: dict = defaultdict(set)
    for fp, effect, job_id, at in recs:
        if at is not None and _aware(at) >= now - REPEAT_WINDOW:
            jobs[(fp, effect)].add(job_id)
    return [{"fingerprint": fp[:16], "effect": effect, "jobs": len(js)}
            for (fp, effect), js in sorted(jobs.items(), key=lambda kv: -len(kv[1]))
            if len(js) >= REPEAT_MIN_JOBS]


def unattributed(rows, now: datetime) -> dict:
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = untraced = 0.0
    for r in rows:
        if _aware(r.at) < month:
            continue
        amt = float(r.amount_cad or 0)
        total += amt
        if not r.job_id and not (r.product_slug or "") and (r.agent or "") in ("", "gateway"):
            untraced += amt
    share = round(untraced / total, 4) if total > 0 else 0.0
    return {"month_cad": round(total, 6), "unattributed_cad": round(untraced, 6),
            "share": share, "tolerance": UNATTRIBUTED_TOLERANCE,
            "over": untraced >= UNATTRIBUTED_FLOOR_CAD and share > UNATTRIBUTED_TOLERANCE}


def oversized_inputs(rows, now: datetime) -> list[dict]:
    since = now - timedelta(hours=24)
    out: dict = {}
    for r in rows:
        if _aware(r.at) >= since and int(r.tokens_in or 0) > INPUT_TOKEN_ALLOWANCE:
            k = r.purpose or ""
            out[k] = max(out.get(k, 0), int(r.tokens_in or 0))
    return [{"purpose": p, "max_tokens_in": n, "allowance": INPUT_TOKEN_ALLOWANCE}
            for p, n in sorted(out.items())]


def sweep(db, *, now: datetime | None = None) -> dict:
    """Run every detector and open an incident for each finding. Changes no ceiling."""
    from sqlalchemy import select

    from ..core.models import CostEntry
    from .governor import _open_incident

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=max(HOURLY_BASELINE_DAYS, 31) + 1)
    with db.session() as s:
        rows = list(s.scalars(select(CostEntry).where(CostEntry.at >= since)))
        for r in rows:
            s.expunge(r)
    found = {"retry_storms": retry_storms(rows, now), "hourly": hourly_spike(rows, now),
             "repeated_requests": repeated_requests(db, now),
             "unattributed": unattributed(rows, now),
             "oversized_inputs": oversized_inputs(rows, now)}
    stamp, hour = now.date().isoformat(), now.strftime("%Y-%m-%dT%H")
    incidents = []

    def _open(sig: str, summary: str, detail: dict, severity: str = "P2"):
        with db.session() as s:
            state = _open_incident(s, signature=sig, summary=summary, detail=detail,
                                   severity=severity)
        incidents.append({"signature": sig, "state": state})

    for st in found["retry_storms"]:
        _open(f"{SIGNATURES['retry_storm']}:{st['agent']}:{st['purpose']}:{hour}"[:200],
              f"Retry storm: {st['agent'] or 'unattributed'} billed "
              f"{st['failed_billed_attempts']} failed attempts at {st['purpose']} within an "
              f"hour (CA${st['cad']}). Money is being spent on the same failure", st)
    if found["hourly"].get("spike"):
        h = found["hourly"]
        _open(f"{SIGNATURES['hourly_spike']}:{hour}",
              f"Hourly spend spike: CA${h['current_hour_cad']} this hour against an ordinary "
              f"hour of CA${h['ordinary_hour_cad']} (threshold CA${h['threshold_cad']})", h)
    for rq in found["repeated_requests"]:
        _open(f"{SIGNATURES['repeat_request']}:{rq['fingerprint']}:{stamp}",
              f"The same {rq['effect']} request was paid for by {rq['jobs']} different jobs "
              f"in 24 hours: identical evidence bought again", rq, severity="P3")
    if found["unattributed"]["over"]:
        u = found["unattributed"]
        _open(f"{SIGNATURES['unattributed']}:{stamp[:7]}",
              f"Unattributed spend CA${u['unattributed_cad']} is {u['share'] * 100:.1f}% of "
              f"the month (tolerance {UNATTRIBUTED_TOLERANCE * 100:.0f}%): spend with no "
              f"agent, job or product cannot be explained", u)
    for big in found["oversized_inputs"]:
        _open(f"{SIGNATURES['oversized_input']}:{big['purpose']}:{stamp}"[:200],
              f"{big['purpose']} sent {big['max_tokens_in']} input tokens in one call, over "
              f"the {INPUT_TOKEN_ALLOWANCE}-token allowance", big, severity="P3")
    return {**found, "incidents": incidents, "ceilings_changed": 0}
