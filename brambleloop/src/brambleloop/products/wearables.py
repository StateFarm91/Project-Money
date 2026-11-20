"""ENG-GARMENT-2: clothing families beyond the chest-graded garment, one framework.

`products.garment_families` builds chest-graded garments (cardigans, sweaters, vests). This
module extends clothing to every other wearable family -- hats, baby rompers and dresses,
simple tops, cardigan variants, socks and slippers, shawls and bags -- with the same rules:

* **Graded from a published body table.** Each family names the Craft Yarn Council table
  it grades from (`cir.graded`: woman / child / baby bodies, the head chart, the foot
  chart), the measurements it requires, the one it is graded by (`primary`), and its stated
  ease. A stretch fit (a beanie, a sock) takes a bounded negative ease
  (`cir.graded.STRETCH_EASE_LIMIT_CM`); everywhere else negative ease is refused.
* **Every size is the same list of steps.** Pieces are built with
  `garment_families.Piece` (flat rows) or `Rounds` (joined rounds), which record each step
  with that size's numbers, so one document prints the smallest size first and the others in
  parentheses, and the text can be read back per size (`gates.wearable_fit`).
* **Deterministic.** A design is a function from one `GradedSize` to a whole CIR. Nothing
  here reads a benchmark or a model: proportions a body chart does not publish (a hat's
  height, a brim's depth) are named design ratios, stated as such.

An `Engine` is one family: its table, requirements, builder, the instrument that measures a
built size from its compiled rows and twin, the family's own gates, the size-chart columns it
prints, its narrative and its schematic. `ENGINES` is the registry the release
(`build` / `certify`), the PDF (`publish.wearable_pdf`), the router
(`creative.construction_families`) and the draft path (`runtime.pipeline`) all read.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from ..cir.graded import FOOT, HEAD, FitIntent, GradedDesign, GradedSize
from ..cir.model import CIR, Component, Material, Op, Row, Seam
from ..cir.shaping import ShapingRefused
from . import garment_families as GF
from .garments import StitchFamily


def _values(xs) -> str:
    from ..publish.garment_writer import values

    return values(xs)

MARKER = "products.wearables"


class WearableRefused(ValueError):
    """A wearable concept no verified family engine builds, with the named reason."""

    def __init__(self, family: str, why: str):
        super().__init__(f"construction_unsupported:{family} -- {why}")
        self.family, self.why = family, why


# ---- facts and round pieces ----------------------------------------------------------------


@dataclass
class WFacts:
    """What a built size states beyond its rows; every gate re-checks these numbers."""

    construction: str
    pieces: dict[str, list[GF.Step]] = field(default_factory=dict)
    rounds: frozenset = frozenset()                     # pieces worked in joined rounds
    seams: list[dict] = field(default_factory=list)
    pickups: list[dict] = field(default_factory=list)
    numbers: dict[str, float] = field(default_factory=dict)
    buttons: int = 0

    def to_dict(self) -> dict:
        return {"construction": self.construction,
                "pieces": {k: [s.to_dict() for s in v] for k, v in self.pieces.items()},
                "rounds": sorted(self.rounds), "seams": self.seams, "pickups": self.pickups,
                "numbers": dict(self.numbers), "buttons": self.buttons}


def facts_of(cir: CIR) -> WFacts | None:
    f = getattr(cir, GF.FACTS_ATTR, None)
    return f if isinstance(f, WFacts) else None


class Rounds(GF.Piece):
    """A piece worked in joined rounds: no turning chain, every round joined with a sl st.

    Records the same `Step`s as a flat piece, plus round shaping kinds:
      even         plain rounds;
      section_dec  `sections` decreases spaced evenly round every round, `rounds` times
                   (a crown: the count falls by `sections` each round);
      section_inc  the same, increasing (a flat circle or a toe).
    """

    def _row(self, ops, *, skips=0, note=None) -> Row:
        merged = [op for op in ops if op.count > 0]
        row = Row(index=self.next_index, ops=merged, declared_count=None, turning_chain=0,
                  skips=skips, note=note)
        self.rows.append(row)
        return row

    def _sections(self, sections: int, rounds: int, *, grow: bool, label: str) -> None:
        if sections < 1 or rounds < 1:
            raise ShapingRefused(f"{self.name}: {rounds} rounds of {sections} sections")
        first = self.next_index
        for _ in range(rounds):
            if self.count % sections:
                raise ShapingRefused(f"{self.name}: {self.count} sts is not {sections} equal "
                                     f"sections")
            per = self.count // sections
            ops: list[Op] = []
            if grow:
                for _s in range(sections):
                    ops += ([Op(self.fam.stitch, per - 1)] if per > 1 else []) + [Op("inc", 1)]
                new = self.count + sections
            else:
                if per < 2:
                    raise ShapingRefused(f"{self.name}: a section of {per} st cannot decrease")
                for _s in range(sections):
                    ops += ([Op(self.fam.stitch, per - 2)] if per > 2 else []) + [Op("dec", 1)]
                new = self.count - sections
            self._finish(self._row(ops), new)
        self._record("section_inc" if grow else "section_dec", first, self.next_index - 1,
                     n=(("sections", sections), ("rounds", rounds)), label=label)

    def spread_dec(self, r: int, *, label: str = "") -> None:
        """One round decreasing `r` stitches spaced evenly round it (`r` may be 0 for some
        sizes of a design: the round is then worked plain, and the line says 0)."""
        i = self.next_index
        plain = self.count - 2 * r
        if plain < 0:
            raise ShapingRefused(f"{self.name}: {r} decreases on {self.count} sts")
        ops: list[Op] = []
        if r:
            base, extra = divmod(plain, r)
            for k in range(r):
                ops += ([Op(self.fam.stitch, base + (1 if k < extra else 0))]
                        if base + (1 if k < extra else 0) else []) + [Op("dec", 1)]
        else:
            ops = [Op(self.fam.stitch, self.count)]
        self._finish(self._row(ops, note=f"decrease {r} sts evenly"), self.count - r)
        self._record("spread_dec", i, i, n=(("dec", r),), label=label)

    def section_dec(self, sections: int, rounds: int, *, label: str = "") -> None:
        self._sections(sections, rounds, grow=False, label=label)

    def section_inc(self, sections: int, rounds: int, *, label: str = "") -> None:
        self._sections(sections, rounds, grow=True, label=label)

    def component(self, construction: str = "joined_rounds") -> Component:
        return Component(self.name, "joined_rounds", rows=self.rows, holds=self.holds,
                         **self.kw)


def flat_sections(g: GradedSize) -> int:
    """How many increases (or decreases) per round keep a disc of this fabric flat.

    A flat circle's circumference grows by 2*pi*(one round's height) per round; in stitches
    that is 2*pi * row_cm / stitch_cm. Derived from the gauge, never typed (sc at the house
    gauges gives 6)."""
    row_cm = 10.0 / g.gauge.rows_per_10cm
    st_cm = 10.0 / g.gauge.stitches_per_10cm
    return max(4, int(round(2 * math.pi * row_cm / st_cm)))


# ---- the spec, the engine, the design ------------------------------------------------------


@dataclass(frozen=True)
class WearableSpec:
    """One wearable design: what it is, who it is for, its family and its stated fit."""

    key: str
    title: str
    category: str                  # beanie | hat | ...
    family: str                    # an ENGINES key
    audience: str                  # baby | child | adult | all
    weight: str
    fibre: str
    ease_cm: tuple[tuple[str, float], ...]
    sizes: tuple[str, ...] | None = None
    version: str = "1.0.0"
    options: tuple[tuple[str, object], ...] = ()

    def option(self, name: str, default=None):
        return dict(self.options).get(name, default)


@dataclass(frozen=True)
class Engine:
    family: str
    title: str                                          # what the PDF calls the construction
    words: tuple[str, ...]                              # title words this family honestly is
    table: object                                       # cir.graded.BodyTable
    sizes: dict                                         # audience -> size names
    requires: tuple[str, ...]
    primary: str
    built_primary: str                                  # the built measure graded strictly
    builder: Callable                                   # (g, spec) -> CIR
    measure: Callable                                   # (cir) -> {name: cm}
    gates: Callable                                     # (ctx) -> [GarmentFinding]
    chart: tuple[tuple[str, str], ...]                  # (claim key, column heading)
    narrative: Callable                                 # (spec, facts) -> str
    schematic: Callable                                 # (sizes, [measures]) -> primitives
    notions: tuple[str, ...] = ("a tapestry needle",)
    risk: str = "B"
    chain_gauge: bool = False      # chains are worked into as fabric (chained-on stitches)
    fit_note: str = ""
    abbreviations: tuple[str, ...] = ("ch", "sc", "inc", "dec", "sk", "slst")
    closing: Callable | None = None                     # (facts list) -> finishing sentence
    where: tuple[tuple[str, str], ...] = ()             # pick-up piece -> where on the edge
    titles: tuple[tuple[str, str], ...] = ()            # piece -> heading
    tips: tuple[str, ...] = ()
    safety_note: str = ("It is made with no buttons, ties, cords or anything sewn on: every "
                        "piece is worked in or sewn flat.")
    category_word: str = ""
    # Concept routing (`spec_for`): the declared forms and constructions this family honestly
    # is, title words it refuses (each with its reason), and per-audience ease and yarn.
    forms: tuple[str, ...] = ()
    constructions: tuple[str, ...] = ()
    refuse: tuple[tuple[str, str], ...] = ()
    ease: tuple[tuple[str, tuple[tuple[str, float], ...]], ...] = ()
    yarn: tuple[tuple[str, tuple[str, str]], ...] = ()
    style_words: tuple[tuple[str, str], ...] = ()      # (regex, style option) from the text
    # Phrases that name what this engine really builds and that the shared feature
    # vocabulary (`construction_families.NAMED_FEATURES`) would otherwise read as a feature
    # it does not ("a ribbed brim" is the beanie's brim, not a rib-stitch fabric).
    honest_phrases: tuple[str, ...] = ()


ENGINES: dict[str, Engine] = {}


def register(engine: Engine) -> Engine:
    ENGINES[engine.family] = engine
    return engine


def engine_of(cir: CIR) -> Engine | None:
    prov = getattr(cir, "provenance", None)
    for p in (getattr(prov, "primitives_used", None) or ()):
        if str(p).startswith(MARKER + ":"):
            return ENGINES.get(str(p).split(":", 1)[1])
    return None


def construction_of(cir: CIR) -> str | None:
    e = engine_of(cir)
    return e.family if e is not None else None


def _material(spec: WearableSpec, gauge) -> Material:
    return Material(name=f"{spec.weight} {spec.fibre}", yarn_weight=gauge.yarn_weight)


def design(spec: WearableSpec) -> GradedDesign:
    """The graded design a wearable spec describes. Every size runs the same builder."""
    eng = ENGINES.get(spec.family)
    if eng is None:
        raise WearableRefused(spec.family, "no wearable engine of that name")
    gauge = GF._gauge(spec.weight)
    if eng.chain_gauge:
        # Chained-on stitches are worked into as fabric: the design states their gauge as
        # the fabric's, and the instructions say to chain loosely (as the one-piece sweater).
        import dataclasses
        gauge = dataclasses.replace(gauge, chains_per_10cm=gauge.stitches_per_10cm)
    sizes = spec.sizes or eng.sizes.get(spec.audience)
    if not sizes:
        raise WearableRefused(spec.family, f"the {spec.family} engine has no "
                                           f"{spec.audience} sizes")

    def template(g):
        return eng.builder(g, spec)

    d = GradedDesign(key=spec.key, title=spec.title, table=eng.table, gauge=gauge,
                     fit=FitIntent(dict(spec.ease_cm)), requires=eng.requires,
                     sizes=tuple(sizes), primitives=("cir.graded", f"{MARKER}:{spec.family}"),
                     template=template, measure=eng.measure, primary=eng.primary)
    d.spec = spec
    return d


def make_cir(g: GradedSize, spec: WearableSpec, *, comps, seams, facts: WFacts, designer: str,
             size_note: str, construction: str = "flat_rows") -> CIR:
    eng = ENGINES[spec.family]
    cir = CIR(slug=f"{spec.key}-{g.size.lower().replace(' ', '-').replace('.', '')}",
              title=f"{spec.title} (size {g.size})", version=spec.version,
              construction=construction, components=comps, gauge=g.gauge,
              materials=[_material(spec, g.gauge)], colors={}, risk_class=eng.risk,
              authored="brambleloop", assembly=seams, finished_size_note=size_note,
              designer_notes=designer)
    setattr(cir, GF.FACTS_ATTR, facts)
    return cir


def step_signature(cir: CIR) -> tuple:
    f = facts_of(cir)
    if f is None:
        return ()
    return tuple((name, tuple((s.kind, s.loop, s.label) for s in steps))
                 for name, steps in f.pieces.items())


def built_measures(cir: CIR) -> dict[str, float]:
    eng = engine_of(cir)
    if eng is None:
        raise ShapingRefused(f"{cir.slug} was not built by a wearable engine")
    return eng.measure(cir)


def _compiled(cir: CIR):
    from ..cir.compiler import compile_cir

    r = compile_cir(cir)
    if not r.ok:
        raise ShapingRefused(f"{cir.slug} does not compile: {[str(e) for e in r.errors][:1]}")
    return r


def _row_cm(g) -> float:
    return 10.0 / g.rows_per_10cm


def _st_cm(g) -> float:
    return 10.0 / g.stitches_per_10cm


# ==== 1. beanies and hats ===================================================================
#
# Bottom-up beanie: a back-loop rib brim worked flat side to side (the rows run round the
# head, so the ridges run up the brim like a rib) and seamed into a ring; the crown is picked
# up along one long edge of the ring and worked in joined rounds, straight to the crown, then
# decreased in `flat_sections` equal sections every round to `sections` stitches, which the
# tail gathers shut. The CYC head chart publishes circumference only, so height and brim are
# stated design ratios of the head:

HAT_HEIGHT_OF_HEAD = {"beanie": 0.36, "slouchy": 0.44}   # crown-to-brim, of the head
BRIM_OF_HEIGHT = 0.25                                     # brim depth, of the hat's height
HAT_EASE_CM = -2.0                                        # stated negative ease at the head
HAT_STRETCH_BAND_CM = (-5.0, 1.0)                         # built ease must stay inside this
HAT_HEIGHT_TOLERANCE = 0.08
HAT_SIZES = {"baby": ("Preemie", "Baby", "Toddler"), "child": ("Child", "Tween"),
             "adult": ("Woman", "Man"),
             "all": ("Preemie", "Baby", "Toddler", "Child", "Tween", "Woman", "Man")}


def beanie(g: GradedSize, spec: WearableSpec) -> CIR:
    fam = StitchFamily("sc", "plain")
    style = spec.option("style", "beanie")
    sections = flat_sections(g)
    target = g.finished_cm("head")
    n = g.stitches(target, minimum=2 * sections)            # the body, to one stitch
    setup = n % sections                                     # decreased away on round 1 of
    crown_from = n - setup                                   # the crown, so it divides
    circ_cm = n * _st_cm(g.gauge)
    height_cm = g.body_cm("head") * HAT_HEIGHT_OF_HEAD[style]
    brim_cm = height_cm * BRIM_OF_HEIGHT
    brim_sts = g.stitches(brim_cm, minimum=4)
    ring_rows = g.rows(circ_cm)
    if ring_rows % 2:
        ring_rows += 1
    crown_rounds = crown_from // sections - 1
    body_rounds = g.rows(height_cm - g.cm_of_stitches(brim_sts)) - crown_rounds - 1
    if body_rounds < 2:
        raise ShapingRefused(f"size {g.size}: no straight rounds between brim and crown")

    brim = GF.Piece("brim", fam, foundation=brim_sts, grain="across", feature="band",
                    direction="side_to_side",
                    note="worked flat side to side; the rows run round the head")
    brim.even(ring_rows, loop="back", label="brim")
    crown = Rounds("crown", fam, foundation=n, feature="body", direction="bottom_up",
                   foundation_kind="none",
                   note="picked up along one long edge of the brim ring and worked in "
                        "joined rounds to the crown")
    crown.even(body_rounds, label="body")
    crown.spread_dec(setup, label="set-up for the crown")
    crown.section_dec(sections, crown_rounds, label="crown")
    comp_brim, comp_crown = brim.component(), crown.component()
    seams = [
        Seam("mattress", "brim", "brim", edge_a="left", edge_b="right",
             note="fold the brim into a ring and sew its last row to its foundation chain, "
                  "through both loops; bury the tails"),
        Seam("pick_up", "crown", "brim", edge_a="bottom", edge_b="top",
             note=f"pick up {n} sts evenly along one long edge of the brim ring, one st in "
                  f"each row end and skipping where the rate says, join with a sl st"),
    ]
    facts = WFacts("hat", pieces={"brim": brim.steps, "crown": crown.steps},
                   rounds=frozenset({"crown"}))
    facts.pickups = [{"piece": "crown", "into": "brim", "edge_rows": ring_rows,
                      "edge_cm": round(g.cm_of_rows(ring_rows), 2), "stitches": n,
                      "rows_along": ring_rows}]
    facts.seams = [{"seam": "brim ring", "a": "brim(last row)", "b": "brim(foundation)",
                    "a_sts": brim_sts, "b_sts": brim_sts, "a_edge_sts": brim_sts,
                    "b_edge_sts": brim_sts}]
    facts.numbers = {"sections": sections, "closing_sts": sections, "brim_sts": brim_sts,
                     "ring_rows": ring_rows, "target_height_cm": round(height_cm, 2),
                     "target_circ_cm": target}
    return make_cir(g, spec, comps=[comp_brim, comp_crown], seams=seams, facts=facts,
                    construction="joined_rounds",
                    designer=(f"A {'slouchy ' if style == 'slouchy' else ''}beanie worked "
                              f"bottom up: a back-loop rib brim worked side to side and "
                              f"seamed into a ring, the crown picked up and worked in joined "
                              f"rounds, decreased in {sections} sections and gathered shut."),
                    size_note=f"Finished circumference {circ_cm:.1f} cm (unstretched), to "
                              f"fit head {g.body_cm('head'):g} cm")


def hat_measures(cir: CIR) -> dict[str, float]:
    """Circumference (unstretched), height and brim depth, from the compiled rows."""
    from ..cir.geometry import _row_height_cm

    r = _compiled(cir)
    g = cir.gauge
    crown = [x for x in r.rows if x.component == "crown"]
    brim_rows = [x for x in r.rows if x.component == "brim"]
    circ = max(x.stitch_count for x in crown) * _st_cm(g)
    brim = brim_rows[0].stitch_count * _st_cm(g)
    comp = next(c for c in cir.components if c.name == "crown")
    rounds = sum(_row_height_cm(row, cir) for row in comp.rows)
    return {"circumference": round(circ, 2), "height": round(brim + rounds, 2),
            "brim": round(brim, 2), "brim_ring": round(len(brim_rows) * _row_cm(g), 2)}


def hat_gates(ctx) -> list:
    """Circumference, stretch, height, crown flatness and closure, brim ring and pick-up."""
    from ..gates.garment_fit import GarmentFinding

    out = []
    g, m, f, size = ctx["g"], ctx["measured"], ctx["facts"], ctx["size"]
    res = ctx["result"]

    def bad(code, msg):
        out.append(GarmentFinding(code, size, msg))

    sections = int(f.numbers["sections"])
    half_st = 0.5 * _st_cm(g.gauge) + 0.05
    target = g.finished_cm("head")
    if abs(m["circumference"] - target) > half_st:
        bad("HAT_CIRCUMFERENCE", f"built {m['circumference']:.1f} cm against the target "
                                 f"{target:g} cm (head + ease); whole stitches allow at most "
                                 f"{half_st:.2f} cm")
    ease = m["circumference"] - g.body_cm("head")
    lo, hi = HAT_STRETCH_BAND_CM
    if not lo <= ease <= hi:
        bad("HAT_STRETCH_OUT_OF_BAND", f"built ease {ease:+.1f} cm is outside the beanie's "
                                       f"stretch band {lo:g} to {hi:+g} cm")
    want_h = float(f.numbers["target_height_cm"])
    if abs(m["height"] - want_h) / want_h > HAT_HEIGHT_TOLERANCE:
        bad("HAT_HEIGHT", f"built height {m['height']:.1f} cm against the stated "
                          f"{want_h:.1f} cm, more than {HAT_HEIGHT_TOLERANCE:.0%}")
    flat = flat_sections(g)
    if sections != flat:
        bad("HAT_CROWN_SHAPE", f"the crown decreases in {sections} sections; this gauge lies "
                               f"flat at {flat}: the crown would cone or ruffle")
    crown = [x for x in res.rows if x.component == "crown"]
    from ..cir.geometry import CLOSEABLE_STITCHES

    last = crown[-1].stitch_count
    if last > CLOSEABLE_STITCHES or last != int(f.numbers["closing_sts"]):
        bad("HAT_CROWN_OPEN", f"the crown ends on {last} sts; the tail gathers at most "
                              f"{CLOSEABLE_STITCHES} shut, and the pattern says "
                              f"{int(f.numbers['closing_sts'])}")
    ring = len([x for x in res.rows if x.component == "brim"])
    if ring != int(f.numbers["ring_rows"]) or ring % 2:
        bad("HAT_BRIM_RING", f"the brim has {ring} rows; the ring needs "
                             f"{int(f.numbers['ring_rows'])} (an even number, so the seam "
                             f"meets rib to rib)")
    out += pickup_rate(ctx)
    return out


def pickup_rate(ctx) -> list:
    """Every pick-up starts on the stitches it says and lies within MAX_PICKUP_DRIFT of the
    edge it is worked into, the edge recomputed from that piece's compiled rows."""
    from ..gates.garment_fit import GarmentFinding

    out = []
    cir, res, f, size = ctx["cir"], ctx["result"], ctx["facts"], ctx["size"]
    counts = {(r.component, r.index): r.stitch_count for r in res.rows}
    comps = {c.name: c for c in cir.components}
    for p in f.pickups:
        comp = comps.get(p["piece"])
        if comp is None:
            out.append(GarmentFinding("GARMENT_PICKUP_RATE", size, f"{p['piece']} is not a "
                                                                   f"piece"))
            continue
        first = counts.get((comp.name, comp.rows[0].index))
        if comp.foundation != p["stitches"] or first != p["stitches"]:
            out.append(GarmentFinding(
                "GARMENT_PICKUP_RATE", size,
                f"{comp.name} says it picks up {p['stitches']} sts; it starts on "
                f"{comp.foundation} and its first round counts {first}"))
        into_rows = [r for r in res.rows if r.component == p["into"]]
        if "edge_rows" in p:
            edge = len(into_rows) * _row_cm(cir.gauge)
            if len(into_rows) != p["edge_rows"]:
                out.append(GarmentFinding("GARMENT_PICKUP_RATE", size,
                                          f"{comp.name}: the edge has {len(into_rows)} rows, "
                                          f"the pattern says {p['edge_rows']}"))
        else:
            edge = float(p["edge_sts"]) * _st_cm(cir.gauge)
        made = p["stitches"] * _st_cm(cir.gauge)
        drift = abs(made - edge) / max(edge, 1e-9)
        if drift > GF.MAX_PICKUP_DRIFT:
            out.append(GarmentFinding(
                "GARMENT_PICKUP_RATE", size,
                f"{comp.name}: {p['stitches']} sts is {made:.1f} cm along a {edge:.1f} cm "
                f"edge ({drift:.1%}, at most {GF.MAX_PICKUP_DRIFT:.0%})"))
    return out


def hat_narrative(spec: WearableSpec, facts: WFacts) -> str:
    s = int(facts.numbers["sections"])
    return ("The brim comes first: a narrow strip worked flat in rows through the back loop, "
            "so the ridges stand up like ribbing, long enough to go round the head. Its ends "
            "are sewn together into a ring. The body is picked up along one edge of the ring "
            "and worked upwards in joined rounds, then the crown is decreased in "
            f"{s} equal sections on every round until {s} stitches remain, and the tail "
            "gathers them shut.")


def _fmt(values) -> str:
    xs = [f"{v:g}" for v in values]
    return xs[0] if len(set(xs)) == 1 else f"{xs[0]} ({', '.join(xs[1:])})"


def _schematic(items, legend, width, height, sizes, ms, kind) -> dict:
    return {"width": width, "height": height, "items": items, "sizes": list(sizes),
            "legend": legend, "measures": dict(zip(sizes, ms)), "kind": kind}


class Sketch:
    """Builds schematic primitives (the `publish.garment_schematic` format) with a legend."""

    def __init__(self, ms: list[dict], names: dict[str, str]):
        self.ms, self.names = ms, names
        self.items: list[dict] = []
        self.legend: list[tuple[str, str, str]] = []

    def lab(self, key) -> str:
        return f"{_fmt([round(m[key], 1) for m in self.ms])} cm"

    def poly(self, points, name):
        self.items.append({"kind": "poly", "name": name, "points": list(points)})

    def line(self, a, b, heavy=False):
        self.items.append({"kind": "line", "from": a, "to": b, "heavy": heavy})

    def text(self, at, s):
        self.items.append({"kind": "text", "at": at, "label": s})

    def dim(self, a, b, key, side):
        letter = "ABCDEFGHIJ"[len([x for x in self.legend if x[0]])]
        self.legend.append((letter, self.names[key], self.lab(key)))
        self.items.append({"kind": "dim", "from": a, "to": b, "label": letter, "side": side,
                           "key": key})

    def note(self, key):
        self.legend.append(("", self.names[key], self.lab(key)))


def hat_schematic(sizes, ms) -> dict:
    sk = Sketch(ms, {"half_circ": "Half circumference, laid flat (unstretched)",
                     "height": "Height, brim to crown", "brim": "Brim depth"})
    for m in ms:
        m["half_circ"] = round(m["circumference"] / 2.0, 1)
    mid = ms[len(ms) // 2]
    W, H, B = mid["half_circ"], mid["height"], mid["brim"]
    x0, y0 = 4.0, 6.0
    crown_h = min(W / 2.0, H - B) * 0.6
    sk.poly([(x0, y0 + crown_h), (x0 + W * 0.2, y0), (x0 + W * 0.8, y0),
             (x0 + W, y0 + crown_h), (x0 + W, y0 + H), (x0, y0 + H)], "hat, laid flat")
    sk.line((x0, y0 + H - B), (x0 + W, y0 + H - B))
    sk.dim((x0, y0 + H), (x0 + W, y0 + H), "half_circ", "below")
    sk.dim((x0 + W, y0), (x0 + W, y0 + H), "height", "right")
    sk.dim((x0, y0 + H - B), (x0, y0 + H), "brim", "left")
    sk.text((x0 + W / 2.0, y0 + H - B / 2.0), "brim (rows run up)")
    sk.text((x0 + W / 2.0, y0 + (H - B) / 2.0 + 1), "rounds")
    return _schematic(sk.items, sk.legend, W + 2 * x0 + 10, H + 2 * y0 + 4, sizes, ms, "hat")


register(Engine(
    family="hat_beanie", title="a back-loop rib brim worked flat and seamed into a ring; the "
                               "crown picked up and worked in joined rounds",
    words=("beanie", "beanies", "hat", "hats", "toque", "toques", "tuque", "tuques"),
    table=HEAD, sizes=HAT_SIZES, requires=("head",), primary="head",
    built_primary="circumference", builder=beanie, measure=hat_measures, gates=hat_gates,
    chart=(("body_cm", "To fit head"), ("circumference_cm", "Finished circumference"),
           ("ease_cm", "Ease"), ("height_cm", "Height"), ("brim_cm", "Brim")),
    narrative=hat_narrative, schematic=hat_schematic,
    fit_note=("A beanie is made a little smaller than the head so it stays on: "
              f"{HAT_EASE_CM:+g} cm of stated ease at the head (negative ease), and every "
              f"size's built ease stays between {HAT_STRETCH_BAND_CM[0]:g} and "
              f"{HAT_STRETCH_BAND_CM[1]:+g} cm."),
    abbreviations=("ch", "sc", "dec", "slst"),
    closing=lambda facts: (
        "Crown: cut the yarn leaving a 20 cm tail, thread it through the front loop of each "
        f"of the last {_values([int(f.numbers['closing_sts']) for f in facts])} sts, "
        "pull tight to gather the crown shut, and fasten off securely on the wrong side."),
    where=(("crown", "one long edge of the brim ring (the row ends), one stitch into each "
                     "row end, skipping evenly"),),
    tips=("Swatch in the round for the body and flat in back-loop rows for the brim; both "
          "are worked at the same gauge.",
          "Try the brim ring round your head before you pick up the body: it should sit "
          "snugly without stretching hard.",
          "Mark the first stitch of every round with a locking marker and move it up as you "
          "go; the joins make a faint line up the back of the hat.",
          "Count every round of the crown: each has one stitch fewer in every section."),
    safety_note=("It is made with no ties, cords, pom-poms or anything sewn on: the brim is "
                 "sewn into a ring and the body is picked up and worked into it."),
    category_word="hat",
    forms=("hat", "fitted_garment"), constructions=("in_the_round", "seamless_tube",
                                                    "bottom_up"),
    refuse=((r"\b(?:bucket|sun|brimmed|cloche|beret|balaclava|helmet|bonnet|earflaps?|"
             r"ear flaps?|visor|cap|caps|headband|ear warmer|turban|trapper|hood(?:ed|ie)?)\b",
             "a shaped brim, flap, visor or headband is a different construction; the beanie "
             "engine builds a rib brim and a round crown only"),),
    ease=tuple((a, (("head", HAT_EASE_CM),)) for a in ("baby", "child", "adult")),
    yarn=(("baby", ("dk", "cotton")), ("child", ("dk", "cotton")),
          ("adult", ("worsted", "wool"))),
    style_words=((r"\bslouch(?:y|ie)?\b", "slouchy"),),
    honest_phrases=(r"\b(?:turned |folded )?ribb?(?:ed|ing)?[- ]?(?:brim(?:med)?|band)\b",)))


# ---- the size chart a family prints, from each size's twin --------------------------------


def size_claims(design, cirs: dict) -> list[dict]:
    """Per size: the body measurement it fits, every chart figure from the twin, yardage."""
    from ..cir.graded import measure_size

    eng = ENGINES[design.spec.family]
    rows = []
    for size, cir in cirs.items():
        g = design.graded_size(size)
        m = measure_size(cir, eng.measure)
        built = m["built_cm"]
        body = g.body_cm(eng.primary)
        row = {"size": size, "body_cm": body}
        for key, _head in eng.chart:
            if key in ("body_cm",):
                continue
            if key == "ease_cm":
                row[key] = round(built[eng.built_primary] - body, 1)
            else:
                row[key] = built[key[:-3]]
        row.update(GF.balls_and_yards(m["yarn_m"], cir.gauge.yarn_weight or ""))
        rows.append(row)
    return rows


# ---- the release ---------------------------------------------------------------------------


@dataclass
class WearableRelease:
    spec: WearableSpec
    design: object
    cirs: dict = field(default_factory=dict)
    certificates: dict = field(default_factory=dict)
    verdict: object = None
    claims: list = field(default_factory=list)

    @property
    def engine(self) -> Engine:
        return ENGINES[self.spec.family]

    @property
    def sizes(self) -> tuple[str, ...]:
        return tuple(self.cirs)

    @property
    def granted(self) -> bool:
        return (bool(self.certificates) and all(c.granted for c in self.certificates.values())
                and self.verdict is not None and self.verdict.ok)

    def reasons(self) -> list[str]:
        out = []
        for size, c in self.certificates.items():
            out += [f"size {size}: {f.code}: {f.message}" for f in c.findings
                    if f.severity == "ERROR"]
        if self.verdict is not None:
            out += [str(f) for f in self.verdict.findings]
        return out


def build(spec: WearableSpec) -> WearableRelease:
    d = design(spec)
    return WearableRelease(spec=spec, design=d,
                           cirs={s: d.build(s) for s in d.sourced_sizes()})


def certify(release: WearableRelease, *, physical_evidence: list[dict] | None = None,
            claims: list[dict] | None = None) -> WearableRelease:
    from ..gates import certificate
    from ..gates import wearable_fit

    for size, cir in release.cirs.items():
        release.certificates[size] = certificate.certify(cir,
                                                         physical_evidence=physical_evidence)
    release.claims = claims if claims is not None else size_claims(release.design,
                                                                   release.cirs)
    release.verdict = wearable_fit.evaluate(release.design, release.cirs,
                                            claims=release.claims)
    return release


# ---- concept -> spec (a table, never a model's guess) ---------------------------------------

import re as _re


def audience_for(recipient: str) -> str:
    return {"new_parent": "baby", "child": "child", "teen": "child"}.get(recipient, "adult")


def family_for(form: str, title: str) -> str | None:
    """The wearable family whose words the title names and whose forms include `form`."""
    from ..creative.fallback_constructions import fold_title

    folded = fold_title(title)
    for eng in ENGINES.values():
        if form in eng.forms and any(_re.search(rf"\b{_re.escape(w)}\b", folded)
                                     for w in eng.words):
            return eng.family
    return None


def spec_for(concept) -> WearableSpec:
    """The wearable spec a concept describes, or WearableRefused naming what is missing."""
    from ..creative.fallback_constructions import fold_title

    family = family_for(concept.form, concept.title or "")
    if family is None:
        raise WearableRefused("wearable", f"no wearable engine builds a {concept.form!r} "
                                          f"titled {concept.title!r}")
    eng = ENGINES[family]
    if concept.construction not in eng.constructions:
        raise WearableRefused(family, f"the {family} engine does not work the "
                                      f"{concept.construction!r} construction")
    text = fold_title(f"{concept.title} {concept.premise} {getattr(concept, 'notes', '')}")
    for rx, why in eng.refuse:
        hit = _re.search(rx, text)
        if hit:
            raise WearableRefused(family, f"the concept names {hit.group(0)!r}: {why}")
    audience = audience_for(concept.recipient)
    ease = dict(eng.ease).get(audience)
    yarn = dict(eng.yarn).get(audience)
    if ease is None or yarn is None or audience not in eng.sizes:
        raise WearableRefused(family, f"the {family} engine is not graded for {audience}")
    options = tuple((opt, True if opt is None else opt) for rx, opt in eng.style_words
                    if _re.search(rx, text))
    options = tuple(("style", o) for _k, o in options)
    category = concept.category if getattr(concept, "category", None) else (
        eng.category_word or family)
    return WearableSpec(concept.key, concept.title, category, family, audience, yarn[0],
                        yarn[1], ease, options=options)


def from_concept(concept) -> WearableRelease:
    return certify(build(spec_for(concept)))


# ==== 2. baby rompers, dresses and pinafores ================================================
#
# Front and back are the same panel (make 2), worked bottom up in flat rows. A dress starts
# at the hem with a back-loop band and decreases evenly up the skirt to the chest (A-line); a
# romper starts at a narrow crotch gusset, chains on at both sides for the hips (the edges of
# the gusset and the chains are the leg openings), and decreases to the chest. Both finish
# with a back-loop chest band at the underarm line and a square neck: the first shoulder is
# worked up on the first stitches while the last are held for the second shoulder (resumed as
# its own piece) and the centre is left unworked. Front and back meet at the shoulders and
# down the sides below the underarm; a romper's gussets are sewn together. Pull-on: no
# buttons, snaps or ties (child-safety rule for under-3s), so the neck opening must pass a
# head: its perimeter is checked against the CYC head chart's largest under-3 head (Toddler,
# 46 cm, upper bound). Proportions the baby chart does not publish are stated design ratios:

DRESS_LENGTH_OF_BACK = {"dress": 2.0, "pinafore": 1.8}   # shoulder to hem, of back length
DRESS_HEM_OF_CHEST = {"dress": 1.35, "pinafore": 1.2}    # A-line hem, of the finished chest
ROMPER_RISE_OF_BACK = 0.6                                 # waist to crotch, of back length
ROMPER_GUSSET_OF_HIP = 0.25                               # crotch gusset, of the half hip
ROMPER_GUSSET_ROWS_CM = 3.0
NECK_OF_CROSS_BACK_BABY = 0.75                            # square neck, of the cross-back
BAND_ROWS_CM = 2.0                                        # chest and hem band depth (baby)
LEG_OPENING_OF_HIP = 0.45                                 # a leg opening, at least, of the hip
PULLOVER_HEAD_CM = 46.0      # CYC head chart, Toddler upper bound: the largest under-3 head
BABY_EASE = (("bust", 10.0), ("hip", 14.0), ("back_length", 0.0), ("armhole_depth", 2.0))
BODICE_LENGTH_TOLERANCE = 0.08


def _split(p: GF.Piece, keep: int, hold: int, *, hold_name: str, label: str) -> None:
    """One row working the first `keep` sts; the last `hold` sts are held for `hold_name` and
    the stitches between are left unworked (a square neck's centre)."""
    from ..cir.model import Hold

    last = p.rows[-1].index
    p.holds.append(Hold(hold_name, at_row=last, count=hold, from_stitch=p.count - hold,
                        note="the second shoulder's stitches wait while the first is worked"))
    i = p.next_index
    row = p._row([Op(p.fam.stitch, keep, loop=p.loop_for(None, i))], skips=p.count - keep,
                 note=f"work {keep} sts; hold the last {hold}; leave the centre unworked")
    p._finish(row, keep)
    p._record("split", i, i, n=(("keep", keep), ("hold", hold),
                                ("centre", p.count + 0 if False else 0)), label=label)


def _top(g: GradedSize, fam, p: GF.Piece, width: int) -> tuple:
    """Chest band, square neck and two shoulders; returns (shoulder piece, numbers)."""
    band = g.rows(BAND_ROWS_CM, minimum=2)
    p.even(band, loop="back", label="chest band")
    neck = g.stitches(g.body_cm("cross_back") * NECK_OF_CROSS_BACK_BABY)
    if (width - neck) % 2:
        neck += 1
    sh = (width - neck) // 2
    if sh < 3:
        raise ShapingRefused(f"size {g.size}: shoulders of {sh} sts")
    rows = g.rows(g.finished_cm("armhole_depth"), minimum=4)
    _split(p, sh, sh, hold_name="shoulder", label="first shoulder")
    p.even(rows - 1, label="first shoulder")
    s = GF.Piece("shoulder", fam, foundation=sh, make=2, resumes="shoulder", feature="body",
                 direction="bottom_up")
    s.even(rows, label="second shoulder")
    return s, {"neck": neck, "shoulder": sh, "shoulder_rows": rows, "band": band}


def baby_dress(g: GradedSize, spec: WearableSpec) -> CIR:
    fam = StitchFamily("sc", "plain")
    style = spec.option("style", "dress")
    width = g.stitches(g.finished_cm("bust") / 2.0)
    total_cm = g.body_cm("back_length") * DRESS_LENGTH_OF_BACK[style]
    band = g.rows(BAND_ROWS_CM, minimum=2)
    arm_rows = g.rows(g.finished_cm("armhole_depth"), minimum=4)
    bodice_rows = max(2, g.rows(g.body_cm("back_length") - g.finished_cm("armhole_depth"))
                      - band)
    skirt_rows = g.rows(total_cm) - arm_rows - band - bodice_rows - band
    if skirt_rows < 4:
        raise ShapingRefused(f"size {g.size}: no skirt below the waist")
    events, every = GF.uniform(max(1, (g.stitches(g.finished_cm("bust") / 2.0
                                                  * DRESS_HEM_OF_CHEST[style]) - width) // 2),
                               skirt_rows - 1)
    hem = width + 2 * events
    p = GF.Piece("panel", fam, foundation=hem, make=2, feature="panel", direction="bottom_up",
                 note="front and back are the same panel, worked from the hem up")
    p.even(band, loop="back", label="hem band")
    used = 0
    if events:
        p.shape(events, every, grow=False, label="skirt decreases")
        used = (events - 1) * every + 1
    if skirt_rows - used > 0:
        p.even(skirt_rows - used, label="skirt")
    p.even(bodice_rows, label="bodice")
    s, n = _top(g, fam, p, width)
    below = band + skirt_rows + bodice_rows + n["band"]
    seams = [
        Seam("whipstitch", "panel", "panel", edge_a="top", edge_b="top",
             note=f"lay the front on the back, right sides out, and sew the first shoulders "
                  f"together, {n['shoulder']} sts each, through both loops"),
        Seam("whipstitch", "shoulder", "shoulder", edge_a="top", edge_b="top",
             note=f"sew the second shoulders together the same way, {n['shoulder']} sts each"),
        Seam("mattress", "panel", "panel", edge_a="left", edge_b="left", at_round=1,
             spans_rounds=below, mirrored=True,
             note=f"join each side from the hem to the top of the chest band ({below} rows), "
                  f"leaving the shoulders' side edges open for the armholes; bury the tails"),
    ]
    facts = WFacts("baby_dress", pieces={"panel": p.steps, "shoulder": s.steps})
    facts.seams = [{"seam": "side", "a": "front", "b": "back", "a_rows": below,
                    "b_rows": below, "a_edge_rows": len(p.rows), "b_edge_rows": len(p.rows)},
                   {"seam": "shoulder", "a": "first shoulder", "b": "second shoulder",
                    "a_rows": n["shoulder_rows"], "b_rows": len(s.rows),
                    "a_edge_rows": n["shoulder_rows"], "b_edge_rows": len(s.rows)},
                   {"seam": "shoulder top", "a": "front shoulder", "b": "back shoulder",
                    "a_sts": n["shoulder"], "b_sts": n["shoulder"],
                    "a_edge_sts": n["shoulder"], "b_edge_sts": n["shoulder"]}]
    facts.numbers = {"width": width, "target_length_cm": round(total_cm, 2), "hem": hem,
                     **n}
    word = "pinafore" if style == "pinafore" else "dress"
    return make_cir(g, spec, comps=[p.component(), s.component()], seams=seams, facts=facts,
                    designer=(f"A pull-on A-line baby {word} worked bottom up in two identical "
                              f"panels with back-loop hem and chest bands, a square neck and "
                              f"shoulders seamed at the top."),
                    size_note=f"Finished chest {2 * width * _st_cm(g.gauge):.0f} cm, to fit "
                              f"chest {g.body_cm('bust'):g} cm")


def baby_romper(g: GradedSize, spec: WearableSpec) -> CIR:
    fam = StitchFamily("sc", "plain")
    width = g.stitches(g.finished_cm("bust") / 2.0)
    half_hip = g.stitches(g.finished_cm("hip") / 2.0)
    gusset = max(4, g.stitches(g.finished_cm("hip") / 2.0 * ROMPER_GUSSET_OF_HIP))
    if (half_hip - gusset) % 2:
        gusset += 1
    extra = (half_hip - gusset) // 2
    # The hips must come in to the chest in whole decrease pairs, at least one.
    if (half_hip - width) % 2:
        width += 1
    if half_hip - width < 2:
        half_hip = width + 2
        if (half_hip - gusset) % 2:
            gusset += 1
        extra = (half_hip - gusset) // 2
    back = g.body_cm("back_length")
    g_rows = g.rows(ROMPER_GUSSET_ROWS_CM, minimum=2)
    band = g.rows(BAND_ROWS_CM, minimum=2)
    rise_rows = g.rows(back * ROMPER_RISE_OF_BACK) - g_rows - 2
    bodice_rows = g.rows(back - g.finished_cm("armhole_depth")) - band
    if rise_rows < 2 or bodice_rows < 2:
        raise ShapingRefused(f"size {g.size}: no body between the crotch and the chest")
    p = GF.Piece("panel", fam, foundation=gusset, make=2, feature="panel",
                 direction="bottom_up", note="front and back are the same panel, worked from "
                                             "the crotch up")
    p.even(g_rows, label="gusset")
    p.chain_on(extra, label="hips")
    p.even(rise_rows, label="hips")
    events, every = GF.uniform(max(1, (half_hip - width) // 2), bodice_rows - 1)
    used = 0
    if events:
        p.shape(events, every, grow=False, label="bodice decreases")
        used = (events - 1) * every + 1
    if bodice_rows - used > 0:
        p.even(bodice_rows - used, label="bodice")
    width = half_hip - 2 * events
    s, n = _top(g, fam, p, width)
    below = 2 + rise_rows + bodice_rows + n["band"]
    seams = [
        Seam("whipstitch", "panel", "panel", edge_a="bottom", edge_b="bottom",
             note=f"sew the front gusset to the back gusset across the foundation chains, "
                  f"{gusset} sts each, through both loops"),
        Seam("whipstitch", "panel", "panel", edge_a="top", edge_b="top",
             note=f"sew the first shoulders together, {n['shoulder']} sts each"),
        Seam("whipstitch", "shoulder", "shoulder", edge_a="top", edge_b="top",
             note=f"sew the second shoulders together the same way, {n['shoulder']} sts each"),
        Seam("mattress", "panel", "panel", edge_a="left", edge_b="left",
             at_round=g_rows + 1, spans_rounds=below, mirrored=True,
             note=f"join each side from the hips to the top of the chest band ({below} rows), "
                  f"leaving the gusset edges open for the legs and the shoulders' side edges "
                  f"open for the armholes"),
    ]
    facts = WFacts("baby_romper", pieces={"panel": p.steps, "shoulder": s.steps})
    leg_cm = 2 * (g.cm_of_rows(g_rows) + g.cm_of_stitches(extra))
    facts.seams = [{"seam": "side", "a": "front", "b": "back", "a_rows": below,
                    "b_rows": below, "a_edge_rows": len(p.rows), "b_edge_rows": len(p.rows)},
                   {"seam": "gusset", "a": "front gusset", "b": "back gusset",
                    "a_sts": gusset, "b_sts": gusset, "a_edge_sts": gusset,
                    "b_edge_sts": gusset},
                   {"seam": "shoulder", "a": "first shoulder", "b": "second shoulder",
                    "a_rows": n["shoulder_rows"], "b_rows": len(s.rows),
                    "a_edge_rows": n["shoulder_rows"], "b_edge_rows": len(s.rows)}]
    total = back * (1 + ROMPER_RISE_OF_BACK)
    facts.numbers = {"width": width, "target_length_cm": round(total, 2), "hip": half_hip,
                     "gusset": gusset, "leg_opening_cm": round(leg_cm, 2), **n}
    return make_cir(g, spec, comps=[p.component(), s.component()], seams=seams, facts=facts,
                    designer=("A pull-on sleeveless baby romper worked bottom up in two "
                              "identical panels: a crotch gusset, the hips chained on at both "
                              "sides, decreased to a back-loop chest band, a square neck and "
                              "shoulders seamed at the top."),
                    size_note=f"Finished chest {2 * width * _st_cm(g.gauge):.0f} cm, to fit "
                              f"chest {g.body_cm('bust'):g} cm")


def babywear_measures(cir: CIR) -> dict[str, float]:
    """Chest, widest (hem or hip), length shoulder to hem, armhole and neck perimeter."""
    from ..cir.geometry import _row_height_cm

    r = _compiled(cir)
    g = cir.gauge
    f = facts_of(cir)
    panel = [x for x in r.rows if x.component == "panel"]
    pcomp = next(c for c in cir.components if c.name == "panel")
    heights = [_row_height_cm(row, cir) for row in pcomp.rows]
    split = next(s for s in f.pieces["panel"] if s.kind == "split").first
    chest_row = panel[split - 2]
    chest = 2 * chest_row.stitch_count * _st_cm(g)
    widest = 2 * max(x.stitch_count for x in panel) * _st_cm(g)
    arm = sum(heights[split - 1:])
    neck_w = (chest_row.stitch_count - 2 * panel[split - 1].stitch_count) * _st_cm(g)
    return {"chest": round(chest, 2), "widest": round(widest, 2),
            "length": round(sum(heights), 2), "armhole": round(arm, 2),
            "neck_opening": round(2 * neck_w + 4 * arm, 2)}


def babywear_gates(ctx) -> list:
    from ..gates.garment_fit import CHEST_TOLERANCE, GarmentFinding

    out = []
    g, m, f, size = ctx["g"], ctx["measured"], ctx["facts"], ctx["size"]

    def bad(code, msg):
        out.append(GarmentFinding(code, size, msg))

    want = g.finished_cm("bust")
    tol = max(CHEST_TOLERANCE, 2 * _st_cm(g.gauge) / want)
    if abs(m["chest"] - want) / want > tol:
        bad("GARMENT_FINISHED_OFF_TARGET", f"built chest {m['chest']:.1f} cm against "
                                           f"{want:g} cm, more than {tol:.0%}")
    if m["chest"] < g.body_cm("bust"):
        bad("GARMENT_FINISHED_OFF_TARGET", "the chest is smaller than the body")
    if f.construction == "baby_romper":
        if m["widest"] + 2 * _st_cm(g.gauge) < g.finished_cm("hip"):
            bad("GARMENT_HIP_FIT", f"the romper is {m['widest']:.1f} cm round the hips; the "
                                   f"finished hip is {g.finished_cm('hip'):g} cm")
        leg = float(f.numbers["leg_opening_cm"])
        if leg < LEG_OPENING_OF_HIP * g.finished_cm("hip"):
            bad("GARMENT_LEG_FIT", f"a leg opening is {leg:.1f} cm round, under "
                                   f"{LEG_OPENING_OF_HIP:.0%} of the finished hip")
    want_len = float(f.numbers["target_length_cm"])
    if abs(m["length"] - want_len) / want_len > BODICE_LENGTH_TOLERANCE:
        bad("GARMENT_FINISHED_OFF_TARGET", f"built length {m['length']:.1f} cm against the "
                                           f"stated {want_len:.1f} cm")
    if m["armhole"] + 1e-9 < g.body_cm("armhole_depth"):
        bad("GARMENT_ARMHOLE_FIT", f"the armhole is {m['armhole']:.1f} cm deep; the body's "
                                   f"armhole depth is {g.body_cm('armhole_depth'):g} cm")
    if m["neck_opening"] < PULLOVER_HEAD_CM:
        bad("GARMENT_NECK_FIT", f"the neck opening is {m['neck_opening']:.1f} cm round; a "
                                f"pull-on garment must pass a {PULLOVER_HEAD_CM:g} cm head "
                                f"(CYC head chart, Toddler upper bound)")
    neck = int(f.numbers["neck"]) * _st_cm(g.gauge)
    cross = g.body_cm("cross_back")
    if not 0.55 <= neck / cross <= 1.0:
        bad("GARMENT_NECK_FIT", f"the square neck is {neck:.1f} cm across, "
                                f"{neck / cross:.2f} of the {cross:g} cm cross-back")
    if f.buttons:
        bad("GARMENT_CLOSURES", "a baby garment is pull-on: no buttons, snaps or ties")
    return out


def _babywear_schematic(sizes, ms) -> dict:
    sk = Sketch(ms, {"half_chest": "Half chest, finished", "half_widest": "Half hem / hip",
                     "length": "Length, shoulder to hem", "armhole": "Armhole depth"})
    for m in ms:
        m["half_chest"] = round(m["chest"] / 2.0, 1)
        m["half_widest"] = round(m["widest"] / 2.0, 1)
    mid = ms[len(ms) // 2]
    W, H, L, A = mid["half_chest"], mid["half_widest"], mid["length"], mid["armhole"]
    x0, y0 = 6.0, 6.0
    top = y0 + A
    left = x0 + max(0.0, (H - W) / 2.0)
    sh = W * 0.2
    sk.poly([(left, y0), (left + sh, y0), (left + sh, top), (left + W - sh, top),
             (left + W - sh, y0), (left + W, y0), (left + W, top), (x0 + H, y0 + L),
             (x0, y0 + L), (left, top)], "panel (front; the back is the same)")
    sk.dim((left, top), (left + W, top), "half_chest", "above")
    sk.dim((x0, y0 + L), (x0 + H, y0 + L), "half_widest", "below")
    sk.dim((x0 + H + 1, y0), (x0 + H + 1, y0 + L), "length", "right")
    sk.dim((left - 1, y0), (left - 1, top), "armhole", "left")
    return _schematic(sk.items, sk.legend, H + 2 * x0 + 10, L + 2 * y0 + 4, sizes, ms,
                      "babywear")


def _babywear_narrative(spec, facts) -> str:
    top = ("At the underarm line a back-loop band is worked, then the square neck: the "
           "first shoulder is worked up on the first stitches while the last stitches wait "
           "on hold, and the second shoulder is worked from them. Front and back are sewn "
           "together at the shoulders and down the sides. It pulls on over the head: nothing "
           "to fasten.")
    if facts.construction == "baby_romper":
        return ("Front and back are the same panel, worked from the bottom up. It begins at "
                "a narrow crotch gusset; stitches are chained on at both sides for the hips, "
                "and the edges of the gusset and those chains become the leg openings. The "
                "body is decreased evenly to the chest. " + top + " The two gussets are sewn "
                "together between the legs.")
    return ("Front and back are the same panel, worked from the bottom up: a back-loop hem "
            "band, then decreases spaced evenly up the skirt to an A-line, and the bodice "
            "straight to the chest. " + top)


from ..cir.graded import BABY as _BABY  # noqa: E402

_REFUSE_CLOSURES = (r"\b(?:buttons?|buttoned|snaps?|poppers?|zip(?:per)?s?|ties?|tie-?up|"
                    r"bows?|straps?|strappy|halter|collar(?:ed)?|sleeves?|sleeved|"
                    r"hood(?:ed|ie)?|smock(?:ed|ing)?|peter pan|footed|footie)\b",
                    "the baby engines build a sleeveless pull-on garment with a square neck "
                    "and no closures, straps, sleeves, collar or feet (no buttons, snaps or "
                    "ties for under-3s)")
_BABYWEAR_COMMON = dict(
    table=_BABY, requires=("bust", "hip", "back_length", "armhole_depth", "cross_back"),
    primary="bust", built_primary="chest", measure=babywear_measures, gates=babywear_gates,
    narrative=_babywear_narrative, schematic=_babywear_schematic, risk="B",
    abbreviations=("ch", "sc", "dec"),
    safety_note=("It is made with no buttons, snaps, ties, cords or anything sewn on: it "
                 "pulls on over the head, and the shoulders are worked in and sewn flat."),
    forms=("fitted_garment",), constructions=("flat_rows", "bottom_up", "modular_panels"),
    ease=(("baby", BABY_EASE),), yarn=(("baby", ("dk", "cotton")),),
    fit_note=("Relaxed: 10 cm of ease at the chest; every size is checked to pull on over a "
              f"{PULLOVER_HEAD_CM:g} cm head (CYC head chart, Toddler)."),
    tips=("Lay the two panels together before seaming and check that the bands line up.",
          "Sew the shoulders first, then the sides: the armholes are the shoulders' side "
          "edges, left open."),
    refuse=(_REFUSE_CLOSURES,), sizes={"baby": ("3m", "6m", "12m", "18m", "24m")},
)
register(Engine(
    family="baby_dress", title="two identical panels worked bottom up and seamed at the "
                               "shoulders and sides",
    words=("dress", "dresses", "pinafore", "pinafores", "sundress"), builder=baby_dress,
    chart=(("body_cm", "To fit chest"), ("chest_cm", "Finished chest"), ("ease_cm", "Ease"),
           ("widest_cm", "Hem"), ("length_cm", "Length")),
    category_word="dress", style_words=((r"\bpinafores?\b", "pinafore"),),
    **_BABYWEAR_COMMON))
register(Engine(
    family="baby_romper", title="two identical panels worked bottom up from a crotch gusset "
                                "and seamed at the shoulders, sides and gusset",
    words=("romper", "rompers", "playsuit", "playsuits", "shortall", "shortalls"),
    builder=baby_romper,
    chart=(("body_cm", "To fit chest"), ("chest_cm", "Finished chest"), ("ease_cm", "Ease"),
           ("widest_cm", "Hips"), ("length_cm", "Length")),
    category_word="romper", chain_gauge=True, **_BABYWEAR_COMMON))
