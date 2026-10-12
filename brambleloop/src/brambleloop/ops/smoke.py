"""F-171: the production smoke matrix -- what /api/verify did not exercise.

`/api/verify` asserts safety (shadow phase, nothing published, spend bounded, worker and
scheduler alive, no unexpected dead letters). F-171 asks for more after a deploy: the critical
cadences actually ran, the queue actually completes work, the provider probes actually ran, a
continuity restore was actually proven, and search intelligence was actually captured. Each is
read here from durable rows the runtime itself wrote -- never from configuration, which says
what should happen rather than what did.

Each check is PASS, FAIL or UNKNOWN (never a default PASS; UNKNOWN when the rows needed to judge
it do not exist yet, e.g. a fresh database or a container younger than one period). The matrix
verdict is FAIL if any check fails, UNKNOWN if none fails and any is unknown, else PASS.

A probe that RAN and was refused by its provider (Etsy answering 403) is a PASS for "the probe
ran" -- the refusal is an external fact reported in the evidence and owned by its gate -- while
a probe that has not run within two periods is a FAIL: the smoke question is whether the
machinery runs, not whether every outside party says yes.

Read-only. Served at GET /api/verify/smoke (200 PASS, 503 otherwise) and as a readback inside
/api/verify, and read after each deploy by ops/readback.py (F-144).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
GRACE_S = 30 * 60
# probe audit action -> the cadence (runtime.worker.CADENCES name) that drives it
PROBES = {"model.probe": "model_probe", "vision.probe": "capability_probes",
          "etsy.probe": "etsy_probe"}
CONTINUITY_CADENCE = "continuity_proof"
SEARCH_CADENCE = "serp_capture"
ROUND_TRIP_WINDOW_S = 60 * 60
OLDEST_DUE_PENDING_MAX_S = 60 * 60


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)


def _period(name: str) -> int | None:
    try:
        from ..runtime.worker import cadence_seconds

        return cadence_seconds(name)
    except Exception:  # noqa: BLE001 - an unscheduled cadence cannot be judged
        return None


def _check(name, verdict, why, evidence, requirement="F-171"):
    return {"check": name, "verdict": verdict, "why": why, "evidence": evidence,
            "requirement": requirement}


def _first_cadence_at(s):
    from sqlalchemy import func, select

    from ..core.models import Job

    return _aware(s.scalar(select(func.min(Job.created_at)).where(
        Job.idempotency_key.like("cadence:%"))))


def _young(first, now, allowed) -> bool:
    """The system has not been scheduling long enough for this check to be due."""
    return first is None or (now - first).total_seconds() < allowed


def probe_recency(s, now) -> list[dict]:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    first = _first_cadence_at(s)
    out = []
    for action, cadence in PROBES.items():
        period = _period(cadence)
        name = f"probe_ran:{action}"
        if period is None:
            out.append(_check(name, UNKNOWN, f"cadence {cadence!r} is not scheduled",
                              {"cadence": cadence}))
            continue
        allowed = 2 * period + GRACE_S
        row = s.scalar(select(AuditLog).where(AuditLog.action == action)
                       .order_by(desc(AuditLog.id)).limit(1))
        last = _aware(row.at) if row is not None else None
        age = None if last is None else (now - last).total_seconds()
        detail = row.detail if row is not None and isinstance(row.detail, dict) else {}
        ev = {"cadence": cadence, "period_s": period, "allowed_age_s": allowed,
              "last_at": last.isoformat() if last else None,
              "age_s": None if age is None else round(age),
              "provider_answered_ok": detail.get("ok") if row is not None else None,
              "provider_reason": (str(detail.get("reason") or detail.get("error") or "")[:160]
                                  or None)}
        if age is not None and age <= allowed:
            out.append(_check(name, PASS, f"{action} ran {round(age)} s ago", ev))
        elif _young(first, now, allowed):
            out.append(_check(name, UNKNOWN, "the system has not been scheduling for two "
                              "periods of this probe yet", ev))
        else:
            out.append(_check(name, FAIL, (f"{action} has not run within {allowed} s"
                                           if last else f"{action} has never run"), ev))
    return out


def continuity_proof(s, now) -> dict:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    period = _period(CONTINUITY_CADENCE)
    if period is None:
        return _check("continuity_restore_proven", UNKNOWN, "continuity cadence not scheduled",
                      {})
    allowed = 2 * period + GRACE_S

    def last(action):
        r = s.scalar(select(AuditLog).where(AuditLog.action == action)
                     .order_by(desc(AuditLog.id)).limit(1))
        return r

    ok, bad = last("continuity.verified"), last("continuity.failed")
    ok_at = _aware(ok.at) if ok is not None else None
    bad_at = _aware(bad.at) if bad is not None else None
    ev = {"last_verified_at": ok_at.isoformat() if ok_at else None,
          "last_failed_at": bad_at.isoformat() if bad_at else None,
          "allowed_age_s": allowed}
    if bad_at and (ok_at is None or bad_at > ok_at):
        return _check("continuity_restore_proven", FAIL,
                      "the latest continuity restore proof failed", ev)
    if ok_at and (now - ok_at).total_seconds() <= allowed:
        return _check("continuity_restore_proven", PASS,
                      "an export was restored into an empty database and hashed identically",
                      ev)
    if _young(_first_cadence_at(s), now, allowed):
        return _check("continuity_restore_proven", UNKNOWN,
                      "the system has not run two continuity periods yet", ev)
    return _check("continuity_restore_proven", FAIL,
                  "no continuity restore proof within two periods", ev)


def cadence_coverage(s, now) -> dict:
    from .slo import cadence_freshness

    r = cadence_freshness(s, now)
    sli = r.get("sli")
    measure = r.get("measure") or {}
    ev = {"reason": r.get("reason"), "fresh": measure.get("fresh"),
          "stale_count": measure.get("stale_count"),
          "stale": (measure.get("stale") or [])[:20],
          "not_yet_judged": measure.get("not_yet_judged")}
    if sli is None:
        return _check("cadence_coverage", UNKNOWN, str(r.get("reason")), ev)
    target = r.get("target")
    ev["target"] = target
    if isinstance(target, (int, float)) and sli >= target:
        # the same objective ops.slo holds the runtime to (F-924), not a second number
        return _check("cadence_coverage", PASS, str(r.get("reason")), ev)
    return _check("cadence_coverage", FAIL, str(r.get("reason")), ev)


def queue_round_trip(s, now) -> dict:
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus

    since = now - timedelta(seconds=ROUND_TRIP_WINDOW_S)
    done_recent = s.scalar(select(func.count()).select_from(Job).where(
        Job.status == JobStatus.DONE, Job.finished_at >= since)) or 0
    oldest_due = _aware(s.scalar(select(func.min(Job.run_after)).where(
        Job.status == JobStatus.PENDING, Job.run_after <= now)))
    wait = None if oldest_due is None else (now - oldest_due).total_seconds()
    first = _first_cadence_at(s)
    ev = {"done_in_last_hour": done_recent, "oldest_due_pending_wait_s":
          None if wait is None else round(wait), "max_wait_s": OLDEST_DUE_PENDING_MAX_S}
    if done_recent > 0 and (wait is None or wait <= OLDEST_DUE_PENDING_MAX_S):
        return _check("queue_round_trip", PASS,
                      "jobs are enqueued, claimed and completed within the hour", ev)
    if _young(first, now, ROUND_TRIP_WINDOW_S):
        return _check("queue_round_trip", UNKNOWN, "the system has run less than an hour", ev)
    why = ("no job completed in the last hour" if done_recent == 0 else
           f"due work has waited {round(wait)} s unclaimed")
    return _check("queue_round_trip", FAIL, why, ev)


def search_intelligence(s, now) -> dict:
    from sqlalchemy import func, select

    from ..core.models import Job, JobStatus
    from ..runtime.worker import CADENCES

    job_type = next((jt for n, _a, jt, _p in CADENCES if n == SEARCH_CADENCE), None)
    period = _period(SEARCH_CADENCE)
    if job_type is None or period is None:
        return _check("search_intelligence_captured", UNKNOWN,
                      "search-intelligence cadence not scheduled", {})
    allowed = 2 * period + GRACE_S
    last = _aware(s.scalar(select(func.max(Job.finished_at)).where(
        Job.job_type == job_type, Job.status == JobStatus.DONE)))
    age = None if last is None else (now - last).total_seconds()
    ev = {"job_type": job_type, "last_done_at": last.isoformat() if last else None,
          "age_s": None if age is None else round(age), "allowed_age_s": allowed}
    if age is not None and age <= allowed:
        return _check("search_intelligence_captured", PASS,
                      f"{job_type} completed {round(age)} s ago", ev)
    if _young(_first_cadence_at(s), now, allowed):
        return _check("search_intelligence_captured", UNKNOWN,
                      "the system has not run two capture periods yet", ev)
    return _check("search_intelligence_captured", FAIL,
                  f"{job_type} has not completed within {allowed} s", ev)


def smoke_matrix(db, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    checks: list[dict] = []
    with db.session() as s:
        for fn in (probe_recency, continuity_proof, cadence_coverage, queue_round_trip,
                   search_intelligence):
            try:
                got = fn(s, now)
            except Exception as exc:  # noqa: BLE001 - one unreadable check is UNKNOWN
                got = _check(fn.__name__, UNKNOWN,
                             f"could not be read: {type(exc).__name__}: {str(exc)[:160]}", {})
            checks.extend(got if isinstance(got, list) else [got])
    verdicts = {c["verdict"] for c in checks}
    verdict = FAIL if FAIL in verdicts else UNKNOWN if (UNKNOWN in verdicts or not checks) \
        else PASS
    return {"verdict": verdict, "as_of": now.isoformat(), "checks": checks,
            "failing": [c["check"] for c in checks if c["verdict"] == FAIL],
            "unknown": [c["check"] for c in checks if c["verdict"] == UNKNOWN],
            "rule": ("FAIL if any check fails; UNKNOWN if none fails and any cannot be judged "
                     "yet; PASS only when every check passes. Read from rows the runtime "
                     "wrote, never from configuration")}
