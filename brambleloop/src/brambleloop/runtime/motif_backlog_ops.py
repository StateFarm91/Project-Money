"""The `assets.motif_backlog` job (ENG-MOTIF-BACKLOG): recover paid renders whose motif check
was refused for budget, by re-checking only the motif through a reservation. See
`publish.motif_backlog`. Never renders; regenerates only a genuine failure, through the
existing photography job."""
from __future__ import annotations

from ..publish import motif_backlog as MB
from .worker import JobContext, handlers

JOB_TYPE = MB.JOB_TYPE


@handlers.register(JOB_TYPE)
def handle_motif_backlog(ctx: JobContext) -> dict:
    out = MB.sweep(ctx.db, ctx.enqueue, audit=ctx.audit)
    return {"rechecked": out["rechecked"], "new": out["scan"]["new"],
            "states": out["states"], "advanced": len(out["advanced"]),
            "work_done": out["work_done"]}
