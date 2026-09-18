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

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from ..cir.model import CIR
from ..cir.twin import TwinModel

# Brand palette (Brand Model Bible): pine, cream, gold, wine, ink.
INK = (26, 43, 60)
PINE = (36, 74, 58)
CREAM = (250, 246, 235)
GOLD = (196, 149, 69)
LINE = (214, 206, 188)
MUTED = (107, 114, 128)

# Stitch glyphs. Deliberately ASCII-safe: a chart that depends on an exotic font renders as
# empty boxes on someone else's machine, and we cannot see that happen.
GLYPHS: dict[str, str] = {
    "ch": "o", "slst": ".", "sc": "x", "hdc": "T", "dc": "F", "tr": "H",
    "inc": "V", "dec": "A", "dc_inc": "W", "dc_dec": "M", "sk": "-",
    # Texture. A stitch with no glyph falls back to the first character of its code, which
    # would have drawn both post stitches and the bobble as "b".
    "fpdc": "]", "bpdc": "[", "bob": "O", "cable2x2": "X", "cable1x1": "x",
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


def color_letters(cir: CIR) -> dict[str, str]:
    """Stable, hue-independent label per colour. Derived from the CIR, never declared."""
    return {name: _CUE_LETTERS[i % len(_CUE_LETTERS)]
            for i, name in enumerate(cir.colors)}


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
    """Pick ink or cream for text, whichever a human can actually read on this square."""
    luminance = (0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]) / 255
    return INK if luminance > 0.55 else CREAM


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


def _cell_size(twin: TwinModel, spec: ChartSpec) -> int:
    """Shrink cells rather than emit an image nobody can open.

    A 160-stitch blanket at 26px per cell is over four thousand pixels wide. Scaling down is
    better than truncating: a chart missing its right-hand edge is worse than a small chart.
    """
    widest = max(twin.row_widths.values(), default=1)
    usable = spec.max_width_px - 2 * spec.margin_px
    return max(6, min(spec.cell_px, usable // max(1, widest)))


# Below this a cell cannot carry a legible letter as well as a stitch glyph, which is the
# point at which the colour cue stops being available rather than merely small.
CUE_MIN_CELL_PX = 13


def render_chart(cir: CIR, twin: TwinModel, spec: ChartSpec | None = None,
                 grids: tuple[list[list[str]], list[list[str | None]]] | None = None,
                 caption: str | None = None) -> Image.Image:
    """Colour chart with stitch glyphs, row numbers and working direction.

    Row 1 is drawn at the bottom, the way fabric actually grows, and alternate rows are
    numbered on alternating sides because that is the side the maker is working from.
    """
    spec = spec or ChartSpec()
    cell = _cell_size(twin, spec) if grids is None else max(
        6, min(spec.cell_px,
               (spec.max_width_px - 2 * spec.margin_px) // max(1, len(grids[0][0]))))
    glyph_font = _font(max(7, int(cell * 0.62)))
    label_font = _font(max(9, int(cell * 0.55)))

    grid = grids[0] if grids else twin.chart_grid()
    colors = grids[1] if grids else twin.color_grid()
    # The colour cue only exists where colour carries information. A single-colour chart
    # marked "A" in every square would be noise presented as accessibility.
    multicolour = len({c for row in colors for c in row if c}) > 1
    cues = color_letters(cir) if multicolour else {}
    cue_font = _font(max(6, int(cell * 0.46)))
    if cues and cell < CUE_MIN_CELL_PX:
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
                       caption: str | None = None, plain: bool = False) -> Image.Image:
    """Concentric chart for a piece worked in the round: round 1 at the centre, outward.

    The grid chart is wrong here in two ways at once, and both of them mislead a maker rather
    than merely looking odd. A disc worked from six stitches to sixty draws as a ragged
    left-aligned staircase, which is not the shape of the thing; and the footer telling them
    that odd rows read right to left is flat-fabric advice, when every round is worked in the
    same direction.

    So the rounds are drawn as rings of wedges, one wedge per stitch, in the colour that
    round is worked in, with the increases and decreases marked where they fall. A maker can
    count the wedges in a ring and compare them with the stitch count in the written line.
    """
    spec = spec or ChartSpec()
    rows = sorted({c.row for c in twin.cells})
    if not rows:
        raise ValueError("cannot render a chart for a twin with no cells")

    cells_by_round: dict[int, list] = {
        r: sorted((c for c in twin.cells if c.row == r), key=lambda c: c.position)
        for r in rows
    }
    ring_px = max(10, min(spec.cell_px, (spec.max_width_px // 2 - spec.margin_px)
                          // max(1, len(rows) + 1)))
    hub = ring_px                      # a small blank centre so round 1 reads as a ring
    outer = hub + len(rows) * ring_px
    size = int(outer * 2 + spec.margin_px * 2)

    label_font = _font(max(10, int(ring_px * 0.6)))
    glyph_font = _font(max(7, int(ring_px * 0.55)))
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
    round_colors = {r: (next(iter(cs)) if len(cs) == 1 else None)
                    for r, cs in per_round.items()}
    multicolour = len({c for cs in per_round.values() for c in cs}) > 1
    mixed_round = any(len(cs) > 1 for cs in per_round.values())
    cues = color_letters(cir) if multicolour else {}
    if cues and not plain and (ring_px < CUE_MIN_CELL_PX or mixed_round):
        global COLOR_CUE_MISSING
        COLOR_CUE_MISSING = True

    title = caption or f"{cir.title} - {twin.component}"
    footer = ("Round 1 is the centre. Every round is worked in the same direction; "
              "V marks an increase, A a decrease.")
    if multicolour:
        footer += " The letter after a round number is its yarn, as in the colour key."
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    # The footer wraps rather than stretching the canvas. Widening it to fit one long line
    # is what a longer footer used to do, and it turns a disc chart into a 2:1 rectangle
    # that is mostly empty cream with a small circle in the middle -- which is exactly the
    # shape the round renderer exists to stop producing. Height is cheap; aspect is not.
    text_px = max(size - spec.margin_px, 200)
    footer_lines = _wrap(probe, footer, label_font, text_px)
    title_lines = _wrap(probe, title, label_font, text_px)
    line_h = int(getattr(label_font, "size", 14) * 1.35)
    head = spec.margin_px + max(0, len(title_lines) - 1) * line_h
    foot = max(0, len(footer_lines) - 1) * line_h
    # The title is a product title -- up to 140 characters -- so it wraps for the same
    # reason the footer does. Sized to the widest line that survived wrapping, which is at
    # most the disc's own width, so the canvas stays disc-shaped.
    width = int(max(size, max(probe.textlength(t, font=label_font) for t in title_lines)
                    + spec.margin_px))
    img = Image.new("RGB", (width, head + size + foot), CREAM)
    # The canvas can still be a little wider than the disc, so the drawing centre is not
    # the canvas centre in both axes: the circle stays centred on the rings, not the text.
    cx, cy = width / 2.0, head + size / 2.0 - spec.margin_px / 2.0
    d = ImageDraw.Draw(img)

    # Outermost ring first. Each ring is drawn as a full pie and then has its centre filled
    # back in, so a ring drawn later must be *inside* the one before it -- going inward-out
    # would erase everything already drawn.
    for depth, r_index in reversed(list(enumerate(rows))):
        inner = hub + depth * ring_px
        edge = inner + ring_px
        cells = cells_by_round[r_index]
        step = 360.0 / len(cells)
        for position, cell in enumerate(cells):
            start = -90.0 + position * step
            bg = _hex_to_rgb(cir.colors.get(cell.color))
            # A wedge is the ring band between two radii; drawing the outer pie and then the
            # inner one in the background colour is the cheap, dependency-free way to get it.
            d.pieslice([cx - edge, cy - edge, cx + edge, cy + edge],
                       start=start, end=start + step, fill=bg, outline=LINE)
        d.ellipse([cx - inner, cy - inner, cx + inner, cy + inner],
                  fill=CREAM, outline=LINE)

        # Mark the shaping where it falls, which is the only thing a round chart really has
        # to show: six stacked marks are a hexagon, six that drift are a circle.
        if ring_px >= 12 and not plain:
            import math as _math
            for position, cell in enumerate(cells):
                if cell.stitch not in ("inc", "dec", "dc_inc", "dc_dec"):
                    continue
                angle = _math.radians(-90.0 + (position + 0.5) * step)
                radius = inner + ring_px * 0.5
                d.text((cx + radius * _math.cos(angle),
                        cy + radius * _math.sin(angle)),
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
        cue = cues.get(round_colors.get(r_index) or "")
        label = f"{r_index}{cue}" if cue and ring_px >= CUE_MIN_CELL_PX else str(r_index)
        half = probe.textlength(label, font=label_font) / 2 + 2
        d.rectangle([cx - half, y - ring_px * 0.4, cx + half, y + ring_px * 0.4],
                    fill=CREAM)
        d.text((cx, y), label, font=label_font, fill=MUTED, anchor="mm")

    for i, line in enumerate(title_lines):
        d.text((width / 2, spec.margin_px / 2 + i * line_h), line, font=label_font,
               fill=PINE, anchor="mm")
    for i, line in enumerate(footer_lines):
        d.text((width / 2, head + size - spec.margin_px / 2 + i * line_h), line,
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
    head, body = _font(17), _font(15)

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
        d.text((24, y + 6), "Each square on the chart carries its yarn's letter, so the "
                            "chart can be read without relying on colour.",
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
