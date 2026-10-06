"""Dedicated execution lanes over the one durable queue -- not another scheduler.

Ported from Codex 8877f05 (`runtime/lanes.py`) and adapted to what this runtime already has.
Codex partitioned job types into disjoint operations/marketing/finance/production lanes. Since
then the runner gained a worker pool sized by the swarm allocation (C-68) and the queue gained
claim tiers (protected work first), so a second, competing concurrency scheme would fight the
first. The part of Codex's design that still closes a real gap is narrower:

**the control lane.** The Executive Orchestrator and the liveness checks are the company's
brain stem. With one active pool worker, a CPU-bound render or an eleven-product planning
cycle holds that worker for minutes, and the orchestrator -- the thing that notices an idle
department -- waits behind it. A dedicated thread that claims only CONTROL job types keeps the
loop turning while production work runs. It overlaps the pool rather than partitioning it
(claims are atomic, so two claimers cannot take one job), so nothing can be stranded on a
lane that is not running.

`departments` mode (one claimer per department, from the charters) is available for a
deployment with the headroom for it; it is not the default.
"""
from __future__ import annotations

CONTROL: frozenset[str] = frozenset({
    "autonomy.orchestrate", "autonomy.department_review", "autonomy.morning_handoff",
    "ops.heartbeat", "ops.health", "ops.queue_check",
})

MODES = ("serial", "control", "departments")


def partitions(known, mode: str = "control") -> dict[str, list[str] | None]:
    """Lane name -> the job types its dedicated claimer takes (None = everything).

    `company` is the existing worker pool and always claims everything, so every handler is
    covered whatever the mode; the other lanes are additional dedicated claimers.
    """
    known = set(known)
    if mode == "serial":
        return {"company": None}
    if mode == "control":
        return {"company": None, "control": sorted(CONTROL & known)}
    if mode == "departments":
        from ..autonomy.charters import CHARTERS, department_of

        lanes: dict[str, list[str] | None] = {"company": None}
        for ch in CHARTERS:
            types = sorted(jt for jt in known if department_of(jt) == ch.key)
            if types:
                lanes[ch.key] = types
        return lanes
    raise ValueError(f"BRAMBLELOOP_WORKER_LANES must be one of {MODES}, not {mode!r}")
