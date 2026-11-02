"""The job that runs `creative.enrichment_requests.sweep` (crochet_engineer).

Hourly. A brief the construction registry held for research enrichment becomes one precise,
deduplicated request for Research (W-CONCEPT answers it through `enrichment_requests.answer`).
CA$0, deterministic, never drafts or publishes by itself.
"""
from __future__ import annotations

from .worker import JobContext, handlers


@handlers.register("research.enrichment_sweep")
def handle_enrichment_sweep(ctx: JobContext) -> dict:
    from ..creative import enrichment_requests as er

    return er.sweep(ctx.db, audit=ctx.audit)
