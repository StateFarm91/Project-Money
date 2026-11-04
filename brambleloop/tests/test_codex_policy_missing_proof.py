"""Unknown proof is not a passing proof position in operational re-verification."""
from sqlalchemy import select
import test_w4_departments as d
from brambleloop.core.models import Job, JobStatus
from brambleloop.publish import withholding
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker


def test_real_policy_worker_withholds_unproved_claim_and_clears_after_copy_fixed():
    cir = d._cir()
    listing = {"title": "Crochet pattern PDF", "description": "Maker tested pattern.",
               "tags": ["crochet pattern"], "price_cad": 6.5, "state": "draft"}
    db = d._db(cir, listing)

    def run():
        job = JobQueue(db).enqueue("policy", "gate.policy", {"slug": cir.slug, "version": cir.version,
                                                            "release_hash": "r" * 64})
        assert Worker(db, "test-policy", job_types=["gate.policy"]).run_once()
        with db.session() as session:
            row = session.get(Job, job.id)
            assert row.status == JobStatus.DONE, row.last_error
            return dict(row.outputs)

    out = run()
    assert out["ok"] is False and "POLICY_PROOF_OVERCLAIM" in str(out["problems"]), out
    held = withholding.reasons(db, cir.slug, cir.version)
    assert held["blocks_publish"] and withholding.QUALITY_REVERIFY in held["reasons"]
    from brambleloop.core.models import Listing
    with db.session() as session:
        session.scalar(select(Listing)).description = "Crochet pattern."
    assert run()["ok"] is True
    assert withholding.QUALITY_REVERIFY not in withholding.reasons(db, cir.slug, cir.version)["reasons"]


def test_explicit_proof_position_allows_earned_claim_and_missing_does_not():
    from brambleloop.gates.policy import check_proof_claims
    unproved = check_proof_claims("Maker tested.", "listing.description", None)
    assert any(item.code == "POLICY_PROOF_OVERCLAIM" for item in unproved)
    proof = {"deterministic_validation": True, "independent_reverse_compilation": True,
             "physical_tester_example": True}
    assert not check_proof_claims("Maker tested.", "listing.description", proof)
    assert not check_proof_claims("Crochet pattern.", "listing.description", None)
