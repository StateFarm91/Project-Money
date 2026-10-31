"""`intel.scan_evidence` (market_radar): per-shop evidence that the competitor scans ran.

Daily. Joins what the scanners already recorded (the anchor's benchmark row and `mjs.scan`
jobs, the watchlist members' state, the listings each scan observed) into one durable reading
per UTC day for the owner's named shops and reference listings (`intel.scan_evidence`).
Read-only over this database; no network, model or spend.
"""
from __future__ import annotations

from .worker import JobContext, handlers

JOB_TYPE = "intel.scan_evidence"


@handlers.register(JOB_TYPE)
def handle_scan_evidence(ctx: JobContext) -> dict:
    from ..intel import scan_evidence as SE

    rep = SE.report(ctx.db)
    written = SE.record(ctx.db, rep)
    ctx.audit(JOB_TYPE, detail={"counts": rep["counts"], "scanned": rep["scanned"],
                                "not_scanned": rep["not_scanned"],
                                "credential": rep["credential"],
                                "references_observed": [r["listing_id"] for r in
                                                        rep["reference_listings"]
                                                        if r["observed"]],
                                "reading": written})
    return {"ran": True, "shops": len(rep["shops"]), "counts": rep["counts"],
            "scanned": len(rep["scanned"]), "reading": written,
            "work_done": len(rep["shops"])}
