"""The business side of the one-Laura boundary (W4-LAURAONE, D-W4-LAURA-UNIFIED, ADD-LCONT-05).

Business register only, and it imports nothing private. It is handed PLAIN text that the owner
has already approved, with a fresh step-up, to cross from the unified thread to the business
side, and it keeps exactly that text (`laura_boundary_crossings`). `approved_texts` is what the
leak guard allow-lists, so an approved quote can travel in later business briefs and history.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select

from .models import LauraBoundaryCrossing, ensure_tables

MAX_TEXT = 2000


def record(db, text: str, *, session_public_id: str = "") -> dict:
    """Record one owner-approved crossing. Returns {id, sha256} (no text)."""
    t = str(text or "").strip()
    if not t or len(t) > MAX_TEXT:
        raise ValueError(f"an approved crossing is non-empty text of at most {MAX_TEXT} chars")
    ensure_tables(db)
    digest = hashlib.sha256(t.encode("utf-8")).hexdigest()
    with db.session() as s:
        row = LauraBoundaryCrossing(session_public_id=str(session_public_id or "")[:40],
                                    approved_text=t, text_sha256=digest)
        s.add(row)
        s.flush()
        return {"id": row.id, "sha256": digest}


def approved_texts(db, limit: int = 200) -> list[str]:
    """Every approved crossing's text, newest first (the leak guard's allow-list)."""
    ensure_tables(db)
    with db.session() as s:
        return [r for (r,) in s.execute(select(LauraBoundaryCrossing.approved_text)
                                        .order_by(LauraBoundaryCrossing.id.desc())
                                        .limit(limit))]


def count(db) -> int:
    ensure_tables(db)
    with db.session() as s:
        return len(list(s.scalars(select(LauraBoundaryCrossing.id))))
