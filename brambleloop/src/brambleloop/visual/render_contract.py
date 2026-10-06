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

CONTRACT_VERSION = "disclosed-render-contract/2"

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
PRODUCT_ZONE = (0.09, 0.09, 0.91, 0.78)        # x0, y0, x1, y1
SCALE_ZONE = (0.09, 0.795, 0.91, 0.845)
CAPTION_TOP = 0.858
CAPTION_PX = 34
LABEL_PX = 30

# Oblique camera for vessel heroes: elevated this far above horizontal, looking at a flat
# face. Dimensions views use 0 (a true elevation), so heights read without projection.
OBLIQUE_DEG = 25.0

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
ANNOTATION_LINE_STEP_PX = 36
# The annotation block may not reach further left than this, so it never crosses the bar.
ANNOTATION_MIN_X_FRACTION = 0.40
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
    if view == "detail":
        if form == "flat":
            return [f"Detail: first {dims['rows']} rows x {dims['cols']} stitches, "
                    f"drawn stitch for stitch"]
        if dims.get("vessel"):
            return [f"Base from above: all {dims['base_rounds']} base rounds"]
        return []
    if view != "scale":
        return []
    if form == "flat":
        return [f"Finished size at the stated gauge: {n1(dims['width'])} cm wide x "
                f"{n1(dims['height'])} cm long"]
    sides = dims.get("sides") or 0
    if sides >= 3:
        name = _POLYGON.get(sides, f"{sides}-sided")
        spans = (f"{n1(dims['points'])} cm across the points, {n1(dims['flats'])} cm across "
                 f"the flats")
        if dims.get("vessel"):
            return [f"Finished size at the stated gauge ({name} base):",
                    f"{spans}, {n1(dims['height'])} cm tall"]
        return [f"Finished size at the stated gauge ({name}):", spans]
    if dims.get("vessel"):
        return [f"Finished size at the stated gauge: {n1(dims['across'])} cm across, "
                f"{n1(dims['height'])} cm tall"]
    return [f"Finished size at the stated gauge: {n1(dims['across'])} cm across"]


def annotation_xy(line_widths: list[float], canvas: int = CANVAS_PX) -> list[tuple[int, int]]:
    """Each annotation line right-aligned to the scale zone, one under the other."""
    _x0, zy0, zx1, _y1 = zone_px(SCALE_ZONE, canvas)
    return [(round(zx1 - w), zy0 + i * ANNOTATION_LINE_STEP_PX)
            for i, w in enumerate(line_widths)]


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
    the verifier can tell a raised stitch from a ground stitch by its pixels alone."""
    r, g, b = rgb
    if 0.2126 * r + 0.7152 * g + 0.0722 * b > 128:
        return (int(r * 0.85), int(g * 0.85), int(b * 0.85))
    return (int(r + (255 - r) * 0.30), int(g + (255 - g) * 0.30), int(b + (255 - b) * 0.30))


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
