"""Run the real store surfaces through lint (truth+voice) and print every distinct customer-facing sentence containing a factual claim word."""
import re
from brambleloop.store_foundation import content as C, readiness as R, lint
s = C.build(None)
rows = R.evaluate(s)
for r in rows:
    f = [(x["code"], x["severity"]) for x in r["findings"]]
    print(f"{r['key']:20} {r['status']:12} {f[:4]}")
txt = "\n".join(v.text() for v in s.values() if v.customer_facing)
for pat in (r"[^.\n]*\b(20\d\d|years?|since|first|new|tested|made|handmade|photograph|sample|review|sold|customers?)\b[^.\n]*\."):
    pass
for m in sorted({m.group(0).strip() for m in re.finditer(r"[^.\n]*\b(20\d\d|years?|since|tested|handmade|photograph\w*|samples?|reviews?|sold)\b[^.\n]*", txt, re.I)})[:40]:
    print(" CLAIMWORD>", m[:200])
