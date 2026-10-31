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

Only single-piece work in joined or spiral rounds is drawn today: that is what the disclosed
renderer's geometry covers (plan view of a disc, oblique view of a vessel). Anything else gets
no stage diagrams rather than an approximation.
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


@dataclass(frozen=True)
class Stage:
    round: int                 # the last round this diagram includes
    first: int                 # the first round of the instruction group it sits beside
    stitches: int              # that round's stitch count, read off the twin
    part: str                  # "base" / "wall" / "disc"
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


def stage_rounds(cir) -> list[int]:
    """Which rounds get a diagram: every base round of a small disc, the evenly spaced
    milestones of a large one, and every colour boundary up a wall."""
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
