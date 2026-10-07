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
}

# The component the finished-size numbers describe. One per product today: every listing
# quotes the whole piece.
FINISHED = "finished piece"

_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:cm\s*)?[x×]\s*(\d+(?:\.\d+)?)\s*cm")


def _asset_id(slug: str, position: int) -> str:
    return f"{slug}-frame-{position}"


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
    return rows


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
                store_renders: bool = False) -> dict:
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

    current_asset = listing_asset.last(db, slug=slug)
    if (current_asset and current_asset.get("kind") == ls.DISCLOSED_RENDER
            and current_asset.get("version") == version):
        return disclosed_listing_set(db, slug=slug, version=version, cir=cir, twin=twin,
                                     listing=listing, rec=current_asset, frames=frames,
                                     release_hash=release_hash, issue=issue,
                                     store_root=store_root)

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


def disclosed_listing_set(db, *, slug: str, version: str, cir, twin, listing, rec: dict,
                          frames, release_hash: str | None, issue: bool,
                          store_root=None) -> dict:
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
                              release_fingerprint=getattr(cir, "fingerprint", "") or "")
        if images else ([], None, {}))
    gate_results = ls.disclosed_gate_results(rec, exported=bool(images) and not any(
        r.startswith("disclosed export") for r in reasons), dimensions_ok=dim["ok"],
        supplement_qa=supplement_qa if supplements else None)

    geometry = geometry_of(twin, cir)
    claims = claims_of(listing, frames, _search_profile(db, slug, version))
    rechecked = recheck(db, slug=slug, version=version, geometry=geometry, claims=claims,
                        policy_version=POLICY_VERSION)
    cert: dict
    try:
        certificate = ls.certify_disclosed(
            slug=slug, version=version, rec=rec, images=images, geometry=geometry,
            claims=claims, policy_version=POLICY_VERSION, platform_policy=policy_stamp(db),
            dimensions_ok=dim["ok"],
            # F-757 / PT-13: the configuration the certified release encodes is what the
            # listing sells; the set must have been rendered for it.
            listing_variant=cir.variant_key, supplements=supplements,
            supplement_qa=supplement_qa) if not reasons else None
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
        "certificate": cert,
    }


def disclosed_supplements(rec: dict, images: list, *, slug: str, version: str,
                          store_root=None, release_fingerprint: str | None = None
                          ) -> tuple[list, dict | None, dict]:
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
                                               release_fingerprint=release_fingerprint)
    except Exception as exc:  # noqa: BLE001 - no supplements is a coverage gap, not a block
        return [], None, {"*": f"{type(exc).__name__}: {exc}"[:300]}
    notes = dict(offer.get("refused") or {})
    base = [Image.open(_io.BytesIO(data)).convert("RGB") for _n, data, _a in images]

    class _F:
        def __init__(self, image, position):
            self.image, self.position = image, position

    kept = []
    for f in offer.get("frames") or []:
        img = Image.open(_io.BytesIO(f["png"])).convert("RGB")
        report = layout_qa.inspect(img, position=f["position"], expect_text=True)
        if report.problems:
            notes[f["job"]] = "layout QA: " + "; ".join(report.problems)[:280]
            continue
        kept.append((f, img))
    supplements: list = []
    for i, (f, _img) in enumerate(kept):
        supplements.append(ls.CertifiedFrame(
            position=len(images) + 1 + i, asset_id=f"{slug}-gallery-{f['job'].lower()}",
            sha256=f["sha256"], job=f["job"], purpose=f["purpose"],
            medium=AssetClass.DIGITAL_TWIN_RENDER.value,
            honesty_label=ls_disclosure(), kind=ls.DISCLOSED_SUPPLEMENT,
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
    candidates += [el.Candidate(asset_id=c.asset_id, medium=AssetClass.DIGITAL_TWIN_RENDER,
                                purpose=c.purpose, job=c.job, position=c.position)
                   for c in supplements]
    frame_set = el.check_set(candidates)
    qa = {"verified": [True] * len(supplements),
          "layout_qa": {"ok": not layout, "problems": layout},
          "frame_set": {"ok": frame_set["ok"], "problems": frame_set["problems"]}}
    return supplements, qa, notes


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
    with db.session() as s:
        current = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == cert.slug,
            ListingSetCertificateRecord.version == cert.version,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        if current is not None:
            on_file = {f["position"]: f["sha256"]
                       for f in (current.certificate or {}).get("frames", [])}
            if on_file == hashes:
                return {"valid": True, "issued": False, "record_id": current.id,
                        "rechecked": rechecked,
                        "why": "a valid certificate covers exactly these frame hashes"}
            current.state = "superseded"
            current.invalidated_by = ["frame_hashes_changed"]
            current.invalidated_at = datetime.now(timezone.utc)
    if not issue:
        return {"valid": False, "issued": False, "rechecked": rechecked,
                "why": "no valid certificate covers these frames and issuing was not asked"}
    with db.session() as s:
        rec = ListingSetCertificateRecord(
            product_slug=cert.slug, version=cert.version, release_hash=release_hash,
            certificate=cert.to_dict(), geometry_fingerprint=cert.geometry_fingerprint,
            claims_fingerprint=cert.claims_fingerprint, policy_version=cert.policy_version,
            state="valid")
        s.add(rec)
        s.flush()
        rid = rec.id
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

    results = []
    with db.session() as s:
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
                positions = {f["asset_id"]: f["position"]
                             for f in (rec.certificate or {}).get("frames", [])}
                for asset_id in verdict["affected_assets"]:
                    pos = positions.get(asset_id)
                    row = s.scalar(select(ListingAsset).where(
                        ListingAsset.product_slug == slug, ListingAsset.version == version,
                        ListingAsset.position == pos)) if pos else None
                    if row is not None:
                        row.approved = False
                        row.blocked_reasons = [
                            f"LISTING_SET_INVALIDATED: certificate {rec.id} invalidated by "
                            f"{', '.join(verdict['invalidated_by'])}; re-certify before "
                            f"export"] + list(row.blocked_reasons or [])[:9]
            results.append(verdict)
    return results


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
    with db.session() as s:
        current = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.version == version,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        if current is not None:
            on_file = {f["position"]: f["sha256"]
                       for f in (current.certificate or {}).get("frames", [])}
            if on_file == hashes:
                return {"valid": True, "issued": False, "record_id": current.id,
                        "rechecked": rechecked,
                        "why": "a valid certificate covers exactly these frame hashes"}
            current.state = "superseded"
            current.invalidated_by = ["frame_hashes_changed"]
            current.invalidated_at = datetime.now(timezone.utc)

    if not issue:
        return {"valid": False, "issued": False, "rechecked": rechecked,
                "why": ("no valid certificate covers these frames, and one is not issued "
                        "while any gate above is failing or has not run")}

    certified = []
    for f in frames:
        job, purpose = ROLE_JOBS[f.role]
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
        rec = ListingSetCertificateRecord(
            product_slug=slug, version=version, release_hash=release_hash,
            certificate=cert.to_dict(), geometry_fingerprint=cert.geometry_fingerprint,
            claims_fingerprint=cert.claims_fingerprint, policy_version=cert.policy_version,
            state="valid")
        s.add(rec)
        s.flush()
        rid = rec.id
    return {"valid": True, "issued": True, "record_id": rid, "rechecked": rechecked,
            "frame_order": list(cert.frame_order),
            "why": "every frame passed all four gates; certificate issued"}


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
    only_marketing = (bool(outstanding) and not halting
                      and all(str(k).startswith("marketing_asset:") for k in outstanding))
    return {"halted": bool(halting), "incidents": halting[:5], "rebuild": graph,
            "policy_changes_unreviewed": [c["source"] for c in policy],
            "blocks": bool(reasons), "reasons": reasons,
            "outstanding_only_marketing": only_marketing}


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


def for_publish(db, *, slug: str, version: str, today: date | None = None,
                positioning: str | None = None, store_root=None) -> dict:
    """Everything store.publish must refuse on, computed once and returned as one verdict."""
    stale = staleness(db, slug=slug)
    window = window_decision(db, slug=slug, version=version, today=today,
                             positioning=positioning)
    set_verdict = listing_set(db, slug=slug, version=version, store_root=store_root,
                              issue=not stale["blocks"] and window["may_launch_seasonally"])
    reasons = list(stale["reasons"])
    originality = originality_gate(db, slug=slug, version=version, store_root=store_root)
    reasons.extend(originality["reasons"])
    if not window["may_launch_seasonally"]:
        reasons.append(f"missed window (#297): {window['action']} -- {window['why']}")
    reasons.extend(set_verdict["reasons"])
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
    # F-111 / F-118 / F-120 (cluster C): the product-level scope -- legacy quarantine, and
    # for a Launch-0 slug the first customer's nine-area gate -- decided in one place.
    from . import eligibility

    row = _listing(db, slug, version)
    scope = eligibility.product_publication(
        db, slug, version,
        listing=(None if row is None else
                 {"title": row.title, "description": row.description,
                  "tags": list(row.tags or []), "price_cad": row.price_cad}))
    reasons.extend(f"{r['code']}: {r['why']}" for r in scope["reasons"])
    return {"slug": slug, "version": version, "blocks_release": bool(reasons),
            "reasons": reasons, "staleness": stale, "window": window,
            "listing_set": set_verdict, "search": search, "standards": standards,
            "withholding": held, "publication_scope": scope, "originality": originality}


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
