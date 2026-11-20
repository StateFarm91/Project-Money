from j_sec_common import *
import re
routes = cc_routes(); print("cc routes:", len(routes))
c = client()
bad=[]
for m,p in routes:
    if (m,p) in auth.PUBLIC_ROUTES: continue
    url = re.sub(r"\{[^}]+\}", "1", p)
    r = c.request(m, url, json={} if m!="GET" else None)
    if r.status_code not in (401,): bad.append((m,p,r.status_code))
print("unauth non-401:", bad)
for path in ["/cc/store-preview","/cc/store-preview?viewport=desktop"]:
    r=c.get(path); print(path, r.status_code, r.headers.get("content-security-policy","")[:60])
# HEAD / OPTIONS / method override
for m in ["HEAD","OPTIONS"]:
    r=c.request(m,"/api/cc/home"); print(m,"/api/cc/home unauth", r.status_code)
r=c.post("/api/cc/home?_method=GET"); print("post override", r.status_code)
r=c.get("/api/cc/home", headers={"X-HTTP-Method-Override":"GET"}); print(r.status_code)
# path tricks
for p in ["/api/cc//home","/api/cc/home/","/API/cc/home","/api/cc/%2e%2e/cc/home","/api/cc/home%00","//api/cc/home","/cc/../api/cc/home","/api/cc/auth/status/../home"]:
    r=c.get(p); print(repr(p), r.status_code, r.text[:80].replace("\n"," "))
# static dir traversal under /cc
for p in ["/cc/../../etc/passwd","/cc/..%2f..%2fetc/passwd","/cc/%2e%2e/%2e%2e/etc/passwd","/cc/js/../../../models.py","/cc/js/..%2f..%2f..%2fmodels.py"]:
    r=c.get(p); print(repr(p), r.status_code, r.text[:50].replace("\n"," "))
# operator token on cc routes
r=c.get("/api/cc/home", headers={"Authorization":f"Bearer {OPS}"}); print("operator bearer on /api/cc/home:", r.status_code)
r=c.post("/api/cc/emergency/pause", headers={"Authorization":f"Bearer {OPS}"}, json={"scope":"company","reason":"abc"}); print("operator bearer pause:", r.status_code)
r=c.get("/cc/store-preview", headers={"Authorization":f"Bearer {OPS}"}); print("operator bearer store-preview:", r.status_code)
# owner session on operator routes
csrf=login(c)
r=c.get("/api/owner/phase"); print("owner cookie on operator /api/owner/phase:", r.status_code)
r=c.get("/api/support"); print("owner cookie on /api/support:", r.status_code)
r=c.post("/api/owner/decision", json={}, headers=fresh(csrf)); print("owner cookie on operator POST:", r.status_code)
