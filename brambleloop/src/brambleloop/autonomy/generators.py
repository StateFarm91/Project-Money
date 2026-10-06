"""Evidence-driven work generation for an idle department (PRIORITY ZERO).

Every candidate names the durable rows that justify it. Nothing here is random and nothing is
"look busy" work: there are exactly three sources, in descending value.

1. **Handoff** -- a producer department wrote rows (a new pattern version, a support case, a
   cost entry, a dead letter...) after the consumer department's last successful run of the
   job type that consumes them. That is downstream work that exists and has not been done.
2. **Overdue cadence** -- one of the department's safe cadences has no success inside two of
   its periods (the scheduler fired and it failed, it was thrash-suspended, or the container
   was down). Catch-up work keyed on the last success, so it cannot repeat.
3. **Self-review** -- the department's KPIs measured and persisted to company memory, at most
   once per `review_hours`. Bounded, deterministic, spends nothing, and it is what turns a
   department's quiet day into a measured reading and (on regression) a routed lesson.

Owner-gated or protected work is never returned as runnable: a generator that sees work only
the owner can authorise returns it with ``protected=True`` and the orchestrator converts it
into an owner approval item.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..core import models as m
from ..core.models import Job, JobStatus
from . import charters


@dataclass
class Candidate:
    department: str
    job_type: str
    value: int
    source: str                 # handoff | overdue | review | approval
    reason: str
    fingerprint: str
    evidence: list[str] = field(default_factory=list)
    inputs: dict = field(default_factory=dict)
    protected: bool = False
    approval: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"department": self.department, "job_type": self.job_type, "value": self.value,
                "source": self.source, "reason": self.reason,
                "fingerprint": self.fingerprint, "evidence": list(self.evidence),
                "protected": self.protected}


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass
class Snapshot:
    """One read of the queue shared by every department's generator in a tick."""

    now: datetime
    open_by_type: dict[str, int]
    last_done: dict[str, tuple[datetime, int]]        # job_type -> (finished_at, job id)
    open_by_department: dict[str, int]

    @classmethod
    def read(cls, db, now: datetime) -> "Snapshot":
        from .kpis import job_department

        with db.session() as s:
            open_rows = list(s.execute(select(Job.job_type, Job.inputs).where(
                Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED]))))
            last = s.execute(select(Job.job_type, func.max(Job.finished_at), func.max(Job.id))
                             .where(Job.status == JobStatus.DONE)
                             .group_by(Job.job_type)).all()
        open_by_type: dict[str, int] = {}
        open_by_dept: dict[str, int] = {}
        for jt, inputs in open_rows:
            open_by_type[jt] = open_by_type.get(jt, 0) + 1
            # The orchestrator itself is not department work; a pending tick must not make
            # the executive look busy forever.
            if jt == "autonomy.orchestrate":
                continue
            d = job_department(jt, inputs)
            if d:
                open_by_dept[d] = open_by_dept.get(d, 0) + 1
        return cls(now=now, open_by_type=open_by_type,
                   last_done={jt: (_aware(at), int(i)) for jt, at, i in last if at},
                   open_by_department=open_by_dept)


def _model(name: str):
    return getattr(m, name)


def handoff_candidates(db, charter: charters.Charter, snap: Snapshot) -> list[Candidate]:
    out: list[Candidate] = []
    for h in charter.consumes:
        model = _model(h.table)
        col = getattr(model, h.time_column)
        last = snap.last_done.get(h.consumer_job_type)
        q = select(func.count(), func.max(model.id))
        for attr, value in h.where:
            q = q.where(getattr(model, attr) == value)
        if last is not None:
            q = q.where(col > last[0])
        with db.session() as s:
            n, max_id = s.execute(q).one()
        if not n:
            continue
        out.append(Candidate(
            department=charter.key, job_type=h.consumer_job_type,
            value=70 + min(int(n), 20), source="handoff",
            reason=f"{n} {h.table} row(s): {h.why}",
            fingerprint=f"handoff:{h.consumer_job_type}:{h.table}:{max_id}",
            evidence=[f"{model.__tablename__}:<= {max_id} (n={n})",
                      f"jobs:last {h.consumer_job_type} done "
                      f"{last[0].isoformat() if last else 'never'}"],
            inputs={"handoff": {"table": model.__tablename__, "max_id": max_id, "rows": n}}))
    return out


def overdue_candidates(charter: charters.Charter, snap: Snapshot) -> list[Candidate]:
    from ..runtime.worker import CADENCES

    out: list[Candidate] = []
    for name, _agent, jt, period in CADENCES:
        if jt not in charter.generatable or jt.startswith("autonomy."):
            continue
        if snap.open_by_type.get(jt):
            continue
        last = snap.last_done.get(jt)
        if last is not None and (snap.now - last[0]).total_seconds() <= 2 * period:
            continue
        age = "never succeeded" if last is None else \
            f"last success {(snap.now - last[0]).total_seconds() / 3600:.1f} h ago"
        out.append(Candidate(
            department=charter.key, job_type=jt, value=50, source="overdue",
            reason=f"cadence {name} overdue: {age}, period {period // 3600 or period} "
                   f"{'h' if period >= 3600 else 's'}",
            fingerprint=f"overdue:{jt}:{last[1] if last else 'never'}",
            evidence=[f"jobs:{last[1]}" if last else f"jobs:none done for {jt}",
                      f"worker.CADENCES:{name}"]))
    return out


def review_candidate(charter: charters.Charter, snap: Snapshot) -> Candidate:
    window = int(snap.now.timestamp() // (charter.review_hours * 3600))
    return Candidate(
        department=charter.key, job_type="autonomy.department_review", value=10,
        source="review",
        reason=f"no other ready work; measure {charter.name} KPIs and persist lessons "
               f"(at most every {charter.review_hours} h)",
        fingerprint=f"review:{charter.key}:{window}",
        evidence=[f"jobs:open for {charter.key}=0"],
        inputs={"department": charter.key})


def approval_candidates(db, charter: charters.Charter, snap: Snapshot) -> list[Candidate]:
    """Protected work the department has prepared and only the owner may authorise."""
    out: list[Candidate] = []
    if charter.key == "store_commerce":
        with db.session() as s:
            drafts = list(s.execute(select(m.Listing.id, m.Listing.product_slug,
                                           m.Listing.version)
                                    .where(m.Listing.state == "draft",
                                           m.Listing.etsy_listing_id == "")
                                    .order_by(m.Listing.id)).all())
            certified = {(slug, v) for slug, v in s.execute(
                select(m.Product.slug, m.PatternVersion.version)
                .join(m.PatternVersion, m.PatternVersion.product_id == m.Product.id)
                .where(m.PatternVersion.certified == True)).all()}  # noqa: E712
        ready = [d for d in drafts if (d.product_slug, d.version) in certified]
        if ready:
            out.append(Candidate(
                department=charter.key, job_type="store.publish", value=0,
                source="approval", protected=True,
                reason=f"{len(ready)} listing draft(s) from certified releases are prepared; "
                       "publication is owner-authorised per release",
                fingerprint=f"approval:store.publish:{len(ready)}:{ready[-1].id}",
                evidence=[f"listings:{d.id}" for d in ready[:20]],
                approval={"requirement_key": "autonomy:store_commerce:publication_review",
                          "action": (f"Review {len(ready)} prepared listing draft(s) from "
                                     "certified releases and decide whether to authorise "
                                     "publication (Store Preview first)"),
                          "reason": "publishing is a protected action; the company prepared "
                                    "it and will not perform it without owner authority",
                          "max_cost_cad": 0.0, "minutes": 10,
                          "consequence": "prepared listings stay drafts; no revenue starts",
                          "blocks": "store_commerce publication"}))
    return out


def executive_candidates(db, charter: charters.Charter, snap: Snapshot) -> list[Candidate]:
    """The morning handoff (F-896): once per day, the first tick after 11:00 UTC."""
    if charter.key != "executive":
        return []
    from . import memory

    day = morning_window(snap.now)
    if memory.get(db, f"brief:{day}") is not None:
        return []
    return [Candidate(department=charter.key, job_type="autonomy.morning_handoff", value=80,
                      source="handoff",
                      reason=f"no morning brief yet for {day}; summarise the unattended hours",
                      fingerprint=f"brief:{day}", evidence=[f"company_memory:brief:{day} absent"])]


def candidates(db, charter: charters.Charter, snap: Snapshot) -> list[Candidate]:
    """Every candidate for one department, best first. Raises on a read failure: the caller
    isolates one department's failure from the others."""
    cands = executive_candidates(db, charter, snap)
    cands += handoff_candidates(db, charter, snap) + overdue_candidates(charter, snap)
    cands += approval_candidates(db, charter, snap)
    cands.append(review_candidate(charter, snap))
    cands.sort(key=lambda c: -c.value)
    return cands


def morning_window(now: datetime, hour_utc: int = 11) -> str:
    """The brief's date: the morning after the night it covers (11:00 UTC ~ 07:00 Toronto)."""
    day = (now - timedelta(hours=hour_utc)).date()
    return day.isoformat()
