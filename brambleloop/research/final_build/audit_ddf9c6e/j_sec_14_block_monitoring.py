from j_sec_common import *
from brambleloop.autonomy import orchestrator
c=client(); csrf=login(c)
for d in ("executive","finance","platform","product_truth"):
    p=c.post("/api/cc/emergency/pause", headers=fresh(csrf), json={"scope":"department","department":d,"reason":"try pause"})
    b=c.post(f"/api/cc/departments/{d}/block", headers=fresh(csrf), json={"reason":"x"})
    print(d, "| pause:", p.status_code, p.json().get("code"), "| block (no step-up):", b.status_code)
rep=orchestrator.tick(db)
print({k:v.get("state") for k,v in rep["departments"].items() if k in ("executive","finance","platform","product_truth")})
