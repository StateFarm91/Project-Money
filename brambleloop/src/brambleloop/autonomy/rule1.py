"""Rule #1 measurement: does every department find and do useful work without a prompt?

`measure(db)` reads the jobs table after a run (the real runner, shadow) and reports, per
department: completions, useful completions by the one judge (`did_no_work`), useful
completions with repeated identical outputs counted once (`kpis.fingerprint`), no-ops with
their stated reasons, dead letters, and -- the Rule #1 defect test -- whether the department
ends the window idle while its own generators still offer safe, runnable, not-yet-generated
work. Read-only. Used by `autonomy.proof` and the W4 audit; never raises per department.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select


def _st(v) -> str:
    return getattr(v, "value", str(v))


def measure(db, *, now: datetime | None = None) -> dict:
    from ..core.models import Job
    from . import charters, generators, orchestrator
    from .kpis import SELF_MEASUREMENT_TYPES, did_no_work, fingerprint, job_department

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        jobs = list(s.execute(select(Job.id, Job.job_type, Job.inputs, Job.outputs,
                                     Job.status, Job.idempotency_key)).all())
    out: dict = {}
    for ch in charters.CHARTERS:
        mine = [j for j in jobs if job_department(j.job_type, j.inputs) == ch.key
                and j.job_type != "autonomy.orchestrate"]
        work = [j for j in mine if j.job_type not in SELF_MEASUREMENT_TYPES]
        done = [j for j in work if _st(j.status) == "done"]
        useful = [j for j in done if not did_no_work(j.outputs, j.job_type)]
        distinct = {(j.job_type, fingerprint(j.outputs)) for j in useful}
        noop = [j for j in done if did_no_work(j.outputs, j.job_type)]
        reasons = Counter()
        for j in noop:
            o = j.outputs or {}
            reasons[(j.job_type, str(o.get("reason") or o.get("why") or "no work keys")[:120])] += 1
        entry = {
            "jobs": len(mine), "work_jobs": len(work), "self_measurement_jobs": len(mine) - len(work),
            "done": len(done), "useful": len(useful), "useful_distinct": len(distinct),
            "noop": len(noop),
            "dead": sum(1 for j in work if _st(j.status) == "dead"),
            "open": sum(1 for j in work if _st(j.status) in ("pending", "running", "failed")),
            "useful_rate": round(len(useful) / len(done), 4) if done else None,
            "useful_distinct_rate": round(len(distinct) / len(done), 4) if done else None,
            "useful_types": dict(Counter(j.job_type for j in useful)),
            "top_noop": [{"job_type": jt, "reason": r, "n": n}
                         for (jt, r), n in reasons.most_common(6)],
            "generated_missions": sum(1 for j in mine
                                      if (j.inputs or {}).get("source") == "autonomy"),
        }
        try:
            snap = generators.Snapshot.read(db, now)
            cands = [c for c in generators.candidates(db, ch, snap)
                     if not c.protected and c.job_type != "autonomy.department_review"]
            keys = {orchestrator.mission_key(ch, c) for c in cands}
            taken = {j.idempotency_key for j in jobs if j.idempotency_key in keys}
            untaken = [c.to_dict() for c in cands
                       if orchestrator.mission_key(ch, c) not in taken]
            idle = not snap.open_by_department.get(ch.key)
            entry["eligible_untaken_at_end"] = untaken[:5]
            entry["idle_at_end"] = idle
            entry["rule1_defect"] = bool(idle and untaken)
        except Exception as exc:  # noqa: BLE001
            entry["eligible_error"] = f"{type(exc).__name__}: {exc}"[:200]
        out[ch.key] = entry
    tot_done = sum(e["done"] for e in out.values())
    tot_useful = sum(e["useful"] for e in out.values())
    tot_distinct = sum(e["useful_distinct"] for e in out.values())
    return {"departments": out,
            "totals": {"done": tot_done, "useful": tot_useful, "useful_distinct": tot_distinct,
                       "useful_rate": round(tot_useful / tot_done, 4) if tot_done else None,
                       "useful_distinct_rate": (round(tot_distinct / tot_done, 4)
                                                if tot_done else None)},
            "judge": "runtime.pipeline.did_no_work; distinct = kpis.fingerprint dedupe",
            "excludes": ["autonomy.orchestrate", *SELF_MEASUREMENT_TYPES]}


# ---- Command Center reading (W4-CCFIN) -------------------------------------------------
#
# `measure` above is the offline proof's full-history drain. The Command Center needs the same
# Rule #1 question answered on every page load, so `summary` bounds every cost:
#   * only jobs finished in the last `window_hours` (at most `max_jobs` rows, newest first);
#   * open work from the orchestrator's own `Snapshot` (the open queue, read once);
#   * each department's eligible-work check under a shared wall-clock `budget_s`; a department
#     the budget did not reach reads UNKNOWN, never "no defect";
#   * the "already generated" check is one IN query on the candidate keys, not a drain.
# Read-only: it selects, it never writes, enqueues or remembers. UNKNOWN is never 0.

SUMMARY_WINDOW_HOURS = 24
SUMMARY_MAX_JOBS = 5000
SUMMARY_BUDGET_S = 4.0
PROVIDER = "brambleloop.autonomy.rule1.summary"


def _as_db(db):
    from .status import _db

    return _db(db)


def summary(db, *, now: datetime | None = None, window_hours: float = SUMMARY_WINDOW_HOURS,
            max_jobs: int = SUMMARY_MAX_JOBS, budget_s: float = SUMMARY_BUDGET_S) -> dict:
    """Rule #1 state per department as a provider envelope. Never raises."""
    try:
        return _summary(_as_db(db), now=now or datetime.now(timezone.utc),
                        window_hours=window_hours, max_jobs=max_jobs, budget_s=budget_s)
    except Exception as exc:  # noqa: BLE001 - a provider never raises
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": [], "provider": PROVIDER,
                "reason": f"Rule #1 state unreadable: {type(exc).__name__}"[:200]}


def _summary(db, *, now: datetime, window_hours: float, max_jobs: int,
             budget_s: float) -> dict:
    import time
    from datetime import timedelta

    from sqlalchemy import func

    from ..core.models import Job
    from . import charters, generators, orchestrator
    from .kpis import SELF_MEASUREMENT_TYPES, did_no_work, job_department

    started = time.monotonic()
    since = now - timedelta(hours=window_hours)
    with db.session() as s:
        total_jobs = s.scalar(select(func.count()).select_from(Job)) or 0
        rows = list(s.execute(select(Job.job_type, Job.inputs, Job.outputs, Job.status)
                              .where(Job.finished_at >= since)
                              .order_by(Job.finished_at.desc()).limit(max_jobs + 1)).all())
    truncated = len(rows) > max_jobs
    rows = rows[:max_jobs]
    sources = ["jobs", "autonomy.generators", "autonomy.charters"]
    if not total_jobs:
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": sources, "provider": PROVIDER,
                "reason": "no jobs have ever been recorded; Rule #1 has not been measured"}
    snap = generators.Snapshot.read(db, now)
    items: list[dict] = []
    defects = unevaluated = 0
    for ch in charters.CHARTERS:
        mine = [r for r in rows if r.job_type != "autonomy.orchestrate"
                and r.job_type not in SELF_MEASUREMENT_TYPES
                and job_department(r.job_type, r.inputs) == ch.key]
        done = [r for r in mine if _st(r.status) == "done"]
        useful = sum(1 for r in done if not did_no_work(r.outputs, r.job_type))
        open_now = int(snap.open_by_department.get(ch.key, 0) or 0)
        idle = not open_now
        entry: dict = {
            "department": ch.key, "name": ch.name, "window_hours": window_hours,
            "done": len(done), "useful": useful, "noop": len(done) - useful,
            "dead": sum(1 for r in mine if _st(r.status) == "dead"),
            "useful_rate": round(useful / len(done), 4) if done else None,
            "open_now": open_now, "idle_now": idle,
            "eligible_untaken": None, "rule1_defect": None, "as_of": now.isoformat(),
        }
        if time.monotonic() - started > budget_s:
            entry["status"] = "UNKNOWN"
            entry["why"] = "not evaluated: the Command Center read budget was spent"
            unevaluated += 1
            items.append(entry)
            continue
        try:
            cands = [c for c in generators.candidates(db, ch, snap)
                     if not c.protected and c.job_type != "autonomy.department_review"]
            keys = {orchestrator.mission_key(ch, c): c for c in cands}
            taken: set = set()
            if keys:
                with db.session() as s:
                    taken = set(s.scalars(select(Job.idempotency_key).where(
                        Job.idempotency_key.in_(list(keys)))))
            untaken = [c for k, c in keys.items() if k not in taken]
            defect = bool(idle and untaken)
            entry.update(eligible_untaken=len(untaken), rule1_defect=defect,
                         next_eligible=[{"job_type": c.job_type, "reason": c.reason[:160]}
                                        for c in untaken[:3]],
                         status="DEGRADED" if defect else "OK",
                         why=("idle while its own generators offer safe, runnable work"
                              if defect else
                              "working" if not idle else "idle with no eligible untaken work"))
            defects += defect
        except Exception as exc:  # noqa: BLE001 - one department never hides the others
            entry["status"] = "UNKNOWN"
            entry["why"] = f"eligible work unreadable: {type(exc).__name__}"[:200]
            unevaluated += 1
        items.append(entry)
    evaluated = len(items) - unevaluated
    if defects:
        status, reason = "DEGRADED", (f"{defects} department(s) idle while eligible work "
                                      "waits (Rule #1 defect)")
    elif not evaluated:
        status, reason = "UNKNOWN", "no department's eligible work could be evaluated"
    else:
        status = "OK"
        reason = (f"{unevaluated} department(s) not evaluated; their Rule #1 state is UNKNOWN"
                  if unevaluated else None)
    out = {"status": status, "as_of": now.isoformat(), "basis": "measured", "items": items,
           "sources": sources, "provider": PROVIDER,
           "counts": {"departments": len(items), "evaluated": evaluated,
                      "unevaluated": unevaluated, "defects": defects if evaluated else None},
           "window": {"hours": window_hours, "since": since.isoformat(),
                      "jobs_read": len(rows), "max_jobs": max_jobs, "truncated": truncated},
           "judge": "runtime.pipeline.did_no_work; defect = idle and eligible untaken work"}
    if reason:
        out["reason"] = reason
    return out
