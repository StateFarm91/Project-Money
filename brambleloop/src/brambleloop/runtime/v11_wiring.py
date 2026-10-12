"""v1.1 integrator wiring: the lane job types that run on the shared runtime.

Importing this module (runtime.pipeline does) registers four handlers:

* ``seo.cycle`` (lane G, ``seo.handler``): observe -> propose -> measure SEO; proposals only.
* ``finance.accounting.cycle`` (lane E, ``finance.accounting.job``): the Accountant cycle.
* ``ops.slo`` (lane I W-4): ``ops.slo.check`` -- SLOs evaluated, ``slo.*`` incidents raised,
  restated or closed through ``incident_lifecycle`` (stored notifications only).
* ``marketing.ads_readiness`` (lane H): ``growth.ads_readiness.tick`` -- eligibility evidence
  re-evaluated; a due refresh becomes an owner action. Spends nothing, activates nothing.

All four are GREEN: they read and write this database only, make no network call, spend no
model or ad money and contact nobody.
"""
from __future__ import annotations

from ..finance.accounting import job as _accounting_job  # noqa: F401 - registers the cycle
from ..seo import handler as _seo_handler  # noqa: F401 - registers seo.cycle
from .worker import JobContext, handlers

SLO_JOB = "ops.slo"
ADS_READINESS_JOB = "marketing.ads_readiness"


@handlers.register(SLO_JOB)
def handle_slo(ctx: JobContext) -> dict:
    from ..ops import slo

    r = slo.check(ctx.db)
    return {"ran": True, "inspected": len(r.get("slos") or {}),
            "incidents": r.get("incidents"),
            "states": {k: v.get("state") for k, v in (r.get("slos") or {}).items()}}


@handlers.register(ADS_READINESS_JOB)
def handle_ads_readiness(ctx: JobContext) -> dict:
    from ..growth import ads_readiness

    snap = ads_readiness.tick(ctx.db)
    prep = snap.get("preparation") or {}
    # Structural, not advisory: this job has no path to spend or activate. Say so in the
    # output so a reader of the job row does not have to take the module's word for it.
    if prep.get("campaign_activated") or prep.get("budget_authorised_cad") or \
            snap.get("activation_authorised"):
        raise RuntimeError("ads readiness tick reported activation or budget; refusing")
    return {"ran": True, "rechecked": 1, "etsy_ads_status": snap.get("etsy_ads_status"),
            "candidates": len(prep.get("candidates") or []), "spend_cad": 0.0,
            "campaign_activated": False}
