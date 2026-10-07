"""The truthful imagery set each Launch-0 listing needs, or the exact reason a job is missing.

For every listing in `products.launch0.LAUNCH0_SLUGS` this assembles, without a model, a
provider or a network call:

  * the disclosed render set (`publish.disclosed_listing.build`) for every variant -- the
    DESIRE / SCALE / DETAIL frames, each verified by `render_verification` on its bytes;
  * the disclosed gallery frames (`visual.gallery_frames`) for the further jobs a drawing can
    answer truthfully -- MATERIALS, COLOUR_CONTEXT, CONSTRUCTION, SIZING -- each verified by
    redrawing independently recomputed facts;
  * the job ledger against `publish.eligibility.gallery_jobs_for` for the listing's category,
    sizes and colours: covered jobs with the frame that covers them, and missing jobs with the
    precise blocker (what would serve it, and whether that needs spend, a physical sample or
    further engineering).

`register(db, ...)` files the result as an `assets.gallery_frames` audit row per listing so the
listing pipeline and the Command Center can read it (`last(db, slug)`). Nothing here uploads,
publishes or certifies: the listing-set certificate is still issued only by
`publish.listing_set.certify_disclosed` on exported bytes.
"""
from __future__ import annotations

ACTION = "assets.gallery_frames"

# What the disclosed renderer's views serve (visual.disclosed_render.VIEWS).
_DISCLOSED_JOBS = ("DESIRE", "SCALE", "DETAIL")
# The vessel ANGLE view (disclosed_render view "angle", verified by render_verification at
# the same camera elevation). Bumped when the view or its verification changes.
ANGLE_METHOD = "disclosed-angle/1"


def _angle_frame(primary, store) -> tuple[dict | None, str]:
    """The disclosed ANGLE frame for a vessel, verified on its bytes, or why there is none."""
    from . import disclosed_render as DR
    from . import render_verification as RV

    try:
        fr = DR.render(primary, "angle")
    except DR.RenderRefused as exc:
        return None, str(exc)
    verdict = RV.verify(fr.png, cir=primary, view="angle")
    stored = store.put(f"{primary.slug}/{primary.version}/disclosed-angle.png", fr.png,
                       "image/png")
    return ({"job": "ANGLE", "view": "angle", "sha256": stored.sha256,
             "verification": verdict["status"],
             "failed": list(verdict.get("failed") or []),
             "unknown": list(verdict.get("unknown") or []),
             "camera_deg": fr.manifest["layout"].get("alpha_deg"),
             "disclosure": fr.manifest["disclosure"],
             "renderer_version": fr.manifest["renderer_version"]}, "")


def _listing_parts(slug: str):
    from ..products import launch0

    cand = launch0.candidate(slug)
    cirs = [launch0.cir_for(v.build) for v in cand.variants]
    if not cirs:
        raise ValueError(f"{slug}: no variants")
    identity = launch0.listing_identity(cirs[0].slug) or launch0.listing_identity(slug)
    category = identity.etsy_category if identity else ""
    return cand, cirs, category


def assemble(slug: str, *, store=None) -> dict:
    """The imagery set for one Launch-0 listing and its job ledger. Deterministic, local."""
    from ..core.artifacts import ArtifactStore
    from ..publish import disclosed_listing as DL
    from ..publish import eligibility as el
    from . import gallery_frames as G

    store = store or ArtifactStore()
    cand, cirs, category = _listing_parts(slug)
    primary, siblings = cirs[0], cirs[1:]
    colours = len(primary.colors or {})
    applicable = el.gallery_jobs_for(category, sizes=len(cirs), colours=colours)

    disclosed = {}
    for cir in cirs:
        rec = DL.build(cir, store=store)
        disclosed[cir.slug] = {
            "version": cir.version, "usable": bool(rec.get("usable_as_listing_asset")),
            "blocked": rec.get("launch_blocked") or [],
            "frames": [{"view": f["view"], "job": (f.get("disclosed_render") or {}).get("job"),
                        "sha256": f["image"]["sha256"],
                        "structural_truth": f["structural_truth"]["status"],
                        "alt_text": f.get("alt_text")} for f in rec.get("frames") or []]}

    frames, refused = [], {}
    for job in G.applicable_jobs(primary, siblings=siblings):
        try:
            fr = G.render(primary, job, siblings=siblings)
        except G.FrameRefused as exc:
            refused[job] = str(exc)
            continue
        verdict = G.verify(fr.png, primary, fr.manifest, siblings=siblings)
        stored = store.put(f"{primary.slug}/{primary.version}/gallery-{job.lower()}.png",
                           fr.png, "image/png")
        frames.append({"job": job, "sha256": stored.sha256, "verification": verdict["status"],
                       "failed": verdict["failed"], "manifest": fr.manifest,
                       "disclosure": fr.manifest["disclosure"]})

    angle_frames = []
    if "ANGLE" in applicable:
        af, why = _angle_frame(primary, store)
        if af is None:
            refused["ANGLE"] = why
        else:
            angle_frames.append(af)
            if af["verification"] != "PASS":
                refused["ANGLE"] = (f"the angle view did not verify on its bytes: "
                                    f"failed {af['failed']}, unknown {af['unknown']}")[:300]

    covered: dict[str, str] = {}
    hero = disclosed[primary.slug]
    if hero["usable"]:
        for f in hero["frames"]:
            if f["job"] in _DISCLOSED_JOBS and f["structural_truth"] == "PASS":
                covered[f["job"]] = f"disclosed render {primary.slug} {f['view']} {f['sha256'][:12]}"
    for f in frames:
        if f["verification"] == "PASS":
            covered[f["job"]] = f"gallery frame {f['job'].lower()} {f['sha256'][:12]}"
    for f in angle_frames:
        if f["verification"] == "PASS":
            covered["ANGLE"] = f"disclosed render {primary.slug} angle {f['sha256'][:12]}"

    # A verified frame for a job K1 does not list for this category is kept as a supporting
    # frame, never counted as coverage.
    supporting = {j: v for j, v in covered.items() if j not in applicable}
    covered = {j: v for j, v in covered.items() if j in applicable}
    missing = {}
    for job in sorted(set(applicable) - set(covered)):
        if job in refused:
            missing[job] = f"refused: {refused[job]}"
        elif job in G.NOT_DRAWABLE:
            missing[job] = G.NOT_DRAWABLE[job]
        elif job in _DISCLOSED_JOBS:
            missing[job] = "disclosed render not usable: " + "; ".join(hero["blocked"])[:400]
        else:
            missing[job] = "no truthful producer for this job yet"
    return {"slug": slug, "title": getattr(cand, "title", slug), "category": category,
            "variants": [c.slug for c in cirs], "version": primary.version,
            "applicable_jobs": sorted(applicable), "covered": covered, "missing": missing,
            "supporting": supporting,
            "disclosed": disclosed, "gallery_frames": frames, "angle_frames": angle_frames,
            "hero_ready": "DESIRE" in covered,
            "complete": not missing,
            "paid_or_physical_only": sorted(j for j in missing if j in ("LIFESTYLE", "FIT")),
            "method": {"disclosed_render": DL.ACTION, "gallery_frames": G.VERSION,
                       "angle_view": ANGLE_METHOD}}


def assemble_all(*, store=None) -> list[dict]:
    from ..products import launch0

    return [assemble(s, store=store) for s in launch0.LAUNCH0_SLUGS]


def _fingerprints(slug: str) -> dict:
    _cand, cirs, _cat = _listing_parts(slug)
    return {c.slug: c.fingerprint for c in cirs}


def refresh(db, *, store=None) -> dict:
    """Assemble and register every Launch-0 listing whose registered record is stale.

    Stale means: none on file, a different gallery-frame method, or a variant whose certified
    CIR fingerprint changed. Never raises for one listing: a failure is reported by slug."""
    from ..products import launch0
    from . import gallery_frames as G

    out = {}
    for slug in launch0.LAUNCH0_SLUGS:
        try:
            fps = _fingerprints(slug)
            prev = last(db, slug)
            if (prev and prev.get("fingerprints") == fps
                    and (prev.get("method") or {}).get("gallery_frames") == G.VERSION
                    and (prev.get("method") or {}).get("angle_view") == ANGLE_METHOD):
                out[slug] = {"refreshed": False, "covered": sorted(prev.get("covered") or []),
                             "missing": sorted(prev.get("missing") or [])}
                continue
            rec = assemble(slug, store=store)
            rec["fingerprints"] = fps
            register(db, rec)
            out[slug] = {"refreshed": True, "covered": sorted(rec["covered"]),
                         "missing": sorted(rec["missing"])}
        except Exception as exc:  # noqa: BLE001 - one listing never stops the others
            out[slug] = {"refreshed": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    return out


def register(db, rec: dict) -> None:
    """File one listing's imagery set where the listing pipeline reads it."""
    from ..core.models import AuditLog

    slim = dict(rec)
    slim["gallery_frames"] = [{k: v for k, v in f.items() if k != "manifest"} |
                              {"facts": f["manifest"]["facts"]} for f in rec["gallery_frames"]]
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=ACTION,
                       artifact=f"{rec['slug']}@{rec['version']}", detail=slim))


def last(db, slug: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.action == ACTION,
            AuditLog.artifact.startswith(f"{slug}@", autoescape=True))
            .order_by(desc(AuditLog.id)).limit(1))
        return dict(row.detail or {}) if row is not None else None


# --------------------------------------------------------------------------- certification
#
# F-030 / F-254: the verified gallery and angle frames enter the listing-set certificate
# beside the disclosed hero/scale/detail set, as frames of kind SUPPLEMENT_KIND. Nothing is
# taken from the registered record on trust: every frame is re-rendered from the certified
# CIR, its bytes must be exactly the stored ones, and it is re-verified on those bytes by the
# independent verifier (`gallery_frames.verify` / `render_verification.verify`) here, at
# certification, and again at upload (`runtime.etsy_ops.certified_images`).

SUPPLEMENT_KIND = "disclosed_gallery_frame"
# The order the further jobs take after hero, scale and detail.
# CONTENTS (W4-VISUAL2) is last so that adding it moved no frame already certified.
SUPPLEMENT_ORDER = ("ANGLE", "CONSTRUCTION", "COLOUR_CONTEXT", "SIZING", "MATERIALS",
                    "CONTENTS")
_SUPPLEMENT_TEXT = {
    "ANGLE": "the finished piece seen from the side at a raised angle",
    "CONSTRUCTION": "how it is built: the stitch count of every round or row, in working order",
    "COLOUR_CONTEXT": "each yarn colour's share of the finished piece, counted from the pattern",
    "SIZING": "every size sold, drawn to one scale with its finished measurements",
    "MATERIALS": "the yarn colours, yarn weight, hook size and gauge the pattern calls for",
    "CONTENTS": "the first pages of the PDF pattern you download, shown at reduced size",
}


def supplement_purpose(job: str) -> str:
    from ..publish import eligibility as el

    return el.ENGINEERING_EVIDENCE if job == "ANGLE" else el.CUSTOMER_INFORMATION


def supplement_alt_text(job: str, title: str) -> str:
    """The alt text a supplement frame is certified with: the disclosure first (as every
    disclosed render's is), then what it shows."""
    from ..publish.disclosed_listing import ALT_TEXT_MAX, DISCLOSURE

    if job == "CONTENTS":
        # A preview of the document, not a render of the design: the preview label leads.
        from .contents_frame import alt_text

        return alt_text(title)
    return f"{DISCLOSURE}. {title}: {_SUPPLEMENT_TEXT[job]}."[:ALT_TEXT_MAX]


def supplement_medium(job: str) -> str:
    """What the frame is made of: CONTENTS is pages of the certified PDF, the rest are
    deterministic drawings of the certified CIR."""
    from ..gates.asset_truth import AssetClass

    return (AssetClass.PATTERN_PREVIEW if job == "CONTENTS"
            else AssetClass.DIGITAL_TWIN_RENDER).value


def supplement_label(job: str) -> str:
    from ..publish import eligibility as el
    from ..publish.disclosed_listing import DISCLOSURE

    return el.PREVIEW_LABEL if job == "CONTENTS" else DISCLOSURE


def expected_alt_text(slug: str, job: str) -> str | None:
    """The alt text a supplement frame of `slug` doing `job` is certified with, or None."""
    found = _primary_for(slug)
    if found is None or job not in _SUPPLEMENT_TEXT:
        return None
    return supplement_alt_text(job, found[1])


def _category_of(slug: str) -> str:
    """The product's catalogue category, from where the release chain reads it."""
    try:
        from ..runtime.release import _product_record

        return str((_product_record(slug, {}) or {}).get("category") or "")
    except Exception:  # noqa: BLE001 - an unknown record is an unknown category
        return ""


def _primary_for(slug: str):
    """(listing slug, title, primary CIR, sibling CIRs, category) for a release slug that is
    a variant of a Launch-0 listing (siblings without SIZING), or a single-variant catalogue product with a
    render authority (`render_verification.authoritative_cir`); else None."""
    from ..products import launch0

    for listing in launch0.LAUNCH0_SLUGS:
        cand, cirs, cat = _listing_parts(listing)
        if cirs[0].slug == slug:
            return listing, getattr(cand, "title", listing), cirs[0], cirs[1:], cat
        for c in cirs[1:]:
            if c.slug == slug:
                # A sibling variant released under its own slug gets the frames of its own
                # CIR; SIZING (every size together) stays with the primary's listing.
                return listing, getattr(cand, "title", listing), c, [], cat
    from .render_verification import authoritative_cir

    cir = authoritative_cir(slug)
    if cir is None:
        return None
    return slug, cir.title or slug, cir, [], _category_of(slug)


def _check_contents(slug: str, primary, data: bytes, *, db, store) -> dict:
    """CONTENTS: the bytes must be the preview the release's certified PDF draws today, and
    `contents_frame.verify` must pass them against that PDF and the certified CIR."""
    import hashlib

    from . import contents_frame as CF

    try:
        pdfs = CF.released_pdf(db, primary.slug, primary.version, store=store)
        sha, pdf = pdfs[CF.TERMINOLOGY]
        fr = CF.render(pdf, slug=primary.slug, version=primary.version,
                       title=primary.title or primary.slug, editions=list(pdfs))
    except Exception as exc:  # noqa: BLE001 - no certified PDF is an unverifiable frame
        return {"status": "FAIL", "why": f"CONTENTS refused: {exc}"[:300]}
    if fr.manifest["image_sha256"] != hashlib.sha256(data).hexdigest():
        return {"status": "FAIL", "why": "bytes are not the preview of the certified PDF"}
    v = CF.verify(data, pdf, primary, fr.manifest, certified_sha256=sha, editions=list(pdfs))
    return {"status": v["status"], "why": "" if v["status"] == "PASS" else
            f"contents_frame.verify failed {v.get('failed')} unknown {v.get('unknown')}"[:300],
            "pdf_sha256": sha}


def check_supplement(slug: str, version: str, job: str, data: bytes, *, db=None,
                     store=None) -> dict:
    """Re-verify one supplement frame on its exact bytes against the certified CIR.

    PASS only when the release slug is a Launch-0 listing's primary variant at `version`,
    the bytes are exactly what the producer draws from the certified CIR today, and the
    independent verifier passes them. Anything else is FAIL with the reason; never assumed."""
    import hashlib

    from . import gallery_frames as G

    found = _primary_for(slug)
    if found is None:
        return {"status": "FAIL", "why": f"{slug} is not the primary variant of a Launch-0 listing"}
    _listing, _title, primary, siblings, _cat = found
    if primary.version != version:
        return {"status": "FAIL", "why": f"{slug}: certified CIR is {primary.version}, not {version}"}
    sha = hashlib.sha256(data).hexdigest()
    if job == "CONTENTS":
        return _check_contents(slug, primary, data, db=db, store=store)
    if job == "ANGLE":
        from . import disclosed_render as DR
        from . import render_verification as RV

        try:
            fr = DR.render(primary, "angle")
        except DR.RenderRefused as exc:
            return {"status": "FAIL", "why": f"angle view refused: {exc}"[:300]}
        if hashlib.sha256(fr.png).hexdigest() != sha:
            return {"status": "FAIL", "why": "bytes are not the angle view of the certified CIR"}
        v = RV.verify(data, cir=primary, view="angle")
        return {"status": v["status"], "why": "" if v["status"] == "PASS" else
                f"render_verification failed {v.get('failed')} unknown {v.get('unknown')}"[:300]}
    if job not in G.JOBS:
        return {"status": "FAIL", "why": f"{job!r} has no deterministic producer"}
    try:
        fr = G.render(primary, job, siblings=siblings)
    except G.FrameRefused as exc:
        return {"status": "FAIL", "why": f"refused: {exc}"[:300]}
    if fr.manifest["image_sha256"] != sha:
        return {"status": "FAIL", "why": "bytes are not the frame the certified CIR draws"}
    v = G.verify(data, primary, fr.manifest, siblings=siblings)
    return {"status": v["status"], "why": "" if v["status"] == "PASS" else
            f"gallery_frames.verify failed {v.get('failed')}"[:300]}


def supplements_for_certificate(slug: str, version: str, *, start: int,
                                exclude_jobs=(), store=None,
                                release_fingerprint: str | None = None, db=None) -> dict:
    """The verified supplement frames a disclosed set for `slug@version` may be certified with.

    Returns {"frames": [{position, job, sha256, purpose, alt_text, png, represented_variant}],
    "refused": {job: why}, "listing": slug-or-None}. Only jobs applicable to the listing's
    category (`eligibility.gallery_jobs_for`) and not already done by the disclosed set are
    offered; a job whose frame does not verify on its bytes is refused, never padded in.
    Deterministic and local: no model, provider or network call."""
    from ..core.artifacts import ArtifactStore
    from ..publish import eligibility as el

    found = _primary_for(slug)
    if found is None:
        return {"frames": [], "refused": {}, "listing": None}
    listing, title, primary, siblings, category = found
    if primary.version != version:
        return {"frames": [], "refused": {"*": f"certified CIR is {primary.version}"},
                "listing": listing}
    if release_fingerprint is not None and release_fingerprint != primary.fingerprint:
        return {"frames": [], "refused": {"*": "the release's CIR is not the certified CIR the "
                                               "frames are drawn from"}, "listing": listing}
    applicable = el.gallery_jobs_for(category, sizes=1 + len(siblings),
                                     colours=len(primary.colors or {}))
    store = store if store is not None else ArtifactStore()
    out, refused = [], {}
    position = start
    for job in SUPPLEMENT_ORDER:
        if job not in applicable or job in set(exclude_jobs):
            continue
        try:
            if job == "ANGLE":
                from . import disclosed_render as DR

                png = DR.render(primary, "angle").png
            elif job == "CONTENTS":
                from . import contents_frame as CF

                pdfs = CF.released_pdf(db, primary.slug, primary.version, store=store)
                png = CF.render(pdfs[CF.TERMINOLOGY][1], slug=primary.slug,
                                version=primary.version, title=primary.title or primary.slug,
                                editions=list(pdfs)).png
            else:
                from . import gallery_frames as G

                if job not in G.applicable_jobs(primary, siblings=siblings):
                    refused[job] = "the CIR does not carry what this job draws"
                    continue
                png = G.render(primary, job, siblings=siblings).png
        except Exception as exc:  # noqa: BLE001 - a refused producer is a refused job
            refused[job] = f"{type(exc).__name__}: {exc}"[:300]
            continue
        verdict = check_supplement(slug, version, job, png, db=db, store=store)
        if verdict["status"] != "PASS":
            refused[job] = verdict["why"] or verdict["status"]
            continue
        stored = store.put(f"{primary.slug}/{primary.version}/certified-{job.lower()}.png",
                           png, "image/png")
        out.append({"position": position, "job": job, "sha256": stored.sha256,
                    "purpose": supplement_purpose(job),
                    "alt_text": supplement_alt_text(job, title), "png": png,
                    "medium": supplement_medium(job), "honesty_label": supplement_label(job),
                    "represented_variant": primary.variant_key})
        position += 1
    return {"frames": out, "refused": refused, "listing": listing}
