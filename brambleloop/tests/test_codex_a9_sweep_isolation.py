"""Scheduled sweep isolates release failures, while the durable job retries."""
import sys  # noqa: E402  (review U6 H2: standalone/run_tests.sh import path)
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(_Path(__file__).resolve().parent))
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import select

from brambleloop.core.models import Job, JobStatus, Listing, OwnerAction, PatternVersion, Product, utcnow
from brambleloop.publish import listing_package as lp
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker
from test_codex_a9_source_binding import fixture


def test_scheduled_sweep_progresses_other_release_and_retries_without_duplicates():
    db = fixture()
    with db.session() as session:
        product = Product(slug="a-broken-release", title="Fixture")
        session.add(product)
        session.flush()
        session.add(PatternVersion(product_id=product.id, version="1.0.0", cir_json={},
                                   certified=True, release_hash="b" * 64,
                                   certificate={"granted": True}))
        session.add(Listing(product_slug=product.slug, version="1.0.0", title="Adult Basket",
                            description="Fixture copy", tags=["basket"], release_hash="b" * 64))

    def synthetic_ready(database, slug, version):
        with database.session() as session:
            listing = session.scalar(select(Listing).where(Listing.product_slug == slug))
            copy = {"title": listing.title, "description": listing.description, "tags": listing.tags}
            release_hash = listing.release_hash
        digest = lp.listing_copy_digest(copy)
        return {"slug": slug, "version": version, "fingerprint": digest, "state": lp.READY,
                "release_hash": release_hash, "identity": {}, "copy": copy,
                "listing_snapshot_sha256": digest,
                "source_snapshot_sha256": lp._release(database, slug, version)["source_snapshot_sha256"],
                "blockers": []}

    real_latest = lp.latest
    def failing_latest(database, slug, version):
        if slug == "a-broken-release":
            raise OSError("sensitive transient failure")
        return real_latest(database, slug, version)

    job = JobQueue(db).enqueue("listing", "listing.package", {"cadence": "listing_package"}, priority=0)
    worker = Worker(db, "sweep-isolation", job_types=["listing.package"])
    with patch.object(lp, "assemble", side_effect=synthetic_ready):
        with patch.object(lp, "latest", side_effect=failing_latest):
            worker.run_once()
        with db.session() as session:
            saved = session.get(Job, job.id)
            assert saved.status == JobStatus.FAILED
            assert "sensitive transient failure" not in (saved.last_error or "")
            actions = list(session.scalars(select(OwnerAction).where(OwnerAction.done.is_(False))))
            assert len(actions) == 1 and "test-bound-release" in actions[0].requirement_key
            saved.run_after = utcnow() - timedelta(seconds=1)
        worker.run_once()
    with db.session() as session:
        saved = session.get(Job, job.id)
        assert saved.status == JobStatus.DONE, saved.last_error
        actions = list(session.scalars(select(OwnerAction).where(OwnerAction.done.is_(False))))
        assert len(actions) == 2
        assert sum("test-bound-release" in a.requirement_key for a in actions) == 1
        assert sum("a-broken-release" in a.requirement_key for a in actions) == 1


def test_failed_stale_reconciliation_does_not_skip_other_stale_review():
    from brambleloop.core.models import OperatingReading
    db = fixture()
    with db.session() as session:
        session.add_all([OperatingReading(kind=lp.KIND, period_key="a-stale@1.0", payload={}),
                         OperatingReading(kind=lp.KIND, period_key="z-stale@1.0", payload={})])
    seen = []
    def reconcile(database, slug, version):
        seen.append(slug)
        if slug == "a-stale":
            raise RuntimeError("secret")
        return {"key": f"{slug}@{version}", "changed": True}
    with patch.object(lp, "certified_releases", return_value=[]), \
            patch.object(lp, "_reconcile_ineligible", side_effect=reconcile):
        out = lp.sweep(db)
    assert seen == ["a-stale", "z-stale"]
    assert out["changed"] == 1
    assert out["results"][0]["retry"] is True
    assert "secret" not in str(out)


def test_sweep_inventory_failure_is_not_treated_as_an_empty_inventory():
    import _minipytest as pytest  # Review U6 H2: pytest is not a dependency
    db = fixture()
    with patch.object(lp, "certified_releases", side_effect=RuntimeError("inventory unavailable")), \
            patch.object(lp, "_package_one") as one:
        with pytest.raises(RuntimeError, match="inventory unavailable"):
            lp.sweep(db)
    one.assert_not_called()


def test_lost_lease_stops_worker_before_other_releases():
    from brambleloop.queue.effects import LeaseLost
    db = fixture()
    seen = []
    def no_lease(database, slug, version):
        seen.append(slug)
        raise LeaseLost("lease lost")
    job = JobQueue(db).enqueue("listing", "listing.package", {"cadence": "listing_package"}, priority=0)
    with patch.object(lp, "certified_releases", return_value=[("a", "1"), ("b", "1")]), \
            patch.object(lp, "latest", side_effect=no_lease):
        Worker(db, "sweep-lost-lease", job_types=["listing.package"]).run_once()
    assert seen == ["a"]
    with db.session() as session:
        assert session.get(Job, job.id).status != JobStatus.DONE
        assert not list(session.scalars(select(OwnerAction)))


def test_reader_does_not_swallow_lost_lease():
    import _minipytest as pytest  # Review U6 H2: pytest is not a dependency
    from brambleloop.queue.effects import LeaseLost
    def lost():
        raise LeaseLost("lease lost")
    with pytest.raises(LeaseLost):
        lp._try(lost)


def test_m4_one_release_failing_every_attempt_does_not_dead_letter_the_sweep():
    """Review of 56f92eb9 M4: one release whose assembly raises ValueError on every attempt
    sent the six-hourly sweep to the dead letter as "listing package changed repeatedly"
    (false: it was a ValueError), named the failing release nowhere durable, and never wrote
    the sweep's audit row. Now every attempt writes the sweep row with each release's outcome,
    each failing release is audited with its real error class, retries say what failed, and
    the final attempt completes (degraded) with the other release recorded."""
    from brambleloop.core.models import AuditLog

    db = fixture()
    with db.session() as session:
        product = Product(slug="a-broken-release", title="Fixture")
        session.add(product)
        session.flush()
        session.add(PatternVersion(product_id=product.id, version="1.0.0", cir_json={},
                                   certified=True, release_hash="b" * 64,
                                   certificate={"granted": True}))
        session.add(Listing(product_slug=product.slug, version="1.0.0", title="Adult Basket",
                            description="Fixture copy", tags=["basket"], release_hash="b" * 64))
    def broken_assemble(database, slug, version):
        if slug == "a-broken-release":
            raise ValueError("sensitive detail of a bad release")
        with database.session() as session:      # the healthy release: a READY package
            listing = session.scalar(select(Listing).where(Listing.product_slug == slug))
            copy = {"title": listing.title, "description": listing.description,
                    "tags": listing.tags}
            release_hash = listing.release_hash
        digest = lp.listing_copy_digest(copy)
        return {"slug": slug, "version": version, "fingerprint": digest, "state": lp.READY,
                "release_hash": release_hash, "identity": {}, "copy": copy,
                "listing_snapshot_sha256": digest,
                "source_snapshot_sha256": lp._release(database, slug, version)[
                    "source_snapshot_sha256"],
                "blockers": []}

    job = JobQueue(db).enqueue("listing", "listing.package", {"cadence": "listing_package"},
                               priority=0)
    worker = Worker(db, "sweep-m4", job_types=["listing.package"])
    errors = []
    with patch.object(lp, "assemble", side_effect=broken_assemble):
        for _ in range(5):
            worker.run_once()
            with db.session() as session:
                saved = session.get(Job, job.id)
                if saved.status in (JobStatus.DONE, JobStatus.DEAD):
                    break
                errors.append(saved.last_error or "")
                saved.run_after = utcnow() - timedelta(seconds=1)
    with db.session() as session:
        saved = session.get(Job, job.id)
        assert saved.status == JobStatus.DONE, (saved.status, saved.last_error)
        assert saved.outputs.get("degraded") is True, saved.outputs
        assert saved.outputs["failed_releases"] == [
            {"key": "a-broken-release@1.0.0", "error_class": "ValueError"}], saved.outputs
        sweeps = [r.detail for r in session.scalars(select(AuditLog).where(
            AuditLog.action == "listing.package"))]
        failures = [(r.artifact, r.detail) for r in session.scalars(select(AuditLog).where(
            AuditLog.action == "listing.package_release_failed"))]
        actions = list(session.scalars(select(OwnerAction).where(OwnerAction.done.is_(False))))
    assert errors and all("a-broken-release@1.0.0 (ValueError)" in e for e in errors), errors
    assert not any("changed repeatedly" in e for e in errors), errors
    assert not any("sensitive detail" in e for e in errors), errors
    assert len(sweeps) == len(errors) + 1, (len(sweeps), len(errors))
    for d in sweeps:
        assert d["trigger"] == "sweep"
        assert d["failed"] == [{"key": "a-broken-release@1.0.0", "error_class": "ValueError"}]
        assert any(r["key"] != "a-broken-release@1.0.0" and not r.get("error_class")
                   for r in d["results"]), d["results"]
    assert len(failures) == len(sweeps) and all(
        a == "a-broken-release@1.0.0" and d["error_class"] == "ValueError"
        for a, d in failures), failures
    assert failures[-1][1]["final_attempt"] is True
    assert "sensitive detail" not in str(sweeps) + str(failures)
    # the healthy release was recorded, exactly once
    assert len(actions) == 1 and "test-bound-release" in actions[0].requirement_key, actions

if __name__ == "__main__":
    # Review U6 H2: run under the suite harness (one `OK name` line per test), without pytest.
    import _minipytest

    _minipytest.run_module(globals())
