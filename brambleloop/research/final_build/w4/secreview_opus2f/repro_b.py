"""Repro for Subject B findings (run from the B worktree's brambleloop/, PYTHONPATH=src:tests)."""
import tempfile
from sqlalchemy import insert, select, func
from brambleloop.core.db import Database
from brambleloop.core.models import OwnerAction
from brambleloop.ops import owner_queue_guard as G
db = Database(f"sqlite:///{tempfile.mkdtemp()}/b.sqlite"); db.create_all()
def mk(key, **k):
    return OwnerAction(requirement_key=key, action="a " + key, reason="r", max_cost_cad=0.0,
                       minutes=1, consequence_of_delay="c", blocks="b", **k)
def open_count(key):
    with db.session() as s:
        return s.scalar(select(func.count()).select_from(OwnerAction).where(
            OwnerAction.requirement_key == key, OwnerAction.done == False))  # noqa: E712
# B-1: the race loser's object is silently expunged; a writer that returns/links `.id` gets None.
with db.session() as s:
    s.add(mk("K1"))
with db.session() as s:          # the "loser": it read absent earlier, the winner committed
    obj = mk("K1"); s.add(obj); s.flush(); loser_id = obj.id
print("B-1 loser flush -> obj.id =", loser_id, "(voice_selection does int(row.id) -> TypeError;"
      " ads_readiness links proposal.owner_action_id=None)")
# B-2: update path (adopt/re-key a keyless or legacy open row) is not guarded.
with db.session() as s:
    s.add(mk("K2")); s.add(mk(""))
with db.session() as s:
    row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == ""))
    row.requirement_key = "K2"
print("B-2 open rows for K2 after a re-key update:", open_count("K2"))
# B-3: reopen (done True -> False) of an older row beside an open one is not guarded.
with db.session() as s:
    a = mk("K3", done=True); s.add(a); s.flush(); s.add(mk("K3"))
with db.session() as s:
    old = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == "K3",
                                             OwnerAction.done == True)); old.done = False  # noqa: E712
print("B-3 open rows for K3 after a reopen:", open_count("K3"))
# B-4: a Core insert bypasses the before_flush hook.
with db.session() as s:
    s.add(mk("K4"))
with db.session() as s:
    s.execute(insert(OwnerAction).values(requirement_key="K4", action="x", reason="r",
              max_cost_cad=0.0, minutes=1, consequence_of_delay="c", blocks="b", done=False))
print("B-4 open rows for K4 after a Core insert:", open_count("K4"), "dedup stat", G.STATS)
# B-5: a partial unique index is expressible on SQLite (and Postgres) and would refuse all of the above.
from sqlalchemy import text
db2 = Database(f"sqlite:///{tempfile.mkdtemp()}/c.sqlite"); db2.create_all()
with db2.engine.begin() as c:
    c.execute(text("CREATE UNIQUE INDEX uq_open_req ON owner_actions(requirement_key) "
                   "WHERE done = 0 AND requirement_key <> ''"))
try:
    with db2.session() as s:
        s.add(mk("K5"))
    with db2.engine.begin() as c:
        c.execute(text("INSERT INTO owner_actions (requirement_key, action, reason, max_cost_cad,"
                       " minutes, consequence_of_delay, blocks, done) "
                       "VALUES ('K5','x','r',0,1,'c','b',0)"))
    print("B-5 index did NOT refuse")
except Exception as e:  # noqa: BLE001
    print("B-5 partial unique index refuses a second open K5:", type(e).__name__)
