"""A single held terminology cannot certify both customer PDFs as durable."""
import hashlib
from pathlib import Path

import pytest
from brambleloop.commerce import deliverables as d
from brambleloop.core.artifacts import ArtifactStore
from brambleloop.core.models import AuditLog, ListingAsset
from brambleloop.gates import first_customer
from test_w4_firstsale_deliverables import _db


@pytest.mark.parametrize("present", ["US", "UK"])
def test_first_customer_gate_refuses_single_certified_terminology(tmp_path: Path, present: str):
    db = _db()
    store = ArtifactStore(tmp_path)
    pdf = b"%PDF-1.4 fixture"
    frame = b"fixture frame"
    pdf_hash = hashlib.sha256(pdf).hexdigest()
    frame_hash = hashlib.sha256(frame).hexdigest()
    assert d.keep(db, pdf, "application/pdf", d.keep_why("item", "1", present))
    assert d.keep(db, frame, "image/png", d.keep_why("item", "1", "frame"))
    with db.session() as session:
        session.add(AuditLog(actor="assets", action="assets.built", artifact="item@1",
                             detail={"pdf_sha256_by_terminology": {present: pdf_hash}}))
        session.add(ListingAsset(product_slug="item", version="1", position=1,
                                 asset_class="photo", role="hero", sha256=frame_hash))
    state = d.durable_state(db, "item", "1")
    assert state["state"] == d.FAIL
    missing = "UK" if present == "US" else "US"
    assert state["missing"] == [missing]
    assert first_customer.check_fulfilment_and_download(store, db=db, slug="item", version="1").state == first_customer.FAIL
    secured = d.secure_release(db, "item", "1", store=store, audit=False)
    assert secured["ok"] is False
    assert secured["pdfs"][missing]["held"] is False
    assert secured["pdfs"][present]["held"] is True
