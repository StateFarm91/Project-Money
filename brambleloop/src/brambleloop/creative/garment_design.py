"""From a garment concept to a graded Brambleloop design, without a human in between.

The tournament could invent a `fitted_garment` concept and the prototype stage refused it:
"a graded garment is a size chart, not a finished size". Build 2 closed the grading
(`cir/graded.py`, sourced Craft Yarn Council body tables) and the construction templates
(`products/garments.py`); this is the link that lets a concept reach them, so an original
garment can be designed end to end by the system rather than only by a person calling a
template by name.

Every choice is a rule written here, not a model's guess and never a purchased pattern:

  construction   top_down_yoke -> raglan worked top-down; flat, bottom-up, side-to-side,
                 modular or cable-panel constructions -> drop-shoulder flat pieces seamed.
                 Anything else is refused with its name.
  body table     child and teen recipients -> CYC child/youth 2-16; a new parent's gift is
                 babywear, which no sourced table here covers, so it is refused rather than
                 graded from a child table it does not fit; everyone else -> CYC woman XS-5X.
  fabric         quick lanes (QUICK, SHORT) -> double crochet in DK for speed; the rest ->
                 ridged single crochet in worsted, the sturdier fabric.
  fit            relaxed ease by default. A premise that says "fitted" or "close" gets close
                 ease, which makes the garment class C: certification then refuses it until a
                 physical fit test exists (`PHYSICAL_TEST_REQUIRED`). Refusal is the honest
                 outcome for a fitted garment nobody has tried on.

The design key is the concept's key, and `GradedDesign` stamps the CIR's provenance with it and
with no benchmarks consulted; `cir.specification` independently refuses any result whose
stitch tables contain a purchased benchmark's.
"""
from __future__ import annotations

from ..cir.graded import CHILD, WOMAN, FitIntent, GradedDesign
from ..cir.model import Gauge, Material
from ..products import garments as G
from .concept import Concept

RAGLAN_CONSTRUCTIONS = frozenset({"top_down_yoke"})
DROP_SHOULDER_CONSTRUCTIONS = frozenset({"flat_rows", "bottom_up", "side_to_side",
                                         "modular_panels", "cable_panel"})
CHILD_RECIPIENTS = frozenset({"child", "teen"})
UNSIZED_RECIPIENTS = {"new_parent": "babywear: no sourced baby body table is on file, and "
                                    "grading a baby garment from the child/youth chart would "
                                    "invent measurements"}
QUICK_LANES = frozenset({"QUICK", "SHORT"})
FITTED_WORDS = ("fitted", "close-fitting", "close fitting", "body-skimming", "tailored")

RELAXED_EASE = {"bust": 20, "back_length": 12, "armhole_depth": 4, "upper_arm": 8}
RELAXED_EASE_CHILD = {"bust": 10, "back_length": 6, "armhole_depth": 2, "upper_arm": 5}
CLOSE_EASE = {"bust": 4, "back_length": 4, "armhole_depth": 2, "upper_arm": 3}

SC_WORSTED = (Gauge(stitches_per_10cm=16, rows_per_10cm=18, stitch_type="sc", hook_mm=5.5,
                    yarn_weight="worsted"), Material(name="worsted wool", yarn_weight="worsted"))
DC_DK = (Gauge(stitches_per_10cm=14, rows_per_10cm=8, stitch_type="dc", hook_mm=4.5,
               yarn_weight="dk"), Material(name="dk cotton", yarn_weight="dk"))


class GarmentDesignRefused(ValueError):
    pass


def is_fitted(concept: Concept) -> bool:
    text = f"{concept.premise} {concept.notes}".lower()
    return any(w in text for w in FITTED_WORDS)


def design_for(concept: Concept) -> GradedDesign:
    """The graded design this concept describes, or a refusal that names the missing rule."""
    if concept.form not in ("fitted_garment",):
        raise GarmentDesignRefused(f"{concept.key}: {concept.form!r} is not a garment form")
    if concept.recipient in UNSIZED_RECIPIENTS:
        raise GarmentDesignRefused(f"{concept.key}: {UNSIZED_RECIPIENTS[concept.recipient]}")
    child = concept.recipient in CHILD_RECIPIENTS
    table = CHILD if child else WOMAN
    gauge, material = DC_DK if concept.make_lane in QUICK_LANES else SC_WORSTED
    family = (G.StitchFamily("dc", "plain") if gauge.stitch_type == "dc"
              else G.StitchFamily("sc", "ridged"))
    ease = CLOSE_EASE if is_fitted(concept) else (RELAXED_EASE_CHILD if child else RELAXED_EASE)
    key, title = concept.key, concept.title

    if concept.construction in RAGLAN_CONSTRUCTIONS:
        template = (lambda g: G.raglan_top_down(g, key=key, title=title, family=family,
                                                material=material))
        requires, primitives = G.RAGLAN_REQUIRES, ("cir.graded", "cir.shaping.distribute",
                                                   "Hold", "Seam")
    elif concept.construction in DROP_SHOULDER_CONSTRUCTIONS:
        template = (lambda g: G.drop_shoulder_flat(g, key=key, title=title, family=family,
                                                   material=material))
        requires, primitives = G.DROP_SHOULDER_REQUIRES, ("cir.graded", "cir.shaping.taper",
                                                          "Seam")
    else:
        raise GarmentDesignRefused(
            f"{concept.key}: no garment template is taught the {concept.construction!r} "
            f"construction yet; that is a named engine gap, not a concept failure")
    return GradedDesign(key=key, title=title, table=table, gauge=gauge, fit=FitIntent(ease),
                        requires=requires, primitives=primitives, template=template)


def base_size(design: GradedDesign) -> str:
    """The middle sourced size: the one a single-size prototype stage checks first."""
    sizes = design.sourced_sizes()
    if not sizes:
        raise GarmentDesignRefused(f"{design.key}: no size can be graded from sourced data")
    return sizes[len(sizes) // 2]
