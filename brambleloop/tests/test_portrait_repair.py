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
        model = "claude-sonnet-5"  # priced: the pre-call ceiling check refuses an unpriced model
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
        model = "claude-sonnet-5"  # priced: the pre-call ceiling check refuses an unpriced model
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


def test_assess_judges_and_never_renders():
    """`assess` reads two images and scores them. It must never be a reason to spend.

    This asserted that the whole module never generated, which was true while generation
    was unauthorised and became false when the owner authorised a bounded repair attempt.
    A test that encodes a temporary permission as a permanent invariant fails on the day
    the permission arrives and says nothing about what actually matters -- so it now names
    the durable halves: `assess` renders nothing, and `propose` adopts nothing.
    """
    import inspect as _inspect

    assessing = _inspect.getsource(pr.assess)
    assert "images.generate" not in assessing
    assert "generator" not in assessing


def test_missing_either_image_is_not_a_finding_about_either():
    out = pr.assess(_db(), candidate_ref="", approved_ref="/tmp/approved.jpg")
    assert out["assessed"] is False
    assert "not a finding about either" in out["why"]


def _stub_generator(tmp):
    calls = []

    def generate(prompt, *, reference_urls=None, **kw):
        calls.append({"prompt": prompt, "refs": list(reference_urls or [])})
        path = Path(tmp) / f"candidate-{len(calls)}.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return {"image_ref": str(path), "provider": "test", "cad": 0.04}

    return generate, calls


def _with_compare(compare, fn):
    from brambleloop.visual import model_registry

    original = model_registry.compare_identity
    model_registry.compare_identity = compare
    try:
        return fn()
    finally:
        model_registry.compare_identity = original


def test_nothing_is_rendered_when_the_assessment_cannot_be_made():
    """The load-bearing guard, not a courtesy.

    A candidate nobody can judge is indistinguishable from a different woman, and the one
    outcome worse than no repair is an unverified one adopted because it looked good. Live,
    2026-09-23: both floors are vision calls and that balance is spent.
    """
    from brambleloop.core.models import OwnerAction

    db = _db()
    with db.session() as sess:
        sess.add(OwnerAction(requirement_key="model_provider_balance",
                             action="top up the balance", reason="the balance is spent",
                             done=False))

    out = pr.propose(db, work_dir="/tmp")
    assert out["ran"] is False
    assert out["waiting_on"] == "model_provider_balance"
    assert out["spent_cad"] == 0.0
    assert out["candidates"] == []
    assert "nothing could check for drift" in out["why"]


def test_it_stops_at_the_first_candidate_that_clears_both_floors():
    """The question is whether the method works, not which portrait is prettiest.

    Rendering all three and picking a favourite would be a casting decision nobody
    authorised, and it would spend three times over to answer a question one render
    settled.
    """
    import tempfile

    realism, compare = _judges()
    with tempfile.TemporaryDirectory() as tmp:
        generate, calls = _stub_generator(tmp)
        out = _with_compare(compare, lambda: pr.propose(
            _db(), work_dir=tmp, generator=generate, provider_key="gpt-image-2",
            realism_judger=realism))

    assert len(calls) == 1, "it kept rendering after a candidate had already passed"
    assert out["verdict"] == pr.REPAIRED
    assert out["repaired_candidate"]["attempt"] == 1


def test_it_is_bounded_when_no_candidate_ever_clears():
    """A fourth attempt is evidence the method is wrong rather than the sample."""
    import tempfile

    realism, compare = _judges(realism_false=("skin_looks_real",))
    with tempfile.TemporaryDirectory() as tmp:
        generate, calls = _stub_generator(tmp)
        out = _with_compare(compare, lambda: pr.propose(
            _db(), work_dir=tmp, generator=generate, provider_key="gpt-image-2",
            realism_judger=realism))

    assert len(calls) == pr.MAX_CANDIDATES
    assert out["verdict"] == pr.NOT_REPAIRED
    assert out["repaired_candidate"] is None


def test_a_method_that_drifts_her_identity_is_named_rather_than_retried_into_a_pass():
    """A method that changes the woman is not one to retry. It is one to abandon."""
    import tempfile

    realism, compare = _judges(drift=("face",))
    with tempfile.TemporaryDirectory() as tmp:
        generate, _ = _stub_generator(tmp)
        out = _with_compare(compare, lambda: pr.propose(
            _db(), work_dir=tmp, generator=generate, provider_key="gpt-image-2",
            realism_judger=realism))

    assert out["verdict"] == pr.DIFFERENT_WOMAN
    assert out["repaired_candidate"] is None


def test_the_candidate_is_conditioned_on_her_rather_than_described():
    """Her appearance is carried by the reference image, not by adjectives.

    A prompt that described a face would produce a different woman who matches the words,
    which is the failure `model_photography.prompt_for` already documents. Every clause of
    the repair direction is about the photograph.
    """
    import tempfile

    realism, compare = _judges()
    with tempfile.TemporaryDirectory() as tmp:
        generate, calls = _stub_generator(tmp)
        _with_compare(compare, lambda: pr.propose(
            _db(), work_dir=tmp, generator=generate, provider_key="gpt-image-2",
            realism_judger=realism, approved_ref="/tmp/approved.jpg"))

    assert calls[0]["refs"] == ["/tmp/approved.jpg"], "she was described instead of shown"
    prompt = calls[0]["prompt"].lower()
    # Words that would describe a type rather than repair a photograph. `slim` is
    # deliberately absent from this list: it occurs only inside "do not beautify, slim,
    # youthen", which is a prohibition and the opposite of a description. The first draft
    # of this test banned it outright and failed on the clause that exists to protect her.
    for adjective in ("brunette", "blonde", "young", "beautiful", "pretty"):
        assert adjective not in prompt, f"the prompt describes her: {adjective}"
    assert "do not beautify, slim, youthen" in prompt, (
        "the prohibition against improving her is what makes this a repair")


def test_it_adopts_nothing_and_leaves_the_body_pack_alone():
    """Two standing instructions, asserted rather than trusted to the docstring."""
    import tempfile

    realism, compare = _judges()
    with tempfile.TemporaryDirectory() as tmp:
        generate, _ = _stub_generator(tmp)
        out = _with_compare(compare, lambda: pr.propose(
            _db(), work_dir=tmp, generator=generate, provider_key="gpt-image-2",
            realism_judger=realism))

    assert "no candidate supersedes the canonical reference" in out["adopts_nothing"]
    assert "remain authoritative" in out["body_pack_untouched"]


def test_the_spend_ceiling_stops_it_before_the_attempt_bound_does():
    """Whichever limit binds first is the one that holds."""
    import tempfile

    realism, compare = _judges(realism_false=("skin_looks_real",))
    original = pr.CEILING_CAD
    pr.CEILING_CAD = 0.05  # room for one render at CA$0.0411
    try:
        with tempfile.TemporaryDirectory() as tmp:
            generate, calls = _stub_generator(tmp)
            out = _with_compare(compare, lambda: pr.propose(
                _db(), work_dir=tmp, generator=generate, provider_key="gpt-image-2",
                realism_judger=realism))
    finally:
        pr.CEILING_CAD = original

    assert len(calls) == 1, "it rendered past the ceiling"
    assert out["spent_cad"] <= 0.05


def test_a_check_a_portrait_cannot_answer_does_not_block_the_repair():
    """A floor nothing can clear, in the module whose job is to stop that.

    The first live run judged all three candidates `unverifiable` because
    `hands_are_right` came back unjudged -- on a head-and-shoulders portrait, which has no
    hands in it. `MUST_HOLD` already excluded the morphology dimensions for exactly this
    reason; the same reasoning had not been applied to the realism half.
    """
    assert "hands_are_right" not in pr.PORTRAIT_ANSWERABLE
    assert "skin_looks_real" in pr.PORTRAIT_ANSWERABLE

    # A judge that answers everything except hands, which is what a portrait produces.
    checks = {k: True for k in photoreal.CHECKS}
    del checks["hands_are_right"]

    class _NoHands:
        model = "claude-sonnet-5"  # priced: the pre-call ceiling check refuses an unpriced model
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
    out = _assess(compare, _NoHands())

    assert out["verdict"] == pr.REPAIRED, (
        "a repair was blocked by a question the photograph cannot be asked")


def test_hands_that_are_judged_and_wrong_still_count():
    """Only the requirement to be judged is dropped, never the failure itself."""
    realism, compare = _judges(realism_false=("hands_are_right",))
    out = _assess(compare, realism)
    assert out["verdict"] == pr.NOT_REPAIRED
    assert "hands_are_right" in out["realism_still_failing"]


def test_reassess_recomputes_from_stored_evidence_without_spending():
    """The corrected rule applied to evidence already paid for.

    Not a re-run: the owner's instruction is not to re-judge old evidence merely because
    funding returned, and re-rendering would buy answers already on file.
    """
    record = {"candidates": [
        {"made": True, "attempt": 1,
         "realism_still_failing": ["processing_is_restrained"],
         "realism_unjudged": ["hands_are_right"],
         "identity_drifted": [], "identity_unread": []}]}

    out = pr.reassess(record)
    assert out["verdict"] == pr.NOT_REPAIRED
    assert out["candidates"][0]["verdict_recomputed"] is True
    assert out["candidates"][0]["realism_unjudged_ignored"] == ["hands_are_right"]
    assert "No render and no judgement was re-bought" in out["recomputed"]


def test_reassess_still_reports_a_drifted_candidate_as_a_different_woman():
    """The recomputation must not quietly upgrade anything it should not."""
    record = {"candidates": [
        {"made": True, "attempt": 1, "realism_still_failing": [],
         "realism_unjudged": ["hands_are_right"],
         "identity_drifted": ["face"], "identity_unread": []}]}

    out = pr.reassess(record)
    assert out["verdict"] == pr.DIFFERENT_WOMAN
    assert out["repaired_candidate"] is None


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
