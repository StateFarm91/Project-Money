"""Whole-person identity for a model-bearing frame: valid trial, review band, exact identity.

Wave-3 lane K12. Three requirements that sit on top of the existing Laura gate
(`visual.canonical.laura_verdict`, which is read-only here and is applied unchanged):

* **F-213 Identity Trial Validity.** A trial with missing reference bytes, unsupported
  provider conditioning, an expired reference, a missing judge pair or unmeasurable
  morphology is INVALID or UNMEASURED -- never a zero score and never evidence against a
  provider. `trial_validity` returns `score: None` and `counts_against_provider: False`
  for every such trial.
* **F-219 Human Review Escalation Band.** Obvious drift is auto-refused; anything that is
  not provably the same woman and not an obvious drift enters a review band, persisted in
  `visual_rnd_identity_reviews`. Ambiguous anatomy from obscured clothing or pose is never
  auto-approved.
* **F-732 Exact Identity, Not a Similar Person.** "A woman similar to Laura is not Laura."
  A pass needs every one of: the conditioning receipt proving the frame was made from her
  *current* canonical reference bytes (by sha256, `gateway.images.conditioning_receipt`),
  two independent judges who each read every locked face dimension as a match and the
  morphology floor as readable and matching, and a deterministic biometric floor (cosine
  similarity of face embeddings from a *qualified* embedder, computed here). No embedder is
  qualified in this build -- that needs a face-embedding model, which is not installed and
  is gated -- so the biometric floor is UNMEASURED and every non-drift frame goes to human
  review. That is the honest state, not a defect to route around.

Nothing here generates, calls a model or spends. Nothing here approves an image for
publication: `visual.canonical.asset_status` remains the only publication status, and a
resolved review records what a reviewer saw rather than changing it.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from . import identity

GATE_VERSION = "identity-gate/1"

VALID, INVALID, UNMEASURED = "VALID", "INVALID", "UNMEASURED"
BAND_PASS, BAND_REVIEW, BAND_AUTO_REFUSE, BAND_INVALID = (
    "PASS", "REVIEW", "AUTO_REFUSE", "INVALID")

# Face-embedding models whose cosine similarity is admissible as the biometric floor, with
# the thresholds that model was qualified at: `match_at` and above is the same face,
# below `refuse_below` is a different face, between is borderline (review). Empty: no
# embedder has been installed or qualified (no face-embedding dependency in this build).
# Adding one is a qualification decision recorded here in code, never a caller argument.
QUALIFIED_EMBEDDERS: dict[str, dict] = {}

REVIEW_DECISIONS = frozenset({"confirmed_same_person", "not_laura", "inconclusive"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts) -> datetime | None:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _judges(evidence: dict) -> list[dict]:
    out, seen = [], set()
    for j in (evidence or {}).get("judges") or []:
        if not isinstance(j, dict):
            continue
        name = str(j.get("judge") or "").strip()
        scored = j.get("scored")
        if not name or not isinstance(scored, dict) or not scored or name in seen:
            continue
        seen.add(name)
        out.append({"judge": name, "scored": dict(scored)})
    return out


def _canon_hashes() -> tuple[set[str], set[str], str | None]:
    """(current reference hashes, superseded/forbidden hashes, error)."""
    from . import canonical

    current = {str(v).lower() for v in canonical.CURRENT_REFERENCE_HASHES.values()}
    try:
        forbidden = set(canonical.forbidden_hashes())
    except Exception as exc:  # noqa: BLE001 - an unreadable manifest vouches for nothing
        return current, set(), f"canon manifest unreadable ({type(exc).__name__})"
    return current, forbidden, None


# ---------------------------------------------------------------------------- F-213

def trial_validity(evidence: dict | None, *, now: datetime | None = None) -> dict:
    """Whether this identity trial is a measurement at all. Never a zero score."""
    now = now or _now()
    ev = dict(evidence or {})
    invalid: list[str] = []
    unmeasured: list[str] = []

    receipt = ev.get("conditioning") or {}
    refs = [r for r in (receipt.get("references") or []) if isinstance(r, dict)]
    if not receipt or not refs:
        invalid.append("missing_reference_bytes: no conditioning receipt names a reference")
    else:
        if any(not identity._is_sha256(r.get("sha256")) or not r.get("bytes") for r in refs):
            invalid.append("missing_reference_bytes: a reference has no hashed bytes")
        if not receipt.get("proven"):
            invalid.append("unsupported_conditioning: the provider request did not carry "
                           "every reference (gateway.images.conditioning_receipt)")
        current, forbidden, err = _canon_hashes()
        if err:
            invalid.append(f"reference_unverifiable: {err}")
        shas = {str(r.get("sha256") or "").lower() for r in refs}
        expired = sorted(s[:12] for s in shas if s in forbidden)
        # A product chart conditions the fabric, not the woman: declared by hash, it is
        # exempt from the "is this her reference" question (it must still be transmitted).
        product_refs = {str(x).lower() for x in ev.get("non_identity_references") or ()}
        foreign = sorted(s[:12] for s in shas if s and s not in forbidden
                         and s not in current and s not in product_refs)
        if expired:
            invalid.append(f"expired_reference: {expired} are superseded/historical canon "
                           f"assets, not her current references")
        if foreign:
            invalid.append(f"reference_not_canonical: {foreign} are not her current "
                           f"reference bytes")
        from . import canonical
        if canonical.FACE_SHA256 not in shas:
            invalid.append("missing_reference_bytes: the canonical face reference was not "
                           "among the conditioning references")
    for meta in ev.get("references") or []:
        exp = _parse((meta or {}).get("expires_at")) if isinstance(meta, dict) else None
        if exp is not None and exp <= now:
            invalid.append(f"expired_reference: {str(meta.get('sha256') or '')[:12]} "
                           f"expired at {exp.isoformat()}")

    judges = _judges(ev)
    if len(judges) < 2:
        unmeasured.append(f"missing_judge_pair: {len(judges)} independent judge reading(s); "
                          f"two are required")
    for j in judges:
        g = identity._group_verdict(j["scored"], identity.MORPHOLOGY_DIMENSIONS,
                                    identity.MIN_MEASURABLE["morphology"],
                                    identity.REQUIRED_MEASURABLE["morphology"])
        if g["verdict"] == "unverifiable":
            unmeasured.append(f"unmeasurable_morphology: judge {j['judge']} could read "
                              f"{g['measurable']} (required {g['required']}, floor "
                              f"{g['floor']})")

    validity = INVALID if invalid else (UNMEASURED if unmeasured else VALID)
    return {"validity": validity, "reasons": invalid + unmeasured,
            "judges": [j["judge"] for j in judges],
            # Never a zero, never evidence against a provider unless the trial was valid.
            "score": None, "counts_against_provider": validity == VALID,
            "rule": "F-213: an invalid or unmeasured trial is not a score"}


# ---------------------------------------------------------------------------- F-732

def biometric_floor(bio: dict | None) -> dict:
    """Cosine similarity of two face embeddings from a qualified embedder, computed here."""
    bio = dict(bio or {})
    name = str(bio.get("embedder") or "")
    spec = QUALIFIED_EMBEDDERS.get(name)
    if spec is None:
        return {"status": UNMEASURED, "similarity": None,
                "why": (f"no qualified face-embedding model{' ' + repr(name) if name else ''}"
                        f"; the biometric floor is gated on installing and qualifying one")}
    a, b = bio.get("reference") or [], bio.get("frame") or []
    try:
        a, b = [float(x) for x in a], [float(x) for x in b]
    except (TypeError, ValueError):
        return {"status": UNMEASURED, "similarity": None, "why": "non-numeric embedding"}
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if not a or len(a) != len(b) or na == 0 or nb == 0:
        return {"status": UNMEASURED, "similarity": None,
                "why": "embeddings missing, empty or of different lengths"}
    sim = round(sum(x * y for x, y in zip(a, b)) / (na * nb), 6)
    if sim >= float(spec["match_at"]):
        status = "PASS"
    elif sim < float(spec["refuse_below"]):
        status = "FAIL"
    else:
        status = "BORDERLINE"
    return {"status": status, "similarity": sim, "embedder": name,
            "match_at": spec["match_at"], "refuse_below": spec["refuse_below"],
            "why": f"cosine {sim} under {name}"}


def assess(evidence: dict | None, *, now: datetime | None = None) -> dict:
    """The identity gate for one model-bearing frame: PASS, FAIL or UNKNOWN, with its band.

    Order: any drift read by any judge is auto-refused (FAIL) -- the existing rule, kept;
    an invalid trial is UNKNOWN (fix the trial, no review); everything else that is not
    provably her enters the REVIEW band (UNKNOWN, blocks); PASS needs a valid trial, both
    judges reading Laura with a matching morphology floor, and the biometric floor PASS.
    """
    from . import canonical

    ev = dict(evidence or {})
    validity = trial_validity(ev, now=now)
    judges = _judges(ev)
    verdicts = [{"judge": j["judge"], **canonical.laura_verdict(j["scored"])}
                for j in judges]
    drifted = sorted({d for v in verdicts for d in v["drifted"]})
    bio = biometric_floor(ev.get("biometric"))
    base = {"gate_version": GATE_VERSION, "validity": validity, "judges": verdicts,
            "biometric": bio, "rule": canonical.IDENTITY_RULE, "score": None,
            "publication_approved": False}

    if not judges:
        return {**base, "status": "UNKNOWN", "band": BAND_INVALID,
                "why": "no identity reading: an unconfirmed likeness is not Laura",
                "failed": [], "review_required": False}
    if drifted or bio["status"] == "FAIL":
        why = (f"drift on {drifted}" if drifted else
               f"biometric floor below refusal threshold ({bio['similarity']})")
        return {**base, "status": "FAIL", "band": BAND_AUTO_REFUSE,
                "why": f"{why}. {canonical.IDENTITY_RULE}", "failed": drifted or ["biometric"],
                "review_required": False}
    if validity["validity"] == INVALID:
        return {**base, "status": "UNKNOWN", "band": BAND_INVALID,
                "why": "invalid trial: " + "; ".join(validity["reasons"]),
                "failed": [], "review_required": False}
    reasons = []
    if validity["validity"] == UNMEASURED:
        reasons += validity["reasons"]
    unread = sorted({d for v in verdicts for d in v["unread_locked"]})
    if unread:
        reasons.append(f"locked face dimensions not read as a match: {unread}")
    if bio["status"] != "PASS":
        reasons.append(f"biometric floor {bio['status']}: {bio['why']}")
    if reasons:
        return {**base, "status": "UNKNOWN", "band": BAND_REVIEW,
                "why": "borderline -- held for human review: " + "; ".join(reasons),
                "failed": unread, "review_required": True}
    return {**base, "status": "PASS", "band": BAND_PASS,
            "why": (f"Laura ({canonical.IDENTITY_ID}): current reference bytes proven sent, "
                    f"two judges read every locked dimension and morphology as a match, "
                    f"biometric {bio['similarity']} >= {bio['match_at']}"),
            "failed": [], "review_required": False}


def single_reading(scored: dict | None) -> dict:
    """Evidence for a caller that has one judge's per-dimension reading and nothing else."""
    return {"judges": ([{"judge": "single_reading", "scored": dict(scored)}]
                       if scored else [])}


# ---------------------------------------------------------------------------- F-219 queue

def open_review(db, *, product_class: str, subject: str, gate: dict,
                image_sha256: str = "", judgement_id: int | None = None) -> int | None:
    """Persist a REVIEW-band result. Idempotent per (subject, image) while open."""
    if not gate.get("review_required"):
        return None
    from sqlalchemy import select

    from .rnd import models as M

    M.ensure_tables(db)
    with M.session(db) as s:
        existing = s.scalar(select(M.VisualIdentityReview).where(
            M.VisualIdentityReview.subject == subject[:160],
            M.VisualIdentityReview.image_sha256 == (image_sha256 or "")[:64],
            M.VisualIdentityReview.state == "open"))
        if existing is not None:
            return existing.id
        row = M.VisualIdentityReview(
            product_class=product_class[:48], subject=subject[:160],
            image_sha256=(image_sha256 or "")[:64], judgement_id=judgement_id,
            band=gate.get("band") or BAND_REVIEW,
            reasons=[gate.get("why", "")[:2000]],
            evidence={k: gate.get(k) for k in ("validity", "biometric", "judges")})
        s.add(row)
        s.flush()
        return row.id


def resolve(db, review_id: int, *, decision: str, reviewer: str, note: str = "") -> dict:
    """Record a human's reading. Does not approve anything for publication."""
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(REVIEW_DECISIONS)}")
    if not str(reviewer or "").strip():
        raise ValueError("a review names its reviewer")
    from .rnd import models as M

    with M.session(db) as s:
        row = s.get(M.VisualIdentityReview, review_id)
        if row is None:
            raise LookupError(f"no identity review {review_id}")
        if row.state != "open":
            raise ValueError(f"identity review {review_id} is already {row.state}")
        row.state, row.decision = "resolved", decision
        row.reviewer, row.note = str(reviewer).strip()[:64], str(note)[:4000]
        row.resolved_at = _now()
    return {"review": review_id, "decision": decision, "publication_approved": False,
            "why": ("a review records what was seen; publication status is only ever "
                    "`visual.canonical.asset_status`")}


def queue(db, *, state: str = "open", limit: int = 50) -> list[dict]:
    from sqlalchemy import desc, select

    from .rnd import models as M

    if not M.tables_exist(db):
        return []
    with M.session(db) as s:
        rows = s.scalars(select(M.VisualIdentityReview)
                         .where(M.VisualIdentityReview.state == state)
                         .order_by(desc(M.VisualIdentityReview.id)).limit(limit))
        return [{"id": r.id, "subject": r.subject, "product_class": r.product_class,
                 "image_sha256": r.image_sha256, "band": r.band, "reasons": r.reasons,
                 "opened_at": r.opened_at.isoformat() if r.opened_at else None,
                 "decision": r.decision or None} for r in rows]
