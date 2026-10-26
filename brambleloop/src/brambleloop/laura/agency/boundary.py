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


REDACTED = "[redacted: the owner marked the conversation this came from private]"


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
    """Every approved (not redacted) crossing's text, newest first (the guard's allow-list)."""
    ensure_tables(db)
    with db.session() as s:
        return [r for (r,) in s.execute(select(LauraBoundaryCrossing.approved_text)
                                        .order_by(LauraBoundaryCrossing.id.desc())
                                        .limit(limit)) if r != REDACTED]


def count(db) -> int:
    ensure_tables(db)
    with db.session() as s:
        return len(list(s.scalars(select(LauraBoundaryCrossing.id))))




def redact(db, *, turn_ids=(), crossing_ids=()) -> dict:
    """The owner marked a thread exchange private AFTER a business record was made from it:
    redact what was derived from it (D-W4-LAURA-UNIFIED-FEED). The business turn's brief,
    answer, cited facts and proposals are replaced; an approved crossing's text AND its hash
    are cleared (the row and its time stay as proof that a crossing happened). Ids and costs
    stay. Returns counts."""
    from .models import LauraTurn

    ensure_tables(db)
    n_t = n_x = 0
    with db.session() as s:
        for tid in {int(t) for t in turn_ids}:
            row = s.get(LauraTurn, tid)
            if row is None or row.question == REDACTED:
                continue
            row.question, row.answer = REDACTED, REDACTED
            row.facts, row.sources, row.unknowns, row.proposals = [], [], [], []
            n_t += 1
        for xid in {int(x) for x in crossing_ids}:
            row = s.get(LauraBoundaryCrossing, xid)
            if row is None or row.approved_text == REDACTED:
                continue
            row.approved_text = REDACTED
            row.text_sha256 = ""      # delta review N-8: a bare hash would confirm a guess
            n_x += 1
    return {"business_turns": n_t, "crossings": n_x}


def product_slugs(db) -> dict[str, str]:
    """{slug: title} of the company's products (allowlisted product ids for structured
    business requests)."""
    from ...core.models import Product

    with db.session() as s:
        return {str(a): str(b or "") for a, b in s.execute(select(Product.slug,
                                                                 Product.title))}
