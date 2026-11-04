"""An owner-deferred question is not reused after its actual content changes."""
from sqlalchemy import select
from sqlalchemy.orm import load_only

from brambleloop.core.models import Listing, OperatingReading, OwnerAction, PatternVersion, Product
from brambleloop.ops import owner_queue
from brambleloop.publish import listing_package
from test_codex_a9_source_binding import fixture, package


def _park(db):
    original = package(db)
    assert listing_package.record(db, original)["review_requested"]
    with db.session() as session:
        action = session.scalar(select(OwnerAction).where(OwnerAction.done.is_(False)))
        owner_queue.transition(session, action, owner_queue.PARKED, "review later", actor="owner")
        return original, action.id


def test_changed_copy_supersedes_parked_request_without_sweep():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        session.scalar(select(Listing).where(Listing.product_slug == original["slug"])).title = "New copy"
    with db.session() as session:
        action = session.get(OwnerAction, action_id)
        assert action.done and action.state == owner_queue.SUPERSEDED
    assert listing_package.latest(db, original["slug"], original["version"])["state"] == listing_package.BLOCKED


def test_temporarily_uncertified_release_preserves_parked_owner_decision():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        version = session.scalar(select(PatternVersion).join(Product).where(Product.slug == original["slug"]))
        version.certified = False
    with db.session() as session:
        action = session.get(OwnerAction, action_id)
        assert not action.done and action.state == owner_queue.PARKED


def test_changed_design_and_product_identity_supersede_parked_request():
    for changed in ("design", "product_slug"):
        db = fixture()
        original, action_id = _park(db)
        with db.session() as session:
            product = session.scalar(select(Product).where(Product.slug == original["slug"]))
            if changed == "design":
                session.scalar(select(PatternVersion).where(
                    PatternVersion.product_id == product.id)).cir_json = {"changed": True}
            else:
                product.slug = "replacement-slug"
        with db.session() as session:
            action = session.get(OwnerAction, action_id)
            assert action.done and action.state == owner_queue.SUPERSEDED


def test_certificate_evidence_change_keeps_parked_owner_decision():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        version = session.scalar(select(PatternVersion).join(Product).where(Product.slug == original["slug"]))
        version.certificate = {"granted": False}
    with db.session() as session:
        action = session.get(OwnerAction, action_id)
        assert not action.done and action.state == owner_queue.PARKED


def test_ready_reassembly_of_identical_owner_document_keeps_parked_question():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        version = session.scalar(select(PatternVersion).join(Product).where(Product.slug == original["slug"]))
        version.certificate = {"granted": True, "transient_evidence": "updated"}
    updated = package(db)
    # Real assembly fingerprints the complete package, including the changed
    # source snapshot, even when the rendered owner document is identical.
    updated["fingerprint"] = "d" * 64
    assert updated["source_snapshot_sha256"] != original["source_snapshot_sha256"]
    result = listing_package.record(db, updated)
    assert result["state"] == listing_package.READY and not result["review_requested"], result
    with db.session() as session:
        action = session.get(OwnerAction, action_id)
        assert not action.done and action.state == owner_queue.PARKED
        assert len(list(session.scalars(select(OwnerAction)))) == 1


def test_legacy_unknown_parked_question_holds_reassembly():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        reading = session.scalar(select(OperatingReading).where(OperatingReading.kind == listing_package.KIND))
        payload = dict(reading.payload)
        payload.pop("owner_question_sha256", None)
        reading.payload = payload
    with db.session() as session:
        version = session.scalar(select(PatternVersion).join(Product).where(Product.slug == original["slug"]))
        version.certificate = {"granted": True, "transient_evidence": "updated"}
    updated = package(db)
    updated["fingerprint"] = "d" * 64
    result = listing_package.record(db, updated)
    assert result["state"] == listing_package.BLOCKED and not result["review_requested"], result
    with db.session() as session:
        action = session.get(OwnerAction, action_id)
        assert not action.done and action.state == owner_queue.PARKED
        assert len(list(session.scalars(select(OwnerAction)))) == 1


def test_rolled_back_copy_change_preserves_parked_request_and_package():
    db = fixture()
    original, action_id = _park(db)
    with db._sessions() as session:
        session.scalar(select(Listing).where(Listing.product_slug == original["slug"])).title = "New copy"
        session.flush()
        session.rollback()
    with db.session() as session:
        action = session.get(OwnerAction, action_id)
        assert not action.done and action.state == owner_queue.PARKED
    assert listing_package.latest(db, original["slug"], original["version"])["state"] == listing_package.READY


def test_deferred_same_value_is_not_a_new_owner_question():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        listing = session.scalar(select(Listing).options(load_only(Listing.id)).where(
            Listing.product_slug == original["slug"]))
        listing.title = "Adult Basket"
    with db.session() as session:
        action = session.get(OwnerAction, action_id)
        assert not action.done and action.state == owner_queue.PARKED
    assert listing_package.latest(db, original["slug"], original["version"])["state"] == listing_package.READY


def test_deleted_then_recreated_copy_supersedes_old_parked_question():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        listing = session.scalar(select(Listing).where(Listing.product_slug == original["slug"]))
        session.delete(listing)
    with db.session() as session:
        old = session.get(OwnerAction, action_id)
        assert not old.done and old.state == owner_queue.PARKED
        session.add(Listing(product_slug=original["slug"], version=original["version"],
                            title="Replacement", description="New copy", tags=["basket"],
                            release_hash=original["release_hash"]))
    with db.session() as session:
        old = session.get(OwnerAction, action_id)
        assert old.done and old.state == owner_queue.SUPERSEDED
    updated = package(db)
    assert listing_package.record(db, updated)["review_requested"]
    with db.session() as session:
        old = session.get(OwnerAction, action_id)
        assert old.done and old.state == owner_queue.SUPERSEDED
        active = list(session.scalars(select(OwnerAction).where(OwnerAction.done.is_(False))))
        assert len(active) == 1 and active[0].id != action_id


def test_deleted_then_identically_restored_copy_keeps_parked_decision():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        session.delete(session.scalar(select(Listing).where(Listing.product_slug == original["slug"])))
    with db.session() as session:
        session.add(Listing(product_slug=original["slug"], version=original["version"],
                            title="Adult Basket", description="Fixture copy", tags=["basket"],
                            release_hash=original["release_hash"]))
    with db.session() as session:
        old = session.get(OwnerAction, action_id)
        assert not old.done and old.state == owner_queue.PARKED
    assert not listing_package.record(db, package(db))["review_requested"]


def test_restoration_does_not_treat_temporary_evidence_or_state_as_new_copy():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        session.delete(session.scalar(select(Listing).where(Listing.product_slug == original["slug"])))
        version = session.scalar(select(PatternVersion).join(Product).where(Product.slug == original["slug"]))
        version.certificate = {"granted": False}
    with db.session() as session:
        session.add(Listing(product_slug=original["slug"], version=original["version"],
                            title="Adult Basket", description="Fixture copy", tags=["basket"],
                            release_hash=original["release_hash"], state="paused", seo_score=99.0,
                            etsy_listing_id="existing-id"))
    with db.session() as session:
        old = session.get(OwnerAction, action_id)
        assert not old.done and old.state == owner_queue.PARKED


def test_material_price_change_on_replacement_supersedes_old_question():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        session.delete(session.scalar(select(Listing).where(Listing.product_slug == original["slug"])))
    with db.session() as session:
        session.add(Listing(product_slug=original["slug"], version=original["version"],
                            title="Adult Basket", description="Fixture copy", tags=["basket"],
                            release_hash=original["release_hash"], price_cad=17.0))
    with db.session() as session:
        old = session.get(OwnerAction, action_id)
        assert old.done and old.state == owner_queue.SUPERSEDED


def test_legacy_missing_material_snapshot_preserves_park_until_reassembly():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        reading = session.scalar(select(OperatingReading).where(OperatingReading.kind == listing_package.KIND))
        payload = dict(reading.payload)
        payload.pop("listing_material_sha256", None)
        reading.payload = payload
        session.delete(session.scalar(select(Listing).where(Listing.product_slug == original["slug"])))
    with db.session() as session:
        session.add(Listing(product_slug=original["slug"], version=original["version"],
                            title="Replacement", description="New copy", tags=["basket"],
                            release_hash=original["release_hash"]))
    with db.session() as session:
        old = session.get(OwnerAction, action_id)
        assert not old.done and old.state == owner_queue.PARKED
    assert listing_package.latest(db, original["slug"], original["version"])["state"] == listing_package.BLOCKED
    assert listing_package.record(db, package(db))["review_requested"]
    with db.session() as session:
        assert session.get(OwnerAction, action_id).state == owner_queue.SUPERSEDED


def test_malformed_material_snapshot_does_not_supersede_a_parked_decision():
    db = fixture()
    original, action_id = _park(db)
    with db.session() as session:
        reading = session.scalar(select(OperatingReading).where(OperatingReading.kind == listing_package.KIND))
        reading.payload = {**reading.payload, "listing_material_sha256": "not-a-digest"}
        session.delete(session.scalar(select(Listing).where(Listing.product_slug == original["slug"])))
    with db.session() as session:
        session.add(Listing(product_slug=original["slug"], version=original["version"],
                            title="Replacement", description="New copy", tags=["basket"],
                            release_hash=original["release_hash"]))
    with db.session() as session:
        old = session.get(OwnerAction, action_id)
        assert not old.done and old.state == owner_queue.PARKED
