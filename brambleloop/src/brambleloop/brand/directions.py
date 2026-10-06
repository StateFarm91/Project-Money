"""Brambleloop identity directions -- four genuinely different answers to one brief.

Each direction is a complete small system: an icon (the Etsy shop icon, built to survive 40 px),
a primary emblem (banner/About scale), a wordmark, horizontal and stacked lockups, a repeating
motif tile, a palette with named roles, typography, and usage rules. Everything is geometry plus
outlined open-licence type (`typeset`), so it is deterministic, needs no image model and no
spend, and can be measured by `judge`.

  D1  briar-monogram  The owner's concept (2026-10-06), rebuilt as clean vector: a high-contrast
                      serif B, a bramble sprig in blossom, and a strand of yarn that loops through
                      the letter and ends in a small ball. Spaced serif capitals; small-caps
                      descriptor between hairlines; italic tagline. Its 40 px problem is solved
                      by a separate, simplified monogram icon that keeps the B + loop idea.
  D2  chain-link      Craft-literal but abstract: two elongated loops interlocked exactly as a
                      crochet chain stitch, drawn over-under. Lower-case geometric sans.
  D3  drupelet        "Bramble" made of stitches: a blackberry built from bobble-stitch
                      drupelets whose stem curls into a single loop. Warm, rounded serif.
  D4  tapestry-b      A capital B woven as a tapestry-crochet chart of V stitches. Small-caps
                      serif. The most graphic, least illustrative option.

All four avoid the generic yarn ball / hook clip-art / flower sprig except where D1 transforms
them into the monogram the owner asked for.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from . import typeset as T
from .vector import (Circle, Fill, Knockout, Mark, Path, Stroke, circle_path, closed_through,
                     cubic_through, ellipse_path, leaf_midrib, leaf_path)

ICON = 500.0


@dataclass
class Direction:
    id: str
    name: str
    concept: str
    source: str
    palette: dict[str, str]           # named colours (hex)
    variants: dict[str, dict]         # variant -> {"roles": {role: palette-name}, "ground": name|None}
    typography: dict[str, dict]
    build_icon: Callable[[], Mark]
    build_emblem: Callable[[], Mark]
    build_wordmark: Callable[[], Mark]
    build_motif: Callable[[], Mark]
    descriptor: str = "CROCHET PATTERNS"
    descriptor_font: str = "worksans"
    tagline_font: str = "lora_italic"
    emblem_scale: float = 0.62          # emblem width as a share of the wordmark width
    usage_rules: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    def colours(self, variant: str = "colour") -> dict[str, str]:
        v = self.variants[variant]
        return {role: self.palette[name] for role, name in v["roles"].items()}

    def ground(self, variant: str = "colour") -> str | None:
        g = self.variants[variant]["ground"]
        return self.palette[g] if g else None

    # ---- the system's pieces ------------------------------------------------------------
    def icon(self) -> Mark:
        return self.build_icon()

    def emblem(self) -> Mark:
        return self.build_emblem()

    def wordmark(self) -> Mark:
        return self.build_wordmark()

    def motif(self) -> Mark:
        return self.build_motif()

    def lockup_horizontal(self) -> Mark:
        """Icon + wordmark on one line: the phone header and email footer form."""
        return _lockup_h(self.icon(), self.wordmark(), gap_ratio=0.45, icon_scale=2.1,
                         name=f"{self.id}-lockup-h")

    def lockup_stacked(self, tagline: str | None = None) -> Mark:
        """Emblem over wordmark over descriptor (and an optional tagline): banner/About form.

        The tagline text is lane C's copy; it is a parameter here, never hard-coded."""
        return _stacked(self, tagline)


# ---- shared helpers --------------------------------------------------------------------------


def _hairline_descriptor(m: Mark, font: str, text: str, size: float, cx: float, baseline: float,
                         tracking: float, rule_len: float, gap: float, rule_w: float,
                         role: str, rule_role: str) -> None:
    w = T.measure(font, text, size, tracking)
    m.add(Fill(T.set_text(font, text, size, cx, baseline, tracking=tracking, anchor="middle"),
               role))
    cap = T.font_metrics(font)["cap_height"] * size / 1000
    y = baseline - cap / 2
    for sgn in (-1, 1):
        x0 = cx + sgn * (w / 2 + gap)
        x1 = x0 + sgn * rule_len
        m.add(Stroke(Path().M(x0, y).L(x1, y), rule_w, rule_role))


def _lockup_h(icon: Mark, word: Mark, gap_ratio: float = 0.32, icon_scale: float = 1.0,
              name: str = "lockup") -> Mark:
    """Icon left of wordmark, icon height = wordmark height * icon_scale, centred vertically."""
    H = word.height
    s = H * icon_scale / icon.height
    iw = icon.width * s
    gap = H * gap_ratio
    m = Mark(name, iw + gap + word.width, max(H, icon.height * s))
    oy_i = (m.height - icon.height * s) / 2
    oy_w = (m.height - H) / 2
    for e in icon.elements:
        m.elements.append(_moved(e, s, 0, oy_i))
    for e in word.elements:
        m.elements.append(_moved(e, 1.0, iw + gap, oy_w))
    return m


def _stacked(d: "Direction", tagline: str | None) -> Mark:
    em, wm = d.emblem(), d.wordmark()
    W = 1400.0
    ws = (W * 0.84) / wm.width
    es = (wm.width * ws * d.emblem_scale) / em.width
    eh = em.height * es
    wh = wm.height * ws
    desc = 40.0
    y_word = eh + 70
    y_desc = y_word + wh + 46 + desc * 0.66
    H = y_desc + 40
    tag_size = 62.0
    if tagline:
        H += tag_size * 1.6
    m = Mark(f"{d.id}-stacked", W, H, title="Brambleloop crochet patterns")
    m.elements += place(em, es, (W - em.width * es) / 2, 0)
    m.elements += place(wm, ws, (W - wm.width * ws) / 2, y_word)
    _hairline_descriptor(m, d.descriptor_font, d.descriptor, desc, W / 2, y_desc, 0.3, 210, 34,
                         2.4, "accent_text", "rule")
    if tagline:
        m.add(Fill(T.set_text(d.tagline_font, tagline, tag_size, W / 2, H - 30,
                              anchor="middle"), "ink"))
    return m


def _moved(e, s: float, tx: float, ty: float):
    if isinstance(e, Knockout):
        return Knockout([_moved(x, s, tx, ty) for x in e.shapes])
    if isinstance(e, Circle):
        return Circle(e.cx * s + tx, e.cy * s + ty, e.r * s, e.role)
    if isinstance(e, Stroke):
        return Stroke(e.path.transformed(sx=s, tx=tx, ty=ty), e.width * s, e.role)
    return Fill(e.path.transformed(sx=s, tx=tx, ty=ty), e.role, getattr(e, "rule", "evenodd"))


def trim(mark: Mark, pad: float) -> Mark:
    """Shrink the canvas to the drawn content plus `pad` (so lockups space by ink, not box)."""
    from .vector import all_points

    pts = list(all_points(mark))
    x0 = min(p[0] for p in pts) - pad
    y0 = min(p[1] for p in pts) - pad
    x1 = max(p[0] for p in pts) + pad
    y1 = max(p[1] for p in pts) + pad
    out = Mark(mark.name, x1 - x0, y1 - y0, title=mark.title)
    out.elements = [_moved(e, 1.0, -x0, -y0) for e in mark.elements]
    return out


def place(mark: Mark, s: float, tx: float, ty: float) -> list:
    return [_moved(e, s, tx, ty) for e in mark.elements]


def _yarn_ball(m: Mark, cx: float, cy: float, r: float, role: str, line_role: str,
               lw: float) -> None:
    """A ball of yarn: a disc with wraps drawn as arcs that stay inside the rim."""
    m.add(Circle(cx, cy, r, role))
    for ang, k in ((-35, 0.0), (-35, 0.42), (-35, -0.42), (55, 0.22), (55, -0.3)):
        a = math.radians(ang)
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        off = k * r
        half = math.sqrt(max(0.0, (0.86 * r) ** 2 - off ** 2))
        p0 = (cx + nx * off - ux * half, cy + ny * off - uy * half)
        p1 = (cx + nx * off + ux * half, cy + ny * off + uy * half)
        bow = 0.25 * r
        c = (cx + nx * (off + bow), cy + ny * (off + bow))
        m.add(Stroke(Path().M(*p0).Q(c[0], c[1], *p1), lw, line_role))


def _blossom(m: Mark, cx: float, cy: float, r: float, rot: float, petal_role: str,
             edge_role: str, centre_role: str, edge_w: float) -> None:
    """Five-petal bramble blossom: rounded petals, an edge line, a seeded centre."""
    petals = []
    for i in range(5):
        a = math.radians(rot + i * 72)
        px, py = cx + math.cos(a) * r * 0.52, cy + math.sin(a) * r * 0.52
        petals.append(ellipse_path(px, py, r * 0.52, r * 0.40, rot + i * 72))
    for p in petals:
        m.add(Stroke(p, edge_w, edge_role))
    for p in petals:
        m.add(Fill(p, petal_role))
    m.add(Circle(cx, cy, r * 0.2, centre_role))
    for i in range(7):
        a = math.radians(rot + 20 + i * 51.4)
        m.add(Circle(cx + math.cos(a) * r * 0.27, cy + math.sin(a) * r * 0.27, r * 0.05,
                     centre_role))


def _leaf(m: Mark, base, ang, length, width, role, rib_role, rib_w, bend=0.0) -> None:
    m.add(Fill(leaf_path(base, ang, length, width, bend), role))
    if rib_role:
        m.add(Stroke(leaf_midrib(base, ang, length, bend), rib_w, rib_role))


def _along(pts, t):
    """Point and tangent angle at fraction t of a polyline (by vertex index)."""
    n = len(pts) - 1
    i = min(n - 1, int(t * n))
    (x0, y0), (x1, y1) = pts[i], pts[i + 1]
    return (x0, y0), math.degrees(math.atan2(y1 - y0, x1 - x0))


# ============================================================================================
# D1  briar-monogram  (owner concept)
# ============================================================================================

D1_PALETTE = {
    "forest": "#2F3E33",     # ink: letterform, wordmark
    "sage": "#6F8468",       # leaves
    "sage_mist": "#C9D1BF",  # leaf ribs, quiet rules
    "rose": "#A86B5C",       # yarn (dusty terracotta-rose)
    "rose_deep": "#7E4A3E",  # yarn wraps, small text accents
    "rose_light": "#D49A8A", # yarn on the dark (reversed) ground: 4.7:1 on forest
    "petal": "#FFFCF6",      # blossom
    "paper": "#F6F0E6",      # warm cream ground
    "berry": "#7A2E3A",      # bramble fruit
    "gold": "#B88A3E",       # blossom centre
}


def _d1_B(size: float, x: float, baseline: float) -> Path:
    return T.set_text("gloock", "B", size, x, baseline)


def d1_emblem() -> Mark:
    """Banner/About scale: B + blossoming bramble + yarn figure-of-eight ending in a ball."""
    m = Mark("d1-emblem", 1000, 1000, title="Brambleloop monogram")
    size = 700.0
    bx = 520 - 632 * size / 1000 / 2
    base = 770.0
    m.add(Fill(_d1_B(size, bx, base), "ink"))
    # --- yarn: a figure-of-eight through the letter, crossing over it, ending in a ball
    cx, cy, a, b = 545, 640, 285, 112
    rot = math.radians(-14)

    def lem(t):
        x = a * math.cos(t) / (1 + math.sin(t) ** 2)
        y = b * 2 * math.sin(t) * math.cos(t) / (1 + math.sin(t) ** 2)
        return (cx + x * math.cos(rot) - y * math.sin(rot),
                cy + x * math.sin(rot) + y * math.cos(rot))

    n = 64
    t0, t1 = 0.6, 2 * math.pi - 0.02
    pts = [lem(t0 + (t1 - t0) * i / n) for i in range(n + 1)]
    end = pts[-1]
    ball = (end[0] + 78, end[1] + 6)
    tail = [(end[0] + 30, end[1] + 16), (ball[0] - 30, ball[1] + 10)]
    half = n // 2
    first = cubic_through(pts[:half + 1])
    second = cubic_through(pts[half:] + tail)
    yw = 12
    m.add(Knockout([Stroke(first, yw + 16, "x")]))
    m.add(Stroke(first, yw, "yarn"))
    m.add(Knockout([Stroke(second, yw + 16, "x")]))
    m.add(Stroke(second, yw, "yarn"))
    # --- the bramble sprig, in front of the letter on the left
    stem_pts = [(262, 865), (238, 760), (240, 640), (262, 520), (300, 410), (348, 315),
                (398, 238)]
    stem = cubic_through(stem_pts)
    m.add(Knockout([Stroke(stem, 11 + 14, "x")]))
    m.add(Stroke(stem, 11, "leaf"))
    for t, side, L, W in ((0.1, 1, 104, 30), (0.26, -1, 118, 32), (0.44, 1, 92, 26),
                          (0.6, -1, 112, 30), (0.77, -1, 84, 24), (0.86, 1, 70, 20)):
        (px, py), ang = _along(stem_pts, t)
        _leaf(m, (px, py), ang + side * 52, L * 1.18, W * 1.0, "leaf", "rib", 3.4,
              bend=0.05 * side)
    _blossom(m, 214, 470, 60, 8, "petal", "leaf", "gold", 5)
    for (x, y, r) in ((402, 222, 18), (426, 238, 15), (404, 252, 14), (382, 240, 12)):
        m.add(Circle(x, y, r, "berry"))
    # lower-right sprig
    _leaf(m, (640, 812), -6, 128, 22, "leaf", "rib", 3.2, bend=-0.05)
    _leaf(m, (640, 812), 34, 96, 18, "leaf", "rib", 3.2, bend=0.05)
    _leaf(m, (640, 812), 110, 76, 15, "leaf", "rib", 3.2, bend=0.04)
    _blossom(m, 628, 812, 46, -14, "petal", "leaf", "gold", 4.5)
    m.add(Knockout([Circle(ball[0], ball[1], 56, "x")]))
    _yarn_ball(m, ball[0], ball[1], 46, "yarn", "yarn_line", 4.5)
    return trim(m, 24)


def d1_icon() -> Mark:
    """The 40 px answer: the same B, held in one loop of yarn drawn out of a small ball at the
    lower right; a leaf pair rides the loop to keep the bramble. Nothing finer than the strand
    survives at 40 px, so nothing finer is drawn. Every overlap is separated by a knockout, so
    the one-colour version holds its shapes."""
    m = Mark("d1-icon", ICON, ICON, title="Brambleloop")
    cx, cy, r = 250.0, 248.0, 180.0
    yw = 25
    halo = 20
    ball_a = math.radians(42)
    ball = (cx + r * math.cos(ball_a), cy + r * math.sin(ball_a))
    m.add(Stroke(circle_path(cx, cy, r), yw, "yarn"))
    size = 400.0
    gw, cap = 632 * size / 1000, 750 * size / 1000
    B = _d1_B(size, cx - gw / 2 + 2, cy + cap / 2)
    m.add(Knockout([Fill(B, "x"), Stroke(B, halo, "x")]))
    m.add(Fill(B, "ink"))
    m.add(Knockout([Circle(ball[0], ball[1], 46 + halo / 2, "x")]))
    m.add(Circle(ball[0], ball[1], 44, "yarn"))
    la = math.radians(-128)
    lb = (cx + r * math.cos(la), cy + r * math.sin(la))
    leaves = [leaf_path(lb, -160, 84, 24), leaf_path(lb, -102, 64, 19)]
    m.add(Knockout([Fill(p, "x") for p in leaves] + [Stroke(p, halo, "x") for p in leaves]))
    for p in leaves:
        m.add(Fill(p, "leaf"))
    return m


def d1_wordmark() -> Mark:
    font, size, tr = "baskerville", 100.0, 0.16
    kern = {"LO": -0.03, "OO": -0.01, "AM": -0.02}
    w = T.measure(font, "BRAMBLELOOP", size, tr, kern)
    cap = T.font_metrics(font)["cap_height"] * size / 1000
    pad = 6
    m = Mark("d1-wordmark", w + 2 * pad, cap + 2 * pad, title="Brambleloop")
    m.add(Fill(T.set_text(font, "BRAMBLELOOP", size, pad, pad + cap, tracking=tr, kern=kern),
               "ink"))
    return m


def _lemniscate(cx: float, cy: float, a: float, b: float, rot_deg: float, t0: float = 0.0,
                t1: float = 2 * math.pi, n: int = 48) -> list:
    rot = math.radians(rot_deg)
    out = []
    for i in range(n + 1):
        t = t0 + (t1 - t0) * i / n
        x = a * math.cos(t) / (1 + math.sin(t) ** 2)
        y = b * 2 * math.sin(t) * math.cos(t) / (1 + math.sin(t) ** 2)
        out.append((cx + x * math.cos(rot) - y * math.sin(rot),
                    cy + x * math.sin(rot) + y * math.cos(rot)))
    return out


def d1_motif() -> Mark:
    """Seamless tile: leaf pairs, berries and small figure-of-eight loops on a half-drop grid.
    Every element is drawn at its wrapped neighbours too, so edges join without seams."""
    W = H = 240.0
    m = Mark("d1-motif", W, H, title="Brambleloop bramble pattern")
    els: list = []
    tmp = Mark("t", W, H)
    for (x, y, ang) in ((60, 60, -35), (180, 180, 145)):
        _leaf(tmp, (x, y), ang, 40, 12, "leaf", "rib", 1.4, bend=0.05)
        _leaf(tmp, (x, y), ang + 70, 32, 10, "leaf", "rib", 1.4, bend=-0.05)
        tmp.add(Circle(x - 4, y + 8, 4.2, "berry"))
        tmp.add(Circle(x + 4, y + 11, 3.6, "berry"))
    for (x, y, r) in ((180, 60, -20), (60, 180, 160)):
        tmp.add(Stroke(cubic_through(_lemniscate(x, y, 30, 12, r, 0.3, 2 * math.pi - 0.3)),
                       2.6, "yarn"))
    els = tmp.elements
    for dx in (-W, 0.0, W):
        for dy in (-H, 0.0, H):
            m.elements += [_moved(e, 1.0, dx, dy) for e in els]
    return m


D1 = Direction(
    id="D1-briar-monogram",
    name="Briar Monogram",
    concept=("A high-contrast serif B entwined with a blossoming bramble sprig and a strand of "
             "yarn that loops through the letter and ends in a small ball -- the brand name "
             "drawn: bramble + loop. Primary lockup sets BRAMBLELOOP in spaced serif capitals "
             "with CROCHET PATTERNS in tracked sans between hairlines."),
    source=("Owner concept images 2026-10-06 (owner_logo_concept.png, owner_banner_concept.png), "
            "rebuilt as original vector geometry; the owner's raster is not embedded or traced."),
    palette=D1_PALETTE,
    variants={
        "colour": {"roles": {"ink": "forest", "leaf": "sage", "rib": "sage_mist", "yarn": "rose",
                             "yarn_line": "rose_deep", "petal": "petal", "gold": "gold",
                             "berry": "berry", "accent_text": "rose_deep", "rule": "rose"},
                   "ground": "paper"},
        "mono": {"roles": {"ink": "forest", "leaf": "forest", "rib": "paper", "yarn": "forest",
                           "yarn_line": "paper", "petal": "paper", "gold": "forest",
                           "berry": "forest", "accent_text": "forest", "rule": "forest"},
                 "ground": "paper"},
        "reversed": {"roles": {"ink": "paper", "leaf": "sage_mist", "rib": "forest",
                               "yarn": "rose_light", "yarn_line": "forest", "petal": "paper",
                               "gold": "gold", "berry": "rose_light", "accent_text": "paper",
                               "rule": "sage_mist"},
                     "ground": "forest"},
    },
    typography={
        "wordmark": {"family": "Libre Baskerville", "font": "baskerville", "case": "upper",
                     "tracking_em": 0.16, "licence": "OFL-1.1"},
        "monogram": {"family": "Gloock", "font": "gloock", "licence": "OFL-1.1"},
        "descriptor": {"family": "Work Sans", "font": "worksans", "case": "upper",
                       "tracking_em": 0.28, "licence": "OFL-1.1"},
        "tagline": {"family": "Lora Italic", "font": "lora_italic", "licence": "OFL-1.1",
                    "note": "the owner's concept shows a script; no open-licence formal script "
                            "is available offline, and a script tagline fails below ~14 px on a "
                            "phone. Lora Italic keeps the handmade warmth and stays legible."},
        "body": {"family": "Lora / Work Sans", "licence": "OFL-1.1",
                 "web_files": ["fonts/Lora-Regular.subset.woff",
                               "fonts/WorkSans-Regular.subset.woff"]},
    },
    build_icon=d1_icon,
    build_emblem=d1_emblem,
    build_wordmark=d1_wordmark,
    build_motif=d1_motif,
    emblem_scale=0.5,
)


def _simple_wordmark(name: str, font: str, text: str, tracking: float,
                     kern: dict[str, float] | None = None, size: float = 100.0) -> Mark:
    w = T.measure(font, text, size, tracking, kern)
    met = T.font_metrics(font)
    has_desc = any(c in text for c in "gjpqy")
    asc = (met["cap_height"] if text.isupper() else max(met["cap_height"], met["x_height"] * 1.45)
           ) * size / 1000
    desc = (-met["descender"] * size / 1000 * 0.8) if has_desc else 0.0
    pad = 6
    m = Mark(name, w + 2 * pad, asc + desc + 2 * pad, title="Brambleloop")
    m.add(Fill(T.set_text(font, text, size, pad, pad + asc, tracking=tracking, kern=kern), "ink"))
    return m


# ============================================================================================
# D2  chain-link
# ============================================================================================

D2_PALETTE = {
    "charcoal": "#1F2A2E", "oat": "#EEE7DA", "clay": "#B0553A", "fog": "#8E9A9B",
    "linen": "#FBF8F2",
}


def _d2_links(m: Mark, cx: float, cy: float, scale: float, yw: float, halo: float) -> None:
    """Two loops interlocked as a crochet chain: the second passes over, then under, the
    first. The working yarn leaves the last loop as a short tail."""
    rot = -38
    e1 = ellipse_path(cx - 62 * scale, cy - 58 * scale, 78 * scale, 142 * scale, rot)
    e2 = ellipse_path(cx + 62 * scale, cy + 58 * scale, 78 * scale, 142 * scale, rot)
    # split e2 into its two halves by flattening and slicing
    pts = [p for pl, _ in e2.polylines() for p in pl]
    n = len(pts)
    under = cubic_through(pts[: n // 2 + 1])
    over = cubic_through(pts[n // 2:] + pts[:1])
    m.add(Stroke(under, yw, "accent"))
    m.add(Knockout([Stroke(e1, yw + halo, "x")]))
    m.add(Stroke(e1, yw, "ink"))
    h = pts[n // 2:] + pts[:1]
    q = len(h)
    m.add(Knockout([Stroke(cubic_through(h[q // 5: q - q // 5]), yw + halo, "x")]))
    m.add(Stroke(over, yw, "accent"))


def d2_icon() -> Mark:
    m = Mark("d2-icon", ICON, ICON, title="Brambleloop")
    _d2_links(m, 250, 250, 1.0, 34, 22)
    return m


def d2_wordmark() -> Mark:
    return _simple_wordmark("d2-wordmark", "outfit", "brambleloop", 0.0,
                            kern={"oo": -0.012, "lo": -0.006})


def d2_motif() -> Mark:
    m = Mark("d2-motif", 240, 120, title="Brambleloop chain pattern")
    for i in range(3):
        cx = 40 + i * 80
        e = ellipse_path(cx, 60, 36, 18, 0)
        m.add(Stroke(e, 4, "accent" if i % 2 else "ink"))
    return m


D2 = Direction(
    id="D2-chain-link",
    name="Chain Link",
    concept=("Two elongated loops interlocked exactly as a crochet chain stitch -- the first "
             "stitch of every project -- drawn over-and-under. Lower-case geometric sans "
             "wordmark; charcoal, oat and clay."),
    source="original; no reference asset used",
    palette=D2_PALETTE,
    variants={
        "colour": {"roles": {"ink": "charcoal", "accent": "clay", "accent_text": "clay",
                             "rule": "fog"}, "ground": "oat"},
        "mono": {"roles": {"ink": "charcoal", "accent": "charcoal", "accent_text": "charcoal",
                           "rule": "charcoal"}, "ground": "oat"},
        "reversed": {"roles": {"ink": "linen", "accent": "clay", "accent_text": "oat",
                               "rule": "fog"}, "ground": "charcoal"},
    },
    typography={"wordmark": {"family": "Outfit", "font": "outfit", "case": "lower",
                             "licence": "OFL-1.1"},
                "descriptor": {"family": "Work Sans", "font": "worksans", "licence": "OFL-1.1"}},
    build_icon=d2_icon, build_emblem=d2_icon, build_wordmark=d2_wordmark, build_motif=d2_motif,
    emblem_scale=0.36,
)


# ============================================================================================
# D3  drupelet
# ============================================================================================

D3_PALETTE = {
    "bramble": "#5A1E2C", "moss": "#4A6741", "cream": "#F8F1E4", "blush": "#E7CBBF",
    "umber": "#2E2226",
}


def _d3_berry(m: Mark, cx: float, top: float, r: float, halo: float) -> None:
    rows = (3, 4, 4, 3, 2)
    pitch = r * 1.9
    cells = []
    for j, k in enumerate(rows):
        y = top + j * pitch * 0.88
        for i in range(k):
            x = cx + (i - (k - 1) / 2) * pitch
            cells.append((x, y))
    for x, y in cells:
        m.add(Knockout([Circle(x, y, r + halo / 2, "x")]))
        m.add(Circle(x, y, r, "accent"))
    # calyx: three sepals, and a stem that curls into one loop
    cy = top - r * 1.05
    sepals = [leaf_path((cx, cy), a, r * 2.2, r * 0.55) for a in (-160, -90, -20)]
    m.add(Knockout([Fill(p, "x") for p in sepals] + [Stroke(p, halo, "x") for p in sepals]))
    for p in sepals:
        m.add(Fill(p, "ink"))
    stem = cubic_through([(cx, cy - r * 0.2), (cx + r * 0.15, cy - r * 1.6),
                          (cx + r * 1.2, cy - r * 2.5), (cx + r * 1.7, cy - r * 1.7),
                          (cx + r * 1.0, cy - r * 1.25), (cx + r * 0.5, cy - r * 2.2),
                          (cx + r * 0.9, cy - r * 3.3)])
    m.add(Knockout([Stroke(stem, r * 0.42 + halo, "x")]))
    m.add(Stroke(stem, r * 0.42, "ink"))


def d3_icon() -> Mark:
    m = Mark("d3-icon", ICON, ICON, title="Brambleloop")
    _d3_berry(m, 232, 214, 38, 16)
    return m


def d3_wordmark() -> Mark:
    return _simple_wordmark("d3-wordmark", "youngserif", "brambleloop", 0.005,
                            kern={"oo": -0.01})


def d3_motif() -> Mark:
    m = Mark("d3-motif", 200, 200, title="Brambleloop drupelet pattern")
    for (x, y) in ((50, 50), (150, 150)):
        for dx, dy in ((0, 0), (12, 0), (6, 10), (-6, 10), (18, 10), (6, 20)):
            m.add(Circle(x + dx - 6, y + dy - 10, 5, "accent"))
    m.add(Stroke(cubic_through([(120, 40), (140, 30), (150, 50), (132, 52), (140, 30),
                                (170, 20)]), 2.4, "ink"))
    return m


D3 = Direction(
    id="D3-drupelet",
    name="Drupelet",
    concept=("The bramble fruit built from stitches: a blackberry whose drupelets are bobble "
             "stitches, with a stem that curls into a single loop -- bramble and loop in one "
             "silhouette. Warm, rounded serif lower-case wordmark."),
    source="original; no reference asset used",
    palette=D3_PALETTE,
    variants={
        "colour": {"roles": {"ink": "moss", "accent": "bramble", "accent_text": "bramble",
                             "rule": "blush"}, "ground": "cream"},
        "mono": {"roles": {"ink": "umber", "accent": "umber", "accent_text": "umber",
                           "rule": "umber"}, "ground": "cream"},
        "reversed": {"roles": {"ink": "cream", "accent": "blush", "accent_text": "blush",
                               "rule": "blush"}, "ground": "bramble"},
    },
    typography={"wordmark": {"family": "Young Serif", "font": "youngserif", "case": "lower",
                             "licence": "OFL-1.1"},
                "descriptor": {"family": "Work Sans", "font": "worksans", "licence": "OFL-1.1"}},
    build_icon=d3_icon, build_emblem=d3_icon, build_wordmark=d3_wordmark, build_motif=d3_motif,
    emblem_scale=0.34,
)


# ============================================================================================
# D4  tapestry-b
# ============================================================================================

D4_PALETTE = {
    "indigo": "#243050", "linen": "#F2ECE0", "saffron": "#C08A2A", "slate": "#B9BDC6",
}
_D4_B = ("XXXXXX.", "XX...XX", "XX...XX", "XX..XX.", "XXXXX..", "XX..XX.", "XX...XX",
         "XX...XX", "XXXXXX.")


def _vstitch(cx: float, cy: float, w: float, h: float) -> list[Path]:
    """One single-crochet 'V' as two leaning petals."""
    left = leaf_path((cx, cy + h * 0.45), -118, h * 0.95, w * 0.2)
    right = leaf_path((cx, cy + h * 0.45), -62, h * 0.95, w * 0.2)
    return [left, right]


def d4_icon() -> Mark:
    m = Mark("d4-icon", ICON, ICON, title="Brambleloop")
    cell = 46.0
    cols, rows = len(_D4_B[0]), len(_D4_B)
    x0 = (ICON - cols * cell) / 2
    y0 = (ICON - rows * cell) / 2
    for j, row in enumerate(_D4_B):
        for i, c in enumerate(row):
            role = "ink" if c == "X" else "quiet"
            for p in _vstitch(x0 + (i + 0.5) * cell, y0 + (j + 0.5) * cell, cell, cell):
                m.add(Fill(p, role))
    return m


def d4_wordmark() -> Mark:
    return _simple_wordmark("d4-wordmark", "arsenal", "Brambleloop", 0.09)


def d4_motif() -> Mark:
    m = Mark("d4-motif", 160, 160, title="Brambleloop stitch pattern")
    for j in range(4):
        for i in range(4):
            role = "accent" if (i + j) % 3 == 0 else "quiet"
            for p in _vstitch(20 + i * 40, 20 + j * 40, 40, 40):
                m.add(Fill(p, role))
    return m


D4 = Direction(
    id="D4-tapestry-b",
    name="Tapestry B",
    concept=("A capital B worked as a tapestry-crochet chart of V stitches; ghost stitches "
             "complete the swatch. Graphic and modern; small-caps serif wordmark."),
    source="original; no reference asset used",
    palette=D4_PALETTE,
    variants={
        "colour": {"roles": {"ink": "indigo", "quiet": "slate", "accent": "saffron",
                             "accent_text": "saffron", "rule": "slate"}, "ground": "linen"},
        "mono": {"roles": {"ink": "indigo", "quiet": "linen", "accent": "indigo",
                           "accent_text": "indigo", "rule": "indigo"}, "ground": "linen"},
        "reversed": {"roles": {"ink": "linen", "quiet": "indigo", "accent": "saffron",
                               "accent_text": "saffron", "rule": "slate"}, "ground": "indigo"},
    },
    typography={"wordmark": {"family": "Arsenal SC", "font": "arsenal", "case": "small-caps",
                             "licence": "OFL-1.1"},
                "descriptor": {"family": "Work Sans", "font": "worksans", "licence": "OFL-1.1"}},
    build_icon=d4_icon, build_emblem=d4_icon, build_wordmark=d4_wordmark, build_motif=d4_motif,
    emblem_scale=0.34,
)

DIRECTIONS: dict[str, Direction] = {d.id: d for d in (D1, D2, D3, D4)}
