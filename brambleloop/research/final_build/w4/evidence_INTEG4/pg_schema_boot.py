"""INTEG4 migration proof (local throwaway PostgreSQL only, never production).
usage: pg_schema_boot.py URL MODE(reset|boot) OUT.json
Boots `Database.create_all()` with whichever brambleloop is on PYTHONPATH and dumps
{table: {column: type/nullable/default}} plus the create_all change list."""
import json, sys
from sqlalchemy import inspect, text
from brambleloop.core.db import Database
url, mode, out = sys.argv[1:4]
db = Database(url)
if mode == "reset":
    with db.engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
changes = db.create_all()
ins = inspect(db.engine)
schema = {t: {c["name"]: [str(c["type"]), c["nullable"], str(c.get("default"))]
              for c in ins.get_columns(t)} for t in sorted(ins.get_table_names())}
json.dump({"changes": [str(x) for x in (changes or [])], "schema": schema}, open(out, "w"), indent=1)
print(mode, "tables:", len(schema), "create_all changes:", changes)
