"""Where the v2 Owner Store Preview gets its brand system, its words and its banner crops.

Lane B (store UX / art direction) owns the layout only. The brand system belongs to lane A
(`brambleloop.brand.identity_system`), the customer copy to lane C
(`brambleloop.store_foundation.copy_v2`) and the verified Etsy crop numbers to lane I. This
module reads each of them through a narrow adapter and never edits them.

Every adapter tolerates absence: when a peer module is missing or does not expose the
expected names, it returns an interim fallback and says so (`source` = "fallback"), so the
preview always renders and the owner panel always states which parts are interim. Fallbacks
are deliberately modest; they exist so the layout can be judged, not to pre-empt A or C.

Fallback copy is customer-facing in the preview, so it is held to the same truth lint as
lane C's copy (tests/test_w3_store_ux_structure.py). Nothing here publishes anything.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field

FALLBACK = "fallback"
PEER = "peer"


@dataclass
class Sourced:
    value: object
    source: str                       # PEER or FALLBACK
    origin: str                       # module path or "preview_sources.<NAME>"
    notes: list[str] = field(default_factory=list)


def _import(path: str):
    try:
        return importlib.import_module(path)
    except Exception:  # noqa: BLE001 - a missing or broken peer is a fallback, not a crash
        return None


def _get(mod, *names, call: bool = True):
    """The first attribute of `mod` among `names` (called if it is a zero-arg callable)."""
    if mod is None:
        return None
    for n in names:
        v = getattr(mod, n, None)
        if v is None:
            continue
        if call and callable(v) and not isinstance(v, type):
            try:
                v = v()
            except TypeError:
                continue
            except Exception:  # noqa: BLE001
                continue
        return v
    return None


# ---- brand system (lane A) ---------------------------------------------------------------

# Interim tokens in the owner's concept direction (warm cream, sage, dusty rose, deep forest
# wordmark). Every text/background pair used by the layout clears WCAG AA (tested).
FALLBACK_PALETTE: dict[str, str] = {
    "paper": "#FBF8F2",      # page
    "cream": "#F4EEE3",      # banner ground, soft panels
    "linen": "#E9E0D0",      # wings, dividers with weight
    "line": "#E3DACB",       # hairlines
    "sage": "#8E9B82",       # accent fills, never text on light
    "sage_deep": "#4F5E4A",  # small accent text on light
    "forest": "#2E4034",     # wordmark, headings
    "rose": "#D9B8AF",       # soft accent
    "berry": "#8A3B47",      # price accent, links, berries
    "ink": "#2A2724",        # body text
    "muted": "#625B52",      # secondary text
    "night": "#1E2420",      # dark-surface checks
}

FALLBACK_TYPE = {
    "display": ('"Cormorant Garamond","Cormorant","Didot","Bodoni 72","Playfair Display",'
                '"Iowan Old Style","Georgia","Bitstream Charter","Liberation Serif",serif'),
    "body": ('-apple-system,BlinkMacSystemFont,"Helvetica Neue","Segoe UI","Liberation Sans",'
             'Arial,sans-serif'),
}


def _fallback_mark(ground: str | None = None) -> str:
    """Interim monogram: a serif B inside a fine ring, a yarn loop crossing it and three
    bramble berries. Geometry plus one glyph; replaced by lane A's mark when it exists."""
    P = FALLBACK_PALETTE
    bg = ground or P["cream"]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" '
        'aria-label="Brambleloop mark">'
        f'<rect width="100" height="100" fill="{bg}"/>'
        f'<circle cx="50" cy="50" r="44" fill="none" stroke="{P["forest"]}" stroke-width="2.4"/>'
        f'<text x="50" y="67" text-anchor="middle" font-family=\'{FALLBACK_TYPE["display"]}\' '
        f'font-size="54" font-weight="600" fill="{P["forest"]}">B</text>'
        f'<path d="M22 66 C 34 50, 52 82, 64 60 S 84 50, 78 40" fill="none" '
        f'stroke="{P["sage_deep"]}" stroke-width="3" stroke-linecap="round"/>'
        f'<circle cx="74" cy="31" r="4.6" fill="{P["berry"]}"/>'
        f'<circle cx="81.5" cy="35" r="4.2" fill="{P["berry"]}"/>'
        f'<circle cx="75.5" cy="39.5" r="3.8" fill="{P["berry"]}"/>'
        '</svg>')


def _contrast(fg: str, bg: str) -> float:
    def lum(h):
        h = h.lstrip("#")
        out = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]

    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def _hex(v) -> str | None:
    v = v.get("hex") if isinstance(v, dict) else v
    return v if isinstance(v, str) and v.startswith("#") and len(v) == 7 else None


def identity() -> Sourced:
    """Palette, type and mark SVG for the preview, from lane A when available.

    Lane A's interface (`brand.identity_system`): PALETTE, ROLES (semantic web roles, every
    text pair >= 4.5:1), TYPOGRAPHY[role]["css"], icon_svg(), lockup_stacked_svg(tagline=...),
    DIRECTION_ID, STATUS. A role this layout needs that lane A does not name keeps the
    fallback; any text colour that would fall under 4.5:1 on its ground keeps the fallback.
    """
    mod = _import("brambleloop.brand.identity_system")
    notes: list[str] = []
    palette = dict(FALLBACK_PALETTE)
    types = dict(FALLBACK_TYPE)
    mark = None
    direction = status = None
    if mod is not None:
        roles = getattr(mod, "ROLES", None) or {}
        pal = getattr(mod, "PALETTE", None) or {}
        src = {str(k).lower(): _hex(v) for k, v in {**pal, **roles}.items() if _hex(v)}
        mapping = {"paper": ("surface", "petal", "paper"), "cream": ("background", "paper"),
                   "line": ("rule", "sage_mist"), "sage": ("leaf", "sage"),
                   "forest": ("text", "forest"), "rose": ("accent", "rose"),
                   "berry": ("berry",), "ink": ("text", "forest"),
                   "muted": ("text_muted",), "sage_deep": ("accent_text", "rose_deep"),
                   "night": ("inverse_background", "forest")}
        used = []
        for role, names in mapping.items():
            for n in names:
                if src.get(n):
                    palette[role] = src[n]
                    used.append(role)
                    break
        # keep every text pairing readable whatever the peer supplied
        for role in ("ink", "muted", "forest", "sage_deep", "berry"):
            for ground in ("paper", "cream"):
                if _contrast(palette[role], palette[ground]) < 4.5:
                    notes.append(f"{role} on {ground} under 4.5:1 -- fallback kept")
                    palette[role] = FALLBACK_PALETTE[role]
        if _contrast(palette["paper"], palette["berry"]) < 4.5:
            palette["berry"] = FALLBACK_PALETTE["berry"]
        notes.append(f"palette roles from lane A: {', '.join(sorted(set(used)))}")
        ty = getattr(mod, "TYPOGRAPHY", None)
        if isinstance(ty, dict):
            for role, names in (("display", ("display", "wordmark")), ("body", ("ui", "body"))):
                for n in names:
                    v = ty.get(n)
                    css = v.get("css") if isinstance(v, dict) else v
                    if isinstance(css, str) and css.strip():
                        types[role] = css
                        break
            story = ty.get("body")
            if isinstance(story, dict) and story.get("css"):
                types["story"] = story["css"]
        fn = getattr(mod, "icon_svg", None) or getattr(mod, "mark_svg", None)
        if callable(fn):
            try:
                out = fn()
                if isinstance(out, str) and out.lstrip().startswith("<svg"):
                    mark = out
            except Exception as exc:  # noqa: BLE001
                notes.append(f"icon_svg failed: {type(exc).__name__}")
        direction = getattr(mod, "DIRECTION_ID", None)
        status = getattr(mod, "STATUS", None)
    types.setdefault("story", types["body"])
    value = {"palette": palette, "type": types,
             "mark_svg": mark or _fallback_mark(palette["cream"]),
             "mark_source": PEER if mark else FALLBACK, "direction": direction,
             "status": (status or {}).get("state") if isinstance(status, dict) else status}
    return Sourced(value, PEER if mod is not None else FALLBACK,
                   "brambleloop.brand.identity_system" if mod is not None
                   else "preview_sources.FALLBACK_PALETTE", notes)


def lockup_svg(tagline: str) -> str | None:
    """Lane A's stacked lockup (outlined marks, no live text) with lane C's tagline, or None."""
    mod = _import("brambleloop.brand.identity_system")
    fn = getattr(mod, "lockup_stacked_svg", None) if mod is not None else None
    if not callable(fn):
        return None
    try:
        out = fn(tagline=tagline, transparent=True)
    except TypeError:
        try:
            out = fn()
        except Exception:  # noqa: BLE001
            return None
    except Exception:  # noqa: BLE001
        return None
    return out if isinstance(out, str) and out.lstrip().startswith("<svg") else None


# ---- copy (lane C) ------------------------------------------------------------------------

# Interim words, used only until lane C's copy_v2 is present. Plain, warm, truthful: no
# technology in the story, verification translated into what it means for the maker, Laura
# introduced with the AI disclosure the D-FB-13 wording requires.
FALLBACK_COPY: dict = {
    "tagline": "Crochet patterns for a calmer, cosier home",
    "shop_title": "Calm, clear crochet patterns for home and baby",
    "announcement": ("Our first patterns are here: nesting baskets, a textured baby blanket "
                     "and hexagon coasters, each in US and UK terms."),
    "trust": [
        {"title": "Instant download", "text": "A PDF you can open on your phone or print."},
        {"title": "US and UK terms", "text": "Two complete files with every pattern."},
        {"title": "Free corrections", "text": "If we fix a pattern, every buyer gets the new file."},
        {"title": "Sell what you make", "text": "Small makers may sell their finished pieces."},
    ],
    "laura_intro": ("Brambleloop is Laura's company. Laura is Brambleloop's AI founder: she "
                    "chooses what we make next and keeps every pattern in this shop to one "
                    "standard."),
    "about": [
        "We make crochet patterns for the quieter corners of a home: baskets that hold the "
        "everyday, blankets for the smallest people, and small pieces that make good gifts.",
        "A good pattern should let you relax into it. Ours are written to be read row by "
        "row without second-guessing, with charts that match the words and sizes given in "
        "centimetres.",
    ],
    "proof_title": "Patterns you can trust",
    "proof": [
        "Every stitch count is checked before a pattern is released, so the numbers add up.",
        "Charts and written instructions always agree.",
        "If something is ever wrong, we correct the pattern and send the new file to everyone "
        "who bought it.",
    ],
    "seasonal": {"title": "Winter at Brambleloop",
                 "text": "A seasonal look for the shop. No seasonal patterns are listed yet."},
    "image_note": "Images are digital renderings of each finished design, not photographs.",
}


# Which of lane C's trust signals lead the trust band (customer value), and which sit in the
# About's promise box (how that value is earned). Unknown keys keep C's order.
TRUST_BAND = ("instant", "us_uk", "corrections", "licence")
TRUST_PROMISE = ("reverse_checked", "compiler_checked", "renders_labelled", "answers")
_TRUST_SUB = {"instant": "Open it on your phone or print it.",
              "us_uk": "Two complete files with every pattern.",
              "corrections": "The new file reaches every buyer.",
              "licence": "Individual makers and small businesses."}


def copy() -> Sourced:
    """The v2 storefront words, from lane C's `store_foundation.copy_v2.export()`.

    Mapping (lane C's names -> this layout): BANNER["line"] -> banner tagline; TAGLINE ->
    shop title under the name; ANNOUNCEMENT; ABOUT_PARAGRAPHS (Laura is introduced inside
    them, so no separate intro); TRUST_SIGNALS split into the trust band and the About's
    promise box; faq(); policies; store_disclosure(); SECTIONS names by slug; PAGE_HEADINGS.
    """
    mod = _import("brambleloop.store_foundation.copy_v2")
    out = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
           for k, v in FALLBACK_COPY.items()}
    out.update({"headings": {}, "sections": {}, "policies": {}, "seller_caption": None,
                "faqs": None, "disclosure": None, "support": None})
    exp = None
    if mod is not None and callable(getattr(mod, "export", None)):
        try:
            exp = mod.export()
        except Exception:  # noqa: BLE001 - a broken peer is a fallback
            exp = None
    if not isinstance(exp, dict):
        return Sourced(out, FALLBACK, "preview_sources.FALLBACK_COPY",
                       ["copy_v2 not available: interim layout copy shown"])
    got = []

    def take(key, value):
        if value:
            out[key] = value
            got.append(key)

    banner = exp.get("banner") or {}
    take("tagline", banner.get("line") if isinstance(banner, dict) else None)
    take("shop_title", exp.get("tagline"))
    take("announcement", exp.get("announcement"))
    paras = exp.get("about_paragraphs")
    if isinstance(paras, (list, tuple)) and paras:
        take("about", [str(x) for x in paras])
        out["laura_intro"] = ""           # C's About introduces Laura in its own order
    signals = [t for t in exp.get("trust_signals") or [] if isinstance(t, dict) and t.get("text")]
    if signals:
        by = {t.get("key"): t for t in signals}
        band = [by[k] for k in TRUST_BAND if k in by] or signals[:4]
        take("trust", [{"title": t["text"], "text": _TRUST_SUB.get(t.get("key"), "")}
                       for t in band])
        rest = [by[k] for k in TRUST_PROMISE if k in by] or [t for t in signals
                                                              if t not in band]
        take("proof", [t["text"] for t in rest])
    take("proof_title", exp.get("trust_headline"))
    faqs = exp.get("faq")
    if isinstance(faqs, list) and faqs and all(
            isinstance(f, dict) and f.get("question") and f.get("answer") for f in faqs):
        take("faqs", [{"question": str(f["question"]), "answer": str(f["answer"])}
                      for f in faqs])
    take("headings", {str(k): str(v) for k, v in (exp.get("page_headings") or {}).items()})
    take("sections", {str(x["slug"]): str(x["name"]) for x in exp.get("sections") or []
                      if isinstance(x, dict) and x.get("slug") and x.get("name")})
    pol = exp.get("policies")
    if isinstance(pol, dict):
        take("policies", {str(k): str(v) for k, v in pol.items() if isinstance(v, str)})
    take("disclosure", exp.get("store_disclosure"))
    take("support", exp.get("support_contact"))
    take("seller_caption", exp.get("seller_caption"))
    seas = exp.get("seasonal_announcements")
    head = (exp.get("page_headings") or {}).get("seasonal")
    if head:
        out["seasonal"] = {"title": str(head), "text": FALLBACK_COPY["seasonal"]["text"]}
        got.append("seasonal")
    return Sourced(out, PEER if got else FALLBACK,
                   "brambleloop.store_foundation.copy_v2" if got
                   else "preview_sources.FALLBACK_COPY",
                   [f"from lane C ({exp.get('version')}): {', '.join(got)}"]
                   + ([f"seasonal drafts: {', '.join(seas)}"] if isinstance(seas, dict) else []))


# ---- banner crop geometry (lane I) -------------------------------------------------------

def banner_spec() -> Sourced:
    """Banner canvas and the phone crop window, from lane I's verified Etsy constraints.

    Lane I (`integrations.etsy_constraints`) quotes Etsy's help centre: big banner recommended
    1600 x 400 px; how much of it a phone shows is UNKNOWN (Etsy publishes no crop geometry).
    So the canvas size is taken from lane I when present, and the phone window stays the
    repo's ASSUMED 2:1 centre crop, labelled as an assumption either way.
    """
    from ..brand import storefront
    from ..brand import storefront_preview as sp

    mod = _import("brambleloop.integrations.etsy_constraints")
    cons = getattr(mod, "CONSTRAINTS", None) if mod is not None else None
    if isinstance(cons, dict) and "big_banner_recommended_px" in cons:
        c = cons["big_banner_recommended_px"]
        crop = cons.get("banner_mobile_crop")
        try:
            w, h = c.value
            crop_basis = getattr(crop, "basis", "UNKNOWN") if crop is not None else "UNKNOWN"
            return Sourced(
                {"canvas": (int(w), int(h)), "phone_aspect": sp.PHONE_BANNER_ASPECT,
                 "canvas_basis": c.basis, "phone_basis": crop_basis,
                 "basis": (f"canvas {w}x{h} ({c.basis}, Etsy help centre via lane I); phone "
                           f"crop {crop_basis} at Etsy, so a 2:1 centre crop is ASSUMED here "
                           f"-- check the real crop in the Etsy app after upload")},
                PEER, "brambleloop.integrations.etsy_constraints")
        except Exception:  # noqa: BLE001 - malformed peer data falls back
            pass
    return Sourced({"canvas": tuple(storefront.BANNER_SIZE), "phone_aspect": sp.PHONE_BANNER_ASPECT,
                    "canvas_basis": "REPO_ASSERTED", "phone_basis": "ASSUMED",
                    "basis": "canvas 1600x400 repo-asserted; phone 2:1 centre crop ASSUMED; "
                             "Etsy's own numbers UNVERIFIED here"},
                   FALLBACK, "brand.storefront + brand.storefront_preview")


def etsy_notes() -> list[str]:
    """Lane I facts that change how the preview must be read (empty when lane I is absent)."""
    mod = _import("brambleloop.integrations.etsy_constraints")
    cons = getattr(mod, "CONSTRAINTS", None) if mod is not None else None
    if not isinstance(cons, dict):
        return []
    out = []
    for key in ("profile_is_account_level", "thumbnail_crops", "logo_crop"):
        c = cons.get(key)
        if c is not None:
            out.append(f"{key}: {getattr(c, 'what', '')} -- {getattr(c, 'note', '') or getattr(c, 'quote', '')}")
    return out
