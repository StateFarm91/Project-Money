"""Construction diagrams: the piece as it stands after a given round, drawn from the twin.

The best pattern documents put a picture of the work-in-progress beside the rows it
illustrates, so a maker can hold their piece up against the page and see whether it matches.
Those pictures are usually photographs of a sample. This company has no sample of anything
yet, and a generated "progress photo" would be a model guessing what the rows make -- the
failure the Execution Directive forbids for pattern text and B-691 forbids for imagery.

So these are drawn, not photographed, and drawn by the same code that draws the disclosed
listing renders (`visual.disclosed_render`): every tile is a cell of the compiled twin, in
its row's colour, on the twin's certified ring radii, at one fixed scale across every stage
so the piece visibly grows (the
earliest rounds magnified up to `ZOOM_LIMIT` times so a six-stitch ring is readable). The only thing added is a rose outline round the newest round,
which is an annotation, not fabric. Nothing here invents a stitch, a radius or a colour.

The PDF labels every one of these as a construction diagram drawn from the pattern's stitch
data, not a photograph, because that is what it is.

Two geometries are drawn. Single-piece work in joined or spiral rounds uses the disclosed
renderer's own geometry (plan view of a disc, oblique view of a vessel). Flat row-worked
pieces (blankets, panels, scarves, wraps: every component `flat_rows`) get a ROW-PROGRESS
diagram (BATCH19D): the piece drawn to one scale at its finished width x height from the
twin (`width_cm`, `row_widths`, `row_top_cm`), every worked row's cells in their own colour
and fabric position, the rows still to work as a faint outline, a rose outline round the
newest row, row markers down the left, and the word DIAGRAM on the picture itself. A flat
piece's diagram describes the twin's component (the first); the layouts place it only in
that component's block. Amigurumi pieces keep their component diagrams
(`publish.pdf_template.component_profile`, ENG-PDF-DIAGRAMS): those are one silhouette per
piece, and a pattern with any piece in rounds gets no row-progress diagram, so the two never
draw the same piece twice. Anything else gets no stage diagrams rather than an
approximation.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

# Paper and annotation colours from the brand identity (brand.identity_system.ROLES), so the
# diagram sits on the page rather than in a box of another colour.
PAPER = (243, 238, 231)        # identity "paper" #F3EEE7
HIGHLIGHT = (142, 90, 89)      # identity "rose_deep" #8E5A59
SUPERSAMPLE = 2
SIZE_PX = 640                  # delivered square; drawn at SIZE_PX * SUPERSAMPLE

# How many diagrams a run of rounds may get before it is thinned to evenly spaced stages.
MAX_BASE_STAGES = 8
MAX_WALL_STAGES = 6
# How much larger than the finished scale an early round may be drawn.
ZOOM_LIMIT = 2.5
# How many row-progress diagrams a flat piece gets (evenly spaced, always ending on the last).
MAX_FLAT_STAGES = 6
INK = (52, 46, 42)
FAINT = (205, 196, 184)
FLAT_LABEL = "DIAGRAM"


@dataclass(frozen=True)
class Stage:
    round: int                 # the last round this diagram includes
    first: int                 # the first round of the instruction group it sits beside
    stitches: int              # that round's stitch count, read off the twin
    part: str                  # "base" / "wall" / "disc" / "flat"
    png: bytes

    def image(self):
        return Image.open(io.BytesIO(self.png))


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=9)
    return buf.getvalue()


def _thin(indices: list[int], limit: int) -> list[int]:
    """At most `limit` evenly spaced members of `indices`, always ending on the last."""
    if len(indices) <= limit:
        return list(indices)
    step = math.ceil(len(indices) / limit)
    picked = indices[step - 1::step]
    if picked[-1] != indices[-1]:
        picked.append(indices[-1])
    return picked


def _geometry(cir):
    """The disclosed renderer's own reading of the piece, or None if it cannot draw one."""
    from ..visual import disclosed_render as D

    if len(cir.components) != 1 or cir.gauge is None:
        return None
    if cir.components[0].construction not in ("joined_rounds", "spiral_rounds"):
        return None
    try:
        result, twin, palette = D._compiled(cir)
        sides = D._corners(result, cir)
        if sides is None:
            return None
        rings, rows, base, wall = D._rounds(cir, twin, sides)
    except D.RenderRefused:
        return None
    return result, twin, palette, sides, rings, rows, base, wall


def _flat_geometry(cir):
    """(twin, rows, palette) for a flat row-worked piece, or None if it is not one or the twin
    cannot state its finished width and height. `rows` maps row index to its cells, in fabric
    order."""
    if not cir.components or cir.gauge is None:
        return None
    if any(c.construction != "flat_rows" for c in cir.components):
        return None
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..visual import disclosed_render as D

    result = compile_cir(cir)
    if not result.ok:
        return None
    twin = build_twin(cir, result, component=cir.components[0].name)
    if not twin.width_cm or not twin.height_cm or not twin.row_top_cm or not twin.cells:
        return None
    rows: dict[int, list] = {}
    for c in twin.cells:
        rows.setdefault(c.row, []).append(c)
    if set(rows) - set(twin.row_top_cm):
        return None
    for r in rows.values():
        r.sort(key=lambda c: c.fabric_position)
    palette = D._palette(cir)
    if any(c.color is not None and c.color not in palette for c in twin.cells):
        return None      # a colour the CIR does not define cannot be drawn
    return twin, rows, palette


def flat_caption(st: "Stage", cir) -> str:
    """What a flat stage diagram shows, in words, from the same twin numbers it is drawn
    from."""
    fg = _flat_geometry(cir)
    twin = fg[0]
    return (f"DIAGRAM after row {st.round}: {st.stitches} stitches, "
            f"{twin.row_top_cm[st.round]:.1f} of {twin.height_cm:.1f} cm worked, "
            f"{twin.width_cm:.1f} cm wide at finished size. Drawn from this pattern's stitch "
            f"data, not a photograph.")


def _font(size: int):
    from PIL import ImageFont

    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _flat_stages(cir) -> list["Stage"]:
    """Row-progress diagrams of a flat piece: width x rows at its finished dimensions, on one
    scale for every stage, row 1 at the bottom (the order it is worked)."""
    twin, rows, palette = _flat_geometry(cir)
    picked = _thin(sorted(rows), MAX_FLAT_STAGES)
    S = SIZE_PX * SUPERSAMPLE
    left, right, top, bottom = 0.17 * S, 0.05 * S, 0.12 * S, 0.12 * S
    W, H = twin.width_cm, twin.height_cm
    px = min((S - left - right) / W, (S - top - bottom) / H)
    widest = max(len(r) for r in rows.values())
    x0 = left + ((S - left - right) - W * px) / 2
    base = S - bottom - ((S - top - bottom) - H * px) / 2      # the foundation edge
    cx = x0 + W * px / 2
    order = sorted(rows)
    below = {k: (twin.row_top_cm[order[i - 1]] if i else 0.0) for i, k in enumerate(order)}
    f_big, f_small = _font(15 * SUPERSAMPLE), _font(11 * SUPERSAMPLE)

    def span(k):
        w = W * px * len(rows[k]) / widest
        y1, y2 = base - twin.row_top_cm[k] * px, base - below[k] * px
        return cx - w / 2, y1, cx + w / 2, y2

    out: list[Stage] = []
    first = order[0]
    marked: list[int] = []
    for k in picked:
        img = Image.new("RGB", (S, S), PAPER)
        d = ImageDraw.Draw(img)
        # the finished piece, faint: the rows still to work
        for r in order:
            a, y1, b, y2 = span(r)
            d.rectangle((a, y1, b, y2), fill=FAINT)
        # every worked row, cell by cell, in its own colour and fabric position
        for r in order:
            if r > k:
                break
            a, y1, b, y2 = span(r)
            cw = (b - a) / len(rows[r])
            for i, c in enumerate(rows[r]):
                rgb = palette.get(c.color, INK) if c.color is not None else INK
                d.rectangle((a + i * cw, y1, a + (i + 1) * cw, y2), fill=rgb)
        a, y1, b, y2 = span(k)
        d.rectangle((a, y1, b, y2), outline=HIGHLIGHT, width=3 * SUPERSAMPLE)
        # row markers: row 1, every earlier stage and this one
        marked = sorted(set([order[0]] + [s.round for s in out] + [k]))
        last_y = None
        for m in reversed(marked):
            ma, my1, _mb, _my2 = span(m)
            y = my1
            if last_y is not None and abs(y - last_y) < 14 * SUPERSAMPLE:
                continue
            last_y = y
            d.line((x0 - 10 * SUPERSAMPLE, y, x0 - 2 * SUPERSAMPLE, y), fill=INK,
                   width=SUPERSAMPLE)
            d.text((x0 - 12 * SUPERSAMPLE, y), f"R{m}", fill=HIGHLIGHT if m == k else INK,
                   font=f_small, anchor="rm")
        # dimension line: finished width under the piece
        yb = base + 14 * SUPERSAMPLE
        d.line((x0, yb, x0 + W * px, yb), fill=INK, width=SUPERSAMPLE)
        for x in (x0, x0 + W * px):
            d.line((x, yb - 5 * SUPERSAMPLE, x, yb + 5 * SUPERSAMPLE), fill=INK,
                   width=SUPERSAMPLE)
        d.text((cx, yb + 14 * SUPERSAMPLE), f"{W:.1f} cm", fill=INK, font=f_small,
               anchor="mm")
        d.text((S / 2, top / 2), f"{FLAT_LABEL}: after row {k} of {order[-1]}",
               fill=INK, font=f_big, anchor="mm")
        d.text((S - right, base - H * px - 8 * SUPERSAMPLE),
               f"{twin.row_top_cm[k]:.1f} / {H:.1f} cm", fill=HIGHLIGHT, font=f_small,
               anchor="rb")
        img = img.resize((SIZE_PX, SIZE_PX), Image.LANCZOS)
        out.append(Stage(round=k, first=first, stitches=len(rows[k]), part="flat",
                         png=_png(img)))
        first = k + 1
    return out


def stage_rounds(cir) -> list[int]:
    """Which rounds get a diagram: every base round of a small disc, the evenly spaced
    milestones of a large one, and every colour boundary up a wall. A flat row-worked piece
    gets `MAX_FLAT_STAGES` evenly spaced rows, ending on its last."""
    fg = _flat_geometry(cir)
    if fg is not None:
        return _thin(sorted(fg[1]), MAX_FLAT_STAGES)
    g = _geometry(cir)
    if g is None:
        return []
    _result, _twin, _palette, _sides, _rings, rows, base, wall = g
    picked = _thin([r.index for r in base], MAX_BASE_STAGES if not wall else 5)
    if wall:
        idx = [r.index for r in wall]
        boundary = [i for n, i in enumerate(idx)
                    if n == len(idx) - 1 or rows[idx[n + 1]][0].color != rows[i][0].color]
        picked += _thin(boundary, MAX_WALL_STAGES)
    return picked


def stages(cir) -> list[Stage]:
    """One diagram per stage round, each showing the piece after that round."""
    if _flat_geometry(cir) is not None:
        return _flat_stages(cir)
    g = _geometry(cir)
    if g is None:
        return []
    from ..visual import disclosed_render as D
    from ..visual import render_contract as K

    result, twin, palette, sides, rings, rows, base, wall = g
    picked = stage_rounds(cir)
    S = SIZE_PX * SUPERSAMPLE
    pad = 0.06 * S

    R = (base or rings)[-1].radius_cm
    xs = [D._path_point(R, k / 360, sides)[0] for k in range(360)]
    ys = [D._path_point(R, k / 360, sides)[1] for k in range(360)]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    plan_px = min((S - 2 * pad) / span_x, (S - 2 * pad) / span_y)

    if wall:
        levels = D._wall_levels(cir, result, wall)
        alpha = math.radians(K.camera_deg("angle"))
        ca, sa = math.cos(alpha), math.sin(alpha)
        height_cm = levels[-1] * ca + span_y * sa
        wall_px = min((S - 2 * pad) / span_x, (S - 2 * pad) / height_cm)
        low = S / 2 + height_cm * wall_px / 2
        ground = low - (-min(ys)) * sa * wall_px

    out: list[Stage] = []
    first = 1
    wall_index = {r.index: n for n, r in enumerate(wall)}
    for k in picked:
        img = Image.new("RGB", (S, S), PAPER)
        d = ImageDraw.Draw(img)
        if k in wall_index:
            j = wall_index[k] + 1
            D._draw_vessel(d, cir, twin, palette, sides, cx=S / 2, ground=ground,
                           px=wall_px, alpha=alpha, base=base, wall=wall[:j], rows=rows,
                           levels=levels[:j], wall_top_cm=levels[-1])
            top = [D._project(x, y, levels[j - 1], cx=S / 2, cy=ground, px=wall_px,
                              alpha=alpha)
                   for x, y in D.wall_outline(cir, R, sides, levels[j - 1], levels[-1])]
            d.line(top + [top[0]], fill=HIGHLIGHT, width=4 * SUPERSAMPLE)
            part = "wall"
        else:
            shown = [r for r in (base or rings) if r.index <= k]
            # The early rounds are drawn larger than the finished piece's scale (up to
            # ZOOM_LIMIT times), so a six-stitch ring is still a readable picture. The
            # geometry is unchanged; only the magnification differs, and the PDF says so.
            px = plan_px * min(R / shown[-1].radius_cm, ZOOM_LIMIT)
            D._draw_plan(d, cir, twin, palette, sides, cx=S / 2, cy=S / 2, px=px,
                         rings=shown, rows=rows)
            edge = [(S / 2 + x * px, S / 2 - y * px)
                    for x, y in D._path(shown[-1].radius_cm, 0.0, 1.0, sides)]
            d.line(edge + [edge[0]], fill=HIGHLIGHT, width=4 * SUPERSAMPLE)
            part = "base" if wall else "disc"
        img = img.resize((SIZE_PX, SIZE_PX), Image.LANCZOS)
        out.append(Stage(round=k, first=first, stitches=len(rows[k]), part=part,
                         png=_png(img)))
        first = k + 1
    return out


def schematic_view(cir):
    """The finished piece with its dimension lines -- the disclosed renderer's scale view.

    Returned as a PIL image, or None where the disclosed renderer refuses the piece. The
    frame letters its own measurements and its own disclosure, both verified against the CIR
    by `visual.render_verification`; the PDF adds nothing to the picture.
    """
    from ..visual import disclosed_render as D

    try:
        return Image.open(io.BytesIO(D.render(cir, "scale").png))
    except D.RenderRefused:
        return None
