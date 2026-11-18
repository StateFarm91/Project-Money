"""Review U6 M1/L2/L3: record() re-verifies every bound source under the lock.

The ORM fence (publish/listing_package_fence.py) withdraws review requests when the ORM
flushes a change. A bulk, Core or raw-SQL write bypasses it, so record()'s READY check is the
only defence between an assembled package and an owner review request for content that is
no longer the listing. These tests drive that check with writes the fence cannot see. There
is one case per bound source (copy, non-copy listing field, certificate, CIR, release), plus
one case per individual check, so that removing any one of them is detected.

Before this file, removing all four checks together (mutant RX) survived every A9 suite.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select, text, update

from brambleloop.core.models import Listing, OwnerAction, PatternVersion
from brambleloop.publish import listing_package as lp
from test_codex_a9_source_binding import active, fixture, package

SLUG, VERSION = "test-bound-release", "1.0.0"


def _bulk(db, stmt):
    """A write the ORM fence does not see: no ORM object is flushed."""
    with db.session() as s:
        s.execute(stmt)


def _assert_refused(db, out):
    assert out.get("state") == lp.BLOCKED and out.get("retry") is True, out
    assert out.get("review_requested") is not True, out
    reading = lp.latest(db, SLUG, VERSION)
    assert reading is None or reading["state"] == lp.BLOCKED, reading
    assert active(db) == [], active(db)


def _both_flows(write):
    """First record after the write, and a retried record while a review is already open
    (the request raised before the write must be withdrawn, not left standing)."""
    db = fixture()
    pkg = package(db)
    write(db)
    _assert_refused(db, lp.record(db, pkg))

    db = fixture()
    pkg = package(db)
    assert lp.record(db, pkg)["review_requested"] is True and len(active(db)) == 1
    write(db)
    assert len(active(db)) == 1, "precondition: the fence cannot see this write"
    _assert_refused(db, lp.record(db, pkg, expected_fingerprint=pkg["fingerprint"]))
    assert lp.latest(db, SLUG, VERSION)["state"] == lp.BLOCKED


def _assert_control(db):
    """Control: the same package with no intervening write raises exactly one review."""
    out = lp.record(db, package(db))
    assert out["review_requested"] is True and len(active(db)) == 1, out


def test_control_an_unchanged_source_raises_one_review():
    _assert_control(fixture())


def test_bulk_copy_change_after_assembly_is_refused():
    def write(db):
        _bulk(db, update(Listing).where(Listing.product_slug == SLUG)
              .values(title="Baby Teether Clip"))

    _both_flows(write)


def test_raw_sql_tag_change_after_assembly_is_refused():
    def write(db):
        with db.engine.begin() as conn:
            conn.execute(text("UPDATE listings SET tags = :t WHERE product_slug = :s"),
                         {"t": '["baby"]', "s": SLUG})

    _both_flows(write)


def test_bulk_non_copy_listing_field_change_after_assembly_is_refused():
    def write(db):
        _bulk(db, update(Listing).where(Listing.product_slug == SLUG).values(price_cad=99.0))

    _both_flows(write)


def test_bulk_certificate_change_after_assembly_is_refused():
    def write(db):
        _bulk(db, update(PatternVersion).values(
            certificate={"granted": True, "reissued": "after assembly"}))

    _both_flows(write)


def test_bulk_cir_change_after_assembly_is_refused():
    def write(db):
        _bulk(db, update(PatternVersion).values(cir_json={"changed": "after assembly"}))

    _both_flows(write)


def test_bulk_release_change_after_assembly_is_refused():
    def write(db):
        _bulk(db, update(PatternVersion).values(release_hash="b" * 64))
        _bulk(db, update(Listing).where(Listing.product_slug == SLUG)
              .values(release_hash="b" * 64))

    _both_flows(write)


def test_bulk_decertification_after_assembly_is_refused():
    def write(db):
        _bulk(db, update(PatternVersion).values(certified=False))

    _both_flows(write)


# One case per individual check. In each, every OTHER check agrees, so only the named
# check stands between the package and an owner review.

def test_check_certificate_granted_alone():
    db = fixture()
    _bulk(db, update(PatternVersion).values(certificate={"granted": False}))
    pkg = package(db)          # assembled after the change: source digest agrees
    _assert_refused(db, lp.record(db, pkg))


def test_check_listing_snapshot_digest_alone():
    db = fixture()
    pkg = {**package(db), "listing_snapshot_sha256": "0" * 64}
    _assert_refused(db, lp.record(db, pkg))


def test_check_emitted_copy_against_stored_copy_alone():
    db = fixture()
    pkg = package(db)
    pkg = {**pkg, "copy": {**pkg["copy"], "title": "Baby Teether Clip"}}
    _assert_refused(db, lp.record(db, pkg))


def test_check_source_snapshot_alone():
    db = fixture()
    pkg = {**package(db), "source_snapshot_sha256": "0" * 64}
    _assert_refused(db, lp.record(db, pkg))


def test_check_missing_source_snapshot_alone():
    db = fixture()
    pkg = {**package(db), "source_snapshot_sha256": None}
    _assert_refused(db, lp.record(db, pkg))


# Review U6 L2 (mutant R7): two parked questions for one release are never silently resolved.

def test_two_parked_questions_are_refused_without_a_new_review():
    db = fixture()
    pkg = package(db)
    key = f"{lp.ACTION_PREFIX}{SLUG}@{VERSION}"
    # A real recorded owner question, which the owner deferred: on its own, re-recording the
    # identical package would keep it parked (same_parked) and READY.
    assert lp.record(db, pkg)["review_requested"] is True
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.done == False,  # noqa: E712
                                                 OwnerAction.requirement_key.like(f"{key}:%")))
        row.state = "parked"
        real = row.requirement_key
        # A second parked question for the same release: the queue no longer says which
        # deferral is the owner's answer.
        s.add(OwnerAction(requirement_key=f"{key}:{'2' * 16}", action="old review",
                          reason="fixture", state="parked"))
    out = lp.record(db, pkg, expected_fingerprint=pkg["fingerprint"])
    assert out.get("state") == lp.BLOCKED and out.get("retry") is False, out
    assert out.get("review_requested") is not True, out
    assert lp.latest(db, SLUG, VERSION)["state"] == lp.BLOCKED
    assert "multiple parked" in lp.latest(db, SLUG, VERSION)["invalid_reason"]
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(f"{key}:%"))))
        # Both deferrals stand untouched for reconciliation, and no third question is raised.
        assert sorted((r.requirement_key, r.state, r.done) for r in rows) == sorted(
            [(real, "parked", False), (f"{key}:{'2' * 16}", "parked", False)]), rows


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
