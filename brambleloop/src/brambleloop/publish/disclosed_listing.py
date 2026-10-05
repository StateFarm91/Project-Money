"""The disclosed-render listing set: produce, verify, QA, disclose, record, export (D-FB-7).

`visual.disclosed_render` draws the product; `visual.render_verification` checks the pixels
against the CIR. This module is the listing half: it turns those frames into a customer
listing set that can be shipped only when every gate that applies to a listing image has run
and passed, and it is where the disclosure is enforced in all three places it must live --
the image itself, each image's alt text and the listing copy.

**The wording.** "Digital rendering of the pattern's finished design, not a photograph."
It says what the picture is (a digital rendering), what it shows (the finished design the
pattern makes -- not a product we ship, since we sell a pattern) and what it is not (a
photograph, the thing a buyer would otherwise assume). It deliberately avoids "AI" and
"generated": no model is in this path, and Etsy's AI-disclosure language would misdirect a
buyer about how the picture was made while still not telling them it is not a photograph.
`publish.eligibility.RENDER_LABEL` says the same thing in the same spirit; this sentence is
the one the image carries, so it is the one the copy and alt text must match verbatim.

**A label is not a licence** (eligibility #69). Nothing here lets the disclosure excuse an
inaccurate frame: a frame that fails the verifier is not exportable, disclosed or not, and
the disclosure check runs separately from, never instead of, Product Truth.
"""
from __future__ import annotations

import hashlib
import io

from ..visual import render_contract as K

ACTION = "assets.disclosed_render"
DISCLOSURE = K.DISCLOSURE

# The sentence the listing description carries: one source, the policy gate's disclosure
# table, so the copy the classifier writes and the copy this module checks cannot drift.
from ..gates.platform_policy import DISCLOSURES as _DISCLOSURES  # noqa: E402

COPY_DISCLOSURE = _DISCLOSURES["disclosed_render"]

ALT_TEXT_MAX = 500          # Etsy uploadListingImage: "Max length 500 characters"

THUMB_LEGIBILITY_PX = 340   # the width a phone search grid and a 2-up mobile gallery serve

_VIEW_TEXT = {
    ("flat", "hero"): "the whole piece laid flat, seen from above",
    ("flat", "scale"): "the whole piece with its finished width and length marked",
    ("flat", "detail"): "a close view of one corner, stitch for stitch",
    ("rounds", "hero"): "the finished piece",
    ("rounds", "scale"): "the finished piece with its size marked",
    ("rounds", "detail"): "a close view of the rounds, stitch for stitch",
}


class DisclosureMissing(ValueError):
    """A disclosed render offered for export without its disclosure in every place."""


def _phrase_in(text: str) -> bool:
    norm = " ".join((text or "").lower().replace("’", "'").split())
    return DISCLOSURE.lower() in norm


def alt_text(manifest: dict, cir) -> str:
    """The image's alt text: the disclosure first, then what it shows, from the CIR."""
    colours = sorted({c for c in (cir.colors or {})
                      if any(r.color == c for comp in cir.components for r in comp.rows)})
    shows = _VIEW_TEXT.get((manifest.get("form"), manifest.get("view")), "the finished piece")
    if manifest.get("form") == "rounds" and manifest.get("view") == "hero":
        layout = manifest.get("layout") or {}
        if layout.get("projection") == "oblique":
            shows = "the finished basket seen from slightly above"
        elif (manifest.get("pieces") or 1) > 1:
            shows = f"all {manifest['pieces']} pieces seen from above"
    if manifest.get("form") == "rounds" and manifest.get("view") == "detail" and \
            (manifest.get("layout") or {}).get("part") == "base":
        shows = "the base seen from above, every base round stitch for stitch"
    dims = manifest.get("finished_dimensions_cm") or {}
    size = ""
    if dims.get("width") and dims.get("height"):
        size = (f" About {dims['width']:g} x {dims['height']:g} cm at the stated gauge, "
                f"with a centimetre scale bar.")
    text = (f"{DISCLOSURE}. {cir.title}: {shows}, in {' and '.join(colours)}.{size}")
    return text[:ALT_TEXT_MAX]


def caption_in_image(png: bytes, cir=None) -> dict:
    """Whether the frame's own pixels carry the disclosure caption, in the contract words."""
    from ..visual.render_verification import _caption, _Frame

    palette = {k: K.hex_rgb(v) for k, v in ((cir.colors if cir is not None else {}) or {}).items()}
    try:
        return _caption(_Frame(png, palette))
    except Exception as exc:  # noqa: BLE001 - unreadable is not disclosed
        return {"status": "FAIL", "iou": 0.0, "why": f"unreadable image: {exc}"}


def export_check(frame: dict, *, image_bytes: bytes, description: str, cir=None) -> dict:
    """A disclosed frame may leave only with the disclosure in the image, its alt text and the
    listing copy -- and with structural truth PASS on these exact bytes. Each is checked."""
    problems = []
    if frame.get("kind") != "disclosed_render":
        return {"ok": True, "applies": False, "problems": []}
    sha = hashlib.sha256(image_bytes).hexdigest()
    if sha != ((frame.get("image") or {}).get("sha256")):
        problems.append("the bytes offered are not the frame on record")
    cap = caption_in_image(image_bytes, cir)
    if cap.get("status") != "PASS":
        problems.append(f"disclosure caption missing from the image (iou {cap.get('iou')})")
    if not _phrase_in(frame.get("alt_text", "")):
        problems.append("disclosure missing from the image's alt text")
    if len(frame.get("alt_text", "")) > ALT_TEXT_MAX:
        problems.append("alt text longer than Etsy allows")
    if not _phrase_in(description):
        problems.append("disclosure missing from the listing copy")
    from ..visual.product_authority import structural_floor

    floor = structural_floor(frame)
    if floor["status"] != "PASS":
        problems.append(f"structural truth {floor['status']}: {floor['why'][:160]} "
                        f"(a disclosure never excuses an inaccurate image)")
    return {"ok": not problems, "applies": True, "problems": problems,
            "caption_iou": cap.get("iou"), "structural_truth": floor["status"]}


# --------------------------------------------------------------------------- QA

def _thumb_legibility(png: bytes, model: dict, expected_objects: int) -> dict:
    """At 340 px wide, the whole product is still in frame and the hero still reads.

    Measured, not asserted: the product silhouette must sit inside the title-safe area (whole
    product visible), keep its proportions (the shape reads), stay separated into the pieces
    the pattern makes (a set of four reads as four), and every yarn colour the pattern uses
    must survive the downscale as a visible region (a contrast band that vanishes at
    thumbnail size is a feature the buyer never sees).
    """
    import numpy as np
    from PIL import Image
    from scipy import ndimage

    from ..publish.mobile import TITLE_SAFE_MARGIN

    img = Image.open(io.BytesIO(png)).convert("RGB")
    small = img.resize((THUMB_LEGIBILITY_PX, round(THUMB_LEGIBILITY_PX * img.height / img.width)),
                       Image.LANCZOS)
    arr = np.asarray(small, dtype=np.int32)
    h, w = arr.shape[:2]
    pz = K.zone_px(K.PRODUCT_ZONE, w)
    zone = arr[: int(round(K.PRODUCT_ZONE[3] * h)) + 2]
    dist_bg = np.sqrt(((zone - np.array(K.BACKGROUND)) ** 2).sum(axis=2))
    mask = dist_bg > 30
    problems = []
    if not mask.any():
        return {"ok": False, "problems": ["no product visible at 340 px"]}
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    band = TITLE_SAFE_MARGIN
    inside = x0 >= band * w - 1 and x1 <= (1 - band) * w and y0 >= band * h - 1
    if not inside:
        problems.append("the product reaches the title-safe band at 340 px")
    labels, count = ndimage.label(ndimage.binary_closing(mask, iterations=1))
    sizes = ndimage.sum(mask, labels, range(1, count + 1)) if count else []
    pieces = int(sum(1 for s in sizes if s >= 0.01 * mask.size))
    if pieces != expected_objects:
        problems.append(f"{pieces} piece(s) read at 340 px where the pattern makes {expected_objects}")
    coverage = float((x1 - x0 + 1) * (y1 - y0 + 1) / (w * h))
    if coverage < 0.25:
        problems.append(f"the product fills {coverage:.0%} of the frame at 340 px")
    # The colours this frame shows at full size (a basket's base is all one colour, so its
    # contrast bands are not expected there) must each survive the downscale.
    full = np.asarray(img, dtype=np.int32)[: int(round(K.PRODUCT_ZONE[3] * img.height))]
    colours = {}
    for name, rgb in model["palette"].items():
        if name not in {r["colour"] for r in model["rows"]}:
            continue
        present = float((np.abs(full - np.array(rgb)).sum(axis=2) == 0).mean())
        if present < 0.002:
            continue
        d = np.sqrt(((zone - np.array(rgb)) ** 2).sum(axis=2))
        share = float((d < 40).sum() / max(1, mask.sum()))
        colours[name] = round(share, 4)
        if share < 0.005:
            problems.append(f"colour {name} is shown at full size and not visible at 340 px")
    return {"ok": not problems, "px": THUMB_LEGIBILITY_PX, "inside_title_safe": bool(inside),
            "pieces": pieces, "expected_pieces": expected_objects,
            "coverage": round(coverage, 4), "colour_share": colours, "problems": problems,
            "zone_px": list(pz)}


def listing_qa(frames: list[dict], pngs: dict[str, bytes], cir, *, store=None) -> dict:
    """Every existing listing-image QA gate this set can be run through, plus 340 px legibility.

    Thresholds are the gates' own; nothing is relaxed. One deliberate non-application is
    recorded rather than hidden: `commerce.thumbnail` THUMB_TEXT_ILLEGIBLE judges text meant
    to be read in the search grid (the release passes the hero headline size). The disclosure
    caption is a small full-size caption by owner instruction and is repeated in alt text and
    copy; it is not grid text, so no grid text size is passed for it.
    """
    from PIL import Image

    from ..commerce import thumbnail as thumb
    from ..gates.asset_truth import Asset, AssetClass, Claims, Provenance, check_assets, \
        check_shape_claims
    from ..visual.render_verification import expected_model
    from . import eligibility as el
    from . import layout_qa, mobile

    model = expected_model(cir)
    images = {f["view"]: Image.open(io.BytesIO(pngs[f["view"]])).convert("RGB") for f in frames}
    out: dict = {"frames": {}}

    class _F:  # layout_qa.check_frames reads .image and .position
        def __init__(self, image, position):
            self.image, self.position = image, position

    ordered = sorted(frames, key=lambda f: f["position"])
    layout_problems = layout_qa.check_frames(
        [_F(images[f["view"]], f["position"]) for f in ordered],
        text_positions=tuple(f["position"] for f in ordered))
    out["layout_qa"] = {"problems": layout_problems, "ok": not layout_problems}
    hero = next(f for f in ordered if f["role"] == "hero")
    aspect = None
    dims = hero["disclosed_render"]["finished_dimensions_cm"]
    if dims.get("width") and dims.get("height") and hero["disclosed_render"]["form"] == "flat":
        aspect = dims["width"] / dims["height"]
    thumb_v = thumb.evaluate_thumbnail(images[hero["view"]], subject_aspect=aspect)
    out["hero_thumbnail"] = thumb_v.to_dict() | {
        "text_check": ("not applied: the only text is the disclosure caption, a small "
                       "full-size caption repeated in alt text and copy, not grid text")}

    pieces = cir.components[0].make if hero["disclosed_render"]["form"] == "rounds" else 1
    for f in ordered:
        expected = pieces if f["view"] == "hero" and \
            (f["disclosed_render"]["layout"] or {}).get("objects", 1) > 1 else 1
        out["frames"][f["view"]] = {"legibility_340": _thumb_legibility(pngs[f["view"]], model, expected),
                                    "title_safe_ink_170": round(mobile.title_safe_ink(images[f["view"]]), 5)}

    # Mobile contexts, each actually rendered and stored, with the ink in the title-safe band.
    renders = []
    refs = {}

    def _store_render(name, image):
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        data = buf.getvalue()
        sha = hashlib.sha256(data).hexdigest()
        if store is not None:
            store.put(f"mobile/{name}.png", data, "image/png")
        refs[name] = sha
        return f"sha256:{sha}"

    hero_img = images[hero["view"]]
    renders.append(mobile.ContextRender(
        mobile.SEARCH_THUMBNAIL,
        _store_render("search_thumbnail", hero_img.resize((mobile.MOBILE_THUMB_PX,) * 2)),
        1, mobile.MOBILE_THUMB_PX, mobile.title_safe_ink(hero_img, px=mobile.MOBILE_THUMB_PX)))
    first = [images[f["view"]] for f in ordered[:mobile.BEFORE_SCROLL]]
    strip = Image.new("RGB", (390 * len(first), 390), K.BACKGROUND)
    for i, im in enumerate(first):
        strip.paste(im.resize((390, 390)), (390 * i, 0))
    ink390 = max(mobile.title_safe_ink(im, px=390) for im in first)
    renders.append(mobile.ContextRender(mobile.PHONE_GALLERY, _store_render("phone_gallery", strip),
                                        len(first), 390, ink390))
    renders.append(mobile.ContextRender(mobile.FIRST_THREE, _store_render("first_three", strip),
                                        len(first), 390, ink390))
    renders.append(mobile.ContextRender(
        mobile.FULL_GALLERY, f"sha256:{hero['image']['sha256']}", len(ordered), 2000,
        max(mobile.title_safe_ink(images[f["view"]], px=2000) for f in ordered)))
    purpose = {"hero": el.CONVERSION_CREATIVE, "scale": el.CUSTOMER_INFORMATION,
               "detail": el.ENGINEERING_EVIDENCE}
    candidates = [el.Candidate(asset_id=f"{cir.slug}:{f['view']}",
                               medium=AssetClass.DIGITAL_TWIN_RENDER,
                               purpose=purpose[f["view"]], job=f["disclosed_render"]["job"],
                               position=f["position"]) for f in ordered]
    out["mobile"] = mobile.qa(candidates, renders)
    out["frame_set"] = el.check_set(candidates)

    # Asset Truth: every frame as an asset, provenance "twin", its claims from the CIR.
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    twin = build_twin(cir, compile_cir(cir), component=cir.components[0].name)
    assets = [Asset(asset_id=f"{cir.slug}:{f['view']}", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
                    provenance=Provenance(source="twin", created_by="publishing:disclosed_render",
                                          tool=f["disclosed_render"]["renderer_version"]),
                    depicts_stitches=sorted(twin.stitch_types_used),
                    depicts_colors=sorted(c for c in twin.colors_used if c),
                    depicts_components=[cir.components[0].name],
                    claims=Claims(finished_width_cm=twin.width_cm, finished_height_cm=twin.height_cm),
                    is_hero=f["role"] == "hero", disclosed_as_illustration=True)
              for f in ordered]
    findings = check_assets(assets, cir, twin) + check_shape_claims(cir.title, cir, twin)
    errors = [str(x) for x in findings if x.is_error]
    out["asset_truth"] = {"errors": errors, "ok": not errors}
    return out


# --------------------------------------------------------------------------- the set

def build(cir, *, store=None, db=None, lineage=None, description: str = "") -> dict:
    """Render, store, verify and QA the disclosed listing set for one certified product.

    Returns the record that is filed. `usable_as_listing_asset` is true only when every frame
    verifies PASS, every QA gate passed, and the disclosure is in the image and the alt text
    (the copy disclosure is checked again at export, against the listing actually written).
    """
    from ..core.artifacts import ArtifactStore
    from ..visual import disclosed_render as D
    from ..visual.product_authority import structural_floor

    store = store or ArtifactStore()
    try:
        rendered = D.listing_set(cir)
    except (D.RenderRefused, RuntimeError, OSError) as exc:
        return {"made": False, "generated": False, "kind": "disclosed_render", "slug": cir.slug,
                "version": cir.version, "usable_as_listing_asset": False,
                "launch_blocked": [f"renderer refused: {exc}"], "why": str(exc)}
    frames, pngs = [], {}
    for position, rf in enumerate(rendered, start=1):
        kwargs = {}
        if lineage is not None:
            kwargs = {"artefact_class": "visual_truth", "lineage": lineage}
        stored = store.put(f"{cir.slug}/{cir.version}/disclosed-{rf.view}.png", rf.png,
                           "image/png", db=db,
                           keep=("disclosed render: the customer image and the bytes its "
                                 "verification is bound to") if db is not None else "",
                           **kwargs)
        frame = {"kind": "disclosed_render", "made": True, "generated": False,
                 "deterministic": True, "carries_model": False, "position": position,
                 "role": rf.manifest["role"], "view": rf.view, "slug": cir.slug,
                 "version": cir.version, "image": {"sha256": stored.sha256},
                 "image_ref": f"sha256:{stored.sha256}", "disclosed_render": rf.manifest,
                 "alt_text": alt_text(rf.manifest, cir), "durable": stored.durable,
                 "disclosed_as_illustration": True}
        from pathlib import Path

        from ..core import artifacts as _artifacts

        if Path(store.root) != Path(_artifacts.DEFAULT_DIR):
            frame["artifact_dir"] = str(store.root)
        floor = structural_floor(frame)
        frame["structural_truth"] = {"status": floor["status"], "why": floor["why"],
                                     "failed": (floor.get("verification") or {}).get("failed"),
                                     "unknown": (floor.get("verification") or {}).get("unknown")}
        frames.append(frame)
        pngs[rf.view] = rf.png
    qa = listing_qa(frames, pngs, cir, store=store)
    for f in frames:
        leg = qa["frames"][f["view"]]["legibility_340"]
        f["readable_at_grid"] = bool(leg["ok"]) and not any(
            p.startswith("FRAME_DIES_AT_THUMBNAIL") for p in qa["layout_qa"]["problems"])
        f["disclosure"] = {"in_image": caption_in_image(pngs[f["view"]], cir)["status"] == "PASS",
                           "in_alt_text": _phrase_in(f["alt_text"])}
    blocked = []
    for f in frames:
        if f["structural_truth"]["status"] != "PASS":
            blocked.append(f"{f['view']}: structural truth {f['structural_truth']['status']}")
        if not (f["disclosure"]["in_image"] and f["disclosure"]["in_alt_text"]):
            blocked.append(f"{f['view']}: disclosure incomplete {f['disclosure']}")
        if not qa["frames"][f["view"]]["legibility_340"]["ok"]:
            blocked.append(f"{f['view']}: 340 px legibility "
                           f"{qa['frames'][f['view']]['legibility_340']['problems']}")
    for gate in ("layout_qa", "asset_truth", "frame_set", "mobile"):
        if not qa[gate]["ok"]:
            blocked.append(f"{gate}: {qa[gate].get('problems') or qa[gate].get('errors') or qa[gate].get('why')}")
    if not qa["hero_thumbnail"]["ok"]:
        blocked.append(f"hero_thumbnail: {qa['hero_thumbnail']['problems']}")
    if description and not _phrase_in(description):
        blocked.append("listing copy carries no disclosure")
    return {"made": True, "generated": False, "kind": "disclosed_render",
            "method_version": D.RENDERER_VERSION, "slug": cir.slug, "version": cir.version,
            "cir_fingerprint": cir.fingerprint, "frames": frames, "qa": qa,
            "copy_disclosure": COPY_DISCLOSURE,
            "usable_as_listing_asset": not blocked, "launch_blocked": blocked,
            "why": ("every frame verified against the certified CIR, every listing-image QA "
                    "gate passed and the disclosure is in each image and its alt text"
                    if not blocked else "; ".join(blocked)[:600])}


def record(db, rec: dict) -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=ACTION,
                       artifact=f"{rec.get('slug')}@{rec.get('version')}", detail=rec))


def last_asset(db, *, slug: str = "") -> dict | None:
    """The most recent disclosed set on file for a product."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..visual.disclosed_render import RENDERER_VERSION

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == ACTION)
                             .order_by(desc(AuditLog.id)).limit(50)):
            detail = row.detail or {}
            if (detail.get("made") and detail.get("method_version") == RENDERER_VERSION
                    and (not slug or detail.get("slug") == slug)):
                return detail
    return None


def disclosed_shas(db) -> set[str]:
    """Every image digest filed as a disclosed render, so an export path can recognise one."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    out: set[str] = set()
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == ACTION)):
            for f in (row.detail or {}).get("frames") or []:
                sha = (f.get("image") or {}).get("sha256")
                if sha:
                    out.add(sha)
    return out


def export_images(db, *, slug: str, description: str, store=None) -> list[tuple[str, bytes, str]]:
    """The only exporter for disclosed frames: (filename, bytes, alt_text), or a refusal.

    Refuses the whole set when any frame lacks the disclosure in its pixels, its alt text or
    the listing copy, or when structural truth is not PASS on the exact bytes."""
    from ..core.artifacts import ArtifactStore
    from ..visual.render_verification import authoritative_cir

    rec = last_asset(db, slug=slug)
    if rec is None:
        raise DisclosureMissing(f"no disclosed render set on file for {slug}")
    cir = authoritative_cir(slug, rec.get("version"))
    out, problems = [], []
    for f in sorted(rec["frames"], key=lambda f: f["position"]):
        st = ArtifactStore(store or f.get("artifact_dir") or None)
        data = st.get(f["image"]["sha256"], db=db)
        verdict = export_check(f, image_bytes=data, description=description, cir=cir)
        if not verdict["ok"]:
            problems.append(f"frame {f['position']} ({f['view']}): {verdict['problems']}")
            continue
        out.append((f"{slug}-{f['view']}.png", data, f["alt_text"]))
    if problems:
        raise DisclosureMissing("; ".join(problems))
    return out
