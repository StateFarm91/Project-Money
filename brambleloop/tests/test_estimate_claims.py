"""D-OWNER-ESTIMATE-CLAIMS: with no physical sample, size claims pass only as labelled estimates.

The owner's template: "Where physical calibration is absent, the pattern must state estimates
truthfully" and "Every figure is calculated from certified gauge and stitch geometry."
`gates.estimate_claims` reads that off the rendered PDFs, the listing copy and the alt text,
and `gates.first_customer.check_gauge_and_size_claims` uses it when no sample is bound. These
tests pin the three conditions (accuracy, labelling, no physical implication), that child
safety is never waived, that measured evidence still reads as before, and that dropping the
wording check is caught.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin, size_statement  # noqa: E402
from brambleloop.commerce import seo  # noqa: E402
from brambleloop.gates import estimate_claims as ec  # noqa: E402
from brambleloop.gates import first_customer as FC  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.publish.pdf import extracted_text  # noqa: E402

_STATE: dict = {}


def _coasters():
    """The hexagon coaster set (the cheapest Launch-0 render), uncalibrated, both PDFs."""
    if "c" not in _STATE:
        build = next(v.build for s in l0.LAUNCH0_SLUGS for v in l0.candidate(s).variants
                     if l0.cir_for(v.build).slug == "hexagon-coaster-set")
        cir = l0.cir_for(build)
        result = compile_cir(cir)
        twin = build_twin(cir, result)
        assert twin.calibrated is False
        docs, refusals = FC._documents(cir, twin, result)
        assert not refusals, refusals
        texts = {t: extracted_text(d.pdf_bytes) for t, d in docs.items()}
        _STATE["c"] = (cir, result, twin, docs, texts)
    return _STATE["c"]


def _description(cir, twin, *, size_is_estimate: bool = True) -> str:
    g = cir.gauge
    size_label = (size_statement(twin) if twin.shape is not None
                  else f"{twin.width_cm:.0f} x {twin.height_cm:.0f} cm")
    return seo.build_description(
        cir.title, size_label=size_label, yardage_lines=[], tolerance_pct=10,
        difficulty="Confident beginner", colors=[], terminology="US",
        gauge_line=(f"{g.stitches_per_10cm} sts x {g.rows_per_10cm} rows = 10 cm in "
                    f"{g.stitch_type}, {g.hook_mm:g} mm hook"),
        stitches=[], size_is_estimate=size_is_estimate)


def _surfaces(listing_text: str | None = None, pdf_texts: dict | None = None,
              alt_texts: list | None = None) -> dict:
    cir, result, twin, _docs, texts = _coasters()
    return {"pdf_texts": pdf_texts if pdf_texts is not None else texts,
            "listing_text": (listing_text if listing_text is not None
                             else cir.title + "\n" + _description(cir, twin)),
            "alt_texts": alt_texts or [], "result": result}


def _gauge_check(**kw):
    cir, _result, twin, _docs, _texts = _coasters()
    return FC.check_gauge_and_size_claims(cir, twin, None, estimate=_surfaces(**kw))


def _no_sample_physical() -> dict:
    """What `physical_binding` returns with no sample on file."""
    return {"passed": False, "unbound": [], "content_hash": "f" * 64, "bound": [],
            "first_customer": {"met": False, "why": "none held"}, "size_coverage": {}}


# ---- the writers emit the estimate wording ------------------------------------------------


def test_the_pdf_and_listing_writers_state_estimates_when_no_sample_exists():
    cir, _result, twin, _docs, texts = _coasters()
    assert set(texts) == {"US", "UK"}
    for terminology, text in texts.items():
        flat = re.sub(r"\s+", " ", text)
        assert ec.ESTIMATE_NOTE in flat, terminology
        assert "FINISHED SIZE approx." in flat, terminology
        assert "calculated finished size" in flat, terminology
    copy = _description(cir, twin)
    assert ec.ESTIMATE_NOTE in copy
    assert "Finished size: approx." in copy and "calculated finished size" in copy
    # Measured evidence replaces the estimates: a calibrated caller prints neither.
    measured = _description(cir, twin, size_is_estimate=False)
    assert ec.ESTIMATE_NOTE not in measured and "approx." not in measured


# ---- 1-3: the rule, through the first-customer gate ---------------------------------------


def test_estimate_wording_with_no_sample_passes():
    check = _gauge_check()
    assert check.state == FC.PASS, check
    assert check.detail.startswith("ESTIMATE:"), check.detail
    # The runtime path (a database, no sample bound) takes the same estimate path.
    cir, _result, twin, _docs, _texts = _coasters()
    runtime = FC.check_gauge_and_size_claims(cir, twin, _no_sample_physical(),
                                             estimate=_surfaces())
    assert runtime.state == FC.PASS, runtime


def test_the_whole_gate_reads_the_area_off_the_rendered_documents_and_the_listing():
    cir, _result, twin, _docs, _texts = _coasters()
    listing = {"title": cir.title, "description": _description(cir, twin), "tags": [],
               "price_cad": 5.0}
    gate = FC.gate_product(cir, listing=listing)
    check = {c.area: c for c in gate.checks}["gauge_and_size_claims"]
    assert check.state == FC.PASS, check
    # Without a listing there is nothing to read the wording off: unresolved, never a pass.
    gate = FC.gate_product(cir)
    assert {c.area: c for c in gate.checks}["gauge_and_size_claims"].state == FC.UNRESOLVED


def test_a_number_that_differs_from_the_twin_fails():
    cir, _result, twin, _docs, texts = _coasters()
    good = cir.title + "\n" + _description(cir, twin)
    figure = f"{twin.across_points_cm:.1f}"
    assert figure in good
    wrong = good.replace(figure, f"{twin.across_points_cm * 1.4:.1f}")
    check = _gauge_check(listing_text=wrong)
    assert check.state == FC.FAIL and "nearest twin figure" in check.detail, check
    # The same in a PDF.
    bad_pdf = dict(texts, US=texts["US"].replace(figure, f"{twin.across_points_cm * 2:.1f}"))
    check = _gauge_check(pdf_texts=bad_pdf)
    assert check.state == FC.FAIL and "PDF US" in check.detail, check
    # A gauge that is not the certified gauge fails too.
    g = cir.gauge
    stated = f"{g.stitches_per_10cm} sts x {g.rows_per_10cm} rows = 10 cm"
    assert stated in good
    check = _gauge_check(listing_text=good.replace(stated, f"{g.stitches_per_10cm + 3} sts "
                                                          f"x {g.rows_per_10cm} rows = 10 cm"))
    assert check.state == FC.FAIL and "certified gauge" in check.detail, check


def test_wording_that_implies_a_measurement_fails():
    cir, _result, twin, _docs, _texts = _coasters()
    good = cir.title + "\n" + _description(cir, twin)
    size = size_statement(twin)
    for implied in (f"Finished size measures approx. {size}",
                    f"Finished size approx. {size}, as pictured, measured",
                    f"Tested finished size: approx. {size}"):
        check = _gauge_check(listing_text=good + "\n" + implied)
        assert check.state == FC.FAIL and "physical measurement" in check.detail, \
            (implied, check)
    # Outside a size claim, the listing copy and alt text are read whole.
    check = _gauge_check(listing_text=good + "\nEvery pattern is tested by our makers.")
    assert check.state == FC.FAIL, check
    check = _gauge_check(alt_texts=["The finished coaster, as pictured, measured flat"])
    assert check.state == FC.FAIL and "alt text" in check.detail, check
    # The honest negations are not measurement claims.
    assert ec.physical_implications(ec.ESTIMATE_NOTE) == []
    assert ec.physical_implications("computed, not yet measured on a worked sample") == []
    assert ec.physical_implications("computed rather than measured.") == []


def test_a_claim_or_a_surface_without_estimate_wording_fails():
    cir, _result, twin, _docs, texts = _coasters()
    good = cir.title + "\n" + _description(cir, twin)
    unlabelled = good.replace("approx. ", "").replace(", calculated finished size at the "
                                                      "gauge below", "")
    assert unlabelled != good
    check = _gauge_check(listing_text=unlabelled)
    assert check.state == FC.FAIL and "without estimate language" in check.detail, check
    # The note is required on the listing and on both PDFs.
    check = _gauge_check(listing_text=good.replace(ec.ESTIMATE_NOTE, ""))
    assert check.state == FC.FAIL and "estimate note is missing" in check.detail, check
    flat = re.sub(r"\s+", " ", texts["UK"])
    check = _gauge_check(pdf_texts=dict(texts, UK=flat.replace(ec.ESTIMATE_NOTE, "")))
    assert check.state == FC.FAIL and "PDF UK" in check.detail, check
    # A surface with no readable size claim is unread, not clean.
    check = _gauge_check(listing_text=cir.title + "\n" + ec.ESTIMATE_NOTE)
    assert check.state == FC.FAIL and "no finished-size claim" in check.detail, check


# ---- what this never changes --------------------------------------------------------------


def _toy():
    from brambleloop.creative import fallback_constructions as fb

    return fb.amigurumi(SimpleNamespace(slug="plush-fixture", title="Ball Bear Amigurumi",
                                        category="amigurumi", colors={"MC": "#D8C9B0"},
                                        yarn_weight="worsted"))


def test_child_safety_physical_evidence_is_never_waived():
    from brambleloop.gates import child_safety as CS

    toy = _toy()
    result = compile_cir(toy)
    verdict = CS.evaluate(toy, result)
    assert verdict.applies
    phys = [c for c in verdict.checks if c.code == "PHYSICAL_EVIDENCE"]
    assert len(phys) == 1 and phys[0].state == CS.UNKNOWN
    assert ec.child_safety_physical_needed(toy, result)
    twin = build_twin(toy, result)
    # Perfect estimate surfaces cannot clear a toy: the area stays UNRESOLVED, on both paths.
    for physical in (None, _no_sample_physical()):
        check = FC.check_gauge_and_size_claims(toy, twin, physical, estimate=_surfaces())
        assert check.state == FC.UNRESOLVED, check
        assert "child-safety physical test" in check.detail, check
    # And the child-safety gate itself still holds the toy.
    assert CS.evaluate(toy, result).verdict == CS.VERDICT_HELD
    # A flat product with no child-safety physical need is not affected.
    cir, result, _twin, _docs, _texts = _coasters()
    assert ec.child_safety_physical_needed(cir, result) is None


def test_measured_evidence_reads_as_before():
    cir, _result, twin, _docs, _texts = _coasters()
    passed = {"passed": True, "bound": ["t-1"], "content_hash": "a" * 64,
              "first_customer": {"met": True, "why": "full make bound"}, "size_coverage": {}}
    check = FC.check_gauge_and_size_claims(cir, twin, passed, estimate=_surfaces())
    assert check.state == FC.PASS and "physical sample(s)" in check.detail, check
    assert not check.detail.startswith("ESTIMATE")
    # A bound sample of the wrong class is read as before too: unresolved.
    wrong_class = dict(passed, first_customer={"met": False, "why": "a swatch only"})
    check = FC.check_gauge_and_size_claims(cir, twin, wrong_class, estimate=_surfaces())
    assert check.state == FC.UNRESOLVED and check.detail == "a swatch only", check
    # No surfaces handed in: unchanged UNRESOLVED.
    check = FC.check_gauge_and_size_claims(cir, twin, _no_sample_physical())
    assert check.state == FC.UNRESOLVED and "no passed physical sample" in check.detail


# ---- the wording check is load-bearing ----------------------------------------------------


def test_dropping_the_wording_check_is_caught():
    """Mutation: an estimate check that accepts any wording must fail the labelling test."""
    saved = ec._ESTIMATE
    ec._ESTIMATE = re.compile(r"", re.IGNORECASE)        # matches every claim: no check
    try:
        try:
            test_a_claim_or_a_surface_without_estimate_wording_fails()
        except AssertionError:
            caught = True
        else:
            caught = False
    finally:
        ec._ESTIMATE = saved
    assert caught, "the labelling test passed with the wording check removed"
    saved_note = ec._has_note
    ec._has_note = lambda text: True                   # the note check removed
    try:
        try:
            test_a_claim_or_a_surface_without_estimate_wording_fails()
        except AssertionError:
            caught = True
        else:
            caught = False
    finally:
        ec._has_note = saved_note
    assert caught, "the labelling test passed with the note check removed"
    saved_phys = ec._PHYSICAL
    ec._PHYSICAL = re.compile(r"(?!x)x")                # never matches: implication check off
    try:
        try:
            test_wording_that_implies_a_measurement_fails()
        except AssertionError:
            caught = True
        else:
            caught = False
    finally:
        ec._PHYSICAL = saved_phys
    assert caught, "the implication test passed with the measurement check removed"


if __name__ == "__main__":
    fails = 0
    names = sorted(n for n in globals() if n.startswith("test_"))
    for name in names:
        try:
            globals()[name]()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, repr(e)[:600])
    print(f"\n  {len(names) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
