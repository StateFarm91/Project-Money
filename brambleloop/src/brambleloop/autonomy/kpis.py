"""Department KPIs with anti-gaming guardrails (F-918).

A KPI reading is one of three things and says which:

* ``OK``      -- measured, and no guardrail tripped.
* ``VOID``    -- a guardrail tripped in the window. The value is withheld (``None``): a
                 department that broke Product Truth, customer safety, financial truth or its
                 authority does not get a good score for anything else it did that day.
* ``UNKNOWN`` -- nothing to read. Never rendered as 0.

Anti-gaming is structural, not advisory:

* a completed job that reports it did nothing (`runtime.pipeline.did_no_work`) counts zero;
* identical outputs from the same job type count once (fingerprint over the outputs with the
  volatile keys removed), so re-running a job to farm completions does not move the number;
* work the orchestrator generated (``inputs.source == "autonomy"``) is held to the same rule --
  it cannot inflate the department it was generated for;
* the guardrails read the queue's own refusals (permission denied, budget exceeded,
  provenance refused) and department-specific truth breaches (a customer message sent in
  shadow, a certified version with no certificate, a listing live in shadow, ad spend with
  the ad gate closed).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..core.models import Job, JobStatus
from . import charters

VOLATILE = ("at", "as_of", "now", "ran_at", "generated_at", "checked_at", "timestamp",
            "started_at", "finished_at", "duration_seconds", "elapsed", "job_id", "mission")
GUARD_ERRORS = ("permission denied", "budget exceeded", "provenance refused")


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def fingerprint(outputs) -> str:
    def strip(v):
        if isinstance(v, dict):
            return {k: strip(x) for k, x in sorted(v.items()) if k not in VOLATILE}
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v

    blob = json.dumps(strip(outputs or {}), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def did_no_work(outputs) -> bool:
    from ..runtime.pipeline import did_no_work as _dnw

    outputs = outputs or {}
    if not outputs:
        return True
    try:
        return bool(_dnw(outputs))
    except Exception:  # noqa: BLE001
        return False


def job_department(job_type: str, inputs: dict | None) -> str | None:
    """autonomy.department_review runs as the COO but measures the department it names."""
    if job_type == "autonomy.department_review":
        return (inputs or {}).get("department") or "executive"
    return charters.department_of(job_type)


def _status(job) -> str:
    return getattr(job.status, "value", str(job.status))


def _phase(db) -> str:
    try:
        from ..core.phase import effective

        return str(effective(db))
    except Exception:  # noqa: BLE001
        return "shadow"


def department_guards(db, key: str, *, since: datetime) -> list[str]:
    """Department-specific truth breaches in the window. Each string is one breach."""
    breaches: list[str] = []
    from ..core import models as m

    shadow = "shadow" in _phase(db).lower()
    with db.session() as s:
        if key == "support" and shadow:
            n = s.scalar(select(func.count()).select_from(m.SupportCase).where(
                m.SupportCase.sent == True, m.SupportCase.at >= since))  # noqa: E712
            if n:
                breaches.append(f"{n} support case(s) marked sent while the phase is shadow")
        if key in ("product_truth", "product_design"):
            # Read in Python: a JSON column stores None as JSON null, which IS NULL misses.
            n = sum(1 for (cert,) in s.execute(select(m.PatternVersion.certificate).where(
                m.PatternVersion.certified == True)) if not cert)  # noqa: E712
            if n:
                breaches.append(f"{n} pattern version(s) certified with no certificate")
        if key == "store_commerce" and shadow:
            n = s.scalar(select(func.count()).select_from(m.Listing).where(
                m.Listing.state.in_(["active", "published", "live"])))
            if n:
                breaches.append(f"{n} listing(s) live while the phase is shadow")
        if key in ("growth", "finance"):
            spent = s.scalar(select(func.coalesce(func.sum(m.CostEntry.amount_cad), 0.0)).where(
                m.CostEntry.kind == "ads", m.CostEntry.at >= since)) or 0.0
            if spent > 0:
                try:
                    from ..build2.executor import gate_states

                    ad_open = bool(gate_states(db).get("ad_authority", {}).get("open"))
                except Exception:  # noqa: BLE001 - unreadable gate is closed
                    ad_open = False
                if not ad_open:
                    breaches.append(f"CA${spent:.2f} ad spend with ad_authority closed")
    return breaches


def compute(db, key: str, *, now: datetime | None = None, window_hours: int = 24) -> dict:
    """Every KPI of one department over the window, with guardrails applied."""
    from ..queue.durable import DEFECT, classify_dead_letter
    from ..runtime.worker import CADENCES

    charter = charters.BY_KEY[key]
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=window_hours)
    with db.session() as s:
        rows = list(s.execute(
            select(Job.id, Job.job_type, Job.inputs, Job.outputs, Job.status, Job.last_error,
                   Job.finished_at)
            .where(Job.finished_at >= since)).all())
        # last success per job type, for freshness
        last_done = dict(s.execute(
            select(Job.job_type, func.max(Job.finished_at))
            .where(Job.status == JobStatus.DONE).group_by(Job.job_type)).all())
    mine = [r for r in rows if job_department(r.job_type, r.inputs) == key]

    guard_breaches: list[str] = []
    for r in mine:
        err = (r.last_error or "").lower()
        if _status(r) == "dead" and any(g in err for g in GUARD_ERRORS):
            guard_breaches.append(f"jobs:{r.id} {r.job_type}: {err.split(':')[0]}")
    guard_breaches += department_guards(db, key, since=since)

    useful_prints: set[tuple[str, str]] = set()
    noop = generated_noop = 0
    for r in mine:
        if _status(r) != "done":
            continue
        if did_no_work(r.outputs):
            noop += 1
            if (r.inputs or {}).get("source") == "autonomy":
                generated_noop += 1
            continue
        useful_prints.add((r.job_type, fingerprint(r.outputs)))
    defects = [r for r in mine if _status(r) == "dead"
               and classify_dead_letter(r.job_type, r.last_error or "") == DEFECT]

    cadences = [(jt, period) for _n, _a, jt, period in CADENCES
                if charters.department_of(jt) == key]
    fresh = 0
    for jt, period in cadences:
        done_at = _aware(last_done.get(jt))
        if done_at is not None and (now - done_at).total_seconds() <= 2 * period:
            fresh += 1

    void = bool(guard_breaches)
    measured = bool(mine)

    def reading(value, basis="measured"):
        if void:
            return {"status": "VOID", "value": None, "basis": basis,
                    "why": "guardrail tripped: " + "; ".join(guard_breaches[:5])}
        if value is None:
            return {"status": "UNKNOWN", "value": None, "basis": "unknown",
                    "why": "no department job finished in the window"}
        return {"status": "OK", "value": value, "basis": basis}

    out = {
        "department": key, "as_of": now.isoformat(), "window_hours": window_hours,
        "kpis": {
            "useful_completions_24h": reading(len(useful_prints) if measured else None),
            "defect_dead_letters_24h": reading(len(defects) if measured else None),
            "cadence_freshness": (reading(round(fresh / len(cadences), 4))
                                  if cadences else {"status": "UNKNOWN", "value": None,
                                                    "basis": "unknown",
                                                    "why": "department has no cadence"}),
        },
        "counted": {"finished": len(mine), "useful_distinct": len(useful_prints),
                    "noop": noop, "generated_noop": generated_noop,
                    "defects": len(defects), "cadences": len(cadences),
                    "fresh_cadences": fresh},
        "guardrails": {"tripped": void, "breaches": guard_breaches[:20]},
        "kpi_definitions": [{"key": k.key, "direction": k.direction, "reads": k.reads,
                             "guardrails": list(k.guardrails)} for k in charter.kpis],
        "sources": ["jobs", "worker.CADENCES", "support_cases", "pattern_versions",
                    "listings", "cost_entries"],
    }
    return out
