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
    tables: tuple[tuple[str, object], ...] = ()     # audience -> BodyTable, where not `table`
    fit_character: str | None = None                # cir.graded.FIT_CHARACTERS, if stated
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
    require: str | None = None     # a title must ALSO match this to be this family's


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

    table = dict(eng.tables).get(spec.audience, eng.table)
    d = GradedDesign(key=spec.key, title=spec.title, table=table, gauge=gauge,
                     fit=FitIntent(dict(spec.ease_cm), character=eng.fit_character),
                     requires=eng.requires,
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
                                     for w in eng.words) and \
                (eng.require is None or _re.search(eng.require, folded)):
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
    panel = [x for x in r.rows if x.component == "panel"]
    pcomp = next(c for c in cir.components if c.name == "panel")
    heights = [_row_height_cm(row, cir) for row in pcomp.rows]
    # The square-neck split is the panel's last row that leaves stitches (from the CIR
    # alone: a stored CIR carries no step record).
    split = max(row.index for row in pcomp.rows if row.skips)
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


# ==== 3. simple tops: boxy tee and tank =====================================================
#
# A boxy drop-shoulder top. The body is one flat piece worked from the front hem up, over a
# slash neck bridged by a chain at the shoulder line, and down to the back hem (back-loop hem
# bands at both ends). Folded at the shoulder line, the sides are seamed from the hems up to
# the armhole, which is left open: a tank stops there; a tee has straight short sleeves worked
# from a back-loop cuff band and sewn into the armhole, centred on the shoulder line. Child
# sizes are the tank only: a sleeve sewn onto a child's garment needs physical evidence no
# authority holds yet (`gates.child_safety` "sewn"), so a child's tee is not offered.

TOP_NECK_OF_CROSS_BACK = 0.8           # slash neck width, of the body's cross-back
SHORT_SLEEVE_OF_ARM = 0.25             # tee sleeve length, of the arm length to underarm
TOP_RIB_CM = {"adult": 3.0, "child": 2.0}
TOP_EASE = {
    "adult": (("bust", 20.0), ("back_length", 14.0), ("armhole_depth", 4.0),
              ("upper_arm", 10.0), ("cross_back", 0.0), ("arm_length", 0.0)),
    "child": (("bust", 14.0), ("back_length", 8.0), ("armhole_depth", 3.0),
              ("cross_back", 0.0)),
}
TOP_LENGTH_TOLERANCE = 0.08


def boxy_top(g: GradedSize, spec: WearableSpec) -> CIR:
    fam = StitchFamily("sc", "plain")
    style = "tank" if spec.family == "top_tank" else "tee"
    rib = g.rows(TOP_RIB_CM["child" if spec.audience == "child" else "adult"], minimum=2)
    width = g.stitches(g.finished_cm("bust") / 2.0)
    half_rows = g.rows(g.finished_cm("back_length"))
    neck = g.stitches(g.body_cm("cross_back") * TOP_NECK_OF_CROSS_BACK)
    if (width - neck) % 2:
        neck += 1
    body = GF.Piece("body", fam, foundation=width, feature="body", direction="bottom_up",
                    note="worked in one piece from the front hem, over the shoulders, to the "
                         "back hem")
    body.even(rib, loop="back", label="front hem band")
    body.even(half_rows - rib, label="front")
    neck_row = body.neck_bridge(neck)
    body.even(half_rows - rib, label="back")
    body.even(rib, loop="back", label="back hem band")
    row_cm = _row_cm(g.gauge)
    comps = [body.component()]
    pieces = {"body": body.steps}
    if style == "tee":
        top = g.stitches(max(g.finished_cm("upper_arm"), 2 * g.finished_cm("armhole_depth")))
        half_cover = max(1, round(g.cm_of_stitches(top) / 2.0 / row_cm))
        sl_rows = g.rows(g.body_cm("arm_length") * SHORT_SLEEVE_OF_ARM, minimum=rib + 2)
        sl = GF.Piece("sleeve", fam, foundation=top, make=2, feature="sleeve",
                      direction="bottom_up")
        sl.even(rib, loop="back", label="cuff band")
        sl.even(sl_rows - rib, label="sleeve")
        comps.append(sl.component())
        pieces["sleeve"] = sl.steps
    else:
        half_cover = g.rows(g.finished_cm("armhole_depth"), minimum=4)
    first_cover = neck_row - half_cover
    below = first_cover - 1
    if below <= rib + 2:
        raise ShapingRefused(f"size {g.size}: no side seam below the armhole")
    seams = [Seam("mattress", "body", "body", edge_a="left", edge_b="left", at_round=1,
                  spans_rounds=below, mirrored=True,
                  note=f"fold at the shoulder line and join the front's side to the back's "
                       f"side from the hems up, {below} rows each, through both loops; leave "
                       f"the rest open for the armhole")]
    if style == "tee":
        seams = [Seam("whipstitch", "sleeve", "body", edge_a="top", edge_b="left",
                      at_round=first_cover, spans_rounds=2 * half_cover + 1, mirrored=True,
                      note="centre the sleeve on the shoulder line and sew its top edge into "
                           "the armhole through both loops; bury the tails")] + seams + [
                 Seam("mattress", "sleeve", "sleeve", edge_a="left", edge_b="right",
                      note="close the underarm seam of each sleeve")]
    facts = WFacts(f"top_{style}", pieces=pieces)
    facts.seams = [{"seam": "side", "a": "body(front half)", "b": "body(back half)",
                    "a_rows": neck_row - 1, "b_rows": len(body.rows) - neck_row}]
    if style == "tee":
        facts.seams.append({"seam": "sleeve to armhole", "a": "sleeve", "b": "body",
                            "a_cm": g.cm_of_stitches(top),
                            "b_cm": (2 * half_cover + 1) * row_cm})
    facts.numbers = {"neck": neck, "half_cover": half_cover, "neck_row": neck_row}
    word = "tee" if style == "tee" else "tank"
    return make_cir(g, spec, comps=comps, seams=seams, facts=facts,
                    designer=(f"A boxy drop-shoulder {word}: one body piece worked from the "
                              f"front hem over a slash neck to the back hem, with back-loop "
                              f"hem bands"
                              + (", and straight short sleeves with back-loop cuffs sewn into "
                                 "the armholes." if style == "tee" else
                                 "; the armholes are left open in the side seams.")),
                    size_note=f"Finished chest {2 * width * _st_cm(g.gauge):.0f} cm, to fit "
                              f"chest {g.body_cm('bust'):g} cm")


def top_measures(cir: CIR) -> dict[str, float]:
    """Chest, length, neck width and armhole depth from the rows and the assembly; upper arm
    and sleeve length for a tee. From the CIR alone (a stored CIR has no step record)."""
    from ..cir.geometry import _row_height_cm

    r = _compiled(cir)
    g = cir.gauge
    body = next(c for c in cir.components if c.name == "body")
    rows = [x for x in r.rows if x.component == "body"]
    heights = [_row_height_cm(row, cir) for row in body.rows]
    bridge = next(row for row in body.rows
                  if any(op.stitch == "ch" for op in row.ops if isinstance(op, Op)))
    neck_sts = next(op.count for op in bridge.ops if isinstance(op, Op) and op.stitch == "ch")
    out = {"chest": round(2 * rows[0].stitch_count * _st_cm(g), 2),
           "length": round(sum(heights[:bridge.index]), 2),
           "neck": round(neck_sts * _st_cm(g), 2)}
    sleeve = next((c for c in cir.components if c.name == "sleeve"), None)
    if sleeve is not None:
        place = next(s for s in cir.assembly if s.piece_a == "sleeve" and s.at_round)
        out["armhole"] = round(place.spans_rounds * _row_cm(g) / 2.0, 2)
        out["upper_arm"] = round(sleeve.foundation * _st_cm(g), 2)
        out["sleeve"] = round(sum(_row_height_cm(row, cir) for row in sleeve.rows), 2)
    else:
        side = next(s for s in cir.assembly if s.piece_a == "body" and s.at_round)
        out["armhole"] = round(sum(heights[side.spans_rounds:bridge.index - 1]), 2)
    return out


def top_gates(ctx) -> list:
    from ..gates.garment_fit import CHEST_TOLERANCE, NECK_MAX, NECK_MIN, GarmentFinding

    out = []
    g, m, f, size, res = ctx["g"], ctx["measured"], ctx["facts"], ctx["size"], ctx["result"]

    def bad(code, msg):
        out.append(GarmentFinding(code, size, msg))

    want = g.finished_cm("bust")
    if abs(m["chest"] - want) / want > CHEST_TOLERANCE:
        bad("GARMENT_FINISHED_OFF_TARGET", f"built chest {m['chest']:.1f} cm against "
                                           f"{want:g} cm")
    want_len = g.finished_cm("back_length")
    if abs(m["length"] - want_len) / want_len > TOP_LENGTH_TOLERANCE:
        bad("GARMENT_FINISHED_OFF_TARGET", f"built length {m['length']:.1f} cm against "
                                           f"{want_len:g} cm")
    fit = ctx["design"].fit.character
    if fit:
        from ..cir.graded import FIT_EASE_BANDS_CM

        lo, hi = FIT_EASE_BANDS_CM[fit]
        ease = m["chest"] - g.body_cm("bust")
        if not lo <= ease <= hi:
            bad("GARMENT_EASE_OUT_OF_BAND", f"chest ease {ease:.1f} cm outside {fit} "
                                            f"{lo:g}-{hi:g}")
    ratio = m["neck"] / g.body_cm("cross_back")
    if not NECK_MIN <= ratio <= NECK_MAX:
        bad("GARMENT_NECK_FIT", f"the slash neck is {m['neck']:.1f} cm, {ratio:.2f} of the "
                                f"cross-back")
    if m["armhole"] + 1e-9 < g.body_cm("armhole_depth"):
        bad("GARMENT_ARMHOLE_FIT", f"the armhole is {m['armhole']:.1f} cm deep; the body's "
                                   f"is {g.body_cm('armhole_depth'):g} cm")
    if "upper_arm" in m and m["upper_arm"] + 1e-9 < g.body_cm("upper_arm"):
        bad("GARMENT_ARMHOLE_FIT", f"the sleeve is {m['upper_arm']:.1f} cm round; the upper "
                                   f"arm is {g.body_cm('upper_arm'):g} cm")
    rows = [x.stitch_count for x in res.rows if x.component == "body"]
    nr = int(f.numbers["neck_row"])
    front, back = rows[:nr - 1], rows[nr:]
    if front != list(reversed(back)):
        bad("GARMENT_SEAM_MISMATCH", "the back half is not the front half row for row: the "
                                     "sides do not meet at the fold")
    return out


def _top_schematic(sizes, ms) -> dict:
    tee = "upper_arm" in ms[0]
    names = {"half_chest": "Half chest, finished", "length": "Length, finished",
             "neck": "Neck opening", "armhole": "Armhole depth"}
    if tee:
        names.update(upper_arm="Sleeve width, round", sleeve="Sleeve length")
    sk = Sketch(ms, names)
    for m in ms:
        m["half_chest"] = round(m["chest"] / 2.0, 1)
    mid = ms[len(ms) // 2]
    W, L, N, A = mid["half_chest"], mid["length"], mid["neck"], mid["armhole"]
    x0, y0 = 4.0, 6.0
    sk.poly([(x0, y0), (x0 + W, y0), (x0 + W, y0 + L), (x0, y0 + L)],
            "body (front shown; the back is the same)")
    nx = x0 + (W - N) / 2.0
    sk.line((nx, y0), (nx + N, y0), heavy=True)
    sk.line((x0 + W - 1.2, y0 + A), (x0 + W, y0 + A))
    sk.dim((x0, y0 + L), (x0 + W, y0 + L), "half_chest", "below")
    sk.dim((x0, y0), (x0, y0 + L), "length", "left")
    sk.dim((nx, y0), (nx + N, y0), "neck", "above")
    sk.dim((x0 + W, y0), (x0 + W, y0 + A), "armhole", "right")
    width = W + 2 * x0 + 8
    if tee:
        U, S = mid["upper_arm"], mid["sleeve"]
        sx = x0 + W + 12
        sk.poly([(sx, y0), (sx + U, y0), (sx + U, y0 + S), (sx, y0 + S)], "sleeve")
        sk.dim((sx, y0), (sx + U, y0), "upper_arm", "above")
        sk.dim((sx + U, y0), (sx + U, y0 + S), "sleeve", "right")
        width = sx + U + 12
    return _schematic(sk.items, sk.legend, width, L + 2 * y0 + 4, sizes, ms, "top")


def _top_narrative(spec, facts) -> str:
    base = ("The body is one flat piece. You start at the front hem with a back-loop band, "
            "work straight up to the shoulder line, where a chain bridges the slash neck, and "
            "carry on down the back to the back hem. Fold it at the shoulder line and seam "
            "the sides from the hems up, leaving the top open for the armholes.")
    if facts.construction == "top_tee":
        return base + (" The short sleeves are straight, worked from a back-loop cuff band, "
                       "sewn into the armholes centred on the shoulder line, and seamed "
                       "underneath.")
    return base + " The armhole edges and the neck are left plain."


from ..cir.graded import CHILD as _CHILD, WOMAN as _WOMAN  # noqa: E402

_TOP_COMMON = dict(
    requires=("bust", "back_length", "cross_back", "armhole_depth"), primary="bust",
    built_primary="chest", measure=top_measures, gates=top_gates, narrative=_top_narrative,
    schematic=_top_schematic, risk="B", abbreviations=("ch", "sc", "sk"),
    forms=("fitted_garment",), constructions=("flat_rows", "bottom_up", "modular_panels"),
    yarn=(("adult", ("dk", "cotton")), ("child", ("dk", "cotton"))),
    refuse=((r"\b(?:fitted|bodycon|crop(?:ped)?|v-?neck|scoop(?:ed)?|crew ?neck|collar(?:ed)?|"
             r"buttons?|button-?down|ruffles?|halter|lace|lacy|mesh|open-?work|peplum|wrap|"
             r"long[- ]sleeved?|puff[- ]sleeves?|raglan|hood(?:ed|ie)?|pockets?)\b",
             "the boxy top engine builds a slash-neck drop-shoulder tee or tank in plain "
             "single crochet only"),),
    tips=("Chain loosely across the neck: the next row works into those chains and they "
          "must be as wide as the fabric.",
          "Seam the sides with the top folded flat at the shoulder line so the hems meet."),
    safety_note=("It is made with no buttons, ties, cords or anything sewn on: the body is "
                 "one piece, seamed at the sides."),
)
register(Engine(
    family="top_tee", title="one body piece worked over a slash neck, folded at the shoulder "
                            "line and seamed, with short sleeves sewn in",
    words=("tee", "tees", "t-shirt", "t-shirts", "tshirt"),
    table=_WOMAN, sizes={"adult": _WOMAN.names},
    builder=boxy_top,
    chart=(("body_cm", "To fit chest"), ("chest_cm", "Finished chest"), ("ease_cm", "Ease"),
           ("length_cm", "Length"), ("upper_arm_cm", "Sleeve width")),
    category_word="tee", ease=(("adult", TOP_EASE["adult"]),),
    fit_note="Relaxed and boxy: 20 cm of ease at the chest (the relaxed band is 8-22 cm).",
    **{**_TOP_COMMON, "requires": _TOP_COMMON["requires"] + ("upper_arm", "arm_length")}))
register(Engine(
    family="top_tank", title="one body piece worked over a slash neck, folded at the shoulder "
                             "line and seamed, with open armholes",
    words=("tank", "tanks", "tank top", "tank tops", "singlet", "singlets"),
    table=_WOMAN, tables=(("child", _CHILD),),
    sizes={"adult": _WOMAN.names, "child": ("2", "4", "6", "8", "10", "12")},
    builder=boxy_top,
    chart=(("body_cm", "To fit chest"), ("chest_cm", "Finished chest"), ("ease_cm", "Ease"),
           ("length_cm", "Length"), ("armhole_cm", "Armhole depth")),
    category_word="tank", ease=(("adult", TOP_EASE["adult"]), ("child", TOP_EASE["child"])),
    fit_note="Relaxed and boxy: 20 cm of ease at the chest for adults, 14 cm for children.",
    **_TOP_COMMON))


# ==== 4. cardigan variants: the V-neck raglan cardigan ======================================
#
# Top down, worked flat in one piece from the neck. The foundation is the back neck, the two
# sleeve tops and a two-stitch point for each front; the yoke increases at the four raglan
# lines (as `garment_families.raglan_cardigan`) AND at both neck edges, so the fronts grow
# from the point out to their full width and the front edges slope into a V that bottoms out
# at the underarm. At the underarm the sleeves go on hold and the fronts and back continue as
# one piece to a back-loop hem band; each sleeve is resumed and decreased to a back-loop cuff.
# A band is picked up along each front edge, from the hem up the V to the raglan line; its
# stitches are counted from the edge's own length, the slope included. Open front: no
# buttons (so the baby and child sizes are child-safe: nothing sewn on, nothing to swallow).

VCARDI_EASE = {
    "adult": (("bust", 16.0), ("back_length", 14.0), ("armhole_depth", 4.0),
              ("upper_arm", 8.0), ("cross_back", 0.0), ("arm_length", 0.0)),
    "child": (("bust", 14.0), ("back_length", 8.0), ("armhole_depth", 2.0),
              ("upper_arm", 5.0), ("cross_back", 0.0), ("arm_length", 0.0)),
    "baby": (("bust", 10.0), ("back_length", 4.0), ("armhole_depth", 2.0),
             ("upper_arm", 4.0), ("cross_back", 0.0), ("arm_length", 0.0)),
}
VNECK_BACK_OF_CROSS_BACK = 0.45      # the back neck (foundation), of the cross-back
VNECK_FRONT_POINT = 2                # stitches each front starts on, at the raglan line


def _vraglan_row(p: GF.Piece, f: int, s: int, b: int, m: int, n: int) -> tuple:
    """One yoke row: `m` raglan units at each of the four lines, `n` neck increases at each
    end of the row (the two neck edges). Returns the new (f, s, b)."""
    i = p.next_index
    lp = p.fam.loop(i)
    st, inc = p.fam.stitch, p.fam.inc
    plan = [(inc, n), (st, f - m - n), (inc, 2 * m), (st, s - 2 * m), (inc, 2 * m),
            (st, b - 2 * m), (inc, 2 * m), (st, s - 2 * m), (inc, 2 * m), (st, f - m - n),
            (inc, n)]
    ops: list[Op] = []
    for code, k in plan:
        if k < 0:
            raise ShapingRefused(f"{p.name} row {i}: a section too narrow to increase")
        if k == 0:
            continue
        if ops and ops[-1].stitch == code:
            ops[-1] = Op(code, ops[-1].count + k, loop=lp)
        else:
            ops.append(Op(code, k, loop=lp))
    new = 2 * f + 2 * s + b + 8 * m + 2 * n
    p._finish(p._row(ops), new)
    return f + m + n, s + 2 * m, b + 2 * m


def vneck_cardigan(g: GradedSize, spec: WearableSpec) -> CIR:
    fam = StitchFamily("sc", "plain")
    rib = GF._rib_rows(g)
    band_rows = GF._band_rows(g)
    band_cm = g.cm_of_rows(band_rows)
    body_sts = g.stitches(g.finished_cm("bust") - band_cm)
    back = GF._even(body_sts // 2)
    front = (body_sts - back) // 2
    sleeve_top = GF._even(g.stitches(g.finished_cm("upper_arm")))
    yoke_rows = g.rows(g.finished_cm("armhole_depth"), minimum=4)
    b0 = GF._even(g.stitches(g.body_cm("cross_back") * VNECK_BACK_OF_CROSS_BACK))
    units = (back - b0) // 2
    # The sleeve top keeps at least a few stitches at the neck: fewer units, wider back neck.
    units = min(units, (sleeve_top - 4) // 2)
    b0 = back - 2 * units
    s0 = sleeve_top - 2 * units
    f0 = VNECK_FRONT_POINT
    neck_incs = front - f0 - units
    if s0 < 2 or units < 1 or neck_incs < 1:
        raise ShapingRefused(f"size {g.size}: the V-neck yoke does not resolve "
                             f"(units {units}, sleeve at neck {s0}, neck increases "
                             f"{neck_incs})")
    doubles = max(0, units - yoke_rows)
    singles = units - 2 * doubles
    if singles + doubles > yoke_rows or neck_incs > yoke_rows:
        raise ShapingRefused(f"size {g.size}: the yoke cannot hold {units} raglan units and "
                             f"{neck_incs} neck increases in {yoke_rows} rows")
    s_events, s_every = GF.uniform(singles, yoke_rows - doubles)
    raglan = [2] * doubles + [0] * (yoke_rows - doubles)
    for k in range(s_events):
        raglan[doubles + k * s_every] = 1
    n_events, n_every = GF.uniform(neck_incs, yoke_rows)
    neck = [0] * yoke_rows
    for k in range(n_events):
        neck[k * n_every] = 1
    p = GF.Piece("yoke_and_body", fam, foundation=2 * f0 + 2 * s0 + b0, feature="yoke",
                 direction="top_down", note="worked flat from the neck down; the fronts "
                                            "start as a point at each raglan line")
    p.even(1, label="set-up row: place the four raglan markers")
    first = p.next_index
    f, s, b = f0, s0, b0
    for m, n in zip(raglan, neck):
        f, s, b = _vraglan_row(p, f, s, b, m, n)
    p._record("vraglan", first, p.next_index - 1,
              n=(("doubles", doubles), ("singles", s_events), ("every", s_every),
                 ("neck", n_events), ("neck_every", n_every), ("rows", yoke_rows),
                 ("f0", f0), ("s0", s0), ("b0", b0)), label="yoke")
    if (f, s, b) != (front, sleeve_top, back):
        raise ShapingRefused(f"size {g.size}: the yoke ends at {(f, s, b)}, not "
                             f"{(front, sleeve_top, back)}")
    length_rows = g.rows(g.finished_cm("back_length"))
    body_rows = length_rows - 1 - yoke_rows - 1
    p.divide(sleeve_top, front, back)
    if body_rows - rib < 2:
        raise ShapingRefused(f"size {g.size}: no body below the underarm")
    p.even(body_rows - rib, label="body")
    p.even(rib, loop="back", label="hem band")
    cuff = min(sleeve_top, GF._even(g.stitches(g.finished_cm("upper_arm")
                                               * GF.CUFF_OF_UPPER_ARM)))
    sleeve_rows = g.rows(g.body_cm("arm_length") + g.fit.ease("arm_length"), minimum=6)
    events, every = GF.uniform(max(1, (sleeve_top - cuff) // 2), sleeve_rows - rib - 2)
    sleeves = []
    for side in ("sleeve_left", "sleeve_right"):
        sp = GF.Piece(side, fam, foundation=sleeve_top, resumes=side, feature="sleeve",
                      direction="top_down")
        sp.even(1, label="first sleeve row")
        sp.shape(events, every, grow=False, label="sleeve decreases")
        plain = sleeve_rows - 1 - ((events - 1) * every + 1) - rib
        sp.even(max(1, plain), label="sleeve")
        sp.even(rib, loop="back", label="cuff band")
        sleeves.append(sp)
    comp = p.component()
    edge_cm = front_edge_cm(comp, g.gauge)
    pick = GF.pick_up_count(edge_cm, g)
    bands = []
    for side in ("band_left", "band_right"):
        bp = GF.Piece(side, fam, foundation=pick, grain="across", feature="button_band",
                      direction="side_to_side", foundation_kind="none",
                      note=f"picked up along the {side.split('_')[1]} front edge, from the "
                           f"hem up the V to the raglan line")
        bp.even(band_rows, loop="back", label="band")
        bands.append(bp)
    seams = [Seam("mattress", sl, sl, edge_a="left", edge_b="right",
                  note="close the sleeve seam from cuff to underarm through both loops")
             for sl in ("sleeve_left", "sleeve_right")]
    seams += [Seam("pick_up", bp.name, "yoke_and_body", edge_a="left",
                   edge_b="left" if bp.name == "band_left" else "right",
                   note=f"pick up {pick} sts evenly along the front edge, from the hem up the "
                        f"V to the raglan line") for bp in bands]
    facts = WFacts("vneck_cardigan",
                   pieces={x.name: x.steps for x in [p] + sleeves + bands})
    facts.pickups = [{"piece": bp.name, "into": "yoke_and_body", "edge_cm": round(edge_cm, 2),
                      "stitches": pick, "rows_along": len(comp.rows), "edge_kind": "front"}
                     for bp in bands]
    facts.numbers = {"band_cm": band_cm, "yoke_rows": yoke_rows, "b0": b0, "s0": s0,
                     "f0": f0, "front": front, "back": back, "sleeve_top": sleeve_top}
    return make_cir(g, spec, comps=[comp] + [x.component() for x in sleeves + bands],
                    seams=seams, facts=facts,
                    designer=("A top-down raglan cardigan with a V neck: the fronts grow from "
                              "a point at the raglan lines, increasing at the neck edges to "
                              "the underarm; back-loop hem, cuffs and picked-up front bands; "
                              "open front, nothing to fasten."),
                    size_note=f"Finished chest {g.cm_of_stitches(2 * front + back) + band_cm:.0f}"
                              f" cm, to fit chest {g.body_cm('bust'):g} cm")


def front_edge_cm(comp: Component, gauge) -> float:
    """The front edge's own length, from the rows: every row's height, and on a yoke row that
    begins with an increase (a neck increase) the slope across that stitch as well."""
    from types import SimpleNamespace

    from ..cir.geometry import _row_height_cm

    shim = SimpleNamespace(gauge=gauge)
    divide = min((row.index for row in comp.rows if row.skips), default=10 ** 9)
    st = _st_cm(gauge)
    total = 0.0
    for row in comp.rows:
        first = row.ops[0] if row.ops else None
        n = first.count if (row.index < divide and isinstance(first, Op)
                            and first.stitch == "inc") else 0
        total += math.hypot(_row_height_cm(row, shim), n * st)
    return round(total, 2)


def vcardi_measures(cir: CIR) -> dict[str, float]:
    from ..cir.geometry import _row_height_cm
    from ..cir.twin import row_width_cm

    r = _compiled(cir)
    g = cir.gauge
    yoke = next(c for c in cir.components if c.name == "yoke_and_body")
    div = next(row for row in yoke.rows if row.skips)
    body_row = next(x for x in r.rows if x.component == yoke.name and x.index == div.index)
    band = next(c for c in cir.components if c.name == "band_right")
    band_cm = len(band.rows) * _row_cm(g)
    heights = [_row_height_cm(row, cir) for row in yoke.rows]
    upper = max(row_width_cm(x, g)[0] for x in r.rows if x.component == "sleeve_left")
    return {"chest": round(body_row.stitch_count * _st_cm(g) + band_cm, 2),
            "length": round(sum(heights), 2), "upper_arm": round(upper, 2),
            "armhole": round(sum(heights[:div.index - 1]), 2),
            "front_edge": front_edge_cm(yoke, g)}


def vcardi_gates(ctx) -> list:
    from ..gates.garment_fit import CHEST_TOLERANCE, LENGTH_TOLERANCE, GarmentFinding

    out = []
    g, m, f, size, cir = ctx["g"], ctx["measured"], ctx["facts"], ctx["size"], ctx["cir"]

    def bad(code, msg):
        out.append(GarmentFinding(code, size, msg))

    want = g.finished_cm("bust")
    if abs(m["chest"] - want) / want > CHEST_TOLERANCE:
        bad("GARMENT_FINISHED_OFF_TARGET", f"built chest {m['chest']:.1f} against {want:g} cm")
    want_len = g.finished_cm("back_length")
    if abs(m["length"] - want_len) / want_len > LENGTH_TOLERANCE:
        bad("GARMENT_FINISHED_OFF_TARGET", f"built length {m['length']:.1f} against "
                                           f"{want_len:g} cm")
    if m["armhole"] + 1e-9 < g.body_cm("armhole_depth"):
        bad("GARMENT_ARMHOLE_FIT", f"the yoke is {m['armhole']:.1f} cm deep; the body's "
                                   f"armhole depth is {g.body_cm('armhole_depth'):g} cm")
    if m["upper_arm"] + 1e-9 < g.body_cm("upper_arm"):
        bad("GARMENT_ARMHOLE_FIT", f"the sleeve is {m['upper_arm']:.1f} cm round; the upper "
                                   f"arm is {g.body_cm('upper_arm'):g} cm")
    back_neck = int(f.numbers["b0"]) * _st_cm(g.gauge)
    cross = g.body_cm("cross_back")
    if not 0.3 <= back_neck / cross <= 0.7:
        bad("GARMENT_NECK_FIT", f"the back neck is {back_neck:.1f} cm, "
                                f"{back_neck / cross:.2f} of the {cross:g} cm cross-back")
    from ..gates.garment_fit import _counts

    counts = _counts(ctx["result"])
    yoke = next(c for c in cir.components if c.name == "yoke_and_body")
    edge = front_edge_cm(yoke, cir.gauge)
    for p in f.pickups:
        comp = next(c for c in cir.components if c.name == p["piece"])
        first = counts.get((comp.name, comp.rows[0].index))
        if comp.foundation != p["stitches"] or first != p["stitches"]:
            bad("GARMENT_PICKUP_RATE", f"{comp.name} says {p['stitches']} sts; it starts on "
                                       f"{comp.foundation}")
        made = p["stitches"] * _st_cm(cir.gauge)
        drift = abs(made - edge) / edge
        if drift > GF.MAX_PICKUP_DRIFT:
            bad("GARMENT_PICKUP_RATE", f"{comp.name}: {p['stitches']} sts is {made:.1f} cm "
                                       f"along a {edge:.1f} cm front edge ({drift:.1%})")
    return out


def _vcardi_schematic(sizes, ms) -> dict:
    sk = Sketch(ms, {"half_chest": "Back width (the two fronts and one band are the same)",
                     "length": "Length, finished", "armhole": "Yoke depth (V depth)",
                     "upper_arm": "Upper arm, finished"})
    for m in ms:
        m["half_chest"] = round(m["chest"] / 2.0, 1)
    mid = ms[len(ms) // 2]
    W, L, A, U = mid["half_chest"], mid["length"], mid["armhole"], mid["upper_arm"]
    x0, y0 = 4.0, 6.0
    sk.poly([(x0, y0), (x0 + W / 2.0, y0 + A), (x0 + W / 2.0, y0 + L), (x0, y0 + L)],
            "left front (the V slopes from the raglan line to the underarm)")
    bx = x0 + W / 2.0 + 4
    sk.poly([(bx, y0), (bx + W, y0), (bx + W, y0 + L), (bx, y0 + L)], "back")
    sk.dim((bx, y0 + L), (bx + W, y0 + L), "half_chest", "below")
    sk.dim((x0 - 1, y0), (x0 - 1, y0 + L), "length", "left")
    sk.dim((x0 + W / 2.0 + 1, y0), (x0 + W / 2.0 + 1, y0 + A), "armhole", "right")
    sx = bx + W + 8
    sk.poly([(sx, y0), (sx + U, y0), (sx + U * 0.9, y0 + L * 0.8), (sx + U * 0.1, y0 + L * 0.8)],
            "sleeve")
    sk.dim((sx, y0), (sx + U, y0), "upper_arm", "above")
    return _schematic(sk.items, sk.legend, sx + U + 10, L + 2 * y0 + 4, sizes, ms, "vcardi")


def _vcardi_narrative(spec, facts) -> str:
    return ("You begin at the back neck with a short chain and work the yoke flat, "
            "increasing at four raglan markers and, on the rows the pattern gives, at both "
            "neck edges too: each front starts as a two-stitch point and grows into the V. At "
            "the underarm the sleeve stitches go on hold and the fronts and back continue as "
            "one piece to the hem, finished with a back-loop band. Each sleeve is worked from "
            "its held stitches down to the cuff, decreasing evenly, and its seam is closed. "
            "Last, a band is picked up along each front edge, from the hem up the V; the "
            "fronts meet edge to edge with nothing to fasten.")


register(Engine(
    family="cardigan_vneck", title="top-down raglan worked flat in one piece from the neck, "
                                   "with a V neck shaped at the front edges",
    words=("cardigan", "cardigans", "cardi", "cardis"),
    table=_WOMAN, tables=(("child", _CHILD), ("baby", _BABY)),
    sizes={"adult": _WOMAN.names, "child": ("2", "4", "6", "8", "10", "12"),
           "baby": ("3m", "6m", "12m", "18m", "24m")},
    requires=("bust", "back_length", "cross_back", "arm_length", "upper_arm",
              "armhole_depth"),
    primary="bust", built_primary="chest", builder=vneck_cardigan, measure=vcardi_measures,
    gates=vcardi_gates,
    chart=(("body_cm", "To fit chest"), ("chest_cm", "Finished chest"), ("ease_cm", "Ease"),
           ("length_cm", "Length"), ("upper_arm_cm", "Upper arm")),
    narrative=_vcardi_narrative, schematic=_vcardi_schematic, risk="B",
    fit_character="relaxed", category_word="cardigan",
    notions=("4 locking stitch markers", "a tapestry needle"),
    abbreviations=("ch", "sc", "inc", "dec", "sk"),
    forms=("fitted_garment",), constructions=("top_down_yoke",),
    ease=tuple(VCARDI_EASE.items()),
    yarn=(("adult", ("worsted", "wool")), ("child", ("dk", "cotton")),
          ("baby", ("dk", "cotton"))),
    fit_note="Relaxed: 16 cm of ease at the chest for adults, 14 for children, 10 for babies.",
    where=(("band_left", "the left front edge, from the hem up the V to the raglan line"),
           ("band_right", "the right front edge, from the raglan line down the V to the hem")),
    titles=(("band_left", "Left front band"), ("band_right", "Right front band")),
    tips=("Use locking markers for the raglan lines and move them up as you go; the neck "
          "increases are worked in the first and last stitch of the row.",),
    safety_note=("It is made with no buttons, ties, cords or anything sewn on: the sleeves "
                 "are worked from held stitches and the bands are picked up and worked in."),
    honest_phrases=(r"\bv[- ]?necks?(?:ed)?\b",),
    require=r"\bv[- ]?necks?(?:ed)?\b",
    # A V-neck cardigan is this engine's only claim: a title must say V-neck.
    refuse=((r"\b(?:buttons?|buttoned|cabled?|hood(?:ed|ie)?|pockets?|fitted|cropped|"
             r"collar(?:ed)?|shawl collar|belted|ties?|granny|lace|lacy)\b",
             "the V-neck cardigan engine builds an open-front plain raglan with a V neck "
             "only"),),
))


# ==== 5. socks and slippers =================================================================
#
# Cuff down, graded on the CYC foot chart. A back-loop rib cuff is worked flat side to side
# and seamed into a ring (as the beanie's brim); the leg is picked up along one edge and
# worked in joined rounds; the heel opening is one round in which half the stitches are
# skipped and bridged by a chain (an afterthought heel); the foot continues straight, the toe
# is decreased in sections and gathered shut. The heel is then worked into the opening -- one
# stitch into each chain and each skipped stitch -- and decreased and gathered the same way.
# Nothing is sewn on. The foot chart publishes circumference and length; the leg (sock
# height is not read unambiguously from the woman chart, so it is UNSOURCED) and the cuff are
# stated design ratios of the foot length.

SOCK_EASE_CM = -1.5                      # stated negative ease at the foot circumference
SOCK_STRETCH_BAND_CM = (-3.0, 0.5)
SOCK_LEG_OF_FOOT = {"sock": 0.55, "slipper": 0.12}   # leg above the heel, of foot length
SOCK_CUFF_OF_FOOT = {"sock": 0.12, "slipper": 0.12}  # cuff depth, of foot length
SOCK_LENGTH_TOLERANCE = 0.06
# No baby sizes: the afterthought heel cup of a sock for under-3s measures inside the small
# parts cylinder (`gates.child_safety` SMALL_PARTS), worked in or not. Held, not argued with.
SOCK_SIZES = {"child": ("Child 10-13", "Youth 1-3", "Youth 4-6"),
              "adult": ("Woman 4-6.5", "Woman 7-9.5", "Woman 10-12.5", "Man 12-14")}


def _opening(p: Rounds, *, label: str) -> int:
    """One round: work half the stitches, chain the other half loosely and skip them (the
    afterthought heel's opening). Returns the round's index."""
    worked = p.count // 2
    bridge = p.count - worked
    i = p.next_index
    row = p._row([Op(p.fam.stitch, worked), Op("ch", bridge, spans=bridge), Op("sk", bridge)],
                 note="the heel opening: the chain bridges the skipped stitches")
    p._finish(row, p.count)
    p._record("opening", i, i, n=(("worked", worked), ("bridge", bridge)), label=label)
    return i


def _gathered(p: Rounds, sections: int, *, label: str) -> None:
    """A spread round down to whole sections, then section decreases to `sections`."""
    setup = p.count % sections
    p.spread_dec(setup, label=f"set-up for the {label}")
    p.section_dec(sections, p.count // sections - 1, label=label)


def sock(g: GradedSize, spec: WearableSpec) -> CIR:
    fam = StitchFamily("sc", "plain")
    style = "slipper" if spec.family == "slipper" else "sock"
    sections = flat_sections(g)
    target = g.finished_cm("foot_circ")
    n = g.stitches(target, minimum=2 * sections)
    foot_cm = g.finished_cm("foot_length")
    row_cm = _row_cm(g.gauge)
    cuff_sts = g.stitches(foot_cm * SOCK_CUFF_OF_FOOT[style], minimum=3)
    ring_rows = max(2, int(round(n * _st_cm(g.gauge) / row_cm)))
    leg_rounds = g.rows(foot_cm * SOCK_LEG_OF_FOOT[style], minimum=2)
    # Toe and heel caps: one set-up round and the section rounds down to `sections`.
    cap_rounds = 1 + (n - n % sections) // sections - 1
    foot_rounds = max(2, int(round((foot_cm - 2 * cap_rounds * row_cm) / row_cm)) - 1)
    cuff = GF.Piece("cuff", fam, foundation=cuff_sts, grain="across", feature="cuff",
                    direction="side_to_side",
                    note="worked flat side to side; the rows run round the leg")
    cuff.even(ring_rows, loop="back", label="cuff")
    leg = Rounds("leg", fam, foundation=n, feature="body", direction="top_down",
                 foundation_kind="none",
                 note="picked up along one long edge of the cuff ring; leg, heel opening, "
                      "foot and toe in joined rounds")
    leg.even(leg_rounds, label="leg")
    opening = _opening(leg, label="heel opening")
    leg.even(foot_rounds, label="foot")
    _gathered(leg, sections, label="toe")
    heel = Rounds("heel", fam, foundation=n, feature="body", direction="top_down",
                  foundation_kind="none",
                  note="worked into the heel opening: one st into each chain and each skipped "
                       "st")
    heel.even(1, label="heel")
    _gathered(heel, sections, label="heel")
    seams = [
        Seam("mattress", "cuff", "cuff", edge_a="left", edge_b="right",
             note="fold the cuff into a ring and sew its last row to its foundation chain, "
                  "through both loops"),
        Seam("pick_up", "leg", "cuff", edge_a="bottom", edge_b="top",
             note=f"pick up {n} sts evenly along one long edge of the cuff ring, join"),
        Seam("pick_up", "heel", "leg", edge_a="bottom", edge_b="opening", at_round=opening,
             note=f"join the yarn at one corner of the heel opening and work {n - n // 2} sc "
                  f"along the chain and {n // 2} sc along the skipped sts; join"),
    ]
    facts = WFacts(style, pieces={"cuff": cuff.steps, "leg": leg.steps, "heel": heel.steps},
                   rounds=frozenset({"leg", "heel"}))
    facts.pickups = [{"piece": "leg", "into": "cuff", "edge_rows": ring_rows,
                      "edge_cm": round(g.cm_of_rows(ring_rows), 2), "stitches": n,
                      "rows_along": ring_rows}]
    facts.seams = [{"seam": "cuff ring", "a": "cuff(last row)", "b": "cuff(foundation)",
                    "a_sts": cuff_sts, "b_sts": cuff_sts, "a_edge_sts": cuff_sts,
                    "b_edge_sts": cuff_sts}]
    facts.numbers = {"sections": sections, "closing_sts": sections, "ring_rows": ring_rows,
                     "opening_round": opening, "target_circ_cm": target,
                     "target_foot_cm": foot_cm}
    word = "slipper" if style == "slipper" else "sock"
    return make_cir(g, spec, comps=[cuff.component(), leg.component(), heel.component()],
                    seams=seams, facts=facts, construction="joined_rounds",
                    designer=(f"A cuff-down {word}: a back-loop rib cuff worked side to side "
                              f"and seamed into a ring, the leg and foot in joined rounds with "
                              f"an afterthought heel opening, a gathered toe, and the heel "
                              f"worked into the opening and gathered."),
                    size_note=f"Finished foot circumference {n * _st_cm(g.gauge):.1f} cm "
                              f"(unstretched), to fit foot {g.body_cm('foot_circ'):g} cm round")


def sock_measures(cir: CIR) -> dict[str, float]:
    """Circumference, foot length (heel cup + foot + toe), leg length, from the rows."""
    from ..cir.geometry import _row_height_cm

    _compiled(cir)
    g = cir.gauge
    leg = next(c for c in cir.components if c.name == "leg")
    heel = next(c for c in cir.components if c.name == "heel")
    cuff = next(c for c in cir.components if c.name == "cuff")
    opening = next(row.index for row in leg.rows
                   if any(isinstance(o, Op) and o.stitch == "ch" for o in row.ops))
    h = [_row_height_cm(row, cir) for row in leg.rows]
    heel_cm = sum(_row_height_cm(row, cir) for row in heel.rows)
    return {"circumference": round(leg.foundation * _st_cm(g), 2),
            "foot_length": round(heel_cm + sum(h[opening:]), 2),
            "leg_length": round(cuff.foundation * _st_cm(g) + sum(h[:opening]), 2),
            "cuff": round(cuff.foundation * _st_cm(g), 2)}


def sock_gates(ctx) -> list:
    from ..cir.geometry import CLOSEABLE_STITCHES
    from ..gates.garment_fit import GarmentFinding

    out = []
    g, m, f, size, res = ctx["g"], ctx["measured"], ctx["facts"], ctx["size"], ctx["result"]

    def bad(code, msg):
        out.append(GarmentFinding(code, size, msg))

    target = g.finished_cm("foot_circ")
    if abs(m["circumference"] - target) > 1.5 * _st_cm(g.gauge) + 0.05:
        bad("SOCK_CIRCUMFERENCE", f"built {m['circumference']:.1f} cm against {target:g} cm")
    ease = m["circumference"] - g.body_cm("foot_circ")
    lo, hi = SOCK_STRETCH_BAND_CM
    if not lo <= ease <= hi:
        bad("SOCK_STRETCH_OUT_OF_BAND", f"built ease {ease:+.1f} cm outside {lo:g} to "
                                        f"{hi:+g} cm")
    want = g.finished_cm("foot_length")
    if abs(m["foot_length"] - want) / want > SOCK_LENGTH_TOLERANCE:
        bad("SOCK_FOOT_LENGTH", f"built foot {m['foot_length']:.1f} cm against the CYC "
                                f"{want:g} cm, more than {SOCK_LENGTH_TOLERANCE:.0%}")
    for piece in ("leg", "heel"):
        last = [x for x in res.rows if x.component == piece][-1].stitch_count
        if last > CLOSEABLE_STITCHES:
            bad("SOCK_CAP_OPEN", f"the {piece} ends on {last} sts; at most "
                                 f"{CLOSEABLE_STITCHES} gather shut")
    if int(f.numbers["sections"]) != flat_sections(g):
        bad("SOCK_CAP_SHAPE", "the toe and heel are not decreased at the flat rate")
    leg_rows = [x for x in res.rows if x.component == "leg"]
    at = int(f.numbers["opening_round"])
    heel_first = [x for x in res.rows if x.component == "heel"][0].stitch_count
    if heel_first != leg_rows[at - 1].stitch_count:
        bad("GARMENT_PICKUP_RATE", f"the heel starts on {heel_first} sts; the opening round "
                                   f"has {leg_rows[at - 1].stitch_count}")
    ring = len([x for x in res.rows if x.component == "cuff"])
    if ring != int(f.numbers["ring_rows"]):
        bad("SOCK_CUFF_RING", f"the cuff has {ring} rows; the ring needs "
                              f"{int(f.numbers['ring_rows'])}")
    out += pickup_rate(dict(ctx, facts=f))
    return out


def sock_schematic(sizes, ms) -> dict:
    sk = Sketch(ms, {"half_circ": "Half circumference, laid flat (unstretched)",
                     "foot_length": "Foot length, heel to toe", "leg_length": "Leg, cuff "
                                                                              "included",
                     "cuff": "Cuff depth"})
    for m in ms:
        m["half_circ"] = round(m["circumference"] / 2.0, 1)
    mid = ms[len(ms) // 2]
    C, F, L, K = mid["half_circ"], mid["foot_length"], mid["leg_length"], mid["cuff"]
    x0, y0 = 6.0, 6.0
    sk.poly([(x0, y0), (x0 + C, y0), (x0 + C, y0 + L), (x0 + C + F - C, y0 + L),
             (x0 + F, y0 + L + C * 0.5), (x0 + F - 1, y0 + L + C), (x0 + C, y0 + L + C),
             (x0, y0 + L + C * 0.6)], "sock, laid flat")
    sk.line((x0, y0 + K), (x0 + C, y0 + K))
    sk.dim((x0, y0), (x0 + C, y0), "half_circ", "above")
    sk.dim((x0 - 1, y0), (x0 - 1, y0 + L), "leg_length", "left")
    sk.dim((x0, y0 + L + C + 1.5), (x0 + F, y0 + L + C + 1.5), "foot_length", "below")
    sk.dim((x0 + C + 1, y0), (x0 + C + 1, y0 + K), "cuff", "right")
    return _schematic(sk.items, sk.legend, x0 + F + 10, L + C + 2 * y0 + 6, sizes, ms, "sock")


def _sock_narrative(spec, facts) -> str:
    word = "slipper" if facts.construction == "slipper" else "sock"
    return (f"The cuff comes first: a narrow strip worked flat in back-loop rows, sewn into a "
            f"ring. The leg is picked up along one edge of the ring and worked down in joined "
            f"rounds. One round makes the heel opening: half the stitches are worked and the "
            f"other half skipped under a loose chain. The foot continues straight to the toe, "
            f"which is decreased in equal sections and gathered shut. Last, the heel is worked "
            f"into the opening, decreased the same way and gathered: an afterthought heel, so "
            f"the whole {word} is worked in one piece apart from its cuff.")


_SOCK_COMMON = dict(
    table=FOOT, sizes=SOCK_SIZES, requires=("foot_circ", "foot_length"), primary="foot_circ",
    built_primary="circumference", builder=sock, measure=sock_measures, gates=sock_gates,
    chart=(("body_cm", "To fit foot (round)"), ("circumference_cm", "Finished round"),
           ("ease_cm", "Ease"), ("foot_length_cm", "Foot length"), ("leg_length_cm", "Leg")),
    narrative=_sock_narrative, schematic=sock_schematic, risk="B", chain_gauge=True,
    abbreviations=("ch", "sc", "dec", "sk", "slst"),
    forms=("fitted_garment", "tube"), constructions=("in_the_round",
                                                                 "seamless_tube"),
    ease=tuple((a, (("foot_circ", SOCK_EASE_CM),)) for a in ("child", "adult")),
    closing=lambda facts: (
        "Toe and heel: cut the yarn leaving a 20 cm tail, thread it through the front loop "
        f"of each of the last {_values([int(f.numbers['closing_sts']) for f in facts])} sts, "
        "pull tight to gather shut, and fasten off securely on the wrong side."),
    where=(("leg", "one long edge of the cuff ring (the row ends), one stitch into each row "
                   "end, skipping evenly"),
           ("heel", "the heel opening, starting at one corner: one stitch into each chain "
                    "and one into each skipped stitch")),
    titles=(("cuff", "Cuff"), ("leg", "Leg, foot and toe"), ("heel", "Heel")),
    tips=("Chain loosely across the heel opening: the heel is worked into those chains.",
          "Try the sock on before the toe: the foot should reach the base of your toes "
          "before you start the toe decreases."),
    safety_note=("It is made with no ties, cords, pom-poms or anything sewn on: the heel is "
                 "worked into the sock, and the cuff is sewn into a ring."),
    fit_note=(f"Made a little smaller round than the foot so it stays up: {SOCK_EASE_CM:+g} cm "
              f"of stated ease, and every size's built ease stays between "
              f"{SOCK_STRETCH_BAND_CM[0]:g} and {SOCK_STRETCH_BAND_CM[1]:+g} cm."),
    refuse=((r"\b(?:toe-?up|knee-?high|over-?the-?knee|thigh|stirrup|toeless|gusset|"
             r"short-?row|cabled?|lace|lacy|pom-?poms?|non-?slip|grip|soles?|leather|"
             r"bow|ties?|lined|moccasins?|clogs?|mary-?janes?|slides?|scuffs?)\b",
             "the sock engine builds a cuff-down sock or slipper with an afterthought heel "
             "in plain single crochet only"),),
    honest_phrases=(r"\b(?:turned |folded )?ribb?(?:ed|ing)?[- ]?(?:cuffs?|band)\b",),
)
register(Engine(
    family="sock", title="cuff down in joined rounds with an afterthought heel",
    words=("sock", "socks"), category_word="sock",
    yarn=(("child", ("fingering", "merino")), ("adult", ("fingering", "merino"))),
    **_SOCK_COMMON))
register(Engine(
    family="slipper", title="cuff down in joined rounds with an afterthought heel, short "
                            "ankle cuff",
    words=("slipper", "slippers", "slipper sock", "slipper socks", "bootie", "booties"),
    category_word="slipper",
    yarn=(("child", ("worsted", "wool")), ("adult", ("worsted", "wool"))),
    **_SOCK_COMMON))


# ==== 6. shawls and wraps ===================================================================
#
# Graded on the CYC woman chart by the measurement a shawl must span: centre back neck to
# wrist. The wingspan is twice the finished neck-to-wrist (body + stated ease), so the shawl
# reaches the wrists with the ease to drape. Sizes are the CYC sizes whose neck-to-wrist
# rises (L and XL, 4X and 5X publish the same figure, so one of each pair is offered).
#
# Triangle: worked bottom up from the point, one stitch increased at each end of every row
# (the depth follows from the gauge: about half the wingspan), finished with a back-loop band
# along the long top edge. Wrap: a rectangle worked from one short end, back-loop bands at
# both ends; its width is a stated ratio of the wingspan. A crescent is not built: its curved
# lower edge cannot be expressed in flat rows that the twin measures, so it is held by name.

SHAWL_SIZES = {"adult": ("XS", "M", "L", "2X", "4X")}
SHAWL_EASE = (("neck_to_wrist", 12.0),)
WRAP_WIDTH_OF_SPAN = 0.28
SHAWL_BAND_CM = 2.5
SHAWL_SPAN_TOLERANCE = 0.05
TRIANGLE_DEPTH_BAND = (0.38, 0.6)      # depth as a share of the wingspan


def shawl(g: GradedSize, spec: WearableSpec) -> CIR:
    fam = StitchFamily("sc", "plain")
    span_cm = 2 * g.finished_cm("neck_to_wrist")
    band = g.rows(SHAWL_BAND_CM, minimum=2)
    if spec.family == "shawl_triangle":
        span = g.stitches(span_cm)
        start = 3
        if (span - start) % 2:
            span += 1
        events = (span - start) // 2
        p = GF.Piece("shawl", fam, foundation=start, feature="body", direction="bottom_up",
                     note="worked from the bottom point up; the last rows are the long top "
                          "edge")
        p.even(1, label="point")
        p.shape(events, 1, grow=True, label="increases")
        p.even(band, loop="back", label="top band")
        facts = WFacts("shawl_triangle", pieces={"shawl": p.steps})
        facts.numbers = {"span": span, "target_span_cm": round(span_cm, 2)}
        word, how = "triangle shawl", ("worked from the point up, increasing at both ends of "
                                       "every row, with a back-loop band along the top edge")
    else:
        width = g.stitches(span_cm * WRAP_WIDTH_OF_SPAN)
        rows = g.rows(span_cm)
        p = GF.Piece("shawl", fam, foundation=width, feature="body", direction="bottom_up",
                     note="worked from one short end to the other")
        p.even(band, loop="back", label="end band")
        p.even(rows - 2 * band, label="body")
        p.even(band, loop="back", label="end band")
        facts = WFacts("shawl_wrap", pieces={"shawl": p.steps})
        facts.numbers = {"width": width, "target_span_cm": round(span_cm, 2)}
        word, how = "wrap", "worked end to end with back-loop bands at both short ends"
    return make_cir(g, spec, comps=[p.component()], seams=[], facts=facts,
                    designer=f"A {word} in single crochet, {how}.",
                    size_note=f"Finished wingspan {span_cm:.0f} cm, to span neck to wrist "
                              f"{g.body_cm('neck_to_wrist'):g} cm each side")


def shawl_measures(cir: CIR) -> dict[str, float]:
    from ..cir.geometry import _row_height_cm

    r = _compiled(cir)
    g = cir.gauge
    comp = cir.components[0]
    rows = [x for x in r.rows if x.component == comp.name]
    depth = sum(_row_height_cm(row, cir) for row in comp.rows)
    widest = max(x.stitch_count for x in rows) * _st_cm(g)
    if rows[0].stitch_count < rows[-1].stitch_count:          # a triangle
        return {"wingspan": round(widest, 2), "depth": round(depth, 2)}
    return {"wingspan": round(depth, 2), "depth": round(widest, 2)}


def shawl_gates(ctx) -> list:
    from ..gates.garment_fit import GarmentFinding

    out = []
    g, m, f, size = ctx["g"], ctx["measured"], ctx["facts"], ctx["size"]
    want = 2 * g.finished_cm("neck_to_wrist")
    if abs(m["wingspan"] - want) / want > SHAWL_SPAN_TOLERANCE:
        out.append(GarmentFinding("SHAWL_WINGSPAN", size, f"built {m['wingspan']:.1f} cm "
                                                          f"against {want:.1f} cm"))
    if m["wingspan"] < 2 * g.body_cm("neck_to_wrist"):
        out.append(GarmentFinding("SHAWL_WINGSPAN", size, "the shawl does not reach both "
                                                          "wrists"))
    if f.construction == "shawl_triangle":
        lo, hi = TRIANGLE_DEPTH_BAND
        ratio = m["depth"] / m["wingspan"]
        if not lo <= ratio <= hi:
            out.append(GarmentFinding("SHAWL_SHAPE", size, f"depth {ratio:.2f} of the "
                                                           f"wingspan is not a triangle shawl "
                                                           f"({lo}-{hi})"))
    else:
        ratio = m["depth"] / m["wingspan"]
        if abs(ratio - WRAP_WIDTH_OF_SPAN) > 0.04:
            out.append(GarmentFinding("SHAWL_SHAPE", size, f"the wrap is {ratio:.2f} as wide "
                                                           f"as it is long"))
    return out


def shawl_schematic(sizes, ms) -> dict:
    sk = Sketch(ms, {"wingspan": "Wingspan", "depth": "Depth (wrap: width)"})
    mid = ms[len(ms) // 2]
    W, D = mid["wingspan"], mid["depth"]
    x0, y0 = 6.0, 6.0
    if D < W * 0.35:
        sk.poly([(x0, y0), (x0 + W, y0), (x0 + W, y0 + D), (x0, y0 + D)], "wrap")
        sk.dim((x0, y0 + D), (x0 + W, y0 + D), "wingspan", "below")
        sk.dim((x0 + W, y0), (x0 + W, y0 + D), "depth", "right")
        sk.text((x0 + W / 2.0, y0 + D / 2.0), "worked end to end")
    else:
        sk.poly([(x0, y0), (x0 + W, y0), (x0 + W / 2.0, y0 + D)], "triangle shawl")
        sk.dim((x0, y0), (x0 + W, y0), "wingspan", "above")
        sk.dim((x0 + W / 2.0, y0), (x0 + W / 2.0, y0 + D), "depth", "right")
        sk.text((x0 + W / 2.0, y0 + D * 0.75), "begin at the point")
    return _schematic(sk.items, sk.legend, W + 2 * x0 + 6, D + 2 * y0 + 4, sizes, ms, "shawl")


def _shawl_narrative(spec, facts) -> str:
    if facts.construction == "shawl_triangle":
        return ("The shawl starts at its bottom point with three stitches and grows upward, "
                "one stitch increased at each end of every row, so the two sloping sides form "
                "as you go. The long top edge -- the wingspan -- is finished with a few rows "
                "worked through the back loop. There is nothing to sew.")
    return ("The wrap is one rectangle worked from one short end to the other, with a few "
            "rows through the back loop at each end for a firm, ridged edge. There is nothing "
            "to sew.")


_SHAWL_COMMON = dict(
    table=_WOMAN, sizes=SHAWL_SIZES, requires=("neck_to_wrist",), primary="neck_to_wrist",
    built_primary="wingspan", builder=shawl, measure=shawl_measures, gates=shawl_gates,
    chart=(("body_cm", "Neck to wrist (body)"), ("wingspan_cm", "Wingspan"),
           ("depth_cm", "Depth / width")),
    narrative=_shawl_narrative, schematic=shawl_schematic, risk="A",
    abbreviations=("ch", "sc", "inc"), ease=(("adult", SHAWL_EASE),),
    yarn=(("adult", ("dk", "merino")),),
    forms=("draped_garment", "scarf", "fitted_garment"),
    constructions=("flat_rows", "bottom_up"),
    fit_note=("Sized to span the arms: the wingspan is twice the neck-to-wrist measurement "
              "plus 12 cm of stated ease each side to drape."),
    tips=("Count every row of the increases: each row ends 2 stitches wider than the last.",),
    refuse=((r"\b(?:crescent|half[- ]moon|circular|circle|pi shawl|lace|lacy|"
             r"openwork|mesh|fring(?:e|ed)|tassels?|pom-?poms?|ruana|poncho|capelet|"
             r"shrug|hood(?:ed)?|pockets?|granny|mosaic|c2c|corner[- ]to[- ]corner)\b",
             "the shawl engines build a plain single crochet triangle shawl or rectangular "
             "wrap; a crescent's curved edge, lace, fringe and the rest are not built"),),
)
register(Engine(
    family="shawl_triangle", title="worked bottom up from the point, increasing at both "
                                   "edges", words=("shawl", "shawls", "kerchief"),
    category_word="shawl", **_SHAWL_COMMON))
register(Engine(
    family="shawl_wrap", title="a rectangle worked end to end",
    words=("wrap", "wraps", "stole", "stoles"), category_word="wrap",
    titles=(("shawl", "Wrap"),), **_SHAWL_COMMON))


# ==== 7. bags and totes =====================================================================
#
# Sized by what they carry: an ISO 216 sheet (A5, A4, A3) standing upright inside, with
# stated room (ease) across and above it. Worked in firm single crochet:
#   tote        a flat rectangular base worked in rows; the sides are picked up all round
#               its edge and worked up in joined rounds to a back-loop top band.
#   market bag  a round base from a magic ring, increased in sections at the flat rate; the
#               sides continue straight up in joined rounds to a back-loop top band.
# Two flat handles are worked separately and each end is sewn across a measured span of the
# top round, inside the bag. Handle length is a stated design figure (shoulder carry).

from ..cir.graded import SHEETS  # noqa: E402

BAG_EASE = (("sheet_width", 4.0), ("sheet_height", 2.0))
BAG_SIZES = {"adult": ("A5", "A4", "A3")}
TOTE_DEPTH_OF_WIDTH = 0.3              # the tote's base depth, of its width
HANDLE_CM = 55.0                        # each handle, end to end (shoulder carry)
HANDLE_WIDTH_CM = 3.0
HANDLE_INSET_OF_SIDE = 0.25             # a handle's ends sit a quarter in from each side
BAG_TOLERANCE = 0.06


class _BagRounds(Rounds):
    def ring(self, n: int, *, label: str = "") -> None:
        self.steps = []
        i = self.next_index
        self._finish(self._row([Op(self.fam.stitch, n)], note="into a magic ring"), n)
        self._record("magic_ring", i, i, n=(("sts", n),), label=label)


def bag(g: GradedSize, spec: WearableSpec) -> CIR:
    fam = StitchFamily("sc", "plain")
    width_cm = g.finished_cm("sheet_width")
    height_cm = g.finished_cm("sheet_height")
    band = g.rows(2.5, minimum=2)
    st, row = _st_cm(g.gauge), _row_cm(g.gauge)
    comps, seams, pieces, rounds = [], [], {}, set()
    if spec.family == "bag_tote":
        w = g.stitches(width_cm)
        d_rows = g.rows(width_cm * TOTE_DEPTH_OF_WIDTH, minimum=4)
        base = GF.Piece("base", fam, foundation=w, feature="panel", direction="bottom_up",
                        note="the flat base, worked in rows")
        base.even(d_rows, label="base")
        perim_cm = 2 * (w * st) + 2 * (d_rows * row)
        n = g.stitches(perim_cm)
        body = Rounds("body", fam, foundation=n, feature="body", direction="bottom_up",
                      foundation_kind="none",
                      note="picked up all round the base and worked up in joined rounds")
        comps.append(base)
        pieces["base"] = base.steps
        seams.append(Seam("pick_up", "body", "base", edge_a="bottom", edge_b="perimeter",
                          note=f"pick up {n} sts all round the base: {w} along each long "
                               f"edge and the rest evenly along the row ends; join"))
        pickups = [{"piece": "body", "into": "base", "edge_cm": round(perim_cm, 2),
                    "edge_sts": round(perim_cm / st, 2), "stitches": n, "rows_along": 0}]
    else:
        sections = flat_sections(g)
        circ_target = 2 * width_cm
        n = max(2 * sections, int(round(g.stitches(circ_target) / sections)) * sections)
        body = _BagRounds("body", fam, foundation=0, feature="body", direction="bottom_up",
                          foundation_kind="magic_ring",
                          note="worked from the centre of the base in joined rounds")
        body.ring(sections, label="base")
        body.section_inc(sections, n // sections - 1, label="base")
        pickups = []
    rounds.add("body")
    side_rounds = g.rows(height_cm, minimum=4) - band
    body.even(side_rounds, label="sides")
    body.even(band, loop="back", label="top band")
    top_round = body.rows[-1].index
    hw = GF._even(g.stitches(HANDLE_WIDTH_CM, minimum=4))
    h_rows = g.rows(HANDLE_CM)
    handle = GF.Piece("handle", fam, foundation=hw, make=2, feature="band",
                      direction="bottom_up", note="a flat strap handle")
    handle.even(h_rows, label="handle")
    comps += [body, handle]
    pieces["body"], pieces["handle"] = body.steps, handle.steps
    for edge in ("bottom", "top"):
        seams.append(Seam("whipstitch", "handle", "body", edge_a=edge, edge_b="top",
                          at_round=top_round, stitches_from_centre=hw // 2, mirrored=True,
                          note=f"sew this end of each handle inside the top band, across "
                               f"{hw} sts, a quarter of the way in from a side; the two "
                               f"handles face each other; sew through both loops all round "
                               f"the strap end and fasten off securely"))
    facts = WFacts(spec.family, pieces=pieces, rounds=frozenset(rounds))
    facts.pickups = pickups
    facts.seams = [{"seam": "handle end", "a": "handle", "b": "body top", "a_sts": hw,
                    "b_sts": 2 * (hw // 2), "a_edge_sts": hw, "b_edge_sts": n}]
    facts.numbers = {"circ_sts": n, "handle_sts": hw, "target_width_cm": width_cm,
                     "target_height_cm": height_cm}
    word = "tote" if spec.family == "bag_tote" else "market bag"
    return make_cir(g, spec, comps=[c.component() for c in comps], seams=seams, facts=facts,
                    construction="joined_rounds",
                    designer=(f"A {word} in firm single crochet, sized to hold an ISO 216 "
                              f"{g.size} sheet upright: "
                              + ("a flat base in rows with the sides picked up all round it"
                                 if word == "tote" else "a round base from a magic ring")
                              + ", straight sides in joined rounds to a back-loop band, and "
                                "two strap handles sewn inside the top."),
                    size_note=f"Finished width {n * st / 2:.1f} cm across, laid flat, to "
                              f"hold a sheet {g.body_cm('sheet_width'):g} cm wide")


def bag_measures(cir: CIR) -> dict[str, float]:
    from ..cir.geometry import _row_height_cm

    r = _compiled(cir)
    g = cir.gauge
    body = next(c for c in cir.components if c.name == "body")
    rows = [x for x in r.rows if x.component == "body"]
    circ = max(x.stitch_count for x in rows)
    first_full = next(i for i, x in enumerate(rows) if x.stitch_count == circ)
    height = sum(_row_height_cm(row, cir) for row in body.rows[first_full:])
    handle = next(c for c in cir.components if c.name == "handle")
    out = {"circumference": round(circ * _st_cm(g), 2), "width": round(circ * _st_cm(g) / 2, 2),
           "height": round(height, 2),
           "handle": round(sum(_row_height_cm(row, cir) for row in handle.rows), 2)}
    base = next((c for c in cir.components if c.name == "base"), None)
    if base is not None:
        out["depth"] = round(sum(_row_height_cm(row, cir) for row in base.rows), 2)
    else:
        out["depth"] = round(circ * _st_cm(g) / math.pi, 2)
    return out


def bag_gates(ctx) -> list:
    from ..gates.garment_fit import GarmentFinding

    out = []
    g, m, f, size, cir = ctx["g"], ctx["measured"], ctx["facts"], ctx["size"], ctx["cir"]

    def bad(code, msg):
        out.append(GarmentFinding(code, size, msg))

    sheet_w, sheet_h = g.body_cm("sheet_width"), g.body_cm("sheet_height")
    inner = m["width"] - (m["depth"] if f.construction == "bag_tote" else 0) / 2.0
    if m["width"] < sheet_w or m["height"] < sheet_h:
        bad("BAG_HOLDS", f"the bag is {m['width']:.1f} x {m['height']:.1f} cm; an {size} "
                         f"sheet is {sheet_w:g} x {sheet_h:g} cm")
    want = g.finished_cm("sheet_height")
    if abs(m["height"] - want) / want > BAG_TOLERANCE:
        bad("BAG_HEIGHT", f"built height {m['height']:.1f} cm against {want:g} cm")
    del inner
    if f.construction == "bag_market":
        last_base = [x.stitch_count for x in ctx["result"].rows if x.component == "body"]
        if int(f.numbers["circ_sts"]) % flat_sections(g) or last_base[0] != flat_sections(g):
            bad("BAG_BASE_SHAPE", "the round base is not increased at the flat rate")
    for s in cir.assembly:
        if s.piece_a == "handle" and 2 * (s.stitches_from_centre or 0) != \
                int(f.numbers["handle_sts"]):
            bad("GARMENT_SEAM_MISMATCH", f"a handle end of {f.numbers['handle_sts']} sts is "
                                         f"sewn across {2 * (s.stitches_from_centre or 0)}")
    if m["handle"] < 0.9 * HANDLE_CM:
        bad("BAG_HANDLE", f"the handle is {m['handle']:.1f} cm; the design states "
                          f"{HANDLE_CM:g} cm")
    out += pickup_rate(ctx)
    return out


def bag_schematic(sizes, ms) -> dict:
    sk = Sketch(ms, {"width": "Width, laid flat", "height": "Height, base to top",
                     "depth": "Base depth (round bag: base diameter)",
                     "handle": "Handle length"})
    mid = ms[len(ms) // 2]
    W, H, Hd = mid["width"], mid["height"], mid["handle"]
    x0, y0 = 6.0, 6.0 + Hd * 0.3
    sk.poly([(x0, y0), (x0 + W, y0), (x0 + W, y0 + H), (x0, y0 + H)], "bag, laid flat")
    for hx in (x0 + W * 0.25, x0 + W * 0.75):
        sk.line((hx - 1, y0), (hx - 1, y0 - Hd * 0.3))
    sk.line((x0 + W * 0.25 - 1, y0 - Hd * 0.3), (x0 + W * 0.75 - 1, y0 - Hd * 0.3))
    sk.dim((x0, y0 + H), (x0 + W, y0 + H), "width", "below")
    sk.dim((x0 + W, y0), (x0 + W, y0 + H), "height", "right")
    sk.note("depth")
    sk.text((x0 + W / 2, y0 - Hd * 0.3 - 1.5), "handles (see legend)")
    sk.note("handle")
    return _schematic(sk.items, sk.legend, W + 2 * x0 + 10, H + y0 + 8, sizes, ms, "bag")


def _bag_narrative(spec, facts) -> str:
    if facts.construction == "bag_tote":
        start = ("The base is a flat rectangle worked in rows. Stitches are picked up all the "
                 "way round its edge, and the sides are worked straight up from it in joined "
                 "rounds")
    else:
        start = ("The base is a flat circle, worked from a magic ring and increased in equal "
                 "sections on every round; the sides then carry straight on up in joined "
                 "rounds")
    return (start + " to a firm back-loop band at the top. The two strap handles are worked "
                    "flat, and each end is sewn securely inside the top band.")


_BAG_COMMON = dict(
    table=SHEETS, sizes=BAG_SIZES, requires=("sheet_width", "sheet_height"),
    primary="sheet_width", built_primary="circumference", builder=bag, measure=bag_measures,
    gates=bag_gates,
    chart=(("body_cm", "Holds a sheet (width)"), ("width_cm", "Width"),
           ("height_cm", "Height"), ("depth_cm", "Base"), ("handle_cm", "Handle")),
    narrative=_bag_narrative, schematic=bag_schematic, risk="B",
    abbreviations=("ch", "sc", "inc", "slst"), ease=(("adult", BAG_EASE),),
    yarn=(("adult", ("worsted", "cotton")),),
    forms=("bag",), constructions=("in_the_round", "seamless_tube", "flat_rows"),
    fit_note=("Sized to hold an ISO 216 sheet upright: 4 cm of stated room across it and "
              "2 cm above it."),
    tips=("Crochet firmly: a bag's fabric carries weight, so a hook one size smaller than "
          "your gauge hook for the handles is a good choice if they stretch.",),
    refuse=((r"\b(?:lin(?:ed|ing)|zip(?:per|pered)?|buttons?|clasp|magnetic|drawstring|"
             r"backpack|crossbody|clutch|purse|wallet|pockets?|mesh|net|string|"
             r"granny|tapestry|leather|wooden|bamboo|ring handles?|baby|kids?|child)\b",
             "the bag engines build an unlined single crochet tote or market bag with strap "
             "handles only"),),
    honest_phrases=(r"\b(?:strap )?handles?\b", r"\bhandled\b", r"\bstraps?\b"),
    category_word="bag",
)
register(Engine(family="bag_tote", title="a flat base in rows, sides picked up and worked "
                                         "in joined rounds, handles sewn on",
                words=("tote", "totes", "tote bag", "tote bags", "shopper"),
                **{**_BAG_COMMON, "category_word": "tote"}))
register(Engine(family="bag_market", title="a round base and sides in joined rounds, "
                                           "handles sewn on",
                words=("market bag", "market bags", "market tote", "farmers market bag"),
                **{**_BAG_COMMON, "category_word": "market bag"}))
