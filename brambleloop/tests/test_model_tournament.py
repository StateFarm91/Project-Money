"""The canonical-model tournament, and the thing it is built to make impossible.

The owner's instruction is the whole design: do not generate one woman and make her canonical
because she happened to be first. So the property worth testing hardest is negative -- that
nothing in the tournament selects, that the field is genuinely a field rather than one woman
twenty-four times, and that a finalist who holds her face and loses her body fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import brief, identity, tournament  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _render(prompt, *, env=None, size=None, reference_urls=None, **kw):
    _render.n = getattr(_render, "n", 0) + 1
    return {"provider": "gpt-image-2", "image_ref": f"/tmp/img-{_render.n}.png",
            "url": "", "cad": 0.0411, "latency_ms": 12.0}


def _screen(_db, ref, score: int = 4, celebrity: bool = False) -> str:
    return json.dumps({**{k: score for k in brief.SCREEN_ON},
                       "reads_as_public_figure": celebrity, "notes": {}})


# ---------------------------------------------------------------------------
# Nothing selects


def test_no_function_in_the_tournament_selects_a_canonical_model():
    """The property the owner asked for, asserted over the module rather than argued."""
    source = (ROOT / "src/brambleloop/visual/tournament.py").read_text()
    assert "select_canonical" not in source
    assert "owner_approved" not in source
    assert tournament.present(None, [])["decision"] == "owner"


def test_the_handler_presents_and_queues_the_owner_rather_than_choosing():
    source = (ROOT / "src/brambleloop/runtime/release.py").read_text()
    block = source[source.index('@handlers.register("creative.model_tournament")'):]
    block = block[:block.index("def _brief_fingerprint")]
    assert "select_canonical" not in block
    assert "canonical_model_selection" in block          # it opens an owner action
    assert '"selected": None' in block


def test_a_reference_photograph_of_a_real_person_is_refused():
    """The one moment that rule breaks is when somebody has a picture and a deadline."""
    try:
        tournament.plan(None, reference_image="/root/uploads/someone.jpg")
    except tournament.TournamentRefused as exc:
        assert "likeness in commercial use" in str(exc)
        assert "celebrity resemblance" in str(exc)
        return
    raise AssertionError("the tournament accepted a real person's photograph as a reference")


# ---------------------------------------------------------------------------
# A field, not a family


def test_the_seed_notes_vary_within_the_direction_rather_than_across_it():
    """The owner narrowed the physical direction on 2026-09-21: this type, not her.

    The first field varied everything -- hair colour, complexion, stature, figure -- which
    was right while the direction was open and wrong once it was not. A spread that ignores
    the brief is not the choice the owner asked to make; a field of one woman repeated is
    not a choice at all. These vary the things that still distinguish one woman from another
    inside the type.
    """
    assert len(tournament.SEED_NOTES) >= brief.TARGET_CANDIDATES[0]
    assert len(set(tournament.SEED_NOTES)) == len(tournament.SEED_NOTES)

    joined = " ".join(tournament.SEED_NOTES).lower()
    # Nothing outside the direction: the type is dark-haired and light-eyed.
    for outside in ("blonde", "auburn", "platinum", "ginger", "copper-red", "grey hair",
                    "brown eyes", "dark brown eyes"):
        assert outside not in joined, outside

    # And it still varies, on the axes that separate two women of one type.
    for note in tournament.SEED_NOTES:
        low = note.lower()
        assert "hair" in low and "eyes" in low, note
        assert any(w in low for w in ("tall", "average height", "petite")), note
    assert len({n.split(".")[0] for n in tournament.SEED_NOTES}) >= 20


def test_the_physical_direction_is_recorded_as_a_type_not_a_person():
    """It was given by pointing at a photograph and saying "not exactly her".

    Every attribute stored is a generic description thousands of people match. The
    photograph is not used, and the rule against a recognisable public figure matters more
    here than before: aiming at a type a celebrity exemplifies is exactly the circumstance
    in which a generator drifts towards the celebrity.
    """
    direction = brief.PHYSICAL_DIRECTION
    for key in ("hair", "eyes", "face", "build", "bust", "waist" if "waist" in direction
                else "torso", "hips", "limbs"):
        assert direction.get(key), key
    assert "not a person" in brief.PHYSICAL_DIRECTION_IS_A_TYPE
    assert "excluded on the rule" in brief.PHYSICAL_DIRECTION_IS_A_TYPE

    prompt = brief.base_prompt()
    assert "blue-green" in prompt and "lean and athletic" in prompt
    # The register stays the brief's, not the photograph's.
    assert "no heavy glamour makeup" in prompt
    assert "naturally beautiful rather than model-perfect" in prompt
    assert "not resembling any known public figure" in prompt


def test_every_candidate_is_generated_from_the_one_brief():
    """Twenty differently-worded briefs would be comparing the prompts."""
    seen = set()
    for note in tournament.SEED_NOTES[:5]:
        prompt = brief.base_prompt(note)
        assert prompt.startswith(brief.base_prompt()[:80])
        seen.add(prompt)
    assert len(seen) == 5


def test_a_candidate_reading_as_a_public_figure_is_excluded_on_the_rule():
    db = _db()
    out = tournament.generate_candidates(
        db, count=6, generator=_render,
        judge=lambda _d, ref: _screen(_d, ref, celebrity=ref.endswith("2.png")))
    assert out["ran"] is True
    assert len(out["excluded"]) == 1
    assert "public figure" in out["excluded"][0]["why"]
    assert all(not c["reads_as_public_figure"] for c in out["candidates"])


def test_a_partial_screen_is_refused_rather_than_averaged():
    partial = json.dumps({brief.SCREEN_ON[0]: 4, "reads_as_public_figure": False})
    try:
        tournament.parse_screen(partial)
    except tournament.TournamentRefused as exc:
        assert "were not scored" in str(exc)
        return
    raise AssertionError("a screen that scored one criterion was accepted")


# ---------------------------------------------------------------------------
# The stress test


def _reference_observation() -> dict:
    """Per-dimension verdicts, which is what a judge shown both photographs returns.

    It used to be two free-text descriptions matched as strings. Against real observations
    that reported every dimension of every scene of every finalist as drift, because two
    honest descriptions of one woman are never identical text.
    """
    return {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}


def test_a_finalist_who_keeps_her_face_and_loses_her_body_fails():
    """The failure the owner caught: the face came back convincingly the same woman while
    the chest and upper-torso morphology changed substantially."""
    db = _db()
    finalist = {"key": "cand-00", "image_ref": "/tmp/ref.png", "provider": "gpt-image-2"}

    def observer(_d, reference, ref):
        if ref == "/tmp/ref.png":
            return _reference_observation()
        return {**_reference_observation(), "bust": identity.DRIFT,
                "waist": identity.DRIFT}

    out = tournament.stress_test(db, finalist, generator=_render, observer=observer,
                                 reference_observer=lambda _d, ref: {
                                     d: "described" for d in identity.DRIFT_DIMENSIONS})
    assert out["usable"] is True
    assert out["face_floor"] == "pass"
    assert out["morphology_floor"] == "fail"
    assert out["clears_both_floors"] is False


def test_a_hidden_waist_is_unverifiable_rather_than_a_failed_finalist():
    """Treating `unverifiable` as `fail` disqualified every finalist on a loose sweater.

    A woman who is perfectly consistent wherever she can be seen was reported as drifted.
    The owner's rule is that an obscured proportion never passes; it does not say it fails.
    Not chosen, not condemned, and short of the evidence a permanent identity deserves.
    """
    db = _db()
    finalist = {"key": "cand-00", "image_ref": "/tmp/ref.png", "provider": "gpt-image-2"}
    seen: list[str] = []

    def render(prompt, *, env=None, size=None, reference_urls=None, **kw):
        seen.append(prompt)
        return {"provider": "gpt-image-2", "image_ref": f"/tmp/scene-{len(seen)}.png",
                "url": "", "cad": 0.04, "latency_ms": 1.0}

    def observer(_d, reference, ref):
        base = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        if ref == "/tmp/scene-2.png":        # one scene hides the body
            base.update({d: identity.UNMEASURABLE for d in identity.MORPHOLOGY_DIMENSIONS})
        return base

    out = tournament.stress_test(
        db, finalist, generator=render, observer=observer,
        reference_observer=lambda _d, ref: {d: "described"
                                            for d in identity.DRIFT_DIMENSIONS})
    assert out["face_floor"] == "pass"
    assert out["morphology_floor"] == "unverifiable"     # not "fail"
    assert out["clears_both_floors"] is False            # and still not chosen
    assert out["morphology_readable_scenes"], out
    assert out["morphology_drifted_scenes"] == []


def test_real_drift_still_fails_rather_than_reading_as_unverifiable():
    db = _db()
    finalist = {"key": "cand-00", "image_ref": "/tmp/ref.png", "provider": "gpt-image-2"}
    out = tournament.stress_test(
        db, finalist, generator=_render,
        observer=lambda _d, a, b: {**{d: identity.MATCH
                                      for d in identity.DRIFT_DIMENSIONS},
                                   "hips": identity.DRIFT},
        reference_observer=lambda _d, ref: {d: "described"
                                            for d in identity.DRIFT_DIMENSIONS})
    assert out["morphology_floor"] == "fail"
    assert out["morphology_drifted_scenes"]


def test_a_finalist_who_holds_the_whole_person_clears_both_floors():
    db = _db()
    finalist = {"key": "cand-00", "image_ref": "/tmp/ref.png", "provider": "gpt-image-2"}
    out = tournament.stress_test(db, finalist, generator=_render,
                                 observer=lambda _d, a, b: _reference_observation(),
                                 reference_observer=lambda _d, ref: {
                                     d: "described" for d in identity.DRIFT_DIMENSIONS})
    assert out["clears_both_floors"] is True
    assert out["complete"] is True
    assert out["scenes_rendered"] == len(brief.STRESS_SCENES) - 1


def test_every_scene_is_conditioned_on_the_finalists_own_reference():
    """A finalist is being tested on whether she can *be* a canonical identity, which means
    the same reference-conditioning mechanism the canonical identity will use."""
    db = _db()
    conditioned: list[list] = []

    def render(prompt, *, env=None, size=None, reference_urls=None, **kw):
        conditioned.append(list(reference_urls or []))
        return {"provider": "gpt-image-2", "image_ref": "/tmp/scene.png", "url": "",
                "cad": 0.04, "latency_ms": 1.0}

    tournament.stress_test(db, {"key": "c", "image_ref": "/tmp/ref.png"},
                           generator=render,
                           observer=lambda _d, a, b: _reference_observation(),
                           reference_observer=lambda _d, ref: {
                               d: "described" for d in identity.DRIFT_DIMENSIONS})
    assert conditioned, "no scene was rendered"
    assert all(refs == ["/tmp/ref.png"] for refs in conditioned)


def test_an_unreadable_reference_portrait_is_unusable_rather_than_assumed():
    db = _db()
    out = tournament.stress_test(db, {"key": "c", "image_ref": "/tmp/ref.png"},
                                 generator=_render,
                                 reference_observer=lambda _d, ref: {
                                     "error": "nothing legible"},
                                 observer=lambda _d, a, b: _reference_observation())
    assert out["usable"] is False


def test_the_scenes_are_materially_different_and_include_a_loose_garment():
    """Five flattering portraits prove only that the generator can repeat a portrait, and a
    loose garment is where morphology becomes unmeasurable rather than matching."""
    keys = [k for k, _ in brief.STRESS_SCENES]
    assert "loose_layered_garment" in keys and "fitted_garment" in keys
    prompts = {k: v for k, v in brief.STRESS_SCENES}
    assert "loose" in prompts["loose_layered_garment"].lower()
    assert "fit" in prompts["fitted_garment"].lower()


def test_the_plan_spends_against_the_monthly_ceiling_not_the_benchmark_authorization():
    """CA$50 measured providers. This measures faces, and saying so keeps two budgets from
    quietly becoming one."""
    plan = tournament.plan(None)
    assert "CA$100 monthly" in plan["spends_against"]
    assert "CA$50" in plan["spends_against"]


def test_a_finalist_package_can_actually_be_looked_at():
    """Renders land in a container's /tmp, which is replaced on every deploy.

    A finalist package pointing at those paths is a package nobody can open -- the same
    defect as the presigned link that expired, one layer up -- and the owner's instruction
    was to *present* the finalists with their comparison sets.
    """
    import tempfile
    from pathlib import Path as P

    from brambleloop.core.artifacts import ArtifactStore

    tmp = P(tempfile.mkdtemp()) / "render.png"
    tmp.write_bytes(b"\x89PNG\r\n\x1a\n" + b"portrait-bytes")

    kept = tournament._keep(str(tmp))
    assert len(kept["sha256"]) == 64
    assert kept["url"] == f"/api/model-tournament/image/{kept['sha256']}"
    # And the bytes come back.
    assert ArtifactStore().get(kept["sha256"]) == tmp.read_bytes()

    # A render that is already gone says so rather than producing a broken reference.
    assert tournament._keep("/tmp/definitely-not-here.png") == {
        "missing": "/tmp/definitely-not-here.png"}
    assert tournament._keep("") == {}


def test_the_image_route_is_digest_addressed_and_cannot_be_browsed():
    source = (ROOT / "src/brambleloop/app/main.py").read_text()
    block = source[source.index('def api_model_tournament_image'):]
    block = block[:block.index("@app.get(\"/api/model-tournament\")")]
    assert "len(sha256) != 64" in block          # a digest, not a path
    assert "ArtifactMissing" in block            # the bytes may be gone; say so


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
