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


# ---------------------------------------------------------------------------
# v1.1 integrator wiring: the departments' own `next_work` providers (lanes B, E, G, H).
#
# Each provider lists the work its department believes is due, in its own shape. Only items
# that are (a) internal -- no owner, no external effect, no spend, not blocked -- and (b) map
# to an existing GREEN job type in the department's `generatable` allowlist become runnable
# candidates. Everything else (owner actions, gated items, spend, items with no handler) is
# never turned into a job here: the provider's own module already raises its owner actions
# (ads refresh, disconnected finance sources), and the orchestrator's enqueue boundary would
# refuse a protected type regardless.
PROVIDER_VALUE = 60                # below a durable handoff (70+), above an overdue cadence
PROVIDER_MIN_GAP_S = 60 * 60       # a provider never re-asks for a job that succeeded <1 h ago


def _learn_item(item: dict) -> tuple[str, str] | None:
    jt = item.get("job_type")
    if jt in ("improve.sandbox", "improve.monitor", "learn.scan"):
        return jt, str(item.get("key") or item.get("kind"))
    return None


def _finance_item(item: dict) -> tuple[str, str] | None:
    # The Accountant cycle posts, reconciles, detects anomalies and checks the close; it is
    # the job that does each of these three kinds. Investigations and month-end locks are
    # decisions, and connect_source is an owner action -- none of them is queued.
    if item.get("kind") in ("run_cycle", "post_rows", "reconcile") and item.get("ready") \
            and not item.get("blocked_by"):
        return "finance.accounting.cycle", str(item.get("id"))
    return None


def _seo_item(item: dict) -> tuple[str, str] | None:
    if item.get("kind") != "internal" or item.get("external_effect") or item.get("gated_by"):
        return None
    key = str(item.get("key") or "")
    if key == "seo.run_cycle" or key.startswith("seo.review:"):
        return "seo.cycle", key
    return None


def _ads_item(item: dict) -> tuple[str, str] | None:
    if item.get("kind") != "internal" or item.get("blocked_by") or \
            float(item.get("spend_cad") or 0.0) != 0.0:
        return None
    if item.get("key") == "ads.eligibility_tick":
        return "marketing.ads_readiness", "ads.eligibility_tick"
    return None


def _visual_item(item: dict) -> tuple[str, str] | None:
    # Visual R&D (W3 lane H): every item is internal and GREEN by contract; one handler,
    # `visual.rnd.cycle`, runs the whole deterministic cycle. Paid challengers never appear as
    # items (they wait for an owner decision), and a provider error is not work.
    # H2 adds hero_calibrate / hero_challenge items (internal, free) run by the same cycle.
    kind = str(item.get("kind") or "")
    if item.get("green") is not True or kind.endswith("provider_error") or \
            "paid" in kind or str(item.get("state") or "") == "GATED_SPEND" or \
            float(item.get("spend_cad") or 0.0) != 0.0 or item.get("external_effect"):
        return None
    if item.get("job_type") == "visual.rnd.cycle" or (
            not item.get("job_type") and kind.split(".")[-1] in ("hero_calibrate",
                                                                 "hero_challenge")):
        return "visual.rnd.cycle", str(item.get("key") or kind)
    return None


# department -> [(provider label, module, function, adapter)]
PROVIDERS: dict[str, tuple[tuple[str, str, str, object], ...]] = {
    "learn": (("learn", "brambleloop.learn.improvement_status", "next_work", _learn_item),),
    "finance": (("finance", "brambleloop.finance.accounting.dashboard", "next_work",
                 _finance_item),),
    "store_commerce": (("seo", "brambleloop.seo.status", "next_work", _seo_item),),
    "growth": (("ads", "brambleloop.growth.ads_readiness", "next_work", _ads_item),),
    "visual": (("visual_rnd", "brambleloop.visual.rnd.status", "next_work", _visual_item),),
}


def provider_module(module: str):
    """Import a provider module by STATIC import statements, so the C-65 reachability rule
    (an AST walk of imports from the runtime roots) sees every provider the orchestrator and
    Laura actually call (closure K15: F-913/F-914/F-915/F-927, seo.status,
    learn.improvement_status). An unknown module falls back to importlib."""
    if module == "brambleloop.learn.improvement_status":
        from ..learn import improvement_status as mod
    elif module == "brambleloop.finance.accounting.dashboard":
        from ..finance.accounting import dashboard as mod
    elif module == "brambleloop.seo.status":
        from ..seo import status as mod
    elif module == "brambleloop.growth.ads_readiness":
        from ..growth import ads_readiness as mod
    elif module == "brambleloop.visual.rnd.status":
        from ..visual.rnd import status as mod
    elif module == "brambleloop.ops.slo":
        from ..ops import slo as mod
    elif module == "brambleloop.autonomy.status":
        from . import status as mod
    else:
        import importlib

        mod = importlib.import_module(module)
    return mod


def provider_candidates(db, charter: charters.Charter, snap: Snapshot) -> list[Candidate]:
    """Runnable candidates from the department's own next_work provider(s). Never raises: a
    broken provider costs only its own candidates."""
    out: list[Candidate] = []
    seen: set[str] = set()
    for label, module, fn, adapt in PROVIDERS.get(charter.key, ()):
        try:
            items = getattr(provider_module(module), fn)(db) or []
        except Exception:  # noqa: BLE001 - a provider failure never stops the department
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            mapped = adapt(item)
            if mapped is None:
                continue
            jt, item_key = mapped
            if jt in charters.PROTECTED_JOB_TYPES or jt not in charter.generatable \
                    or jt in seen or snap.open_by_type.get(jt):
                continue
            last = snap.last_done.get(jt)
            if last is not None and (snap.now - last[0]).total_seconds() < PROVIDER_MIN_GAP_S:
                continue
            seen.add(jt)
            reason = str(item.get("reason") or item.get("why") or item.get("title")
                         or item_key)[:200]
            out.append(Candidate(
                department=charter.key, job_type=jt, value=PROVIDER_VALUE, source="provider",
                reason=f"{label}.next_work: {reason}",
                # One mission per run of the job: the same indication after the job ran
                # again is new evidence; the same indication before it is not.
                fingerprint=f"provider:{label}:{item_key}:{last[1] if last else 'never'}",
                evidence=[f"{module}.{fn}:{item_key}",
                          f"jobs:{last[1]}" if last else f"jobs:none done for {jt}"],
                inputs={"provider": {"name": label, "item": item_key}}))
    return out


def candidates(db, charter: charters.Charter, snap: Snapshot) -> list[Candidate]:
    """Every candidate for one department, best first. Raises on a read failure: the caller
    isolates one department's failure from the others."""
    cands = executive_candidates(db, charter, snap)
    cands += handoff_candidates(db, charter, snap) + overdue_candidates(charter, snap)
    cands += provider_candidates(db, charter, snap)
    cands += approval_candidates(db, charter, snap)
    cands.append(review_candidate(charter, snap))
    cands.sort(key=lambda c: -c.value)
    return cands


def morning_window(now: datetime, hour_utc: int = 11) -> str:
    """The brief's date: the morning after the night it covers (11:00 UTC ~ 07:00 Toronto)."""
    day = (now - timedelta(hours=hour_utc)).date()
    return day.isoformat()
