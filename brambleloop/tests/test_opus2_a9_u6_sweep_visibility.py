"""Review of a9feb805 (MEDIUM + 2 LOW): a listing-package sweep that fails must be SEEN.

On a9feb805 the sweep's final attempt returned DONE (degraded) even when EVERY release failed,
and nothing read the degraded flag or the `listing.package_release_failed` rows: a probe making
`record` fail for every release (the PostgreSQL period_key truncation class) gave FAILED,
FAILED, then DONE -- nothing recorded, no dead letter, every six hours, silently.

Now: all-fail -> DEAD with the real error class and the failing releases; partial-fail -> DONE
degraded AND reported by `ops.production_evidence` (and the Command Center queue reader);
all-ok -> DONE clean. A DONE degraded job no longer keeps an earlier attempt's last_error, and
max_attempts=0 is handled explicitly.
"""
import sys  # noqa: E402  (standard header: standalone/run_tests.sh import path)
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(_Path(__file__).resolve().parent))
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import select

from brambleloop.core.models import (AuditLog, Job, JobStatus, Listing, PatternVersion, Product,
                                     utcnow)
from brambleloop.ops import production_evidence as pe
from brambleloop.publish import listing_package as lp
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker
from test_codex_a9_source_binding import fixture

BROKEN = "a-broken-release@1.0.0"
HEALTHY = "test-bound-release@1.0.0"


class StringDataRightTruncation(Exception):
    """Stands in for psycopg's class of the same name (the production failure)."""


def _two_releases():
    db = fixture()                       # certifies test-bound-release@1.0.0
    with db.session() as session:
        product = Product(slug="a-broken-release", title="Fixture")
        session.add(product)
        session.flush()
        session.add(PatternVersion(product_id=product.id, version="1.0.0", cir_json={},
                                   certified=True, release_hash="b" * 64,
                                   certificate={"granted": True}))
        session.add(Listing(product_slug=product.slug, version="1.0.0", title="Adult Basket",
                            description="Fixture copy", tags=["basket"], release_hash="b" * 64))
    return db


def _ready(database, slug, version):
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


def _drive(db, *, record_fails, max_attempts=3):
    """Run the sweep job to a terminal state; return (job, last_errors_seen_between_attempts)."""
    real_record = lp.record

    def record(database, package, **kw):
        if package["slug"] in record_fails:
            raise StringDataRightTruncation("value too long for type character varying(64) "
                                            "SENSITIVE-ROW-TEXT")
        return real_record(database, package, **kw)

    job = JobQueue(db).enqueue("listing", "listing.package", {"cadence": "listing_package"},
                               priority=0, max_attempts=max_attempts)
    worker = Worker(db, "sweep-visibility", job_types=["listing.package"])
    seen = []
    with patch.object(lp, "assemble", side_effect=_ready), patch.object(lp, "record", record):
        for _ in range(6):
            worker.run_once()
            with db.session() as session:
                saved = session.get(Job, job.id)
                if saved.status in (JobStatus.DONE, JobStatus.DEAD):
                    break
                seen.append(saved.last_error or "")
                saved.run_after = utcnow() - timedelta(seconds=1)
    with db.session() as session:
        saved = session.get(Job, job.id)
        session.expunge(saved)
    return saved, seen


def test_every_release_failing_dead_letters_with_the_real_class_and_releases():
    db = _two_releases()
    job, seen = _drive(db, record_fails={"a-broken-release", "test-bound-release"})
    assert len(seen) == 2, seen                    # FAILED, FAILED, then ...
    assert job.status == JobStatus.DEAD, (job.status, job.outputs)   # ... DEAD, not DONE
    head = job.last_error.splitlines()[0]
    assert head.startswith("StringDataRightTruncation: listing package sweep: 2 release(s) "
                           "not recorded"), head
    assert BROKEN in head and HEALTHY in head, head
    assert "SENSITIVE-ROW-TEXT" not in job.last_error
    now = utcnow() + timedelta(seconds=1)
    dead = pe.dead_letters(db, now=now)
    assert dead["unexpected_total"] == 1, dead
    assert [(g["job_type"], g["error_class"]) for g in dead["by_type"]] == [
        ("listing.package", "StringDataRightTruncation")], dead
    section = pe.listing_package_releases(db, now=now)
    assert section["unrecorded_releases"] == 2 and section["final_attempt_failures"] == 2, section
    assert section["degraded_sweeps"] == 0, section
    ev = pe.evidence(db, now=now)
    assert ev["server_judgement"]["no_unexpected_dead_letters_in_24h"] is False
    assert ev["server_judgement"]["no_unrecorded_listing_releases_in_24h"] is False


def test_partial_failure_completes_degraded_and_is_surfaced_in_production_evidence():
    db = _two_releases()
    job, seen = _drive(db, record_fails={"a-broken-release"})
    assert job.status == JobStatus.DONE, (job.status, job.last_error)
    assert job.outputs["degraded"] is True and job.outputs["recorded"] == 1, job.outputs
    assert job.outputs["failed_releases"] == [
        {"key": BROKEN, "error_class": "StringDataRightTruncation"}], job.outputs
    # LOW: the DONE job does not keep the previous attempt's "retry the job" error.
    assert seen and all("retry the job" in e for e in seen), seen
    assert "retry the job" not in (job.last_error or ""), job.last_error
    assert job.last_error.startswith(
        "StringDataRightTruncation: listing package sweep: 1 release(s) not recorded: "
        f"{BROKEN} (StringDataRightTruncation); completed degraded"), job.last_error
    now = utcnow() + timedelta(seconds=1)
    section = pe.listing_package_releases(db, now=now)
    assert section["readable"] is True
    assert section["degraded_sweeps"] == 1 and section["degraded_job_ids"] == [job.id], section
    assert section["unrecorded_releases"] == 1, section
    [row] = section["by_release"]
    assert row["release"] == BROKEN and row["error_class"] == "StringDataRightTruncation", row
    assert row["failed_attempts"] == 3 and row["final_attempt_failures"] == 1, row
    assert row["job_ids"] == [job.id], row
    assert "SENSITIVE-ROW-TEXT" not in str(section)
    ev = pe.evidence(db, now=now)
    assert ev["server_judgement"]["no_unrecorded_listing_releases_in_24h"] is False, ev
    # Not a dead letter -- but no longer invisible: the operations surface reads it too.
    assert ev["server_judgement"]["no_unexpected_dead_letters_in_24h"] is True
    from brambleloop.app.command_center import readers

    q = readers.queue(db)
    assert q["status"] == "DEGRADED", q
    assert "1 listing release(s) not recorded" in q["reason"], q
    assert q["unrecorded_listing_releases"]["by_release"][0]["release"] == BROKEN, q


def test_every_release_recorded_completes_clean():
    db = _two_releases()
    job, seen = _drive(db, record_fails=set())
    assert not seen
    assert job.status == JobStatus.DONE and "degraded" not in job.outputs, job.outputs
    assert job.last_error is None
    now = utcnow() + timedelta(seconds=1)
    section = pe.listing_package_releases(db, now=now)
    assert section == {"readable": True, "window_hours": 24, "degraded_sweeps": 0,
                       "degraded_job_ids": [], "unrecorded_releases": 0,
                       "final_attempt_failures": 0, "by_release": []}, section
    assert pe.evidence(db, now=now)["server_judgement"][
        "no_unrecorded_listing_releases_in_24h"] is True
    from brambleloop.app.command_center import readers

    q = readers.queue(db)
    assert q["status"] == "OK", q


def test_max_attempts_zero_is_an_explicit_last_attempt():
    """LOW: max_attempts=0 means the queue dead-letters the first failure, so the first
    attempt is the last: a partial failure completes degraded at once (not an exception the
    queue would dead-letter), and an all-fail dead-letters at once."""
    from brambleloop.runtime.listing_package_ops import handle_listing_package
    from brambleloop.runtime.worker import JobContext

    class _J:
        id = None
        attempts = 1
        max_attempts = 0
        inputs = {"cadence": "listing_package"}

    for fails, expect in (({"a-broken-release"}, "degraded"),
                          ({"a-broken-release", "test-bound-release"}, "raise")):
        db = _two_releases()
        audits = []
        ctx = JobContext.__new__(JobContext)
        ctx.db, ctx.job = db, _J()
        ctx.audit = lambda action, **kw: audits.append((action, kw))
        real_record = lp.record

        def record(database, package, _f=fails, **kw):
            if package["slug"] in _f:
                raise StringDataRightTruncation("x")
            return real_record(database, package, **kw)

        with patch.object(lp, "assemble", side_effect=_ready), \
                patch.object(lp, "record", record):
            try:
                out = handle_listing_package(ctx)
            except Exception as exc:  # noqa: BLE001
                out = exc
        if expect == "degraded":
            assert isinstance(out, dict) and out["degraded"] is True, out
        else:
            assert type(out).__name__ == "StringDataRightTruncation", out
        finals = [kw["detail"]["final_attempt"] for a, kw in audits
                  if a == "listing.package_release_failed"]
        assert finals and all(f is True for f in finals), audits


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
