"""Raster rendering of certified fabric: stitches drawn as yarn, not as diagram.

The swatch renderer in `fabric.py` answers "is the structure ours" and looks like a chart,
which is correct for what it is and hopeless as a photograph. This one answers the harder
question: can a deterministic drawing of the certified fabric read as real crocheted yarn?

Everything here is still derived from the compiled twin -- one glyph per counted stitch, its
loop target deciding where the unworked loop sits -- so nothing is invented. What is added is
the physical appearance of yarn rather than the topology of it:

  * a stitch is a **shape**, not a cell. A half double has two legs and a top bar, and the
    bar is the loop another row works into. Drawing the bar where the loop target puts it is
    what makes back-loop and front-loop fabric look different rather than merely be different.
  * **relief**. Yarn is round, so it catches light along its top and shades underneath. A
    flat fill of the right colour looks like paper; the same colour with a highlight and a
    shadow looks like a strand.
  * **irregularity**. Hand crochet is not a lattice: tension varies, stitches lean, the
    fabric breathes. Perfectly regular spacing is one of the strongest tells that an image
    was generated rather than photographed, which is why `not_sterile_perfection` is a
    realism check. The jitter here is seeded, so it is irregular and reproducible at once --
    the same CIR renders the same fabric every time.
  * **fibre**. Worsted acrylic has a faint halo. A hard edge reads as plastic.

None of this touches the structure. Every property that `product_lock` compares is decided by
the twin before this module runs; appearance is the only thing being added.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

# One stitch, in pixels. Below about 18 there is no room to draw a bar and two legs, and the
# fabric collapses back into the coloured-cell look this module exists to escape.
MIN_PX_PER_STITCH = 18


def _shade(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


def fabric_raster(twin, gauge, *, px_per_stitch: int = 26,
                  yarn_rgb: tuple[int, int, int] = (201, 139, 155),
                  max_rows: int | None = None, max_cols: int | None = None,
                  seed: int = 0, fibre: bool = True) -> Image.Image:
    """Draw the compiled fabric as yarn. Deterministic for a given twin and seed."""
    if px_per_stitch < MIN_PX_PER_STITCH:
        raise ValueError(f"{px_per_stitch}px per stitch cannot show a stitch's shape; "
                         f"below {MIN_PX_PER_STITCH} this is a chart, not a fabric")

    # A stitch is wider than it is tall in most crochet, and that ratio is certified geometry.
    aspect = (10.0 / gauge.stitches_per_10cm) / (10.0 / gauge.rows_per_10cm)
    cw = px_per_stitch
    ch = max(MIN_PX_PER_STITCH, int(round(px_per_stitch / aspect)))

    rows = sorted({c.row for c in twin.cells})
    if max_rows:
        rows = rows[:max_rows]
    by_row = {r: sorted((c for c in twin.cells if c.row == r),
                        key=lambda c: getattr(c, "fabric_position", c.position))
              for r in rows}
    ncols = max((len(v) for v in by_row.values()), default=0)
    if max_cols:
        ncols = min(ncols, max_cols)

    # Rows overlap. This is the difference between fabric and netting: a row of half
    # doubles seats INTO the row below, so the vertical pitch is smaller than a stitch is
    # tall and the fabric closes up. Drawn at full pitch it reads as an open mesh, which was
    # the first thing wrong with this renderer -- the structure was right and the density
    # was not, and density is most of what makes crochet look like crochet.
    pitch = int(round(ch * 0.62))
    w, h = ncols * cw, len(rows) * pitch + ch
    # The gap between strands shows the shadowed inside of the fabric, not the page.
    img = Image.new("RGB", (w, h), _shade(yarn_rgb, 0.55))
    d = ImageDraw.Draw(img)
    rng = random.Random(seed)

    hi, lo = _shade(yarn_rgb, 1.22), _shade(yarn_rgb, 0.62)
    mid = yarn_rgb

    for ri, r in enumerate(rows):
        for c in by_row[r][:ncols]:
            col = getattr(c, "fabric_position", c.position)
            if col >= ncols:
                continue
            # Tension varies stitch to stitch. Small, seeded, and the difference between
            # fabric and graph paper.
            jx = rng.uniform(-cw * 0.06, cw * 0.06)
            jy = rng.uniform(-ch * 0.05, ch * 0.05)
            lean = rng.uniform(-cw * 0.05, cw * 0.05)
            x0, y0 = col * cw + jx, ri * pitch + jy
            tone = rng.uniform(0.94, 1.06)          # yarn is not one flat colour
            body = _shade(mid, tone)

            _stitch(d, x0, y0, cw, ch, lean, body, hi, lo,
                    loop=getattr(c, "loop", "both"), rng=rng)

    if fibre:
        # A faint halo: worsted acrylic is fuzzy, and a hard edge reads as plastic.
        img = img.filter(ImageFilter.GaussianBlur(radius=max(0.6, px_per_stitch / 34.0)))
        img = Image.blend(img, img.filter(ImageFilter.SMOOTH_MORE), 0.35)
    return img


def _stitch(d: ImageDraw.ImageDraw, x: float, y: float, w: float, h: float, lean: float,
            body, hi, lo, *, loop: str, rng) -> None:
    """One half-double-ish stitch: two legs, a top bar, drawn with relief.

    The bar is the pair of loops the next row works into. Which of them is left unworked is
    what a loop target means, so a back-loop stitch shows its front loop lying on the surface
    and a front-loop stitch shows the back one -- the mechanism behind every textured pattern
    and the thing a flat cell cannot express.
    """
    pad = w * 0.01
    left, right = x + pad, x + w - pad
    top, bottom = y + pad * 0.6, y + h - pad * 0.6

    # The post: two legs leaning together, drawn thick so they read as strands.
    lw = max(3, int(w * 0.52))
    d.line([(left + lean, bottom), (left + lean * 0.3, top + h * 0.34)], fill=body, width=lw)
    d.line([(right + lean, bottom), (right + lean * 0.3, top + h * 0.34)], fill=body, width=lw)
    # Highlight along the top of each leg, shadow beneath: yarn is round.
    d.line([(left + lean, bottom - h * 0.06), (left + lean * 0.3, top + h * 0.38)],
           fill=hi, width=max(1, lw // 3))
    d.line([(right + lean * 0.3, top + h * 0.40), (right + lean, bottom - h * 0.02)],
           fill=lo, width=max(1, lw // 3))

    # The top bar -- two loops, one in front of the other.
    bar_h = max(3, int(h * 0.30))
    by = top + h * 0.10
    front = (left - w * 0.02, by, right + w * 0.02, by + bar_h)
    back = (left - w * 0.02, by - bar_h * 0.55, right + w * 0.02, by + bar_h * 0.45)

    if loop == "back":
        # Worked through the back loop: the FRONT loop is left lying on the surface.
        d.rounded_rectangle(back, radius=bar_h // 2, fill=_shade(body, 0.86))
        d.rounded_rectangle(front, radius=bar_h // 2, fill=body)
        d.line([(front[0], front[1] + 1), (front[2], front[1] + 1)], fill=hi,
               width=max(1, bar_h // 3))
    elif loop == "front":
        d.rounded_rectangle(front, radius=bar_h // 2, fill=_shade(body, 0.86))
        d.rounded_rectangle(back, radius=bar_h // 2, fill=body)
        d.line([(back[0], back[1] + 1), (back[2], back[1] + 1)], fill=hi,
               width=max(1, bar_h // 3))
    else:
        d.rounded_rectangle(back, radius=bar_h // 2, fill=_shade(body, 0.92))
        d.rounded_rectangle(front, radius=bar_h // 2, fill=body)
        d.line([(front[0], front[1] + 1), (front[2], front[1] + 1)], fill=_shade(hi, 0.96),
               width=max(1, bar_h // 4))

    # The hole at the stitch's centre, where the hook went through.
    hx, hy = (left + right) / 2 + lean * 0.5, bottom - h * 0.22
    rad = max(1.0, w * 0.055)
    d.ellipse([hx - rad, hy - rad * 0.8, hx + rad, hy + rad * 0.8], fill=_shade(body, 0.55))


# ---------------------------------------------------------------------------
# Per-pixel lighting from a height field.
#
# The glyph renderer above draws yarn as flat shapes with a highlight line, and the result
# reads as a woven plastic mesh rather than as wool -- correct in structure, wrong in every
# respect that makes a photograph look like one. The diagnosis is not a parameter: filled
# vector shapes have hard edges and uniform interiors, and photographed yarn has neither. A
# strand is round, so its brightness varies continuously across its width; it is spun from
# fibres, so its edge is a halo rather than a boundary.
#
# The fix is the standard one for fabric, and it is much smaller than a 3D engine: describe
# the fabric as a HEIGHT FIELD -- how far each point stands proud of the surface -- then light
# that field per pixel. Where the surface tilts towards the light it brightens; where it
# turns away it falls into shadow. Roundness, occlusion between crossing strands and the soft
# shading in the gaps all come out of the same arithmetic, because they are all consequences
# of shape under light rather than effects to be drawn separately.
#
# The height field is still derived entirely from the certified twin. Nothing here invents
# structure; it decides how the structure catches light.
# ---------------------------------------------------------------------------

from PIL import ImageChops, ImageOps  # noqa: E402


def height_field(twin, gauge, *, px_per_stitch: int = 34, max_rows: int | None = None,
                 max_cols: int | None = None, seed: int = 0) -> Image.Image:
    """A greyscale map of how far each point of the fabric stands proud of the surface.

    White is the top of a strand, black is the gap between them. Drawn with the same glyph
    geometry as the colour renderer so the two describe the same fabric.
    """
    aspect = (10.0 / gauge.stitches_per_10cm) / (10.0 / gauge.rows_per_10cm)
    cw = px_per_stitch
    ch = max(MIN_PX_PER_STITCH, int(round(px_per_stitch / aspect)))
    pitch = int(round(ch * 0.62))

    rows = sorted({c.row for c in twin.cells})
    if max_rows:
        rows = rows[:max_rows]
    by_row = {r: sorted((c for c in twin.cells if c.row == r),
                        key=lambda c: getattr(c, "fabric_position", c.position))
              for r in rows}
    ncols = max((len(v) for v in by_row.values()), default=0)
    if max_cols:
        ncols = min(ncols, max_cols)

    img = Image.new("L", (ncols * cw, len(rows) * pitch + ch), 26)
    d = ImageDraw.Draw(img)
    rng = random.Random(seed)

    for ri, r in enumerate(rows):
        for c in by_row[r][:ncols]:
            col = getattr(c, "fabric_position", c.position)
            if col >= ncols:
                continue
            jx = rng.uniform(-cw * 0.05, cw * 0.05)
            jy = rng.uniform(-ch * 0.04, ch * 0.04)
            lean = rng.uniform(-cw * 0.05, cw * 0.05)
            x, y = col * cw + jx, ri * pitch + jy
            loop = getattr(c, "loop", "both")

            pad = cw * 0.01
            left, right = x + pad, x + cw - pad
            top, bottom = y + ch * 0.06, y + ch - ch * 0.06
            lw = max(3, int(cw * 0.52))

            # Posts stand proud; drawn as several passes of decreasing width and increasing
            # brightness, which is a cheap way to say "round" without per-pixel maths.
            for k, (shrink, level) in enumerate(((1.0, 150), (0.62, 200), (0.30, 242))):
                width = max(1, int(lw * shrink))
                d.line([(left + lean, bottom), (left + lean * 0.3, top + ch * 0.34)],
                       fill=level, width=width)
                d.line([(right + lean, bottom), (right + lean * 0.3, top + ch * 0.34)],
                       fill=level, width=width)

            bar_h = max(3, int(ch * 0.30))
            by = top + ch * 0.10
            front = (left - cw * 0.02, by, right + cw * 0.02, by + bar_h)
            back = (left - cw * 0.02, by - bar_h * 0.55, right + cw * 0.02, by + bar_h * 0.45)
            # The unworked loop sits ON TOP, which is exactly why loop targeting is visible
            # at all: it is the highest thing on the surface and catches the most light.
            lower, upper = (back, front) if loop == "back" else (
                (front, back) if loop == "front" else (back, front))
            d.rounded_rectangle(lower, radius=bar_h // 2, fill=170)
            for shrink, level in ((1.0, 205), (0.55, 250)):
                box = _inset(upper, (1 - shrink) * bar_h * 0.5)
                d.rounded_rectangle(box, radius=max(1, int(bar_h * shrink) // 2), fill=level)

            hx = (left + right) / 2 + lean * 0.5
            hy = bottom - ch * 0.22
            rad = max(1.0, cw * 0.055)
            d.ellipse([hx - rad, hy - rad * 0.8, hx + rad, hy + rad * 0.8], fill=12)

    # Yarn is spun, not moulded: soften the field so no edge is a cliff.
    return img.filter(ImageFilter.GaussianBlur(radius=max(1.0, px_per_stitch / 22.0)))


def _inset(box, by):
    x0, y0, x1, y1 = box
    return (x0 + by, y0 + by, x1 - by, y1 - by)


# `light()` and `lit_fabric()` lived here and have been removed rather than shipped.
#
# They lit the height field per pixel by estimating slope from offset differences, and the
# implementation was wrong: the output came out far too dark and the autocontrast crushed the
# colour out of it. It is not kept as a broken helper, because a function that is present and
# does not work is worse than an absent one -- somebody calls it, sees output, and does not
# know the output is meaningless.
#
# It is also not worth fixing at present, and that is the more important finding. The
# dominant failure in all three attempts was not the lighting: it was that the fabric is a
# lattice of identical glyphs, and no lighting model stops a lattice reading as a lattice.
# What real crocheted fabric has and this does not is continuous tone across round strands,
# a fibre halo instead of an edge, ply twist, contact shadow where strands cross, and --
# probably most telling -- tension that drifts across the whole panel rather than jittering
# per stitch. Hand fabric breathes at the scale of the piece; local noise on a perfect grid
# reads as a textured grid.
#
# Doing this properly means per-pixel normal-mapped or physically based rendering, which is a
# different class of work from filled vector shapes and wants numpy, which this environment
# does not have. That is an owner decision about the next increment rather than something to
# improvise here.
