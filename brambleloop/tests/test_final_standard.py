"""The listing-image standard. These tests exist to stop it being eroded later.

Every assertion here is a rule the owner set on 2026-09-24, and each is the kind that gets
relaxed by a future session holding a nearly-good-enough result. Written before the
photographic bridge exists, so none of them was shaped by what that bridge can do.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.visual import final_standard as F


def _floor(name, *, failed=(), unjudged=(), asked=("check",)):
    return F.judge_floor(name, failed=failed, unjudged=unjudged, asked=asked)


def _verdict(product="pass", identity_face="pass", identity_body="pass", realism="pass"):
    v = F.AssetVerdict(asset_ref="candidate")
    def mk(name, state):
        if state == "pass":
            return _floor(name)
        if state == "fail":
            return _floor(name, failed=("x",), asked=("x",))
        return _floor(name, unjudged=("x",), asked=("x",))
    v.floors[F.PRODUCT_TRUTH] = mk(F.PRODUCT_TRUTH, product)
    v.floors[F.MODEL_IDENTITY] = mk(F.MODEL_IDENTITY, "pass")
    v.floors[F.PHOTOGRAPHIC_REALISM] = mk(F.PHOTOGRAPHIC_REALISM, realism)
    v.identity_halves[F.IDENTITY_FACE] = mk("face", identity_face)
    v.identity_halves[F.IDENTITY_MORPHOLOGY] = mk("morphology", identity_body)
    if identity_face != "pass" or identity_body != "pass":
        v.floors[F.MODEL_IDENTITY] = mk(F.MODEL_IDENTITY, "fail")
    return v


def test_all_three_floors_must_pass_and_none_compensates():
    assert _verdict().ships
    for kwargs in ({"product": "fail"}, {"realism": "fail"},
                   {"identity_face": "fail"}, {"identity_body": "fail"}):
        assert not _verdict(**kwargs).ships, f"{kwargs} was allowed to ship"


def test_a_beautiful_photograph_of_the_wrong_garment_fails():
    """The one the deterministic pipeline exists to prevent."""
    v = _verdict(product="fail")
    assert not v.ships
    assert F.PRODUCT_TRUTH in v.blocked_by


def test_a_truthful_garment_on_a_different_woman_fails():
    """Identity is not paid for by the product being right."""
    assert not _verdict(identity_face="fail").ships
    assert not _verdict(identity_body="fail").ships


def test_face_and_morphology_are_separate_floors():
    """A matching face on a different body fails, and the reverse fails too.

    Scored together, a convincing face would carry a wrong body over the line -- which is
    exactly how a generative model's failure mode (a plausible, subtly different person)
    gets through.
    """
    assert not _verdict(identity_face="pass", identity_body="fail").ships
    assert not _verdict(identity_face="fail", identity_body="pass").ships
    assert set(F.IDENTITY_HALVES) == {"face", "morphology"}


def test_unmeasurable_is_never_pass():
    for kwargs in ({"product": "unmeasurable"}, {"realism": "unmeasurable"},
                   {"identity_face": "unmeasurable"}, {"identity_body": "unmeasurable"}):
        assert not _verdict(**kwargs).ships, f"{kwargs} shipped on an unmeasured floor"


def test_a_floor_nobody_asked_is_unmeasurable_rather_than_clear():
    r = F.judge_floor(F.PHOTOGRAPHIC_REALISM, failed=(), unjudged=(), asked=())
    assert r.verdict == F.UNMEASURABLE and not r.clears


def test_a_known_failure_is_not_excused_by_an_unknown():
    """Fail outranks unmeasurable: a defect you found is not softened by one you did not."""
    r = F.judge_floor(F.PHOTOGRAPHIC_REALISM, failed=("plastic_skin",),
                      unjudged=("depth_of_field_is_believable",),
                      asked=("plastic_skin", "depth_of_field_is_believable"))
    assert r.verdict == F.FAIL


def test_a_missing_floor_cannot_ship_by_omission():
    """Leaving a floor out must not be easier than failing it."""
    v = _verdict()
    del v.floors[F.PHOTOGRAPHIC_REALISM]
    assert not v.ships
    assert any("never evaluated" in b for b in v.blocked_by)
    v2 = _verdict()
    del v2.identity_halves[F.IDENTITY_MORPHOLOGY]
    assert not v2.ships


def test_the_gate_raises_rather_than_returning_a_soft_answer():
    """A publish path must not be able to ignore a returned boolean."""
    try:
        F.refuse_unless_it_ships(_verdict(realism="fail"))
    except F.StandardViolation as exc:
        assert "photographic_realism" in str(exc)
    else:
        raise AssertionError("a failing asset passed the gate")
    F.refuse_unless_it_ships(_verdict())          # a clean one must not raise


def test_the_product_lock_names_what_the_presentation_stage_changed():
    before = {"stitch_total": 8556, "surface": "checkered", "width_cm": 64.8}
    same = F.product_lock_held(before, dict(before))
    assert same.verdict == F.PASS
    drifted = F.product_lock_held(before, {**before, "surface": "ridges_along_the_rows"})
    assert drifted.verdict == F.FAIL
    assert "surface" in drifted.failed_checks
    assert "looks better and shows a different garment" in drifted.why


def test_an_unmeasured_product_lock_is_unmeasurable_not_held():
    assert F.product_lock_held({}, {"a": 1}).verdict == F.UNMEASURABLE
    assert F.product_lock_held({"a": 1}, {}).verdict == F.UNMEASURABLE


def test_the_realism_checklist_states_requirements_and_disqualifiers():
    """Absence of a defect is not presence of realism, so both lists must exist."""
    assert "skin_has_texture_and_pores" in F.REALISM_REQUIRES
    assert "hands_and_fingers_are_anatomically_correct" in F.REALISM_REQUIRES
    assert "crochet_drape_is_physically_plausible" in F.REALISM_REQUIRES
    assert "plastic_skin" in F.REALISM_REJECTS
    assert "catalogue_perfect_sterility" in F.REALISM_REJECTS
    assert not set(F.REALISM_REQUIRES) & set(F.REALISM_REJECTS)


def test_morphology_covers_the_whole_person_not_just_a_portrait():
    """A head-and-shoulders check can never clear the body floor.

    This is why the canonical portrait repair could hold identity and still say nothing
    about morphology: a portrait has no hips in it.
    """
    for dim in ("stature", "shoulders", "torso", "bust", "waist", "hips", "limbs"):
        assert dim in F.MORPHOLOGY_DIMENSIONS


def test_the_standard_records_when_it_was_set():
    assert F.STANDARD_SET_AT == "2026-09-24"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("OK  ", name)
            except Exception as e:
                fails += 1; print("FAIL", name, repr(e)); traceback.print_exc()
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
