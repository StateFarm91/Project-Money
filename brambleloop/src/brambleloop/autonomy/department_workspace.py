"""F-667: one workspace per department -- agents and jobs, queue, spend, experiments,
incidents and blockers together.

`/api/company/departments` says whether each department has a mandate, backlog, KPIs,
evidence and an improvement loop; `/api/profiles` holds each improvement cell's measurements
and proposals; jobs, spend, improvements and incidents each had their own route. A
department head had to join them by hand. `workspace(db, key)` joins them for one
department, keyed on the department's charter agents and improvement cells:

* `coverage` -- its row from `departments.coverage` (what is PRESENT or MISSING);
* `agents` -- per charter agent, jobs in the last 24 h by status and what is queued now;
* `spend` -- cost entries of its agents over 30 days (CA$ and calls);
* `improvement` -- its cells' latest measurements and open improvements (experiments);
* `incidents` -- unresolved incidents naming one of its agents or job types;
* `blockers` -- MISSING elements, parked/dead jobs and open incidents, in one list.

Read-only. An unreadable section is UNKNOWN by name; the rest still render.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _guard(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a section, never the whole workspace
        return {"state": "UNKNOWN", "why": f"{type(exc).__name__}: {str(exc)[:160]}"}


def workspace(db, key: str, *, now: datetime | None = None) -> dict:
    from sqlalchemy import func, select

    from ..core.models import CostEntry, Improvement, Incident, Job, JobStatus
    from ..improve import cells as cells_mod
    from . import charters, departments

    now = now or datetime.now(timezone.utc)
    dept = next((d for d in departments.COMPANY if d["key"] == key), None)
    if dept is None:
        raise KeyError(key)
    ch = charters.BY_KEY.get(dept["charter"]) if dept["charter"] else None
    agents = sorted(ch.agents) if ch else []
    job_types = sorted(ch.generatable) if ch and ch.generatable else []
    cells = [c for c in dept["cells"] if c in cells_mod.BY_KEY]

    def coverage():
        return next(r for r in departments.coverage(db)["departments"] if r["key"] == key)

    def jobs():
        out = {}
        with db.session() as s:
            for a in agents:
                recent = dict(s.execute(select(Job.status, func.count()).where(
                    Job.agent == a, Job.created_at >= now - timedelta(hours=24))
                    .group_by(Job.status)).all())
                queued = s.scalar(select(func.count()).select_from(Job).where(
                    Job.agent == a, Job.status == JobStatus.PENDING)) or 0
                out[a] = {"last_24h": {getattr(k, "value", str(k)): v for k, v in recent.items()},
                          "queued": int(queued)}
        return out

    def spend():
        with db.session() as s:
            cad, n = s.execute(select(func.coalesce(func.sum(CostEntry.amount_cad), 0.0),
                                      func.count()).where(
                CostEntry.agent.in_(agents or ["-"]),
                CostEntry.at >= now - timedelta(days=30))).one()
        return {"cad_30d": round(float(cad or 0.0), 4), "calls": int(n), "agents": agents}

    def improvement():
        out = {}
        with db.session() as s:
            for c in cells:
                open_ = [(i.id, i.state, i.hypothesis[:120]) for i in s.scalars(
                    select(Improvement).where(Improvement.cell == c,
                                              Improvement.state.notin_(("promoted",
                                                                        "rejected"))))]
                out[c] = {"metric": cells_mod.BY_KEY[c].metric,
                          "latest": cells_mod.latest_capability(db, c),
                          "open_improvements": [{"id": a, "state": b, "hypothesis": h}
                                                for a, b, h in open_]}
        return out

    def incidents():
        needles = [a for a in agents] + job_types
        with db.session() as s:
            rows = list(s.scalars(select(Incident).where(Incident.resolved == False)))  # noqa: E712
            hits = [{"id": i.id, "severity": i.severity, "signature": i.signature}
                    for i in rows
                    if any(n and (n in (i.signature or "") or n in str(i.detail or {}))
                           for n in needles)]
        return hits

    out = {"key": key, "name": dept["name"], "charter": dept["charter"],
           "coverage": _guard(coverage), "agents": _guard(jobs), "spend": _guard(spend),
           "improvement": _guard(improvement), "incidents": _guard(incidents),
           "as_of": now.isoformat()}
    blockers = []
    cov = out["coverage"]
    if isinstance(cov, dict) and cov.get("missing"):
        blockers += [f"missing: {m}" for m in cov["missing"]]
    if isinstance(out["agents"], dict) and "state" not in out["agents"]:
        with db.session() as s:
            stuck = s.scalar(select(func.count()).select_from(Job).where(
                Job.agent.in_(agents or ["-"]), Job.status == JobStatus.DEAD)) or 0
        if stuck:
            blockers.append(f"{stuck} dead-lettered job(s) for this department's agents")
    if isinstance(out["incidents"], list) and out["incidents"]:
        blockers.append(f"{len(out['incidents'])} open incident(s)")
    out["blockers"] = blockers
    return out
