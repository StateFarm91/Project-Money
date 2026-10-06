"""Disclosed deterministic renders of a whole certified product (owner ruling D-FB-7).

Truthful customer-ready imagery is launch-critical; photorealism is not. This module draws
the finished object a certified CIR makes, one glyph per compiled twin cell, and nothing
else. It is not a beauty renderer and it does not pretend to be a photograph: every frame
carries the disclosure in its own pixels, and the listing carries it in copy and alt text.

What "derived 1:1" means here, concretely:

  * every stitch drawn is a cell of `cir.twin.build_twin` -- one glyph per cell, no more,
    no fewer -- and its colour is that cell's row colour from the CIR's palette;
  * flat pieces are laid out in fabric order (`Cell.fabric_position`), row 1 at the bottom,
    each stitch `10 / stitches_per_10cm` cm wide and as tall as its own stitch's row height
    (`cir.stitches` row_height against the gauge stitch), so a double crochet stands twice
    as tall as the single crochet beside it, which is what the twin's row heights say;
  * round pieces are laid out on the twin's certified ring radii (`twin.geometry.rings`).
    When the CIR stacks its increases (`cir.geometry.corners` reports n), the rounds are
    n-sided polygons with corners on those radii -- a hexagon coaster is drawn as the
    hexagon it is -- and otherwise circles. A vessel's walls rise one row height per wall
    round, so the elevation's height is the twin's axial height;
  * the scale bar is drawn in centimetres at the frame's own pixels-per-centimetre, so the
    finished size can be read off the picture rather than off a caption.

Polygon geometry (2.0.0, PT-10): the twin's rings are circles (`diameter = stitches x stitch
width / pi`), but a stacked-increase round is a polygon whose perimeter is the stitch count
times the stitch width. Rounds are drawn on that polygon -- corners at
`circumference / (2 n sin(pi/n))` -- so the drawn stitch pitch is the gauge width and the
drawn spans are the twin's across-the-points and across-the-flats figures, which is what the
scale view letters and the listing prints.

Text (2.0.0, PT-05): the only words on a frame are the disclosure, the scale bar's "N cm" and
the contract annotation lines (`render_contract.annotation_lines`), whose numbers come from
the CIR. The verifier re-draws exactly those and refuses any other text.

Output: PNG bytes plus a construction manifest. The manifest is a claim, never evidence:
`visual.render_verification` re-measures the pixels against the CIR independently and
ignores everything the manifest says about layout.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from . import render_contract as K

KIND = "disclosed_render"
RENDERER_VERSION = "disclosed-render/2.0.0"

# The views a listing set is built from, and the gallery role each plays. One job each
# (publish.eligibility.check_set refuses duplicate jobs).
VIEWS: dict[str, dict] = {
    "hero": {"role": "hero", "job": "DESIRE"},
    "scale": {"role": "scale", "job": "SCALE"},
    "detail": {"role": "detail", "job": "DETAIL"},
}


class RenderRefused(ValueError):
    """The CIR asks for something this renderer cannot draw truthfully."""


@dataclass(frozen=True)
class RenderedFrame:
    view: str
    png: bytes
    manifest: dict

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.png).hexdigest()


# --------------------------------------------------------------------------- inputs

def _palette(cir) -> dict[str, tuple[int, int, int]]:
    colours = {}
    for name, value in (cir.colors or {}).items():
        colours[name] = K.hex_rgb(value)
    return colours


def _compiled(cir):
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    if len(cir.components) != 1:
        raise RenderRefused(
            f"{cir.slug}: {len(cir.components)} components. This renderer draws one compiled "
            f"piece; assembling several into one object is a claim it cannot yet derive")
    result = compile_cir(cir)
    if not result.ok:
        raise RenderRefused(f"{cir.slug} does not compile; nothing true to render")
    twin = build_twin(cir, result, component=cir.components[0].name)
    used = {c.color for c in twin.cells}
    palette = _palette(cir)
    missing = sorted(str(c) for c in used if c not in palette)
    if missing:
        raise RenderRefused(f"{cir.slug}: colours {missing} have no RGB value in cir.colors; "
                            f"a colour the CIR does not define cannot be drawn")
    if K.separation({k: v for k, v in palette.items() if k in used}) < K.MIN_SEPARATION:
        raise RenderRefused(f"{cir.slug}: palette too close to a contract colour to measure")
    return result, twin, palette


def twin_digest(twin) -> str:
    cells = [(c.row, c.fabric_position, c.stitch, c.color, c.loop) for c in twin.cells]
    payload = {"cells": cells, "width_cm": twin.width_cm, "height_cm": twin.height_cm,
               "row_widths": sorted(twin.row_widths.items())}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def colour_map_digest(cir, twin) -> str:
    rows = sorted({(c.row, c.color) for c in twin.cells})
    payload = {"rows": rows, "palette": sorted((cir.colors or {}).items())}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _by_row(twin) -> dict[int, list]:
    rows: dict[int, list] = {}
    for c in twin.cells:
        rows.setdefault(c.row, []).append(c)
    return {r: sorted(cs, key=lambda c: c.fabric_position) for r, cs in sorted(rows.items())}


def _stitch_height_units(code: str, base: str) -> float:
    from ..cir import stitches

    b = stitches.get(base).row_height or 1.0
    return (stitches.get(code).row_height or b) / b


# --------------------------------------------------------------------------- drawing kit

def _canvas():
    img = Image.new("RGB", (K.CANVAS_PX, K.CANVAS_PX), K.BACKGROUND)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"          # no antialiasing: every pixel is exactly a contract colour
    return img, d


def _tile(d, poly, rgb, *, notch: bool = True) -> None:
    """One stitch: the yarn-coloured glyph, a gap outline, and the sc 'v' where it fits.

    `poly` runs top-left, top-right, ..., bottom-right, bottom-left: the first and last
    points are the stitch's top corners, which is where the 'v' of the stitch top opens.
    """
    pts = [(float(x), float(y)) for x, y in poly]
    d.polygon(pts, fill=rgb, outline=K.GAP, width=K.GAP_PX)
    if not notch or len(pts) < 4:
        return
    tl, tr = pts[0], pts[1]
    br, bl = pts[-2], pts[-1]
    width = math.dist(tl, tr)
    height = min(math.dist(tl, bl), math.dist(tr, br))
    if width < 20 or height < 18:
        return

    def at(u, v):
        top = (tl[0] + (tr[0] - tl[0]) * u, tl[1] + (tr[1] - tl[1]) * u)
        bot = (bl[0] + (br[0] - bl[0]) * u, bl[1] + (br[1] - bl[1]) * u)
        return (top[0] + (bot[0] - top[0]) * v, top[1] + (bot[1] - top[1]) * v)

    d.line([at(0.28, 0.16), at(0.5, 0.40), at(0.72, 0.16)], fill=K.GAP,
           width=max(1, K.GAP_PX - 1))


def _scale_bar(d, px_per_cm: float) -> dict:
    zx0, zy0, zx1, zy1 = K.zone_px(K.SCALE_ZONE)
    segments = max(3, min(30, int(round(420 / px_per_cm))))
    while segments * px_per_cm > (zx1 - zx0) * 0.6 and segments > 3:
        segments -= 1
    y0 = zy0 + 6
    y1 = y0 + K.SCALE_BAR_HEIGHT_PX
    x0 = zx0 + K.SCALE_BAR_OUTLINE_PX
    for i in range(segments):
        a = x0 + i * px_per_cm
        b = x0 + (i + 1) * px_per_cm
        if i % 2 == 0:
            d.rectangle([round(a), y0, round(b) - 1, y1], fill=K.SCALE_DARK)
    end = x0 + segments * px_per_cm
    o = K.SCALE_BAR_OUTLINE_PX
    d.rectangle([x0 - o, y0 - o, round(end) - 1 + o, y1 + o], outline=K.SCALE_DARK, width=o)
    label = K.scale_label(segments)
    d.text(K.scale_label_xy(round(end), y0), label, fill=K.CAPTION, font=K.font(K.LABEL_PX))
    return {"segments_cm": segments, "x0": x0, "y0": y0, "px_per_cm": px_per_cm}


def _caption(d, lines: list[str] | None = None) -> dict:
    """The disclosure, and the contract annotation lines (`render_contract.annotation_lines`).

    Nothing else is ever lettered on a frame: the verifier re-draws exactly these words from
    its own reading of the CIR and refuses any other text (PT-05)."""
    f = K.font(K.CAPTION_PX)
    text = K.DISCLOSURE
    w = d.textlength(text, font=f)
    x = round((K.CANVAS_PX - w) / 2)
    y = round(K.CAPTION_TOP * K.CANVAS_PX)
    d.text((x, y), text, fill=K.CAPTION, font=f)
    out = {"text": text, "x": x, "y": y}
    if lines:
        lf = K.font(K.LABEL_PX)
        widths = [d.textlength(line, font=lf) for line in lines]
        positions = K.annotation_xy(widths)
        if min(px for px, _py in positions) < K.ANNOTATION_MIN_X_FRACTION * K.CANVAS_PX:
            raise RenderRefused("annotation text is too long for the scale zone")
        for line, xy in zip(lines, positions):
            d.text(xy, line, fill=K.CAPTION, font=lf)
        out["label"] = " ".join(lines)
        out["lines"] = list(lines)
    return out


def _png(img) -> bytes:
    buf = io.BytesIO()
    # No metadata, fixed compression: the bytes are a function of the pixels alone.
    img.save(buf, format="PNG", optimize=False, compress_level=9)
    return buf.getvalue()


def _dimension_line(d, a, b, *, ticks: str) -> None:
    d.line([a, b], fill=K.LINE, width=3)
    for p in (a, b):
        if ticks == "v":
            d.line([(p[0], p[1] - 14), (p[0], p[1] + 14)], fill=K.LINE, width=3)
        else:
            d.line([(p[0] - 14, p[1]), (p[0] + 14, p[1])], fill=K.LINE, width=3)


def dimension_figures(twin) -> dict:
    """The figures a scale view letters, from the twin (`render_contract.annotation_lines`)."""
    return {"width": twin.width_cm, "height": twin.height_cm, "sides": twin.sides or 0,
            "points": twin.across_points_cm, "flats": twin.across_flats_cm,
            "across": twin.width_cm, "vessel": twin.shape not in (None, "disc")}


# --------------------------------------------------------------------------- flat pieces

def _flat_geometry(cir, twin):
    gauge = cir.gauge
    w_cm = 10.0 / gauge.stitches_per_10cm
    sc_cm = 10.0 / gauge.rows_per_10cm
    rows = _by_row(twin)
    tops = dict(twin.row_top_cm)
    return gauge, w_cm, sc_cm, rows, tops


def _draw_flat(d, cir, twin, palette, *, px: float, left: float, bottom: float,
               rows_window: tuple[int, int] | None = None,
               cols_window: tuple[int, int] | None = None) -> dict:
    gauge, w_cm, sc_cm, rows, tops = _flat_geometry(cir, twin)
    base = gauge.stitch_type
    indices = sorted(rows)
    r0, r1 = rows_window or (indices[0], indices[-1])
    c0, c1 = cols_window or (0, max(len(v) for v in rows.values()) - 1)
    shown = [r for r in indices if r0 <= r <= r1]
    floor_cm = tops.get(r0 - 1, 0.0) if r0 > indices[0] else 0.0
    ncols = c1 - c0 + 1
    width_cm = ncols * w_cm
    height_cm = tops[shown[-1]] - floor_cm
    d.rectangle([left, bottom - height_cm * px, left + width_cm * px - 1, bottom - 1],
                fill=K.GAP)
    rendered = []
    for r in shown:
        band_bottom = bottom - (tops.get(r - 1, 0.0) - floor_cm) * px if r > indices[0] \
            else bottom
        band_top = bottom - (tops[r] - floor_cm) * px
        cells = [c for c in rows[r] if c0 <= c.fabric_position <= c1]
        for c in cells:
            x0 = left + (c.fabric_position - c0) * w_cm * px
            x1 = x0 + w_cm * px
            # Every stitch fills its row: the twin carries a height per row, not per stitch,
            # and the fabric is continuous. A stitch taller than the gauge stitch (a dc in an
            # sc ground) stands above the ground, which is drawn as its raised post.
            poly = [(x0, band_top), (x1, band_top), (x1, band_bottom), (x0, band_bottom)]
            rgb = palette[c.color]
            _tile(d, poly, rgb)
            if _stitch_height_units(c.stitch, base) > 1.0 + 1e-9:
                post_w = max(2.0, (x1 - x0) * 0.36)
                mid = (x0 + x1) / 2
                inset = K.GAP_PX + max(1.0, (band_bottom - band_top) * 0.10)
                d.rectangle([round(mid - post_w / 2), round(band_top + inset),
                             round(mid + post_w / 2) - 1, round(band_bottom - inset) - 1],
                            fill=K.relief(rgb))
        rendered.append({"row": r, "count": len(cells),
                         "colour": cells[0].color if cells else None,
                         "stitches": hashlib.sha256(
                             ",".join(c.stitch for c in cells).encode()).hexdigest()[:16]})
    return {"rows": rendered, "width_cm": round(width_cm, 3), "height_cm": round(height_cm, 3),
            "window": {"rows": [r0, r1], "cols": [c0, c1]}}


def _flat_view(cir, twin, palette, view: str) -> tuple[Image.Image, dict]:
    gauge, w_cm, sc_cm, rows, tops = _flat_geometry(cir, twin)
    img, d = _canvas()
    zx0, zy0, zx1, zy1 = K.zone_px(K.PRODUCT_ZONE)
    full_w = max(len(v) for v in rows.values()) * w_cm
    full_h = tops[max(rows)]
    layout: dict
    if view == "detail":
        # A corner of the fabric at a scale where every stitch is a readable glyph: the
        # end border and the first full motif repeat, which is where a buyer looks first.
        r_last = max(r for r in rows if tops[r] <= 26.0) if any(tops[r] <= 26.0 for r in rows) \
            else min(rows)
        cols = int(min(len(rows[min(rows)]), max(6, round(30.0 / w_cm))))
        win_w, win_h = cols * w_cm, tops[r_last]
        px = min((zx1 - zx0) / win_w, (zy1 - zy0) / win_h)
        left = zx0 + ((zx1 - zx0) - win_w * px) / 2
        bottom = zy1 - ((zy1 - zy0) - win_h * px) / 2
        layout = _draw_flat(d, cir, twin, palette, px=px, left=left, bottom=bottom,
                            rows_window=(min(rows), r_last), cols_window=(0, cols - 1))
        extra = K.annotation_lines("detail", "flat", {"rows": r_last, "cols": cols})
    else:
        margin = 70 if view == "scale" else 0
        px = min((zx1 - zx0 - margin) / full_w, (zy1 - zy0 - margin) / full_h)
        left = zx0 + margin + ((zx1 - zx0 - margin) - full_w * px) / 2
        bottom = zy1 - ((zy1 - zy0 - margin) - full_h * px) / 2 - margin
        if view == "hero":
            left = zx0 + ((zx1 - zx0) - full_w * px) / 2
            bottom = zy1 - ((zy1 - zy0) - full_h * px) / 2
        layout = _draw_flat(d, cir, twin, palette, px=px, left=left, bottom=bottom)
        extra = []
        if view == "scale":
            top = bottom - full_h * px
            _dimension_line(d, (left, bottom + 40), (left + full_w * px, bottom + 40), ticks="v")
            _dimension_line(d, (left - 40, top), (left - 40, bottom), ticks="h")
            extra = K.annotation_lines("scale", "flat", dimension_figures(twin))
    layout["px_per_cm"] = px
    layout["scale_bar"] = _scale_bar(d, px)
    layout["caption"] = _caption(d, extra)
    return img, layout


# --------------------------------------------------------------------------- round pieces

def _corners(result, cir) -> int | None:
    from ..cir.geometry import corners

    name = cir.components[0].name
    return corners([r for r in result.rows if r.component == name])


def _path_point(rho: float, t: float, sides: int) -> tuple[float, float]:
    """A point at arc parameter t in [0, 1) on a polygon (or circle) of circumradius rho.

    Corners at angles 0, 360/sides, ...; t runs anticlockwise. Coordinates are (X, Y) with
    Y pointing away from the viewer in an oblique view and up in a plan view."""
    t = t % 1.0
    if sides == 0:
        a = 2 * math.pi * t
        return rho * math.cos(a), rho * math.sin(a)
    j = int(t * sides) % sides
    f = t * sides - int(t * sides)
    a0 = 2 * math.pi * j / sides
    a1 = 2 * math.pi * (j + 1) / sides
    x0, y0 = rho * math.cos(a0), rho * math.sin(a0)
    x1, y1 = rho * math.cos(a1), rho * math.sin(a1)
    return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f


def _path(rho: float, t0: float, t1: float, sides: int) -> list[tuple[float, float]]:
    pts = [_path_point(rho, t0, sides)]
    if sides == 0:
        steps = max(2, int(math.ceil((t1 - t0) * 96)))
        pts += [_path_point(rho, t0 + (t1 - t0) * k / steps, 0) for k in range(1, steps)]
    else:
        k = math.floor(t0 * sides) + 1
        while k / sides < t1 - 1e-12:
            pts.append(_path_point(rho, k / sides, sides))
            k += 1
    pts.append(_path_point(rho, t1, sides))
    return pts


def _rounds(cir, twin, sides: int = 0):
    rings = list(twin.geometry.rings) if twin.geometry else []
    if not rings:
        raise RenderRefused(f"{cir.slug}: a round piece with no certified ring geometry")
    if sides:
        # A stacked-increase round is an n-sided polygon whose PERIMETER is the stitch count
        # times the stitch width, so its corners sit at circumference / (2 n sin(pi/n)) --
        # not on the circle's radius, which drew every polygon 4.5 % under gauge (PT-10).
        from dataclasses import replace as _replace

        k = 2 * sides * math.sin(math.pi / sides)
        rings = [_replace(r, radius_cm=r.circumference_cm / k) for r in rings]
    rows = _by_row(twin)
    base, wall = [], []
    for ring in rings:
        (wall if ring.axial_cm > 0 or (wall and ring.radius_delta_cm == 0) else base).append(ring)
    return rings, rows, base, wall


def _draw_plan(d, cir, twin, palette, sides: int, *, cx: float, cy: float, px: float,
               rings, rows, mirror: bool = False) -> list[dict]:
    """Rounds seen from above (or from below, mirrored), one tile per stitch."""
    outer = rings[-1].radius_cm
    poly = [(cx + (-x if mirror else x) * px, cy - y * px)
            for x, y in _path(outer, 0.0, 1.0, sides)]
    d.polygon(poly, fill=K.GAP)
    rendered = []
    previous = 0.0
    for ring in rings:
        cells = rows[ring.index]
        n = len(cells)
        for i, c in enumerate(cells):
            t0, t1 = i / n, (i + 1) / n
            out = _path(ring.radius_cm, t0, t1, sides)
            inn = list(reversed(_path(previous, t0, t1, sides)))
            pts = [(cx + (-x if mirror else x) * px, cy - y * px) for x, y in out + inn]
            _tile(d, pts, palette[c.color])
        rendered.append({"round": ring.index, "count": n, "colour": cells[0].color,
                         "outer_radius_cm": ring.radius_cm})
        previous = ring.radius_cm
    return rendered


def _project(X, Y, Z, *, cx, cy, px, alpha):
    ca, sa = math.cos(alpha), math.sin(alpha)
    return cx + X * px, cy - (Z * ca + Y * sa) * px


def _draw_vessel(d, cir, twin, palette, sides: int, *, cx: float, ground: float, px: float,
                 alpha: float, base, wall, rows) -> list[dict]:
    """A vessel: the base disc, then walls one row height per wall round, painter's order.

    `ground` is the screen y of the base centre (Z=0, Y=0)."""
    R = base[-1].radius_cm if base else wall[0].radius_cm
    h_round = 10.0 / cir.gauge.rows_per_10cm
    proj = lambda X, Y, Z: _project(X, Y, Z, cx=cx, cy=ground, px=px, alpha=alpha)  # noqa: E731
    sa = math.sin(alpha)

    def tiles(back: bool):
        out = []
        for j, ring in enumerate(wall):
            cells = rows[ring.index]
            n = len(cells)
            z0, z1 = j * h_round, (j + 1) * h_round
            for i, c in enumerate(cells):
                t0, t1 = i / n, (i + 1) / n
                tm = (t0 + t1) / 2
                if sides:
                    face = int(tm * sides)
                    normal_angle = 2 * math.pi * (face + 0.5) / sides
                else:
                    normal_angle = 2 * math.pi * tm
                facing_back = math.sin(normal_angle) > 1e-9
                if facing_back != back:
                    continue
                path = _path(R, t0, t1, sides)
                bottom = [proj(x, y, z0) for x, y in path]
                top = [proj(x, y, z1) for x, y in path]
                # Outer surface seen from the front, inner surface of the back seen from
                # inside: left-to-right on screen, top edge first.
                if top[0][0] > top[-1][0]:
                    top, bottom = list(reversed(top)), list(reversed(bottom))
                depth = sum(y for _x, y in path) / len(path)
                out.append((depth, top + list(reversed(bottom)), palette[c.color]))
        return out

    if sa > 1e-9:
        # Inside of the back wall, farthest first, then the base's upper face.
        for _depth, pts, rgb in sorted(tiles(True), key=lambda t: -t[0]):
            _tile(d, pts, rgb)
        previous = 0.0
        for ring in base:
            cells = rows[ring.index]
            n = len(cells)
            for i, c in enumerate(cells):
                t0, t1 = i / n, (i + 1) / n
                out = [proj(x, y, 0.0) for x, y in _path(ring.radius_cm, t0, t1, sides)]
                inn = [proj(x, y, 0.0) for x, y in reversed(_path(previous, t0, t1, sides))]
                _tile(d, out + inn, palette[c.color], notch=False)
            previous = ring.radius_cm
    for _depth, pts, rgb in sorted(tiles(False), key=lambda t: -t[0]):
        _tile(d, pts, rgb)
    # The rim, so the opening reads as an opening.
    H = len(wall) * h_round
    rim = [proj(x, y, H) for x, y in _path(R, 0.0, 1.0, sides)]
    d.line(rim + [rim[0]], fill=K.GAP, width=K.GAP_PX + 1)
    return [{"round": ring.index, "count": len(rows[ring.index]),
             "colour": rows[ring.index][0].color, "part": "wall"} for ring in wall]


def _round_view(cir, result, twin, palette, view: str) -> tuple[Image.Image, dict]:
    sides = _corners(result, cir)
    if sides is None:
        raise RenderRefused(
            f"{cir.slug}: the increases neither all stack nor all stagger, so the outline "
            f"is not a named shape and drawing one would be a guess (cir.geometry.corners)")
    rings, rows, base, wall = _rounds(cir, twin, sides)
    img, d = _canvas()
    zx0, zy0, zx1, zy1 = K.zone_px(K.PRODUCT_ZONE)
    zw, zh = zx1 - zx0, zy1 - zy0
    R = (base or rings)[-1].radius_cm
    # Plan-view extents of the outline: across the corners horizontally, across the flats
    # (or the diameter) vertically.
    xs = [_path_point(R, k / 360, sides)[0] for k in range(360)]
    ys = [_path_point(R, k / 360, sides)[1] for k in range(360)]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    extra: list[str] = []
    dims = dimension_figures(twin)
    layout: dict = {"sides": sides, "objects": 1}
    if not wall:
        make = cir.components[0].make
        if view == "hero" and make > 1:
            cols = int(math.ceil(math.sqrt(make)))
            nrows = int(math.ceil(make / cols))
            gap_cm = 0.18 * span_x
            px = min(zw / (cols * span_x + (cols - 1) * gap_cm),
                     zh / (nrows * span_y + (nrows - 1) * gap_cm))
            total_w = (cols * span_x + (cols - 1) * gap_cm) * px
            total_h = (nrows * span_y + (nrows - 1) * gap_cm) * px
            centres = []
            for k in range(make):
                rr, cc = divmod(k, cols)
                centres.append((zx0 + (zw - total_w) / 2 + (cc * (span_x + gap_cm) + span_x / 2) * px,
                                zy0 + (zh - total_h) / 2 + (rr * (span_y + gap_cm) + span_y / 2) * px))
            for c_x, c_y in centres:
                rendered = _draw_plan(d, cir, twin, palette, sides, cx=c_x, cy=c_y, px=px,
                                      rings=rings, rows=rows)
            layout["objects"] = make
        else:
            margin = 80 if view == "scale" else 0
            px = min((zw - margin) / span_x, (zh - margin) / span_y)
            c_x, c_y = zx0 + zw / 2, zy0 + (zh - margin) / 2
            rendered = _draw_plan(d, cir, twin, palette, sides, cx=c_x, cy=c_y, px=px,
                                  rings=rings, rows=rows)
            if view == "scale":
                y = c_y + span_y / 2 * px + 40
                _dimension_line(d, (c_x - span_x / 2 * px, y), (c_x + span_x / 2 * px, y),
                                ticks="v")
                extra = K.annotation_lines("scale", "rounds", dims)
        layout["rounds"] = rendered
        layout["projection"] = "plan"
    else:
        h_round = 10.0 / cir.gauge.rows_per_10cm
        H = len(wall) * h_round
        if view == "detail":
            # The base, seen from above: every base round, stitch for stitch.
            px = min(zw / span_x, zh / span_y)
            rendered = _draw_plan(d, cir, twin, palette, sides, cx=zx0 + zw / 2,
                                  cy=zy0 + zh / 2, px=px, rings=base, rows=rows)
            layout.update(rounds=rendered, projection="plan", part="base")
            extra = K.annotation_lines("detail", "rounds",
                                       {"vessel": True, "base_rounds": len(base)})
        else:
            alpha = math.radians(K.OBLIQUE_DEG if view == "hero" else 0.0)
            ca, sa = math.cos(alpha), math.sin(alpha)
            margin = 80 if view == "scale" else 0
            height_cm = H * ca + span_y * sa
            px = min((zw - margin) / span_x, (zh - margin) / height_cm)
            cx = zx0 + margin / 2 + (zw - margin) / 2
            low = (zy0 + (zh - margin) / 2) + height_cm * px / 2
            ground = low - (-min(ys)) * sa * px     # front of the base sits at `low`
            rendered = _draw_vessel(d, cir, twin, palette, sides, cx=cx, ground=ground,
                                    px=px, alpha=alpha, base=base, wall=wall, rows=rows)
            layout.update(rounds=rendered, projection="oblique" if sa else "elevation",
                          alpha_deg=round(math.degrees(alpha), 3), part="wall")
            if view == "scale":
                top = low - H * px
                _dimension_line(d, (cx - span_x / 2 * px, low + 40),
                                (cx + span_x / 2 * px, low + 40), ticks="v")
                _dimension_line(d, (cx - span_x / 2 * px - 40, top),
                                (cx - span_x / 2 * px - 40, low), ticks="h")
                extra = K.annotation_lines("scale", "rounds", dims)
    layout["px_per_cm"] = px
    layout["scale_bar"] = _scale_bar(d, px)
    layout["caption"] = _caption(d, extra)
    return img, layout


# --------------------------------------------------------------------------- public API

def render(cir, view: str) -> RenderedFrame:
    """One disclosed frame of the whole product, with its construction manifest."""
    if view not in VIEWS:
        raise RenderRefused(f"{view!r} is not a view: {sorted(VIEWS)}")
    if cir.gauge is None:
        raise RenderRefused(f"{cir.slug}: no gauge, so no physical size to draw at")
    result, twin, palette = _compiled(cir)
    construction = cir.components[0].construction
    if construction == "flat_rows":
        img, layout = _flat_view(cir, twin, palette, view)
        form = "flat"
    elif construction in ("joined_rounds", "spiral_rounds"):
        img, layout = _round_view(cir, result, twin, palette, view)
        form = "rounds"
    else:
        raise RenderRefused(f"{cir.slug}: construction {construction!r} is not drawable here")
    png = _png(img)
    rows = _by_row(twin)
    manifest = {
        "kind": KIND,
        "renderer_version": RENDERER_VERSION,
        "contract_version": K.CONTRACT_VERSION,
        "slug": cir.slug, "version": cir.version, "title": cir.title,
        "cir_fingerprint": cir.fingerprint,
        # F-757: the configuration this frame shows -- the one the CIR's rows encode, which
        # is the only one the renderer can draw. `single` for a design with no options.
        "represented_variant": {"key": cir.variant_key,
                                "features": dict(cir.represented_variant)},
        "twin_digest": twin_digest(twin),
        "colour_map_digest": colour_map_digest(cir, twin),
        "view": view, "role": VIEWS[view]["role"], "job": VIEWS[view]["job"],
        "form": form, "construction": construction,
        "stitch_counts": {str(r): len(cs) for r, cs in rows.items()},
        "finished_dimensions_cm": {"width": twin.width_cm, "height": twin.height_cm},
        "pieces": cir.components[0].make,
        "layout": layout,
        "disclosure": K.DISCLOSURE,
        "image_sha256": hashlib.sha256(png).hexdigest(),
        "image_px": [K.CANVAS_PX, K.CANVAS_PX],
        "generated": False, "photograph": False, "model_in_path": False,
        "calibrated": twin.calibrated,
        "modelling_notes": (
            ["polygon rounds are drawn on the perimeter the stitch count makes, so side "
             "pitch is the gauge width"]
            if form == "rounds" and layout.get("sides") else []),
    }
    return RenderedFrame(view=view, png=png, manifest=manifest)


def listing_set(cir) -> list[RenderedFrame]:
    """The disclosed listing set for one product: hero, scale, detail -- in gallery order."""
    return [render(cir, view) for view in ("hero", "scale", "detail")]
