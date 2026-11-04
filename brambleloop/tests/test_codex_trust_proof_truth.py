"""Synthetic unlinked rows must not clear the paid-traffic trust rung."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from brambleloop.commerce import trust
from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog, CreatorProfile, Customer, LedgerEntry, Order, PhysicalTest
from brambleloop.quality import physical, tester_programme
from brambleloop.runtime.growth_ops import proof_sweep


def test_bare_owner_and_duplicate_sale_rows_cannot_clear_actual_trust_gate(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'proof.db'}", scratch=True)
    db.create_all()
    with db.session() as session:
        for index in range(3):
            session.add(PhysicalTest(product_slug=f"p{index}", version="1.0.0", tester_ref="owner",
                passed=True, completed_at=datetime.now(timezone.utc), measured={"owner_made": True}))
            session.add(LedgerEntry(category="sale", evidence_ref="fixture-duplicate", gross_cad=10))
    decision = trust.may_scale_ads(db, storefront_problems=[], disclosure_ok=True, claims_ok=True,
        thumbnails_coherent=True, support_meets_target=True,
        search_gate={"cleared": True, "failed": [], "unmeasured": []})
    assert decision["may_scale"] is False and "legitimate_proof" in decision["blocking"]
    assert trust.proof_count(db)["total"] == 0
    result = proof_sweep(db)
    assert result["recorded"] == 0 and result["withheld"] == 6
    with db.session() as session:
        row_id = session.scalar(select(PhysicalTest.id))
        assert not list(session.scalars(select(AuditLog).where(AuditLog.action == "trust.proof")))
    with pytest.raises(trust.TrustRefused):
        trust.record_proof(db, origin="physical_test", row_id=row_id, summary="fixture")


def test_linked_synthetic_evidence_counts_once_per_recorded_identity(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'proof.db'}", scratch=True)
    db.create_all()
    tester_programme.record_agreement(db, handle_ref="fixture-tester", specialties=["home_decor"],
        express_consent=True, consent_source="synthetic fixture", relationship="none",
        qualification="https://example.test/projects/fixture")
    report = physical.SampleReport(product_slug="fixture-pattern", version="1.0.0",
        tester_ref="fixture-tester", grams_by_color={"fixture": 100},
        ball_band=physical.BallBand(100, 200), instructions_followed=True)
    assessment = physical.SampleAssessment(report=report, estimated_metres={"fixture": 200},
        measured_metres={"fixture": 200}, factor=1.0, size_agrees=True,
        scope="full_make", made={"blanket": 1}, whole_pattern=True)
    first = physical.record(db, assessment, content_hash="a" * 64)
    physical.record(db, assessment, content_hash="a" * 64)
    with db.session() as session:
        buyer = Customer(customer_ref="fixture-buyer")
        session.add(buyer)
        session.flush()
        sold_at = datetime.now(timezone.utc)
        session.add(Order(customer_id=buyer.id, external_ref="fixture-order", product_slug="fixture-pattern",
            version="1.0.0", at=sold_at, price_cad=10, amount_original=10, revenue_cad=10,
            source="etsy_receipts", detail={"state": "paid"}))
        session.add(LedgerEntry(category="sale", evidence_ref="fixture-order", external_id="fixture-order",
            at=sold_at, source="etsy_receipts", basis="measured", gross_cad=10, amount_original=10))
    assert trust.proof_count(db) == {"physical_test": 1, "sale": 1, "total": 2}
    with db.session() as session:
        rows = list(session.scalars(select(PhysicalTest)))
        snapshots = {row.id: dict(row.measured) for row in rows}
        for row in rows:
            measured = dict(row.measured)
            agreement = dict(measured["tester_agreement"])
            agreement.pop("consent_source_sha256")
            row.measured = {**measured, "tester_agreement": agreement}
    assert trust.proof_count(db)["physical_test"] == 0  # old unbound rows are withheld
    with db.session() as session:
        for row in session.scalars(select(PhysicalTest)):
            row.measured = snapshots[row.id]
    assert trust.record_proof(db, origin="physical_test", row_id=first, summary="synthetic fixture")
    with db.session() as session:
        sale = session.scalar(select(LedgerEntry).where(LedgerEntry.evidence_ref == "fixture-order"))
        sale.gross_cad = 9
    assert trust.proof_count(db)["sale"] == 0
    with db.session() as session:
        sale = session.scalar(select(LedgerEntry).where(LedgerEntry.evidence_ref == "fixture-order"))
        sale.gross_cad = 10
        session.add(LedgerEntry(category="sale", evidence_ref="fixture-order", external_id="fixture-order",
            source="etsy_receipts", basis="measured", gross_cad=10, amount_original=10))
    assert trust.proof_count(db)["sale"] == 0  # ambiguous duplicate ledger evidence
    with db.session() as session:
        order = session.scalar(select(Order).where(Order.external_ref == "fixture-order"))
        order.refunded = True
    assert trust.proof_count(db)["sale"] == 0
    with db.session() as session:
        profile = session.scalar(select(CreatorProfile).where(CreatorProfile.ref == "fixture-tester"))
        permissions = [dict(permission) for permission in profile.permissions]
        permissions[-1]["consent_source"] = "changed-after-test"
        profile.permissions = permissions
    assert trust.proof_count(db)["physical_test"] == 0
