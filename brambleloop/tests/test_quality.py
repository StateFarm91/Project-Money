"""Confidence tracking and regression capture (section 3, acceptance Gate B).

Both of these exist to stop a specific kind of self-deception.

Separate confidence dimensions stop a listing implying the yarn estimate is as solid as the
stitch counts. A single averaged score would do exactly that, which is why there isn't one.

Regression capture stops a fixed bug from coming back. A suite made of *fixed* patterns proves
only that the fixed patterns are still fixed; these fixtures hold the defective ones.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fixtures import (  # noqa: E402
    broken_repeat, broken_stitch_count, broken_unknown_color, good_mosaic_panel,
)

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.reverse import compare  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gates import confidence as conf  # noqa: E402
from brambleloop.gates import regression as reg  # noqa: E402
from brambleloop.gates.certificate import certify  # noqa: E402
from brambleloop.gates.incidents import DefectReport, IncidentTracker  # noqa: E402
from brambleloop.products import nordic_forest as nf  # noqa: E402


def _profile(cir=None):
    cir = cir or nf.build("throw")
    result = compile_cir(cir)
    # The twin refuses to model a pattern that failed compilation, which is correct and means
    # a broken pattern's profile is assessed without one.
    twin = build_twin(cir, result) if result.ok else None
    reverse = compare(cir, write_pattern(cir, result), "US") if result.ok else [1]
    return conf.assess(cir, result, twin, reverse_findings=reverse)


# ---- confidence ------------------------------------------------------------


def test_every_dimension_section_three_names_is_tracked():
    p = _profile()
    for dim in conf.Dimension:
        assert dim in p.scores, dim


def test_there_is_deliberately_no_single_overall_score():
    """An average is more confident than the guess and less than the proof."""
    out = _profile().to_dict()
    assert "overall" not in out and "score" not in out
    assert set(out["scores"]) == {d.value for d in conf.Dimension}


def test_arithmetic_is_near_total_and_physical_is_zero():
    p = _profile()
    assert p.get(conf.Dimension.ARITHMETIC) >= 0.9
    assert p.get(conf.Dimension.INSTRUCTION) == 1.0
    assert p.get(conf.Dimension.PHYSICAL) == 0.0
    assert "nobody has crocheted this" in p.notes[conf.Dimension.PHYSICAL]


def test_computation_can_never_raise_physical_confidence():
    p = _profile()
    assert conf.UNCALIBRATED_CEILING[conf.Dimension.PHYSICAL] == 0.0
    assert p.weakest()[0] is conf.Dimension.PHYSICAL


def test_yardage_confidence_is_capped_while_uncalibrated():
    p = _profile()
    assert p.get(conf.Dimension.YARDAGE) <= conf.UNCALIBRATED_CEILING[conf.Dimension.YARDAGE]
    assert not p.claimable(conf.Dimension.YARDAGE)
    assert "uncalibrated" in p.notes[conf.Dimension.YARDAGE]


def test_a_broken_pattern_has_no_arithmetic_confidence():
    p = _profile(broken_stitch_count())
    assert p.get(conf.Dimension.ARITHMETIC) == 0.0


def test_claims_are_refused_when_their_evidence_is_missing():
    p = _profile()
    problems = conf.check_claims(p, ["stitch_counts", "finished_size", "yarn_required",
                                     "drape", "fit"])
    assert not any("stitch_counts" in x for x in problems), problems
    assert any("yarn_required" in x for x in problems), problems
    assert any("drape" in x for x in problems), problems
    assert any("fit" in x for x in problems), problems


def test_an_unmapped_claim_is_refused_rather_than_waved_through():
    problems = conf.check_claims(_profile(), ["makes_you_happy"])
    assert any("UNKNOWN_CLAIM" in x for x in problems), problems


def test_the_certificate_carries_the_confidence_profile():
    cert = certify(nf.build("throw"))
    assert cert.granted
    assert "confidence" in cert.stages_run
    assert cert.confidence["scores"]["physical"] == 0.0
    assert cert.confidence["weakest"] == "physical"


def test_the_release_chain_runs_the_originality_gate():
    """Section 17 puts it before the product acquires assets and becomes costly to withdraw."""
    cert = certify(nf.build("baby"))
    assert "originality" in cert.stages_run
    order = cert.stages_run
    assert order.index("originality") < order.index("physical_test")


# ---- regression capture ----------------------------------------------------


def test_a_defect_becomes_a_permanent_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        f = reg.capture(broken_stitch_count(), source="incident-1", directory=d)
        assert f.expected_codes, "a fixture that expects nothing asserts nothing"
        assert list(d.glob("*.json")), "nothing was written to disk"
        run = reg.run(d)
        assert run.checked == 1 and run.ok, run.to_dict()


def test_the_fixture_stores_the_failure_not_the_fix():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        f = reg.capture(broken_repeat(), source="incident-2", directory=d)
        loaded = reg.load_all(d)[0]
        from brambleloop.cir.model import CIR

        assert not compile_cir(CIR.from_dict(loaded.cir)).ok, \
            "the stored pattern compiles clean, so it proves nothing"
        assert set(f.expected_codes) <= {x.code for x in
                                          compile_cir(CIR.from_dict(loaded.cir)).errors}


def test_a_clean_pattern_cannot_become_a_regression_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            reg.capture(good_mosaic_panel(), source="x", directory=Path(tmp))
        except reg.NotAReproducibleDefect as e:
            assert "nothing for a regression test to catch" in str(e)
        else:
            raise AssertionError("a clean pattern was captured as a regression fixture")


def test_loosening_a_check_is_caught_by_the_suite():
    """The whole point: a future change that stops catching a bug fails here."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        reg.capture(broken_unknown_color(), source="incident-3", directory=d)

        # Simulate a check being removed: the fixture now expects a code nothing produces.
        path = next(d.glob("*.json"))
        import json

        data = json.loads(path.read_text())
        data["expected_codes"] = ["A_CHECK_SOMEONE_DELETED"]
        path.write_text(json.dumps(data))

        run = reg.run(d)
        assert not run.ok
        assert "no longer produces" in run.failures[0]["problem"]


def test_every_committed_fixture_still_fails_the_way_it_should():
    """The repository's own regression corpus, re-run."""
    run = reg.run()
    assert run.ok, run.failures


def test_an_incident_whose_pattern_compiles_clean_is_recorded_as_not_reproducible():
    """Most customer reports are not compiler-visible defects, and the suite must not fill
    with fixtures that assert nothing."""
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    tracker = IncidentTracker(db)
    incident = None
    for i in range(3):
        incident = tracker.report(DefectReport("test-mosaic", "1.0.0", "panel", 2,
                                               f"c{i}", "row 2 looks wrong"))
    with tempfile.TemporaryDirectory() as tmp:
        out = reg.capture_from_incident(db, incident.id, good_mosaic_panel(),
                                        directory=Path(tmp))
        assert out is None
        assert not list(Path(tmp).glob("*.json"))

    from brambleloop.core.models import Incident

    with db.session() as s:
        row = s.get(Incident, incident.id)
        assert row.detail["regression_fixture"] is None
        assert "missing check is the bug" in row.detail["not_reproducible"]


def test_a_reproducible_incident_captures_a_fixture_once():
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    tracker = IncidentTracker(db)
    incident = None
    for i in range(3):
        incident = tracker.report(DefectReport("test-sphere", "1.0.0", "body", 3,
                                               f"c{i}", "row 3 count is wrong"))
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        first = reg.capture_from_incident(db, incident.id, broken_stitch_count(), directory=d)
        second = reg.capture_from_incident(db, incident.id, broken_stitch_count(), directory=d)
        assert first is not None
        assert second is None, "the same incident captured a second fixture"
        assert len(list(d.glob("*.json"))) == 1


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
