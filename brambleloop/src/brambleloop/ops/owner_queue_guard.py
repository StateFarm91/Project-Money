"""OPUS2 (P1-OWNER-QUEUE-RACES): one serialised owner queue, whichever writer inserts.

INTEG8 serialised `launch.readiness` and `etsy_ops.seed_owner_queue`: each reads the open
owner actions, then inserts what is missing, under `release._serialise_owner_queue`. Two
passes at once otherwise both read "absent" and both insert, and the owner sees one decision
twice. The integration review (INTEGFIX LOW-3) found some forty more writers with the same
read-then-insert shape and no lock.

This guard closes the race for all of them at the point every insert passes through: the
session flush. When a flush would insert an *open* `OwnerAction` that carries a
`requirement_key` (the model's identity for an action: "the queue de-duplicates on this"):

1. It takes the same owner-queue lock: `pg_advisory_xact_lock(OWNER_QUEUE_LOCK)` on Postgres,
   or `BEGIN IMMEDIATE` on SQLite. If the SQLite connection is already in a write
   transaction, this session already holds the database's write lock and is serialised.
2. Under the lock it re-reads the open rows for those keys. A new row whose key is already
   open, from a concurrent pass that committed first or earlier in this same flush, is not
   inserted.

A writer therefore never creates a second open action for one requirement, however it read
the queue. Closed rows, rows without a key and every update path are untouched. Nothing here
changes what any writer decides, only that the same decision is not queued twice.
"""
from __future__ import annotations

from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

STATS = {"deduplicated": 0}


def _lock(session: Session) -> None:
    conn = session.connection()
    if conn.dialect.name == "postgresql":
        from ..runtime.release import OWNER_QUEUE_LOCK

        conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": OWNER_QUEUE_LOCK})
        return
    if conn.dialect.name == "sqlite":
        raw = conn.connection.dbapi_connection
        if not getattr(raw, "in_transaction", False):
            conn.exec_driver_sql("BEGIN IMMEDIATE")


@event.listens_for(Session, "before_flush")
def _one_open_action_per_requirement(session: Session, _flush_context, _instances) -> None:
    from ..core.models import OwnerAction

    new = [o for o in session.new if isinstance(o, OwnerAction)
           and not o.done and (o.requirement_key or "").strip()]
    if not new:
        return
    _lock(session)
    keys = sorted({o.requirement_key for o in new})
    # A row this same flush closes or deletes is not open any more: a writer that closes the
    # old action and queues its replacement in one transaction keeps the replacement.
    leaving = {o.id for o in session.dirty if isinstance(o, OwnerAction) and o.done} | {
        o.id for o in session.deleted if isinstance(o, OwnerAction)}
    with session.no_autoflush:
        open_keys = {key for rid, key in session.execute(
            select(OwnerAction.id, OwnerAction.requirement_key).where(
                OwnerAction.requirement_key.in_(keys), OwnerAction.done == False))  # noqa: E712
            if rid not in leaving}
    for obj in sorted(new, key=lambda o: id(o)):
        if obj.requirement_key in open_keys:
            session.expunge(obj)
            STATS["deduplicated"] += 1
        else:
            open_keys.add(obj.requirement_key)
