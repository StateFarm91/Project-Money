from _h import *
from brambleloop.finance.accounting import dashboard, views, controller
from brambleloop.core.models import CostEntry, LedgerEntry
db = mkdb(seed=True)
controller.run_cycle(db, now=NOW)
s = dashboard.summary(db, now=NOW)
it = {i["metric"]:i for i in s["items"]}
acc = views.accrual(db, since=NOW-timedelta(days=30), until=NOW)
print("revenue_by_basis_cad:", acc["revenue_by_basis_cad"], "all_measured:", acc["all_measured"], "summary basis:", s["basis"])
for k in ("gross_sales","net_sales","refunds"): print(k, it[k]["value_cad"], it[k]["reading"], "estimated_cad", it[k]["estimated_cad"], "actual_cad", it[k]["actual_cad"])
# profit when fees all measured & opex measured but revenue modelled: isolate
db2 = mkdb()
from brambleloop.finance.accounting import shadow_dataset as sd
sd.connect_order_source(db2)
from brambleloop.commerce import orders_ingest
rec = [sd._receipt(2001, 601, 9001, 1000, NOW-timedelta(days=1), currency="USD")]
orders_ingest.ingest(db2, reader=sd._Feed(rec), now=NOW)
s2 = dashboard.summary(db2, now=NOW); it2={i["metric"]:i for i in s2["items"]}
acc2 = views.accrual(db2, since=NOW-timedelta(days=30), until=NOW)
print("USD-only: revenue_by_basis", acc2["revenue_by_basis_cad"], "fees_by_basis", acc2["fees_by_basis_cad"])
for k in ("gross_sales","net_sales","fees","profit","tax_reserve"): print(" ", k, it2[k]["value_cad"], it2[k]["reading"], "est", it2[k]["estimated_cad"])
