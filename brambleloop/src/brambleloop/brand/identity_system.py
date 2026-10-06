"""brambleloop.brand.identity_system -- THE interface other lanes read for the Brambleloop identity.

Lane A owns this. Store layout (lane B), copy (lane C), Command Center and any future renderer
read the chosen direction from here and never hard-code a colour, a font or a mark.

PRIMARY DIRECTION (owner decision D-FB-16, 2026-10-06): "O1-owner-bramble-b", the owner's own
concept professionalised into a production vector identity (`brand.owner_identity`). D1
"Briar Monogram" and D2-D4 (`brand.directions`) remain available as design research only
(`RESEARCH_DIRECTION_ID`, `alternatives()`, `mark_svg(..., direction_id=...)`).

What it gives you
  DIRECTION_ID, STATUS            the chosen direction and how final it is
  PALETTE, ROLES                  named colours, and semantic web roles (text/background/...)
  TYPOGRAPHY, font_face_css()     open-licence families, bundled .woff subsets, CSS stacks
  icon_svg() / emblem_svg() / wordmark_svg() / lockup_horizontal_svg() / lockup_stacked_svg()
  monogram_svg() / micro_mark_svg() / hero_lockup_svg()   (owner-concept names, same marks)
  motif_svg()                     deterministic, self-contained SVG strings (no <text>, no
                                  external refs, no scripts); variant = colour | mono | reversed
  icon_png(px)                    raster export (Pillow) for the Etsy shop-icon upload
  CLEAR_SPACE, MIN_SIZE           spacing and minimum-size rules (also in USAGE_RULES)
  USAGE_RULES                     how the system is used, including next to Laura
  alternatives()                  the research directions, kept for comparison
  to_dict()                       one JSON-serialisable record of all of the above

Nothing here is uploaded to Etsy. `STATUS` says what has and has not happened.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path as _FsPath

from . import directions as _D
from . import owner_identity as _O
from .vector import rasterize, to_png_bytes, to_svg

DIRECTION_ID = _O.DIRECTION_ID
RESEARCH_DIRECTION_ID = "D1-briar-monogram"
STATUS = {
    "state": "OWNER_DIRECTED_PRIMARY",
    "basis": ("the owner chose their own concept as the primary brand direction (D-FB-16); "
              "this system professionalises it into production vector masters. The owner has "
              "not yet approved these final drawings; nothing is uploaded to Etsy; not "
              "certified by the independent brand certifier"),
    "decided_at": "2026-10-06",
    "decision": "D-FB-16",
    "research_only": sorted(_D.DIRECTIONS),
}

# Every direction a caller may name: the primary plus the research directions.
ALL_DIRECTIONS: dict[str, _D.Direction] = {_O.DIRECTION_ID: _O.O1, **_D.DIRECTIONS}


def get_direction(direction_id: str | None = None) -> _D.Direction:
    return ALL_DIRECTIONS[direction_id or DIRECTION_ID]


FONT_DIR = _FsPath(__file__).resolve().parent / "fonts"


def direction() -> _D.Direction:
    return get_direction(DIRECTION_ID)


_d = direction()
PALETTE: dict[str, str] = dict(_d.palette)
TAGLINE = _O.TAGLINE

# Semantic roles for page design (lane B). Every text pair here is tested >= 4.5:1.
ROLES: dict[str, str] = {
    "background": PALETTE["paper"],
    "surface": PALETTE["surface"],
    "text": PALETTE["forest"],
    "text_muted": "#5B5A4E",
    "accent": PALETTE["rose"],            # dusty rose: hearts, decoration -- not body text
    "accent_text": PALETTE["rose_deep"],  # rose safe for small text on background
    "descriptor": PALETTE["taupe"],       # CROCHET PATTERNS, small tracked caps labels
    "yarn": PALETTE["yarn"],
    "leaf": PALETTE["leaf"],
    "sage": PALETTE["sage"],
    "rule": PALETTE["taupe"],
    "berry": PALETTE["berry"],
    "inverse_background": PALETTE["forest"],
    "inverse_text": PALETTE["paper"],
    "focus": PALETTE["rose_deep"],
}

TYPOGRAPHY: dict[str, dict] = {
    "wordmark": dict(_d.typography["wordmark"], use="outlined in the SVG marks only"),
    "monogram": dict(_d.typography["monogram"], use="the B in the monogram, outlined"),
    "micro_monogram": dict(_d.typography["micro_monogram"],
                           use="the same B in the micro-mark (icon), outlined"),
    "tagline": dict(_d.typography["tagline"], use="outlined in the hero lockup"),
    "display": {"family": "Cormorant Garamond", "weight": 600,
                "css": "'Cormorant Garamond', 'Libre Baskerville', Georgia, serif",
                "file": "fonts/CormorantGaramond-SemiBold.subset.woff",
                "use": "headings and section titles (the wordmark's face); caps tracked "
                       "0.12-0.18em for short labels; 22px minimum on phones",
                "licence": "OFL-1.1"},
    "body": {"family": "Lora", "css": "Lora, Georgia, 'Times New Roman', serif",
             "file": "fonts/Lora-Regular.subset.woff", "weight": 400,
             "use": "About/story and long-form paragraphs; 16px minimum on phones",
             "licence": "OFL-1.1"},
    "italic": {"family": "Lora", "style": "italic", "css": "Lora, Georgia, serif",
               "file": "fonts/Lora-Italic.subset.woff",
               "use": "pull quotes, Laura's sign-off line (never a fake signature)",
               "licence": "OFL-1.1"},
    "ui": {"family": "Work Sans", "css": "'Work Sans', system-ui, -apple-system, sans-serif",
           "file": "fonts/WorkSans-Regular.subset.woff", "weight": 400,
           "use": "descriptor line, navigation, prices, labels, buttons; caps tracked 0.2-0.32em",
           "licence": "OFL-1.1"},
    "script": {"family": "Allison", "css": "Allison, 'Lora', Georgia, cursive",
               "file": "fonts/Allison-Regular.subset.woff", "weight": 400,
               "use": "the tagline only, 32px+ (its x-height is 22% of the em); never body, "
                      "never buttons, never under 32px",
               "licence": "OFL-1.1"},
    "licence_files": sorted(p.name for p in FONT_DIR.glob("*-OFL.txt")),
    "rule": ("Only these families. No external font CDN: the .woff subsets ship in "
             "brand/fonts/. Marks never use live text; they are outlined. Playfair Display "
             "(the B) has a Reserved Font Name and is used only as outlined artwork."),
}

DESCRIPTOR = _d.descriptor

# Clear space and minimum sizes. Unit "B" = the cap height of the B in the mark being used.
CLEAR_SPACE: dict[str, str] = {
    "hero_lockup": "0.5 x the monogram B's cap height on all sides",
    "lockup_horizontal": "1 x the wordmark cap height on all sides",
    "monogram": "0.25 x its B's cap height on all sides",
    "micro_mark": "1/8 of the icon square (already built into icon_svg's 500 px square)",
}
MIN_SIZE: dict[str, dict] = {
    "micro_mark": {"min_px": 40, "min_mm": 6,
                   "note": "the only mark for 40-96 px (Etsy shop icon, favicon, avatar)"},
    "monogram": {"min_px": 160, "min_mm": 25,
                 "note": "sprig, blossoms and berries turn to noise below 160 px wide"},
    "lockup_horizontal": {"min_px_height": 28, "min_mm_height": 6,
                          "note": "phone header 28-40 px tall; descriptor drops below 32 px"},
    "hero_lockup": {"min_px_width": 320, "min_mm_width": 50,
                    "note": "the script tagline needs >= 22 px letter height to read"},
}

USAGE_RULES: list[str] = [
    "Primary identity = the owner's concept (D-FB-16): serif B + bramble growth + yarn loop "
    "and ball; BRAMBLELOOP; CROCHET PATTERNS between hairlines; the script tagline; the heart.",
    "Etsy shop icon (40-70 px on screen): ONLY the micro-mark, icon_svg('colour') exported with "
    "icon_png(500). It is the same B, simplified -- never shrink the full monogram into the "
    "icon slot. It sits inside the central circle, so a circular crop loses nothing.",
    "Full monogram (B with sprig, blossoms, berries, figure-of-eight and ball): 160 px wide or "
    "larger -- banner, About, packaging, PDF covers.",
    "Hero lockup (monogram + wordmark + descriptor + script tagline + heart): banner centre, "
    "About header, pattern PDF cover; at least 320 px wide so the script reads.",
    "Phone header / email footer: lockup_horizontal_svg() at 28-40 px tall (micro-mark + "
    "wordmark + descriptor). Never the hero lockup in a phone header.",
    "Clear space: hero lockup 0.5 B, horizontal lockup 1 cap height, monogram 0.25 B, "
    "micro-mark 1/8 of its square. Nothing -- text, product, Laura -- enters it.",
    "Colour: forest ink on cream paper is the default. Reversed (cream on forest) for dark "
    "grounds. One-colour forest (mono) for stamps, embossing, PDF footers, one-ink print.",
    "On photographs: place marks only on a calm, low-detail area at contrast >= 3:1, or on a "
    "cream panel. Never over a face, a product, or busy crochet texture.",
    "Never: recolour outside the palette, stretch, rotate, outline, add shadows/glows, set the "
    "wordmark or tagline in another font, re-draw the B, or add a second yarn ball.",
    "Text colours: forest for text; taupe for the descriptor and small caps labels; rose is "
    "decoration (heart, accents) and rose_deep is the rose for small text (>= 4.5:1).",
    "The script (Allison) is for the tagline only, never under 32 px and never for body copy, "
    "buttons, prices or anything a customer must read quickly.",
    "Laura: she is the face, the mark is the signature -- they complement, they do not compete. "
    "In a banner Laura sits to one side and the hero lockup takes the centre (as in the "
    "owner's banner concept); the micro-mark may sit as a small corner seal on Laura imagery, "
    "never on her face or body. Her seller portrait carries no logo overlay.",
    "Until the customer-facing Laura pipeline qualifies, any preview that shows the canonical "
    "Laura portrait must be labelled INTERNAL -- the identity system does not change that.",
    "Motif (bramble scatter) is a background pattern for packaging, PDF covers and section "
    "dividers at <= 20% visual weight; never behind body text.",
    "Slogan props from the concept images (mugs, signs, the category line) are merchandising "
    "and copy (lane C), not part of the identity.",
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
    d = get_direction(direction_id)
    if kind == "lockup_stacked":
        return d.lockup_stacked(tagline)
    return _BUILDERS[kind](d)


def mark_svg(kind: str, variant: str = "colour", *, transparent: bool = False,
             width: float | None = None, direction_id: str | None = None,
             tagline: str | None = None) -> str:
    did = direction_id or DIRECTION_ID
    d = get_direction(did)
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
    d = get_direction(did)
    return rasterize(_mark(did, "icon"), d.colours(variant), px, ground=d.ground(variant))


def icon_png(px: int = 500, variant: str = "colour") -> bytes:
    """PNG bytes of the icon at `px` square (Etsy shop icon upload is a raster)."""
    return to_png_bytes(icon_raster(px, variant))


FONT_FACES = ("display", "body", "italic", "ui")


def font_face_css(base_url: str = "", extra: tuple[str, ...] = ()) -> str:
    """@font-face rules for the bundled subsets. `base_url` is where brand/fonts is served.

    The four page faces by default; pass extra=("script",) for the tagline script."""
    out = []
    for key in FONT_FACES + tuple(k for k in extra if k not in FONT_FACES):
        t = TYPOGRAPHY[key]
        style = t.get("style", "normal")
        out.append(f"@font-face{{font-family:'{t['family']}';font-style:{style};"
                   f"font-weight:{t.get('weight', 400)};font-display:swap;"
                   f"src:url('{base_url}{t['file']}') format('woff');}}")
    return "\n".join(out)


def css_variables() -> str:
    lines = [f"  --bl-{k.replace('_', '-')}: {v};" for k, v in ROLES.items()]
    for k in ("display", "body", "ui", "script"):
        lines.append(f"  --bl-font-{k}: {TYPOGRAPHY[k]['css']};")
    return ":root {\n" + "\n".join(lines) + "\n}"


def monogram_svg(variant: str = "colour", **kw) -> str:
    """The full B / bramble / yarn monogram (= emblem)."""
    return mark_svg("emblem", variant, **kw)


def micro_mark_svg(variant: str = "colour", **kw) -> str:
    """The simplified micro-mark derived from the same B (= icon)."""
    return mark_svg("icon", variant, **kw)


def hero_lockup_svg(variant: str = "colour", tagline: str | None = None, **kw) -> str:
    """The full hero lockup with the owner's tagline (= stacked lockup)."""
    return mark_svg("lockup_stacked", variant, tagline=tagline, **kw)


def alternatives() -> list[dict]:
    """The research directions, kept for comparison (and the judge's notes on each).

    The automated judge ranked the research directions before the owner decided (D1 first);
    the owner's concept was then chosen as primary by the owner (D-FB-16), not by the judge."""
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
                    "why_not": verdict["why_not"].get(did, "") or (
                        "design research only: the owner chose their own concept as the "
                        "primary direction (D-FB-16); kept for comparison")})
    return out


def to_dict(include_svgs: bool = True) -> dict:
    d = direction()
    rec = {
        "direction_id": DIRECTION_ID, "name": d.name, "concept": d.concept,
        "source": d.source, "status": dict(STATUS), "palette": dict(PALETTE),
        "roles": dict(ROLES), "typography": TYPOGRAPHY, "descriptor": DESCRIPTOR,
        "usage_rules": list(USAGE_RULES), "variants": list(VARIANTS),
        "alternatives": [a["id"] for a in alternatives()],
        "research_direction_id": RESEARCH_DIRECTION_ID, "tagline": TAGLINE,
        "clear_space": dict(CLEAR_SPACE), "min_size": MIN_SIZE,
        "basis": "deterministic SVG geometry + outlined OFL type; no image model, no spend",
    }
    if include_svgs:
        rec["svgs"] = {k: mark_svg(k) for k in
                       ("icon", "emblem", "wordmark", "lockup_horizontal", "lockup_stacked",
                        "motif")}
        rec["svgs"]["icon_mono"] = mark_svg("icon", "mono")
        rec["svgs"]["icon_reversed"] = mark_svg("icon", "reversed")
    return rec


# ---- production SVG masters ------------------------------------------------------------------

MASTER_KINDS = {"hero-lockup": "lockup_stacked", "horizontal-lockup": "lockup_horizontal",
                "monogram": "emblem", "micro-mark": "icon", "wordmark": "wordmark"}
MASTERS_DIR = _FsPath(__file__).resolve().parent / "masters"


def master_svgs() -> dict[str, str]:
    """Every production master of the primary identity: {file name: SVG}. Grounded masters
    carry their paper/forest ground; `-transparent` masters have none (for placing on a page
    or photograph -- the knockout gaps are masks, not painted ground, so they stay true)."""
    out: dict[str, str] = {}
    for name, kind in MASTER_KINDS.items():
        for variant in VARIANTS:
            out[f"brambleloop-{name}-{variant}.svg"] = mark_svg(kind, variant)
        out[f"brambleloop-{name}-colour-transparent.svg"] = mark_svg(kind, "colour",
                                                                     transparent=True)
    return out


def export_masters(dest: _FsPath | None = None) -> list[_FsPath]:
    dest = _FsPath(dest) if dest else MASTERS_DIR
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    for name, svg in sorted(master_svgs().items()):
        p = dest / name
        p.write_text(svg + "\n")
        written.append(p)
    return written
