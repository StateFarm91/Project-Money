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


# ---- the product lock, enforced by provenance rather than by inspection ----

def _composite_plan():
    from brambleloop.visual.presentation import PresentationPlan
    return (PresentationPlan()
            .add("generate", touches_product=False, note="scene, room, light, model")
            .add("warp_to_surface", touches_product=True)
            .add("relight", touches_product=True)
            .add("shadow_cast", touches_product=True)
            .add("composite", touches_product=True)
            .add("depth_of_field_blur", touches_product=True)
            .add("grain", touches_product=True))


def test_structure_preserving_operations_may_touch_the_product():
    """Relighting, warping, blurring and compositing move existing pixels.

    None of them has a model of what crochet is, so none can invent a stitch. Fabric that is
    shadowed or blurred becomes harder to read; it does not become different fabric.
    """
    assert _composite_plan().lock_verdict()["verdict"] == "pass"


def test_a_generative_operation_over_the_product_is_a_redesign():
    """The failure mode is a plausible texture that is not the certified one."""
    from brambleloop.visual.presentation import PresentationPlan
    plan = (PresentationPlan()
            .add("generate", touches_product=False)
            .add("image_to_image", touches_product=True, note="make it look photographic"))
    v = plan.lock_verdict()
    assert v["verdict"] == "fail"
    assert "image_to_image" in v["failed_checks"]


def test_every_generative_name_is_refused_over_the_product():
    """Including the ones that do not sound generative: enhance, refine, upscale, restore."""
    from brambleloop.visual.presentation import GENERATIVE, PresentationPlan
    for name in GENERATIVE:
        plan = PresentationPlan().add(name, touches_product=True)
        assert plan.lock_verdict()["verdict"] == "fail", f"{name} was allowed over the product"


def test_generative_work_away_from_the_product_is_allowed_and_is_the_point():
    """The rule is not 'no generative AI'. Scene, pose, light and model may all be generated."""
    from brambleloop.visual.presentation import scene_generation_is_allowed
    plan = _composite_plan()
    assert scene_generation_is_allowed(plan)
    assert plan.lock_verdict()["verdict"] == "pass"


def test_an_unclassified_operation_may_not_touch_the_product():
    """An operation nobody has classified is not assumed safe.

    This is the gap a future technique arrives through: something new, plausibly harmless,
    applied to the product because no rule named it. The default is refusal.
    """
    from brambleloop.visual.presentation import PresentationPlan
    plan = PresentationPlan().add("neural_texture_fixup", touches_product=True)
    v = plan.lock_verdict()
    assert v["verdict"] == "fail"
    assert "neural_texture_fixup" in v["failed_checks"]
    # ...but the same unknown operation elsewhere in the frame is merely reported.
    ok = PresentationPlan().add("composite", touches_product=True)
    ok.add("neural_texture_fixup", touches_product=False)
    assert ok.lock_verdict()["verdict"] == "pass"


def test_an_undeclared_pipeline_is_unmeasurable_rather_than_safe():
    from brambleloop.visual.presentation import PresentationPlan
    assert PresentationPlan().lock_verdict()["verdict"] == "unmeasurable"


def test_the_lock_raises_rather_than_returning_a_soft_answer():
    from brambleloop.visual.presentation import PresentationPlan, ProductRedesigned
    plan = PresentationPlan().add("inpaint", touches_product=True)
    try:
        plan.refuse_if_the_product_is_redesigned()
    except ProductRedesigned as exc:
        assert "redesign" in str(exc)
    else:
        raise AssertionError("a generative redraw of the product passed the lock")
    _composite_plan().refuse_if_the_product_is_redesigned()


def test_the_two_operation_sets_do_not_overlap():
    """An operation that is both preserving and generative would decide by lookup order."""
    from brambleloop.visual.presentation import GENERATIVE, STRUCTURE_PRESERVING
    assert not STRUCTURE_PRESERVING & GENERATIVE


# ---- the second product lock: geometry ------------------------------------

def _certified():
    from brambleloop.cir import assembly, benchmarks as B
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.visual import presentation as P
    c = B.cardigan("S")
    r = compile_cir(c)
    tw = {x.name: build_twin(c, r, component=x.name) for x in c.components}
    return P.certified_ratios(assembly.assemble(c, tw), c.gauge)


def test_authentic_pixels_in_the_wrong_shape_still_fail_product_truth():
    """The gap the provenance lock alone leaves open.

    A cardigan squashed to fit a pose has every certified stitch in it and is not the
    product the customer's pattern makes. Deterministic is not the same as truthful.
    """
    from brambleloop.visual.presentation import geometry_lock_held
    cert = _certified()
    squashed = dict(cert)
    squashed["garment_aspect"] *= 1.20
    v = geometry_lock_held(cert, squashed)
    assert v.verdict == "fail"
    assert "garment_aspect" in v.failed_checks
    assert "deterministic does not make it truthful" in v.why


def test_stretching_the_stitches_fails_even_when_the_garment_fits():
    """Motif aspect is certified geometry: stretch it and every stitch is subtly wrong."""
    from brambleloop.visual.presentation import geometry_lock_held
    cert = _certified()
    stretched = dict(cert)
    stretched["stitch_aspect"] *= 1.15
    assert geometry_lock_held(cert, stretched).verdict == "fail"


def test_uniform_scale_is_free_because_ratios_are_what_is_certified():
    """A photograph may show the garment at any size; it may not change its shape."""
    from brambleloop.visual.presentation import geometry_lock_held
    cert = _certified()
    assert geometry_lock_held(cert, dict(cert)).verdict == "pass"


def test_geometry_that_was_not_measured_is_unmeasurable_not_held():
    """The way this lock would otherwise be defeated: decline to report your own geometry."""
    from brambleloop.visual.presentation import geometry_lock_held
    cert = _certified()
    partial = {k: v for k, v in cert.items() if k != "stitch_aspect"}
    v = geometry_lock_held(cert, partial)
    assert v.verdict == "unmeasurable"
    assert "stitch_aspect" in v.unjudged_checks
    assert geometry_lock_held({}, cert).verdict == "unmeasurable"


def test_the_two_product_locks_are_independent_and_do_not_average():
    """Either failing fails Product Truth. That is why there are two locks, not one score."""
    from brambleloop.visual.presentation import PresentationPlan, both_product_locks
    cert = _certified()
    clean = (PresentationPlan()
             .add("generate", touches_product=False)
             .add("composite", touches_product=True)
             .add("relight", touches_product=True))
    dirty = PresentationPlan().add("inpaint", touches_product=True)
    squashed = dict(cert); squashed["garment_aspect"] *= 1.20

    assert both_product_locks(clean, cert, dict(cert))["product_truth"] == "pass"
    # Pixels authentic, shape wrong.
    assert both_product_locks(clean, cert, squashed)["product_truth"] == "fail"
    # Shape right, pixels invented.
    assert both_product_locks(dirty, cert, dict(cert))["product_truth"] == "fail"


def test_a_certified_object_reports_the_ratios_that_matter():
    cert = _certified()
    for key in ("garment_aspect", "stitch_aspect", "sleeve_to_body", "pocket_to_body"):
        assert key in cert and cert[key] > 0


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
