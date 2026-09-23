"""Whether the photographic-realism standard can be met at all.

Two live renders in a row were blocked on `skin_looks_real`, `processing_is_restrained`
and `not_sterile_perfection`, and the second plainly had pores, freckles and fine lines in
it. At that point there are two possibilities needing opposite fixes: the renders really
are unphotographic, or the judge cannot pass a photograph.

This system has found "a floor nothing can clear" four times, so the flattering assumption
is the one not to make. The control is a real photograph -- used as a control and nothing
else: not copied, not re-hosted, not imitated, and never described.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import photoreal  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


class _Judge:
    """A provider that answers however the test needs, and records what it was shown."""

    model = "test-model"
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def __init__(self, **answers):
        self.answers = {k: True for k in photoreal.CHECKS}
        self.answers.update(answers)
        self.shown: list[str] = []

    def see(self, system, prompt, images, max_tokens=0):
        import json as _json
        self.shown.extend(images)
        payload = _json.dumps({**self.answers, "notes": ""})

        class R:
            text = payload
            input_tokens = output_tokens = 0
        return R()


def test_a_judge_that_clears_a_photograph_says_the_standard_is_reachable():
    judge = _Judge()
    out = photoreal.calibrate(_db(), image_url="https://example.invalid/photo.jpg",
                              provider=judge)
    assert out["verdict"] == "clear"
    assert out["reachable"] is True
    assert "needs changing" in out["what_it_means"]
    assert judge.shown == ["https://example.invalid/photo.jpg"]


def test_a_judge_that_blocks_a_photograph_is_the_thing_that_is_wrong():
    """The answer that must not be quietly discarded.

    If a real camera's output fails this standard, then tightening the render against it
    is chasing something nothing can meet -- and every render blocked by it has been
    blocked by a measurement rather than by a defect.
    """
    out = photoreal.calibrate(
        _db(), image_url="https://example.invalid/photo.jpg",
        provider=_Judge(skin_looks_real=False, not_sterile_perfection=False))
    assert out["verdict"] == "blocked"
    assert out["reachable"] is False
    assert out["failed"] == ["not_sterile_perfection", "skin_looks_real"]
    assert "not 'reads as generated'" in out["what_it_means"]


def test_the_calibration_says_what_the_control_is_and_what_it_is_not():
    """Competitor research is for intelligence. The photograph is a control, not a source."""
    out = photoreal.calibrate(_db(), image_url="https://example.invalid/photo.jpg",
                              provider=_Judge())
    for promise in ("not copied", "re-hosted", "never described"):
        assert promise in out["control_is"], promise


def test_no_observed_photograph_means_no_control_rather_than_a_substitute():
    """A generated image used as the control would calibrate the judge against itself."""
    assert photoreal.control_image(_db()) == ""


def test_a_control_is_read_from_the_observed_benchmark():
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks

    db = _db()
    with db.session() as s:
        s.add(BenchmarkListing(
            benchmark_key=benchmarks.MJS_KEY, listing_ref="1", title="t",
            detail={"image_urls": ["https://i.etsystatic.com/example.jpg"]}))
    assert photoreal.control_image(db) == "https://i.etsystatic.com/example.jpg"


def test_a_calibration_belongs_to_the_checks_it_was_made_against():
    """A tightened judge that reads an older calibration back as current is never re-checked."""
    from brambleloop.agents.registry import Registry
    from brambleloop.runtime.release import photoreal_calibration

    db = _db()
    Registry(db).audit("creative_director", photoreal.CALIBRATION_ACTION,
                       detail={"checks_version": "v0-an-earlier-standard",
                               "reachable": True})
    assert photoreal_calibration(db) is None

    Registry(db).audit("creative_director", photoreal.CALIBRATION_ACTION,
                       detail={"checks_version": photoreal.CHECKS_VERSION,
                               "reachable": True})
    assert photoreal_calibration(db)["reachable"] is True



def test_a_control_that_cannot_answer_a_check_is_not_a_standard_that_cannot_pass():
    """The first live calibration, and the defect it nearly wrote into its own verdict.

    The control was a flat-lay swatch with no person and no background in it, so
    `anatomy_is_possible` and `depth_of_field_is_natural` came back unjudged -- honestly,
    because that photograph cannot show either. It failed nothing, and it answered all
    three of the checks that were blocking our renders. Calling that "unreachable" would
    have been a verdict computed from absence of evidence: the exact defect this function
    exists to test for, committed by the test, and it would have sent the next session to
    loosen a standard that was working.
    """
    judge = _Judge()
    del judge.answers["anatomy_is_possible"]
    del judge.answers["depth_of_field_is_natural"]

    out = photoreal.calibrate(_db(), image_url="https://example.invalid/swatch.jpg",
                              provider=judge)
    assert out["verdict"] == "unjudged"
    assert out["failed"] == []
    assert out["reachable"] is True, "a check nobody could make is not a check that failed"
    assert "skin_looks_real" in out["discriminating"]
    assert "unproven rather than unreachable" in out["what_it_means"]


def test_the_three_checks_that_block_our_renders_are_reported_as_discriminating():
    """What the calibration is actually for: which checks a real photograph cleared."""
    out = photoreal.calibrate(_db(), image_url="https://example.invalid/photo.jpg",
                              provider=_Judge())
    for check in ("skin_looks_real", "processing_is_restrained", "not_sterile_perfection"):
        assert check in out["discriminating"], check

class _Ref:
    """A judge with a fixed answer, standing in for the vision model."""

    model = "test"
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def __init__(self, **checks):
        self.answers = {k: True for k in photoreal.CHECKS}
        self.answers.update(checks)

    def see(self, system, prompt, refs, max_tokens=0):
        import json as _json

        class R:
            text = _json.dumps({**self.answers, "notes": "seen"})
            input_tokens = 1
            output_tokens = 1
        return R()


_PATHS = {"face": "/tmp/face.png", "body": "/tmp/body.png", "pack_version": "v2"}


def test_an_airbrushed_reference_is_named_as_the_cause_the_render_inherits():
    """The finding that decides whether to change the method or re-make the pack.

    A generator given a reference reproduces the person in it, skin included. If the
    frozen portrait is already airbrushed then no prompt language can outvote it, and
    three more renders would be spend on a question already answered.
    """
    out = photoreal.reference_realism(_db(), provider=_Ref(skin_looks_real=False),
                                      paths=dict(_PATHS))
    assert out["judged"] is True
    assert out["verdict"] == "pack_is_the_cause"
    assert out["inheritable_failures"] == ["skin_looks_real"]
    assert "the pack is what has to change" in out["what_it_means"]


def test_a_reference_that_fails_only_a_scene_property_does_not_excuse_the_render():
    """Lighting and sterile perfection belong to the scene the new frame builds.

    A reference shot under bad light says nothing about a render made somewhere else, and
    reading it as "the pack is the cause" would let a real generator failure hide behind a
    reference's irrelevant flaw -- a verdict drawn from evidence about something else.
    """
    out = photoreal.reference_realism(_db(), provider=_Ref(lighting_is_coherent=False),
                                      paths=dict(_PATHS))
    assert out["inheritable_failures"] == []
    assert out["other_failures"] == ["lighting_is_coherent"]
    assert out["verdict"] == "pack_is_not_the_cause_of_the_inherited_failures"
    assert "the generator's doing rather than hers" in out["what_it_means"]


def test_a_clean_reference_puts_the_blame_on_the_method():
    out = photoreal.reference_realism(_db(), provider=_Ref(), paths=dict(_PATHS))
    assert out["verdict"] == "pack_is_not_the_cause"
    assert "The method or the provider is what has to change" in out["what_it_means"]


def test_no_materialisable_reference_is_not_a_finding_about_the_pack():
    """Absence of evidence, refused out loud, for the seventh time this week."""
    out = photoreal.reference_realism(_db(), provider=_Ref(),
                                      paths={"face": "", "body": "", "pack_version": "v2"})
    assert out["judged"] is False
    assert "not a finding about the pack" in out["why"]
    assert "verdict" not in out


class _Counting(_Ref):
    """Counts how many times it was actually asked."""

    def __init__(self, **checks):
        super().__init__(**checks)
        self.calls = 0

    def see(self, system, prompt, refs, max_tokens=0):
        self.calls += 1
        return super().see(system, prompt, refs, max_tokens)


def test_the_carried_portrait_is_judged_once_per_set_of_bytes_and_then_read_for_free():
    """It is the same file every time, so the answer cannot change while the bytes do not.

    Asking per build would pay repeatedly for an answer that is already on file, in a
    function whose entire purpose is to refuse before spending.
    """
    db = _db()
    judge = _Counting(skin_looks_real=False)

    first = photoreal.carried_portrait(db, provider=judge)
    assert first["judged"] is True
    assert first["inheritable_failures"] == ["skin_looks_real"]
    assert judge.calls == 1

    second = photoreal.carried_portrait(db, provider=judge)
    assert second["fingerprint"] == first["fingerprint"]
    assert judge.calls == 1, "the same bytes were judged twice"


def test_a_replaced_portrait_is_a_new_question_rather_than_a_stale_refusal():
    """Keying by content hash is what makes replacing the file the fix."""
    db = _db()
    photoreal.carried_portrait(db, provider=_Ref(skin_looks_real=False))

    assert photoreal.filed_portrait_verdict(db, fingerprint="0" * 64) is None


def test_an_unreadable_portrait_is_not_a_finding_about_the_portrait():
    out = photoreal.carried_portrait(_db(), provider=_Ref(),
                                     path="/nowhere/identity_portrait.jpg")
    assert out["judged"] is False
    assert "not readable" in out["why"]
    assert "inheritable_failures" not in out


def test_the_carried_portrait_verdict_says_why_one_file_decides_every_pack():
    out = photoreal.carried_portrait(_db(), provider=_Ref())
    assert "every pack this code can build" in out["why_it_matters"]


def _gallery_judge(**overrides):
    """A judge that answers the gallery realism checks."""
    from brambleloop.visual import gallery

    answers = {k: True for k in gallery.REALISM_CHECKS}
    answers.update(overrides)

    def inspect_image(ref, db=None, provider=None, claim=None):
        return {"image": ref, "described": True, "realism_judged": True,
                "realism": dict(answers),
                "realism_unjudged": [k for k in gallery.REALISM_CHECKS
                                     if k not in answers]}
    return inspect_image


def test_a_check_a_real_photograph_fails_is_named_unreachable():
    """The question four blocked renders made unavoidable.

    Every product-first asset was blocked on `texture_not_repeating`, and crocheted fabric
    is by construction a surface that repeats. If a real photograph fails the same check,
    the gate is asking something no photograph of crochet can satisfy.
    """
    from brambleloop.visual import inspect as inspect_mod

    original = inspect_mod.inspect_image
    inspect_mod.inspect_image = _gallery_judge(texture_not_repeating=False)
    try:
        out = inspect_mod.calibrate(_db(), image_url="https://example.invalid/real.jpg")
    finally:
        inspect_mod.inspect_image = original

    assert out["calibrated"] is True
    assert out["failed"] == ["texture_not_repeating"]
    assert out["reachable"] is False
    assert "nothing can meet" in out["what_it_means"]


def test_a_real_photograph_that_fails_nothing_leaves_the_render_to_blame():
    """The gate has to be able to clear a photograph, or it proves nothing either way."""
    from brambleloop.visual import inspect as inspect_mod

    original = inspect_mod.inspect_image
    inspect_mod.inspect_image = _gallery_judge()
    try:
        out = inspect_mod.calibrate(_db(), image_url="https://example.invalid/real.jpg")
    finally:
        inspect_mod.inspect_image = original

    assert out["reachable"] is True
    assert out["failed"] == []
    assert "a render that needs changing" in out["what_it_means"]


def test_no_benchmark_photograph_is_not_a_finding_about_the_checks():
    """Absence of a control is absence of evidence, for the eighth time this week."""
    from brambleloop.visual import inspect as inspect_mod

    out = inspect_mod.calibrate(_db())
    assert out["calibrated"] is False
    assert "not a finding about the checks" in out["why"]
    assert "failed" not in out


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
