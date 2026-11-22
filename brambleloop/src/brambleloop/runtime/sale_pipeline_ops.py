"""`sale.pipeline` and `sale.pipeline_sweep` (listing): the automatic sale chain
(D-OWNER-SALE-PIPELINE, HARD RULE; `publish.sale_pipeline`).

* `sale.pipeline` is one stage of one release's chain (admission -> gallery -> pdf_build ->
  pdf_certify -> attach -> ready). Each stage enqueues its successor under an idempotency
  key; the gallery stage is enqueued by `visual.image_production` when its run ends.
  Admission is the only place image spend can start, and only within the caps.
* `sale.pipeline_sweep` (hourly, Railway's scheduler) admits newly eligible releases,
  re-drives a stalled stage (bounded) and keeps one P2 incident per stalled release with its
  named blocker; an incident closes when its release is READY, parked or rejected.

Neither publishes, calls Etsy or a model, or spends by itself.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .worker import JobContext, handlers

ADMISSION_DELAY = timedelta(minutes=5)


def _follow(ctx: JobContext, *, run_after: datetime | None = None):
    from ..publish import sale_pipeline as SPL

    def follow(inputs, key):
        kw = {"idempotency_key": key}
        if run_after is not None:
            kw["run_after"] = run_after
        return ctx.enqueue(SPL.AGENT, SPL.JOB_TYPE, inputs, **kw)
    return follow


def start_images(ctx: JobContext):
    """Start an admitted release's image production: a new run, or the admitted re-entry of
    a run waiting in `awaiting_pre_image_readiness`. A run already at an end state hands
    straight on to the gallery stage."""
    from ..publish import sale_pipeline as SPL
    from ..visual import image_production as IP

    def enqueue(inputs, key):
        return ctx.enqueue(IP.AGENT, IP.JOB_TYPE, inputs, idempotency_key=key)

    def start(slug, version, release):
        run = SPL.image_run(ctx.db, slug, version, release)
        if run is None:
            # BATCH19F: the sale pipeline's gallery stage certifies the seven-frame FLUX
            # campaign (D-OWNER-FLUX-GALLERY), so a new run is started on that route.
            return {"started": "new", **IP.trigger(enqueue, slug=slug, version=version,
                                                   release=release, route=IP.SP.FLUX_ROUTE)}
        if run["state"] in (IP.AWAITING_PRE_IMAGE, "awaiting_certified_pattern"):
            # Re-enter exactly this run: its route is part of its key and its inputs.
            route = IP.route_of_key(run["run_key"])
            inputs = {"slug": slug, "version": version, "release": release,
                      "stage": IP.STAGES[0][0], "round": 0}
            if route:
                inputs["route"] = route
            if run.get("restarts"):
                inputs["epoch"] = int(run["restarts"])
            hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
            job = enqueue(inputs, IP.stage_key(slug, version, release, IP.STAGES[0][0],
                                               epoch=int(run.get("restarts") or 0),
                                               route=route)
                          + f":admitted:{hour}")
            return {"started": "admitted_reentry", "enqueued": job is not None,
                    "run_key": run["run_key"]}
        if run["state"] == IP.SALE_WAITING:
            # SALE-PREIMAGE: a FLUX run parked by the vis-gallery for-sale admission. The sale
            # pipeline admitted the release, so the run is re-entered through that admission
            # point: it re-checks `sale_admission` (both spend admissions must hold, Batch 19),
            # re-enters once per wait under its own idempotency key, or leaves the run parked
            # with the reason recorded. Before, this read as "in_progress" and nothing
            # re-entered the run until a six-hourly listing.package sweep, if ever.
            got = IP.admit_for_sale(ctx.db, enqueue, slug=slug, version=version,
                                    release=release)
            return {"started": "sale_readmission" if got.get("enqueued") else "still_waiting",
                    "enqueued": bool(got.get("enqueued")), "run_key": run["run_key"],
                    "admission": {k: (got.get("admission") or {}).get(k)
                                  for k in ("admitted", "why")}}
        if run["state"] in SPL.IMAGE_END_STATES:
            SPL.image_run_ended(_follow(ctx), slug=slug, version=version, release=release,
                                state=run["state"], epoch=int(run.get("restarts") or 0))
            return {"started": "already_ended", "state": run["state"],
                    "run_key": run["run_key"]}
        return {"started": "in_progress", "state": run["state"], "run_key": run["run_key"]}
    return start


@handlers.register("sale.pipeline")
def handle_sale_pipeline(ctx: JobContext) -> dict:
    from ..publish import sale_pipeline as SPL

    inputs = dict(ctx.job.inputs or {})
    out = SPL.run_stage(ctx.db, inputs, follow=_follow(ctx), start_images=start_images(ctx),
                        store_root=inputs.get("artifact_dir"))
    ctx.audit(SPL.AUDIT, artifact=f"{inputs.get('slug')}@{inputs.get('version')}",
              detail={k: out.get(k) for k in ("run_key", "stage", "state", "next", "blocker",
                                               "why", "admitted", "skipped")})
    return {**{k: v for k, v in out.items() if k != "certificates"},
            "work_done": bool(out.get("next") or out.get("admitted")
                              or out.get("state") == SPL.READY)}


@handlers.register("sale.pipeline_sweep")
def handle_sale_pipeline_sweep(ctx: JobContext) -> dict:
    from ..ops import incident_lifecycle as lifecycle
    from ..publish import sale_pipeline as SPL

    def incident(signature, summary, detail):
        with ctx.db.session() as s:
            lifecycle.open_or_restate(s, signature=signature[:200], severity="P2",
                                      product_slug=signature.split(":", 1)[-1].split("@")[0],
                                      summary=summary[:500], detail=detail,
                                      halts_publication=False)

    out = SPL.sweep(ctx.db, follow=_follow(ctx), incident=incident)
    closed = SPL.resolved_signatures(ctx.db)
    if closed:
        with ctx.db.session() as s:
            lifecycle.resolve_signatures(s, closed, resolution="release reached READY, or "
                                                               "was parked or rejected")
    board = SPL.board(ctx.db)
    ctx.audit(SPL.SWEEP_JOB_TYPE, detail={**{k: out[k] for k in ("admission_asked", "redriven",
                                                                  "stalled")},
                                          "board": {k: board.get(k) for k in (
                                              "eligible", "gallery_done", "pdfs_certified",
                                              "ready", "blocked_by_reason", "stalled")}})
    return {**out, "board": board}


def admission_follow(ctx: JobContext):
    """For the chain's entry points (end of launch.plan): admission a few minutes later,
    once the launch decision that selects the release for sale is DONE."""
    return _follow(ctx, run_after=datetime.now(timezone.utc) + ADMISSION_DELAY)
