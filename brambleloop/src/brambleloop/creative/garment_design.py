"""From a garment concept to a graded Brambleloop design, without a human in between.

The tournament could invent a `fitted_garment` concept and the prototype stage refused it:
"a graded garment is a size chart, not a finished size". Build 2 closed the grading
(`cir/graded.py`, sourced Craft Yarn Council body tables) and the construction templates
(`products/garments.py`); this is the link that lets a concept reach them, so an original
garment can be designed end to end by the system rather than only by a person calling a
template by name.

Every choice is a rule written here, as a named table, not a model's guess and never a
purchased pattern. Routing (what CAN be made):

  construction   top_down_yoke -> raglan worked top-down; flat, bottom-up, side-to-side,
                 modular or cable-panel constructions -> drop-shoulder flat pieces seamed.
                 Anything else is refused with its name.
  body table     child and teen recipients -> CYC child/youth 2-16; a new parent's gift is
                 babywear, which no sourced table here covers, so it is refused rather than
                 graded from a child table it does not fit; everyone else -> CYC woman XS-5X.
  fabric         quick lanes (QUICK, SHORT) -> double crochet in DK for speed; the rest ->
                 single crochet in worsted, the sturdier fabric.

Design (what the concept SAYS it is -- certification audit C-8 found that the concept's
own words changed nothing, so two different ideas were one garment under two names):

  ease           `EASE_WORDS` in the premise pick fitted / relaxed / oversized / slouchy;
                 otherwise the feeling does (`EASE_BY_FEELING`). Each character is a stated
                 ease set per body table (`EASE_SETS`). Fitted is class C: certification
                 refuses it until a physical fit test exists (`PHYSICAL_TEST_REQUIRED`).
  length         `LENGTH_WORDS` in the premise pick cropped / standard / longline, each a
                 stated ratio of the finished back length (`LENGTH_RATIOS`).
  neckline       the occasion picks close / crew / wide (`NECKLINE_BY_OCCASION`), each a
                 stated ratio of the cross-back per construction (`NECKLINES`), always inside
                 the plausibility floor `cir.specification` enforces.
  texture        `TEXTURE_WORDS` in the motif pick the fabric's loop pattern; otherwise the
                 feeling does (`TEXTURE_BY_FEELING`). Only textures the writer and reverse
                 compiler already round-trip (`garments.TEXTURES`); no stitch is invented.
  colour         the palette story names the colours (split on "and", commas, "&", "/",
                 "with"; at most `MAX_COLOURS`); each gets a hex from `COLOUR_HEX` or, when
                 unnamed there, from `FALLBACK_HEX` by a stable hash. One colour is solid;
                 more are striped or colour-blocked as the feeling says (`COLOUR_PLAN_BY_
                 FEELING`), with a stated band height.

The design key is the concept's key, and `GradedDesign` stamps the CIR's provenance with it and
with no benchmarks consulted; `cir.specification` independently refuses any result whose
stitch tables carry a purchased benchmark's piece.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ..cir.graded import CHILD, WOMAN, FitIntent, GradedDesign
from ..cir.model import Gauge, Material
from ..cir.specification import garment_implausibilities
from ..products import garments as G
from .concept import FEELINGS, OCCASIONS, Concept

RAGLAN_CONSTRUCTIONS = frozenset({"top_down_yoke"})
DROP_SHOULDER_CONSTRUCTIONS = frozenset({"flat_rows", "bottom_up", "side_to_side",
                                         "modular_panels", "cable_panel"})
CHILD_RECIPIENTS = frozenset({"child", "teen"})
UNSIZED_RECIPIENTS = {"new_parent": "babywear: no sourced baby body table is on file, and "
                                    "grading a baby garment from the child/youth chart would "
                                    "invent measurements"}
QUICK_LANES = frozenset({"QUICK", "SHORT"})

SC_WORSTED = (Gauge(stitches_per_10cm=16, rows_per_10cm=18, stitch_type="sc", hook_mm=5.5,
                    yarn_weight="worsted"), Material(name="worsted wool", yarn_weight="worsted"))
DC_DK = (Gauge(stitches_per_10cm=14, rows_per_10cm=8, stitch_type="dc", hook_mm=4.5,
               yarn_weight="dk"), Material(name="dk cotton", yarn_weight="dk"))

# ---- ease -----------------------------------------------------------------------------------

FITTED_WORDS = ("fitted", "close-fitting", "close fitting", "body-skimming", "tailored")
# Premise words, checked in this order; the first character with a word present wins.
EASE_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fitted", FITTED_WORDS),
    ("oversized", ("oversized", "boxy", "roomy", "generous")),
    ("slouchy", ("slouchy", "drapey", "loose", "slouch")),
    ("relaxed", ("relaxed", "easy fit", "easy-fitting")),
)
# Ease sets in cm per character and body table. Relaxed and above keep at least
# `garments.RELAXED_EASE_CM` on the chest (class B); fitted is close ease (class C). The
# child relaxed set is deliberately not the Pebble fixture's (10 cm): a concept must not
# come out as an existing design's tables. Child chest eases are also chosen so the CYC 14 ->
# 16 step (2.5 cm of chest) still adds a whole even stitch count to the dc back: 18 cm would
# round both sizes to the same back and the built chest would not rise (checked by
# `GradedDesign.check_monotonic` on the built CIRs).
EASE_SETS: dict[str, dict[str, dict[str, float]]] = {
    "adult": {
        "fitted": {"bust": 4, "back_length": 4, "armhole_depth": 2, "upper_arm": 3},
        "relaxed": {"bust": 20, "back_length": 12, "armhole_depth": 4, "upper_arm": 8},
        "slouchy": {"bust": 26, "back_length": 14, "armhole_depth": 5, "upper_arm": 10},
        "oversized": {"bust": 32, "back_length": 12, "armhole_depth": 6, "upper_arm": 12},
    },
    "child": {
        "fitted": {"bust": 4, "back_length": 4, "armhole_depth": 2, "upper_arm": 3},
        "relaxed": {"bust": 14, "back_length": 6, "armhole_depth": 2, "upper_arm": 5},
        "slouchy": {"bust": 16, "back_length": 7, "armhole_depth": 3, "upper_arm": 6},
        "oversized": {"bust": 22, "back_length": 6, "armhole_depth": 3, "upper_arm": 7},
    },
}
RELAXED_EASE = EASE_SETS["adult"]["relaxed"]
RELAXED_EASE_CHILD = EASE_SETS["child"]["relaxed"]
CLOSE_EASE = EASE_SETS["adult"]["fitted"]
# When the premise names no fit, the feeling does.
EASE_BY_FEELING: dict[str, str] = {
    "heirloom": "relaxed", "cosy": "oversized", "playful": "relaxed", "nostalgic": "relaxed",
    "celebratory": "relaxed", "serene": "slouchy", "whimsical": "slouchy", "bold": "oversized",
    "tender": "relaxed", "festive": "relaxed", "rugged": "oversized", "romantic": "slouchy",
    "quietly_luxurious": "slouchy", "folkloric": "relaxed",
}

# ---- length ---------------------------------------------------------------------------------

LENGTH_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cropped", ("cropped", "crop", "short-bodied", "boxy crop")),
    ("longline", ("longline", "long-line", "tunic", "hip-length", "long body")),
)
# Finished body length as a ratio of the finished (body + ease) back length.
LENGTH_RATIOS: dict[str, float] = {"cropped": 0.85, "standard": 1.0, "longline": 1.2}

# ---- neckline -------------------------------------------------------------------------------

# Neck width as ratios of the body's cross-back, per construction: the raglan's whole neck
# edge target and its sleeve saddle at the neck (`garments.raglan_top_down`), and the
# drop-shoulder's slash-neck span. "crew" is each template's default. The widest setting
# stays inside `cir.specification`'s plausibility floor at every size of both tables, and
# the gate refuses it if it ever does not.
NECKLINES: dict[str, dict[str, float]] = {
    "close": {"raglan": 0.9, "saddle": 0.02, "drop": 0.7},
    "crew": {"raglan": G.NECK_EDGE_OF_CROSS_BACK, "saddle": G.SLEEVE_AT_NECK_OF_CROSS_BACK,
             "drop": G.NECK_OF_CROSS_BACK},
    "wide": {"raglan": 1.15, "saddle": 0.10, "drop": 0.9},
}
# When a neckline would breach the plausibility floor at some size (a wide neck on a small,
# close-fitting child's body), that size steps down this ladder to the next narrower one
# instead of shipping a neck that falls off the shoulders. Stated per size in the CIR notes.
NECKLINE_LADDER: tuple[str, ...] = ("wide", "crew", "close")
NECKLINE_BY_OCCASION: dict[str, str] = {
    "christmas": "close", "halloween": "crew", "easter": "crew", "valentines": "wide",
    "thanksgiving": "close", "new_baby": "crew", "housewarming": "crew", "wedding": "wide",
    "birthday": "crew", "mothers_day": "wide", "fathers_day": "crew", "graduation": "crew",
    "everyday": "crew", "winter_nesting": "close", "spring_refresh": "wide",
    "summer_travel": "wide", "back_to_school": "crew",
}

# ---- texture --------------------------------------------------------------------------------

# Motif words, checked in this order; the first texture with a word present wins.
TEXTURE_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ribbed", ("rib", "bark", "cord", "furrowed field", "corduroy", "pleat")),
    ("furrowed", ("ripple", "wave", "tide", "furrow", "lattice", "weave", "woven")),
    ("ridged", ("ridge", "window", "pane", "stripe", "ladder", "step", "brick")),
    ("plain", ("stone", "pebble", "glass", "smooth", "still", "calm", "cloud")),
)
TEXTURE_BY_FEELING: dict[str, str] = {
    "heirloom": "ridged", "cosy": "ribbed", "playful": "plain", "nostalgic": "ridged",
    "celebratory": "plain", "serene": "plain", "whimsical": "furrowed", "bold": "ribbed",
    "tender": "plain", "festive": "ridged", "rugged": "ribbed", "romantic": "furrowed",
    "quietly_luxurious": "plain", "folkloric": "furrowed",
}

# ---- colour ---------------------------------------------------------------------------------

MAX_COLOURS = 4
COLOUR_HEX: dict[str, str] = {
    "cream": "#F3EEDF", "oat": "#DCCFB4", "oatmeal": "#D8CCB2", "sand": "#D9C6A0",
    "natural": "#EDE6D3", "ivory": "#F6F1E3", "stone": "#A8A196", "granite": "#6E6A66",
    "slate": "#5B6770", "charcoal": "#3A3A3C", "soot": "#2B2A29", "ink": "#23283A",
    "silver": "#B9BCBF", "moss": "#6B7445", "forest": "#2F4A35", "spruce": "#2E4D47",
    "sage": "#9AA78A", "sea-glass": "#A9CFC4", "glass": "#B5D3CB", "teal": "#2F6F73",
    "denim": "#4C6A8C", "sky": "#9CC0DA", "ember": "#B5482F", "rust": "#A0522D",
    "clay": "#B36B4F", "terracotta": "#C0603F", "cranberry": "#8C1C35", "wine": "#6E1F2A",
    "berry": "#7E2F56", "rose": "#D59A9E", "blush": "#E8C3BF", "gold": "#C9A23A",
    "lantern-gold": "#D8A73C", "mustard": "#C49A2C", "honey": "#D4A04A", "plum": "#5E3A58",
    "heather": "#9C8AA5", "lavender": "#B7A8CF", "brown": "#6B4E3A", "chestnut": "#7A4A2E",
}
# Unnamed colours take one of these muted yarn shades by a stable hash of their name, so the
# same words always give the same hex and no colour is left without one.
FALLBACK_HEX: tuple[str, ...] = ("#8E8A7E", "#7D8C82", "#9A8577", "#7F8797", "#A39A7A",
                                 "#8C7F8F", "#6F7D74", "#A08C84")
# (plan, band height in cm) by feeling, used when the palette has two or more colours.
COLOUR_PLAN_BY_FEELING: dict[str, tuple[str, float]] = {
    "heirloom": ("blocks", 0.0), "cosy": ("stripes", 6.0), "playful": ("stripes", 3.0),
    "nostalgic": ("stripes", 4.0), "celebratory": ("stripes", 2.5), "serene": ("blocks", 0.0),
    "whimsical": ("stripes", 2.0), "bold": ("blocks", 0.0), "tender": ("stripes", 5.0),
    "festive": ("stripes", 3.5), "rugged": ("blocks", 0.0), "romantic": ("stripes", 4.5),
    "quietly_luxurious": ("blocks", 0.0), "folkloric": ("stripes", 1.5),
}
_SPLIT = re.compile(r"\s*(?:,|&|/|\+|\band\b|\bwith\b)\s*")

assert set(EASE_BY_FEELING) == set(FEELINGS) == set(TEXTURE_BY_FEELING) \
    == set(COLOUR_PLAN_BY_FEELING), "every feeling needs a rule in every table"
assert set(NECKLINE_BY_OCCASION) == set(OCCASIONS), "every occasion needs a neckline rule"


class GarmentDesignRefused(ValueError):
    pass


@dataclass(frozen=True)
class DesignChoices:
    """Every decision the concept's words made, stated so a reviewer can audit it."""

    construction: str      # "raglan" | "drop"
    table: str             # "adult" | "child"
    stitch: str
    texture: str
    ease: str
    length: str
    neckline: str
    colours: tuple[tuple[str, str], ...]
    colour_plan: str
    band_cm: float

    def to_dict(self) -> dict:
        return {k: (list(map(list, v)) if k == "colours" else v)
                for k, v in self.__dict__.items()}


def _words(text: str, table) -> str | None:
    """The first entry of `table` with a word that starts a word of `text` ("rib" matches
    "ribs" and "ribbed", not "crib")."""
    low = text.lower()
    for name, words in table:
        if any(re.search(r"\b" + re.escape(w), low) for w in words):
            return name
    return None


def is_fitted(concept: Concept) -> bool:
    text = f"{concept.premise} {concept.notes}".lower()
    return any(w in text for w in FITTED_WORDS)


def colours_of(palette_story: str) -> tuple[tuple[str, str], ...]:
    """The named colours of a palette story, each with its hex, in the order named."""
    names: list[str] = []
    for part in _SPLIT.split(palette_story.strip().lower()):
        name = re.sub(r"[^a-z0-9]+", "-", part).strip("-")
        if name and name not in names:
            names.append(name)
    names = names[:MAX_COLOURS] or ["natural"]
    out = []
    for name in names:
        hexa = COLOUR_HEX.get(name) or COLOUR_HEX.get(name.split("-")[-1])
        if hexa is None:
            h = int(hashlib.sha256(name.encode()).hexdigest(), 16)
            hexa = FALLBACK_HEX[h % len(FALLBACK_HEX)]
        out.append((name, hexa))
    return tuple(out)


def choices_for(concept: Concept) -> DesignChoices:
    """The design decisions this concept makes, by the tables above. Deterministic."""
    if concept.form not in ("fitted_garment",):
        raise GarmentDesignRefused(f"{concept.key}: {concept.form!r} is not a garment form")
    if concept.recipient in UNSIZED_RECIPIENTS:
        raise GarmentDesignRefused(f"{concept.key}: {UNSIZED_RECIPIENTS[concept.recipient]}")
    if concept.construction in RAGLAN_CONSTRUCTIONS:
        construction = "raglan"
    elif concept.construction in DROP_SHOULDER_CONSTRUCTIONS:
        construction = "drop"
    else:
        raise GarmentDesignRefused(
            f"{concept.key}: no garment template is taught the {concept.construction!r} "
            f"construction yet; that is a named engine gap, not a concept failure")
    premise = f"{concept.premise} {concept.notes}"
    ease = "fitted" if is_fitted(concept) else (
        _words(premise, EASE_WORDS) or EASE_BY_FEELING[concept.feeling])
    colours = colours_of(concept.palette_story)
    plan, band = ("solid", 0.0) if len(colours) == 1 else \
        COLOUR_PLAN_BY_FEELING[concept.feeling]
    return DesignChoices(
        construction=construction,
        table="child" if concept.recipient in CHILD_RECIPIENTS else "adult",
        stitch="dc" if concept.make_lane in QUICK_LANES else "sc",
        texture=_words(concept.motif, TEXTURE_WORDS) or TEXTURE_BY_FEELING[concept.feeling],
        ease=ease,
        length=_words(premise, LENGTH_WORDS) or "standard",
        neckline=NECKLINE_BY_OCCASION[concept.occasion],
        colours=colours, colour_plan=plan, band_cm=band)


def design_for(concept: Concept) -> GradedDesign:
    """The graded design this concept describes, or a refusal that names the missing rule."""
    ch = choices_for(concept)
    table = CHILD if ch.table == "child" else WOMAN
    gauge, material = DC_DK if ch.stitch == "dc" else SC_WORSTED
    family = G.StitchFamily(ch.stitch, ch.texture)
    ease = EASE_SETS[ch.table][ch.ease]
    colours = G.ColourPlan(ch.colours, ch.colour_plan, ch.band_cm)
    length_ratio = LENGTH_RATIOS[ch.length]
    key, title = concept.key, concept.title

    def build_with(g, neckline: str):
        n = NECKLINES[neckline]
        if ch.construction == "raglan":
            return G.raglan_top_down(g, key=key, title=title, family=family,
                                     material=material, length_ratio=length_ratio,
                                     neck_of_cross_back=n["raglan"],
                                     sleeve_at_neck_of_cross_back=n["saddle"],
                                     colours=colours)
        return G.drop_shoulder_flat(g, key=key, title=title, family=family,
                                    material=material, length_ratio=length_ratio,
                                    neck_of_cross_back=n["drop"], colours=colours)

    def template(g):
        ladder = NECKLINE_LADDER[NECKLINE_LADDER.index(ch.neckline):]
        for neckline in ladder:
            cir = build_with(g, neckline)
            if neckline == ladder[-1] or not garment_implausibilities(
                    cir, cross_back_cm=g.body_cm("cross_back")):
                break
        cir.designer_notes = (f"{cir.designer_notes} Neckline: {neckline}"
                              + ("" if neckline == ch.neckline else
                                 f" (the {ch.neckline} neckline would not sit on this size)")
                              + ".")
        return cir

    if ch.construction == "raglan":
        requires, primitives = G.RAGLAN_REQUIRES, ("cir.graded", "cir.shaping.distribute",
                                                   "Hold", "Seam")
    else:
        requires, primitives = G.DROP_SHOULDER_REQUIRES, ("cir.graded", "cir.shaping.taper",
                                                          "Seam")
    design = GradedDesign(key=key, title=title, table=table, gauge=gauge,
                          fit=FitIntent(ease), requires=requires, primitives=primitives,
                          template=template, measure=G.built_measures)
    design.choices = ch
    return design


def base_size(design: GradedDesign) -> str:
    """The middle sourced size: the one a single-size prototype stage checks first."""
    sizes = design.sourced_sizes()
    if not sizes:
        raise GarmentDesignRefused(f"{design.key}: no size can be graded from sourced data")
    return sizes[len(sizes) // 2]
