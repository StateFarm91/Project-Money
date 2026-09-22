"""The canonical reference pack, built from the owner's own candidate.

The owner rejected all five tournament finalists and supplied a generated concept instead,
with two instructions that shape everything here: prove the whole woman holds before
anything is frozen, and treat chest/bust and torso continuity as explicit hard floors rather
than as two of eight dimensions averaged in with the rest.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import brief, identity  # noqa: E402
from brambleloop.visual import reference_pack as rp  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


class _Generator:
    """A stand-in renderer that records what it was conditioned on.

    Given everything the real call receives, on purpose: a double handed less than the real
    generator cannot catch the real generator dropping something, which is exactly how the
    missing reference image survived the benchmark's own tests.
    """

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.calls: list[dict] = []

    def __call__(self, prompt, *, env=None, size="1024x1024", reference_urls=None):
        index = len(self.calls)
        path = self.tmp / f"render-{index}.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + str(index).encode())
        self.calls.append({"prompt": prompt, "refs": list(reference_urls or []),
                           "image_ref": str(path)})
        return {"image_ref": str(path), "provider": "gpt-image-2", "cad": 0.04}


def _seen(**overrides) -> dict:
    out = {d: "described" for d in identity.DRIFT_DIMENSIONS}
    out.update(overrides)
    return out


def _approved_refs() -> set[str]:
    return {brief.approved_reference("torso_fit_reference"),
            brief.approved_reference("full_length_standing")}


def _compare(**overrides):
    """A comparer that behaves like a successful revision unless told otherwise.

    Against the *approved* body it reports the bust as changed and everything else as held,
    which is what a targeted revision looks like. Against the new frames it reports
    everything matching, which is what identity consistency looks like. Two different
    questions, and a double that answered both the same way could not tell them apart.
    """
    def comparer(db, reference_ref, candidate_ref):
        out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        if reference_ref in _approved_refs():
            out["bust"] = identity.DRIFT
            return out
        out.update(overrides)
        return out
    return comparer


def _revision(**overrides):
    """A comparer whose answers *against the approved body* are the ones under test."""
    def comparer(db, reference_ref, candidate_ref):
        out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        if reference_ref in _approved_refs():
            out["bust"] = identity.DRIFT
            out.update(overrides)
        return out
    return comparer


def _build(tmp: Path, *, observe=None, compare=None, hair=None):
    gen = _Generator(tmp)
    package = rp.build(_db(), work_dir=str(tmp), generator=gen,
                       observer=observe or (lambda db, ref: _seen()),
                       comparer=compare or _compare(),
                       hair_comparer=hair or _never_asked)
    return gen, package


def _never_asked(db, reference_ref, candidate_ref):  # pragma: no cover - must not be reached
    raise AssertionError("the hair question was asked when hair did not move")


def _hair(*, arrangement_differs: bool = True, **overrides):
    """The narrower hair question, answered the way the live one answers it.

    Deliberately runs the real verdict rule rather than a hand-set boolean: a double that
    decided `same_hair` for itself could not have caught the bun.
    """
    out = {"colour": identity.MATCH, "length": identity.MATCH, "cut": identity.MATCH}
    out.update(overrides)

    def comparer(db, reference_ref, candidate_ref):
        no_drift = identity.DRIFT not in out.values()
        readable = sum(1 for v in out.values() if v == identity.MATCH)
        return {"same_hair": no_drift and readable >= 2 and arrangement_differs,
                "verdicts": out, "arrangement_differs": arrangement_differs,
                "note": "same hair, worn differently"}
    return comparer


def test_the_reference_is_three_frames_and_the_portrait_is_carried(tmp_path=None):
    """Two defects of one shape: a reference that cannot state what it is trusted for.

    The tournament measured every finalist against a head-and-shoulders portrait, so the
    body was unmeasurable by construction. The first pack added a full-length frame and
    pinned the body from it -- and a standing figure at 1024 pixels reads `bust:
    unmeasurable`, so the chest went into the pack as a dimension nothing could drift from.
    The torso frame is the bridge: close enough to read the chest, wide enough to read the
    torso, and with a face the judge can still match.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        gen, package = _build(Path(tmp))

    frames = [f["frame"] for f in package["reference_frames"]]
    assert frames == ["neutral_portrait", "torso_fit_reference", "full_length_standing"]

    # The portrait is carried from the approved asset rather than rendered: the revision
    # changes one body dimension and must not put an approved face at risk to do it.
    portrait = [f for f in package["reference_frames"] if f["frame"] == "neutral_portrait"][0]
    assert portrait["image_ref"] == brief.approved_portrait()
    assert "carried" in portrait["source"]

    torso_prompt = gen.calls[0]["prompt"].lower()
    for readable in ("bust", "torso length", "waist", "close-fitting"):
        assert readable in torso_prompt, readable
    assert "nothing loose" in torso_prompt

    full_length_prompt = gen.calls[1]["prompt"]
    assert "full-length" in full_length_prompt.lower()
    assert "head to feet" in full_length_prompt.lower()
    for readable in ("stature", "shoulder width", "torso length", "bust", "waist", "hips"):
        assert readable in full_length_prompt.lower(), readable


def test_every_scene_is_conditioned_on_all_three_reference_frames():
    """An identity lock is reference conditioning, not a better description."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        gen, package = _build(Path(tmp))

    portrait = brief.approved_portrait()
    torso, full_length = (c["image_ref"] for c in gen.calls[:2])
    # Each revised frame sees the approved frame it is revising and the approved face it
    # must keep.
    assert gen.calls[0]["refs"] == [brief.approved_reference("torso_fit_reference"), portrait]
    assert gen.calls[1]["refs"] == [torso, brief.approved_reference("full_length_standing")]
    for call in gen.calls[2:]:
        assert call["refs"] == [portrait, torso, full_length], call["prompt"][:40]


def test_each_dimension_is_pinned_from_the_frame_that_can_see_it():
    """The pack's own defect, made into a test.

    The first build pinned the body from the full-length frame, which read the chest as
    unmeasurable -- so `bust` went into the reference pack as the word "unmeasurable", and a
    dimension a reference cannot state is a dimension nothing can drift from. The chest now
    comes from the torso frame, and if no frame can state a required dimension the pack says
    so rather than pinning the absence.
    """
    import tempfile

    def observer(db, ref):
        # render-1 is the full-length: it sees stature and not the chest, exactly as the
        # live one did. render-0 is the torso frame, which sees the chest.
        if ref.endswith("render-1.png"):
            return _seen(bust=identity.UNMEASURABLE, torso=identity.UNMEASURABLE,
                         stature="average to tall")
        if ref.endswith("render-0.png"):
            return _seen(bust="full and clearly rounded", torso="long, narrow waist",
                         stature=identity.UNMEASURABLE)
        return _seen()

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), observe=observer)

    observed = package["reference_observation"]
    assert observed["bust"] == "full and clearly rounded"
    assert observed["torso"] == "long, narrow waist"
    assert observed["stature"] == "average to tall"
    assert package["required_dimensions_unpinned"] == []


def test_a_required_dimension_no_frame_can_state_stops_the_pack():
    """Not approvable, and not quietly passed by the six dimensions that were readable."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp),
                            observe=lambda db, ref: _seen(bust=identity.UNMEASURABLE))

    assert package["required_dimensions_unpinned"] == ["bust"]
    assert package["ready_for_owner_approval"] is False


def test_the_bridge_is_checked_where_the_answer_is_readable():
    """The previous build asked whether a thirty-pixel face matched a portrait.

    It answered `unverifiable` every time, which is a fault in the question rather than a
    finding about the pack. The face is now bridged portrait-to-torso, where the face is
    large, and the body torso-to-full-length, where the body is.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp))

    bridges = package["reference_bridges"]
    assert set(bridges["face_portrait_to_torso"]) == set(identity.FACE_DIMENSIONS)
    assert set(bridges["body_torso_to_full_length"]) == set(identity.MORPHOLOGY_DIMENSIONS)
    assert package["reference_frames_are_the_same_woman"]["verdict"] == "pass"


def test_a_torso_frame_that_cannot_read_the_chest_is_rendered_again():
    """The frame has one job, and three live builds turned on whether it did it.

    A render in which the chest is not readable is a failed render, not a fact about the
    woman. Bounded: a fourth attempt would be evidence that the prompt is wrong rather than
    the sample.
    """
    import tempfile

    def observer(db, ref):
        # render-0 is the torso frame and render-2 is its retry: the first misses the
        # chest, the retry finds it.
        if ref.endswith("render-0.png"):
            return _seen(bust=identity.UNMEASURABLE)
        if ref.endswith("render-2.png"):
            return _seen(bust="full and clearly rounded")
        return _seen()

    with tempfile.TemporaryDirectory() as tmp:
        gen, package = _build(Path(tmp), observe=observer)

    torso = [f for f in package["reference_frames"]
             if f["frame"] == "torso_fit_reference"][0]
    assert torso["attempts"] == 2, "it did not re-render the frame that missed its job"
    assert torso["image_ref"].endswith("render-2.png"), "it kept the frame that missed"
    assert package["reference_observation"]["bust"] == "full and clearly rounded"
    assert package["unpinned_dimensions"] == []

    # And it stops: a pack whose chest is still unreadable after the bound says so rather
    # than rendering until it gets lucky.
    with tempfile.TemporaryDirectory() as tmp:
        _, stuck = _build(Path(tmp),
                          observe=lambda db, ref: _seen(bust=identity.UNMEASURABLE))
    assert stuck["unpinned_dimensions"] == ["bust"]
    assert stuck["ready_for_owner_approval"] is False


def test_a_revision_that_makes_the_whole_woman_bigger_is_caught():
    """The check the owner's instruction actually needs.

    "Increase the bust" is satisfied trivially by a larger woman, and every other floor in
    this module passes her: the face still matches, and nothing drifts against a pack built
    from the new body. Measuring the revision against the body it revised is the only place
    a widened waist shows up as one.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, good = _build(Path(tmp), compare=_revision())
    assert good["revision"]["changed"] is True
    assert good["revision"]["also_moved"] == []
    assert good["approval_conditions"]["the_bust_actually_changed"]["met"] is True
    assert good["approval_conditions"]["nothing_else_changed"]["met"] is True
    assert good["ready_for_owner_approval"] is True

    with tempfile.TemporaryDirectory() as tmp:
        _, bigger = _build(Path(tmp), compare=_revision(
            waist=identity.DRIFT, hips=identity.DRIFT))
    assert bigger["revision"]["also_moved"] == ["hips", "waist"]
    assert bigger["approval_conditions"]["nothing_else_changed"]["met"] is False
    assert bigger["ready_for_owner_approval"] is False


def test_a_revision_that_did_not_change_anything_is_not_a_revision():
    """A generator that ignored the instruction returns the same woman, and that is a fail
    rather than a pass -- the one case where `match` against the old body is wrong."""
    import tempfile

    def unchanged(db, reference_ref, candidate_ref):
        return {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=unchanged)
    assert package["revision"]["changed"] is False
    assert package["approval_conditions"]["the_bust_actually_changed"]["met"] is False
    assert package["ready_for_owner_approval"] is False


def test_a_preserved_dimension_nothing_could_read_is_not_counted_as_unchanged():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=_revision(waist=identity.UNMEASURABLE))
    assert "waist" in package["revision"]["unreadable"]
    assert "waist" not in package["revision"]["also_moved"]
    assert "reported here rather than counted as unchanged" in \
        package["revision"]["unreadable_is_not_preserved"]


def test_hair_worn_up_is_not_a_different_woman():
    """The defect the first real revision run exposed, in production, against real images.

    Eight of nine approval conditions met and the ninth was `nothing_else_changed: ['hair']`
    -- with the before and after showing identical colour, length and cut, worn up in the
    approved references and down in the revised ones. The pack's single `hair` dimension
    conflates who she is with how it was arranged that day, and the brief itself says she
    wears it both ways. A floor that fails a revision for doing what the brief permits is
    not a floor, it is a coin toss.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=_revision(hair=identity.DRIFT),
                            hair=_hair())
    assert package["revision"]["also_moved"] == []
    assert package["revision"]["hair"]["same_hair"] is True
    assert package["revision"]["hair"]["arrangement_differs"] is True
    assert package["approval_conditions"]["nothing_else_changed"]["met"] is True
    assert package["ready_for_owner_approval"] is True


def test_a_bun_is_not_a_haircut():
    """The first live run of the hair check failed on its own floor.

    The approved reference wears her hair up, and length is unmeasurable from a bun by
    construction. The observer said exactly that -- colour match, cut match, length
    unmeasurable, "pulled up into a bun ... the color and highlight pattern match" -- and
    demanding three matches called that a different woman. A floor a bun can never clear
    is the same defect as one nothing can fail, one costume over.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=_revision(hair=identity.DRIFT),
                            hair=_hair(length=identity.UNMEASURABLE))
    assert package["revision"]["also_moved"] == []
    assert package["approval_conditions"]["nothing_else_changed"]["met"] is True


def test_hair_that_moved_with_no_change_of_arrangement_is_unexplained():
    """The discipline that stops the narrower question becoming an excuse. It has to
    *explain* the flagged drift, not merely fail to find one: identical styling with the
    hair still reading as changed is unexplained, and unexplained is not styling."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=_revision(hair=identity.DRIFT),
                            hair=_hair(arrangement_differs=False))
    assert package["revision"]["also_moved"] == ["hair"]
    assert package["ready_for_owner_approval"] is False


def test_hair_that_actually_changed_still_fails_the_revision():
    """The narrower question has to be able to say no, or it is an excuse rather than a
    check. Cutting or recolouring her is a redesign, which is the thing the owner ruled
    out: a targeted morphology revision, not a different woman."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=_revision(hair=identity.DRIFT),
                            hair=_hair(colour=identity.DRIFT))
    assert package["revision"]["also_moved"] == ["hair"]
    assert package["approval_conditions"]["nothing_else_changed"]["met"] is False
    assert package["ready_for_owner_approval"] is False

    with tempfile.TemporaryDirectory() as tmp:
        _, thin = _build(Path(tmp), compare=_revision(hair=identity.DRIFT),
                         hair=_hair(length=identity.UNMEASURABLE,
                                    cut=identity.UNMEASURABLE))
    # One readable match is not evidence of the same hair. A bun costs the length and
    # nothing else, so two of three stays reachable; one of three means the question was
    # not actually answered, and unanswered is not a pass.
    assert thin["revision"]["also_moved"] == ["hair"]


def test_the_torso_retry_chooses_on_the_revision_and_not_only_on_clarity():
    """What the v9 run exposed once its own reporting was honest.

    Three torso frames were rendered with the revision clause on them, the clearest was
    kept, and the revision was never part of the choice -- so a frame that did carry the
    change could be rendered and then discarded for a clearer one that did not. The pack
    then reported `the_bust_actually_changed: match` with no way to tell whether the
    generator had ever complied or whether the selection had thrown the compliance away.

    Readability still wins first: an unreadable frame cannot evidence a change at all,
    which is the rung below. Among equally readable frames, the one that carried the
    instruction wins.
    """
    import tempfile

    rendered: list[str] = []

    def picky(db, reference_ref, candidate_ref):
        out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        if reference_ref in _approved_refs():
            # Renders 0 and 1 are the first torso and full-length frames; the torso
            # retries are 2 and 3. Only the second retry actually moved the bust. The
            # first two torso frames are perfectly readable and perfectly unchanged,
            # which is the case that was silently winning.
            if candidate_ref in rendered and rendered.index(candidate_ref) >= 3:
                out["bust"] = identity.DRIFT
        return out

    with tempfile.TemporaryDirectory() as tmp:
        gen = _Generator(Path(tmp))

        def watched(*a, **kw):
            out = gen(*a, **kw)
            rendered.append(out["image_ref"])
            return out

        package = rp.build(_db(), work_dir=tmp, generator=watched,
                           observer=lambda db, ref: _seen(),
                           comparer=picky, hair_comparer=_never_asked)

    assert package["revision"]["changed"] is True
    assert package["approval_conditions"]["the_bust_actually_changed"]["met"] is True
    torso = next(f for f in package["reference_frames"]
                 if f["frame"] == "torso_fit_reference")
    assert torso["attempts"] > 1, "the loop stopped on a readable frame that had not changed"


def test_the_retry_only_insists_after_it_has_measured_a_failure():
    """Escalation is a response to evidence, not a louder first ask -- and it repeats the
    owner's bounds rather than relaxing them to get a result. The owner asked for a change
    that is clearly visible *and* natural and proportionate; a retry that bought the first
    half by dropping the second would be answering a question nobody asked."""
    plain = brief.revision_clause()
    insisted = brief.revision_clause(insist=True)
    assert plain in insisted and len(insisted) > len(plain)
    for bound in ("still natural", "still proportionate", "never exaggerated",
                  "change nothing else about her"):
        assert bound in insisted
    assert "reproduced the reference chest unchanged" in insisted


def test_an_insisting_retry_builds_on_its_best_attempt_rather_than_the_approved_body():
    """What seven renders across two live runs were actually demonstrating.

    Every torso attempt was conditioned on the approved -- pre-revision -- body, and
    reference conditioning is a far stronger signal than a textual delta, so every attempt
    reproduced the pre-revision chest. Escalating the words changed nothing, because the
    words were never the binding constraint. The measurement does not move with the fix:
    the final frame is still compared against the approved body, so a retry that drifted
    the waist to get there still fails. The anchor is dropped from the generation, not
    from the floor.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        gen = _Generator(Path(tmp))
        rp.build(_db(), work_dir=tmp, generator=gen,
                 observer=lambda db, ref: _seen(bust=identity.UNMEASURABLE),
                 comparer=_revision(), hair_comparer=_never_asked)

    torso_calls = [c for c in gen.calls
                   if brief.revision_clause() in c["prompt"]]
    assert len(torso_calls) >= 3, "the retry budget was not spent"
    approved = brief.approved_reference("torso_fit_reference")
    # The first retry still starts from the approved body: nothing has been measured as
    # unchanged yet, so there is nothing better to build on.
    assert approved in torso_calls[0]["refs"]
    # Once it insists, it builds on its own best frame instead.
    assert approved not in torso_calls[-1]["refs"], \
        "the retry restarted from the body it is trying to revise"
    assert brief.approved_portrait() in torso_calls[-1]["refs"], \
        "identity must still be anchored by the approved face"


def test_an_insisting_retry_changes_the_hand_as_well_as_the_anchor():
    """Eleven torso renders across three versions all reported the chest unchanged, and
    every one of them came from the same provider. "This model declines this edit" is the
    one explanation those eleven cannot distinguish from "the instruction is wrong", so
    the insisting retry tries a second identity-capable renderer. Safe for the same reason
    the anchor change is: every frame is measured against the approved body and the
    approved face afterwards, so a provider that returns a different woman fails the
    floors rather than being trusted."""
    both = {"BRAMBLELOOP_IMAGE_KEY_OPENAI": "x", "BRAMBLELOOP_IMAGE_KEY_BFL": "y"}
    assert rp._alternate_provider(None, both, "gpt-image-2") == "flux-2-pro"
    assert rp._alternate_provider(None, both, "flux-2-pro") != "flux-2-pro"
    # With only one provider it returns the one it has: a retry on a renderer that does
    # not exist is a render that never happens, reported as an attempt that did.
    only = {"BRAMBLELOOP_IMAGE_KEY_OPENAI": "x"}
    assert rp._alternate_provider(None, only, "gpt-image-2") == "gpt-image-2"


def test_a_refused_render_and_an_unhelpful_one_are_told_apart():
    """The loop was spending money and discarding the result of the spending.

    Twelve torso renders across four versions reported the chest unchanged and not one
    left a trace: the pack recorded how many attempts were made and which frame won, and
    nothing about the ones that lost. So "the second provider did not help" and "the
    second provider raised and the loop stopped" produced identical output, and an
    attempt count below the budget could mean either.
    """
    import tempfile

    from brambleloop.core.resilience import TransientError

    with tempfile.TemporaryDirectory() as tmp:
        gen = _Generator(Path(tmp))
        calls = {"n": 0}

        def breaks_on_the_insisting_attempt(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 4:                     # torso, full-length, retry, retry
                raise TransientError("the provider refused this brief")
            return gen(*a, **kw)

        _, package = _build_with(tmp, breaks_on_the_insisting_attempt)

    torso = next(f for f in package["reference_frames"]
                 if f["frame"] == "torso_fit_reference")
    log = torso["attempt_log"]
    assert len(log) >= 2
    refused = [row for row in log if "refused" in str(row.get("failed", ""))]
    assert refused, "a refused render left no trace"
    assert refused[0]["kept"] is False
    # Every row says who rendered it and what it was anchored on, so a provider that
    # never helps is visible as a provider rather than as a missing attempt. (The key is
    # empty here because no image credential is set in the suite; the point under test is
    # that the field is written for every attempt, including the ones that failed.)
    for row in log:
        assert "provider" in row
        assert row["anchor"] in ("the approved body", "its own best frame")
    # The insisting attempt is the one that changed both the anchor and the hand.
    assert any(row["insisted"] and row["anchor"] == "its own best frame" for row in log)


def _build_with(tmp: str, generator):
    package = rp.build(_db(), work_dir=tmp, generator=generator,
                       observer=lambda db, ref: _seen(bust=identity.UNMEASURABLE),
                       comparer=_revision(), hair_comparer=_never_asked)
    return generator, package


def test_the_owner_action_is_rewritten_on_every_build_rather_than_written_once():
    """It told the owner the pack had failed for a day after it stopped failing.

    The row was created on the first build and never touched again, so the one sentence
    somebody reads to decide whether to look was describing a pack five versions old. A
    value written once and read for a week is the same defect as a gate reading
    configuration: right when it was written, and nothing keeps it right.
    """
    import tempfile

    from brambleloop.core.models import OwnerAction
    from brambleloop.runtime import release
    from sqlalchemy import select

    db = _db()
    with db.session() as s:
        s.add(OwnerAction(
            requirement_key="canonical_model_approval",
            action="Approve or reject the canonical Brambleloop model",
            reason="face unverifiable, whole-person morphology unverifiable",
            max_cost_cad=0.0, minutes=10, consequence_of_delay="x", blocks="y"))

    class _Ctx:
        pass

    ctx = _Ctx()
    ctx.db = db
    ctx.job = type("J", (), {"inputs": {}})()
    ctx.audit = lambda *a, **k: None

    with tempfile.TemporaryDirectory() as tmp:
        package = rp.build(db, work_dir=tmp, generator=_Generator(Path(tmp)),
                           observer=lambda db_, ref: _seen(),
                           comparer=_revision(), hair_comparer=_never_asked)
    assert package["ready_for_owner_approval"] is True

    # The handler's rewrite, exercised through the same package the handler would see.
    release._refresh_canonical_model_action(db, package)

    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "canonical_model_approval"))
        assert "unverifiable" not in row.reason
        assert "ready for your review" in row.reason
        assert package["pack_version"] in row.reason


def test_a_verdict_on_a_dimension_no_frame_could_state_is_not_a_verdict():
    """The contradiction the first v9 run was built to stop, seen in production.

    Three torso frames in a row came back with `bust: unmeasurable`, and the comparison of
    those same frames against the approved body returned `bust: match` -- so the pack
    reported that the revision had not changed the bust, on the strength of two images
    neither of which could state a bust. "It did not change" and "nothing here could see
    it" are different findings with different fixes, and printing the first when the second
    is true sends the next run after the generator instead of after the frame.
    """
    import tempfile

    def cannot_see_the_chest(db, ref):
        return _seen(bust=identity.UNMEASURABLE)

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), observe=cannot_see_the_chest,
                            compare=_revision())
    assert package["revision"]["no_frame_could_state_it"] is True
    assert package["revision"]["revised_verdict"] == identity.UNMEASURABLE
    assert package["revision"]["changed"] is False
    condition = package["approval_conditions"]["the_bust_actually_changed"]
    assert condition["met"] is False
    assert "nothing to compare" in condition["detail"]
    assert "is not a pass" in condition["detail"]
    assert package["ready_for_owner_approval"] is False


def test_the_hair_question_is_only_asked_when_hair_moved():
    """It costs a vision call. A second opinion solicited on every dimension that already
    agreed is how a check becomes a way of paying to be told yes."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=_revision())   # _never_asked would raise
    assert package["revision"]["hair"] is None


def test_one_close_fitting_frame_must_read_chest_torso_and_waist_together():
    """The owner's requirement, and the reason for it: a set in which every frame hides the
    chest passes every other check and proves nothing."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp))
    assert package["close_fitting_validation"]["reads"] == ["bust", "torso", "waist"]
    assert package["approval_conditions"][
        "a_close_fitting_frame_reads_chest_torso_and_waist"]["met"] is True

    with tempfile.TemporaryDirectory() as tmp:
        _, hidden = _build(Path(tmp), compare=_hide_in_scenes(
            keep_fit_frame=False, bust=identity.UNMEASURABLE))
    assert hidden["close_fitting_validation"]["reads"] == []
    assert hidden["approval_conditions"][
        "a_close_fitting_frame_reads_chest_torso_and_waist"]["met"] is False
    assert hidden["ready_for_owner_approval"] is False


def test_a_hidden_chest_does_not_stop_approval_and_a_changed_one_does():
    """The condition that could never be met, and the one that must never be.

    Approval used to require every scene to read `pass` on morphology -- in a set the owner
    specified to include a winter coat and a loose sweater. That is a floor nothing could
    clear, which is the same defect as a floor nothing could fail, met from the other side.
    What replaced it is stricter where it counts: no drift anywhere, chest and torso
    evidenced somewhere, every dimension pinned.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, clean = _build(Path(tmp))
    assert clean["ready_for_owner_approval"] is True
    assert all(c["met"] for c in clean["approval_conditions"].values())

    # A scene in which the chest is hidden is `unverifiable` and does not block approval,
    # because the chest was evidenced by the reference bridge.
    with tempfile.TemporaryDirectory() as tmp:
        _, hidden = _build(Path(tmp), compare=_hide_in_scenes(bust=identity.UNMEASURABLE))
    assert hidden["morphology_floor"] == "unverifiable"
    assert hidden["approval_conditions"]["chest_and_torso_evidenced"]["met"] is True
    assert hidden["ready_for_owner_approval"] is True

    # A chest that *changed* still fails, which is the whole point.
    with tempfile.TemporaryDirectory() as tmp:
        _, drifted = _build(Path(tmp), compare=_compare(bust=identity.DRIFT))
    assert drifted["approval_conditions"]["no_morphology_drift_anywhere"]["met"] is False
    assert drifted["ready_for_owner_approval"] is False


def _hide_in_scenes(*, keep_fit_frame: bool = True, **overrides):
    """Reference comparisons read everything; scene comparisons hide what a garment hides.

    The close-fitting validation frame keeps its chest readable by default, because that is
    the frame whose entire job is to expose it -- and the owner requires one such frame.
    """
    seen: list[int] = []

    def comparer(db, reference_ref, candidate_ref):
        out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        if reference_ref in _approved_refs():
            out["bust"] = identity.DRIFT
            return out
        seen.append(1)
        # The two bridges come first, then one comparison pair per scene; the fit frame is
        # the second scene, so its pair is the fifth and sixth calls.
        is_fit_frame = len(seen) in (5, 6)
        if len(seen) > 2 and not (keep_fit_frame and is_fit_frame):
            out.update(overrides)
        return out
    return comparer


def test_the_reference_bridge_counts_as_continuity_evidence():
    """Two separately generated photographs of the same woman, compared dimension by
    dimension, is the continuity test -- not a lesser form of it.

    The first three-frame run had `bust: match` and `torso: match` on the torso-to-
    full-length comparison and reported both as unproven, because the check read only the
    four garment scenes. In those the chest is genuinely hidden by a crocheted sweater and a
    winter scarf, which the rule correctly calls unmeasurable -- so the pack could never be
    approvable no matter how well the identity held.
    """
    scenes = [{"scene": "winter_seasonal", "rendered": True,
               "dimensions": {"bust": identity.UNMEASURABLE,
                              "torso": identity.UNMEASURABLE}}]
    bridge = {"bust": identity.MATCH, "torso": identity.MATCH}

    without = rp._required_evidence(scenes)
    assert without["bust"]["verdict"] == "unverifiable"

    with_bridge = rp._required_evidence(scenes, bridge)
    assert with_bridge["bust"]["verdict"] == "pass"
    assert with_bridge["torso"]["matched_in"] == ["reference:torso_to_full_length"]

    # And drift anywhere still fails, including on the bridge: the reference frames
    # disagreeing about the chest is the worst version of this, not an exempt one.
    drifted = rp._required_evidence(scenes, {"bust": identity.DRIFT,
                                             "torso": identity.MATCH})
    assert drifted["bust"]["verdict"] == "fail"


def test_the_validation_frame_is_controlled_rather_than_commercial():
    """It was dressed in a close-fitting crocheted top, and crochet is textured and open.

    The judge read the chest as "unmeasurable (garment structure and fit obscure natural
    shape)" and the one frame whose job was to make chest, torso and waist readable
    together failed at it. The product belongs in the four commercial scenes; this frame
    exists to be measurable.
    """
    keys = [k for k, _ in brief.STRESS_SCENES]
    assert brief.FIT_VALIDATION_SCENE in keys
    prompt = dict(brief.STRESS_SCENES)[brief.FIT_VALIDATION_SCENE].lower()
    for needed in ("chest", "torso length", "waist", "plain close-fitting"):
        assert needed in prompt, needed
    assert "crochet" not in prompt, "the validation frame is wearing the product again"
    assert "open-work" in prompt


def test_a_decline_with_a_reason_is_still_a_decline():
    """The live answer was "unmeasurable (garment structure and fit obscure natural shape)"
    and an exact-match readability test read it as a reading.

    So the torso retry never fired, the chest was pinned from the full-length frame
    instead, and the frame built to make the chest readable was allowed to fail at its only
    job -- the same shape as every string comparison this build has had to fix.
    """
    assert rp._readable("unmeasurable (garment structure and fit obscure natural shape)") \
        is False
    assert rp._readable("cannot be assessed from this angle") is False
    assert rp._readable("narrow, defined waistline visible above waistband") is True
    assert rp._readable("") is False
    assert rp._readable(None) is False


def test_a_face_the_camera_was_too_far_away_to_see_is_not_a_failure_of_identity():
    """One of the five scenes is a full-length editorial. Requiring every scene to read the
    face is the floor-nothing-can-clear mistake, met from the same side as before."""
    import tempfile

    def far_away(db, reference_ref, candidate_ref):
        out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        if reference_ref in _approved_refs():
            out["bust"] = identity.DRIFT
            return out
        far_away.seen = getattr(far_away, "seen", 0) + 1
        if far_away.seen == 3:  # the first scene's face comparison
            for d in identity.FACE_DIMENSIONS:
                out[d] = identity.UNMEASURABLE
        return out

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=far_away)

    assert package["face_floor"] == "unverifiable"
    held = package["approval_conditions"]["facial_identity_held"]
    assert held["met"] is True, held
    assert "matched in" in held["detail"]

    # A face that actually drifted still fails, which is the whole point.
    with tempfile.TemporaryDirectory() as tmp:
        _, drifted = _build(Path(tmp), compare=_compare(face=identity.DRIFT))
    assert drifted["approval_conditions"]["facial_identity_held"]["met"] is False


def test_a_face_match_above_a_changed_chest_fails():
    """The failure the owner named, as the test that has to keep failing."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=_compare(bust=identity.DRIFT))

    assert package["face_floor"] == "pass"
    assert package["morphology_floor"] == "fail"
    assert package["required_morphology"]["bust"]["verdict"] == "fail"
    assert package["ready_for_owner_approval"] is False


def test_an_obscured_chest_is_unverifiable_and_never_a_pass():
    """Clothing hides anatomy; a set that never saw the chest did not prove it."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=_compare(bust=identity.UNMEASURABLE))

    assert package["morphology_floor"] == "unverifiable"
    assert package["required_morphology"]["bust"]["verdict"] == "unverifiable"
    assert package["required_morphology"]["torso"]["verdict"] == "pass"
    assert package["ready_for_owner_approval"] is False
    # And it is not reported as drift: nobody looked, which is a different fact.
    assert package["morphology_drifted_scenes"] == []


def test_a_clean_run_is_ready_for_approval_and_still_frozen_by_nobody():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp))

    assert package["built"] is True
    assert package["face_floor"] == "pass"
    assert package["morphology_floor"] == "pass"
    assert package["required_morphology_ok"] is True
    assert package["ready_for_owner_approval"] is True
    assert package["decision"] == "owner"
    # Nothing in this module can freeze an identity, and that is checked by parsing rather
    # than by grepping -- the docstring names `select_canonical` to say what this module is
    # not allowed to do, and a text search cannot tell a call from a sentence about a call.
    import ast

    tree = ast.parse((ROOT / "src/brambleloop/visual/reference_pack.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = (func.attr if isinstance(func, ast.Attribute) else
                    func.id if isinstance(func, ast.Name) else "")
            assert name not in ("select_canonical", "select"), f"{name} is called here"
        if isinstance(node, ast.keyword):
            assert node.arg != "owner_approved"


def test_the_two_reference_frames_are_checked_against_each_other():
    """If the portrait and the full-length are two women, the pack is already incoherent."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        _, package = _build(Path(tmp), compare=_compare(face=identity.DRIFT))

    coherence = package["reference_frames_are_the_same_woman"]
    assert coherence["verdict"] == "fail"
    assert package["ready_for_owner_approval"] is False


def test_bust_and_torso_are_required_rather_than_counted():
    """Three of eight readable clears the count and can still miss what went wrong."""
    scored = {d: identity.UNMEASURABLE for d in identity.DRIFT_DIMENSIONS}
    for readable in ("stature", "shoulders", "limbs"):
        scored[readable] = identity.MATCH
    for face in identity.FACE_DIMENSIONS:
        scored[face] = identity.MATCH

    pack = identity.select(
        identity.Candidate("c", fields={f: "described" for f in identity.IDENTITY_FIELDS}),
        owner_approved=True)
    out = identity.drift_check(scored, pack)
    assert out["morphology"]["verdict"] == "unverifiable"
    assert out["morphology"]["required_unreadable"] == ["bust", "torso"]
    assert "hard-floor dimensions" in out["reason"]


def test_a_job_asking_for_a_newer_pack_than_this_build_makes_fails_rather_than_answering():
    """A rolling deploy runs two commits at once and the queue does not care which one.

    Observed live: the boot enqueue of the corrected pack was picked up by a replica still
    running the previous build, which computed the *old* fingerprint, found the old pack,
    reported "already built" and left the corrected pack unrun with its key spent. Every
    word of that answer was true and it was about a different question.
    """
    from brambleloop.runtime import release

    class _Ctx:
        db = None
        job = type("J", (), {"inputs": {"pack_version": "v99-from-the-future"}})()

        def audit(self, *a, **k):  # pragma: no cover - must not be reached
            raise AssertionError("it answered instead of standing aside")

    try:
        release.handle_model_reference_pack(_Ctx())
    except RuntimeError as e:
        assert "another replica" in str(e)
    else:
        raise AssertionError("a stale build answered for a pack it cannot produce")


def test_the_tournament_does_not_run_once_the_owner_has_chosen_a_candidate():
    """Rendering twenty more women answers a question the owner has answered."""
    assert brief.owner_candidate_supplied() is True

    from brambleloop.runtime import release

    class _Ctx:
        db = None
        job = type("J", (), {"inputs": {}})()

        def audit(self, *a, **k):  # pragma: no cover - must not be reached
            raise AssertionError("the tournament spent something")

    out = release.handle_model_tournament(_Ctx())
    assert out["ran"] is False
    assert "supplied a canonical-model candidate" in out["reason"]


def test_the_owners_candidate_is_a_generated_concept_and_the_rules_still_hold():
    """Owner-supplied does not exempt a candidate from the public-figure screen."""
    state = brief.state()
    assert "not a photograph of a real person" in state["owner_candidate"]["is"]
    assert "public_figure_likeness" in [f["rule"] for f in state["forbidden"]]
    assert "real_person_reference" in [f["rule"] for f in state["forbidden"]]
    assert "not eligible for automatic selection" in \
        state["owner_candidate"]["rejected_finalists"]
    # And the conditioning source is a clean frame rather than the collage or the frame
    # with the brand lockup printed across it.
    assert Path(brief.candidate_reference()).is_file()
    assert Path(brief.candidate_concept()).is_file()


def test_the_bust_direction_is_the_owners_revision():
    """Recorded as a pinned identity dimension, not left as a styling preference."""
    assert brief.PHYSICAL_DIRECTION["bust"].startswith("full and clearly rounded")
    assert "bust" in brief.REQUIRED_MORPHOLOGY
    assert identity.REQUIRED_MEASURABLE["morphology"] == ("bust", "torso")


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
