"""Rollback rehearsal must read bytes, not just trust a filename."""
import hashlib

from brambleloop.commerce import deliverables
from brambleloop.core.artifacts import ArtifactStore
from brambleloop.core.models import Job, JobStatus, Listing, ListingAsset, PatternVersion, Product
from brambleloop.launch import rollback
from test_w4_firstsale_deliverables import _db


def test_rehearsal_rejects_corrupt_disk_and_accepts_verified_durable_copy(tmp_path):
    db = _db()
    store = ArtifactStore(tmp_path)
    pdf, image = b"%PDF-1.4 test", b"image test"
    pdf_sha, image_sha = (hashlib.sha256(value).hexdigest() for value in (pdf, image))
    store.put("item.pdf", pdf, "application/pdf")
    store.put("item.png", image, "image/png")
    with db.session() as session:
        product = Product(slug="item", title="Item")
        session.add(product)
        session.flush()
        session.add(PatternVersion(product_id=product.id, version="1", cir_json={},
                                   certified=True, release_hash="a" * 64, certificate={"granted": True}))
        session.add(Listing(product_slug="item", version="1", title="Item",
                            description="Fixture", tags=[], state="draft"))
        session.add(ListingAsset(product_slug="item", version="1", position=1,
                                 asset_class="photo", role="hero", sha256=image_sha))
        session.add(Job(agent="assets", job_type="assets.build", status=JobStatus.DONE,
                        inputs={"slug": "item", "version": "1", "release": "a" * 64},
                        outputs={"slug": "item", "version": "1", "release": "a" * 64, "pdf_sha256": pdf_sha}))
    def step():
        result = rollback.rehearse(db, slug="item", version="1", store=store)
        return next(s for s in result["steps"] if s["step"] == "deliverables_restorable")
    assert step()["ok"]
    (tmp_path / pdf_sha[:2] / pdf_sha).write_bytes(b"corrupt")
    assert not step()["ok"]
    assert deliverables.keep(db, pdf, "application/pdf", "test retained PDF")
    assert not step()["ok"], "an existing corrupt file blocks the current recovery path"
    (tmp_path / pdf_sha[:2] / pdf_sha).unlink()
    assert step()["ok"], "a separately verified durable copy is a valid missing-file fallback"
    assert store.get(pdf_sha, db=db) == pdf
