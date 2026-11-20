"""Durable identity records: one row per identity evaluation of one image (ENG-VIS-IDENTITY).

For every model-bearing image the identity gate evaluates, this records:

* the identity verdict (`PASS` / `HOLD` / `REFUSE`) and the gate's own status, band and reason;
* the references the frame was conditioned on, each with its sha256 and whether it is one of
  Laura's current canonical references (`laura-r2-a42aeac7`);
* the biometric method (embedder name, version, weights sha256), its qualification (record
  sha256, admitted, certification) and the measured similarity;
* every judge's output (judge id, image order, per-dimension reading, or why it did not answer)
  and whether the judges agreed;
* the outfit reserved for the listing and the outfit check.

Rows live in `visual_identity_records` (the shared database), so a restart, a redeploy or a
second worker sees exactly what was decided. `record` is idempotent: the same evaluation of
the same image (same content hash) is one row; a re-evaluation with different evidence is a
new row, so history is append-only and never rewritten. Nothing here decides anything.

Interface (stable; consumed by the FLUX provider and the gallery certificate route):

    record(db, image_sha256=..., listing=..., identity=<vision_judges.identity_check result>,
           outfit=<outfit check or None>, slug="") -> {"id", "created", "verdict", ...}
    latest(db, image_sha256) -> dict | None      # the most recent record for the image
    history(db, image_sha256) -> list[dict]       # every record, oldest first
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow

RECORD_VERSION = "identity-record/1"
VERDICTS = ("PASS", "HOLD", "REFUSE")


class VisualIdentityRecord(Base):
    __tablename__ = "visual_identity_records"
    __table_args__ = (UniqueConstraint("image_sha256", "evaluation_sha256",
                                       name="uq_identity_record_eval"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 index=True)
    image_sha256: Mapped[str] = mapped_column(String(64), index=True)
    evaluation_sha256: Mapped[str] = mapped_column(String(64))
    identity_id: Mapped[str] = mapped_column(String(64), default="")
    listing: Mapped[str] = mapped_column(String(120), default="", index=True)
    slug: Mapped[str] = mapped_column(String(120), default="")
    verdict: Mapped[str] = mapped_column(String(8), index=True)
    status: Mapped[str] = mapped_column(String(16), default="")
    band: Mapped[str] = mapped_column(String(24), default="")
    why: Mapped[str] = mapped_column(Text, default="")
    references: Mapped[list] = mapped_column(JSON, default=list)
    method: Mapped[dict] = mapped_column(JSON, default=dict)
    judges: Mapped[list] = mapped_column(JSON, default=list)
    judge_agreement: Mapped[dict] = mapped_column(JSON, default=dict)
    outfit: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[str] = mapped_column(String(32), default=RECORD_VERSION)


_ensured: set = set()
_lock = threading.Lock()


def ensure_tables(db) -> None:
    key = id(db.engine)
    if key in _ensured:
        return
    with _lock:
        if key not in _ensured:
            VisualIdentityRecord.__table__.create(db.engine, checkfirst=True)
            _ensured.add(key)


def _verdict(identity: dict) -> str:
    v = (identity or {}).get("verdict")
    if v in VERDICTS:
        return v
    # A result without a consumer verdict is never a PASS.
    return "REFUSE" if (identity or {}).get("status") == "FAIL" else "HOLD"


def build(*, image_sha256: str, listing: str, identity: dict, outfit: dict | None = None,
          slug: str = "") -> dict:
    """The record body (no database). Deterministic for the same inputs."""
    from . import canonical

    ident = dict(identity or {})
    current = set(canonical.CURRENT_REFERENCE_HASHES.values())
    frames = {h: f for f, h in canonical.CURRENT_REFERENCE_HASHES.items()}
    refs = []
    for r in ident.get("references") or []:
        sha = str((r or {}).get("sha256") or "").lower()
        refs.append({"sha256": sha, "bytes": (r or {}).get("bytes"),
                     "canonical_frame": frames.get(sha), "canonical": sha in current})
    bio = ident.get("biometric") or {}
    q = bio.get("qualification") or {}
    method = {"biometric_status": bio.get("status"), "similarity": bio.get("similarity"),
              "match_at": bio.get("match_at"), "refuse_below": bio.get("refuse_below"),
              "against": bio.get("against"), "embedder": q.get("embedder"),
              "embedder_version": q.get("embedder_version"),
              "qualification_record_sha256": q.get("record_sha256"),
              "qualification_admitted": q.get("admitted"),
              "certification": q.get("certification"),
              "conditioning_proven": ident.get("conditioning_proven")}
    judges = [dict(j) for j in ident.get("readings") or []] or \
        [{"judge": j} for j in ident.get("judges") or []]
    body = {"version": RECORD_VERSION, "image_sha256": str(image_sha256).lower(),
            "identity_id": canonical.IDENTITY_ID, "listing": listing, "slug": slug,
            "verdict": _verdict(ident), "status": ident.get("status"),
            "band": ident.get("band"), "why": str(ident.get("why") or "")[:4000],
            "references": refs, "method": method, "judges": judges,
            "judge_agreement": ident.get("judge_agreement") or {},
            "outfit": dict(outfit or {})}
    body["evaluation_sha256"] = hashlib.sha256(json.dumps(
        {k: v for k, v in body.items() if k != "image_sha256"}, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()
    return body


def _view(r) -> dict:
    return {"id": r.id, "created_at": r.created_at.isoformat() if r.created_at else None,
            "image_sha256": r.image_sha256, "evaluation_sha256": r.evaluation_sha256,
            "identity_id": r.identity_id, "listing": r.listing, "slug": r.slug,
            "verdict": r.verdict, "status": r.status, "band": r.band, "why": r.why,
            "references": list(r.references or []), "method": dict(r.method or {}),
            "judges": list(r.judges or []), "judge_agreement": dict(r.judge_agreement or {}),
            "outfit": dict(r.outfit or {}), "version": r.version}


def record(db, *, image_sha256: str, listing: str, identity: dict,
           outfit: dict | None = None, slug: str = "") -> dict:
    """Persist one evaluation. Idempotent on (image, evaluation content)."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    sha = str(image_sha256 or "").strip().lower()
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("an identity record names the image by its sha256")
    body = build(image_sha256=sha, listing=listing, identity=identity, outfit=outfit,
                 slug=slug)
    ensure_tables(db)

    def existing():
        with db.session() as s:
            r = s.scalar(select(VisualIdentityRecord).where(
                VisualIdentityRecord.image_sha256 == sha,
                VisualIdentityRecord.evaluation_sha256 == body["evaluation_sha256"]))
            return _view(r) if r is not None else None

    found = existing()
    if found is not None:
        return {**found, "created": False}
    try:
        with db.session() as s:
            row = VisualIdentityRecord(**{k: body[k] for k in (
                "image_sha256", "evaluation_sha256", "identity_id", "listing", "slug",
                "verdict", "status", "band", "why", "references", "method", "judges",
                "judge_agreement", "outfit", "version")})
            s.add(row)
            s.flush()
            out = _view(row)
        return {**out, "created": True}
    except IntegrityError:
        return {**(existing() or {}), "created": False}


def history(db, image_sha256: str) -> list[dict]:
    from sqlalchemy import select

    ensure_tables(db)
    with db.session() as s:
        return [_view(r) for r in s.scalars(select(VisualIdentityRecord).where(
            VisualIdentityRecord.image_sha256 == str(image_sha256).lower())
            .order_by(VisualIdentityRecord.id))]


def latest(db, image_sha256: str) -> dict | None:
    h = history(db, image_sha256)
    return h[-1] if h else None
