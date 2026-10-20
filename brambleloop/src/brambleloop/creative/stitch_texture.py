"""A deterministic close-up of what the crochet fabric looks like, drawn from the stitch definitions.

The owner's first FLUX 3 test (reading-nook-cable-wrap) conditioned on a symbolic chart, a grid
of letters, and the model drew knitted rope cables (`failure_codes.WRONG_CRAFT_TEXTURE`). A
letter grid says which stitch goes where, not what crochet looks like. This draws the structure
itself, cell by cell from the twin, using the CIR's own colours:

- every stitch's **top loops**, the sideways chain of "V"s that runs along the top of every
  crochet row and that knitting never has;
- **sc**: a short, dense body under its loops (taxonomy row height 1);
- **hdc**: a mid-height post with the horizontal bar of its yarn-over;
- **dc / tr / post stitches**: tall posts (row height from the taxonomy) with the diagonal
  wrap of the yarn-over across the middle, and the gaps between posts that make dc fabric open;
- **cables** (`cable2x2` …): a group of `consumes` posts in which the second half crosses over
  the first, with a drop shadow, so the crossing reads as raised crochet posts, not a knit rope.
  Where the CIR does not declare the crossing side (`Stitch.crossing is None`), the drawing uses
  one convention and the manifest says so: the side is UNKNOWN, not asserted.

Fabric scale follows the gauge (stitch width : row height). No randomness, no text, no model.
"""
from __future__ import annotations

from dataclasses import dataclass

STITCH_PX = 56
CLOSEUP_COLS = 18           # a close-up: an edge plus about two repeats
TALL = ("dc", "tr", "dtr", "fpdc", "bpdc", "fptr", "bptr", "dc_inc", "dc_dec")
MID = ("hdc", "hdc_inc", "hdc_inc3")
CHAIN = ("ch",)
FLAT = ("slst",)


@dataclass(frozen=True)
class TextureRegion:
    component: str
    first_row: int          # 1-based, fabric rows
    last_row: int
    first_col: int          # 0-based, fabric positions
    last_col: int
    stitches: tuple[str, ...]
    crossing_side: str      # "front" | "back" | "UNKNOWN (drawn as front by convention)" | ""


def _rgb(hexval: str | None) -> tuple[int, int, int]:
    from ..publish import charts

    return charts._hex_to_rgb(hexval) if hexval else (200, 190, 175)


def _shade(c, f: float):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def _tint(c, f: float):
    return tuple(int(v + (255 - v) * f) for v in c)


def choose_region(twin, *, max_rows: int = 16, max_cols: int = CLOSEUP_COLS
                  ) -> tuple[int, int, int, int]:
    """Rows from the bottom edge up until every stitch type in the piece is shown, plus one
    four-row cycle, and columns from the left edge: a close-up that includes a real edge (the
    layout reference shows the whole width)."""
    from ..publish import charts

    grid, colors = twin.chart_grid(), twin.color_grid()
    rows = len(grid)
    across = max((len(r) for r in grid), default=0)
    used = {s for r in grid for s in r}
    seen: set[str] = set()
    last = 0
    for i, r in enumerate(grid):
        seen |= set(r)
        last = i
        if seen >= used:
            break
    cp, rp = charts.detect_repeat(grid, colors)
    want = min(rows, max(last + 1 + 4, 8), max_rows)
    cols = min(across, max_cols)
    # Never cut a cable or other multi-stitch group in half at the right edge of the crop.
    from ..cir import stitches as taxonomy

    for r in grid[:want]:
        j = 0
        while j < len(r):
            try:
                n = max(1, taxonomy.get(r[j]).consumes) if taxonomy.get(r[j]).is_cable else 1
            except Exception:  # noqa: BLE001
                n = 1
            if j < cols < j + n:
                cols = j
                break
            j += n
    return 0, want - 1, 0, max(1, cols) - 1


def render(cir, twin, *, region: tuple[int, int, int, int] | None = None):
    """(image, TextureRegion). Bottom row at the bottom, as the fabric grows."""
    from PIL import Image, ImageDraw

    from ..cir import stitches as taxonomy

    r0, r1, c0, c1 = region or choose_region(twin)
    grid, colors = twin.chart_grid(), twin.color_grid()
    W = STITCH_PX
    g = cir.gauge
    unit_h = W * (float(g.stitches_per_10cm) / float(g.rows_per_10cm or g.stitches_per_10cm))
    if str(g.stitch_type) != "sc":
        unit_h = unit_h / max(0.25, taxonomy.get(str(g.stitch_type)).row_height or 1.0)

    def row_height(r):
        hs = []
        for code in grid[r][c0:c1 + 1]:
            try:
                hs.append(taxonomy.get(code).row_height or 1.0)
            except Exception:  # noqa: BLE001 - an unknown code draws at sc height
                hs.append(1.0)
        return max(10, int(round(max(hs or [1.0]) * unit_h)))

    heights = [row_height(r) for r in range(r0, r1 + 1)]
    width = (c1 - c0 + 1) * W
    height = sum(heights)
    ink = _rgb(next(iter(cir.colors.values()), None)) if cir.colors else (200, 190, 175)
    img = Image.new("RGB", (width, height), _shade(ink, 0.35))
    d = ImageDraw.Draw(img)
    drawn: set[str] = set()
    sides: set[str] = set()
    y_bottom = height
    for k, r in enumerate(range(r0, r1 + 1)):
        h = heights[k]
        y_top = y_bottom - h
        row = grid[r]
        crow = colors[r] if r < len(colors) else []
        base = _rgb(cir.colors.get(crow[c0]) if crow else None)
        d.rectangle((0, y_top, width, y_bottom), fill=_shade(base, 0.45))
        loop_h = max(6, int(min(h, unit_h) * 0.42))
        j = c0
        while j <= c1:
            code = row[j] if j < len(row) else ""
            col = _rgb(cir.colors.get(crow[j]) if j < len(crow) else None)
            light, mid, dark = _tint(col, 0.30), col, _shade(col, 0.55)
            x = (j - c0) * W
            st = None
            try:
                st = taxonomy.get(code)
            except Exception:  # noqa: BLE001
                st = None
            if st is not None and st.is_cable:
                n = max(1, min(st.consumes, c1 - j + 1))
                _cable(d, x, y_top, y_bottom, n, W, loop_h, light, mid, dark,
                       front_first=st.crossing != "back")
                sides.add(st.crossing or "UNKNOWN (drawn as front by convention)")
                drawn.add(code)
                j += n
                continue
            _loops(d, x, y_top, W, loop_h, light, dark)
            body_top = y_top + loop_h - 2
            if code in TALL:
                _post(d, x, body_top, y_bottom, W, mid, light, dark, bar="diagonal")
            elif code in MID:
                _post(d, x, body_top, y_bottom, W, mid, light, dark, bar="flat")
            elif code in CHAIN or code in FLAT:
                d.ellipse((x + 4, body_top, x + W - 4, y_bottom - 2), fill=mid, outline=dark)
            else:  # sc and its increases/decreases: short and dense
                d.rounded_rectangle((x + 2, body_top, x + W - 2, y_bottom - 1), radius=4,
                                    fill=mid, outline=dark)
                d.line((x + W // 2, body_top + 2, x + W // 2, y_bottom - 3), fill=dark,
                       width=2)
                for t in (0.3, 0.7):
                    d.line((x + int(W * t) - 3, y_bottom - 3, x + int(W * t) + 3,
                            body_top + 3), fill=_shade(mid, 0.85), width=1)
            if code:
                drawn.add(code)
            j += 1
        y_bottom = y_top
    region_ = TextureRegion(component=twin.component, first_row=r0 + 1, last_row=r1 + 1,
                            first_col=c0, last_col=c1, stitches=tuple(sorted(drawn)),
                            crossing_side=" / ".join(sorted(sides)))
    return img, region_


def _loops(d, x, y_top, W, loop_h, light, dark):
    """The two top loops of one stitch: one arm of the row's chain of sideways Vs."""
    d.ellipse((x + 1, y_top + 1, x + W // 2 + 3, y_top + loop_h), fill=light, outline=dark)
    d.ellipse((x + W // 2 - 3, y_top + 1, x + W - 1, y_top + loop_h), fill=light, outline=dark)


def _post(d, x, top, bottom, W, mid, light, dark, *, bar: str):
    l, r = x + int(W * 0.22), x + int(W * 0.78)
    d.rounded_rectangle((l, top, r, bottom - 1), radius=5, fill=mid, outline=dark)
    m = (top + bottom) // 2
    if bar == "diagonal":
        d.line((l - 1, m + 5, r + 1, m - 5), fill=light, width=4)
        d.line((l - 1, m + 8, r + 1, m - 2), fill=dark, width=1)
    else:
        d.line((l - 1, m, r + 1, m), fill=light, width=4)
    for t in (0.35, 0.65):
        d.line((x + int(W * t), bottom - 4, x + int(W * t) + 3, top + 4),
               fill=_shade(mid, 0.8), width=1)


def _cable(d, x, top, bottom, n, W, loop_h, light, mid, dark, *, front_first: bool):
    """`n` posts; the second half crosses over the first (or under, for a back cross)."""
    for i in range(n):
        _loops(d, x + i * W, top, W, loop_h, light, dark)
    half = n // 2 or 1
    body_top = top + loop_h - 2
    pw = int(W * 0.9)

    def post(i_from, i_to, fill, outline, shadow):
        bx = x + i_from * W + (W - pw) // 2
        tx = x + i_to * W + (W - pw) // 2
        poly = [(bx, bottom - 1), (bx + pw, bottom - 1), (tx + pw, body_top), (tx, body_top)]
        if shadow:
            d.polygon([(px + 3, py + 2) for px, py in poly], fill=_shade(mid, 0.3))
        d.polygon(poly, fill=fill, outline=outline)
        mx, my = (bx + tx) // 2 + pw // 2, (bottom + body_top) // 2
        d.line((mx - pw // 2, my + 4, mx + pw // 2, my - 4), fill=light if shadow else mid,
               width=3)

    back = [(i, i + half) for i in range(half)]                   # first half moves right
    front = [(i + half, i) for i in range(half)]                  # second half moves left
    under, over = (back, front) if front_first else (front, back)
    for a, b in under:
        post(a, b, _shade(mid, 0.8), dark, shadow=False)
    for a, b in over:
        post(a, b, _tint(mid, 0.28), dark, shadow=True)
