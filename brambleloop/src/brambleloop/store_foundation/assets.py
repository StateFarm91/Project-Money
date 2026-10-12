"""The shop icon and banner, drawn deterministically as SVG from the brand bible.

No image model and no paid generation: the mark is geometry, so the same call produces the
same bytes on every machine, and the checks below can read the drawing rather than judge a
picture. The briefs in `brand.storefront` (icon: one loop-and-bramble mark in pine on cream,
no text; banner: crochet fabric in the palette, centred wordmark inside
`BANNER_WORDMARK_BOX` so a phone's centre crop keeps it) are what these draw.

Text in the banner is set with `textLength`, so the wordmark occupies exactly the box the
crop check measures whichever sans-serif the viewer's machine substitutes for Helvetica.

Etsy accepts raster uploads for the icon and banner; converting these SVGs to PNG at the
upload size is an owner-side step listed in the settings checklist (the recommended pixel
sizes are UNKNOWN here -- see `limits.LIMITS['banner_px']`).
"""
from __future__ import annotations

import base64
import hashlib
import math
import re

from ..brand import bible, storefront

P = bible.PALETTE


def _identity():
    """Lane A's identity system (`brand.identity_system`), or None before it exists."""
    try:
        from ..brand import identity_system
    except Exception:  # noqa: BLE001 - absent identity: the legacy drawing below is used
        return None
    return identity_system


def palette_hexes() -> set[str]:
    """Every colour the shop's assets may use: the bible plus the identity system's palette."""
    out = {v.upper() for v in P.values()}
    ident = _identity()
    if ident is not None:
        out |= {str(v).upper() for v in getattr(ident, "PALETTE", {}).values()}
    return out


def _mark_ground() -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    ident = _identity()
    if ident is not None:
        def rgb(h):
            h = h.lstrip("#")
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        return rgb(ident.PALETTE["forest"]), rgb(ident.PALETTE["paper"])
    return bible.rgb255("pine"), bible.rgb255("cream")
ICON_W, ICON_H = storefront.ICON_SIZE
BANNER_W, BANNER_H = storefront.BANNER_SIZE
WORDMARK_BOX = storefront.BANNER_WORDMARK_BOX
WORDMARK = storefront.SHOP_NAME.split()[0].upper()        # BRAMBLELOOP
SUBMARK = "STUDIO · CROCHET PATTERNS"


def _f(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _leaf(x: float, y: float, angle_deg: float, length: float, width: float) -> str:
    """A pointed leaf from (x, y) along `angle_deg`: two quadratic curves meeting at the tip."""
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    tx, ty = x + ux * length, y + uy * length
    mx, my = x + ux * length * 0.5, y + uy * length * 0.5
    c1 = (mx + nx * width, my + ny * width)
    c2 = (mx - nx * width, my - ny * width)
    return (f'<path d="M {_f(x)} {_f(y)} Q {_f(c1[0])} {_f(c1[1])} {_f(tx)} {_f(ty)} '
            f'Q {_f(c2[0])} {_f(c2[1])} {_f(x)} {_f(y)} Z" fill="{P["pine"]}"/>')


def _sprig(cx: float, cy: float, scale: float, angle_deg: float) -> str:
    """A bramble sprig: a stem, two leaves and a three-berry cluster, all palette colours."""
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)

    def along(t: float, off: float = 0.0) -> tuple[float, float]:
        return (cx + (ux * t - uy * off) * scale, cy + (uy * t + ux * off) * scale)

    s1, s2 = along(48, -5), along(90)
    stem = (f'<path d="M {_f(cx)} {_f(cy)} Q {_f(s1[0])} {_f(s1[1])} {_f(s2[0])} '
            f'{_f(s2[1])}" fill="none" stroke="{P["pine"]}" stroke-width="{_f(6 * scale)}" '
            f'stroke-linecap="round"/>')
    leaves = []
    for t, turn in ((30, -48), (56, 44)):
        bx, by = along(t, -2)
        leaves.append(_leaf(bx, by, angle_deg + turn, 34 * scale, 11 * scale))
    berries = []
    for t, off in ((100, -8), (106, 6), (94, 9)):
        bx, by = along(t, off)
        berries.append(f'<circle cx="{_f(bx)}" cy="{_f(by)}" r="{_f(8 * scale)}" '
                       f'fill="{P["wine"]}"/>')
    return stem + "".join(leaves) + "".join(berries)


def icon_svg() -> str:
    """The shop icon: lane A's chosen mark (`identity_system.icon_svg()`, outlined, no live
    text) when the identity system exists; otherwise the legacy loop-and-bramble drawing."""
    ident = _identity()
    if ident is not None:
        return ident.icon_svg()
    return _legacy_icon_svg()


def _legacy_icon_svg() -> str:
    """The v1 icon: a closed loop of yarn holding one stitch, a bramble sprig growing from
    its lower right. No text."""
    pine, gold, cream = P["pine"], P["gold"], P["cream"]
    ring = (f'<circle cx="250" cy="236" r="148" fill="none" stroke="{pine}" '
            f'stroke-width="36"/>')
    stitch = (f'<path d="M 220 210 L 250 260 L 280 210" fill="none" stroke="{gold}" '
              f'stroke-width="20" stroke-linecap="round" stroke-linejoin="round"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ICON_W}" height="{ICON_H}" '
            f'viewBox="0 0 {ICON_W} {ICON_H}" role="img" aria-label="Brambleloop Studio mark">'
            f'<rect width="{ICON_W}" height="{ICON_H}" fill="{cream}"/>'
            f'{ring}{stitch}{_sprig(338, 330, 1.2, 42)}</svg>')


def _stitch_rows(y0: float, rows: int, colours: list[str], pitch: float = 18.0,
                 row_h: float = 13.0) -> str:
    """Rows of crochet 'v' stitches across the banner, one path per colour."""
    paths = []
    for i in range(rows):
        colour = colours[i % len(colours)]
        y = y0 + i * row_h
        off = (pitch / 2) if i % 2 else 0.0
        d = []
        x = -pitch + off
        while x < BANNER_W + pitch:
            d.append(f"M{_f(x)} {_f(y)}l{_f(pitch / 2 - 1.5)} {_f(row_h - 3)}"
                     f"l{_f(pitch / 2 - 1.5)} {_f(-(row_h - 3))}")
            x += pitch
        paths.append(f'<path d="{"".join(d)}" fill="none" stroke="{colour}" '
                     f'stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round"/>')
    return "".join(paths)


def _inner(svg: str, x: float, y: float, w: float, h: float) -> str:
    """Place a standalone SVG inside another at (x, y, w, h), keeping its viewBox."""
    m = re.search(r"<svg\b([^>]*)>", svg)
    vb = re.search(r'viewBox="([^"]+)"', m.group(1)).group(1)
    body = svg[m.end():svg.rindex("</svg>")]
    return (f'<svg x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}" viewBox="{vb}" '
            f'preserveAspectRatio="xMidYMid meet">{body}</svg>')


def banner_svg() -> str:
    """A drawn utility banner (v1 readiness checks). NOT the storefront banner: under D-FB-17
    the storefront banner is the owner's canonical file (`brand.canonical_assets`, assessed by
    `store_foundation.owner_banner`); this drawing may never be substituted for it.

    With lane A's identity system: the horizontal lockup centred in `WORDMARK_BOX` on paper,
    the bramble motif in the wings only (outside the phone crop), no Laura (her imagery is
    not publication-approved). Otherwise the legacy drawing."""
    ident = _identity()
    if ident is None:
        return _legacy_banner_svg()
    x0, y0, x1, y1 = WORDMARK_BOX
    lock = ident.lockup_horizontal_svg(transparent=True)
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', lock).group(1).split()]
    lw = x1 - x0
    lh = lw * vb[3] / vb[2]
    ly = (y0 + y1) / 2 - lh / 2
    motif = ident.motif_svg(transparent=True)
    wings = "".join(_inner(motif, x, 40 + (i % 2) * 120, 160, 160)
                    for i, x in enumerate((20, 200, BANNER_W - 380, BANNER_W - 200)))
    ground = ident.PALETTE["paper"]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{BANNER_W}" height="{BANNER_H}" '
            f'viewBox="0 0 {BANNER_W} {BANNER_H}" role="img" '
            f'aria-label="{WORDMARK} · Brambleloop Studio banner">'
            f'<rect width="{BANNER_W}" height="{BANNER_H}" fill="{ground}"/>'
            f'{wings}{_inner(lock, x0, ly, lw, lh)}</svg>')


def _legacy_banner_svg() -> str:
    """The v1 banner: crochet fabric bands top and bottom, the wordmark centred in its box."""
    x0, y0, x1, y1 = WORDMARK_BOX
    mid = (x0 + x1) / 2
    word_w = (x1 - x0) - 40
    line_c, pine, wine, gold = P["line"], P["pine"], P["wine"], P["gold"]
    top = _stitch_rows(10, 3, [line_c, line_c, gold])
    bottom = _stitch_rows(BANNER_H - 82, 6, [gold, line_c, pine, line_c, wine, line_c])
    rule_y = y1 - 14
    rules = (f'<path d="M {_f(x0 + 20)} {rule_y} H {_f(mid - 150)} M {_f(mid + 150)} {rule_y} '
             f'H {_f(x1 - 20)}" stroke="{gold}" stroke-width="2"/>')
    word = (f'<text x="{_f(mid)}" y="{y0 + 62}" text-anchor="middle" '
            f'font-family="Helvetica Neue, Helvetica, Arial, sans-serif" font-weight="700" '
            f'font-size="64" fill="{pine}" textLength="{_f(word_w)}" '
            f'lengthAdjust="spacingAndGlyphs">{WORDMARK}</text>')
    sub = (f'<text x="{_f(mid)}" y="{rule_y + 6}" text-anchor="middle" '
           f'font-family="Helvetica Neue, Helvetica, Arial, sans-serif" font-size="17" '
           f'fill="{P["ink"]}" textLength="276" lengthAdjust="spacing">{SUBMARK}</text>')
    left = _sprig(x0 - 150, (y0 + y1) / 2 + 8, 1.3, -14)
    right = _sprig(x1 + 150, (y0 + y1) / 2 + 8, 1.3, 194)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{BANNER_W}" height="{BANNER_H}" '
            f'viewBox="0 0 {BANNER_W} {BANNER_H}" role="img" '
            f'aria-label="Brambleloop Studio banner">'
            f'<rect width="{BANNER_W}" height="{BANNER_H}" fill="{P["cream"]}"/>'
            f'{top}{bottom}{left}{right}{word}{rules}{sub}</svg>')


def data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def colours_used(svg: str) -> set[str]:
    return {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", svg)}


def check_icon(svg: str | None = None) -> list[dict]:
    svg = svg if svg is not None else icon_svg()
    out: list[dict] = []
    off = colours_used(svg) - palette_hexes()
    if off:
        out.append({"code": "ASSET_OFF_PALETTE", "severity": "fail",
                    "detail": f"icon uses colours outside the brand palette: {sorted(off)}"})
    if "<text" in svg:
        out.append({"code": "ICON_HAS_TEXT", "severity": "fail",
                    "detail": "the icon brief forbids text: it is illegible at 40 px"})
    if (ICON_W, ICON_H) != storefront.ICON_SIZE or ICON_W != ICON_H:
        out.append({"code": "ICON_NOT_SQUARE", "severity": "fail", "detail": "icon not square"})
    contrast = bible.contrast_ratio(*(tuple(c / 255 for c in rgb) for rgb in _mark_ground()))
    if contrast < 3.0:
        out.append({"code": "ICON_LOW_CONTRAST", "severity": "fail",
                    "detail": f"mark/ground contrast {contrast:.2f}:1 under 3:1"})
    # The ring's stroke at the 40 px it is actually shown: 36 units of 500 is 2.9 px.
    stroke_40 = 36 * 40 / ICON_W
    if stroke_40 < 2.0:
        out.append({"code": "ICON_STROKE_VANISHES", "severity": "fail",
                    "detail": f"ring stroke is {stroke_40:.1f}px at 40px"})
    out.append({"code": "ICON_RASTER_PENDING", "severity": "owner",
                "detail": "Etsy takes a raster upload; export this SVG to PNG at Etsy's "
                          "recommended size (not on file) and upload in Shop Manager"})
    return out


def check_banner(svg: str | None = None) -> list[dict]:
    from ..brand import storefront_preview as sp

    svg = svg if svg is not None else banner_svg()
    out: list[dict] = []
    off = colours_used(svg) - palette_hexes()
    if off:
        out.append({"code": "ASSET_OFF_PALETTE", "severity": "fail",
                    "detail": f"banner uses colours outside the brand palette: {sorted(off)}"})
    crops = sp.banner_crops(box=WORDMARK_BOX, size=(BANNER_W, BANNER_H))
    for name, c in crops.items():
        for p in c["problems"]:
            out.append({"code": "BANNER_CROP", "severity": "fail", "detail": p})
    contrast = bible.contrast_ratio(*(tuple(c / 255 for c in rgb) for rgb in _mark_ground()))
    if contrast < bible.MIN_TEXT_CONTRAST:
        out.append({"code": "BANNER_WORDMARK_CONTRAST", "severity": "fail",
                    "detail": f"wordmark contrast {contrast:.2f}:1"})
    if WORDMARK not in svg:
        out.append({"code": "BANNER_NO_WORDMARK", "severity": "fail",
                    "detail": "the wordmark is missing from the banner"})
    out.append({"code": "BANNER_RASTER_PENDING", "severity": "owner",
                "detail": "Etsy takes a raster upload; export to PNG at Etsy's recommended "
                          "size (not on file) and upload, or record a deliberate no-banner "
                          "choice (master section 56 permits one)"})
    return out


def describe() -> dict:
    icon, banner = icon_svg(), banner_svg()
    from ..brand import storefront_preview as sp

    return {
        "icon": {"sha256": hashlib.sha256(icon.encode()).hexdigest(), "bytes": len(icon),
                 "size": [ICON_W, ICON_H], "colours": sorted(colours_used(icon))},
        "banner": {"sha256": hashlib.sha256(banner.encode()).hexdigest(),
                   "bytes": len(banner), "size": [BANNER_W, BANNER_H],
                   "colours": sorted(colours_used(banner)),
                   "crops": sp.banner_crops(box=WORDMARK_BOX, size=(BANNER_W, BANNER_H))},
        "basis": ("deterministic SVG from brand.identity_system (lane A) when present, else "
                  "brand.bible.PALETTE; no image model, no spend"),
    }
