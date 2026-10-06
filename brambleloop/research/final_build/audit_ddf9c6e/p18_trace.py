from _h import *
from brambleloop.finance.accounting import dashboard, controller, reconciliation as R
db = mkdb(seed=True); controller.run_cycle(db, now=NOW)
R.import_statement(db, "bank", [{"external_id":"b1","at":NOW-timedelta(days=3),"kind":"owner_contribution","amount":500.0,"reference":"seed"}], now=NOW); R.match(db, now=NOW)
bad=0
for win in ("30d","mtd","ytd","all", NOW.strftime("%Y-%m")):
    s = dashboard.summary(db, window=win, now=NOW); it={i["metric"]:i for i in s["items"]}
    for m in dashboard.METRICS:
        if m not in it: continue
        d = dashboard.drill(db, m, window=win, now=NOW)
        a, b = it[m]["value_cad"], d.get("value_cad")
        ok = (a is None and b is None) or (a is not None and b is not None and abs(a-b)<0.006)
        if not ok: bad+=1; print("MISMATCH", win, m, "summary", a, "drill", b, d.get("reading"))
        if d.get("check") and not d["check"]["matches"]: print("CHECK FAIL", win, m)
print("mismatches:", bad)
