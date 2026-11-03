"""A child audience decision is for an exact design, not any CIR under its slug."""
import dataclasses

import test_a1r_child_safety_core as harness
from brambleloop.products import inventory, launch0
from brambleloop.publish import pdf


def test_child_assignment_is_bound_to_exact_version_and_content():
    for slug in launch0._cir_audience_map():
        original = inventory._engineered(slug)
        assert original is not None, slug
        state, assignment = launch0.childrens_decision_for(original)
        assert state == launch0.ASSIGNED and pdf.childrens_assignment(original) == assignment, slug
        for changed in (dataclasses.replace(original, version="9.9.9"),
                        dataclasses.replace(original, title="Different Child Design")):
            assert launch0.childrens_decision_for(changed)[0] == launch0.UNDECIDED
            assert pdf.childrens_assignment(changed) is None
            assert "exact design" in harness._refused(changed)
    # A separately constructed stuffed toy cannot inherit a basket's assignment.
    spoof = dataclasses.replace(harness._one_piece_ball(), slug="market-basket-medium",
                                title="Baby Cushion")
    assert launch0.childrens_decision_for(spoof)[0] == launch0.UNDECIDED
    assert pdf.childrens_assignment(spoof) is None
    result = harness._assets_build_full(spoof)
    assert harness._held(result), result
    assert result["outputs"]["reason"] == "undecided", result
    assert "exact design" in result["outputs"]["why"], result
    from brambleloop.core.models import OwnerAction
    from sqlalchemy import select
    with result["db"].session() as session:
        action = session.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"childrens-decision:{spoof.slug}"))
        assert "reapproval workflow is not yet implemented" in action.action, action.action
    # A previously stored certificate cannot skip the new assignment hold at publication.
    from brambleloop.core.models import PatternVersion
    from brambleloop.publish import eligibility
    from sqlalchemy import select
    with result["db"].session() as session:
        pv = session.scalar(select(PatternVersion).where(PatternVersion.version == spoof.version))
        pv.certificate = {"granted": True}
    verdict = eligibility.product_publication(result["db"], spoof.slug, spoof.version,
                                               listing={"title": spoof.title},
                                               first_customer=lambda *_a, **_k: [])
    assert not verdict["publishable"], verdict
    assert any("assignment does not bind" in r["why"] for r in verdict["reasons"]), verdict
    # The real SEO handler must refuse before writing copy under the wrong category.
    from brambleloop.core.models import Job, Listing
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker
    queued = JobQueue(result["db"]).enqueue("listing", "listing.seo",
        {"slug": spoof.slug, "version": spoof.version}, idempotency_key="codex:child:seo")
    assert Worker(result["db"], "child-seo", job_types=["listing.seo"]).run_once()
    with result["db"].session() as session:
        job = session.get(Job, queued.id)
        assert job.outputs["ok"] is False, job.outputs
        assert "assignment does not bind" in str(job.outputs["blocking"]), job.outputs
        assert session.scalar(select(Listing).where(Listing.product_slug == spoof.slug)) is None


if __name__ == "__main__":
    test_child_assignment_is_bound_to_exact_version_and_content()
    print("PASS exact child assignment binding through actual assets Worker")
