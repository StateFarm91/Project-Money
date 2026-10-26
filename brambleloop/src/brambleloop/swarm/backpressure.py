"""F-490: conflicts, regressions and failures slow the swarm down, not only duplication.

The governor's parallelism advice turned on one input -- whether added workers duplicated
work -- and spend spikes paused an agent. A burst of failing jobs or a fresh breakage left
concurrency where it was, so more workers kept producing more failures. Here two measured
triggers return the pool to one worker (`scale_down`), whatever the governor last advised:

* **defect dead letters** -- jobs that died in the last `WINDOW` and are defects by the one
  dead-letter classifier (`queue.durable.classify_dead_letter`; deliberate refusals such as
  shadow-mode publication are the guard working and never count), at least `DEAD_LIMIT`;
* **fresh severe incidents** -- unresolved P0/P1 incidents opened in the last `INCIDENT_WINDOW`
  (a regression, a halted publication, a failing contract), at least one.

Resource saturation already returns the pool to one in `swarm.capacity.worker_target` (F-470).
An unreadable input is reported and is not pressure; it never raises concurrency either.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

WINDOW = timedelta(hours=1)
DEAD_LIMIT = 3
INCIDENT_WINDOW = timedelta(hours=6)
SEVERE = ("P0", "P1")


def _aware(v):
    return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)


def read(db, *, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import Incident, Job, JobStatus
    from ..queue.durable import DEFECT, classify_dead_letter

    now = now or datetime.now(timezone.utc)
    triggers, unreadable = [], []
    try:
        with db.session() as s:
            dead = [(j.id, j.job_type, j.last_error or "") for j in s.scalars(
                select(Job).where(Job.status == JobStatus.DEAD,
                                  Job.finished_at >= now - WINDOW))]
        defects = [d for d in dead if classify_dead_letter(d[1], d[2]) == DEFECT]
        if len(defects) >= DEAD_LIMIT:
            triggers.append({"trigger": "defect_dead_letters", "count": len(defects),
                             "jobs": [d[0] for d in defects][:10],
                             "why": f"{len(defects)} defect dead letters in the last hour"})
    except Exception as exc:  # noqa: BLE001
        unreadable.append(f"dead letters: {type(exc).__name__}")
    try:
        with db.session() as s:
            fresh = [(i.id, i.severity, i.signature) for i in s.scalars(
                select(Incident).where(Incident.resolved == False,  # noqa: E712
                                       Incident.severity.in_(SEVERE),
                                       Incident.at >= now - INCIDENT_WINDOW))]
        if fresh:
            triggers.append({"trigger": "fresh_severe_incidents", "count": len(fresh),
                             "incidents": [f"{i[1]} {i[2]}" for i in fresh][:10],
                             "why": f"{len(fresh)} unresolved P0/P1 incident(s) in 6 hours"})
    except Exception as exc:  # noqa: BLE001
        unreadable.append(f"incidents: {type(exc).__name__}")
    return {"pressure": bool(triggers), "triggers": triggers, "unreadable": unreadable}
