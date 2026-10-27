"""F-527 Brand Asset Health: the colour and typography half (W4-C08).

"Maintain logo/icon, banner, color, typography and listing-image consistency across Etsy.
Detect stale, missing, low-resolution or off-brand assets and route fixes to Brand/Visual."

`store_foundation.asset_health.check` (W4-AGENTS C3) already detects missing, stale, blocked
and low-resolution assets on the live shop and routes them; it reports live colour and
typography as UNMEASURED, because no Etsy API returns them. What we CAN read is every brand
asset we hold before it reaches Etsy. This module checks those, deterministically:

* **colour** -- every fill/stroke/stop colour in an SVG mark, and every colour in a page's CSS,
  must be a brand colour (`identity_system.PALETTE` plus its semantic `ROLES`); pure black and
  white are allowed only in the mono / reversed / transparent variants (and inside a
  `<mask>`, which is luminance, not colour);
* **typography** -- marks never carry live `<text>` (they are outlined); a page or listing
  overlay may only name the bundled families (`identity_system.TYPOGRAPHY`);
* **resolution** -- a raster brand asset must meet its surface's minimum (Etsy shop icon 500 px
  square; banner 1200 px wide; listing image 2000 px shortest side).

Findings carry `route_to` (`brand` for marks and pages, `publishing` for listing images),
the same shape as `asset_health` findings, so the storefront review can route them unchanged.
Read-only, local, CA$0.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

MASTERS = Path(__file__).resolve().parent / "masters"
_HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_FONT = re.compile(r"font-family\s*:\s*([^;}\"]+)", re.I)
_GENERIC = {"serif", "sans-serif", "monospace", "cursive", "system-ui", "-apple-system",
            "fantasy", "inherit", "initial"}
_SAFE_FALLBACKS = {"georgia", "times new roman"}
NEUTRAL = {"#000000", "#ffffff"}
NEUTRAL_VARIANTS = ("mono", "reversed", "transparent")
MIN_PX = {"shop_icon": (500, 500), "shop_banner": (1200, 0), "listing_image": (2000, 2000)}


def _norm(h: str) -> str:
    h = h.lstrip("#").lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def brand_colours() -> set[str]:
    from . import identity_system as I

    return {_norm(v) for v in I.PALETTE.values()} | {
        _norm(v) for v in I.ROLES.values() if isinstance(v, str) and v.startswith("#")}


def brand_families() -> set[str]:
    from . import identity_system as I

    out = set()
    for t in I.TYPOGRAPHY.values():
        if isinstance(t, dict) and t.get("family"):
            out.add(str(t["family"]).lower())
    return out


def _f(code, subject, route, why):
    return {"code": code, "subject": subject, "route_to": route, "why": why,
            "severity": "fix"}


def check_svg(name: str, text: str) -> list[dict]:
    out = []
    allowed = brand_colours() | (NEUTRAL if any(v in name for v in NEUTRAL_VARIANTS) else set())
    # <mask> / <clipPath> content is a luminance or shape mask, never a visible colour.
    visible = re.sub(r"<(mask|clipPath)\b.*?</\1>", "", text, flags=re.S)
    off = sorted({_norm(m.group(0)) for m in _HEX.finditer(visible)} - allowed)
    if off:
        out.append(_f("MARK_OFF_PALETTE", name, "brand",
                      f"colours outside the brand palette: {off[:8]}"))
    if re.search(r"<text[\s>]", text):
        out.append(_f("MARK_LIVE_TEXT", name, "brand",
                      "a mark carries live <text>; marks are outlined artwork"))
    return out


def check_css(name: str, text: str, *, route: str = "brand") -> list[dict]:
    out = []
    off = sorted({_norm(m.group(0)) for m in _HEX.finditer(text)} - brand_colours())
    if off:
        out.append(_f("PAGE_OFF_PALETTE", name, route,
                      f"colours outside the brand palette: {off[:8]}"))
    fams = brand_families()
    bad = set()
    for m in _FONT.finditer(text):
        for fam in m.group(1).split(","):
            f = fam.strip().strip("'\"").lower()
            if f and f not in fams and f not in _GENERIC and f not in _SAFE_FALLBACKS:
                bad.add(f)
    if bad:
        out.append(_f("OFF_BRAND_TYPEFACE", name, route,
                      f"typefaces outside the brand families: {sorted(bad)}"))
    return out


def check_raster(name: str, data: bytes, surface: str) -> list[dict]:
    route = "publishing" if surface == "listing_image" else "brand"
    try:
        from PIL import Image

        w, h = Image.open(io.BytesIO(data)).size
    except Exception:  # noqa: BLE001
        return [_f("ASSET_UNREADABLE", name, route, "the bytes are not a readable image")]
    mw, mh = MIN_PX[surface]
    if w < mw or (mh and h < mh):
        return [_f("ASSET_LOW_RESOLUTION", name, route,
                   f"{w}x{h} px is under the {surface} minimum {mw}x{mh or 'any'} px")]
    return []


def sweep(*, masters: Path | None = None, pages: dict[str, str] | None = None) -> dict:
    """Every committed mark, plus any page/overlay CSS handed in (e.g. the storefront)."""
    root = masters or MASTERS
    findings = []
    marks = sorted(root.glob("*.svg"))
    for p in marks:
        findings += check_svg(p.name, p.read_text(encoding="utf-8", errors="replace"))
    for name, text in (pages or {}).items():
        findings += check_css(name, text)
    return {"findings": findings, "marks_checked": len(marks),
            "pages_checked": len(pages or {}),
            "routes": sorted({f["route_to"] for f in findings}),
            "fix_count": len(findings), "writes": 0}
