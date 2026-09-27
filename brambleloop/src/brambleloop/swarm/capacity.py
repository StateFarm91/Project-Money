"""Capacity that decides something: workers, functions and production lanes at the claim.

Certification C-68 (#5, #30, #175, #188). The allocations existed and were recorded, and the
running system could not act on any of them: one worker thread ran one job at a time, so a
lane limit of one could never hold anything back; the #30 function mix was a weekly audit row
nobody read; and the Fast/Flagship label (#5) was attached to a product and then drove no
queue, priority or engineering capacity. This module is the part that turns each of them into
a decision the worker makes when it claims a job.

Three limits, all read from the database at the claim, all work-conserving -- a job is held
back only when *something else that is starved* is waiting, never merely because a share was
reached with nothing else to do:

1. **Workers** (#175, #188). The runner starts a pool of worker threads
   (`BRAMBLELOOP_WORKER_THREADS`, default 3) and activates as many of them as the latest
   swarm allocation's open work justifies (`worker_target`). The governor's parallelism
   advice moves that target: `scale_up` adds a worker, `scale_down` returns to one. Quiet
   periods run one worker; a fan-out runs the pool.
2. **Functions** (#30). Every agent belongs to one of the four functions of
   `scale/allocation.py`. The latest `ops.capacity` reading's mix is the target share of the
   active workers; a job whose function already holds its share is held while another
   function with runnable work is below its own -- which is how the distribution floor is
   enforced on actual work rather than on a report.
3. **Production lanes** (#5). A product engineering job (drafting, compiling, certifying,
   asset building, listing drafting) for a product `gate.lanes` routed to the Fast or
   Flagship queue is counted against that lane's capacity, split by `commerce.lanes.allocate`
   (which refuses a split that breaks either floor). A lane over its share is held while the
   other lane has runnable engineering work below its share.

Nothing here spends, raises a ceiling or skips a gate. A held job goes back to the queue
unchanged (`swarm.orchestrate.lane_hold`), its attempt not counted.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone

from ..scale import allocation as mix_mod

DISTRIBUTION = mix_mod.DISTRIBUTION
PRODUCT_QA = mix_mod.PRODUCT_QA
MARKET_INTELLIGENCE = mix_mod.MARKET_INTELLIGENCE
INFRASTRUCTURE = mix_mod.INFRASTRUCTURE

# Which of #30's four functions each agent's work is. Written down, not inferred from a name:
# the function decides which floor a job counts against.
FUNCTION_OF_AGENT: dict[str, str] = {
    "crochet_engineer": PRODUCT_QA, "validator": PRODUCT_QA, "quality_director": PRODUCT_QA,
    "asset_truth": PRODUCT_QA, "policy": PRODUCT_QA, "publishing": PRODUCT_QA,
    "market_radar": MARKET_INTELLIGENCE, "creative_director": MARKET_INTELLIGENCE,
    "pricing": MARKET_INTELLIGENCE, "experiment_steward": MARKET_INTELLIGENCE,
    "growth": DISTRIBUTION, "listing": DISTRIBUTION, "store_operator": DISTRIBUTION,
    "ads": DISTRIBUTION, "support": DISTRIBUTION,
    "orchestrator": INFRASTRUCTURE, "cfo": INFRASTRUCTURE, "swarm_steward": INFRASTRUCTURE,
}

# The product engineering work a production lane's capacity is made of (#5: "making
# capacity, never a count of products"). Each carries the product's slug in its inputs.
ENGINEERING_JOB_TYPES: frozenset[str] = frozenset({
    "cir.draft", "cir.compile", "gate.certify", "assets.build", "listing.draft",
    "collection.assemble", "assets.owned_photography", "assets.model_photography",
})

DEFAULT_WORKER_THREADS = 3
LANE_ROUTED_ACTION = "gate.lane_routed"
LANE_CAPACITY_ACTION = "lanes.capacity"
CAPACITY_ACTION = "ops.capacity"
# A capacity reading older than this is not acted on.
READING_MAX_AGE = timedelta(days=8)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def worker_threads(env=None) -> int:
    """The worker pool size this deployment runs. Default above one, so limits can bind."""
    env = os.environ if env is None else env
    try:
        n = int(env.get("BRAMBLELOOP_WORKER_THREADS", DEFAULT_WORKER_THREADS))
    except ValueError:
        n = DEFAULT_WORKER_THREADS
    return max(1, n)


def function_of(agent: str) -> str:
    """The #30 function an agent's work counts against. Unmapped (meta) agents: infrastructure."""
    return FUNCTION_OF_AGENT.get(agent, INFRASTRUCTURE)


# ---------------------------------------------------------------------------
# readings


def latest_mix(db, *, now: datetime | None = None) -> dict:
    """The #30 target mix: the latest weekly `ops.capacity` reading, else the build mix."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == CAPACITY_ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        if row is not None and now - _aware(row.at) <= READING_MAX_AGE:
            mix = dict((row.detail or {}).get("mix") or {})
            if mix and mix_mod.check_mix(mix).get("ok"):
                return {"mix": mix, "source": f"ops.capacity audit {row.id}",
                        "phase": (row.detail or {}).get("phase"),
                        "constraint": (row.detail or {}).get("constraint")}
    return {"mix": dict(mix_mod.BUILD_MIX), "source": "build mix (no recent ops.capacity)",
            "phase": "build", "constraint": None}


def function_budgets(mix: dict[str, float], workers: int) -> dict[str, int]:
    """Workers each function may hold at once: its share of the pool, at least one."""
    return {f: max(1, math.floor(share * workers + 1e-9)) for f, share in mix.items()}


def product_lane(db, slug: str) -> str | None:
    """The queue `gate.lanes` last routed this product to, or None (unrouted: not held)."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    if not slug:
        return None
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.action == LANE_ROUTED_ACTION,
            AuditLog.artifact.like(f"{slug}@%")).order_by(desc(AuditLog.id)).limit(1))
    return (row.detail or {}).get("lane") if row is not None else None


def lane_limits(db, engineering_workers: int) -> dict:
    """Each production lane's share of engineering capacity, via `lanes.allocate`."""
    from sqlalchemy import desc, select

    from ..commerce import lanes
    from ..core.models import AuditLog

    shares = None
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == LANE_CAPACITY_ACTION)
                       .order_by(desc(AuditLog.id)).limit(1))
        if row is not None:
            shares = (row.detail or {}).get("shares")
    plan = lanes.allocate(float(engineering_workers), shares or None)
    return {"units": plan["units"], "shares": plan["shares"],
            "limits": {k: max(1, math.floor(v + 1e-9)) for k, v in plan["units"].items()}}


def _slug(job) -> str:
    inputs = job.inputs if isinstance(job.inputs, dict) else {}
    return str(inputs.get("slug") or inputs.get("product_slug") or "")


def _live_running(rows, now):
    return [j for j in rows if j.lease_expires_at is None or _aware(j.lease_expires_at) > now]


def _runnable(rows, now):
    from ..core.models import JobStatus

    return [j for j in rows if j.status in (JobStatus.PENDING, JobStatus.FAILED)
            and _aware(j.run_after) <= now]


def share_decision(db, job, *, now: datetime | None = None, exempt=("swarm.",)) -> dict:
    """Whether a just-claimed job's function share and production-lane share leave it room.

    Held only when this job's function (or lane) already holds its share *and* another
    function (or lane) that is below its share has runnable work waiting. Otherwise it runs.
    """
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    now = now or datetime.now(timezone.utc)
    if job.job_type.startswith(tuple(exempt)):
        return {"hold": False, "why": "the allocator's own work is never held"}
    with db.session() as s:
        running = _live_running(list(s.scalars(select(Job).where(
            Job.status == JobStatus.RUNNING, Job.id != job.id))), now)
        waiting = _runnable(list(s.scalars(select(Job).where(
            Job.status.in_((JobStatus.PENDING, JobStatus.FAILED)),
            Job.run_after <= now, Job.id != job.id))), now)
        for j in running + waiting:
            s.expunge(j)
    running = [j for j in running if not j.job_type.startswith(tuple(exempt))]
    waiting = [j for j in waiting if not j.job_type.startswith(tuple(exempt))]

    workers = worker_threads()
    mix = latest_mix(db, now=now)
    budgets = function_budgets(mix["mix"], workers)
    mine = function_of(job.agent)
    held_by = {f: sum(1 for j in running if function_of(j.agent) == f) for f in budgets}
    starved = sorted(f for f in budgets if f != mine and held_by[f] < budgets[f]
                     and any(function_of(j.agent) == f for j in waiting))
    out = {"function": mine, "running_by_function": held_by, "budgets": budgets,
           "mix_source": mix["source"], "workers": workers}
    if held_by.get(mine, 0) >= budgets.get(mine, 1) and starved:
        return {**out, "hold": True, "kind": "function_share",
                "why": (f"{mine} already runs {held_by[mine]} of {workers} workers against a "
                        f"share of {budgets[mine]}, while {starved} have runnable work below "
                        f"their share (#30: the mix is enforced on work, not reported)")}

    if job.job_type in ENGINEERING_JOB_TYPES:
        lane = product_lane(db, _slug(job))
        if lane is not None:
            limits = lane_limits(db, budgets.get(PRODUCT_QA, 1))
            def lane_of(j):
                return product_lane(db, _slug(j)) if j.job_type in ENGINEERING_JOB_TYPES else None
            eng_running = [lane_of(j) for j in running if j.job_type in ENGINEERING_JOB_TYPES]
            in_lane = sum(1 for x in eng_running if x == lane)
            other_starved = sorted(
                other for other in limits["limits"] if other != lane
                and sum(1 for x in eng_running if x == other) < limits["limits"][other]
                and any(j.job_type in ENGINEERING_JOB_TYPES and lane_of(j) == other
                        for j in waiting))
            out.update({"lane": lane, "lane_limits": limits["limits"],
                        "lane_units": limits["units"], "lane_running": in_lane})
            if in_lane >= limits["limits"][lane] and other_starved:
                return {**out, "hold": True, "kind": "lane_share",
                        "why": (f"the {lane} lane already runs {in_lane} engineering job(s) "
                                f"against its share of {limits['limits'][lane]} while the "
                                f"{other_starved} lane has runnable engineering work below "
                                f"its share (#5: both floors hold on making capacity)")}
    return {**out, "hold": False, "why": "within its function share and lane share"}


# ---------------------------------------------------------------------------
# workers (#175, #188)


def worker_target(db, *, now: datetime | None = None, pool: int | None = None) -> dict:
    """How many of the pool's workers should be claiming now.

    Read from the latest allocation: the lanes with open work and the specialists granted to
    them, bounded by the pool. The governor's parallelism advice moves it -- `scale_up` adds
    one worker (added workers were materially adding throughput), `scale_down` returns to one
    (they were duplicating). No allocation: one worker, and it says so.
    """
    from . import orchestrate

    pool = pool or worker_threads()
    alloc = orchestrate.latest_allocation(db, now=now)
    if alloc is None:
        return {"target": 1, "pool": pool, "why": "no recent allocation; one worker"}
    wanted = sum(min(int(l.get("granted") or 0), max(1, int(l.get("open_work") or 0)))
                 for l in (alloc.get("lanes") or {}).values() if int(l.get("open_work") or 0))
    target = max(1, min(pool, wanted))
    advice = orchestrate.parallelism_advice(db, now=now)
    why = f"{wanted} specialist(s) granted to lanes with open work, pool of {pool}"
    if advice and advice.get("advice") == "scale_down":
        target = 1
        why += "; the governor found added workers duplicated work, so one runs"
    elif advice and advice.get("advice") == "scale_up":
        target = min(pool, max(target, 1) + 1)
        why += "; the governor found added workers raised throughput, so one more runs"
    return {"target": target, "pool": pool, "wanted": wanted,
            "parallelism": (advice or {}).get("advice"),
            "allocation_id": alloc.get("allocation_id"), "why": why}


def measured_lane_split(db, *, days: int = 7, now: datetime | None = None) -> dict:
    """Engineering job-seconds per production lane over the window: the split actually run."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    seconds: dict[str, float] = {}
    with db.session() as s:
        rows = [(j.job_type, dict(j.inputs or {}), j.started_at, j.finished_at)
                for j in s.scalars(select(Job).where(
                    Job.status == JobStatus.DONE, Job.finished_at >= since,
                    Job.job_type.in_(sorted(ENGINEERING_JOB_TYPES))))]
    for _jt, inputs, started, finished in rows:
        lane = product_lane(db, str(inputs.get("slug") or inputs.get("product_slug") or ""))
        if lane is None or started is None or finished is None:
            continue
        seconds[lane] = seconds.get(lane, 0.0) + max(
            1.0, (_aware(finished) - _aware(started)).total_seconds())
    total = sum(seconds.values())
    return {"seconds": {k: round(v, 3) for k, v in seconds.items()}, "total": round(total, 3),
            "shares": ({k: v / total for k, v in seconds.items()} if total else None),
            "days": days}
