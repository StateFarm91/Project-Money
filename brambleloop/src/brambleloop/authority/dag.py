"""The durable company coordinator: one work DAG for every department (F-658, F-702, F-721).

Each node (`company_work_items`) holds what the coordinator needs to survive a deploy or a
restart without anybody's memory: its dependencies, priority, owning department and executing
agent, its authority state and, once finished, its completion evidence (the job row, terminal
status and whether it did useful work). Nothing lives only in a process.

States:

    blocked            a dependency is not done (or failed: blocks only its dependants)
    awaiting_approval  the action needs the owner (a gated class, or a job type outside the
                       closed SAFE_GENERATED allowlist) -- an owner action is raised once
    approved           owner-approved gated work waiting for a phase that lets it run
    ready              every dependency done and authority satisfied: the next tick enqueues it
    enqueued           a job exists; reconciled against the job row each tick
    done | failed | refused | cancelled   terminal

Authority may be gated; initiative may not (F-702): an item awaiting the owner blocks only the
items that depend on it (F-721). Every other item -- other departments, unrelated branches --
is recomputed READY and dispatched on the same tick.

`tick(db, queue)` runs inside every COO orchestrator tick (`autonomy.orchestrator.tick`), so
READY work is recomputed automatically, every fifteen minutes and on the idle wake, by the
hosted runtime. Dispatch goes through the ordinary queue, so every job still meets
`Registry.authorize` (with the authority-class check), the handler's own gates, the spend
ceilings and the phase.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from . import classes
from .models import WorkItem, ensure_tables

TERMINAL = frozenset({"done", "failed", "refused", "cancelled"})
FAILED_LIKE = frozenset({"failed", "refused", "cancelled"})
OPEN = frozenset({"pending", "blocked", "awaiting_approval", "approved", "ready"})
MAX_DISPATCH_PER_TICK = 10
SOURCE = "company_dag"


class WorkRefused(PermissionError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _row(w: WorkItem) -> dict:
    return {"key": w.key, "department": w.department, "job_type": w.job_type,
            "action_class": w.action_class, "title": w.title, "priority": w.priority,
            "owner_agent": w.owner_agent, "submitted_by": w.submitted_by,
            "depends_on": list(w.depends_on or []), "state": w.state, "reason": w.reason,
            "requires_approval": bool(w.requires_approval), "approved_by": w.approved_by,
            "job_id": w.job_id, "evidence": dict(w.evidence or {}),
            "inputs": dict(w.inputs or {}), "sources": list(w.sources or []),
            "updated_at": _aware(w.updated_at).isoformat() if w.updated_at else None}


def _needs_approval(job_type: str) -> bool:
    from ..autonomy import charters

    return classes.is_gated(job_type) or job_type in charters.PROTECTED_JOB_TYPES or \
        job_type not in charters.SAFE_GENERATED


def submit(db, *, key: str, department: str, job_type: str, submitted_by: str,
           inputs: dict | None = None, depends_on=(), priority: int = 0, title: str = "",
           owner_agent: str | None = None, sources=(), requires_approval: bool | None = None,
           now: datetime | None = None) -> dict:
    """Add a node. Idempotent on `key`: a re-submission returns the existing node unchanged.

    `requires_approval` may only be *added* by a caller: a gated or non-allowlisted job type
    needs the owner whatever the caller says (no caller can submit its way past authority).
    """
    from ..autonomy import charters

    if not key or not job_type or not (submitted_by or "").strip():
        raise WorkRefused("a work item names its key, job type and submitter")
    if department and department not in charters.BY_KEY:
        raise WorkRefused(f"unknown department {department!r}")
    deps = [str(d) for d in (depends_on or ()) if d]
    if key in deps:
        raise WorkRefused("a work item cannot depend on itself")
    now = now or _now()
    ensure_tables(db)
    with db.session() as s:
        existing = s.scalar(select(WorkItem).where(WorkItem.key == key))
        if existing is not None:
            return _row(existing)
        if deps and _would_cycle(s, key, deps):
            raise WorkRefused(f"{key} would create a dependency cycle")
        needs = _needs_approval(job_type) or bool(requires_approval)
        w = WorkItem(key=key[:200], department=department or "", job_type=job_type,
                     action_class=classes.class_value(job_type), title=(title or "")[:500],
                     priority=int(priority), owner_agent=owner_agent or "",
                     submitted_by=submitted_by[:64], inputs=dict(inputs or {}),
                     depends_on=deps, state="pending", requires_approval=needs,
                     sources=list(sources or [])[:20], created_at=now, updated_at=now)
        s.add(w)
        s.flush()
        return _row(w)


def _would_cycle(s, key: str, deps: list[str]) -> bool:
    seen, stack = set(), list(deps)
    while stack:
        k = stack.pop()
        if k == key:
            return True
        if k in seen:
            continue
        seen.add(k)
        row = s.scalar(select(WorkItem.depends_on).where(WorkItem.key == k))
        stack.extend(row or [])
    return False


def record_mission(db, *, key: str, department: str, job_type: str, job_id: int,
                   agent: str, reason: str = "", sources=(), now: datetime | None = None) -> None:
    """The COO's mission, already enqueued through its own boundary, as an `enqueued` node so
    its completion evidence lands in the same DAG."""
    now = now or _now()
    ensure_tables(db)
    with db.session() as s:
        if s.scalar(select(WorkItem.id).where(WorkItem.key == key)) is not None:
            return
        s.add(WorkItem(key=key[:200], department=department, job_type=job_type,
                       action_class=classes.class_value(job_type), title=reason[:500],
                       owner_agent=agent, submitted_by="coo", state="enqueued",
                       reason="enqueued by the COO mission boundary", job_id=job_id,
                       sources=list(sources or [])[:20], created_at=now, updated_at=now))


def approve(db, key: str, *, approved_by: str, step_up_verified: bool, approval_ref: str = "",
            now: datetime | None = None) -> dict:
    """The owner approves one awaiting item (behind the Command Center step-up)."""
    from ..agents.registry import DEFAULT_AGENTS, Registry

    actor = " ".join((approved_by or "").split()).casefold()
    if actor != "owner" or actor in {a["name"] for a in DEFAULT_AGENTS}:
        raise WorkRefused(f"{approved_by!r} cannot approve: only the owner approves")
    if step_up_verified is not True:
        raise WorkRefused("approval needs the owner's fresh step-up")
    now = now or _now()
    ensure_tables(db)
    with db.session() as s:
        w = s.scalar(select(WorkItem).where(WorkItem.key == key))
        if w is None:
            raise WorkRefused(f"no work item {key!r}")
        if w.state in TERMINAL or w.state == "enqueued":
            raise WorkRefused(f"{key} is {w.state}; nothing to approve")
        if w.action_class == classes.ActionClass.DEPLOY.value:
            raise WorkRefused("DEPLOY is the owner's production_deploy gate, not a work item")
        w.approved_by, w.approval_ref, w.updated_at = "owner", (approval_ref or "")[:120], now
        out = _row(w)
    Registry(db).audit("owner", "work_item.approved", artifact=f"company_work_items:{key}",
                       detail={"job_type": out["job_type"], "class": out["action_class"],
                               "ref": approval_ref})
    return out


def cancel(db, key: str, *, by: str, reason: str = "", now: datetime | None = None) -> None:
    ensure_tables(db)
    with db.session() as s:
        w = s.scalar(select(WorkItem).where(WorkItem.key == key))
        if w is None or w.state in TERMINAL:
            return
        w.state, w.reason, w.updated_at = "cancelled", f"cancelled by {by}: {reason}"[:500], \
            now or _now()


def known_failure(db, fingerprint: str) -> str | None:
    """The key of a failed/refused item carrying this fingerprint, if any."""
    ensure_tables(db)
    with db.session() as s:
        for w in s.scalars(select(WorkItem).where(WorkItem.state.in_(["failed", "refused"]))
                           .order_by(WorkItem.id.desc()).limit(500)):
            if (w.inputs or {}).get("fingerprint") == fingerprint:
                return w.key
    return None


# ---- the coordinator loop ---------------------------------------------------------------

def reconcile(db, *, now: datetime | None = None) -> dict:
    """Close every enqueued node whose job reached a terminal state, with its evidence."""
    from ..autonomy.kpis import did_no_work
    from ..core.models import Job

    now = now or _now()
    counts = {"done": 0, "failed": 0, "open": 0}
    ensure_tables(db)
    with db.session() as s:
        for w in s.scalars(select(WorkItem).where(WorkItem.state == "enqueued")):
            job = s.get(Job, w.job_id) if w.job_id else None
            status = getattr(getattr(job, "status", None), "value", None)
            if job is not None and status in ("pending", "running", "failed"):
                counts["open"] += 1
                continue
            outputs = dict(job.outputs or {}) if job is not None else {}
            ok = status == "done"
            w.state = "done" if ok else "failed"
            w.evidence = {"job_id": w.job_id, "job_status": status or "missing",
                          "did_no_work": did_no_work(outputs, w.job_type) if ok else None,
                          "output_keys": sorted(outputs)[:20],
                          "error": "" if ok else ((job.last_error or "")[:300] if job
                                                  else "job row missing"),
                          "closed_at": now.isoformat()}
            w.reason = "completed" if ok else "job failed; dependants stay blocked"
            w.updated_at = now
            counts["done" if ok else "failed"] += 1
    return counts


def _policy_allows(db, w: WorkItem, agent: str | None, now: datetime) -> tuple[bool, str, int | None]:
    """Whether an owner AuthorityPolicy lets this gated item run without per-item approval."""
    if not agent:
        return False, "no executing agent", None
    from . import policy

    eff = policy.effective_level(db, agent, w.job_type, now=now)
    if eff["effective"] == "standing":
        return True, "owner policy (standing)", eff["policy_id"]
    if eff["effective"] == "bounded":
        pol = next((p for p in policy.active_policies(db, agent=agent)
                    if p["id"] == eff["policy_id"]), None)
        cap = int((pol or {}).get("max_per_day") or 0)
        today = now.date().isoformat()
        with db.session() as s:
            used = sum(1 for e in s.scalars(select(WorkItem.evidence).where(
                WorkItem.state.in_(["enqueued", "done", "failed"])))
                if (e or {}).get("authorised_by_policy") == eff["policy_id"]
                and str((e or {}).get("dispatched_at", ""))[:10] == today)
        if used < cap:
            return True, f"owner policy (bounded {used}/{cap} today)", eff["policy_id"]
        return False, f"owner policy bound reached ({used}/{cap} today)", None
    why = eff["why"] + (f"; would allow {eff['shadow_would']}" if eff.get("shadow_would")
                        else "")
    return False, why, None


def _agent(w: WorkItem) -> str | None:
    return _agent_for_row({"owner_agent": w.owner_agent, "job_type": w.job_type})


def _agent_for_row(item: dict) -> str | None:
    if item.get("owner_agent"):
        return item["owner_agent"]
    from ..autonomy.orchestrator import _agent_for

    return _agent_for(item["job_type"])


def _set(db, key: str, *, state: str, reason: str, now: datetime, **fields) -> None:
    with db.session() as s:
        w = s.scalar(select(WorkItem).where(WorkItem.key == key))
        if w is None:
            return
        w.state, w.reason, w.updated_at = state, reason[:500], now
        for k, v in fields.items():
            setattr(w, k, v)


def _raise_owner_action(s, w: WorkItem) -> None:
    from ..core.models import OwnerAction

    rk = (w.inputs or {}).get("requirement_key") or f"dag:{w.key}"
    if s.scalar(select(OwnerAction.id).where(OwnerAction.requirement_key == rk,
                                             OwnerAction.done == False)) is None:  # noqa: E712
        s.add(OwnerAction(
            requirement_key=rk[:500],
            action=f"Approve {w.job_type} ({w.action_class}) for {w.department or 'company'}: "
                   f"{w.title or w.key}"[:900],
            reason=(f"{w.action_class} work needs the owner before it runs; only the work "
                    "that depends on it waits (F-702/F-721)"),
            max_cost_cad=float((w.inputs or {}).get("max_cost_cad") or 0.0), minutes=2,
            consequence_of_delay="only this item and its dependants wait",
            blocks=w.key[:500]))


def _phase(db) -> str:
    from .policy import _phase as ph

    return ph(db)


def recompute(db, *, now: datetime | None = None) -> dict:
    """Recompute every open node's state from its dependencies and authority."""
    from .policy import EFFECTIVE_PHASES

    now = now or _now()
    ensure_tables(db)
    phase = _phase(db)
    counts: dict[str, int] = {}
    with db.session() as s:
        items = list(s.scalars(select(WorkItem).where(WorkItem.state.in_(list(OPEN)))))
        dep_keys = {k for w in items for k in (w.depends_on or [])}
        states = dict(s.execute(select(WorkItem.key, WorkItem.state).where(
            WorkItem.key.in_(list(dep_keys)))).all()) if dep_keys else {}
        for w in items:
            state, reason = "ready", "dependencies done; authority satisfied"
            missing = [d for d in (w.depends_on or []) if d not in states]
            failed = [d for d in (w.depends_on or []) if states.get(d) in FAILED_LIKE]
            waiting = [d for d in (w.depends_on or []) if states.get(d) not in
                       (None, "done") and d not in failed]
            if missing:
                state, reason = "blocked", f"unknown dependency {missing[:3]}"
            elif failed:
                state, reason = "blocked", (f"dependency {failed[:3]} did not complete; "
                                            "only this branch waits")
            elif waiting:
                state, reason = "blocked", f"waiting on {waiting[:5]}"
            elif w.requires_approval and w.approved_by != "owner":
                ok, why, pid = (_policy_allows(db, w, _agent(w), now)
                                if classes.is_gated(w.job_type) else (False, "", None))
                if ok:
                    reason = why
                    w.evidence = {**(w.evidence or {}), "authorised_by_policy": pid}
                else:
                    state = "awaiting_approval"
                    reason = ("owner approval required" + (f" ({why})" if why else "")
                              + "; only dependants wait")
                    _raise_owner_action(s, w)
            elif classes.is_gated(w.job_type) and phase not in EFFECTIVE_PHASES:
                state, reason = "approved", (f"owner-approved; phase {phase} does not run "
                                             f"{w.action_class} work yet (shadow first)")
            if state != w.state or reason != w.reason:
                w.state, w.reason, w.updated_at = state, reason[:500], now
            counts[state] = counts.get(state, 0) + 1
    return counts


def dispatch(db, queue, *, now: datetime | None = None,
             limit: int = MAX_DISPATCH_PER_TICK) -> list[dict]:
    """Enqueue READY nodes, highest priority first, through the ordinary queue."""
    from ..queue.durable import DuplicateJob
    from . import constitution

    now = now or _now()
    out: list[dict] = []
    with db.session() as s:
        ready = [(w.key, w.priority) for w in s.scalars(
            select(WorkItem).where(WorkItem.state == "ready")
            .order_by(WorkItem.priority.desc(), WorkItem.id).limit(limit))]
    for key, _p in ready:
        with db.session() as s:
            w = s.scalar(select(WorkItem).where(WorkItem.key == key))
            if w is None or w.state != "ready":
                continue
            item = _row(w)
        agent = _agent_for_row(item)
        if agent is None:
            _set(db, key, state="refused", reason="no registered agent holds it", now=now)
            out.append({"key": key, "state": "refused"})
            continue
        verdict = constitution.evaluate(db, {
            "actor": item["submitted_by"], "agent": agent, "job_type": item["job_type"],
            "department": item["department"], "key": key, "title": item["title"],
            **{k: v for k, v in item["inputs"].items() if k in (
                "cost_cad", "provenance", "claims", "metrics", "customer_harm",
                "hypothesis", "success_metric", "falsified_if", "kind", "fingerprint",
                "addresses_failure", "skip_validation", "description")}}, now=now)
        if not verdict["allowed"]:
            _set(db, key, state="refused", now=now, reason="constitution: " + "; ".join(
                f"{x['clause']}: {x['why']}" for x in verdict["violations"]))
            out.append({"key": key, "state": "refused", "violations": verdict["violations"]})
            continue
        inputs = {**item["inputs"], "source": SOURCE, "work_item": key,
                  "department": item["department"]}
        try:
            job = queue.enqueue(agent, item["job_type"], inputs,
                                idempotency_key=f"dag:{key}"[:200])
            job_id = job.id
        except DuplicateJob as dup:
            job_id = dup.existing_id
        _set(db, key, state="enqueued", reason=f"enqueued as jobs:{job_id}", now=now,
             job_id=job_id, owner_agent=agent,
             evidence={**item["evidence"], "dispatched_at": now.isoformat()})
        out.append({"key": key, "state": "enqueued", "job_id": job_id, "agent": agent})
    return out


def tick(db, queue=None, *, now: datetime | None = None) -> dict:
    """reconcile -> recompute -> dispatch -> recompute. Safe to call as often as you like."""
    from ..queue.durable import JobQueue

    now = now or _now()
    queue = queue or JobQueue(db)
    report = {"reconciled": reconcile(db, now=now)}
    report["before"] = recompute(db, now=now)
    report["dispatched"] = dispatch(db, queue, now=now)
    report["states"] = recompute(db, now=now)
    return report


def items(db, *, state: str | None = None, limit: int = 200) -> list[dict]:
    ensure_tables(db)
    with db.session() as s:
        q = select(WorkItem).order_by(WorkItem.priority.desc(), WorkItem.id).limit(limit)
        if state:
            q = q.where(WorkItem.state == state)
        return [_row(w) for w in s.scalars(q)]


def summary(db) -> dict:
    """Provider-contract summary of the company DAG (for the Command Center)."""
    try:
        ensure_tables(db)
        with db.session() as s:
            rows = list(s.execute(select(WorkItem.state, WorkItem.updated_at)).all())
        by: dict[str, int] = {}
        for r in rows:
            by[r.state] = by.get(r.state, 0) + 1
        latest = max((_aware(r.updated_at) for r in rows if r.updated_at), default=None)
        waiting = items(db, state="awaiting_approval", limit=20)
        return {"status": "OK" if rows else "UNKNOWN",
                "as_of": latest.isoformat() if latest else None,
                "basis": "measured" if rows else "unknown",
                "reason": "" if rows else "no work items recorded yet",
                "counts": by, "items": waiting, "sources": ["company_work_items"]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": [], "reason": f"{type(exc).__name__}"}
