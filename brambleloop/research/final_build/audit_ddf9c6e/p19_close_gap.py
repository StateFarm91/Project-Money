from _h import *
from brambleloop.finance.accounting import close, controller, reconciliation as R, exceptions as X, ledger
from brambleloop.finance.accounting import views
db = mkdb(seed=True); controller.run_cycle(db, now=NOW)
y,m = NOW.year, NOW.month; py, pm = (y-1,12) if m==1 else (y,m-1); prev=f"{py}-{pm:02d}"
print("prev", prev, "open exceptions:", len(X.listing(db)))
# 1) import statement lines in prev period that match nothing (a stray fee + a missing-order refund) -- no match() run
R.import_statement(db, "etsy_ledger", [
  {"external_id":"z1","at":datetime(py,pm,15,tzinfo=timezone.utc),"kind":"fee","amount":-40.0,"reference":"9999999"},
  {"external_id":"z2","at":datetime(py,pm,16,tzinfo=timezone.utc),"kind":"refund","amount":-55.0,"reference":"8888888"}], now=NOW)
cl = close.checklist(db, prev, now=NOW)
print("with 2 unmatched, unprocessed statement lines (match() not yet run): closable =", cl["closable"], "| steps non-pass:", [(s["step"],s["outcome"]) for s in cl["steps"] if s["outcome"]!="pass"])
r = close.lock_period(db, prev, by="J-audit", now=NOW)
print("LOCKED:", r["locked"], "| verify_lock", close.verify_lock(db, prev))
R.match(db, now=NOW)
print("after match(): open exceptions now", [(x['kind'], x['period']) for x in X.listing(db)])
print("period", prev, "is locked yet has", len(X.listing(db, period=prev)), "open exception(s) -- they can never block that close")
