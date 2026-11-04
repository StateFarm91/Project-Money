"""A nonfinite price is not a valid listing price."""
from sqlalchemy import select
import test_w4_departments as d
from brambleloop.core.models import Job, JobStatus, Listing
from brambleloop.publish import withholding
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker


def test_real_policy_worker_holds_nonfinite_price_and_recovers():
    cir = d._cir()
    db = d._db(cir, {"title": "Crochet pattern PDF", "description": "Crochet pattern.",
                     "tags": ["crochet pattern"], "price_cad": float("inf"), "state": "draft"})
    def run():
        job = JobQueue(db).enqueue("policy", "gate.policy", {"slug": cir.slug, "version": cir.version})
        assert Worker(db, "finite-price", job_types=["gate.policy"]).run_once()
        with db.session() as session:
            row = session.get(Job, job.id)
            assert row.status == JobStatus.DONE, row.last_error
            return dict(row.outputs)
    out = run()
    assert out["ok"] is False and "POLICY_NO_PRICE" in str(out["problems"]), out
    assert withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]
    with db.session() as session:
        session.scalar(select(Listing)).price_cad = 6.5
    assert run()["ok"] is True
    assert not withholding.reasons(db, cir.slug, cir.version)["blocks_publish"]


def test_nonfinite_and_boolean_prices_are_not_valid():
    from brambleloop.gates.policy import ListingDraft, check_listing
    def codes(price, compare=None):
        draft = ListingDraft(title="Crochet pattern", description="Crochet pattern.",
                             tags=[], price_cad=price, compare_at_cad=compare)
        return {f.code for f in check_listing(draft) if f.is_error}
    for bad in (float("nan"), float("inf"), float("-inf"), True, None):
        assert "POLICY_NO_PRICE" in codes(bad)
    for bad in (float("nan"), float("inf"), True):
        assert "POLICY_BAD_COMPARE_AT" in codes(6.5, bad)
    assert "POLICY_NO_PRICE" not in codes(6.5)
    assert "POLICY_BAD_COMPARE_AT" not in codes(6.5, 8.0)
