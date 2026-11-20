"""ENG-VIS-FLUX: whether FLUX 3 generation may run now, and whether a replacement may be bought.

Two questions the generation job (`creative.flux3_generator.Flux3Generator`) asks before any
paid render, both answered from evidence, neither spending anything:

1. **`readiness`** -- READY only when BOTH hold: a BFL credential is present in the environment
   (its presence is read, its value never is), and the owner's activation of `flux-3-image` for
   `generation` is active (`paid_provider_gate`, the existing step-up activation route; a key is
   not an activation). Anything else is UNKNOWN with a precise reason code, and the job refuses
   with that reason before a reservation is taken.

2. **`replacement_allowed`** -- the owner's rule: never buy a replacement before the paid images
   already bought have been recovered and re-checked. A render rejected at generation
   (`images.GENERATION_REJECTED_ACTION`) is re-checked here from its kept bytes, offline, before
   anything else is bought for that gallery; and any paid render of the product still open in
   ENG-MOTIF-BACKLOG's recovery table (`motif_recovery`, read when present -- that branch owns
   it, this module never writes it) blocks a new purchase until it is resolved.
"""
from __future__ import annotations

import os
from pathlib import Path

PROVIDER = "flux-3-image"
ACCOUNT = "bfl"
# The variable the gateway reads for this provider (`images.key_var("bfl")`). The general slot
# `BRAMBLELOOP_IMAGE_KEY` is honoured only when `BRAMBLELOOP_IMAGE_PROVIDER=flux-3-image`.
KEY_ENV_VAR = "BRAMBLELOOP_IMAGE_KEY_BFL"
FALLBACK_KEY_ENV_VAR = "BRAMBLELOOP_IMAGE_KEY"
FALLBACK_PROVIDER_ENV_VAR = "BRAMBLELOOP_IMAGE_PROVIDER"

READY, UNKNOWN = "READY", "UNKNOWN"
NO_KEY = "no_bfl_credential"
RECHECK_ACTION = "image.generation_rejection_rechecked"
OPEN_MOTIF_STATES = ("BLOCKED", "QUEUED_BUDGET", "QUEUED_RETRY", "PARKED")


class FluxNotReady(RuntimeError):
    """Generation refused before any reservation; `.code` is the UNKNOWN reason."""

    def __init__(self, code: str, message: str):
        super().__init__(f"UNKNOWN [{code}] {message}")
        self.code = code


class ReplacementRefused(RuntimeError):
    """A paid image for this gallery or product is not yet recovered and re-checked."""


def key_present(env: dict | None = None) -> bool:
    """Whether the BFL credential is present. Reads presence only; the value is never returned,
    logged or compared to anything."""
    from . import images

    return bool(images.key_for(PROVIDER, env))


def readiness(db, *, env: dict | None = None) -> dict:
    """{state, code, reason, key_env_var, key_present, activation, spends}. Never raises."""
    from . import paid_provider_gate as gate

    present = key_present(env)
    act = gate.activation_state(db, PROVIDER, gate.GENERATION)
    out = {"provider": PROVIDER, "key_env_var": KEY_ENV_VAR,
           "fallback": f"{FALLBACK_KEY_ENV_VAR} with {FALLBACK_PROVIDER_ENV_VAR}={PROVIDER}",
           "key_present": present, "activation_active": bool(act["active"]),
           "activation": act.get("activation"), "spends": 0.0,
           "caps": gate.image_caps()}
    if not present:
        out.update(state=UNKNOWN, code=NO_KEY,
                   reason=f"no BFL credential: {KEY_ENV_VAR} is not set in this environment, "
                          f"so no FLUX 3 render can be sent. Nothing was reserved or spent")
    elif not act["active"]:
        out.update(state=UNKNOWN, code=act["reason"],
                   reason=f"{act['reason']}: {PROVIDER} has no active owner activation for "
                          f"generation. {gate.KEY_IS_NOT_ACTIVATION}. Nothing was reserved "
                          f"or spent")
    else:
        out.update(state=READY, code="", reason="BFL credential present and the owner's "
                                                "generation activation is active")
    return out


def require_ready(db, *, env: dict | None = None) -> dict:
    state = readiness(db, env=env)
    if state["state"] != READY:
        raise FluxNotReady(state["code"], state["reason"])
    return state


def _rejections(db, gallery: str) -> list:
    from sqlalchemy import select

    from ..core.models import AuditLog
    from .images import GENERATION_REJECTED_ACTION

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action == GENERATION_REJECTED_ACTION,
            AuditLog.artifact == str(gallery)[:200]).order_by(AuditLog.id)))
        rechecked = {int((r.detail or {}).get("rejection_id") or 0): dict(r.detail or {})
                     for r in s.scalars(select(AuditLog).where(
                         AuditLog.action == RECHECK_ACTION))}
        return [(r.id, dict(r.detail or {}), rechecked.get(r.id)) for r in rows]


def recheck(db, rejection_id: int, detail: dict) -> dict:
    """Re-read a rejected render's kept bytes and run the generation-time check again (free).

    CONFIRMED: the defect is in the bytes, so the render is recovered as a known reject and a
    replacement may be bought. RECOVERED: the kept bytes now pass (the defect was in the
    reading, not the render) -- the paid image is usable and no replacement is bought.
    BYTES_MISSING: the bytes cannot be read back; recorded, and nothing can be recovered."""
    from ..core.models import AuditLog
    from . import flux_qc

    path = Path(str(detail.get("path") or ""))
    verdict = dict(detail.get("verdict") or {})
    if not path.is_file():
        outcome, qc = "BYTES_MISSING", None
    else:
        qc = flux_qc.inspect(path.read_bytes(), requested_size=str(
            verdict.get("requested_size") or ""), frame_role=str(verdict.get("role") or ""))
        outcome = "RECOVERED" if qc["ok"] else "CONFIRMED"
    row = {"rejection_id": rejection_id, "outcome": outcome, "path": str(path),
           "sha256": detail.get("sha256"), "reasons": (qc or {}).get("reasons"),
           "gallery": detail.get("gallery")}
    with db.session() as s:
        s.add(AuditLog(actor="gateway", action=RECHECK_ACTION,
                       artifact=str(detail.get("gallery") or "")[:200], detail=row))
    return row


def _open_motif_recoveries(db, slug: str) -> int:
    """ENG-MOTIF-BACKLOG's open recoveries for this product, when its table exists here."""
    from sqlalchemy import inspect, text

    try:
        with db.session() as s:
            if not inspect(s.get_bind()).has_table("motif_recovery"):
                return 0
            marks = ", ".join(f":s{i}" for i in range(len(OPEN_MOTIF_STATES)))
            params = {f"s{i}": v for i, v in enumerate(OPEN_MOTIF_STATES)}
            return int(s.execute(text(
                f"SELECT COUNT(*) FROM motif_recovery WHERE slug = :slug AND state IN "
                f"({marks})"), {"slug": slug, **params}).scalar() or 0)
    except Exception as exc:  # noqa: BLE001 - unreadable recovery state is UNKNOWN: refuse
        raise ReplacementRefused(f"the motif-recovery backlog could not be read "
                                 f"({type(exc).__name__}); a replacement is not bought while "
                                 f"paid renders may be awaiting recovery") from exc


def replacement_allowed(db, *, gallery: str, slug: str = "") -> dict:
    """{allowed, rechecked, recovered, open_motif_recoveries, why}. Re-checks first (free)."""
    done = []
    recovered = []
    for rid, detail, already in _rejections(db, gallery):
        if already:
            # Re-checked before. A RECOVERED render is a usable paid image and keeps blocking a
            # replacement for this gallery: the run takes those bytes instead of buying more.
            if already.get("outcome") == "RECOVERED":
                recovered.append(already)
            continue
        got = recheck(db, rid, detail)
        done.append(got)
        if got["outcome"] == "RECOVERED":
            recovered.append(got)
    open_motif = _open_motif_recoveries(db, slug) if slug else 0
    why = ""
    if recovered:
        why = (f"{len(recovered)} paid render(s) in gallery {gallery!r} pass on re-check of "
               f"their kept bytes; they are recovered, not replaced")
    elif open_motif:
        why = (f"{open_motif} paid render(s) of {slug} are still open in the motif-recovery "
               f"backlog (ENG-MOTIF-BACKLOG); no replacement is bought until they resolve")
    return {"allowed": not why, "rechecked": done, "recovered": recovered,
            "open_motif_recoveries": open_motif, "why": why}


def require_replacement_allowed(db, *, gallery: str, slug: str = "") -> dict:
    got = replacement_allowed(db, gallery=gallery, slug=slug)
    if not got["allowed"]:
        raise ReplacementRefused(got["why"])
    return got


def env_var_report(env: dict | None = None) -> dict:
    """What the owner sets, by name only. Never a value, never a prefix of one."""
    e = env if env is not None else os.environ
    return {"key_env_var": KEY_ENV_VAR, "key_present": key_present(e),
            "fallback_key_env_var": FALLBACK_KEY_ENV_VAR,
            "fallback_requires": f"{FALLBACK_PROVIDER_ENV_VAR}={PROVIDER}"}
