"""F-451: the master orchestrator view -- one read joining requirements, departments,
dependencies, owner gates, external blockers, spend, deployments and active work.

Every section comes from the module that owns it (build2.executor, autonomy.departments and
the last orchestrator tick, scale.dependency, the approval inbox, finance.spend_report,
core.build identity and the deploy audit rows, the job queue). Each section is guarded: one
unreadable source reads UNKNOWN with the reason and never blanks the others. Read-only.

Not here: build-side Claude lanes (ops/registry.py, the file tool) are not visible to the
runtime, which never holds the repository; that stays named rather than faked.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _guard(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - one source never blanks the others
        return {"state": "UNKNOWN", "why": f"unreadable: {type(exc).__name__}: {str(exc)[:120]}"}


def view(db, *, env: dict | None = None, now: datetime | None = None) -> dict:
    from sqlalchemy import func, select

    from ..core.models import AuditLog, Job, JobStatus

    now = now or datetime.now(timezone.utc)
    env = env if env is not None else {}

    def requirements():
        from ..build2 import executor

        q = executor.queue(db, limit=5)
        return {k: q.get(k) for k in ("ready_total", "parked_total", "blocked_total",
                                      "running_total", "done_total", "parked_by_kind")} | {
            "next": (q.get("next") or {}).get("requirement_id") if q.get("next") else None}

    def departments():
        from . import departments as dept, memory

        last = memory.get(db, "orchestrator:last_tick") or {}
        cov = dept.coverage(db)
        return {"states": (last.get("body") or {}).get("states"),
                "last_tick": (last.get("body") or {}).get("at"),
                "records_complete": f"{cov['complete']} / {cov['total']}",
                "incomplete": cov["incomplete"]}

    def dependencies():
        from ..scale import dependency

        reg = dependency.register(db, now=now)
        return {k: reg.get(k) for k in ("existential", "axes", "providers") if k in reg} or reg

    def owner_gates():
        from ..build2 import executor

        inbox = executor.approval_inbox(db, env=env)
        return {"cards": len(inbox.get("cards") or []),
                "gates": [c.get("gate") for c in inbox.get("cards") or []][:20],
                "not_yet_askable": [c.get("gate") for c in inbox.get("not_yet_askable") or []],
                "waiting_on_data": [c.get("gate") for c in inbox.get("waiting_on_data") or []]}

    def external():
        from ..build2 import executor

        inbox = executor.approval_inbox(db, env=env)
        return [{"gate": e.get("gate"), "unblocks": e.get("unblocks_count"),
                 "why": (e.get("why") or "")[:160]}
                for e in inbox.get("external_capability_unavailable") or []]

    def spend():
        from ..finance import spend_policy, spend_report

        r = spend_report.what_it_bought(db, now=now)
        return {"month": r["month"], "spent_cad": r["spent_cad"],
                "projected_month_end_cad": r["projected_month_end_cad"],
                "headroom": spend_policy.headroom(r["spent_cad"])}

    def deployments():
        from ..core.build import identity

        ident = identity(env)
        with db.session() as s:
            rows = list(s.scalars(select(AuditLog).where(AuditLog.action.like("deploy%"))
                                  .order_by(AuditLog.id.desc()).limit(5)))
        return {"running": {k: ident.get(k) for k in ("commit", "commit_short", "branch",
                                                      "known")},
                "recent": [{"at": r.at.isoformat(), "action": r.action,
                            "artifact": r.artifact} for r in rows],
                "note": ("the running commit is read from the build identity; deploy history "
                         "is whatever deploy audit rows exist (none is not 'never deployed')")}

    def active_work():
        with db.session() as s:
            by_status = dict(s.execute(select(Job.status, func.count())
                                       .group_by(Job.status)).all())
            running = list(s.execute(select(Job.agent, Job.job_type).where(
                Job.status == JobStatus.RUNNING).limit(20)).all())
        return {"by_status": {getattr(k, "value", k): int(v) for k, v in by_status.items()},
                "running": [{"agent": a, "job_type": t} for a, t in running]}

    return {
        "as_of": now.isoformat(),
        "requirements": _guard(requirements),
        "departments": _guard(departments),
        "dependencies": _guard(dependencies),
        "owner_gates": _guard(owner_gates),
        "external_blockers": _guard(external),
        "spend": _guard(spend),
        "deployments": _guard(deployments),
        "active_work": _guard(active_work),
        "not_visible_here": ["build-side Claude lanes (ops/registry.py; the runtime holds no "
                             "repository)"],
    }
