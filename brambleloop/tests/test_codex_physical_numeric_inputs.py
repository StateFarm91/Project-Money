"""Invalid measurement types must never bind sample evidence."""
import pytest
import test_physfix as h
from brambleloop.core.models import JobStatus
from brambleloop.quality import physical


@pytest.mark.parametrize("field,value", [
    ("ball_band_grams", True), ("ball_band_metres", True),
    ("grams_by_color", {"cream": True}), ("measured_width_cm", True),
    ("measured_height_cm", False), ("hook_mm", True),
])
def test_boolean_measurements_are_refused_before_sample_storage(field, value):
    db = h._db()
    cir = h._basket()
    h._certify(db, cir)
    payload = h._inputs(cir, scope="full_make", holds_shape=True)
    payload[field] = value
    # Matching band ratio proves True-as-1.0 can otherwise look like valid data.
    if field == "ball_band_grams":
        payload["ball_band_metres"] = 77.0 / 50.0
    job = h._run(db, "physical.record", payload)
    assert job.status in (JobStatus.FAILED, JobStatus.DEAD), (job.status, job.outputs)
    assert h._rows(db) == [], "boolean measurement must not become evidence"


def test_numeric_control_and_direct_assessment_reject_boolean():
    db = h._db()
    cir = h._basket()
    h._certify(db, cir)
    job = h._run(db, "physical.record", h._inputs(cir, scope="full_make", holds_shape=True))
    assert job.status == JobStatus.DONE and len(h._rows(db)) == 1, job.last_error
    report = physical.SampleReport(product_slug="fixture", version="1", tester_ref="fixture",
                                   grams_by_color={"cream": True},
                                   ball_band=physical.BallBand(50, 77))
    assert "grams_by_color.cream" in physical._non_finite(report)
