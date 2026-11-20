"""Recovery first: an image already generated for this release is re-checked before any new
one is bought (D-OWNER-FLUX-GALLERY; owner: "Recover the backlog of existing paid images
before generating replacements").

`publish.motif_backlog` (eng/motif-backlog) recovers the owned / model photography renders
filed in the audit log. This covers the other store of paid images: `image_candidates` rows
written by `visual.image_production` (any earlier run of the same release, e.g. the campaign
run). Nothing here generates anything or calls the image provider.

For one slot of a generated-gallery run, before its first generation:

* candidates of the SAME product, version and release, listing and role are considered,
  paid ones first, newest first, at most MAX_CHECKS per slot;
* never an experiment image, never bytes with a negative decision (owner-rejected or a
  FAIL verdict), never bytes whose hash no longer matches;
* a Laura slot takes only a Laura frame in the run's reserved outfit (one outfit per listing),
  and a no-Laura slot only a frame without her;
* the bytes are judged again, now, under the route (`candidate_gates.evaluate` with
  `route`), so motif fidelity and the exception's evidence are read fresh. Only a technical
  PASS is recovered: it is recorded in this run (`method="recovered"`, `cost_cad=0.0`, with
  the source candidate and its original cost) and the slot is not generated. Anything else
  is noted in the run's `_recovery` record and the slot is generated as usual.
"""
from __future__ import annotations

import hashlib

METHOD = "recovered"
MAX_CHECKS = 3          # prior images re-judged per slot before a new one is bought


def candidates(db, *, key: str, slug: str, version: str, release: str, listing: str,
               role: str, laura: bool, outfit_id: str | None) -> list:
    from sqlalchemy import func, select

    from .experiment import is_experiment_image
    from .image_production import _image_has_negative_decision
    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        rows = list(s.scalars(select(ImageCandidate).where(
            ImageCandidate.slug == slug, ImageCandidate.version == version,
            func.lower(ImageCandidate.release) == str(release).lower(),
            ImageCandidate.listing == listing, ImageCandidate.role == role,
            ImageCandidate.run_key != key, ImageCandidate.sha256 != "")
            .order_by(ImageCandidate.id.desc()).limit(50)))
        for r in rows:
            s.expunge(r)
    out, seen = [], set()
    for r in sorted(rows, key=lambda r: (-(float(r.cost_cad or 0) > 0), -r.id)):
        if r.sha256 in seen or "#" in str(r.run_key or ""):
            continue
        seen.add(r.sha256)
        if bool(r.laura_present) != bool(laura):
            continue
        if laura and (not outfit_id or r.outfit_id != outfit_id):
            continue
        if not str(r.provenance_kind or "").startswith("ai_generated_"):
            continue
        if is_experiment_image(db, r.sha256) or _image_has_negative_decision(
                db, slug=slug, version=version, sha=r.sha256):
            continue
        out.append(r)
    return out[:MAX_CHECKS]


def recover(db, key: str, *, slug: str, version: str, release: str, listing: str,
            role: str, laura: bool, outfit_id: str | None, judges, route: str,
            stage: str) -> dict | None:
    """Recover one prior image into this run for `role`, or None (then generate)."""
    from ..core.artifacts import ArtifactStore
    from . import candidate_gates as CG
    from . import image_production as IP

    tried = []
    found = None
    for r in candidates(db, key=key, slug=slug, version=version, release=release,
                        listing=listing, role=role, laura=laura, outfit_id=outfit_id):
        try:
            data = ArtifactStore().get(r.sha256, db=db)
        except Exception as exc:  # noqa: BLE001 - lost bytes are not recoverable
            tried.append({"candidate_id": r.id, "result": f"bytes unavailable "
                                                         f"({type(exc).__name__})"})
            continue
        if hashlib.sha256(data).hexdigest() != r.sha256:
            tried.append({"candidate_id": r.id, "result": "bytes changed"})
            continue
        checks = dict(r.checks or {})
        cand = {"slug": slug, "version": version, "release": release, "run_key": key,
                "role": role, "provider": r.provider, "model": r.model, "prompt": r.prompt,
                "references": list(r.references or []), "laura_present": bool(r.laura_present),
                "outfit_id": r.outfit_id or None, "listing": listing,
                "provenance_kind": r.provenance_kind, "prompt_version": r.prompt_version,
                "identity_evidence": checks.get("_identity_evidence") or {},
                "route": route, "data": data, "sha256": r.sha256, "cost_cad": 0.0,
                "cost_basis": f"recovered: candidate {r.id} (originally CA${r.cost_cad or 0})",
                "latency_s": 0.0}
        verdict = CG.evaluate(db, cand, judges=judges, record_outfit_use=bool(laura))
        tried.append({"candidate_id": r.id, "result": verdict["technical_status"]})
        if verdict["technical_status"] != CG.PASS:
            continue
        verdict = {**verdict, "checks": {**verdict["checks"], "_recovered": {
            "from_candidate": r.id, "from_run": r.run_key, "original_cost_cad": r.cost_cad,
            "rejudged_under_route": route}}}
        rec = IP.record_candidate(db, cand, verdict, method=METHOD, run=key, stage=stage,
                                  attempt=1)
        found = {**rec, "technical_status": verdict["technical_status"],
                 "publishable": verdict["publishable"], "cost_cad": 0.0, "attempt": 1,
                 "recovered_from": r.id}
        break
    _note(db, key, role, tried, found)
    return found


def _note(db, key: str, role: str, tried: list, found: dict | None) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    from .image_production import _run_locked

    if not tried:
        return
    with db.session() as s:
        r = _run_locked(s, key)
        st = dict(r.stages or {})
        rec = dict(st.get("_recovery") or {})
        rec[role] = {"tried": tried, "recovered": (found or {}).get("candidate_id")}
        st["_recovery"] = rec
        r.stages = st
        flag_modified(r, "stages")


def already(db, key: str, role: str) -> dict | None:
    """The image already recovered into this run for `role` (a retried job never buys one)."""
    from sqlalchemy import select

    from .image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        r = s.scalar(select(ImageCandidate).where(
            ImageCandidate.run_key == key, ImageCandidate.role == role,
            ImageCandidate.method == METHOD).order_by(ImageCandidate.id.desc()).limit(1))
        if r is None:
            return None
        return {"candidate_id": r.id, "sha256": r.sha256, "outcome": r.outcome,
                "technical_status": r.technical_status, "publishable": r.publishable,
                "cost_cad": 0.0, "attempt": r.attempt,
                "recovered_from": ((r.checks or {}).get("_recovered") or {}).get(
                    "from_candidate")}
