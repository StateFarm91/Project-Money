from _h import *
from brambleloop.finance.accounting import shadow_dataset as sd, dashboard, controller
from brambleloop.finance.books import Books
from brambleloop.app.command_center import tabs
db = mkdb()
sd.seed(db, now=NOW-timedelta(days=10))   # last order read 10 days ago
controller.run_cycle(db, now=NOW-timedelta(days=10))
s = dashboard.summary(db, now=NOW, window="all")
it = {i["metric"]:i for i in s["items"]}
print("ledger summary status", s["status"], "| gross_sales", it["gross_sales"]["value_cad"], it["gross_sales"]["reading"], "| profit", it["profit"]["reading"])
pl = Books(db).profit_and_loss(since=NOW-timedelta(days=60), until=NOW)
print("books.py sales_reading:", pl.sales_reading, "| order_source.last_read_at:", pl.order_source.get("last_read_at"), "| all_figures_observed:", pl.to_dict()["all_figures_observed"], "profit_basis", pl.to_dict()["profit_basis"])
m = tabs.money(db)
print("MONEY tab headline revenue:", m["revenue"]["state"], m["revenue"].get("value_cad"), "|", m["revenue"].get("why"))
print("   source_health:", m["source_health"])
