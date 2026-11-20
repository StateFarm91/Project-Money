from _h import *
from brambleloop.finance import spend_report
from brambleloop.gateway import anthropic as gw
from brambleloop.agents.registry import BudgetExceeded
db = mkdb()
spend_report.record(db, agent="a", amount_cad=90.0, purpose="real spend", provider="anthropic", model="m")
print("spent after +90:", gw.spent_this_month_cad(db, now=NOW))
def tryest(e):
    try: gw.check_budget_cad(db, estimate_cad=e, agent="", now=NOW, reserve=False); return "GRANTED"
    except BudgetExceeded: return "refused"
print("est 20 vs 90 spent:", tryest(20.0))
spend_report.record(db, agent="a", amount_cad=-80.0, purpose="negative row", provider="anthropic", model="m")
print("spent after -80 row:", gw.spent_this_month_cad(db, now=NOW), "| est 20:", tryest(20.0))
spend_report.record(db, agent="a", amount_cad=float("nan"), purpose="nan row", provider="anthropic", model="m")
print("spent after NaN row:", gw.spent_this_month_cad(db, now=NOW))
