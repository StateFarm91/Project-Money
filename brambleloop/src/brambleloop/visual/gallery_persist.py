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


def write_frames(db, slug: str, version: str, frames: list[dict], *, run_key: str) -> dict:
    """Write verified generated frames as `ListingAsset` rows. Called only by
    `persist_approved` after its re-verification. Never overwrites other bytes."""
    from sqlalchemy import select

    from ..core.models import ListingAsset

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
            s.add(ListingAsset(product_slug=slug, version=version, position=f["position"],
                               asset_class=ASSET_CLASS, role=f["role"], sha256=f["sha256"],
                               claims={"source": SOURCE, "run_key": run_key,
                                       "candidate_id": f["candidate_id"], "job": f.get("job"),
                                       "is_photograph": False,
                                       "label": "AI-generated concept image"},
                               approved=True, blocked_reasons=[]))
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
