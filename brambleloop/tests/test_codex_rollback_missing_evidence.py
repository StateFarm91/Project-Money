"""Incomplete artifact metadata must produce an audited rollback refusal."""
import hashlib

import pytest
from sqlalchemy import select
from brambleloop.core.artifacts import ArtifactStore
from brambleloop.core.models import AuditLog, Job, JobStatus, Listing, ListingAsset, PatternVersion, Product
from brambleloop.launch import rollback
from test_w4_firstsale_deliverables import _db


@pytest.mark.parametrize("defect", ["missing-frame", "invalid-frame", "invalid-pdf", "malformed-pdf-map"])
def test_incomplete_artifact_evidence_is_audited_as_refused(tmp_path, defect):
    db = _db()
    store = ArtifactStore(tmp_path)
    pdf, image = b"%PDF-1.4 fixture", b"image fixture"
    pdf_sha, image_sha = (hashlib.sha256(v).hexdigest() for v in (pdf, image))
    store.put("item.pdf", pdf, "application/pdf")
    store.put("item.png", image, "image/png")
    with db.session() as session:
        product = Product(slug="item", title="Item")
        session.add(product)
        session.flush()
        session.add(PatternVersion(product_id=product.id, version="1", cir_json={},
                                   certified=True, certificate={"granted": True}))
        session.add(Listing(product_slug="item", version="1", title="Item", description="Fixture", tags=[], state="draft"))
        session.add(ListingAsset(product_slug="item", version="1", position=1, asset_class="photo", role="hero",
                                 sha256=None if defect == "missing-frame" else "bad" if defect == "invalid-frame" else image_sha))
        output = {"slug": "item", "version": "1", "pdf_sha256": pdf_sha}
        if defect == "invalid-pdf":
            output["pdf_sha256_by_terminology"] = {"US": pdf_sha, "UK": None}
        elif defect == "malformed-pdf-map":
            output["pdf_sha256_by_terminology"] = []
        session.add(Job(agent="assets", job_type="assets.build", status=JobStatus.DONE, outputs=output))
    result = rollback.rehearse(db, slug="item", version="1", store=store)
    step = next(s for s in result["steps"] if s["step"] == "deliverables_restorable")
    assert not result["ok"] and not step["ok"]
    assert step["invalid_pdf_hashes" if defect in {"invalid-pdf", "malformed-pdf-map"} else "invalid_frame_hashes"] == 1
    with db.session() as session:
        audit = session.scalar(select(AuditLog).where(AuditLog.action == rollback.ACTION))
        assert audit is not None and audit.detail["ok"] is False
