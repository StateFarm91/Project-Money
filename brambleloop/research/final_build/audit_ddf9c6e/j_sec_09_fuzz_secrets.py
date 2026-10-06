from j_sec_common import *
import re, json, logging, io
log=io.StringIO(); h=logging.StreamHandler(log); logging.getLogger().addHandler(h); logging.getLogger().setLevel(logging.DEBUG)
c=client(); csrf=login(c)
SECRETS=[OPS, PASS, os.environ[auth.PASSPHRASE_VAR], os.environ[auth.PASSPHRASE_VAR].split("$")[-1], c.cookies.get("__Host-bl_cc")]
bodies=[None,[],"str",123,{"scope":{"a":1},"reason":{"b":2},"department":[1]},{"id":"1; DROP TABLE x"},{"question":{"x":1}},{"question":"A"*100000},{"job_id":10**30},{"approval_id":-1},{"approval_id":10**30},{"cadence":"../../etc"},{"name":"x"*500,"request_id":"r"},{"slug":None,"version":None},{"hour":"x","enabled":"yes"}, {"expected_digest":None,"slug":"a","version":"b","release":"c","reason":"d"}]
five=[];seen_leak=[]
import itertools
for m,p in cc_routes():
    if m!="POST" or p in ("/api/cc/auth/login","/api/cc/auth/logout"): continue
    for b in bodies:
        url=re.sub(r"\{[^}]+\}","1",p)
        try: r=c.post(url, headers=fresh(csrf), json=b)
        except Exception as e: five.append((p,"EXC",repr(e)[:80])); continue
        if r.status_code==429: 
            c=client(); csrf=login(c); r=c.post(url, headers=fresh(csrf), json=b)
        if r.status_code>=500: five.append((p,r.status_code,json.dumps(b)[:50],r.text[:120]))
        for sct in SECRETS:
            if sct and sct in r.text: seen_leak.append((p,sct[:6]))
print("5xx on fuzz:", five or "none"); print("secret in fuzz responses:", seen_leak or "none")
# secrets in GET responses (authenticated)
c=client(); csrf=login(c); leaks=[]
for m,p in cc_routes():
    if m=="GET" and "{" not in p:
        t=c.get(p).text
        for sct in SECRETS+["BRAMBLELOOP_","pbkdf2","Bearer "]:
            if sct and sct in t: leaks.append((p,sct[:8]))
print("secrets in authed GET bodies:", leaks or "none")
# security events / audit rows contain secrets?
from sqlalchemy import select
from brambleloop.app.command_center.models import SecurityEvent
from brambleloop.core.models import AuditLog
c.post("/api/cc/auth/login", json={"passphrase":"WRONGPASS-sentinel-123"})
with db.session() as s:
    blob=json.dumps([[e.reason,e.detail,e.route] for e in s.scalars(select(SecurityEvent))],default=str)+json.dumps([[a.actor,a.action,a.artifact,a.detail] for a in s.scalars(select(AuditLog))],default=str)
print("wrong passphrase persisted in events/audit:", "WRONGPASS-sentinel" in blob, "| real secrets persisted:", any(x and x in blob for x in SECRETS))
print("secrets in captured logs:", any(x and x in log.getvalue() for x in SECRETS+["WRONGPASS-sentinel-123"]))
# error shape on unknown path with operator header
r=c.get("/api/cc/nonexistent"); print("unknown cc path authed:", r.status_code)
# 404 under /api/cc unauth => fine? (gate runs only for matched routes)
r=client().get("/api/cc/nonexistent"); print("unknown cc path unauth:", r.status_code)
