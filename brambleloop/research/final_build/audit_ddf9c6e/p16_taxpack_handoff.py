from _h import *
from brambleloop.finance.accounting import tax_pack, handoff
db = mkdb()
p = tax_pack.pack(db, "2026-09", now=NOW)
print("empty DB tax pack summary_cad:", p["summary_cad"], "| sales_reading", p["sales_reading"])
import inspect
print([n for n in dir(handoff) if not n.startswith('_')][:20])
