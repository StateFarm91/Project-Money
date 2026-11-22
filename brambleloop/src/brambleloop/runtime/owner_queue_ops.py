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
    # D-OWNER-APPROVE-ALL-3: every card, through the press's own path, inside its window.
    from ..ops import approve_all_directive

    approve3 = approve_all_directive.apply(ctx.db)
    out = oqc.sweep(ctx.db)
    summary = {"directive": out["directive"], "closed": out["closed"],
               "routine_superseded": len(out["routine_superseded"]),
               "auto_closed": len(out["auto_closed"]),
               "genuine_open": len(out["genuine_open"]),
               "unclassified_open": sorted(set(out["unclassified_open"]))[:50],
               "owner_directive": directive,
               "approve_all_3": {k: approve3.get(k) for k in ("ran", "closed_kept",
                                                              "approved", "failed")}}
    ctx.audit(JOB_TYPE, detail=summary)
    return {**summary, "ran": True,
            "work_done": (out["closed"] + len(directive["activated"])
                          + int(approve3.get("approved") or 0)
                          + int(approve3.get("closed_kept") or 0))}
