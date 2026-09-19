"""Turning a proven object into a seasonal one, and refusing to call a recolour that.

Requirements 279 and 282. For every proven evergreen or benchmark concept, evaluate the
season and holiday transformations: palette, styling, motif vocabulary, trim, gift context,
collection story, supporting accessories. The requirement's own condition is that they remain
technically legitimate, and the worked example it gives -- a striped cardigan in Christmas,
winter, spring and fall palettes -- is the one most likely to be got wrong.

Because the obvious reading of that example is wrong, and expensively. A cardigan in forest
and cranberry is the *same cardigan*. It is a photograph and a listing, not an engineering
project, and treating it as a new product spends weeks producing something the concept engine
already scores at zero distance from its parent. Meanwhile the transformation that would
actually be worth engineering -- the one with a motif vocabulary, a trim, a companion object
-- never gets made, because the quota was filled by recolours.

So every transformation is routed before it is costed:

**Presentation-only layers re-merchandise.** Palette, styling, gift context and collection
story change what a buyer sees and nothing about what a maker makes. They belong to #292's
path, which already refuses to count them as catalogue growth, and this module hands them
over rather than duplicating the judgement.

**Object-changing layers must earn the engineering.** A motif vocabulary, a trim or a
companion accessory changes the thing itself, so it gets a new CIR, a compile and a physical
test -- and it therefore has to be worth them. A transformation that changes the object and
carries no emotional promise is a technically valid, forgettable product, which is the exact
thing the owner's standard rejects and the thing a generator produces by default.

The emotional promise is not decoration on this check. The creative jury's dominant failure
mode on the Build-1 catalogue was emotional appeal: eleven technically perfect products that
named no moment a buyer would act on. A transformation engine that did not demand a promise
would produce eleven more, in seasonal colours.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .concept import Concept
from .invention import (
    FLAGSHIP, MOTIF_GRAMMAR, SATURATED, InventionRefused, Promise, promise, wow,
)

REMERCHANDISE, ENGINEER = "remerchandise", "engineer"


@dataclass(frozen=True)
class Layer:
    key: str
    what: str
    changes_the_object: bool
    why: str


LAYERS: tuple[Layer, ...] = (
    Layer("palette", "the colours it is made and photographed in", False,
          "a maker follows the same rows in different yarn; nothing about the pattern moves"),
    Layer("styling", "how it is photographed and presented", False,
          "the object is identical and the photograph is doing the seasonal work"),
    Layer("gift_context", "who it is positioned for and why", False,
          "a change of listing and audience, which is real commercial work and is not a "
          "change to the object"),
    Layer("collection_story", "what it is sold beside", False,
          "merchandising: the same object gains meaning from its siblings"),
    Layer("motif_vocabulary", "what it depicts", True,
          "a motif is worked into the fabric, so this is a different chart and a different "
          "pattern"),
    Layer("trim", "edging, appliqué, hardware or finish", True,
          "a trim adds rows, pieces and instructions, and is where a seasonal version "
          "usually stops being a recolour"),
    Layer("accessory", "a companion object that ships with it", True,
          "a second object is a second pattern, with its own compile and its own test"),
)

LAYER_BY_KEY: dict[str, Layer] = {l.key: l for l in LAYERS}


class TransformRefused(ValueError):
    """A recolour called a transformation, or an engineered variant with nothing to say."""


@dataclass
class Transformation:
    parent: str
    occasion: str
    layers: tuple[str, ...]
    route: str
    motifs: tuple[str, ...] = ()
    emotional_promise: Promise | None = None
    wow_mechanism: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return {
            "parent": self.parent, "occasion": self.occasion,
            "layers": list(self.layers), "route": self.route,
            "changes_the_object": self.route == ENGINEER,
            "motifs": list(self.motifs),
            "emotional_promise": (self.emotional_promise.to_dict()
                                  if self.emotional_promise else None),
            "wow_mechanism": self.wow_mechanism,
            "counts_as_new_product": self.route == ENGINEER,
            "problems": list(self.problems),
            "ok": self.ok,
        }


def route_for(layers: tuple[str, ...]) -> str:
    """Which path this transformation belongs on, decided by what it actually changes."""
    unknown = [l for l in layers if l not in LAYER_BY_KEY]
    if unknown:
        raise TransformRefused(
            f"{unknown} are not transformation layers: {sorted(LAYER_BY_KEY)}")
    if not layers:
        raise TransformRefused(
            "a transformation with no layers changes nothing, and a seasonal name is not a "
            "layer")
    return ENGINEER if any(LAYER_BY_KEY[l].changes_the_object for l in layers) else \
        REMERCHANDISE


def transform(parent: Concept, *, occasion: str, layers: tuple[str, ...],
              motifs: tuple[str, ...] = (),
              feeling: str = "", execution: str = "", how: str = "",
              wow_mechanism: str | None = None, grounded_in: str = "") -> Transformation:
    """Evaluate one seasonal transformation of a proven concept, and route it honestly."""
    if occasion not in MOTIF_GRAMMAR:
        raise TransformRefused(
            f"{occasion!r} has no motif grammar: {sorted(MOTIF_GRAMMAR)}. A season this "
            f"company cannot describe in motifs is one it cannot design for")

    route = route_for(layers)
    result = Transformation(parent=parent.key, occasion=occasion, layers=tuple(layers),
                            route=route, motifs=tuple(motifs))

    if route == REMERCHANDISE:
        if motifs:
            raise TransformRefused(
                "motifs were supplied for a presentation-only transformation. A motif is "
                "worked into the fabric, so declaring one makes this an engineering change "
                "-- add the motif_vocabulary layer or drop the motifs")
        result.problems.append(
            "PRESENTATION_ONLY: this is a photograph and a listing, not a pattern. It is "
            "real commercial work and it belongs to re-merchandising (#292), which already "
            "refuses to count it as catalogue growth")
        return result

    # From here the object changes, so it is a product, and a product has to be worth making.
    if "motif_vocabulary" in layers:
        if not motifs:
            result.problems.append(
                "MOTIF_LAYER_EMPTY: the motif vocabulary is the layer and no motif was named")
        outside = [m for m in motifs if m not in MOTIF_GRAMMAR[occasion]]
        if outside:
            result.problems.append(
                f"MOTIF_OUT_OF_SEASON: {outside} are not in the {occasion} grammar; a motif "
                f"nobody reads as {occasion} does the season's work for nobody")
        saturated = SATURATED.get(occasion, frozenset())
        if motifs and all(m in saturated for m in motifs):
            result.problems.append(
                "MOTIF_IS_THE_DEFAULT: every motif here is one the whole category uses. It "
                "is not forbidden and it is not a transformation either -- the seasonal "
                "version has to be recognisably this shop's")

    if not feeling:
        result.problems.append(
            "NO_EMOTIONAL_PROMISE: this changes the object, takes a compile and a physical "
            "test, and names no moment a buyer would act on. The creative jury's dominant "
            "failure on the existing catalogue was exactly this, and a seasonal palette does "
            "not fix it (#109)")
    else:
        try:
            result.emotional_promise = promise(feeling, execution, how)
        except InventionRefused as exc:
            result.problems.append(f"PROMISE_REFUSED: {exc}")

    if parent.make_lane == FLAGSHIP:
        verdict = wow(parent.make_lane, wow_mechanism, grounded_in)
        result.wow_mechanism = verdict.mechanism
        result.problems.extend(f"WOW: {p}" for p in verdict.problems)

    return result


def derive(parent: Concept, transformation: Transformation, *, key: str,
           title: str, premise: str, palette_story: str, recipient: str,
           function: str) -> Concept:
    """Build the child concept an engineered transformation produces.

    Only an engineering route may derive a concept. A presentation-only transformation has
    no child -- it is the same object in a different photograph, and minting a Concept for it
    would put a recolour into the catalogue through the side door, which is how the count of
    products stops meaning anything.

    The child is a concept like any other, so it faces the creative jury on its own. That is
    the point: the engine's job is to produce something that survives the gate, not to be
    trusted instead of it.
    """
    if transformation.route != ENGINEER:
        raise TransformRefused(
            "a presentation-only transformation has no child concept: it is the same object "
            "in a different photograph, and minting a concept for it puts a recolour in the "
            "catalogue through the side door")
    if not transformation.ok:
        raise TransformRefused(
            f"this transformation has unresolved problems and cannot become a concept: "
            f"{transformation.problems}")

    feeling = (transformation.emotional_promise.feeling
               if transformation.emotional_promise else parent.feeling)
    motif = ", ".join(transformation.motifs) if transformation.motifs else parent.motif
    return Concept(
        key=key, title=title, premise=premise, pod=parent.pod, form=parent.form,
        construction=parent.construction, motif=motif, palette_story=palette_story,
        recipient=recipient, occasion=transformation.occasion, feeling=feeling,
        function=function, make_lane=parent.make_lane,
        provenance=f"transformed:{parent.key}")


def ladder(parent: Concept, *, occasion: str) -> list[dict]:
    """Every transformation worth evaluating for this concept, cheapest first.

    Cheapest first because that is the commercial order and the one a creative department
    inverts by instinct: the photograph costs an afternoon and the trim costs a fortnight,
    and the fortnight is the one that feels like real work.
    """
    out = []
    for layer in LAYERS:
        out.append({
            "layer": layer.key, "what": layer.what, "why": layer.why,
            "route": ENGINEER if layer.changes_the_object else REMERCHANDISE,
            "changes_the_object": layer.changes_the_object,
            "requires": (["emotional promise", "motif in the season's grammar"]
                         if layer.changes_the_object else
                         ["nothing this shop does not already have"]),
        })
    out.sort(key=lambda row: row["changes_the_object"])
    return out


def evaluate(parent: Concept, *, occasions: tuple[str, ...] = ()) -> dict:
    """The seasonal transformation survey #279 asks for, across every described season."""
    seasons = occasions or tuple(MOTIF_GRAMMAR)
    unknown = [s for s in seasons if s not in MOTIF_GRAMMAR]
    if unknown:
        raise TransformRefused(f"no motif grammar for {unknown}")
    return {
        "parent": parent.key,
        "parent_lane": parent.make_lane,
        "seasons": [{"occasion": season,
                     "motifs_available": list(MOTIF_GRAMMAR[season]),
                     "ladder": ladder(parent, occasion=season)}
                    for season in seasons],
        "note": ("Presentation layers re-merchandise and cost a photograph; object layers "
                 "are products and cost a compile, a test and a promise a buyer would act "
                 "on. Routing them before costing them is the whole of #279."),
    }


# ---------------------------------------------------------------------------
# #282: the worked example, as code rather than as a paragraph


def striped_cardigan_example() -> dict:
    """The requirement's own example, run through the engine.

    It is in the master because it is the case most likely to be got wrong: four seasonal
    palettes of a proven cardigan look like four products and are one. Running it here means
    the answer is a function of the rules rather than of whoever is reading them.
    """
    parent = Concept(
        key="cropped-striped-cardigan", title="Cropped Striped Cardigan",
        premise="a cropped v-neck cardigan with bands of colour across the body",
        pod="garments", form="fitted_garment", construction="top_down_yoke",
        motif="horizontal bands", palette_story="cream and oat",
        recipient="self", occasion="everyday", feeling="cosy",
        function="a layer worn indoors in spring and autumn", make_lane="FLAGSHIP")

    palettes = []
    for season, story in (("christmas", "forest, cranberry, cream and gold"),
                          ("fall", "rust, moss and oat"),
                          ("spring", "sorbet, cream and sage")):
        result = transform(parent, occasion=season, layers=("palette", "styling"))
        palettes.append({"occasion": season, "palette_story": story,
                         **result.to_dict()})

    engineered = transform(
        parent, occasion="christmas",
        layers=("motif_vocabulary", "trim", "palette"),
        motifs=("woodland", "star"),
        feeling="nostalgic", execution="motif",
        how=("a band of woodland figures walks the yoke where the stripes were, so the "
             "colourwork is the garment's structure rather than a patch on it"),
        wow_mechanism="exceptional_motif_composition",
        grounded_in=("the yoke's increases place the figures so the herd widens as the "
                     "shoulder does"))

    return {
        "parent": parent.key,
        "palette_variants": palettes,
        "engineered_variant": engineered.to_dict(),
        "catalogue_growth": 1 if engineered.ok else 0,
        "note": ("three seasonal palettes are one cardigan photographed three ways -- real "
                 "commercial work, zero new patterns. The Christmas version worth "
                 "engineering is the one that changes what the garment depicts, and it has "
                 "to carry a promise to be worth the compile (#282)."),
    }
