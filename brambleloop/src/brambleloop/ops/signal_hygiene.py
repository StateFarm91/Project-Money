"""Signal hygiene on the health sweep: aggregation, noise, disk trend (F-139, F-140, F-149).

F-139 Incident Aggregation: "Homogeneous large backlogs create one actionable incident with
count/scope while retaining item evidence." Defect dead letters of one job type become ONE
incident `dead-letters:<job_type>` carrying the count, the time span and every job id (capped,
with the cap stated), restated as the backlog changes and resolved when it is gone. Deliberate
refusals (shadow-mode publish refusals, capability stand-asides) are not defects and are never
aggregated into one.

F-140 Signal Actionability: "A permanently noisy/false health signal is itself a defect." A
signature that opened and closed `NOISY_CYCLES` or more times in `NOISY_WINDOW_DAYS` is
flapping; one that has stayed open past `STUCK_OPEN_DAYS` without any detector restating it is
a signal nobody confirms. Either opens `noisy-signal:<signature>` as a defect of the signal
itself, resolved when the pattern stops.

F-149 Disk Pressure Monitor: "Monitor scratch/cache growth, disk utilization and abnormal
file-count growth before ENOSPC." Each sweep stores a disk sample (`ops.disk_sample`: free GB
per filesystem, temp directories left behind). Over the samples of the last `TREND_HOURS`:
leftover-directory growth beyond `TEMP_GROWTH_PER_DAY`, or a free-space decline that reaches
zero within `ENOSPC_HORIZON_HOURS`, opens `disk-trend:<what>`. Too few samples is UNKNOWN, never
fine.

Reads rows and writes audit rows and incidents only; removes nothing; spends nothing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

AGG_MIN = 3
AGG_IDS_CAP = 200
NOISY_CYCLES = 4
NOISY_WINDOW_DAYS = 7
STUCK_OPEN_DAYS = 14
WATCHED_PREFIXES = ("health:", "dead-letters:", "disk-trend:")
SAMPLE_ACTION = "ops.disk_sample"
TREND_HOURS = 24
MIN_SAMPLES = 4
TEMP_GROWTH_PER_DAY = 20
ENOSPC_HORIZON_HOURS = 48


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)


def _parse(v):
    try:
        return _aware(datetime.fromisoformat(str(v)))
    except (TypeError, ValueError):
        return None


# ---- F-139 --------------------------------------------------------------------------------

def aggregate_dead_letters(session, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import Job, JobStatus
    from ..queue.durable import deliberate_refusal
    from . import incident_lifecycle as lifecycle

    now = now or datetime.now(timezone.utc)
    groups: dict[str, list] = {}
    for job in session.scalars(select(Job).where(Job.status == JobStatus.DEAD)
                               .order_by(Job.id)):
        if deliberate_refusal(job.job_type, job.last_error or ""):
            continue
        groups.setdefault(job.job_type, []).append(job)
    large = {t: js for t, js in groups.items() if len(js) >= AGG_MIN}
    life = lifecycle.reconcile(
        session, "dead-letters:", lambda row: row.signature.split(":", 1)[1] in large,
        resolution="no defect dead letter of this job type remains", now=now)
    opened = []
    for job_type, jobs in sorted(large.items()):
        stamps = [_aware(j.finished_at or j.created_at) for j in jobs
                  if (j.finished_at or j.created_at) is not None]
        ids = [j.id for j in jobs]
        errors: dict[str, int] = {}
        for j in jobs:
            key = (j.last_error or "").split("\n")[0][:160]
            errors[key] = errors.get(key, 0) + 1
        detail = {"job_type": job_type, "count": len(jobs),
                  "first_at": min(stamps).isoformat() if stamps else None,
                  "last_at": max(stamps).isoformat() if stamps else None,
                  "job_ids": ids[:AGG_IDS_CAP],
                  "job_ids_truncated": max(0, len(ids) - AGG_IDS_CAP),
                  "errors": dict(sorted(errors.items(), key=lambda kv: -kv[1])[:10])}
        _row, new = lifecycle.open_or_restate(
            session, signature=f"dead-letters:{job_type}", severity="P2",
            summary=(f"{len(jobs)} defect dead letters of {job_type}: one backlog, one "
                     f"incident (every job id kept in the detail)"), detail=detail, now=now)
        if new:
            opened.append(job_type)
    return {"aggregated": {t: len(js) for t, js in sorted(large.items())},
            "below_threshold": {t: len(js) for t, js in sorted(groups.items())
                                if t not in large},
            "opened": opened, "resolved": life["resolved"]}


# ---- F-140 --------------------------------------------------------------------------------

def noisy_signals(session, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import Incident
    from . import incident_lifecycle as lifecycle

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=NOISY_WINDOW_DAYS)
    cycles: dict[str, int] = {}
    stuck: dict[str, float] = {}
    for row in session.scalars(select(Incident)):
        sig = row.signature or ""
        if not sig.startswith(WATCHED_PREFIXES):
            continue
        if _aware(row.at) >= since:
            cycles[sig] = cycles.get(sig, 0) + 1
        if not row.resolved:
            last = _parse((row.detail or {}).get("last_seen")) or _aware(row.at)
            age = (now - _aware(row.at)).days
            unconfirmed_h = (now - last).total_seconds() / 3600
            if age >= STUCK_OPEN_DAYS and unconfirmed_h >= 24 * STUCK_OPEN_DAYS:
                stuck[sig] = round(unconfirmed_h / 24, 1)
    flapping = {s: n for s, n in cycles.items() if n >= NOISY_CYCLES}
    noisy = set(flapping) | set(stuck)
    life = lifecycle.reconcile(
        session, "noisy-signal:", lambda row: row.signature.split(":", 1)[1] in noisy,
        resolution=(f"fewer than {NOISY_CYCLES} open/close cycles in {NOISY_WINDOW_DAYS} days "
                    "and confirmed by its detector"), now=now)
    opened = []
    for sig in sorted(noisy):
        why = (f"opened {flapping[sig]} times in {NOISY_WINDOW_DAYS} days" if sig in flapping
               else f"open and unconfirmed by any detector for {stuck[sig]} days")
        _row, new = lifecycle.open_or_restate(
            session, signature=f"noisy-signal:{sig}", severity="P2",
            summary=f"the signal {sig} is not actionable: {why}; fix the signal (F-140)",
            detail={"signal": sig, "cycles": flapping.get(sig), "unconfirmed_days":
                    stuck.get(sig), "window_days": NOISY_WINDOW_DAYS}, now=now)
        if new:
            opened.append(sig)
    return {"flapping": flapping, "stuck_unconfirmed": stuck, "opened": opened,
            "resolved": life["resolved"]}


# ---- F-149 --------------------------------------------------------------------------------

def disk_sample(facts: dict | None) -> dict | None:
    if not isinstance(facts, dict) or not facts:
        return None
    return {"temp_dirs_left_behind": facts.get("temp_dirs_left_behind"),
            "free_gb": {k: v.get("free_gb") for k, v in (facts.get("filesystems") or {})
                        .items() if isinstance(v, dict)}}


def disk_trend(samples: list[tuple[datetime, dict]], *, now: datetime) -> dict:
    """Pure: growth of leftover temp directories and free-space decline over the window."""
    window = [(t, s) for t, s in samples if t >= now - timedelta(hours=TREND_HOURS)]
    if len(window) < MIN_SAMPLES:
        return {"state": "UNKNOWN", "samples": len(window),
                "why": f"fewer than {MIN_SAMPLES} disk samples in {TREND_HOURS} h: no trend "
                       "can be read, which is not the same as no growth"}
    window.sort(key=lambda x: x[0])
    (t0, s0), (t1, s1) = window[0], window[-1]
    hours = max((t1 - t0).total_seconds() / 3600, 1e-6)
    alarms = []
    a, b = s0.get("temp_dirs_left_behind"), s1.get("temp_dirs_left_behind")
    if isinstance(a, int) and isinstance(b, int):
        per_day = (b - a) / hours * 24
        if per_day > TEMP_GROWTH_PER_DAY:
            alarms.append({"what": "temp_dirs", "per_day": round(per_day, 1),
                           "why": f"leftover working directories grew {b - a} in "
                                  f"{hours:.1f} h ({per_day:.0f}/day > {TEMP_GROWTH_PER_DAY})"})
    for fs, free1 in (s1.get("free_gb") or {}).items():
        free0 = (s0.get("free_gb") or {}).get(fs)
        if not isinstance(free0, (int, float)) or not isinstance(free1, (int, float)):
            continue
        rate = (free0 - free1) / hours           # GB per hour consumed
        if rate > 0 and free1 / rate <= ENOSPC_HORIZON_HOURS:
            alarms.append({"what": f"free:{fs}", "gb_per_hour": round(rate, 4),
                           "hours_to_full": round(free1 / rate, 1),
                           "why": f"{fs} loses {rate:.3f} GB/h and has {free1:.2f} GB left: "
                                  f"full in {free1 / rate:.0f} h"})
    return {"state": "ALARM" if alarms else "OK", "samples": len(window),
            "hours": round(hours, 2), "alarms": alarms}


def disk_watch(db, session, facts: dict | None, *, now: datetime | None = None) -> dict:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from . import incident_lifecycle as lifecycle

    now = now or datetime.now(timezone.utc)
    sample = disk_sample(facts)
    if sample is not None:
        session.add(AuditLog(actor="orchestrator", action=SAMPLE_ACTION, detail=sample, at=now))
        session.flush()
    rows = list(session.scalars(select(AuditLog).where(AuditLog.action == SAMPLE_ACTION)
                                .order_by(desc(AuditLog.id)).limit(500)))
    samples = [(_aware(r.at), r.detail or {}) for r in rows]
    trend = disk_trend(samples, now=now)
    if trend["state"] == "UNKNOWN":
        return dict(trend, sampled=sample is not None)
    keys = {a["what"] for a in trend["alarms"]}
    life = lifecycle.reconcile(session, "disk-trend:",
                               lambda row: row.signature.split(":", 1)[1] in keys,
                               resolution="the disk trend no longer predicts exhaustion",
                               now=now)
    for a in trend["alarms"]:
        lifecycle.open_or_restate(session, signature=f"disk-trend:{a['what']}", severity="P1",
                                  summary=a["why"] + " (F-149: before ENOSPC)",
                                  detail={"trend": a}, now=now)
    return dict(trend, sampled=sample is not None, resolved=life["resolved"])


def sweep(db, session, *, facts: dict | None, now: datetime | None = None) -> dict:
    """All three, each guarded: one failing check never hides the others."""
    out = {}
    for name, fn in (("dead_letter_aggregation", lambda: aggregate_dead_letters(session, now=now)),
                     ("disk_trend", lambda: disk_watch(db, session, facts, now=now)),
                     ("noisy_signals", lambda: noisy_signals(session, now=now))):
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001 - reported as UNKNOWN, never as clean
            out[name] = {"state": "UNKNOWN", "error": f"{type(exc).__name__}: {exc}"[:200]}
    return out
