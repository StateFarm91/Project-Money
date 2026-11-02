"""Worker handlers for the existing quarantined reference library."""
from sqlalchemy import select

from ..core.models import BenchmarkProduct
from ..teardown import analysis_store, jobs, licence
from .worker import handlers


@handlers.register("teardown.analyse")
def handle_teardown_analyse(ctx):
    inputs = dict(ctx.job.inputs or {})
    ctx.assert_lease()
    result = analysis_store.analyse_file(ctx.db, inputs.get("benchmark_id"),
                                         inputs.get("file_sha256"))
    ctx.audit("teardown.analysis_recorded", detail={"benchmark_id": inputs["benchmark_id"],
              "file_sha256": inputs["file_sha256"], "analysis_id": result["id"]})
    # Analysis is not review: the purchase remains awaiting an analyst until
    # independent finding review is implemented and completed.
    return {"analysis_id": result["id"], "created": result["created"], "work_done": 1}


@handlers.register("teardown.analyse_sweep")
def handle_teardown_analyse_sweep(ctx):
    with ctx.db.session() as s:
        ids = list(s.scalars(select(BenchmarkProduct.id).where(
            BenchmarkProduct.teardown_state.in_(("queued", "awaiting_analyst")))))
    queued = existing = refused = 0
    for benchmark_id in ids:
        ctx.assert_lease()
        try:
            result = jobs.enqueue_purchase(ctx.db, benchmark_id)
        except licence.LicenceRefused:
            refused += 1
            continue
        queued += result["queued"]
        existing += result["existing"]
    return {"purchases": len(ids), "queued": queued, "existing": existing,
            "licence_refused": refused}
