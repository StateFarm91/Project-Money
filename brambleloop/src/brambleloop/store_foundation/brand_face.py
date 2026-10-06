"""Laura in the Store Foundation: the brand face as one surface of one brand system.

Owner rulings 2026-10-06 (D-FB-11..13): Laura is a persistent AI person and the Founder/CEO of
Brambleloop; the approved woman is her permanent visual identity and the face of her company.
Publicly she is "Brambleloop's AI founder" -- never claimed to be human.
The shop is designed around one coherent system -- Laura, the
loop-and-bramble mark, the typography, the palette, product-first merchandising and the calm
voice -- and she appears where she earns it, not everywhere.

This module holds three things and refuses a fourth:

* the **usage plan**: every store/brand placement, whether Laura anchors it, is optional in
  it, or stays out of it (product-first), with the reason;
* the **readiness** of the brand face, which is GATED and can only become READY when a
  specific image of her is `publication_approved` after every customer-facing gate
  (`visual.canonical.CUSTOMER_FACING_GATES`). Today none is;
* the **owner preview material**: the approved canonical portrait, verified by its bytes
  through `visual.brief.approved_portrait()` (never a filename), labelled on every use
  "Internal preview — canonical reference, not publication-approved";
* and the refusal: `image_for(..., for_customers=True)` raises for every Laura image until it
  is publication-approved. A preview is never a publication path.

No image model, no network, no spend.
"""
from __future__ import annotations

import base64

PREVIEW_IMAGE_LABEL = "Internal preview — canonical reference, not publication-approved"
SURFACE_KEY = "brand_face"


class BrandFaceRefused(ValueError):
    """A Laura image asked for a customer-facing use it has not been approved for."""


# Where Laura appears in the shop and brand system. `laura` is one of:
#   anchor        -- she is the visual anchor of this surface
#   preferred     -- she is the default when the gates for that image pass
#   optional      -- design judgment per piece; product may lead
#   product_first -- the product leads; Laura only in a fitting lifestyle scene, never forced
#   no            -- she does not belong in it
PLACEMENTS: tuple[dict, ...] = (
    {"surface": "seller_portrait", "where": "Shop owner / seller profile photo (About area)",
     "laura": "anchor",
     "why": "the human-recognisable face of the shop is Laura's best canonical portrait; "
            "until that exact image passes every customer-facing gate it is preview-only"},
    {"surface": "shop_icon", "where": "Shop icon (shown at 40 and 70 px)", "laura": "no",
     "why": "DECIDED: the icon is the loop-and-bramble logo mark. A face is unreadable at "
            "40 px and would duplicate the seller portrait beside it; the mark stays legible "
            "and gives the shop a second, non-human recognition cue. Laura is the seller "
            "photo, the mark is the icon"},
    {"surface": "banner", "where": "Shop banner (desktop and phone centre crop)",
     "laura": "anchor",
     "why": "banner composed around Laura with the wordmark in the phone-safe centre; "
            "premium editorial photography, not a collage or template"},
    {"surface": "about", "where": "About / shop story", "laura": "anchor",
     "why": "visually anchored by Laura, introduced truthfully as Brambleloop's AI founder; "
            "no human biography and no legal-ownership statement"},
    {"surface": "seasonal", "where": "Seasonal storefront extension", "laura": "anchor",
     "why": "seasonal banner/announcement creative keeps Laura constant and changes the "
            "season around her: recognition and continuity, not repetition"},
    {"surface": "marketing", "where": "Social / marketing / lifestyle creative",
     "laura": "preferred", "why": "the recurring face of Brambleloop's brand creative"},
    {"surface": "wearable_listing", "where": "Wearable listing photography",
     "laura": "preferred",
     "why": "garment fit and scale; only when Product Truth can render the garment accurately "
            "on her -- never an accurate Laura with a false product"},
    {"surface": "non_wearable_listing", "where": "Blankets, decor, amigurumi listings",
     "laura": "product_first",
     "why": "the product is the hero; Laura only in an appropriate lifestyle frame"},
    {"surface": "listing_thumbnail", "where": "Listing thumbnails in the grid",
     "laura": "optional",
     "why": "thumbnails are product-first for comprehension at grid size; Laura carries brand "
            "continuity through banner, About and wearable frames rather than every tile"},
    {"surface": "website", "where": "Future website / brand surfaces", "laura": "anchor",
     "why": "same identity, same rules, same gates"},
)


def _canonical():
    from ..visual import canonical

    return canonical


def portrait_bytes() -> tuple[bytes, str]:
    """The approved canonical portrait's bytes and sha256, verified against the manifest.

    `brief.approved_portrait()` raises when the bytes are not the approved bytes, so a
    replaced, historical or merely similar image can never reach the preview.
    """
    from pathlib import Path

    from ..visual import brief

    path = brief.approved_portrait()
    data = Path(path).read_bytes()
    import hashlib

    sha = hashlib.sha256(data).hexdigest()
    canonical = _canonical()
    if sha != canonical.FACE_SHA256:  # pragma: no cover - approved_portrait already refuses
        raise BrandFaceRefused("the approved portrait is not Laura's approved face")
    return data, sha


def image_for(surface: str, *, for_customers: bool) -> dict:
    """The Laura image a store surface may use, and on what terms.

    For the owner preview: the canonical portrait as a data URI, labelled. For customers:
    refused unless that exact image is publication-approved (none is), because a canonical
    reference defines her and is not customer imagery.
    """
    canonical = _canonical()
    data, sha = portrait_bytes()
    ready = canonical.customer_ready(sha)
    if for_customers and not ready["customer_ready"]:
        raise BrandFaceRefused(
            f"{surface}: Laura's canonical portrait ({sha[:8]}) is a canonical reference, not "
            f"publication-approved. Blocking gates: {ready['blocking']}. {ready['why']}")
    return {"surface": surface, "sha256": sha, "identity_id": canonical.IDENTITY_ID,
            "status": canonical.asset_status(sha), "customer_ready": ready["customer_ready"],
            "label": PREVIEW_IMAGE_LABEL,
            "data_uri": "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")}


def gate_chain(sha: str | None = None) -> list[dict]:
    """Each customer-facing gate for Laura's store imagery, with its honest state today."""
    canonical = _canonical()
    sha = sha or canonical.FACE_SHA256
    approved = sha in canonical.PUBLICATION_APPROVED
    state = {
        "canonical_identity": ("PASS", "the image is the approved canonical portrait, "
                               "verified by sha256"),
        "photorealism": ("FAIL", "the frozen pack's own frames failed skin_looks_real / "
                         "processing_is_restrained in production (B-657); the repair path is "
                         "task #59"),
        "anatomy": ("UNVERIFIED", "not judged for a customer-facing use"),
        "product_truth_if_product_shown": ("NOT_APPLICABLE", "no product shown in the "
                                           "portrait; applies to every wearable frame"),
        "composition_brand_qa": ("UNVERIFIED", "brand QA has not reviewed a final crop"),
        "disclosure_policy": ("GATED", "AI-generated imagery disclosure and Etsy policy "
                              "reading for a seller photo are not settled"),
        "publication_gate": ("GATED", "no owner publication authority for any Laura image"),
    }
    out = []
    for g in canonical.CUSTOMER_FACING_GATES:
        st, why = state[g]
        out.append({"gate": g, "status": "PASS" if approved else st, "why": why})
    return out


def brand_face() -> dict:
    """The brand-face entry of the Store Foundation design system."""
    canonical = _canonical()
    try:
        _, sha = portrait_bytes()
        integrity = canonical.verify()
    except Exception as exc:  # noqa: BLE001 - a refused portrait is a FAIL, not a crash
        return {"identity_id": canonical.IDENTITY_ID, "name": canonical.IDENTITY_NAME,
                "ok": False, "why": f"{type(exc).__name__}: {str(exc)[:200]}",
                "customer_ready": False, "publishable": False}
    return {
        "identity_id": canonical.IDENTITY_ID, "name": canonical.IDENTITY_NAME,
        "role": canonical.ROLE, "public_identity": canonical.PUBLIC_IDENTITY,
        "truthful_identity": canonical.TRUTHFUL_IDENTITY,
        "identity_rule": canonical.IDENTITY_RULE,
        "portrait_sha256": sha, "portrait_status": canonical.asset_status(sha),
        "integrity_ok": integrity["ok"], "integrity_problems": integrity["problems"],
        "placements": [dict(p) for p in PLACEMENTS],
        "shop_icon_decision": next(p for p in PLACEMENTS if p["surface"] == "shop_icon"),
        "gates": gate_chain(sha),
        "customer_ready": False, "publishable": False,
        "missing_canonical": canonical.summary()["missing_canonical"],
        "preview_label": PREVIEW_IMAGE_LABEL,
        "system": ["Laura", "loop-and-bramble mark", "Helvetica Neue wordmark",
                   "brand.bible.PALETTE", "product-first merchandising", "calm, specific voice"],
    }


def check(value: dict | None = None) -> list[dict]:
    """Readiness findings for the brand face. Never READY while no image is approved."""
    value = value if value is not None else brand_face()
    out: list[dict] = []
    if not value.get("ok", True) or not value.get("integrity_ok", False):
        out.append({"code": "BRAND_FACE_INTEGRITY", "severity": "fail",
                    "detail": f"Laura's canonical assets do not verify: "
                              f"{value.get('why') or value.get('integrity_problems')}"})
    for g in value.get("gates") or []:
        if g["status"] in ("FAIL", "UNVERIFIED", "GATED"):
            out.append({"code": f"BRAND_FACE_{g['gate'].upper()}", "severity": "gated",
                        "detail": f"{g['gate']}: {g['status']} -- {g['why']}"})
    if not value.get("customer_ready"):
        out.append({"code": "BRAND_FACE_NOT_CUSTOMER_READY", "severity": "gated",
                    "detail": "Laura's imagery is canonical reference only; preview, never "
                              "publish (identity -> photorealism -> anatomy -> Product Truth "
                              "-> brand QA -> disclosure -> publication)"})
    if value.get("missing_canonical"):
        out.append({"code": "BRAND_FACE_MISSING_CANONICAL", "severity": "owner",
                    "detail": f"frozen v15 frames held only in production: "
                              f"{value['missing_canonical']}; owner action OA-CANON-1"})
    return out


# ---- the Laura banner composition (owner preview only) -----------------------------------
#
# Etsy shows a wide banner on desktop and a centre crop on a phone (`brand.storefront_preview`:
# 2:1 centre window, ASSUMED). So both the wordmark and Laura sit inside the centre window
# x 400-1200 of the 1600x400 canvas (`brand.storefront.BANNER_SIZE`, repo-asserted, Etsy's
# upload size UNVERIFIED): wordmark left of centre, Laura right of centre, crochet fabric and
# bramble sprigs only in the desktop-only wings. One photograph, typography and the palette --
# not a collage.
LAURA_WORDMARK_BOX = (450, 140, 790, 262)
LAURA_PHOTO_BOX = (812, 0, 1150, 400)
SEASONS = ("evergreen", "winter")


def banner_crops() -> dict:
    """Where the wordmark and Laura land on desktop and in the phone centre crop."""
    from ..brand import bible, storefront
    from ..brand import storefront_preview as sp

    w, h = storefront.BANNER_SIZE
    out = sp.banner_crops(box=LAURA_WORDMARK_BOX, size=(w, h))
    margin = bible.CROP_RULES["safe_margin_pct"]
    x0, _, x1, _ = LAURA_PHOTO_BOX
    for name, c in out.items():
        cx0, _, cx1, _ = c["crop"]
        cw = cx1 - cx0
        inside = x0 >= cx0 + cw * margin and x1 <= cx1 - cw * margin
        c["laura_inside_safe_area"] = inside
        if not inside:
            c["problems"].append(f"banner ({name}): Laura leaves the safe area")
            c["ok"] = False
    out["basis"] = ("phone crop ASSUMED 2:1 centre (brand.storefront_preview); banner canvas "
                    "1600x400 repo-asserted; Etsy's own banner/crop numbers UNVERIFIED")
    return out


def banner_overlay_svg(season: str = "evergreen") -> str:
    """The banner's type and fabric layer; Laura's photograph is placed under the clear box."""
    from ..brand import bible, storefront
    from . import assets

    P = bible.PALETTE
    w, h = storefront.BANNER_SIZE
    season = season if season in SEASONS else "evergreen"
    x0, y0, x1, y1 = LAURA_WORDMARK_BOX
    mid = (x0 + x1) / 2
    bands = ([P["line"], P["gold"], P["line"]] if season == "evergreen"
             else [P["wine"], P["gold"], P["pine"]])
    sub = "STUDIO · CROCHET PATTERNS" if season == "evergreen" else "WINTER PATTERNS · STUDIO"
    left_wing = assets._stitch_rows(14, 4, bands)
    bottom = assets._stitch_rows(h - 70, 5, list(reversed(bands)) + [P["line"]])
    word = (f'<text x="{mid}" y="{y0 + 70}" text-anchor="middle" '
            f'font-family="Helvetica Neue, Helvetica, Arial, sans-serif" font-weight="700" '
            f'font-size="58" fill="{P["pine"]}" textLength="{x1 - x0 - 20}" '
            f'lengthAdjust="spacingAndGlyphs">{assets.WORDMARK}</text>')
    rule = (f'<path d="M {x0 + 10} {y1 - 30} H {x1 - 10}" stroke="{P["gold"]}" '
            f'stroke-width="2"/>')
    subt = (f'<text x="{mid}" y="{y1 - 6}" text-anchor="middle" '
            f'font-family="Helvetica Neue, Helvetica, Arial, sans-serif" font-size="16" '
            f'fill="{P["ink"]}" textLength="{x1 - x0 - 60}" lengthAdjust="spacing">{sub}</text>')
    sprigs = assets._sprig(180, 210, 1.3, -14) + assets._sprig(1420, 210, 1.3, 194)
    # Laura's photograph is laid over LAURA_PHOTO_BOX by the page, above this layer.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="Brambleloop banner layer">'
            f'<rect width="{w}" height="{h}" fill="{P["cream"]}"/>{left_wing}{bottom}'
            f'{sprigs}{word}{rule}{subt}</svg>')
