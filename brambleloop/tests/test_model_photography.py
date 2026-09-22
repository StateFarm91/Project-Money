"""A listing frame with the canonical model in it (#72, #130, #202).

The path everything waited on: she was approved, frozen and enforced, and nothing built a
frame with her in it. What these tests protect is the difference between a frame that was
*conditioned on* the frozen identity and checked afterwards, and one that merely says it
was -- because a prompt listing her features produces a different woman who matches the
adjectives, and a generator asked whether it complied says yes.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.products.builder import for_slug  # noqa: E402
from brambleloop.publish import model_photography as mp  # noqa: E402
from brambleloop.visual import brief, identity, inspect as inspect_mod  # noqa: E402
from brambleloop.visual import model_registry, photoreal  # noqa: E402


def _db(*, frozen: bool = True) -> Database:
    db = Database("sqlite://")
    db.create_all()
    if frozen:
        model_registry.record_candidate(
            db, "brambleloop-canonical",
            fields={f: f"{f} as described" for f in identity.IDENTITY_FIELDS},
            image_refs=[brief.approved_portrait()])
        model_registry.select_canonical(db, "brambleloop-canonical", owner_approved=True)
    return db


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


def _make(db, tmp: Path, *, slug="winter-cardigan", **kw):
    import dataclasses

    cir, twin = _subject()
    cir = dataclasses.replace(cir, slug=slug, title="Cardigan")
    gen = _Generator(tmp)
    record = mp.make(db, cir, twin, generator=gen,
                     observer=kw.pop("observer", _observer()),
                     inspector=kw.pop("inspector", _inspector()),
                     motif_judger=kw.pop("motif_judger", _motif()),
                     realism_judger=kw.pop("realism_judger", _realism()), **kw)
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
    assert gen.calls[0]["refs"] == [brief.approved_portrait()], gen.calls[0]["refs"]
    assert record["conditioned_on"]["reference_image"] == brief.approved_portrait()
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
    assert "sharply in focus" in prompt
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
    """Put a frame on the audit log the way the handler does."""
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
    """Unbounded retry is how a loop spends the ceiling chasing the same failure."""
    with tempfile.TemporaryDirectory() as tmp:
        db = _db()
        for _ in range(mp.ATTEMPTS):
            _, record = _make(db, Path(tmp),
                              realism_judger=_realism(skin_looks_real=False))
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


def test_the_frame_asks_for_a_body_the_morphology_floor_can_actually_read():
    """A floor nothing can clear is the same defect as one nothing can fail."""
    cir, twin = _subject()
    db = _db()
    prompt = mp.prompt_for(cir, twin, model_registry.canonical_pack(db))
    for part in ("shoulders", "chest", "torso", "waist", "hips"):
        assert part in prompt, part
    # And the fabric large enough for the motif judge to count a repeat in.
    assert "stitches" in prompt and "repeat" in prompt

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
