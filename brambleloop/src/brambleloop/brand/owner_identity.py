"""O1 "Bramble B" -- the owner's own brand concept, professionalised into a production identity.

Owner decision D-FB-16 (2026-10-06): the owner-supplied concept (owner_logo_concept.png, sha256
28f301b2..., and the banner variant owner_banner_concept.png, sha256 048a1991...) is the PRIMARY
Brambleloop identity. D1 "Briar Monogram" and the other `directions` remain design research only.

This is not a trace and not a redesign. Every element of the concept is kept and rebuilt as
clean, original vector geometry plus outlined open-licence type:

  * an elegant high-contrast serif B (Playfair Display, a Didone/transitional design, OFL),
  * botanical bramble growth climbing the B: leaves, five-petal bramble blossoms, and -- from
    the banner variant -- clusters of bramble berries,
  * a yarn strand that loops through the letter as a figure-of-eight and ends in a small ball,
  * a spaced serif BRAMBLELOOP wordmark (Cormorant Garamond SemiBold, OFL),
  * CROCHET PATTERNS between hairlines (Work Sans, OFL), in the concept's warm taupe,
  * the tagline "Patterns for a More Handmade Life" in a fine signature script (Allison, OFL),
  * a small dusty-rose heart between short hairlines, as in both concept images.

The concept's 40 px problem (lane A2 measured 42% of ink at >= 3:1 and a 2.44:1 median contrast)
is solved by simplification of the SAME identity, not by a different idea: the micro-mark is
the same Playfair B in its heaviest cut, two large bramble leaves instead of a sprig, and a
single bold loop of yarn ending in the ball. Nothing finer than ~2 px at 40 px is drawn.

Palette: sampled from the concept rasters (see CONCEPT_SAMPLES; `tests/
test_w3_brand_owner_identity.py` re-samples the owner's file and checks the tolerance).
"""
from __future__ import annotations

import math

from . import typeset as T
from .directions import (Direction, _blossom, _hairline_descriptor, _leaf, _moved, place,
                         trim)
from .vector import (Circle, Fill, Knockout, Mark, Path, Stroke, cubic_through, leaf_path)

DIRECTION_ID = "O1-owner-bramble-b"
ICON = 500.0

TAGLINE = "Patterns for a More Handmade Life"
DESCRIPTOR = "CROCHET PATTERNS"

# ---- palette (sampled from the owner's concept; names kept compatible with lane B) ----------

PALETTE: dict[str, str] = {
    "paper": "#F3EEE7",      # cream ground -- concept paper, border median (exact)
    "forest": "#2F3E33",     # ink: B, wordmark, tagline -- banner wordmark #303F38 (dE 2.7),
                             # logo wordmark #37392D (dE 6.0)
    "taupe": "#7F6851",      # CROCHET PATTERNS descriptor -- sampled #7F6851 (exact)
    "rose": "#A67372",       # dusty-rose heart -- sampled #A67372 (exact); decorative only
    "rose_deep": "#8E5A59",  # the rose, deepened to pass 4.5:1 for small text
    "yarn": "#9E8170",       # yarn strand and ball -- sampled strand #987D6C / ball #A38675
    "yarn_deep": "#7E6253",  # ball shadow #886B5C deepened: micro-mark loop, yarn wraps
    "leaf": "#4B503F",       # bramble leaves -- sampled #4B503F (exact)
    "sage": "#7A7B68",       # soft sage -- the banner's B #7A7B68 (exact)
    "sage_mist": "#CFD0C3",  # leaf veins, quiet rules
    "petal": "#FBF8F3",      # blossom -- the concept's near-white petals, lifted off the paper
    "pollen": "#A48B5A",     # blossom centre
    "berry": "#86413D",      # bramble berries -- banner berries #86413D (exact)
    "yarn_light": "#D2B9A9", # yarn on forest (reversed): >= 3:1 on forest
    "rose_light": "#DDB0AA", # heart / accent on forest (reversed)
    "surface": "#FBF8F3",    # raised card surface for pages
}

# Where each palette colour came from: name -> (concept file, crop box x0,y0,x1,y1 or None,
# sampling method, sampled hex, max CIE76 dE allowed between the palette value and the sample).
# `sample_concept()` re-runs each sample on the owner's files; the test checks both distances.
OWNER_LOGO_SHA256 = "28f301b28766acea7b0f632ceefcb1c66e271a6fba8da0c84a65c94647d35998"
OWNER_BANNER_SHA256 = "048a199133f7589cc243cb876a7ee5b0f68b5d6530929a922c79de9eda64eb98"
CONCEPT_SAMPLES: dict[str, tuple] = {
    "paper": ("logo", None, "border", "#F3EEE7", 3.0),
    "forest": ("banner", (620, 315, 1440, 390), "dark", "#303F38", 6.0),
    "taupe": ("logo", (470, 700, 1060, 725), "ink_darkest_half", "#7F6851", 3.0),
    "rose": ("logo", (750, 850, 785, 885), "ink_soft", "#A67372", 3.0),
    "leaf": ("logo", (470, 60, 1060, 560), "green", "#4B503F", 3.0),
    "berry": ("banner", (870, 40, 1180, 290), "red", "#86413D", 3.0),
    "yarn": ("logo", (540, 250, 1050, 500), "pink", "#987D6C", 6.0),
    "sage": ("banner", (870, 40, 1180, 290), "sage", "#7A7B68", 3.0),
}


def concept_paths() -> dict[str, "object"]:
    """The owner's files, if present and byte-identical to what the owner supplied.

    Read from the repository copies (`canonical_assets`, D-FB-17), so this runs on any
    machine. `BRAMBLELOOP_OWNER_BRAND_DIR` may point at another copy; it is used only when its
    bytes hash to the owner's."""
    import hashlib
    import os
    from pathlib import Path as P

    from . import canonical_assets as CA

    out = {}
    env = os.environ.get("BRAMBLELOOP_OWNER_BRAND_DIR")
    for key, role, sha in (("logo", CA.HERO_LOGO, OWNER_LOGO_SHA256),
                           ("banner", CA.STOREFRONT_BANNER, OWNER_BANNER_SHA256)):
        cands = [CA.path(role)]
        if env:
            cands.insert(0, P(env) / CA.ASSETS[role].file)
        for f in cands:
            if f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest() == sha:
                out[key] = f
                break
    return out


def sample_concept(name: str) -> str | None:
    """Re-sample one palette colour from the owner's concept with its declared method."""
    import numpy as np
    from PIL import Image

    src, box, method, _hexv, _tol = CONCEPT_SAMPLES[name]
    paths = concept_paths()
    if src not in paths:
        return None
    a = np.asarray(Image.open(paths[src]).convert("RGB")).astype(int)
    if method == "border":
        px = np.concatenate([a[:20].reshape(-1, 3), a[-20:].reshape(-1, 3)])
    else:
        x0, y0, x1, y1 = box
        r = a[y0:y1, x0:x1].reshape(-1, 3)
        paper = np.array([0xF3, 0xEE, 0xE7])
        dist = np.sqrt(((r - paper) ** 2).sum(1))
        mean = r.mean(1)
        if method == "dark":
            px = r[mean < 110]
        elif method == "ink_darkest_half":
            ink = r[dist > 60]
            px = ink[ink.mean(1) <= np.percentile(ink.mean(1), 50)]
        elif method == "ink_soft":
            px = r[dist > 40]
        elif method == "green":
            px = r[(r[:, 1] > r[:, 0] + 4) & (r[:, 1] > r[:, 2]) & (mean < 150)]
        elif method == "red":
            px = r[r[:, 0] > r[:, 1] + 50]
        elif method == "pink":
            px = r[(r[:, 0] > r[:, 1] + 18) & (mean < 200)]
        elif method == "sage":
            px = r[(r[:, 1] >= r[:, 0]) & (mean < 190) & (mean > 110)]
        else:
            raise ValueError(method)
    med = np.median(px, 0)
    return "#" + "".join(f"{int(round(v)):02X}" for v in med)


def delta_e(a: str, b: str) -> float:
    """CIE76 colour difference between two hex colours (D65)."""
    def lab(h):
        h = h.lstrip("#")
        c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        x = (0.4124 * c[0] + 0.3576 * c[1] + 0.1805 * c[2]) / 0.95047
        y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
        z = (0.0193 * c[0] + 0.1192 * c[1] + 0.9505 * c[2]) / 1.08883

        def f(t):
            return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

        return (116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))

    return math.dist(lab(a), lab(b))


VARIANTS: dict[str, dict] = {
    "colour": {"roles": {"ink": "forest", "leaf": "leaf", "rib": "sage_mist", "yarn": "yarn",
                         "yarn_line": "yarn_deep", "loop": "yarn_deep", "petal": "petal",
                         "petal_edge": "leaf", "gold": "pollen", "berry": "berry",
                         "accent_text": "taupe", "rule": "taupe", "heart": "rose",
                         "script": "forest"},
               "ground": "paper"},
    "mono": {"roles": {"ink": "forest", "leaf": "forest", "rib": "paper", "yarn": "forest",
                       "yarn_line": "paper", "loop": "forest", "petal": "paper",
                       "petal_edge": "forest", "gold": "forest", "berry": "forest",
                       "accent_text": "forest", "rule": "forest", "heart": "forest",
                       "script": "forest"},
             "ground": "paper"},
    "reversed": {"roles": {"ink": "paper", "leaf": "sage_mist", "rib": "forest",
                           "yarn": "yarn_light", "yarn_line": "forest", "loop": "yarn_light",
                           "petal": "paper", "petal_edge": "forest", "gold": "pollen",
                           "berry": "rose_light", "accent_text": "yarn_light",
                           "rule": "yarn_light", "heart": "rose_light", "script": "paper"},
                 "ground": "forest"},
}

TYPOGRAPHY: dict[str, dict] = {
    "monogram": {"family": "Playfair Display", "font": "playfair_bold", "weight": 700,
                 "licence": "OFL-1.1", "note": "Reserved Font Name: used only as outlined "
                 "artwork, never shipped as a modified font"},
    "micro_monogram": {"family": "Playfair Display", "font": "playfair_black", "weight": 900,
                       "licence": "OFL-1.1", "note": "the same B, heaviest cut"},
    "wordmark": {"family": "Cormorant Garamond", "font": "cormorant_semibold", "weight": 600,
                 "case": "upper", "tracking_em": 0.17, "licence": "OFL-1.1"},
    "descriptor": {"family": "Work Sans", "font": "worksans", "case": "upper",
                   "tracking_em": 0.32, "licence": "OFL-1.1"},
    "tagline": {"family": "Allison", "font": "allison", "licence": "OFL-1.1",
                "note": "signature script, outlined; legible only from ~22 px letter height, "
                        "so it appears in the hero lockup and banner, never in the icon or the "
                        "phone header"},
}

# ---- geometry helpers ---------------------------------------------------------------------


def _B(font: str, cap: float, left: float, baseline: float) -> Path:
    """The B with its ink box's left edge at `left` and the given cap height."""
    met = T.font_metrics(font)
    size = cap * met["upm"] / met["cap_height"]
    raw = _close_waist_slit(T.set_text(font, "B", size, 0, baseline))
    x0 = raw.bbox()[0]
    return raw.transformed(tx=left - x0)


def _stem_inner_x(B: Path) -> float:
    """x of the stem's inner (right) edge: the leftmost point of the counter contour."""
    ops = B.ops
    a = [i for i, op in enumerate(ops) if op[0] == "M"][1]
    return min(q[0] for op in ops[a:] for q in op[1:])


def _close_waist_slit(p: Path) -> Path:
    """Playfair's B carries a hairline slit where the two counters meet, cut into the stem.
    At logo scale it reads as a printing fault and at 40 px as a break in the stem, so the
    identity's B closes it: points of the counter contour left of the stem's inner edge are
    moved onto that edge. (A deliberate, documented drawing change to the letter.)"""
    ops = list(p.ops)
    starts = [i for i, op in enumerate(ops) if op[0] == "M"]
    if len(starts) < 2:
        return p
    a = starts[1]
    pts = [q for op in ops[a:] for q in op[1:]]
    xs = sorted({round(q[0], 6) for q in pts})
    if len(xs) < 2:
        return p
    lo, edge = xs[0], xs[1]
    out = Path()
    out.ops = ops[:a] + [(op[0],) + tuple((edge if round(q[0], 6) == lo else q[0], q[1])
                                          for q in op[1:]) for op in ops[a:]]
    return out


def _text(font: str, text: str, size: float, x: float, baseline: float, *,
          tracking: float = 0.0, anchor: str = "start", kern=None) -> Path:
    return T.set_text(font, text, size, x, baseline, tracking=tracking, anchor=anchor, kern=kern)


def _berries(m: Mark, pts, r: float, role: str = "berry", hi_role: str | None = None) -> None:
    for (x, y) in pts:
        m.add(Circle(x, y, r, role))
    if hi_role:
        for (x, y) in pts:
            m.add(Circle(x - r * 0.32, y - r * 0.32, r * 0.22, hi_role))


def _heart(cx: float, cy: float, s: float) -> Path:
    """A small heart, `s` wide, as in both concept images."""
    h = s * 0.9
    return (Path().M(cx, cy + h * 0.5)
            .C(cx - s * 0.08, cy + h * 0.38, cx - s * 0.5, cy + h * 0.08, cx - s * 0.5, cy - h * 0.16)
            .C(cx - s * 0.5, cy - h * 0.42, cx - s * 0.26, cy - h * 0.52, cx - s * 0.13, cy - h * 0.5)
            .C(cx - s * 0.04, cy - h * 0.48, cx, cy - h * 0.36, cx, cy - h * 0.28)
            .C(cx, cy - h * 0.36, cx + s * 0.04, cy - h * 0.48, cx + s * 0.13, cy - h * 0.5)
            .C(cx + s * 0.26, cy - h * 0.52, cx + s * 0.5, cy - h * 0.42, cx + s * 0.5, cy - h * 0.16)
            .C(cx + s * 0.5, cy + h * 0.08, cx + s * 0.08, cy + h * 0.38, cx, cy + h * 0.5).Z())


def _ball(m: Mark, cx: float, cy: float, r: float, lw: float, role="yarn",
          line_role="yarn_line") -> None:
    """Yarn ball: disc + wraps (arcs kept inside the rim), two wrap directions."""
    m.add(Circle(cx, cy, r, role))
    for ang, k in ((-30, -0.5), (-30, -0.12), (-30, 0.26), (-30, 0.6), (62, -0.3), (62, 0.18)):
        a = math.radians(ang)
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        off = k * r
        half = math.sqrt(max(0.0, (0.88 * r) ** 2 - off ** 2))
        p0 = (cx + nx * off - ux * half, cy + ny * off - uy * half)
        p1 = (cx + nx * off + ux * half, cy + ny * off + uy * half)
        c = (cx + nx * (off + 0.22 * r), cy + ny * (off + 0.22 * r))
        m.add(Stroke(Path().M(*p0).Q(c[0], c[1], *p1), lw, line_role))


def _sprig_leaves(m: Mark, stem_pts, specs, rib_w: float) -> None:
    """Leaves along a stem polyline: (t, side, length, width, bend)."""
    n = len(stem_pts) - 1
    for t, side, L, W, bend in specs:
        i = min(n - 1, int(t * n))
        (x0, y0), (x1, y1) = stem_pts[i], stem_pts[i + 1]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        _leaf(m, (x0, y0), ang + side * 48, L, W, "leaf", "rib", rib_w, bend=bend * side)


def _sample(pts, t: float):
    n = len(pts) - 1
    i = min(n - 1, int(t * n))
    return pts[i]


def _infinity(cx: float, cy: float, a: float, b: float, rot: float, skew: float,
              t0: float, t1: float, n: int = 72) -> list:
    """A figure-of-eight (Gerono-style lemniscate) whose right lobe is larger by `skew`."""
    r = math.radians(rot)
    out = []
    for i in range(n + 1):
        t = t0 + (t1 - t0) * i / n
        x = a * math.cos(t) / (1 + math.sin(t) ** 2)
        y = b * 2 * math.sin(t) * math.cos(t) / (1 + math.sin(t) ** 2)
        if x > 0:
            x, y = x * (1 + skew), y * (1 + skew)
        out.append((cx + x * math.cos(r) - y * math.sin(r), cy + x * math.sin(r) + y * math.cos(r)))
    return out


# ---- the full monogram (hero / banner / About scale) ---------------------------------------


def monogram() -> Mark:
    """B + bramble growth (leaves, blossoms, berries) + yarn figure-of-eight ending in a ball."""
    m = Mark("o1-monogram", 1000, 1000, title="Brambleloop monogram")
    cap, left, base = 560.0, 318.0, 790.0
    B = _B("playfair_bold", cap, left, base)
    halo = 14.0
    yw = 11.0

    # yarn: one strand drawn as a figure-of-eight through the letter. It starts hidden behind
    # the lower sprig, passes BEHIND the stem, turns in a small lobe left of the letter, comes
    # back OVER the stem and the lower bowl, swings out in the large right lobe and ends in the
    # ball -- the interlace the concept shows, with real over/under gaps.
    under_pts = [(452, 700), (380, 680), (290, 650), (222, 652)]
    over_pts = [(222, 652), (180, 690), (206, 742), (300, 748), (420, 712), (560, 640),
                (700, 560), (820, 500), (902, 500), (928, 556), (896, 610), (858, 628)]
    under = cubic_through(under_pts)
    over = cubic_through(over_pts)
    ball = (842, 650)
    m.add(Stroke(under, yw, "yarn"))
    m.add(Knockout([Fill(B, "x", "nonzero"), Stroke(B, halo, "x")]))
    m.add(Fill(B, "ink", "nonzero"))
    m.add(Knockout([Stroke(over, yw + halo, "x")]))
    m.add(Stroke(over, yw, "yarn"))

    # bramble: a stem climbs the left of the B from its foot to above its top serif
    stem_pts = [(372, 868), (330, 790), (282, 690), (250, 590), (246, 480), (262, 370),
                (296, 270), (330, 190), (350, 120)]
    stem = cubic_through(stem_pts)
    m.add(Knockout([Stroke(stem, 7 + halo, "x")]))
    m.add(Stroke(stem, 7, "leaf"))
    _sprig_leaves(m, stem_pts, (
        (0.10, -1, 96, 30, 0.05), (0.22, 1, 104, 32, 0.05), (0.36, -1, 92, 28, 0.04),
        (0.52, 1, 86, 26, 0.05), (0.66, -1, 98, 30, 0.04), (0.80, 1, 80, 24, 0.05),
        (0.92, -1, 70, 21, 0.04)), 2.4)
    # top: a leaf pair and a closed bud at the tip
    _leaf(m, (350, 120), -100, 92, 22, "leaf", "rib", 2.4, bend=0.04)
    _leaf(m, (350, 124), -40, 70, 18, "leaf", "rib", 2.4, bend=-0.04)
    _berries(m, [(338, 112), (356, 100), (352, 120)], 10, "berry")
    # blossoms on the left (as in the concept) -- drawn after leaves so they sit on top
    _blossom(m, 205, 478, 54, 12, "petal", "petal_edge", "gold", 3.2)
    _blossom(m, 300, 330, 36, -20, "petal", "petal_edge", "gold", 2.8)
    # berry clusters (banner variant)
    _berries(m, [(214, 640), (236, 652), (218, 664), (240, 676), (200, 656)], 13, "berry")
    # lower-right sprig: from the foot of the B along the bottom bowl to the ball
    low = [(396, 862), (470, 872), (548, 860), (626, 836), (700, 804)]
    lp = cubic_through(low)
    m.add(Knockout([Stroke(lp, 6 + halo, "x")]))
    m.add(Stroke(lp, 6, "leaf"))
    _sprig_leaves(m, low, ((0.05, 1, 74, 22, 0.05), (0.32, -1, 84, 24, 0.05),
                           (0.58, 1, 72, 21, 0.05), (0.8, -1, 64, 19, 0.05)), 2.2)
    _leaf(m, (700, 804), -22, 76, 21, "leaf", "rib", 2.2, bend=0.04)
    _blossom(m, 520, 858, 44, 4, "petal", "petal_edge", "gold", 3.0)
    _berries(m, [(716, 776), (736, 786), (720, 798), (740, 766)], 11, "berry")
    # the ball (in front of everything it touches)
    m.add(Knockout([Circle(ball[0], ball[1], 50 + halo / 2, "x")]))
    _ball(m, ball[0], ball[1], 50, 3.6)
    return trim(m, 20)


# ---- the micro-mark (Etsy shop icon, 40-70 px) ----------------------------------------------


def micro_mark() -> Mark:
    """The SAME B, simplified for 40-70 px: heaviest Playfair cut, two large bramble leaves at
    the top of the stem, one bold loop of yarn through the letter ending in the ball.

    Rules that make it survive 40 px: every stroke >= 2 px at 40 px, every colour >= 3:1 on
    cream, every overlap separated by a knockout gap so the one-ink version keeps its shapes,
    everything inside the circular crop."""
    m = Mark("o1-micro", ICON, ICON, title="Brambleloop")
    cap = 300.0
    B = _B("playfair_black", cap, 0, 0)
    x0, y0, x1, y1 = B.bbox()
    bw = x1 - x0
    left = 250 - bw / 2 + 14
    base = 250 + cap / 2 + 30
    B = _B("playfair_black", cap, left, base)
    halo = 22.0
    lw = 30.0
    # one bold loop, as the concept's strand: it leaves the letter from BEHIND the stem, turns
    # left of the letter, and sweeps back OVER the stem foot and up across the lower bowl to
    # the ball at the right (a real over/under interlace with knockout gaps)
    ball = (404.0, 318.0)
    under = cubic_through([(_stem_inner_x(B) - 20, 300), (200, 296), (130, 312), (98, 344)])
    over = cubic_through([(98, 344), (116, 376), (184, 384), (272, 366), (346, 336), ball])
    m.add(Stroke(under, lw, "loop"))
    m.add(Knockout([Fill(B, "x", "nonzero"), Stroke(B, halo, "x")]))
    m.add(Fill(B, "ink", "nonzero"))
    m.add(Knockout([Stroke(over, lw + halo, "x")]))
    m.add(Stroke(over, lw, "loop"))
    bx, by = ball
    m.add(Knockout([Circle(bx, by, 48 + halo / 2, "x")]))
    m.add(Circle(bx, by, 48, "loop"))
    # wraps on the ball: knocked out of the ball (reads in one ink too)
    m.add(Knockout([Stroke(Path().M(bx - 36, by - 16).Q(bx, by - 36, bx + 32, by - 32), 9, "x"),
                    Stroke(Path().M(bx - 42, by + 12).Q(bx, by - 8, bx + 42, by + 4), 9, "x")]))
    # two large bramble leaves from the top of the stem, with a halo
    root = (left + 34, base - cap + 6)
    leaves = [leaf_path((root[0] - 6, root[1]), -158, 96, 30, 0.06),
              leaf_path((root[0] + 6, root[1] - 4), -72, 86, 27, -0.06)]
    m.add(Knockout([Fill(p, "x") for p in leaves] + [Stroke(p, halo, "x") for p in leaves]))
    for p in leaves:
        m.add(Fill(p, "leaf"))
    return m


# ---- wordmark, descriptor, lockups --------------------------------------------------------

WORD_KERN = {"LO": -0.02, "AM": -0.01, "OP": -0.01}


def wordmark() -> Mark:
    font, size, tr = "cormorant_semibold", 100.0, 0.17
    w = T.measure(font, "BRAMBLELOOP", size, tr, WORD_KERN)
    cap = T.font_metrics(font)["cap_height"] * size / 1000
    pad = 6
    m = Mark("o1-wordmark", w + 2 * pad, cap + 2 * pad, title="Brambleloop")
    m.add(Fill(_text(font, "BRAMBLELOOP", size, pad, pad + cap, tracking=tr, kern=WORD_KERN),
               "ink", "nonzero"))
    return m


def hero_lockup(tagline: str | None = TAGLINE, heart: bool = True) -> Mark:
    """The full hero lockup, as in the concept: monogram, BRAMBLELOOP, CROCHET PATTERNS between
    hairlines, the script tagline and a small heart between short hairlines."""
    mg, wm = monogram(), wordmark()
    W = 1400.0
    ws = (W * 0.80) / wm.width
    es = (W * 0.42) / mg.width
    eh = mg.height * es
    wh = wm.height * ws
    y_word = eh + 34
    desc = 34.0
    y_desc = y_word + wh + 34 + desc * 0.7
    H = y_desc + 28
    # the script is sized so the tagline spans the wordmark's width, as in the concept
    tag_size = (W * 0.80) / T.measure("allison", tagline, 100.0) * 100.0 if tagline else 0.0
    tag_size = min(tag_size, 170.0)
    if tagline:
        y_tag = H + 30 + tag_size * 0.62
        H = y_tag + tag_size * 0.30
    if heart:
        y_heart = H + 34
        H = y_heart + 30
    m = Mark("o1-hero", W, H, title="Brambleloop crochet patterns")
    m.elements += place(mg, es, (W - mg.width * es) / 2, 0)
    m.elements += place(wm, ws, (W - wm.width * ws) / 2, y_word)
    _hairline_descriptor(m, "worksans", DESCRIPTOR, desc, W / 2, y_desc, 0.32,
                         W * 0.80 / 2 - T.measure("worksans", DESCRIPTOR, desc, 0.32) / 2 - 40,
                         40, 2.0, "accent_text", "rule")
    if tagline:
        m.add(Fill(_text("allison", tagline, tag_size, W / 2, y_tag, anchor="middle"),
                   "script", "nonzero"))
    if heart:
        m.add(Fill(_heart(W / 2, y_heart, 26), "heart"))
        for sgn in (-1, 1):
            m.add(Stroke(Path().M(W / 2 + sgn * 34, y_heart).L(W / 2 + sgn * 150, y_heart), 1.8,
                         "rule"))
    return trim(m, 24)


def lockup_horizontal() -> Mark:
    """Monogram-B micro-mark + wordmark + descriptor on one line: header / footer / email."""
    icon, wm = micro_mark(), wordmark()
    it = trim(icon, 0)
    H = wm.height
    desc = 30.0
    block_h = H + 26 + desc
    s = block_h * 1.25 / it.height
    gap = H * 0.55
    W = it.width * s + gap + wm.width
    m = Mark("o1-lockup-h", W, max(block_h, it.height * s), title="Brambleloop crochet patterns")
    oy_i = (m.height - it.height * s) / 2
    m.elements += place(it, s, 0, oy_i)
    oy = (m.height - block_h) / 2
    x_text = it.width * s + gap
    m.elements += place(wm, 1.0, x_text, oy)
    cx = x_text + wm.width / 2
    _hairline_descriptor(m, "worksans", DESCRIPTOR, desc, cx, oy + block_h, 0.32,
                         wm.width / 2 - T.measure("worksans", DESCRIPTOR, desc, 0.32) / 2 - 22,
                         20, 1.6, "accent_text", "rule")
    return trim(m, 8)


def motif() -> Mark:
    """Seamless bramble tile for packaging and PDF covers: leaf pairs, berries, small loops."""
    from .directions import _lemniscate

    W = H = 240.0
    m = Mark("o1-motif", W, H, title="Brambleloop bramble pattern")
    tmp = Mark("t", W, H)
    for (x, y, ang) in ((60, 60, -35), (180, 180, 145)):
        _leaf(tmp, (x, y), ang, 42, 13, "leaf", "rib", 1.4, bend=0.05)
        _leaf(tmp, (x, y), ang + 70, 32, 10, "leaf", "rib", 1.4, bend=-0.05)
        _berries(tmp, [(x - 5, y + 9), (x + 4, y + 12), (x - 1, y + 17)], 3.8)
    for (x, y, rr) in ((180, 60, -20), (60, 180, 160)):
        tmp.add(Stroke(cubic_through(_lemniscate(x, y, 30, 12, rr, 0.3, 2 * math.pi - 0.3)),
                       2.4, "yarn"))
    for dx in (-W, 0.0, W):
        for dy in (-H, 0.0, H):
            m.elements += [_moved(e, 1.0, dx, dy) for e in tmp.elements]
    return m


class OwnerDirection(Direction):
    """A Direction whose stacked lockup is the concept's hero lockup."""

    def lockup_horizontal(self) -> Mark:
        return lockup_horizontal()

    def lockup_stacked(self, tagline: str | None = None) -> Mark:
        # The tagline is the owner's (D-FB-16); a caller may pass lane C's copy instead. A
        # tagline the outlined script cannot set (missing glyphs) falls back to the owner's.
        t = tagline if tagline and T.has_glyphs("allison", tagline) else TAGLINE
        return hero_lockup(t)


O1 = OwnerDirection(
    id=DIRECTION_ID,
    name="Bramble B (owner concept)",
    concept=("The owner's concept, professionalised: an elegant high-contrast serif B with "
             "bramble growth (leaves, blossoms, berries) and a yarn figure-of-eight ending in a "
             "small ball; BRAMBLELOOP in spaced serif capitals; CROCHET PATTERNS between "
             "hairlines; 'Patterns for a More Handmade Life' in a fine script; a small heart."),
    source=("Owner concept images 2026-10-06 (owner_logo_concept.png sha256 28f301b2..., "
            "owner_banner_concept.png sha256 048a1991...), owner decision D-FB-16; rebuilt as "
            "original vector geometry + outlined OFL type. The owner's raster is not embedded "
            "or traced."),
    palette=PALETTE,
    variants=VARIANTS,
    typography=TYPOGRAPHY,
    build_icon=micro_mark,
    build_emblem=monogram,
    build_wordmark=wordmark,
    build_motif=motif,
    descriptor=DESCRIPTOR,
    descriptor_font="worksans",
    tagline_font="allison",
)
