"""INTEG5 migration proof, full lazy surface (local throwaway PostgreSQL only, never production).
usage: pg_schema_boot_full.py URL MODE(reset|boot) OUT.json

`Database.create_all()` registers only the modules core/db.py imports, so tables that are
created lazily on first use (laura.agency.models.ensure_tables: laura_cost_events,
laura_boundary_crossings; the private store's own PrivateBase metadata) do not appear in a
plain boot. This script imports EVERY brambleloop module on PYTHONPATH (failures are listed),
runs create_all, then creates every table registered on core.db.Base and on the private
store's PrivateBase -- a superset of any code path's lazy creation -- and dumps the schema."""
import importlib, json, pkgutil, sys
from sqlalchemy import inspect, text
import brambleloop
from brambleloop.core.db import Base, Database
url, mode, out = sys.argv[1:4]
failed = []
for m in pkgutil.walk_packages(brambleloop.__path__, "brambleloop."):
    if ".tests" in m.name or m.name.endswith("__main__"):
        continue
    try:
        importlib.import_module(m.name)
    except BaseException as e:  # noqa: BLE001 - recorded, not hidden
        failed.append(f"{m.name}: {type(e).__name__}")
db = Database(url)
if mode == "reset":
    with db.engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
changes = db.create_all()
Base.metadata.create_all(db.engine)
try:
    from brambleloop.laura.private.models import PrivateBase
    PrivateBase.metadata.create_all(db.engine)
except ImportError:
    pass
ins = inspect(db.engine)
schema = {t: {c["name"]: [str(c["type"]), c["nullable"], str(c.get("default"))]
              for c in ins.get_columns(t)} for t in sorted(ins.get_table_names())}
json.dump({"changes": [str(x) for x in (changes or [])], "schema": schema,
           "import_failures": failed}, open(out, "w"), indent=1)
print(mode, "tables:", len(schema), "create_all changes:", changes,
      "| modules that failed to import:", len(failed), failed[:8])
