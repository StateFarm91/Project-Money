"""F-718 / F-733: the owner's canonical-model approval, held by the repository.

Until W4-PROVENANCE the approved pack's fingerprint existed only in one production audit row
(`model.frozen`), so a lost database, or a session that never read it, lost which pack the owner
approved. `approval_record.json` (beside this module, shipped in the image) is that row
exported read-only from production; `compare(db)` checks it against whatever `model.frozen` row
the running database holds, so the two copies cannot drift apart silently.

States: MATCH (the database row agrees on every pinned field), MISMATCH (it disagrees: which
fields), NO_ROW (this database has no freeze row -- a fresh or test database; not a pass),
UNREADABLE (the committed record cannot be read). Read-only.
"""
from __future__ import annotations

import json
from pathlib import Path

RECORD_PATH = Path(__file__).resolve().parent / "approval_record.json"
PINNED = ("key", "version", "approved_at", "pack_version", "candidate_fingerprint")


def load() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


def latest_row(db) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == "model.frozen")
                       .order_by(desc(AuditLog.id)).limit(1))
        if row is None:
            return None
        return {"id": row.id, "freeze": dict((row.detail or {}).get("freeze") or {})}


def compare(db) -> dict:
    try:
        rec = load()
    except (OSError, ValueError) as exc:
        return {"state": "UNREADABLE", "why": f"{type(exc).__name__}", "source": str(RECORD_PATH.name)}
    want = rec.get("freeze") or {}
    row = latest_row(db)
    base = {"record": {k: want.get(k) for k in PINNED},
            "record_source": rec.get("source"), "file": "visual/approval_record.json"}
    if row is None:
        return {**base, "state": "NO_ROW",
                "why": "this database holds no model.frozen row to compare against"}
    got = row["freeze"]
    diff = [k for k in PINNED if str(got.get(k)) != str(want.get(k))]
    return {**base, "state": "MISMATCH" if diff else "MATCH", "database_audit_id": row["id"],
            "mismatched_fields": diff,
            "why": ("the database freeze row disagrees with the repository record on "
                    + ", ".join(diff)) if diff else
            "the repository record and the database freeze row agree on every pinned field"}
