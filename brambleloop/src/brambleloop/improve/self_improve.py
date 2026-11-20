"""The automatic self-improvement team's daily pass, and its Mission Control panel.

`cycle` is the `improve.self_tune` job (GREEN: reads rows, may change a tunable champion inside
the allowlist, files change requests; spends nothing, calls no model, edits no code):

1. judge every active champion/challenger trial (`tuning.judge_all`): promote on a
   statistically meaningful KPI gain, reject on harm, roll back a watched promotion that
   regressed against its holdback;
2. build the department x KPI x lesson-consumer table (`department_loops.table`) and file one
   deduplicated change request per finding (no consumer, dormant consumer);
3. file a change request for every improve.* loop the thrash breaker holds at its maximum
   backoff (a failing loop);
4. verify every DEPLOYED change request against its KPI (`ecr.verify`): close it only when
   the improvement is measured, reopen it with the new evidence when it is not.

`panel` is the read-only Self-improvement section: per department the KPI trend (UNKNOWN on a
small sample), lessons learned / verified / applied, active challengers, promotions and
rollbacks, and open / shipped / verified change requests. A no-op never counts: a department
"improved" only when its trend reads UP on enough runs, or a change it shipped was VERIFIED.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import department_loops, ecr, tuning

JOB_TYPE = "improve.self_tune"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parked_improve_loops(db, now: datetime) -> list[dict]:
    from ..swarm.orchestrate import MAX_BACKOFF_FACTOR, suspended_job_types

    out = []
    for jt, sus in (suspended_job_types(db, now=now) or {}).items():
        if not jt.startswith("improve."):
            continue
        factor = sus.get("factor") or (sus.get("suspension") or {}).get("factor")
        if sus.get("kind") == "suspended" or (factor and int(factor) >= MAX_BACKOFF_FACTOR):
            out.append({"job_type": jt, "kind": sus.get("kind"), "factor": factor,
                        "incident": sus.get("incident"), "until": sus.get("until")})
    return out


def _file_parked(db, parked: list[dict]) -> list[dict]:
    out = []
    for p in parked:
        out.append(ecr.file(
            db, defect_class="failing_loop", department="ops", module=p["job_type"],
            title=f"{p['job_type']} parked by the thrash breaker",
            problem=(f"{p['job_type']} is held ({p['kind']}, factor {p['factor']}): its runs "
                     f"returned identical results with no new input."),
            evidence={"suspension": p, "examples": [p]},
            proposed_change=(f"Give {p['job_type']} an input probe (swarm.orchestrate."
                             f"INPUT_PROBES) or a work_done count so new input lifts the "
                             f"backoff, or fix the upstream that leaves it nothing to do."),
            acceptance_criteria=[f"{p['job_type']} is not in suspended_job_types after new "
                                 f"input arrives", "a test reproduces the park and the lift"],
            priority="P2", expected_kpi_gain={"kpi": "ops.useful_yield", "direction": "up"}))
    return out


def _verify_deployed(db, now: datetime) -> list[dict]:
    out = []
    for r in ecr.listing(db, open_only=True):
        if r["state"] != ecr.DEPLOYED or r["department"] not in department_loops.BY_KEY:
            continue
        dept = r["department"]
        out.append(ecr.verify(db, r["id"], now=now, measure=lambda a, b, d=dept:
                              department_loops.kpi_counts(db, d, a, b)))
    return out


def cycle(db, *, now: datetime | None = None) -> dict:
    now = now or _now()
    judged = tuning.judge_all(db)
    tbl = department_loops.table(db, now=now)
    filed = department_loops.file_findings(db, tbl)
    try:
        parked = _parked_improve_loops(db, now)
    except Exception as exc:  # noqa: BLE001 - reported, never a silent pass
        parked, parked_error = [], f"{type(exc).__name__}: {exc}"
    else:
        parked_error = None
    filed += _file_parked(db, parked)
    verified = _verify_deployed(db, now)
    decisions = [j for j in judged if j.get("decision") not in ("wait", "none")]
    work = len(decisions) + sum(1 for f in filed if f["created"]) + sum(
        1 for v in verified if v.get("verdict") in (ecr.VERIFIED, ecr.REOPENED))
    return {"ran": True, "work_done": work,
            "trials_judged": len(judged), "decisions": decisions,
            "departments": tbl["total"], "loops_closed": tbl["closed"],
            "findings": [{"department": f["department"], "defect_class": f["defect_class"]}
                         for f in tbl["findings"]],
            "ecrs_filed": [f["id"] for f in filed if f["created"]],
            "ecrs_merged": [f["id"] for f in filed if not f["created"]],
            "parked_improve_loops": [p["job_type"] for p in parked],
            "parked_read_error": parked_error,
            "ecrs_verified": [v["id"] for v in verified if v.get("verdict") == ecr.VERIFIED],
            "ecrs_reopened": [v["id"] for v in verified if v.get("verdict") == ecr.REOPENED]}


def panel(db, *, now: datetime | None = None) -> dict:
    """The Self-improvement section (read-only)."""
    now = now or _now()
    tbl = department_loops.table(db, now=now)
    trials = tuning.trials(db)
    ecrs = ecr.summary(db)
    rows = []
    for d in tbl["departments"]:
        mine = [t for t in trials if t["department"] == d["department"]]
        e = ecrs.get(d["department"], {"open": 0, "shipped": 0, "verified": 0, "reopened": 0})
        trend = d["kpi"]["trend"]["trend"]
        rows.append({
            "department": d["department"], "name": d["name"],
            "kpi": {"value": d["kpi"]["value"], "trials": d["kpi"]["trials"],
                    "state": d["kpi"]["state"], "trend": trend,
                    "why": d["kpi"]["trend"].get("why")},
            "lessons": {k: d["lessons"][k] for k in ("learned", "verified", "applied")},
            "consumers": [{"module": c["module"], "state": c["state"]} for c in d["consumers"]]
                         or [{"module": None, "state": "MISSING"}],
            "loop": d["verdict"],
            "challengers_active": [t for t in mine if t["state"] in tuning.ACTIVE_STATES],
            "promotions": sum(1 for t in mine if t["promoted_at"]),
            "rollbacks": sum(1 for t in mine if t["state"] == tuning.ROLLED_BACK),
            "ecrs": e,
            # Improvement is claimed only on evidence: an UP trend on enough runs, or a
            # verified shipped change. Everything else -- including "nothing happened" -- is not.
            "improving": ("YES" if trend == "UP" or e["verified"] else
                          "UNKNOWN" if trend == "UNKNOWN" else "NO")})
    status = "OK" if tbl["closed"] == tbl["total"] else "DEGRADED"
    return {"status": status, "as_of": now.isoformat(), "departments": rows,
            "loops_closed": tbl["closed"], "total": tbl["total"],
            "findings": tbl["findings"],
            "basis": "measured from jobs, lessons, learn_decisions, si_challengers and "
                     "engineering_change_requests; UNKNOWN below the sample floor",
            "tunables": tuning.describe()}
