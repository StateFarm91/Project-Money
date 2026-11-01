import sys
sys.argv = ["x"]
import test_opus2_listing_package as T   # reuses the branch's own real-chain fixture
from sqlalchemy import inspect, text
from brambleloop.publish import listing_package as LP
db, cir, rh = T._release("idem")
def counts():
    with db.engine.connect() as c:
        return {t: c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                for t in inspect(db.engine).get_table_names()}
c0 = counts(); r1 = LP.sweep(db); c1 = counts(); r2 = LP.sweep(db); c2 = counts()
p1 = LP.latest(db, cir.slug, cir.version)
print("sweep1:", r1["releases"], "changed", r1["changed"], "| sweep2 changed", r2["changed"])
print("state:", p1["state"], "blockers:", len(p1["blockers"]))
print("rows written by sweep1 (excl. OperatingReading/audit):",
      {t: c1[t]-c0[t] for t in c1 if c1[t] != c0[t]})
print("rows written by sweep2:", {t: c2[t]-c1[t] for t in c2 if c2[t] != c1[t]})
print("disclosures:", p1["disclosures"]); print("gallery alt_text present:",
      [bool(f.get("alt_text")) for f in p1["gallery"]])
for b in p1["blockers"][:8]: print("  -", b["source"], b["why"][:140])
