"""The colourwork family: original charted designs generated from a motif library (ENG-COLOURWORK).

Research shows durable demand for tapestry, mosaic and other charted colourwork on blankets,
cushions, placemats, bags and baskets. This module is the engine that makes them, and it is
built on the Execution Directive's first rule: a pattern is a software release, never a
picture a model is asked to explain. Every chart here is

* **generated deterministically** from the Brambleloop motif library (`MOTIFS`, parametric
  geometric tiles written here: diamonds, chevrons, steps, lattices, checks, waves) and the
  concept itself (its slug and title pick the motif, the tile size, the band layout, the
  half-drop and the colour inversion -- the same concept always draws the same chart, and a
  different concept draws a different one);
* **declared on the CIR** (`cir.model.Chart`) beside the rows that work it, so the compiler
  proves cell by cell that the instructions work the chart (`cir.colourwork`), the twin's
  fabric is the chart (`cir.colourwork.twin_findings`), and the PDF prints the true chart;
* **original**: the generator reads only this module. It never reads the benchmark library
  (B-117: `teardown.library.retrieve` refuses every generation role), takes no competitor
  chart, photograph or instruction as input, and its output is compared against every chart
  fingerprint captured at teardown (`chart_fingerprint`, `gates.originality`'s chart
  dimension) before sale.

Techniques. Slice 1 builds **tapestry** crochet: single crochet with the colour not in use
laid along the top of the row below and worked over, so every stitch is one colour and the
carried strand is enclosed. Flat rows (blanket, placemat, cushion front) and joined rounds
(basket wall). Overlay mosaic, inset mosaic and corner-to-corner need primitives the CIR does
not have yet; a title that claims them is refused by name (`route`), never drafted as
tapestry, and `creative.construction_families` holds it with the reason.
"""
from __future__ import annotations

import hashlib
import math
import re

from ..cir.colourwork import MAX_FLOAT
from ..cir.model import CIR, Chart, Component, Material, Op, Repeat, Row, Seam

TAPESTRY = "tapestry"
MAIN, CONTRAST = "0", "1"
WIDTHS = (6, 12)               # tile widths: both divide a hexagon basket's base count
SEPARATOR = ("111000", "011100")   # a two-row stepped dash between motif blocks
BORDER_ROWS = 3                # plain main-colour rows below and above a flat chart
BASKET_PLAIN_BELOW = 2
BASKET_PLAIN_RIM = 2
MIN_MINORITY_SHARE = 0.10      # launch0.COLOURWORK_MIN_MINORITY_SHARE: each charted row
MIN_CONTRAST_RUN = 2           # launch0.COLOURWORK_MIN_RUN


# ---- the motif library --------------------------------------------------------------------
#
# Each motif is a function of a small parameter set returning a tile: rows of "0" (main) and
# "1" (contrast), bottom row first. Geometry, not pictures: none is traced from, derived from
# or measured against another designer's chart.

def _diamond(w: int, t: int) -> tuple[str, ...]:
    c = (w - 1) / 2.0
    r = w / 2.0
    return tuple("".join("1" if r - t < abs(x - c) + abs(y - c) <= r else "0"
                         for x in range(w)) for y in range(w))


def _chevron(w: int, t: int) -> tuple[str, ...]:
    h = w // 2
    rows = []
    for y in range(h):
        row = ""
        for x in range(w):
            tri = abs((x // 1) - (w - 1) / 2.0)
            row += "1" if (y - int(tri // 1)) % h < t else "0"
        rows.append(row)
    return tuple(rows)


def _step(w: int, s: int) -> tuple[str, ...]:
    return tuple("".join("1" if ((x // s) - (y // s)) % 3 == 0 else "0" for x in range(w))
                 for y in range(w))


def _lattice(w: int, t: int) -> tuple[str, ...]:
    return tuple("".join("1" if (x + y) % w < t or (x - y) % w < t else "0" for x in range(w))
                 for y in range(w))


def _check(w: int, s: int) -> tuple[str, ...]:
    return tuple("".join("1" if (x // s + y // s) % 2 == 0 else "0" for x in range(w))
                 for y in range(2 * s))


def _wave(w: int, t: int) -> tuple[str, ...]:
    h = w // 2
    lift = [int(round((h / 3.0) * math.sin(2 * math.pi * (x // 2 * 2) / w))) for x in range(w)]
    return tuple("".join("1" if (y - lift[x]) % h < t else "0" for x in range(w))
                 for y in range(h))


MOTIFS: dict[str, tuple] = {
    # key: (generator, parameter options, the words a title may use for it)
    "diamond": (_diamond, ((6, 2), (12, 2), (12, 3)), ("diamond", "diamonds")),
    "chevron": (_chevron, ((12, 2), (12, 3)), ("chevron", "chevrons", "zigzag",
                                                       "zig-zag")),
    "step": (_step, ((6, 2), (12, 4)), ("step", "steps", "stepped", "terrace", "staircase")),
    "lattice": (_lattice, ((6, 2), (12, 2), (12, 3)), ("lattice", "trellis")),
    "check": (_check, ((6, 3), (12, 6)), ("check", "checked", "checker", "checkerboard",
                                          "chequer", "chequered", "chequerboard")),
    "wave": (_wave, ((12, 2), (12, 3)), ("wave", "waves", "wavy")),
}
MOTIF_WORD: dict[str, str] = {w: k for k, (_g, _p, words) in MOTIFS.items() for w in words}


def _row_ok(row: str, cyclic_cap: int) -> bool:
    """A tile row tiles into chart rows that pass every gate: both colours, the scarcer at
    least MIN_MINORITY_SHARE with a run of MIN_CONTRAST_RUN, no carry longer than the cap."""
    if set(row) != {MAIN, CONTRAST}:
        return False
    counts = {s: row.count(s) for s in (MAIN, CONTRAST)}
    minority = min(counts, key=counts.get)
    if counts[minority] / len(row) < MIN_MINORITY_SHARE:
        return False
    ring = row + row
    longest = {s: max(len(m) for m in re.findall(f"{s}+", ring)) for s in (MAIN, CONTRAST)}
    if min(longest[minority], len(row)) < MIN_CONTRAST_RUN:
        return False
    # The carry of each yarn is the longest run of the OTHER symbol, cyclically.
    return all(min(longest[s], len(row)) <= cyclic_cap for s in (MAIN, CONTRAST))


def tile(motif: str, params: tuple[int, int]) -> tuple[str, ...]:
    gen, _options, _words = MOTIFS[motif]
    return gen(*params)


def valid_tile(rows: tuple[str, ...], cap: int = MAX_FLOAT[TAPESTRY]) -> bool:
    return bool(rows) and len({len(r) for r in rows}) == 1 and all(_row_ok(r, cap) for r in rows)


def library_problems() -> list[str]:
    """Every motif option that cannot tile a valid chart (empty: the library is sound)."""
    out = []
    for key, (gen, options, _words) in MOTIFS.items():
        for p in options:
            rows = gen(*p)
            if len(rows[0]) not in WIDTHS:
                out.append(f"{key}{p}: width {len(rows[0])} not in {WIDTHS}")
            elif not valid_tile(rows):
                out.append(f"{key}{p}: a row fails the colour/float/run rule")
    if not valid_tile(SEPARATOR):
        out.append("separator fails the colour/float/run rule")
    return out


# ---- the concept's chart ---------------------------------------------------------------------


def _seed(slug: str, title: str) -> bytes:
    return hashlib.sha256(f"brambleloop-colourwork-v1|{slug}|{title}".encode()).digest()


def motif_named(title: str | None) -> list[str]:
    """The library motifs a title names, in order (duplicates folded)."""
    from .fallback_constructions import fold_title

    words = re.findall(r"[a-z]+(?:-[a-z]+)*", fold_title(title))
    return list(dict.fromkeys(MOTIF_WORD[w] for w in words if w in MOTIF_WORD))


def design(slug: str, title: str, *, widths: tuple[int, ...] = WIDTHS) -> dict:
    """The concept's chart design: motif, tile, layout choices. Deterministic."""
    seed = _seed(slug, title)
    named = motif_named(title)
    keys = sorted(MOTIFS)
    motif = named[0] if named else keys[seed[0] % len(keys)]
    gen, options, _w = MOTIFS[motif]
    usable = [p for p in options if p[0] in widths and valid_tile(gen(*p))]
    if not usable:
        raise ValueError(f"no {motif} tile of width {widths} passes the chart rules")
    params = usable[seed[1] % len(usable)]
    return {"motif": motif, "params": params, "tile": gen(*params),
            "blocks": 1 + seed[2] % 3,          # tile repeats per block, vertically
            "half_drop": bool(seed[3] % 2),     # alternate blocks shifted half a tile
            "invert": bool(seed[4] % 2),        # alternate blocks swap main and contrast
            "separator": bool(seed[5] % 2)}


def _shift(rows: tuple[str, ...], by: int) -> tuple[str, ...]:
    return tuple(r[by:] + r[:by] for r in rows) if by else rows


def _invert(rows: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(r.translate(str.maketrans("01", "10")) for r in rows)


def band(d: dict, height: int) -> list[str]:
    """`height` chart rows (one tile wide) for design `d`: blocks of the tile, alternately
    half-dropped and inverted, with an optional two-row separator between blocks. Always whole
    tiles: the band is cut to the last whole block, never mid-motif. Of the block heights up to
    the design's, the one that fills the most rows is used (ties keep the taller block), so a
    small piece is not left with wide plain borders."""
    best: list[str] = []
    for blocks in range(d["blocks"], 0, -1):
        try:
            got = _band({**d, "blocks": blocks}, height)
        except ValueError:
            continue
        if len(got) > len(best):
            best = got
    if not best:
        raise ValueError(f"the band is {height} rows; one {d['motif']} tile needs "
                         f"{len(d['tile'])}")
    return best


def _band(d: dict, height: int) -> list[str]:
    t = d["tile"]
    w = len(t[0])
    sep = [SEPARATOR[i] * (w // len(SEPARATOR[i])) for i in range(2)] if d["separator"] else []
    out: list[str] = []
    k = 0
    while True:
        block = t * d["blocks"]
        if k % 2 and d["half_drop"]:
            block = _shift(block, w // 2)
        if k % 2 and d["invert"]:
            block = _invert(block)
        unit = (sep if k else []) + list(block)
        if len(out) + len(unit) > height:
            break
        out.extend(unit)
        k += 1
    if not out:
        raise ValueError(f"the band is {height} rows; one {d['motif']} tile needs {len(t)}")
    return out


def unit_height(d: dict) -> int:
    return len(d["tile"]) * d["blocks"]


def chart_rows(d: dict, width: int, height: int) -> list[str]:
    """The band tiled across `width` stitches (a multiple of the tile width)."""
    w = len(d["tile"][0])
    if width % w:
        raise ValueError(f"width {width} is not a multiple of the {w}-st tile")
    return [r * (width // w) for r in band(d, height)]


# ---- runs -> ops ---------------------------------------------------------------------------


def _runs(line: str, colours: dict[str, str], row_colour: str) -> list:
    runs: list[list] = []
    for ch in line:
        c = colours[ch]
        if runs and runs[-1][0] == c:
            runs[-1][1] += 1
        else:
            runs.append([c, 1])
    return [Op("sc", n, color=None if c == row_colour else c) for c, n in runs]


def _row_ops(fabric_line: str, colours: dict[str, str], row_colour: str, *,
             reverse: bool, repeat: int) -> list:
    """Ops in WORKING order for a fabric-order line, as a bracketed repeat of one tile."""
    line = fabric_line[::-1] if reverse else fabric_line
    unit = len(line) // repeat
    if line != line[:unit] * repeat:
        return _runs(line, colours, row_colour)
    return [Repeat(_runs(line[:unit], colours, row_colour), times=repeat)]


# ---- flat pieces (blanket, placemat, cushion front) -----------------------------------------

FLAT_CATEGORIES = ("blanket", "placemat", "pillow")
_DEFAULT_TARGET_CM = {"blanket": (128.0, 152.0), "placemat": (30.0, 45.0),
                      "pillow": (45.0, 45.0)}


def target_cm(category: str, title: str) -> tuple[float, float]:
    """(short, long) cm: the size class the title names, else the category's standard."""
    from . import size_truth

    req = size_truth.request(category, title)
    if req.get("refused"):
        raise ValueError(req["refused"])
    return tuple(req["target"]) if req.get("target") else _DEFAULT_TARGET_CM[category]


def _flat_rows(d: dict, width: int, total_rows: int, main: str, contrast: str
               ) -> tuple[list[Row], Chart]:
    w = len(d["tile"][0])
    band_rows = chart_rows(d, width, total_rows - 2 * BORDER_ROWS)
    below = (total_rows - len(band_rows)) // 2
    colours = {MAIN: main, CONTRAST: contrast}
    rows: list[Row] = []
    for i in range(1, total_rows + 1):
        b = i - below - 1
        if 0 <= b < len(band_rows):
            ops = _row_ops(band_rows[b], colours, main, reverse=i % 2 == 0,
                           repeat=width // w)
        else:
            ops = [Op("sc", width)]
        rows.append(Row(index=i, ops=ops, declared_count=width, turning_chain=1, color=main))
    first, last = below + 1, below + len(band_rows)
    rows[first - 1].note = f"join {contrast} at the start of this row and carry it"
    if last < total_rows:
        rows[last - 1].note = f"cut {contrast} after this row and fasten it off"
    chart = Chart(technique=TAPESTRY, key={MAIN: main, CONTRAST: contrast},
                  rows=band_rows, first_row=first, motif=d["motif"])
    return rows, chart


FLAT_NOTE = ("Tapestry crochet in rows. On every charted row carry the colour not in use along "
             "the top of the row below and work over it, so it is hidden inside the stitches; "
             "change colour on the last yarn-over of the stitch before the new colour. Read "
             "odd-numbered (right-side) rows of the chart from right to left and even-numbered "
             "(wrong-side) rows from left to right; the written rows already give every "
             "stitch in working order. At the end of a charted row keep both yarns at the "
             "edge and carry the contrast up into the turning chain.")


def flat_piece(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A flat tapestry piece (blanket, placemat) or a cushion cover with a charted front."""
    from .prototype import gauge_for

    category = concept.category
    if category not in FLAT_CATEGORIES:
        raise ValueError(f"{concept.slug}: no flat colourwork template for {category!r}")
    colours = list(dict.fromkeys(concept.colors))
    if len(colours) < 2 or len({concept.colors[c] for c in colours[:2]}) < 2:
        raise ValueError(f"{concept.slug}: tapestry needs two distinct colours")
    main, contrast = colours[0], colours[1]
    gauge = gauge_for(concept.yarn_weight)
    d = design(concept.slug, concept.title)
    w = len(d["tile"][0])
    short, long_ = target_cm(category, concept.title)
    across_cm, tall_cm = (long_, short) if category == "placemat" else (short, long_)
    width = max(w, int(round(across_cm * gauge.stitches_per_10cm / 10.0 / w)) * w)
    total = int(round(tall_cm * gauge.rows_per_10cm / 10.0))
    if total - 2 * BORDER_ROWS < unit_height(d):
        raise ValueError(f"{concept.slug}: {total} rows cannot hold one {d['motif']} block")
    rows, chart = _flat_rows(d, width, total, main, contrast)
    piece = "front" if category == "pillow" else category
    materials = [Material(name=f"{concept.yarn_weight} acrylic",
                          yarn_weight=concept.yarn_weight, color_id=c) for c in (main, contrast)]
    comps = [Component(name=piece, construction="flat_rows", rows=rows, foundation=width,
                       foundation_kind="chain", note=FLAT_NOTE, chart=chart)]
    assembly: list[Seam] = []
    noun = {"blanket": "blanket", "placemat": "placemat", "pillow": "cushion cover"}[category]
    if category == "pillow":
        back = [Row(index=i, ops=[Op("sc", width)], declared_count=width, turning_chain=1,
                    color=main) for i in range(1, total + 1)]
        comps.append(Component(name="back", construction="flat_rows", rows=back,
                               foundation=width, foundation_kind="chain",
                               note="Plain single crochet in the main colour."))
        assembly = [Seam("whipstitch", "front", "back", edge_a=e, edge_b=e,
                         note=f"Hold the panels wrong sides together and whipstitch the {e} "
                              f"edges.") for e in ("left", "top", "right")]
        assembly.append(Seam("whipstitch", "front", "back", edge_a="bottom", edge_b="bottom",
                             stuff_before_closing=True,
                             note="Insert the cushion pad, then whipstitch the bottom edges "
                                  "closed."))
    tile_w, tile_h = w, len(d["tile"])
    return CIR(
        slug=concept.slug, title=concept.title, version=version, construction="flat_rows",
        risk_class=concept.risk_class, colors=dict(concept.colors), gauge=gauge,
        materials=materials, components=comps, assembly=assembly,
        designer_notes=(f"{category} concept drafted as a tapestry crochet {noun}: an original "
                        f"{d['motif']} chart ({tile_w} sts x {tile_h} rows per tile, generated "
                        f"from the Brambleloop motif library) worked in {main} and {contrast} "
                        f"over rows {chart.first_row}-{chart.last_row}, with "
                        f"{chart.first_row - 1} plain rows below and "
                        f"{total - chart.last_row} above"),
        finished_size_note=(f"A tapestry {noun} computed at the stated gauge; not yet "
                            f"measured on a worked sample."),
        provenance=provenance,
    )


# ---- the basket wall (joined rounds) ------------------------------------------------------


def basket_wall(concept, *, version: str = "1.0.0", provenance=None) -> CIR:
    """A hexagon-based basket whose wall carries a generated tapestry chart in rounds."""
    from ..products.vessels import (BASKET_SIZES, _disc_rounds, base_stitches_for,
                                    hexagon_spans_cm)
    from .fallback_constructions import _TAPESTRY_SIZE_WORDS, fold_title
    from .prototype import gauge_for

    colours = list(dict.fromkeys(concept.colors))
    if len(colours) < 2 or len({concept.colors[c] for c in colours[:2]}) < 2:
        raise ValueError(f"{concept.slug}: tapestry needs two distinct colours")
    main, contrast = colours[0], colours[1]
    folded = fold_title(concept.title)
    key = next((k for word, k in _TAPESTRY_SIZE_WORDS if re.search(rf"\b{word}\b", folded)),
               "medium")
    spec = next(s for s in BASKET_SIZES if s.key == key)
    gauge = gauge_for(concept.yarn_weight)
    d = design(concept.slug, concept.title)
    w = len(d["tile"][0])
    wanted = base_stitches_for(spec.across_cm, gauge)
    base = max(12, int(round(wanted / 12.0)) * 12)       # six wedges and both tile widths
    rows = _disc_rounds(base, main)
    row_cm = 10.0 / gauge.rows_per_10cm
    wall = max(BASKET_PLAIN_BELOW + BASKET_PLAIN_RIM + unit_height(d),
               int(round(spec.tall_cm / row_cm)))
    band_rows = chart_rows(d, base, wall - BASKET_PLAIN_BELOW - BASKET_PLAIN_RIM)
    below = BASKET_PLAIN_BELOW
    rim = wall - below - len(band_rows)
    colours_map = {MAIN: main, CONTRAST: contrast}
    index = rows[-1].index
    first = index + below + 1
    for wnd in range(wall):
        index += 1
        b = wnd - below
        if 0 <= b < len(band_rows):
            ops = _row_ops(band_rows[b], colours_map, main, reverse=False, repeat=base // w)
        else:
            ops = [Op("sc", base)]
        rows.append(Row(index=index, ops=ops, declared_count=base, color=main))
    last = first + len(band_rows) - 1
    by = {r.index: r for r in rows}
    by[first].note = f"join {contrast} at the start of this round"
    if last < rows[-1].index:
        by[last].note = f"cut {contrast} after this round and fasten it off"
    chart = Chart(technique=TAPESTRY, key=dict(colours_map), rows=band_rows, first_row=first,
                  motif=d["motif"])
    points, flats = hexagon_spans_cm(base, gauge)
    return CIR(
        slug=concept.slug, title=concept.title, version=version,
        construction="joined_rounds", risk_class=concept.risk_class,
        colors=dict(concept.colors), gauge=gauge,
        materials=[Material(name=f"{concept.yarn_weight} acrylic",
                            yarn_weight=concept.yarn_weight, color_id=c)
                   for c in (main, contrast)],
        components=[Component(
            name="basket", construction="joined_rounds", rows=rows, foundation=0,
            foundation_kind="magic_ring", chart=chart,
            note=(f"Worked in one piece from the centre of the base. Work each increase into "
                  f"the second stitch of the previous round's increase, so the base is a "
                  f"hexagon. Rounds {first}-{last} are tapestry crochet: lay the colour not "
                  f"in use along the top of the round and work over it, and change colour in "
                  f"the last yarn-over of the stitch before. Read every chart round from "
                  f"right to left. Tapestry single crochet in rounds leans slightly in the "
                  f"working direction, so the chart's columns spiral a little; that is the "
                  f"fabric, not an error."))],
        designer_notes=(f"{concept.category} concept drafted as a tapestry crochet basket: "
                        f"hexagon base of {base} sts, {wall} wall rounds, of which rounds "
                        f"{first}-{last} carry an original {d['motif']} chart ({w} sts per "
                        f"tile, generated from the Brambleloop motif library) in {main} and "
                        f"{contrast}; {rim} plain rounds at the rim"),
        finished_size_note=(
            f"A hexagonal tapestry basket about {points:.1f} cm across the points and "
            f"{flats:.1f} cm across the flats, walls about {wall * row_cm:.0f} cm tall, at the "
            f"stated gauge. Computed, not yet measured on a worked sample."),
        provenance=provenance,
    )


PRIMITIVES = ("creative.colourwork", "creative.colourwork.MOTIFS", "cir.colourwork")
FLAT_PRIMITIVES = PRIMITIVES + ("creative.colourwork.flat_piece",)
BASKET_PRIMITIVES = PRIMITIVES + ("creative.colourwork.basket_wall",
                                  "products.vessels._disc_rounds",
                                  "products.vessels.base_stitches_for")


def motif_primitive(motif: str) -> str:
    """The provenance primitive naming one library motif (`launch0.MOTIF_DECLARATIONS`)."""
    return f"creative.colourwork:{motif}"


def motif_declarations() -> dict[str, dict]:
    """What each library motif backs as a title word, for `launch0.motif_promise`."""
    return {motif_primitive(k): {"backs": frozenset(words), "medium": "colourwork"}
            for k, (_g, _p, words) in MOTIFS.items()}


# ---- routing ------------------------------------------------------------------------------

FAMILY = "colourwork_tapestry"
OVERLAY_MOSAIC = "colourwork_overlay_mosaic"
INSET_MOSAIC = "colourwork_inset_mosaic"
C2C = "colourwork_c2c"

CLAIM = r"\b(?:tapestry|colou?r ?work|charted)\b"
_NOT_TAPESTRY: tuple[tuple[str, str, str], ...] = (
    (r"\binset mosaic\b", INSET_MOSAIC, "inset mosaic: chain spaces bridged now and filled by "
                                        "stitches dropped from the row above, which the CIR "
                                        "does not express yet"),
    (r"\b(?:mosaic|overlay)\b", OVERLAY_MOSAIC, "overlay mosaic: stitches that reach down past "
                                                "the previous row, which the CIR does not "
                                                "express yet"),
    (r"\b(?:c2c|corner[- ]to[- ]corner)\b", C2C, "corner-to-corner: diagonal tiles increased "
                                                 "and decreased, which the CIR does not "
                                                 "express yet"),
    (r"\b(?:graph ?gh?an|pixel)\b", C2C, "a pixel picture (graphghan): worked as C2C or "
                                         "charted single crochet with bobbins; not built"),
    (r"\b(?:intarsia|duplicate[- ]stitch(?:ed)?)\b", "intarsia",
     "separate colour blocks with no carried strand (bobbins), not modelled"),
    (r"\b(?:fair[- ]?isle|stranded|jacquard)\b", "fair_isle",
     "a floated stranded technique, not tapestry"),
    (r"\b(?:three|four|multi|tri)[- ]?colou?r(?:ed)?\b", FAMILY,
     "more than two colours in a row; tapestry carries two"),
)
_PLURAL = r"\b(?:pair|pairs|set|sets|duo|trio|two|three|four|six|\d+)\b"
_CHILDREN = r"\b(?:baby|babies|nursery|infant|newborn|toddler|child|children|kids?|crib|cot)\b"
_FLAT_HEADS = {"blanket": r"\b(?:blanket|throw|afghan)$", "placemat": r"\bplacemat$",
               "pillow": r"\b(?:cushion|pillow)(?: cover)?$"}
def _allowed() -> frozenset[str]:
    from .fallback_constructions import _TAPESTRY_ALLOWED_WORDS

    return frozenset(_TAPESTRY_ALLOWED_WORDS) | {
        "charted", "blanket", "throw", "afghan", "placemat", "cushion", "pillow", "cover",
        "basket", "lap", "sofa", "couch", "bed", "twin", "full", "queen", "king", "home",
        "contemporary", "minimal", "minimalist", "bold", "graphic", "heirloom", "farmhouse",
        "boho", "scandi", "nordic", "retro", "vintage", "the", "a", "of", "in", "crochet",
        "pattern", "rustic", "woven-look"} - {"woven-look"}


_ALLOWED = _allowed()
HELD_CATEGORY_WHY: dict[str, str] = {
    "bag": "a bag needs a tote's straps and assembly; the tote family is not verified end to "
           "end, so a charted bag panel is held until a tapestry tote certifies",
    "baby": "a baby item with carried strands is not assessed by the children's gates for "
            "colourwork; held until it is",
    "runner": "no end-to-end proof for a charted runner yet",
    "wall_decor": "no end-to-end proof for a charted wall hanging yet",
    "scarf": "a scarf shows its wrong side; tapestry's carried strand is not reversible",
    "dishcloth": "a dishcloth is scrubbed; carried strands are not a dishcloth fabric",
}


def technique_claim(title: str | None) -> tuple[str, str] | None:
    """(family, why) for a colourwork technique the title names that tapestry is not."""
    from .fallback_constructions import fold_title

    folded = fold_title(title)
    for rx, family, why in _NOT_TAPESTRY:
        if re.search(rx, folded):
            return family, why
    return None


# CERTFIX-3 (D-CERTFIX3-WALL-TAPESTRY): in wall decor a bare "tapestry" is the object -- a
# wall tapestry, the hanging `creative.size_truth.TAPESTRY` already reads it as and binds to
# its own size band -- not a claim of tapestry crochet. "Tapestry crochet"/"tapestry stitch",
# "charted", "colourwork" or a library motif word is still a technique claim, and a wall
# hanging that makes one stays held (`HELD_CATEGORY_WHY["wall_decor"]`): no plain panel is
# drafted under a colourwork claim.
_WALL_OBJECT = r"\btapestr(?:y|ies)\b(?!\s+(?:crochet|stitch))"


def wall_object_only(folded: str) -> bool:
    """True when a wall-decor title's only colourwork word is the object noun "tapestry"."""
    if not re.search(_WALL_OBJECT, folded):
        return False
    rest = re.sub(_WALL_OBJECT, " ", folded)
    return not re.search(CLAIM, rest) and not motif_named(folded)


def route(category: str, title: str | None) -> dict | None:
    """The fallback plan for a colourwork title, or None when the title claims no colourwork.

    Called by `fallback_constructions.plan`. Flat categories route here when the title claims
    tapestry or charted colourwork; a basket routes here only when it names a library motif the
    existing two-chart tapestry basket does not have (diamond and check stay with it)."""
    from .fallback_constructions import REFUSED, fold_title

    folded = fold_title(title)
    other = technique_claim(title)
    claims = bool(re.search(CLAIM, folded))
    if not claims and other is None:
        return None
    if category == "wall_decor" and other is None and wall_object_only(folded):
        return None          # the object the category names, not a technique: S1's route
    if category == "basket":
        named = motif_named(title)
        if other is not None or not claims or not named or set(named) <= {"diamond", "check"}:
            return None      # the existing tapestry basket route decides
    elif category not in FLAT_CATEGORIES:
        if category in HELD_CATEGORY_WHY:
            return {"family": REFUSED, "needs": "an end-to-end colourwork proof for "
                                                f"{category!r}",
                    "why": HELD_CATEGORY_WHY[category], "colourwork": FAMILY}
        return None
    if other is not None:
        family, why = other
        return {"family": REFUSED, "needs": why, "colourwork": family,
                "why": f"the title claims {why.split(':')[0]}; only tapestry is drafted"}
    if re.search(_CHILDREN, folded):
        return {"family": REFUSED, "needs": "a children's colourwork assessment",
                "why": HELD_CATEGORY_WHY["baby"], "colourwork": FAMILY}
    if re.search(_PLURAL, folded) or re.search(r"\bbaskets\b", folded):
        return {"family": REFUSED, "needs": "one certified release per piece",
                "why": "the title promises more than one piece; one draft is one piece",
                "colourwork": FAMILY}
    if category != "basket":
        head = re.search(_FLAT_HEADS[category], folded)
        if not head:
            return {"family": REFUSED, "needs": f"a {category} title",
                    "why": f"the title {title!r} does not name the {category} it would draft",
                    "colourwork": FAMILY}
    named = motif_named(title)
    if len(named) > 1:
        return {"family": REFUSED, "needs": "one certified release per chart",
                "why": f"the title names {' and '.join(named)}; one release carries one chart",
                "colourwork": FAMILY}
    # An allowlist, as the tapestry basket's: every word must be a colourwork, motif, size or
    # plain descriptive word, so a picture the chart does not draw ("heron", "juniper") is
    # refused whatever it is called, never sold over a geometric chart.
    tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", folded)
    unbacked = [w for w in tokens if w not in _ALLOWED and w not in MOTIF_WORD]
    leftover = re.sub(r"[a-z0-9\s\-]", "", folded)
    if leftover:
        unbacked.append(leftover)
    if unbacked:
        return {"family": REFUSED, "colourwork": FAMILY,
                "needs": f"the motif or construction {' '.join(unbacked)!r} names",
                "why": f"the title names {unbacked!r}, which the colourwork engine does not "
                       f"make (motifs: {', '.join(sorted(MOTIFS))})"}
    return {"family": FAMILY, "needs": "",
            "why": "charted tapestry crochet, generated from the Brambleloop motif library"}


# ---- originality: chart fingerprints -------------------------------------------------------

CHART_WINDOW = 6
_CHART_SALT = b"brambleloop-chart-v1"


def _norm(window: list[str]) -> str:
    """Colour-blind: symbols renamed by first appearance, so swapping colours is no disguise."""
    names: dict[str, str] = {}
    return "/".join("".join(names.setdefault(ch, "abcdefghij"[len(names)]) for ch in row)
                    for row in window)


def chart_fingerprint(rows: list[str], n: int = CHART_WINDOW) -> frozenset[str]:
    """Salted, truncated hashes of every n x n two-colour window, mirror-folded. Identifies a
    chart's geometry without storing it (the teardown rule: fingerprints, never charts)."""
    out: set[str] = set()
    if len(rows) < n:
        return frozenset()
    width = min(len(r) for r in rows)
    for y in range(len(rows) - n + 1):
        for x in range(width - n + 1):
            win = [rows[y + j][x:x + n] for j in range(n)]
            if len({c for r in win for c in r}) < 2:
                continue
            a, b = _norm(win), _norm([r[::-1] for r in win])
            key = min(a, b).encode()
            out.add(hashlib.sha256(_CHART_SALT + key).hexdigest()[:16])
    return frozenset(out)


def cir_chart_fingerprint(cir: CIR) -> frozenset[str]:
    out: set[str] = set()
    for comp in cir.components:
        if comp.chart is not None:
            out |= chart_fingerprint(comp.chart.rows)
    return frozenset(out)
