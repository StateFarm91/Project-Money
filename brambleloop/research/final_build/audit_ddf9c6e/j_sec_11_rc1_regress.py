from j_sec_common import *
import re
from brambleloop.core.models import Job, JobStatus, Customer, SupportCase, Order
XSS='<script>alert(1)</script><img src=x onerror=alert(2)>'
REF="CXREGR-BUYER-5512"
with db.session() as s:
    s.add(Job(job_type="x.y", agent="a", inputs={}, status=JobStatus.FAILED, last_error=XSS, attempts=3))
    cu=Customer(customer_ref=REF); s.add(cu); s.flush()
    s.add(SupportCase(customer_ref=REF, question="q", answer="a"))
c=client()
# 1 unauthenticated mutating routes
bad=[]
for path,methods,_ in security.iter_api_routes(main.app):
    for m in methods-{"GET","HEAD","OPTIONS"}:
        if (m,path) in security.PUBLIC_MUTATING_ROUTES: continue
        url=re.sub(r"\{[^}]+\}","1",path)
        r=c.request(m,url,json={})
        if r.status_code not in (401,403,503): bad.append((m,path,r.status_code))
print("unauthenticated mutating routes not refused:", bad or "none")
# attack from A3-01: as_of unauth
print("unauth /api/plan-cycle?as_of=<script>:", c.post("/api/plan-cycle?as_of="+XSS).status_code)
print("operator /api/plan-cycle?as_of=<script>:", c.post("/api/plan-cycle?as_of="+XSS, headers={"Authorization":f"Bearer {OPS}"}).status_code)
# 2 stored XSS on html routes
html_hits=[]; refleaks=[]
for path,methods,_ in security.iter_api_routes(main.app):
    pass
cands=["/","/dashboard","/owner","/console","/ops","/ops/teardown","/health","/api/verify"]
getp=[p for p,mm,_ in security.iter_api_routes(main.app) if "GET" in mm and "{" not in p and p not in ("/api/etsy/oauth/start",)]
for p in sorted(set(cands+getp)):
    r=c.get(p)
    t=r.text
    if "html" in r.headers.get("content-type","") and re.search(r"<script>alert\(1\)|<img src=x",t): html_hits.append(p)
    if REF in t or REF.lower() in t.lower(): refleaks.append(p)
print("unauth routes reflecting raw script payload:", html_hits or "none"); print("unauth routes leaking buyer ref:", refleaks or "none")
print("payload visible escaped on any unauth html:", any("&lt;script&gt;" in c.get(p).text for p in sorted(set(cands+getp)) if "html" in c.get(p).headers.get("content-type","")))
