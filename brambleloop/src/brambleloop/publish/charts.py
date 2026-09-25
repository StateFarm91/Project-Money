"""Stitch and colour charts rendered from the digital twin.

Every pixel here is derived from the compiled CIR. Nothing is drawn from a description, a
prompt or a reference image, which is the only way a chart can be trusted to agree with the
written instructions -- if the chart and the text can disagree, one of them is lying to a
customer who is forty hours into a blanket.

Charts are also the clearest differentiation available to us. The profiled competitors ship
charts as flat images with no legend discipline and one finished size; ours are generated,
so they are consistent, legible and reproducible for every size we publish.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from ..brand import bible
from ..cir.model import CIR
from ..cir.twin import TwinModel


# The brand palette, read from the brand system rather than restated here.
#
# `brand/bible.py` says "anything that renders an asset reads from here", and this module held
# its own copies of six of those hex codes -- written out as RGB triples, which is how a
# duplicate survives a search for the hex string that would have found it. The customer's PDF
# was corrected on 2026-09-24 and the chart inside it was not, so the chart was the last asset
# where the brand was not actually locked. The values are byte-identical; nothing about any
# render changes, which is the point.
INK = bible.rgb255("ink")
PINE = bible.rgb255("pine")
CREAM = bible.rgb255("cream")
GOLD = bible.rgb255("gold")
LINE = bible.rgb255("line")


def _legible_on(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """Brand ink darkened until it clears the text-contrast floor on this background.

    The same rule, from the same place, as the PDF that embeds these images. `muted` on `cream`
    measures 4.48:1 -- under WCAG AA for text below 18pt -- and it is the colour of the chart's
    row and stitch numbers, its caption and the legend's colour-cue note. Those are the labels
    a maker reads with the work in their hands, and they were the half of the document's type
    that nothing measured: the PDF darkened its own prose and the pictures inside it kept the
    raw palette.
    """
    r, g, b = bible.legible(tuple(c / 255 for c in fg), tuple(c / 255 for c in bg))
    return (round(r * 255), round(g * 255), round(b * 255))


# Every use of MUTED in this module is small type on the chart's cream ground.
MUTED = _legible_on(bible.rgb255("muted"), CREAM)

# Stitch glyphs. Deliberately ASCII-safe: a chart that depends on an exotic font renders as
# empty boxes on someone else's machine, and we cannot see that happen.
GLYPHS: dict[str, str] = {
    "ch": "o", "slst": ".", "sc": "x", "hdc": "T", "dc": "F", "tr": "H",
    "inc": "V", "dec": "A", "dc_inc": "W", "dc_dec": "M", "sk": "-",
    # Texture. A stitch with no glyph falls back to the first character of its code, which
    # would have drawn both post stitches and the bobble as "b".
    #
    # `cable1x1` was "x", which is also `sc`. Nothing in the catalogue uses `cable1x1`, so the
    # two had never appeared in one chart and the collision was invisible -- a defect whose only
    # sample could not contain it. A chart drawing two different stitches with one mark, over a
    # legend listing that mark twice, is a maker working the wrong stitch off a chart the whole
    # product is sold on. "/" is the single crossing to "X"'s double.
    "fpdc": "]", "bpdc": "[", "bob": "O", "cable2x2": "X", "cable1x1": "/",
}


# Set when a TrueType face could not be loaded. Pillow's fallback is a bitmap font a few
# pixels tall, which on a 2000px listing image is invisible -- so the images looked right on
# a machine with DejaVu installed and shipped with no legible text from a container without
# it. A silent fallback is how that went unnoticed, so it is recorded and surfaced by
# `check_frame_plan` instead.
FONT_FALLBACK_IN_USE = False

# Set when a multi-colour chart had to be drawn without a hue-independent colour cue.
#
# Master Plan section 31 asks for "colour-independent cues where practical", and in overlay
# mosaic the colour *is* the motif: a chart that distinguishes cream from pine by hue alone
# is unreadable to a maker with a colour vision deficiency, and they are the customer least
# able to recover from it -- they cannot ask the fabric which yarn a square meant. So every
# cell of a multi-colour chart carries its colour's letter, matching the legend, and if the
# cells are too small to carry one that is recorded here rather than shipped silently. Same
# discipline as the font fallback above, for the same reason: a silent degradation is the
# kind that survives a deploy.
COLOR_CUE_MISSING = False


def reset_render_flags() -> None:
    """Clear the per-render degradation flags before rendering a product's imagery.

    `COLOR_CUE_MISSING` is a property of one chart, so it has to be cleared or a single
    chart that could not carry a cue would block every product rendered after it in the
    same worker process -- a false accusation, which is how a real check becomes noise that
    gets ignored.

    `FONT_FALLBACK_IN_USE` is deliberately *not* cleared. It is a fact about the container,
    not about a product: either a TrueType face exists on this machine or it does not, and
    `_font` re-sets it on the next render anyway. Clearing it would throw away an
    environment truth in order to re-derive it, and it would make a test that simulates a
    missing font pass on a machine that has one.
    """
    global COLOR_CUE_MISSING
    COLOR_CUE_MISSING = False


# A, B, C... in the CIR's own colour order, which is the order the legend and the written
# instructions already use. An index, not a rename: the colour keeps its name everywhere.
_CUE_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# How to find a colour's letter on the chart, which depends on the chart.
#
# Stated once, here, because the legend image and the PDF's text colour key both have to say
# it and a picture and a paragraph disagreeing about where to look is worse than either alone.
COLOUR_CUE_NOTE_FLAT = (
    "Each square on the chart carries its yarn's letter in the top-left corner; the symbol in "
    "the middle of the square is the stitch."
)
COLOUR_CUE_NOTE_ROUND = (
    "Each round number on the chart carries its yarn's letter, where that whole round is "
    "worked in one colour, so the chart can be read without relying on colour."
)


def color_letters(cir: CIR) -> dict[str, str]:
    """Stable, hue-independent label per colour. Derived from the CIR, never declared."""
    return {name: _CUE_LETTERS[i % len(_CUE_LETTERS)]
            for i, name in enumerate(cir.colors)}


def flat_cue_letters(cir: CIR, colors: list[list[str | None]], cell: int) -> dict[str, str]:
    """The colour letters a flat chart over these cells will actually carry.

    Called by `render_chart` and by the document that prints the key in text, so the picture
    and the paragraph cannot disagree about whether there are any letters to look up. A single
    colour carries none -- an "A" in every square would be noise presented as accessibility --
    and a cell too small to hold one carries none either.
    """
    if cell < CUE_MIN_CELL_PX:
        return {}
    if len({c for row in colors for c in row if c}) <= 1:
        return {}
    return color_letters(cir)


def round_cue_labels(cir: CIR, twin: TwinModel, *, ring_px: int,
                     rounds: tuple[int, int] | None = None) -> dict[int, str]:
    """Round number to colour letter, for the rounds a round chart will actually label.

    Extracted from `render_round_chart` rather than restated, because the document has to know
    what the picture says. **A cropped round chart is the case that made this necessary.** A
    basket's shaping rounds are all one colour -- the contrast bands are up the wall, in the
    straight rounds the chart no longer draws -- so a chart of rounds 1 to 24 carries no
    letters at all, while the document went on printing "each round number on the chart
    carries its yarn's letter". That is the same defect as telling a round chart's reader to
    look at squares, arriving by a different route.

    Only rounds worked entirely in one colour get a letter: one letter beside a ring worked in
    two yarns would be a wrong label rather than a missing one.
    """
    shown = [r for r in _rounds_of(twin) if rounds is None or rounds[0] <= r <= rounds[1]]
    per_round = {r: {c.color for c in _round_cells(twin, r) if c.color} for r in shown}
    if ring_px < CUE_MIN_CELL_PX:
        return {}
    if len({c for cs in per_round.values() for c in cs}) <= 1:
        return {}
    letters = color_letters(cir)
    out: dict[int, str] = {}
    for r in shown:
        names = per_round[r]
        if len(names) != 1:
            continue
        letter = letters.get(next(iter(names)))
        if letter:
            out[r] = letter
    return out


def _font(size: int) -> ImageFont.ImageFont:
    """Load a real TrueType face when one exists, else fall back without crashing."""
    global FONT_FALLBACK_IN_USE
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    FONT_FALLBACK_IN_USE = True
    return ImageFont.load_default()


def _wrap(draw: "ImageDraw.ImageDraw", text: str, font, max_px: int) -> list[str]:
    """Break a caption into lines that fit, measuring with the font that will draw it.

    Greedy by word, and a single word wider than the whole line is left on its own rather
    than dropped: an over-long line is ugly, a missing one is a lie about what the image
    says.
    """
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    line = words[0]
    for word in words[1:]:
        candidate = f"{line} {word}"
        if draw.textlength(candidate, font=font) <= max_px:
            line = candidate
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def _hex_to_rgb(value: str | None, fallback: tuple[int, int, int] = CREAM):
    if not value or not value.startswith("#") or len(value) != 7:
        return fallback
    try:
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
    except ValueError:
        return fallback


def _readable_on(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """Ink or cream on this square, whichever measures better -- and moved until it passes.

    Said it picked "whichever a human can actually read" and decided on a weighted-average
    lightness against a hand-set threshold of 0.55, which is not a contrast measurement and
    does not have to agree with one. On the brand's own `muted` it chose cream at 4.48:1,
    under the AA floor for text this size.

    That matters more here than anywhere else in the document, because what this colour draws
    is the per-colour letter cue -- the thing that makes a mosaic chart readable by a maker who
    cannot distinguish the yarns by hue. An accessibility feature rendered below the contrast
    floor is the feature failing in the case it exists for. Yarn colourways come out of the CIR
    as arbitrary hex, so any threshold standing in for the measurement will eventually be given
    the colour it is wrong about.

    Both candidates are moved away from the background until they clear the floor, and the
    better *result* is taken. Ranking the two before moving them is a subtler version of the
    same mistake: on a mid-lightness yarn the brand cream measures fractionally better than the
    brand ink and cannot be improved, because it is already nearly white, while the ink can be
    darkened all the way to legible. Picking the leader of the unimproved pair chose the one
    with nowhere to go and landed at 3.9:1 on a plain mid-grey.
    """
    ground = tuple(c / 255 for c in bg)
    return max((_legible_on(INK, bg), _legible_on(CREAM, bg)),
               key=lambda fg: bible.contrast_ratio(tuple(c / 255 for c in fg), ground))


def detect_repeat(grid: list[list[str]], colors: list[list[str | None]]
                  ) -> tuple[int, int]:
    """Find the smallest block the chart is built from, in (columns, rows).

    A 144 x 120 blanket chart printed on one page gives each stitch about one pixel, which is
    decoration, not a chart. Real mosaic patterns publish one repeat and say how many times to
    work it, and that is only honest if the repeat is *derived* from the fabric rather than
    asserted by whoever wrote the copy. So it is computed here: the smallest column period and
    row period that the whole grid actually satisfies.

    Colour is part of the comparison. Two rows with identical stitches in different colours are
    different rows to a maker.
    """
    rows = len(grid)
    cols = max((len(r) for r in grid), default=0)
    if rows == 0 or cols == 0:
        return 0, 0

    def row_key(i: int) -> list[tuple[str, str | None]]:
        cs = colors[i] if i < len(colors) else []
        return [(grid[i][j], cs[j] if j < len(cs) else None) for j in range(len(grid[i]))]

    col_period = cols
    for period in range(1, cols + 1):
        if cols % period:
            continue
        if all(row_key(i)[j] == row_key(i)[j % period]
               for i in range(rows) for j in range(len(grid[i]))):
            col_period = period
            break

    row_period = rows
    for period in range(1, rows + 1):
        if rows % period:
            continue
        if all(row_key(i) == row_key(i % period) for i in range(rows)):
            row_period = period
            break
    return col_period, row_period


def crop_grids(grid: list[list[str]], colors: list[list[str | None]],
               cols: int, rows: int) -> tuple[list[list[str]], list[list[str | None]]]:
    """The bottom-left block of the chart: the unit a maker actually reads."""
    g = [r[:cols] for r in grid[:rows]]
    c = [r[:cols] for r in colors[:rows]]
    return g, c


@dataclass(frozen=True)
class ChartSpec:
    cell_px: int = 26
    margin_px: int = 56
    max_width_px: int = 2400
    show_glyphs: bool = True


def cell_size(twin: TwinModel, spec: ChartSpec,
              grids: tuple[list[list[str]], list[list[str | None]]] | None = None) -> int:
    """Shrink cells rather than emit an image nobody can open.

    A 160-stitch blanket at 26px per cell is over four thousand pixels wide. Scaling down is
    better than truncating: a chart missing its right-hand edge is worse than a small chart.

    Public, and called by `render_chart` rather than repeated inside it, because the caller has
    to be able to ask how big a cell will be *before* deciding whether this chart is the one to
    print. The expression lived in two places -- here for a full chart and inline in
    `render_chart` for a cropped one -- and nothing outside could ask either of them.
    """
    if grids is not None:
        widest = max((len(r) for r in grids[0]), default=1)
    else:
        widest = max(twin.row_widths.values(), default=1)
    usable = spec.max_width_px - 2 * spec.margin_px
    return max(6, min(spec.cell_px, usable // max(1, widest)))


def row_block(cir: CIR, twin: TwinModel) -> tuple[int, int, int] | None:
    """The rows the chart should show, as (first, last, further_repeats), 1-indexed.

    **Asks the writer's own repeat detector rather than a second one.** `detect_repeat` searches
    for a row period that *divides* the row count and starts at row 1, and eight of the sixteen
    shippable designs satisfy neither: they open with setup rows and then repeat a block whose
    period is not a divisor of the total. So `detect_repeat` reported "no vertical repeat" and
    the chart page printed the whole fabric -- 121 rows of a cabled throw, captioned "this chart
    shows one repeat: 8 stitches wide and 121 rows tall", three pages after written instructions
    that say "Repeat rows 2-5 29 more times".

    Two repeat detectors, one fabric, two answers, and the chart printed the wrong one. The
    rowcycle detector is the canonical one: the written pattern collapses to it and the reverse
    compiler expands it back, which is the property the whole validation chain rests on.

    Returns the block from row 1 through the end of the first repeat, so no row is left out of
    the chart -- a chart that silently started at row 2 would be a new defect, not a fix.
    """
    from ..cir.rowcycle import detect_cycle

    # Only where the grid is this component's rows. A multi-component piece charts something
    # else, and guessing which rows those are is how a chart stops matching its instructions.
    if len(cir.components) != 1:
        return None
    rows = cir.components[0].rows
    if len(rows) != len(twin.chart_grid()):
        return None
    cycle = detect_cycle(rows)
    if cycle is None:
        return None
    return cycle.start, cycle.end, cycle.repeats


# Below this a cell cannot carry a legible letter as well as a stitch glyph, which is the
# point at which the colour cue stops being available rather than merely small.
CUE_MIN_CELL_PX = 13


# ---- how big the chart sets its own type -----------------------------------
#
# Every piece of type in a chart is a fraction of the chart's readable unit -- the cell on a
# flat chart, the ring on a round one -- because the whole image is then scaled to the page.
# So the only way to say "no type in this document is below the brand's minimum" is to know
# these fractions, and they were written as bare literals inside two render functions with a
# third copy of one of them (`0.62`) in `publish/pdf.py`, where the legibility floor is
# derived. A floor derived from a copy of a number is a floor that stops meaning anything the
# first time somebody changes the original.
#
# Named here, used by the renderers below, and read by `publish/pdf.py`. The smallest of them
# is what the floor has to be derived from: a floor set by the *largest* type in the picture
# certifies the one piece of type that was never in danger.
GLYPH_RATIO = 0.62          # the stitch symbol in the middle of a flat cell
LABEL_RATIO = 0.55          # row numbers, the flat chart's title and its reading-direction note
CUE_RATIO = 0.46            # the colour's letter in the corner of a flat cell
ROUND_GLYPH_RATIO = 0.55    # the increase/decrease mark in a ring
ROUND_LABEL_RATIO = 0.60    # round numbers, the round chart's title and its footer

# The smallest type each kind of chart sets, as a fraction of its readable unit.
FLAT_TYPE_RATIO = min(GLYPH_RATIO, LABEL_RATIO, CUE_RATIO)
ROUND_TYPE_RATIO = min(ROUND_GLYPH_RATIO, ROUND_LABEL_RATIO)


def flat_type_px(cell: int) -> dict[str, int]:
    """Every font size a flat chart sets, for a cell this many pixels across.

    The renderer calls this rather than computing the sizes inline, so a check asking "is any
    type in this picture below the brand's minimum" is asking the renderer rather than a
    reading of it. The lower bounds are pixel floors rather than ratios: below them a glyph
    stops being a shape at all, and a chart that has reached one is a chart the legibility
    floor should already have rejected.
    """
    return {"glyph": max(7, int(cell * GLYPH_RATIO)),
            "label": max(9, int(cell * LABEL_RATIO)),
            "cue": max(6, int(cell * CUE_RATIO))}


def round_type_px(ring: int) -> dict[str, int]:
    """Every font size a round chart sets, for a ring this many pixels wide."""
    return {"glyph": max(7, int(ring * ROUND_GLYPH_RATIO)),
            "label": max(10, int(ring * ROUND_LABEL_RATIO))}


# The legend's type. Fixed pixels rather than a ratio, because a legend is a list of rows and
# has no readable unit to be a fraction of -- but it is still type inside an image inside the
# customer's document, so it is named here and measured on the page like everything else. A
# legend tall enough to be scaled down by page height would shrink it; at every entry count
# the taxonomy can produce it is not, and the check says so with a number rather than a hope.
LEGEND_TYPE_PX: dict[str, int] = {"head": 17, "body": 15}


# The only stitches a round chart draws a mark for. A ring of wedges shows where the count
# changes; everything else in the round is the ground the wedges are drawn on.
ROUND_MARKED_CODES: tuple[str, ...] = ("inc", "dec", "dc_inc", "dc_dec")


def round_mark_note(codes) -> str:
    """'V marks an increase and A a decrease', for the marks this chart actually draws.

    Built from the codes present rather than written out, because the footer said "V marks an
    increase, A a decrease" on every round chart while `GLYPHS` draws `dc_inc` as W and
    `dc_dec` as M. No design in this catalogue works a disc in double crochet, so the sentence
    has never yet been wrong on a shipped document -- which is the same shape as the two
    stitches that shared one glyph: a defect whose only sample cannot contain it.
    """
    from ..cir import stitches as taxonomy

    parts = []
    for code in ROUND_MARKED_CODES:
        if code not in codes:
            continue
        st = taxonomy.get(code)
        what = "an increase" if st.produces > st.consumes else "a decrease"
        # "V marks an increase and A a decrease": the verb is carried by the first clause,
        # which is how the sentence read when it was a literal.
        parts.append(f"{GLYPHS[code]} marks {what}" if not parts
                     else f"{GLYPHS[code]} {what}")
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0] + "."
    return ", ".join(parts[:-1]) + f" and {parts[-1]}."


def shaping_codes() -> frozenset[str]:
    """Every stitch that changes the count of the round it is worked in.

    Derived from the taxonomy's own `consumes`/`produces` rather than listed here, because a
    list is a second opinion about what an increase is: `cir.stitches` already says that a
    stitch consuming one and producing two is an increase, and a stitch added there with no
    entry in a private list would silently stop counting as shaping.

    This answers "does this round change the fabric's geometry", which is a different question
    from "which mark does the round chart draw in this wedge" -- that one is the renderer's,
    and it draws V and A for the four increase and decrease codes it names in its own footer.
    """
    from ..cir import stitches as taxonomy

    return frozenset(code for code in taxonomy.known_codes()
                     if taxonomy.get(code).consumes != taxonomy.get(code).produces)


def _rounds_of(twin: TwinModel) -> list[int]:
    return sorted({c.row for c in twin.cells})


def _round_cells(twin: TwinModel, r: int) -> list:
    return sorted((c for c in twin.cells if c.row == r), key=lambda c: c.position)


def wedge_count(twin: TwinModel) -> int:
    """How many identical wedges every round of this piece repeats around.

    The round equivalent of `detect_repeat`'s column period, and derived the same way: the
    largest number that divides every round's stitch count and leaves every round unchanged
    when its cells are read modulo that period. Colour is part of the comparison, as it is
    there -- two wedges with the same stitches in different yarns are different wedges.

    A disc worked from a magic ring is six-fold by construction (`[sc in next n, inc] x 6`),
    and that six is what makes a sixty-degree slice of the chart a complete statement of the
    round rather than a piece of one. It is read out of the fabric rather than taken from the
    `Repeat(times=...)` in the CIR, so a piece whose wedges are only *nearly* identical
    reports the period it actually has.
    """
    common: set[int] | None = None
    for r in _rounds_of(twin):
        seq = [(c.stitch, c.color) for c in _round_cells(twin, r)]
        n = len(seq)
        periods = {k for k in range(1, n + 1) if n % k == 0
                   and all(seq[i] == seq[i % (n // k)] for i in range(n))}
        common = periods if common is None else (common & periods)
        if not common:
            return 1
    return max(common) if common else 1


@dataclass(frozen=True)
class RoundBlock:
    """The rounds a round chart should draw, and the truth about the ones it does not.

    `tail` is the straight run at the end -- rounds with no shaping and a constant stitch
    count. On a basket that is the side wall: forty-six rounds of "sc in each st around",
    drawn by the chart as forty-six concentric rings occupying two thirds of the radius of a
    disc that is really a flat base with a cylinder standing on it. They cost every ring in
    the picture two thirds of its width and they show a maker nothing the written line does
    not say in six words.

    The fields are here so the caption can state what the chart leaves out in the document's
    own numbers, rather than the chart quietly showing less than the pattern contains.
    """

    first: int
    last: int
    tail: tuple[int, ...]
    tail_stitches: int
    tail_color: str | None
    tail_other_colors: tuple[tuple[str, int, int], ...]


def round_block(twin: TwinModel) -> RoundBlock | None:
    """Rounds 1 to the last one that shapes, when everything after it is worked straight.

    `None` when there is nothing to leave out -- the hexagon coaster shapes in every round it
    has, so its chart is the whole piece and stays so.
    """
    rounds = _rounds_of(twin)
    if len(rounds) < 3:
        return None
    shaping = shaping_codes()
    cells = {r: _round_cells(twin, r) for r in rounds}
    counts = {r: len(cells[r]) for r in rounds}
    shaped = {r for r in rounds if any(c.stitch in shaping for c in cells[r])}

    i = len(rounds) - 1
    while i > 0 and rounds[i] not in shaped and counts[rounds[i]] == counts[rounds[i - 1]]:
        i -= 1
    tail = tuple(rounds[i + 1:])
    # One straight round at the end is not worth a sentence explaining its absence.
    if len(tail) < 2:
        return None
    # A piece with no shaping anywhere has no shaped block to show, and cropping to round 1
    # would be a chart of a single ring -- less of the piece rather than more of the chart.
    if rounds[i] not in shaped:
        return None

    def colour_of(r: int) -> str | None:
        names = {c.color for c in cells[r]}
        return next(iter(names)) if len(names) == 1 else None

    base = colour_of(tail[0])
    others: list[tuple[str, int, int]] = []
    run_name, run_from, run_to = None, 0, 0
    for r in tail:
        name = colour_of(r)
        if name == base:
            if run_name is not None:
                others.append((run_name, run_from, run_to))
                run_name = None
            continue
        if name == run_name and r == run_to + 1:
            run_to = r
        else:
            if run_name is not None:
                others.append((run_name, run_from, run_to))
            run_name, run_from, run_to = name or "", r, r
    if run_name is not None:
        others.append((run_name, run_from, run_to))

    return RoundBlock(first=rounds[0], last=rounds[i], tail=tail,
                      tail_stitches=counts[tail[0]], tail_color=base,
                      tail_other_colors=tuple(others))


def round_chart_size(twin: TwinModel, spec: ChartSpec | None = None, *,
                     rounds: tuple[int, int] | None = None,
                     wedges: int | None = None) -> tuple[int, int, int]:
    """(ring width, drawing width, drawing height) in pixels, before any text is laid out.

    Public and separate from the renderer because the caller has to be able to ask how large
    a ring will land on the page *before* deciding which chart to print -- the same reason
    `cell_size` is public for the flat chart. Nothing here draws, so asking is cheap even for
    a seventy-round basket whose full chart is a 2384-pixel square.

    The sector case is the reason the ring can be worth widening at all. A whole disc puts its
    *diameter* across the page, so a ring is at most half the page width divided by the round
    count; one wedge puts its *radius* across the page instead, which is twice as much room
    for the same number of rounds.
    """
    spec = spec or ChartSpec()
    shown = [r for r in _rounds_of(twin) if rounds is None or rounds[0] <= r <= rounds[1]]
    bands = max(1, len(shown) + 1)          # the rings, plus the blank hub inside round 1
    sector = bool(wedges and wedges > 1)
    if rounds is None and not sector:
        # The default: a whole disc at the spec's own cell size. Unchanged, so every chart
        # that was already legible renders exactly the bytes it rendered before.
        ring = max(10, min(spec.cell_px, (spec.max_width_px // 2 - spec.margin_px) // bands))
    elif sector:
        half = math.pi / wedges
        ring = max(10, int((spec.max_width_px - 2 * spec.margin_px)
                           / (2 * math.sin(half)) // bands))
    else:
        ring = max(10, (spec.max_width_px // 2 - spec.margin_px) // bands)
    outer = ring * bands
    if sector:
        half = math.pi / wedges
        width = int(2 * outer * math.sin(half) + spec.margin_px * 2)
        height = int(outer + spec.margin_px * 2)
    else:
        width = height = int(outer * 2 + spec.margin_px * 2)
    return ring, width, height


def render_chart(cir: CIR, twin: TwinModel, spec: ChartSpec | None = None,
                 grids: tuple[list[list[str]], list[list[str | None]]] | None = None,
                 caption: str | None = None) -> Image.Image:
    """Colour chart with stitch glyphs, row numbers and working direction.

    Row 1 is drawn at the bottom, the way fabric actually grows, and alternate rows are
    numbered on alternating sides because that is the side the maker is working from.
    """
    spec = spec or ChartSpec()
    cell = cell_size(twin, spec, grids)
    type_px = flat_type_px(cell)
    glyph_font = _font(type_px["glyph"])
    label_font = _font(type_px["label"])

    grid = grids[0] if grids else twin.chart_grid()
    colors = grids[1] if grids else twin.color_grid()
    # The colour cue only exists where colour carries information. A single-colour chart
    # marked "A" in every square would be noise presented as accessibility.
    multicolour = len({c for row in colors for c in row if c}) > 1
    # `flat_cue_letters` is the one implementation of "will this chart carry letters", and the
    # document that prints the key in text asks the same function, so the picture and the
    # paragraph cannot disagree about whether there is anything to look up.
    cues = flat_cue_letters(cir, colors, cell)
    cue_font = _font(type_px["cue"])
    if multicolour and not cues:
        global COLOR_CUE_MISSING
        COLOR_CUE_MISSING = True
    rows = len(grid)
    cols = max((len(r) for r in grid), default=0)
    if rows == 0 or cols == 0:
        raise ValueError("cannot render a chart for a twin with no cells")

    gutter = spec.margin_px
    grid_w = cols * cell
    title = caption or f"{cir.title} - {twin.component}"
    footer = "odd rows read right to left   even rows read left to right"
    # A small repeat chart is narrower than its own caption. Sizing the canvas to the grid
    # alone silently crops the title and the reading-direction note off both edges, which is
    # the sort of thing that looks like a broken file to a customer.
    probe = Image.new("RGB", (1, 1))
    pd = ImageDraw.Draw(probe)
    text_w = max(pd.textlength(title, font=label_font),
                 pd.textlength(footer, font=label_font))
    width = int(max(grid_w + gutter * 2, text_w + gutter * 2))
    height = gutter * 2 + rows * cell
    left = (width - grid_w) // 2
    img = Image.new("RGB", (width, height), CREAM)
    d = ImageDraw.Draw(img)

    for r_idx in range(rows):
        row_number = r_idx + 1
        y = gutter + (rows - row_number) * cell   # row 1 at the bottom
        row_cells = grid[r_idx]
        row_colors = colors[r_idx] if r_idx < len(colors) else []
        for c_idx in range(len(row_cells)):
            x = left + c_idx * cell
            color_id = row_colors[c_idx] if c_idx < len(row_colors) else None
            bg = _hex_to_rgb(cir.colors.get(color_id) if color_id else None)
            d.rectangle([x, y, x + cell, y + cell], fill=bg, outline=LINE)
            ink = _readable_on(bg)
            cue = cues.get(color_id or "")
            if spec.show_glyphs and cell >= 10:
                code = row_cells[c_idx]
                g = GLYPHS.get(code, code[:1])
                d.text((x + cell / 2, y + cell / 2), g, font=glyph_font, fill=ink,
                       anchor="mm")
                # The letter sits in the corner so it never hides the stitch, which is the
                # other thing the square has to say.
                if cue and cell >= CUE_MIN_CELL_PX:
                    d.text((x + cell * 0.19, y + cell * 0.21), cue, font=cue_font,
                           fill=ink, anchor="mm")
            elif cue and cell >= CUE_MIN_CELL_PX:
                # No room for both, and the glyphs are already suppressed at this size, so
                # the colour is the only thing left to say and it says it in the middle.
                d.text((x + cell / 2, y + cell / 2), cue, font=cue_font, fill=ink,
                       anchor="mm")

        # Number every row on the side it is worked from; on a tiny cell, every fifth.
        if cell >= 10 or row_number % 5 == 0 or row_number == rows:
            label = str(row_number)
            if row_number % 2 == 1:
                d.text((left - 8, y + cell / 2), label, font=label_font, fill=MUTED,
                       anchor="rm")
            else:
                d.text((left + len(row_cells) * cell + 8, y + cell / 2), label,
                       font=label_font, fill=MUTED, anchor="lm")

    d.text((width / 2, gutter - 26), title, font=label_font, fill=PINE, anchor="ms")
    d.text((width / 2, height - gutter + 22), footer, font=label_font, fill=MUTED,
           anchor="ms")
    return img


def render_round_chart(cir: CIR, twin: TwinModel, spec: ChartSpec | None = None,
                       caption: str | None = None, plain: bool = False, *,
                       rounds: tuple[int, int] | None = None,
                       wedges: int | None = None) -> Image.Image:
    """Concentric chart for a piece worked in the round: round 1 at the centre, outward.

    The grid chart is wrong here in two ways at once, and both of them mislead a maker rather
    than merely looking odd. A disc worked from six stitches to sixty draws as a ragged
    left-aligned staircase, which is not the shape of the thing; and the footer telling them
    that odd rows read right to left is flat-fabric advice, when every round is worked in the
    same direction.

    So the rounds are drawn as rings of wedges, one wedge per stitch, in the colour that
    round is worked in, with the increases and decreases marked where they fall. A maker can
    count the wedges in a ring and compare them with the stitch count in the written line.

    `rounds` and `wedges` are the round chart's two ways of being legible, and they are the
    exact counterparts of what the flat chart already does: show the rows that carry the
    pattern, and show one repeat across rather than the whole width.

    * `rounds` draws a contiguous block instead of every round. A seventy-round basket spends
      forty-six of them on a straight side wall, and drawing those as forty-six concentric
      rings costs every ring in the picture two thirds of its width.
    * `wedges` draws one of the piece's identical wedges instead of the whole disc, which puts
      the chart's *radius* across the page instead of its diameter -- twice the ring width for
      the same rounds. The wedge is centred on twelve o'clock so the round numbers, which are
      drawn there, stay inside it.

    Both are off by default, so a chart that was already legible renders the bytes it always
    rendered. The caller decides, on a measurement, and says in the caption what it did --
    a chart that silently showed part of a piece would be a new defect, not a fix.
    """
    spec = spec or ChartSpec()
    every_round = _rounds_of(twin)
    if not every_round:
        raise ValueError("cannot render a chart for a twin with no cells")
    rows = [r for r in every_round if rounds is None or rounds[0] <= r <= rounds[1]]
    if not rows:
        raise ValueError(f"no round of this piece falls in {rounds}")
    if plain and (rounds is not None or wedges):
        raise ValueError("the fabric view is the whole piece: it takes no block and no wedge")

    cells_by_round: dict[int, list] = {r: _round_cells(twin, r) for r in rows}
    ring_px, disc_w, disc_h = round_chart_size(twin, spec, rounds=rounds, wedges=wedges)
    hub = ring_px                      # a small blank centre so round 1 reads as a ring
    outer = hub + len(rows) * ring_px
    sector = bool(wedges and wedges > 1)
    # A whole disc is the sector nobody cropped: 360 degrees, starting where it always did.
    span = 360.0 / wedges if sector else 360.0
    arc0 = -90.0 - span / 2.0 if sector else -90.0

    type_px = round_type_px(ring_px)
    label_font = _font(type_px["label"])
    glyph_font = _font(type_px["glyph"])
    # Every round in this catalogue is worked in one colour, so the cue belongs on the
    # round's number rather than in every wedge: repeating it sixty times around a ring says
    # nothing more than once beside the ring does, and a round chart has no spare room.
    #
    # The CIR permits a round worked in two colours, though, and one letter beside such a
    # ring would be a wrong label rather than a missing one -- so that case reports no cue
    # instead of an inaccurate one. `plain` is exempt because it is the fabric view: the
    # hero image carries no labels at all by design, and the chart page beside it is where
    # a maker reads the colours.
    per_round = {r: {c.color for c in cells_by_round[r] if c.color} for r in rows}
    multicolour = len({c for cs in per_round.values() for c in cs}) > 1
    mixed_round = any(len(cs) > 1 for cs in per_round.values())
    # The one implementation of which rounds get a letter, shared with the document that
    # prints the key in text -- see `round_cue_labels` for why a cropped chart made that
    # necessary.
    cue_labels = round_cue_labels(cir, twin, ring_px=ring_px, rounds=rounds)
    if multicolour and not plain and (ring_px < CUE_MIN_CELL_PX or mixed_round):
        global COLOR_CUE_MISSING
        COLOR_CUE_MISSING = True

    title = caption or f"{cir.title} - {twin.component}"
    # The innermost ring shown, which is round 1 unless the caller asked for a block.
    marks = round_mark_note({c.stitch for r in rows for c in cells_by_round[r]})
    footer = f"Round {rows[0]} is the centre. Every round is worked in the same direction."
    if marks:
        footer += f" {marks}"
    if sector:
        # Said on the picture as well as in the document's caption, because the picture is
        # what a maker has beside the work and a slice of a disc that does not say it is a
        # slice is a disc with most of its stitches missing.
        footer += (f" This is one of the {wedges} identical wedges of each round: multiply "
                   f"a ring's wedge count by {wedges} for that round's stitch count.")
    # Only when a round number actually carries one. A cropped chart of a basket's base shows
    # rounds worked in one colour, so there is no letter after any of its numbers and this
    # sentence would be pointing at something that is not on the picture.
    if cue_labels:
        footer += " The letter after a round number is its yarn, as in the colour key."
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    # The footer wraps rather than stretching the canvas. Widening it to fit one long line
    # is what a longer footer used to do, and it turns a disc chart into a 2:1 rectangle
    # that is mostly empty cream with a small circle in the middle -- which is exactly the
    # shape the round renderer exists to stop producing. Height is cheap; aspect is not.
    text_px = max(disc_w - spec.margin_px, 200)
    footer_lines = _wrap(probe, footer, label_font, text_px)
    title_lines = _wrap(probe, title, label_font, text_px)
    line_h = int(getattr(label_font, "size", 14) * 1.35)
    # Room for one line of type at whatever size this chart sets it.
    #
    # The title is centred half a margin from the top and the last footer line half a margin
    # from the bottom, which is fine while a line of type is shorter than the margin -- and it
    # was, because the ring was capped at 22 pixels and the type with it. A chart sized to fill
    # the page sets 68-pixel type inside a 56-pixel margin, and the first thing a reader saw
    # was a title with its ascenders cut off and a footer missing its last line's descenders.
    # Measured from the font rather than fixed, so it cannot go stale the next time the cap
    # moves; identical to the old arithmetic wherever a line still fits the margin, which is
    # every chart that was rendering before.
    pad = max(spec.margin_px, line_h)
    head = pad + max(0, len(title_lines) - 1) * line_h
    foot = max(0, len(footer_lines) - 1) * line_h + (pad - spec.margin_px)
    # The title is a product title -- up to 140 characters -- so it wraps for the same
    # reason the footer does. Sized to the widest line that survived wrapping, which is at
    # most the disc's own width, so the canvas stays disc-shaped.
    width = int(max(disc_w, max(probe.textlength(t, font=label_font) for t in title_lines)
                    + spec.margin_px))
    img = Image.new("RGB", (width, head + disc_h + foot), CREAM)
    # The canvas can still be a little wider than the disc, so the drawing centre is not
    # the canvas centre in both axes: the circle stays centred on the rings, not the text.
    #
    # A sector's centre is its apex, which sits at the bottom of the drawing area with the
    # rings stacked above it -- the round numbers then run up the middle of the wedge.
    cx = width / 2.0
    cy = (head + spec.margin_px + outer) if sector else (head + disc_h / 2.0
                                                         - spec.margin_px / 2.0)
    d = ImageDraw.Draw(img)

    # Outermost ring first. Each ring is drawn as a full pie and then has its centre filled
    # back in, so a ring drawn later must be *inside* the one before it -- going inward-out
    # would erase everything already drawn.
    for depth, r_index in reversed(list(enumerate(rows))):
        inner = hub + depth * ring_px
        edge = inner + ring_px
        cells = cells_by_round[r_index]
        step = 360.0 / len(cells)
        # One wedge of the round, or all of it. `wedge_count` guarantees the first slice is
        # a complete statement of the round, because it only reports a period the whole
        # round actually satisfies.
        drawn = len(cells) // wedges if sector else len(cells)
        for position in range(drawn):
            cell = cells[position]
            start = arc0 + position * step
            bg = _hex_to_rgb(cir.colors.get(cell.color))
            # A wedge is the ring band between two radii; drawing the outer pie and then the
            # inner one in the background colour is the cheap, dependency-free way to get it.
            d.pieslice([cx - edge, cy - edge, cx + edge, cy + edge],
                       start=start, end=start + step, fill=bg, outline=LINE)
        if sector:
            d.pieslice([cx - inner, cy - inner, cx + inner, cy + inner],
                       start=arc0, end=arc0 + span, fill=CREAM, outline=LINE)
        else:
            d.ellipse([cx - inner, cy - inner, cx + inner, cy + inner],
                      fill=CREAM, outline=LINE)

        # Mark the shaping where it falls, which is the only thing a round chart really has
        # to show: six stacked marks are a hexagon, six that drift are a circle.
        if ring_px >= 12 and not plain:
            for position in range(drawn):
                cell = cells[position]
                if cell.stitch not in ROUND_MARKED_CODES:
                    continue
                angle = math.radians(arc0 + (position + 0.5) * step)
                radius = inner + ring_px * 0.5
                d.text((cx + radius * math.cos(angle),
                        cy + radius * math.sin(angle)),
                       GLYPHS.get(cell.stitch, "V"), font=glyph_font, fill=INK, anchor="mm")

    if plain:
        # `plain` is the fabric view: the object as the twin knows it, seen from above, with
        # no chart furniture. Used for the hero, where a numbered chart would be a diagram of
        # the product rather than a picture of it.
        return img.crop((int(cx - outer), int(cy - outer), int(cx + outer), int(cy + outer)))

    # Round numbers last, so a label is never painted over by a later ring, and only where
    # there is room for one: a sixty-round basket cannot carry sixty legible numbers.
    step_labels = 1 if ring_px >= 16 else 5
    for depth, r_index in enumerate(rows):
        if r_index % step_labels and r_index not in (rows[0], rows[-1]):
            continue
        y = cy - (hub + depth * ring_px + ring_px * 0.5)
        cue = cue_labels.get(r_index, "")
        label = f"{r_index}{cue}" if cue else str(r_index)
        half = probe.textlength(label, font=label_font) / 2 + 2
        d.rectangle([cx - half, y - ring_px * 0.4, cx + half, y + ring_px * 0.4],
                    fill=CREAM)
        d.text((cx, y), label, font=label_font, fill=MUTED, anchor="mm")

    for i, line in enumerate(title_lines):
        d.text((width / 2, pad / 2 + i * line_h), line, font=label_font,
               fill=PINE, anchor="mm")
    for i, line in enumerate(footer_lines):
        d.text((width / 2, head + disc_h - spec.margin_px / 2 + i * line_h), line,
               font=label_font, fill=MUTED, anchor="mm")
    return img


def render_round_fabric(cir: CIR, twin: TwinModel,
                        spec: ChartSpec | None = None) -> Image.Image:
    """The round-worked piece seen from above, in its own colours. No chart furniture."""
    return render_round_chart(cir, twin, spec, plain=True)


def is_round(cir: CIR, twin: TwinModel) -> bool:
    comp = next((c for c in cir.components if c.name == twin.component), None)
    return comp is not None and comp.construction != "flat_rows"


def render_any_chart(cir: CIR, twin: TwinModel, spec: ChartSpec | None = None,
                     caption: str | None = None) -> Image.Image:
    """The right chart for the construction, so no caller has to remember which."""
    if is_round(cir, twin):
        return render_round_chart(cir, twin, spec, caption)
    return render_chart(cir, twin, spec, caption=caption)


def render_legend(cir: CIR, twin: TwinModel, spec: ChartSpec | None = None) -> Image.Image:
    """A legend covering exactly the stitches and colours the chart actually uses.

    Listing every stitch in the taxonomy would be padding; listing fewer than the chart uses
    would be a defect. Both are derived from the twin so neither can happen.
    """
    spec = spec or ChartSpec()
    row_h = 34
    stitches = sorted(twin.stitch_types_used)
    used_colors = sorted(c for c in twin.colors_used if c)
    entries = len(stitches) + len(used_colors) + 2
    width, height = 720, 40 + entries * row_h
    img = Image.new("RGB", (width, height), CREAM)
    d = ImageDraw.Draw(img)
    head, body = _font(LEGEND_TYPE_PX["head"]), _font(LEGEND_TYPE_PX["body"])

    y = 20
    d.text((24, y), "STITCH KEY", font=head, fill=PINE)
    y += row_h
    from ..cir import stitches as taxonomy

    for code in stitches:
        d.rectangle([24, y, 24 + 24, y + 24], fill=CREAM, outline=LINE)
        d.text((36, y + 12), GLYPHS.get(code, code[:1]), font=body, fill=INK, anchor="mm")
        try:
            st = taxonomy.get(code)
            name = f"{st.name_us}  (UK {st.name_uk})"
        except taxonomy.UnknownStitch:  # pragma: no cover - taxonomy is closed
            name = code
        d.text((64, y + 12), f"{code}   {name}", font=body, fill=INK, anchor="lm")
        y += row_h

    y += 8
    d.text((24, y), "COLOUR KEY", font=head, fill=PINE)
    y += row_h
    # The letter is what makes the key usable without colour vision: a swatch identified
    # only by its hue tells a colour-blind maker nothing, and in mosaic work the colour is
    # the motif rather than a decoration they can ignore.
    cues = color_letters(cir) if len(used_colors) > 1 else {}
    for name in used_colors:
        bg = _hex_to_rgb(cir.colors.get(name))
        d.rectangle([24, y, 24 + 24, y + 24], fill=bg, outline=LINE)
        cue = cues.get(name)
        if cue:
            d.text((36, y + 12), cue, font=body, fill=_readable_on(bg), anchor="mm")
        label = f"{cue}   {name}" if cue else name
        d.text((64, y + 12), f"{label}   {cir.colors.get(name, '')}", font=body, fill=INK,
               anchor="lm")
        y += row_h
    if cues:
        # Where the letter actually is, per chart kind.
        #
        # This said "each square on the chart carries its yarn's letter" for every pattern,
        # and a round chart has no squares: `render_round_chart` appends the letter to the
        # round *number*, and only for a round worked entirely in one colour. So on the one
        # construction where the reader most needs telling where to look, the legend described
        # a chart that was not in front of them. The flat chart's letter sits in the corner of
        # the square and the symbol in the middle is the stitch, which is also worth saying:
        # several stitch glyphs are themselves capital letters.
        d.text((24, y + 6), COLOUR_CUE_NOTE_ROUND if is_round(cir, twin)
                            else COLOUR_CUE_NOTE_FLAT,
               font=body, fill=MUTED)
    return img


def render_fabric(cir: CIR, twin: TwinModel, *, cell_px: int = 18,
                  grids: tuple[list[list[str]], list[list[str | None]]] | None = None,
                  ) -> Image.Image:
    """What the finished fabric looks like, with no chart furniture on it.

    A chart is an instruction; this is a depiction. The hero image needs the second one --
    row numbers, glyphs and a legend on the first listing image say "technical drawing" to a
    shopper scrolling a grid, and the thing they are deciding about is whether the blanket is
    beautiful.

    The overlay-mosaic construction is modelled rather than ignored, and this matters more
    than it sounds. Each row is worked in one colour, so colouring cells by their row's yarn
    produces flat horizontal stripes and no motif at all -- the first version of this function
    did exactly that and the fir trees vanished. In real overlay mosaic the pattern comes from
    the *taller* stitches: a double crochet is worked over the top of the row below and hangs
    down into it, so it reads as a mark in this row's colour against the previous row's
    contrasting band. Drawing that overhang is what makes the motif appear, and it appears
    only because the compiled pattern really does put those stitches there.

    It remains a digital twin render and nothing else: it cannot depict a motif, colour or
    proportion the pattern does not produce.
    """
    grid = grids[0] if grids else twin.chart_grid()
    colors = grids[1] if grids else twin.color_grid()
    rows = len(grid)
    cols = max((len(r) for r in grid), default=0)
    if rows == 0 or cols == 0:
        raise ValueError("cannot render fabric for a twin with no cells")

    from ..cir import stitches as taxonomy

    def row_height_units(r_idx: int) -> float:
        tallest = 1.0
        for code in grid[r_idx]:
            try:
                tallest = max(tallest, taxonomy.get(code).row_height or 1.0)
            except taxonomy.UnknownStitch:  # pragma: no cover - taxonomy is closed
                pass
        return tallest

    # Row bands are sized by the row's shortest stitch: the tall ones overhang downward
    # instead of inflating the band, which is how the fabric actually stacks.
    band = max(3, int(cell_px * 0.62))
    width, height = cols * cell_px, rows * band
    img = Image.new("RGB", (width, height), CREAM)
    d = ImageDraw.Draw(img)

    def cell_color(r_idx: int, c_idx: int):
        row_colors = colors[r_idx] if r_idx < len(colors) else []
        name = row_colors[c_idx] if c_idx < len(row_colors) else None
        return _hex_to_rgb(cir.colors.get(name))

    def relief(code: str) -> float:
        """How much lighter or darker this stitch sits than the plain ground.

        Colourwork is not the only way fabric has a pattern. A cabled throw in one cream
        yarn is *all* relief -- the design is light and shadow off the stitch geometry -- and
        colouring cells by their row's yarn rendered it as a blank cream rectangle. The hero
        for the rebuilt cable throw was literally empty, and the thumbnail check caught it in
        production while passing locally, because the only visible thing in the frame was
        the title text.
        """
        return {
            "bob": -0.30,        # a raised dot catches light on top and shades beneath
            "cable2x2": -0.20,   # a crossing sits proud of the ground
            "cable1x1": -0.17,
            "fpdc": -0.13,       # a front post stitch stands forward
            "bpdc": 0.10,        # a back post stitch recedes
            "dc": -0.04,
            "tr": -0.07,
            "slst": 0.08,
        }.get(code, 0.0)

    def shaded(base, code: str):
        amount = relief(code)
        if not amount:
            return base
        if amount < 0:
            return tuple(max(0, int(v * (1.0 + amount))) for v in base)
        return tuple(min(255, int(v + (255 - v) * amount)) for v in base)

    # Base bands, bottom row first, each cell shaded by the relief of its own stitch.
    for r_idx in range(rows):
        y = height - (r_idx + 1) * band
        for c_idx in range(len(grid[r_idx])):
            x = c_idx * cell_px
            code = grid[r_idx][c_idx]
            d.rectangle([x, y, x + cell_px, y + band],
                        fill=shaded(cell_color(r_idx, c_idx), code))

    # Tall stitches, drawn as overhangs into the rows beneath them.
    for r_idx in range(rows):
        y = height - (r_idx + 1) * band
        for c_idx, code in enumerate(grid[r_idx]):
            try:
                extra = (taxonomy.get(code).row_height or 1.0) - 1.0
            except taxonomy.UnknownStitch:  # pragma: no cover
                extra = 0.0
            if extra <= 0:
                continue
            x = c_idx * cell_px
            drop = int(band * extra)
            # Shaded, like the base band. Painting the overhang in the flat row colour
            # erased the relief underneath it, which is why a single-colour cabled fabric
            # still rendered as a blank rectangle after the shading was added.
            d.rectangle([x, y, x + cell_px, min(height, y + band + drop)],
                        fill=shaded(cell_color(r_idx, c_idx), code))

    # One lighter stroke per stitch reads as a loop at thumbnail size and stops a large flat
    # field from looking like a printed colour block.
    for r_idx in range(rows):
        y = height - (r_idx + 1) * band
        for c_idx in range(len(grid[r_idx])):
            x = c_idx * cell_px
            base = img.getpixel((min(width - 1, x + cell_px // 2),
                                 min(height - 1, y + band // 2)))
            hi = tuple(min(255, int(v * 1.14)) for v in base)
            d.line([(x + cell_px * 0.28, y + band * 0.3),
                    (x + cell_px * 0.72, y + band * 0.3)], fill=hi, width=1)
    return img
