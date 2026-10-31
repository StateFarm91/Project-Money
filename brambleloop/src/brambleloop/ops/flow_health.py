"""W5-INVENTORY: flow health per product, and department activity, from job rows only.

**Flow health** (`flow`), per inventory row:
  * the latest stage worked on, the last *useful* progress time (a DONE job the one judge,
    `runtime.pipeline.did_no_work`, counts as work), and whether each hand-off's successor
    exists;
  * STALLED -- a stage succeeded and said it hands off (`HANDOFFS`: promoted, compiled,
    granted, drafted, ok...) but no successor job exists and the row has not advanced past it
    by other means; or a job sat PENDING/FAILED-awaiting-retry past `PENDING_STALL`, RUNNING
    past `RUNNING_STALL`; or a defect dead letter (`queue.durable.classify_dead_letter`) has
    no later success of the same type;
  * LOOPING -- the same job type re-ran on the same input digest (`production_inventory.
    input_digest`, volatile keys such as the rebuild token removed) `LOOP_MIN` times inside
    `LOOP_WINDOW`, reported with whether the outputs were unchanged too; or a compile/revise
    cycle: more completed `cir.revise` runs on one version than `engineering_ops.
    MAX_REVISIONS` allows (each revision changes the CIR, so the digest rule misses it);
  * HELD -- the row's holds (owner / physical / paid_approval / policy) from the inventory,
    plus a refused dead letter (shadow mode is the owner's phase decision).

**Department activity** (`activity`), per agent and per department (`autonomy.charters.
department_of`) over 24 h and 7 d: started, completed, failed, dead-lettered (defect vs refused),
useful vs no-op (the one judge, with the job type so `WORK_KEYS` applies), cost (`CostEntry`),
busy and idle seconds, and the next scheduled cadence (`runtime.worker.CADENCES`, the window
arithmetic `Scheduler.tick` uses; suspended types from `swarm.orchestrate`).

Read-only: nothing here writes a row or enqueues a job.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..products import production_inventory as inv_mod

PENDING_STALL = timedelta(hours=6)
RUNNING_STALL = timedelta(hours=2)
LOOP_WINDOW = timedelta(days=7)
LOOP_MIN = 3
WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7)}


def _ok(o):
    return o.get("ok") is not False


# job type -> (did this run hand off?, successor job types, state the successor's work reaches)
HANDOFFS: dict[str, tuple] = {
    "radar.score": (lambda o: o.get("promoted") is True, ("cir.draft",),
                    inv_mod.PATTERN_IN_DEVELOPMENT),
    "cir.draft": (lambda o: o.get("drafted") is True, ("cir.compile",),
                  inv_mod.PATTERN_VALIDATED),
    "cir.compile": (lambda o: o.get("compiled") is True, ("gate.certify",),
                    inv_mod.REVIEW_PASSED),
    "gate.certify": (lambda o: o.get("granted") is True and not o.get("withheld"),
                     ("listing.draft",), inv_mod.PDF_COMPLETED),
    "listing.draft": (lambda o: o.get("drafted") is True, ("assets.build",),
                      inv_mod.PDF_COMPLETED),
    "assets.build": (lambda o: bool(o.get("pdf_sha256")) and _ok(o), ("pricing.position",),
                     inv_mod.LISTING_COMPLETED),
    "pricing.position": (lambda o: bool(o.get("price_cad")) and not o.get("refused")
                         and not o.get("stopped"),
                         ("listing.seo",), inv_mod.LISTING_COMPLETED),
    "listing.seo": (lambda o: o.get("ok") is True, ("launch.plan",), inv_mod.LISTING_COMPLETED),
    "launch.plan": (lambda o: not o.get("held") and not o.get("withheld"), ("store.publish",),
                    inv_mod.PUBLISHED),
}
# Types matched on slug only (their successor's version is not known in the predecessor).
SLUG_ONLY = frozenset({"radar.score", "cir.draft"})
TERMINAL = (inv_mod.PUBLISHED, inv_mod.REJECTED)


def _aware(v):
    return inv_mod._aware(v)


def _useful(job) -> bool:
    from ..runtime.pipeline import did_no_work

    try:
        return not did_no_work(job.outputs or {}, job.job_type)
    except Exception:  # noqa: BLE001 - an unjudgeable output is not evidence of work
        return False


def _dead_kind(job) -> str:
    from ..queue.durable import classify_dead_letter

    return classify_dead_letter(job.job_type, job.last_error or "")


def row_flow(item: dict, jobs: list, *, now: datetime) -> dict:
    """Flow health for one inventory row from its own jobs."""
    slug, version = item["slug"], item["version"]
    stalls, loops = [], []
    holds = list(item.get("holds") or [])
    latest = max(jobs, key=lambda j: j.id) if jobs else None
    useful_done = [j for j in jobs if j.status == "done" and j.finished_at and _useful(j)]
    last_progress = max((j.finished_at for j in useful_done), default=None)
    state_rank = inv_mod.RANK.get(item["state"], 0)
    successors = []
    if item["state"] not in TERMINAL:
        for jt, (handed_off, succ_types, reaches) in HANDOFFS.items():
            done = inv_mod._latest(jobs, jt)
            if done is None or not handed_off(done.outputs or {}):
                continue
            exists = [j for j in jobs if j.job_type in succ_types and (
                jt in SLUG_ONLY or j.version in (None, done.version))
                and (not done.release or not j.release or j.release == done.release)]
            entry = {"after": jt, "job_id": done.id, "successor_types": list(succ_types),
                     "successor_job_ids": [j.id for j in exists][-3:]}
            successors.append(entry)
            advanced = (item["state"] != inv_mod.REVISION_REQUIRED
                        and state_rank >= inv_mod.RANK[reaches])
            if not exists and not advanced:
                stalls.append({"kind": "no_successor", "job_id": done.id, "job_type": jt,
                               "finished_at": inv_mod._iso(done.finished_at),
                               "why": f"{jt} succeeded and handed off, but no "
                                      f"{'/'.join(succ_types)} job exists"})
    for j in jobs:
        if j.status in ("pending", "failed"):
            since = j.run_after or j.created_at
            if since and now - since > PENDING_STALL:
                stalls.append({"kind": "waiting_too_long", "job_id": j.id,
                               "job_type": j.job_type, "status": j.status,
                               "age_hours": round((now - since).total_seconds() / 3600, 1)})
        elif j.status == "running" and j.started_at and now - j.started_at > RUNNING_STALL:
            stalls.append({"kind": "running_too_long", "job_id": j.id, "job_type": j.job_type,
                           "age_hours": round((now - j.started_at).total_seconds() / 3600, 1)})
        elif j.status == "dead":
            later = [k for k in jobs if k.job_type == j.job_type and k.id > j.id
                     and k.status == "done"]
            if later:
                continue
            kind = _dead_kind(j)
            if kind == "refused":
                holds.append({"kind": inv_mod.HOLD_OWNER if j.job_type.startswith("store.")
                              else inv_mod.HOLD_POLICY,
                              "why": f"{j.job_type} refused by a closed gate (job {j.id})"})
            elif kind == "defect":
                stalls.append({"kind": "dead_letter", "job_id": j.id, "job_type": j.job_type,
                               "why": "dead-lettered with no later success"})
    groups: dict[tuple, list] = {}
    for j in jobs:
        if j.status == "done" and j.finished_at and now - j.finished_at <= LOOP_WINDOW:
            groups.setdefault((j.job_type, inv_mod.input_digest(j.inputs)), []).append(j)
    for (jt, digest), runs in sorted(groups.items()):
        if len(runs) >= LOOP_MIN:
            outs = {inv_mod.output_digest(r.outputs) for r in runs}
            loops.append({"kind": "same_input_digest", "job_type": jt,
                          "input_digest": digest, "runs": len(runs),
                          "job_ids": [r.id for r in runs][-5:],
                          "outputs_unchanged": len(outs) == 1})
    # The compile/revise cycle (ported from FABLE-P0 stage_register): each revision changes
    # the CIR, so its input digest differs and the rule above cannot see it. The engineer may
    # revise a version `MAX_REVISIONS` times; more completed revisions than that inside the
    # window means the repair rule is not converging.
    from ..runtime.engineering_ops import MAX_REVISIONS

    revisions = [j for j in jobs if j.job_type == "cir.revise" and j.status == "done"
                 and j.finished_at and now - j.finished_at <= LOOP_WINDOW]
    if len(revisions) > MAX_REVISIONS:
        loops.append({"kind": "compile_revise_cycle", "job_type": "cir.revise",
                      "input_digest": None, "runs": len(revisions),
                      "job_ids": [r.id for r in revisions][-5:], "outputs_unchanged": None,
                      "why": f"{len(revisions)} revisions of one version in "
                             f"{LOOP_WINDOW.days} d against a cap of {MAX_REVISIONS}: the "
                             f"repair rule is not converging"})
    return {"slug": slug, "version": version, "state": item["state"],
            "latest_stage": inv_mod.stage_of(latest.job_type) if latest else None,
            "latest_job": ({"id": latest.id, "job_type": latest.job_type,
                            "status": latest.status} if latest else None),
            "last_progress_at": inv_mod._iso(last_progress),
            "successors": successors, "stalled": bool(stalls), "stalls": stalls,
            "looping": bool(loops), "loops": loops, "held": bool(holds),
            "held_reasons": sorted({h["kind"] for h in holds}), "holds": holds}


def flow(db, *, inventory: dict | None = None, records: dict | None = None,
         now: datetime | None = None) -> dict:
    now = _aware(now) or datetime.now(timezone.utc)
    rec = records if records is not None else inv_mod.load_records(db)
    inv = inventory if inventory is not None else inv_mod.derive(db, records=rec)
    rows = []
    for item in inv["items"]:
        jobs = inv_mod._jobs_for(rec, item["slug"], item["version"], item["head"])
        rows.append(row_flow(item, jobs, now=now))
    return {"as_of": now.isoformat(), "rows": rows,
            "stalled_count": sum(r["stalled"] for r in rows),
            "looping_count": sum(r["looping"] for r in rows),
            "held_count": sum(r["held"] for r in rows),
            "thresholds": {"pending_stall_hours": PENDING_STALL.total_seconds() / 3600,
                           "running_stall_hours": RUNNING_STALL.total_seconds() / 3600,
                           "loop_window_days": LOOP_WINDOW.days, "loop_min_runs": LOOP_MIN}}


# ---- department activity -----------------------------------------------------------------------

def _window_jobs(db, since):
    from sqlalchemy import or_, select

    from ..core.models import Job

    with db.session() as s:
        return [inv_mod._Job(j) for j in s.scalars(select(Job).where(or_(
            Job.created_at >= since, Job.started_at >= since, Job.finished_at >= since,
            Job.status.in_(("running",)))))]


def _bucket():
    return {"started": 0, "completed": 0, "failed": 0, "dead_letters": 0,
            "dead_defect": 0, "dead_refused": 0, "useful": 0, "no_op": 0, "running": 0,
            "cost_cad": 0.0, "busy_s": 0.0, "last_finished_at": None}


def _tally(b: dict, j, since, now) -> None:
    if j.started_at and j.started_at >= since:
        b["started"] += 1
    if j.status == "running":
        b["running"] += 1
    if j.status == "done" and j.finished_at and j.finished_at >= since:
        b["completed"] += 1
        b["useful" if _useful(j) else "no_op"] += 1
    if j.status == "failed" and (j.started_at or j.created_at) and (
            j.started_at or j.created_at) >= since:
        b["failed"] += 1
    if j.status == "dead" and j.finished_at and j.finished_at >= since:
        b["dead_letters"] += 1
        b["dead_" + ("refused" if _dead_kind(j) == "refused" else "defect")] += 1
    if j.started_at:
        end = j.finished_at or now
        start = max(j.started_at, since)
        if end > start:
            b["busy_s"] += (end - start).total_seconds()
    if j.finished_at and (b["last_finished_at"] is None or j.finished_at > b["last_finished_at"]):
        b["last_finished_at"] = j.finished_at


def _costs(db, since) -> tuple[dict, dict]:
    from sqlalchemy import select

    from ..core.models import CostEntry

    by_agent: dict[str, float] = {}
    by_dept: dict[str, float] = {}
    with db.session() as s:
        for c in s.scalars(select(CostEntry).where(CostEntry.at >= since)):
            by_agent[c.agent] = by_agent.get(c.agent, 0.0) + float(c.amount_cad or 0.0)
            d = c.department or "unattributed"
            by_dept[d] = by_dept.get(d, 0.0) + float(c.amount_cad or 0.0)
    return by_agent, by_dept


def next_cadences(db, *, now: datetime | None = None) -> list[dict]:
    """Each cadence's next window opening -- `Scheduler.tick`'s arithmetic, read-only."""
    from ..runtime.worker import CADENCES

    now = _aware(now) or datetime.now(timezone.utc)
    try:
        from ..swarm.orchestrate import suspended_job_types

        suspended = suspended_job_types(db, now=now)
    except Exception:  # noqa: BLE001
        suspended = {}
    out = []
    for name, agent, job_type, period in CADENCES:
        nxt = (int(now.timestamp() // period) + 1) * period
        out.append({"cadence": name, "agent": agent, "job_type": job_type,
                    "period_s": int(period), "suspended": job_type in suspended,
                    "next_at": datetime.fromtimestamp(nxt, timezone.utc).isoformat()})
    return sorted(out, key=lambda c: c["next_at"])


def activity(db, *, now: datetime | None = None) -> dict:
    from ..autonomy.charters import department_of

    now = _aware(now) or datetime.now(timezone.utc)
    cadences = next_cadences(db, now=now)
    nxt_by_agent: dict[str, dict] = {}
    for c in cadences:
        if not c["suspended"] and c["agent"] not in nxt_by_agent:
            nxt_by_agent[c["agent"]] = c
    out = {}
    for wname, span in WINDOWS.items():
        since = now - span
        agents: dict[str, dict] = {}
        depts: dict[str, dict] = {}
        for j in _window_jobs(db, since):
            _tally(agents.setdefault(j.agent, _bucket()), j, since, now)
            _tally(depts.setdefault(department_of(j.job_type) or "unchartered", _bucket()), j,
                   since, now)
        cost_a, cost_d = _costs(db, since)
        for name, cost in cost_a.items():
            agents.setdefault(name, _bucket())["cost_cad"] = round(cost, 4)
        for name, cost in cost_d.items():
            depts.setdefault(name, _bucket())["cost_cad"] = round(cost, 4)
        total = span.total_seconds()
        for name, b in list(agents.items()) + list(depts.items()):
            b["busy_s"] = round(b["busy_s"], 1)
            b["idle_s"] = round(max(0.0, total - b["busy_s"]), 1)
            b["last_finished_at"] = inv_mod._iso(b["last_finished_at"])
        for name, b in agents.items():
            c = nxt_by_agent.get(name)
            b["next_cadence"] = ({"cadence": c["cadence"], "job_type": c["job_type"],
                                  "next_at": c["next_at"]} if c else None)
        out[wname] = {
            "agents": [{"agent": k, **v} for k, v in sorted(agents.items())],
            "departments": [{"department": k, **v} for k, v in sorted(depts.items())]}
    return {"as_of": now.isoformat(), "windows": out}


def useful_split(db, *, now: datetime | None = None) -> dict:
    """Useful vs no-op completions per window, company-wide (the one judge)."""
    now = _aware(now) or datetime.now(timezone.utc)
    out = {}
    for wname, span in WINDOWS.items():
        since = now - span
        b = _bucket()
        for j in _window_jobs(db, since):
            _tally(b, j, since, now)
        out[wname] = {"completed": b["completed"], "useful": b["useful"], "no_op": b["no_op"],
                      "failed": b["failed"], "dead_defect": b["dead_defect"],
                      "dead_refused": b["dead_refused"]}
    return out


def next_work(db, *, now: datetime | None = None, limit: int = 15) -> dict:
    """The next scheduled work: due/pending jobs by run_after, and the next cadence windows."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    now = _aware(now) or datetime.now(timezone.utc)
    with db.session() as s:
        pending = [inv_mod._Job(j) for j in s.scalars(
            select(Job).where(Job.status == JobStatus.PENDING).order_by(Job.run_after)
            .limit(limit))]
    return {"pending": [{"job_id": j.id, "job_type": j.job_type, "agent": j.agent,
                         "run_after": inv_mod._iso(j.run_after), "product": j.slug,
                         "due": bool(j.run_after and j.run_after <= now)} for j in pending],
            "cadences": [c for c in next_cadences(db, now=now) if not c["suspended"]][:limit]}
