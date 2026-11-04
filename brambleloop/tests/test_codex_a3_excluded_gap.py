"""A terminally excluded supplement must not leave effective position gaps."""
from sqlalchemy import select

from brambleloop.core.db import Database
from brambleloop.core.models import ListingAsset, PhysicalPhoto
from brambleloop.publish import photo_asset_review as review
from brambleloop.publish import release_gates
import test_opus2_photo_asset_review as fixture
import test_physfix_photo_first as physical


def test_nonqualifying_supplement_leaves_contiguous_effective_gallery():
    db, cir, _, _ = fixture._setup()
    old_leader = fixture._photo_frame(db, cir)
    assert review.sweep(db)["approved"] == 1
    test_id = physical._passed_full_make(db, cir)
    fixture._second_attested_photo(db, cir, test_id)
    assert review.sweep(db)["approved"] == 1
    with db.session() as session:
        supplement = session.get(ListingAsset, old_leader)
        assert supplement.approved and not supplement.claims.get("leads_gallery")
        photo = session.get(PhysicalPhoto, supplement.claims["physical_photo_id"])
        photo.detail = {**photo.detail, "owner_attestation": {}}
        held = session.scalar(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version,
            ListingAsset.asset_class != review.PHOTO_CLASS))
        held_id = held.id
        held.approved = False
        held.blocked_reasons = list(held.blocked_reasons or []) + ["owner_veto"]
    review.sweep(db)
    reopened = Database(str(db.engine.url), scratch=True)
    with reopened.session() as session:
        supplement = session.get(ListingAsset, old_leader)
        assert not supplement.approved and any(
            str(reason).startswith(review.NOT_QUALIFYING) for reason in supplement.blocked_reasons)
        rows = list(session.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version)))
        assert sum(bool((row.claims or {}).get("leads_gallery")) for row in rows) == 1
        stable_positions = {row.id: row.position for row in rows}
        held = session.get(ListingAsset, held_id)
        assert not held.approved and "owner_veto" in held.blocked_reasons
    effective = release_gates._frames(reopened, cir.slug, cir.version)
    positions = sorted(row.position for row in effective)
    assert positions == list(range(1, len(positions) + 1)), positions
    review.sweep(reopened)
    with reopened.session() as session:
        again = {row.id: row.position for row in session.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version))}
    assert again == stable_positions


def test_preexisting_malformed_order_is_not_silently_repaired():
    db, cir, _, _ = fixture._setup()
    old_leader = fixture._photo_frame(db, cir)
    assert review.sweep(db)["approved"] == 1
    test_id = physical._passed_full_make(db, cir)
    fixture._second_attested_photo(db, cir, test_id)
    assert review.sweep(db)["approved"] == 1
    with db.session() as session:
        supplement = session.get(ListingAsset, old_leader)
        supplement.approved = False
        supplement.blocked_reasons = [review.AWAITING]
        photo = session.get(PhysicalPhoto, supplement.claims["physical_photo_id"])
        photo.detail = {**photo.detail, "owner_attestation": {}}
        rows = list(session.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version)))
        max(rows, key=lambda row: row.position).position += 7
    with db.session() as session:
        before = {row.id: row.position for row in session.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version))}
    result = review.review_frame(db, old_leader, reissue=False)
    assert result.get("not_qualifying") and result.get("excluded_frame_parked") is False
    with db.session() as session:
        after = {row.id: row.position for row in session.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version))}
        assert not session.get(ListingAsset, old_leader).approved
    assert after == before


def test_owner_held_leader_is_not_used_to_reorder_the_gallery():
    db, cir, _, _ = fixture._setup()
    old_leader = fixture._photo_frame(db, cir)
    assert review.sweep(db)["approved"] == 1
    test_id = physical._passed_full_make(db, cir)
    fixture._second_attested_photo(db, cir, test_id)
    assert review.sweep(db)["approved"] == 1
    with db.session() as session:
        supplement = session.get(ListingAsset, old_leader)
        supplement.approved = False
        supplement.blocked_reasons = [review.AWAITING]
        photo = session.get(PhysicalPhoto, supplement.claims["physical_photo_id"])
        photo.detail = {**photo.detail, "owner_attestation": {}}
        leader = session.scalar(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version,
            ListingAsset.position == 1))
        leader_id = leader.id
        leader.approved = False
        leader.blocked_reasons = ["owner_veto"]
        before = {row.id: row.position for row in session.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version))}
    result = review.review_frame(db, old_leader, reissue=False)
    assert result.get("not_qualifying") and result.get("excluded_frame_parked") is False
    with db.session() as session:
        leader = session.get(ListingAsset, leader_id)
        assert not leader.approved and "owner_veto" in leader.blocked_reasons
        after = {row.id: row.position for row in session.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version))}
    assert after == before
