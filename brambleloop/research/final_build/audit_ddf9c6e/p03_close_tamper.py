from _h import *
from sqlalchemy import text, select
from brambleloop.finance.accounting import dashboard, close, ledger, posting_rules, anomalies, views, controller
from brambleloop.core.models import CostEntry
from brambleloop.finance.accounting import exceptions as X
db = mkdb(seed=True)
y,m = NOW.year, NOW.month
prev = f"{y-(m==1)}-{12 if m==1 else m-1:02d}"
print("prev period", prev)
cl = close.checklist(db, prev, now=NOW)
print("checklist closable:", cl["closable"], [ (s['step'],s['outcome']) for s in cl['steps'] if s['outcome']!='pass'])
# 1. add two duplicate cost rows in prev month with no charge id, 61s apart (not caught), then lock
with db.session() as s:
    at = datetime(NOW.year if m>1 else NOW.year-1, int(prev[5:]), 5, 10, 0, tzinfo=timezone.utc)
    for i in range(2):
        s.add(CostEntry(at=at+timedelta(seconds=61*i), kind="llm", agent="writer", provider="anthropic", model="x", purpose="dup", amount_cad=3.0, department="eng"))
posting_rules.post_all(db, now=NOW)
a = anomalies.detect(db, now=NOW)
print("A1 duplicate cost rows 61s apart, anomalies:", [f["type"] for f in a["findings"]])
# 2. lock without running anomalies/cycle? use fresh db
db2 = mkdb(seed=True)
controller.run_cycle(db2, now=NOW)
cl = close.checklist(db2, prev, now=NOW)
print("fresh closable", cl["closable"], [(s['step'],s['outcome']) for s in cl['steps'] if s['outcome']!='pass'])
# STALE orders: now = +3 days
later = NOW+timedelta(days=3)
cl2 = close.checklist(db2, prev, now=later)
print("orders stale (3d later) closable:", cl2["closable"], [(s['step'],s['outcome']) for s in cl2['steps'] if s['step'] in('source_completeness',)])
r = close.lock_period(db2, prev, by="J", now=later)
print("LOCK with stale orders:", r["locked"])
print("verify_lock", close.verify_lock(db2, prev))
# raw SQL edit in locked month
with db2.session() as s:
    pid = s.execute(text("select p.id from acct_postings p join acct_journal_entries e on e.id=p.entry_id where e.period=:p and p.account='4000' limit 1"),{"p":prev}).scalar()
    s.execute(text("update acct_postings set credit_micros = credit_micros + 5000000 where id=:i"),{"i":pid})
    s.execute(text("update acct_postings set debit_micros = debit_micros + 5000000 where id=(select id from acct_postings where entry_id=(select entry_id from acct_postings where id=:i) and debit_micros>0 limit 1)"),{"i":pid})
print("after balanced raw edit: verify_chain", ledger.verify_chain(db2)["ok"], "verify_lock", close.verify_lock(db2, prev))
sm = dashboard.summary(db2, now=later)
print("SUMMARY after tamper: status", sm["status"], "| reason:", sm["reason"][:200])
print("exceptions", sm["exceptions"])
print("gross", [i['value_cad'] for i in sm['items'] if i['metric']=='gross_sales'])
