from _h import *
from brambleloop.finance.accounting import shadow_dataset as sd, dashboard
from brambleloop.finance.books import Books
from brambleloop.commerce import orders_ingest
db = mkdb()
sd.connect_order_source(db)
orders_ingest.ingest(db, reader=sd._Feed([]), now=NOW)
d = Books(db).profit_and_loss(since=NOW-timedelta(days=30), until=NOW).to_dict()
print("books.py: sales_reading", d["sales_reading"], "cash_cad", d["cash_cad"], "cash_reading", d["cash_reading"], "net_profit", d["net_profit_cad"])
s = dashboard.summary(db, now=NOW); it={i["metric"]:i for i in s["items"]}
print("ledger : cash", it["cash"]["value_cad"], it["cash"]["reading"], "|", it["cash"]["why"][:70])
# with a real sale in books
sd_db = mkdb()
sd.connect_order_source(sd_db)
rec=[sd._receipt(3001, 701, 9001, 5000, NOW-timedelta(days=2))]
orders_ingest.ingest(sd_db, reader=sd._Feed(rec), now=NOW)
d = Books(sd_db).profit_and_loss(since=NOW-timedelta(days=30), until=NOW).to_dict()
print("books.py w/ 1 sale: cash_cad", d["cash_cad"], d["cash_reading"], "net_profit", d["net_profit_cad"], "all_observed", d["all_figures_observed"], "fees_basis", d["platform_fees_basis"])
from brambleloop.finance.books import ProfitAndLoss
pl = ProfitAndLoss(period_start="2026-09-01", period_end="2026-09-30", gross_sales_cad=100.0, platform_fees_cad=10.0, fees_by_basis={"measured":10.0}, cost_by_kind={"llm":5.0}, operating_costs_by_basis={"measured":5.0})
d = pl.to_dict(); print("all-measured P&L: net_profit", d["net_profit_cad"], "-> cash_cad", d["cash_cad"], d["cash_reading"], "(no bank statement exists)")
