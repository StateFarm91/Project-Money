"""OPUS2 (P1-OWNER-QUEUE-RACES): one serialised owner queue, whichever writer inserts.

INTEG8 serialised `launch.readiness` and `etsy_ops.seed_owner_queue`: each reads the open
owner actions, then inserts what is missing, under `release._serialise_owner_queue`. Two
passes at once otherwise both read "absent" and both insert, and the owner sees one decision
twice. The integration review (INTEGFIX LOW-3) found some forty more writers with the same
read-then-insert shape and no lock.

This guard closes the race at the point every ORM write passes through: the session flush.
When a flush would make an owner action **open for a requirement_key** -- the model's identity
for an action, "the queue de-duplicates on this" -- by inserting one (the race), re-keying a
row onto a key (review OPUS2F B-2), or reopening a closed row (B-3):

1. It takes the same owner-queue lock: `pg_advisory_xact_lock(OWNER_QUEUE_LOCK)` on Postgres,
   or `BEGIN IMMEDIATE` on SQLite. If the SQLite connection is already in a write transaction,
   this session holds the database's write lock and is serialised.
2. Under the lock it re-reads the open rows for those keys. A row this flush closes or deletes
   is not open any more, so close-and-replace keeps the replacement.
3. A new row whose key is already open is **merged onto the open row** (review OPUS2F B-1): the
   open row is restated with the newcomer's text, the newcomer is not inserted, and it is given
   the open row's id, so a caller reading `row.id` after the flush gets a real id, never None.
   An update that would open a second row for a key (re-key or reopen) is reverted to its
   previous key or state, so the queue keeps exactly one open action per requirement.

Scope, stated honestly:
- ORM writes only. A Core `insert(OwnerAction)` bypasses session flush events (B-4); no
  current site uses one.
- On Postgres the advisory lock is taken at the first such flush, possibly mid-transaction after
  a writer already holds row locks (B-6). A lock-order inversion with a writer that took the
  advisory lock first is broken by Postgres's deadlock detector (one transaction errors and its
  job retries); it does not hang.
- A database-level partial unique index (B-5) would be the authoritative constraint. It needs a
  data migration closing existing duplicates first, which `core.migrate` deliberately does not
  do ("those are real migrations and they need a human looking at them"); it is proposed to
  the integrator, not created here.
"""
from __future__ import annotations

from sqlalchemy import event, inspect as sa_inspect, select, text
from sqlalchemy.orm import Session

STATS = {"merged": 0, "reverted": 0}
_RESTATED = ("action", "reason", "max_cost_cad", "minutes", "consequence_of_delay", "blocks")


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


def _opening_update(obj):
    """('key', previous key) or ('done', True) when this dirty row is being made open for a
    key by this flush; None otherwise."""
    if obj.done or not (obj.requirement_key or "").strip():
        return None
    state = sa_inspect(obj)
    key_hist = state.attrs.requirement_key.history
    if key_hist.has_changes():
        return "key", (key_hist.deleted[0] if key_hist.deleted else "")
    done_hist = state.attrs.done.history
    if done_hist.has_changes() and done_hist.deleted and done_hist.deleted[0]:
        return "done", True
    return None


@event.listens_for(Session, "before_flush")
def _one_open_action_per_requirement(session: Session, _flush_context, _instances) -> None:
    from ..core.models import OwnerAction

    new = [o for o in session.new if isinstance(o, OwnerAction)
           and not o.done and (o.requirement_key or "").strip()]
    opening = [(o, _opening_update(o)) for o in session.dirty if isinstance(o, OwnerAction)]
    opening = [(o, how) for o, how in opening if how is not None]
    if not new and not opening:
        return
    _lock(session)
    keys = sorted({o.requirement_key for o in new} | {o.requirement_key for o, _ in opening})
    leaving = {o.id for o in session.dirty if isinstance(o, OwnerAction) and o.done} | {
        o.id for o in session.deleted if isinstance(o, OwnerAction)}
    moving = {o.id for o, _ in opening}
    with session.no_autoflush:
        holder: dict[str, object] = {}       # key -> the one row that stays open for it
        for rid, key in session.execute(
                select(OwnerAction.id, OwnerAction.requirement_key).where(
                    OwnerAction.requirement_key.in_(keys),
                    OwnerAction.done == False).order_by(OwnerAction.id)):  # noqa: E712
            if rid not in leaving and rid not in moving and key not in holder:
                holder[key] = session.get(OwnerAction, rid)
        # B-2/B-3: an update that would open a second row for a key is reverted.
        for obj, (how, old) in opening:
            if obj.requirement_key in holder:
                if how == "key":
                    obj.requirement_key = old
                else:
                    obj.done = True
                STATS["reverted"] += 1
            else:
                holder[obj.requirement_key] = obj
        # B-1: a new row for a key that already has its open row is merged onto that row.
        merged = []
        for obj in sorted(new, key=id):
            keeper = holder.get(obj.requirement_key)
            if keeper is None:
                holder[obj.requirement_key] = obj            # the first newcomer is inserted
                continue
            for field in _RESTATED:
                value = getattr(obj, field, None)
                if value not in (None, ""):
                    setattr(keeper, field, value)
            session.expunge(obj)
            merged.append((obj, keeper))
            STATS["merged"] += 1
    if merged:
        # The newcomer takes its keeper's id once the keeper has one (a keeper inserted in this
        # same flush gets it at flush time), so `row.id` is never None for the caller.
        pending = [(o, k) for o, k in merged if k.id is None]
        for obj, keeper in merged:
            if keeper.id is not None:
                obj.id = keeper.id
        if pending:
            @event.listens_for(session, "after_flush", once=True)
            def _give_ids(sess, _ctx, _pending=tuple(pending)):
                for obj, keeper in _pending:
                    obj.id = keeper.id
