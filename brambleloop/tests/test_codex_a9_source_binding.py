"""Review requests bind to the current release and copy, and a durable document."""
from unittest.mock import patch
from sqlalchemy import select

import test_w5_a9_package_event as t
from brambleloop.core.models import DurableArtifact, Listing, OwnerAction, PatternVersion, Product
from brambleloop.publish import listing_package as lp


def fixture():
    db = t._db("source-binding")
    with db.session() as s:
        p = Product(slug="test-bound-release", title="Fixture")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={},
                             certified=True, release_hash="a" * 64))
        s.add(Listing(product_slug=p.slug, version="1.0.0", title="Adult Basket",
                      description="Fixture copy", tags=["basket"], release_hash="a" * 64))
    return db


def package(db):
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == "test-bound-release"))
        copy = {"title": listing.title, "description": listing.description, "tags": listing.tags}
    digest = lp.listing_copy_digest(copy)
    return {"slug": "test-bound-release", "version": "1.0.0", "fingerprint": digest,
            "state": lp.READY, "release_hash": "a" * 64, "identity": {}, "copy": copy,
            "listing_snapshot_sha256": digest,
            "source_snapshot_sha256": lp._release(db, "test-bound-release", "1.0.0")["source_snapshot_sha256"],
            "blockers": []}


def active(db):
    return [key for key, done, _ in t._requests(db) if not done]


def test_changed_listing_invalidates_old_owner_request():
    db = fixture()
    old = package(db)
    assert lp.record(db, old)["review_requested"]
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == old["slug"]))
        listing.title = "Baby Basket"
    out = lp.record(db, old, expected_fingerprint=old["fingerprint"])
    assert out["retry"] is True and lp.latest(db, old["slug"], old["version"])["state"] == lp.BLOCKED
    assert not active(db)
    new = package(db)
    assert lp.record(db, new)["review_requested"]
    assert active(db)[0].endswith(new["fingerprint"][:16])


def test_price_or_design_changes_invalidate_old_owner_request():
    for field in ("price", "design"):
        db = fixture()
        old = package(db)
        assert lp.record(db, old)["review_requested"]
        with db.session() as session:
            if field == "price":
                listing = session.scalar(select(Listing).where(Listing.product_slug == old["slug"]))
                listing.price_cad += 1
            else:
                pv = session.scalar(select(PatternVersion).join(Product).where(Product.slug == old["slug"]))
                pv.cir_json = {"changed": True}
        out = lp.record(db, old, expected_fingerprint=old["fingerprint"])
        assert out["retry"] is True and not active(db), out
        assert lp.latest(db, old["slug"], old["version"])["state"] == lp.BLOCKED


def test_revoked_certification_never_raises_a_review():
    db = fixture()
    old = package(db)
    assert lp.record(db, old)["review_requested"]
    with db.session() as s:
        pv = s.scalar(select(PatternVersion).join(Product).where(Product.slug == old["slug"]))
        pv.certified = False
    out = lp.record(db, old, expected_fingerprint=old["fingerprint"])
    assert out["retry"] is True and not active(db)
    assert lp.latest(db, old["slug"], old["version"])["state"] == lp.BLOCKED


def test_storage_failure_closes_review_and_durable_artifact_is_retained():
    from brambleloop.core.artifacts import ArtifactStore
    db = fixture()
    item = package(db)
    out = lp.record(db, item)
    assert out["review_requested"] and out["markdown_sha256"]
    with db.session() as s:
        assert s.get(DurableArtifact, out["markdown_sha256"]) is not None
    with patch.object(ArtifactStore, "put", side_effect=OSError("storage failed")):
        blocked = lp.record(db, item, expected_fingerprint=item["fingerprint"])
    assert blocked["state"] == lp.BLOCKED and not active(db)
    assert lp.latest(db, item["slug"], item["version"])["state"] == lp.BLOCKED


def test_owner_request_match_escapes_slug_wildcards():
    db = t._db("slug-wildcard")
    release = "a" * 64
    for slug in ("sock_a", "sockXa"):
        with db.session() as session:
            product = Product(slug=slug, title=slug)
            session.add(product)
            session.flush()
            session.add(PatternVersion(product_id=product.id, version="1.0.0", cir_json={},
                                       certified=True, release_hash=release))
            session.add(Listing(product_slug=slug, version="1.0.0", title=slug,
                                description="fixture", tags=[], release_hash=release))
        copy = {"title": slug, "description": "fixture", "tags": []}
        digest = lp.listing_copy_digest(copy)
        item = {"slug": slug, "version": "1.0.0", "fingerprint": digest,
                "state": lp.READY, "release_hash": release, "identity": {}, "copy": copy,
                "listing_snapshot_sha256": digest,
                "source_snapshot_sha256": lp._release(db, slug, "1.0.0")["source_snapshot_sha256"],
                "blockers": []}
        assert lp.record(db, item)["review_requested"]
    with db.session() as session:
        listing = session.scalar(select(Listing).where(Listing.product_slug == "sock_a"))
        listing.title = "Updated A"
    copy = {"title": "Updated A", "description": "fixture", "tags": []}
    digest = lp.listing_copy_digest(copy)
    updated = {"slug": "sock_a", "version": "1.0.0", "fingerprint": digest,
               "state": lp.READY, "release_hash": release, "identity": {}, "copy": copy,
               "listing_snapshot_sha256": digest,
               "source_snapshot_sha256": lp._release(db, "sock_a", "1.0.0")["source_snapshot_sha256"],
               "blockers": []}
    assert lp.record(db, updated)["review_requested"]
    requests = active(db)
    assert len(requests) == 2, requests
    assert any("sockXa@1.0.0" in key for key in requests), requests
    assert any("sock_a@1.0.0" in key and key.endswith(digest[:16]) for key in requests), requests


def test_worker_rechecks_source_changed_after_assembly():
    db = fixture()
    old = package(db)
    assert lp.record(db, old)["review_requested"]
    calls = []

    def assemble_then_change(database, slug, version):
        calls.append(1)
        if len(calls) == 1:
            stale = package(database)
            with database.session() as s:
                pv = s.scalar(select(PatternVersion).join(Product).where(Product.slug == slug))
                pv.certified = False
            return stale
        return None  # the real assembler refuses an uncertified release

    with patch.object(lp, "assemble", side_effect=assemble_then_change):
        job = t._run(db, {"slug": old["slug"], "version": old["version"]},
                     "source-revoked-after-assembly")
    assert job.status == t.JobStatus.DONE, job.last_error
    assert len(calls) == 2
    assert lp.latest(db, old["slug"], old["version"])["state"] == lp.BLOCKED
    assert not active(db)


if __name__ == "__main__":
    test_changed_listing_invalidates_old_owner_request()
    test_price_or_design_changes_invalidate_old_owner_request()
    test_revoked_certification_never_raises_a_review()
    test_storage_failure_closes_review_and_durable_artifact_is_retained()
    test_worker_rechecks_source_changed_after_assembly()
    test_owner_request_match_escapes_slug_wildcards()
    print("6/6 passed")
