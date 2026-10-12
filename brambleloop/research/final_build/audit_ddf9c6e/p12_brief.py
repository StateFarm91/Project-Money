from _h import *
from brambleloop.app.command_center import tabs
from brambleloop.core.models import CostEntry
db = mkdb()
b = tabs.morning_brief(db)["sections"]["money_spent"]
print("empty:", b["status"], b["total"])
with db.session() as s:
    s.add(CostEntry(at=NOW, kind="etsy_listing_fee", agent="x", provider="etsy", model="", purpose="reserve", amount_cad=0.28, detail={"basis":"modelled"}))
    s.add(CostEntry(at=NOW, kind="llm", agent="x", provider="anthropic", model="m", purpose="p", amount_cad=1.0, estimated_cad=1.0, detail={}))
b = tabs.morning_brief(db)["sections"]["money_spent"]
print("with modelled/estimated rows:", b["total"], [ (i["kind"],i["amount_cad"]) for i in b["items"]])
from brambleloop.finance.listing_costs import cost_basis
with db.session() as s:
    for c in s.query(CostEntry): print("  row", c.kind, "cost_basis ->", cost_basis(c))
