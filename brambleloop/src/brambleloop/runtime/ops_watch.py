"""Ops cadences that hold the build's own claims to account (Final Build FB-4).

`ops.maturity_disagreements` (F-125): a completion claim the measurement contradicts -- a
Build-2 requirement closed COMPLETE+PROVEN whose job types never ran, or a Final Master row at
INTEGRATED or above whose producer is not reached from any runtime root -- is a defect. It
was found by hand reconciliation before (C-78); this runs it daily and opens one incident per
disagreement, resolved on the run where claim and measurement agree again.
"""
from __future__ import annotations

from .worker import JobContext, handlers

JOB_TYPE = "ops.maturity_disagreements"


@handlers.register(JOB_TYPE)
def handle_maturity_disagreements(ctx: JobContext) -> dict:
    from ..build2 import maturity

    found = maturity.disagreements(ctx.db)
    recorded = maturity.record_disagreements(ctx.db, found)
    out = {"count": found["count"], "final_matrix": found["final_matrix"],
           "opened": recorded["opened"], "resolved": recorded["resolved"],
           "open": len(recorded["open"])}
    ctx.audit(JOB_TYPE, detail=out)
    return out
