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


def _drop_index(db):
    from sqlalchemy import text

    with db.engine.begin() as conn:
        conn.execute(text("DROP INDEX uq_owner_actions_open_requirement"))


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
    """Proves the harness forces the race (so the test above is not vacuous).

    Without the guard both threads insert. Since B-5 the database's own unique index refuses
    the second insert, so the race now surfaces as an IntegrityError instead of a second row;
    with the index dropped too, the duplicate is stored."""
    from sqlalchemy.exc import IntegrityError

    db = _db()
    event.remove(Session, "before_flush", G._one_open_action_per_requirement)
    try:
        errors = _race(_read_then_insert, db)
        assert len(errors) == 1 and isinstance(errors[0], IntegrityError), errors
        assert len(_open(db)) == 1
        bare = _db()
        _drop_index(bare)
        assert _race(_read_then_insert, bare) == []
        assert len(_open(bare)) == 2
    finally:
        event.listen(Session, "before_flush", G._one_open_action_per_requirement)


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


def test_review_opus2f_b1_the_loser_is_merged_and_keeps_a_real_id():
    db = _db()
    _read_then_insert(db)
    with db.session() as s:
        first_id = s.scalar(select(OwnerAction.id).where(OwnerAction.requirement_key == KEY))
    with db.session() as s:
        late = OwnerAction(requirement_key=KEY, action="restated text", reason="newer reason")
        s.add(late)
        s.flush()
        assert late.id == first_id, (late.id, first_id)   # int(row.id) works for the caller
    rows = _open(db)
    assert len(rows) == 1 and rows[0].action == "restated text" and rows[0].reason == \
        "newer reason"
    # Two newcomers in one flush: one is inserted, the other takes its id.
    with db.session() as s:
        a = OwnerAction(requirement_key="pair-key", action="a", reason="r")
        b = OwnerAction(requirement_key="pair-key", action="b", reason="r")
        s.add_all([a, b])
        s.flush()
        assert a.id is not None and a.id == b.id
    assert len(_open(db, "pair-key")) == 1


def test_review_opus2f_b2_b3_rekeying_or_reopening_never_opens_a_second_row():
    db = _db()
    _read_then_insert(db)
    with db.session() as s:
        s.add(OwnerAction(requirement_key="", action="legacy keyless", reason="r"))
        s.add(OwnerAction(requirement_key=KEY, action="old", reason="r", done=True))
    with db.session() as s:                                 # B-2: re-key onto an open key
        legacy = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == ""))
        legacy.requirement_key = KEY
    with db.session() as s:                                 # B-3: reopen beside an open row
        old = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == KEY,
                                                 OwnerAction.done == True))  # noqa: E712
        old.done = False
    assert len(_open(db)) == 1
    with db.session() as s:
        assert s.scalar(select(OwnerAction).where(OwnerAction.action == "legacy keyless")
                        ).requirement_key == ""
    # A re-key onto a key with no open row is untouched.
    with db.session() as s:
        legacy = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == ""))
        legacy.requirement_key = "fresh-key"
    assert len(_open(db, "fresh-key")) == 1


def test_review_opus2ef2_ef26_a_merge_never_lowers_a_stated_ceiling():
    from brambleloop.core.models import MAX_COST_UNKNOWN

    db = _db()
    with db.session() as s:                       # the reviewer's repro
        s.add(OwnerAction(requirement_key="SPEND", action="a", reason="r", max_cost_cad=50.0,
                          max_cost_basis="stated"))
    with db.session() as s:
        s.add(OwnerAction(requirement_key="SPEND", action="a2", reason="r", max_cost_cad=0.0,
                          max_cost_basis=MAX_COST_UNKNOWN))
    [row] = _open(db, "SPEND")
    assert row.max_cost_basis == MAX_COST_UNKNOWN and row.max_cost_known is None
    # Two stated figures keep the higher, in either order.
    with db.session() as s:
        s.add(OwnerAction(requirement_key="CAP", action="a", reason="r", max_cost_cad=50.0))
    for restated in (10.0, 80.0):
        with db.session() as s:
            s.add(OwnerAction(requirement_key="CAP", action="a", reason="r",
                              max_cost_cad=restated))
    [row] = _open(db, "CAP")
    assert row.max_cost_known == 80.0, row.max_cost_cad
    # OPUS2G D-4: a lower restatement never wins (50 then 10 stays 50).
    with db.session() as s:
        s.add(OwnerAction(requirement_key="DROP", action="a", reason="r", max_cost_cad=50.0))
    with db.session() as s:
        s.add(OwnerAction(requirement_key="DROP", action="a", reason="r", max_cost_cad=10.0))
    [row] = _open(db, "DROP")
    assert row.max_cost_known == 50.0, row.max_cost_cad
    # A restatement that names no ceiling leaves it alone; why/expiry are restated.
    with db.session() as s:
        s.add(OwnerAction(requirement_key="CAP", action="a", reason="r",
                          why_software_cannot="KYC"))
    [row] = _open(db, "CAP")
    assert row.max_cost_known == 80.0 and row.why_software_cannot == "KYC"


def test_review_opus2ef2_ef28_a_reverted_reopen_keeps_the_owners_outcome():
    db = _db()
    _read_then_insert(db)
    with db.session() as s:
        s.add(OwnerAction(requirement_key=KEY, action="old", reason="r", done=True,
                          state="satisfied", state_reason="owner did it"))
    with db.session() as s:
        old = s.scalar(select(OwnerAction).where(OwnerAction.action == "old"))
        before = (old.state, old.state_at, old.state_reason)
        old.done = False                          # reopen beside the open row: reverted
    with db.session() as s:
        old = s.scalar(select(OwnerAction).where(OwnerAction.action == "old"))
        assert old.done is True
        assert (old.state, old.state_reason) == ("satisfied", "owner did it"), old.state
        assert (old.state, old.state_at, old.state_reason)[0] == before[0]
    assert len(_open(db)) == 1


def test_b5_the_database_itself_holds_one_open_action_per_requirement():
    """B-4 closed by B-5: a Core write that bypasses the session guard is refused by the index."""
    from sqlalchemy import insert, update
    from sqlalchemy.exc import IntegrityError

    db = _db()
    _read_then_insert(db)
    for stmt in (insert(OwnerAction).values(requirement_key=KEY, action="core", reason="r",
                                            done=False),):
        try:
            with db.engine.begin() as conn:
                conn.execute(stmt)
            raise AssertionError("a Core insert opened a second row")
        except IntegrityError:
            pass
    with db.engine.begin() as conn:                     # closed and keyless rows are free
        conn.execute(insert(OwnerAction).values(requirement_key=KEY, action="c", reason="r",
                                                done=True))
        conn.execute(insert(OwnerAction).values(requirement_key="", action="k1", reason="r",
                                                done=False))
        conn.execute(insert(OwnerAction).values(requirement_key="", action="k2", reason="r",
                                                done=False))
    try:                                                # a Core reopen is refused too
        with db.engine.begin() as conn:
            conn.execute(update(OwnerAction).where(OwnerAction.action == "c").values(done=False))
        raise AssertionError("a Core reopen opened a second row")
    except IntegrityError:
        pass
    assert len(_open(db)) == 1


def test_b5_migrate_defers_the_index_over_duplicates_and_the_dedupe_step_clears_them():
    from sqlalchemy import insert, inspect

    from brambleloop.core import migrate
    from brambleloop.ops import owner_queue_dedupe as D

    db = _db()
    _drop_index(db)                                     # a database from before B-5
    with db.engine.begin() as conn:
        for action in ("first", "second", "newest"):
            conn.execute(insert(OwnerAction).values(requirement_key=KEY, action=action,
                                                    reason="r", done=False))
        conn.execute(insert(OwnerAction).values(requirement_key="other", action="solo",
                                                reason="r", done=False))
    assert D.conflicts(db.engine) == 1
    changes = migrate.apply(db.engine)                  # never fails, never alters data
    assert any("DEFERRED" in c and D.INDEX in c for c in changes), changes
    assert D.INDEX not in {i["name"] for i in inspect(db.engine).get_indexes("owner_actions")}
    assert len(_open(db)) == 3
    closed = D.close_duplicates(db.engine)
    assert len(closed) == 2 and {c["kept"] for c in closed} == {max(r.id for r in _open(db))}
    [kept] = _open(db)
    assert kept.action == "newest" and len(_open(db, "other")) == 1
    with db.session() as s:
        gone = list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == KEY,
                                                        OwnerAction.done == True)))  # noqa: E712
        assert {g.state for g in gone} == {"superseded"}
        assert all(f"#{kept.id}" in g.state_reason for g in gone)
    assert D.close_duplicates(db.engine) == [] and D.conflicts(db.engine) == 0
    assert any(c == f"index {D.INDEX}" for c in migrate.apply(db.engine))
    assert D.INDEX in {i["name"] for i in inspect(db.engine).get_indexes("owner_actions")}


def test_review_opus2ef2_ef27_ensure_returns_the_stored_row_so_later_edits_land():
    from brambleloop.ops import owner_queue

    db = _db()
    with db.session() as s:
        first = owner_queue.ensure(s, "ENS", action="decide", reason="r", max_cost_cad=40.0)
        first_id = first.id
    with db.session() as s:
        row = owner_queue.ensure(s, "ENS", action="decide again", reason="newer",
                                 max_cost_cad=10.0)
        assert row.id == first_id and row in s            # the persistent row, not a copy
        row.why_software_cannot = "KYC"                   # an edit after the write lands
    [stored] = _open(db, "ENS")
    assert (stored.action, stored.reason, stored.why_software_cannot) == (
        "decide again", "newer", "KYC")
    assert stored.max_cost_known == 40.0                  # the ceiling was not lowered
    try:
        with db.session() as s:
            owner_queue.ensure(s, "  ", action="x")
        raise AssertionError("a keyless requirement was ensured")
    except ValueError:
        pass


def test_review_opus2g_d1_dedupe_keeps_the_owners_deferral_and_never_lowers_a_ceiling():
    from sqlalchemy import insert

    from brambleloop.core.models import MAX_COST_UNKNOWN, AuditLog
    from brambleloop.ops import owner_queue_dedupe as D

    db = _db()
    _drop_index(db)
    with db.engine.begin() as conn:                   # the reviewer's repro, written by Core
        conn.execute(insert(OwnerAction).values(
            requirement_key="K", action="deferred", reason="r", done=False, state="parked",
            state_reason="deferred by the owner", max_cost_cad=0.0,
            max_cost_basis=MAX_COST_UNKNOWN))
        conn.execute(insert(OwnerAction).values(requirement_key="K", action="re-raised",
                                                reason="r", done=False, max_cost_cad=0.0))
        conn.execute(insert(OwnerAction).values(requirement_key="C", action="fifty",
                                                reason="r", done=False, max_cost_cad=50.0))
        conn.execute(insert(OwnerAction).values(requirement_key="C", action="zero",
                                                reason="r", done=False, max_cost_cad=0.0))
    closed = D.close_duplicates(db.engine)
    assert len(closed) == 2
    [k] = _open(db, "K")
    assert k.state == "parked" and k.action == "deferred"            # the owner's deferral kept
    assert k.max_cost_known is None                                   # UNKNOWN stays UNKNOWN
    [c] = _open(db, "C")
    assert c.max_cost_known == 50.0                                    # never lowered to 0.00
    with db.session() as s:
        audits = [a for a in s.scalars(select(AuditLog).where(
            AuditLog.action == "owner_action.lifecycle"))]
        assert len(audits) == 2 and all(a.detail["to"] == "superseded" for a in audits)


def test_review_opus2g_d2_an_acceptance_ruling_lands_on_the_stored_row():
    from brambleloop.app.command_center import approvals
    from brambleloop.build2 import executor

    db = _db()
    with db.session() as s:                            # an open row already under the key
        s.add(OwnerAction(requirement_key=executor.ACCEPTANCE_RULING_KEY,
                          action="older open request", reason="r"))
    ruling = sorted(approvals.ACCEPTANCE_RULINGS)[0]
    out = approvals._record_acceptance_ruling(db, ruling, "owner reason", actor="owner")
    with db.session() as s:
        row = s.get(OwnerAction, out["owner_action_id"])
        assert row.done is True and row.state == "satisfied", (row.done, row.state)
    assert _open(db, executor.ACCEPTANCE_RULING_KEY) == []


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
