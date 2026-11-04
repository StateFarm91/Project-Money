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

    raw = ctx.job.inputs
    i = dict(raw) if isinstance(raw, dict) else None
    # W5-A9 (P0-PACKAGE-EVENT): a job naming one release is the event `launch.plan` raises
    # when that release's chain completes; one with no release is the six-hourly sweep, kept
    # as the safety net. Both run the same per-release step, so neither duplicates the other.
    scoped = i is not None and ("slug" in i or "version" in i)
    valid_event = bool(scoped and all(
        isinstance(i.get(key), str) and i[key].strip() and i[key] == i[key].strip()
        for key in ("slug", "version")) and ("release" not in i or isinstance(i["release"], str)))
    # The scheduler and its post-deploy retry use these exact forms. A typo or
    # incomplete event must not accidentally authorize a company-wide sweep.
    valid_sweep = bool(i is not None and (not i or (
        i.get("cadence") == "listing_package" and set(i) <= {"cadence", "retry_for_commit"}
        and ("retry_for_commit" not in i or (
            isinstance(i["retry_for_commit"], str) and bool(i["retry_for_commit"].strip()))))))
    if not valid_event and not valid_sweep:
        # An incomplete per-release event is not the scheduler's deliberate
        # unscoped sweep. Refuse it without touching other releases.
        ctx.audit("listing.package_invalid_scope", detail={
            "why": "expected a complete release event or recognized listing-package sweep"})
        return {"eligible": False, "releases": 0, "ready": 0, "changed": 0,
                "publishes": False, "work_done": False, "refused": "invalid_release_scope"}
    single = valid_event
    out = (LP.for_release(ctx.db, i["slug"], i["version"], expected_release=i.get("release", ""))
           if single else LP.sweep(ctx.db))
    if any(result.get("retry") for result in out["results"]):
        # Let the durable worker retry; do not report an unrecorded snapshot as done.
        raise RuntimeError("listing package changed repeatedly; retry the job")
    ctx.audit(JOB_TYPE, artifact=(f"{i['slug']}@{i['version']}" if single else None),
              detail={"trigger": "event" if single else "sweep",
                      "eligible": out.get("eligible", True),
                      "releases": out["releases"], "ready": out["ready"],
                      "changed": out["changed"],
                      "results": [{k: r.get(k) for k in ("key", "state", "blockers",
                                                         "review_requested", "error", "refused")}
                                  for r in out["results"][:30]]})
    refused = next((r["refused"] for r in out["results"] if r.get("refused")), None)
    return {"ran": True, "trigger": "event" if single else "sweep",
            "eligible": out.get("eligible", True), "releases": out["releases"],
            "ready": out["ready"], "changed": out["changed"], "publishes": False,
            "work_done": bool(out["changed"]), **({"refused": refused} if refused else {})}
