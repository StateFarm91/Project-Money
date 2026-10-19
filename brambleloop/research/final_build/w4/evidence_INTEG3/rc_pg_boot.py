import sys
from sqlalchemy import inspect, text
from brambleloop.core.db import Database
db = Database(sys.argv[1])
if sys.argv[2] == "reset":
    with db.engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
changes = db.create_all()
t = set(inspect(db.engine).get_table_names())
print(sys.argv[2], "tables:", len(t), "changes:", changes[:10])
for n in ("etsy_webhook_refusals", "prospecting_brief_cursors"):
    print("  ", n, n in t)
