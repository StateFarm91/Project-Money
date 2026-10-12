from _h import *
from brambleloop.core.models import Listing, CostEntry
from brambleloop.finance import sustainability as S
db = mkdb()
now = NOW
with db.session() as s:
    s.add(Listing(product_slug="p1", version="1.0.0", title="t", description="", price_cad=8.0, state="draft", created_at=now - timedelta(days=20)))
    for i in range(25):
        s.add(CostEntry(at=now - timedelta(days=20 - i*0.7), agent="a", kind="llm", amount_cad=0.5, product_slug="p1" if i%5==0 else "", detail={"price_basis":"assumed"}))
print("scenarios", {k:v["sales_per_month"] for k,v in S.SCENARIOS.items()})
v = S.verdict(db, now=now); print("default: sustainable", v["sustainable"], "measured_orders", v["measured_orders"], "|", v["problems"][:2])
saved = {k: dict(v) for k,v in S.SCENARIOS.items()}
for vol in (1, 5, 1_000_000):
    for sc in S.SCENARIOS.values(): sc["sales_per_month"]=vol
    v = S.verdict(db, now=now); print("assumed volume", vol, "-> sustainable", v["sustainable"], "measured_orders", v["measured_orders"])
