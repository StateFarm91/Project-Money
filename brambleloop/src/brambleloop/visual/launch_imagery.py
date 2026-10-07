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
