"""Independent verification of a disclosed render, from its pixels, against the CIR.

The producer (`visual.disclosed_render`) writes a construction manifest. This module never
reads it. It takes the exact image bytes and the *authoritative* certified CIR for the
product the frame claims to show, and answers one question: do these pixels show what that
CIR makes? It measures:

  * the scale, from the scale bar's alternating 1 cm segments (no label is read);
  * the product's extent in centimetres, against dimensions it recomputes from the gauge;
  * every stitch, as a connected component of yarn-coloured pixels: how many per row or
    round, where each sits, its colour, and -- for flat fabric -- whether it is a raised
    stitch, all compared position by position with the compiled rows;
  * stitch pitch and row/round height against the gauge;
  * the disclosure caption, pixel for pixel against the contract wording.

Expected values come from `cir.compiler.compile_cir` and `cir.stitches` -- the row ops as
compiled, expanded here by this module's own arithmetic -- and not from the twin's layout,
the producer's code path or the manifest. Fabric order for flat work (even rows worked from
the other edge), ring radii (circumference / 2 pi), polygon corners (`cir.geometry.corners`)
and the base/wall split of a vessel are all recomputed here.

Verdicts: PASS only when every check passed within its stated tolerance. A check that cannot
be measured is UNKNOWN, and UNKNOWN blocks exactly like FAIL. There is no score and nothing
is averaged.

Tolerances (each is stated with why, and none was tuned to make a frame pass):

  COUNT_EXACT     stitch counts, round/row counts, colours and raised-stitch placement are
                  discrete; any difference is a different product. Tolerance 0.
  EXTENT_REL      +-2 % (or 6 px, whichever is larger) on overall size. A glyph's outline
                  insets the yarn edge by about one pixel per side and the scale bar is read
                  to under half a pixel over 400 px; 2 % is under a third of the 7 % a listing
                  could be off by if one round were missing from a 15-round piece, so a
                  missing or extra round cannot hide inside it.
  PITCH_REL       +-4 % on stitch pitch along a row / a polygon side, measured as a median of
                  centroid spacings. Quantisation is under 1 px on pitches of 9-180 px.
  HEIGHT_REL      +-3 % (or 4 px) on row bands and wall height.
  OFF_PALETTE     at most 0.1 % of pixels may be off the contract palette; a redraw, a blur,
                  a resample or a lossy round-trip all exceed it by orders of magnitude.
  CAPTION_IOU     0.98 between the caption pixels and the contract wording rendered in the
                  contract face at the contract position.
  ANNOTATION_PX   12 pixels. Outside the product zone every pixel must be what the contract
                  puts there -- background, the scale bar re-drawn from its own measured
                  ends, its "N cm" label, the disclosure, and the annotation lines re-lettered
                  from this module's own reading of the CIR -- and inside it nothing may be
                  lettered at all. Text is drawn without antialiasing in the contract face at
                  contract positions, so an honest frame differs by 0 px; 12 px is less than
                  one glyph of the label face, so no word, figure or claim fits inside it.
                  (The scale bar's segment boundaries are excused +-1 px: they are re-drawn
                  from a measured pixels-per-cm.)

Contract 2 (PT-05): version 1 verified every stitch and the caption and read no other text,
so a scale view re-lettered with a false finished size and a false material/safety claim
passed. Every text pixel is now accounted for.
"""
from __future__ import annotations

import hashlib
import io
import math

import numpy as np
from PIL import Image, ImageDraw

from . import render_contract as K

VERIFIER_VERSION = "render-verification/2.0.0"

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

EXTENT_REL, EXTENT_PX = 0.02, 6.0
PITCH_REL = 0.04
HEIGHT_REL, HEIGHT_PX = 0.03, 4.0
CAPTION_IOU = 0.98
ANNOTATION_PX = 12
LINE_THICKNESS_PX = 34
RAISED_FRACTION = 0.08     # a raised post covers >= 25 % of a dc glyph; an sc carries none

TOLERANCES = {
    "counts": "exact", "colours": "exact", "raised_stitch_placement": "exact",
    "extent": f"+-{EXTENT_REL:.0%} or {EXTENT_PX:g}px", "pitch": f"+-{PITCH_REL:.0%}",
    "height": f"+-{HEIGHT_REL:.0%} or {HEIGHT_PX:g}px",
    "off_palette": f"<= {K.MAX_OFF_PALETTE_SHARE:.1%} of pixels",
    "caption_iou": f">= {CAPTION_IOU}",
    "annotation_text": f"<= {ANNOTATION_PX}px differing from the re-drawn contract text",
}


def _check(name, status, why, **numbers) -> dict:
    return {"check": name, "status": status, "why": why, **numbers}


def _verdict(checks: list[dict], **extra) -> dict:
    statuses = [c["status"] for c in checks]
    status = FAIL if FAIL in statuses else UNKNOWN if (UNKNOWN in statuses or not checks) else PASS
    return {"status": status, "verifier_version": VERIFIER_VERSION, "checks": checks,
            "failed": [c["check"] for c in checks if c["status"] == FAIL],
            "unknown": [c["check"] for c in checks if c["status"] == UNKNOWN],
            "tolerances": TOLERANCES, "reads_manifest": False, **extra}


# --------------------------------------------------------------------------- authority

def authoritative_cir(slug: str, version: str | None = None):
    """The certified CIR for a Launch-0 product slug, built from its registered builder.

    Not from the frame and not from the manifest: a frame names the product it claims to
    show, and the design it is measured against comes from where designs are defined."""
    from ..products import launch0

    for s in launch0.LAUNCH0_SLUGS:
        for v in launch0.candidate(s).variants:
            cir = launch0.cir_for(v.build)
            if cir.slug == slug and (version is None or cir.version == version):
                return cir
    return None


def expected_model(cir) -> dict:
    """What the compiled pattern makes, recomputed here from the compiler's rows."""
    from ..cir import stitches
    from ..cir.compiler import compile_cir
    from ..cir.geometry import corners

    if len(cir.components) != 1 or cir.gauge is None:
        raise ValueError("one gauged component is required")
    comp = cir.components[0]
    result = compile_cir(cir)
    if not result.ok:
        raise ValueError("the CIR does not compile")
    rows = [r for r in result.rows if r.component == comp.name]
    g = cir.gauge
    w_cm = 10.0 / g.stitches_per_10cm
    unit_cm = 10.0 / g.rows_per_10cm
    base_h = stitches.get(g.stitch_type).row_height or 1.0
    out_rows = []
    for r in rows:
        seq = []
        for op in r.ops:
            st = stitches.get(op.stitch)
            for _ in range(op.count):
                seq.extend([op.stitch] * st.produces)
        # Row height by the stitch-weighted rule (PT-08): every stitch the row makes counts
        # its own row height. Recomputed here from the expanded stitches, not imported.
        worked = ([st for st in seq if st not in ("ch", "sk", "slst")]
                  or [st for st in seq if st not in ("ch", "sk")])
        units = (sum((stitches.get(st).row_height or base_h) for st in worked)
                 / len(worked) / base_h) if worked else 1.0
        if comp.construction == "flat_rows" and r.index % 2 == 0:
            seq = list(reversed(seq))          # worked from the other edge: fabric order
        out_rows.append({"index": r.index, "colour": r.color, "seq": seq,
                         "raised": [(stitches.get(s).row_height or base_h) > base_h + 1e-9
                                    for s in seq],
                         "height_cm": unit_cm * units})
    model = {"construction": comp.construction, "w_cm": w_cm, "unit_cm": unit_cm,
             "rows": out_rows, "make": comp.make,
             "palette": {k: K.hex_rgb(v) for k, v in (cir.colors or {}).items()}}
    if comp.construction != "flat_rows":
        counts = [len(r["seq"]) for r in out_rows]
        base_n = 1
        while base_n < len(counts) and counts[base_n] > counts[base_n - 1]:
            base_n += 1
        if any(counts[i] != counts[base_n - 1] for i in range(base_n, len(counts))):
            raise ValueError("rounds that grow again after the wall begins are not a vessel "
                             "this verifier models")
        sides = corners(rows)
        # A stacked-increase round is a polygon with the stitch count's perimeter; its
        # corners sit at perimeter / (2 n sin(pi/n)). A circle's radius is perimeter / 2 pi.
        k = (2 * sides * math.sin(math.pi / sides)) if sides else 2 * math.pi
        model["radii_cm"] = [n * w_cm / k for n in counts]
        model["base_rounds"] = base_n
        model["wall_rounds"] = len(counts) - base_n
        model["sides"] = sides
    return model


# --------------------------------------------------------------------------- pixels

class _Frame:
    def __init__(self, png: bytes, palette: dict[str, tuple[int, int, int]]):
        img = Image.open(io.BytesIO(png))
        self.mode = img.mode
        self.rgb = np.asarray(img.convert("RGB"), dtype=np.int32)
        self.h, self.w = self.rgb.shape[:2]
        names = list(palette)
        self.yarn_names = names
        refs = [palette[n] for n in names] + [K.relief(palette[n]) for n in names] + [
            K.BACKGROUND, K.GAP, K.SCALE_DARK, K.CAPTION, K.LINE]
        self.refs = np.array(refs, dtype=np.int32)
        n = len(names)
        self.BG, self.GAP, self.DARK, self.CAPTION, self.LINE = range(2 * n, 2 * n + 5)
        packed = (self.rgb[..., 0] << 16) | (self.rgb[..., 1] << 8) | self.rgb[..., 2]
        uniq, inverse = np.unique(packed.ravel(), return_inverse=True)
        u_rgb = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], axis=1)
        d2 = ((u_rgb[:, None, :] - self.refs[None, :, :]) ** 2).sum(axis=2)
        cls = d2.argmin(axis=1)
        far = np.sqrt(d2.min(axis=1)) > K.OFF_PALETTE_DISTANCE
        self.cls = cls[inverse].reshape(self.h, self.w)
        self.off_palette = far[inverse].reshape(self.h, self.w)
        self.n = n
        # yarn index (0..n-1) for yarn and raised-yarn pixels, -1 elsewhere
        self.yarn = np.where(self.cls < n, self.cls, np.where(self.cls < 2 * n, self.cls - n, -1))
        self.raised = (self.cls >= n) & (self.cls < 2 * n)


def _scale(frame: _Frame) -> dict:
    x0, y0, x1, y1 = K.zone_px(K.SCALE_ZONE, frame.w)
    dark = frame.cls[y0:y1, x0:x1] == frame.DARK
    from scipy import ndimage

    labels, count = ndimage.label(dark)
    if not count:
        return {"status": UNKNOWN, "why": "no scale bar"}
    sizes = ndimage.sum(dark, labels, range(1, count + 1))
    biggest = int(np.argmax(sizes)) + 1
    ys, xs = np.nonzero(labels == biggest)
    bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
    o = K.SCALE_BAR_OUTLINE_PX
    mid = (by0 + by1) // 2
    line = dark[mid, bx0 + o: bx1 - o + 1]
    if line.size < 30:
        return {"status": UNKNOWN, "why": "scale bar too short to read"}
    runs, start = [], 0
    for i in range(1, line.size + 1):
        if i == line.size or line[i] != line[start]:
            runs.append((bool(line[start]), start, i))
            start = i
    if len(runs) < 3 or not runs[0][0]:
        return {"status": UNKNOWN, "why": f"scale bar has {len(runs)} segments; need >= 3"}
    inner = line.size
    px_per_cm = inner / len(runs)
    lengths = np.array([b - a for _d, a, b in runs[1:-1]], dtype=float)
    if lengths.size and np.abs(lengths - px_per_cm).max() > 1.5:
        return {"status": FAIL, "why": "scale-bar segments are not equal 1 cm steps",
                "segments_px": lengths.tolist()}
    return {"status": PASS, "px_per_cm": float(px_per_cm), "segments_cm": len(runs),
            "bar_px": [int(bx0 + x0), int(by0 + y0), int(bx1 + x0), int(by1 + y0)]}


def _caption(frame: _Frame) -> dict:
    f = K.font(K.CAPTION_PX)
    probe = Image.new("L", (frame.w, frame.h), 0)
    d = ImageDraw.Draw(probe)
    d.fontmode = "1"
    width = d.textlength(K.DISCLOSURE, font=f)
    x = round((frame.w - width) / 2)
    y = round(K.CAPTION_TOP * frame.h)
    d.text((x, y), K.DISCLOSURE, fill=255, font=f)
    expected = np.asarray(probe) > 0
    band = slice(int(y - 12), int(y + K.CAPTION_PX * 2))
    seen = frame.cls[band, :] == frame.CAPTION
    exp = expected[band, :]
    union = (seen | exp).sum()
    iou = float((seen & exp).sum() / union) if union else 0.0
    return {"status": PASS if iou >= CAPTION_IOU else FAIL, "iou": round(iou, 4),
            "text": K.DISCLOSURE}


def _components(frame: _Frame, region=None):
    from scipy import ndimage

    x0, y0, x1, y1 = region or K.zone_px(K.PRODUCT_ZONE, frame.w)
    yarn = frame.yarn[y0:y1, x0:x1]
    mask = yarn >= 0
    labels, count = ndimage.label(mask)
    if not count:
        return [], mask
    idx = range(1, count + 1)
    objs = ndimage.find_objects(labels)
    areas = ndimage.sum(mask, labels, idx)
    raised = ndimage.sum(frame.raised[y0:y1, x0:x1], labels, idx)
    comps = []
    for k, sl in enumerate(objs, start=1):
        sub = labels[sl] == k
        ys, xs = np.nonzero(sub)
        colours = yarn[sl][sub]
        values, counts = np.unique(colours, return_counts=True)
        comps.append({
            "area": float(areas[k - 1]),
            "cx": float(xs.mean() + sl[1].start + x0), "cy": float(ys.mean() + sl[0].start + y0),
            "x0": sl[1].start + x0, "x1": sl[1].stop - 1 + x0,
            "y0": sl[0].start + y0, "y1": sl[0].stop - 1 + y0,
            "colour": frame.yarn_names[int(values[np.argmax(counts)])],
            "mixed_colour": len(values) > 1,
            "raised_fraction": float(raised[k - 1] / areas[k - 1]),
        })
    return comps, mask


def _within(measured, expected, rel, px=0.0, scale=1.0) -> bool:
    return abs(measured - expected) <= max(rel * abs(expected), px / scale)


# --------------------------------------------------------------------------- flat

def _verify_flat(frame, model, view, u, checks) -> dict:
    comps, _ = _components(frame)
    w_px = model["w_cm"] * u
    min_area = 0.25 * w_px * model["unit_cm"] * u
    comps = [c for c in comps if c["area"] >= min_area]
    if not comps:
        checks.append(_check("stitches_found", UNKNOWN, "no stitch glyphs in the product zone"))
        return {}
    left = min(c["x0"] for c in comps)
    right = max(c["x1"] for c in comps)
    bottom = max(c["y1"] for c in comps)
    top = min(c["y0"] for c in comps)
    rows = model["rows"]
    n_full = max(len(r["seq"]) for r in rows)
    # Columns and rows shown: the full fabric for hero/scale; for the detail view, the corner
    # window the pixels themselves show (row 1 at the bottom, the first stitch at the left),
    # which is then checked stitch for stitch against those rows of the pattern.
    cols = int(round((right - left + K.GAP_PX) / w_px))
    if view == "detail":
        heights, acc = [], 0.0
        for r in rows:
            acc += r["height_cm"]
            heights.append(acc)
        shown_cm = (bottom - top + K.GAP_PX) / u
        n_rows = int(np.argmin([abs(h - shown_cm) for h in heights])) + 1
        if cols < 12 or n_rows < 12:
            checks.append(_check("detail_window", FAIL,
                                 f"detail shows {cols} x {n_rows}; a detail must show at least "
                                 f"12 stitches by 12 rows to evidence the fabric"))
            return {}
    else:
        n_rows = len(rows)
    shown = rows[:n_rows]
    width_cm = cols * model["w_cm"]
    height_cm = sum(r["height_cm"] for r in shown)
    m_w = (right - left + K.GAP_PX) / u
    m_h = (bottom - top + K.GAP_PX) / u
    ok = _within(m_w, width_cm, EXTENT_REL, EXTENT_PX, u) and _within(m_h, height_cm, EXTENT_REL, EXTENT_PX, u)
    if view != "detail" and cols != n_full:
        ok = False
    checks.append(_check("extent_cm", PASS if ok else FAIL,
                         "overall size from the scale bar against the gauge arithmetic",
                         measured=[round(m_w, 2), round(m_h, 2)],
                         expected=[round(width_cm, 2), round(height_cm, 2)]))
    # Assign every glyph to a row band and a column.
    bands, acc = [], 0.0
    for r in shown:
        b = bottom + K.GAP_PX / 2 - acc * u
        bands.append((b - r["height_cm"] * u, b, r))
        acc += r["height_cm"]
    got: dict[int, dict[int, dict]] = {}
    stray = 0
    for c in comps:
        band = next((bd for bd in bands if bd[0] - 1 <= c["cy"] <= bd[1] + 1), None)
        if band is None:
            stray += 1
            continue
        col = int((c["cx"] - left + K.GAP_PX / 2) // w_px)
        cell = got.setdefault(band[2]["index"], {})
        if col in cell or col >= cols:
            stray += 1
            continue
        cell[col] = c
    count_bad, colour_bad, raised_bad, height_bad = [], [], [], []
    pitches = []
    for lo, hi, r in bands:
        cells = got.get(r["index"], {})
        want = cols
        if sorted(cells) != list(range(want)):
            count_bad.append({"row": r["index"], "found": len(cells), "expected": want})
            continue
        xs = [cells[k]["cx"] for k in range(want)]
        pitches.extend(np.diff(xs).tolist())
        for k in range(want):
            c = cells[k]
            if c["colour"] != r["colour"] or c["mixed_colour"]:
                colour_bad.append((r["index"], k))
            if (c["raised_fraction"] > RAISED_FRACTION) != r["raised"][k]:
                raised_bad.append((r["index"], k))
            hgt = c["y1"] - c["y0"] + 1 + K.GAP_PX
            if not _within(hgt, (hi - lo), HEIGHT_REL, HEIGHT_PX):
                height_bad.append((r["index"], k))
    checks.append(_check("stitch_counts", FAIL if (count_bad or stray) else PASS,
                         "one glyph per compiled stitch, in every row shown",
                         rows=len(bands), stitches_per_row=cols, bad_rows=count_bad[:5],
                         stray_glyphs=stray))
    checks.append(_check("colour_placement", FAIL if colour_bad else PASS,
                         "every stitch the colour its row is worked in", bad=colour_bad[:5]))
    checks.append(_check("raised_stitch_placement", FAIL if raised_bad else PASS,
                         "raised posts exactly where the pattern works a taller stitch",
                         bad=raised_bad[:5]))
    checks.append(_check("row_heights", FAIL if height_bad else PASS,
                         "each glyph as tall as its row's gauge height", bad=height_bad[:5]))
    if pitches:
        p = float(np.median(pitches)) / u
        checks.append(_check("stitch_pitch_cm", PASS if _within(p, model["w_cm"], PITCH_REL) else FAIL,
                             "median stitch spacing against 10 cm / stitches per 10 cm",
                             measured=round(p, 4), expected=round(model["w_cm"], 4)))
    return {"rows": len(bands), "cols": cols, "window": {"rows": n_rows, "cols": cols},
            "measured_cm": [round(m_w, 2), round(m_h, 2)]}


# --------------------------------------------------------------------------- rounds

def _hex_radius(px, py, sides):
    if not sides:
        return math.hypot(px, py)
    best = 0.0
    for j in range(sides):
        a = 2 * math.pi * (j + 0.5) / sides
        best = max(best, px * math.cos(a) + py * math.sin(a))
    return best / math.cos(math.pi / sides)


def _hex_param(px, py, sides):
    """Arc parameter in [0, 1) of a point's projection onto the polygon (or circle)."""
    ang = math.atan2(py, px) % (2 * math.pi)
    if not sides:
        return ang / (2 * math.pi)
    j = int(ang / (2 * math.pi / sides)) % sides
    a0, a1 = 2 * math.pi * j / sides, 2 * math.pi * (j + 1) / sides
    v0 = np.array([math.cos(a0), math.sin(a0)])
    v1 = np.array([math.cos(a1), math.sin(a1)])
    # intersection of the ray with the side, as a fraction along it
    d = np.array([math.cos(ang), math.sin(ang)])
    m = np.array([v1 - v0, -d]).T
    f = np.linalg.solve(m, -v0)[0]
    return (j + min(max(f, 0.0), 1.0)) / sides


def _objects(frame, expected_n):
    from scipy import ndimage

    x0, y0, x1, y1 = K.zone_px(K.PRODUCT_ZONE, frame.w)
    mask = frame.yarn[y0:y1, x0:x1] >= 0
    closed = ndimage.binary_closing(mask, iterations=K.GAP_PX + 1)
    closed = ndimage.binary_fill_holes(closed)
    labels, count = ndimage.label(closed)
    out = []
    for k, sl in enumerate(ndimage.find_objects(labels), start=1):
        area = (labels[sl] == k).sum()
        if area < 0.002 * mask.size:
            continue
        out.append((sl[1].start + x0, sl[0].start + y0, sl[1].stop - 1 + x0, sl[0].stop - 1 + y0))
    return sorted(out, key=lambda b: (round(b[1] / 200), b[0]))


def _verify_plan(frame, model, view, u, checks, part) -> dict:
    sides = model["sides"]
    radii = model["radii_cm"]
    rows = model["rows"]
    if part == "base":
        rows, radii = rows[:model["base_rounds"]], radii[:model["base_rounds"]]
    expected_objects = model["make"] if (view == "hero" and part == "whole") else 1
    objs = _objects(frame, expected_objects)
    checks.append(_check("object_count", PASS if len(objs) == expected_objects else FAIL,
                         "pieces shown against the pieces the pattern makes",
                         found=len(objs), expected=expected_objects))
    if len(objs) != expected_objects:
        return {}
    R = radii[-1]
    span_y = (math.sqrt(3) * R) if sides == 6 else 2 * R
    if sides not in (0, 6):
        span_y = 2 * R * max(math.sin(2 * math.pi * k / sides) for k in range(sides))
    comps, _ = _components(frame)
    polygon = sides or 64
    ring1_area = (0.5 * polygon * radii[0] ** 2 * math.sin(2 * math.pi / polygon)
                  / len(rows[0]["seq"]) * u * u)
    comps = [c for c in comps if c["area"] >= 0.3 * ring1_area]
    per_object = []
    all_ok = True
    for b in objs:
        bx0, by0, bx1, by1 = b
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        m_w = (bx1 - bx0 + K.GAP_PX) / u
        m_h = (by1 - by0 + K.GAP_PX) / u
        ext_ok = _within(m_w, 2 * R, EXTENT_REL, EXTENT_PX, u) and _within(m_h, span_y, EXTENT_REL, EXTENT_PX, u)
        mine = [c for c in comps if bx0 <= c["cx"] <= bx1 and by0 <= c["cy"] <= by1]
        rings: dict[int, list] = {}
        stray = 0
        for c in mine:
            x, y = (c["cx"] - cx) / u, -(c["cy"] - cy) / u
            d = _hex_radius(x, y, sides)
            k = next((i for i, r in enumerate(radii) if d <= r * 1.0 + 0.02 and
                      d >= (radii[i - 1] if i else 0.0) - 0.02), None)
            if k is None:
                stray += 1
                continue
            rings.setdefault(k, []).append((c, x, y))
        count_bad, colour_bad = [], []
        for k, r in enumerate(rows):
            got = rings.get(k, [])
            if len(got) != len(r["seq"]):
                count_bad.append({"round": r["index"], "found": len(got), "expected": len(r["seq"])})
            if any(c["colour"] != r["colour"] or c["mixed_colour"] for c, _x, _y in got):
                colour_bad.append(r["index"])
        pitch = None
        outer = rings.get(len(rows) - 1, [])
        if len(outer) >= 6:
            mid = (radii[-1] + radii[-2]) / 2 if len(radii) > 1 else radii[-1] / 2
            perim = (sides * 2 * mid * math.sin(math.pi / sides)) if sides else 2 * math.pi * mid
            ts = sorted(_hex_param(x, y, sides) for _c, x, y in outer)
            gaps = np.diff(ts + [ts[0] + 1.0])
            measured = float(np.median(gaps)) * perim
            expected = perim / len(rows[-1]["seq"])
            pitch = {"measured_cm": round(measured, 4), "expected_cm": round(expected, 4),
                     "gauge_width_cm": round(model["w_cm"], 4),
                     "centreline_pitch_vs_gauge": round(expected / model["w_cm"] - 1, 4),
                     "ok": _within(measured, expected, PITCH_REL)}
        ok = ext_ok and not count_bad and not colour_bad and not stray and bool(pitch and pitch["ok"])
        all_ok &= ok
        per_object.append({"bbox": list(b), "measured_cm": [round(m_w, 2), round(m_h, 2)],
                           "expected_cm": [round(2 * R, 2), round(span_y, 2)],
                           "extent_ok": ext_ok, "rounds": len(rows),
                           "bad_rounds": count_bad[:5], "bad_colour_rounds": colour_bad[:5],
                           "stray_glyphs": stray, "pitch": pitch})
    checks.append(_check("extent_cm", PASS if all(o["extent_ok"] for o in per_object) else FAIL,
                         "across the points and across the flats, from the scale bar",
                         objects=[{"measured": o["measured_cm"], "expected": o["expected_cm"]}
                                  for o in per_object]))
    checks.append(_check("stitch_counts", PASS if all(not o["bad_rounds"] and not o["stray_glyphs"]
                                                      for o in per_object) else FAIL,
                         "one glyph per compiled stitch in every round, every piece",
                         rounds=len(rows), objects=[{"bad": o["bad_rounds"], "stray": o["stray_glyphs"]}
                                                    for o in per_object]))
    checks.append(_check("colour_placement", PASS if all(not o["bad_colour_rounds"] for o in per_object) else FAIL,
                         "every round in the colour it is worked in"))
    pitch_ok = [o["pitch"] for o in per_object]
    checks.append(_check("stitch_pitch_cm",
                         PASS if all(p and p["ok"] for p in pitch_ok) else
                         (UNKNOWN if any(p is None for p in pitch_ok) else FAIL),
                         "outer-round pitch along the polygon the rounds are laid on",
                         objects=pitch_ok))
    return {"objects": per_object, "sides": sides}


def _verify_vessel(frame, model, view, u, checks) -> dict:
    sides = model["sides"]
    if sides != 6:
        checks.append(_check("wall_counts", UNKNOWN,
                             f"wall counting is defined for a stacked hexagon; this vessel has "
                             f"{sides!r} corners"))
        return {}
    alpha = math.radians(K.camera_deg(view))
    ca, sa = math.cos(alpha), math.sin(alpha)
    radii = model["radii_cm"]
    R = radii[model["base_rounds"] - 1]
    walls = model["rows"][model["base_rounds"]:]
    h = model["unit_cm"]
    H = len(walls) * h
    objs = _objects(frame, 1)
    checks.append(_check("object_count", PASS if len(objs) == 1 else FAIL,
                         "one vessel", found=len(objs), expected=1))
    if len(objs) != 1:
        return {}
    bx0, by0, bx1, by1 = objs[0]
    cx = (bx0 + bx1) / 2
    m_R = (bx1 - bx0 + K.GAP_PX) / u / 2
    a = m_R * math.cos(math.pi / 6)
    comps, _ = _components(frame)
    w_face = R / (len(walls[0]["seq"]) / 6)
    comps = [c for c in comps if c["area"] >= 0.25 * (w_face * u) * (h * u * ca)]
    front = [c for c in comps if abs(c["cx"] - cx) < m_R * u / 2]
    half = max(2, int(w_face * u / 2))
    band = frame.yarn[: K.zone_px(K.PRODUCT_ZONE, frame.w)[3],
                      int(round(cx)) - half: int(round(cx)) + half + 1] >= 0
    ys = np.nonzero(band.any(axis=1))[0]
    if not ys.size:
        checks.append(_check("wall_counts", UNKNOWN, "no front face found"))
        return {}
    y_bottom = float(ys.max()) + K.GAP_PX / 2
    rounds: dict[int, list] = {}
    above = 0
    for c in front:
        z = (y_bottom - c["cy"]) / (u * ca)
        j = int(z // h)
        if j >= len(walls):
            above += 1               # inside of the back wall, seen over the rim
            continue
        rounds.setdefault(j, []).append(c)
    count_bad, colour_bad, pitches = [], [], []
    per_face = len(walls[0]["seq"]) // 6
    for j, r in enumerate(walls):
        got = sorted(rounds.get(j, []), key=lambda c: c["cx"])
        if len(got) != len(r["seq"]) // 6:
            count_bad.append({"round": r["index"], "found": len(got), "expected": len(r["seq"]) // 6})
        if any(c["colour"] != r["colour"] or c["mixed_colour"] for c in got):
            colour_bad.append(r["index"])
        pitches.extend(np.diff([c["cx"] for c in got]).tolist())
    top_front = min((c["y0"] for j in rounds for c in rounds[j]), default=None)
    m_H = (y_bottom - top_front + K.GAP_PX / 2) / (u * ca) if top_front is not None else 0.0
    m_w = 2 * m_R
    ext_ok = _within(m_w, 2 * R, EXTENT_REL, EXTENT_PX, u)
    checks.append(_check("extent_cm", PASS if ext_ok else FAIL,
                         "across the corners, from the scale bar", measured=round(m_w, 2),
                         expected=round(2 * R, 2)))
    checks.append(_check("wall_height_cm", PASS if _within(m_H, H, HEIGHT_REL, HEIGHT_PX, u * ca) else FAIL,
                         "front-face height, un-projected by the contract camera angle",
                         measured=round(m_H, 2), expected=round(H, 2)))
    checks.append(_check("stitch_counts", FAIL if count_bad else PASS,
                         "every wall round: one glyph per stitch on the front face "
                         "(stitches per round / 6 on a stacked hexagon)",
                         rounds=len(walls), per_face=per_face, bad=count_bad[:5]))
    checks.append(_check("colour_placement", FAIL if colour_bad else PASS,
                         "every wall round in the colour it is worked in", bad=colour_bad[:5]))
    if pitches:
        p = float(np.median(pitches)) / u
        checks.append(_check("stitch_pitch_cm", PASS if _within(p, w_face, PITCH_REL) else FAIL,
                             "front-face pitch: side length / stitches per side",
                             measured=round(p, 4), expected=round(w_face, 4),
                             gauge_width_cm=round(model["w_cm"], 4)))
    else:
        checks.append(_check("stitch_pitch_cm", UNKNOWN, "no front-face stitches to measure"))
    return {"wall_rounds": len(walls), "per_face": per_face, "seen_over_rim": above}



# --------------------------------------------------------------------------- annotations

def _expected_figures(cir, model) -> tuple[dict, list[str]]:
    """The figures the scale view must letter, from a fresh twin of the authoritative CIR,
    cross-checked against this module's own gauge arithmetic. Returns (figures, problems)."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    comp = cir.components[0]
    twin = build_twin(cir, compile_cir(cir), component=comp.name)
    figures = {"width": twin.width_cm, "height": twin.height_cm, "sides": twin.sides or 0,
               "points": twin.across_points_cm, "flats": twin.across_flats_cm,
               "across": twin.width_cm, "vessel": twin.shape not in (None, "disc")}
    problems = []

    def agree(name, stated, computed):
        if stated is None or abs(stated - computed) > max(0.02 * computed, 0.11):
            problems.append(f"{name}: twin {stated} against gauge arithmetic {computed:.2f}")

    if model["construction"] == "flat_rows":
        agree("width", twin.width_cm, max(len(r["seq"]) for r in model["rows"]) * model["w_cm"])
        agree("height", twin.height_cm, sum(r["height_cm"] for r in model["rows"]))
    else:
        R = model["radii_cm"][model["base_rounds"] - 1]
        sides = model["sides"] or 0
        if sides >= 3:
            agree("across the points", twin.across_points_cm,
                  2 * R if sides % 2 == 0 else R * (1 + math.cos(math.pi / sides)))
            agree("across the flats", twin.across_flats_cm,
                  2 * R * math.cos(math.pi / sides) if sides % 2 == 0
                  else R * (1 + math.cos(math.pi / sides)))
        else:
            agree("across", twin.width_cm, 2 * R)
        if model.get("wall_rounds"):
            agree("height", twin.height_cm, model["wall_rounds"] * model["unit_cm"])
    return figures, problems


def _text_mask(lines_at: list[tuple[str, tuple[int, int], int]], w: int, h: int):
    probe = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(probe)
    d.fontmode = "1"
    for text, xy, size in lines_at:
        d.text(xy, text, fill=255, font=K.font(size))
    return np.asarray(probe) > 0


def _annotations(frame: _Frame, cir, model, view: str, scale: dict, detail: dict,
                 checks: list[dict]) -> None:
    """Every pixel outside the product zone, and every lettered pixel inside it (PT-05)."""
    from scipy import ndimage

    form = "flat" if model["construction"] == "flat_rows" else "rounds"
    lines: list[str] = []
    if view == "scale":
        figures, problems = _expected_figures(cir, model)
        checks.append(_check("dimension_figures", FAIL if problems else PASS,
                             "the finished size the frame letters is the CIR's, and agrees "
                             "with the gauge arithmetic", problems=problems))
        lines = K.annotation_lines("scale", form, figures)
    elif view == "detail":
        if form == "flat":
            win = (detail or {}).get("window") or {}
            if win:
                lines = K.annotation_lines("detail", "flat",
                                           {"rows": win["rows"], "cols": win["cols"]})
        elif model.get("wall_rounds"):
            lines = K.annotation_lines("detail", "rounds",
                                       {"vessel": True, "base_rounds": model["base_rounds"]})
    w, h = frame.w, frame.h
    # The text that may appear, re-lettered at the contract positions.
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    lf = K.font(K.LABEL_PX)
    texts = [(K.DISCLOSURE, (round((w - probe.textlength(K.DISCLOSURE, font=K.font(K.CAPTION_PX))) / 2),
                             round(K.CAPTION_TOP * h)), K.CAPTION_PX)]
    if lines:
        texts += [(t, xy, K.LABEL_PX) for t, xy in
                  zip(lines, K.annotation_xy([probe.textlength(t, font=lf) for t in lines], w))]
    o = K.SCALE_BAR_OUTLINE_PX
    bx0, by0, bx1, _by1 = scale["bar_px"]
    x0, y0, end = bx0 + o, by0 + o, bx1 - o + 1
    segments = int(scale["segments_cm"])
    texts.append((K.scale_label(segments), K.scale_label_xy(end, y0), K.LABEL_PX))
    exp_text = _text_mask(texts, w, h)
    # The scale bar, re-drawn from its own measured ends.
    bar = Image.new("L", (w, h), 0)
    bd = ImageDraw.Draw(bar)
    y1 = y0 + K.SCALE_BAR_HEIGHT_PX
    u = (end - x0) / segments
    fuzzy = np.zeros((h, w), bool)
    for i in range(segments):
        a, b = x0 + i * u, x0 + (i + 1) * u
        if i % 2 == 0:
            bd.rectangle([round(a), y0, round(b) - 1, y1], fill=255)
        for edge in (a, b):
            fuzzy[y0:y1 + 1, max(0, int(edge) - 1):int(edge) + 2] = True
    bd.rectangle([x0 - o, y0 - o, end - 1 + o, y1 + o], outline=255, width=o)
    exp_dark = np.asarray(bar) > 0
    zx0, zy0, zx1, zy1 = K.zone_px(K.PRODUCT_ZONE, w)
    inside = np.zeros((h, w), bool)
    # The drawing may touch the zone's edge by a pixel or two (rounding); text cannot hide
    # in a 3 px ring.
    inside[max(0, zy0 - 3):zy1 + 3, max(0, zx0 - 3):zx1 + 3] = True
    seen_line = frame.cls == frame.LINE

    seen_text = frame.cls == frame.CAPTION
    seen_dark = frame.cls == frame.DARK
    seen_bg = (frame.cls == frame.BG) & ~frame.off_palette
    expected_bg = ~exp_text & ~exp_dark
    outside = ~inside & ~fuzzy
    # Dimension-line pixels are accounted for by the dimension-line check below, which sees
    # the whole canvas (a line's end ticks may cross the zone edge).
    wrong = outside & ((seen_text != exp_text) | (seen_dark != exp_dark)
                       | (expected_bg & ~seen_bg & ~seen_line) | frame.off_palette)
    # Inside the product zone nothing is lettered and nothing is a scale bar.
    lettered_inside = inside & (seen_text | seen_dark)
    n_out, n_in = int(wrong.sum()), int(lettered_inside.sum())
    where = None
    if n_out:
        ys, xs = np.nonzero(wrong)
        where = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    checks.append(_check(
        "annotation_text", PASS if (n_out <= ANNOTATION_PX and n_in <= ANNOTATION_PX) else FAIL,
        "every word on the frame is the disclosure, the scale label or a contract annotation "
        "whose figures are recomputed from the CIR; nothing else is lettered anywhere",
        differing_px=n_out, lettered_in_product_zone_px=n_in, differing_bbox=where,
        expected_lines=lines))

    # Marks inside the product zone that are not part of the drawn object(s).
    zone = (~seen_bg[zy0:zy1, zx0:zx1]) & ~seen_line[zy0:zy1, zx0:zx1]
    closed = ndimage.binary_fill_holes(ndimage.binary_closing(zone, iterations=K.GAP_PX + 1))
    labels, count = ndimage.label(closed | zone)
    stray = 0
    if count:
        areas = ndimage.sum(np.ones_like(zone), labels, range(1, count + 1))
        small = {k + 1 for k, a in enumerate(areas) if a < 0.002 * zone.size}
        if small:
            stray = int((zone & np.isin(labels, list(small))).sum())
    # Dimension lines: exactly the contract's, as long as the product they measure.
    line_mask = seen_line & ~frame.off_palette
    l_labels, l_count = ndimage.label(line_mask)
    found = []
    for sl in ndimage.find_objects(l_labels):
        found.append((sl[1].stop - sl[1].start, sl[0].stop - sl[0].start))
    want = []
    if view == "scale":
        if form == "flat":
            m = (detail or {}).get("measured_cm") or [0, 0]
            want = [("h", m[0]), ("v", m[1])]
        else:
            R = model["radii_cm"][model["base_rounds"] - 1]
            sides = model["sides"] or 0
            span = (2 * R) if not sides or sides % 2 == 0 else R * (1 + math.cos(math.pi / sides))
            want = [("h", span)]
            if model.get("wall_rounds"):
                want.append(("v", model["wall_rounds"] * model["unit_cm"]))
    lines_ok = len(found) == len(want)
    for kind, cm in want:
        target = cm * scale["px_per_cm"]
        hit = [f for f in found
               if (f[1] if kind == "h" else f[0]) <= LINE_THICKNESS_PX
               and abs((f[0] if kind == "h" else f[1]) - target) <= max(0.03 * target, 10)]
        lines_ok &= bool(hit)
    checks.append(_check(
        "marks_in_product_zone", PASS if (stray <= ANNOTATION_PX and lines_ok) else FAIL,
        "nothing in the product zone but the product and the contract dimension lines",
        stray_px=stray, dimension_lines_found=len(found), dimension_lines_expected=len(want)))

# --------------------------------------------------------------------------- entry point

def verify(png: bytes, *, cir, view: str) -> dict:
    """Verify one disclosed frame's pixels against the given authoritative CIR.

    Fails closed: anything that goes wrong while measuring is UNKNOWN, never a crash in the
    gate that called it and never a PASS."""
    try:
        return _verify(png, cir=cir, view=view)
    except Exception as exc:  # noqa: BLE001
        return _verdict([_check("measurement", UNKNOWN,
                                f"verification could not complete: {type(exc).__name__}: "
                                f"{str(exc)[:200]}")])


def _verify(png: bytes, *, cir, view: str) -> dict:
    checks: list[dict] = []
    try:
        model = expected_model(cir)
    except Exception as exc:  # noqa: BLE001 - every refusal is an UNKNOWN, never a pass
        return _verdict([_check("expected_model", UNKNOWN, f"cannot model the CIR: {exc}")])
    used = {r["colour"] for r in model["rows"]}
    palette = {k: v for k, v in model["palette"].items() if k in used}
    if set(palette) != used:
        return _verdict([_check("palette", UNKNOWN, "a row colour has no RGB in the CIR")])
    try:
        frame = _Frame(png, palette)
    except Exception as exc:  # noqa: BLE001
        return _verdict([_check("decode", FAIL, f"not a decodable image: {exc}")])
    sha = hashlib.sha256(png).hexdigest()
    if (frame.w, frame.h) != (K.CANVAS_PX, K.CANVAS_PX):
        return _verdict([_check("canvas", FAIL, f"{frame.w}x{frame.h} is not the contract canvas")],
                        image_sha256=sha)
    off = float(frame.off_palette.mean())
    checks.append(_check("contract_palette", PASS if off <= K.MAX_OFF_PALETTE_SHARE else FAIL,
                         "every pixel is a contract colour; a redraw or resample is not",
                         off_palette_share=round(off, 6)))
    if off > K.MAX_OFF_PALETTE_SHARE:
        return _verdict(checks, image_sha256=sha)
    cap = _caption(frame)
    checks.append(_check("disclosure_in_image", cap["status"],
                         "the disclosure caption, in the contract words and place",
                         iou=cap["iou"]))
    scale = _scale(frame)
    checks.append(_check("scale_bar", scale["status"], scale.get("why", "1 cm segments read"),
                         px_per_cm=round(scale.get("px_per_cm", 0.0), 4),
                         segments_cm=scale.get("segments_cm")))
    if scale["status"] != PASS:
        return _verdict(checks, image_sha256=sha)
    u = scale["px_per_cm"]
    construction = model["construction"]
    if view == "angle" and not (construction != "flat_rows" and model.get("wall_rounds")):
        checks.append(_check("view", FAIL, "an angle view exists only for a vessel; on a flat "
                                           "or plan-form product it would repeat the hero"))
        return _verdict(checks, image_sha256=sha)
    if construction == "flat_rows":
        detail = _verify_flat(frame, model, view, u, checks)
    elif model.get("wall_rounds"):
        if view == "detail":
            detail = _verify_plan(frame, model, view, u, checks, part="base")
        else:
            detail = _verify_vessel(frame, model, view, u, checks)
    else:
        detail = _verify_plan(frame, model, view, u, checks, part="whole")
    _annotations(frame, cir, model, view, scale, detail, checks)
    return _verdict(checks, image_sha256=sha, view=view, slug=cir.slug,
                    cir_fingerprint=cir.fingerprint, px_per_cm=round(u, 4), measured=detail)


def verify_claim(png: bytes, *, slug: str, version: str | None, view: str) -> dict:
    """Verify a frame against the authoritative CIR for the product it claims to show."""
    cir = authoritative_cir(slug, version)
    if cir is None:
        return _verdict([_check("authority", UNKNOWN,
                                f"no authoritative CIR for {slug}@{version}; nothing to verify against")])
    return verify(png, cir=cir, view=view)
