"""The storefront trust gate on rendered assets and real copy (K2: F-233/234/235/237/263/279).

`brand.storefront.check_storefront` used to pass the icon and banner when their *brief
strings* were non-empty. A shop is not complete because a brief exists; it is complete when
the icon a buyer will see is legible at the sizes Etsy shows it, the banner composition holds
the mark inside every crop, the About a buyer reads is substantive and truthful, the trust
surfaces answer a first-time buyer's questions, the sections read as a buyer browses, and the
banner, announcement and grid tell one story.

This module checks those things on the actual assets and words:

* icon  -- lane A's `brand.identity_system.icon_raster(px)` rasterised at 40 and 70 px
           (Etsy's display sizes as the repo models them) and measured: contrast of mark
           against ground, coverage, and a stroke that survives;
* banner-- lane A's stacked lockup in the v2 banner composition (`preview_v2._geometry`)
           against the banner canvas from lane I's Etsy constraints: lockup inside the phone
           window, rendered tall enough on a 390 px phone; and whether a raster export for
           upload exists (it does not yet: an honest FAIL, not a pass on a description);
* copy  -- lane C's `store_foundation.copy_v2` (falling back to the drafted surfaces in
           `store_foundation.content`) through `store_foundation.lint` truth rules, plus the
           buyer-question coverage F-234 names and the jargon rule for the top surfaces.

A missing peer is a FAIL with the reason ("asset not rendered"), never a pass. No network,
no image model, no spend. Each finding names the F-row it serves.

`problems()` is the list `check_storefront` appends (WIRING REQUEST to lane A, which owns
`brand/storefront.py`); `evaluate()` is the per-row view for the Command Center and handoff.
"""
from __future__ import annotations

import re

from . import preview_sources as S

ROWS = ("F-233", "F-234", "F-235", "F-237", "F-263", "F-279")
ICON_SIZES = (40, 70)
ICON_MIN_CONTRAST = 3.0
ICON_COVERAGE = (0.08, 0.70)
ICON_MIN_STROKE_PX = 2
PHONE_WIDTH = 390
LOCKUP_MIN_PHONE_PX = 96          # the wordmark is about a sixth of the stacked lockup: >= 16 px
SECTION_NAME_MAX = 24            # Etsy help centre via lane I (integrations.etsy_constraints)
ABOUT_MIN = 400                   # brand.storefront.ABOUT_MIN
PRODUCT_NOUNS = ("basket", "blanket", "coaster", "cardigan", "sweater", "jumper", "hat",
                 "beanie", "scarf", "shawl", "bag", "tote", "amigurumi", "toy", "pillow",
                 "cushion", "rug", "mitten", "sock", "throw")
INTERNAL_SECTION = re.compile(r"(_|\blaunch|\bdept\b|\bdepartment\b|\bmisc\b|^other$|\btest\b|\bdraft\b|\btbd\b|^\w+-\w+$)",
                              re.I)


def _f(row: str, code: str, detail: str) -> dict:
    return {"row": row, "code": code, "detail": detail}


# ---- icon ------------------------------------------------------------------------------------

def icon_legibility(arr, size: int) -> dict:
    """Measure one rasterised icon (H x W x 3 array or PIL image) at `size` px."""
    import numpy as np

    a = np.asarray(arr, dtype=float)
    if a.ndim == 2:
        a = np.stack([a] * 3, axis=-1)
    a = a[..., :3]
    if a.max() <= 1.0:
        a = a * 255.0
    if a.shape[0] != size or a.shape[1] != size:
        from PIL import Image

        a = np.asarray(Image.fromarray(a.clip(0, 255).astype("uint8")).resize(
            (size, size), Image.LANCZOS), dtype=float)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    # ground = the border colour (the icon is a mark on a square ground)
    border = np.concatenate([lum[0], lum[-1], lum[:, 0], lum[:, -1]])
    ground = float(np.median(border))
    dist = np.abs(lum - ground)
    mark = dist > 40.0
    coverage = float(mark.mean())

    def rel(v):
        c = v / 255.0
        c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]

    if mark.any() and (~mark).any():
        lm, lg = float(rel(a[mark]).mean()), float(rel(a[~mark]).mean())
        contrast = (max(lm, lg) + 0.05) / (min(lm, lg) + 0.05)
    else:
        contrast = 1.0
    # the thickest run of mark pixels on any row: the stroke a shopper resolves
    stroke = 0
    for row in mark:
        run = best = 0
        for v in row:
            run = run + 1 if v else 0
            best = max(best, run)
        stroke = max(stroke, best)
    problems = []
    if contrast < ICON_MIN_CONTRAST:
        problems.append(f"contrast {contrast:.2f}:1 under {ICON_MIN_CONTRAST}:1")
    if not ICON_COVERAGE[0] <= coverage <= ICON_COVERAGE[1]:
        problems.append(f"mark covers {coverage:.0%}, outside "
                        f"{ICON_COVERAGE[0]:.0%}-{ICON_COVERAGE[1]:.0%}")
    if stroke < ICON_MIN_STROKE_PX:
        problems.append(f"no stroke survives ({stroke} px)")
    return {"size": size, "contrast": round(contrast, 2), "coverage": round(coverage, 3),
            "max_stroke_px": stroke, "ok": not problems, "problems": problems}


def check_icon() -> tuple[list[dict], dict]:
    mod = S._import("brambleloop.brand.identity_system")
    fn = getattr(mod, "icon_raster", None) if mod is not None else None
    if not callable(fn):
        return ([_f("F-233", "STORE_ICON_NOT_RENDERED",
                    "no rendered icon asset: brand.identity_system.icon_raster is absent; a "
                    "brief is not an icon")], {"rendered": False})
    out, sizes = [], {}
    for px in ICON_SIZES:
        try:
            m = icon_legibility(fn(px), px)
        except Exception as exc:  # noqa: BLE001 - a failed render is a failed icon
            out.append(_f("F-233", "STORE_ICON_RENDER_FAILED", f"{px} px: {type(exc).__name__}: "
                          f"{str(exc)[:120]}"))
            continue
        sizes[px] = m
        for p in m["problems"]:
            out.append(_f("F-233", "STORE_ICON_ILLEGIBLE", f"icon at {px} px: {p}"))
    return out, {"rendered": True, "sizes": sizes,
                 "direction": getattr(mod, "DIRECTION_ID", None)}


# ---- banner ----------------------------------------------------------------------------------

def check_banner(tagline: str) -> tuple[list[dict], dict]:
    from . import preview_v2

    out: list[dict] = []
    spec = S.banner_spec()
    g = preview_v2._geometry(spec.value)
    lockup = S.lockup_svg(tagline)
    info = {"canvas": list(spec.value["canvas"]), "canvas_source": spec.source,
            "basis": spec.value["basis"], "lockup": bool(lockup)}
    if not lockup:
        out.append(_f("F-233", "STORE_BANNER_NOT_RENDERED",
                      "no banner lockup asset: brand.identity_system.lockup_stacked_svg is "
                      "absent; a brief is not a banner"))
        return out, info
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', lockup)
    aspect = float(m.group(1)) / float(m.group(2)) if m else 1.6
    lo, hi = g["win"]
    a, b = g["lock"]
    if not (lo - 1e-9 <= a and b <= hi + 1e-9):
        out.append(_f("F-233", "STORE_BANNER_LOCKUP_CROPPED",
                      "the lockup leaves the phone crop window"))
    w, h = spec.value["canvas"]
    canvas_px = PHONE_WIDTH / (hi - lo)             # canvas width when the window is 390 px
    box_w, box_h = (b - a) * canvas_px, canvas_px / (w / h) * 0.86
    lock_h = min(box_w / aspect, box_h)
    info["lockup_phone_px"] = round(lock_h, 1)
    if lock_h < LOCKUP_MIN_PHONE_PX:
        out.append(_f("F-233", "STORE_BANNER_LOCKUP_SMALL",
                      f"lockup {lock_h:.0f} px tall on a {PHONE_WIDTH} px phone, under "
                      f"{LOCKUP_MIN_PHONE_PX} px"))
    exporter = getattr(S._import("brambleloop.brand.identity_system"), "banner_png", None)
    info["raster_export"] = callable(exporter)
    if not callable(exporter):
        out.append(_f("F-233", "STORE_BANNER_NOT_EXPORTED",
                      f"no {w}x{h} raster banner exists for upload (the composition renders "
                      f"in the owner preview only); export without Laura until her imagery "
                      f"is publication-approved"))
    if spec.source != S.PEER:
        out.append(_f("F-233", "STORE_BANNER_SIZE_UNSOURCED",
                      "banner canvas size not read from lane I's Etsy constraints"))
    return out, info


# ---- copy ------------------------------------------------------------------------------------

def _copy_and_surfaces(db=None):
    from . import content as C

    surfaces = C.build(db)
    cp = S.copy()
    return cp, surfaces


def check_copy(db=None) -> tuple[list[dict], dict]:
    from . import lint
    from .preview_v2 import jargon_hits

    cp, s = _copy_and_surfaces(db)
    v = cp.value
    out: list[dict] = []
    info = {"copy_source": cp.source, "copy_origin": cp.origin}
    if cp.source != S.PEER:
        out.append(_f("F-233", "STORE_COPY_INTERIM",
                      "lane C's copy_v2 is not present: the storefront words are interim"))

    def truth(row, name, text):
        for f in lint.lint(text, voice=False):
            if f["kind"] == lint.TRUTH:
                out.append(_f(row, "STORE_COPY_UNTRUE", f"{name}: {f['code']}: {f['match']!r}"))

    top = {"tagline": v.get("tagline", ""), "shop_title": v.get("shop_title", ""),
           "announcement": v.get("announcement", "")}
    for name, text in top.items():
        if not str(text).strip():
            out.append(_f("F-233", "STORE_SURFACE_BLANK", f"{name} is blank"))
            continue
        truth("F-233", name, text)
        hits = jargon_hits(text)
        if hits:
            out.append(_f("F-233", "STORE_TOP_COPY_TECHNICAL",
                          f"{name} leads with implementation words {sorted(set(hits))}"))
    # F-235 About: substantive, truthful, introduces Laura with her AI disclosure
    about = "\n\n".join([v.get("laura_intro", "")] + list(v.get("about") or [])
                        + list(v.get("proof") or []))
    if len(about) < ABOUT_MIN:
        out.append(_f("F-235", "STORE_ABOUT_THIN", f"About is {len(about)} characters, under "
                      f"{ABOUT_MIN}"))
    truth("F-235", "about", about)
    if "Laura" in about and "AI" not in about:
        out.append(_f("F-235", "STORE_ABOUT_LAURA_UNDISCLOSED",
                      "About names Laura without saying she is an AI"))
    # F-234 trust architecture: the questions a first-time buyer must not have to infer
    trust = list(v.get("trust") or [])
    if len(trust) < 3:
        out.append(_f("F-234", "STORE_TRUST_THIN", f"{len(trust)} trust points, need >= 3"))
    for t in trust:
        truth("F-234", "trust", f"{t.get('title', '')}. {t.get('text', '')}")
    faqs = v.get("faqs") or s["faq"].value
    corpus = " ".join([about, " ".join(f"{t.get('title')} {t.get('text')}" for t in trust)]
                      + [f"{f['question']} {f['answer']}" for f in faqs]
                      + [str(s[k].value) for k in ("policy_delivery", "policy_returns",
                                                   "policy_licence", "support_contact")]).lower()
    needs = {"what is sold": ("pattern",), "what the buyer receives": ("pdf",),
             "digital delivery": ("download", "purchases and downloads"),
             "skill expectations": ("skill", "difficulty", "beginner"),
             "support path": ("message",), "returns": ("cannot be returned", "refund")}
    for need, words in needs.items():
        if not any(w in corpus for w in words):
            out.append(_f("F-234", "STORE_TRUST_GAP", f"nothing tells a buyer {need}"))
    disc = str(s["disclosures"].value)
    truth("F-234", "disclosures", disc)
    if "not a photograph" not in disc.lower():
        out.append(_f("F-234", "STORE_RENDER_DISCLOSURE_MISSING",
                      "image disclosure does not say renders are not photographs"))
    if re.search(r"\b\d[\d,]*\s*(sales|reviews|favou?rites|orders|happy customers)\b",
                 corpus, re.I):
        out.append(_f("F-234", "STORE_SOCIAL_PROOF_CLAIM", "copy states social-proof figures"))
    info["trust_points"] = len(trust)
    return out, info


# ---- sections and continuity -----------------------------------------------------------------

def check_sections(db=None) -> tuple[list[dict], dict]:
    from . import content as C

    s = C.build(db)
    out: list[dict] = []
    secs = s["sections"].value
    shown = [x for x in secs if x["shown"]]
    limit, basis = SECTION_NAME_MAX, "fallback"
    cons = getattr(S._import("brambleloop.integrations.etsy_constraints"), "CONSTRAINTS", None)
    if isinstance(cons, dict) and "section_name_max_chars" in cons:
        limit = int(cons["section_name_max_chars"].value)
        basis = cons["section_name_max_chars"].basis
    if not shown:
        out.append(_f("F-237", "STORE_NO_SECTIONS_SHOWN", "no section is shown"))
    for x in secs:
        if INTERNAL_SECTION.search(x["name"]) or x["name"].isupper():
            out.append(_f("F-237", "STORE_SECTION_NAME_INTERNAL",
                          f"section {x['name']!r} does not read as a buyer browses"))
        if len(x["name"]) > limit:
            out.append(_f("F-237", "STORE_SECTION_NAME_TOO_LONG",
                          f"section {x['name']!r} is {len(x['name'])} characters; Etsy allows "
                          f"{limit} ({basis})"))
        if x["shown"] and not x["listings"]:
            out.append(_f("F-237", "STORE_SECTION_EMPTY_SHOWN", f"{x['name']!r} is shown empty"))
    return out, {"sections": [x["name"] for x in shown]}


def check_continuity(db=None) -> tuple[list[dict], dict]:
    from . import content as C

    s = C.build(db)
    v = S.copy().value
    out: list[dict] = []
    grid = " ".join(p["title"] for p in s["opening_grid"].value).lower()
    if not s["opening_grid"].value:
        out.append(_f("F-233", "STORE_GRID_EMPTY", "no ordered listings in the opening grid"))
    ann = str(v.get("announcement", "")).lower()
    for noun in PRODUCT_NOUNS:
        if re.search(rf"\b{noun}s?\b", ann) and noun not in grid:
            out.append(_f("F-279", "STORE_ANNOUNCEMENT_OFF_GRID",
                          f"announcement promises {noun!r}, which is not in the grid"))
    seasonal_listed = any(x["slug"] == "seasonal" and x["listings"]
                          for x in s["sections"].value)
    info = {"seasonal_live": seasonal_listed,
            "banner_tagline_is_shop_tagline": True}
    # the banner lockup is drawn with the same tagline the shop shows (preview_v2 passes
    # copy["tagline"]); a seasonal banner may go live only with seasonal listings to land on
    if not seasonal_listed:
        info["seasonal_banner"] = "preview only: no seasonal listings to land on"
    return out, info


# ---- roll-up ---------------------------------------------------------------------------------

def evaluate(db=None) -> dict:
    """Per-row status for K2. FAIL when any finding exists for the row; F-263 (ads gate)
    inherits every storefront finding, because traffic may not be bought to an unfinished
    shop."""
    findings: list[dict] = []
    info: dict = {}
    copy_info = None
    for name, fn in (("icon", check_icon), ("copy", lambda: check_copy(db)),
                     ("sections", lambda: check_sections(db)),
                     ("continuity", lambda: check_continuity(db))):
        try:
            f, i = fn()
        except Exception as exc:  # noqa: BLE001 - the gate fails closed
            f, i = [_f("F-233", "STORE_GATE_ERROR", f"{name}: {type(exc).__name__}: "
                       f"{str(exc)[:160]}")], {}
        findings += f
        info[name] = i
        if name == "copy":
            copy_info = i
    try:
        f, i = check_banner(S.copy().value["tagline"])
    except Exception as exc:  # noqa: BLE001
        f, i = [_f("F-233", "STORE_GATE_ERROR", f"banner: {type(exc).__name__}")], {}
    findings += f
    info["banner"] = i
    rows = {}
    for row in ROWS:
        own = [x for x in findings if x["row"] == row]
        if row == "F-263":
            own = list(findings)
        rows[row] = {"status": "FAIL" if own else "PASS", "findings": own}
    return {"rows": rows, "findings": findings, "info": info,
            "ok": not findings, "copy": copy_info,
            "basis": "measured: rendered icon rasters, banner geometry, lint over the copy"}


def problems(db=None) -> list[str]:
    """`check_storefront`-style strings (one per finding), for the launch trust ladder."""
    return [f"{x['code']}: {x['detail']} ({x['row']})" for x in evaluate(db)["findings"]]
