"""OPUS2 B-5: close duplicate open owner actions so the queue's unique index can exist.

`OwnerAction` declares `uq_owner_actions_open_requirement`: one open row per non-empty
`requirement_key`. A database written before that index (or by a Core write that bypassed
`ops.owner_queue_guard`) may hold several open rows for one key, and the index cannot be
created over them. `core.migrate` never alters data, so it defers the index and names this
module instead.

This module is the explicit, deterministic data step:
- `conflicts(engine)` counts keys with more than one open row. It is read-only.
- `close_duplicates(engine)` keeps the newest open row per key (the highest id, which carries
  the latest restatement) and closes every other one as `superseded`, naming the row it was
  superseded by. It writes nothing else, and it is idempotent: a second run finds nothing.
- `python -m brambleloop.ops.owner_queue_dedupe [--apply]` reports, or applies and then
  creates the index. Without `--apply` it changes nothing.

Closing a duplicate loses no decision: the kept row is the same requirement, still open, and
the closed rows stay in the table with their history and the reason.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine

INDEX = "uq_owner_actions_open_requirement"


def _groups(conn):
    from ..core.models import OwnerAction

    return list(conn.execute(
        select(OwnerAction.requirement_key, func.max(OwnerAction.id), func.count())
        .where(OwnerAction.done == False, OwnerAction.requirement_key != "")  # noqa: E712
        .group_by(OwnerAction.requirement_key).having(func.count() > 1)))


def conflicts(engine: Engine) -> int:
    """How many requirement keys have more than one open row (read-only)."""
    with engine.connect() as conn:
        return len(_groups(conn))


def close_duplicates(engine: Engine, *, now: datetime | None = None) -> list[dict]:
    """Close all but the newest open row per key as superseded. Returns what was closed."""
    from ..core.models import OwnerAction
    from . import owner_queue

    now = now or datetime.now(timezone.utc)
    closed: list[dict] = []
    with engine.begin() as conn:
        for key, keep_id, _n in _groups(conn):
            ids = [r for (r,) in conn.execute(select(OwnerAction.id).where(
                OwnerAction.requirement_key == key, OwnerAction.done == False,  # noqa: E712
                OwnerAction.id != keep_id))]
            conn.execute(update(OwnerAction).where(OwnerAction.id.in_(ids)).values(
                done=True, state=owner_queue.SUPERSEDED, state_at=now,
                state_reason=f"duplicate open action for {key!r}; superseded by #{keep_id} "
                             f"before the one-open-per-requirement index (B-5)"))
            closed += [{"id": i, "requirement_key": key, "kept": keep_id} for i in ids]
    return closed


def main(argv: list[str]) -> int:
    from ..core.db import Database
    from ..core.models import OwnerAction

    db = Database()          # BRAMBLELOOP_DATABASE_URL / DATABASE_URL, as the service reads it
    n = conflicts(db.engine)
    print(f"{n} requirement key(s) with more than one open owner action")
    if "--apply" not in argv:
        print("dry run: nothing changed (pass --apply to close duplicates and create the index)")
        return 0
    for row in close_duplicates(db.engine):
        print(f"closed #{row['id']} ({row['requirement_key']}), kept #{row['kept']}")
    for index in OwnerAction.__table__.indexes:
        if index.name == INDEX:
            index.create(bind=db.engine, checkfirst=True)
            print(f"index {INDEX} present")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
