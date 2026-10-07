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
