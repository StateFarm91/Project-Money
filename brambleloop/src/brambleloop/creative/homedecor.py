"""ENG-HOMEDECOR: vessels in the round the factory can certify, and the gates that hold them true.

The gap this closes (found 2026-11-20, before anything was built). The vessel engine makes ONE
object: a hexagon base of stacked increases and straight striped walls. The router admitted
every basket title that did not name a held feature, and certification checked only the shape
words it already knew, so five different products certified as that same hexagon basket:

* "Round ... Basket"   -- a circle word on a six-cornered base (`check_shape_claims` reads
                          "round" only before a flat noun such as "coaster");
* "Oval ... Basket"    -- an outline no engine works (the surface model is a circle);
* "... Yarn Bowl"      -- a 16 cm straight-walled basket sold as a bowl;
* "... Plant Pot Cozy" -- a basket at no pot's size, sold as a fitted cover;
* "Moss Stitch Basket" -- plain single crochet sold as a texture stitch it does not contain.

Each one granted a certificate (reproduced through the real handlers, `test_eng_homedecor`).

This module does two things, both deterministic.

1. **Builds** four vessel variants, each derived from `fallback_constructions.vessel` (the
   verified engine) so the walls, palette and gauge are the ones that already certify:

   - ``round_vessel``   -- the same basket on a ROUND base: the increases are staggered half a
                           wedge on alternate rounds, so no corner column forms
                           (`cir.geometry.corners` reads 0 out of the stitch positions).
   - ``bowl``           -- a round base, then a wall that flares: one +6 round in every
                           `BOWL_FLARE_EVERY`, so the rim is wider than the base and the wall
                           leans out at a computed angle.
   - ``lidded_vessel``  -- the hexagon basket plus a LID: a disc grown past the basket's rim by
                           whole wedges until its lip clears the wall, then a straight lip.
   - ``handled_vessel`` -- the basket with two CUT-OUT handles: one wall round works
                           "ch N, sk N" twice, opposite each other, and the next round works
                           into the chains, so the count is restored.

2. **Gates** what a vessel's name may claim (`findings`, run by `gates.certificate.certify`
   on every CIR, whatever path drafted it):

   - VESSEL_BASE_NOT_FLAT          a vessel's base rounds must grow at their own row height;
   - VESSEL_OUTLINE_UNSUPPORTED    a circle word needs 0 corners; "oval" needs an oval model;
   - VESSEL_BOWL_NOT_FLARED        "bowl" needs a rim measurably wider than its base;
   - VESSEL_LID_DOES_NOT_FIT       "lid" needs a lid piece whose lip clears the rim, not loose;
   - VESSEL_HANDLE_UNSUPPORTED     "handle" needs two opposite openings a hand fits, below rim;
   - VESSEL_OBJECT_UNSUPPORTED     "plant pot cozy" / "planter" needs a sourced pot size;
   - VESSEL_TEXTURE_UNSUPPORTED    a stitch-texture word needs that texture's stitches.

Every figure here that is a design choice says so; none is a measurement. Fit, lean and
opening sizes are computed from the stated gauge and are estimates until a sample is worked.
"""
from __future__ import annotations

import dataclasses
import math
import re

from ..cir.model import CIR, Component, Op, Repeat, Row

ROUND_VESSEL = "round_vessel"
BOWL = "bowl"
LIDDED = "lidded_vessel"
HANDLED = "handled_vessel"
VARIANTS = (ROUND_VESSEL, BOWL, LIDDED, HANDLED)

PRIMITIVES = {
    ROUND_VESSEL: ("creative.homedecor.round_vessel", "creative.homedecor.round_disc_rounds"),
    BOWL: ("creative.homedecor.bowl", "creative.homedecor.round_disc_rounds"),
    LIDDED: ("creative.homedecor.lidded_vessel", "creative.homedecor.lid_count"),
    HANDLED: ("creative.homedecor.handled_vessel",),
}

# ---- vocabulary: what a vessel title can claim ------------------------------------------------

# "year round", "all round", "in the round" and "a round" (one round of stitches) are not
# outlines.
_ROUND_RE = (r"(?<!year )(?<!year-)(?<!all )(?<!all-)(?<!the )(?<!a )"
             # "carried round the wall" / "round its rim" is the preposition, not an outline.
             r"\b(?:round\b(?!\s+(?:the|its|it|each|every)\b)|circular\b|circle\b)")
# "granny square" and "afghan square" name a motif (`construction_families` holds it by name).
_OVAL_RE = (r"\b(?:oval|oblong|rectangular)\b|(?<!granny )(?<!afghan )\bsquare\b"
            r"(?! motifs?)")
_BOWL_RE = r"\bbowls?\b"
_LID_RE = r"\b(?:lids?|lidded)\b"
_HANDLE_RE = r"\b(?:handles?|handled)\b"
_PLANTER_RE = (r"\bplanters?\b|\bplant[- ]?pots?\b|\bpot (?:cozy|cosy|cozies|cosies|cover|"
               r"covers|holder|sleeve)s?\b|\bplant (?:cozy|cosy|basket|cover)s?\b")
# Stitch textures the vessel engines do not work. Bobble, ribbing and waffle are also read by
# `asset_truth._TECHNIQUE_CLAIMS` (which wants their stitches); these are the ones nothing read.
TEXTURE_WORDS = (r"\bmoss(?: stitch)?\b|\bseed stitch\b|\blinen stitch\b|\bgranite stitch\b|"
                 r"\bherringbone\b|\bv[- ]stitch\b|\bgriddle stitch\b|\bhoneycomb\b|"
                 r"\blemon peel\b|\bsuzette\b|\bwattle stitch\b|\bspike stitch\b|"
                 r"\bthermal stitch\b|\bbasket[- ]?weave\b|\bwaffle\b|\bribbed\b|\bribbing\b|"
                 r"\bbobbles?\b|\bpopcorn\b|\bpuff stitch\b|\bcrocodile\b|\bshell stitch\b|"
                 r"\bwoven stitch\b|\bcluster stitch\b|\btextured?\b")
# Words a variant does not combine with in this slice: each proven variant is one feature.
_FEATURE_RES = {ROUND_VESSEL: _ROUND_RE, BOWL: _BOWL_RE, LIDDED: _LID_RE, HANDLED: _HANDLE_RE}


def _fold(text: str | None) -> str:
    from .fallback_constructions import fold_title

    return fold_title(text)


def claims(text: str | None) -> dict[str, str]:
    """{claim: matched word} for every vessel claim in a title (empty when it names none)."""
    folded = _fold(text)
    out: dict[str, str] = {}
    for key, rx in (("round", _ROUND_RE), ("oval", _OVAL_RE), ("bowl", _BOWL_RE),
                    ("lid", _LID_RE), ("handles", _HANDLE_RE), ("planter", _PLANTER_RE),
                    ("texture", TEXTURE_WORDS)):
        m = re.search(rx, folded)
        if m:
            out[key] = m.group(0)
    return out


def vessel_route(title: str | None) -> dict | None:
    """The variant a basket-category title drafts, a refusal by name, or None (plain vessel).

    Called by `fallback_constructions._plan` for a vessel category, after the tapestry route:
    the one routing rule, so intake (`construction_families.route`) and `cir.draft` agree."""
    from .fallback_constructions import REFUSED

    c = claims(title)
    if not c:
        return None
    if "texture" in c:
        return {"family": REFUSED, "needs": f"a {c['texture']} stitch definition in the vessel wall",
                "why": (f"the title names {c['texture']!r}, a stitch texture the vessel engines "
                        f"do not work; the plain single-crochet wall would sell a texture the "
                        f"pattern does not make")}
    if "oval" in c:
        return {"family": REFUSED, "needs": "a base worked around a foundation chain, and a "
                                            "surface model for a non-circular outline",
                "why": (f"the title names {c['oval']!r}; cir.geometry models a vessel as a "
                        f"surface of revolution (a circle), so no {c['oval']} outline can be "
                        f"drafted or measured")}
    if "planter" in c:
        return {"family": REFUSED, "needs": "a sourced pot size (top and base diameter, "
                                            "height) for the cozy to be fitted to",
                "why": (f"the title names {c['planter']!r}, a cover fitted to a pot; no pot "
                        f"dimension is on file, so the fit cannot be computed or claimed")}
    named = [v for v, rx in _FEATURE_RES.items() if re.search(rx, _fold(title))]
    if len(named) > 1:
        return {"family": REFUSED, "needs": f"a proven combination of {named}",
                "why": (f"the title combines {named}; each vessel variant is proven on its own "
                        f"and no combination has an end-to-end proof yet")}
    family = named[0]
    if family == BOWL and not re.search(r"\bbowl$", _fold(title)):
        return {"family": REFUSED, "needs": "a title whose object is the bowl",
                "why": "'bowl' is not the title's head noun, so the object it names is unclear"}
    return {"family": family, "needs": "", "why": {
        ROUND_VESSEL: "a basket on a round base of staggered increases, worked in the round",
        BOWL: "a bowl: a round base and a wall that flares by whole wedges",
        LIDDED: "a basket with a lid grown past its rim by whole wedges, worked in the round",
        HANDLED: "a basket with two cut-out handles worked into a wall round",
    }[family]}


# ---- builders --------------------------------------------------------------------------------


def _ops(*pairs) -> list:
    """Ops from (stitch, count) pairs, dropping empty runs (an Op cannot count 0)."""
    return [Op(code) if code == "inc" else Op(code, n) for code, n in pairs
            if code == "inc" or n > 0]


def round_disc_rounds(base_count: int, color: str, wedges: int = 6, start: int = 1) -> list[Row]:
    """Increase rounds from a magic ring to `base_count` with the increases STAGGERED.

    Same counts as `products.vessels._disc_rounds`, different positions: on alternate rounds
    the increase moves half a wedge along, so it never lands in the stitch the last increase
    made and no corner column forms. `cir.geometry.corners` reads 0 for this disc."""
    if base_count % wedges:
        raise ValueError(f"{base_count} stitches is not a multiple of {wedges} wedges")
    rows = [Row(index=start, ops=[Op("sc", wedges)], declared_count=wedges, color=color)]
    index, count = start, wedges
    made: set[int] = set()          # positions, in each wedge, that the last increase made
    end = False
    while count < base_count:
        index += 1
        per = count // wedges          # stitches per wedge going in
        if per == 1:
            lead = 0
        else:
            # Alternate the increase between the middle and the end of the wedge, taking
            # whichever does not land on a stitch the previous round's increase made.
            options = [per - 1, per // 2] if not end else [per // 2, per - 1]
            lead = next((o for o in options if o not in made), options[0])
            end = lead == per - 1
        body = _ops(("sc", lead), ("inc", 1), ("sc", per - 1 - lead))
        made = {lead, lead + 1}
        count += wedges
        rows.append(Row(index=index, ops=[Repeat(body, times=wedges)], declared_count=count,
                        color=color))
    return rows


def _base_rounds(comp: Component) -> int:
    """How many leading rounds of the component grow (the base)."""
    n = 1
    for prev, row in zip(comp.rows, comp.rows[1:]):
        if (row.declared_count or 0) > (prev.declared_count or 0):
            n += 1
        else:
            break
    return n


def _renumber(rows: list[Row], start: int = 1) -> list[Row]:
    return [dataclasses.replace(r, index=start + i) for i, r in enumerate(rows)]


def _base_note(round_: bool) -> str:
    if round_:
        return ("Worked in one piece from the centre of the base. On alternate rounds the "
                "increase moves half a wedge along, so the increases never stack and the base "
                "stays round.")
    return ("Worked in one piece from the centre of the base. Work each increase into the "
            "second stitch of the previous round's increase, so the increases stack into six "
            "corners and the base is a hexagon.")


def _sized_spec(title: str):
    from ..products.vessels import BASKET_SIZES

    folded = _fold(title)
    key = next((k for w, k in (("small", "small"), ("mini", "small"), ("bread", "small"),
                               ("medium", "medium"), ("large", "large"), ("market", "large"))
                if re.search(rf"\b{w}\b", folded)), "medium")
    return next(s for s in BASKET_SIZES if s.key == key)


def round_vessel(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """The verified vessel with its base re-worked round: identical counts, staggered increases."""
    from .fallback_constructions import vessel

    cir = vessel(concept, version=version, provenance=provenance)
    body = cir.components[0]
    nbase = _base_rounds(body)
    base = round_disc_rounds(body.rows[nbase - 1].declared_count, body.rows[0].color)
    rows = base + body.rows[nbase:]
    across = body.rows[nbase - 1].declared_count / cir.gauge.stitches_per_10cm * 10.0 / math.pi
    tall = (len(rows) - nbase) * 10.0 / cir.gauge.rows_per_10cm
    return dataclasses.replace(
        cir, components=[dataclasses.replace(body, rows=rows, note=_base_note(True))],
        designer_notes=cir.designer_notes.replace("hexagon base", "round base"),
        finished_size_note=(
            f"A round basket about {across:.1f} cm across, walls about {tall:.0f} cm tall, at "
            f"the stated gauge: the increases are staggered so the base is a circle. Computed, "
            f"not yet measured on a worked sample."))


# A bowl (house design sizes; no published standard bowl size exists for crochet catch-alls).
BOWL_SIZES = {"small": (12.0, 6.0), "medium": (16.0, 8.0), "large": (20.0, 10.0)}
BOWL_FLARE_EVERY = 3          # one +6 round in every three wall rounds
BOWL_MIN_LEAN_DEG = 8.0       # below this a "bowl" is a straight-walled basket
BOWL_MAX_LEAN_DEG = 50.0      # beyond this it is a plate, not a bowl


def bowl(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A round base, then a wall that flares by one wedge round in every BOWL_FLARE_EVERY."""
    from ..products.vessels import base_stitches_for
    from .fallback_constructions import vessel
    from .prototype import gauge_for

    folded = _fold(concept.title)
    key = next((k for k in BOWL_SIZES if re.search(rf"\b{k}\b", folded)), "medium")
    base_cm, tall_cm = BOWL_SIZES[key]
    gauge = gauge_for(concept.yarn_weight)
    shell = vessel(concept, version=version, provenance=provenance)   # palette, materials
    palette = list(concept.colors)
    main, accent = palette[0], palette[1 % len(palette)]
    base_count = base_stitches_for(base_cm, gauge)
    rows = round_disc_rounds(base_count, main)
    row_cm = 10.0 / gauge.rows_per_10cm
    # A flare round grows at its own row height and so adds almost no rise: only the plain
    # rounds lift the wall, so there are enough of them to reach the bowl's height.
    wall_rounds = max(6, int(round(tall_cm / row_cm * BOWL_FLARE_EVERY
                                   / (BOWL_FLARE_EVERY - 1))))
    count, index = base_count, rows[-1].index
    for w in range(1, wall_rounds + 1):
        index += 1
        colour = accent if (w // 2) % 3 == 2 else main
        if w % BOWL_FLARE_EVERY == 0:
            per = count // 6
            lead = per // 2
            rows.append(Row(index=index, ops=[Repeat(_ops(("sc", lead), ("inc", 1),
                                                          ("sc", per - 1 - lead)), times=6)],
                            declared_count=count + 6, color=colour,
                            note="the flare: one increase in each wedge, staggered"))
            count += 6
        else:
            rows.append(Row(index=index, ops=[Op("sc", count)], declared_count=count,
                            color=colour))
    rim = count / gauge.stitches_per_10cm * 10.0 / math.pi
    return dataclasses.replace(
        shell, gauge=gauge,
        components=[Component(
            name="bowl", construction="joined_rounds", rows=rows, foundation=0,
            foundation_kind="magic_ring",
            note=(_base_note(True) + f" From round {len(rows) - wall_rounds + 1} the wall "
                  f"flares: every {BOWL_FLARE_EVERY}rd wall round adds one stitch to each "
                  f"wedge."))],
        designer_notes=(f"{concept.category} concept drafted as a bowl: a round base of "
                        f"{base_count} sts and {wall_rounds} plain wall rounds that "
                        f"flare to {count} sts; the concept's stitch repeat is not used"),
        finished_size_note=(
            f"A round bowl about {rim:.1f} cm across the rim, on a flat base, at the stated "
            f"gauge. Computed, not yet measured on a worked sample."))


# A lid: a disc grown past the basket's base count by whole wedges until its lip clears the
# wall, then a straight lip worked down over the rim. The fabric's thickness is a MODELLING
# ASSUMPTION (half a row height; uncalibrated), stated wherever the fit is.
LID_LIP_CM = 2.0
FABRIC_THICKNESS_ROWS = 0.5
LID_MIN_CLEARANCE_CM = 0.3    # around the rim: below this the lip binds on the wall
LID_MAX_CLEARANCE_CM = 6.0    # around the rim: beyond this the lid slides about loose


def fabric_thickness_cm(gauge) -> float:
    return FABRIC_THICKNESS_ROWS * 10.0 / gauge.rows_per_10cm


def lid_clearance_cm(rim_count: int, lid_count: int, gauge) -> float:
    """How much longer (cm, measured around) the lid lip's inside is than the rim's outside."""
    per = 10.0 / gauge.stitches_per_10cm
    t = fabric_thickness_cm(gauge)
    rim_outside = rim_count * per + 2 * math.pi * t
    lip_inside = lid_count * per - 2 * math.pi * t
    return lip_inside - rim_outside


def lid_count(rim_count: int, gauge, wedges: int = 6) -> int:
    """The smallest whole-wedge lid count whose lip clears the rim by LID_MIN_CLEARANCE_CM."""
    n = rim_count
    while lid_clearance_cm(rim_count, n, gauge) < LID_MIN_CLEARANCE_CM:
        n += wedges
    return n


def lidded_vessel(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """The verified vessel, plus a lid component worked to fit over its rim."""
    from ..products.vessels import _disc_rounds
    from .fallback_constructions import vessel

    cir = vessel(concept, version=version, provenance=provenance)
    body = cir.components[0]
    rim = body.rows[-1].declared_count
    n = lid_count(rim, cir.gauge)
    colour = body.rows[0].color
    rows = _disc_rounds(n, colour)
    lip = max(2, int(round(LID_LIP_CM * cir.gauge.rows_per_10cm / 10.0)))
    for _ in range(lip):
        rows.append(Row(index=rows[-1].index + 1, ops=[Op("sc", n)], declared_count=n,
                        color=colour))
    clearance = lid_clearance_cm(rim, n, cir.gauge)
    lid = Component(
        name="lid", construction="joined_rounds", rows=rows, foundation=0,
        foundation_kind="magic_ring",
        note=(f"Worked like the base, to {n} stitches ({n - rim} more than the basket's rim, "
              f"so the lip goes over the wall), then {lip} straight rounds for the lip. The "
              f"lid sits over the rim; it is not sewn on."))
    return dataclasses.replace(
        cir, components=[body, lid],
        designer_notes=(f"{cir.designer_notes}; with a lid of {n} sts and a {lip}-round lip. "
                        f"The lip is computed to clear the {rim}-st rim by about "
                        f"{clearance:.1f} cm measured around, taking the fabric as "
                        f"{fabric_thickness_cm(cir.gauge):.2f} cm thick (a modelling "
                        f"assumption, not a measurement)"),
        finished_size_note=(
            f"{cir.finished_size_note} The lid is about "
            f"{n / cir.gauge.stitches_per_10cm * 10.0 / math.pi:.1f} cm across."))


# Cut-out handles. HANDLE_MIN_CM is a DESIGN CHOICE, not a sourced standard: an opening a
# little wider than an adult's four fingers held together, so a hand goes through it.
HANDLE_MIN_CM = 8.0
HANDLE_RIM_ROUNDS = 2         # whole rounds left above the opening, so the rim is a grip
HANDLE_MAX_SHARE = 0.4        # the two openings together, of the round's circumference


def handle_stitches(gauge) -> int:
    return math.ceil(HANDLE_MIN_CM * gauge.stitches_per_10cm / 10.0)


def handled_vessel(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """The verified vessel with two opposite cut-out handles below its rim."""
    from .fallback_constructions import vessel

    cir = vessel(concept, version=version, provenance=provenance)
    body = cir.components[0]
    n = body.rows[-1].declared_count
    h = handle_stitches(cir.gauge)
    if 2 * h > HANDLE_MAX_SHARE * n:
        raise ValueError(f"{concept.slug}: two {h}-st openings are more than "
                         f"{HANDLE_MAX_SHARE:.0%} of a {n}-st round")
    at = len(body.rows) - HANDLE_RIM_ROUNDS - 1          # list position of the opening round
    half = n // 2
    lead = (half - h) // 2
    row = body.rows[at]
    opening = _ops(("sc", lead), ("ch", h), ("sk", h), ("sc", half - h),
                   ("ch", h), ("sk", h), ("sc", n - half - h - lead))
    opening = [dataclasses.replace(o, spans=h) if o.stitch == "ch" else o for o in opening]
    rows = list(body.rows)
    rows[at] = dataclasses.replace(
        row, ops=opening,
        note=(f"the handle openings: each ch {h} bridges the {h} stitches passed over, and the "
              f"two openings sit opposite each other"))
    nxt = rows[at + 1]
    rows[at + 1] = dataclasses.replace(
        nxt, ops=[Op("sc", n)],
        note=(f"work one stitch into each chain of the openings, so the round is {n} "
              f"sts again"))
    width = h * 10.0 / cir.gauge.stitches_per_10cm
    return dataclasses.replace(
        cir, components=[dataclasses.replace(body, rows=rows)],
        designer_notes=(f"{cir.designer_notes}; with two opposite cut-out handles of {h} "
                        f"chains (about {width:.1f} cm each at the stated gauge) in round "
                        f"{row.index}, {HANDLE_RIM_ROUNDS} rounds below the rim"))


BUILDERS = {ROUND_VESSEL: round_vessel, BOWL: bowl, LIDDED: lidded_vessel,
            HANDLED: handled_vessel}


def build(family: str, concept, *, provenance=None) -> CIR:
    return BUILDERS[family](concept, provenance=provenance)


# ---- gates -----------------------------------------------------------------------------------

_VESSEL_NOUN = r"\b(?:baskets?|bowls?|bins?|buckets?|caddy|caddies|hampers?|vessels?|trays?)\b"
FLAT_LO, FLAT_HI = 0.85, 1.15  # = 2 - geometry.SMOOTH_TOLERANCE, geometry.SMOOTH_TOLERANCE


def _rings(twins: dict, name: str):
    t = twins.get(name)
    geo = getattr(t, "geometry", None) if t is not None else None
    return list(getattr(geo, "rings", None) or [])


def _openings(comp: Component) -> list[tuple[int, int, int]]:
    """(round index, first skipped stitch, width) for every 'ch N, sk N' bridge (N >= 3)."""
    from ..cir import stitches

    out = []
    for row in comp.rows:
        pos = 0
        ops = [o for o in row.ops if isinstance(o, Op)]
        if len(ops) != len(row.ops):
            continue
        for a, b in zip(ops, ops[1:] + [None]):
            if a.stitch == "ch" and b is not None and b.stitch == "sk" and a.count == b.count \
                    and a.count >= 3:
                out.append((row.index, pos, a.count))
            pos += stitches.get(a.stitch).consumes * a.count
    return out


def findings(cir: CIR, twins: dict, where: str = "cir.title", text: str | None = None) -> list:
    """Every vessel claim in `text` (default the CIR title) checked against the rows and twin."""
    from ..cir.compiler import ERROR, Finding

    title = cir.title if text is None else text
    folded = _fold(title)
    if not re.search(_VESSEL_NOUN, folded):
        return []
    rounds = [c for c in cir.components if c.construction != "flat_rows"]
    if not rounds:
        return []           # a flat vessel name is check_shape_claims' finding
    body = rounds[0]
    out: list = []

    def err(code, why):
        out.append(Finding(ERROR, code, why, where))

    # 1. The base is flat: every base round grows at its own row height.
    rings = _rings(twins, body.name)
    if not rings:
        # No twin, or a twin with no geometry (no gauge): no vessel claim can be measured.
        # UNKNOWN is not a pass, so the claim is an error rather than silence.
        err("VESSEL_GEOMETRY_UNKNOWN", (
            "vessel claim cannot be checked: the twin has no readable geometry (UNKNOWN is "
            "not a pass)"))
        return out
    nbase = _base_rounds(body)
    early = claims(title)
    if body.foundation_kind != "magic_ring" and any(k in early for k in ("round", "bowl", "lid")):
        err("VESSEL_GEOMETRY_UNKNOWN", (
            f"the name claims {', '.join(repr(early[k]) for k in ('round', 'bowl', 'lid') if k in early)}"
            f", but the base is not worked from a magic ring ({body.foundation_kind!r}), so "
            f"the flat-base check cannot run (UNKNOWN is not a pass)"))
    if body.foundation_kind == "magic_ring" and len(rings) >= nbase >= 2:
        bad = [(r.index, r.growth_ratio) for r in rings[1:nbase]
               if not FLAT_LO <= r.growth_ratio <= FLAT_HI]
        if bad:
            i, g = bad[0]
            err("VESSEL_BASE_NOT_FLAT", (
                f"round {i} of the base grows at {g:.2f}x its own row height (a flat base is "
                f"{FLAT_LO}-{FLAT_HI}x): below that the base cups, above it the base ruffles, "
                f"and the vessel will not stand"))

    c = claims(title)
    twin = twins.get(body.name)
    sides = getattr(twin, "sides", None)
    if "round" in c and sides != 0:
        err("VESSEL_OUTLINE_UNSUPPORTED", (
            f"the name claims {c['round']!r}, but the base's increases make "
            f"{'no readable' if sides is None else sides} corner columns, not a circle"))
    if "oval" in c:
        err("VESSEL_OUTLINE_UNSUPPORTED", (
            f"the name claims {c['oval']!r}; the vessel is worked from a magic ring as a "
            f"surface of revolution, which no {c['oval']} outline is"))
    if "planter" in c:
        err("VESSEL_OBJECT_UNSUPPORTED", (
            f"the name claims {c['planter']!r}, a cover fitted to a pot, and no pot size is "
            f"on file to fit it to"))
    if "texture" in c:
        from ..gates.asset_truth import _TECHNIQUE_CLAIMS

        backed = [rx for rx, _st, _w in _TECHNIQUE_CLAIMS if re.search(rx, c["texture"])]
        if not backed:   # those words are check_technique_claims' finding already
            err("VESSEL_TEXTURE_UNSUPPORTED", (
                f"the name claims {c['texture']!r}, a stitch texture this pattern's rounds do "
                f"not work"))
    if "bowl" in c and len(rings) > nbase:
        base_r = rings[nbase - 1].radius_cm
        rim_r = rings[-1].radius_cm
        rise = sum(r.rise_cm for r in rings[nbase:])
        lean = math.degrees(math.atan2(rim_r - base_r, max(rise, 1e-9)))
        if not BOWL_MIN_LEAN_DEG <= lean <= BOWL_MAX_LEAN_DEG:
            err("VESSEL_BOWL_NOT_FLARED", (
                f"the name claims a bowl, but the wall leans {lean:.0f} degrees out (a bowl "
                f"is {BOWL_MIN_LEAN_DEG:g}-{BOWL_MAX_LEAN_DEG:g}): the rim is "
                f"{2 * rim_r:.1f} cm across over a {2 * base_r:.1f} cm base"))
    if "lid" in c:
        lids = [comp for comp in rounds if comp.name == "lid"]
        if not lids:
            err("VESSEL_LID_DOES_NOT_FIT", "the name claims a lid, and no piece is a lid")
        else:
            rim = body.rows[-1].declared_count or 0
            n = lids[0].rows[-1].declared_count or 0
            gap = lid_clearance_cm(rim, n, cir.gauge)
            if not LID_MIN_CLEARANCE_CM <= gap <= LID_MAX_CLEARANCE_CM:
                err("VESSEL_LID_DOES_NOT_FIT", (
                    f"the lid's {n}-st lip clears the {rim}-st rim by {gap:.1f} cm around "
                    f"(it must be {LID_MIN_CLEARANCE_CM:g}-{LID_MAX_CLEARANCE_CM:g} cm): "
                    f"{'it binds on the wall' if gap < LID_MIN_CLEARANCE_CM else 'it is loose'}"))
            lid_rings = _rings(twins, "lid")
            lb = _base_rounds(lids[0])
            if len(lid_rings) <= lb:
                err("VESSEL_LID_DOES_NOT_FIT", "the lid has no lip to hold it over the rim")
    if "handles" in c and not cir.assembly:
        ops = _openings(body)
        n = body.rows[-1].declared_count or 0
        last = body.rows[-1].index
        need = handle_stitches(cir.gauge)
        problem = None
        if len(ops) != 2:
            problem = f"it has {len(ops)} cut-out openings, not two"
        else:
            (r1, p1, w1), (r2, p2, w2) = ops
            if r1 != r2 or abs((p2 - p1) - n / 2) > 1:
                problem = "the two openings are not opposite each other in one round"
            elif min(w1, w2) < need:
                problem = (f"an opening is {min(w1, w2)} sts, under the {need} sts "
                           f"({HANDLE_MIN_CM:g} cm) a hand goes through")
            elif last - r1 < HANDLE_RIM_ROUNDS:
                problem = (f"the openings are {last - r1} round(s) below the rim, under the "
                           f"{HANDLE_RIM_ROUNDS} a grip needs")
            elif w1 + w2 > HANDLE_MAX_SHARE * n:
                problem = "the openings take too much of the round for the wall to stand"
        if problem:
            err("VESSEL_HANDLE_UNSUPPORTED", f"the name claims handles, but {problem}")
    return out
