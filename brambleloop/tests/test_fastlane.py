"""A shorter queue, and the slide into a shorter list of gates that it must not become.

v1.4.3 requirement 291. A high-confidence, time-sensitive, technically simple trend goes down
a fast lane with bounded scope -- and fast does not bypass pattern truth, IP and policy,
visual truth or what the customer was told.

Every fast lane in every company begins as a queue-jump and ends as an exemption. The slide
is never decided; it happens one defensible deadline at a time. So these tests check that the
exemption is impossible to express rather than discouraged, and that what the lane actually
buys is scope: a fast product is small by construction, which is the only honest way to go
fast.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.gates import certificate  # noqa: E402
from brambleloop.seasonal import fastlane as F  # noqa: E402


def _candidate(**over) -> F.Candidate:
    base = dict(slug="pine-coaster", half_life="flash", make_lane="QUICK", risk_class="A",
                components=1, colours=2, new_techniques=0, evidence_confidence=0.85)
    base.update(over)
    return F.Candidate(**base)


# ---- the lane does not subtract gates -------------------------------------


def test_the_fast_lane_runs_the_release_chains_own_stage_list():
    """Imported rather than retyped: a second copy is how the guarantee quietly stops being
    true -- somebody edits one, both still look right, and the lane has an exemption nobody
    decided to give it."""
    assert set(F.NON_NEGOTIABLE_GATES) | set(F.CONDITIONAL_GATES) == set(
        certificate.CANONICAL_STAGES)


def test_the_canonical_stage_list_matches_what_the_chain_actually_runs():
    """The constant is only useful if it cannot drift from the code beside it."""
    source = Path(certificate.__file__).read_text(encoding="utf-8")
    appended = re.findall(r'stages\.append\("([a-z_]+)"\)', source)

    assert set(appended) == set(certificate.CANONICAL_STAGES), (
        sorted(set(appended) ^ set(certificate.CANONICAL_STAGES)))


def test_a_release_that_skipped_a_gate_is_refused_by_name():
    try:
        F.check_release("pine-coaster", gates_passed=("compile", "twin"))
    except F.FastLaneRefused as e:
        assert "reverse" in str(e)
        assert "shortens the queue, never the gate list" in str(e)
    else:
        raise AssertionError("a fast-lane product released without its gates")


def test_conditional_stages_stay_conditional_on_the_product_never_on_the_lane():
    """A listing means policy and asset truth are owed, whichever queue the product came
    down."""
    passed = F.NON_NEGOTIABLE_GATES
    assert F.check_release("a", gates_passed=passed)["ok"] is True

    try:
        F.check_release("b", gates_passed=passed,
                        applicable_conditional=("policy", "asset_truth"))
    except F.FastLaneRefused as e:
        assert "policy" in str(e) and "asset_truth" in str(e)
    else:
        raise AssertionError("a listed product skipped policy because it was in a hurry")

    full = tuple(passed) + ("policy", "asset_truth")
    assert F.check_release("c", gates_passed=full,
                           applicable_conditional=("policy", "asset_truth"))["ok"] is True


def test_an_invented_conditional_stage_is_refused():
    try:
        F.check_release("a", gates_passed=F.NON_NEGOTIABLE_GATES,
                        applicable_conditional=("vibes",))
    except F.FastLaneRefused as e:
        assert "not conditional stages" in str(e)
    else:
        raise AssertionError("an invented stage was accepted as conditional")


def test_physical_test_and_confidence_are_not_conditional():
    """The two stages a hurry most wants to drop are the two it cannot."""
    assert "physical_test" in F.NON_NEGOTIABLE_GATES
    assert "confidence" in F.NON_NEGOTIABLE_GATES


# ---- what the lane actually buys: scope -----------------------------------


def test_a_small_confident_time_sensitive_product_is_admitted():
    report = F.admit(_candidate())

    assert report["admitted"] is True
    assert "less of it to check" in report["note"]


def test_a_weak_signal_is_a_fast_way_to_make_something_nobody_wanted():
    report = F.admit(_candidate(evidence_confidence=0.4))

    assert report["admitted"] is False
    assert any("nobody wanted" in r for r in report["reasons"])


def test_a_heavy_make_is_not_fast_whatever_the_trend_is_doing():
    report = F.admit(_candidate(half_life="evergreen", make_lane="FLAGSHIP"))

    assert report["admitted"] is False
    assert any("two-week window" in r for r in report["reasons"])


def test_a_risk_class_the_compiler_cannot_fully_verify_is_refused():
    report = F.admit(_candidate(risk_class="C"))

    assert any("there is less to check rather than" in r for r in report["reasons"])


def test_a_new_technique_needs_a_sample_and_a_sample_cannot_be_hurried():
    report = F.admit(_candidate(new_techniques=1))

    assert any("nobody can hurry" in r for r in report["reasons"])


def test_assembly_and_colour_count_are_bounded_in_numbers_not_judgement():
    many_parts = F.admit(_candidate(components=4))
    many_colours = F.admit(_candidate(colours=9))

    assert any("assembly is where a quick make stops being quick" in r
               for r in many_parts["reasons"])
    assert any("chart that disagrees with its written instructions" in r
               for r in many_colours["reasons"])


def test_a_trend_whose_half_life_cannot_repay_the_work_is_refused():
    """The calendar's own rule, reused rather than restated."""
    report = F.admit(_candidate(half_life="flash", make_lane="SHORT"))

    assert report["admitted"] is False
    assert any("half-life" in r or "may not justify" in r for r in report["reasons"])


def test_a_refused_candidate_may_still_be_built_through_the_ordinary_queue():
    report = F.admit(_candidate(components=4))

    assert "through the ordinary queue" in report["note"]


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
