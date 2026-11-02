"""Worker handlers for the existing quarantined reference library."""
from sqlalchemy import select

from ..core.models import BenchmarkAnalysis, BenchmarkProduct
from ..improve import design_knowledge
from ..teardown import analysis_store, jobs, licence
from .worker import handlers


@handlers.register("teardown.analyse")
def handle_teardown_analyse(ctx):
    inputs = dict(ctx.job.inputs or {})
    ctx.assert_lease()
    result = analysis_store.analyse_file(ctx.db, inputs.get("benchmark_id"),
                                         inputs.get("file_sha256"))
    ctx.assert_lease()
    progress = analysis_store.reconcile_state(ctx.db, inputs["benchmark_id"])
    ctx.audit("teardown.analysis_recorded", detail={"benchmark_id": inputs["benchmark_id"],
              "file_sha256": inputs["file_sha256"], "analysis_id": result["id"]})
    # Analysis is not review or approval: the observation remains proposed.
    return {"analysis_id": result["id"], "created": result["created"],
            "analysis_state": progress["state"], "work_done": 1}


@handlers.register("teardown.analyse_sweep")
def handle_teardown_analyse_sweep(ctx):
    with ctx.db.session() as s:
        ids = list(s.scalars(select(BenchmarkProduct.id).where(
            BenchmarkProduct.teardown_state.in_(("queued", "awaiting_analyst", "needs_analyst")))))
        reviewed = list(s.scalars(select(BenchmarkAnalysis.id).where(
            BenchmarkAnalysis.review_state == "reviewed")))
    queued = existing = refused = 0
    for benchmark_id in ids:
        ctx.assert_lease()
        try:
            result = jobs.enqueue_purchase(ctx.db, benchmark_id)
        except licence.LicenceRefused:
            refused += 1
            continue
        if result.get("reason") == "licence_refused":
            refused += 1
        queued += result["queued"]
        existing += result["existing"]
        analysis_store.reconcile_state(ctx.db, benchmark_id)
    proposed = blocked = 0
    for analysis_id in reviewed:
        ctx.assert_lease()
        try:
            result = design_knowledge.propose_from_analysis(ctx.db, analysis_id)
        except design_knowledge.DesignKnowledgeRefused:
            blocked += 1
            continue
        proposed += int(result["proposed"])
    return {"purchases": len(ids), "queued": queued, "existing": existing,
            "licence_refused": refused, "knowledge_proposed": proposed,
            "knowledge_blocked": blocked}
