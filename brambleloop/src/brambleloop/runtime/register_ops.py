"""`products.stage_register` (orchestrator): the daily product stage register (P0 §6).

Derives every known product's stage on the owner's fifteen stages from the rows the
pipeline already wrote (`products.stage_register`), records one durable reading per UTC day
and audits the stalls and loops it measured. It reads this company's own tables only:
no model, no network, CA$0. It never moves a product, enqueues work, certifies anything or
opens an incident; what it writes is the reading the Command Center shows, so the dashboard
reports production output (certified versions, customer PDFs, visual and listing packages,
published listings) and the products that are stuck, rather than scheduled heartbeats.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..products import stage_register
from .worker import JobContext, handlers

JOB_TYPE = "products.stage_register"


@handlers.register(JOB_TYPE)
def handle_stage_register(ctx: JobContext) -> dict:
    raw = ctx.job.inputs.get("as_of")
    now = datetime.fromisoformat(raw) if raw else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    reg = stage_register.register(ctx.db, now=now)
    written = stage_register.record(ctx.db, reg)
    ctx.audit(stage_register.AUDIT_ACTION, artifact=written["period_key"], detail={
        "products": reg["products"], "counts": reg["counts"], "stalled": reg["stalled"],
        "looping": [{"slug": l["slug"],
                     "kinds": sorted({x["kind"] for x in l["loops"]})}
                    for l in reg["looping"]],
        "produced": reg["produced"], "owner_held": reg["owner_held"],
        "reading": {k: written[k] for k in ("kind", "period_key", "created")}})
    return {"ran": True, "work_done": reg["products"], "products": reg["products"],
            "counts": reg["counts"], "stalled": reg["stalled"],
            "looping": [l["slug"] for l in reg["looping"]], "produced": reg["produced"],
            "owner_held": reg["owner_held"], "reading": written}
