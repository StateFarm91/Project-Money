"""A delayed release event cannot assemble a different current release."""
from unittest.mock import patch

from sqlalchemy import select

from brambleloop.core.models import JobStatus, Listing, OwnerAction, PatternVersion, Product
from brambleloop.publish import listing_package
from test_codex_a9_event_scope import _run
from test_codex_a9_source_binding import fixture, package


def test_old_release_event_leaves_current_review_untouched():
    db = fixture()
    current = package(db)
    assert listing_package.record(db, current)["review_requested"]
    with db.session() as session:
        original_id = session.scalar(select(OwnerAction).where(OwnerAction.done.is_(False))).id
    with patch.object(listing_package, "assemble", return_value=current), \
            patch.object(listing_package, "record", wraps=listing_package.record) as record:
        status, out, error = _run(db, {"slug": current["slug"], "version": current["version"],
                                       "release": "b" * 64})
    assert status == JobStatus.DONE and out.get("refused") == "event_release_mismatch", (out, error)
    assert not out.get("work_done")
    record.assert_not_called()
    with db.session() as session:
        active = list(session.scalars(select(OwnerAction).where(OwnerAction.done.is_(False))))
        assert len(active) == 1 and active[0].id == original_id
    assert listing_package.latest(db, current["slug"], current["version"])["state"] == listing_package.READY


def test_matching_release_event_reaches_the_normal_recorder():
    db = fixture()
    current = package(db)
    with patch.object(listing_package, "assemble", return_value=current), \
            patch.object(listing_package, "record", wraps=listing_package.record) as record:
        status, out, error = _run(db, {"slug": current["slug"], "version": current["version"],
                                       "release": current["release_hash"]})
    assert status == JobStatus.DONE and out.get("ready") == 1, (out, error)
    assert "refused" not in out
    assert record.call_count == 1
    with db.session() as session:
        assert len(list(session.scalars(select(OwnerAction).where(OwnerAction.done.is_(False))))) == 1


def test_source_change_before_record_is_rechecked_before_old_event_retries():
    db = fixture()
    first = package(db)
    assert listing_package.record(db, first)["review_requested"]
    real_record = listing_package.record
    changed = []

    def assembled(database, slug, version):
        value = package(database)
        with database.session() as session:
            pv = session.scalar(select(PatternVersion).join(Product).where(Product.slug == slug))
            value["release_hash"] = pv.release_hash
        return value

    def racing_record(database, value, **kwargs):
        if not changed:
            changed.append(True)
            with database.session() as session:
                pv = session.scalar(select(PatternVersion).join(Product).where(Product.slug == first["slug"]))
                pv.release_hash = "b" * 64
                session.scalar(select(Listing).where(Listing.product_slug == first["slug"])).release_hash = "b" * 64
        return real_record(database, value, **kwargs)

    with patch.object(listing_package, "assemble", side_effect=assembled), \
            patch.object(listing_package, "record", side_effect=racing_record):
        status, out, error = _run(db, {"slug": first["slug"], "version": first["version"],
                                       "release": "a" * 64})
    assert status == JobStatus.DONE and out.get("refused") == "event_release_mismatch", (out, error)
    with db.session() as session:
        assert not list(session.scalars(select(OwnerAction).where(OwnerAction.done.is_(False))))
    assert listing_package.latest(db, first["slug"], first["version"])["state"] == listing_package.BLOCKED
