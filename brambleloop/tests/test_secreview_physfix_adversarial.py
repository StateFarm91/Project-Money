"""Independent SECREVIEW of PHYSFIX adabd597: adversarial probes. Each test asserts the
SAFE behaviour; a failure is a finding.

Adopted verbatim as a regression suite by W-PHYSFIX, with one kind of change: the swatch
payloads now answer "followed exactly?" (`instructions_followed`), which the intake requires
since F2/F4. Without it they would be refused at intake, and two of the probes would pass
trivially instead of testing what a recorded swatch can prove."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_physfix import (  # noqa: E402
    _db, _run, _certify, _inputs, _rows, _coasters, _basket, _basket_medium, BAND_GRAMS,
    BAND_METRES, physical, rm, compile_cir, build_twin, select, Incident, OwnerAction)


def test_relabelled_identical_content_does_not_lift_size_halt():
    """Version bump only, same design: the halt must survive."""
    from brambleloop.gates.incidents import IncidentTracker
    db = _db()
    cir = _basket_medium()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                              measured_width_cm=40.0))
    assert (job.outputs or {})["publication_halted"], job.outputs
    relabel = _basket_medium()
    relabel.version = "1.2.1"          # nothing else changed
    out = _certify(db, relabel)
    assert out.get("halted_by_incident") is True, ("relabel certified", out.get("granted"))
    assert IncidentTracker(db).publication_halted(cir.slug), "relabel resolved the halt"


def test_size_halt_does_not_halt_another_product():
    from brambleloop.gates.incidents import IncidentTracker
    db = _db()
    med = _basket_medium()
    _certify(db, med)
    _run(db, "physical.record", _inputs(med, scope="full_make", holds_shape=True,
                                        measured_width_cm=40.0))
    small = _basket()
    out = _certify(db, small)
    assert not out.get("halted_by_incident"), out
    assert not IncidentTracker(db).publication_halted(small.slug)


def test_instructions_followed_no_as_text_is_not_a_pass():
    db = _db()
    cir = _basket()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                              instructions_followed="no"))
    rows = _rows(db)
    assert not rows or rows[0].passed is False, (job.outputs or {}).get("findings")


def test_blank_followed_answer_on_sheet_is_not_read_as_yes():
    from brambleloop.quality import tester_kit
    _, chash = tester_kit.content_hash("basket_small")
    p = tester_kit.intake_payload({"tester_ref": "t", "made_basket": "1", "followed": ""},
                                  content_hash=chash, key="basket_small")
    assert p.get("instructions_followed") is not True, p


def test_a_swatch_alone_does_not_prove_a_size():
    db = _db()
    cir = _basket()
    _certify(db, cir)
    _run(db, "physical.record", {
        "slug": cir.slug, "version": cir.version, "tester_ref": "t", "scope": "swatch",
        "instructions_followed": True, "grams_by_color": {"cream": 6.0}, "ball_band_grams": BAND_GRAMS,
        "ball_band_metres": BAND_METRES, "hook_mm": 5.0,
        "swatch_stitches_per_10cm": cir.gauge.stitches_per_10cm,
        "swatch_rows_per_10cm": cir.gauge.rows_per_10cm})
    cov = physical.size_coverage(db, cir)
    assert cov["proven"] == [], ("swatch reported as a physically proven size", cov["proven"])


def test_a_swatch_alone_does_not_clear_coaster_first_customer():
    """Coaster kit: 'the coaster's one physical claim: it lies flat'."""
    from brambleloop.gates.first_customer import physical_binding
    db = _db()
    cir = _coasters()
    _certify(db, cir)
    job = _run(db, "physical.record", {
        "slug": cir.slug, "version": cir.version, "tester_ref": "t", "scope": "swatch",
        "instructions_followed": True, "grams_by_color": {"cream": 3.0}, "ball_band_grams": BAND_GRAMS,
        "ball_band_metres": BAND_METRES, "hook_mm": 5.0,
        "swatch_stitches_per_10cm": cir.gauge.stitches_per_10cm,
        "swatch_rows_per_10cm": cir.gauge.rows_per_10cm})
    assert _rows(db), job.last_error
    fc = physical_binding(db, cir)["first_customer"]
    assert fc["met"] is False, ("swatch alone meets coaster first-customer floor", fc)


def test_problem_written_in_notes_only_still_passes():
    """Informational: free-text `notes` is WARNING only (by design)."""
    db = _db()
    cir = _basket()
    _certify(db, cir)
    _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                        notes="round 9 is wrong, ripped back twice"))
    rows = _rows(db)
    assert rows and rows[0].passed is False, "problem in notes auto-passed"


def test_component_covering_whole_set_is_still_partial_class():
    db = _db()
    cir = _coasters()
    _certify(db, cir)
    job = _run(db, "physical.record", _inputs(cir, scope="component",
                                              made={"coaster": 4}, lies_flat=True))
    rows = _rows(db)
    assert rows, job.last_error
    assert rows[0].measured["evidence_class"] == rm.PARTIAL_PHYSICAL


def test_partial_make_cannot_be_forced_full_with_measurement_and_no_scope():
    db = _db()
    cir = _coasters()
    _certify(db, cir)
    _run(db, "physical.record", _inputs(cir, 0.5, made={"coaster": 2}, lies_flat=True))
    rows = _rows(db)
    assert not rows or rows[0].measured["evidence_class"] == rm.PARTIAL_PHYSICAL, \
        rows[0].measured["evidence_class"]
    assert physical.calibration_from_db(db, cir) == 1.0


def test_lies_flat_false_with_holds_shape_true_on_coaster_is_partial():
    db = _db()
    cir = _coasters()
    _certify(db, cir)
    _run(db, "physical.record", _inputs(cir, scope="full_make", made={"coaster": 4},
                                        lies_flat="no", holds_shape=True))
    rows = _rows(db)
    assert rows and rows[0].passed is False and rows[0].measured["outcome"] == "PARTIAL"
    assert physical.calibration_from_db(db, cir) == 1.0


def test_partial_outcome_never_calibrates_even_with_off_factor():
    db = _db()
    cir = _basket()
    _certify(db, cir)
    _run(db, "physical.record", _inputs(cir, 1.5, scope="full_make", holds_shape=False))
    assert physical.calibration_from_db(db, cir) == 1.0


def test_chain_relabel_then_swatch_clears_first_customer_with_known_wrong_size():
    """F1+F3 chained: size FAIL on 1.2.0, relabel 1.2.1 (same geometry), swatch on 1.2.1."""
    from brambleloop.gates.first_customer import physical_binding
    from brambleloop.gates.incidents import IncidentTracker
    db = _db()
    cir = _basket_medium()
    _certify(db, cir)
    _run(db, "physical.record", _inputs(cir, scope="full_make", holds_shape=True,
                                        measured_width_cm=40.0))
    relabel = _basket_medium()
    relabel.version = "1.2.1"
    out = _certify(db, relabel)
    job = _run(db, "physical.record", {
        "slug": relabel.slug, "version": relabel.version, "tester_ref": "t2",
        "scope": "swatch", "instructions_followed": True,
        "grams_by_color": {"cream": 6.0}, "ball_band_grams": BAND_GRAMS,
        "ball_band_metres": BAND_METRES, "hook_mm": 5.0,
        "swatch_stitches_per_10cm": relabel.gauge.stitches_per_10cm,
        "swatch_rows_per_10cm": relabel.gauge.rows_per_10cm})
    b = physical_binding(db, relabel)
    halted = IncidentTracker(db).publication_halted(relabel.slug)
    assert halted or not b["first_customer"]["met"], (
        "known-wrong size cleared", out.get("granted"), b["first_customer"], job.last_error)


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn(); print("OK  ", name)
        except Exception as exc:  # noqa: BLE001
            fails += 1; print("FAIL", name, repr(exc)[:400])
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
