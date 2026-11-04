"""Re-verification must check product and colourwork claims in live listing copy."""
import pytest
from sqlalchemy import select
import test_w4_departments as d
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.core.models import Job, JobStatus, Listing
from brambleloop.gates import first_customer as fc
from brambleloop.publish import withholding
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker


@pytest.mark.parametrize("title,tags,expected", [
    ("Blanket crochet pattern", ["crochet pattern"], "LISTING_PRODUCT_TYPE_UNSUPPORTED"),
    ("Basket crochet pattern", ["crochet blanket"], "LISTING_PRODUCT_TYPE_UNSUPPORTED"),
    ("Basket crochet pattern", ["tapestry crochet"], "LISTING_COLOURWORK_UNSUPPORTED"),
])
def test_real_worker_holds_wrong_identity_and_recovers(title, tags, expected):
    cir = d._cir()
    twin = build_twin(cir, compile_cir(cir))
    findings = fc.product_type_findings(cir, title=title, tags=tags) + fc.colourwork_findings(cir, twin, title=title, tags=tags)
    assert expected in str(findings), findings
    db = d._db(cir, {"title": title, "description": "Crochet pattern.",
                     "tags": tags, "price_cad": 6.5, "state": "draft"})
    def run():
        job = JobQueue(db).enqueue("asset_truth", "gate.asset_truth", {"slug": cir.slug, "version": cir.version, "release_hash": "r" * 64})
        assert Worker(db, "identity-test", job_types=["gate.asset_truth"]).run_once()
        with db.session() as session:
            row = session.get(Job, job.id)
            assert row.status == JobStatus.DONE, row.last_error
            return dict(row.outputs)
    result = run()
    assert result["ok"] is False and expected in str(result["problems"]), result
    assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
    with db.session() as session:
        row = session.scalar(select(Listing))
        row.title, row.tags = "Basket crochet pattern", ["basket crochet"]
    assert run()["ok"] is True
    assert not withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
