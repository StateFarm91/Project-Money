"""Quality re-verification must inspect each customer-visible listing tag."""
from sqlalchemy import select
import test_w4_departments as d
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.core.models import Job, JobStatus, Listing
from brambleloop.gates.asset_truth import check_technique_claims
from brambleloop.publish import withholding
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker


def test_real_asset_truth_worker_holds_and_recovers_for_tag_only_misclaim():
    cir = d._cir()
    assert check_technique_claims("bobble", cir, build_twin(cir, compile_cir(cir)))
    db = d._db(cir, {"title": "Crochet pattern PDF", "description": "Crochet pattern.",
                     "tags": ["bobble"], "price_cad": 6.5, "state": "draft"})
    def run():
        job = JobQueue(db).enqueue("asset_truth", "gate.asset_truth", {"slug": cir.slug, "version": cir.version})
        assert Worker(db, "asset-truth-test", job_types=["gate.asset_truth"]).run_once()
        with db.session() as session:
            row = session.get(Job, job.id)
            assert row.status == JobStatus.DONE, row.last_error
            return dict(row.outputs)
    out = run()
    assert out["ok"] is False and "CLAIM_TECHNIQUE_UNSUPPORTED" in str(out["problems"]), out
    held = withholding.reasons(db, cir.slug, cir.version)
    assert held["blocks_publish"] and withholding.QUALITY_REVERIFY in held["reasons"]
    with db.session() as session:
        session.delete(session.scalar(select(Listing)))
    assert run()["ok"] is None
    assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
    with db.session() as session:
        session.add(Listing(product_slug=cir.slug, version=cir.version,
                            title="Crochet pattern PDF", description="Crochet pattern.",
                            tags=["crochet pattern"], price_cad=6.5, state="draft"))
    assert run()["ok"] is True
    assert withholding.QUALITY_REVERIFY not in withholding.reasons(db, cir.slug, cir.version)["reasons"]


def test_malformed_tag_collection_is_not_a_clean_reverification():
    cir = d._cir()
    db = d._db(cir, {"title": "Crochet pattern PDF", "description": "Crochet pattern.",
                     "tags": {"bobble": True}, "price_cad": 6.5, "state": "draft"})
    job = JobQueue(db).enqueue("asset_truth", "gate.asset_truth", {"slug": cir.slug, "version": cir.version})
    assert Worker(db, "asset-truth-malformed", job_types=["gate.asset_truth"]).run_once()
    with db.session() as session:
        row = session.get(Job, job.id)
        assert row.status == JobStatus.DONE and row.outputs["ok"] is False, row.last_error
        assert "malformed" in str(row.outputs["problems"])
    assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
