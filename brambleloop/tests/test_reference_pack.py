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


def _compare(**overrides):
    def comparer(db, reference_ref, candidate_ref):
        out = {d: identity.MATCH for d in identity.DRIFT_DIMENSIONS}
        out.update(overrides)
        return out
    return comparer


def _build(tmp: Path, *, observe=None, compare=None):
    gen = _Generator(tmp)
    package = rp.build(_db(), work_dir=str(tmp), generator=gen,
                       observer=observe or (lambda db, ref: _seen()),
                       comparer=compare or _compare())
    return gen, package


def test_the_reference_is_two_frames_and_the_body_frame_sees_the_body(tmp_path=None):
    """The defect the first pack could not survive: a cropped reference.

    Every tournament finalist was measured against a head-and-shoulders portrait, so
    stature, torso, bust, waist and hips were unmeasurable on the reference itself. A floor
    that can only return `unverifiable` is not a floor.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        gen, package = _build(Path(tmp))

    frames = [f["frame"] for f in package["reference_frames"]]
    assert frames == ["neutral_portrait", "full_length_standing"]

    full_length_prompt = gen.calls[1]["prompt"]
    assert "full-length" in full_length_prompt.lower()
    assert "head to feet" in full_length_prompt.lower()
    for readable in ("stature", "shoulder width", "torso length", "bust", "waist", "hips"):
        assert readable in full_length_prompt.lower(), readable


def test_every_scene_is_conditioned_on_both_reference_frames():
    """An identity lock is reference conditioning, not a better description."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        gen, package = _build(Path(tmp))

    portrait, full_length = gen.calls[0]["image_ref"], gen.calls[1]["image_ref"]
    assert gen.calls[0]["refs"] == [brief.candidate_reference()]
    assert gen.calls[1]["refs"] == [portrait, brief.candidate_reference()]
    for call in gen.calls[2:]:
        assert call["refs"] == [portrait, full_length], call["prompt"][:40]


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
    assert brief.PHYSICAL_DIRECTION["bust"].startswith("moderate and naturally full")
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
