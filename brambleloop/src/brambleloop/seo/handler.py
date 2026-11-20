"""The `seo.cycle` job handler: runs `seo.jobs.run_cycle` from the durable queue.

Importing this module registers the handler (the pattern `runtime.release` and
`runtime.growth_ops` use). It is not imported by the runtime yet -- see the WIRING REQUEST in
`research/final_build/v1_1/handoff_G.md` (pipeline import, cadence, agent permission).
No external effect: the cycle reads the database and writes only seo_* rows and one audit row.
"""
from __future__ import annotations

from ..runtime.worker import JobContext, handlers
from .jobs import JOB_TYPE, run_cycle


@handlers.register(JOB_TYPE)
def handle_seo_cycle(ctx: JobContext) -> dict:
    out = run_cycle(ctx.db)
    return {k: out[k] for k in ("changed", "evidence_added", "proposals_written",
                                "proposals_unchanged", "cycle_fingerprint", "taxonomy",
                                "attribution_status", "packages", "writes_to_etsy")}
