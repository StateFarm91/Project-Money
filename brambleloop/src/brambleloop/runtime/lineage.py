"""F-662: which job caused which (W4-CLOSE6).

The company timeline (/api/cc/timeline) listed events side by side, and nothing recorded
cause and effect. A `cir.compile` that led to a certification, a listing and a refused
publish appeared as unrelated rows among hundreds of heartbeats. That is the "raw tool-call
noise" F-662 asks to replace.

`JobContext.enqueue` now writes one row per follow-on job it creates: the parent job and the
child job. Nothing reads this table to decide anything. It exists so the timeline can tell a
chain as one story (`app/command_center/causal.py`).

A failure to write a link never fails the enqueue: the follow-on work matters more than its
genealogy. A job whose link was not recorded shows in the timeline as its own story, with
"cause not recorded"; it is never guessed.

The table is owned here and created on first use (`ensure_table`), like
`finance.credits`.
"""
from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.models import utcnow


class JobLink(Base):
    __tablename__ = "job_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    parent_id: Mapped[int] = mapped_column(Integer, index=True)
    child_id: Mapped[int] = mapped_column(Integer, index=True, unique=True)
    parent_type: Mapped[str] = mapped_column(String(80), default="")
    child_type: Mapped[str] = mapped_column(String(80), default="")


_LOCK = threading.Lock()
_FLAG = "_brambleloop_job_links_ready"


def ensure_table(db) -> None:
    engine = db.engine if hasattr(db, "engine") else db.get_bind()
    if getattr(engine, _FLAG, False):
        return
    with _LOCK:
        if getattr(engine, _FLAG, False):
            return
        Base.metadata.create_all(engine, tables=[JobLink.__table__], checkfirst=True)
        setattr(engine, _FLAG, True)


def record(db, parent, child) -> bool:
    """Link `child` to the job that enqueued it. Best effort: False when not recorded."""
    try:
        if parent is None or child is None or getattr(parent, "id", None) is None \
                or getattr(child, "id", None) is None:
            return False
        ensure_table(db)
        with db.session() as s:
            s.add(JobLink(parent_id=parent.id, child_id=child.id,
                          parent_type=str(parent.job_type or "")[:80],
                          child_type=str(child.job_type or "")[:80]))
        return True
    except Exception:  # noqa: BLE001 - genealogy never blocks the work itself
        return False


def parents(db, child_ids) -> dict[int, int]:
    """child job id -> parent job id, for the ids that have a recorded link."""
    from sqlalchemy import select

    ids = [int(i) for i in child_ids]
    if not ids:
        return {}
    ensure_table(db)
    with db.session() as s:
        return {c: p for c, p in s.execute(select(JobLink.child_id, JobLink.parent_id)
                                           .where(JobLink.child_id.in_(ids))).all()}
