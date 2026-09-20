"""#3 stage four: a CIR authored from a concept, compiled, and checked against the twin.

The interesting tests are the ones about a CIR that compiles perfectly and describes the
wrong object, because that is what the first draft of this module produced.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.creative import prototype as P  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402


def _concept(form: str, construction: str, key: str = "") -> Concept:
    return Concept(
        key=key or f"k-{form}", title="Test Object",
        premise="a test object carried through the prototype stage of the tournament",
        pod="home_decor", form=form, construction=construction, motif="lantern",
        palette_story="ember and soot", recipient="self", occasion="everyday",
        feeling="cosy", function="warmth", make_lane="SHORT", provenance="test")


def test_the_gauge_is_derived_from_the_yarn_rather_than_typed():
    """The defect this closes is in the shipped catalogue: worsted declared at 16 sts/10cm.

    The published band for medium yarn is 11 to 14, so those patterns state a fabric their
    own yarn cannot make. Deriving the gauge from the declared weight's band means nothing
    this system authors can repeat it.
    """
    from brambleloop.publish.substitution import WEIGHT_BY_KEY, holds_gauge

    gauge = P.gauge_for("worsted")
    assert holds_gauge(WEIGHT_BY_KEY["medium"], gauge.stitches_per_10cm), gauge
    assert gauge.yarn_weight == "medium"

    # And every weight this module can be asked for lands inside its own band.
    for key, weight in WEIGHT_BY_KEY.items():
        assert holds_gauge(weight, P.gauge_for(key).stitches_per_10cm), key

    raised = None
    try:
        P.gauge_for("artisanal vibes")
    except P.PrototypeRefused as e:
        raised = e
    assert raised is not None
    assert "cannot make" in str(raised)


def test_the_finished_size_is_the_input_and_the_stitch_count_is_derived():
    """The other direction is how a "blanket" ends up 100cm wide and 17cm tall.

    Somebody picks round numbers of stitches and rows and nobody converts them back into an
    object. Stating the object and computing the counts cannot produce that.
    """
    for form in ("rectangle_throw", "scarf", "hat", "stocking"):
        geometry = P.FORM_GEOMETRY[form]
        construction = "in_the_round" if geometry.closed else "flat_rows"
        cir = P.author(_concept(form, construction))
        result = compile_cir(cir)
        assert result.ok, [str(f) for f in result.errors][:3]
        twin = build_twin(cir, result)
        width = (twin.circumference_cm if geometry.closed and twin.circumference_cm
                 else twin.width_cm)
        assert abs(width - geometry.width_cm) / geometry.width_cm <= P.SIZE_TOLERANCE, (
            form, width, geometry.width_cm)
        assert abs(twin.height_cm - geometry.height_cm) / geometry.height_cm <= P.SIZE_TOLERANCE


def test_a_compiling_cir_that_describes_the_wrong_object_is_refused():
    """The bug this module shipped in its first draft, kept as a gate.

    It alternated single and double crochet rows under a gauge stated in single crochet. It
    compiled perfectly and built a "150cm throw" the twin measured at 225cm. A CIR that
    compiles and describes the wrong object is precisely what the twin exists to catch, so
    the stage asks it rather than trusting the compile.
    """
    # Every prototype is worked in one stitch, which is what makes the declared gauge
    # describe the fabric. If that ever stops being true this assertion is the alarm.
    assert P.PROTOTYPE_REPEAT == (("sc", 4),), P.PROTOTYPE_REPEAT

    geometry = P.FORM_GEOMETRY["rectangle_throw"]
    drift = P._drift(geometry, geometry.width_cm, geometry.height_cm * 1.5)
    assert drift["height"] > P.SIZE_TOLERANCE, drift


def test_a_form_with_no_finished_size_is_refused_rather_than_guessed():
    """A guessed dimension compiles perfectly and describes an object nobody designed.

    The refusal is the engineering backlog, with the reason attached: a graded garment is a
    size chart rather than a finished size, and the grading that decides where the armhole
    division goes does not exist yet.
    """
    raised = None
    try:
        P.author(_concept("fitted_garment", "top_down_yoke"))
    except P.PrototypeRefused as e:
        raised = e
    assert raised is not None
    assert "no finished size on file" in str(raised)
    assert "size chart" in str(raised)

    # Named rather than absent: a missing key and an unsized form are different things.
    assert "fitted_garment" in P.NO_GEOMETRY_YET
    for form, why in P.NO_GEOMETRY_YET.items():
        assert form not in P.FORM_GEOMETRY, form
        assert why.strip(), form


def test_a_construction_with_no_engine_route_is_a_named_gap_not_a_bad_concept():
    from brambleloop.creative.prospecting import ENGINE_ROUTE

    unrouted = [k for k, v in ENGINE_ROUTE.items() if v is None]
    if not unrouted:
        return
    raised = None
    try:
        P.author(_concept("rectangle_throw", unrouted[0]))
    except P.PrototypeRefused as e:
        raised = e
    assert raised is not None
    assert "named engine gap" in str(raised)


def test_the_stage_cuts_what_cannot_be_built_and_carries_what_can():
    out = P.prototype([
        _concept("rectangle_throw", "flat_rows"),
        _concept("hat", "in_the_round"),
        _concept("fitted_garment", "top_down_yoke"),
    ])
    kept = {c.key for c in out["survivors"]}
    assert kept == {"k-rectangle_throw", "k-hat"}, kept
    assert out["killed"] == {"k-fitted_garment": "unverifiable"}
    # Every survivor carries what the twin measured, so the listing's claims have a source.
    for key in kept:
        assert out["detail"][key]["measured_cm"], out["detail"][key]
        assert out["detail"][key]["yarn_metres"], out["detail"][key]


def test_no_model_is_consulted_about_what_the_pattern_says():
    """Section 2: a model may never generate canonical pattern content.

    The whole stage is a lookup table and arithmetic, and this asserts it stays that way --
    a gateway reaching into this module would be the rule broken quietly.
    """
    source = (Path(__file__).resolve().parents[1]
              / "src/brambleloop/creative/prototype.py").read_text()
    for forbidden in ("gateway", "complete_json", "ModelGateway", "prompt"):
        assert forbidden not in source, forbidden


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
