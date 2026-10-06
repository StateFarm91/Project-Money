from _h import *
import threading
from sqlalchemy import select, func
from brambleloop.finance.accounting import dashboard, close, ledger, posting_rules, anomalies, views, controller, reconciliation as R
from brambleloop.core.models import CostEntry, LedgerEntry
from brambleloop.finance.accounting.models import AcctJournalEntry
# --- concurrency
db = mkdb(seed=True)
errs=[]
def run():
    try: posting_rules.post_all(db, now=NOW)
    except Exception as e: errs.append(repr(e)[:150])
ts=[threading.Thread(target=run) for _ in range(6)]
[t.start() for t in ts]; [t.join() for t in ts]
with db.session() as s:
    n = s.scalar(select(func.count(AcctJournalEntry.id)))
    keys = s.scalars(select(AcctJournalEntry.entry_key)).all()
print("concurrent post_all x6: entries", n, "distinct keys", len(set(keys)), "errors", errs[:3], "chain", ledger.verify_chain(db)["ok"])
# --- duplicate ledger fee row w/ different external_id & evidence_ref  
db = mkdb(seed=True); controller.run_cycle(db, now=NOW)
base = ledger.balances.__module__
with db.session() as s:
    fee = s.scalars(select(LedgerEntry).where(LedgerEntry.fees_cad>0).order_by(LedgerEntry.id)).first()
    print("base ledger row", fee.id, fee.category, fee.source, fee.external_id, fee.evidence_ref, fee.gross_cad, fee.fees_cad)
    s.add(LedgerEntry(at=fee.at+timedelta(hours=1), category=fee.category, description=fee.description, gross_cad=0, fees_cad=fee.fees_cad, evidence_ref=fee.evidence_ref, source=fee.source, external_id=fee.external_id+"-b", currency=fee.currency, basis=fee.basis, fees_basis=fee.fees_basis, classification=fee.classification))
b0 = dashboard.summary(db, now=NOW)
fe = {i["metric"]:i for i in b0["items"]}["fees"]["value_cad"]
c = controller.run_cycle(db, now=NOW)
b1 = dashboard.summary(db, now=NOW)
fe1 = {i["metric"]:i for i in b1["items"]}["fees"]["value_cad"]
print("duplicate fee row w/ new external_id: fees before cycle(post) ->", fe, " after", fe1, " anomalies", c["anomalies"], "exceptions", b1["exceptions"]["open"], [x['kind'] for x in b1['exceptions']['top']])
db = mkdb(seed=True)
base = {i["metric"]:i for i in dashboard.summary(db, now=NOW)["items"]}
print("BASELINE fees", base["fees"]["value_cad"], "gross", base["gross_sales"]["value_cad"])
with db.session() as s:
    r = s.scalars(select(LedgerEntry).where(LedgerEntry.category=="sale").order_by(LedgerEntry.id)).first()
    # whole-sale duplicate: same receipt, new external id, +1h
    s.add(LedgerEntry(at=r.at+timedelta(hours=1), category="sale", description=r.description, gross_cad=r.gross_cad, fees_cad=r.fees_cad, refunds_cad=r.refunds_cad, evidence_ref=r.evidence_ref, source=r.source, external_id=r.external_id+":dup", currency=r.currency, basis=r.basis, fees_basis=r.fees_basis))
sm = dashboard.summary(db, now=NOW)
it = {i["metric"]:i for i in sm["items"]}
print("AFTER dup sale row: fees", it["fees"]["value_cad"], "gross", it["gross_sales"]["value_cad"], "exceptions", sm["exceptions"]["open"], sm["status"])
