"""`ops.owner_queue_consolidate` (orchestrator, BUILD, hourly; ENG-APPROVALS).

Applies the owner's standing authority D-OWNER-STANDING-INTERNAL to the owner queue
(`ops.owner_queue_consolidate.sweep`): routine internal cards are superseded by the directive,
redundant / stale / satisfied cards are closed with their reason, genuine exceptions are never
touched. Every move keeps the row and writes an audit row citing the directive. No network,
no model, no spend; it signs, publishes and messages nothing.
"""
from __future__ import annotations

from .worker import JobContext, handlers

JOB_TYPE = "ops.owner_queue_consolidate"


@handlers.register(JOB_TYPE)
def handle_owner_queue_consolidate(ctx: JobContext) -> dict:
    from ..ops import owner_directives
    from ..ops import owner_queue_consolidate as oqc

    # D-OWNER-APPROVE-ALL is applied here, as its own step, never inside the sweep: the sweep
    # signs no grant. `apply` writes each listed activation once and never renews one.
    directive = owner_directives.apply(ctx.db)
    # D-OWNER-AUDIT-APPROVALS (F-01): the directed SHADOW -> STAGING move, attempted through
    # every gate of the phase record (readiness evaluated now); a refusal is recorded and
    # retried next pass. Hourly, not at boot: the readiness verdict is a long read.
    phase_directive = owner_directives.apply_phase(ctx.db)
    out = oqc.sweep(ctx.db)
    summary = {"directive": out["directive"], "closed": out["closed"],
               "routine_superseded": len(out["routine_superseded"]),
               "auto_closed": len(out["auto_closed"]),
               "genuine_open": len(out["genuine_open"]),
               "unclassified_open": sorted(set(out["unclassified_open"]))[:50],
               "owner_directive": directive,
               "phase_directive": {k: phase_directive.get(k) for k in
                                   ("recorded", "already", "transition_id")}}
    ctx.audit(JOB_TYPE, detail=summary)
    return {**summary, "ran": True, "work_done": out["closed"] + len(directive["activated"])}
