"""brambleloop.brand.identity_system -- THE interface other lanes read for the Brambleloop identity.

Lane A (wave 3) owns this. Store layout (lane B), copy (lane C), Command Center and any future
renderer read the chosen direction from here and never hard-code a colour, a font or a mark.

What it gives you
  DIRECTION_ID, STATUS            the chosen direction and how final it is
  PALETTE, ROLES                  named colours, and semantic web roles (text/background/...)
  TYPOGRAPHY, font_face_css()     open-licence families, bundled .woff subsets, CSS stacks
  icon_svg() / emblem_svg() / wordmark_svg() / lockup_horizontal_svg() / lockup_stacked_svg()
  motif_svg()                     deterministic, self-contained SVG strings (no <text>, no
                                  external refs, no scripts); variant = colour | mono | reversed
  icon_png(px)                    raster export (Pillow) for the Etsy shop-icon upload
  USAGE_RULES                     how the system is used, including next to Laura
  alternatives()                  the runners-up, kept for the owner's comparison
  to_dict()                       one JSON-serialisable record of all of the above

The choice and its reasoning are made by `brand.judge` and recorded in
research/final_build/w3/A_brand_decision.md; `STATUS` says what has and has not happened
(nothing here is uploaded to Etsy; the owner has not yet approved a final mark).
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path as _FsPath

from . import directions as _D
from .vector import rasterize, to_png_bytes, to_svg

DIRECTION_ID = "D1-briar-monogram"
STATUS = {
    "state": "RECOMMENDED_PENDING_OWNER_APPROVAL",
    "basis": ("chosen by brand.judge (automated raster checks + documented rubric) with the "
              "owner's concept images as a declared strong signal; not owner-approved, not "
              "uploaded, not certified by the independent brand certifier (lane J)"),
    "decided_at": "2026-10-06",
}

FONT_DIR = _FsPath(__file__).resolve().parent / "fonts"


def direction() -> _D.Direction:
    return _D.DIRECTIONS[DIRECTION_ID]


_d = direction()
PALETTE: dict[str, str] = dict(_d.palette)

# Semantic roles for page design (lane B). Every text pair here is tested >= 4.5:1.
ROLES: dict[str, str] = {
    "background": PALETTE["paper"],
    "surface": "#FFFCF6",
    "text": PALETTE["forest"],
    "text_muted": "#5B5A4E",
    "accent": PALETTE["rose"],            # yarn: decorative fills, rules, icons -- not body text
    "accent_text": PALETTE["rose_deep"],  # accent colour safe for small text on background
    "leaf": PALETTE["sage"],
    "rule": PALETTE["sage_mist"],
    "berry": PALETTE["berry"],
    "inverse_background": PALETTE["forest"],
    "inverse_text": PALETTE["paper"],
    "focus": PALETTE["rose_deep"],
}

TYPOGRAPHY: dict[str, dict] = {
    "wordmark": dict(_d.typography["wordmark"], use="outlined in the SVG marks only"),
    "monogram": dict(_d.typography["monogram"], use="the B in icon and emblem, outlined"),
    "display": {"family": "Libre Baskerville", "css": "'Libre Baskerville', Georgia, serif",
                "file": "fonts/LibreBaskerville-Regular.subset.woff", "weight": 400,
                "use": "headings, section titles; caps tracked 0.08-0.16em for small labels",
                "licence": "OFL-1.1"},
    "body": {"family": "Lora", "css": "Lora, Georgia, 'Times New Roman', serif",
             "file": "fonts/Lora-Regular.subset.woff", "weight": 400,
             "use": "About/story and long-form paragraphs; 16px minimum on phones",
             "licence": "OFL-1.1"},
    "italic": {"family": "Lora", "style": "italic", "css": "Lora, Georgia, serif",
               "file": "fonts/Lora-Italic.subset.woff",
               "use": "tagline, pull quotes, Laura's sign-off line (never a fake signature)",
               "licence": "OFL-1.1"},
    "ui": {"family": "Work Sans", "css": "'Work Sans', system-ui, -apple-system, sans-serif",
           "file": "fonts/WorkSans-Regular.subset.woff", "weight": 400,
           "use": "descriptor line, navigation, prices, labels, buttons; caps tracked 0.2-0.3em",
           "licence": "OFL-1.1"},
    "licence_files": sorted(p.name for p in FONT_DIR.glob("*-OFL.txt")),
    "rule": ("Only these families. No external font CDN: the .woff subsets ship in "
             "brand/fonts/. Marks never use live text; they are outlined."),
}

DESCRIPTOR = _d.descriptor

USAGE_RULES: list[str] = [
    "Etsy shop icon: icon_svg('colour') exported with icon_png(500); it is a square with the "
    "mark inside the central circle, so a circular crop loses nothing.",
    "Below 64 px use only the icon (B in a loop of yarn). Never shrink the emblem (sprig, "
    "blossoms, figure-of-eight) below 160 px wide: its detail turns to noise.",
    "Phone header: lockup_horizontal_svg() at 28-36 px tall, or the icon alone at 32-40 px with "
    "the shop name set live in the display face. Never the stacked lockup in a phone header.",
    "Banner / About / packaging: lockup_stacked_svg(), emblem at least 160 px wide; on a phone "
    "crop keep the whole lockup inside the centre safe area.",
    "Clear space around any mark: at least the height of the wordmark's B (or 1/6 of the icon) "
    "on all sides. Nothing -- text, product, Laura -- enters it.",
    "Colour: forest on paper is the default. Reversed (paper on forest) for dark grounds. "
    "One-colour forest for stamps, embossing, PDF footers and anything printed in one ink.",
    "On photographs: place marks only on a calm, low-detail area at contrast >= 3:1, or on a "
    "paper panel. Never over a face, a product, or busy crochet texture.",
    "Never: recolour outside the palette, stretch, rotate, outline, add shadows/glows, set the "
    "wordmark in another font, re-draw the B, or add a second yarn ball.",
    "Accent rose is for the yarn and decoration; text in an accent colour uses accent_text "
    "(rose_deep), which passes 4.5:1 on paper.",
    "Laura: she is the face, the mark is the signature -- they complement, they do not compete. "
    "In a banner Laura sits to one side and the stacked lockup takes the centre or the other "
    "third; the icon may sit as a small corner seal on Laura imagery, never on her face or "
    "body. Her seller portrait is a photograph-style portrait without any logo overlay.",
    "Until the customer-facing Laura pipeline qualifies, any preview that shows the canonical "
    "Laura portrait must be labelled INTERNAL -- the identity system does not change that.",
    "Motif (bramble scatter) is a background pattern for packaging, PDF covers and section "
    "dividers at <= 20% visual weight; never behind body text.",
    "The tagline is lane C's copy and is passed in; the identity never hard-codes a slogan. "
    "Props with slogans (mugs, signs) from the owner's concept are not part of the identity.",
]


# ---- marks -----------------------------------------------------------------------------------

_BUILDERS = {
    "icon": lambda d: d.icon(),
    "emblem": lambda d: d.emblem(),
    "wordmark": lambda d: d.wordmark(),
    "lockup_horizontal": lambda d: d.lockup_horizontal(),
    "motif": lambda d: d.motif(),
}
VARIANTS = ("colour", "mono", "reversed")


@lru_cache(maxsize=64)
def _mark(direction_id: str, kind: str, tagline: str | None = None):
    d = _D.DIRECTIONS[direction_id]
    if kind == "lockup_stacked":
        return d.lockup_stacked(tagline)
    return _BUILDERS[kind](d)


def mark_svg(kind: str, variant: str = "colour", *, transparent: bool = False,
             width: float | None = None, direction_id: str | None = None,
             tagline: str | None = None) -> str:
    did = direction_id or DIRECTION_ID
    d = _D.DIRECTIONS[did]
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}")
    m = _mark(did, kind, tagline)
    ground = None if transparent else d.ground(variant)
    return to_svg(m, d.colours(variant), ground, width=width,
                  id_prefix=f"bl-{did.split('-')[0].lower()}-{kind[:6]}-{variant[:3]}")


def icon_svg(variant: str = "colour", **kw) -> str:
    return mark_svg("icon", variant, **kw)


def emblem_svg(variant: str = "colour", **kw) -> str:
    return mark_svg("emblem", variant, **kw)


def wordmark_svg(variant: str = "colour", **kw) -> str:
    return mark_svg("wordmark", variant, **kw)


def lockup_horizontal_svg(variant: str = "colour", **kw) -> str:
    return mark_svg("lockup_horizontal", variant, **kw)


def lockup_stacked_svg(variant: str = "colour", tagline: str | None = None, **kw) -> str:
    return mark_svg("lockup_stacked", variant, tagline=tagline, **kw)


def motif_svg(variant: str = "colour", **kw) -> str:
    return mark_svg("motif", variant, **kw)


def data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode("ascii")


def icon_raster(px: int, variant: str = "colour", direction_id: str | None = None):
    did = direction_id or DIRECTION_ID
    d = _D.DIRECTIONS[did]
    return rasterize(_mark(did, "icon"), d.colours(variant), px, ground=d.ground(variant))


def icon_png(px: int = 500, variant: str = "colour") -> bytes:
    """PNG bytes of the icon at `px` square (Etsy shop icon upload is a raster)."""
    return to_png_bytes(icon_raster(px, variant))


def font_face_css(base_url: str = "") -> str:
    """@font-face rules for the bundled subsets. `base_url` is where brand/fonts is served."""
    out = []
    for key in ("display", "body", "italic", "ui"):
        t = TYPOGRAPHY[key]
        style = t.get("style", "normal")
        out.append(f"@font-face{{font-family:'{t['family']}';font-style:{style};"
                   f"font-weight:400;font-display:swap;"
                   f"src:url('{base_url}{t['file']}') format('woff');}}")
    return "\n".join(out)


def css_variables() -> str:
    lines = [f"  --bl-{k.replace('_', '-')}: {v};" for k, v in ROLES.items()]
    for k in ("display", "body", "ui"):
        lines.append(f"  --bl-font-{k}: {TYPOGRAPHY[k]['css']};")
    return ":root {\n" + "\n".join(lines) + "\n}"


def alternatives() -> list[dict]:
    """The runners-up, kept so the owner can compare (and the judge's reasons for each)."""
    from . import judge

    verdict = judge.cached_verdict()
    out = []
    for did, d in _D.DIRECTIONS.items():
        if did == DIRECTION_ID:
            continue
        out.append({"id": did, "name": d.name, "concept": d.concept,
                    "palette": dict(d.palette), "typography": d.typography,
                    "icon_svg": mark_svg("icon", direction_id=did),
                    "wordmark_svg": mark_svg("wordmark", direction_id=did),
                    "score": verdict["scores"].get(did, {}).get("total"),
                    "why_not": verdict["why_not"].get(did, "")})
    return out


def to_dict(include_svgs: bool = True) -> dict:
    d = direction()
    rec = {
        "direction_id": DIRECTION_ID, "name": d.name, "concept": d.concept,
        "source": d.source, "status": dict(STATUS), "palette": dict(PALETTE),
        "roles": dict(ROLES), "typography": TYPOGRAPHY, "descriptor": DESCRIPTOR,
        "usage_rules": list(USAGE_RULES), "variants": list(VARIANTS),
        "alternatives": [a["id"] for a in alternatives()],
        "basis": "deterministic SVG geometry + outlined OFL type; no image model, no spend",
    }
    if include_svgs:
        rec["svgs"] = {k: mark_svg(k) for k in
                       ("icon", "emblem", "wordmark", "lockup_horizontal", "lockup_stacked",
                        "motif")}
        rec["svgs"]["icon_mono"] = mark_svg("icon", "mono")
        rec["svgs"]["icon_reversed"] = mark_svg("icon", "reversed")
    return rec
