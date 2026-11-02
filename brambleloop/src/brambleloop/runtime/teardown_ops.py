"""Worker handlers for the existing quarantined reference library."""
from sqlalchemy import select

from ..core.models import BenchmarkAnalysis, BenchmarkProduct, DesignRule
from ..improve import design_knowledge, knowledge_gaps
from ..quality import design_eval
from ..queue.durable import DuplicateJob, JobQueue
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
    gap = knowledge_gaps.observe_analysis(ctx.db, result["id"])
    ctx.audit("teardown.analysis_recorded", detail={"benchmark_id": inputs["benchmark_id"],
              "file_sha256": inputs["file_sha256"], "analysis_id": result["id"]})
    # Analysis is not review or approval: the observation remains proposed.
    return {"analysis_id": result["id"], "created": result["created"],
            "analysis_state": progress["state"], "gap_state": gap["state"],
            "work_done": int(result["created"] or gap["changed"])}


@handlers.register("teardown.analyse_sweep")
def handle_teardown_analyse_sweep(ctx):
    with ctx.db.session() as s:
        ids = list(s.scalars(select(BenchmarkProduct.id).where(
            BenchmarkProduct.teardown_state.in_(("queued", "awaiting_analyst", "needs_analyst")))))
        reviewed = list(s.scalars(select(BenchmarkAnalysis.id).where(
            BenchmarkAnalysis.review_state == "reviewed")))
        analyses = list(s.scalars(select(BenchmarkAnalysis.id)))
    queued = existing = refused = requeued = 0
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
        requeued += result.get("requeued", 0)
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
    gap_changes = 0
    for analysis_id in analyses:
        ctx.assert_lease()
        gap_changes += int(knowledge_gaps.observe_analysis(ctx.db, analysis_id)["changed"])
    return {"purchases": len(ids), "queued": queued, "existing": existing, "requeued": requeued,
            "licence_refused": refused, "knowledge_proposed": proposed,
            "knowledge_blocked": blocked, "gap_changes": gap_changes,
            "work_done": queued + proposed + gap_changes}


@handlers.register("design_eval.evaluate")
def handle_design_eval(ctx):
    ctx.assert_lease()
    with ctx.db.session() as s:
        rule = s.get(DesignRule, (ctx.job.inputs or {}).get("rule_id"))
        if rule is None or rule.state != "proposed":
            return {"state": "no_longer_proposed", "work_done": 0}
    try:
        result = design_eval.evaluate(ctx.db, (ctx.job.inputs or {}).get("rule_id"),
                                      expected_key=(ctx.job.inputs or {}).get("run_key"))
    except design_eval.StaleEvaluation:
        return {"state": "stale", "work_done": 0}
    ctx.assert_lease()
    return {"state": result["state"], "audit_id": result["audit_id"],
            "work_done": int(result["created"])}


@handlers.register("design_eval.sweep")
def handle_design_eval_sweep(ctx):
    with ctx.db.session() as s:
        ids = list(s.scalars(select(DesignRule.id).where(DesignRule.state == "proposed")))
    queued = existing = unknown = requeued = 0
    for rule_id in ids:
        ctx.assert_lease()
        try:
            key = design_eval.evaluation_key(ctx.db, rule_id)
            JobQueue(ctx.db).enqueue("orchestrator", "design_eval.evaluate",
                {"rule_id": rule_id, "run_key": key}, idempotency_key=key)
            queued += 1
        except DuplicateJob as exc:
            existing += 1
            result = JobQueue(ctx.db).requeue_dead(job_types=["design_eval.evaluate"],
                                                   ids=[exc.existing_id],
                                                   max_automatic_redrives=jobs.MAX_AUTOMATIC_REDRIVES)
            requeued += len(result["requeued"])
        except (design_eval.DesignEvaluationRefused, design_knowledge.DesignKnowledgeRefused):
            unknown += 1
    return {"queued": queued, "existing": existing, "requeued": requeued,
            "unavailable": unknown, "work_done": queued}
