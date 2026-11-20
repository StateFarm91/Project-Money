"""F-550: the permanent Etsy loop's missing pieces -- a daily exception report and a
quarterly deep audit. Read-only: it reads rows the runtime already wrote and writes one audit
row; it makes no Etsy call and changes no listing.

* **daily** (`daily`): what needs a look today -- open incidents in the Etsy/listing families,
  Etsy-side jobs dead-lettered in 24 h, Etsy-side cadences that have not completed within
  two periods, the latest Etsy probe answer -- each as an exception with the evidence row.
* **quarterly** (`quarterly`): the 90-day deep audit -- incidents opened and resolved by
  family, Etsy-side job completions and dead letters by type, recorded listing outcomes
  (UNMEASURED when none), open owner actions that block Etsy work.

`run(db)` writes the daily report every time it is called (from the daily
`commerce.readings` cadence) and the quarterly audit once per calendar quarter.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

DAILY_ACTION = "etsy.daily_exceptions"
QUARTERLY_ACTION = "etsy.quarterly_audit"
INCIDENT_FAMILIES = ("taxonomy-drift:", "etsy", "listing", "policy", "store.", "provider-health:")
JOB_PREFIXES = ("etsy.", "listing.", "store.", "commerce.")
CADENCES = ("etsy_probe", "etsy_taxonomy", "commerce_readings", "policy_watch",
            "etsy_credential_health", "etsy_shop_snapshot")


def _aware(v):
    return None if v is None else (v if v.tzinfo else v.replace(tzinfo=timezone.utc))


def daily(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, Incident, Job, JobStatus
    from ..runtime.worker import CADENCES as ALL, cadence_seconds

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    exceptions = []
    with db.session() as s:
        for inc in s.scalars(select(Incident).where(Incident.resolved == False)):  # noqa: E712
            if (inc.signature or "").startswith(INCIDENT_FAMILIES):
                exceptions.append({"kind": "incident", "ref": inc.signature,
                                   "severity": inc.severity,
                                   "summary": (inc.summary or "")[:200]})
        dead = list(s.execute(select(Job.job_type, Job.id).where(
            Job.status == JobStatus.DEAD, Job.finished_at >= since)).all())
        for jt, jid in dead:
            if jt.startswith(JOB_PREFIXES):
                exceptions.append({"kind": "dead_letter", "ref": f"job:{jid}", "job_type": jt})
        jobtype = {n: jt for n, _a, jt, _p in ALL}
        for name in CADENCES:
            jt = jobtype.get(name)
            if jt is None:
                continue
            period = cadence_seconds(name) or 0
            last = _aware(s.scalar(select(Job.finished_at).where(
                Job.job_type == jt, Job.status == JobStatus.DONE)
                .order_by(desc(Job.finished_at)).limit(1)))
            if last is None or (now - last).total_seconds() > 2 * period:
                exceptions.append({"kind": "stale_cadence", "ref": name, "job_type": jt,
                                   "last_done": last.isoformat() if last else None})
        probe = s.scalar(select(AuditLog).where(AuditLog.action == "etsy.probe")
                         .order_by(desc(AuditLog.id)).limit(1))
    probe_state = ("UNKNOWN" if probe is None else
                   "ok" if (probe.detail or {}).get("ok") else "failing")
    if probe_state != "ok":
        exceptions.append({"kind": "etsy_probe", "ref": "etsy.probe", "state": probe_state})
    return {"as_of": now.isoformat(), "exceptions": exceptions, "count": len(exceptions),
            "etsy_probe": probe_state,
            "note": "read-only: no Etsy call, no listing change; each exception names its row"}


def quarterly(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import Incident, Job, JobStatus, ListingOutcome, OwnerAction

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=90)
    fam: dict[str, dict] = {}
    with db.session() as s:
        for inc in s.scalars(select(Incident)):
            sig = inc.signature or ""
            f = next((p for p in INCIDENT_FAMILIES if sig.startswith(p)), None)
            if f is None:
                continue
            row = fam.setdefault(f, {"opened": 0, "resolved": 0, "open_now": 0})
            first = _aware(inc.at)
            if first is None or first >= since:
                row["opened"] += 1
            if inc.resolved:
                row["resolved"] += 1
            else:
                row["open_now"] += 1
        jobs: dict[str, dict] = {}
        for jt, st in s.execute(select(Job.job_type, Job.status).where(
                Job.finished_at >= since)).all():
            if not jt.startswith(JOB_PREFIXES):
                continue
            r = jobs.setdefault(jt, {"done": 0, "dead": 0})
            if st == JobStatus.DONE:
                r["done"] += 1
            elif st == JobStatus.DEAD:
                r["dead"] += 1
        outcomes = list(s.scalars(select(ListingOutcome)))
        blockers = [a.action[:160] for a in s.scalars(select(OwnerAction).where(
            OwnerAction.done == False))  # noqa: E712
            if any(w in (a.action or "").lower() for w in ("etsy", "listing", "shop"))]
    return {"as_of": now.isoformat(), "window_days": 90, "incidents_by_family": fam,
            "jobs_by_type": dict(sorted(jobs.items())),
            "listing_outcomes": ({"periods": len(outcomes),
                                  "visits": sum(int(o.visits or 0) for o in outcomes),
                                  "orders_known": sum(1 for o in outcomes if o.orders is not None)}
                                 if outcomes else "UNMEASURED"),
            "owner_actions_blocking_etsy": blockers}


def _quarter(d: datetime) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def run(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    d = daily(db, now=now)
    out = {"daily": {"count": d["count"]}}
    with db.session() as s:
        s.add(AuditLog(actor="store_operator", action=DAILY_ACTION, at=now, detail=d))
        q = _quarter(now)
        done = any((r.detail or {}).get("quarter") == q for r in s.scalars(
            select(AuditLog).where(AuditLog.action == QUARTERLY_ACTION)))
    if not done:
        qa = quarterly(db, now=now)
        with db.session() as s:
            s.add(AuditLog(actor="store_operator", action=QUARTERLY_ACTION, at=now,
                           detail={"quarter": q, **qa}))
        out["quarterly"] = q
    return out
