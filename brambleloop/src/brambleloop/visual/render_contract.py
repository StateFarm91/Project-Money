"""The rendering contract shared by the disclosed-render producer and its verifier (D-FB-7).

This module holds only what a verifier needs to *find* things in a frame: the canvas, the
non-product colours, where annotations may sit, the scale-bar convention, the oblique camera
angle and the disclosure wording. It holds no product geometry. Every stitch count, round
radius, row height and colour placement the verifier compares against is recomputed by the
verifier from the certified CIR through the compiler, never read from here and never read
from the producer's manifest.

Why a contract at all: a measurement needs a convention for what is background and what is
a scale. Without one, the verifier would have to guess, and a verifier that guesses can be
talked into a PASS. With one, every pixel of a frame is either one of a small set of known
colours or a sign the frame is not a contract render -- which is what makes a redraw,
a JPEG round-trip or a generated "improvement" fail closed instead of drifting into a pass.
"""
from __future__ import annotations

import math

# Contract 3 (W4-PRODREADY, owner ruling 2026-10-19, D-W4-VISROLE-LEGIBILITY): every word a
# disclosed frame letters is essential text -- the disclosure, the scale label, the finished
# dimensions -- and must be legible at the size it is really shown (a 390 px phone gallery).
# Contract 2 lettered the disclosure at 34 px and the labels at 30 px on the 2000 px canvas,
# 6.6 px and 5.8 px in a phone gallery. Contract 3 letters both at `TEXT_PX`, wraps lines
# to the zone instead of shrinking them, and gives the lettering its own rows below the
# product zone. Positions are computed here, once, by `caption_layout` and
# `annotation_layout`; the producer draws them and the verifier re-letters exactly them.
CONTRACT_VERSION = "disclosed-render-contract/3"

# Square, because the gallery must share one aspect (layout_qa FRAME_RATIOS_DISAGREE) and a
# square frame survives the mobile grid's centre crop whole. 2000 px is Etsy's recommended
# listing-image size.
CANVAS_PX = 2000

# Non-product colours. Chosen so every one sits far (> 40 RGB Euclidean) from every Launch-0
# yarn colour (cream #FAF6EB, wine #6E1F2A, ink #1A2B3C) and from each other; `separation()`
# checks that for any palette, and the producer refuses a palette that falls inside it.
BACKGROUND = (176, 186, 172)    # soft linen sage: cream, wine and ink all read against it
GAP = (88, 70, 44)              # the shadow between stitches and between rows/rounds
SCALE_DARK = (16, 16, 16)       # filled scale-bar segments and the bar's outline
CAPTION = (52, 40, 96)          # the disclosure caption and annotation text
LINE = (24, 92, 160)            # dimension lines

ANNOTATION_COLOURS = {"scale_dark": SCALE_DARK, "caption": CAPTION, "line": LINE}

# Minimum separation between any two contract colours, yarn included.
MIN_SEPARATION = 40.0
# A pixel further than this from every contract colour is "off-palette". Contract frames are
# drawn without antialiasing, so every pixel is exactly a contract colour; this allowance is
# for nothing but lossless re-encoding and is far below MIN_SEPARATION / 2.
OFF_PALETTE_DISTANCE = 12.0
# The share of off-palette pixels above which a frame is not a contract render at all.
MAX_OFF_PALETTE_SHARE = 0.001

# Zones, as fractions of the canvas. Everything sits inside the 8 % title-safe band
# (publish.mobile.TITLE_SAFE_MARGIN), so nothing the marketplace overlays can hide it.
# Contract 3 rows, top to bottom on the 2000 px canvas: the product 180-1490; the scale bar
# and its "N cm" label on the row from 1504; up to two annotation lines from 1570; the two
# disclosure lines from 1704. The last line's glyphs end at 1836, inside the 8 % title-safe
# band (1840). The product keeps 95 % of contract 2's height: measured, a smaller drawing
# loses a thin contrast row at 340 px (the cloudline blanket's cream at 0.68), and the 340 px
# colour check is not relaxed to make room for type.
PRODUCT_ZONE = (0.09, 0.09, 0.91, 0.745)        # x0, y0, x1, y1
SCALE_ZONE = (0.09, 0.753, 0.91, 0.77)
ANNOTATION_TOP = 0.785
CAPTION_TOP = 0.852
# The legibility floor at the display size (`frame_role.text_tier`): essential text is
# 11 px at 390 px, i.e. 57 px on 2000 px. One size for every contract word.
TEXT_PX = 58
CAPTION_PX = TEXT_PX
LABEL_PX = TEXT_PX
LINE_STEP_PX = 66
MAX_ANNOTATION_LINES = 2

# Oblique camera for vessel heroes: elevated this far above horizontal, looking at a flat
# face. Dimensions views use 0 (a true elevation), so heights read without projection.
OBLIQUE_DEG = 25.0
# The vessel ANGLE view (F-254 "the side, back or inside the hero cannot show"): the same
# camera raised to this elevation, so the inside of the back wall and the base's upper face
# read over the rim. Measured by `render_verification` with the same un-projection.
ANGLE_DEG = 50.0


# Elongated flat pieces (W4-VISUAL2). A table runner is 3.8:1; drawn upright in a square
# frame it reads as a thin strip that fills ~13 % of the frame at 340 px, so the whole-piece
# views (hero, scale) of a flat piece at least this elongated are drawn on the diagonal: the
# same certified fabric, every stitch, rotated as one rigid body so its long axis rises at
# the angle that draws it largest inside the product zone. Nothing is cropped, padded or
# re-proportioned. `render_verification` recomputes the rotation from the CIR (never from
# the manifest) and un-rotates the measured stitch glyphs before checking them.
ELONGATED_ASPECT = 2.5
# The scale view keeps this clear band inside the zone for its two dimension lines.
DIAGONAL_SCALE_MARGIN_PX = 70


def diagonal_deg(width_cm: float, height_cm: float, view: str,
                 canvas: int = CANVAS_PX) -> float | None:
    """The rigid rotation (degrees, counter-clockwise as seen) for a flat piece's `view`, or
    None when the piece is drawn upright (not elongated, or not a whole-piece view).

    The long axis is set rising to the right at the whole degree in [10, 80] that maximises
    the drawing scale inside the view's box; ties go to the shallower angle."""
    if view not in ("hero", "scale") or min(width_cm, height_cm) <= 0:
        return None
    long_, short = max(width_cm, height_cm), min(width_cm, height_cm)
    if long_ / short < ELONGATED_ASPECT:
        return None
    zx0, zy0, zx1, zy1 = zone_px(PRODUCT_ZONE, canvas)
    m = 2 * DIAGONAL_SCALE_MARGIN_PX if view == "scale" else 0
    bw, bh = (zx1 - zx0) - m, (zy1 - zy0) - m
    best, best_s = None, -1.0
    for a in range(10, 81):
        r = math.radians(a)
        s = min(bw / (long_ * math.cos(r) + short * math.sin(r)),
                bh / (long_ * math.sin(r) + short * math.cos(r)))
        if s > best_s + 1e-9:
            best, best_s = a, s
    # An upright long axis turns clockwise by (90 - best); a level one turns up by best.
    return float(best - 90) if height_cm >= width_cm else float(best)


def rotate_xy(x: float, y: float, deg: float, cx: float = 0.0, cy: float = 0.0):
    """(x, y) rotated `deg` counter-clockwise as seen (image y runs down) about (cx, cy)."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    dx, dy = x - cx, y - cy
    return cx + dx * c + dy * s, cy - dx * s + dy * c


def camera_deg(view: str) -> float:
    """The camera elevation a vessel view is drawn and verified at."""
    return {"hero": OBLIQUE_DEG, "angle": ANGLE_DEG}.get(view, 0.0)

# Gap between stitch glyphs, in pixels. Two pixels is the smallest gap that keeps adjacent
# stitches separate connected components under every scale the producer uses.
GAP_PX = 2

# Scale bar: alternating 1 cm segments (dark, background, dark ...) inside a dark outline.
SCALE_BAR_HEIGHT_PX = 18
SCALE_BAR_OUTLINE_PX = 2

# The disclosure. Wording justified in publish/disclosed_listing.py: it names the medium
# (a digital rendering), what it depicts (the finished design this pattern makes) and what it
# is not (a photograph), without the words "AI" or "generated", which would be false of a
# deterministic render and would misdirect a buyer about how the picture was made.
DISCLOSURE = "Digital rendering of the pattern's finished design, not a photograph"

FONT_PATHS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",)

# ---- annotations (contract 2, PT-05) -------------------------------------------------------
#
# Every word in a disclosed frame is one of three things, and nothing else may be: the
# disclosure caption, the scale bar's "N cm" label, and the annotation lines below. Their
# wording is fixed here and their numbers are filled from the CIR -- by the producer from its
# twin, and independently by the verifier from its own compile of the authoritative CIR -- so
# the verifier can re-draw exactly the words that may appear and refuse any other pixel of
# text. Contract 1 protected only the caption, and a scale view re-lettered "120 x 150 cm"
# with "certified safe for newborns" beside it passed every check.
SCALE_LABEL_GAP_PX = 24
SCALE_LABEL_RISE_PX = 8
ANNOTATION_LINE_STEP_PX = LINE_STEP_PX
_POLYGON = {3: "triangle", 4: "square", 5: "pentagon", 6: "hexagon", 8: "octagon"}


def scale_label(segments: int) -> str:
    return f"{segments} cm"


def scale_label_xy(bar_end_px: int, bar_top_px: int) -> tuple[int, int]:
    """Where the scale bar's label sits: just right of the bar, level with it."""
    return bar_end_px + SCALE_LABEL_GAP_PX, bar_top_px - SCALE_LABEL_RISE_PX


def annotation_lines(view: str, form: str, dims: dict) -> list[str]:
    """The annotation text a frame of this view and form carries, from its CIR figures.

    `dims` keys: flat -- width, height; rounds -- sides, points, flats, across, height,
    vessel (bool); detail -- rows, cols (flat) or base_rounds (vessel base)."""
    n1 = lambda v: f"{float(v):.1f}"  # noqa: E731
    # Contract 3: at most two lines, each within the zone width at TEXT_PX (`annotation_layout`
    # refuses otherwise). The figures and their words are contract 2's; only the line breaks
    # moved so that nothing is set smaller to fit.
    if view == "detail":
        if form == "flat":
            return [f"Detail: first {dims['rows']} rows x {dims['cols']} stitches,",
                    "drawn stitch for stitch"]
        if dims.get("vessel"):
            return [f"Base from above: all {dims['base_rounds']} base rounds"]
        return []
    if view != "scale":
        return []
    if form == "assembled" and dims.get("copies"):
        # W4-CAND: one of several identical pockets threaded on a cord, drawn alone.
        return [f"One of {int(dims['copies'])} pockets, {n1(dims['width'])} cm wide x "
                f"{n1(dims['height'])} cm tall,",
                f"at the stated gauge, on a {n1(dims['cord_cm'])} cm cord (not drawn)"]
    if form == "assembled":
        # W4-RENDER: the assembled object as drawn (pieces placed by the CIR's joins).
        return ["Assembled at the stated gauge:",
                f"{n1(dims['width'])} cm wide x {n1(dims['height'])} cm tall"]
    if form == "flat":
        return ["Finished size at the stated gauge:",
                f"{n1(dims['width'])} cm wide x {n1(dims['height'])} cm long"]
    sides = dims.get("sides") or 0
    if sides >= 3:
        name = _POLYGON.get(sides, f"{sides}-sided")
        spans = (f"{n1(dims['points'])} cm across the points, {n1(dims['flats'])} cm across "
                 f"the flats")
        if dims.get("vessel"):
            return [f"{name.capitalize()} base at the stated gauge, {n1(dims['height'])} cm "
                    f"tall:", spans]
        return [f"Finished size at the stated gauge ({name}):", spans]
    if dims.get("vessel"):
        return ["Finished size at the stated gauge:",
                f"{n1(dims['across'])} cm across, {n1(dims['height'])} cm tall"]
    return ["Finished size at the stated gauge:", f"{n1(dims['across'])} cm across"]


class LetteringRefused(ValueError):
    """The words do not fit the contract rows at a legible size; nothing is shrunk to fit."""


def _measure():
    from PIL import Image, ImageDraw

    return ImageDraw.Draw(Image.new("L", (1, 1)))


def wrap(text: str, px: int, max_w: float) -> list[str]:
    """Greedy word wrap at `px`. A single word wider than `max_w` is refused, not shrunk."""
    d, f = _measure(), font(px)
    out, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=f) <= max_w:
            line = trial
            continue
        if not line or d.textlength(word, font=f) > max_w:
            raise LetteringRefused(f"{word!r} is wider than {max_w:.0f} px at {px} px")
        out.append(line)
        line = word
    if line:
        out.append(line)
    return out


def caption_lines() -> list[str]:
    """The disclosure on two lines, split after its comma, so "not a photograph" is whole."""
    head, _sep, tail = DISCLOSURE.partition(", ")
    return [head + ",", tail] if tail else [DISCLOSURE]


def centred_layout(lines: list[str], top: float, canvas: int = CANVAS_PX,
                   px: int = TEXT_PX) -> list[tuple[str, tuple[int, int]]]:
    """Each line centred on the canvas, one LINE_STEP_PX under the other, from `top`."""
    d, f = _measure(), font(px)
    y0 = round(top * canvas)
    return [(t, (round((canvas - d.textlength(t, font=f)) / 2), y0 + i * LINE_STEP_PX))
            for i, t in enumerate(lines)]


def caption_layout(canvas: int = CANVAS_PX, lines: list[str] | None = None
                   ) -> list[tuple[str, tuple[int, int]]]:
    """Where the disclosure (or another frame label) is lettered: centred, from CAPTION_TOP.
    A line wider than the zone refuses (`LetteringRefused`)."""
    zx0, _zy0, zx1, _zy1 = zone_px(PRODUCT_ZONE, canvas)
    d, f = _measure(), font(CAPTION_PX)
    lines = list(lines if lines is not None else caption_lines())
    out: list[str] = []
    for t in lines:
        out += [t] if d.textlength(t, font=f) <= zx1 - zx0 else wrap(t, CAPTION_PX, zx1 - zx0)
    if len(out) > 2:
        raise LetteringRefused(f"the caption needs {len(out)} lines; the contract has 2")
    return centred_layout(out, CAPTION_TOP, canvas, CAPTION_PX)


def annotation_layout(lines: list[str], canvas: int = CANVAS_PX
                      ) -> list[tuple[str, tuple[int, int]]]:
    """The annotation lines wrapped to the zone width at LABEL_PX, left-aligned, one under
    the other from ANNOTATION_TOP. More than MAX_ANNOTATION_LINES refuses."""
    zx0, _zy0, zx1, _zy1 = zone_px(PRODUCT_ZONE, canvas)
    out: list[str] = []
    for t in lines:
        out += wrap(t, LABEL_PX, zx1 - zx0)
    if len(out) > MAX_ANNOTATION_LINES:
        raise LetteringRefused(f"{len(out)} annotation lines at {LABEL_PX} px; the contract "
                               f"has {MAX_ANNOTATION_LINES}")
    y0 = round(ANNOTATION_TOP * canvas)
    return [(t, (zx0, y0 + i * ANNOTATION_LINE_STEP_PX)) for i, t in enumerate(out)]


def lettering(caption: list[tuple[str, tuple[int, int]]],
              annotations: list[tuple[str, tuple[int, int]]],
              scale: tuple[str, tuple[int, int]] | None) -> list[dict]:
    """The frame's lettering as layout records ({text, pt, slot, box}) for legibility checks
    (`frame_role.legibility`): the disclosure, the dimension annotations, the scale label."""
    d = _measure()
    rows = [(t, xy, CAPTION_PX, "disclosure") for t, xy in caption]
    rows += [(t, xy, LABEL_PX, "annotation") for t, xy in annotations]
    if scale:
        rows.append((scale[0], scale[1], LABEL_PX, "scale_label"))
    return [{"kind": "text", "text": t, "pt": px, "slot": slot,
             "box": list(d.textbbox(xy, t, font=font(px)))} for t, xy, px, slot in rows]


def font(size: int):
    """The contract face. Refuses to fall back: a caption in a bitmap fallback face is a
    different picture of the same words, and the verifier compares pictures."""
    import os

    from PIL import ImageFont

    configured = os.environ.get("BRAMBLELOOP_FONT_PATH", "").strip()
    for path in ((configured,) if configured else ()) + FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise RuntimeError("no contract font available; a disclosed render cannot be captioned")


def zone_px(zone: tuple[float, float, float, float], canvas: int = CANVAS_PX) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = zone
    return (int(round(x0 * canvas)), int(round(y0 * canvas)),
            int(round(x1 * canvas)), int(round(y1 * canvas)))


def hex_rgb(value: str) -> tuple[int, int, int]:
    v = value.strip().lstrip("#")
    if len(v) != 6:
        raise ValueError(f"{value!r} is not a #RRGGBB colour")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


def _dist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def relief(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """The tone of a stitch that stands above the ground (a dc among sc).

    A light yarn is drawn 15 % darker on its raised post, a dark yarn 30 % lighter: the
    post is the same yarn catching light differently, and the tone is a contract colour so
    the verifier can tell a raised stitch from a ground stitch by its pixels alone.

    W4-VISUAL: when that default tone lands inside MIN_SEPARATION of its own yarn (a
    mid-light yarn such as gold #C49545 darkened 15 % sits 39.4 away), the post is drawn
    5 % further per step until it clears the separation. The minimum is not changed; the
    tone is made distinct. Every palette whose default tone already clears it -- all Launch-0
    palettes -- is drawn exactly as before."""
    r, g, b = rgb
    light = 0.2126 * r + 0.7152 * g + 0.0722 * b > 128
    tone = rgb
    for step in range(8):
        if light:
            f = 0.85 - 0.05 * step
            tone = (int(r * f), int(g * f), int(b * f))
        else:
            f = 0.30 + 0.05 * step
            tone = (int(r + (255 - r) * f), int(g + (255 - g) * f), int(b + (255 - b) * f))
        if _dist(tone, rgb) >= MIN_SEPARATION:
            return tone
    return tone


def separation(yarn: dict[str, tuple[int, int, int]]) -> float:
    """The smallest distance between any two contract colours for this palette, the raised
    tone of every yarn included."""
    colours = (list(yarn.values()) + [relief(v) for v in yarn.values()]
               + [BACKGROUND, GAP, *ANNOTATION_COLOURS.values()])
    best = float("inf")
    for i, a in enumerate(colours):
        for b in colours[i + 1:]:
            best = min(best, _dist(a, b))
    return best
