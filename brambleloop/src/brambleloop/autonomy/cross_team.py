"""F-690: structured work one department creates for another.

Lessons route *knowledge* by subject. What did not exist was a *task* one team hands another
with its evidence: support seeing the same confusion three times should leave Pattern
Engineering a task naming the product and the cases, not only a lesson. A cross-team task is a
company-memory row (`kind="cross_team_task"`, keyed by recipient + evidence, so a detector
re-reading the same evidence creates one task) with `from_dept`, `to_dept`, the request, the
evidence ref and its state (`open` until the recipient closes it with a resolution).

When the request names a job type that one of the recipient department's charter agents may
run and that is GREEN-only (`app.hq_worker._green_only_types`: no publication, spend or owner
action), the task also enqueues that job once. Anything else waits for the recipient's own
loop to pick it up -- a detector never makes a consequential change in another department.
"""
from __future__ import annotations

KIND = "cross_team_task"
OPEN, DONE = "open", "done"


class CrossTeamRefused(ValueError):
    pass


def _dept(key: str) -> dict:
    from . import departments

    d = next((x for x in departments.COMPANY if x["key"] == key), None)
    if d is None:
        raise CrossTeamRefused(f"no department {key!r}")
    return d


def create(db, *, from_dept: str, to_dept: str, request: str, evidence_ref: str,
           job_type: str | None = None, inputs: dict | None = None) -> dict:
    from . import charters, memory

    _dept(from_dept)
    to = _dept(to_dept)
    if from_dept == to_dept:
        raise CrossTeamRefused("a cross-team task goes to another department")
    if len(request.split()) < 5 or not evidence_ref.strip():
        raise CrossTeamRefused("a task states its request and names its evidence")
    key = f"xteam:{to_dept}:{evidence_ref.strip()}"[:200]
    existing = memory.get(db, key)
    if existing is not None:
        return {"task": key, "created": False, "enqueued": existing["body"].get("enqueued")}
    enqueued = None
    if job_type:
        from ..app.hq_worker import _green_only_types
        from ..queue.durable import DuplicateJob, JobQueue

        ch = charters.BY_KEY.get(to["charter"]) if to["charter"] else None
        agent = next((a for a in sorted(ch.agents) if _may_run(db, a, job_type)), None) \
            if ch else None
        if agent and job_type in _green_only_types():
            try:
                job = JobQueue(db).enqueue(agent, job_type, dict(inputs or {}),
                                           idempotency_key=key)
                enqueued = {"job": getattr(job, "id", None), "agent": agent,
                            "job_type": job_type}
            except DuplicateJob:
                enqueued = {"duplicate": True, "job_type": job_type}
        else:
            enqueued = {"refused": f"{job_type} is not a GREEN job a {to_dept} agent may run; "
                                   f"left for the department's own loop"}
    memory.remember(db, key, kind=KIND, department=to_dept, state=OPEN,
                    subject=request[:200],
                    body={"from_dept": from_dept, "to_dept": to_dept, "request": request,
                          "evidence_ref": evidence_ref, "enqueued": enqueued},
                    sources=[evidence_ref])
    return {"task": key, "created": True, "enqueued": enqueued}


def _may_run(db, agent: str, job_type: str) -> bool:
    from ..agents.registry import DEFAULT_AGENTS

    spec = next((a for a in DEFAULT_AGENTS if a["name"] == agent), None)
    return bool(spec) and job_type in (spec.get("allowed_job_types") or [])


def close(db, key: str, *, resolution: str) -> dict:
    from . import memory

    row = memory.get(db, key)
    if row is None or row["kind"] != KIND:
        raise CrossTeamRefused(f"no cross-team task {key!r}")
    if len(resolution.split()) < 3:
        raise CrossTeamRefused("closing a task says what was done")
    memory.remember(db, key, kind=KIND, state=DONE,
                    body={**row["body"], "resolution": resolution})
    return {"task": key, "state": DONE}


def inbox(db, to_dept: str, *, state: str | None = OPEN) -> list[dict]:
    from . import memory

    return [{"task": r["key"], "state": r["state"], **r["body"]}
            for r in memory.recall(db, kind=KIND, department=to_dept, state=state)]
