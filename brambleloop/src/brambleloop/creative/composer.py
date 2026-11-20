"""ENG-COMPOSER: assemble an ORIGINAL item from a declarative component plan of PROVEN primitives.

The owner's goal: production learns to build new things without a new hand-written engine per
product family. Every engine in `creative.fallback_constructions`, `creative.cushions` and
`creative.baby` is the same handful of moves -- a magic-ring disc, even rounds, decreases to a
gathered close, a flattened piece sewn across a placed round, a flat panel of rows, two edges
seamed -- hard-wired to one object. This module names those moves as primitives, solves their
parameters from the gauge, and composes them from a plan.

Patterns are software releases. A plan is DATA (a dict any proposer may write, including a
language model); it becomes a CIR only through the deterministic builders below, and that CIR is
then certified by exactly the chain every hand-written engine goes through
(`gates.certificate.certify`: compile, twin, assembly, reverse, originality, child safety,
Product Truth). Nothing here is approximated: a shape, join or detail the library cannot express
is REFUSED by name (`ComposeRefused.primitive`), and an unexpressible concept files an
engineering change request naming the missing primitive (`file_missing_primitive`), which is how
production learns what to build next.

Three layers:

1. `PRIMITIVES` -- the library. Each entry names the module that already validates it (the
   proving test) or the composer test that validates it here. Nothing outside it is accepted.
2. `compose(plan)` -- plan -> CIR. Every count is solved from the gauge (a sphere at a target
   diameter sets its widest round; an ovoid at a target height sets its even rounds); every
   finished dimension in the size note is read back from the compiled twin (`cir.twin`,
   `cir.geometry`), never typed.
3. `plan_for(concept)` -- concept -> plan, from a template library (`TEMPLATES`, `SUBJECTS`) and
   deterministic parameter solving. `adjudicate(proposals)` lets any number of model proposals
   compete; the validator alone decides, so a plan every model votes for is still refused if it
   does not validate.

Originality: every subject here is a generic animal or object form described by Brambleloop's
own shape vocabulary (an ovoid with folded wings), never another designer's pattern, chart or
stitch table; `gates.certificate` runs the originality and benchmark-similarity checks on the
result regardless.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from types import SimpleNamespace

from ..cir.model import CIR, Component, Material, Op, Provenance, Repeat, Row, Seam

COMPOSER = "creative.composer"
VERSION = "1.0.0"

# ---- the primitive library -------------------------------------------------------------------
# kind: shape | closure | join | detail. `proof` names where the primitive is validated: an
# existing engine's pinned test (the primitive is reused unchanged) or the composer's own test.
COMPOSER_PROOF = "tests/test_eng_composer.py"
PRIMITIVES: dict[str, dict] = {
    # shapes in the round
    "flat_circle": {"kind": "shape", "builder": "products.moment_candidates._disc",
                    "proof": "tests/test_eng_plush.py (ear and body discs); "
                             f"{COMPOSER_PROOF}::test_every_shape_primitive_validates"},
    "sphere": {"kind": "shape", "builder": "_disc + even rounds + _decrease_to",
               "proof": "tests/test_eng_plush.py::test_the_toy_is_a_closed_spiral_with_counts_"
                        "and_geometry_validated"},
    "ovoid": {"kind": "shape", "builder": "_disc + solved even rounds + _decrease_to",
              "proof": f"{COMPOSER_PROOF}::test_every_shape_primitive_validates"},
    "cylinder": {"kind": "shape", "builder": "_disc + even rounds (a vessel or a limb)",
                 "proof": "tests/test_eng_families.py (vessel); "
                          f"{COMPOSER_PROOF}::test_every_shape_primitive_validates"},
    "cone": {"kind": "shape", "builder": "magic ring + increases spread by shaping.distribute",
             "proof": f"{COMPOSER_PROOF}::test_every_shape_primitive_validates"},
    "tube": {"kind": "shape", "builder": "chain ring + even joined rounds, open both ends",
             "proof": f"{COMPOSER_PROOF}::test_every_shape_primitive_validates"},
    # flat panels
    "rectangle": {"kind": "shape", "builder": "flat rows of sc",
                  "proof": "tests/test_eng_families.py (flat panel)"},
    "trapezoid": {"kind": "shape", "builder": "cir.shaping.taper (both edges)",
                  "proof": f"{COMPOSER_PROOF}::test_every_shape_primitive_validates"},
    "triangle": {"kind": "shape", "builder": "cir.shaping.taper to a point",
                 "proof": f"{COMPOSER_PROOF}::test_every_shape_primitive_validates"},
    # closures
    "gathered": {"kind": "closure", "builder": "Component.closes + stuff_at_round",
                 "proof": "tests/test_eng_plush.py::test_closed_forms_refuse_a_wrong_stuffing_"
                          "point_or_an_open_closure"},
    "folded_flat": {"kind": "closure", "builder": "the open round flattened (the ear rule)",
                    "proof": "tests/test_eng_plush.py (ears)"},
    "open": {"kind": "closure", "builder": "the last round left open (a vessel rim)",
             "proof": "tests/test_eng_families.py (vessel)"},
    # joins
    "sewn": {"kind": "join", "builder": "Seam(whipstitch, at_round, stitches_from_centre)",
             "proof": "tests/test_eng_plush.py::test_joins_must_be_placed_measured_and_sewn_"
                      "through_both_loops"},
    "join_as_you_go": {"kind": "join", "builder": "Seam(slst, at_round, stitches_from_centre)",
                       "proof": f"{COMPOSER_PROOF}::test_join_as_you_go_is_placed_and_measured"},
    "seamed_panels": {"kind": "join", "builder": "Seam(mattress, named edges)",
                      "proof": "tests/test_eng_plush.py (cushions); "
                               f"{COMPOSER_PROOF}::test_seamed_panels_are_measured"},
    "surface": {"kind": "join", "builder": "Seam(sew, edge_b=surface)",
                "proof": "tests/test_eng_plush.py::test_surface_joins_are_measured_and_"
                         "misplacement_is_refused"},
    "rim": {"kind": "join", "builder": "Seam(whipstitch, top to top) round to round",
            "proof": f"{COMPOSER_PROOF}::test_seamed_panels_are_measured"},
    # details
    "colour_blocks": {"kind": "detail", "builder": "Row.color by stated fractions",
                      "proof": f"{COMPOSER_PROOF}::test_colour_blocks_and_edging"},
    "band_edging": {"kind": "detail", "builder": "plain contrast rounds/rows at the open edge",
                    "proof": f"{COMPOSER_PROOF}::test_colour_blocks_and_edging"},
}
SHAPES = tuple(k for k, v in PRIMITIVES.items() if v["kind"] == "shape")
CLOSURES = tuple(k for k, v in PRIMITIVES.items() if v["kind"] == "closure")
JOINS = tuple(k for k, v in PRIMITIVES.items() if v["kind"] == "join")
ROUND_SHAPES = ("flat_circle", "sphere", "ovoid", "cylinder", "cone", "tube")
FLAT_SHAPES = ("rectangle", "trapezoid", "triangle")

# Named primitives the library does NOT have. A plan or concept naming one is refused by that
# name, and the refusal files a change request for it. (word regex, primitive, why)
UNEXPRESSIBLE: tuple[tuple[str, str, str], ...] = (
    (r"\b(?:beanie|hat|toque|bonnet|beret)s?\b", "graded_head_fit",
     "a hat needs a crown-to-brim height and a negative ease from a published standard; the "
     "only sourced head data (CYC head circumference chart, re-read 2026-11-20) publishes "
     "circumference only"),
    (r"\b(?:bobbles?|popcorn|puff stitch)\b", "bobble_texture",
     "a bobble needs a calibrated height and yarn figure (F-074) the composer does not carry"),
    (r"\b(?:cables?|cabled)\b", "post_stitch_cable", "no composer primitive crosses post stitches"),
    (r"\b(?:fring(?:e|ed)|tassels?|pom[- ]?poms?)\b", "fringe_trim",
     "a cut-yarn trim has no rows and no counted geometry"),
    (r"\b(?:picots?|scallop(?:s|ed)?|shell edging|crab stitch|ruffles?)\b", "shaped_edging",
     "only a plain band edging is a composer primitive"),
    (r"\b(?:zip(?:per)?s?|buttons?|buttonholes?|snaps?|velcro)\b", "hard_closure",
     "a hardware closure is not a crochet primitive and is refused on child items"),
    (r"\b(?:lin(?:ed|ing)|pockets?|quilted|felted)\b", "lining_or_pocket",
     "a lining or pocket needs an opening-and-panel assembly the composer does not have"),
    (r"\b(?:granny|hexie|hexagon|motifs?)\b", "motif_join",
     "joined motifs need a motif primitive with corner geometry"),
    (r"\b(?:mosaic|tapestry|fair[- ]?isle|intarsia|c2c|graphghan)\b", "charted_colourwork",
     "charted colourwork belongs to the tapestry engine, not to colour blocks"),
    (r"\b(?:fluffy|furry|fur|loop stitch|shaggy|boucle)\b", "loop_texture",
     "a loop-stitch texture has no modelled yarn quantity"),
    (r"\b(?:safety eyes?|beads?|bells?|rattles?|squeakers?|teethers?|pellets?)\b", "hard_part",
     "a hard part is refused on any child's or stuffed item (gates.child_safety)"),
    (r"\b(?:sweaters?|cardigans?|socks?|mittens?|gloves?|slippers?)\b", "graded_garment",
     "a garment is the graded garment engine's (products.garment_release), not the composer's"),
)


class ComposeRefused(ValueError):
    """A plan or concept the library cannot express. `primitive` names what is missing."""

    def __init__(self, primitive: str, why: str):
        super().__init__(f"{primitive}: {why}")
        self.primitive = primitive
        self.why = why


# ---- gauge-solved builders -------------------------------------------------------------------

def _gauge(weight: str):
    from .prototype import gauge_for

    return gauge_for(weight)


def _round6(x: float, lo: int = 6) -> int:
    return max(lo, int(round(x / 6.0)) * 6)


def _sc_ring(cm_around: float, gauge, step: int = 6) -> int:
    """Stitches around, a whole number of 6-st wedges; `step=12` when the piece folds flat, so
    its flattened edge is an even count that can be centred on a round."""
    return max(step, int(round(cm_around * gauge.stitches_per_10cm / 10.0 / step)) * step)


def clear_diameter_cm(gauge, step: int = 12) -> float:
    """The smallest stated diameter at which a sewn-on piece worked from a ring clears the
    small-parts cylinder with its tolerance (`gates.small_parts`), at this gauge. Solved, so a
    template's ear, wing or fin is never drafted at a size the child-safety gate refuses."""
    from ..gates import small_parts

    st_mm = 100.0 / gauge.stitches_per_10cm
    need = small_parts.CYLINDER_MM + small_parts.SMALL_PARTS_TOLERANCE_MM
    n = step
    while n * st_mm / math.pi <= need:
        n += step
    return n / (gauge.stitches_per_10cm / 10.0) / math.pi


def _row_cm(gauge) -> float:
    return 10.0 / gauge.rows_per_10cm


def _assign_colours(rows: list[Row], main: str, blocks: list[dict] | None) -> None:
    """Colour blocks as fractions [from, to) of the piece's rows; the rest is the main colour."""
    n = len(rows)
    for r in rows:
        r.color = main
    for b in blocks or []:
        lo, hi = float(b["from"]), float(b["to"])
        a, z = int(round(lo * n)), int(round(hi * n))
        for r in rows[a:z]:
            r.color = b["colour"]


def _ring_rows(spec: dict, gauge) -> tuple[list[Row], dict]:
    """The rounds of a shaped piece in the round, solved from the gauge. Returns (rows, facts)."""
    from ..cir.shaping import distribute
    from ..products.moment_candidates import _decrease_to, _disc, _Rows

    shape, colour = spec["shape"], spec.get("colour", "MC")
    step = 12 if spec.get("closure") == "folded_flat" else 6
    rows = _Rows()
    facts: dict = {}
    rc = _row_cm(gauge)
    if shape == "tube":
        n = _sc_ring(spec["around_cm"], gauge)
        even = max(2, int(round(spec["length_cm"] / rc)))
        for _ in range(even):
            rows.add([Op("sc", n)], n, colour)
        facts.update(widest=n, even=even)
        return rows.rows, facts
    if shape == "cone":
        n = _sc_ring(math.pi * spec["base_cm"], gauge, step)
        total = max(2, int(round(spec["height_cm"] / rc)))
        steps = (n - 6) // 6
        if steps > total - 1:
            raise ComposeRefused("cone", f"a {spec['base_cm']} cm cone over {total} rounds would "
                                         f"increase faster than once per round; it would frill")
        rows.add([Op("sc", 6)], 6, colour)
        count = 6
        for k, ev in enumerate(distribute(steps, total - 1)):
            if ev:
                per = count // 6
                body = [Op("inc")] if per == 1 else [Op("sc", per - 1), Op("inc")]
                count += 6
                rows.add([Repeat(body, times=6)], count, colour)
            else:
                rows.add([Op("sc", count)], count, colour)
        facts.update(widest=count, even=0)
        return rows.rows, facts
    if shape == "flat_circle":
        n = _sc_ring(math.pi * spec["diameter_cm"], gauge)
        _disc(rows, n, colour)
        facts.update(widest=n, even=0)
        return rows.rows, facts
    if shape in ("sphere", "ovoid", "cylinder"):
        across = spec["diameter_cm"] if shape != "ovoid" else spec["width_cm"]
        n = _sc_ring(math.pi * across, gauge, step)
        _disc(rows, n, colour)
        inc_rounds = rows.last
        if shape == "cylinder":
            even = max(1, int(round(spec["length_cm"] / rc)) - inc_rounds)
            for _ in range(even):
                rows.add([Op("sc", n)], n, colour)
            facts.update(widest=n, even=even)
            return rows.rows, facts
        close = spec.get("close_sts", 6)
        dec_rounds = (n - close) // 6
        if shape == "sphere":
            # The meridian of a sphere is half its circumference.
            meridian = math.pi * across / 2.0
        else:
            a, b = across / 2.0, spec["height_cm"] / 2.0
            if b <= a * 1.15:
                raise ComposeRefused("ovoid", f"a {spec['width_cm']} x {spec['height_cm']} cm "
                                              f"ovoid is not taller than it is wide; plan a "
                                              f"sphere")
            h = ((a - b) / (a + b)) ** 2      # Ramanujan: half the ellipse's perimeter
            meridian = math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h))) / 2.0
        even = max(1, int(round(meridian / rc)) - inc_rounds - dec_rounds)
        for _ in range(even):
            rows.add([Op("sc", n)], n, colour)
        _decrease_to(rows, n, close, colour)
        facts.update(widest=n, even=even, close=close)
        return rows.rows, facts
    raise ComposeRefused(shape, f"{shape!r} is not a round shape in the library")


def _flat_rows(spec: dict, gauge) -> tuple[list[Row], dict]:
    from ..cir.shaping import taper

    shape, colour = spec["shape"], spec.get("colour", "MC")
    spc = gauge.stitches_per_10cm / 10.0
    n_rows = max(2, int(round(spec["height_cm"] / _row_cm(gauge))))
    if shape == "rectangle":
        n = max(2, int(round(spec["width_cm"] * spc)))
        rows = [Row(index=i, ops=[Op("sc", n)], declared_count=n, turning_chain=1, color=colour)
                for i in range(1, n_rows + 1)]
        return rows, {"widest": n, "foundation": n}
    if shape in ("trapezoid", "triangle"):
        bottom = int(round(spec["bottom_cm" if shape == "trapezoid" else "base_cm"] * spc))
        top = int(round(spec["top_cm"] * spc)) if shape == "trapezoid" else 2
        if (bottom - top) % 2:
            bottom += 1
        t = taper(bottom, top, n_rows, edge="both", color=colour)
        return list(t.rows), {"widest": max(bottom, top), "foundation": bottom}
    raise ComposeRefused(shape, f"{shape!r} is not a flat shape in the library")


def build_part(spec: dict, gauge) -> tuple[Component, dict]:
    """One plan part -> one CIR component (and the solved facts the joins need)."""
    shape = spec.get("shape")
    # Defence in depth: the builders refuse by name on their own, so a plan that somehow
    # skipped `validate` still cannot reach a builder with a shape or size it does not have.
    if shape not in SHAPES:
        raise ComposeRefused(str(shape), f"{shape!r} is not a shape in the primitive library")
    missing = [d for d in _REQUIRED_DIMS[shape] if not isinstance(spec.get(d), (int, float))]
    if missing:
        raise ComposeRefused(shape, f"part {spec.get('name')!r} states no {missing}")
    closure = spec.get("closure", "open")
    if shape in ROUND_SHAPES:
        rows, facts = _ring_rows(spec, gauge)
    else:
        rows, facts = _flat_rows(spec, gauge)
    main = spec.get("colour", "MC")
    _assign_colours(rows, main, spec.get("blocks"))
    edging = spec.get("edging")
    if edging:
        last = rows[-1]
        n = last.declared_count
        for k in range(int(edging["rows"])):
            rows.append(Row(index=last.index + 1 + k, ops=[Op("sc", n)], declared_count=n,
                            color=edging["colour"], turning_chain=last.turning_chain))
    kw: dict = {}
    if shape in ROUND_SHAPES:
        kw["construction"] = "joined_rounds" if shape == "tube" else "spiral_rounds"
        kw["foundation_kind"] = "chain" if shape == "tube" else "magic_ring"
        kw["foundation"] = facts["widest"] if shape == "tube" else 0
    else:
        kw.update(construction="flat_rows", foundation_kind="chain",
                  foundation=facts["foundation"], grain="up")
    if closure == "gathered":
        last_widest = max(r.index for r in rows if r.declared_count == facts["widest"])
        after = [r for r in rows if r.index > last_widest]
        stuff = next((r.index for r in after if r.declared_count == 18), None)
        if stuff is None:
            stuff = next((r.index for r in after if r.declared_count == 12), None)
        kw.update(closes=True, stuff_at_round=stuff)
    note = spec.get("note") or ""
    if closure == "folded_flat":
        note = (note + " " if note else "") + (
            f"Fasten off and flatten the open round so it closes into a straight edge of "
            f"{rows[-1].declared_count // 2} sts; leave a 30 cm tail for sewing.")
    comp = Component(name=spec["name"], rows=rows, make=int(spec.get("make", 1)),
                     note=note or None, **kw)
    facts["last"] = rows[-1].declared_count
    facts["rounds"] = len(rows)
    return comp, facts


# ---- validation -----------------------------------------------------------------------------

_REQUIRED_DIMS = {
    "flat_circle": ("diameter_cm",), "sphere": ("diameter_cm",),
    "ovoid": ("width_cm", "height_cm"), "cylinder": ("diameter_cm", "length_cm"),
    "cone": ("base_cm", "height_cm"), "tube": ("around_cm", "length_cm"),
    "rectangle": ("width_cm", "height_cm"), "trapezoid": ("bottom_cm", "top_cm", "height_cm"),
    "triangle": ("base_cm", "height_cm"),
}
MAX_DIM_CM = 120.0


def _text_refusal(*texts: str) -> ComposeRefused | None:
    from .fallback_constructions import fold_title

    for text in texts:
        folded = fold_title(text or "")
        for rx, primitive, why in UNEXPRESSIBLE:
            hit = re.search(rx, folded)
            if hit:
                return ComposeRefused(primitive, f"{hit.group(0)!r} names {primitive}: {why}")
    return None


def validate(plan: dict) -> list[str]:
    """Every reason this plan cannot be composed, deterministically. Empty means expressible.

    Each reason starts with the missing or misused primitive's name, so a refusal is a
    request for that primitive and nothing is approximated."""
    out: list[str] = []
    if not isinstance(plan, dict):
        return ["plan: not a mapping"]
    for key in ("slug", "title", "yarn_weight", "colours", "parts"):
        if not plan.get(key):
            out.append(f"plan: missing {key!r}")
    if out:
        return out
    named = _text_refusal(plan["title"], *(f.get("name", "") for f in plan.get("features", [])))
    if named:
        out.append(str(named))
    try:
        _gauge(plan["yarn_weight"])
    except Exception as exc:  # noqa: BLE001 - an unknown weight has no gauge to solve from
        out.append(f"gauge: {exc}")
    palette = set(plan["colours"])
    names = [p.get("name") for p in plan["parts"]]
    if len(set(names)) != len(names) or not all(names):
        out.append(f"parts: names must be present and unique, got {names}")
    used: set[str] = set()
    for p in plan["parts"]:
        shape = p.get("shape")
        if shape not in SHAPES:
            out.append(f"{shape}: shape of part {p.get('name')!r} is not in the primitive "
                       f"library {list(SHAPES)}")
            continue
        for d in _REQUIRED_DIMS[shape]:
            v = p.get(d)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) \
                    or not 0 < v <= MAX_DIM_CM:
                out.append(f"{shape}: part {p['name']!r} {d}={v!r} is not a size in "
                           f"(0, {MAX_DIM_CM:g}] cm")
        closure = p.get("closure", "open")
        if closure not in CLOSURES:
            out.append(f"{closure}: closure of part {p['name']!r} is not in {list(CLOSURES)}")
        elif closure == "gathered" and shape not in ("sphere", "ovoid"):
            out.append(f"gathered: only a sphere or an ovoid closes; part {p['name']!r} is a "
                       f"{shape}")
        elif closure == "folded_flat" and shape not in ("cylinder", "cone"):
            out.append(f"folded_flat: only a cylinder or a cone folds flat; part "
                       f"{p['name']!r} is a {shape}")
        elif shape in ("sphere", "ovoid") and closure != "gathered":
            out.append(f"gathered: a {shape} ({p['name']!r}) is a closed form and must state "
                       f"the gathered closure")
        colours = [p.get("colour", "MC")] + [b.get("colour") for b in p.get("blocks") or []]
        if p.get("edging"):
            colours.append(p["edging"].get("colour"))
            if p["edging"].get("style", "band") != "band" or not \
                    1 <= int(p["edging"].get("rows", 0)) <= 6:
                out.append(f"band_edging: part {p['name']!r} edging must be a plain band of "
                           f"1-6 rows")
        for c in colours:
            if c not in palette:
                out.append(f"colour_blocks: part {p['name']!r} names colour {c!r} not in the "
                           f"palette {sorted(palette)}")
        used.update(c for c in colours if c)
        spans = sorted((float(b["from"]), float(b["to"])) for b in p.get("blocks") or [])
        prev = 0.0
        for lo, hi in spans:
            if not 0.0 <= lo < hi <= 1.0 or lo < prev:
                out.append(f"colour_blocks: part {p['name']!r} blocks must be ordered, "
                           f"non-overlapping fractions of the rows")
            prev = hi
        if not 1 <= int(p.get("make", 1)) <= 4:
            out.append(f"make: part {p['name']!r} make must be 1-4")
    if palette - used:
        out.append(f"colour_blocks: palette colours {sorted(palette - used)} are worked "
                   f"nowhere; a listed colour must be used")
    parts = {p.get("name"): p for p in plan["parts"]}
    for j in plan.get("joins", []):
        kind = j.get("kind")
        if kind not in JOINS:
            out.append(f"{kind}: join {j.get('a')}->{j.get('b')} is not in the library "
                       f"{list(JOINS)}")
            continue
        a, b = parts.get(j.get("a")), parts.get(j.get("b"))
        if a is None or b is None:
            out.append(f"{kind}: join names an unknown part ({j.get('a')}, {j.get('b')})")
            continue
        if kind in ("sewn", "join_as_you_go"):
            if j.get("ends"):
                if kind != "sewn" or a["shape"] != "rectangle":
                    out.append(f"{kind}: only a rectangle strap is sewn by its two ends "
                               f"({a['name']!r} is a {a['shape']})")
            elif a.get("closure") not in ("folded_flat", "open") or a["shape"] not in \
                    ("cylinder", "cone", "tube"):
                out.append(f"{kind}: {a['name']!r} must be an open or folded-flat cylinder, "
                           f"cone or tube to be sewn across a round")
            if b["shape"] not in ROUND_SHAPES:
                out.append(f"{kind}: {b['name']!r} must be worked in rounds")
            at = j.get("at")
            lo_ok = 0.0 < float(at) <= 1.0 if isinstance(at, (int, float)) else False
            if not lo_ok or (float(at) >= 1.0 and not j.get("ends")):
                out.append(f"{kind}: {a['name']}->{b['name']} needs 'at' as a fraction (0, 1) "
                           f"of {b['name']}'s rounds")
        elif kind == "seamed_panels":
            if a["shape"] not in FLAT_SHAPES or b["shape"] not in FLAT_SHAPES:
                out.append(f"seamed_panels: {a['name']}+{b['name']} must both be flat panels")
            edges = ("top", "bottom", "left", "right")
            if j.get("edge_a") not in edges or j.get("edge_b") not in edges:
                out.append(f"seamed_panels: {a['name']}+{b['name']} must name both edges")
        elif kind == "rim":
            if a["shape"] not in ROUND_SHAPES or b["shape"] not in ROUND_SHAPES:
                out.append(f"rim: {a['name']}+{b['name']} must both be worked in rounds")
        elif kind == "surface":
            if b["shape"] not in FLAT_SHAPES:
                out.append(f"surface: {b['name']!r} must be a flat panel to lie on")
    return out


# ---- plan -> CIR ----------------------------------------------------------------------------

def plan_digest(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, default=str).encode()).hexdigest()


SEWN_GAP_STS = 6        # = fallback_constructions.AMI_EAR_GAP

_SEW_NOTE = ("Sew through both loops of every stitch of its closed edge and through the "
             "fabric beneath, across and back again, so the whole edge is joined and no single "
             "stitch carries it; knot the tail on the inside and bury it through at least 5 cm "
             "of stitches")


def _join_seams(plan: dict, comps: dict, facts: dict) -> tuple[list[Seam], list[str]]:
    seams: list[Seam] = []
    problems: list[str] = []
    used_on_round: dict[tuple[str, int], int] = {}
    for j in plan.get("joins", []):
        kind, a, b = j["kind"], j["a"], j["b"]
        ca, cb = comps[a], comps[b]
        if kind in ("sewn", "join_as_you_go"):
            n_b = len(cb.rows)
            at_round = cb.rows[max(0, min(n_b - 1, int(round(float(j["at"]) * n_b)) - 1))].index
            round_count = next(r.declared_count for r in cb.rows if r.index == at_round)
            copies = 2 if j.get("mirrored") else 1
            where = j.get("where", "at the front")
            if j.get("ends"):
                # A flat strap: each end's foundation/last row edge is sewn across its own width.
                flat = facts[a]["widest"]
                if flat % 2:
                    problems.append(f"sewn: {a!r} is {flat} sts wide, which cannot be centred")
                    continue
                used_on_round[(b, at_round)] = used_on_round.get((b, at_round), 0) + \
                    2 * flat * ca.make
                for edge, which in (("bottom", "first"), ("top", "other")):
                    seams.append(Seam(
                        "whipstitch", a, b, edge_a=edge, edge_b="top", at_round=at_round,
                        stitches_from_centre=flat // 2, mirrored=bool(j.get("mirrored")),
                        note=(f"Sew the {which} end of each {a} across {flat} sts of round "
                              f"{at_round} of the {b} ({round_count} sts), {where}, without "
                              f"twisting the {a}. Sew through both loops of every stitch and "
                              f"through the fabric beneath, across and back again; bury the "
                              f"tails through at least 5 cm of stitches")))
                continue
            flat = facts[a]["last"] // 2
            if flat % 2:
                problems.append(f"{kind}: {a!r} flattens to {flat} sts, which cannot be centred")
                continue
            used_on_round[(b, at_round)] = used_on_round.get((b, at_round), 0) + flat * ca.make
            each = "each" if copies == 2 else "the"
            if kind == "sewn":
                method = "whipstitch"
                lead = (f"Sew {each} flattened {a} across {flat} sts of round {at_round} of the "
                        f"{b} ({round_count} sts), {where}")
            else:
                method = "slst"
                lead = (f"Join {each} {a} as you go: hold its flattened last round against "
                        f"round {at_round} of the {b} ({round_count} sts), {where}, and slip "
                        f"stitch through both layers and the {b} across {flat} sts")
            seams.append(Seam(
                method, a, b, edge_a="top", edge_b="top", at_round=at_round, spans_rounds=1,
                stitches_from_centre=flat // 2, mirrored=bool(j.get("mirrored")),
                note=(lead + (", mirrored" if copies == 2 else "")
                      + f". {_SEW_NOTE}" + (f". {j['note']}" if j.get("note") else ""))))
        elif kind == "seamed_panels":
            seams.append(Seam("mattress", a, b, edge_a=j["edge_a"], edge_b=j["edge_b"],
                              note=(f"With right sides out, mattress-stitch the {a}'s "
                                    f"{j['edge_a']} edge to the {b}'s {j['edge_b']} edge, "
                                    f"through both loops; bury the tails"
                                    + (f". {j['note']}" if j.get("note") else ""))))
        elif kind == "rim":
            seams.append(Seam("whipstitch", a, b, edge_a="top", edge_b="top",
                              at_round=cb.rows[-1].index,
                              stuff_before_closing=bool(j.get("insert_before_closing")),
                              note=(f"Hold the {a} and the {b} wrong sides together and "
                                    f"whipstitch the last rounds together through both loops of "
                                    f"every stitch; bury the tails"
                                    + (f". {j['note']}" if j.get("note") else ""))))
        elif kind == "surface":
            n_rows = len(cb.rows)
            row = cb.rows[max(0, min(n_rows - 1, int(round(float(j.get("at", 0.5)) * n_rows))
                                     - 1))].index
            seams.append(Seam("sew", a, b, edge_a="bottom", edge_b="surface", at_round=row,
                              spans_rounds=1, stitches_from_centre=int(j.get("offset_sts", 0)),
                              note=(f"Centre the {a}'s closed end on row {row} of the {b}, on "
                                    f"the centre line; sew all round its last 4 rounds through "
                                    f"both loops and the {b}, around twice, knot on the wrong "
                                    f"side and bury the tail through at least 5 cm of stitches")))
    for (b, rnd), sts in used_on_round.items():
        count = next(r.declared_count for r in comps[b].rows if r.index == rnd)
        # The amigurumi engine's rule (AMI_EAR_GAP): pieces on one round keep a gap at the
        # front and at the back, so they sit apart rather than wrapping the round.
        if sts + 2 * SEWN_GAP_STS > count:
            problems.append(f"sewn: pieces sewn to round {rnd} of {b!r} need {sts} sts plus "
                            f"{SEWN_GAP_STS} sts clear front and back, and the round has "
                            f"{count}")
    return seams, problems


def _stuffed(plan: dict) -> bool:
    return any(p.get("closure") == "gathered" for p in plan["parts"]) or any(
        j.get("insert_before_closing") for j in plan.get("joins", []))


def compose(plan: dict, *, version: str = VERSION) -> CIR:
    """Plan -> CIR, or ComposeRefused naming the primitive. Deterministic in the plan."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    # b18-c A2: a malformed proposal (a non-numeric count, a part that is not a dict) is a
    # named refusal, never a crash that aborts adjudication of the proposals after it.
    if not isinstance(plan, dict):
        raise ComposeRefused("plan", f"the plan is a {type(plan).__name__}, not a dict")
    try:
        problems = validate(plan)
    except ComposeRefused:
        raise
    except Exception as exc:  # noqa: BLE001 - malformed input is refused by name
        raise ComposeRefused("plan", f"malformed plan: {type(exc).__name__}: {exc}") from exc
    if problems:
        primitive = problems[0].split(":", 1)[0]
        raise ComposeRefused(primitive, "; ".join(problems))
    gauge = _gauge(plan["yarn_weight"])
    comps: dict[str, Component] = {}
    facts: dict[str, dict] = {}
    for spec in plan["parts"]:
        comp, f = build_part(spec, gauge)
        comps[comp.name] = comp
        facts[comp.name] = f
    seams, problems = _join_seams(plan, comps, facts)
    if problems:
        raise ComposeRefused(problems[0].split(":", 1)[0], "; ".join(problems))
    weight = plan["yarn_weight"]
    fibre = plan.get("fibre", "acrylic")
    palette = list(plan["colours"])
    materials = [Material(name=f"{weight} {fibre} ({c})", yarn_weight=weight, color_id=c)
                 for c in palette]
    stuffed = _stuffed(plan)
    if any(p.get("closure") == "gathered" for p in plan["parts"]):
        materials.append(Material(name="new polyester fibrefill (toy stuffing)"))
    for extra in plan.get("extra_materials", []):
        materials.append(Material(name=extra))
    if plan.get("face"):
        materials.append(Material(name=f"dark {weight} {fibre} scrap for the embroidered "
                                       f"features", yarn_weight=weight))
    # A gathered closed form is a stuffed toy shape: class C (gates.risk_matrix), as every
    # amigurumi engine declares. A cover sewn shut over a pillow form is left to the matrix.
    risk = "C" if any(p.get("closure") == "gathered" for p in plan["parts"]) else \
        plan.get("risk_class", "A")
    first = plan["parts"][0]
    construction = comps[first["name"]].construction
    used = sorted({p["shape"] for p in plan["parts"]}
                  | {p.get("closure", "open") for p in plan["parts"]}
                  | {j["kind"] for j in plan.get("joins", [])}
                  | ({"colour_blocks"} if any(p.get("blocks") for p in plan["parts"]) else set())
                  | ({"band_edging"} if any(p.get("edging") for p in plan["parts"]) else set()))
    provenance = Provenance(concept_key=plan["slug"], brief_digest=plan_digest(plan),
                            primitives_used=tuple([COMPOSER] + [f"{COMPOSER}.{u}" for u in used]),
                            generated_by="brambleloop")
    notes = plan.get("designer_notes") or (
        f"{plan.get('category', 'item')} composed from proven primitives: "
        + ", ".join(f"{p['name']} ({p['shape']}, {p.get('closure', 'open')})"
                    for p in plan["parts"]))
    if plan.get("face"):
        notes += (". Features are embroidered with yarn only: " + plan["face"])
    draft = CIR(slug=plan["slug"], title=plan["title"], version=version,
                construction=construction, risk_class=risk, colors=dict(plan["colours"]),
                gauge=gauge, materials=materials, components=list(comps.values()),
                assembly=seams, designer_notes=notes, provenance=provenance)
    # Product Truth: the size note is read back from the compiled geometry, never typed.
    result = compile_cir(draft)
    if not result.ok:
        bad = [f"{f.code}: {f.message}" for f in result.findings if f.is_error][:3]
        raise ComposeRefused("compile", "; ".join(bad))
    twins = {c.name: build_twin(draft, result, component=c.name) for c in draft.components}
    draft.finished_size_note = size_note(draft, twins, plan)
    return draft


def size_note(cir: CIR, twins: dict, plan: dict) -> str:
    """The finished size, measured from the twin of the piece that carries the object.

    Written as "about N cm" figures, the form `gates.risk_matrix.stated_dimensions` reads, so
    every figure stated here is re-checked against the twin at certification (F-117). (A
    "W x H cm" statement is NOT read by that check today; see the ENG-COMPOSER review
    request.)"""
    body = cir.components[0]
    twin = twins[body.name]
    gauge = cir.gauge
    tail = " at the stated gauge. Computed from the stitch counts, not yet measured on a " \
           "worked sample."
    if body.closes:
        around = max(r.declared_count for r in body.rows) / gauge.stitches_per_10cm * 10.0
        return (f"The {body.name} is about {around:.1f} cm around its widest round at the "
                f"stated gauge. Computed from the stitch counts, not yet measured on a worked "
                f"sample; its height depends on the stuffing and is measured on the sample.")
    w, h = twin.width_cm, twin.height_cm
    if body.construction == "flat_rows" and w and h:
        return f"The {body.name} is about {w:.1f} cm wide and about {h:.1f} cm tall{tail}"
    if w and plan["parts"][0]["shape"] == "flat_circle":
        return f"The {body.name} is about {w:.1f} cm across{tail}"
    if w and h and h > 0.5:
        return f"The {body.name} is about {w:.1f} cm across and about {h:.1f} cm tall{tail}"
    if w:
        return f"The {body.name} is about {w:.1f} cm across{tail}"
    raise ComposeRefused("size_truth", f"the twin of {body.name!r} gives no finished size")


# ---- concepts -> plans ------------------------------------------------------------------------
# A subject is a generic form in Brambleloop's own shape vocabulary. Dimensions are design
# choices stated in cm; every count is solved from the gauge by `compose`.
SUBJECTS: dict[str, dict] = {
    "owl": {
        "body": {"shape": "ovoid", "width_cm": 11.0, "height_cm": 14.0, "closure": "gathered"},
        "pieces": [
            {"name": "wing", "shape": "cylinder", "diameter_cm": 3.0, "length_cm": 5.0,
             "closure": "folded_flat", "make": 2, "colour": 1,
             "join": {"kind": "sewn", "at": 0.45, "mirrored": True,
                      "where": "one at each side of the body"}},
            {"name": "ear tuft", "shape": "cone", "base_cm": 2.6, "height_cm": 3.0,
             "closure": "folded_flat", "make": 2, "colour": 1,
             "join": {"kind": "sewn", "at": 0.3, "mirrored": True,
                      "where": "at the top of the head, one either side of the centre line"}}],
        "face": ("two eyes of 6 straight stitches each worked as a ring, and a small beak of 5 "
                 "satin stitches between them, worked through the fabric with every knot pulled "
                 "to the inside"),
    },
    "whale": {
        "body": {"shape": "ovoid", "width_cm": 12.0, "height_cm": 16.0, "closure": "gathered"},
        "pieces": [
            {"name": "fin", "shape": "cylinder", "diameter_cm": 2.8, "length_cm": 4.0,
             "closure": "folded_flat", "make": 2, "colour": 1,
             "join": {"kind": "sewn", "at": 0.55, "mirrored": True,
                      "where": "one at each side of the body"}},
            {"name": "tail", "shape": "cone", "base_cm": 3.4, "height_cm": 5.0,
             "closure": "folded_flat", "colour": 1,
             "join": {"kind": "sewn", "at": 0.85, "where": "at the back, centred"}}],
        "face": ("two closed eyes of 5 straight stitches each and a smile of 7 back stitches, "
                 "worked through the fabric with every knot pulled to the inside"),
    },
    "lamb": {
        "body": {"shape": "sphere", "diameter_cm": 9.5, "closure": "gathered"},
        "pieces": [
            {"name": "ear", "shape": "cylinder", "diameter_cm": 2.8, "length_cm": 4.0,
             "closure": "folded_flat", "make": 2, "colour": 1,
             "join": {"kind": "sewn", "at": 0.3, "mirrored": True,
                      "where": "at the sides of the head"}}],
        "face": ("two sleeping eyes of 5 straight stitches each and a nose of 5 satin stitches, "
                 "worked through the fabric with every knot pulled to the inside"),
    },
}
SUBJECT_SYNONYMS = {"owlet": "owl", "whales": "whale", "sheep": "lamb", "lambkin": "lamb"}

# Templates: form -> how a concept's subject, size and features become a plan. Each returns a
# plan dict; `compose` validates it, so a template can never smuggle in an unproven primitive.
TOTE_SIZES = {"small": (24.0, 26.0), "medium": (28.0, 32.0), "large": (32.0, 36.0)}
TOTE_SIZE_BASIS = "products.vessels.BASKET_SIZES-style house design sizes (design choice)"
SLEEVE_SIZES = {"tablet": (26.0, 20.0), "laptop": (36.0, 26.0)}   # (across, up) cm
ROUND_CUSHION_FORMS = {"14 in": 35.5, "16 in": 40.5}             # round pillow-form diameter


def _subject(concept) -> str | None:
    s = str(getattr(concept, "subject", "") or "").lower().strip()
    s = SUBJECT_SYNONYMS.get(s, s)
    return s if s in SUBJECTS else None


def _palette(concept, n: int) -> tuple[dict, list[str]]:
    colours = dict(getattr(concept, "colours", None) or getattr(concept, "colors", None) or {})
    keys = list(colours)
    if not keys:
        raise ComposeRefused("colour_blocks", "the concept names no colour")
    if len(keys) > n:
        raise ComposeRefused("colour_blocks", f"the plan works {n} colours and the concept "
                                              f"names {len(keys)}; a listed colour must be "
                                              f"worked")
    used = keys + [keys[0]] * (n - len(keys))      # one colour works every piece
    return {k: colours[k] for k in keys}, used


def _cleared(piece: dict, gauge) -> dict:
    """A sewn-on piece raised, if needed, to the solved small-parts clearance diameter."""
    d = clear_diameter_cm(gauge)
    key = {"cylinder": "diameter_cm", "cone": "base_cm"}.get(piece["shape"])
    if key and piece[key] < d:
        piece[key] = round(d + 0.05, 1)
        if piece["shape"] == "cone":     # keep the cone no steeper than one increase a round
            piece["height_cm"] = max(piece["height_cm"], round(d * 1.2, 1))
    return piece


def _toy_plan(concept, subject: str) -> dict:
    spec = SUBJECTS[subject]
    colours, keys = _palette(concept, 2)
    body = {"name": "body", "colour": keys[0], **spec["body"],
            "note": "Worked from the top down as one closed piece; work tightly so the stuffing "
                    "does not show between stitches."}
    parts, joins = [body], []
    gauge = _gauge(concept.yarn_weight)
    for piece in spec["pieces"]:
        p = _cleared({k: v for k, v in piece.items() if k != "join"}, gauge)
        p["colour"] = keys[piece.get("colour", 0)]
        parts.append(p)
        joins.append({"a": p["name"], "b": "body", **piece["join"]})
    return {"slug": concept.slug, "title": concept.title, "category": concept.category,
            "yarn_weight": concept.yarn_weight, "colours": colours, "parts": parts,
            "joins": joins, "face": spec["face"]}


def _lovey_plan(concept, subject: str) -> dict:
    spec = SUBJECTS[subject]
    colours, keys = _palette(concept, 2)
    head_body = dict(spec["body"])
    if head_body["shape"] == "ovoid":       # a lovey's head is a ball whatever the toy's body
        head_body = {"shape": "sphere", "diameter_cm": 9.5, "closure": "gathered"}
    parts = [{"name": "square", "shape": "rectangle", "width_cm": 30.0, "height_cm": 30.0,
              "colour": keys[1], "note": "Worked flat; a plain square with no loops, picots or "
                                         "tassels."},
             {"name": "head", "colour": keys[0], **head_body}]
    joins = [{"kind": "surface", "a": "head", "b": "square", "at": 0.5}]
    for piece in spec["pieces"]:
        if piece["join"]["at"] > 0.6:
            continue        # a tail or a low fin belongs to a body, not a head
        p = _cleared({k: v for k, v in piece.items() if k != "join"},
                     _gauge(concept.yarn_weight))
        p["colour"] = keys[0]
        parts.append(p)
        joins.append({"a": p["name"], "b": "head", **piece["join"]})
    return {"slug": concept.slug, "title": concept.title, "category": concept.category,
            "yarn_weight": concept.yarn_weight, "colours": colours, "parts": parts,
            "joins": joins, "face": spec["face"]}


def _tote_plan(concept) -> dict:
    size = str(getattr(concept, "size", "") or "medium")
    if size not in TOTE_SIZES:
        raise ComposeRefused("tote_size", f"size {size!r} is not one of {sorted(TOTE_SIZES)}")
    across, tall = TOTE_SIZES[size]
    colours, keys = _palette(concept, 2)
    # Solved: the strap is a whole, even number of stitches (STRAP_STITCHES, the tote engine's),
    # so each end centres on the round it is sewn across.
    from .fallback_constructions import STRAP_STITCHES

    strap_cm = round(STRAP_STITCHES / (_gauge(concept.yarn_weight).stitches_per_10cm / 10.0), 2)
    return {"slug": concept.slug, "title": concept.title, "category": concept.category,
            "yarn_weight": concept.yarn_weight, "colours": colours, "fibre": "cotton",
            "parts": [
                {"name": "bag", "shape": "cylinder", "diameter_cm": across / math.pi * 2.0,
                 "length_cm": tall, "closure": "open", "colour": keys[0],
                 "blocks": [{"colour": keys[1], "from": 0.55, "to": 0.7}],
                 "edging": {"colour": keys[1], "rows": 3, "style": "band"},
                 "note": "A round base, then straight walls; a contrast block and a rim band."},
                {"name": "strap", "shape": "rectangle", "width_cm": strap_cm, "height_cm": 45.0,
                 "make": 2, "colour": keys[1],
                 "note": "Make 2. A flat strap of single crochet rows."}],
            "joins": [{"kind": "sewn", "a": "strap", "b": "bag", "at": 1.0, "ends": True,
                       "mirrored": True,
                       "where": "at the front and the back, each strap's two ends a hand's "
                                "width apart"}],
            "designer_notes": (f"bag concept composed as a round-based tote, {across:.0f} cm "
                               f"across flat and {tall:.0f} cm tall (design choice), with a "
                               f"contrast colour block, a band edging and two flat straps")}


def _round_cushion_plan(concept) -> dict:
    form = str(getattr(concept, "size", "") or "16 in")
    if form not in ROUND_CUSHION_FORMS:
        raise ComposeRefused("round_cushion_form", f"form {form!r} is not one of "
                                                   f"{sorted(ROUND_CUSHION_FORMS)}")
    d = ROUND_CUSHION_FORMS[form]
    colours, keys = _palette(concept, 2)
    return {"slug": concept.slug, "title": concept.title, "category": concept.category,
            "yarn_weight": concept.yarn_weight, "colours": colours,
            "extra_materials": [f"a {form} ({d:.1f} cm) round pillow form"],
            "parts": [
                {"name": "front", "shape": "flat_circle", "diameter_cm": d, "colour": keys[0],
                 "blocks": [{"colour": keys[1], "from": 0.0, "to": 0.25}]},
                {"name": "back", "shape": "flat_circle", "diameter_cm": d, "colour": keys[0]}],
            "joins": [{"kind": "rim", "a": "front", "b": "back", "insert_before_closing": True,
                       "note": f"Leave a third of the edge open, insert the {form} round form, "
                               f"then close the opening the same way"}],
            "designer_notes": (f"pillow concept composed as a round cushion cover for a {form} "
                               f"round form: two flat circles with a contrast centre, "
                               f"whipstitched together round the edge")}


def _sleeve_plan(concept) -> dict:
    size = str(getattr(concept, "size", "") or "tablet")
    if size not in SLEEVE_SIZES:
        raise ComposeRefused("sleeve_size", f"size {size!r} is not one of {sorted(SLEEVE_SIZES)}")
    across, up = SLEEVE_SIZES[size]
    colours, keys = _palette(concept, 2)
    panel = {"shape": "rectangle", "width_cm": across, "height_cm": up, "colour": keys[0],
             "blocks": [{"colour": keys[1], "from": 0.0, "to": 0.2}],
             "edging": {"colour": keys[1], "rows": 2, "style": "band"}}
    return {"slug": concept.slug, "title": concept.title, "category": concept.category,
            "yarn_weight": concept.yarn_weight, "colours": colours, "fibre": "cotton",
            "parts": [{"name": "front", **panel}, {"name": "back", **panel}],
            "joins": [{"kind": "seamed_panels", "a": "front", "b": "back", "edge_a": "left",
                       "edge_b": "left"},
                      {"kind": "seamed_panels", "a": "front", "b": "back", "edge_a": "right",
                       "edge_b": "right"},
                      {"kind": "seamed_panels", "a": "front", "b": "back", "edge_a": "bottom",
                       "edge_b": "bottom"}],
            "designer_notes": (f"case concept composed as a {size} sleeve: two {across:.0f} x "
                               f"{up:.0f} cm panels (design choice) with a contrast block and a "
                               f"band edging, seamed on three sides")}


TEMPLATES = {"toy": _toy_plan, "lovey": _lovey_plan, "tote": _tote_plan,
             "round_cushion": _round_cushion_plan, "sleeve": _sleeve_plan}
_FORM_ALIASES = {"amigurumi": "toy", "plush": "toy", "bag": "tote", "pillow": "round_cushion",
                 "cushion": "round_cushion", "case": "sleeve"}


def plan_for(concept) -> dict:
    """Concept (form, subject, size, features) -> plan, or ComposeRefused naming the primitive."""
    named = _text_refusal(getattr(concept, "title", ""),
                          *[str(f) for f in getattr(concept, "features", None) or ()])
    if named:
        raise named
    form = str(getattr(concept, "form", "") or "")
    form = _FORM_ALIASES.get(form, form)
    if form not in TEMPLATES:
        raise ComposeRefused(f"template:{form or 'unknown'}",
                             f"no composer template for the form {form!r} "
                             f"(templates: {sorted(TEMPLATES)})")
    if form in ("toy", "lovey"):
        subject = _subject(concept)
        if subject is None:
            raise ComposeRefused(f"subject:{getattr(concept, 'subject', '') or 'unknown'}",
                                 f"no subject template for {getattr(concept, 'subject', '')!r} "
                                 f"(subjects: {sorted(SUBJECTS)})")
        return _one_colour(TEMPLATES[form](concept, subject))
    return _one_colour(TEMPLATES[form](concept))


def _one_colour(plan: dict) -> dict:
    """A one-colour palette has no contrast: its blocks are dropped and nothing says contrast."""
    if len(plan["colours"]) > 1:
        return plan
    for p in plan["parts"]:
        p.pop("blocks", None)
        if p.get("note"):
            p["note"] = p["note"].replace("a contrast block and ", "")
    if plan.get("designer_notes"):
        plan["designer_notes"] = (plan["designer_notes"].replace("a contrast colour block, ", "")
                                  .replace(" with a contrast centre", "")
                                  .replace(" with a contrast block and", " with"))
    return plan


# Reading a research concept's title: the template its head noun names, the subject, the size.
_FORM_WORDS: tuple[tuple[str, str], ...] = (
    (r"\blove(?:y|ys)\b|\bsnuggle square\b", "lovey"),
    (r"\b(?:amigurumi|plush|plushie|stuffie|soft toy)\b", "toy"),
    (r"\b(?:tote|market bag|shopper)s?\b", "tote"),
    (r"\bround (?:cushion|pillow)(?: cover)?s?\b", "round_cushion"),
    (r"\b(?:tablet|laptop) sleeves?\b", "sleeve"),
)
# Accessory pieces no subject template carries: named, so a toy is never sold with a piece its
# plan does not make.
_ACCESSORY = (r"\b(?:scarf|scarves|bows?|flowers?|hearts?|crowns?|hoods?|backpacks?|dress(?:es)?|"
              r"overalls|clothes|outfit|hat|tutu|wings? and|with)\b")
_SIZE_WORDS = {"small": "small", "mini": "small", "medium": "medium", "large": "large",
               "tablet": "tablet", "laptop": "laptop", "14": "14 in", "16": "16 in"}


def concept_from_text(*, slug: str, title: str, category: str = "", colours: dict | None = None,
                      yarn_weight: str = "worsted", premise: str = "") -> SimpleNamespace:
    """A research concept's title read into the composer's (form, subject, size) -- or the
    named refusal. Deterministic: the same title always reads the same way."""
    from .fallback_constructions import fold_title

    named = _text_refusal(title, premise)
    if named:
        raise named
    folded = fold_title(title)
    form = next((f for rx, f in _FORM_WORDS if re.search(rx, folded)), None)
    if form is None:
        raise ComposeRefused(f"template:{category or 'unknown'}",
                             f"the title {title!r} names no composer template "
                             f"({sorted(TEMPLATES)})")
    acc = re.search(_ACCESSORY, folded)
    if acc and form in ("toy", "lovey"):
        raise ComposeRefused(f"accessory:{acc.group(0)}",
                             f"the title names {acc.group(0)!r}, a piece no subject template "
                             f"makes")
    words = re.findall(r"[a-z0-9]+", folded)
    subject = next((SUBJECT_SYNONYMS.get(w, w) for w in words
                    if SUBJECT_SYNONYMS.get(w, w) in SUBJECTS), None)
    if form in ("toy", "lovey") and subject is None:
        guess = next((w for w in reversed(words) if w not in ("amigurumi", "plush", "lovey",
                                                              "toy", "soft", "crochet")), "")
        raise ComposeRefused(f"subject:{guess or 'unknown'}",
                             f"no subject template for {guess!r} (subjects: {sorted(SUBJECTS)})")
    size = next((_SIZE_WORDS[w] for w in words if w in _SIZE_WORDS), None)
    return concept(slug=slug, title=title, category=category, form=form, subject=subject,
                   size=size, colours=dict(colours or {}), yarn_weight=yarn_weight)


def expressible(*, slug: str, title: str, category: str = "", colours: dict | None = None,
                yarn_weight: str = "worsted", premise: str = "") -> dict:
    """{"expressible": bool, "primitive": missing primitive or "", "why"}. Composes the plan
    (with placeholder colours when none are given), so "expressible" means it validates AND
    builds -- never that a template merely matched."""
    palette = dict(colours or {}) or {"MC": "#D8C9B0", "CC": "#6B4E3D"}
    try:
        c = concept_from_text(slug=slug or "composer-probe", title=title, category=category,
                              colours=palette, yarn_weight=yarn_weight, premise=premise)
        compose(plan_for(c))
    except ComposeRefused as exc:
        return {"expressible": False, "primitive": exc.primitive, "why": exc.why}
    return {"expressible": True, "primitive": "", "why": "", "form": c.form,
            "subject": c.subject}


def adjudicate(proposals: list[dict]) -> dict:
    """Any proposer (a model, a template, a person) may propose plan structures. The validator
    alone decides: the first proposal that validates AND composes wins; votes do not count.
    Returns {"plan", "cir", "refused": [(index, reason)]}."""
    refused: list[tuple[int, str]] = []
    for i, plan in enumerate(proposals):
        try:
            cir = compose(plan)
        except ComposeRefused as exc:
            refused.append((i, str(exc)))
            continue
        return {"plan": plan, "cir": cir, "refused": refused}
    return {"plan": None, "cir": None, "refused": refused}


# ---- routing: family engine, composer, or a change request -------------------------------------

def route(concept, *, db=None) -> dict:
    """The production decision for a concept the family router does not admit.

    `{"route": "family_engine"}` when `construction_families.route` admits it; `"composer"` with
    the composed CIR when the composer can express it; otherwise `"ecr"` with the missing
    primitive, and (given a db) the engineering change request filed for it."""
    from . import construction_families as CF

    fam = CF._route_engines(category=concept.category, title=concept.title,
                            form=getattr(concept, "declared_form", None) or concept.category,
                            construction=getattr(concept, "construction", "in_the_round"),
                            slug=concept.slug)
    if fam.get("admitted"):
        return {"route": "family_engine", "family": fam["family"]}
    try:
        plan = plan_for(concept)
        cir = compose(plan)
    except ComposeRefused as exc:
        out = {"route": "ecr", "primitive": exc.primitive, "why": exc.why,
               "family_hold": fam.get("reason", "")}
        if db is not None:
            out["ecr"] = file_missing_primitive(db, concept, exc)
        return out
    return {"route": "composer", "plan": plan, "cir": cir, "family_hold": fam.get("reason", "")}


def file_missing_primitive(db, concept, exc: ComposeRefused) -> dict:
    """File (or merge into) the change request for a missing composer primitive."""
    from ..improve import ecr

    return ecr.file(
        db, defect_class="missing_capability", department="creative",
        module=f"{COMPOSER}:{exc.primitive}",
        title=f"Composer primitive missing: {exc.primitive}",
        problem=(f"Concept {concept.slug!r} ({concept.title!r}) has no family engine and the "
                 f"composer cannot express it: {exc.why}"),
        evidence={"examples": [concept.slug], "primitive": exc.primitive, "why": exc.why},
        proposed_change=(f"Add the {exc.primitive!r} primitive to creative.composer.PRIMITIVES "
                         f"with a deterministic builder and a validating test"),
        acceptance_criteria=[
            f"creative.composer validates a plan using {exc.primitive!r}",
            "the composed CIR compiles, builds its twin, reverse-compiles US and UK and "
            "certifies (or is withheld only for physical evidence)",
            f"{concept.slug!r} routes to the composer instead of this request"],
        priority="P2", filed_by=COMPOSER)


def concept(**kw) -> SimpleNamespace:
    """A concept record for the composer route (slug, title, category, form, subject, size,
    features, colours, yarn_weight)."""
    kw.setdefault("yarn_weight", "worsted")
    kw.setdefault("features", ())
    return SimpleNamespace(**kw)


@dataclass(frozen=True)
class Composed:
    plan: dict
    cir: CIR
