from _h import *
from brambleloop.app.command_center import tabs, readers
from brambleloop.finance.accounting import controller, reconciliation as R
print("VALUE_STATES", readers.VALUE_STATES)
db = mkdb(seed=True)
controller.run_cycle(db, now=NOW)
R.import_statement(db, "bank", [{"external_id":"b1","at":NOW-timedelta(days=30),"kind":"owner_contribution","amount":500.0,"reference":"seed"}], now=NOW-timedelta(days=6))
R.match(db, now=NOW)
m = tabs.money(db)
print("tab status", m["status"], "revenue", m["revenue"].get("state"), m["revenue"].get("value_cad"), "| profit", m["profit"]["state"], m["profit"]["display"])
items = {i["metric"]:i for i in m["sections"]["accounting"]["items"]}
for k in ("gross_sales","fees","profit","cash","safe_discretionary_budget","tax_reserve","expected_payout"):
    i=items[k]; print(" ", k, i.get("state"), i.get("display"), "| provider_reading", i.get("provider_reading"))
for met in ("revenue","recorded_spend","profit","cash","bogus"):
    d = tabs.money_drill(db, met)
    print("DRILL", met, d.get("status"), (d.get("reason") or d.get("why") or "")[:120], "rows", len(d.get("rows") or d.get("items") or []))
