"""brambleloop.brand.comparison -- side-by-side identity candidates for the owner's logo decision.

Wave 3, lane A2. The owner has NOT locked a mark: D1 "Briar Monogram" is a finalist, not the
answer. This module puts the finalists through the same contexts at the same sizes so the owner
can choose. It recommends nothing.

Candidates
  * D1 Briar Monogram    -- `identity_system` (vector, outlined, deterministic)
  * Owner concept        -- the owner-supplied raster, shown AS SUPPLIED: only cropped (to its
                            monogram for icon sizes, to its lockup for banner/header) and
                            resampled. Never traced, redrawn, recoloured or cleaned up. The one
                            derived view is the monochrome check, labelled as a derived
                            luminance threshold, because a raster has no designed one-ink version.
  * D2 Chain Link, D3 Drupelet -- the next finalists from `brand.judge` (ranked 2 and 3, tied
                            on total 73.3 in research/final_build/w3/evidence/A_judge_verdict.json).

Every measurement is the same procedure for every candidate (`measure`), on a 500 px square
icon (Etsy's verified minimum logo size, `etsy_constraints.logo_min_px`).

Read-only on `identity_system`, `directions` and lane B's `store_foundation.preview_v2`: the
storefront mock is lane B's v2 renderer with the candidate's icon and lockup injected into its
render context (`storefront_html`); the layout, copy, palette and type are lane B's / lane C's /
D1's tokens held constant for every candidate.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from . import directions as _D
from . import identity_system as I

OWNER_SHA256 = "28f301b28766acea7b0f632ceefcb1c66e271a6fba8da0c84a65c94647d35998"
OWNER_LABEL = "Owner concept (raster, as supplied)"
OWNER_ENV = "BRAMBLELOOP_OWNER_LOGO_CONCEPT"
# Crop boxes (x0, y0, x1, y1) inside the 1536x1024 owner raster, found from its ink bands
# (paper colour #F3EEE7 sampled at the border). Monogram: B + sprig + yarn + ball. Lockup: the
# whole stacked lockup (monogram, wordmark, descriptor, script tagline, category line).
# Header lockup: monogram + wordmark + descriptor, without the script tagline.
OWNER_CROP_MARK = (470, 45, 1060, 574)
OWNER_CROP_LOCKUP = (190, 45, 1346, 960)
OWNER_CROP_HEADER = (190, 45, 1346, 735)
OWNER_WORDMARK_CAP_PX = 88          # BRAMBLELOOP cap height in the source raster (rows 580-668)
OWNER_SIZE = (1536, 1024)

FINALIST_IDS = ("D1-briar-monogram", "D2-chain-link", "D3-drupelet")
ICON_PX = 500                       # Etsy logo minimum and recommended (verified, lane I)
SMALL = (40, 70)

# Neutral common grounds for the monochrome test (D1's paper and forest, used for every
# candidate so the grounds do not differ between them).
BLACK = "#111111"
CREAM = I.PALETTE["paper"]
FOREST = I.PALETTE["forest"]


@dataclass
class Candidate:
    key: str
    label: str
    kind: str                         # "vector" | "raster"
    direction_id: str | None = None
    source: str = ""
    notes: list[str] = field(default_factory=list)


def owner_path() -> Path | None:
    """The owner raster, if present and byte-identical to what the owner supplied: the
    repository copy (`canonical_assets`, D-FB-17), or `BRAMBLELOOP_OWNER_LOGO_CONCEPT` when it
    hashes to the same bytes."""
    from . import canonical_assets as CA

    env = os.environ.get(OWNER_ENV)
    cands = [Path(env)] if env else []
    cands.append(CA.path(CA.HERO_LOGO))
    for p in cands:
        if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == OWNER_SHA256:
            return p
    return None


def candidates(include_owner: bool = True) -> list[Candidate]:
    out = []
    for did in FINALIST_IDS:
        d = _D.DIRECTIONS[did]
        out.append(Candidate(did.split("-")[0], f"{did.split('-')[0]} {d.name}", "vector", did,
                             "brand.directions (deterministic SVG, outlined OFL type)"))
        if did == FINALIST_IDS[0] and include_owner and owner_path() is not None:
            out.append(Candidate(
                "OWNER", OWNER_LABEL, "raster", None,
                f"owner-supplied PNG {OWNER_SIZE[0]}x{OWNER_SIZE[1]}, sha256 {OWNER_SHA256[:12]}",
                ["cropped and resampled only; no tracing, redrawing or recolouring",
                 "no horizontal lockup or designed one-ink version exists for this raster",
                 "its tagline and category line are part of the supplied artwork"]))
    return out


# ---- images ---------------------------------------------------------------------------------

def _pil():
    from PIL import Image

    return Image


@lru_cache(maxsize=1)
def _owner_rgb():
    p = owner_path()
    if p is None:
        raise FileNotFoundError("owner concept raster not available (sha256 mismatch or missing)")
    return _pil().open(p).convert("RGB")


def owner_ground() -> str:
    import numpy as np

    a = np.asarray(_owner_rgb())
    edge = np.concatenate([a[:20].reshape(-1, 3), a[-20:].reshape(-1, 3)])
    r, g, b = (int(v) for v in np.median(edge, 0))
    return f"#{r:02X}{g:02X}{b:02X}"


def _pad_square(im, colour: str):
    Image = _pil()
    w, h = im.size
    n = max(w, h)
    out = Image.new("RGB", (n, n), colour)
    out.paste(im, ((n - w) // 2, (n - h) // 2))
    return out


def ground(c: Candidate) -> str:
    return owner_ground() if c.kind == "raster" else I.get_direction(c.direction_id).ground("colour")


def icon_image(c: Candidate, px: int = ICON_PX):
    """Square RGB icon at `px`. Raster: monogram crop padded with its own paper colour."""
    Image = _pil()
    if c.kind == "raster":
        sq = _pad_square(_owner_rgb().crop(OWNER_CROP_MARK), owner_ground())
        return sq.resize((px, px), Image.LANCZOS)
    arr = I.icon_raster(px, "colour", direction_id=c.direction_id)
    return Image.open(io.BytesIO(_to_png(arr))).convert("RGB")


def _to_png(arr) -> bytes:
    from .vector import to_png_bytes

    return to_png_bytes(arr)


def small_icon(c: Candidate, px: int):
    """The icon as a browser would show a 500 px upload at `px` (Lanczos downsample)."""
    return icon_image(c, ICON_PX).resize((px, px), _pil().LANCZOS)


def lockup_image(c: Candidate, width: int, *, header: bool = False):
    """RGB lockup image `width` wide. Vector: horizontal (header) or stacked lockup on the
    direction's own ground. Raster: the supplied lockup crop."""
    Image = _pil()
    if c.kind == "raster":
        im = _owner_rgb().crop(OWNER_CROP_HEADER if header else OWNER_CROP_LOCKUP)
    else:
        from .vector import rasterize

        d = I.get_direction(c.direction_id)
        m = d.lockup_horizontal() if header else d.lockup_stacked(tagline())
        arr = rasterize(m, d.colours("colour"), max(width, 600), ground=d.ground("colour"),
                        ss=3)
        im = Image.open(io.BytesIO(_to_png(arr))).convert("RGB")
    h = max(1, round(im.size[1] * width / im.size[0]))
    return im.resize((width, h), Image.LANCZOS)


def fit(im, box_w: int, box_h: int):
    s = min(box_w / im.size[0], box_h / im.size[1])
    return im.resize((max(1, round(im.size[0] * s)), max(1, round(im.size[1] * s))),
                     _pil().LANCZOS)


def tagline() -> str:
    try:
        from ..store_foundation import preview_sources as S

        return S.copy().value["tagline"]
    except Exception:  # noqa: BLE001
        return "Crochet patterns"


# ---- monochrome -----------------------------------------------------------------------------

def _lum(a):
    import numpy as np

    c = np.where(a <= 0.03928, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def otsu(values) -> float:
    import numpy as np

    hist, edges = np.histogram(values.ravel(), bins=256, range=(0.0, 1.0))
    w = hist.astype(float)
    mids = (edges[:-1] + edges[1:]) / 2
    best, thr = -1.0, 0.5
    for i in range(1, 256):
        w0, w1 = w[:i].sum(), w[i:].sum()
        if w0 == 0 or w1 == 0:
            continue
        m0 = (w[:i] * mids[:i]).sum() / w0
        m1 = (w[i:] * mids[i:]).sum() / w1
        v = w0 * w1 * (m0 - m1) ** 2
        if v > best:
            best, thr = v, edges[i]
    return float(thr)


def mono_alpha(c: Candidate, px: int = ICON_PX):
    """Ink coverage 0..1 for the one-ink version at `px`.

    Vector: the direction's own designed one-colour variant (ink depth from luminance between
    its ground and ink). Raster: DERIVED -- an Otsu luminance threshold of the supplied
    colours (at 2x, then averaged down), because no designed one-ink version exists.
    """
    import numpy as np

    if c.kind == "raster":
        big = np.asarray(icon_image(c, px * 2)).astype(np.float32) / 255
        lum = _lum(big)
        hard = (lum < otsu(lum)).astype(np.float32)
        return hard.reshape(px, 2, px, 2).mean((1, 3))
    d = I.get_direction(c.direction_id)
    arr = I.icon_raster(px, "mono", direction_id=c.direction_id)[..., :3]
    from .judge import _hex

    lg = float(_lum(np.array(_hex(d.ground("mono")), dtype=np.float32)))
    li = float(_lum(np.array(_hex(d.colours("mono")["ink"]), dtype=np.float32)))
    return np.clip((lg - _lum(arr)) / (lg - li), 0, 1)


def mono_image(c: Candidate, px: int, ink: str, on: str):
    import numpy as np

    from .judge import _hex

    a = mono_alpha(c, ICON_PX)[..., None]
    out = np.array(_hex(on), np.float32) * (1 - a) + np.array(_hex(ink), np.float32) * a
    im = _pil().fromarray((out * 255 + 0.5).astype("uint8"), "RGB")
    return im if px == ICON_PX else im.resize((px, px), _pil().LANCZOS)


# ---- measurement (identical procedure for every candidate) ----------------------------------

def _wcag(l1: float, l2: float) -> float:
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)


def measure(c: Candidate) -> dict:
    import numpy as np

    from .judge import _erode, _hex, ink_mask

    g = ground(c)
    lg = float(_lum(np.array(_hex(g), np.float32)))
    a160 = np.asarray(small_icon(c, 160)).astype(np.float32) / 255
    a40 = np.asarray(small_icon(c, 40)).astype(np.float32) / 255
    m160, m40 = ink_mask(a160, g), ink_mask(a40, g)
    l40 = _lum(a40)
    ink40 = l40[m40]
    out: dict = {"candidate": c.key, "label": c.label, "kind": c.kind, "ground": g,
                 "basis": "measured on a 500 px square icon resampled (Lanczos) to 160/70/40 px"}
    out["ink_coverage_40"] = round(float(m40.mean()), 3)
    out["contrast_median_ink_40"] = round(_wcag(float(np.median(ink40)), lg), 2) if ink40.size else 0.0
    out["contrast_darkest_ink_40"] = (round(_wcag(float(np.percentile(ink40, 5)), lg), 2)
                                      if ink40.size else 0.0)
    # share of ink pixels at 40 px that reach at least 3:1 against the ground (WCAG non-text)
    lum_ok = np.array([_wcag(float(v), lg) >= 3.0 for v in ink40]) if ink40.size else np.array([])
    out["ink_at_3to1_share_40"] = round(float(lum_ok.mean()) if lum_ok.size else 0.0, 3)
    # detail retained at 40: edge correlation of the 40 px icon (upsampled back to 160) with the
    # 160 px icon. 1.0 = nothing lost.
    up = np.asarray(small_icon(c, 40).resize((160, 160), _pil().BICUBIC)).astype(np.float32) / 255
    e1 = np.hypot(*np.gradient(_lum(a160)))
    e2 = np.hypot(*np.gradient(_lum(up)))
    out["detail_retained_40"] = round(float(np.corrcoef(e1.ravel(), e2.ravel())[0, 1]), 3)
    # stroke survival (as brand.judge): ink at 160 eroded by 2 px (0.5 px each side at 40)
    er = _erode(m160, 2)
    out["stroke_survival_40"] = round(float(er.sum() / m160.sum()) if m160.sum() else 0.0, 3)
    yy, xx = np.mgrid[0:160, 0:160]
    outside = ((xx - 79.5) ** 2 + (yy - 79.5) ** 2) > (0.49 * 160) ** 2
    out["ink_outside_circle"] = round(float((m160 & outside).sum() / max(1, m160.sum())), 3)
    # monochrome: share of the colour icon's ink still inked in the one-ink version (160 px),
    # and edge correlation colour vs one-ink at 70 px
    ma = np.asarray(_pil().fromarray((mono_alpha(c) * 255).astype("uint8")).resize(
        (160, 160), _pil().LANCZOS)).astype(np.float32) / 255
    out["mono_ink_kept"] = round(float((ma[m160] > 0.5).mean()) if m160.any() else 0.0, 3)
    c70 = np.asarray(small_icon(c, 70)).astype(np.float32) / 255
    k70 = np.asarray(mono_image(c, 70, BLACK, CREAM)).astype(np.float32) / 255
    gc, gm = np.hypot(*np.gradient(_lum(c70))), np.hypot(*np.gradient(_lum(k70)))
    out["mono_edge_correlation_70"] = round(float(np.corrcoef(gc.ravel(), gm.ravel())[0, 1]), 3)
    out["mono_basis"] = ("designed one-colour variant" if c.kind == "vector"
                         else "DERIVED Otsu luminance threshold of the supplied raster")
    out["header_letter_px"] = header_letter_px(c)
    return out


def header_letter_px(c: Candidate) -> float:
    """Wordmark letter height (cap or x-height) when the header lockup is fitted in 280x40."""
    if c.kind == "raster":
        x0, y0, x1, y1 = OWNER_CROP_HEADER
        s = min(280 / (x1 - x0), 40 / (y1 - y0))
        return round(OWNER_WORDMARK_CAP_PX * s, 1)
    from .judge import measure_direction

    return float(measure_direction(I.get_direction(c.direction_id))["header_letter_px"])


# ---- storefront (lane B's v2 renderer, mark injected) ---------------------------------------

def data_uri_png(im, max_side: int | None = None) -> str:
    if max_side and max(im.size) > max_side:
        im = fit(im, max_side, max_side)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _marks(c: Candidate) -> tuple[str, str]:
    """(icon data URI, stacked-lockup data URI) for the candidate."""
    from ..store_foundation import preview_v2 as V2

    if c.kind == "raster":
        return (data_uri_png(icon_image(c, 256)),
                data_uri_png(_owner_rgb().crop(OWNER_CROP_LOCKUP), 700))
    icon = I.mark_svg("icon", direction_id=c.direction_id)
    lock = I.mark_svg("lockup_stacked", direction_id=c.direction_id, tagline=tagline(),
                      transparent=True)
    return V2._svg_uri(icon), V2._svg_uri(lock)


def _ctx(c: Candidate, viewport: str):
    from ..store_foundation import preview_v2 as V2

    ctx = V2._context(None, None, viewport)
    icon, lock = _marks(c)
    ctx["mark_uri"] = icon
    ctx["lockups"] = {"evergreen": "__LOCKUP__"}
    return ctx, lock


def _inject(css_or_html: str, lock: str) -> str:
    from ..store_foundation import preview_v2 as V2

    return css_or_html.replace(f'url("{V2._svg_uri("__LOCKUP__")}")', f'url("{lock}")')


def _banner_label(c: Candidate) -> str:
    return (f'<div class="a2tag">{c.label} -- identity comparison mock, not live; '
            f'Laura image: internal preview, not publication-approved</div>')


A2_CSS = (".a2tag{position:fixed;right:6px;bottom:6px;z-index:99;background:#111;color:#fff;"
          "font:600 11px/1.3 system-ui,sans-serif;padding:3px 7px;border-radius:4px;"
          "max-width:70%;opacity:.85}")


def storefront_html(c: Candidate, viewport: str = "mobile") -> str:
    """Lane B's v2 storefront with this candidate's icon and banner lockup. Script-free."""
    from ..store_foundation import preview_v2 as V2

    ctx, lock = _ctx(c, viewport)
    css = _inject(V2._vars_css(ctx), lock) + V2._css(ctx["p"], ctx["t"]) + A2_CSS
    body = V2._shop(ctx) + _banner_label(c)
    w = 390 if viewport == "mobile" else 1280
    html = V2._doc(f"Brambleloop identity comparison -- {c.label} ({viewport})", viewport,
                   css, body)
    return html.replace("<head>", f'<head><meta name="shoot" content="{w}x'
                        f'{844 if viewport == "mobile" else 800}">', 1)


def banner_html(c: Candidate) -> str:
    """The shop banner at Etsy's recommended 1600x400 (whole canvas)."""
    from ..integrations import etsy_constraints as E
    from ..store_foundation import preview_v2 as V2

    bw, bh = E.value("big_banner_recommended_px")
    ctx, lock = _ctx(c, "desktop")
    css = (_inject(V2._vars_css(ctx), lock) + V2._css(ctx["p"], ctx["t"]) + A2_CSS
           + f"body{{margin:0;width:{bw}px;height:{bh}px;overflow:hidden}}")
    body = V2._banner(ctx, mode="desktop", width=f"{bw}px") + _banner_label(c)
    html = V2._doc(f"Banner {bw}x{bh} -- {c.label}", "desktop", css, body)
    return html.replace("<head>", f'<head><meta name="shoot" content="{bw}x{bh}">', 1)


def summary() -> dict:
    """JSON-serialisable comparison record (no recommendation)."""
    from ..integrations import etsy_constraints as E

    cs = candidates()
    return {"as_of": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "decision": "OWNER_TO_DECIDE", "recommendation": None,
            "candidates": [{"key": c.key, "label": c.label, "kind": c.kind,
                            "direction_id": c.direction_id, "source": c.source,
                            "notes": c.notes} for c in cs],
            "measurements": {c.key: measure(c) for c in cs},
            "etsy": {"logo_min_px": E.value("logo_min_px"),
                     "big_banner_recommended_px": E.value("big_banner_recommended_px")},
            "owner_included": any(c.kind == "raster" for c in cs)}
