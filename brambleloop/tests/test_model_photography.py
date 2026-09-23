"""A listing frame with the canonical model in it (#72, #130, #202).

The path everything waited on: she was approved, frozen and enforced, and nothing built a
frame with her in it. What these tests protect is the difference between a frame that was
*conditioned on* the frozen identity and checked afterwards, and one that merely says it
was -- because a prompt listing her features produces a different woman who matches the
adjectives, and a generator asked whether it complied says yes.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# Before the artifact store is imported: it reads its root once, and the body reference
# these tests file has to be somewhere the test owns.
_ART = tempfile.TemporaryDirectory(prefix="model-frame-artifacts-")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = _ART.name

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.products.builder import for_slug  # noqa: E402
from brambleloop.publish import model_photography as mp  # noqa: E402
from brambleloop.visual import bible, brief, identity  # noqa: E402
from brambleloop.visual import inspect as inspect_mod  # noqa: E402
from brambleloop.visual import model_registry, photoreal  # noqa: E402


def _db(*, frozen: bool = True, body_reference: bool = True) -> Database:
    db = Database("sqlite://")
    db.create_all()
    if frozen:
        model_registry.record_candidate(
            db, "brambleloop-canonical",
            fields={f: f"{f} as described" for f in identity.IDENTITY_FIELDS},
            image_refs=[brief.approved_portrait()])
        model_registry.select_canonical(db, "brambleloop-canonical", owner_approved=True)
    if body_reference:
        _file_body_reference(db)
    return db


def _file_body_reference(db, *, pack_version: str = "v-test") -> None:
    """The frozen pack's own torso frame, kept where a restart cannot reach it.

    The production path compares the body against this rather than against the portrait,
    so a fixture without it is a fixture in which the morphology floor cannot pass -- which
    is exactly what happened in production and is why these two rows exist here.
    """
    from brambleloop.agents.registry import Registry
    from brambleloop.visual import freeze, reference_pack, tournament

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        fh.write(b"\x89PNG\r\n\x1a\ntorso")
        path = fh.name
    frame = {"frame": freeze.BODY_FRAME, "image_ref": path,
             "image": tournament._keep(path, db=db, why="a test body reference")}
    Registry(db).audit("creative_director", reference_pack.PACK_ACTION,
                       detail={"built": True, "pack_version": pack_version,
                               "reference_frames": [frame]})
    Registry(db).audit("creative_director", "model.frozen",
                       detail={"freeze": {"pack_version": pack_version}})


def _subject(slug: str = "cloudline-baby-blanket"):
    cir = for_slug(slug)
    return cir, build_twin(cir, compile_cir(cir))


class _Generator:
    """Records exactly what it was asked to condition on."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.calls: list[dict] = []

    def __call__(self, prompt, *, env=None, size="1024x1024", reference_urls=None):
        path = self.tmp / f"frame-{len(self.calls)}.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        self.calls.append({"prompt": prompt, "refs": list(reference_urls or [])})
        return {"image_ref": str(path), "provider": "gpt-image-2", "cad": 0.04}


def _observer(**overrides):
    """A comparison that never sees the prompt -- the signature makes that structural."""
    def compare(db, reference_ref, candidate_ref):
        out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        out.update(overrides)
        return out
    return compare


def _inspector():
    def inspect(image_ref, *, db=None, claim=None):
        out = {"image": image_ref, "described": True, "realism_judged": True,
               "description": {"finished_or_in_progress": "finished",
                               "chart_or_diagram": False, "human_present": True,
                               "clarity": "clear", "object_count": "1",
                               "third_party_marks": []},
               "realism": {k: True for k in inspect_mod.REALISM_CHECKS},
               "realism_unjudged": []}
        if claim:
            out["semantic"] = inspect_mod.compare(out["description"], claim)
        return out
    return inspect


def _motif(**overrides):
    answer = {"repeating_unit_shape": "diamond outline lattice", "repeats_across": 14,
              "colour_arrangement": "two colours alternating", "same_pattern_as_chart": True,
              "fabric_readable": True}
    answer.update(overrides)
    return lambda image_ref, chart_ref: answer


def _realism(**overrides):
    checks = {k: True for k in photoreal.CHECKS}
    checks.update(overrides)
    return lambda image_ref, db=None: {"judged": True, "checks": checks, "notes": ""}


def _styling(**overrides):
    def judge(image_ref, db=None, axes=None):
        asked = tuple(axes or tuple(bible.AXES))
        answers = {k: True for k in bible.QUESTIONS if bible.AXIS_OF[k] in asked}
        answers.update({k: v for k, v in overrides.items()
                        if bible.AXIS_OF[k] in asked})
        return {"judged": True, "answers": answers, "axes": list(asked), "notes": ""}
    return judge


def _make(db, tmp: Path, *, slug="winter-cardigan", **kw):
    import dataclasses

    cir, twin = _subject()
    cir = dataclasses.replace(cir, slug=slug, title="Cardigan")
    gen = _Generator(tmp)
    record = mp.make(db, cir, twin, generator=gen,
                     observer=kw.pop("observer", _observer()),
                     inspector=kw.pop("inspector", _inspector()),
                     motif_judger=kw.pop("motif_judger", _motif()),
                     realism_judger=kw.pop("realism_judger", _realism()),
                     styling_judger=kw.pop("styling_judger", _styling()), **kw)
    return gen, record


def test_the_frame_is_conditioned_on_the_frozen_pack_rather_than_described():
    """The property that makes this an identity lock instead of a description.

    A prompt that lists dark hair and light eyes produces a woman who matches the
    adjectives and is not her. The reference image goes to the provider as a reference,
    and the record names what it conditioned on.
    """
    db = _db()
    with tempfile.TemporaryDirectory() as tmp:
        gen, record = _make(db, Path(tmp))

    assert record["made"] is True
    assert len(gen.calls) == 1
    # Two references, not one: the face frame and the pack's own body frame. A generator
    # handed only a portrait has been asked for a body it was never shown.
    assert gen.calls[0]["refs"][0] == brief.approved_portrait(), gen.calls[0]["refs"]
    assert gen.calls[0]["refs"][1] == record["conditioned_on"]["body_reference_image"]
    assert record["conditioned_on"]["reference_image"] == brief.approved_portrait()
    assert record["conditioned_on"]["body_reference_frame"] == "torso_fit_reference"
    assert record["conditioned_on"]["pack_version"] == 1
    # And her features are not smuggled into the prompt as adjectives instead.
    prompt = gen.calls[0]["prompt"]
    assert "reference image" in prompt
    for described in ("facial_geometry as described", "bust_proportions as described"):
        assert described not in prompt


def test_nothing_is_rendered_before_there_is_somebody_to_check_against():
    """With no frozen identity a model frame is a stranger with a caption, so it is
    refused rather than rendered -- and refused without spending."""
    db = _db(frozen=False)
    with tempfile.TemporaryDirectory() as tmp:
        gen, record = _make(db, Path(tmp))
    assert record["made"] is False
    assert record["waiting_on"] == "canonical_model"
    assert gen.calls == [], "money was spent before there was anything to verify against"


def test_the_result_is_verified_by_something_that_did_not_render_it():
    """Conditioning is a request, not a result. The generator is never asked whether it
    complied: a vision model describes the frame and `drift_check` decides."""
    db = _db()
    with tempfile.TemporaryDirectory() as tmp:
        _, record = _make(db, Path(tmp))
    assert record["identity"]["face"]["verdict"] == "pass"
    assert record["identity"]["morphology"]["verdict"] == "pass"
    assert "never saw the prompt" in record["identity"]["checked_by"]
    assert record["usable_as_listing_asset"] is True


def test_a_drifted_face_and_a_drifted_body_each_block_on_their_own():
    """Two independent floors. Either one fails the frame and neither can cover for the
    other -- the failure the owner named is a familiar face over a different body."""
    db = _db()
    with tempfile.TemporaryDirectory() as tmp:
        _, face = _make(db, Path(tmp), observer=_observer(face=identity.DRIFT))
    assert face["floors"]["face_identity"] == "fail"
    assert face["usable_as_listing_asset"] is False

    with tempfile.TemporaryDirectory() as tmp:
        _, body = _make(db, Path(tmp),
                        observer=_observer(bust=identity.DRIFT, torso=identity.DRIFT))
    assert body["floors"]["face_identity"] == "pass"
    assert body["floors"]["whole_person_morphology"] == "fail"
    assert body["usable_as_listing_asset"] is False, \
        "a matching face carried a drifted body onto a listing"


def test_an_unreadable_chest_is_unverifiable_and_never_a_pass():
    db = _db()
    with tempfile.TemporaryDirectory() as tmp:
        _, record = _make(db, Path(tmp),
                          observer=_observer(bust=identity.UNMEASURABLE,
                                             torso=identity.UNMEASURABLE))
    assert record["floors"]["whole_person_morphology"] != "pass"
    assert record["usable_as_listing_asset"] is False


def test_a_beautiful_photograph_of_the_wrong_crochet_fails():
    """Product truth is its own floor and beauty cannot buy it. The checkerboard case."""
    db = _db()
    with tempfile.TemporaryDirectory() as tmp:
        _, record = _make(db, Path(tmp), motif_judger=_motif(
            repeating_unit_shape="solid square", repeats_across=8))
    assert record["floors"]["face_identity"] == "pass"
    assert record["floors"]["photographic_realism"] == "pass"
    assert record["floors"]["product_truth"] == "fail"
    assert record["usable_as_listing_asset"] is False


def test_a_frame_that_reads_as_generated_fails_even_when_everything_else_holds():
    """The owner's natural-photography standard, as a floor rather than a preference."""
    db = _db()
    with tempfile.TemporaryDirectory() as tmp:
        _, record = _make(db, Path(tmp), realism_judger=_realism(hands_are_right=False))
    assert record["floors"]["product_truth"] == "pass"
    assert record["floors"]["photographic_realism"] == "fail"
    assert record["usable_as_listing_asset"] is False
    assert "hands_are_right" in record["photographic_realism"]["failed"]


def test_an_unjudged_realism_check_is_not_a_pass():
    db = _db()
    with tempfile.TemporaryDirectory() as tmp:
        _, record = _make(db, Path(tmp),
                          realism_judger=lambda ref, db=None: {"judged": True,
                                                               "checks": {}, "notes": ""})
    assert record["photographic_realism"]["verdict"] == "unjudged"
    assert record["floors"]["photographic_realism"] == "unverifiable"
    assert record["usable_as_listing_asset"] is False


def test_the_product_stays_the_hero_in_what_is_asked_for():
    """#202: she is present to show fit, scale and use, and the crochet is the subject."""
    db = _db()
    with tempfile.TemporaryDirectory() as tmp:
        gen, _ = _make(db, Path(tmp))
    prompt = gen.calls[0]["prompt"]
    assert brief.PRODUCT_IS_THE_HERO in prompt
    assert "fit, scale and use" in prompt
    # And the photography standard is asked for, not only checked afterwards.
    assert photoreal.DIRECTION in prompt


def test_the_model_is_the_exception_and_an_unclassified_form_is_shot_as_an_object():
    """The defect production data exposed, as the fixture that keeps it fixed.

    `form_of` knew only the product-first vocabulary, so a slug with no product-first word
    fell back to the CIR's *construction*: `winter-village-graphghan` -- a blanket --
    reported its form as `flat_rows`, and asking "is this not product-first" then classed
    it as needing a model. Four catalogue products were, including a pet snuggle mat and a
    wall hanging. A construction is not a form, and "not on the product-first list" is not
    the same claim as "somebody has to wear it".

    #74 makes her the exception rather than the fallback, so the answer comes off an
    allowlist of worn forms and an unclassified product is photographed as an object. The
    cost of being wrong that way is a flat photograph of a scarf; the other way it is a
    woman draped in a blanket and a render nobody should have paid for.
    """
    import dataclasses

    from brambleloop.products.builder import CATALOGUE, for_slug
    from brambleloop.publish import listing_asset, owned_photography as op

    routed = [s for s in CATALOGUE
              if for_slug(s) is not None and listing_asset.needs_the_model(for_slug(s))]
    assert routed == [], f"flat catalogue products routed to the model path: {routed}"

    # And every catalogue form names itself rather than its construction.
    for slug in CATALOGUE:
        cir = for_slug(slug)
        if cir is None:
            continue
        assert op.form_of(cir) != (cir.construction or "").lower(), \
            f"{slug} is labelled by its construction rather than its form"

    # The gate still bites where it should: a worn form needs her.
    base = for_slug("cloudline-baby-blanket")
    for worn in ("winter-cardigan", "alpine-beanie", "cosy-scarf", "hats-hat-0"):
        assert listing_asset.needs_the_model(dataclasses.replace(base, slug=worn)), worn

    # An unknown form is not a worn one.
    assert not listing_asset.needs_the_model(
        dataclasses.replace(base, slug="mystery-thing"))



def _file(db, record):
    """Put a record on the audit log the way the handler does.

    The handler files the *sequence*, not its frames: `listing_asset.make` writes the one
    record `sequence()` returned, with the individual frames nested inside it. Tests that
    filed frames one at a time were describing a shape production never writes, which is
    how frame reuse shipped green and dead -- so every caller here passes the sequence.
    """
    from brambleloop.agents.registry import Registry

    Registry(db).audit("publishing", mp.ACTION, detail=record)


def test_a_release_with_an_unusable_frame_does_not_have_a_frame():
    """The handler used to stop at the existence of a row.

    On 2026-09-22 the first live frame came back with face identity passing and three
    floors `unverifiable` -- a head-and-shoulders crop with no body and no readable
    fabric in it. The handler's idempotency then answered "this release already has a
    model frame" and declined to render again, so a release whose only frame could not be
    used reported as finished, and the next deploy agreed with it. A row standing in for
    the capability the row was supposed to evidence is the defect this whole system exists
    to catch, and it had got into the guard rather than the gate.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = _db()
        _, record = _make(db, Path(tmp), realism_judger=_realism(skin_looks_real=False))
        assert record["usable_as_listing_asset"] is False
        _file(db, record)

        move = mp.what_to_do_next(db, slug=record["slug"], version=record["version"])
        assert move["render"] is True
        assert move["reason"] == "no_usable_frame_yet"
        assert move["attempts"] == 1
        assert mp.usable_asset(db, slug=record["slug"]) is None


def test_a_release_with_a_usable_frame_is_not_rendered_again():
    with tempfile.TemporaryDirectory() as tmp:
        db = _db()
        _, record = _make(db, Path(tmp))
        assert record["usable_as_listing_asset"] is True
        _file(db, record)

        move = mp.what_to_do_next(db, slug=record["slug"], version=record["version"])
        assert move["render"] is False
        assert move["reason"] == "usable_frame_on_file"
        assert mp.usable_asset(db, slug=record["slug"])["image_ref"] == record["image_ref"]


def test_retrying_is_bounded_and_says_the_method_is_what_needs_changing():
    """Unbounded retry is how a loop spends the ceiling chasing the same failure.

    Each attempt fails a *different* floor on purpose. Three attempts failing the same one
    is a systematic failure and stops earlier for a better reason, which the block tests
    cover; this is the bad-luck case the per-release bound exists for, and giving it the
    systematic pattern would have tested the wrong gate.
    """
    breakers = (
        {"realism_judger": _realism(skin_looks_real=False)},
        {"styling_judger": _styling(light_is_soft_and_directional=False)},
        {"motif_judger": _motif(repeating_unit_shape="solid square", repeats_across=8)},
    )
    with tempfile.TemporaryDirectory() as tmp:
        db = _db()
        for breaker in breakers[:mp.ATTEMPTS]:
            _, record = _make(db, Path(tmp), **breaker)
            _file(db, record)

        move = mp.what_to_do_next(db, slug=record["slug"], version=record["version"])
        assert move["render"] is False
        assert move["reason"] == "attempts_exhausted"
        assert move["attempts"] == mp.ATTEMPTS
        assert "the method" in move["why"] and "METHOD_VERSION" in move["why"]


def test_a_corrected_method_is_not_locked_out_by_the_old_ones_attempts():
    """The attempts belong to the method, not to the product.

    A new METHOD_VERSION is a different question, and answering it with the previous
    method's exhausted budget is how a fix never gets to run.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = _db()
        for _ in range(mp.ATTEMPTS):
            _, record = _make(db, Path(tmp),
                              realism_judger=_realism(skin_looks_real=False))
            _file(db, record)
        stale = dict(record, method_version="v0-an-earlier-method")
        assert mp.what_to_do_next(
            db, slug=record["slug"], version=record["version"])["render"] is False

        fresh = _db()
        _file(fresh, stale)
        move = mp.what_to_do_next(fresh, slug=stale["slug"], version=stale["version"])
        assert move["render"] is True and move["attempts"] == 0


def test_each_shot_asks_for_what_its_floor_has_to_read():
    """A floor nothing can clear is the same defect as one nothing can fail.

    The fit frame has to show a body the morphology check can measure; the detail frame
    has to show fabric the motif check can count. Neither prompt can do both jobs, which
    is why there are two of them.
    """
    cir, twin = _subject()
    pack = model_registry.canonical_pack(_db())

    fit = mp.prompt_for(cir, twin, pack, plan=mp.SHOT_PLAN)
    for part in ("shoulders", "chest", "torso", "waist", "hips"):
        assert part in fit, part

    detail = mp.prompt_for(cir, twin, pack, plan=mp.DETAIL_PLAN)
    assert "stitches" in detail and "repeat" in detail
    assert "sharply in focus" in detail


def test_styling_is_a_floor_of_its_own_and_the_right_woman_does_not_excuse_it():
    """The gap #73 and #202 both named.

    Every dimension the identity gate measures matches; the makeup is editorial, the light
    is gelled and the dress has a print that fights the crochet. Before the character
    bible, nothing in the release path could tell -- the frame was exactly the right woman,
    so exactly the right woman shipped.
    """
    with tempfile.TemporaryDirectory() as tmp:
        _, record = _make(_db(), Path(tmp), styling_judger=_styling(
            makeup_is_daytime_natural=False, nothing_competes_with_the_product=False))
    assert record["floors"]["face_identity"] == "pass"
    assert record["floors"]["styling"] == "fail"
    assert record["usable_as_listing_asset"] is False
    assert sorted(record["styling"]["outside"]) == ["makeup", "wardrobe"]


def test_unjudged_styling_is_not_a_pass_either():
    def half_read(image_ref, db=None, axes=None):
        asked = tuple(axes or tuple(bible.AXES))
        keys = [k for k in bible.QUESTIONS if bible.AXIS_OF[k] in asked]
        return {"judged": True, "notes": "", "axes": list(asked),
                "answers": {k: True for k in keys[:2]}}

    with tempfile.TemporaryDirectory() as tmp:
        _, record = _make(_db(), Path(tmp), styling_judger=half_read)
    assert record["floors"]["styling"] == "unverifiable"
    assert record["usable_as_listing_asset"] is False


def test_the_frame_is_asked_for_the_styling_it_will_be_checked_on():
    """A prompt that asks for one thing and a gate that checks another is two standards."""
    cir, twin = _subject()
    db = _db()
    prompt = mp.prompt_for(cir, twin, model_registry.canonical_pack(db))
    assert bible.direction() in prompt


def test_the_body_is_compared_against_a_body_rather_than_against_a_portrait():
    """The reason the morphology floor could not pass in production.

    `select_canonical` takes one `reference_image`, and freezing put the committed portrait
    there because it is the only reference that survives a container restart. Every frame
    was then compared, whole, against a head-and-shoulders crop -- so bust, torso, waist
    and hips came back `unmeasurable` however well the frame was shot. That is a floor
    nothing can clear, which is the same defect as one nothing can fail.
    """
    asked: list[str] = []

    def look(db, reference_ref, candidate_ref):
        asked.append(reference_ref)
        out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        # A portrait genuinely cannot answer for the body, so the fixture does not let it.
        if reference_ref == brief.approved_portrait():
            for d in identity.MORPHOLOGY_DIMENSIONS:
                out[d] = identity.UNMEASURABLE
        return out

    with tempfile.TemporaryDirectory() as tmp:
        _, record = _make(_db(), Path(tmp), observer=look)

    assert len(asked) == 2 and asked[0] == brief.approved_portrait()
    assert asked[1] != asked[0], "the body was asked of the portrait again"
    assert record["floors"]["face_identity"] == "pass"
    assert record["floors"]["whole_person_morphology"] == "pass"


def test_without_a_body_reference_the_morphology_floor_is_unverifiable_not_passed():
    """And never falls back to the committed pre-revision body frames.

    Those are the superseded pack the owner replaced. Comparing against them would enforce
    the wrong body while reporting a pass, which is worse than reporting that nobody could
    check -- the owner's rule is that the superseded pack is never eligible for automatic
    selection, and a silent fallback is exactly automatic selection.
    """
    from brambleloop.visual import freeze

    with tempfile.TemporaryDirectory() as tmp:
        db = _db(body_reference=False)
        _, record = _make(db, Path(tmp))

    assert record["conditioned_on"]["body_reference_image"] == ""
    assert record["floors"]["whole_person_morphology"] == "unverifiable"
    assert record["usable_as_listing_asset"] is False
    paths = freeze.reference_paths(db)
    assert paths["body"] == ""
    assert brief.approved_reference("torso_fit_reference") not in paths.values()


def _sequence(db, tmp: Path, *, slug="winter-cardigan", **kw):
    import dataclasses

    cir, twin = _subject()
    cir = dataclasses.replace(cir, slug=slug, title="Cardigan")
    gen = _Generator(tmp)
    record = mp.sequence(db, cir, twin, generator=gen,
                         observer=kw.pop("observer", _observer()),
                         inspector=kw.pop("inspector", _inspector()),
                         motif_judger=kw.pop("motif_judger", _motif()),
                         realism_judger=kw.pop("realism_judger", _realism()),
                         styling_judger=kw.pop("styling_judger", _styling()), **kw)
    return gen, record


def test_the_sequence_is_two_frames_and_each_floor_is_taken_from_the_one_that_can_see_it():
    """The finding the first correctly-framed live attempt produced.

    A three-quarter frame of a woman in a crocheted hat showed the whole body and the
    motif judge read its fabric as unmeasurable, saying exactly what it needed: a closer
    frame. Pulling in far enough to count stitches loses the hips. The two floors are
    questions about two photographs, so the sequence has two.
    """
    with tempfile.TemporaryDirectory() as tmp:
        gen, record = _sequence(_db(), Path(tmp))

    assert record["shots"] == ["fit", "detail"]
    assert len(gen.calls) == 2
    assert gen.calls[0]["prompt"] != gen.calls[1]["prompt"]
    assert record["floor_sources"]["whole_person_morphology"] == "fit"
    assert record["floor_sources"]["product_truth"] == "detail"
    assert record["floor_sources"]["photographic_realism"] == "every frame"
    assert record["usable_as_listing_asset"] is True


def test_a_detail_frame_that_cannot_see_the_hips_does_not_sink_the_body_floor():
    """The authoritative frame decides what `unverifiable` means.

    Letting any frame's `unmeasurable` drag a floor down makes the body floor unclearable
    again by a different route -- a close crop of a sleeve was never going to answer for
    stature, and treating that as a finding about the woman is the defect inverted.
    """
    def look(db, reference_ref, candidate_ref):
        out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        # The second frame rendered is the detail one, and it shows almost no body.
        if candidate_ref.endswith("frame-1.png"):
            for d in identity.MORPHOLOGY_DIMENSIONS:
                out[d] = identity.UNMEASURABLE
        return out

    with tempfile.TemporaryDirectory() as tmp:
        _, record = _sequence(_db(), Path(tmp), observer=look)

    assert record["floors"]["whole_person_morphology"] == "pass"
    assert record["usable_as_listing_asset"] is True


def test_a_face_that_drifted_in_the_detail_frame_still_blocks():
    """Being the wrong authority is not a licence. That frame ships too."""
    def look(db, reference_ref, candidate_ref):
        out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        if candidate_ref.endswith("frame-1.png"):
            out["face"] = out["eyes"] = out["hair"] = identity.DRIFT
        return out

    with tempfile.TemporaryDirectory() as tmp:
        _, record = _sequence(_db(), Path(tmp), observer=look)

    assert record["floors"]["face_identity"] == "fail"
    assert record["usable_as_listing_asset"] is False


def test_a_shared_floor_takes_the_worst_answer_any_frame_gave():
    """Either frame is a customer-facing asset on its own, so both have to be sound."""
    seen: list[str] = []

    def realism(image_ref, db=None):
        seen.append(image_ref)
        checks = {k: True for k in photoreal.CHECKS}
        if image_ref.endswith("frame-1.png"):
            checks["skin_looks_real"] = False
        return {"judged": True, "checks": checks, "notes": ""}

    with tempfile.TemporaryDirectory() as tmp:
        _, record = _sequence(_db(), Path(tmp), realism_judger=realism)

    assert len(seen) == 2, "a shared floor was only asked of one frame"
    assert record["floors"]["photographic_realism"] == "fail"
    assert record["usable_as_listing_asset"] is False


def test_a_sequence_missing_a_frame_is_not_a_sequence():
    """No reading at all is `unverifiable`, never a pass."""
    assert mp._combine_floors([])["product_truth"] == "unverifiable"
    fit_only = [{"shot": "fit", "floors": {f: "pass" for f in mp.FLOORS}}]
    assert mp._combine_floors(fit_only)["product_truth"] == "unverifiable"
    assert mp._combine_floors(fit_only)["whole_person_morphology"] == "pass"


def test_nothing_in_the_sequence_is_averaged():
    """Five of six floors is not five sixths of a pass."""
    frames = [{"shot": "fit", "floors": {f: "pass" for f in mp.FLOORS}},
              {"shot": "detail", "floors": {**{f: "pass" for f in mp.FLOORS},
                                            "product_truth": "fail"}}]
    floors = mp._combine_floors(frames)
    assert floors["product_truth"] == "fail"
    assert not all(v == "pass" for v in floors.values())


def test_the_shot_plan_and_the_character_bible_ask_for_the_same_light():
    """Two pieces of direction in one prompt disagreed, and the generator obeyed one.

    The shot plan said "evenly lit" to make the body readable while `bible.direction()`,
    in the same prompt, asked for soft directional daylight -- and the bible says why that
    matters beyond taste: flat light removes the shadow that makes crochet texture legible,
    so it is a product-truth failure wearing a styling costume. The first sequence under
    the bible blocked its fit frame on `lighting` and the judge was right about the frame
    and about the instruction. The body needed no deep shadow, not flat light.
    """
    assert "evenly lit" not in mp.SHOT_PLAN
    assert "directional" in mp.SHOT_PLAN and "falloff" in mp.SHOT_PLAN
    # And the bible's own range is still what the prompt carries, unparaphrased.
    cir, twin = _subject()
    prompt = mp.prompt_for(cir, twin, model_registry.canonical_pack(_db()),
                           plan=mp.SHOT_PLAN)
    assert bible.AXES["lighting"]["range"] in prompt


def test_a_close_crop_is_never_asked_whether_the_outfit_is_right():
    """The defect that survived making styling fit-authoritative.

    The detail frame went on being asked the wardrobe questions. First it answered
    `unjudged`, which the gate refused to pass; then on the next render it answered
    *False* -- a crop of a hat reporting that the outfit is wrong. Under "a failure
    anywhere blocks everywhere" that became a false block on the whole sequence, so a
    frame's limitation arrived as a finding about the styling. It is the same defect as
    comparing a body against a portrait, one gate along.
    """
    asked: list[tuple] = []

    def judge(image_ref, db=None, axes=None):
        asked.append(tuple(axes or ()))
        answers = {k: True for k in bible.QUESTIONS
                   if bible.AXIS_OF[k] in (axes or tuple(bible.AXES))}
        return {"judged": True, "answers": answers, "axes": list(axes or []), "notes": ""}

    with tempfile.TemporaryDirectory() as tmp:
        _, record = _sequence(_db(), Path(tmp), styling_judger=judge)

    assert len(asked) == 2
    assert "wardrobe" in asked[0], "the fit frame shows the outfit and must be asked"
    assert "wardrobe" not in asked[1], "a hat crop was asked about the outfit again"
    assert record["floors"]["styling"] == "pass"
    detail = next(f for f in record["frames"] if f["shot"] == "detail")
    assert detail["styling"]["axes"]["wardrobe"]["verdict"] == "not_asked"


def test_a_styling_breach_a_close_crop_can_see_still_blocks():
    """Narrowing what is asked is not narrowing what counts.

    Makeup, expression and lighting are all visible in a crop that includes her face, so
    a breach in any of them blocks the sequence exactly as before.
    """
    def judge(image_ref, db=None, axes=None):
        asked = tuple(axes or tuple(bible.AXES))
        answers = {k: True for k in bible.QUESTIONS if bible.AXIS_OF[k] in asked}
        if image_ref.endswith("frame-1.png"):
            answers["makeup_is_daytime_natural"] = False
        return {"judged": True, "answers": answers, "axes": list(asked), "notes": ""}

    with tempfile.TemporaryDirectory() as tmp:
        _, record = _sequence(_db(), Path(tmp), styling_judger=judge)

    assert record["floors"]["styling"] == "fail"
    assert record["usable_as_listing_asset"] is False


def test_every_frame_in_the_sequence_sees_the_chart():
    """One listing is one fabric, and the frames are independent renders.

    The chart was given to the detail frame only, because product truth is that frame's
    floor. The live v10 sequence showed both halves of why that was wrong: the fit frame's
    fabric is read too and its `mismatch` blocks the sequence, and -- worse -- one frame
    conditioned on the chart and one not produced two different fabrics in a single
    listing. Not being a floor's authority is not the same as not being judged by it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        gen, record = _sequence(_db(), Path(tmp))

    assert len(gen.calls) == 2
    charts = [c["refs"][-1] for c in gen.calls]
    assert all(c.endswith("chart-ref.png") for c in charts), charts
    assert charts[0] == charts[1], "the two frames were shown different charts"


def test_a_frame_that_cleared_its_floors_is_kept_rather_than_rolled_again():
    """The architectural fix for oscillation, and the reason it is not a weakening.

    Generation is stochastic and the floors are independent, so re-rendering the whole
    sequence on any failure asks all six floors to land in a single draw. The live runs
    showed exactly that: v8 passed identity, morphology, asset truth and styling; v10
    passed product truth; no single draw passed everything. Keeping what passed turns
    "all six floors in one attempt" into "each frame passes in some attempt" -- the same
    standard, a fraction of the cost.
    """
    def detail_only_fails(image_ref, db=None):
        """Realism fails on the second frame rendered -- the detail shot -- and not the fit."""
        checks = {k: True for k in photoreal.CHECKS}
        if image_ref.endswith("frame-1.png"):
            checks["skin_looks_real"] = False
        return {"judged": True, "checks": checks, "notes": ""}

    with tempfile.TemporaryDirectory() as tmp:
        db = _db()
        gen, first = _sequence(db, Path(tmp), realism_judger=detail_only_fails)
        assert first["floors"]["photographic_realism"] == "fail"
        fit = next(f for f in first["frames"] if f["shot"] == "fit")
        assert all(v == "pass" for v in fit["floors"].values()), fit["floors"]
        _file(db, first)

        rendered_before = len(gen.calls)
        gen2, second = _sequence(db, Path(tmp))

    # The fit frame was kept; only the detail frame was rendered again.
    assert second["reused_frames"] == ["fit"], second["reused_frames"]
    assert len(gen2.calls) == 1, "the whole sequence was re-rendered"
    assert second["floors"]["photographic_realism"] == "pass"
    assert second["usable_as_listing_asset"] is True
    assert rendered_before == 2


def test_a_frame_with_any_failed_floor_is_never_kept():
    """Even a floor it is not the authority for.

    A fit frame whose fabric read as a mismatch is a bad photograph, and keeping it would
    carry that `fail` into every later sequence under the "a failure anywhere blocks"
    rule -- poisoning the release permanently with a verdict nothing could clear.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db = _db()
        _, first = _sequence(db, Path(tmp), motif_judger=_motif(
            repeating_unit_shape="solid square", repeats_across=8))
        for frame in first["frames"]:
            assert frame["floors"]["product_truth"] == "fail"
        _file(db, first)

        gen2, second = _sequence(db, Path(tmp))

    assert second["reused_frames"] == []
    assert len(gen2.calls) == 2


def test_a_frame_is_kept_only_on_verdicts_that_were_actually_made():
    """`unverifiable` is not a pass here either, or reuse would launder an unmade check."""
    with tempfile.TemporaryDirectory() as tmp:
        db = _db()

        def half_read(image_ref, db=None):
            return {"judged": False, "error": "provider refused", "checks": {}}

        _, first = _sequence(db, Path(tmp), realism_judger=half_read)
        assert first["floors"]["photographic_realism"] == "unverifiable"
        _file(db, first)

        gen2, second = _sequence(db, Path(tmp))

    assert second["reused_frames"] == [], "a frame with an unmade check was kept"
    assert len(gen2.calls) == 2


def test_a_kept_frame_does_not_bill_twice():
    """Cost per usable gallery is the number this exists to move; counting a kept frame's
    original spend again would flatter it."""
    def detail_only_fails(image_ref, db=None):
        checks = {k: True for k in photoreal.CHECKS}
        if image_ref.endswith("frame-1.png"):
            checks["skin_looks_real"] = False
        return {"judged": True, "checks": checks, "notes": ""}

    with tempfile.TemporaryDirectory() as tmp:
        db = _db()
        _, first = _sequence(db, Path(tmp), realism_judger=detail_only_fails)
        _file(db, first)
        assert first["spent_cad"] == 0.08, "two frames rendered, two billed"

        _, second = _sequence(db, Path(tmp))

    assert second["reused_frames"] == ["fit"]
    # Only the newly rendered frame is billed to this pass.
    assert second["spent_cad"] == 0.04

def test_reuse_reads_the_shape_the_real_filing_path_writes():
    """The guard for the defect that made frame reuse green and dead on arrival.

    The three reuse tests above call `_file` and so can only ever prove the reader agrees
    with the test helper. This one files through `listing_asset.make(record=True)` -- the
    real path, the one the handler and the seasonal cycle both go through -- so if the
    written shape and the read shape ever diverge again, this fails instead of passing.
    """
    import dataclasses

    from brambleloop.publish import listing_asset

    def detail_only_fails(image_ref, db=None):
        checks = {k: True for k in photoreal.CHECKS}
        if image_ref.endswith("frame-1.png"):
            checks["skin_looks_real"] = False
        return {"judged": True, "checks": checks, "notes": ""}

    with tempfile.TemporaryDirectory() as tmp:
        db = _db()
        cir, twin = _subject()
        cir = dataclasses.replace(cir, slug="winter-cardigan", title="Cardigan")
        assert listing_asset.needs_the_model(cir), "this test needs the model-bearing path"

        gen = _Generator(Path(tmp))
        first = listing_asset.make(db, cir, twin, generator=gen, observer=_observer(),
                                   inspector=_inspector(), motif_judger=_motif(),
                                   realism_judger=detail_only_fails,
                                   styling_judger=_styling())
        assert first["made"] and first["floors"]["photographic_realism"] == "fail"

        gen2, second = _sequence(db, Path(tmp))

    assert second["reused_frames"] == ["fit"], (
        "the frame the real filing path wrote could not be found by the reader")
    assert len(gen2.calls) == 1
    assert second["usable_as_listing_asset"] is True


def _filed(db, **detail):
    from brambleloop.agents.registry import Registry

    Registry(db).audit("publishing", mp.ACTION, detail={
        "made": True, "method_version": mp.METHOD_VERSION, "slug": "hats-hat-0",
        "version": "0.1.0", "spent_cad": 0.08, **detail})


def test_a_method_whose_floor_never_once_passed_stops_spending_on_the_next_product_too():
    """`ATTEMPTS` bounds one release and does nothing about a method that does not work.

    Live, 2026-09-23: three sequences for `hats-hat-0` blocked on `photographic_realism`,
    against direction that names airbrushed skin explicitly and a judge the calibration
    proved can pass a real photograph. Each new release starts its attempt budget again,
    so without this the next product pays three more times for the same answer. A floor
    that has never once passed is a code change, not a sample.
    """
    db = _db()
    for _ in range(3):
        _filed(db, floors={"face_identity": "pass", "photographic_realism": "fail"})

    move = mp.what_to_do_next(db, slug="winter-cardigan", version="1.0.0")
    assert move["render"] is False
    assert move["reason"] == "method_systematically_blocked"
    assert move["blocked_on"] == ["photographic_realism"]
    assert "a new METHOD_VERSION is what tells this check the method changed" in move["why"]


def test_a_floor_that_merely_has_not_been_asked_does_not_block_anything():
    """"This does not work" and "nobody has checked" are the defect family, not a nuance."""
    db = _db()
    _filed(db, floors={"face_identity": "pass"})
    _filed(db, floors={"face_identity": "pass"})

    move = mp.what_to_do_next(db, slug="winter-cardigan", version="1.0.0")
    assert move["render"] is True
    assert move["reason"] == "no_usable_frame_yet"


def test_a_floor_that_fails_sometimes_is_retried_rather_than_blocked():
    """Stochastic failure is exactly what the attempt budget is for."""
    db = _db()
    _filed(db, floors={"photographic_realism": "fail"})
    _filed(db, floors={"photographic_realism": "pass"})

    move = mp.what_to_do_next(db, slug="winter-cardigan", version="1.0.0")
    assert move["render"] is True


def test_changing_the_method_version_clears_a_systematic_block():
    """The escape, and the only one: a floor nothing can clear must be clearable by work.

    The measurement counts only the current method, so a block is lifted by changing the
    method -- which is a code change somebody has to make and cannot be waited out.
    """
    db = _db()
    from brambleloop.agents.registry import Registry

    for _ in range(3):
        Registry(db).audit("publishing", mp.ACTION, detail={
            "made": True, "method_version": "v11-superseded", "slug": "hats-hat-0",
            "version": "0.1.0", "spent_cad": 0.08,
            "floors": {"photographic_realism": "fail"}})

    move = mp.what_to_do_next(db, slug="hats-hat-0", version="0.1.0")
    assert move["render"] is True, "a superseded method's failures blocked the new one"


def test_both_shot_plans_ask_for_the_hands_two_floors_ask_about():
    """A floor nobody can answer is a floor nobody can clear.

    Live, 2026-09-23: `asset_truth` returned `unjudged` on `hands_and_fingers` and
    `photographic_realism` `unjudged` on `hands_are_right`, in both frames, because her
    hands were in neither. Unmade is not passed here, so both floors could only ever have
    been cleared by the generator including something no plan requested -- the same defect
    as the shot plan saying "evenly lit" while the bible asked for directional light.

    Asking for hands asks for the harder thing. They are the classic generated-image tell,
    so this is a frame that has to be better rather than a floor that has been lowered.
    """
    from brambleloop.visual import gallery, photoreal

    assert "hands_and_fingers" in gallery.REALISM_CHECKS
    assert "hands_are_right" in photoreal.CHECKS
    for shot, plan, _ in mp.SHOTS:
        assert "hand" in plan.lower(), f"{shot} is checked on hands it never asks for"
        assert "finger" in plan.lower(), shot


def _file_reference_verdict(db, *, pack_version, failures):
    from brambleloop.agents.registry import Registry
    from brambleloop.visual import photoreal

    Registry(db).audit("creative_director", photoreal.REFERENCE_ACTION, detail={
        "judged": True, "pack_version": pack_version,
        "inheritable_failures": list(failures),
        "verdict": "pack_is_the_cause" if failures else "pack_is_not_the_cause",
        "what_it_means": "a generator copies the skin it is shown"})


def _pack_version(db):
    from brambleloop.visual import freeze

    return freeze.reference_paths(db).get("pack_version")


def test_a_reference_that_cannot_be_photographed_stops_the_render_before_it_is_paid_for():
    """The stronger answer, and it holds on the first attempt rather than waiting.

    A rate says "this keeps failing"; the reference verdict says why. Live, 2026-09-23:
    the frozen pack's own images fail `skin_looks_real` and `processing_is_restrained`,
    which are exactly the checks a render inherits from them. Every frame made from her is
    unusable before it is rendered, so waiting for three samples to say so is three renders
    of wasted spend.
    """
    db = _db()
    _file_reference_verdict(db, pack_version=_pack_version(db),
                            failures=["processing_is_restrained", "skin_looks_real"])

    move = mp.what_to_do_next(db, slug="winter-cardigan", version="1.0.0")
    assert move["render"] is False
    assert move["reason"] == "reference_cannot_produce_a_photograph"
    assert move["blocked_on"] == ["processing_is_restrained", "skin_looks_real"]
    assert "cannot pass" in move["why"]


def test_a_verdict_about_a_superseded_pack_does_not_block_a_new_identity():
    """A new identity is not answerable for the old one's skin.

    The other direction is worse and the same defect: clearing a new pack on the old one's
    pass would be a gate reading evidence about something else.
    """
    db = _db()
    _file_reference_verdict(db, pack_version="v0-an-earlier-pack",
                            failures=["skin_looks_real"])

    assert mp.what_to_do_next(db, slug="winter-cardigan", version="1.0.0")["render"] is True


def test_no_filed_verdict_is_not_a_finding_about_the_reference():
    """"She cannot be photographed" and "nobody has checked" need opposite responses."""
    db = _db()
    move = mp.what_to_do_next(db, slug="winter-cardigan", version="1.0.0")
    assert move["render"] is True
    assert move["reason"] == "no_usable_frame_yet"


def test_a_reference_that_passes_what_a_render_inherits_does_not_block():
    """The gate has to be able to pass, or it is the defect it was built against."""
    db = _db()
    _file_reference_verdict(db, pack_version=_pack_version(db), failures=[])

    assert mp.what_to_do_next(db, slug="winter-cardigan", version="1.0.0")["render"] is True


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
