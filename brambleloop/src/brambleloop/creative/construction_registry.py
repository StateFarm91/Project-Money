"""The research -> Product Development contract: a brief becomes a construction request, and a
request is built by a reusable construction -- or held, naming exactly what the brief lacks.

Before this, a tournament winner's brief (`creative.concept.Concept`: form, construction,
motif, palette story, recipient, occasion, feeling, function) reached `cir.draft`, and every
non-garment winner went to `creative.prototype.author`, which reads only the form's default
size and emits a single-crochet stripe in a fixed palette. The brief's construction, motif and
palette never reached a pattern, and the reusable constructions Product Development has (round
vessels, tapestry colourwork, shaped stuffed toys, drawstring pouches, totes) were reachable
only from the radar fallback, by title words.

Three rules.

**The brief is read, never guessed.** `request_for` reads the concept's own closed-vocabulary
fields and the brief dict prospecting passes with it. Every parameter a construction needs is
taken from those, or from a table this repository already holds (`prototype.FORM_GEOMETRY`,
`products.vessels.BASKET_SIZES`, the motif library). A parameter that is in neither is not
invented: it is an `unresolved` item naming the field and why.

**One registry, explicit parameters.** `ROUTES` maps (form, construction) to a construction,
and each construction is called with the parameters the request carries (chart, size, kind)
rather than with words it re-parses out of a title. Adding a brief needs no code; adding a
construction is one registry entry.

**A held brief is a recorded dependency, not a refusal in disguise.** A request with
unresolved items is not drafted. `cir.draft` records `cir.draft_held` with every item, and
the item names whether research must enrich the brief (a missing dimension, a motif with no
chart) or an engine decision is pending (mosaic's reach-down stitch, joined motifs).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HELD_ACTION = "cir.draft_held"
ENRICH = "research_enrichment"        # the brief must say more
ENGINE = "engine_decision"            # Product Development cannot build it yet

# Constructions a brief may ask for that no engine can honestly make yet, and what blocks them.
ENGINE_BLOCKED: dict[str, str] = {
    "mosaic_overlay": ("overlay mosaic needs stitches that reach past the previous row; the "
                       "CIR has no reach-down primitive (integrator decision 5)"),
    "granny_square": ("joined motifs are one object only once Seam.joins_copies exists "
                      "(integrator decision 2)"),
    "motif_join": ("joined motifs are one object only once Seam.joins_copies exists "
                   "(integrator decision 2)"),
    "corner_to_corner": "a corner-to-corner graph is not modelled by any construction",
    "cable_panel": "post-stitch cables are not a construction any builder makes",
}

# Brief motif words a construction can actually make, per construction.
AMIGURUMI_KINDS = {"bear": "bear", "teddy": "bear", "bunny": "bunny", "rabbit": "bunny"}
SIZE_WORDS = ("small", "medium", "large")


@dataclass
class ConstructionRequest:
    """A brief as Product Development reads it."""

    key: str
    title: str
    form: str
    construction: str
    motif: str
    palette: dict[str, str]
    yarn_weight: str
    size: str | None = None
    family: str | None = None
    params: dict = field(default_factory=dict)
    unresolved: list[dict] = field(default_factory=list)

    def hold(self, what: str, why: str, kind: str = ENRICH) -> None:
        self.unresolved.append({"field": what, "why": why, "resolved_by": kind})

    def to_dict(self) -> dict:
        return {"key": self.key, "form": self.form, "construction": self.construction,
                "motif": self.motif, "palette": dict(self.palette),
                "yarn_weight": self.yarn_weight, "size": self.size, "family": self.family,
                "params": dict(self.params), "unresolved": list(self.unresolved)}


def _words(text: str) -> list[str]:
    from .fallback_constructions import fold_title

    return re.findall(r"[a-z]+", fold_title(text))


def _tapestry(req: ConstructionRequest) -> None:
    from .fallback_constructions import _chart_word, tapestry_charts

    backed = tapestry_charts()
    charts = {_chart_word(w) for w in _words(req.motif) if _chart_word(w)}
    if len(charts) != 1 or next(iter(charts)) not in backed:
        req.hold("motif", (f"the brief's motif {req.motif!r} names no single backed tapestry "
                           f"chart (have: {sorted(backed)})"))
        return
    if len(req.palette) < 2 or len(set(list(req.palette.values())[:2])) < 2:
        req.hold("palette", "tapestry needs two distinct colours; the palette story names "
                            f"{len(req.palette)}")
        return
    req.params["chart"] = charts.pop()
    if req.size:
        req.params["size"] = req.size


def _amigurumi(req: ConstructionRequest) -> None:
    kinds = {AMIGURUMI_KINDS[w] for w in _words(req.motif) if w in AMIGURUMI_KINDS}
    if len(kinds) != 1:
        req.hold("motif", (f"the brief's motif {req.motif!r} names no single shape the "
                           f"ball-body toy makes (have: {sorted(set(AMIGURUMI_KINDS.values()))})"))
        return
    req.params["kind"] = kinds.pop()


def _plain(req: ConstructionRequest) -> None:
    """A construction that carries no motif: a motif word in the brief would be unbacked."""
    from ..products.launch0 import MOTIF_WORDS
    from .fallback_constructions import LIBRARY_CHART_WORDS, _TAPESTRY_CHART_WORDS

    # A motif word, or a pattern word a chart would make ("checked", "chequered"), names a
    # pattern this construction does not work: the name would promise what the fabric is not.
    pattern_words = set(MOTIF_WORDS) | set(_TAPESTRY_CHART_WORDS) | set(LIBRARY_CHART_WORDS)
    named = sorted({w for w in _words(f"{req.motif} {req.title}") if w in pattern_words})
    if named:
        req.hold("motif", (f"the brief names the motif {named} and this construction works "
                           f"no motif; it needs a construction that does"))
    if req.family == "vessel" and req.size:
        req.params["size"] = req.size


# (form, construction) -> (family, the parameter resolver). Every family's builder is in
# `creative.fallback_constructions` and is the same code the radar fallback runs.
ROUTES: dict[tuple[str, str], tuple[str, object]] = {
    ("basket", "in_the_round"): ("vessel", _plain),
    ("basket", "seamless_tube"): ("vessel", _plain),
    ("basket", "tapestry"): ("tapestry", _tapestry),
    ("toy", "amigurumi_shaping"): ("amigurumi", _amigurumi),
    ("sphere", "amigurumi_shaping"): ("amigurumi", _amigurumi),
    ("pouch", "in_the_round"): ("pouch", _plain),
    ("bag", "in_the_round"): ("tote", _plain),
}


def request_for(concept, brief: dict | None = None) -> ConstructionRequest | None:
    """The construction request a creative concept describes, or None when no construction
    in the registry serves its (form, construction) and no engine block names it -- the
    existing authoring path (`prototype.author`) then applies, unchanged."""
    from .garment_design import colours_of

    brief = dict(brief or {})
    palette = dict(colours_of(getattr(concept, "palette_story", "") or ""))
    req = ConstructionRequest(
        key=concept.key, title=concept.title or concept.key, form=concept.form,
        construction=concept.construction, motif=concept.motif or "",
        palette=palette, yarn_weight=str(brief.get("yarn_weight") or "worsted"))
    size = str(brief.get("size") or "").lower() or None
    if size is not None and size not in SIZE_WORDS:
        req.hold("size", f"the brief's size {size!r} is not one this repository sizes "
                         f"({', '.join(SIZE_WORDS)})")
    req.size = size if size in SIZE_WORDS else None
    if brief.get("dimensions_cm"):
        req.hold("dimensions_cm", ("the brief states dimensions; the constructions here are "
                                   "sized from sourced tables and cannot yet honour a stated "
                                   "dimension"), ENGINE)
    blocked = ENGINE_BLOCKED.get(concept.construction)
    route = ROUTES.get((concept.form, concept.construction))
    if blocked and route is None:
        req.hold("construction", blocked, ENGINE)
        return req
    if route is None:
        return None
    req.family, resolve = route
    resolve(req)
    return req


def build(req: ConstructionRequest, *, version: str = "1.0.0", provenance=None):
    """The CIR a resolved request describes. Raises ValueError on an unresolved request."""
    from ..runtime.pipeline import Concept as RadarConcept
    from . import fallback_constructions as FC

    if req.unresolved or not req.family:
        raise ValueError(f"{req.key}: unresolved: {req.unresolved}")
    category = {"vessel": "basket", "tapestry": "basket", "amigurumi": "amigurumi",
                "pouch": "bag", "tote": "bag"}[req.family]
    concept = RadarConcept(slug=req.key, title=req.title, category=category,
                           stitch_repeat=[("sc", 4)], width_stitches=24, rows=8,
                           colors=dict(req.palette), yarn_weight=req.yarn_weight)
    builder = {"vessel": FC.vessel, "tapestry": FC.tapestry_basket, "amigurumi": FC.amigurumi,
               "pouch": FC.pouch, "tote": FC.tote}[req.family]
    return builder(concept, version=version, provenance=provenance, **req.params)


def declared_primitives(req: ConstructionRequest) -> tuple[str, ...]:
    """What the built CIR must declare so the truth gates can back the brief's words: the
    library motif a tapestry chart works (launch0.MOTIF_DECLARATIONS)."""
    from .fallback_constructions import tapestry_motif_primitive

    if req.family == "tapestry" and req.params.get("chart"):
        prim = tapestry_motif_primitive(req.params["chart"])
        return (prim,) if prim else ()
    return ()


PRIMITIVES = ("creative.construction_registry.request_for",
              "creative.construction_registry.build")
