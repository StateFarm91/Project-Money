"""Spelling variants of the existing proof claims receive the same evidence gate."""
import pytest
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.gates import first_customer as fc
from brambleloop.products import launch0


@pytest.mark.parametrize("claim", ["maker-tested", "maker\u2011tested", "test-crocheted"])
def test_unproved_hyphenated_claim_refused_in_listing_gate(claim):
    cir = launch0.cir_for("basket_small")
    twin = build_twin(cir, compile_cir(cir))
    listing = {"title": "Bread Basket | Crochet Pattern PDF",
               "description": f"A crochet basket pattern; {claim}.",
               "tags": ["basket crochet"], "price_cad": 6.5}
    check = fc.check_listing_claims(cir, twin, listing, physically_evidenced=False)
    assert check.state == fc.FAIL and "POLICY_PROOF_OVERCLAIM" in check.detail, check
    assert fc.check_listing_claims(cir, twin, listing, physically_evidenced=True).state == fc.PASS


def test_real_certification_handler_refuses_stored_unproved_test_crocheted_claim():
    from sqlalchemy import select
    import test_launch0_listing_truth as h
    from brambleloop.core.models import AuditLog, Listing

    db = h._db("proof_claim")
    cir = launch0.cir_for("hexagon_coasters")
    with db.session() as session:
        session.add(Listing(product_slug=cir.slug, version=cir.version,
                            title="Hexagon Coaster Set | Crochet Pattern PDF",
                            description="Test-crocheted coaster pattern.", price_cad=4.0,
                            tags=["coaster crochet"], state="draft"))
    job = h._run(db, "quality_director", "gate.certify", {"cir": cir.to_dict()}, "proof")
    assert job.outputs.get("granted") is False and "test crocheted" in str(job.outputs), job.outputs
    with db.session() as session:
        refusal = session.scalar(select(AuditLog).where(AuditLog.action == "gate.blocked"))
        assert refusal is not None and "test crocheted" in str(refusal.detail), refusal
