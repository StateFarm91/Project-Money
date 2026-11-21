"""The listing set a publish would export, judged in the running system.

Requirements 58, 60, 65, 66, 70, 80, 172, 173 and 297 each have a tested library. What this
module adds is the part a proof-chain audit found missing: something in the release chain
that reads the real rows -- the frames `assets.build` persisted, the listing copy, the
certified geometry, the provenance graph, the incident flags, the launch window -- hands
them to those libraries, and returns one verdict the publish and marketing handlers act on.

Nothing here renders a frame, calls a model or touches the network. Every gate reading comes
from evidence already on file, and a gate with no evidence reads `not_run`, which blocks:
a listing exported because a check was never wired up is the failure all nine requirements
were reopened for.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime, timezone

from ..gates.asset_truth import AssetClass
from . import dimensions as dims
from . import eligibility as el
from . import listing_set as ls
from . import mobile

# What each frame the chain builds is *for* (#65): one job, and the purpose that does it.
# Read from the role `publish.listing_assets` gives the frame. A role not in this table has
# no commercial job, which is filler by #80's definition and refused rather than reordered.
ROLE_JOBS: dict[str, tuple[str, str]] = {
    "hero": (el.DESIRE, el.CONVERSION_CREATIVE),
    "whats_included": (el.CONTENTS, el.CUSTOMER_INFORMATION),
    "size": (el.SCALE, el.CUSTOMER_INFORMATION),
    "materials": (el.MATERIALS, el.CUSTOMER_INFORMATION),
    "pattern_preview": (el.PATTERN_PREVIEW, el.CUSTOMER_INFORMATION),
    "chart": (el.DETAIL, el.ENGINEERING_EVIDENCE),
    "collection": (el.CROSS_SELL, el.CUSTOMER_INFORMATION),
    # VISGATE E-A: a photograph from `physical_upgrade` arrives as role "proof" and was
    # removed as filler because this table did not know the role. PROOF is done only by
    # PHYSICAL_PROOF, so a generated or drawn frame claiming it is refused when its Candidate
    # is built. LIFESTYLE is a CONVERSION_CREATIVE job that a camera photo can do. A generated
    # frame can also be classified for it, but `may_export` still refuses it (F-852).
    # Both roles are photographic for the #61 review (`frame_role.classify`), so they keep
    # every realism check. Nothing is lowered.
    "proof": (el.PROOF, el.PHYSICAL_PROOF),
    "lifestyle": (el.LIFESTYLE, el.CONVERSION_CREATIVE),
}

# The component the finished-size numbers describe. One per product today: every listing
# quotes the whole piece.
FINISHED = "finished piece"

_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:cm\s*)?[x×]\s*(\d+(?:\.\d+)?)\s*cm")


def _asset_id(slug: str, position: int) -> str:
    return f"{slug}-frame-{position}"


# W-VISNEXT: frames written by `visual.gallery_persist` from autonomous image production.
GENERATED_SOURCE = "visual.image_production"


# D-OWNER-FLUX-GALLERY: the jobs a generated-gallery frame does, by its role. Every one is
# CONVERSION_CREATIVE (the only purpose an AI_LIFESTYLE_CONCEPT can serve).
GENERATED_ROLE_JOBS: dict[str, tuple[str, str]] = {
    "hero": (el.DESIRE, el.CONVERSION_CREATIVE),
    "colour_context": (el.COLOUR_CONTEXT, el.CONVERSION_CREATIVE),
    "lifestyle": (el.LIFESTYLE, el.CONVERSION_CREATIVE),
    "angle": (el.ANGLE, el.CONVERSION_CREATIVE),
    "detail": (el.DETAIL, el.CONVERSION_CREATIVE),
    "size": (el.SCALE, el.CONVERSION_CREATIVE),
}
GENERATED_GALLERY = "generated_gallery"             # the listing-set kind of this route
GENERATED_RENDER_KIND = "generated_render"          # a certified frame's kind in it
SELECTED_ACTION = "images.generated_gallery_selected"


def is_gallery_route_frame(f) -> bool:
    return is_generated_frame(f) and (getattr(f, "claims", None) or {}).get(
        "route") == el.GALLERY_ROUTE


def _job_of_frame(f):
    if is_gallery_route_frame(f):
        return GENERATED_ROLE_JOBS.get(f.role)
    return ROLE_JOBS.get(f.role)


def is_generated_frame(f) -> bool:
    """A ListingAsset frame that image production generated (never a photograph)."""
    return (getattr(f, "claims", None) or {}).get("source") == GENERATED_SOURCE


def generated_frame_verdict(db, slug: str, version: str, f) -> dict:
    """The four promotion gates for one generated ListingAsset frame, judged per its role.

    A generated frame was not made by `assets.build`, so it is not judged on that build's
    readings (which would say "never ran" whatever the frame is). Its gates come from its own
    record: DATA_TRUTH from the stored technical verdict of its candidate (binding, Product
    Truth, identity, outfit), LAYOUT_QA from its measured quality, COMMERCIAL_QA from its role,
    realism and anatomy checks, POLICY_PROVENANCE from its provenance row (the file on record
    must be the file written). `eligibility.may_export` then decides, and its F-852 rule refuses
    generated product imagery in every role. Nothing here relaxes that. A frame written by the
    generated-gallery route (D-OWNER-FLUX-GALLERY) is judged by that route's exception
    (`eligibility.gallery_exception`), on the evidence its own candidate record carries."""
    job = _job_of_frame(f)
    base = {"asset_id": _asset_id(slug, f.position), "position": f.position, "role": f.role,
            "sha256": f.sha256, "generated": True}
    from ..visual.experiment import LABEL, is_experiment_image

    if is_experiment_image(db, f.sha256):
        why = f"{LABEL}: a controlled-experiment image is never exported"
        return {**base, "may_export": False, "blockers": [why], "why": why,
                "job": (job or ("",))[0], "gates": {}}
    if job is None:
        why = f"role {f.role!r} has no commercial job; a frame with no job is filler (#65)"
        return {**base, "may_export": False, "blockers": [why], "why": why, "job": "",
                "gates": {}}
    try:
        c = el.Candidate(asset_id=_asset_id(slug, f.position), medium=AssetClass(f.asset_class),
                         purpose=job[1], job=job[0], position=f.position)
    except (el.EligibilityRefused, ValueError) as e:
        why = str(e)[:300]
        return {**base, "may_export": False, "blockers": [why], "why": why, "job": job[0],
                "gates": {}}
    checks: dict = {}
    cand: dict = {}
    cand_run_key = ""
    cid = (f.claims or {}).get("candidate_id")
    if cid:
        from ..visual.image_records import ImageCandidate, ensure_tables

        ensure_tables(db)
        with db.session() as s:
            row = s.get(ImageCandidate, int(cid))
            if row is not None and row.sha256 == f.sha256:
                checks = dict(row.checks or {})
                checks["_technical"] = {"status": row.technical_status}
                cand = {"sha256": row.sha256, "role": row.role, "model": row.model,
                        "references": list(row.references or []),
                        "prompt_version": row.prompt_version,
                        "provenance_kind": row.provenance_kind,
                        "laura_present": bool(row.laura_present),
                        "identity_evidence": checks.get("_identity_evidence") or {},
                        "route": (checks.get("_route") or {}).get("route") or ""}
                cand_run_key = row.run_key or ""
                if is_gallery_route_frame(f) and cand["route"] != el.GALLERY_ROUTE:
                    # written as a gallery frame but not generated and judged under the route
                    cand["route"] = "mismatch"

    def outcome(*names):
        st = [str((checks.get(n) or {}).get("status") or "UNKNOWN") for n in names]
        st = [x for x in st if x != "NOT_APPLICABLE"]
        if "FAIL" in st:
            return el.FAILED
        return el.PASSED if st and all(x == "PASS" for x in st) else el.NOT_RUN

    no_record = "no verification record for these bytes" if not checks else ""
    gates = [el.GateResult(el.DATA_TRUTH, outcome("_technical"),
                           no_record or "the candidate's stored technical verdict"),
             el.GateResult(el.LAYOUT_QA, outcome("quality"), no_record or "measured quality"),
             el.GateResult(el.COMMERCIAL_QA, outcome("role", "realism", "anatomy"),
                           no_record or "role, realism and anatomy readings")]
    sha = _provenance_sha(db, slug, version, f.id)
    if sha is None:
        gates.append(el.GateResult(el.POLICY_PROVENANCE, el.FAILED,
                                   "no provenance row: source and rights cannot be shown"))
    elif sha != f.sha256:
        gates.append(el.GateResult(el.POLICY_PROVENANCE, el.FAILED,
                                   f"provenance records {sha[:12]}, the frame on file is "
                                   f"{str(f.sha256)[:12]}"))
    else:
        gates.append(el.GateResult(el.POLICY_PROVENANCE, el.PASSED,
                                   "provenance row (#36 ai_generated) matches the file"))
    evidence = None
    if cand:
        # D-W4-F852-AMEND: the verified-exception evidence, from the frame's own record only.
        from ..visual import candidate_gates as CG

        other = []
        if cand["laura_present"]:
            from ..visual import canonical
            from ..visual import laura_approval

            # IMAGE-BF: the registry, or the owner's step-up approval of these bytes for the
            # gallery run that made them (`visual.laura_approval`); nothing else.
            status = laura_approval.publication_status(db, f.sha256 or "", cand_run_key)
            if status != canonical.PUBLICATION_APPROVED_STATUS:
                other.append(f"Laura publication gate: '{status}'")
        evidence = CG.exception_evidence(cand, {k: v for k, v in checks.items()
                                                if isinstance(v, dict)}, job[0],
                                         cand["laura_present"],
                                         other_publication_blockers=other)
    verdict = el.may_export(c, gates, truth_verdict=gates[0].outcome,
                            generated_evidence=evidence)
    return {**verdict, **base}


def _classify(reason: str) -> str:
    """Which of the four gates an `assets.build` blocking reason belongs to."""
    text = reason.upper()
    if "ASSET_" in text:
        return el.DATA_TRUTH
    if "IDENTITY" in text or "MODEL" in text:
        return el.POLICY_PROVENANCE
    return el.LAYOUT_QA


# ---- evidence on file --------------------------------------------------------------------

def _release(db, slug: str, version: str):
    from sqlalchemy import select

    from ..cir.model import CIR
    from ..core.models import PatternVersion, Product

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = (s.scalar(select(PatternVersion).where(PatternVersion.product_id == product.id,
                                                    PatternVersion.version == version))
              if product is not None else None)
        if pv is None or not pv.certified or not pv.cir_json:
            return None, ""
        return CIR.from_dict(pv.cir_json), pv.release_hash or ""


def _twin(db, cir):
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..quality.physical import calibration_from_db

    return build_twin(cir, compile_cir(cir), calibration=calibration_from_db(db, cir))


def geometry_of(twin, cir) -> dict:
    """What a listing certificate is invalidated by when it changes (#70)."""
    g = cir.gauge
    return {
        "width_cm": twin.width_cm, "height_cm": twin.height_cm,
        "circumference_cm": getattr(twin, "circumference_cm", None),
        "shape": getattr(twin, "shape", None),
        "gauge": ({"sts": g.stitches_per_10cm, "rows": g.rows_per_10cm,
                   "stitch": g.stitch_type, "hook_mm": g.hook_mm} if g else None),
    }


def _frames(db, slug: str, version: str) -> list:
    from sqlalchemy import select

    from ..core.models import ListingAsset

    with db.session() as s:
        rows = list(s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == slug, ListingAsset.version == version)
            .order_by(ListingAsset.position)))
        for r in rows:
            s.expunge(r)
    # I-A3-NONQUALIFYING-PHOTO (opus2): a photo frame the asset-truth review holds as not
    # qualifying is out of the listing set; it never blocks the set it was appended to.
    # Review U5 F8: only a PHOTO frame drops out this way (as photo_snapshot_current and
    # photo_certificate_current read it); any other frame carrying that reason still blocks.
    from .photo_asset_review import NOT_QUALIFYING, PHOTO_CLASS

    return [r for r in rows
            if not (r.asset_class == PHOTO_CLASS
                    and any(str(x).startswith(NOT_QUALIFYING)
                            for x in (r.blocked_reasons or [])))]


def _listing(db, slug: str, version: str):
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        if row is not None:
            s.expunge(row)
        return row


def _audit_detail(db, action: str, artifact: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == action,
                                              AuditLog.artifact == artifact)
                       .order_by(desc(AuditLog.id)).limit(1))
        return dict(row.detail or {}) if row is not None else None


def _provenance_sha(db, slug: str, version: str, row_id: int) -> str | None:
    from sqlalchemy import select

    from ..core.models import ArtefactProvenance
    from ..ops import artefacts as provenance

    with db.session() as s:
        row = s.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "visual_truth",
            ArtefactProvenance.artefact_key == provenance.visual_key(slug, version, row_id)))
        return (row.sha256 or "") if row is not None else None


def claims_of(listing, frames, search=None) -> dict:
    """Everything the listing set's certificate is bound to, besides geometry and policy.

    F-294: tags, the taxonomy node and the property payload are claims as much as the title
    is -- a tag edit, a recategorisation or a changed attribute changes what the listing says
    to a buyer and to Etsy's search -- so they are in the fingerprint and an edit to any of
    them invalidates the certificate through `listing_set.still_valid`. `search` is the
    listing's `ListingSearchProfile` row (or None when listing.seo has not written one, which
    fingerprints as "no taxonomy, no attributes" rather than being skipped).
    """
    return {
        "title": getattr(listing, "title", None),
        "description": getattr(listing, "description", None),
        "tags": list(getattr(listing, "tags", None) or []),
        "taxonomy_id": getattr(search, "taxonomy_id", None),
        "attributes": dict(getattr(search, "attributes", None) or {}),
        "properties": list(getattr(search, "properties", None) or []),
        "frames": {str(f.position): dict(f.claims or {}) for f in frames},
    }


def _search_profile(db, slug: str, version: str):
    from sqlalchemy import select

    from ..core.models import ListingSearchProfile

    with db.session() as s:
        row = s.scalar(select(ListingSearchProfile).where(
            ListingSearchProfile.product_slug == slug,
            ListingSearchProfile.version == version))
        if row is not None:
            s.expunge(row)
        return row


def search_fingerprint(*, title: str, description: str, tags: list, taxonomy_id,
                       properties: list) -> str:
    """What the search certificate was issued against (F-004, F-294)."""
    import hashlib
    import json

    blob = json.dumps({"title": title or "", "description": description or "",
                       "tags": list(tags or []), "taxonomy_id": taxonomy_id,
                       "properties": list(properties or [])}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def search_gate(db, *, slug: str, version: str, set_verdict: dict | None = None) -> dict:
    """The search verdict at publish: the drafted certificate, still current, plus the hero.

    F-004: category, attributes, copy, tags and description come from the certificate
    `listing.seo` wrote; the hero comes from the listing-set verdict computed in the same
    publish decision (frame 1 through all four gates). F-294: the certificate is bound to a
    fingerprint of the listing's title, description, tags, taxonomy and properties, so a
    listing edited after certification reads stale and refuses. No profile, an UNKNOWN
    category, or any failed or pending check refuses -- search certification is never
    inferred from the absence of a finding.
    """
    profile = _search_profile(db, slug, version)
    listing = _listing(db, slug, version)
    if profile is None:
        return {"ok": False, "verdict": "REFUSED", "reasons": [
            "search certificate (F-004): listing.seo has recorded no search profile for "
            f"{slug}@{version}"]}
    cert = profile.certificate if isinstance(profile.certificate, dict) else {}
    stored_checks = cert.get("checks")
    checks = dict(stored_checks) if isinstance(stored_checks, dict) else {}
    # A truncated/legacy row cannot certify by omitting the checks it never ran.
    # Hero is recomputed below; all other required evidence must be explicit.
    for key in ("category", "attributes", "copy", "tags", "description"):
        if not isinstance(checks.get(key), dict):
            checks[key] = {"ok": None, "why": "required search check missing or malformed"}
    reasons: list[str] = []
    if listing is None:
        reasons.append("search certificate (F-004): no drafted listing row to certify")
    else:
        now = search_fingerprint(title=listing.title, description=listing.description,
                                 tags=listing.tags, taxonomy_id=profile.taxonomy_id,
                                 properties=profile.properties)
        if now != profile.fingerprint:
            reasons.append("search certificate (F-294): the listing's title, description, "
                           "tags, taxonomy or properties changed after certification; "
                           "re-run listing.seo")
    if profile.category_status != "CHOSEN":
        reasons.append("search certificate (F-005): category UNKNOWN -- no stored Etsy "
                       "taxonomy snapshot names a node for this product, and none is assumed")
    frames = (set_verdict or {}).get("frames") or []
    hero = next((f for f in frames if f.get("position") == 1), None)
    hero_ok = bool(hero and hero.get("may_export"))
    checks["hero"] = {"ok": hero_ok,
                      "why": ("frame 1 passed all four gates" if hero_ok else
                              f"frame 1 is not export-ready: "
                              f"{(hero or {}).get('why') or 'no frame 1 on file'}")[:300]}
    for key, check in sorted(checks.items()):
        if not isinstance(check, dict):
            reasons.append(f"search certificate (F-004) {key}: malformed check")
            continue
        if check.get("ok") is not True and not (key == "category"
                                                and profile.category_status != "CHOSEN"):
            reasons.append(f"search certificate (F-004) {key}: "
                           f"{check.get('why') or 'not passed'}"[:300])
    return {"ok": not reasons, "verdict": "PASS" if not reasons else "REFUSED",
            "reasons": reasons, "checks": checks, "taxonomy_id": profile.taxonomy_id,
            "category_status": profile.category_status,
            "profile_verdict": profile.verdict}


# ---- F-250: renewal is never a visibility trick ----------------------------------------

RENEWAL_REASONS = ("expired", "material_change")


def renewal_decision(*, reason: str, listing_state: str = "",
                     material_change: str = "") -> dict:
    """Whether a listing may be renewed. Only on expiry or a material product change.

    A new or renewed listing gets a temporary visibility boost, which makes renewing on a
    schedule a recency trick (F-250, F-298). Nothing in this company renews listings today;
    this is the rule any renewal path must pass, so one cannot be added as a boost strategy.
    """
    r = (reason or "").strip().lower()
    if r == "expired" and listing_state == "expired":
        return {"allowed": True, "why": "the listing expired; renewal restores it"}
    if r == "material_change" and material_change.strip():
        return {"allowed": True, "why": f"material product change: {material_change[:200]}"}
    return {"allowed": False,
            "why": (f"renewal for {reason!r} refused: a listing is renewed only when it has "
                    f"expired or the product materially changed, never for recency (F-250)")}


# ---- #60: every displayed measurement, traced ---------------------------------------------

def dimension_audit(db, *, slug: str, version: str, twin, frames, listing) -> dict:
    """The numbers this listing shows, from the size card, the copy and the PDF cover."""
    from .listing_assets import size_frame_displays

    rounded = getattr(twin, "shape", None) in ("vessel", "disc", "tube", "cone", "dome")
    canonical: list[dims.Canonical] = []
    if twin.width_cm:
        canonical.append(dims.Canonical("finished.width",
                                        dims.DIAMETER if rounded else dims.WIDTH,
                                        FINISHED, float(twin.width_cm), blocked=dims.AT_GAUGE))
    if twin.height_cm:
        canonical.append(dims.Canonical("finished.length", dims.LENGTH, FINISHED,
                                        float(twin.height_cm), blocked=dims.AT_GAUGE))
    if getattr(twin, "circumference_cm", None):
        canonical.append(dims.Canonical("finished.circumference", dims.CIRCUMFERENCE,
                                        FINISHED, float(twin.circumference_cm),
                                        blocked=dims.AT_GAUGE))
    by_key = {c.key: c for c in canonical}

    displayed: list[dims.Displayed] = []
    references: list[dims.Reference] = []
    for f in frames:
        if f.role != "size":
            continue
        claims = f.claims or {}
        shown = size_frame_displays(width_cm=claims.get("width_cm"),
                                    height_cm=claims.get("height_cm"),
                                    shape=getattr(twin, "shape", None))
        for m in shown["measurements"]:
            displayed.append(dims.Displayed(where=f"frame {f.position} ({m['where']})",
                                            value_cm=m["value_cm"], traces_to=m["traces_to"]))
        for r in shown["references"]:
            references.append(dims.Reference(where=f"frame {f.position}", value_cm=r["value_cm"],
                                             names=r["names"], label=r["label"]))

    def _pairs(where: str, text: str | None) -> None:
        for a, b in _SIZE_RE.findall(text or "")[:2]:
            displayed.append(dims.Displayed(where=where, value_cm=float(a),
                                            traces_to="finished.width"))
            displayed.append(dims.Displayed(where=where, value_cm=float(b),
                                            traces_to="finished.length"))

    _pairs("listing description", getattr(listing, "description", None))
    built = _audit_detail(db, "assets.built", f"{slug}@{version}") or {}
    _pairs("PDF cover size label", built.get("size_label"))

    out = dims.audit(displayed, canonical, references=references)
    out["sources"] = sorted({d.traces_to for d in displayed if d.traces_to in by_key})
    out["where"] = sorted({d.where for d in displayed} | {r.where for r in references})
    return out


# ---- #66: the set as a shopper meets it --------------------------------------------------

def mobile_contexts(db, *, slug: str, version: str, frames, candidates, store_root=None,
                    store_renders: bool = False) -> dict:
    """Render the four contexts from the approved frame bytes and judge them.

    The renders are stored by the QA stage (`launch.plan`, `store_renders=True`). Every other
    caller -- store.publish above all, which must not write storage before its Shadow Mode
    refusal -- re-renders deterministically and accepts a context only if that exact render
    is already in the store. A render that was never stored is `not_rendered`, which blocks.
    """
    import hashlib
    from PIL import Image

    from ..core.artifacts import ArtifactMissing, ArtifactStore

    store = ArtifactStore(store_root)
    images: dict[int, Image.Image] = {}
    missing: list[str] = []
    for f in frames:
        if not f.sha256:
            missing.append(f"frame {f.position}: no hash recorded")
            continue
        try:
            images[f.position] = Image.open(io.BytesIO(store.get(f.sha256, db=db))).convert("RGB")
        except (ArtifactMissing, OSError) as e:
            missing.append(f"frame {f.position}: {str(e)[:120]}")

    renders: list[mobile.ContextRender] = []
    ink: dict[int, float] = {}
    if images and not missing:
        ink = {p: mobile.title_safe_ink(im) for p, im in images.items()}
        ordered = [images[p] for p in sorted(images)]

        def _sheet(frames_, px):
            sheet = Image.new("RGB", (px * len(frames_), px), (255, 255, 255))
            for i, im in enumerate(frames_):
                sheet.paste(im.resize((px, px)), (i * px, 0))
            return sheet

        def _put(name, image):
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            data = buf.getvalue()
            if store_renders:
                return store.put(f"{slug}/{version}/qa/{name}.png", data, "image/png").sha256
            digest = hashlib.sha256(data).hexdigest()
            return digest if store.exists(digest) else ""

        first = sorted(images)[:mobile.BEFORE_SCROLL]
        thumb = ordered[0].resize((mobile.MOBILE_THUMB_PX, mobile.MOBILE_THUMB_PX))
        phone = _sheet([images[p] for p in first], 390)
        specs = [
            (mobile.SEARCH_THUMBNAIL, _put("search_thumbnail", thumb), 1,
             mobile.MOBILE_THUMB_PX, ink[sorted(images)[0]]),
            (mobile.PHONE_GALLERY, _put("phone_gallery", phone),
             len(first), 390, max(ink[p] for p in first)),
            (mobile.FIRST_THREE, _put("first_three", phone),
             len(first), 390, max(ink[p] for p in first)),
            (mobile.FULL_GALLERY, _put("full_gallery", _sheet(ordered, 200)),
             len(ordered), 200, max(ink.values())),
        ]
        # A context whose render is not on file is left out, so `qa` reports it not_rendered.
        renders = [mobile.ContextRender(*spec) for spec in specs if spec[1]]
    if not candidates:
        return {"ok": False, "complete": False, "not_rendered": list(mobile.CONTEXTS),
                "why": "no frame carries a valid job, so the set cannot be judged",
                "missing_bytes": missing}
    out = mobile.qa(candidates, renders)
    out["missing_bytes"] = missing
    out["title_safe_ink_by_position"] = {str(p): round(v, 4) for p, v in ink.items()}
    return out


# ---- #58 / #65 / #80 / #70: the set ------------------------------------------------------

def listing_set(db, *, slug: str, version: str, store_root=None, issue: bool = True,
                cir=None, release_hash: str | None = None,
                store_renders: bool = False, persist_supplements: bool = True) -> dict:
    """Every frame through the four gates, the set through #65/#66/#80, and a certificate."""
    if cir is None:
        cir, release_hash = _release(db, slug, version)
    if cir is None:
        return {"slug": slug, "version": version, "blocks_release": True,
                "reasons": [f"{slug}@{version} has no certified release, so no listing set "
                            f"exists to judge: every gate reads not_run"],
                "frames": [], "certificate": None}
    twin = _twin(db, cir)
    frames = _frames(db, slug, version)
    listing = _listing(db, slug, version)
    reasons: list[str] = []
    # D-FB-7: when the listing's imagery is the disclosed render set (what parity judges via
    # `listing_asset.frames_for`), that set is what is certified and uploaded -- one listing
    # set, one certificate, one upload path.
    from . import listing_asset

    # D-OWNER-FLUX-GALLERY: a generated gallery selected for this release is the listing set,
    # judged and certified on its own path (one set, one certificate, one upload path).
    selection = generated_selection(db, slug, version)
    if selection is not None:
        return generated_listing_set(db, slug=slug, version=version, cir=cir, twin=twin,
                                     listing=listing, selection=selection, frames=frames,
                                     release_hash=release_hash, issue=issue,
                                     store_root=store_root, store_renders=store_renders)
    current_asset = listing_asset.last(db, slug=slug)
    if (current_asset and current_asset.get("kind") == ls.DISCLOSED_RENDER
            and current_asset.get("version") == version):
        return disclosed_listing_set(db, slug=slug, version=version, cir=cir, twin=twin,
                                     listing=listing, rec=current_asset, frames=frames,
                                     release_hash=release_hash, issue=issue,
                                     store_root=store_root,
                                     persist_supplements=persist_supplements)

    if not frames:
        return {"slug": slug, "version": version, "blocks_release": True,
                "reasons": ["no listing frames are on file for this release: all four gates "
                            "read not_run and there is nothing to export"],
                "frames": [], "certificate": None}

    built = _audit_detail(db, "assets.listing_images_built", f"{slug}@{version}")
    blocked_row = _audit_detail(db, "assets.listing_images_blocked", f"{slug}@{version}")

    candidates: list[el.Candidate] = []
    by_position: dict[int, el.Candidate] = {}
    invalid: dict[int, str] = {}
    for f in frames:
        job = ROLE_JOBS.get(f.role)
        if job is None:
            invalid[f.position] = (f"role {f.role!r} has no commercial job; a frame with no "
                                   f"buyer-relevant job is filler and is removed (#65, #80)")
            continue
        try:
            c = el.Candidate(asset_id=_asset_id(slug, f.position),
                             medium=AssetClass(f.asset_class), purpose=job[1], job=job[0],
                             position=f.position)
        except (el.EligibilityRefused, ValueError) as e:
            invalid[f.position] = str(e)[:300]
            continue
        candidates.append(c)
        by_position[f.position] = c

    frame_set = (el.check_set(candidates) if candidates else
                 {"ok": False, "problems": [{"kind": "no_valid_frames"}], "jobs_covered": []})
    colliding = {a for p in frame_set["problems"] if p.get("kind") == "duplicate_job"
                 for a in p.get("assets", [])}
    dim = dimension_audit(db, slug=slug, version=version, twin=twin, frames=frames,
                          listing=listing)
    mob = mobile_contexts(db, slug=slug, version=version, frames=frames,
                          candidates=candidates, store_root=store_root,
                          store_renders=store_renders)
    first_three_ok = bool(mob.get("first_three", {}).get("ok"))
    thumb_problem = (mob.get("contexts", {}).get(mobile.SEARCH_THUMBNAIL, {}) or {}).get("problem")

    per_frame: list[dict] = []
    for f in frames:
        if is_generated_frame(f):
            # W-VISNEXT: judged on its own verification record, per its role (F-852 holds).
            per_frame.append(generated_frame_verdict(db, slug, version, f))
            continue
        c = by_position.get(f.position)
        reasons_for = list(f.blocked_reasons or [])
        # DATA_TRUTH and LAYOUT_QA are the readings `assets.build` recorded (asset_truth and
        # layout_qa/check_frame_plan), not second implementations of them.
        gates: list[el.GateResult] = []
        ran_build = bool(built or blocked_row) and bool(f.sha256)
        by_gate: dict[str, list[str]] = {}
        for r in reasons_for:
            by_gate.setdefault(_classify(str(r)), []).append(str(r))
        if f.approved is False and not reasons_for:
            by_gate.setdefault(el.DATA_TRUTH, []).append(
                "the frame is not approved and no reason is on file (withdrawn or "
                "invalidated); it must be rebuilt and re-checked")
        for gate in (el.DATA_TRUTH, el.LAYOUT_QA):
            if not ran_build:
                gates.append(el.GateResult(gate, el.NOT_RUN,
                                           "assets.build left no reading for this frame"))
            elif by_gate.get(gate):
                gates.append(el.GateResult(gate, el.FAILED, "; ".join(by_gate[gate])[:400]))
            else:
                gates.append(el.GateResult(gate, el.PASSED))
        # Contradictory or contextless dimensions are a LAYOUT_QA failure by #58's own text,
        # and they land on the frame that shows them.
        dim_here = [p for p in dim["problems"]
                    if f"frame {f.position}" in str(p.get("where", ""))]
        if dim_here and gates[1].outcome == el.PASSED:
            gates[1] = el.GateResult(el.LAYOUT_QA, el.FAILED,
                                     "; ".join(p["kind"] for p in dim_here))
        # COMMERCIAL_QA: one defined job, not colliding, and holding up where shoppers look.
        if c is None:
            gates.append(el.GateResult(el.COMMERCIAL_QA, el.FAILED,
                                       invalid.get(f.position, "no job")))
        elif not mob.get("complete"):
            gates.append(el.GateResult(
                el.COMMERCIAL_QA, el.NOT_RUN,
                f"mobile contexts not rendered: "
                f"{mob.get('missing_bytes') or mob.get('not_rendered') or mob.get('why')}"))
        else:
            why = []
            if c.asset_id in colliding:
                why.append(f"another frame also does {c.job}")
            if f.position <= mobile.BEFORE_SCROLL and not first_three_ok:
                why.append(f"first three frames fail: {mob['first_three'].get('why')}")
            if f.position == 1 and thumb_problem:
                why.append(f"search thumbnail: {thumb_problem}")
            gates.append(el.GateResult(el.COMMERCIAL_QA, el.FAILED if why else el.PASSED,
                                       "; ".join(why)))
        # POLICY_PROVENANCE: made by our own renderer, recorded with lineage, and the file on
        # record is the file approved.
        sha = _provenance_sha(db, slug, version, f.id)
        if by_gate.get(el.POLICY_PROVENANCE):
            gates.append(el.GateResult(el.POLICY_PROVENANCE, el.FAILED,
                                       "; ".join(by_gate[el.POLICY_PROVENANCE])[:400]))
        elif sha is None:
            gates.append(el.GateResult(el.POLICY_PROVENANCE, el.FAILED,
                                       "no provenance row: source and rights cannot be shown"))
        elif sha and f.sha256 and sha != f.sha256:
            gates.append(el.GateResult(el.POLICY_PROVENANCE, el.FAILED,
                                       f"provenance records {sha[:12]}, the frame on file is "
                                       f"{f.sha256[:12]}"))
        else:
            gates.append(el.GateResult(el.POLICY_PROVENANCE, el.PASSED))

        truth = gates[0].outcome
        if c is not None:
            verdict = el.may_export(c, gates, truth_verdict=truth)
        else:
            verdict = {"asset_id": _asset_id(slug, f.position), "may_export": False,
                       "gates": {g.gate: g.to_dict() for g in gates},
                       "blockers": [invalid.get(f.position, "no job")],
                       "why": invalid.get(f.position, "no job"), "job": ""}
        verdict.update({"position": f.position, "role": f.role, "sha256": f.sha256})
        per_frame.append(verdict)

    from ..visual import gallery

    quality = gallery.minimum_quality([
        {"position": v["position"], "role": v["role"], "job": v.get("job") or "",
         "passed": v["may_export"], "why": v["why"]} for v in per_frame])

    if not frame_set["ok"]:
        reasons.append("frame set (#65): " + "; ".join(p.get("kind", "?")
                                                        for p in frame_set["problems"])[:300])
    if not dim["ok"]:
        reasons.append("dimensions (#60): " + "; ".join(
            f"{p['kind']} at {p.get('where')}" for p in dim["problems"])[:400])
    if not mob.get("ok"):
        reasons.append(f"mobile QA (#66): {mob.get('why')}")
    if not quality["ok"]:
        reasons.append(f"gallery minimum quality (#80): remove frames {quality['remove']}")
    refused = [v for v in per_frame if not v["may_export"]]
    if refused:
        reasons.append(f"four-gate export (#58): {len(refused)} frame(s) may not export -- "
                       + "; ".join(f"{v['position']}: {v['why'][:120]}" for v in refused[:3]))

    geometry = geometry_of(twin, cir)
    claims = claims_of(listing, frames, _search_profile(db, slug, version))
    cert = certificate_step(db, slug=slug, version=version, release_hash=release_hash or "",
                            frames=frames, per_frame=per_frame, geometry=geometry,
                            claims=claims, issue=issue and not reasons, listing=listing)
    if not cert.get("valid"):
        reasons.append(f"listing-set certificate (#70): {cert.get('why')}")

    return {
        "slug": slug, "version": version, "blocks_release": bool(reasons),
        "reasons": reasons,
        "frames": [{k: v.get(k) for k in ("position", "role", "job", "may_export", "why")}
                   | {"gates": {g: o["outcome"] for g, o in v["gates"].items()}}
                   for v in per_frame],
        "frame_set": {k: frame_set.get(k) for k in ("ok", "jobs_covered", "problems")},
        "gallery": quality, "dimensions": {k: dim[k] for k in ("ok", "problems", "sources",
                                                                "displayed", "references")},
        "mobile": {k: mob.get(k) for k in ("ok", "complete", "not_rendered", "why",
                                           "title_safe_ink_by_position", "missing_bytes")}
                  | {"render_refs": {n: r.get("render_ref")
                                     for n, r in (mob.get("contexts") or {}).items()}},
        "certificate": cert,
    }


def sample_photo_lead(db, *, slug: str, version: str, frames, cir) -> dict | None:
    """The leading unedited sample photograph, with its attestation and QA, or None.

    P0-GALLERY-ASSEMBLY (OPUS2-P0). W-PHYSFIX-PHOTO places the photograph of a passed full make
    of this release at position 1 and marks it `leads_gallery`; this re-reads every fact that
    made it eligible from its own records rather than trusting the mark, and measures the
    readings the photo-led certificate needs. Nothing here approves the frame: an unapproved
    or blocked frame reads `asset_truth: not ok`, and the certificate refuses.
    """
    import hashlib

    from ..core.artifacts import ArtifactStore
    from . import sample_photo

    lead = next((f for f in frames if getattr(f, "asset_class", "") == "PHYSICAL_PRODUCT_PHOTO"
                 and (getattr(f, "claims", None) or {}).get("leads_gallery") is True), None)
    if lead is None:
        return None
    claims = dict(lead.claims or {})
    # Review OPUS2C F2-1 (HIGH): ONE photo standard. Whether this photograph may lead is
    # `sample_photo.qualifying_photos` -- the owner's Command Center attestation bound to these
    # bytes, not a system-made file, bound by `first_customer.physical_binding` to a passed full
    # make of this release's content, rights, bytes on file. Nothing is rebuilt here: the lead
    # qualifies exactly when that rule lists this photo id with this frame's SHA-256.
    pid = claims.get("physical_photo_id")
    try:
        verdict = sample_photo.qualifying_photos(db, slug, version)
    except Exception as exc:  # noqa: BLE001 - an unreadable rule qualifies nothing
        verdict = {"qualifying": [], "rejected": [
            {"photo_id": pid, "why": f"qualifying_photos unreadable: {type(exc).__name__}"}]}
    match = next((q for q in verdict.get("qualifying") or []
                  if q.get("photo_id") == pid and q.get("sha256") == lead.sha256), None)
    rejected = next((q for q in verdict.get("rejected") or [] if q.get("photo_id") == pid),
                    None)
    ok = match is not None
    why = ("" if ok else (rejected or {}).get("why")
           or "the lead frame's photo is not a qualifying photograph of this release "
              "(photo id or SHA-256 not on file for it)")
    from .listing_set import PHOTO_ATTESTATION

    attestation = {**{k: ok for k in PHOTO_ATTESTATION},
                   "slug": slug if ok else None, "version": version if ok else None,
                   "rule": "publish.sample_photo.qualifying_photos",
                   "physical_test_id": (match or {}).get("physical_test_id"),
                   **({"why": why} if why else {})}
    qa: dict = {"asset_truth": {"ok": bool(lead.approved) and not (lead.blocked_reasons or [])}}
    try:
        data = ArtifactStore().get(lead.sha256, db=db)
        qa["bytes"] = {"ok": hashlib.sha256(data).hexdigest() == lead.sha256}
        from PIL import Image

        from ..commerce import thumbnail as thumb

        verdict = thumb.evaluate_thumbnail(Image.open(io.BytesIO(data)).convert("RGB"))
        qa["hero_thumbnail"] = {"ok": bool(verdict.ok), **verdict.to_dict()}
    except Exception as exc:  # noqa: BLE001 - unread bytes are a failed reading, never a pass
        qa["bytes"] = {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
    title = getattr(cir, "title", "") or slug
    return {"photo": {"asset_id": f"{slug}-sample-photo-{claims.get('physical_photo_id')}",
                      "sha256": lead.sha256,
                      "alt_text": (f"Photograph of a {title} sample crocheted from this "
                                   f"pattern, unedited")[:250],
                      "represented_variant": claims.get("represented_variant")
                                             or getattr(cir, "variant_key", None),
                      "attestation": attestation},
            "qa": qa, "position": lead.position}


def _disclosed_mobile(rec: dict, *, store_root=None) -> dict | None:
    """The disclosed render set's mobile-context QA (#66), with every stored render verified
    on file now; None if the export never ran it."""
    from ..core.artifacts import ArtifactStore

    mob = (rec.get("qa") or {}).get("mobile")
    if not mob:
        return None
    refs = {n: _bare_sha((r or {}).get("render_ref"))
            for n, r in (mob.get("contexts") or {}).items()}
    store = ArtifactStore(store_root)
    missing = sorted(n for n, r in refs.items() if not r or not store.exists(r))
    out = {k: mob.get(k) for k in ("ok", "complete", "not_rendered", "why",
                                   "title_safe_ink_by_position", "missing_bytes")}
    if missing:
        out.update(ok=False, complete=False,
                   not_rendered=sorted(set(out.get("not_rendered") or []) | set(missing)),
                   why=f"render(s) not on file: {missing}")
    return out | {"render_refs": refs}


def _bare_sha(ref):
    """disclosed_listing writes refs as 'sha256:<hex>'; the frames path and ArtifactStore
    address bytes by the bare hex digest. One form, so publish verifies either path."""
    ref = str(ref or "")
    return ref.split(":", 1)[1] if ref.startswith("sha256:") else (ref or None)


def disclosed_listing_set(db, *, slug: str, version: str, cir, twin, listing, rec: dict,
                          frames, release_hash: str | None, issue: bool,
                          store_root=None, persist_supplements: bool = True) -> dict:
    """The disclosed-render set through the listing-set certificate (#70, D-FB-7).

    Preconditions are `disclosed_listing.export_images`' refusals -- the disclosure in the
    pixels, every alt text and the listing copy, and structural truth PASS on the exact bytes
    -- and the set's own QA readings map onto the four promotion gates. The listing copy's
    dimensions are audited against the certified geometry exactly as for any other set.
    """
    from ..gates.platform_policy import policy_stamp
    from ..gates.policy import POLICY_VERSION
    from . import disclosed_listing

    reasons: list[str] = []
    if listing is None:
        reasons.append("no listing copy is drafted, so the copy disclosure cannot be shown")
    dim = dimension_audit(db, slug=slug, version=version, twin=twin, frames=[],
                          listing=listing)
    if not dim["ok"]:
        reasons.append("dimensions (#60): " + "; ".join(
            f"{p['kind']} at {p.get('where')}" for p in dim["problems"])[:400])
    if not rec.get("usable_as_listing_asset"):
        reasons.append("disclosed set QA: " + "; ".join(rec.get("launch_blocked") or [])[:400])
    images: list = []
    try:
        images = disclosed_listing.export_images(
            db, slug=slug, description=getattr(listing, "description", "") or "",
            store=store_root)
    except disclosed_listing.DisclosureMissing as e:
        reasons.append(f"disclosed export (D-FB-7): {str(e)[:400]}")
    supplements, supplement_qa, supplement_notes = (
        disclosed_supplements(rec, images, slug=slug, version=version, store_root=store_root,
                              release_fingerprint=getattr(cir, "fingerprint", "") or "",
                              db=db, persist=persist_supplements)
        if images else ([], None, {}))
    gate_results = ls.disclosed_gate_results(rec, exported=bool(images) and not any(
        r.startswith("disclosed export") for r in reasons), dimensions_ok=dim["ok"],
        supplement_qa=supplement_qa if supplements else None)

    # #66: the shopper contexts the export rendered must still be on file. A missing render
    # reads not_rendered, blocks the set and leaves COMMERCIAL_QA not_run (the frames path's
    # rule), so publish never ships a set whose context QA it cannot verify.
    mobile_qa = _disclosed_mobile(rec, store_root=store_root)
    if mobile_qa is not None and not mobile_qa["complete"]:
        gate_results = {**dict(gate_results), "COMMERCIAL_QA": "not_run"}
        reasons.append(f"mobile QA (#66): {len(mobile_qa['not_rendered'] or [])} context(s) "
                       f"not rendered or not on file: {mobile_qa['not_rendered']}")

    # W-VISNEXT: generated ListingAsset frames are judged per their role, not ignored. A
    # refused one is excluded from the certified set and reported. One that passed its gates
    # would need a mixed-set certificate, which the disclosed certificate is not: blocked.
    generated = [generated_frame_verdict(db, slug, version, f) for f in frames
                 if is_generated_frame(f) and not is_gallery_route_frame(f)]
    passing = [g for g in generated if g.get("may_export")]
    if passing:
        reasons.append(f"generated frame(s) {[g['position'] for g in passing]} passed their "
                       f"gates, but the disclosed-render certificate does not cover "
                       f"ListingAsset frames; a mixed set is not certified here")
    geometry = geometry_of(twin, cir)
    claims = claims_of(listing, [f for f in frames if not is_generated_frame(f)],
                       _search_profile(db, slug, version))
    rechecked = recheck(db, slug=slug, version=version, geometry=geometry, claims=claims,
                        policy_version=POLICY_VERSION)
    cert: dict
    # P0-GALLERY-ASSEMBLY (OPUS2-P0): an attested, approved sample photograph leads the set.
    lead = sample_photo_lead(db, slug=slug, version=version, frames=frames, cir=cir)
    try:
        common = dict(
            slug=slug, version=version, rec=rec, images=images, geometry=geometry,
            claims=claims, policy_version=POLICY_VERSION, platform_policy=policy_stamp(db),
            dimensions_ok=dim["ok"],
            # F-757 / PT-13: the configuration the certified release encodes is what the
            # listing sells; the set must have been rendered for it.
            listing_variant=cir.variant_key, supplements=supplements,
            supplement_qa=supplement_qa)
        certificate = None if reasons else (
            ls.certify_photo_led(photo=lead["photo"], photo_qa=lead["qa"], **common)
            if lead is not None else ls.certify_disclosed(**common))
    except ls.ListingSetRefused as e:
        certificate = None
        reasons.append(f"listing-set certificate (#70): {str(e)[:400]}")
    if certificate is None:
        cert = {"valid": False, "issued": False, "rechecked": rechecked,
                "why": "no disclosed-set certificate is issued while any precondition or gate "
                       "above fails"}
        if not any(r.startswith("listing-set certificate") for r in reasons):
            reasons.append(f"listing-set certificate (#70): {cert['why']}")
    else:
        cert = _record_certificate(db, certificate, release_hash=release_hash or "",
                                   issue=issue, rechecked=rechecked)
        if not cert.get("valid"):
            reasons.append(f"listing-set certificate (#70): {cert.get('why')}")
    return {
        "slug": slug, "version": version, "blocks_release": bool(reasons),
        "reasons": reasons, "kind": ls.DISCLOSED_RENDER,
        "frames": [{"position": f["position"], "role": f.get("role"), "job":
                    (f.get("disclosed_render") or {}).get("job"),
                    "may_export": not reasons, "why": "; ".join(reasons)[:200]}
                   | {"gates": dict(gate_results)}
                   for f in sorted(rec.get("frames") or [], key=lambda f: f["position"])],
        "frame_set": {"ok": bool(((rec.get("qa") or {}).get("frame_set") or {}).get("ok"))},
        "supplements": {"certified": [f.job for f in supplements],
                        "refused": supplement_notes},
        "dimensions": {k: dim[k] for k in ("ok", "problems", "sources", "displayed",
                                           "references")},
        # #66: the disclosed export rendered and stored the four shopper contexts
        # (disclosed_listing's QA); report them in the same shape as the frames path, so the
        # QA stage's `listing.mobile_qa` record and store.publish read one contract.
        "mobile": mobile_qa,
        "certificate": cert,
        "generated_frames": [{k: g.get(k) for k in ("position", "role", "job", "may_export",
                                                    "why")} for g in generated],
        "generated_excluded": [g["position"] for g in generated if not g.get("may_export")],
    }


def disclosed_supplements(rec: dict, images: list, *, slug: str, version: str,
                          store_root=None, release_fingerprint: str | None = None,
                          db=None, persist: bool = True) -> tuple[list, dict | None, dict]:
    """The verified gallery frames (F-030/F-254) a disclosed set is certified with, their
    QA readings over the whole ordered set, and why any applicable job was left out.

    A frame is offered only after `visual.launch_imagery.check_supplement` passes it on its
    bytes and `layout_qa.inspect` passes it at listing scale (type expected); a frame that
    fails either is left out with the reason, never certified. The readings returned feed
    `listing_set.disclosed_gate_results` beside the set's own -- they add to it, never replace it.
    """
    import io as _io

    from PIL import Image

    from ..core.artifacts import ArtifactStore
    from ..gates.asset_truth import AssetClass
    from ..visual import launch_imagery as LI
    from . import eligibility as el
    from . import layout_qa

    ordered = sorted(rec.get("frames") or [], key=lambda f: int(f.get("position") or 0))
    taken = {(f.get("disclosed_render") or {}).get("job") for f in ordered}
    try:
        offer = LI.supplements_for_certificate(slug, version, start=len(images) + 1,
                                               exclude_jobs=taken,
                                               store=ArtifactStore(store_root),
                                               release_fingerprint=release_fingerprint,
                                               db=db, persist=persist)
    except Exception as exc:  # noqa: BLE001 - no supplements is a coverage gap, not a block
        return [], None, {"*": f"{type(exc).__name__}: {exc}"[:300]}
    notes = dict(offer.get("refused") or {})
    base = [Image.open(_io.BytesIO(data)).convert("RGB") for _n, data, _a in images]

    class _F:
        def __init__(self, image, position):
            self.image, self.position = image, position

    found = LI._primary_for(slug)
    primary = found[2] if found else None
    kept, presented = [], []
    for f in offer.get("frames") or []:
        img = Image.open(_io.BytesIO(f["png"])).convert("RGB")
        report = layout_qa.inspect(img, position=f["position"], expect_text=True)
        if report.problems:
            notes[f["job"]] = "layout QA: " + "; ".join(report.problems)[:280]
            continue
        # W4-VISUALSEO: a supplement is exported into the phone gallery and the full gallery
        # like the disclosed set, so it is measured in those contexts and for its label in
        # its own pixels/alt text before it may be certified -- never assumed from its
        # producer. A frame that fails is left out with the reason (fail closed).
        shown = supplement_presentation(f, img, cir=primary)
        if not shown["ok"]:
            notes[f["job"]] = "presentation: " + "; ".join(shown["problems"])[:280]
            continue
        kept.append((f, img))
        presented.append(shown)
    supplements: list = []
    for i, (f, _img) in enumerate(kept):
        supplements.append(ls.CertifiedFrame(
            position=len(images) + 1 + i, asset_id=f"{slug}-gallery-{f['job'].lower()}",
            sha256=f["sha256"], job=f["job"], purpose=f["purpose"],
            medium=f.get("medium") or AssetClass.DIGITAL_TWIN_RENDER.value,
            honesty_label=f.get("honesty_label") or ls_disclosure(),
            kind=ls.DISCLOSED_SUPPLEMENT,
            alt_text=f["alt_text"], represented_variant=f["represented_variant"]))
    if not supplements:
        return [], None, notes
    layout = layout_qa.check_frames(
        [_F(im, i + 1) for i, im in enumerate(base + [im for _f, im in kept])],
        text_positions=tuple(range(1, len(base) + len(kept) + 1)))
    purpose = {"hero": el.CONVERSION_CREATIVE, "scale": el.CUSTOMER_INFORMATION,
               "detail": el.ENGINEERING_EVIDENCE}
    candidates = [el.Candidate(asset_id=f"{slug}:{f.get('view')}",
                               medium=AssetClass.DIGITAL_TWIN_RENDER,
                               purpose=purpose.get(f.get("view") or "", el.CUSTOMER_INFORMATION),
                               job=(f.get("disclosed_render") or {}).get("job") or "",
                               position=int(f["position"])) for f in ordered]
    candidates += [el.Candidate(asset_id=c.asset_id, medium=AssetClass(c.medium),
                                purpose=c.purpose, job=c.job, position=c.position)
                   for c in supplements]
    frame_set = el.check_set(candidates)
    qa = {"verified": [True] * len(supplements),
          "layout_qa": {"ok": not layout, "problems": layout},
          "frame_set": {"ok": frame_set["ok"], "problems": frame_set["problems"]},
          # W4-VISUALSEO: the gallery as exported (disclosed set + supplements), not the
          # disclosed set alone, in the contexts a supplement is seen in.
          "mobile": {"ok": all(p["ok"] for p in presented),
                     "full_gallery_frames": len(base) + len(kept),
                     "contexts": [mobile.PHONE_GALLERY, mobile.FULL_GALLERY],
                     "frames": {p["job"]: p["readings"] for p in presented}},
          "disclosure": {"ok": all(p["readings"]["label_in_image"] is True
                                   and p["readings"]["label_in_alt_text"] is True
                                   for p in presented)}}
    return supplements, qa, notes


# The contexts a supplement (position > mobile.BEFORE_SCROLL, never the search thumbnail) is
# seen in, and the size each is measured at: the swiped phone gallery and the full gallery.
SUPPLEMENT_CONTEXT_PX: dict[str, int] = {mobile.PHONE_GALLERY: 390, mobile.FULL_GALLERY: 2000}


def supplement_presentation(frame: dict, image, *, cir=None) -> dict:
    """Measure one supplement frame where a shopper sees it, and its honesty label.

    - no ink in the marketplace's title-safe band at each context's size
      (`mobile.title_safe_ink`, threshold 0 as for the disclosed set);
    - the label in the pixels: a drawn frame carries the render disclosure caption
      (`disclosed_listing.caption_in_image`); the CONTENTS frame is a document preview whose
      label is `eligibility.PREVIEW_LABEL`, verified with the bytes by `contents_frame.verify`;
    - the alt text opens with the frame's own label, within Etsy's alt-text limit.

    Every value is True/False from a measurement; nothing is assumed from the producer.
    """
    from . import disclosed_listing as dl

    job = frame.get("job") or ""
    label = frame.get("honesty_label") or ""
    alt = frame.get("alt_text") or ""
    ink = {ctx: round(mobile.title_safe_ink(image, px=px), 5)
           for ctx, px in SUPPLEMENT_CONTEXT_PX.items()}
    if job == el.CONTENTS:
        in_image = label == el.PREVIEW_LABEL
    else:
        in_image = (label == dl.DISCLOSURE
                    and dl.caption_in_image(frame.get("png") or b"", cir).get("status") == "PASS")
    norm = " ".join(alt.lower().replace("’", "'").split())
    in_alt = bool(label) and norm.startswith(label.lower()) and len(alt) <= dl.ALT_TEXT_MAX
    problems = [f"{ctx}: {v:.2%} of the ink sits in the title-safe band"
                for ctx, v in ink.items() if v > 0]
    if not in_image:
        problems.append(f"{job}: the frame's label is not in its pixels")
    if not in_alt:
        problems.append(f"{job}: the alt text does not open with the frame's label")
    return {"job": job, "ok": not problems, "problems": problems,
            "readings": {"title_safe_ink": ink, "label_in_image": in_image,
                         "label_in_alt_text": in_alt}}


def ls_disclosure() -> str:
    from .disclosed_listing import DISCLOSURE

    return DISCLOSURE


def _record_certificate(db, cert: ls.ListingCertificate, *, release_hash: str, issue: bool,
                        rechecked: list) -> dict:
    """File a certificate unless a valid one already covers exactly these frame hashes."""
    from sqlalchemy import desc, select

    from ..core.models import ListingSetCertificateRecord

    hashes = {f.position: f.sha256 for f in cert.frames}
    if not release_hash:
        # PT-13: a certificate bound to no release is one the upload path cannot check
        # against the release it publishes, so it is never filed.
        return {"valid": False, "issued": False, "rechecked": rechecked,
                "why": (f"{cert.slug}@{cert.version} has no release hash on file, so a "
                        f"listing-set certificate would bind to nothing; refused")}
    covered = None
    with db.session() as s:
        from .photo_asset_review import _lock, photo_certificate_current
        _lock(s, db)
        if not photo_certificate_current(s, db, cert.slug, cert.version, cert.frames):
            return {"valid": False, "issued": False, "rechecked": rechecked,
                    "why": "photo frame or evidence changed before certificate review"}
        current = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == cert.slug,
            ListingSetCertificateRecord.version == cert.version,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        if current is not None:
            on_file = {f["position"]: f["sha256"]
                       for f in (current.certificate or {}).get("frames", [])}
            if on_file == hashes:
                covered = {"valid": True, "issued": False, "record_id": current.id,
                           "rechecked": rechecked,
                           "why": "a valid certificate covers exactly these frame hashes"}
            else:
                current.state = "superseded"
                current.invalidated_by = ["frame_hashes_changed"]
                current.invalidated_at = datetime.now(timezone.utc)
    if covered is not None:
        _keep_frame_bytes(db, cert.slug, cert.version, list(hashes.values()))
        return covered
    if not issue:
        return {"valid": False, "issued": False, "rechecked": rechecked,
                "why": "no valid certificate covers these frames and issuing was not asked"}
    with db.session() as s:
        from .photo_asset_review import _lock, photo_certificate_current
        _lock(s, db)
        if not photo_certificate_current(s, db, cert.slug, cert.version, cert.frames):
            return {"valid": False, "issued": False, "rechecked": rechecked,
                    "why": "photo frame or evidence changed before certificate issuance"}
        rec = ListingSetCertificateRecord(
            product_slug=cert.slug, version=cert.version, release_hash=release_hash,
            certificate=cert.to_dict(), geometry_fingerprint=cert.geometry_fingerprint,
            claims_fingerprint=cert.claims_fingerprint, policy_version=cert.policy_version,
            state="valid")
        s.add(rec)
        s.flush()
        rid = rec.id
    _keep_certified_bytes(db, cert)
    return {"valid": True, "issued": True, "record_id": rid, "rechecked": rechecked,
            "frame_order": list(cert.frame_order),
            "why": "every disclosed frame passed all four gates and the exporter's "
                   "disclosure and structural checks; certificate issued"}


def _aggregate(per_frame: list[dict]) -> dict:
    out = {}
    for gate in el.GATES:
        outcomes = [v["gates"][gate]["outcome"] for v in per_frame]
        out[gate] = (el.FAILED if el.FAILED in outcomes else
                     el.NOT_RUN if (el.NOT_RUN in outcomes or not outcomes) else el.PASSED)
    return out


def _certificate_from_record(rec) -> ls.ListingCertificate:
    body = rec.certificate or {}
    frames = tuple(ls.CertifiedFrame(
        position=f["position"], asset_id=f["asset_id"], sha256=f["sha256"], job=f["job"],
        purpose=f["purpose"], medium=f["medium"], honesty_label=f.get("honesty_label", ""),
        measurement_sources=tuple(f.get("measurement_sources") or ()),
        kind=f.get("kind", ""), alt_text=f.get("alt_text", ""),
        represented_variant=f.get("represented_variant", ""))
        for f in body.get("frames", []))
    return ls.ListingCertificate(
        slug=rec.product_slug, version=rec.version, frames=frames,
        gate_results=dict(body.get("gate_results") or {}),
        geometry_fingerprint=rec.geometry_fingerprint,
        claims_fingerprint=rec.claims_fingerprint, policy_version=rec.policy_version,
        platform_policy=dict(body.get("platform_policy") or {}),
        disclosures=tuple(body.get("disclosures") or ()),
        represented_variant=body.get("represented_variant") or ls.SINGLE_VARIANT)


def recheck(db, *, slug: str, version: str, geometry: dict, claims: dict,
            policy_version: str) -> list[dict]:
    """Recompute every valid certificate for this release with `still_valid` (#70).

    An invalidated certificate is marked, and the frames it names lose their approval until
    the chain re-certifies them -- the revocation is a consequence of the inputs moving, not
    a step somebody has to remember.
    """
    from sqlalchemy import select

    from ..core.models import ListingAsset, ListingSetCertificateRecord

    from .photo_asset_review import AWAITING, PHOTO_CLASS

    results = []
    # Review A3 U5 F3: a release whose gallery holds a photo frame is rechecked under the
    # photo review's write lock, so no review or issuance interleaves with the revocation.
    with db.session() as s:
        photo_led = s.scalar(select(ListingAsset.id).where(
            ListingAsset.product_slug == slug, ListingAsset.version == version,
            ListingAsset.asset_class == PHOTO_CLASS).limit(1)) is not None
    with db.session() as s:
        if photo_led:
            from .photo_asset_review import _lock

            _lock(s, db)
        for rec in s.scalars(select(ListingSetCertificateRecord).where(
                ListingSetCertificateRecord.product_slug == slug,
                ListingSetCertificateRecord.version == version,
                ListingSetCertificateRecord.state == "valid")):
            verdict = ls.still_valid(_certificate_from_record(rec), geometry=geometry,
                                     claims=claims, policy_version=policy_version)
            verdict["record_id"] = rec.id
            if not verdict["valid"]:
                rec.state = "invalidated"
                rec.invalidated_by = list(verdict["invalidated_by"])
                rec.invalidated_at = datetime.now(timezone.utc)
                certified = {f["asset_id"]: (f.get("position"), f.get("sha256"))
                             for f in (rec.certificate or {}).get("frames", [])}
                gallery = list(s.scalars(select(ListingAsset).where(
                    ListingAsset.product_slug == slug, ListingAsset.version == version)))
                for asset_id in verdict["affected_assets"]:
                    pos, sha = certified.get(asset_id, (None, None))
                    for row in _certified_rows(gallery, pos, sha):
                        _mark_invalidated(row, rec, verdict, PHOTO_CLASS, AWAITING)
            results.append(verdict)
    return results


def _certified_rows(gallery, position, sha256) -> list:
    """The stored rows a certificate frame names (review of 3928ba00 L3). A certificate
    records each frame's position AND its exact bytes; a later shift (`plan_upgrade` putting
    a photograph first) moves the bytes to another slot. Resolving by the recorded position
    alone marked whatever row now sits there -- the newly approved photograph went back to
    awaiting review, and the shifted render the certificate actually named was missed. The
    row holding the certified bytes at the recorded slot is preferred; else every row that
    holds those bytes; with no recorded hash (a legacy record), the recorded slot."""
    if sha256:
        same = [r for r in gallery if r.sha256 == sha256]
        at = [r for r in same if r.position == position]
        return at or same
    return [r for r in gallery if position and r.position == position]


def _mark_invalidated(row, rec, verdict, PHOTO_CLASS, AWAITING) -> None:
    """Take a certified frame's approval away when its certificate is invalidated."""
    row.approved = False
    if row.asset_class == PHOTO_CLASS:
        # Review A3 U5 F3: a photo frame is not rebuilt -- a rebuild never replaces it -- so a
        # LISTING_SET_INVALIDATED mark would strand it for good. It goes back to the
        # asset-truth review instead, which re-checks it and re-issues the set.
        row.blocked_reasons = [AWAITING] + [
            r for r in (row.blocked_reasons or []) if r != AWAITING][:9]
    else:
        row.blocked_reasons = [
            f"LISTING_SET_INVALIDATED: certificate {rec.id} invalidated by "
            f"{', '.join(verdict['invalidated_by'])}; re-certify before "
            f"export"] + list(row.blocked_reasons or [])[:9]


def certificate_step(db, *, slug: str, version: str, release_hash: str, frames, per_frame,
                     geometry: dict, claims: dict, issue: bool, listing=None) -> dict:
    """Re-check what is on file, and issue a certificate when the whole set passed."""
    from sqlalchemy import desc, select

    from ..core.models import ListingSetCertificateRecord
    from ..gates.platform_policy import policy_stamp
    from ..gates.policy import POLICY_VERSION

    rechecked = recheck(db, slug=slug, version=version, geometry=geometry, claims=claims,
                        policy_version=POLICY_VERSION)
    hashes = {v["position"]: v.get("sha256") for v in per_frame}
    covered = None
    with db.session() as s:
        from .photo_asset_review import _lock, photo_snapshot_current
        _lock(s, db)
        if not photo_snapshot_current(s, db, slug, version, frames):
            return {"valid": False, "issued": False, "rechecked": rechecked,
                    "why": "photo frame or evidence changed before certificate review"}
        current = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.version == version,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        if current is not None:
            on_file = {f["position"]: f["sha256"]
                       for f in (current.certificate or {}).get("frames", [])}
            if on_file == hashes:
                covered = {"valid": True, "issued": False, "record_id": current.id,
                           "rechecked": rechecked,
                           "why": "a valid certificate covers exactly these frame hashes"}
            else:
                current.state = "superseded"
                current.invalidated_by = ["frame_hashes_changed"]
                current.invalidated_at = datetime.now(timezone.utc)
    if covered is not None:
        _keep_frame_bytes(db, slug, version, list(hashes.values()))
        return covered

    if not issue:
        return {"valid": False, "issued": False, "rechecked": rechecked,
                "why": ("no valid certificate covers these frames, and one is not issued "
                        "while any gate above is failing or has not run")}

    certified = []
    for f in frames:
        job, purpose = _job_of_frame(f) or ROLE_JOBS[f.role]
        label = el.honesty_label(AssetClass(f.asset_class), job)
        sources = (("finished.width", "finished.length")
                   if f.role == "size" and (f.claims or {}).get("width_cm") else ())
        certified.append(ls.CertifiedFrame(
            position=f.position, asset_id=_asset_id(slug, f.position), sha256=f.sha256 or "",
            job=job, purpose=purpose, medium=f.asset_class,
            honesty_label=label["label"] if label["required"] else "",
            measurement_sources=sources))
    try:
        cert = ls.certify(slug=slug, version=version, frames=certified,
                          gate_results=_aggregate(per_frame), geometry=geometry,
                          claims=claims, policy_version=POLICY_VERSION,
                          platform_policy=policy_stamp(db),
                          disclosures=tuple(sorted({c.honesty_label for c in certified
                                                    if c.honesty_label})))
    except ls.ListingSetRefused as e:
        return {"valid": False, "issued": False, "rechecked": rechecked, "why": str(e)[:400]}
    with db.session() as s:
        from .photo_asset_review import _lock, photo_snapshot_current
        _lock(s, db)
        if not photo_snapshot_current(s, db, slug, version, frames):
            return {"valid": False, "issued": False, "rechecked": rechecked,
                    "why": "photo frame or evidence changed before certificate issuance"}
        rec = ListingSetCertificateRecord(
            product_slug=slug, version=version, release_hash=release_hash,
            certificate=cert.to_dict(), geometry_fingerprint=cert.geometry_fingerprint,
            claims_fingerprint=cert.claims_fingerprint, policy_version=cert.policy_version,
            state="valid")
        s.add(rec)
        s.flush()
        rid = rec.id
    _keep_certified_bytes(db, cert)
    return {"valid": True, "issued": True, "record_id": rid, "rechecked": rechecked,
            "frame_order": list(cert.frame_order),
            "why": "every frame passed all four gates; certificate issued"}


def _keep_certified_bytes(db, cert) -> None:
    """W4-FIRSTSALE: the certified upload set must outlive a redeploy (Postgres keep)."""
    body = cert.to_dict()
    _keep_frame_bytes(db, body.get("slug") or "", body.get("version") or "",
                      [f.get("sha256") for f in body.get("frames") or []])


def _keep_frame_bytes(db, slug: str, version: str, shas: list) -> None:
    try:
        from ..commerce import deliverables

        deliverables.keep_frames(db, shas, slug=slug, version=version)
    except Exception:  # noqa: BLE001 - keeping never blocks a certificate
        pass


# ---- #297: the launch window -------------------------------------------------------------

def window_decision(db, *, slug: str, version: str, today: date | None = None,
                    positioning: str | None = None) -> dict:
    """What #297 says to do with this product today: launch, or pivot/simplify/hold.

    The same computation the seasonal sentinel audits (`catalogue_plans`): the product's own
    make time, its occasion, the next occurrence. `positioning="evergreen"` records that the
    seasonal premise has been removed from the listing, which is what a pivot means.
    """
    from ..cir.compiler import compile_cir
    from ..radar.market import SEASONAL_EVENTS
    from ..seasonal import leadtime as lt

    today = today or date.today()
    occasion = lt.occasion_for(slug)
    if occasion in (lt.EVERGREEN, lt.UNASSIGNED):
        return {"slug": slug, "action": lt.LAUNCH, "occasion": occasion,
                "may_launch_seasonally": True,
                "why": f"{occasion}: no seasonal premise to miss"}
    cir, _ = _release(db, slug, version)
    if cir is None:
        return {"slug": slug, "action": lt.HOLD, "occasion": occasion,
                "may_launch_seasonally": False,
                "why": "no certified release to schedule, so no window can be shown to be met"}
    event = next((e for e in SEASONAL_EVENTS if e.name == occasion), None)
    if event is None:
        return {"slug": slug, "action": lt.HOLD, "occasion": occasion,
                "may_launch_seasonally": False,
                "why": f"occasion {occasion!r} names no seasonal event; the window is unknown"}
    base, _cal = lt.calibrate_from_samples(db, lt.DEFAULT)
    from ..seasonal.harvest import adjusted_assumptions

    event_base = adjusted_assumptions(db, event.name, base)
    compiled = compile_cir(cir)
    estimate = lt.estimate_for(cir, compiled, base)
    when = lt.next_occurrence(event.event_date, today)
    # #283: planned for the maker the pattern's printed difficulty is bought by, not a
    # default intermediate; the whole skill distribution rides beside the decision.
    skill, printed = lt.maker_skill_for(cir, compiled)
    hours = estimate.to_dict()["hours"]
    plan = lt.compile_launch(event.name, when, make_hours=hours, assumptions=event_base,
                             skill=skill)
    action, why = plan.recommendation(today)
    pivoted = action == lt.PIVOT_EVERGREEN and positioning == "evergreen"
    return {"slug": slug, "occasion": occasion, "event_date": when.isoformat(),
            "skill": skill, "difficulty": printed,
            "make_time_by_skill": lt.skill_distribution(event.name, when, make_hours=hours,
                                                        today=today, assumptions=event_base),
            "status": plan.status(today), "action": action, "why": why,
            "latest_effective_launch": plan.latest_effective_launch.isoformat(),
            "positioning": positioning or "seasonal",
            "may_launch_seasonally": action == lt.LAUNCH or pivoted,
            "pivot_applied": pivoted}


# ---- #172 / #173: staleness --------------------------------------------------------------

# eng/stale-rebuild-loop: the families that are staleness -- the sentinel's own rows and the
# rebuild graph's `rebuild-incomplete` (a rebuild that has not yet delivered). Both are what
# a rebuild cures, so neither may refuse the rebuild; an *exhausted* rebuild-incomplete row
# (REBUILD_MAX_ATTEMPTS attempts failed) is a named hold instead of a waiver.
STALENESS_FAMILIES = frozenset({"stale-artefact", "rebuild-incomplete"})


def _staleness_only(ev: dict) -> bool:
    fams = set(ev.get("widespread_families") or ())
    return (bool(ev.get("systemic")) and not ev.get("integrity_failures") and bool(fams)
            and fams <= STALENESS_FAMILIES)


def incident_slug(row) -> str | None:
    """The product an incident is filed against. Review M-A of 4b683993: rebuild-incomplete
    rows written before the product slug was filed carry it only in their signature
    (`rebuild-incomplete:<slug>`), so a reader that matched on `product_slug` alone never saw
    them -- an exhausted legacy row held nothing."""
    from ..ops.rebuild_graph import REBUILD_INCOMPLETE_SIGNATURE

    if row.product_slug:
        return row.product_slug
    sig = str(row.signature or "")
    if sig.startswith(f"{REBUILD_INCOMPLETE_SIGNATURE}:"):
        return sig[len(REBUILD_INCOMPLETE_SIGNATURE) + 1:] or None
    return None


def rebuild_withheld(db, slug: str) -> tuple[str | None, str | None]:
    """(version, withholding summary) for the release `chain.rebuild` targets -- the newest
    release by version, its withholding record re-read (owner ruling included) exactly as
    the rebuild reads it. Review L1: the retry hold and the rebuild's own refusal read one
    function, so they cannot disagree."""
    from sqlalchemy import select

    from ..core.models import Product
    from ..ops import artefacts as provenance
    from . import withholding

    with db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        pv = provenance.newest_release(s, product.id) if product is not None else None
        version = pv.version if pv is not None else None
    if version is None:
        return None, None
    summary = withholding.current(db, slug, version, stage="chain.rebuild")["summary"]
    return version, (summary or None)


def rebuild_exhausted(row) -> bool:
    """A `rebuild-incomplete:<slug>` row whose attempts are used up (held, named reason).
    A row written before eng/stale-rebuild-loop is not: it gets a fresh budget first."""
    from ..ops.rebuild_graph import REBUILD_INCOMPLETE_SIGNATURE, incomplete_exhausted

    if not str(row.signature or "").startswith(f"{REBUILD_INCOMPLETE_SIGNATURE}:"):
        return False
    # review M-E of 0d2e6cbc: one definition; a pre-branch row is not exhausted by its count
    return incomplete_exhausted(row.report_count, row.detail)


def _waivable_staleness(row, slug: str, fresh: set[str]) -> bool:
    """A halting row that is this product's staleness and so may not refuse its rebuild:
    a sentinel row for an artefact that already reads FRESH again (the next sweep closes
    it -- the rebuild in progress just remade it), or a rebuild-incomplete row that is not
    yet exhausted."""
    from ..ops.artefacts import SENTINEL_SIGNATURE
    from ..ops.rebuild_graph import REBUILD_INCOMPLETE_SIGNATURE

    sig = str(row.signature or "")
    if sig.startswith(f"{SENTINEL_SIGNATURE}:"):
        return sig[len(SENTINEL_SIGNATURE) + 1:] in fresh
    if sig == f"{REBUILD_INCOMPLETE_SIGNATURE}:{slug}":
        return not rebuild_exhausted(row)
    return False


def _own_rebuild_pending(db, slug: str) -> bool:
    """This product's own `rebuild-incomplete` row is open and its budget is not exhausted.
    Unreadable is False (a halt is never waived on a failed read)."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..ops.rebuild_graph import REBUILD_INCOMPLETE_SIGNATURE

    try:
        with db.session() as s:
            row = s.scalar(select(Incident).where(
                Incident.resolved == False,  # noqa: E712
                Incident.signature == f"{REBUILD_INCOMPLETE_SIGNATURE}:{slug}"))
            return row is not None and not rebuild_exhausted(row)
    except Exception:  # noqa: BLE001
        return False


def _halting_other_than_staleness(db, slug: str, own: set[str],
                                  fresh: set[str] | None = None) -> list:
    """Open halting incidents for `slug` other than its own stale-marketing rows and other
    than a company-wide halt whose only evidence is widespread stale-artefact rows.

    Review F3/F5: the waiver names exactly `SYSTEMIC_SIGNATURE` (not any `systemic-halt:`
    row), and the evidence and the incident list are read in one session, so a tamper row
    opened between two reads cannot ride a stale "staleness only" verdict. Unreadable
    evidence never waives a halt."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..ops.incident_lifecycle import SYSTEMIC_SIGNATURE, systemic_evidence
    from ..ops.rebuild_graph import REBUILD_INCOMPLETE_SIGNATURE

    with db.session() as s:
        try:
            ev = systemic_evidence(s)
            staleness_only = _staleness_only(ev)
        except Exception:  # noqa: BLE001
            staleness_only = False
        rows = list(s.scalars(select(Incident).where(
            Incident.resolved == False,  # noqa: E712
            Incident.halts_publication.is_(True),
            (Incident.product_slug == slug) | Incident.signature.like("systemic-halt:%")
            | (Incident.signature == f"{REBUILD_INCOMPLETE_SIGNATURE}:{slug}"))))
        return [r.signature for r in rows
                if r.signature not in own
                and not _waivable_staleness(r, slug, fresh or set())
                and not (staleness_only and r.signature == SYSTEMIC_SIGNATURE)]


def staleness(db, *, slug: str) -> dict:
    """Open halting incidents (the sentinel's among them) and the rebuild graph's verdict."""
    from ..gates.incidents import IncidentTracker
    from ..ops import rebuild_graph

    tracker = IncidentTracker(db)
    halting = [{"id": i.id, "severity": i.severity, "summary": (i.summary or "")[:160]}
               for i in tracker.open_incidents(slug) if i.halts_publication]
    with db.session() as s:
        graph = rebuild_graph.publication_gate(s, slug=slug)
    reasons = []
    if halting:
        reasons.append(f"halted (#173): {len(halting)} open publication-halting incident(s): "
                       + "; ".join(h["summary"] for h in halting[:2]))
    # #39: a material platform-policy change nobody has reviewed and tested blocks every
    # product's publication, not one slug's -- the rule changed for the whole shop.
    from ..gates.platform_policy import unreviewed_changes

    policy = [c for c in unreviewed_changes(db) if "publishing" in c["affects"]]
    if policy:
        reasons.append("platform policy changed (#39): "
                       + ", ".join(c["source"] for c in policy)
                       + " changed materially and has not been reviewed and tested")
    if not graph["may_publish"]:
        reasons.append(f"rebuild outstanding (#172): {graph['why']}")
    outstanding = list(graph.get("outstanding") or [])
    # C-80 defect 11: a structured flag for the one exception marketing.schedule may take --
    # the only thing outstanding is marketing content and nothing halts the product -- so
    # the caller reads a field, not the wording of a reason.
    # W4-LISTREADY (R4): "nothing halts the product" means nothing *besides* the sentinel's
    # own rows for exactly this outstanding marketing content. Those rows exist because the
    # content is stale, so counting them made stale marketing unrebuildable by construction
    # (the rebuild was refused on the staleness it exists to cure). This flag lets only the
    # marketing rebuild proceed; `halted`, `reasons` and `blocks` -- what publication reads --
    # are unchanged, and any other halting incident still refuses the rebuild too.
    own_marketing = {f"stale-artefact:{k}" for k in outstanding
                     if str(k).startswith("marketing_asset:")}
    # W4-PRODFIX: the company-wide halt is the same staleness escalated (#173 -> F-168) when
    # its only evidence is widespread stale-artefact rows and no integrity failure. Counting
    # it re-created R4's deadlock one level up: stale marketing in >= 3 products opens the
    # systemic halt, the systemic halt refuses every marketing rebuild, so the staleness that
    # holds the halt open can never be cured (production 051dbee2: 123 stale marketing rows,
    # halt open since 2026-10-11). It is waived for this rebuild flag only; `halted`,
    # `reasons` and `blocks` -- what publication reads -- still carry it, and a systemic halt
    # with any other evidence (an integrity failure, another family) still refuses.
    # eng/stale-rebuild-loop (production ea3aacc7): the same rebuild that remade this
    # product's PDF, charts and copy reaches marketing.schedule before the hourly sweep has
    # closed the sentinel rows for those artefacts. Counting rows whose artefact already reads
    # FRESH refused the marketing rebuild on every attempt, so marketing never converged.
    halting_other = _halting_other_than_staleness(db, slug, own_marketing,
                                                  set(graph.get("fresh") or ()))
    # Review F4: an unreviewed platform-policy change (#39) is not staleness, so it is never
    # waived by the marketing rebuild exception.
    # ENG-RECOVERY: only a change governing growth or product creation holds the marketing
    # rebuild (drafted, held content); a listing-image or search change holds publication.
    policy_marketing = policy_holds_manufacturing(policy, MARKETING_REBUILD_POLICY_WORKFLOWS)
    # ENG-RECOVERY fix round 1 (review L5): a legacy rebuild-incomplete row names keys that
    # read "no provenance row" -- nothing is outstanding in the graph -- and the targeted
    # rebuild that row is waiting for reaches marketing.schedule with an empty `outstanding`.
    # Requiring a non-empty outstanding list refused that rebuild on every attempt (proved by
    # test_eng_recovery's end-to-end L5 test), spending the row's three-attempt budget on a
    # refusal the rebuild exists to cure. So the exception also applies when this product's
    # own rebuild-incomplete row is open and not exhausted. Everything else is unchanged: any
    # other halting row, a growth/product-creation policy change or non-marketing outstanding
    # work still refuses, and `halted`, `reasons` and `blocks` (what publication reads) still
    # carry the halt and every unreviewed publishing change.
    own_rebuild_pending = not outstanding and _own_rebuild_pending(db, slug)
    only_marketing = ((bool(outstanding) or own_rebuild_pending)
                      and not halting_other and not policy_marketing
                      and all(str(k).startswith("marketing_asset:") for k in outstanding))
    return {"halted": bool(halting), "incidents": halting[:5], "rebuild": graph,
            "policy_changes_unreviewed": [c["source"] for c in policy],
            "policy_publication_only": policy_publication_only(policy),
            "blocks": bool(reasons), "reasons": reasons,
            "outstanding_only_marketing": only_marketing}


# ENG-RECOVERY (prod 2026-11-19, owner directive): a publication-side platform-policy question
# must not halt internal production; it may hold publication only. Production held 16 daily
# rebuild retries (and left 14 legacy rebuild-incomplete rows unable to start their fresh
# budget) on `listing_image_rules` alone -- a change that governs what a *listing* may show,
# pending the owner's review since 2026-10-11 -- so stale PDFs, charts and galleries were
# never remade, the stale-artefact halt could never converge and certification stayed halted.
#
# The scope rule: an unreviewed change holds the internal rebuild only when it governs whether
# the product may be MADE at all (`product_creation`: a prohibited children's item, a design
# outside the creativity categories). Every other unreviewed change -- image, listing, search,
# seller rules -- leaves internal manufacturing running under the codified, owner-reviewed
# reading (`gates.policy_knowledge`), which is the stricter of the two until the new text is
# reviewed: nothing the new reading may relax is used, and nothing built under it can
# publish, because `staleness()` (what for_publish and for_marketing read) still refuses on
# EVERY unreviewed publishing change. The marketing rebuild (drafted and held content) is
# held by changes that govern growth or product creation.
MANUFACTURING_POLICY_WORKFLOWS: frozenset[str] = frozenset({"product_creation"})
MARKETING_REBUILD_POLICY_WORKFLOWS: frozenset[str] = frozenset({"product_creation", "growth"})


def policy_holds_manufacturing(changes, workflows=MANUFACTURING_POLICY_WORKFLOWS) -> list[str]:
    """The unreviewed policy sources that hold internal work of the given kind (#39 scope)."""
    return sorted({str(c.get("source")) for c in changes or ()
                   if set(c.get("affects") or ()) & set(workflows)})


def policy_publication_only(changes) -> list[str]:
    """Unreviewed sources that hold publication but let internal manufacturing proceed."""
    held = set(policy_holds_manufacturing(changes))
    return sorted({str(c.get("source")) for c in changes or ()
                   if "publishing" in (c.get("affects") or ()) and str(c.get("source")) not in held})


def retry_hold_reason(db, *, slug: str) -> str | None:
    """INTEG7 (review S-2, corrected by review H1 of dbb4ebf): why the daily rebuild retry for
    `slug` should wait, or None.

    A retry is held only while a gate the rebuild cannot cure refuses the product:
    - an unreviewed material platform-policy change (#39) that governs product creation
      (ENG-RECOVERY: a publication-side change -- listing images, search, seller rules --
      holds publication only, never the internal rebuild), or
    - an open halting incident for the product that is not staleness (integrity, tamper and
      the like).
    - eng/stale-rebuild-loop: an exhausted `rebuild-incomplete` row (REBUILD_MAX_ATTEMPTS
      attempts at the change failed; its named reason is returned), or a withheld release
      -- each a refusal the retry cannot cure.
    The sentinel's own `stale-artefact:*` rows, which are the staleness the retry exists to
    cure, never hold it, nor does a rebuild-incomplete row with attempts left. Neither does a
    company-wide halt whose only evidence is widespread staleness rows. The hold lifts by
    itself when the gate clears. An unreadable gate does not hold (the retry is CA$0 and
    bounded to once a day)."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..gates.platform_policy import unreviewed_changes
    from ..ops.artefacts import SENTINEL_SIGNATURE
    from ..ops.incident_lifecycle import SYSTEMIC_SIGNATURE, systemic_evidence
    from ..ops.rebuild_graph import REBUILD_INCOMPLETE_SIGNATURE, REBUILD_MAX_ATTEMPTS

    try:
        policy = policy_holds_manufacturing(unreviewed_changes(db))
        with db.session() as s:
            try:
                ev = systemic_evidence(s)
                staleness_only = _staleness_only(ev)
            except Exception:  # noqa: BLE001 - unreadable evidence never waives a halt
                staleness_only = False
            rows = list(s.scalars(select(Incident).where(
                Incident.resolved == False,  # noqa: E712
                Incident.halts_publication.is_(True),
                (Incident.product_slug == slug) | Incident.signature.like("systemic-halt:%")
                # review M-A: a legacy row carries its product only in the signature
                | (Incident.signature == f"{REBUILD_INCOMPLETE_SIGNATURE}:{slug}"))))
            # eng/stale-rebuild-loop: rebuild-incomplete (now filed against its product) is
            # staleness the retry exists to cure, so it never holds while attempts remain.
            # Once they are used up it becomes the named hold.
            exhausted = [r for r in rows if incident_slug(r) == slug and rebuild_exhausted(r)]
            others = [r.signature for r in rows
                      if not str(r.signature).startswith(f"{SENTINEL_SIGNATURE}:")
                      and not str(r.signature).startswith(f"{REBUILD_INCOMPLETE_SIGNATURE}:")
                      and not (staleness_only and r.signature == SYSTEMIC_SIGNATURE)]
            exhausted_why = [str((r.detail or {}).get("held") or r.summary or "")[:300]
                             for r in exhausted]
    except Exception:  # noqa: BLE001
        return None
    if policy:
        return ("held: platform policy change governing product creation awaiting the "
                "owner's review (#39): " + ", ".join(policy))
    if exhausted_why:
        return (f"held: rebuild could not complete after {REBUILD_MAX_ATTEMPTS} attempts "
                f"({REBUILD_INCOMPLETE_SIGNATURE}:{slug}): " + exhausted_why[0])
    # eng/stale-rebuild-loop: what `chain.rebuild` itself refuses on -- a release withheld
    # (#163/#228) -- is a gate the retry cannot cure. It was retried daily, refused, and
    # left no incident (a silent loop). Read live, so the hold
    # lifts by itself when the withholding clears.
    try:
        # review L1: the same function `chain.rebuild` refuses on (newest release, its
        # withholding record re-read at stage chain.rebuild).
        version, withheld = rebuild_withheld(db, slug)
        if withheld:
            return f"held: release {slug}@{version} withheld (#163/#228): {str(withheld)[:200]}"
    except Exception:  # noqa: BLE001 - an unreadable gate does not hold (CA$0, once a day)
        pass
    if others:
        return ("held: open halting incident(s) the rebuild cannot cure: "
                + ", ".join(map(str, others[:3])))
    return None


def _frame_bytes(db, slug: str, version: str, store_root=None) -> dict[str, bytes]:
    from ..core.artifacts import ArtifactMissing, ArtifactStore

    store = ArtifactStore(store_root)
    out: dict[str, bytes] = {}
    for f in _frames(db, slug, version):
        if f.sha256:
            try:
                out[f"frame-{f.position}"] = store.get(f.sha256, db=db)
            except (ArtifactMissing, OSError):
                continue
    return out


def originality_gate(db, *, slug: str, version: str, store_root=None) -> dict:
    """Current corpus/rights at protected execution, including evidence added after QA."""
    from ..cir.compiler import compile_cir
    from ..cir.writer import write_pattern
    from ..gates import originality
    try:
        cir, release_hash = _release(db, slug, version)
        if cir is None:
            return {"blocks": True, "reasons": ["originality: no certified source CIR"],
                    "state": "UNKNOWN"}
        result = compile_cir(cir)
        if not result.ok:
            return {"blocks": True, "reasons": ["originality: source CIR no longer compiles"],
                    "state": "UNKNOWN"}
        findings = originality.release_findings(cir, pattern_text=write_pattern(cir, result), db=db)
        # F-784 / F-795: presentation -- this release's listing frames against every
        # benchmark image, by perceptual hash.
        findings.extend(originality.presentation_review(
            db, frames=_frame_bytes(db, slug, version, store_root)))
        reasons = [f"{f.code}: {f.message}" for f in findings if f.is_error]
        return {"blocks": bool(reasons), "reasons": reasons,
                "state": "REFUSED" if reasons else "CHECKED", "release_hash": release_hash,
                "presentation_warnings": [f.message for f in findings
                                          if f.code == "SIMILARITY_UNMEASURED"],
                "limitation": "deterministic comparison is not independent legal/creative adjudication"}
    except Exception as exc:
        return {"blocks": True, "reasons": ["originality evidence unavailable: " + type(exc).__name__],
                "state": "UNKNOWN"}


def launch_price_check(slug: str, listing_price_cad) -> dict:
    """A Launch-0 listing must carry its own price plan's price (PT-04, W4-CAP1).

    `mosaic-placemat-pair@1.3.0` was drafted in production at CA$9.50 before it joined
    Launch-0: the generic path had no "placemat" band and priced it at the top of the unsourced
    DEFAULT_BAND (4.50-9.50). Its plan is CA$5.00 on the SOURCED CA$4-12 cluster. A stored
    listing priced off-plan is refused at publication until the release chain re-prices it;
    the comparison is exact to the cent. Outside Launch-0 there is no plan: NOT_APPLICABLE.
    """
    from ..products import launch0

    plan = launch0.launch_price(slug)
    if plan is None or plan.get("price_cad") is None:
        return {"state": "NOT_APPLICABLE", "why": "no Launch-0 price plan for this slug"}
    if listing_price_cad is None:
        return {"state": "NO_LISTING", "plan_cad": plan["price_cad"],
                "why": "no stored listing to compare"}
    if round(float(listing_price_cad), 2) != round(float(plan["price_cad"]), 2):
        return {"state": "DRIFT", "plan_cad": plan["price_cad"],
                "listing_cad": float(listing_price_cad),
                "why": (f"the stored listing is CA${float(listing_price_cad):.2f} but the "
                        f"Launch-0 price plan is CA${plan['price_cad']:.2f} ({plan['basis']}); "
                        f"re-run pricing.position for this release")}
    return {"state": "MATCH", "plan_cad": plan["price_cad"], "why": "listing carries the plan"}


def superseded_release(db, *, slug: str, version: str) -> dict:
    """W4-LISTREADY (R1): whether a newer certified release of this product exists.

    The stale-artefact sentinel judges an artefact against the release it was built from, so
    an older release's artefacts are `superseded` rather than stale and raise no halt. This is
    the guard that keeps a superseded release from being published on the strength of that:
    only the product's newest certified release may publish. Unreadable state refuses.
    """
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    try:
        with db.session() as s:
            rows = list(s.execute(
                select(PatternVersion.id, PatternVersion.version)
                .join(Product, PatternVersion.product_id == Product.id)
                .where(Product.slug == slug, PatternVersion.certified == True)))  # noqa: E712
    except Exception as exc:  # noqa: BLE001 - unreadable is a refusal, never a pass
        return {"superseded": True, "newest": None,
                "why": f"superseded release (R1): certified releases unreadable "
                       f"({type(exc).__name__})"}
    if not rows:
        return {"superseded": False, "newest": None, "why": ""}
    # Review F2: newest by version, never by the row inserted last. Unorderable refuses.
    from ..ops.artefacts import newest_version

    newest = newest_version([r[1] for r in rows])
    if newest is None:
        return {"superseded": True, "newest": None,
                "why": (f"superseded release (R1): the certified versions of {slug} cannot be "
                        f"ordered ({sorted({r[1] for r in rows})}), so the newest is unknown; "
                        f"refused")}
    if newest == version:
        return {"superseded": False, "newest": newest, "why": ""}
    return {"superseded": True, "newest": newest,
            "why": (f"superseded release (R1): {slug}@{version} is not the product's newest "
                    f"certified release ({slug}@{newest}); only the newest may publish")}


#: The two Etsy-facing stages `for_publish` judges. A private draft (createDraftListing) is
#: not shown to buyers; activation is public publication.
STAGE_DRAFT = "draft"
STAGE_ACTIVATION = "activation"
STAGES = (STAGE_DRAFT, STAGE_ACTIVATION)


def for_publish(db, *, slug: str, version: str, today: date | None = None,
                positioning: str | None = None, store_root=None,
                read_only: bool = False, stage: str = STAGE_DRAFT) -> dict:
    """Everything store.publish must refuse on, computed once and returned as one verdict.

    `read_only=True` (store.publish) writes no artifact: supplement frames are judged only if
    already stored, so the Shadow Mode refusal comes before any storage write.

    `stage` (W4-LAUNCHFIX, owner clarification 2026-10-27): every gate applies at both
    stages except Etsy's sample-photo requirement, which governs listings shown to buyers and
    so refuses only at `activation`. At `draft` it is reported, and the copy-truth check
    still refuses a draft that claims a sample photograph it does not have. An unknown stage
    is refused (raised; `pipeline._release_gates` turns that into a closed gate)."""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}, not {stage!r}")
    stale = staleness(db, slug=slug)
    window = window_decision(db, slug=slug, version=version, today=today,
                             positioning=positioning)
    set_verdict = listing_set(db, slug=slug, version=version, store_root=store_root,
                              issue=not stale["blocks"] and window["may_launch_seasonally"],
                              persist_supplements=not read_only)
    reasons = list(stale["reasons"])
    superseded = superseded_release(db, slug=slug, version=version)
    if superseded["superseded"]:
        reasons.append(superseded["why"])
    originality = originality_gate(db, slug=slug, version=version, store_root=store_root)
    reasons.extend(originality["reasons"])
    if not window["may_launch_seasonally"]:
        reasons.append(f"missed window (#297): {window['action']} -- {window['why']}")
    reasons.extend(set_verdict["reasons"])
    # OPUS2-P0 (owner report 2026-10-27, "Nesting Baskets, three sizes" delivered a medium-only
    # PDF): one certified release delivers one size of instructions, so neither its listing
    # nor its customer PDF may promise more. An unreadable verdict refuses, never passes.
    from ..gates import size_claims

    try:
        sizes = size_claims.for_release(db, slug=slug, version=version)
    except Exception as exc:  # noqa: BLE001
        sizes = {"state": size_claims.UNKNOWN,
                 "reasons": [f"size-claim truth could not be read ({type(exc).__name__})"]}
    reasons.extend(sizes["reasons"])
    # F-004 / F-294: search certification -- category, attributes, copy, tags, description
    # and hero, bound to the listing as it stands.
    search = search_gate(db, slug=slug, version=version, set_verdict=set_verdict)
    reasons.extend(search["reasons"])
    # The hero judged here is written back to the stored certificate with the evidence it
    # used, so the stored verdict the payload builder reads is the one this gate computed --
    # PASS only when this gate passed on a certified set, never PENDING promoted.
    from ..commerce import search as search_mod

    try:
        search["stored"] = search_mod.judge_hero(db, slug=slug, version=version,
                                                 set_verdict=set_verdict, gate=search)
    except Exception as exc:  # noqa: BLE001 - an unrecorded verdict refuses, never passes
        reasons.append(f"search certificate (F-004): the hero verdict could not be recorded "
                       f"({type(exc).__name__})")
    # #153-#160, #220, #228: the standards this company holds itself to, read at the gate.
    standards = standards_gate(db, slug=slug, version=version)
    reasons.extend(standards["reasons"])
    # C-67 / M10: the standards' verdicts are written to the release's one withholding
    # record, kind by kind, and the record's other reasons -- the teardown QA's withhold
    # (#163), which nothing above computes -- refuse here too.
    from . import withholding

    held = withholding.reconcile(db, slug, version, standards=standards)
    for kind, entry in sorted(held["reasons"].items()):
        if kind == withholding.TEARDOWN_QA:
            reasons.append(f"release withheld (#163): {entry['reason']}")
        elif kind == withholding.QUALITY_REVERIFY:
            # P0-REVERIFY-WITHHOLD (OPUS2-P0): durable, so it survives audit-log pruning.
            reasons.append(f"release withheld (re-verification): {entry['reason']}")
    # PHYSFIX (SECREVIEW 8da830d R28 follow-up): the version a physical sample measured at
    # the wrong size never publishes again -- read from the record and, independently, from
    # its durable audit row, so neither a replaced certificate nor retention un-withholds it.
    size_failed = [str(entry["reason"]) for kind, entry in held["reasons"].items()
                   if kind == withholding.PHYSICAL_SIZE_FAILED]
    size_failed += withholding.durable_reasons(db, slug, version)
    for why in dict.fromkeys(size_failed):
        reasons.append(f"release withheld (physical size): {why}")
    # F-111 / F-118 / F-120 (cluster C): the product-level scope -- legacy quarantine, and
    # for a Launch-0 slug the first customer's nine-area gate -- decided in one place.
    from . import eligibility

    row = _listing(db, slug, version)
    scope = eligibility.product_publication(
        db, slug, version,
        listing=(None if row is None else
                 {"title": row.title, "description": row.description,
                  # Preserve malformed values so the audience gate can fail closed;
                  # list("baby") would silently turn the word into four tags.
                  "tags": row.tags if row.tags is not None else [],
                  "price_cad": row.price_cad}))
    reasons.extend(f"{r['code']}: {r['why']}" for r in scope["reasons"])
    price_check = launch_price_check(slug, None if row is None else row.price_cad)
    if price_check["state"] == "DRIFT":
        reasons.append(f"LISTING_PRICE_NOT_PLAN: {price_check['why']}")
    # Review cbd4ff1 N-2: an Etsy taxonomy drift held for the owner (re-queue OFF) does not
    # halt gate.certify -- that would block the rebuild -- but it does stop publication.
    from ..integrations.taxonomy_drift import held_drift

    for h in held_drift(db, slug):
        reasons.append(f"taxonomy drift held for the owner (incident {h['id']}): "
                       f"{h['summary']}")
    # W4-LAUNCHFIX (Etsy Help 44297885802647 / 115015663347): a pattern listing shown to
    # buyers needs an unedited photograph of a sample made from THIS release, first in the
    # certified gallery. That refuses at activation (public publication) only; a private
    # draft is not shown to buyers, and no verified Etsy evidence says a draft needs one.
    # At both stages the copy must be truthful about whether such a photo exists.
    from . import sample_photo

    photo = sample_photo.requirement(db, slug, version)
    if stage == STAGE_ACTIVATION:
        reasons.extend(photo["reasons"])
    if row is not None:
        reasons.extend(sample_photo.copy_problems(
            row.description, photographed_sample=photo["satisfied"]))
    return {"slug": slug, "version": version, "blocks_release": bool(reasons),
            "reasons": reasons, "staleness": stale, "window": window,
            "superseded": superseded, "listing_set": set_verdict, "search": search, "standards": standards,
            "withholding": held, "publication_scope": scope, "originality": originality,
            "sample_photo": photo, "stage": stage}


IMAGE_STANDARDS = ("gallery_images", "video_in_gallery")
HERO_REASON = "search certificate (F-004) hero:"


def image_reasons(verdict: dict | None) -> set[str]:
    """b17-c A3 (D-OWNER-SPEND-ORDER): the reasons of a `for_publish` verdict that the
    listing's images cause -- the listing set, image originality, the search hero, the
    sample-photo requirement and the gallery-size competitive standards. Every other reason
    is a non-image listing gate, and a product with one is not admitted for image spend.
    A reason this cannot attribute is non-image: unknown never admits."""
    v = verdict or {}
    out: set[str] = set()
    for part in ("listing_set", "originality", "sample_photo"):
        out.update(str(r) for r in ((v.get(part) or {}).get("reasons") or []))
    out.update(str(r) for r in ((v.get("search") or {}).get("reasons") or [])
               if str(r).startswith(HERO_REASON))
    out.update(str(r) for r in ((v.get("standards") or {}).get("reasons") or [])
               if any(str(r).startswith(f"competitive standard {k} ") for k in IMAGE_STANDARDS))
    return out


# D-MAIN-IMAGE-ADMISSION: the publish-time / store-wide first-customer gates. Both still
# block PUBLISHING exactly as before (they stay in `for_publish`'s reasons); they do not stop a
# release being admitted for its paid images, because neither is about the product's pattern
# truth: `gauge_and_size_claims` waits on a physical sample (an owner action) and
# `etsy_remote_state` is a store-wide integration check (UNVERIFIABLE until Etsy is read).
# An explicit allow-list of first-customer AREAS, read from the structured reason -- never a
# pattern over the text. Any area not listed here stays a non-image blocker.
PUBLISH_TIME_AREAS = frozenset({"gauge_and_size_claims", "etsy_remote_state"})


def publish_time_reasons(verdict: dict | None) -> dict[str, str]:
    """The reasons of a `for_publish` verdict that come from an allow-listed publish-time gate
    (`PUBLISH_TIME_AREAS`), mapped to that gate's area. Read from the product scope's structured
    reasons (`eligibility.product_publication`), so a reason whose area is missing, or not on
    the list, is not here -- it stays non-image, and unknown never admits."""
    from .eligibility import FIRST_CUSTOMER_BLOCKING

    scope = (verdict or {}).get("publication_scope") or {}
    out: dict[str, str] = {}
    for r in scope.get("reasons") or []:
        if (isinstance(r, dict) and r.get("code") == FIRST_CUSTOMER_BLOCKING
                and isinstance(r.get("area"), str) and r["area"] in PUBLISH_TIME_AREAS):
            out[f"{r['code']}: {r['why']}"] = r["area"]
    return out


def our_competitive_reading(db, *, slug: str, version: str, key: str) -> float | None:
    """This listing's own reading on one CompetitiveStandard, or None when unmeasurable."""
    from sqlalchemy import select

    from ..core.models import ListingAsset, PatternVersion, Product

    with db.session() as s:
        assets = list(s.scalars(select(ListingAsset).where(
            ListingAsset.product_slug == slug, ListingAsset.version == version)))
        if key == "gallery_images":
            return float(sum(1 for a in assets if a.approved
                             and "video" not in (a.asset_class or "")))
        if key == "video_in_gallery":
            return 1.0 if any(a.approved and "video" in (a.asset_class or "")
                              for a in assets) else 0.0
        if key == "size_options":
            product = s.scalar(select(Product).where(Product.slug == slug))
            pv = None if product is None else s.scalar(
                select(PatternVersion).where(PatternVersion.product_id == product.id,
                                             PatternVersion.version == version))
            if pv is None:
                return None
            sizes = (pv.cir_json or {}).get("sizes")
            return float(len(sizes)) if isinstance(sizes, list) and sizes else 1.0
    return None


def standards_gate(db, *, slug: str, version: str) -> dict:
    """The owner's veto, the moving competitive bar and the teardown requirements, at publish.

    Three standards that were recorded and read by nothing (#220, #228, #153-#160):

    - an **owner veto** (#228) on this product blocks its publication until the owner rules
      otherwise -- the latest ruling on the subject decides;
    - every **CompetitiveStandard** a benchmark has raised (#220) is compared with this
      listing's own reading: below the bar blocks, and a bar this listing cannot be measured
      against blocks too, because unmeasured is never passing;
    - every binding **teardown requirement** (`teardown.enforce`) for the PDF, the premium
      standard, the delivery bundle, video and support is checked against our own product.
    """
    from sqlalchemy import select

    from ..core.models import CompetitiveStandard
    from ..intel import mission_runtime
    from ..teardown import enforce

    reasons: list[str] = []
    veto = mission_runtime.active_veto(db, slug)
    if veto["vetoed"]:
        reasons.append(f"owner veto (#228): {veto['why']}")

    competitive = []
    with db.session() as s:
        bars = [(r.key, r.value, r.higher_is_better) for r in s.scalars(
            select(CompetitiveStandard)) if r.value is not None]
    for key, value, higher in bars:
        ours = our_competitive_reading(db, slug=slug, version=version, key=key)
        if ours is None:
            verdict = "unmeasured"
        else:
            verdict = "met" if (ours >= value if higher else ours <= value) else "below"
        competitive.append({"standard": key, "bar": value, "ours": ours, "verdict": verdict})
        if verdict != "met":
            reasons.append(f"competitive standard {key} (#220): bar {value}, ours "
                           f"{ours if ours is not None else 'unmeasured'}")

    teardown = enforce.check(db, slug, consumers=enforce.PUBLISH_CONSUMERS)
    reasons.extend(teardown["reasons"])
    return {"reasons": reasons, "blocks": bool(reasons), "veto": veto,
            "competitive": competitive,
            "teardown": {k: teardown[k] for k in ("requirements", "met", "unmet",
                                                  "unmeasured", "provisional", "blocks")}}


def for_marketing(db, *, slug: str, version: str, today: date | None = None,
                  positioning: str | None = None) -> dict:
    """What marketing.schedule must refuse on: a halted or stale product, or a missed window."""
    stale = staleness(db, slug=slug)
    window = window_decision(db, slug=slug, version=version, today=today,
                             positioning=positioning)
    reasons = list(stale["reasons"])
    if not window["may_launch_seasonally"]:
        reasons.append(f"missed window (#297): {window['action']} -- {window['why']}")
    return {"slug": slug, "version": version, "blocks": bool(reasons), "reasons": reasons,
            "staleness": stale, "window": window,
            # the marketing rebuild may proceed exactly when its own stale content is the
            # only block: nothing halted, the window open, only marketing_asset outstanding
            "only_own_marketing_stale": (stale["outstanding_only_marketing"]
                                         and bool(window["may_launch_seasonally"]))}


# ---- D-OWNER-FLUX-GALLERY: the generated-gallery listing set --------------------------------

def generated_selection(db, slug: str, version: str) -> dict | None:
    """The generated gallery `visual.gallery_persist` selected for this release, or None.

    Written only after every frame passed every gate there; it names each frame's position,
    role and sha256 and the deterministic CONTENTS frame. A withdrawn selection (`withdrawn`)
    is no selection."""
    det = _audit_detail(db, SELECTED_ACTION, f"{slug}@{version}")
    if not det or det.get("route") != el.GALLERY_ROUTE or det.get("withdrawn"):
        return None
    return det


def certified_contents_frame(db, slug: str, version: str, store_root=None) -> dict:
    """The download-information frame: the CONTENTS pattern preview the deterministic path
    built from the certified PDF, re-verified on its bytes now (`check_supplement`), with the
    alt text it is certified with. Never generated. Status PASS / FAIL / UNMEASURED."""
    from sqlalchemy import desc, select

    from ..core.artifacts import ArtifactMissing, ArtifactStore
    from ..core.models import ListingSetCertificateRecord
    from ..visual import launch_imagery as LI

    with db.session() as s:
        rows = list(s.scalars(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.version == version)
            .order_by(desc(ListingSetCertificateRecord.id))))
        found = None
        for r in rows:
            for f in (r.certificate or {}).get("frames") or []:
                if f.get("job") == el.CONTENTS and f.get("kind") == ls.DISCLOSED_SUPPLEMENT:
                    found = dict(f)
                    break
            if found:
                break
    if not found:
        return {"status": "UNMEASURED", "why": "no certified CONTENTS (download information) "
                "preview is on file for this release: assets.build has not certified the "
                "pattern-preview frame", "owner": "publishing (assets.build)"}
    try:
        data = ArtifactStore(store_root).get(found["sha256"], db=db)
    except (ArtifactMissing, OSError) as e:
        return {"status": "UNMEASURED", "why": f"CONTENTS preview bytes unreadable: {e}"[:300],
                "owner": "publishing (assets.build)"}
    verdict = LI.check_supplement(slug, version, el.CONTENTS, data, db=db,
                                  store=ArtifactStore(store_root))
    want_alt = LI.expected_alt_text(slug, el.CONTENTS)
    if verdict.get("status") != "PASS":
        return {"status": "FAIL" if verdict.get("status") == "FAIL" else "UNMEASURED",
                "why": f"CONTENTS preview re-verification: {verdict.get('why')}"[:300],
                "owner": "publishing (assets.build)"}
    if found.get("alt_text") != want_alt:
        return {"status": "FAIL", "why": "the CONTENTS preview's certified alt text is not the "
                "one it is certified with today", "owner": "publishing (assets.build)"}
    return {"status": "PASS", "why": "certified pattern preview, re-verified on its bytes",
            "frame": found, "data": data}


def _gallery_alt_text(job: str) -> str:
    from .disclosed_listing import ALT_TEXT_MAX

    what = {el.DESIRE: "the finished piece", el.COLOUR_CONTEXT: "full view of the finished piece",
            el.LIFESTYLE: "the finished piece in use", el.ANGLE: "another angle of the piece",
            el.DETAIL: "stitch close-up", el.SCALE: "the finished piece showing its size"}
    return f"{el.CONCEPT_LABEL}. {what.get(job, job.lower())}."[:ALT_TEXT_MAX]


class _Shown:
    """A frame as `mobile_contexts` reads it: a position and the bytes' hash."""

    def __init__(self, position: int, sha256: str):
        self.position, self.sha256 = position, sha256


def generated_listing_set(db, *, slug: str, version: str, cir, twin, listing, selection: dict,
                          frames, release_hash: str | None, issue: bool, store_root=None,
                          store_renders: bool = False) -> dict:
    """The selected generated gallery through the four gates and the set checks, and a
    listing-set certificate only when every frame and every set check passed.

    Each generated frame is judged by `generated_frame_verdict` on its own candidate record
    (identity, outfit, motif and product fidelity, anatomy, realism, quality, provenance, the
    route's exception). The CONTENTS frame is the deterministic preview, re-verified now. The
    set: one job per frame (#65), the seven-frame standard, mobile contexts (#66) and the
    dimension audit (#60). Anything not run, unreadable or UNMEASURED blocks."""
    from ..gates.asset_truth import AssetClass
    from ..gates.platform_policy import policy_stamp
    from ..gates.policy import POLICY_VERSION
    from ..visual import shot_plans as SP

    reasons: list[str] = []
    by_pos = {f.position: f for f in frames}
    selected = sorted(selection.get("frames") or [], key=lambda x: int(x["position"]))
    chosen = []
    per_frame: list[dict] = []
    for sel in selected:
        f = by_pos.get(int(sel.get("stored_position") or sel["position"]))
        if f is None or f.sha256 != sel.get("sha256") or not is_gallery_route_frame(f):
            why = (f"frame {sel['position']} ({sel.get('role')}): the selected bytes "
                   f"{str(sel.get('sha256'))[:12]} are not on file as a generated-gallery frame")
            per_frame.append({"position": int(sel["position"]), "role": sel.get("role"),
                              "sha256": sel.get("sha256"), "may_export": False, "why": why,
                              "blockers": [why], "job": "", "gates": {}})
            continue
        chosen.append(f)
        v = generated_frame_verdict(db, slug, version, f)
        # judged on its stored row; placed at its listing position
        per_frame.append({**v, "position": int(sel["position"]),
                          "asset_id": _asset_id(slug, int(sel["position"]))})
    # assets.build's own build-side rows are not listing frames on this path (as on the
    # disclosed path); another generated-gallery frame not in the selection is a mixed set.
    taken = {int(x.get("stored_position") or x["position"]) for x in selected}
    strays = sorted(p for p, f in by_pos.items() if is_gallery_route_frame(f) and p not in taken)
    if strays:
        reasons.append(f"generated-gallery frames at {strays} are on file but not part of "
                       f"the selected gallery; a mixed set is not certified on this path")
    contents = certified_contents_frame(db, slug, version, store_root=store_root)
    cpos = int((selection.get("contents") or {}).get("position") or len(selected) + 1)
    if contents["status"] != "PASS":
        reasons.append(f"download-information frame (CONTENTS): {contents['status']}: "
                       f"{contents['why']}")
    candidates = []
    for v in per_frame:
        job = (GENERATED_ROLE_JOBS.get(v.get("role") or "") or ("", ""))[0]
        if job:
            candidates.append(el.Candidate(asset_id=_asset_id(slug, v["position"]),
                                           medium=AssetClass.AI_LIFESTYLE_CONCEPT,
                                           purpose=el.CONVERSION_CREATIVE, job=job,
                                           position=v["position"]))
    candidates.append(el.Candidate(asset_id=_asset_id(slug, cpos),
                                   medium=AssetClass.PATTERN_PREVIEW,
                                   purpose=el.CUSTOMER_INFORMATION, job=el.CONTENTS,
                                   position=cpos))
    frame_set = el.check_set(candidates)
    standard = SP.campaign_standard({"roles": [{"job": c.job} for c in candidates]})
    if not frame_set["ok"]:
        reasons.append("frame set (#65): " + "; ".join(p.get("kind", "?")
                                                        for p in frame_set["problems"])[:300])
    if not standard["ok"]:
        reasons.append(f"seven-frame campaign standard: {standard['problems']}")
    shown = [_Shown(v["position"], v.get("sha256") or "") for v in per_frame]
    if contents["status"] == "PASS":
        shown.append(_Shown(cpos, contents["frame"]["sha256"]))
    mob = mobile_contexts(db, slug=slug, version=version, frames=shown, candidates=candidates,
                          store_root=store_root, store_renders=store_renders)
    if not mob.get("ok"):
        reasons.append(f"mobile QA (#66): {mob.get('why') or mob.get('not_rendered')}")
    dim = dimension_audit(db, slug=slug, version=version, twin=twin, frames=[],
                          listing=listing)
    if not dim["ok"]:
        reasons.append("dimensions (#60): " + "; ".join(
            f"{p['kind']} at {p.get('where')}" for p in dim["problems"])[:400])
    refused = [v for v in per_frame if not v.get("may_export")]
    if refused:
        reasons.append(f"generated frames: {len(refused)} may not export -- " + "; ".join(
            f"{v['position']}: {str(v.get('why'))[:160]}" for v in refused[:4]))
    if listing is None:
        reasons.append("no listing copy is drafted; the listing set cannot be certified")

    geometry = geometry_of(twin, cir)
    claims = claims_of(listing, chosen, _search_profile(db, slug, version))
    rechecked = recheck(db, slug=slug, version=version, geometry=geometry, claims=claims,
                        policy_version=POLICY_VERSION)
    cert: dict
    if reasons:
        cert = {"valid": False, "issued": False, "rechecked": rechecked,
                "why": "no generated-gallery certificate while any frame or set check above "
                       "fails or is unmeasured"}
    else:
        certified = []
        for v in per_frame:
            job = GENERATED_ROLE_JOBS[v["role"]][0]
            certified.append(ls.CertifiedFrame(
                position=v["position"], asset_id=_asset_id(slug, v["position"]),
                sha256=v["sha256"], job=job, purpose=el.CONVERSION_CREATIVE,
                medium=AssetClass.AI_LIFESTYLE_CONCEPT.value,
                honesty_label=el.honesty_label(AssetClass.AI_LIFESTYLE_CONCEPT, job)["label"],
                kind=GENERATED_RENDER_KIND, alt_text=_gallery_alt_text(job),
                represented_variant=cir.variant_key))
        cf = contents["frame"]
        certified.append(ls.CertifiedFrame(
            position=cpos, asset_id=cf.get("asset_id") or _asset_id(slug, cpos),
            sha256=cf["sha256"], job=el.CONTENTS, purpose=cf.get("purpose") or
            el.CUSTOMER_INFORMATION, medium=cf.get("medium") or ls.PREVIEW_MEDIUM,
            honesty_label=cf.get("honesty_label") or el.PREVIEW_LABEL,
            kind=ls.DISCLOSED_SUPPLEMENT, alt_text=cf.get("alt_text") or "",
            represented_variant=cf.get("represented_variant") or cir.variant_key))
        gate_results = {g: (el.PASSED if all(
            (v["gates"].get(g) or {}).get("outcome") == el.PASSED for v in per_frame)
            else el.FAILED) for g in el.GATES}
        try:
            certificate = ls.certify(
                slug=slug, version=version, frames=certified, gate_results=gate_results,
                geometry=geometry, claims=claims, policy_version=POLICY_VERSION,
                platform_policy=policy_stamp(db),
                disclosures=tuple(sorted({c.honesty_label for c in certified})),
                variant=cir.variant_key)
            cert = _record_certificate(db, certificate, release_hash=release_hash or "",
                                       issue=issue, rechecked=rechecked)
        except ls.ListingSetRefused as e:
            cert = {"valid": False, "issued": False, "rechecked": rechecked,
                    "why": str(e)[:400]}
        if not cert.get("valid"):
            reasons.append(f"listing-set certificate (#70): {cert.get('why')}")
    return {
        "slug": slug, "version": version, "kind": GENERATED_GALLERY,
        "blocks_release": bool(reasons), "reasons": reasons,
        "selection": {k: selection.get(k) for k in ("run_key", "route", "family")},
        "frames": [{k: v.get(k) for k in ("position", "role", "job", "may_export", "why")}
                   | {"gates": {g: o["outcome"] for g, o in (v.get("gates") or {}).items()}}
                   for v in per_frame],
        "contents": {k: contents.get(k) for k in ("status", "why")} | {"position": cpos},
        "frame_set": {k: frame_set.get(k) for k in ("ok", "jobs_covered", "problems")},
        "campaign_standard": standard,
        "dimensions": {k: dim[k] for k in ("ok", "problems", "sources", "displayed",
                                           "references")},
        "mobile": {k: mob.get(k) for k in ("ok", "complete", "not_rendered", "why",
                                           "title_safe_ink_by_position", "missing_bytes")}
                  | {"render_refs": {n: r.get("render_ref")
                                     for n, r in (mob.get("contexts") or {}).items()}},
        "certificate": cert,
    }
