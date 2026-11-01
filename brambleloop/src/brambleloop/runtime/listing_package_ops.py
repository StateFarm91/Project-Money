"""`listing.package` (listing): the owner-review listing package for every certified release.

Every six hours. Assembles each certified release's package from the chain's own stored
outputs (`publish.listing_package`), records it durably, and raises one owner review request
for a package with no blocker. Internal writes only (class B, review OPUS2F A-6): no Etsy call,
model, network or spend, and nothing is published. Integrator item INTEG-LISTING-JOB, claimed as OPUS2-LISTING-PACKAGE-JOB.
"""
from __future__ import annotations

from .worker import JobContext, handlers

JOB_TYPE = "listing.package"


@handlers.register(JOB_TYPE)
def handle_listing_package(ctx: JobContext) -> dict:
    from ..publish import listing_package as LP

    out = LP.sweep(ctx.db)
    ctx.audit(JOB_TYPE, detail={"releases": out["releases"], "ready": out["ready"],
                                "changed": out["changed"],
                                "results": [{k: r.get(k) for k in ("key", "state", "blockers",
                                                                   "review_requested", "error")}
                                            for r in out["results"][:30]]})
    return {"ran": True, "releases": out["releases"], "ready": out["ready"],
            "changed": out["changed"], "publishes": False,
            "work_done": bool(out["changed"])}
