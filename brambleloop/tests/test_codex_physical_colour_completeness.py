"""Incomplete yarn measurements cannot establish or calibrate a full sample."""
import pytest
import test_physfix as h
from brambleloop.core.models import JobStatus
from brambleloop.quality import physical


@pytest.mark.parametrize("case", ["missing", "zero"])
def test_unmeasured_estimated_colour_cannot_produce_passing_full_make(case):
    db = h._db()
    cir = h._basket()
    h._certify(db, cir)
    payload = h._inputs(cir, scope="full_make", holds_shape=True)
    assert len(payload["grams_by_color"]) >= 2
    omitted = sorted(payload["grams_by_color"])[-1]
    if case == "missing":
        del payload["grams_by_color"][omitted]
    else:
        payload["grams_by_color"][omitted] = 0
    job = h._run(db, "physical.record", payload)
    rows = h._rows(db)
    assert job.status == JobStatus.DONE and len(rows) == 1, (job.status, job.last_error)
    assert rows[0].passed is False, rows[0].measured
    assert "SAMPLE_COLOUR_UNMEASURED" in str(rows[0].measured)
    assert physical.calibration_from_db(db, cir) == 1.0


def test_complete_colour_measurements_can_pass():
    db = h._db()
    cir = h._basket()
    h._certify(db, cir)
    job = h._run(db, "physical.record", h._inputs(cir, scope="full_make", holds_shape=True))
    rows = h._rows(db)
    assert job.status == JobStatus.DONE and len(rows) == 1 and rows[0].passed, job.last_error
