"""The owner's canonical storefront banner through every applicable publication gate (D-FB-17).

`brand.canonical_assets` holds the file (brambleloop_owner_banner_canonical.png, sha256
048a1991..., 1983 x 793). D-FB-17: use the exact file if it passes every applicable
publication gate; if a gate stops it, keep it as the canonical target, say precisely which
gate and why, and bring only MINIMAL correction candidates (same composition) back to the
owner. Never substitute, never weaken a gate, never fabricate evidence about the image.

What this module can and cannot know
* MEASURED from pixels: size, aspect, format, transparency, embedded metadata, the vertical
  and horizontal extent of the centred identity block (ink rows in the central band), and
  what a 4:1 crop or the assumed phone window keeps of it.
* MEASURED from the repo: Etsy's published numbers (`integrations.etsy_constraints`, quoted
  from Etsy's Help Center -- what Etsy *publishes*, never observed enforced on this shop), the
  catalogue and its sections (`store_foundation.content`), the Laura canon and its
  publication status (`visual.canonical`), the store disclosure (`copy_v2`).
* DECLARED, not measured: what the picture shows. No OCR, face detector or face-embedding
  model is installed, so the visible words are a transcription (recorded below with its
  source) and whether the woman is Laura, what crochet is shown and whether any of it reads
  as a Brambleloop product are for human review. Those gates are UNKNOWN, and UNKNOWN never
  counts as PASS.

Statuses: PASS (evidence attached), FAIL (evidence attached), UNKNOWN (what is missing and who
must look). Nothing here publishes, uploads or calls a model.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from ..brand import canonical_assets as CA

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
# A check that rests on an internal assumption Etsy does not state (D-FB-18 item 4: the 4:1
# rule "must not drive a redesign until verified"). Advisory: never PASS, never a blocker,
# always shown with what would verify it.
UNVERIFIED_ASSUMPTION = "UNVERIFIED_ASSUMPTION"
STATUSES = (PASS, FAIL, UNKNOWN, UNVERIFIED_ASSUMPTION)
BLOCKING = (FAIL, UNKNOWN)
OWNER_REVIEW_REQUIRED = "OWNER_REVIEW_REQUIRED"
REJECTED_BY_OWNER = "REJECTED_BY_OWNER"
ASSESSMENT_VERSION = "owner-banner-assessment/2"

# Etsy's own words, read-only GETs on 2026-10-06 by lane B2. Help Center articles were read as
# JSON through the Help Center article API (the HTML pages answer automated readers with 403);
# etsy.com/legal and the seller handbook answered 403 (bot protection) and stay UNVERIFIED.
ETSY_EVIDENCE: tuple[dict, ...] = (
    {"key": "big_banner_size", "source_label": "Etsy Help Center article 115015663347 (images in your shop)", "status": "VERIFIED_HELP_CENTER",
     "url": "https://help.etsy.com/hc/en-us/articles/115015663347-Requirements-and-Best-"
            "Practices-for-Images-in-Your-Etsy-Shop",
     "api_url": "https://help.etsy.com/api/v2/help_center/en-us/articles/115015663347.json",
     "retrieved_at": "2026-10-06T18:29:18Z", "edited_at": "2026-05-04T19:20:43Z",
     "quotes": ["The minimum required size for big shop banners is 1200 x 300px.",
                "The recommended size is 1600 x 400px.",
                "Image sizes are optimized for mobile displays."]},
    {"key": "banner_display", "source_label": "Etsy Help Center article 115015663247 (shop appearance)", "status": "VERIFIED_HELP_CENTER",
     "url": "https://help.etsy.com/hc/en-us/articles/115015663247-How-to-Customize-Your-"
            "Shop-s-Appearance",
     "api_url": "https://help.etsy.com/api/v2/help_center/en-us/articles/115015663247.json",
     "retrieved_at": "2026-10-06T18:29:18Z", "edited_at": "2026-05-05T14:06:33Z",
     "quotes": ["Big Banner: A large image with a minimum size of 1200 x 300 pixels.",
                "This image appears when shoppers view your shop on the standard view of the "
                "website as well as on mobile devices."]},
    {"key": "banner_aspect_or_crop", "source_label": "Etsy Help Center articles 115015663347 and 115015663247", "status": "NOT_STATED",
     "url": "(both articles above)", "retrieved_at": "2026-10-06T18:29:18Z",
     "quotes": [], "note": "neither article states a required aspect ratio, a crop rule or a "
                           "safe zone for the big banner; 1600x400 is a recommendation"},
    {"key": "ai_disclosure", "source_label": "Etsy Help Center article 360024112614 (what can I sell)", "status": "VERIFIED_HELP_CENTER",
     "url": "https://help.etsy.com/hc/en-us/articles/360024112614-What-Can-I-Sell-on-Etsy",
     "api_url": "https://help.etsy.com/api/v2/help_center/en-us/articles/360024112614.json",
     "retrieved_at": "2026-10-06T18:29:57Z", "edited_at": "2025-09-17T18:36:53Z",
     "quotes": ["As a seller, you can offer your original design as a digital download, or use "
                "a third party to produce or print your design onto a physical item. This "
                "category also includes seller-prompted AI creations.",
                "Seller-prompted AI creations must disclose the use of AI."],
     "note": "the rule is about items offered for sale; no fetched text addresses shop "
             "banners or branding imagery"},
    {"key": "seller_policy_and_creativity_standards", "source_label": "Etsy Seller Policy, Creativity Standards and seller handbook article 1275449912004", "status": "BLOCKED_403",
     "url": "https://www.etsy.com/legal/sellers/ ; https://www.etsy.com/legal/creativity ; "
            "https://www.etsy.com/seller-handbook/article/1275449912004",
     "retrieved_at": "2026-10-06T18:29:36Z", "quotes": [],
     "note": "HTTP 403 (bot protection) on all three; their content stays UNVERIFIED here "
             "(gates.policy_knowledge holds search-engine excerpts: AI disclosure 'in your "
             "relevant listings')"},
)

# Visual work recorded, never started here (paid generation needs owner spend approval).
VISUAL_TASKS: tuple[dict, ...] = (
    {"id": "VT-B2-1", "status": "GATED",
     "task": "reproduce the banner scene with verified Brambleloop products in place of the "
             "concept crochet, preserving Laura, the warm room, the central identity, the "
             "tagline and the feel; owner review before any public replacement",
     "trigger": "Product Truth review concludes concept crochet is unsuitable on the public "
                "banner, or matching products exist", "decision": "D-FB-18 item 2",
     "gated_on": ["owner spend approval for generation", "owner review"]},
    {"id": "VT-B2-2", "status": "NOT_REQUIRED_BY_EVIDENCE",
     "task": "recompose the same scene at Etsy's verified banner dimensions, preserving Laura, "
             "the warm room, the lifestyle aesthetic, the central identity, the crochet/yarn "
             "environment, the tagline, balance and feel; owner review before public "
             "replacement",
     "trigger": "only if Etsy evidence (or the owner's in-app check after an owner-approved "
                "upload) shows a different ratio is required or the composition is cropped",
     "decision": "D-FB-18 item 4",
     "gated_on": ["verified requirement", "owner spend approval", "owner review"]},
)

# D-FB-18 item 2: the banner's crochet is brand/lifestyle concept imagery. It is never mapped
# to a pattern and never implies those exact pieces are available.
CROCHET_CLASSIFICATION = {"class": "brand_lifestyle_concept", "mapped_to_patterns": (),
                          "decision": "D-FB-18 item 2",
                          "rule": "never mapped to existing patterns; never implies those "
                                  "pieces are available"}
ROLE = CA.STOREFRONT_BANNER

# Ink detection for the centred identity block. The search band is the central fifth of the
# width, where the owner's record places the identity ("centred identity", D-FB-17 item 2);
# rows with >= ROW_INK_MIN of the band darker than INK_LUM are ink. A run whose band is more
# than SCENERY_INK dark is furniture (the table), not lettering.
SEARCH_BAND = (0.40, 0.60)
INK_LUM = 170.0
ROW_INK_MIN = 0.004
SCENERY_INK = 0.5
CLUSTER_GAP_PX = 40

# The visible words. NOT read from pixels (no OCR is installed): transcribed in the lane B2
# brief (integrator, 2026-10-06) and, for the logo footer, DECISION_LOG D-FB-17 item 1.
VISIBLE_TEXT_SOURCE = ("transcription in the lane B2 brief (2026-10-06) and DECISION_LOG "
                       "D-FB-17; not OCR -- completeness unverified")
VISIBLE_TEXT: dict[str, str] = {
    "wordmark": "BRAMBLELOOP",
    "descriptor": "CROCHET PATTERNS",
    "tagline": "Patterns for a More Handmade Life",
    "nav": "HOME | BABY | WEARABLES | GIFTS | SEASONAL",
    "sign_left": "Good Things Take Time",
    "sign_right": "SAME YARN MORE HAPPY",
    "mug": "Crochet a Brighter Everyday",
    "book_spine_1": "CROCHET",
    "book_spine_2": "A CALMER HOME",
    "book_spine_3": "A BRIGHTER YOU",
}
BANNER_NAV = ("Home", "Baby", "Wearables", "Gifts", "Seasonal")
LOGO_FOOTER_NAV = ("Home", "Baby", "Gifts", "Seasonal")   # HOME · BABY · GIFTS · SEASONAL
NAV_TO_SLUG = {"home": "home", "baby": "baby", "wearables": "wear", "gifts": "collections",
               "seasonal": "seasonal"}

# What the owner's record declares the picture shows (D-FB-17 item 2). Declared, not measured.
DECLARED_CONTENT = ("Laura left, warm cozy setting, centred identity, crochet/yarn right, "
                    "tagline (DECISION_LOG D-FB-17 item 2)")

CANDIDATE_DIR_REL = "research/final_build/w3/owner_banner_candidates"
REVIEW_WIDTH = 1200                      # review copies: Etsy's minimum banner width
REVIEW_MAX_BYTES = 300_000               # wave-3 limit for committed images


def _gate(gate: str, status: str, evidence: dict, *, basis: str, why: str,
          rule: str = "", review: str = "") -> dict:
    assert status in STATUSES
    out = {"gate": gate, "status": status, "why": why, "basis": basis, "evidence": evidence,
           "rule": rule}
    if review:
        out["review"] = review
    return out


# ---- pixels ------------------------------------------------------------------------------

def _array():
    import numpy as np

    return np.asarray(CA.image(ROLE), dtype=float)


def _runs(mask) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def _cluster(cols, centre: int) -> tuple[int, int] | None:
    """The contiguous inked column span around `centre`, tolerating gaps < CLUSTER_GAP_PX."""
    w = len(cols)
    lo = hi = None
    for step in (-1, 1):
        x, gap, edge = centre, 0, None
        while 0 <= x < w:
            if cols[x]:
                edge, gap = x, 0
            else:
                gap += 1
                if gap > CLUSTER_GAP_PX:
                    break
            x += step
        if step < 0:
            lo = edge
        else:
            hi = edge
    if lo is None or hi is None:
        return None
    return lo, hi


def measure_identity_block(a=None) -> dict:
    """Rows and columns of the centred identity block (monogram, wordmark, descriptor,
    tagline, heart, nav), measured from ink in the central band."""
    import numpy as np

    a = _array() if a is None else a
    h, w = a.shape[:2]
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    x0, x1 = int(SEARCH_BAND[0] * w), int(SEARCH_BAND[1] * w)
    band = lum[:, x0:x1] < INK_LUM
    runs = []
    for r0, r1 in _runs(band.mean(axis=1) > ROW_INK_MIN):
        frac = float(band[r0:r1 + 1].mean())
        cols = (lum[r0:r1 + 1] < INK_LUM).mean(axis=0) > 0.01
        span = _cluster(cols, w // 2)
        runs.append({"rows": [r0, r1], "band_ink": round(frac, 3),
                     "scenery": frac > SCENERY_INK, "cols": list(span) if span else None})
    lock = []
    for r in runs:
        if r["scenery"]:
            break
        lock.append(r)
    if not lock:
        return {"found": False, "runs": runs}
    # The widest element (the wordmark) sets the block's width; a neighbour such as a picture
    # frame can join the cluster of a short run, so take the median-width-robust maximum of
    # runs whose span stays inside the central 80%.
    spans = [r["cols"] for r in lock if r["cols"] and r["cols"][0] > 0.1 * w
             and r["cols"][1] < 0.9 * w]
    widest = max(spans, key=lambda s: s[1] - s[0]) if spans else None
    y0, y1 = lock[0]["rows"][0], lock[-1]["rows"][1]
    return {"found": True, "rows": [y0, y1], "height_px": y1 - y0 + 1,
            "cols": widest, "width_px": (widest[1] - widest[0] + 1) if widest else None,
            "elements": len(lock), "runs": runs, "search_band": list(SEARCH_BAND),
            "procedure": (f"rows whose central band ({SEARCH_BAND[0]:.0%}-{SEARCH_BAND[1]:.0%} "
                          f"of the width) is >= {ROW_INK_MIN:.1%} darker than luminance "
                          f"{INK_LUM:.0f}; consecutive runs from the top until the first "
                          f"run > {SCENERY_INK:.0%} dark (furniture); width from the widest "
                          f"run's central column cluster")}


def _cbor_text_after(body: bytes, key: bytes) -> list[str]:
    """CBOR text values that follow the text key `key` (major type 3, short length)."""
    import re

    out = []
    k = bytes([0x60 + len(key)]) + key
    for m in re.finditer(re.escape(k), body):
        i = m.end()
        if i < len(body) and 0x60 <= body[i] <= 0x77:
            n = body[i] - 0x60
            out.append(body[i + 1:i + 1 + n].decode("utf-8", "replace"))
        elif i + 1 < len(body) and body[i] == 0x78:
            n = body[i + 1]
            out.append(body[i + 2:i + 2 + n].decode("utf-8", "replace"))
    return out


def c2pa_claims(data: bytes) -> dict:
    """What an embedded C2PA (Content Credentials) manifest *declares*, parsed from the PNG's
    caBX chunk. The manifest's signature is NOT cryptographically verified here (no C2PA
    library is installed): this is the file's own statement, labelled as such."""
    import re

    bodies, i = [], 8
    while i + 8 <= len(data):
        n = int.from_bytes(data[i:i + 4], "big")
        if data[i + 4:i + 8] == b"caBX":
            bodies.append(data[i + 8:i + 8 + n])
        i += 12 + n
    if not bodies:
        return {"present": False}
    body = b"".join(bodies)
    dst = sorted({m.decode() for m in re.findall(
        rb"digitalsourcetype/([A-Za-z]+)", body)})
    actions = sorted({m.decode() for m in re.findall(rb"c2pa\.(created|converted|edited|"
                                                     rb"opened|placed|cropped|resized|"
                                                     rb"color_adjustments|drawing)", body)})
    names = [x for x in _cbor_text_after(body, b"name") if x and x.isprintable()
             and "manifest" not in x]
    versions = [x for x in _cbor_text_after(body, b"version") if x and x.isprintable()]
    orgs = sorted({m.decode().strip() for m in re.findall(rb"(OpenAI[ A-Za-z,.]{0,30}?)"
                                                          rb"(?:[0-9]|$)", body)})
    when = sorted({m.decode() for m in re.findall(rb"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d",
                                                  body)})
    return {"present": True, "bytes": len(body), "digital_source_types": dst,
            "actions": actions, "generator_names": sorted(set(names))[:6],
            "generator_versions": sorted(set(versions))[:6], "signer_strings": orgs[:6],
            "timestamps": when[:4],
            "ai_generated_declared": "trainedAlgorithmicMedia" in dst,
            "signature_verified": False,
            "basis": ("parsed from the file's embedded C2PA manifest (caBX chunk); its "
                      "signature is not verified here -- the file's own declaration")}


def metadata(role: str = ROLE) -> dict:
    """Embedded provenance in the PNG (text chunks, XMP, C2PA/JUMBF), measured."""
    data = CA.verified_bytes(role)
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        info = {k: (str(v)[:80]) for k, v in im.info.items()}
        mode, fmt = im.mode, im.format
    chunks, i = [], 8
    while i + 8 <= len(data):
        n = int.from_bytes(data[i:i + 4], "big")
        chunks.append(data[i + 4:i + 8].decode("latin-1"))
        i += 12 + n
    prov = [c for c in chunks if c in ("tEXt", "iTXt", "zTXt", "eXIf", "caBX", "jumb")]
    return {"format": fmt, "mode": mode, "info_keys": sorted(info), "chunks": sorted(set(chunks)),
            "provenance_chunks": prov, "bytes": len(data), "c2pa": c2pa_claims(data)}


# ---- gates -------------------------------------------------------------------------------

def _etsy(w: int, h: int, nbytes: int, fmt: str, transparent: bool) -> tuple[list[dict], dict]:
    from ..integrations import etsy_constraints as E

    probs = E.image_problems("big_banner", width=w, height=h, nbytes=nbytes, fmt=fmt,
                             transparent=transparent)
    c = E.CONSTRAINTS
    basis = {k: {"value": list(c[k].value), "basis": c[k].basis, "quote": c[k].quote}
             for k in ("big_banner_min_px", "big_banner_recommended_px")}
    basis["banner_mobile_crop"] = {"value": None, "basis": c["banner_mobile_crop"].basis,
                                   "note": c["banner_mobile_crop"].note}
    basis["retrieved_on"] = E.RETRIEVED_ON
    basis["meaning"] = ("VERIFIED_HELP_CENTER = a sentence in Etsy's Help Center states it "
                        "(what Etsy publishes); no upload has been made, so Etsy's handling "
                        "of this file is not observed")
    return probs, basis


def _catalogue(db=None) -> dict:
    from . import content as C

    s = C.build(db)
    secs = {x["slug"]: x for x in s["sections"].value}
    products = [{"title": p["title"].split(" | ")[0], "build": p["representative"]["build"],
                 "section": p.get("section")} for p in s["opening_grid"].value]
    return {"sections": {k: {"name": v["name"], "listings": v["listings"], "shown": v["shown"]}
                         for k, v in secs.items()}, "products": products}


def _nav_truth(nav: tuple[str, ...], cat: dict) -> dict:
    rows, empty = [], []
    for word in nav:
        slug = NAV_TO_SLUG[word.lower()]
        sec = cat["sections"].get(slug) or {"listings": 0, "shown": False}
        rows.append({"nav": word, "section_slug": slug, "listings": sec["listings"]})
        if not sec["listings"]:
            empty.append(word)
    return {"rows": rows, "empty": empty}


def assess(db=None) -> dict:
    """Every applicable gate on the exact canonical banner. Never raises on a gate's error: a
    gate that cannot run is UNKNOWN with the reason."""
    v = CA.verify()
    canon = CA.ASSETS[ROLE]
    gates: list[dict] = []
    gates.append(_gate(
        "canonical_integrity", PASS if v["ok"] else FAIL,
        {"sha256": canon.sha256, "verify": v["problems"] or "re-hashed, size and SHA256SUMS "
         "agree"}, basis="measured: sha256 of the repository copy",
        why="the file is byte-identical to what the owner supplied" if v["ok"] else
        "the canonical file is missing or altered: nothing below is about the owner's file",
        rule="D-FB-17: the owner files are immutable"))
    if not v["ok"]:
        return _rollup(gates, db_used=db is not None)

    a = _array()
    h, w = a.shape[:2]
    meta = metadata()
    transparent = meta["mode"] in ("RGBA", "LA", "P") and "transparency" in meta["info_keys"]
    probs, ebasis = _etsy(w, h, meta["bytes"], "png", transparent)
    codes = {p.get("code") for p in probs}
    hard = [p for p in probs if p.get("code") in ("IMAGE_BELOW_MINIMUM",
                                                   "IMAGE_FORMAT_UNSUPPORTED",
                                                   "IMAGE_TRANSPARENT", "IMAGE_ANIMATED")]
    gates.append(_gate(
        "etsy_banner_minimum_and_format", FAIL if hard else PASS,
        {"size": [w, h], "format": "png", "transparent": transparent, "findings": hard,
         "etsy": ebasis, "etsy_live": [e for e in ETSY_EVIDENCE
                                       if e["key"] in ("big_banner_size", "banner_display")]},
        basis="measured file vs Etsy Help Center text re-read 2026-10-06 (published, not "
        "enforcement-observed; no upload made)",
        why=(f"{w}x{h} PNG, opaque: at or above Etsy's published minimum 1200x300 and "
             f"recommended 1600x400; PNG is a supported type" if not hard else
             "; ".join(p.get("detail", "") for p in hard)),
        rule="integrations.etsy_constraints.image_problems('big_banner')"))
    target = ebasis["big_banner_recommended_px"]["value"]
    t_aspect = target[0] / target[1]
    aspect = w / h
    gates.append(_gate(
        "f233_banner_canvas_4to1",
        PASS if abs(aspect - t_aspect) <= 0.02 else UNVERIFIED_ASSUMPTION,
        {"aspect": round(aspect, 3), "canvas": target, "canvas_aspect": round(t_aspect, 3),
         "etsy_finding": [p for p in probs if p.get("code") == "BANNER_ASPECT_DIFFERS"],
         "canvas_basis": ("1600x400 is asserted in this repo (brand.storefront.BANNER_SIZE) "
                          "and quoted from Etsy's Help Center by lane I as the *recommended* "
                          "size; how Etsy fits a 2.50:1 upload into it is NOT published "
                          "(UNVERIFIED) -- it may crop or scale")},
        basis="measured aspect vs an UNVERIFIED assumption",
        rule="storefront_gate F-233 assumed a 4:1 canvas; Etsy states only a minimum "
             "(1200x300) and a recommended size (1600x400) -- no required ratio or crop rule",
        why=(f"the file is {aspect:.2f}:1 against a 4:1 *recommendation*. Etsy publishes no "
             f"required aspect ratio and no crop behaviour (re-read 2026-10-06), so this is "
             f"not a failure; it drives no redesign (D-FB-18 item 4)"),
        review="owner: after an owner-approved upload, look at the banner in the Etsy app "
               "and on desktop; reopen VT-B2-2 only if it is cropped badly"))

    block = measure_identity_block(a)
    crop_h = int(round(w / t_aspect))
    top = (h - crop_h) // 2
    if block["found"]:
        y0, y1 = block["rows"]
        lost_top = max(0, top - y0)
        lost_bottom = max(0, y1 - (top + crop_h - 1))
        fits = block["height_px"] <= crop_h
        gates.append(_gate(
            "f233_identity_block_survives_4to1", PASS if (lost_top == 0 and lost_bottom == 0)
            else UNVERIFIED_ASSUMPTION,
            {"identity_block_rows": block["rows"], "identity_block_height_px":
             block["height_px"], "full_width_4to1_height_px": crop_h,
             "centre_crop_rows": [top, top + crop_h - 1], "rows_lost_top": lost_top,
             "rows_lost_bottom": lost_bottom, "any_full_width_4to1_crop_fits": fits,
             "elements": block["elements"], "procedure": block["procedure"]},
            basis="measured (ink rows) under the ASSUMED 4:1 centre crop (Etsy states no crop)",
            rule="storefront_gate F-233: the mark stays whole inside the canvas",
            why=(f"the centred identity block is {block['height_px']} px tall (rows "
                 f"{y0}-{y1}); a full-width 4:1 crop is {crop_h} px tall, so no 4:1 crop "
                 f"of the exact file keeps all of it; a centre crop (rows {top}-"
                 f"{top + crop_h - 1}) cuts {lost_top} px from the top of the monogram"
                 + (f" and {lost_bottom} px from the bottom" if lost_bottom else "")
                 + " -- IF Etsy crops to 4:1, which it does not state"),
            review="owner: in-app check after an owner-approved upload"))
        cols = block["cols"]
        phone_w = crop_h * 2
        p0 = (w - phone_w) // 2
        inside = bool(cols) and p0 <= cols[0] and cols[1] <= p0 + phone_w - 1
        gates.append(_gate(
            "f233_identity_block_in_phone_window", UNVERIFIED_ASSUMPTION,
            {"identity_block_cols": cols, "assumed_phone_window_cols": [p0, p0 + phone_w - 1],
             "horizontally_inside_assumed_window": inside,
             "phone_crop_basis": ebasis["banner_mobile_crop"]["basis"]},
            basis="measured block vs an ASSUMED 2:1 centre window",
            rule="storefront_gate F-233: the mark inside the phone window",
            why=(f"inside the assumed 2:1 centre window horizontally ({inside}); Etsy says "
                 f"only that the banner shows on mobile and sizes are 'optimized for mobile "
                 f"displays' -- no crop geometry, so this cannot pass; check in the Etsy app "
                 f"after an owner-approved upload"),
            review="owner: check the real phone crop after upload (checklist B2)"))
    else:
        gates.append(_gate("f233_identity_block_survives_4to1", UNKNOWN,
                           {"runs": block["runs"]}, basis="measured",
                           why="the identity block could not be located by the ink procedure",
                           review="human: locate the lockup"))

    gates += _laura_gates()
    gates += _disclosure_gates(meta)
    gates += _truth_gates(db)
    _finalise_publication(gates)
    return _rollup(gates, db_used=db is not None, block=block)


def _finalise_publication(gates: list[dict]) -> None:
    """W3-WIRE4 (B2 wiring 5): `laura_publication_status` reads the owner's approval scoped
    to THIS asset on the storefront_banner surface (`visual.canonical.surface_publication`),
    conditional on every other applicable gate measured here. Advisory
    UNVERIFIED_ASSUMPTION gates are not conditions. Nothing global is flipped."""
    from ..visual import canonical

    idx = next((i for i, g in enumerate(gates) if g["gate"] == "laura_publication_status"),
               None)
    if idx is None:
        return
    sha = CA.ASSETS[ROLE].sha256
    conditions = {g["gate"]: g["status"] for g in gates
                  if g["gate"] != "laura_publication_status"
                  and g["status"] != UNVERIFIED_ASSUMPTION}
    pub = canonical.surface_publication(sha, canonical.SURFACE_STOREFRONT_BANNER, conditions)
    g = gates[idx]
    g["status"] = pub["status"]
    g["evidence"].update({
        "surface": pub["surface"],
        "surface_status": canonical.asset_status(sha,
                                                 surface=canonical.SURFACE_STOREFRONT_BANNER),
        "owner_surface_approval": pub["approval"], "outstanding_failed": pub["failing"],
        "outstanding_unknown": pub["unknown"]})
    g["basis"] = ("measured: visual.canonical.surface_publication -- the owner's approval "
                  "scoped to this sha on storefront_banner, AND every applicable gate here")
    g["rule"] = ("no Laura image reaches customers until publication_approved; a scoped "
                 "owner approval covers only its asset and surface and waives no gate")
    g["why"] = pub["why"] + (". Globally the bytes stay "
                             f"'{pub['global_asset_status']}' (not customer_ready); the "
                             "owner's identity review approves identity, not the empty-"
                             "category navigation or the concept crochet")
    g["review"] = ("resolve the outstanding gates; the owner's scoped approval already "
                   "covers identity") if pub["approval"] else g.get("review")


def _laura_gates() -> list[dict]:
    out = []
    sha = CA.ASSETS[ROLE].sha256
    try:
        from ..visual import canonical, identity_gate

        g = identity_gate.assess({})
        review = CA.owner_identity_review(sha)
        machine = {"identity_gate": {k: g.get(k) for k in ("status", "band", "why",
                                                            "gate_version")},
                   "biometric": identity_gate.biometric_floor(None),
                   "qualified_embedders": sorted(identity_gate.QUALIFIED_EMBEDDERS),
                   "conditioning_receipt": None}
        if review and review.get("identity") == canonical.IDENTITY_ID:
            out.append(_gate(
                "laura_identity", PASS,
                {"identity_id": canonical.IDENTITY_ID, "owner_human_review": review,
                 "sha256": sha, "machine_reading": machine},
                basis=f"owner human identity review ({review['decision']}), bound to these "
                      f"exact bytes; no machine reading claimed",
                rule="F-732 / F-219: identity by a human review where the machine floor is "
                     "unmeasured; the review covers this depiction only",
                why=(f"the owner confirmed the woman in this banner is Laura "
                     f"({canonical.IDENTITY_ID}) -- {review['decision']} item {review['item']}, "
                     f"{review['scope']}. Every other frame keeps the identity gate and its "
                     f"review queue")))
        else:
            out.append(_gate(
                "laura_identity", UNKNOWN,
                {"identity_id": canonical.IDENTITY_ID, **machine,
                 "c2pa": {k: (metadata().get("c2pa") or {}).get(k) for k in
                          ("ai_generated_declared", "generator_names", "timestamps")},
                 "is_canonical_reference_bytes": sha in {
                     e.get("sha256") for e in canonical.all_entries()}},
                basis="identity gate run on the file: no judge readings, no conditioning "
                      "receipt, no qualified face-embedding model",
                rule="F-732: a woman similar to Laura is not Laura",
                why=(f"a person is declared in the banner ({DECLARED_CONTENT}); whether she "
                     f"is Laura ({canonical.IDENTITY_ID}) cannot be measured here and no "
                     f"owner review covers these bytes. Human identity-review queue; never "
                     f"PASS"),
                review="human identity review (visual.identity_gate queue)"))
        ready = canonical.customer_ready(sha)
        out.append(_gate(
            "laura_publication_status", FAIL,
            {"asset_status": canonical.asset_status(sha), "customer_ready": ready,
             "publication_approved": sorted(canonical.PUBLICATION_APPROVED),
             "customer_facing_gates": list(canonical.CUSTOMER_FACING_GATES)},
            basis="measured: visual.canonical.asset_status / customer_ready on the file's "
                  "sha256",
            rule="no Laura image reaches customers until publication_approved",
            why=(f"the file's bytes are '{canonical.asset_status(sha)}'. D-FB-18 confirmed "
                 f"her identity, not publication. The publication model "
                 f"(visual.canonical.PUBLICATION_APPROVED) is a per-asset sha set with no "
                 f"surface scope and implies every CUSTOMER_FACING_GATE passed; it cannot "
                 f"express 'owner-approved for the storefront banner only', and photorealism/"
                 f"anatomy are unjudged. Not flipped (visual.canonical is read-only here)"),
            review="owner publication decision + a per-surface approval in visual.canonical "
                   "(WIRING REQUEST)"))
        out.append(_gate(
            "laura_photorealism_anatomy", UNKNOWN,
            {"vision_reading": None},
            basis="no vision-judge reading exists for this file",
            rule="visual.canonical CUSTOMER_FACING_GATES: photorealism, anatomy",
            why="not judged: no reading is invented", review="vision judge + human"))
    except Exception as exc:  # noqa: BLE001 - a gate that cannot run is UNKNOWN
        out.append(_gate("laura_identity", UNKNOWN, {"error": f"{type(exc).__name__}: "
                                                              f"{str(exc)[:160]}"},
                         basis="gate unavailable", why="the Laura gates could not run",
                         review="engineering"))
    return out


def _disclosure_gates(meta: dict) -> list[dict]:
    from ..gates import platform_policy as PP
    from . import copy_v2, lint

    disc = copy_v2.store_disclosure()
    has_laura = "She is an AI, not a human" in disc
    has_generated = PP.DISCLOSURES["generated_imagery"] in disc
    c2 = meta.get("c2pa") or {}
    declared_ai = bool(c2.get("ai_generated_declared"))
    ev = {e["key"]: e for e in ETSY_EVIDENCE}
    out = [_gate(
        "ai_generated_imagery_disclosure", UNKNOWN,
        {"c2pa": c2, "png_chunks": meta["chunks"], "provenance_kept": "caBX" in meta["chunks"],
         "etsy_rule": ev["ai_disclosure"], "etsy_blocked": ev["seller_policy_and_creativity_"
                                                               "standards"],
         "store_disclosure_has_laura_ai_line": has_laura,
         "store_disclosure_has_generated_imagery_line": has_generated,
         "marketing_sentence_required": False},
        basis="Etsy Help Center text re-read 2026-10-06 + the file's C2PA manifest",
        rule=("Etsy (Help Center 360024112614): 'Seller-prompted AI creations must disclose "
              "the use of AI.' -- a rule about items for sale; D-FB-18 item 9: no AI marketing "
              "language merely because of Content Credentials; never strip provenance"),
        why=(("the file's own manifest declares it AI-generated (signature not verified). "
              if declared_ai else "provenance not declared in the file. ")
             + "Etsy's verified text requires AI disclosure for items offered for sale; no "
               "fetched Etsy text addresses shop banners or branding imagery, and the Seller "
               "Policy / Creativity Standards pages returned 403. So what (if anything) a "
               "banner requires is UNVERIFIED: nothing is added to customer copy on this "
               "basis, and the C2PA metadata stays in the file"),
        review="owner or a human page reading of Etsy's Seller Policy / Creativity Standards "
               "for shop banners")]
    hits = {k: [f["code"] for f in lint.lint(t, voice=False)
                if f["code"] == "TRUTH_LAURA_HUMAN_CLAIM"] for k, t in VISIBLE_TEXT.items()}
    ai_words = [k for k, t in VISIBLE_TEXT.items() if " AI" in f" {t} " or "artificial" in t.lower()]
    out.append(_gate(
        "laura_never_claims_human_in_text", PASS if not any(hits.values()) else FAIL,
        {"lint_hits": hits, "scope": "the transcribed words only", "text_source":
         VISIBLE_TEXT_SOURCE},
        basis="lint TRUTH_LAURA_HUMAN_CLAIM over the transcribed words",
        rule="Laura is never presented as human",
        why=("no transcribed word claims she is human" if not any(hits.values()) else
             "a transcribed word claims a human Laura")))
    about = " ".join(str(x) for x in (copy_v2.export().get("about_paragraphs") or []))
    about_ai = "Laura" in about and " AI" in f" {about}"
    out.append(_gate(
        "laura_ai_disclosure_at_banner", PASS if (has_laura and about_ai) else FAIL,
        {"in_image_disclosure": bool(ai_words), "store_level_disclosure": has_laura,
         "about_names_laura_as_ai": about_ai,
         "etsy_banner_caption": "Etsy publishes no caption field for a big banner"},
        basis="measured: store disclosure and About text (copy_v2)",
        rule="spec/07 + D-FB-11..13: Laura is disclosed as an AI where she is presented; "
             "never claims to be human (Etsy's own banner requirement: see "
             "ai_generated_imagery_disclosure)",
        why=("the shop's disclosure and About both say Laura is an AI; the banner adds no "
             "human claim. In-image AI wording is not required by any verified rule"
             if has_laura and about_ai else
             "the shop does not say Laura is an AI where she is presented")))
    return out


def _truth_gates(db=None) -> list[dict]:
    from . import lint

    out = []
    try:
        cat = _catalogue(db)
    except Exception as exc:  # noqa: BLE001
        cat = None
        out.append(_gate("product_truth", UNKNOWN, {"error": f"{type(exc).__name__}"},
                         basis="catalogue unavailable", why="the catalogue could not be read",
                         review="engineering"))
    if cat is not None:
        from ..visual import final_image_gate as FIG

        data = CA.verified_bytes(ROLE)
        fg = FIG.evaluate({"image_png": data,
                           "image_sha256": hashlib.sha256(data).hexdigest()})
        from ..gates import platform_policy as PP

        mood = PP.ASSET_ROLES.get("mood_frame")
        out.append(_gate(
            "product_truth", UNKNOWN,
            {"final_image_gate": {k: fg.get(k) for k in ("status", "why", "gate_version")},
             "crochet_classification": {**CROCHET_CLASSIFICATION,
                                        "mapped_to_patterns": list(
                                            CROCHET_CLASSIFICATION["mapped_to_patterns"])},
             "rules_consulted": {
                 "platform_policy.ASSET_ROLES['mood_frame']": list(mood) if mood else None,
                 "platform_policy (module rule)": "a generated image may not misrepresent what "
                                                  "the buyer receives",
                 "etsy_help_center": "no fetched Etsy text addresses what a shop banner may "
                                     "depict (ETSY_EVIDENCE)"},
             "catalogue_products": cat["products"], "declared_content": DECLARED_CONTENT,
             "visual_task": "VT-B2-1"},
            basis="final_image_gate on the file + the catalogue + the repo's marketplace rules",
            rule=("Product Truth (unweakened): an image may not present a product that does "
                  "not exist. platform_policy permits a generated 'mood_frame' only as a "
                  "listing image that makes no claim about the object; no rule covers concept "
                  "crochet on a storefront banner"),
            why=(f"D-FB-18 classifies the banner's crochet as brand/lifestyle concept imagery, "
                 f"mapped to no pattern ({len(cat['products'])} patterns exist: "
                 + ", ".join(p["title"] for p in cat["products"])
                 + "). Whether concept crochet is acceptable on a public storefront banner "
                 "cannot be proven from the repo's rules or Etsy's fetched text, and whether a "
                 "shopper would read it as for sale is unmeasured -- so UNKNOWN (blocks). The "
                 "composition stays the canonical art target; VT-B2-1 (GATED) reproduces the "
                 "scene with verified products when warranted"),
            review=("human: would a shopper take any crochet shown (or the book spines) for "
                    "something this shop sells?")))
        nav = _nav_truth(BANNER_NAV, cat)
        out.append(_gate(
            "nav_categories_truth", FAIL if nav["empty"] else PASS,
            {"banner_nav": nav["rows"], "empty": nav["empty"],
             "text_source": VISIBLE_TEXT_SOURCE},
            basis="transcribed nav words vs measured catalogue sections",
            rule="D-FB-18 item 3: never advertise empty categories publicly; generated "
                 "navigation shows only populated categories (store_foundation.navigation)",
            why=(f"the banner's baked-in nav names {', '.join(nav['empty'])}, which hold no "
                 f"pattern today. The owner chose not to alter the source file, so this stays a "
                 f"reported truth finding for the banner; every generated surface hides those "
                 f"categories until populated" if nav["empty"]
                 else "every named category holds a pattern"),
            review="owner: publish the banner only once those categories hold products, or "
                   "accept/decide otherwise; the canonical PNG is never edited"))
    found = {k: [f["code"] for f in lint.lint(t, voice=False) if f["kind"] == lint.TRUTH]
             for k, t in VISIBLE_TEXT.items()}
    voice = {k: sorted({f["code"] for f in lint.lint(t) if f["kind"] == lint.VOICE})
             for k, t in VISIBLE_TEXT.items()}
    out.append(_gate(
        "public_copy_truth_lint", FAIL if any(found.values()) else PASS,
        {"truth_findings": found, "voice_advisories": {k: v for k, v in voice.items() if v},
         "strings": VISIBLE_TEXT, "text_source": VISIBLE_TEXT_SOURCE},
        basis="store_foundation.lint truth rules over the transcribed words",
        rule="customer copy truth lint",
        why=("no truth rule fires on any transcribed word (all-caps voice advisories are "
             "typography in the artwork, not copy)" if not any(found.values()) else
             "a truth rule fires: " + str({k: v for k, v in found.items() if v}))))
    out.append(_gate(
        "visible_text_complete", UNKNOWN,
        {"ocr_installed": False, "strings_checked": len(VISIBLE_TEXT)},
        basis="no OCR in this build", rule="every word a shopper reads is linted",
        why="the lint covers the transcription; nobody has machine-checked that it is every "
            "word in the image", review="human: confirm the transcription is complete"))
    return out


def _rollup(gates: list[dict], *, db_used: bool, block: dict | None = None) -> dict:
    by = {s: [g["gate"] for g in gates if g["status"] == s] for s in STATUSES}
    dimensional = {"f233_banner_canvas_4to1", "f233_identity_block_survives_4to1",
                   "f233_identity_block_in_phone_window", "etsy_banner_minimum_and_format"}
    nondim = [g for g in by[FAIL] if g not in dimensional]
    canon = CA.ASSETS[ROLE]
    return {
        "version": ASSESSMENT_VERSION, "asset": canon.to_dict(), "decision": canon.decision,
        "gates": gates, "passed": by[PASS], "failed": by[FAIL], "unknown": by[UNKNOWN],
        "unverified_assumptions": by[UNVERIFIED_ASSUMPTION],
        "publishable": not by[FAIL] and not by[UNKNOWN],
        "status": "PUBLISHABLE" if not by[FAIL] and not by[UNKNOWN] else "BLOCKED",
        "only_dimensional_failures": bool(by[FAIL]) and not nondim,
        "non_dimensional_failures": nondim,
        "identity_block": {k: (block or {}).get(k) for k in ("rows", "cols", "height_px",
                                                              "width_px")},
        "declared_content": DECLARED_CONTENT, "visible_text_source": VISIBLE_TEXT_SOURCE,
        "rule": ("D-FB-17/18: the exact file is used only if every applicable gate passes; "
                 "UNKNOWN blocks like FAIL and is never reported as PASS; an "
                 "UNVERIFIED_ASSUMPTION is advisory -- never a pass, never a verified failure"),
        "etsy_evidence": list(ETSY_EVIDENCE), "visual_tasks": list(VISUAL_TASKS),
        "db_used": db_used,
    }


def storefront_findings(result: dict | None = None) -> list[dict]:
    """F-233 findings naming the exact gate that stops the owner's file."""
    r = result or assess()
    out = []
    for g in r["gates"]:
        if g["status"] not in BLOCKING:
            continue
        code = f"STORE_BANNER_OWNER_{g['gate'].upper()}_{g['status']}"
        if g["gate"] == "canonical_integrity":
            code = "STORE_BANNER_CANONICAL_UNVERIFIED"
        out.append({"row": "F-233", "code": code,
                    "detail": f"canonical owner banner ({r['asset']['sha256'][:12]}, "
                              f"{r['decision']}): {g['gate']} {g['status']}: {g['why'][:300]}"})
    return out


def identity_review_request(db, result: dict | None = None) -> int | None:
    """Put the banner's person in the human identity-review queue (F-219). Idempotent while
    open. Records a question; approves nothing."""
    from ..visual import identity_gate

    r = result or assess()
    g = next((x for x in r["gates"] if x["gate"] == "laura_identity"), None)
    review = (g or {}).get("evidence", {}).get("owner_human_review")
    if g is not None and g["status"] == PASS and review:
        # Record the owner's review in the same queue, resolved, so the provenance is durable.
        sha = r["asset"]["sha256"]
        done = [x for x in identity_gate.queue(db, state="resolved", limit=500)
                if x["image_sha256"] == sha and x["decision"] == "confirmed_same_person"]
        if done:
            return done[0]["id"]
        rid = identity_gate.open_review(
            db, product_class="storefront_banner",
            subject="owner canonical banner (D-FB-17)",
            gate={"band": identity_gate.BAND_REVIEW, "review_required": True,
                  "why": "owner human identity review", "validity": None, "biometric": None,
                  "judges": []}, image_sha256=sha)
        identity_gate.resolve(db, rid, decision="confirmed_same_person",
                              reviewer=f"owner ({review['decision']})",
                              note=f"{review['scope']}; {review['not']}")
        return rid
    if g is None or g["status"] != UNKNOWN:
        return None
    gate = {"band": identity_gate.BAND_REVIEW, "review_required": True,
            "why": g["why"], "validity": None,
            "biometric": g["evidence"].get("biometric"), "judges": []}
    return identity_gate.open_review(db, product_class="storefront_banner",
                                     subject="owner canonical banner (D-FB-17)",
                                     gate=gate, image_sha256=r["asset"]["sha256"])


# ---- owner-review correction candidates --------------------------------------------------

def _crop_rows(block: dict, h: int, crop_h: int) -> tuple[int, int]:
    """A full-width 4:1 window anchored at the top of the identity block, so it keeps the
    monogram whole and as much of the block as the height allows."""
    top = max(0, min(block["rows"][0], h - crop_h))
    return top, top + crop_h - 1


def candidates() -> list[dict]:
    """Deterministic, non-generative 4:1 reframes of the exact file -- REJECTED by the owner
    (D-FB-18 item 4: never crop away the tagline/heart/category composition, never use
    stretched-edge padding). Kept only as historical evidence of what was proposed; neither
    can be adopted. Returned with PIL images under "image"."""
    import numpy as np
    from PIL import Image

    im = CA.image(ROLE)
    w, h = im.size
    a = np.asarray(im)
    block = measure_identity_block(a.astype(float))
    crop_h = int(round(w / 4))
    out = []
    if block["found"]:
        t0, t1 = _crop_rows(block, h, crop_h)
        kept = [r for r in block["runs"] if not r["scenery"] and r["rows"][1] <= t1]
        cut = [r["rows"] for r in block["runs"] if not r["scenery"] and r["rows"][1] > t1]
        out.append({
            "id": "A_crop_4x1_top_anchored", "image": im.crop((0, t0, w, t1 + 1)),
            "size": [w, crop_h], "aspect": round(w / crop_h, 3),
            "changes": {"rows_kept": [t0, t1], "rows_removed_top": t0,
                        "rows_removed_bottom": h - 1 - t1, "owner_pixels_altered": 0,
                        "pixels_added": 0, "identity_rows_cut": cut,
                        "identity_elements_kept": len(kept)},
            "note": (f"full-width crop to {w}x{crop_h} ({w / crop_h:.3f}:1), rows {t0}-{t1}: "
                     f"keeps the monogram, wordmark, descriptor and most of the script line; "
                     f"identity rows beyond {t1} are cut ({cut}) -- per the ink runs that is "
                     f"the last row of the script line, the heart and the category line. "
                     f"Everything below row {t1} is removed. Whether the person's face stays "
                     f"whole is NOT measured (no face detector): owner to look")})
    # B: pad left/right to 4:1 with the image's own edge colours (per row, vertically smoothed)
    new_w = h * 4
    pad = new_w - w
    lp, rp = pad // 2, pad - pad // 2
    k = 201
    kern = np.ones(k) / k

    def edge(cols):
        col = cols.mean(axis=1)
        sm = np.stack([np.convolve(np.pad(col[:, c], k // 2, mode="edge"), kern, "valid")
                       for c in range(3)], axis=1)
        return sm.clip(0, 255).astype("uint8")

    left = np.repeat(edge(a[:, :4].astype(float))[:, None, :], lp, axis=1)
    right = np.repeat(edge(a[:, -4:].astype(float))[:, None, :], rp, axis=1)
    padded = np.concatenate([left, a, right], axis=1)
    out.append({
        "id": "B_pad_4x1_edge_colour", "image": Image.fromarray(padded),
        "size": [new_w, h], "aspect": round(new_w / h, 3),
        "changes": {"columns_added_left": lp, "columns_added_right": rp,
                    "owner_pixels_altered": 0, "pixels_added": pad * h,
                    "owner_pixels_kept": w * h,
                    "fill": f"per-row mean of the 4 outermost columns, {k}-row box smoothed"},
        "note": (f"every owner pixel kept unchanged at its own size; {lp} px added left and "
                 f"{rp} px right in the image's own edge colours to reach {new_w}x{h} (4:1). "
                 f"Visible change: side bands that are a soft vertical gradient of each "
                 f"edge's own colours (no new imagery); the artwork occupies the centre "
                 f"{w / new_w:.0%} of the width. Under the ASSUMED 2:1 phone window the "
                 f"owner columns {(new_w - 2 * h) // 2 - lp}-{(new_w + 2 * h) // 2 - lp - 1} "
                 f"show")})
    for c in out:
        c["status"] = REJECTED_BY_OWNER
        c["rejected_by"] = "D-FB-18 item 4"
        c["adopted"] = False
        c["fixes"] = ["f233_banner_canvas_4to1"] + (
            ["f233_identity_block_survives_4to1"] if c["id"].startswith("B") else [])
        c["does_not_fix"] = ["laura_publication_status", "laura_identity", "product_truth",
                             "nav_categories_truth", "ai_generated_imagery_disclosure",
                             "laura_ai_disclosure_at_banner"]
        if c["id"].startswith("A"):
            c["does_not_fix"].insert(0, "f233_identity_block_survives_4to1 (heart and "
                                        "category line are cut)")
    return out


def centre_crop_simulation():
    """What a plain centre crop to 4:1 would show (one possible Etsy behaviour; Etsy does not
    publish its fitting rule). For the assessment, not a candidate."""
    im = CA.image(ROLE)
    w, h = im.size
    ch = int(round(w / 4))
    t = (h - ch) // 2
    return im.crop((0, t, w, t + ch)), [t, t + ch - 1]


def _review_png(img, width: int = REVIEW_WIDTH) -> bytes:
    from PIL import Image

    w, h = img.size
    small = img.resize((width, max(1, round(h * width / w))), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def write_evidence(root: Path, *, now: datetime | None = None) -> dict:
    """Write the assessment JSON and the review PNGs (each < 1 MB). Returns the record."""
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    cdir = root / CANDIDATE_DIR_REL
    cdir.mkdir(parents=True, exist_ok=True)
    result = assess()
    files = []
    for c in candidates():
        img = c.pop("image")
        data = _review_png(img)
        width = REVIEW_WIDTH
        while len(data) > REVIEW_MAX_BYTES and width > 600:
            width -= 100
            data = _review_png(img, width)
        name = f"{c['id']}.png"
        (cdir / name).write_bytes(data)
        c.update({"review_file": f"{CANDIDATE_DIR_REL}/{name}",
                  "review_file_sha256": hashlib.sha256(data).hexdigest(),
                  "review_file_px": [width, round(c["size"][1] * width / c["size"][0])],
                  "review_file_bytes": len(data),
                  "review_copy_note": "resampled (LANCZOS) for review; the full-size "
                                      "candidate is regenerated deterministically by "
                                      "owner_banner.candidates()"})
        files.append(c)
    sim, rows = centre_crop_simulation()
    width = REVIEW_WIDTH
    data = _review_png(sim, width)
    while len(data) > REVIEW_MAX_BYTES and width > 600:
        width -= 100
        data = _review_png(sim, width)
    (cdir / "simulation_centre_crop_4x1.png").write_bytes(data)
    record = {"generated_at": now.isoformat(), "assessment": result, "candidates": files,
              "simulation": {"file": f"{CANDIDATE_DIR_REL}/simulation_centre_crop_4x1.png",
                             "rows": rows, "bytes": len(data), "px": [width, width // 4],
                             "what": "a plain 4:1 centre crop of the exact file -- one "
                                     "possible Etsy behaviour, not a candidate"}}
    (cdir / "owner_banner_assessment.json").write_text(
        json.dumps(record, indent=1, sort_keys=True, default=str) + "\n")
    return record
