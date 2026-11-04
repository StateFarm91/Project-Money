"""A malformed stored listing cannot be treated as examined clean copy."""
from sqlalchemy import select
import pytest
import test_launch0_listing_truth as h
from brambleloop.core.models import AuditLog, Listing
from brambleloop.products import launch0


@pytest.mark.parametrize("tags", [{"coaster": True}, "coaster", None, [42]])
def test_certification_does_not_attest_malformed_stored_tags(tags):
    db = h._db("malformed_tags")
    cir = launch0.cir_for("hexagon_coasters")
    with db.session() as session:
        session.add(Listing(product_slug=cir.slug, version=cir.version,
                            title="Hexagon Coaster Set | Crochet Pattern PDF",
                            description="A crochet coaster pattern.", tags=tags,
                            price_cad=4.0, state="draft"))
    job = h._run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, "malformed")
    with db.session() as session:
        event = session.scalar(select(AuditLog).where(AuditLog.action.in_(["gate.certified", "gate.blocked"])))
        assert event is not None and event.action == "gate.blocked", job.outputs
    assert job.outputs.get("granted") is False and "POLICY_TAGS_INVALID" in str(job.outputs), job.outputs
