"""Receipt rehearsal must not treat false-looking strings as paid or digital."""
import hashlib

import pytest
from brambleloop.commerce import deliverables as d
from brambleloop.core.artifacts import ArtifactStore
from brambleloop.core.models import AuditLog
from test_w4_firstsale_deliverables import _db


@pytest.mark.parametrize("flag", ["false", "0", 1, None])
def test_unknown_payment_flag_does_not_create_paid_delivery_links(flag):
    receipt = {"is_paid": flag, "transactions": [{"listing_id": "1", "is_digital": True}]}
    assert d.delivery_links(receipt, {"1": ("item", "1")}) == []


@pytest.mark.parametrize("flag", ["false", "0", 1, False])
def test_conflicting_payment_status_does_not_override_bad_flag(flag):
    receipt = {"is_paid": flag, "status": "paid", "transactions": [{"listing_id": "1", "is_digital": True}]}
    assert d.delivery_links(receipt, {"1": ("item", "1")}) == []


def test_unknown_digital_status_fails_rehearsal_even_if_other_line_is_deliverable(tmp_path):
    db = _db()
    hashes = {}
    for terminology in ("US", "UK"):
        payload = ("%PDF-1.4 " + terminology).encode()
        hashes[terminology] = hashlib.sha256(payload).hexdigest()
        assert d.keep(db, payload, "application/pdf", "test")
    with db.session() as session:
        session.add(AuditLog(actor="assets", action="assets.built", artifact="item@1",
                             detail={"pdf_sha256_by_terminology": hashes}))
    receipt = {"receipt_id": "receipt", "is_paid": True, "transactions": [
        {"transaction_id": "good", "listing_id": "1", "is_digital": True},
        {"transaction_id": "unknown", "listing_id": "1", "is_digital": "false"},
        {"transaction_id": "physical", "listing_id": "1", "is_digital": False},
    ]}
    out = d.rehearse_purchase(db, receipt, {"1": ("item", "1")}, store=ArtifactStore(tmp_path))
    assert out["state"] == d.FAIL
    assert {f["transaction_id"] for f in out["files"]} == {"good", "unknown"}
    assert sum(f["state"] == d.PASS for f in out["files"]) == 2
    assert next(f for f in out["files"] if f["transaction_id"] == "unknown")["why"] == "digital status is not a boolean"
