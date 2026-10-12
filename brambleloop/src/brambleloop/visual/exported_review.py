"""#61 Visual Semantic QA on the frames a disclosed listing actually exports.

`release._review_frames` reviews the frames `assets.build` stores as `ListingAsset` rows, and
the publish path reads `release.frame_review_state` over those rows. A Launch-0 listing under
D-FB-7 does not upload those frames, though. It uploads the listing-set certificate's
disclosed set plus its verified gallery supplements (`runtime.etsy_ops.certified_images`,
the only upload path). So the frames a buyer sees were never semantically reviewed, and the
frames that were reviewed are never shown. This module reviews the exported set.

* Each certified frame's exact upload bytes are described blind (`inspect.describe_image`,
  one budgeted call; realism is not applicable to a disclosed render, D-FB-9). Deterministic
  code then compares the description against the claim registered for the frame's job. A
  job with no registered claim is UNCLAIMED and blocks (the C-80 rule): a frame compared
  against nothing passes by having nothing to fail.
* The first image (DESIRE) also needs the CIR's product family and the 230 px grid reading
  (F-027 / F-031).
* The review is filed with the sha256 of every exported frame. `review_state` counts it only
  while it covers exactly the frames the certificate exports now, every one `clear`.
  Unreviewed, unjudged, unclaimed or a stale set is not reviewed.
It runs only while the `image_vision` gate is open; otherwise nothing is called.
"""
from __future__ import annotations

ACTION = "visual.exported_frame_review"

# What each certified job claims, in `inspect.compare`'s closed vocabulary.
JOB_CLAIMS: dict[str, dict] = {
    "DESIRE": {"shows_finished_object": True},
    "ANGLE": {"shows_finished_object": True},
    "SCALE": {"shows_size_reference": True},
    "SIZING": {"shows_size_reference": True},
    "DETAIL": {"shows_text": True},           # stitch close-up, lettered with its rows
    "CONSTRUCTION": {"shows_text": True},     # stitch counts per round/row
    "COLOUR_CONTEXT": {"shows_text": True},   # each colour's share, lettered
    "MATERIALS": {"shows_text": True},        # yarn, hook, gauge
    "CONTENTS": {"shows_text": True},         # PDF pages
}
IDENTIFYING_JOBS = frozenset({"DESIRE", "ANGLE"})


def applies(db, slug: str, version: str) -> bool:
    """Whether this release exports a disclosed set (and so needs this review)."""
    from ..runtime.etsy_ops import certified_frames

    try:
        cert = certified_frames(db, slug, version)
    except Exception:  # noqa: BLE001 - no certificate: nothing exported, nothing to review
        return False
    return any(str(f.get("kind") or "").startswith("disclosed") for f in cert.get("frames") or [])


def review(db, slug: str, version: str, *, provider=None, gate_open: bool | None = None) -> dict:
    """Describe every exported frame blind and file the reading, bound to its bytes."""
    import os
    import shutil
    import tempfile

    from ..core.models import AuditLog
    from ..runtime.etsy_ops import certified_images
    from ..visual.render_verification import authoritative_cir
    from . import inspect as inspection_mod

    if gate_open is None:
        from .gallery import gates_now

        gate_open = bool(gates_now(db, keys=("image_vision",)).get("image_vision"))
    if not gate_open:
        return {"reviewed": False, "why": "image_vision gate closed: no model has been proven "
                                          "to look at a picture"}
    served = certified_images(db, slug, version)
    if served.get("problems") or not served.get("images"):
        return {"reviewed": False, "why": "the certified set cannot be served: "
                                          f"{(served.get('problems') or ['no images'])[:2]}"}
    families = inspection_mod.product_families(authoritative_cir(slug, version))
    frames: dict[str, dict] = {}
    tmp = tempfile.mkdtemp(prefix="exported_review_")
    try:
        for (name, data), row in zip(served["images"], served["order"]):
            job = str(row.get("job") or "")
            pos = str(row["position"])
            claim = JOB_CLAIMS.get(job)
            if claim is None:
                frames[pos] = {"job": job, "sha256": row["sha256"], "verdict": "unclaimed",
                               "why": f"no claim is registered for job {job!r} (#61)"}
                continue
            path = os.path.join(tmp, name)
            with open(path, "wb") as fh:
                fh.write(data)
            if job in IDENTIFYING_JOBS:
                claim = {**claim, "identifies_as": families}
            try:
                got = inspection_mod.describe_image(path, db=db, provider=provider, claim=claim)
            except Exception as exc:  # noqa: BLE001 - unmade, never passed
                got = {"described": False, "description_error": f"{type(exc).__name__}: {exc}"}
            sem = got.get("semantic") or {}
            if not got.get("described"):
                verdict, why = "unreviewed", str(got.get("description_error") or "")[:200]
            elif sem.get("problems"):
                verdict, why = "blocked", str(sem["problems"])[:300]
            elif job in IDENTIFYING_JOBS and sem.get("identified") is not True:
                verdict, why = "unjudged", "the product family was not established"
            else:
                verdict, why = "clear", "communicates its job's claim"
            entry = {"job": job, "sha256": row["sha256"], "verdict": verdict, "why": why,
                     "problems": sem.get("problems") or []}
            if job == "DESIRE" and verdict == "clear":
                grid = inspection_mod.identify_at_grid(path, families=families, db=db,
                                                       provider=provider)
                entry["grid"] = {k: grid.get(k) for k in ("verdict", "why", "grid_px")}
                if grid.get("verdict") != "clear":
                    entry["verdict"] = "blocked" if grid.get("verdict") == "blocked" \
                        else "unjudged"
                    entry["why"] = f"at grid size: {grid.get('why')}"[:300]
            frames[pos] = entry
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    detail = {"slug": slug, "version": version, "frames": frames,
              "frame_shas": {p: f["sha256"] for p, f in frames.items()},
              "certificate_record_id": served.get("record_id")}
    with db.session() as s:
        s.add(AuditLog(actor="quality_director", action=ACTION,
                       artifact=f"{slug}@{version}", detail=detail))
    bad = {p: f["verdict"] for p, f in frames.items() if f["verdict"] != "clear"}
    return {"reviewed": not bad and bool(frames), "not_clear": bad, **detail}


def review_state(db, slug: str, version: str) -> dict:
    """The latest exported-frame review, counted only when it covers exactly what is exported."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..runtime.etsy_ops import certified_frames

    if not applies(db, slug, version):
        return {"applies": False, "reviewed": True,
                "why": "this release exports no disclosed set; #61 is read from the stored "
                       "listing frames (release.frame_review_state)"}
    cert = certified_frames(db, slug, version)
    exported = {str(int(f.get("position") or 0)): str(f.get("sha256") or "")
                for f in cert.get("frames") or []}
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == ACTION,
                                              AuditLog.artifact == f"{slug}@{version}")
                       .order_by(desc(AuditLog.id)).limit(1))
        detail = dict(row.detail or {}) if row is not None else None
    if detail is None:
        return {"applies": True, "reviewed": False,
                "why": "the exported frames were never independently reviewed (#61)"}
    frames = detail.get("frames") or {}
    if not frames:
        return {"applies": True, "reviewed": False, "why": "an empty review is not a review"}
    if {str(k): v for k, v in (detail.get("frame_shas") or {}).items()} != exported:
        return {"applies": True, "reviewed": False,
                "why": "the review on record is not of the frames the certificate exports now"}
    bad = {p: f.get("verdict") for p, f in frames.items() if f.get("verdict") != "clear"}
    return {"applies": True, "reviewed": not bad, "not_clear": bad,
            "why": ("every exported frame was independently reviewed and communicates its "
                    "job" if not bad else f"exported frames not cleared (#61): {bad}")}
