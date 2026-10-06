from _h import *
import threading
from brambleloop.gateway import anthropic as gw, failover
from brambleloop.finance import reservations
from brambleloop.agents.registry import BudgetExceeded
db = mkdb()
ok=[];ref=[];other=[]
def go(i):
    try:
        gw.check_budget_cad(db, estimate_cad=30.0, agent="", purpose="t", holder=f"h{i}", now=NOW, model="m", provider="anthropic")
        ok.append(i)
    except BudgetExceeded: ref.append(i)
    except Exception as e: other.append(repr(e)[:120])
ts=[threading.Thread(target=go,args=(i,)) for i in range(10)]
[t.start() for t in ts];[t.join() for t in ts]
print("ceiling", gw.monthly_ceiling_cad(), "granted", len(ok), "x30 =", len(ok)*30, "refused", len(ref), "other", other[:2])
print("outstanding", reservations.outstanding(db, now=NOW)["cad"])
# NaN / inf / negative / string
for est in (float("nan"), float("inf"), -5, "abc", None, 1e-12):
    try:
        gw.check_budget_cad(mkdb(), estimate_cad=est, agent="", now=NOW, reserve=False); print(repr(est), "GRANTED")
    except BudgetExceeded: print(repr(est), "refused")
    except Exception as e: print(repr(est), "EXC", type(e).__name__)
