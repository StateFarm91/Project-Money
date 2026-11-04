"""A malformed per-release event must not turn into a global package sweep."""
from unittest.mock import patch

import pytest
from sqlalchemy import select

from brambleloop.core.models import AuditLog, Job, JobStatus, OwnerAction
from brambleloop.publish import listing_package
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime.worker import Worker
from test_codex_a9_source_binding import fixture


def _run(db, inputs):
    job = JobQueue(db).enqueue("listing", "listing.package", inputs, priority=0)
    Worker(db, "scope-test", job_types=["listing.package"]).run_once()
    with db.session() as session:
        saved = session.get(Job, job.id)
        return saved.status, dict(saved.outputs or {}), saved.last_error


@pytest.mark.parametrize("inputs", [
    {"slug": "test-bound-release"}, {"version": "1.0.0"},
    {"slug": "test-bound-release", "version": ""},
    {"slug": " ", "version": "1.0.0"},
    {"slug": "test-bound-release", "version": None},
    {"slug": 42, "version": "1.0.0"},
    {"slugs": "test-bound-release"}, {"release": "abc"},
    {"cadence": "different_job"}, {"cadence": "listing_package", "extra": "unexpected"},
    {"cadence": "listing_package", "retry_for_commit": False},
])
def test_incomplete_event_never_dispatches_a_global_sweep(inputs):
    db = fixture()
    with patch.object(listing_package, "sweep") as sweep, \
            patch.object(listing_package, "for_release") as single:
        status, out, error = _run(db, inputs)
    assert status == JobStatus.DONE, (out, error)
    assert out.get("refused") == "invalid_release_scope" and not out.get("work_done"), out
    sweep.assert_not_called()
    single.assert_not_called()
    with db.session() as session:
        assert not list(session.scalars(select(OwnerAction)))
        assert session.scalar(select(AuditLog).where(
            AuditLog.action == "listing.package_invalid_scope")) is not None


@pytest.mark.parametrize("inputs", [{}, {"cadence": "listing_package"},
                                    {"cadence": "listing_package", "retry_for_commit": "commit"}])
def test_unscoped_scheduled_job_still_dispatches_sweep(inputs):
    db = fixture()
    result = {"releases": 0, "results": [], "ready": 0, "changed": 0}
    with patch.object(listing_package, "sweep", return_value=result) as sweep, \
            patch.object(listing_package, "for_release") as single:
        status, out, error = _run(db, inputs)
    assert status == JobStatus.DONE and out.get("releases") == 0, (out, error)
    sweep.assert_called_once()
    single.assert_not_called()


def test_complete_event_still_dispatches_only_its_release():
    db = fixture()
    result = {"eligible": True, "releases": 0, "results": [], "ready": 0, "changed": 0}
    with patch.object(listing_package, "sweep") as sweep, \
            patch.object(listing_package, "for_release", return_value=result) as single:
        status, out, error = _run(db, {"slug": "test-bound-release", "version": "1.0.0"})
    assert status == JobStatus.DONE and out.get("eligible") is True, (out, error)
    sweep.assert_not_called()
    assert single.call_args.args[1:] == ("test-bound-release", "1.0.0")
