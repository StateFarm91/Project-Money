"""ENG-CATALOGUE slice 2: operating evidence per department (GET /api/cc/operating-evidence).

The agents panel answers "is the company doing useful work", from persisted rows only:

* last successful USEFUL job -- the newest DONE job the one judge (`runtime.pipeline.
  did_no_work`, which applies `WORK_KEYS`) counts as work. Self-observation (`ops.health`,
  `ops.heartbeat`, `ops.slo`) is never useful work: a green health check is not autonomy
  evidence. The scan is bounded (`SCAN_LIMIT` newest completions); when the bound is hit with
  no useful job the answer is UNKNOWN, never "none";
* next scheduled work -- the earliest pending job (SQL `MIN(run_after)`) and the next cadence
  window (`ops.flow_health.next_cadences`, the scheduler's own arithmetic);
* queue depth and oldest age per stage and per department (pending/failed-awaiting-retry,
  SQL `GROUP BY job_type`, mapped with `production_inventory.stage_of` and
  `autonomy.charters.department_of`);
* jobs in progress (RUNNING);
* stage transitions (useful stage jobs completed) and products completed in the last 24 h
  (`listing.seo_drafted` = listing package completed; `gate.certify` granted = certified);
* recoveries (`recovery.*` audit rows and the queue's `queue.lease_reclaimed`);
* dead letters (`DEAD` jobs, defect vs deliberate refusal, `queue.durable.
  classify_dead_letter`);
* blocked agents with reasons (`swarm.orchestrate.suspended_job_types`, and a defect dead
  letter with no later success of the same type);
* healthy and unhealthy workers (`ops_runtime_samples` heartbeats per component/instance).

Read-only: nothing here writes a row, queues a job or calls a provider. A part that cannot be
read is UNKNOWN with the reason; it never reads as a pass or as 0.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

UNKNOWN = "UNKNOWN"
SCAN_LIMIT = 1000
SCAN_BATCH = 200
DAY = timedelta(hours=24)
RECENT = 10
WAITING = ("pending", "failed")


def _aware(v):
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


def _iso(v):
    v = _aware(v)
    return v.isoformat() if isinstance(v, datetime) else None


def _dept(job_type: str) -> str:
    from ...autonomy.charters import department_of

    return department_of(job_type) or "unchartered"


def _self_observing() -> frozenset:
    from ...ops.health import SELF_OBSERVING_JOB_TYPES

    return SELF_OBSERVING_JOB_TYPES


def _useful(job_type: str, outputs) -> bool:
    from ...runtime.pipeline import did_no_work

    if job_type in _self_observing():
        return False
    try:
        return not did_no_work(outputs or {}, job_type)
    except Exception:  # noqa: BLE001 - an unjudgeable output is not evidence of work
        return False


def _guard(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never a pass
        return {"state": UNKNOWN, "why": f"could not be read: {type(exc).__name__}: "
                                         f"{str(exc)[:160]}"}


# ---- per-type SQL aggregates -------------------------------------------------------------------

def _by_type(s, now):
    """One pass of SQL aggregates per job type."""
    from sqlalchemy import case, func, select

    from ...core.models import Job

    waiting = Job.status.in_(WAITING)
    rows = s.execute(select(
        Job.job_type,
        func.sum(case((waiting, 1), else_=0)),
        func.min(case((waiting, Job.created_at), else_=None)),
        func.min(case((Job.status == "pending", Job.run_after), else_=None)),
        func.sum(case((Job.status == "running", 1), else_=0)),
        func.sum(case((Job.status == "dead", 1), else_=0)),
    ).group_by(Job.job_type)).all()
    agents = {}
    for jt, agent in s.execute(select(Job.job_type, Job.agent).distinct()):
        agents.setdefault(jt, set()).add(agent)
    out = {}
    for jt, depth, oldest, nxt, running, dead in rows:
        out[jt] = {"waiting": int(depth or 0), "oldest_created": _aware(oldest),
                   "next_run_after": _aware(nxt), "running": int(running or 0),
                   "dead": int(dead or 0), "agents": sorted(agents.get(jt, ()))}
    return out


def _last_useful(s, job_types) -> dict:
    """The newest DONE job of these types the judge counts as useful work, bounded."""
    from sqlalchemy import select

    from ...core.models import Job

    types = sorted(set(job_types) - _self_observing())
    if not types:
        return {"state": "NONE", "why": "no work-bearing job type recorded"}
    scanned, offset = 0, 0
    while scanned < SCAN_LIMIT:
        batch = list(s.execute(
            select(Job.id, Job.job_type, Job.agent, Job.finished_at, Job.outputs)
            .where(Job.status == "done", Job.job_type.in_(types))
            .order_by(Job.finished_at.desc(), Job.id.desc())
            .limit(SCAN_BATCH).offset(offset)))
        for jid, jt, agent, fin, outputs in batch:
            if _useful(jt, outputs):
                return {"state": "FOUND", "job_id": jid, "job_type": jt, "agent": agent,
                        "finished_at": _iso(fin)}
        scanned += len(batch)
        offset += SCAN_BATCH
        if len(batch) < SCAN_BATCH:
            return {"state": "NONE", "scanned": scanned,
                    "why": "no completed job of this department did useful work"}
    return {"state": UNKNOWN, "scanned": scanned,
            "why": f"no useful job in the newest {SCAN_LIMIT} completions; older rows were "
                   f"not scanned"}


def _done_24h(s, now) -> list:
    from sqlalchemy import select

    from ...core.models import Job

    return list(s.execute(select(Job.job_type, Job.outputs, Job.agent)
                          .where(Job.status == "done", Job.finished_at >= now - DAY)))


def _dead_rows(s, now) -> list:
    """Dead letters with no later successful completion of the same type."""
    from sqlalchemy import func, select

    from ...core.models import Job

    last_ok = dict(s.execute(select(Job.job_type, func.max(Job.finished_at))
                             .where(Job.status == "done").group_by(Job.job_type)).all())
    out = []
    for jid, jt, agent, fin, err in s.execute(
            select(Job.id, Job.job_type, Job.agent, Job.finished_at, Job.last_error)
            .where(Job.status == "dead").order_by(Job.id.desc())):
        ok_at = _aware(last_ok.get(jt))
        fin = _aware(fin)
        out.append({"job_id": jid, "job_type": jt, "agent": agent, "at": _iso(fin),
                    "superseded": bool(ok_at and fin and ok_at > fin),
                    "error": (err or "")[:160], "_at": fin})
    return out


# ---- sections ----------------------------------------------------------------------------------

def workers(db, now) -> dict:
    from sqlalchemy import func, inspect, select

    from ...ops import slo

    with db.session() as s:
        if not inspect(s.get_bind()).has_table(slo.RuntimeSample.__tablename__):
            return {"state": UNKNOWN, "why": "no heartbeat table: worker health is unmeasured",
                    "healthy": None, "unhealthy": None, "items": []}
        latest = s.execute(select(slo.RuntimeSample.component, slo.RuntimeSample.instance,
                                  func.max(slo.RuntimeSample.at))
                           .where(slo.RuntimeSample.kind == "heartbeat")
                           .group_by(slo.RuntimeSample.component,
                                     slo.RuntimeSample.instance)).all()
        items = []
        for comp, inst, at in latest:
            ok = s.scalar(select(slo.RuntimeSample.ok).where(
                slo.RuntimeSample.kind == "heartbeat", slo.RuntimeSample.component == comp,
                slo.RuntimeSample.instance == inst, slo.RuntimeSample.at == at).limit(1))
            age = (now - _aware(at)).total_seconds() if at else None
            fresh = age is not None and age <= slo.WORKER_STALL_S
            healthy = bool(ok) and fresh
            items.append({"component": comp, "instance": inst, "last_heartbeat": _iso(at),
                          "age_s": round(age) if age is not None else None,
                          "healthy": healthy,
                          "why": None if healthy else ("heartbeat reported not ok" if fresh
                                                      else "no heartbeat in "
                                                      f"{slo.WORKER_STALL_S // 60} minutes")})
        stall = slo.worker_stall(s, now)
    if not items:
        return {"state": UNKNOWN, "why": "no heartbeat has ever been recorded",
                "healthy": None, "unhealthy": None, "items": [], "queue_drain": stall}
    bad = [i for i in items if not i["healthy"]]
    return {"state": "DEGRADED" if bad or stall.get("stalled") else "OK",
            "healthy": len(items) - len(bad), "unhealthy": len(bad),
            "items": sorted(items, key=lambda i: (i["healthy"], i["component"], i["instance"])),
            "queue_drain": stall}


def recoveries(db, now) -> dict:
    from sqlalchemy import and_, func, or_, select

    from ...core.models import AuditLog

    # A refused recovery request (`recovery.refused`) recovered nothing: reported apart.
    refused = AuditLog.action == "recovery.refused"
    cond = or_(and_(AuditLog.action.like("recovery.%"), ~refused),
               AuditLog.action == "queue.lease_reclaimed")
    with db.session() as s:
        n24 = s.scalar(select(func.count()).select_from(AuditLog)
                       .where(cond, AuditLog.at >= now - DAY))
        n7 = s.scalar(select(func.count()).select_from(AuditLog)
                      .where(cond, AuditLog.at >= now - timedelta(days=7)))
        r24 = s.scalar(select(func.count()).select_from(AuditLog)
                       .where(refused, AuditLog.at >= now - DAY))
        recent = [{"id": i, "at": _iso(at), "action": a, "actor": who, "job_id": jid,
                   "result": (d or {}).get("result")}
                  for i, at, a, who, jid, d in s.execute(
                      select(AuditLog.id, AuditLog.at, AuditLog.action, AuditLog.actor,
                             AuditLog.job_id, AuditLog.detail)
                      .where(cond).order_by(AuditLog.id.desc()).limit(RECENT))]
    return {"state": "OK", "last_24h": int(n24 or 0), "last_7d": int(n7 or 0),
            "refused_24h": int(r24 or 0),
            "recent": recent}


def view(db, *, now: datetime | None = None) -> dict:
    from ...products.production_inventory import stage_of
    from ...queue.durable import classify_dead_letter

    now = _aware(now) or datetime.now(timezone.utc)
    out: dict = {"tab": "OPERATING_EVIDENCE", "read_only": True, "as_of": now.isoformat(),
                 "note": "from persisted rows only; a green health check is not autonomy "
                         "evidence"}

    def core():
        with db.session() as s:
            types = _by_type(s, now)
            done = _done_24h(s, now)
            dead = _dead_rows(s, now)
            depts: dict[str, dict] = {}
            for jt, a in types.items():
                d = depts.setdefault(_dept(jt), {"job_types": [], "agents": set(),
                                                 "waiting": 0, "oldest": None, "next": None,
                                                 "running": 0})
                d["job_types"].append(jt)
                d["agents"].update(a["agents"])
                d["waiting"] += a["waiting"]
                d["running"] += a["running"]
                if a["oldest_created"] and (d["oldest"] is None or a["oldest_created"] <
                                            d["oldest"]):
                    d["oldest"] = a["oldest_created"]
                if a["next_run_after"] and (d["next"] is None or a["next_run_after"] <
                                            d["next"]):
                    d["next"] = a["next_run_after"]
            last = {k: _last_useful(s, v["job_types"]) for k, v in depts.items()}
        return types, done, dead, depts, last

    try:
        types, done, dead, depts, last = core()
    except Exception as exc:  # noqa: BLE001
        out.update(state=UNKNOWN, why=f"jobs could not be read: {type(exc).__name__}: "
                                      f"{str(exc)[:160]}", departments=None,
                   queue_by_stage=None, last_24h=None, dead_letters=None)
        out["workers"] = _guard(lambda: workers(db, now))
        out["recoveries"] = _guard(lambda: recoveries(db, now))
        return out

    from ...ops import flow_health
    from ...swarm import orchestrate

    cad = _guard(lambda: flow_health.next_cadences(db, now=now))
    cad_ok = isinstance(cad, list)
    sus = _guard(lambda: orchestrate.suspended_job_types(db, now=now))
    # `_guard` returns {"state": UNKNOWN, ...} on failure; a suspension map never has that key.
    sus_ok = isinstance(sus, dict) and sus.get("state") != UNKNOWN

    # Useful stage transitions and departments' useful/no-op completions in 24 h.
    trans: dict[str, int] = {}
    useful24: dict[str, dict] = {}
    for jt, outputs, _agent in done:
        u = _useful(jt, outputs)
        b = useful24.setdefault(_dept(jt), {"useful": 0, "no_op": 0})
        b["useful" if u else "no_op"] += 1
        st = stage_of(jt)
        if u and st != "other":
            trans[st] = trans.get(st, 0) + 1

    # Queue per stage (product pipeline stages) -- SQL aggregates, mapped.
    stages: dict[str, dict] = {}
    for jt, a in types.items():
        if not a["waiting"]:
            continue
        st = stages.setdefault(stage_of(jt), {"waiting": 0, "oldest": None})
        st["waiting"] += a["waiting"]
        if a["oldest_created"] and (st["oldest"] is None or a["oldest_created"] < st["oldest"]):
            st["oldest"] = a["oldest_created"]
    queue_by_stage = {k: {"waiting": v["waiting"], "oldest_created": _iso(v["oldest"]),
                          "oldest_age_s": round((now - v["oldest"]).total_seconds())
                          if v["oldest"] else None} for k, v in sorted(stages.items())}

    open_dead = [d for d in dead if not d["superseded"]]
    for d in open_dead:
        d["kind"] = classify_dead_letter(d["job_type"], d["error"])

    items = []
    for key, d in sorted(depts.items()):
        blocked = []
        if sus_ok:
            blocked += [{"job_type": jt, "why": f"{v.get('kind')}: "
                         f"{v.get('why') or ('until ' + str(v.get('until')))}",
                         "incident": v.get("incident")}
                        for jt, v in sus.items() if jt in d["job_types"]]
        blocked += [{"job_type": x["job_type"], "why": f"defect dead letter (job "
                     f"{x['job_id']}) with no later success: {x['error']}"}
                    for x in open_dead if x["job_type"] in d["job_types"]
                    and x["kind"] != "refused"]
        nxt_cad = None
        if cad_ok:
            # `next_cadences` is sorted by next_at: the first unsuspended cadence whose job
            # type this department owns.
            nxt_cad = next(({"cadence": c["cadence"], "job_type": c["job_type"],
                             "next_at": c["next_at"]} for c in cad
                            if not c["suspended"] and _dept(c["job_type"]) == key), None)
        dl24 = [x for x in dead if x["job_type"] in d["job_types"] and x["_at"]
                and x["_at"] >= now - DAY]
        lu = last[key]
        items.append({
            "department": key, "agents": sorted(d["agents"]),
            "last_useful_job": lu,
            "next_scheduled": {"pending_run_after": _iso(d["next"]),
                               "cadence": nxt_cad if cad_ok else UNKNOWN},
            "queue": {"waiting": d["waiting"], "oldest_created": _iso(d["oldest"]),
                      "oldest_age_s": round((now - d["oldest"]).total_seconds())
                      if d["oldest"] else None},
            "in_progress": d["running"],
            "completed_24h": useful24.get(key, {"useful": 0, "no_op": 0}),
            "dead_letters": {"last_24h": len(dl24),
                             "open": sum(1 for x in open_dead
                                         if x["job_type"] in d["job_types"])},
            "blocked": blocked if sus_ok else UNKNOWN,
            "state": ("BLOCKED" if blocked else
                      UNKNOWN if lu["state"] == UNKNOWN or not sus_ok else
                      "OK" if lu["state"] == "FOUND" else "IDLE"),
        })

    with db.session() as s:
        from sqlalchemy import func, select

        from ...core.models import AuditLog

        pkg = s.scalar(select(func.count(func.distinct(AuditLog.artifact)))
                       .where(AuditLog.action == "listing.seo_drafted",
                              AuditLog.at >= now - DAY))
    certified = sum(1 for jt, o, _a in done if jt == "gate.certify"
                    and (o or {}).get("granted") is True)
    out.update(
        # OK needs useful work in the last 24 h: no rows, or only no-op and self-observing
        # completions, is IDLE -- never OK.
        state=("BLOCKED" if any(i["state"] == "BLOCKED" for i in items) else
               UNKNOWN if any(i["state"] == UNKNOWN for i in items) else
               "OK" if any(b["useful"] for b in useful24.values()) else "IDLE"),
        departments=items,
        queue_by_stage=queue_by_stage,
        last_24h={"stage_transitions": trans, "listing_packages_completed": int(pkg or 0),
                  "versions_certified": certified,
                  "useful": sum(b["useful"] for b in useful24.values()),
                  "no_op": sum(b["no_op"] for b in useful24.values())},
        dead_letters={"total": len(dead), "open": len(open_dead),
                      "open_defect": sum(1 for x in open_dead if x["kind"] != "refused"),
                      "open_refused": sum(1 for x in open_dead if x["kind"] == "refused"),
                      "last_24h": sum(1 for x in dead if x["_at"] and x["_at"] >= now - DAY),
                      "recent": [{k: v for k, v in x.items() if k != "_at"}
                                 for x in open_dead[:RECENT]]},
        blocked_agents=[{"department": i["department"], "agents": i["agents"],
                         "reasons": i["blocked"]} for i in items
                        if isinstance(i["blocked"], list) and i["blocked"]],
        suspensions_readable=sus_ok,
    )
    out["workers"] = _guard(lambda: workers(db, now))
    out["recoveries"] = _guard(lambda: recoveries(db, now))
    return out
