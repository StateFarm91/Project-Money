"""The real owner action handler must not report a closed request as parked."""
import pytest
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from unittest.mock import patch
from sqlalchemy import select, text

from brambleloop.app.command_center import approvals
from brambleloop.core.models import Listing, OwnerAction
from brambleloop.ops import owner_queue
from brambleloop.publish import listing_package
from test_codex_a9_source_binding import fixture, package


def _request(db):
    source = package(db)
    assert listing_package.record(db, source)["review_requested"]
    with db.session() as session:
        return source, session.scalar(select(OwnerAction).where(OwnerAction.done.is_(False))).id


def test_actual_defer_handler_refuses_a_superseded_listing_question():
    db = fixture()
    source, action_id = _request(db)
    with db.session() as session:
        session.scalar(select(Listing).where(Listing.product_slug == source["slug"])).title = "Changed copy"
    with pytest.raises(approvals.ActionRefused):
        approvals.execute(db, "owner_action.defer", {"owner_action_id": action_id, "note": "later"},
                          actor="owner:cc:test")
    with db.session() as session:
        action = session.get(OwnerAction, action_id)
        assert action.done and action.state == owner_queue.SUPERSEDED


def test_actual_defer_handler_is_idempotent_for_a_parked_question():
    db = fixture()
    _, action_id = _request(db)
    for index, note in enumerate(("later", "different request")):
        out = approvals.execute(db, "owner_action.defer", {"owner_action_id": action_id, "note": note},
                                actor="owner:cc:test")
        assert out["result"]["state"] == owner_queue.PARKED
        assert out["result"]["note"] == "later" and out["result"]["changed"] is (index == 0)
    with db.session() as session:
        action = session.get(OwnerAction, action_id)
        assert not action.done and action.state == owner_queue.PARKED


def test_inconsistent_closed_state_is_not_revived_by_deferral():
    db = fixture()
    _, action_id = _request(db)
    # Simulate a legacy/inconsistent row without invoking the lifecycle helper.
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE owner_actions SET state=:state, done=:done WHERE id=:id"),
                           {"state": owner_queue.SUPERSEDED, "done": False, "id": action_id})
    with pytest.raises(approvals.ActionRefused):
        approvals.execute(db, "owner_action.defer", {"owner_action_id": action_id},
                          actor="owner:cc:test")
    with db.session() as session:
        action = session.get(OwnerAction, action_id)
        assert not action.done and action.state == owner_queue.SUPERSEDED


def test_defer_rechecks_after_source_writer_releases_owner_queue_lock():
    from brambleloop.runtime import release

    db = fixture()
    source, action_id = _request(db)
    locked, attempted, release_writer = Event(), Event(), Event()
    real_lock = release._serialise_owner_queue

    def writer():
        with db.session() as session:
            session.scalar(select(Listing).where(Listing.product_slug == source["slug"])).title = "Changed copy"
            session.flush()
            locked.set()
            assert release_writer.wait(10)

    def observed_lock(session, database):
        attempted.set()
        return real_lock(session, database)

    def defer():
        try:
            return approvals.execute(db, "owner_action.defer",
                                     {"owner_action_id": action_id, "note": "later"},
                                     actor="owner:cc:test")
        except approvals.ActionRefused as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_writer = pool.submit(writer)
        assert locked.wait(10)
        with patch.object(release, "_serialise_owner_queue", side_effect=observed_lock):
            pending_defer = pool.submit(defer)
            try:
                assert attempted.wait(10)
                with pytest.raises(TimeoutError):
                    pending_defer.result(timeout=0.25)
            finally:
                release_writer.set()
            pending_writer.result(timeout=10)
            result = pending_defer.result(timeout=10)
    assert isinstance(result, approvals.ActionRefused), result
    with db.session() as session:
        row = session.get(OwnerAction, action_id)
        assert row.done and row.state == owner_queue.SUPERSEDED
