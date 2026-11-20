from _h import *
import json
from brambleloop.finance.accounting import forecast, controller, dashboard
db = mkdb(seed=True); controller.run_cycle(db, now=NOW)
f = forecast.forecast(db, now=NOW)
print(json.dumps(f, indent=1, default=str)[:1800])
