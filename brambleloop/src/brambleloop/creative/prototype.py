"""Authoring a machine-checkable CIR from a concept, so the tournament can reach stage four.

Requirement 3's prototype stage: *run through the deterministic compiler and the digital
twin*. Until now the tournament named it as a stage it could not run, which was true -- there
was no route from a concept, which says what an object is, to a CIR, which says how many
stitches it is.

This is that route, and it is a lookup table rather than a model call, for the reason section
2 gives: a model may never generate canonical pattern content. What a concept supplies is the
form, the construction and the palette. What this supplies is the geometry -- a finished size
per form, in centimetres, from which the stitch and row counts are *computed*.

Three rules make the output honest rather than plausible.

**The finished size is the input and the stitch count is derived.** The other direction is how
a "blanket" ends up 100cm wide and 17cm tall: somebody picks round numbers of stitches and
rows, and nobody converts them back into an object. Stating the object and computing the
counts cannot produce that.

**The gauge is derived from the yarn the pattern declares.** `publish/substitution` holds the
published band for each standard weight, and this picks the middle of the declared weight's
band. The existing eleven products declare worsted at 16 stitches per 10cm when the published
band for medium yarn is 11 to 14 -- a gauge its own yarn cannot hold. Deriving it means
nothing this system authors can repeat that.

**A form with no geometry is refused, not approximated.** A concept for a form nobody has
given a finished size is a concept this company cannot yet build, and that is an engineering
item with a name. Guessing dimensions would produce a CIR that compiles and describes an
object nobody designed.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row
from .concept import Concept

# The yarn every authored prototype declares until a design says otherwise. Worsted acrylic
# is what the catalogue is made of and what the benchmark's department sells.
DEFAULT_YARN = "worsted acrylic"
DEFAULT_WEIGHT = "worsted"

# Row gauge relative to stitch gauge for single crochet. Rows are slightly shorter than
# stitches are wide in sc; 1.1 is the working ratio and it is stated rather than buried so a
# measured swatch can replace it.
SC_ROW_RATIO = 1.1

# How far the twin's measurement may sit from the finished size the geometry asked for
# before the prototype is refused. Rounding a width up to a whole repeat moves it, and a
# small object moves proportionally more -- an 11cm coaster lands at 12.8cm. What this is
# actually guarding against is the defect that produced it: the first draft of this module
# alternated sc and dc rows under a gauge stated in sc, compiled perfectly, and built a
# "150cm throw" the twin measured at 225cm. A CIR that compiles and describes the wrong
# object is exactly what the twin exists to catch, so it is asked.
SIZE_TOLERANCE = 0.20


class PrototypeRefused(ValueError):
    """A concept whose form this company has no geometry for, or whose CIR cannot be built."""


@dataclass(frozen=True)
class Geometry:
    """One form's finished size, and how it is worked.

    `width_cm` is the flat width for a flat form and the circumference for a closed one --
    the same number a maker measures, which is why it is one field rather than two that have
    to agree.
    """

    form: str
    width_cm: float
    height_cm: float
    closed: bool
    what: str


# Finished sizes a maker would recognise, in centimetres. Sourced from what the object is for
# rather than from what is convenient to work: a throw is sofa-sized, a baby blanket is
# pram-sized, an ornament fits in a hand.
FORM_GEOMETRY: dict[str, Geometry] = {
    "rectangle_throw": Geometry("rectangle_throw", 120.0, 150.0, False, "a sofa throw"),
    "flat_panel": Geometry("flat_panel", 22.0, 22.0, False, "a dishcloth or potholder"),
    "runner": Geometry("runner", 35.0, 120.0, False, "a table runner"),
    "scarf": Geometry("scarf", 22.0, 160.0, False, "a wrapped scarf"),
    "pillow": Geometry("pillow", 45.0, 45.0, False, "a cushion front"),
    "wall_hanging": Geometry("wall_hanging", 40.0, 60.0, False, "a hung panel"),
    "coaster": Geometry("coaster", 11.0, 11.0, False, "a coaster"),
    "round_disc": Geometry("round_disc", 24.0, 24.0, False, "a round mat"),
    "hat": Geometry("hat", 52.0, 22.0, True, "an adult hat, worked in the round"),
    "tube": Geometry("tube", 24.0, 20.0, True, "a cosy or sleeve"),
    "basket": Geometry("basket", 60.0, 18.0, True, "a storage basket"),
    "bag": Geometry("bag", 70.0, 35.0, True, "a tote"),
    "pouch": Geometry("pouch", 36.0, 20.0, True, "a small pouch"),
    "stocking": Geometry("stocking", 40.0, 45.0, True, "a Christmas stocking"),
    "ornament": Geometry("ornament", 18.0, 9.0, True, "a hanging ornament"),
    "sphere": Geometry("sphere", 30.0, 30.0, True, "a stuffed ball or pouf top"),
}

# Forms the tournament can produce that have no geometry yet. Named rather than absent,
# because an absent key and a form nobody has sized look identical to a caller and mean
# completely different things -- one is a bug, the other is the engineering backlog.
NO_GEOMETRY_YET: dict[str, str] = {
    "fitted_garment": ("a graded garment is a size chart, not a finished size: the armhole "
                       "division exists but the bust/length grading that decides where it "
                       "goes does not"),
    "draped_garment": ("a shawl's finished size depends on its shaping, and the shaping is "
                       "the design rather than a dimension"),
    "toy": "a sculptural piece is a sequence of shaped rounds, not a rectangle with a size",
    "cone": "a cone is defined by its rate of increase, which is a design decision",
    "garland": "a garland is a repeat count and a spacing, not a panel",
    "wreath": "a wreath is built on a form whose diameter is the design",
}


def gauge_for(weight: str = DEFAULT_WEIGHT) -> Gauge:
    """A gauge the declared yarn can actually hold, taken from its published band.

    The middle of the band rather than an end of it, so a maker swatching either loosely or
    tightly is inside the range rather than outside it on one side.
    """
    from ..publish.substitution import WEIGHT_BY_KEY, normalise

    key = normalise(weight)
    if not key:
        raise PrototypeRefused(
            f"{weight!r} is not a standard yarn weight, so there is no published gauge band "
            f"to place this pattern in. A gauge typed rather than derived is how a pattern "
            f"ends up declaring a fabric its own yarn cannot make")
    low, high = WEIGHT_BY_KEY[key].sc_per_10cm
    stitches = round((low + high) / 2.0, 1)
    return Gauge(stitches_per_10cm=stitches,
                 rows_per_10cm=round(stitches * SC_ROW_RATIO, 1),
                 stitch_type="sc", hook_mm=5.0, yarn_weight=key)


def geometry_for(form: str) -> Geometry:
    geometry = FORM_GEOMETRY.get(form)
    if geometry is not None:
        return geometry
    why = NO_GEOMETRY_YET.get(form)
    raise PrototypeRefused(
        f"{form!r} has no finished size on file, so it cannot be prototyped: "
        + (why or "nobody has given this form a size, which is an engineering item rather "
                  "than a concept failure"))


# Every prototype is worked in single crochet throughout, and that is a correctness
# requirement rather than a simplification. The gauge is stated in sc, and a fabric that
# alternates sc and dc rows is taller per row than the sc gauge describes -- the first draft
# of this module mixed them and produced a "150cm throw" the twin measured at 225cm. A
# declared gauge that does not describe the fabric is the same defect as a declared yarn that
# cannot hold the gauge, one level down.
#
# It is also honest about what this stage is. The prototype gate asks whether an object of
# this size in this construction compiles and measures correctly. It is not the finished
# design, and a decorative repeat invented here would be pattern content that no designer
# wrote and no model was allowed to.
PROTOTYPE_REPEAT: tuple[tuple[str, int], ...] = (("sc", 4),)


def author(concept: Concept, *, version: str = "0.1.0",
           yarn_weight: str = DEFAULT_WEIGHT) -> CIR:
    """Build a compilable CIR for one concept, or refuse and say why.

    The stitch and row counts are computed from the finished size and the gauge, then the
    width is rounded *up* to a whole number of repeats. Rounding up rather than to nearest
    means the object is never smaller than the size it states, which is the direction a buyer
    forgives.
    """
    from .prospecting import ENGINE_ROUTE

    geometry = geometry_for(concept.form)
    gauge = gauge_for(yarn_weight)
    construction = ENGINE_ROUTE.get(concept.construction)
    if construction is None:
        raise PrototypeRefused(
            f"{concept.construction!r} has no route into the CIR's three constructions yet, "
            f"so a pattern in it cannot be checked. That is a named engine gap, not a "
            f"failure of the concept")

    repeat = list(PROTOTYPE_REPEAT)
    unit = sum(n for _, n in repeat)
    raw_stitches = geometry.width_cm / 10.0 * gauge.stitches_per_10cm
    stitches = int(-(-raw_stitches // unit) * unit)      # ceil to a whole repeat
    rows_count = max(2, round(geometry.height_cm / 10.0 * gauge.rows_per_10cm))

    palette = {"main": "#244A3A", "accent": "#FAF6EB"}
    names = list(palette)
    rows: list[Row] = []
    for i in range(1, rows_count + 1):
        colour = names[(i - 1) % len(names)]
        if i == 1:
            ops = [Op("sc", stitches)]
        elif i % 2 == 0:
            ops = [Repeat([Op(code, n) for code, n in repeat], times=None)]
        else:
            ops = [Op("sc", stitches)]
        rows.append(Row(index=i, ops=ops, declared_count=stitches,
                        turning_chain=0 if geometry.closed else 1, color=colour))

    return CIR(
        slug=concept.key,
        title=concept.title or concept.key,
        version=version,
        construction=construction,
        risk_class="A" if not geometry.closed else "B",
        colors=dict(palette),
        gauge=gauge,
        materials=[Material(name=DEFAULT_YARN, yarn_weight=gauge.yarn_weight, color_id=name)
                   for name in names],
        components=[Component(name="body", construction=construction, rows=rows,
                              foundation=stitches,
                              foundation_kind="ring" if geometry.closed else "chain")],
        designer_notes=(f"prototype of {concept.key}: {geometry.what}, "
                        f"{geometry.width_cm:g} x {geometry.height_cm:g} cm at "
                        f"{gauge.stitches_per_10cm:g} sts/10cm"),
    )


def _drift(geometry: Geometry, width_cm: float, height_cm: float) -> dict[str, float]:
    """How far the made object is from the object that was asked for, per dimension."""
    return {
        "width": round(abs(width_cm - geometry.width_cm) / geometry.width_cm, 3),
        "height": round(abs(height_cm - geometry.height_cm) / geometry.height_cm, 3),
    }


def prototype(concepts: list) -> dict:
    """Stage four: author, compile and run the twin. What does not check does not advance.

    The gate the funnel names for this stage is deterministic validation, and that is exactly
    what happens here -- no model is asked whether the pattern is right, because the compiler
    and the twin answer that and a model that disagrees is noise.
    """
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    survivors, killed, detail = [], {}, {}
    for candidate in concepts:
        concept = getattr(candidate, "concept", candidate)
        try:
            cir = author(concept)
        except PrototypeRefused as e:
            killed[concept.key] = "unverifiable"
            detail[concept.key] = {"refused": str(e)[:300]}
            if hasattr(candidate, "killed_by"):
                candidate.killed_by = "unverifiable"
                candidate.detail = str(e)[:400]
            continue

        result = compile_cir(cir)
        if not result.ok:
            killed[concept.key] = "unverifiable"
            detail[concept.key] = {
                "compile_errors": [str(f) for f in result.errors][:3]}
            if hasattr(candidate, "killed_by"):
                candidate.killed_by = "unverifiable"
                candidate.detail = "; ".join(str(f) for f in result.errors)[:400]
            continue

        twin = build_twin(cir, result)
        geometry = FORM_GEOMETRY[concept.form]
        # The width a maker measures: circumference for a closed form, flat width otherwise.
        measured_width = (twin.circumference_cm if geometry.closed and twin.circumference_cm
                          else twin.width_cm)
        drift = _drift(geometry, measured_width, twin.height_cm)
        detail[concept.key] = {
            "construction": cir.construction,
            "stitch_total": twin.stitch_total,
            "declared_cm": [geometry.width_cm, geometry.height_cm],
            "measured_cm": [round(measured_width, 1), round(twin.height_cm, 1)],
            "drift": drift,
            "yarn_metres": dict(twin.yarn_metres_by_color),
        }
        if max(drift.values()) > SIZE_TOLERANCE:
            killed[concept.key] = "unverifiable"
            detail[concept.key]["why"] = (
                f"the twin measures this at {measured_width:.0f} x {twin.height_cm:.0f} cm "
                f"against a declared {geometry.width_cm:g} x {geometry.height_cm:g}. A CIR "
                f"that compiles and describes the wrong object is what the twin is for")
            if hasattr(candidate, "killed_by"):
                candidate.killed_by = "unverifiable"
                candidate.detail = detail[concept.key]["why"]
            continue
        survivors.append(candidate)

    return {
        "survivors": survivors,
        "killed": killed,
        "detail": detail,
        "forms_with_no_geometry": dict(NO_GEOMETRY_YET),
        "note": ("Deterministic validation, which is the gate this stage is for. A concept "
                 "whose form has no finished size on file is refused rather than sized by "
                 "guess -- that is an engineering item with a name, and a guessed dimension "
                 "compiles perfectly and describes an object nobody designed (#3)."),
    }
