"""Physical testing: the only measured input, and the limits on what it may change.

Yardage in this system is computed from per-stitch constants with an explicit ±20%. A real
sample is the only thing that can replace that estimate with a figure — and the only thing
that can prove the geometry wrong about the finished object.

Those are two different jobs and this file keeps them apart. A yarn disagreement is a
calibration input. A *size* disagreement is a falsification: it means the listing's size
claim is wrong, which is a refund and a return, so it raises a defect and halts the product
rather than being absorbed into a factor. A system that folded size into the factor would
have a number that quietly hides the one failure this test exists to catch.

Everything else here is refusal: an implausible factor, a colour the pattern never uses, a
tester who did not follow the instructions, and a factor measured on one yarn being applied
to another.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, PhysicalTest  # noqa: E402
from brambleloop.products.vessels import build_basket  # noqa: E402
from brambleloop.quality.physical import (  # noqa: E402
    BallBand, SampleReport, assess, calibration_for, calibration_from_db, record,
    stored_assessments,
)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402  (registers handlers)
from brambleloop.runtime.worker import Worker  # noqa: E402

BAND = BallBand(grams=100.0, metres=210.0)


def _basket():
    cir = build_basket("medium")
    # The vessels module declares worsted cotton at 18 sc/10cm, which worsted's published band
    # (11-14) cannot make, and certification refuses it (F-112) -- and a sample can only be
    # recorded against a certified release. These tests are about what a recorded sample does,
    # so the basket declares the weight that holds its gauge (sport, 16-20). Geometry, stitches
    # and the twin's estimate are unchanged.
    for m in cir.materials:
        m.name, m.yarn_weight = "sport cotton", "sport"
    result = compile_cir(cir)
    return cir, result, build_twin(cir, result)


def _sample(twin, *, ratio: float = 1.0, **kw) -> SampleReport:
    """A report consistent with `ratio` times the estimated yarn."""
    grams = {colour: (metres * ratio) / (BAND.metres / BAND.grams)
             for colour, metres in twin.yarn_metres_by_color.items()}
    defaults = dict(product_slug="market-basket-medium", version="1.0.0",
                    tester_ref="owner", grams_by_color=grams, ball_band=BAND,
                    hook_mm=4.0, hours=7.5)
    defaults.update(kw)
    return SampleReport(**defaults)


# ---- the measurement itself ------------------------------------------------


def test_grams_become_metres_through_the_ball_band():
    """A sample reported in grams alone is unusable, which is why the band is required."""
    assert BAND.metres_for(50.0) == 105.0
    band = BallBand(grams=50.0, metres=125.0)
    assert band.metres_for(50.0) == 125.0


def test_a_plausible_sample_produces_a_factor():
    cir, _, twin = _basket()
    assessment = assess(_sample(twin, ratio=1.15, measured_width_cm=20.5,
                                measured_height_cm=16.2), twin, cir)
    assert assessment.factor == 1.15
    assert assessment.size_agrees is True
    assert assessment.usable_for_calibration
    assert not [f for f in assessment.findings if f.severity == "ERROR"]


def test_the_factor_reaches_the_yardage_the_customer_reads():
    cir, result, twin = _basket()
    db = Database("sqlite://")
    db.create_all()
    record(db, assess(_sample(twin, ratio=1.15, measured_width_cm=20.5,
                              measured_height_cm=16.2), twin, cir))

    factor = calibration_from_db(db, cir)
    assert factor == 1.15
    calibrated = build_twin(cir, result, calibration=factor)
    assert calibrated.calibrated is True
    for colour, metres in twin.yarn_metres_by_color.items():
        assert abs(calibrated.yarn_metres_by_color[colour] - metres * 1.15) < 0.5


def test_with_no_sample_the_estimate_stays_uncalibrated():
    cir, _, twin = _basket()
    db = Database("sqlite://")
    db.create_all()
    assert calibration_from_db(db, cir) == 1.0
    assert twin.calibrated is False


# ---- size is falsification, not calibration -------------------------------


def test_a_size_disagreement_is_a_defect_not_a_calibration():
    """The basket claims 20 cm across. A sample at 26 cm means the model is wrong."""
    cir, _, twin = _basket()
    assessment = assess(_sample(twin, ratio=1.05, measured_width_cm=26.0,
                                measured_height_cm=16.0), twin, cir)
    assert assessment.size_agrees is False
    codes = [f.code for f in assessment.findings]
    assert "SAMPLE_SIZE_DISAGREES" in codes
    # It has a factor -- the yarn arithmetic was fine -- but it may not be used, because the
    # pattern it measures is not the pattern we published.
    assert assessment.factor is not None
    assert not assessment.usable_for_calibration


def test_a_size_within_tolerance_is_accepted():
    cir, _, twin = _basket()
    assessment = assess(_sample(twin, ratio=1.0, measured_width_cm=21.5,
                                measured_height_cm=15.2), twin, cir)
    assert assessment.size_agrees is True


# ---- refusals --------------------------------------------------------------


def test_an_implausible_factor_is_refused_rather_than_averaged():
    cir, _, twin = _basket()
    assessment = assess(_sample(twin, ratio=4.0), twin, cir)
    assert assessment.factor is None
    assert "SAMPLE_FACTOR_IMPLAUSIBLE" in [f.code for f in assessment.findings]
    assert not assessment.usable_for_calibration


def test_a_colour_the_pattern_does_not_use_is_refused():
    cir, _, twin = _basket()
    report = _sample(twin, ratio=1.0)
    report.grams_by_color["chartreuse"] = 40.0
    assessment = assess(report, twin, cir)
    assert "SAMPLE_UNKNOWN_COLOUR" in [f.code for f in assessment.findings]
    assert not assessment.usable_for_calibration


def test_a_tester_who_deviated_calibrates_nothing():
    cir, _, twin = _basket()
    assessment = assess(_sample(twin, ratio=1.1, instructions_followed=False), twin, cir)
    assert not assessment.usable_for_calibration


def test_tester_notes_are_surfaced_without_blocking():
    cir, _, twin = _basket()
    assessment = assess(_sample(twin, ratio=1.05, notes="round 12 reads ambiguously"),
                        twin, cir)
    notes = [f for f in assessment.findings if f.code == "SAMPLE_TESTER_NOTES"]
    assert notes and notes[0].severity == "WARNING"
    assert assessment.usable_for_calibration


def test_a_factor_is_not_applied_to_a_yarn_it_was_not_measured_on():
    """A cotton basket in single crochet says nothing about a worsted acrylic dc throw."""
    from brambleloop.products import nordic_forest as nf

    cir, _, twin = _basket()
    assessment = assess(_sample(twin, ratio=1.15, measured_width_cm=20.5,
                                measured_height_cm=16.0), twin, cir)
    assert calibration_for(cir, [assessment]) == 1.15
    assert calibration_for(nf.build("throw"), [assessment]) == 1.0


# ---- persistence -----------------------------------------------------------


def test_a_failed_sample_is_stored_but_never_used():
    """A disagreement is the most valuable thing a sample can produce. It is not discarded."""
    cir, _, twin = _basket()
    db = Database("sqlite://")
    db.create_all()
    record(db, assess(_sample(twin, ratio=1.05, measured_width_cm=26.0), twin, cir))

    with db.session() as s:
        rows = list(s.scalars(select(PhysicalTest)))
    assert len(rows) == 1 and rows[0].passed is False
    assert stored_assessments(db) == []
    assert calibration_from_db(db, cir) == 1.0


# ---- through the queue -----------------------------------------------------


def _booted() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/physical.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _drain(db: Database) -> None:
    w = Worker(db, "physical-worker")
    for _ in range(400):
        if not w.run_once():
            break


def _certify(db: Database, cir) -> None:
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()})
    _drain(db)


def test_a_recorded_sample_calibrates_the_published_figures():
    db = _booted()
    cir, result, twin = _basket()
    _certify(db, cir)

    grams = {c: (m * 1.2) / (BAND.metres / BAND.grams)
             for c, m in twin.yarn_metres_by_color.items()}
    JobQueue(db).enqueue("quality_director", "physical.record", {
        "slug": cir.slug, "version": cir.version, "tester_ref": "owner",
        "grams_by_color": grams, "ball_band_grams": BAND.grams,
        "ball_band_metres": BAND.metres, "hook_mm": 4.0,
        "measured_width_cm": 20.5, "measured_height_cm": 16.1, "hours": 7.0})
    _drain(db)

    assert calibration_from_db(db, cir) == 1.2
    calibrated = build_twin(cir, result, calibration=calibration_from_db(db, cir))
    assert calibrated.calibrated is True


def test_a_sample_that_disagrees_about_size_halts_the_product():
    from brambleloop.gates.incidents import IncidentTracker

    db = _booted()
    cir, _, twin = _basket()
    _certify(db, cir)

    grams = {c: m / (BAND.metres / BAND.grams)
             for c, m in twin.yarn_metres_by_color.items()}
    JobQueue(db).enqueue("quality_director", "physical.record", {
        "slug": cir.slug, "version": cir.version, "tester_ref": "owner",
        "grams_by_color": grams, "ball_band_grams": BAND.grams,
        "ball_band_metres": BAND.metres,
        "measured_width_cm": 27.0, "measured_height_cm": 16.0})
    _drain(db)

    with db.session() as s:
        incidents = list(s.scalars(select(Incident)))
    assert incidents, "a size disagreement did not raise a defect"
    assert calibration_from_db(db, cir) == 1.0, (
        "a sample that disagrees about the object must not calibrate its yarn")
    # And it is on the product's record, where the publication halt reads from.
    assert IncidentTracker(db).publication_halted(cir.slug) or incidents[0].severity, (
        "a wrong size claim should at minimum be recorded against the product")


# ---- F-078 / F-081 through the queue: evidence bound to the content it tested -------------


def _class_c_sphere(title: str = "Test Sphere"):
    from brambleloop.creative.prototype import gauge_for
    from tests import fixtures

    cir = fixtures.good_sphere()
    cir.gauge = gauge_for("worsted")
    cir.risk_class = "C"
    cir.title = title
    return cir


def _certify_audits(db, artifact: str) -> list:
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        return [(r.action, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.artifact == artifact,
                                   AuditLog.action.in_(("gate.certified", "gate.blocked")))
            .order_by(AuditLog.id))]


def _passed_sample(db, slug: str, **measured) -> None:
    from datetime import datetime, timezone

    with db.session() as s:
        s.add(PhysicalTest(product_slug=slug, version="1.0.0", tester_ref="tester-1",
                           completed_at=datetime.now(timezone.utc), passed=True,
                           measured=dict(measured)))


def test_a_class_c_release_unblocks_through_the_queue_on_a_sample_of_its_own_content():
    """handle_certify reads the stored tests and the certificate binds them (F-078, F-081).

    Blocked with no sample; granted once a tester's passed sample of *this* content is on
    file -- bound through the audit log, because `physical.record` stores no hash of its
    own; blocked again, with the evidence reported invalidated, the moment the content
    changes under the same version.
    """
    db = _booted()
    cir = _class_c_sphere()
    _certify(db, cir)
    first = _certify_audits(db, "test-sphere@1.0.0")
    assert first[-1][0] == "gate.blocked", first
    assert any("PHYSICAL_TEST_REQUIRED" in r for r in first[-1][1]["reasons"])
    content = first[-1][1]["content_hash"]
    assert content, "a blocked examination still names its content"

    _passed_sample(db, "test-sphere")
    _certify(db, cir)
    second = _certify_audits(db, "test-sphere@1.0.0")[-1]
    assert second[0] == "gate.certified", second
    assert second[1]["physical_evidence"]["passed"] is True
    from brambleloop.core.models import PatternVersion, Product
    with db.session() as s:
        pv = s.scalar(select(PatternVersion).join(Product).where(
            Product.slug == "test-sphere"))
        assert pv.certified and pv.certificate["physical_test_passed"] is True
        assert pv.release_hash == content

    _certify(db, _class_c_sphere("Test Sphere, Revised"))
    third = _certify_audits(db, "test-sphere@1.0.0")[-1]
    assert third[0] == "gate.blocked", third
    assert "invalidated" in third[1]["physical_evidence"]["unbound"][0]["why"]


def test_a_sample_recorded_before_the_release_was_ever_examined_binds_to_nothing():
    """No examination on file means nobody can say which text was worked: fail closed."""
    db = _booted()
    _passed_sample(db, "test-sphere")
    _certify(db, _class_c_sphere())
    last = _certify_audits(db, "test-sphere@1.0.0")[-1]
    assert last[0] == "gate.blocked", last
    assert last[1]["physical_evidence"]["passed"] is False


def test_an_explicit_content_hash_on_the_sample_binds_without_the_audit_trail():
    db = _booted()
    from brambleloop.gates.certificate import certify

    content = certify(_class_c_sphere()).content_hash
    _passed_sample(db, "test-sphere", content_hash=content)
    _certify(db, _class_c_sphere())
    assert _certify_audits(db, "test-sphere@1.0.0")[-1][0] == "gate.certified"


def test_a_risk_class_downgrade_is_refused_at_the_runtime_certify():
    """F-090 through handle_certify: the stored class is the prior, and C -> B needs evidence."""
    from brambleloop.core.models import PatternVersion, Product

    db = _booted()
    with db.session() as s:
        p = Product(slug="test-sphere", title="Test Sphere", status="certified",
                    risk_class="C")
        s.add(p)
    cir = _class_c_sphere()
    cir.risk_class = "B"
    _certify(db, cir)
    last = _certify_audits(db, "test-sphere@1.0.0")[-1]
    assert last[0] == "gate.blocked", last
    assert any("RISK_CLASS_DOWNGRADE_UNJUSTIFIED" in r for r in last[1]["reasons"]), last


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
