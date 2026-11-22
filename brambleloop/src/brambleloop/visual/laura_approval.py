"""IMAGE-BF (finding B): the owner's production path to approve Laura in a generated gallery.

Before this, `canonical.PUBLICATION_APPROVED` was the only source of Laura publication
approval: an empty code constant. Every Laura frame read `laura_publication` UNMEASURED, so no
gallery with Laura could ever be certified in production.

The path (D-IMAGE-BF-LAURA):

1. **One card per gallery.** When a generated-gallery run is verified -- every frame gate and
   every set check passes, and the only thing standing is Laura's publication approval -- one
   OwnerAction card is raised for that gallery (`raise_card`). Its identity is the run and the
   digest of the exact Laura frame hashes, so a re-certification of the same gallery never
   raises a second card, and a gallery with different bytes is a different gallery. The card
   lists every Laura frame (position, role, candidate id, sha256, the image URL the Command
   Center serves the stored bytes from).
2. **The owner decides with the existing step-up.** `decide` is called only by the Command
   Center route `POST /api/cc/laura-gallery/decide` after `auth.require_stepup` (passphrase +
   TOTP), or by "Approve all eligible" (`approve_all.execute`, which needs the same fresh
   step-up). `decide` itself refuses a non-owner actor and a call that does not assert the
   step-up. It re-reads the gallery and refuses if the Laura frames changed since the card.
3. **Recorded per gallery and frame hash.** One `LauraGalleryApproval` row per frame, with the
   decision, the actor, the step-up, the route and the session. `approved` reads True for
   exactly those (run, hash) pairs; anything else stays UNMEASURED.
4. **Audited.** `laura_gallery.card_raised`, `laura_gallery.decision` and the OwnerAction
   lifecycle row. Nothing here infers approval: no sweep, no default, no other card.

Laura (laura-r2-a42aeac7) is LOCKED: nothing here modifies, regenerates or substitutes her. An
approval is the owner's look at the generated frames; it changes no identity, pack or gate.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

CARD_PREFIX = "laura_gallery_review:"
STEP_UP_ACTION = "laura_gallery.decide"
AUDIT_RAISED = "laura_gallery.card_raised"
AUDIT_DECIDED = "laura_gallery.decision"
APPROVED = "approved"
REJECTED = "rejected"
DECISIONS = (APPROVED, REJECTED)
IMAGE_URL = "/api/cc/images/candidates/{id}/image"
RULE = "D-IMAGE-BF-LAURA"


class Refused(ValueError):
    pass


def _now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def is_card(requirement_key: str | None) -> bool:
    return str(requirement_key or "").startswith(CARD_PREFIX)


def digest(frames: list[dict]) -> str:
    body = json.dumps(sorted([int(f["position"]), str(f["sha256"])] for f in frames),
                      separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def requirement_key(run_key: str, gallery_digest: str) -> str:
    # Hex only after the prefix: no run name can make the key read as something else.
    run = hashlib.sha256(run_key.encode()).hexdigest()[:16]
    return f"{CARD_PREFIX}{run}:{gallery_digest[:16]}"


# ---- the record the gates read ---------------------------------------------------------------

def approved(db, run_key: str | None, sha256: str | None) -> bool:
    """True only when the owner approved these exact bytes for this exact gallery run, and no
    later decision for the same (run, bytes) rejected them. Never inferred: no row, False."""
    if not run_key or not sha256:
        return False
    from sqlalchemy import select

    from .image_records import LauraGalleryApproval, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        last = s.scalar(select(LauraGalleryApproval).where(
            LauraGalleryApproval.run_key == str(run_key),
            LauraGalleryApproval.frame_sha256 == str(sha256).lower())
            .order_by(LauraGalleryApproval.id.desc()).limit(1))
        if last is None or last.decision != APPROVED:
            return False
        if last.step_up:
            return True
        # D-OWNER-APPROVE-ALL-3: an approval written by the owner's standing directive (its
        # recognised actor, no step-up) counts too; any other unstepped row does not.
        from ..ops import approve_all_directive as _AD

        return str(last.decided_by or "") == _AD.ACTOR


def publication_status(db, sha256: str | None, run_key: str | None) -> str:
    """`canonical.asset_status` for a generated Laura frame, with the owner's gallery approval.

    The global registry (`canonical.PUBLICATION_APPROVED`) still wins first; otherwise these
    bytes read `publication_approved` only with an owner approval for this run."""
    from . import canonical

    status = canonical.asset_status(sha256 or "")
    if status == canonical.PUBLICATION_APPROVED_STATUS:
        return status
    if db is not None and approved(db, run_key, sha256):
        return canonical.PUBLICATION_APPROVED_STATUS
    return status


# ---- the card --------------------------------------------------------------------------------

def laura_frames(st: dict) -> list[dict]:
    """The Laura frames of a gallery status (`gallery_persist.gallery_status`)."""
    out = []
    for f in st.get("frames") or []:
        if f.get("deterministic") or not f.get("laura_present") or not f.get("sha256"):
            continue
        out.append({"position": int(f["position"]), "role": f.get("role") or "",
                    "candidate_id": f.get("candidate_id"), "sha256": str(f["sha256"]).lower(),
                    "image_url": IMAGE_URL.format(id=f.get("candidate_id"))})
    return sorted(out, key=lambda x: x["position"])


def verified_but_for_laura(db, run_key: str, st: dict) -> bool:
    """Every frame gate and set check passes except Laura's publication approval: the real
    status has blockers, and the same gallery judged as if Laura were approved has none."""
    from . import gallery_persist

    if st.get("ok") or not laura_frames(st):
        return False
    review = gallery_persist.gallery_status(db, run_key, review_only_assume_laura_approved=True)
    return bool(review.get("ok")) and digest(laura_frames(review)) == digest(laura_frames(st))


def raise_card(db, run_key: str, *, st: dict | None = None,
               now: datetime | None = None) -> dict:
    """Raise the one owner card for a verified generated gallery that contains Laura.

    Idempotent per gallery: a card already raised for this run and frame set (open or
    answered) is never raised again."""
    from sqlalchemy import select

    from ..core.models import AuditLog, OwnerAction
    from ..ops import owner_queue
    from . import gallery_persist

    now = _now(now)
    st = st if st is not None else gallery_persist.gallery_status(db, run_key)
    if not verified_but_for_laura(db, run_key, st):
        return {"raised": False, "why": "the gallery is not verified apart from Laura's "
                                        "publication approval"}
    frames = laura_frames(st)
    pending = [f for f in frames if not approved(db, run_key, f["sha256"])]
    if not pending:
        return {"raised": False, "why": "every Laura frame of this gallery is already approved"}
    dg = digest(frames)
    key = requirement_key(run_key, dg)
    with db.session() as s:
        existing = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key)
                            .order_by(OwnerAction.id).limit(1))
        if existing is not None:
            return {"raised": False, "requirement_key": key, "card_id": existing.id,
                    "why": "this gallery's card was already raised"}
        listing = f"{st.get('slug')}@{st.get('version')}"
        row = owner_queue.ensure(
            s, key,
            action=(f"Review Laura in the generated gallery for {listing} ({len(frames)} "
                    f"frame(s)) and approve or reject their publication"),
            reason=(f"Every frame and set check of gallery run {run_key} passed. Laura "
                    f"(locked identity) appears in {len(frames)} frame(s); her publication is "
                    f"the owner's decision and is never inferred ({RULE})."),
            max_cost_cad=0.0, minutes=3,
            consequence_of_delay=(f"{listing} keeps its gallery uncertified: the listing "
                                  f"cannot become ready for sale (D-OWNER-GALLERY-COMPLETE)"),
            blocks=f"{listing} generated-gallery certificate",
            why_software_cannot=("Laura's publication is an owner decision; software never "
                                 "approves it"))
        card_id = row.id
        s.add(AuditLog(actor="visual.laura_approval", action=AUDIT_RAISED, at=now,
                       artifact=f"owner_action:{card_id}",
                       detail={"requirement_key": key, "run_key": run_key,
                               "slug": st.get("slug"), "version": st.get("version"),
                               "release": st.get("release"), "gallery_digest": dg,
                               "frames": frames, "rule": RULE, "at": now.isoformat()}))
    return {"raised": True, "requirement_key": key, "card_id": card_id, "frames": frames,
            "gallery_digest": dg}


def card(db, key: str) -> dict | None:
    """The card as raised: its run, digest and frames (what the owner looks at)."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        for a in s.scalars(select(AuditLog).where(AuditLog.action == AUDIT_RAISED)
                           .order_by(AuditLog.id.desc())):
            d = dict(a.detail or {})
            if d.get("requirement_key") == key:
                return d
    return None


# ---- the decision ----------------------------------------------------------------------------

def _decide_in(s, db, row, *, decision: str, actor: str, step_up: bool, via: str,
               session_public_id: str = "", note: str = "", now: datetime,
               owner_directive: str | None = None) -> dict:
    """Inside the caller's session: check, record each frame, close the card, audit."""
    from ..core.models import AuditLog
    from ..ops import owner_queue
    from . import gallery_persist
    from .image_records import LauraGalleryApproval, ensure_tables

    if decision not in DECISIONS:
        raise Refused(f"decision must be one of {DECISIONS}")
    if owner_directive is not None:
        # D-OWNER-APPROVE-ALL-3: the owner's standing directive, applied by the system and
        # recorded as owner_directed_without_attestation. Only that directive is recognised.
        from ..ops import approve_all_directive as _AD

        if (owner_directive != _AD.DIRECTIVE_ID or actor != _AD.ACTOR or step_up
                or decision != APPROVED):
            raise Refused("not a recognised owner directive")
    else:
        if not str(actor).startswith("owner:"):
            raise Refused("only an owner session may decide Laura's publication")
        if step_up is not True:
            raise Refused("Laura's publication needs the owner's step-up (passphrase + TOTP)")
    if row is None or not is_card(row.requirement_key):
        raise Refused("no such Laura gallery card")
    if owner_queue.effective_state(row) not in (owner_queue.OPEN, owner_queue.PARKED):
        raise Refused("this Laura gallery card is already answered")
    raised = card(db, row.requirement_key)
    if raised is None:
        raise Refused("the card's gallery record is missing; nothing is approved")
    run_key = raised["run_key"]
    now_st = gallery_persist.gallery_status(db, run_key)
    frames = laura_frames(now_st)
    if digest(frames) != raised["gallery_digest"]:
        raise Refused("the gallery's Laura frames changed since this card was raised; "
                      "nothing is approved")
    ensure_tables(db)
    for f in frames:
        s.add(LauraGalleryApproval(
            run_key=run_key, requirement_key=row.requirement_key,
            gallery_digest=raised["gallery_digest"], frame_sha256=f["sha256"],
            candidate_id=f.get("candidate_id"), role=f.get("role") or "", decision=decision,
            decided_by=actor[:120], step_up=bool(step_up), via=via[:40],
            session_public_id=session_public_id[:64], created_at=now))
    reason = (f"owner {decision} Laura's publication in this gallery ({len(frames)} frame(s)) "
              f"via {via} (step-up)")
    if owner_directive is not None:
        reason = (f"owner {decision} Laura's publication in this gallery ({len(frames)} "
                  f"frame(s)) under the owner directive {owner_directive} "
                  f"(owner_directed_without_attestation; no step-up)")
    owner_queue.transition(s, row, owner_queue.SATISFIED, reason, actor=actor, now=now)
    s.add(AuditLog(actor=actor[:64], action=AUDIT_DECIDED, at=now,
                   artifact=f"owner_action:{row.id}",
                   detail={"requirement_key": row.requirement_key, "run_key": run_key,
                           "decision": decision, "gallery_digest": raised["gallery_digest"],
                           "frames": [{k: f[k] for k in ("position", "role", "sha256")}
                                      for f in frames],
                           "step_up": bool(step_up), "owner_directive": owner_directive,
                           "via": via, "session": session_public_id[:64],
                           "note": note[:500], "rule": RULE, "at": now.isoformat()}))
    return {"decided": True, "decision": decision, "run_key": run_key, "card_id": row.id,
            "frames": [f["sha256"] for f in frames]}


def after_decision(db, run_key: str, *, enqueue_package: bool = True) -> dict:
    """An approval re-judges the gallery for its certificate now (internal, deterministic),
    and on certification re-assembles the listing package, as the worker's stage does."""
    from . import gallery_persist
    from . import image_production as IP

    got = gallery_persist.certify_gallery(db, run_key, actor="laura_approval")
    certified = bool(got.get("certified"))
    if certified and enqueue_package:
        run = IP.get_run(db, run_key) or {}
        try:
            from ..queue.durable import DuplicateJob, JobQueue

            JobQueue(db).enqueue("listing", "listing.package",
                                 {"slug": run.get("slug"), "version": run.get("version"),
                                  "release": run.get("release")},
                                 idempotency_key=f"listing.package:laura_approval:{run_key}")
        except DuplicateJob:
            pass
    return {"certified": certified, "blockers": len(got.get("blockers") or [])}


def decide(db, key: str, *, decision: str, actor: str, step_up: bool, via: str = "route",
           session_public_id: str = "", note: str = "", now: datetime | None = None,
           recertify: bool = True) -> dict:
    """The owner's decision on one Laura gallery card. The CALLER enforces the owner session
    and the fresh step-up (`auth.require_stepup`); this refuses a call that does not say so."""
    from sqlalchemy import select

    from ..core.models import OwnerAction

    now = _now(now)
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == str(key))
                       .order_by(OwnerAction.id.desc()).limit(1))
        out = _decide_in(s, db, row, decision=decision, actor=actor, step_up=step_up, via=via,
                         session_public_id=session_public_id, note=note, now=now)
    if recertify and decision == APPROVED:
        out["recertified"] = after_decision(db, out["run_key"])
    return out
