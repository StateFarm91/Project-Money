from j_sec_common import *
import json
from datetime import datetime, timedelta, timezone
REF="CXBUYER-4410-ETSY"; MSG="CXMSG: my order is wrong, email me at jane.doe@example.com or 555-010-0199"
op={"Authorization":f"Bearer {OPS}"}
oc=client()
rcv=(datetime.now(timezone.utc)-timedelta(hours=30)).isoformat()
r=oc.post("/api/support/messages", headers=op, json={"event":"buyer_message","customer_ref":REF,"message":MSG,"received_at":rcv,"product_slug":"seed"}); print("record:", r.status_code, r.json())
from brambleloop.support import response_watch
print("watch:", response_watch.watch(db))
c=client(); csrf=login(c)
c.post("/api/cc/notifications/refresh", headers=fresh(csrf), json={})
hits={}
urls=[p for m,p in cc_routes() if m=="GET" and "{" not in p]+[f"/api/cc/operations/drill?kind={k}&id={i}" for k in("job","incident","audit") for i in range(1,12)]+["/api/cc/operations/drill?kind=agent&id=support","/api/cc/timeline?limit=200","/api/cc/brief/morning?hours=9999"]
for u in urls:
    t=c.get(u).text
    for n,pat in [("ref",REF),("ref-lc",REF.lower()),("msg","CXMSG"),("email","jane.doe"),("phone","555-010")]:
        if pat in t: hits.setdefault(u,set()).add(n)
for card in c.get("/api/cc/approvals").json()["cards"]:
    t=c.get("/api/cc/approvals/"+card["card_id"]).text
    for n,pat in [("ref",REF),("msg","CXMSG"),("email","jane.doe")]:
        if pat in t: hits.setdefault(card["card_id"],set()).add(n)
for q in ["what incidents are open?","what is blocking launch?","why does the support reply need my approval?","what did Brambleloop do overnight?","customer approval"]:
    t=c.post("/api/cc/ask", headers=fresh(csrf), json={"question":q}).text
    for n,pat in [("ref",REF),("msg","CXMSG"),("email","jane.doe")]:
        if pat in t: hits.setdefault("ASK:"+q,set()).add(n)
print("REAL-PATH leaks through CC (scrub active):", {k:sorted(v) for k,v in hits.items()} or "none")
# what raw rows hold the message?
from sqlalchemy import select, text
with db.session() as s:
    from brambleloop.core.models import AuditLog, Incident, OwnerAction
    for M in (AuditLog, Incident, OwnerAction):
        for row in s.scalars(select(M)):
            blob=json.dumps({k:str(getattr(row,k,"")) for k in row.__table__.columns.keys()})
            if "CXMSG" in blob or REF in blob: print("row holding buyer data:", M.__tablename__, row.id, "msg" if "CXMSG" in blob else "", "ref" if REF in blob else "")
