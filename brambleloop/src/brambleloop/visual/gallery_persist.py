"""Approved gallery frames into `ListingAsset`, re-certified through `release_gates.listing_set`
(W-VISNEXT; OWNERIMG E5).

The order is fixed and nothing in it can be skipped:

1. The run must be `approved_for_publication`. `image_production.approve` only sets that when
   the owner approved the look AND no publication blocker remained.
2. Every generated frame on the card is re-verified now (`image_production.reverify`) with the
   production judges, and its publication verdict (`candidate_gates.publication_verdict`:
   F-852, the Etsy policy reading, Laura's publication status) must still be publishable.
   One refusal and nothing is written.
3. The frames are written as `ListingAsset` rows (class `AI_LIFESTYLE_CONCEPT`, never a
   photograph) at their shot-plan positions. A position already holding different bytes is
   never overwritten.
4. `release_gates.listing_set` re-judges the whole set and decides whether a listing-set
   certificate is issued. Its four gates and F-852 run unchanged on the new rows.

Today step 2 always refuses: F-852 refuses generated product imagery in every role, and the
Etsy listing-image policy is UNKNOWN. So this path is wired and tested, and it writes nothing.
Experiments never reach it (`experiment.refuse_if_experiment`).
"""
from __future__ import annotations

from . import candidate_gates as CG

SOURCE = "visual.image_production"
ASSET_CLASS = "AI_LIFESTYLE_CONCEPT"


def _frames_of(card: dict) -> list[dict]:
    return [{"position": r["position"], "role": r["role"], "job": r.get("job"),
             "candidate_id": (r.get("candidate") or {}).get("candidate_id"),
             "sha256": (r.get("candidate") or {}).get("sha256")}
            for r in card.get("roles") or []
            if r.get("source") == "generated" and r.get("candidate")]


def persist_approved(db, key: str, *, judges=None, store_root=None) -> dict:
    from . import experiment as XP
    from . import image_production as IP
    from .image_records import ImageCandidate

    run = IP.get_run(db, key)
    if run is None:
        return {"persisted": False, "why": "no such run"}
    try:
        XP.refuse_if_experiment(db, run["slug"], run["version"], action="listing asset write")
    except XP.ExperimentRefused as exc:
        return {"persisted": False, "why": str(exc)}
    if (run.get("card") or {}).get("experiment"):
        return {"persisted": False, "why": f"{XP.LABEL}: experiments never write listing assets"}
    if run["state"] != "approved_for_publication":
        return {"persisted": False, "why": f"run is {run['status']}; only a gallery the owner "
                                           f"approved with no publication blocker is written"}
    frames = _frames_of(run.get("card") or {})
    if not frames:
        return {"persisted": False, "why": "the approved card has no generated frame"}
    judges = judges or CG.RealJudges(db)
    blockers = []
    for f in frames:
        got = IP.reverify(db, f["candidate_id"], judges=judges)
        with db.session() as s:
            row = s.get(ImageCandidate, f["candidate_id"])
            publishable = bool(row and row.publishable and row.technical_status == "PASS")
            pub = ((row.checks or {}).get("_publication") or {}) if row else {}
        if not got.get("reverified") or not publishable:
            blockers += [f"{f['role']}: {b}" for b in (pub.get("blockers") or
                                                      [got.get("why") or "not publishable"])]
    if blockers:
        return {"persisted": False, "why": "re-verification refused the frames; nothing written",
                "blockers": sorted(set(blockers))}
    written = write_frames(db, run["slug"], run["version"], frames, run_key=key)
    if written["refused"]:
        return {"persisted": False, "why": "a frame position already holds other bytes",
                **written}
    return {"persisted": True, **written,
            "listing_set": recertify(db, run["slug"], run["version"],
                                     positions=written["written"] + written["kept"],
                                     store_root=store_root)}


def _candidate_facts(s, candidate_id) -> dict:
    from .image_records import ImageCandidate

    row = s.get(ImageCandidate, int(candidate_id)) if candidate_id else None
    if row is None:
        return {}
    return {"provenance_kind": row.provenance_kind, "method": row.method,
            "provider": row.provider, "model": row.model, "cost_cad": row.cost_cad,
            "technical_status": row.technical_status, "run_key": row.run_key,
            "prompt_sha256": row.prompt_sha256, "sha256": row.sha256}


def write_frames(db, slug: str, version: str, frames: list[dict], *, run_key: str,
                 actor: str = "publishing") -> dict:
    """Write verified generated frames as `ListingAsset` rows, each with its provenance.

    Called only by `persist_approved` after its re-verification. Never overwrites other
    bytes. Every written frame gets an append-only audit row and a `visual_truth` provenance
    row whose lineage says what it is: AI-generated by image production (#36 kind
    `ai_generated_*`), never a photograph, with the provider, model, cost and the candidate
    it came from, keyed to the frame row and carrying the file's sha256. A frame whose
    candidate record does not match its bytes is refused rather than given a lineage."""
    from sqlalchemy import select

    from ..core.models import AuditLog, ListingAsset
    from ..ops import artefacts as provenance

    written, refused, kept = [], [], []
    with db.session() as s:
        for f in frames:
            row = s.scalar(select(ListingAsset).where(
                ListingAsset.product_slug == slug, ListingAsset.version == version,
                ListingAsset.position == f["position"]))
            if row is not None and row.sha256 == f["sha256"]:
                kept.append(f["position"])
                continue
            if row is not None:
                refused.append({"position": f["position"], "role": f["role"],
                                "why": f"position {f['position']} holds {str(row.sha256)[:12]} "
                                       f"({row.role}); a certified frame is never overwritten"})
                continue
            facts = _candidate_facts(s, f.get("candidate_id"))
            if not facts or facts["sha256"] != f["sha256"] or not str(
                    facts.get("provenance_kind") or "").startswith("ai_generated_"):
                refused.append({"position": f["position"], "role": f["role"],
                                "why": "no generated-candidate record matches these bytes; "
                                       "a frame without a truthful provenance is not written"})
                continue
            asset = ListingAsset(
                product_slug=slug, version=version, position=f["position"],
                asset_class=ASSET_CLASS, role=f["role"], sha256=f["sha256"],
                claims={"source": SOURCE, "run_key": run_key, "candidate_id": f["candidate_id"],
                        "job": f.get("job"), "is_photograph": False,
                        "provenance_kind": facts["provenance_kind"],
                        "label": "AI-generated concept image"},
                approved=True, blocked_reasons=[])
            s.add(asset)
            s.flush()
            audit = AuditLog(actor=str(actor)[:64], action="images.listing_asset_written",
                             artifact=f"{slug}@{version}#{asset.id}",
                             detail={"candidate_id": f["candidate_id"], "run_key": run_key,
                                     "sha256": f["sha256"], "position": f["position"],
                                     "provenance_kind": facts["provenance_kind"]})
            s.add(audit)
            s.flush()
            provenance.record_lineage(
                s, artefact_class="visual_truth",
                artefact_key=provenance.visual_key(slug, version, asset.id),
                product_slug=slug,
                inputs={f"asset:image_candidate_{int(f['candidate_id'])}": f["sha256"]},
                lineage=provenance.Lineage(
                    created_by=str(actor)[:64], model=str(facts.get("model") or "")[:80],
                    provider=str(facts.get("provider") or "")[:40],
                    cost_cad=facts.get("cost_cad"), sha256=f["sha256"],
                    validation_status="reverified", source="backfilled",
                    evidence={"matched_on": "image_candidates.sha256 == listing_assets.sha256",
                              "audit_id": audit.id, "candidate_id": f["candidate_id"],
                              "run_key": run_key, "kind": facts["provenance_kind"],
                              "method": facts.get("method"), "is_photograph": False,
                              "technical_status": facts.get("technical_status")}))
            written.append(f["position"])
        if refused:
            s.rollback()
            written = []
    return {"written": written, "kept": kept, "refused": refused}


def recertify(db, slug: str, version: str, *, positions=(), store_root=None) -> dict:
    """`release_gates.listing_set` on the set as it now stands; its verdict is the answer.

    When the listing's imagery is the disclosed render set (D-FB-7), `listing_set` certifies
    that set and does not judge `ListingAsset` frames at all. A generated frame then is NOT
    part of any certificate, and this says so (`generated_frames_judged: False`) rather than
    reading the disclosed certificate as covering it."""
    from ..publish import release_gates

    out = release_gates.listing_set(db, slug=slug, version=version, store_root=store_root,
                                    issue=True)
    frames = [f for f in out.get("frames") or [] if f.get("position") in set(positions)]
    judged = bool(frames)
    reasons = list(out.get("reasons") or [])
    if positions and not judged:
        reasons.append("the generated frames were not judged by the listing-set path in use "
                       "(the disclosed render set is certified on its own); they are not "
                       "part of any certificate")
    return {"blocks_release": bool(out.get("blocks_release")) or (bool(positions) and
                                                                 not judged),
            "reasons": reasons, "certificate": bool((out.get("certificate") or {}).get("valid")) and judged,
            "generated_frames": frames, "generated_frames_judged": judged}
