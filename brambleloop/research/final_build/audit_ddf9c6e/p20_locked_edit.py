from _h import *
from sqlalchemy import select
from brambleloop.finance.accounting import close, controller, views, dashboard, ledger
from brambleloop.core.models import LedgerEntry, CostEntry
db = mkdb(seed=True); controller.run_cycle(db, now=NOW)
y,m = NOW.year, NOW.month; py, pm = (y-1,12) if m==1 else (y,m-1); prev=f"{py}-{pm:02d}"
close.lock_period(db, prev, by="J", now=NOW)
before = views.accrual(db, period=prev)["accrual_gross_sales_cad"]
with db.session() as s:   # source row edited in place after the lock (LedgerEntry is mutable)
    e = s.scalars(select(LedgerEntry).where(LedgerEntry.category=="sale", LedgerEntry.at < datetime(NOW.year,NOW.month,1,tzinfo=timezone.utc)).order_by(LedgerEntry.id)).first()
    print("editing ledger row", e.id, "gross", e.gross_cad, "->", e.gross_cad+100); e.gross_cad += 100
r = controller.run_cycle(db, now=NOW)
print("cycle posting:", {k:v for k,v in r["posting"].items() if v})
print("locked period gross before", before, "after", views.accrual(db, period=prev)["accrual_gross_sales_cad"], "| verify_lock", close.verify_lock(db, prev))
cur = views.accrual(db, period=NOW.strftime("%Y-%m"))
print("current period gross includes late adj:", cur["accrual_gross_sales_cad"], "| chain", ledger.verify_chain(db)["ok"])
s = dashboard.summary(db, now=NOW); print("summary exceptions", s["exceptions"]["open"])
