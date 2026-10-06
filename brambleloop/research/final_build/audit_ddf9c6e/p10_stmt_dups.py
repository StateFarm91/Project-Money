from _h import *
from brambleloop.finance.accounting import reconciliation as R, controller, exceptions as X, posting_rules
db = mkdb(seed=True); controller.run_cycle(db, now=NOW)
base = {"external_id":"e1","at":NOW-timedelta(days=10),"kind":"fee","amount":-1.25,"reference":"1001"}
R.import_statement(db, "etsy_ledger", [base], now=NOW)
variants = {
 "same everything, new id": dict(base, external_id="e2"),
 "ref case differs": dict(base, external_id="e3", reference="1001 "),
 "ref has suffix": dict(base, external_id="e4", reference="1001-A"),
 "4 days later": dict(base, external_id="e5", at=base["at"]+timedelta(days=4)),
 "amount +0.01": dict(base, external_id="e6", amount=-1.26),
 "blank ref+desc": dict(base, external_id="e7", reference=""),
}
for name, v in variants.items():
    r = R.import_statement(db, "etsy_ledger", [v], now=NOW)
    print(f"{name:28s} duplicate_detected={bool(r['duplicates'])}")
m = R.match(db, now=NOW)
print("match:", {k:v for k,v in m.items() if not isinstance(v,(list,dict))})
for x in X.listing(db): print(" EXC", x["kind"], x["severity"], x["summary"][:110])
