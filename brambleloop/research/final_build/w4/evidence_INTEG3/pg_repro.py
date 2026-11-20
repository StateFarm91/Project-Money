"""INTEG3: reproduce the ops.policy_watch dead letter on Postgres 16 and prove the widening.

Usage: PYTHONPATH=src python pg_repro.py postgresql+psycopg2://...  (a throwaway database)
1. builds the schema as production has it (policy_snapshots.version VARCHAR(40));
2. runs policy_knowledge.seed_snapshots -> the production error (or, after the fix, none);
3. runs Database.create_all() (migrate.widen) and seeds again.
"""
import sys

from sqlalchemy import inspect, text

from brambleloop.core.db import Database
from brambleloop.gates import policy_knowledge

db = Database(sys.argv[1])
with db.engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
print("changes on first create_all:", db.create_all()[:3])
with db.engine.begin() as c:   # the production column width before INTEG3
    c.execute(text('ALTER TABLE policy_snapshots ALTER COLUMN version TYPE VARCHAR(40)'))
w = lambda: [c["type"] for c in inspect(db.engine).get_columns("policy_snapshots")
             if c["name"] == "version"][0]
print("version column:", w())
try:
    policy_knowledge.seed_snapshots(db)
    print("seed on VARCHAR(40): OK (unexpected)")
except Exception as e:
    print("seed on VARCHAR(40): FAILED", type(e).__name__, str(e).splitlines()[0][:120])
print("create_all (migrate) changes:", [x for x in db.create_all() if "policy" in x])
print("version column:", w())
got = policy_knowledge.seed_snapshots(db)
with db.engine.connect() as c:
    print("seeded:", len(got["seeded"]), "max version length:",
          c.execute(text("select max(length(version)) from policy_snapshots")).scalar())
print("second create_all changes:", [x for x in db.create_all() if "policy" in x])
