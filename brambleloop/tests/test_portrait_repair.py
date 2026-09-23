"""Whether a repaired canonical portrait is still the same woman, and actually repaired.

The owner's instruction of 2026-09-23: preserve the approved woman and repair the deficient
reference photography rather than casually replacing her. What these tests protect is the
one failure that instruction implies and nothing else in this system would catch -- a
"repair" that fixes the skin and quietly changes who is in the picture.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import identity, photoreal  # noqa: E402
from brambleloop.visual import portrait_repair as pr  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _judges(*, realism_false=(), drift=(), unmeasurable=()):
    """A realism judge and an identity comparer with fixed answers."""
    checks = {k: True for k in photoreal.CHECKS}
    for name in realism_false:
        checks[name] = False

    class _Realism:
        model = "test"
        cost_per_1k_input_cad = 0.0
        cost_per_1k_output_cad = 0.0

        def see(self, system, prompt, refs, max_tokens=0):
            import json as _json

            class R:
                text = _json.dumps(checks)
                input_tokens = 1
                output_tokens = 1
            return R()

    answers = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
    for name in drift:
        answers[name] = identity.DRIFT
    for name in unmeasurable:
        answers[name] = identity.UNMEASURABLE

    def compare(db, ref, cand, *, provider=None):
        return dict(answers)

    return _Realism(), compare


def _assess(monkeypatched_compare, realism_judger, **kw):
    from brambleloop.visual import model_registry

    original = model_registry.compare_identity
    model_registry.compare_identity = monkeypatched_compare
    try:
        return pr.assess(_db(), candidate_ref="/tmp/candidate.png",
                         approved_ref="/tmp/approved.jpg",
                         realism_judger=realism_judger, **kw)
    finally:
        model_registry.compare_identity = original


def test_a_prettier_picture_of_a_different_woman_is_a_replacement_not_a_repair():
    """The failure this module exists for, and the one nothing else would catch.

    `face_identity` compares a render against the pack, so once a drifted portrait becomes
    the pack, every later frame agrees with it perfectly -- the reference that is supposed
    to be the check has become the thing being checked. A silently swapped identity would
    pass every gate this system has.
    """
    realism, compare = _judges(drift=("face",))
    out = _assess(compare, realism)

    assert out["verdict"] == pr.DIFFERENT_WOMAN
    assert out["identity_drifted"] == ["face"]
    assert "reserved" in out["what_to_do"] or "replacement rather than a repair" in out["what_to_do"]
    assert "nothing downstream could detect that afterwards" in out["what_to_do"]


def test_drift_outranks_a_clean_realism_pass():
    """Fixing the skin does not buy permission to change the woman.

    Reporting this as `repaired` because the realism floor passed would be the system
    making the owner's decision on their behalf.
    """
    realism, compare = _judges(drift=("eyes",))
    out = _assess(compare, realism)

    assert out["realism_still_failing"] == [], "the realism floor passed on this candidate"
    assert out["verdict"] == pr.DIFFERENT_WOMAN


def test_still_her_and_still_airbrushed_is_simply_not_repaired_yet():
    """The benign outcome, and it needs a different response from the dangerous one."""
    realism, compare = _judges(realism_false=("skin_looks_real",))
    out = _assess(compare, realism)

    assert out["verdict"] == pr.NOT_REPAIRED
    assert out["realism_still_failing"] == ["skin_looks_real"]
    assert out["identity_drifted"] == []
    assert "not a different woman" in out["what_to_do"]


def test_a_dimension_nobody_could_read_is_unproven_rather_than_unchanged():
    """A comparison that could not see the face has not checked the face."""
    realism, compare = _judges(unmeasurable=("face",))
    out = _assess(compare, realism)

    assert out["verdict"] == pr.UNVERIFIABLE
    assert out["identity_unread"] == ["face"]
    assert "unproven rather than confirmed" in out["what_to_do"]


def test_an_unmade_realism_check_is_not_a_passed_one():
    """Unmade is not passed, here as everywhere else in this system."""
    checks = {k: True for k in photoreal.CHECKS}
    del checks["skin_looks_real"]

    class _Partial:
        model = "test"
        cost_per_1k_input_cad = 0.0
        cost_per_1k_output_cad = 0.0

        def see(self, system, prompt, refs, max_tokens=0):
            import json as _json

            class R:
                text = _json.dumps(checks)
                input_tokens = 1
                output_tokens = 1
            return R()

    _, compare = _judges()
    out = _assess(compare, _Partial())
    assert out["verdict"] == pr.UNVERIFIABLE
    assert "skin_looks_real" in out["realism_unjudged"]


def test_a_real_repair_is_accepted_and_still_left_to_the_owner():
    realism, compare = _judges()
    out = _assess(compare, realism)

    assert out["verdict"] == pr.REPAIRED
    assert out["identity_drifted"] == [] and out["realism_still_failing"] == []
    assert "the owner can decide on" in out["what_to_do"]
    assert "adopts nothing" in out["replaces_nothing"]


def test_an_identity_comparison_that_failed_is_not_a_silent_pass():
    """Unverified is not the same as unchanged, and adopting on it would make the
    reference agree with itself for ever."""
    from brambleloop.visual import model_registry

    realism, _ = _judges()
    out = _assess(lambda db, a, b, provider=None: {"error": "provider refused"}, realism)
    assert out["assessed"] is False
    assert out["verdict"] == pr.UNVERIFIABLE
    assert "agree with itself for ever" in out["why"]


def test_the_dimensions_come_from_identity_rather_than_being_retyped_here():
    """A private list of dimension names would stop matching the judge's vocabulary and
    report every repair as unverifiable -- a floor nothing can clear, via a typo."""
    assert set(pr.MUST_HOLD) <= set(identity.FACE_DIMENSIONS)
    assert "stylisation" not in pr.MUST_HOLD, "a rebuilt photograph may carry a new expression"
    assert not set(pr.MUST_HOLD) & set(identity.MORPHOLOGY_DIMENSIONS), (
        "a head-and-shoulders portrait cannot answer for bust or hips")


def test_it_assesses_and_never_generates():
    """Producing a candidate is spend and a decision the owner has not given."""
    import inspect as _inspect

    source = _inspect.getsource(pr)
    assert "images.generate" not in source
    assert "generator" not in source


def test_missing_either_image_is_not_a_finding_about_either():
    out = pr.assess(_db(), candidate_ref="", approved_ref="/tmp/approved.jpg")
    assert out["assessed"] is False
    assert "not a finding about either" in out["why"]


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
