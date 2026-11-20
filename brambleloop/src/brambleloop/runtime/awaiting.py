"""F-464: no waiter occupancy -- wait on a durable external operation without holding a
worker thread.

A handler that starts an external operation (a render, an export, a provider batch) calls
`defer(ctx, ...)` and returns at once; the queue runs a poll job `delay_s` later. The poll
handler calls `check(...)` with what it observed: done -> the follow-on runs; not done ->
another poll is deferred, up to `max_polls`, after which the wait is recorded as given up
(never silently dropped). Every step is an ordinary durable job, so a restart loses nothing
and no thread sleeps on a provider. Idempotent per (operation, poll number).

Converting the long render handlers (`model_photography`, `owned_photography`) onto this is
their owners' change (the product-engine lane); this is the shared mechanism they use.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

ACTION = "runtime.await_external"


def defer(ctx, *, op_ref: str, poll_job_type: str, inputs: dict | None = None,
          delay_s: int = 60, max_polls: int = 30, poll: int = 1,
          now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    body = {**(inputs or {}), "await": {"op_ref": op_ref, "poll": poll, "max_polls": max_polls,
                                        "delay_s": delay_s}}
    job = ctx.enqueue(ctx.job.agent, poll_job_type, body,
                      idempotency_key=f"await:{op_ref}:{poll}"[:200],
                      run_after=now + timedelta(seconds=delay_s))
    ctx.audit(ACTION, artifact=op_ref[:200], detail={"poll": poll, "delay_s": delay_s,
                                                      "poll_job": getattr(job, "id", None)})
    return {"awaiting": op_ref, "poll": poll, "poll_job_id": getattr(job, "id", None),
            "thread_held": False}


def check(ctx, *, done: bool, observed: dict | None = None,
          now: datetime | None = None) -> dict:
    """Called by the poll handler with what it observed for the operation it was given."""
    a = dict((ctx.job.inputs or {}).get("await") or {})
    op_ref, poll = a.get("op_ref"), int(a.get("poll") or 1)
    if not op_ref:
        raise ValueError("this job carries no awaited operation")
    if done:
        ctx.audit(ACTION + ".done", artifact=op_ref[:200], detail={"polls": poll,
                                                                    **(observed or {})})
        return {"done": True, "op_ref": op_ref, "polls": poll}
    if poll >= int(a["max_polls"] if a.get("max_polls") is not None else 30):
        ctx.audit(ACTION + ".gave_up", artifact=op_ref[:200],
                  detail={"polls": poll, **(observed or {})})
        return {"done": False, "gave_up": True, "op_ref": op_ref, "polls": poll}
    inputs = {k: v for k, v in (ctx.job.inputs or {}).items() if k != "await"}
    nxt = defer(ctx, op_ref=op_ref, poll_job_type=ctx.job.job_type, inputs=inputs,
                delay_s=int(a["delay_s"] if a.get("delay_s") is not None else 60),
                max_polls=int(a["max_polls"] if a.get("max_polls") is not None else 30),
                poll=poll + 1, now=now)
    return {"done": False, "op_ref": op_ref, "polls": poll, "next": nxt}
