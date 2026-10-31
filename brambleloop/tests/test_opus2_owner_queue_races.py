"""OPUS2 (P1-OWNER-QUEUE-RACES): no writer can queue one owner requirement twice.

`ops.owner_queue_guard` serialises every flush that inserts an open `OwnerAction` (the same
lock `release._serialise_owner_queue` takes) and re-checks the open keys under it. The race
is forced, not hoped for: a barrier holds each thread right after its read of the owner
queue, so both read "absent" before either writes -- exactly the interleaving that produced
duplicates. With the guard removed, the same harness produces the duplicate, so the test
proves the harness reproduces the race and the guard closes it.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_owner_queue_races.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import event, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import OwnerAction  # noqa: E402
from brambleloop.ops import owner_queue_guard as G  # noqa: E402

KEY = "opus2-race-fixture"


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/race.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


@contextmanager
def _barrier_after_owner_queue_reads(parties=2):
    """Every racing thread waits once, right after its first SELECT of owner_actions."""
    barrier = threading.Barrier(parties, timeout=3)
    waited = threading.local()

    def hook(orm_execute_state):
        if not orm_execute_state.is_select or getattr(waited, "done", False):
            return
        tables = {getattr(d.get("entity"), "__tablename__", None)
                  for d in orm_execute_state.statement.column_descriptions}
        if "owner_actions" in tables and getattr(threading.current_thread(), "racing", False):
            result = orm_execute_state.invoke_statement()
            waited.done = True
            try:
                barrier.wait()          # unserialised: both hold their "absent" read here
            except threading.BrokenBarrierError:
                pass                    # serialised: the other thread waits on the lock
            return result

    event.listen(Session, "do_orm_execute", hook)
    try:
        yield
    finally:
        event.remove(Session, "do_orm_execute", hook)


def _race(writer, db, n=2):
    errors: list[BaseException] = []

    def run():
        threading.current_thread().racing = True
        try:
            writer(db)
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    with _barrier_after_owner_queue_reads(n):
        threads = [threading.Thread(target=run) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
    return errors


def _open(db, key=KEY):
    with db.session() as s:
        return list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == key,
                                                         OwnerAction.done == False)))  # noqa: E712


def _read_then_insert(db, key=KEY):
    """The shape INTEGFIX LOW-3 found in some forty writers: read open, insert if absent."""
    with db.session() as s:
        if s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key,
                                              OwnerAction.done == False)) is None:  # noqa: E712
            s.add(OwnerAction(requirement_key=key, action="decide", reason="r"))


def test_a_forced_read_then_insert_race_queues_one_action():
    db = _db()
    assert _race(_read_then_insert, db) == []
    assert len(_open(db)) == 1


def test_without_the_guard_the_same_harness_reproduces_the_duplicate():
    """Proves the harness forces the race (so the test above is not vacuous)."""
    db = _db()
    event.remove(Session, "before_flush", G._one_open_action_per_requirement)
    try:
        assert _race(_read_then_insert, db) == []
    finally:
        event.listen(Session, "before_flush", G._one_open_action_per_requirement)
    assert len(_open(db)) == 2


def test_a_real_unlocked_writer_queues_its_requirement_once():
    """`etsy_ops.record_auth_needs_owner` reads then inserts with no lock of its own."""
    from brambleloop.runtime import etsy_ops

    db = _db()
    errors = _race(lambda d: etsy_ops.record_auth_needs_owner(
        d, "401 invalid_token", where="race-fixture"), db)
    assert errors == [], errors
    assert len(_open(db, etsy_ops.AUTH_KEY)) == 1


def test_closing_and_replacing_in_one_flush_keeps_the_replacement():
    db = _db()
    _read_then_insert(db)
    with db.session() as s:
        old = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == KEY))
        old.done = True
        s.add(OwnerAction(requirement_key=KEY, action="restated", reason="r2"))
    rows = _open(db)
    assert len(rows) == 1 and rows[0].action == "restated"


def test_closed_rows_keyless_rows_and_two_new_rows_in_one_flush():
    db = _db()
    with db.session() as s:
        s.add(OwnerAction(requirement_key="", action="a", reason="r"))
        s.add(OwnerAction(requirement_key="", action="b", reason="r"))
        s.add(OwnerAction(requirement_key=KEY, action="closed", reason="r", done=True))
        s.add(OwnerAction(requirement_key=KEY, action="first", reason="r"))
        s.add(OwnerAction(requirement_key=KEY, action="second", reason="r"))
    with db.session() as s:
        keyless = list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == "")))
        closed = list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == KEY,
                                                           OwnerAction.done == True)))  # noqa: E712
    assert len(keyless) == 2 and len(closed) == 1
    assert len(_open(db)) == 1          # two new rows for one key in one flush: one is kept


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
