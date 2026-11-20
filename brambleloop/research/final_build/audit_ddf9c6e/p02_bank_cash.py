from _h import *
from brambleloop.finance.accounting import dashboard, cash, reconciliation as R, posting_rules, close
db = mkdb(seed=True)
# A: bank statements stale (imported 6 days ago) -> cash_known True
R.import_statement(db, "bank", [{"external_id":"b1","at":NOW-timedelta(days=30),"kind":"owner_contribution","amount":500.0,"reference":"seed"}], now=NOW-timedelta(days=6))
R.match(db, now=NOW)
s = dashboard.summary(db, now=NOW)
it = {i["metric"]:i for i in s["items"]}
print("A stale-bank (6d) cash:", it["cash"]["value_cad"], it["cash"]["reading"], "|", it["cash"]["why"])
print("  safe:", it["safe_discretionary_budget"]["value_cad"], it["safe_discretionary_budget"]["reading"])
s8 = dashboard.summary(db, now=NOW+timedelta(days=3))
it8 = {i["metric"]:i for i in s8["items"]}
print("A2 bank 9d old cash:", it8["cash"]["value_cad"], it8["cash"]["reading"], s8["source_health"]["bank"]["state"])
print("  safe:", it8["safe_discretionary_budget"]["value_cad"], it8["safe_discretionary_budget"]["reading"])
# B: bank deposit imported but not matched -> not posted; bank balance snapshot says 1234
db2 = mkdb(seed=True)
R.import_statement(db2, "bank", [
  {"external_id":"d1","at":NOW-timedelta(days=2),"kind":"deposit","amount":900.0,"reference":"NOPAYOUT"},
  {"external_id":"bal","at":NOW-timedelta(days=1),"kind":"balance","amount":1234.0,"reference":"snap"}], now=NOW)
R.match(db2, now=NOW)
s = dashboard.summary(db2, now=NOW)
it = {i["metric"]:i for i in s["items"]}
print("B unmatched deposit; snapshot 1234: cash", it["cash"]["value_cad"], it["cash"]["reading"], "safe", it["safe_discretionary_budget"]["value_cad"])
d = dashboard.drill(db2,"cash",now=NOW); print("  drill cash", d["value_cad"], d["reading"], d["status"])
