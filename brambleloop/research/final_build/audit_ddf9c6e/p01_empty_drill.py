from _h import *
from brambleloop.finance.accounting import dashboard, cash, forecast
db = mkdb()
s = dashboard.summary(db)
print("SUMMARY status", s["status"], s["basis"])
for i in s["items"]: print("  ", i["metric"], i["value_cad"], i["reading"])
for m in dashboard.METRICS:
    d = dashboard.drill(db, m)
    print("DRILL", m, d["status"], d.get("value_cad"), d.get("reading"))
print("FORECAST", forecast.forecast(db))
