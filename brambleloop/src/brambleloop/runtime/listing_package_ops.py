"""`listing.package` (listing): the owner-review listing package for every certified release.

Every six hours (the safety net), and at once for one release when `launch.plan` finishes
its chain (W5-A9, the event path; inputs `slug`, `version`). Assembles each certified
release's package from the chain's own stored outputs (`publish.listing_package`), records
it durably, and raises one owner review request for a package with no blocker. Internal writes only (class B, review OPUS2F A-6): no Etsy call,
model, network or spend, and nothing is published. Integrator item INTEG-LISTING-JOB, claimed as OPUS2-LISTING-PACKAGE-JOB.
"""
from __future__ import annotations

from .worker import JobContext, handlers

JOB_TYPE = "listing.package"


@handlers.register(JOB_TYPE)
def handle_listing_package(ctx: JobContext) -> dict:
    from ..publish import listing_package as LP

    i = dict(ctx.job.inputs or {})
    # W5-A9 (P0-PACKAGE-EVENT): a job naming one release is the event `launch.plan` raises
    # when that release's chain completes; one with no release is the six-hourly sweep, kept
    # as the safety net. Both run the same per-release step, so neither duplicates the other.
    single = bool(i.get("slug") and i.get("version"))
    out = (LP.for_release(ctx.db, i["slug"], i["version"]) if single else LP.sweep(ctx.db))
    ctx.audit(JOB_TYPE, artifact=(f"{i['slug']}@{i['version']}" if single else None),
              detail={"trigger": "event" if single else "sweep",
                      "eligible": out.get("eligible", True),
                      "releases": out["releases"], "ready": out["ready"],
                      "changed": out["changed"],
                      "results": [{k: r.get(k) for k in ("key", "state", "blockers",
                                                         "review_requested", "error")}
                                  for r in out["results"][:30]]})
    return {"ran": True, "trigger": "event" if single else "sweep",
            "eligible": out.get("eligible", True), "releases": out["releases"],
            "ready": out["ready"], "changed": out["changed"], "publishes": False,
            "work_done": bool(out["changed"])}
