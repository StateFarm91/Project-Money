"""The Executive Orchestrator (F-893, F-894, F-895; PRIORITY ZERO).

One scheduled job (`autonomy.orchestrate`, every fifteen minutes, plus an immediate wake when
the whole queue is empty) that runs the company loop inside the hosted runtime, with no
owner PC and no development session involved:

    OBSERVE   one read of the queue (Snapshot) and of every department's blocks
    DETERMINE each idle department's candidates from durable evidence (generators)
    PRIORITISE protected departments first (support, product truth, platform, finance...);
              inside a department, handoff > overdue cadence > self-review; job types whose
              recent generated missions produced nothing are suppressed (learned)
    CREATE    one mission per idle department per tick: an idempotent job + a mission row in
              company memory + a timeline event. Protected work becomes an owner approval
              item instead -- the orchestrator never enqueues a protected job type.
    EXECUTE   the ordinary worker runs the job through the permission layer
    VALIDATE / MEASURE  the next tick reconciles each mission against its job: useful,
              no-op, failed -- persisted as the mission's outcome
    HAND OFF  a useful mission's rows are the next department's evidence (charters.consumes)
    LEARN     department reviews persist KPI snapshots; a regression or tripped guardrail
              becomes a routed Lesson that Learn's generator then consumes

Isolation: each department is generated inside its own try/except and a blocked department
is skipped with its blocker recorded, so one department failing or waiting on the owner never
stops the others (§95).

Idempotency: every effect is keyed (job idempotency key, memory key, timeline key, owner
action requirement key), so a tick killed half-way and re-run by another worker after its
lease is reclaimed produces no duplicates (§95).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..core.models import Job, JobStatus
from . import charters, generators, memory
from .models import ensure_tables


def _never_paused(department: str) -> bool:
    """The shared F-889 rule (one definition, in the emergency controls)."""
    from ..app.command_center.emergency import never_paused_refusal

    return never_paused_refusal(department) is not None

MAX_MISSIONS_PER_TICK = 11          # at most one per department
NOOP_SUPPRESS_AFTER = 3             # consecutive no-op generated missions of one job type
NOOP_SUPPRESS_HOURS = 24
ORCHESTRATE_JOB = "autonomy.orchestrate"
COO = "coo"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _agent_for(job_type: str) -> str | None:
    """The agent that runs a job type: its cadence's agent, else the first registry agent
    that already holds it (never one structurally forbidden from it)."""
    if job_type.startswith("autonomy."):
        return COO
    from ..agents.registry import DEFAULT_AGENTS, FORBIDDEN_COMBINATIONS
    from ..runtime.worker import CADENCES

    for _n, agent, jt, _p in CADENCES:
        if jt == job_type:
            return agent
    for a in DEFAULT_AGENTS:
        if job_type in a["allowed_job_types"] and \
                job_type not in FORBIDDEN_COMBINATIONS.get(a["name"], set()):
            return a["name"]
    return None


def mission_key(charter: charters.Charter, cand: generators.Candidate) -> str:
    return f"autonomy:{charter.key}:{cand.fingerprint}"[:200]


class ProtectedActionRefused(RuntimeError):
    """The orchestrator tried to enqueue something it may never enqueue. A defect."""


def _enqueue_mission(db, queue, charter: charters.Charter, cand: generators.Candidate,
                     now: datetime) -> dict:
    """The single enqueue boundary. Re-checks authority here, not only in the charter."""
    from ..queue.durable import DuplicateJob

    jt = cand.job_type
    if jt in charters.PROTECTED_JOB_TYPES or cand.protected:
        raise ProtectedActionRefused(f"{jt} is protected; it becomes an owner approval item")
    if jt not in charter.generatable or jt not in charters.SAFE_GENERATED:
        raise ProtectedActionRefused(f"{jt} is outside {charter.key}'s generatable authority")
    agent = _agent_for(jt)
    if agent is None:
        raise ProtectedActionRefused(f"no registered agent holds {jt}")
    key = mission_key(charter, cand)
    inputs = {**cand.inputs, "source": "autonomy", "department": charter.key,
              "mission": key, "reason": cand.reason[:300], "evidence": cand.evidence[:10]}
    try:
        job = queue.enqueue(agent, jt, inputs, idempotency_key=key)
        job_id, created = job.id, True
    except DuplicateJob as dup:
        job_id, created = dup.existing_id, False
    # Keyed on the job's idempotency key: a re-run after a reclaimed lease finds the row and
    # leaves it (and its outcome, if already measured) alone.
    if memory.get(db, key) is None:
        memory.remember(db, key, kind="mission", department=charter.key,
                        subject=f"{jt}: {cand.reason}"[:200], state="queued",
                        body={"job_id": job_id, "job_type": jt, "agent": agent,
                              "source": cand.source, "value": cand.value,
                              "reason": cand.reason, "evidence": cand.evidence,
                              "created": now.isoformat()},
                        sources=[f"jobs:{job_id}", *cand.evidence[:10]], now=now)
    # Keyed, so idempotent -- and it also covers a re-run that lost the first write.
    memory.record_event(db, f"mission.created:{key}", kind="mission.created",
                        department=charter.key, actor=COO,
                        summary=f"{charter.name}: {jt} ({cand.source}) -- {cand.reason}",
                        refs=[f"jobs:{job_id}", f"company_memory:{key}"], at=now)
    return {"department": charter.key, "job_type": jt, "agent": agent, "job_id": job_id,
            "created": created, "key": key, "source": cand.source, "reason": cand.reason}


def _raise_approval(db, charter: charters.Charter, cand: generators.Candidate,
                    now: datetime) -> dict:
    """Protected work -> one deduplicated owner action (F-885/F-929). Never a job."""
    from ..core.models import OwnerAction

    a = cand.approval
    rk = a["requirement_key"]
    with db.session() as s:
        open_row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == rk,
                                                      OwnerAction.done == False))  # noqa: E712
        created = False
        if open_row is None:
            s.add(OwnerAction(requirement_key=rk, action=a["action"], reason=a["reason"],
                              max_cost_cad=float(a.get("max_cost_cad") or 0.0),
                              minutes=int(a.get("minutes") or 0),
                              consequence_of_delay=a.get("consequence", ""),
                              blocks=a.get("blocks", "")))
            created = True
        else:
            open_row.action = a["action"]      # current figures, one entry (dedup on key)
    memory.remember(db, f"approval:{rk}", kind="approval", department=charter.key,
                    subject=a["action"][:200], state="awaiting_owner",
                    body={"job_type": cand.job_type, "reason": cand.reason,
                          "requirement_key": rk}, sources=cand.evidence[:20], now=now)
    if created:
        memory.record_event(db, f"approval.requested:{rk}:{cand.fingerprint}",
                            kind="approval.requested", department=charter.key, actor=COO,
                            severity="decision", summary=a["action"],
                            refs=[f"owner_actions:{rk}", *cand.evidence[:5]], at=now)
    return {"department": charter.key, "requirement_key": rk, "created": created,
            "job_type": cand.job_type}


def _suppressed(db, charter: charters.Charter, now: datetime) -> dict[str, str]:
    """Job types whose last N generated missions in this department all did nothing."""
    out: dict[str, str] = {}
    rows = memory.recall(db, kind="mission", department=charter.key,
                         since=now - timedelta(hours=NOOP_SUPPRESS_HOURS), limit=100)
    by_type: dict[str, list[str]] = {}
    for r in rows:                                   # newest first
        jt = r["body"].get("job_type")
        if r["state"] in ("useful", "noop", "failed"):
            by_type.setdefault(jt, []).append(r["state"])
    for jt, states in by_type.items():
        recent = states[:NOOP_SUPPRESS_AFTER]
        if len(recent) == NOOP_SUPPRESS_AFTER and all(s == "noop" for s in recent):
            out[jt] = (f"last {NOOP_SUPPRESS_AFTER} generated {jt} missions produced no work "
                       f"within {NOOP_SUPPRESS_HOURS} h; suppressed until evidence changes")
    return out


def reconcile_missions(db, *, now: datetime | None = None) -> dict:
    """MEASURE: close every queued mission whose job reached a terminal state."""
    from .kpis import did_no_work

    now = now or _now()
    counts = {"useful": 0, "noop": 0, "failed": 0, "open": 0}
    for r in memory.recall(db, kind="mission", state="queued", limit=500):
        job_id = r["body"].get("job_id")
        with db.session() as s:
            job = s.get(Job, job_id) if job_id else None
            status = getattr(job.status, "value", None) if job else None
            outputs = dict(job.outputs or {}) if job else {}
            job_type = job.job_type if job else None
            err = (job.last_error or "")[:300] if job else "job row missing (retention?)"
        if status in ("pending", "running", "failed"):
            counts["open"] += 1
            continue
        if status == "done":
            state = "noop" if did_no_work(outputs, job_type) else "useful"
        else:
            state = "failed"
        counts[state] += 1
        memory.remember(db, r["key"], kind="mission", department=r["department"],
                        state=state,
                        body={**r["body"], "outcome": state, "closed": now.isoformat(),
                              "error": err if state == "failed" else ""}, now=now)
        charter = charters.BY_KEY.get(r["department"])
        downstream = list(charter.handoff_to) if (charter and state == "useful") else []
        memory.record_event(
            db, f"mission.{state}:{r['key']}", kind=f"mission.{state}",
            department=r["department"], actor=r["body"].get("agent", ""),
            severity="warn" if state == "failed" else "info",
            summary=(f"{r['body'].get('job_type')} {state}"
                     + (f"; output is evidence for {', '.join(downstream)}" if downstream
                        else "")),
            refs=[f"jobs:{job_id}", f"company_memory:{r['key']}"], at=now)
    return counts


DEPARTMENT_ORDER = sorted(charters.CHARTERS, key=lambda c: (c.protected_kind, c.key))


def tick(db, queue=None, *, now: datetime | None = None, departments=None) -> dict:
    """One pass of the company loop. Safe to call as often as you like."""
    from ..queue.durable import JobQueue

    ensure_tables(db)
    now = now or _now()
    queue = queue or JobQueue(db)
    report: dict = {"at": now.isoformat(), "departments": {}, "missions": [],
                    "approvals": [], "errors": {}}
    report["reconciled"] = reconcile_missions(db, now=now)
    snap = generators.Snapshot.read(db, now)
    try:
        from ..swarm.orchestrate import suspended_job_types

        thrash = suspended_job_types(db, now=now)
    except Exception:  # noqa: BLE001 - a failed read never stops the loop
        thrash = {}

    created = 0
    for charter in departments or DEPARTMENT_ORDER:
        key = charter.key
        entry: dict = {"open_jobs": snap.open_by_department.get(key, 0)}
        report["departments"][key] = entry
        try:
            block = memory.active_block(db, key, now=now)
            if block and _never_paused(key):
                # F-889: monitoring/evidence/recovery departments never stop, whatever wrote
                # the block (audit ddf9c6e M3). The block is reported, not obeyed.
                entry["ignored_block"] = block["body"].get("reason")
                block = None
            if block:
                entry.update(state="BLOCKED", blocker=block["body"].get("reason"),
                             owner_action=block["body"].get("owner_action"))
                continue
            if entry["open_jobs"]:
                entry["state"] = "BUSY"
                continue
            cands = generators.candidates(db, charter, snap)
            for c in [c for c in cands if c.protected]:
                report["approvals"].append(_raise_approval(db, charter, c, now))
            supp = _suppressed(db, charter, now)
            runnable = [c for c in cands if not c.protected and c.job_type not in supp
                        and c.job_type not in thrash]
            entry["suppressed"] = supp
            entry["candidates"] = [c.to_dict() for c in cands[:5]]
            # Work whose key already exists was already generated from this exact evidence;
            # take the next candidate instead of re-proposing it.
            keys = {mission_key(charter, c): c for c in runnable}
            with db.session() as s:
                done_keys = set(s.scalars(select(Job.idempotency_key).where(
                    Job.idempotency_key.in_(list(keys)))))
            runnable = [c for k, c in keys.items() if k not in done_keys]
            runnable.sort(key=lambda c: -c.value)
            if not runnable:
                entry["state"] = "SATURATED"
                entry["why"] = ("every candidate for the current evidence was already "
                                "generated; next work arrives with new evidence or the next "
                                "review window")
                continue
            if created >= MAX_MISSIONS_PER_TICK:
                entry["state"] = "DEFERRED"
                continue
            mission = _enqueue_mission(db, queue, charter, runnable[0], now)
            created += 1 if mission["created"] else 0
            report["missions"].append(mission)
            entry.update(state="GENERATED", mission=mission["key"])
        except Exception as exc:  # noqa: BLE001 - one department never stops the others
            entry["state"] = "DEGRADED"
            report["errors"][key] = f"{type(exc).__name__}: {exc}"[:300]
            memory.record_event(db, f"department.degraded:{key}:{now.isoformat()}",
                                kind="department.degraded", department=key, actor=COO,
                                severity="warn",
                                summary=f"{charter.name} work generation failed: "
                                        f"{type(exc).__name__}", at=now)

    memory.remember(db, "orchestrator:last_tick", kind="orchestrator", department="executive",
                    subject="last orchestrator tick", state="ok" if not report["errors"]
                    else "degraded",
                    body={"at": now.isoformat(),
                          "missions": [m["key"] for m in report["missions"]],
                          "created": created,
                          "states": {k: v.get("state") for k, v in
                                     report["departments"].items()},
                          "errors": report["errors"], "reconciled": report["reconciled"]},
                    sources=["jobs", "company_memory"], now=now)
    report["created"] = created
    return report


def idle_wake(db, queue, *, now: datetime | None = None) -> bool:
    """Event wake: when nothing at all is queued, ask the orchestrator now rather than at the
    next fifteen-minute window. Keyed per five minutes so it cannot flood."""
    from ..queue.durable import DuplicateJob

    now = now or _now()
    with db.session() as s:
        busy = s.scalar(select(Job.id).where(
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])).limit(1))
    if busy is not None:
        return False
    try:
        queue.enqueue(COO, ORCHESTRATE_JOB, {"wake": "idle_queue"},
                      idempotency_key=f"autonomy.orchestrate:idle:{int(now.timestamp() // 300)}")
        return True
    except DuplicateJob:
        return False
