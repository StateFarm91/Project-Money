"""ENG-CANDIDATE-VIEWER: read-only projections of generated image candidates and gallery runs,
for the operator's readback (`BRAMBLELOOP_READBACK_TOKEN`, `app.security.READBACK_ROUTES`).

* `candidates(db, ...)` -- the body of `GET /api/readback/candidates`: one entry per
  `image_candidates` row (`visual.image_records.ImageCandidate`), newest first, paginated by
  an id cursor (`before_id`), at most `MAX_LIMIT` per page. Each entry is metadata only: gate
  verdicts with failure codes, fidelity and Laura identity readings (bounded), the generation
  receipt (model, verbatim prompt, ordered reference hashes and kinds, aspect, resolution,
  seed, cost) and `created_at`. No image bytes are embedded; each entry names its image URL.
* `image(db, candidate_id)` -- the stored bytes of ONE candidate, by id, through the existing
  accessors (`core.artifacts.ArtifactStore` on disk, else the kept `DurableArtifact` row).
  Read-only: a disk miss is served from the durable row without writing it back to disk.
* `galleries(db, ...)` -- the body of `GET /api/readback/galleries`: each
  `image_production_runs` row with its frames (role, candidate_id, status) from the stored
  card, paginated the same way.

Never a secret: internal tokens (`_paid_call`), the owner's identity (`submitted_by`) and any
key whose name reads as a credential are dropped, and any configured secret value found in a
string is replaced by `[redacted]`. Nothing here writes.
"""
from __future__ import annotations

import os
import re

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_STR = 600
MAX_LIST = 24
MAX_DEPTH = 5
MAX_THUMB_PX = 1024
REDACTED = "[redacted]"

# Key names that read as a credential; dropped wherever they appear in a projection.
_SECRET_KEY = re.compile(r"(token|secret|passw|api[_-]?key|authoriz|bearer|credential|cookie|"
                         r"private[_-]?key|session[_-]?id|x-key)", re.I)
# Environment variables whose values are credentials (by name).
_SECRET_ENV = re.compile(r"(TOKEN|SECRET|PASSWORD|API_KEY|_KEY$|CREDENTIAL|DATABASE_URL|DSN)")
# Internal check keys never shown: payment-call tokens, the owner's route attribution.
_DROP_CHECKS = frozenset({"_paid_call"})
FIDELITY_CHECKS = ("product_truth", "motif_fidelity")
IDENTITY_CHECKS = ("identity", "body_proportions", "anatomy", "outfit", "outfit_consistency",
                   "outfit_distinctness")
RECEIPT_KEYS = ("aspect_ratio", "resolution", "seed")
METHOD_KEY = "_generation_method"   # visual.image_production.METHOD_KEY (kept import-free)


def _secret_values() -> list[str]:
    vals = []
    for k, v in os.environ.items():
        if _SECRET_ENV.search(k.upper()) and v and len(v.strip()) >= 12:
            vals.append(v.strip())
    return sorted(set(vals), key=len, reverse=True)


def _scrub_str(s: str, secrets: list[str], limit: int | None = MAX_STR) -> str:
    for v in secrets:
        if v in s:
            s = s.replace(v, REDACTED)
    return s if limit is None or len(s) <= limit else s[:limit] + "...[truncated]"


def _bounded(obj, secrets: list[str], depth: int = 0):
    """A JSON-safe, size-bounded copy with credential-named keys dropped."""
    if depth > MAX_DEPTH:
        return "[depth]"
    if isinstance(obj, dict):
        out = {}
        for k, v in list(obj.items())[:60]:
            ks = str(k)
            if _SECRET_KEY.search(ks) or ks in _DROP_CHECKS:
                continue
            out[ks[:80]] = _bounded(v, secrets, depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        items = [_bounded(v, secrets, depth + 1) for v in list(obj)[:MAX_LIST]]
        if len(obj) > MAX_LIST:
            items.append(f"[+{len(obj) - MAX_LIST} more]")
        return items
    if isinstance(obj, str):
        return _scrub_str(obj, secrets)
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    return _scrub_str(str(obj), secrets)


def _find(obj, key: str, depth: int = 0):
    """The first value stored under `key` anywhere in a nested record (depth-limited)."""
    if depth > MAX_DEPTH:
        return None
    if isinstance(obj, dict):
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
        for v in obj.values():
            hit = _find(v, key, depth + 1)
            if hit not in (None, ""):
                return hit
    elif isinstance(obj, list):
        for v in obj[:MAX_LIST]:
            hit = _find(v, key, depth + 1)
            if hit not in (None, ""):
                return hit
    return None


def _codes(check: dict) -> list:
    out = []
    for k in ("codes", "failed", "failure_codes"):
        v = check.get(k)
        if isinstance(v, list):
            out.extend(str(x)[:120] for x in v[:MAX_LIST])
    return out


def _clamp(limit) -> int:
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, n))


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def candidate_view(row, secrets: list[str] | None = None) -> dict:
    secrets = _secret_values() if secrets is None else secrets
    checks = dict(row.checks or {})
    gates = {}
    for name, v in checks.items():
        if str(name).startswith("_") or not isinstance(v, dict):
            continue
        gates[name] = {"status": v.get("status"),
                       "why": _scrub_str(str(v.get("why") or ""), secrets, 300),
                       "codes": _codes(v)}
    publication = checks.get("_publication") or {}
    receipt_src = {k: checks.get(k) for k in ("_identity_evidence", METHOD_KEY,
                                              "_reference_provenance", "_route")}
    found = {k: _find(receipt_src, k) for k in RECEIPT_KEYS}
    refs = []
    for i, r in enumerate(row.references or []):
        r = r if isinstance(r, dict) else {}
        refs.append({"position": i, "sha256": r.get("sha256"), "role": r.get("kind"),
                     **({"source": r.get("source"), "label": _scrub_str(
                         str(r.get("label") or ""), secrets, 60)} if r.get("source") else {})})
    method = checks.get(METHOD_KEY)
    return {
        "candidate_id": row.id, "sha256": row.sha256, "run_key": row.run_key,
        "slug": row.slug, "version": row.version, "release": row.release,
        "listing": row.listing, "role": row.role, "stage": row.stage,
        "method": row.method, "provenance_kind": row.provenance_kind,
        "generation_method": _bounded(method, secrets) if isinstance(method, dict) else None,
        "attempt": row.attempt, "outcome": row.outcome,
        "technical_status": row.technical_status, "publishable": bool(row.publishable),
        "failure_categories": list(row.failure_categories or [])[:MAX_LIST],
        "gates": gates,
        "publication": _bounded(publication, secrets),
        "fidelity": {k: _bounded(checks[k], secrets) for k in FIDELITY_CHECKS
                     if isinstance(checks.get(k), dict)},
        "laura_identity": {"laura_present": bool(row.laura_present),
                           "outfit_id": row.outfit_id,
                           **{k: _bounded(checks[k], secrets) for k in IDENTITY_CHECKS
                              if isinstance(checks.get(k), dict)}},
        "receipt": {
            "provider": row.provider, "model": row.model,
            # verbatim (as stored, at most 8000 characters), secret values redacted
            "prompt": _scrub_str(row.prompt or "", secrets, None),
            "prompt_sha256": row.prompt_sha256, "prompt_version": row.prompt_version,
            "references": refs,
            "reference_provenance": _bounded(checks.get("_reference_provenance"), secrets),
            "conditioning": _bounded((checks.get("_identity_evidence") or {})
                                     .get("references"), secrets),
            "aspect_ratio": found["aspect_ratio"], "resolution": found["resolution"],
            "seed": found["seed"],
            "not_recorded": [k for k in RECEIPT_KEYS if found[k] in (None, "")],
            "width": row.width, "height": row.height,
            "cost_cad": row.cost_cad, "cost_basis": row.cost_basis,
            "latency_s": row.latency_s},
        "image_url": f"/api/readback/candidates/{row.id}/image",
        "created_at": _iso(row.created_at),
    }


def candidates(db, *, run_key: str = "", role: str = "", limit=DEFAULT_LIMIT,
               before_id=None) -> dict:
    from sqlalchemy import select

    from ..visual.image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    n = _clamp(limit)
    q = select(ImageCandidate).order_by(ImageCandidate.id.desc())
    if run_key:
        q = q.where(ImageCandidate.run_key == str(run_key)[:200])
    if role:
        q = q.where(ImageCandidate.role == str(role)[:40])
    try:
        if before_id not in (None, ""):
            q = q.where(ImageCandidate.id < int(before_id))
    except (TypeError, ValueError):
        pass
    secrets = _secret_values()
    with db.session() as s:
        rows = list(s.scalars(q.limit(n + 1)))
        page = [candidate_view(r, secrets) for r in rows[:n]]
    more = len(rows) > n
    return {"candidates": page, "count": len(page), "limit": n,
            "next_before_id": page[-1]["candidate_id"] if more and page else None,
            "note": "metadata only; fetch one image at a time by image_url"}


def _sniff(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def image(db, candidate_id, *, max_px=None) -> tuple[bytes, str, str] | None:
    """(bytes, content type, sha256) of one candidate's stored image, or None.

    Reads exactly one blob. `max_px`, when given, returns a JPEG thumbnail no larger than that
    on its longer side (bounded by MAX_THUMB_PX); otherwise the stored bytes, unchanged."""
    import hashlib

    from ..core import artifacts as A
    from ..visual.image_records import ImageCandidate, ensure_tables

    ensure_tables(db)
    try:
        cid = int(candidate_id)
    except (TypeError, ValueError):
        return None
    with db.session() as s:
        row = s.get(ImageCandidate, cid)
        sha = str(row.sha256 or "") if row is not None else ""
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        return None
    store = A.ArtifactStore()
    data = None
    try:
        if store.exists(sha):
            data = store.get(sha)           # no db: never rehydrates (writes) anything
        else:
            data = A._recover(db, sha)      # the kept DurableArtifact row, read only
    except Exception:  # noqa: BLE001 - missing or corrupt bytes are a 404, never a substitute
        data = None
    if not data or hashlib.sha256(data).hexdigest() != sha:
        return None
    if max_px not in (None, ""):
        try:
            px = max(16, min(MAX_THUMB_PX, int(max_px)))
            import io

            from PIL import Image

            im = Image.open(io.BytesIO(data))
            im.thumbnail((px, px))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=82)
            return buf.getvalue(), "image/jpeg", sha
        except Exception:  # noqa: BLE001 - a thumbnail that cannot be made: the original
            pass
    return data, _sniff(data), sha


def galleries(db, *, limit=DEFAULT_LIMIT, before_id=None, run_key: str = "") -> dict:
    from sqlalchemy import select

    from ..visual.image_records import ImageProductionRun, ensure_tables

    ensure_tables(db)
    n = _clamp(limit)
    q = select(ImageProductionRun).order_by(ImageProductionRun.id.desc())
    if run_key:
        q = q.where(ImageProductionRun.run_key == str(run_key)[:200])
    try:
        if before_id not in (None, ""):
            q = q.where(ImageProductionRun.id < int(before_id))
    except (TypeError, ValueError):
        pass
    secrets = _secret_values()
    out = []
    with db.session() as s:
        rows = list(s.scalars(q.limit(n + 1)))
        for r in rows[:n]:
            card = r.card if isinstance(r.card, dict) else {}
            frames = []
            for f in (card.get("roles") or [])[:40]:
                if not isinstance(f, dict):
                    continue
                c = f.get("candidate") if isinstance(f.get("candidate"), dict) else {}
                cid = c.get("candidate_id")
                frames.append({"position": f.get("position"), "role": f.get("role"),
                               "status": f.get("status"), "source": f.get("source"),
                               "candidate_id": cid, "sha256": c.get("sha256"),
                               "technical_status": c.get("technical_status"),
                               "image_url": (f"/api/readback/candidates/{cid}/image"
                                             if cid else None)})
            out.append({"id": r.id, "run_key": r.run_key, "slug": r.slug,
                        "version": r.version, "release": r.release, "listing": r.listing,
                        "stage": r.stage, "status": r.status,
                        "blocked_reason": _scrub_str(r.blocked_reason or "", secrets, 300),
                        "generation_calls": r.generation_calls, "spent_cad": r.spent_cad,
                        "outfit_id": r.outfit_id, "frames": frames,
                        "created_at": _iso(r.created_at), "updated_at": _iso(r.updated_at)})
    more = len(rows) > n
    return {"galleries": out, "count": len(out), "limit": n,
            "next_before_id": out[-1]["id"] if more and out else None}
