from j_sec_common import *
import datetime
from brambleloop.app.command_center.models import RequestNonce, OwnerSession, SecurityEvent
from sqlalchemy import select
print("=== F1: X-CC-Timestamp: nan bypasses freshness; nonce purge makes request replayable")
c=client(); csrf=login(c)
n=uuid.uuid4().hex
hdr={"X-CC-Nonce":n,"X-CC-Timestamp":"nan","X-CSRF-Token":csrf}
r1=c.post("/api/cc/home/seen", headers=hdr, json={}); print("first (ts=nan):", r1.status_code)
r2=c.post("/api/cc/home/seen", headers=hdr, json={}); print("immediate replay:", r2.status_code, r2.json().get("code"))
# fast-forward 11 minutes: the nonce row ages out of retention (purged on next mutating request)
with db.session() as s:
    for row in s.query(RequestNonce).filter(RequestNonce.nonce==n): row.at = auth._now()-datetime.timedelta(minutes=11)
c.post("/api/cc/home/seen", headers=fresh(csrf), json={})  # any later mutating request purges
r3=c.post("/api/cc/home/seen", headers=hdr, json={}); print("replay after retention purge (same nonce, ts=nan):", r3.status_code)
# control: with a real stale timestamp the same replay is refused
hdr2={"X-CC-Nonce":uuid.uuid4().hex,"X-CC-Timestamp":str(int(time.time())-3600),"X-CSRF-Token":csrf}
print("control stale ts:", c.post("/api/cc/home/seen", headers=hdr2, json={}).status_code)

print("\n=== F2: login lockout of the real owner by unauthenticated attacker")
clear_events()
atk=client()
codes=[]
for i in range(25):
    r=atk.post("/api/cc/auth/login", json={"passphrase":f"guess{i}"}, headers={"X-Forwarded-For":f"203.0.113.{i}","User-Agent":f"ua{i}"}); codes.append(r.status_code)
print("attacker w/ rotating XFF/UA, codes:", codes)
own=client(); r=own.post("/api/cc/auth/login", json={"passphrase":PASS}); print("REAL OWNER correct passphrase now:", r.status_code, r.json())
# same-origin check is not required for attacker; attempt count: 20 global fails => lock
print("distinct client hashes:", )
# Does lockout self-extend? simulate attacker keeping 20 events/15min: age all events to 14 min, owner still blocked?
with db.session() as s:
    for e in s.query(SecurityEvent).filter(SecurityEvent.kind=="login"): e.at = auth._now()-datetime.timedelta(minutes=14)
print("owner at +14min:", client().post("/api/cc/auth/login", json={"passphrase":PASS}).status_code)
with db.session() as s:
    for e in s.query(SecurityEvent).filter(SecurityEvent.kind=="login"): e.at = auth._now()-datetime.timedelta(minutes=16)
print("owner at +16min (all events aged out):", client().post("/api/cc/auth/login", json={"passphrase":PASS}).status_code)

print("\n=== F2b: per-client limit bypass via X-Forwarded-For (brute-force budget)")
clear_events()
atk=client(); ok=0
for i in range(19):
    r=atk.post("/api/cc/auth/login", json={"passphrase":"x"}, headers={"X-Forwarded-For":f"198.51.100.{i}"}); ok+= r.status_code==401
print("401 BAD_CREDENTIALS (not 429) with one real IP spoofing XFF, 19 tries:", ok)
clear_events()
atk=client(); codes=[atk.post("/api/cc/auth/login", json={"passphrase":"x"}).status_code for _ in range(8)]; print("same client no spoof:", codes)

print("\n=== F2c: lockout is self-perpetuating (429s are themselves counted)")
clear_events(); atk=client()
for i in range(20): atk.post("/api/cc/auth/login", json={"passphrase":"g"}, headers={"X-Forwarded-For":f"192.0.2.{i}"})
with db.session() as s:
    for e in s.query(SecurityEvent).filter(SecurityEvent.kind=="login"): e.at = auth._now()-datetime.timedelta(minutes=14)
codes=[atk.post("/api/cc/auth/login", json={"passphrase":"g"}, headers={"X-Forwarded-For":f"192.0.2.{i}"}).status_code for i in range(20)]
print("20 more attacker attempts at +14min, codes (all 429 = refused, but each logged):", set(codes))
with db.session() as s:
    for e in s.query(SecurityEvent).filter(SecurityEvent.kind=="login", SecurityEvent.at < auth._now()-datetime.timedelta(minutes=13)): e.at = auth._now()-datetime.timedelta(minutes=16)
print("original burst now 16 min old; real owner:", client().post("/api/cc/auth/login", json={"passphrase":PASS}).status_code)
clear_events()
print("\n=== session lifecycle")
c=client()
c.cookies.set("__Host-bl_cc","attackerchosentoken"+"A"*20, domain="testserver.local")
r=c.post("/api/cc/auth/login", json={"passphrase":PASS}); tok=r.cookies.get("__Host-bl_cc") if hasattr(r,'cookies') else None
print("fixation: server issued token != preset:", tok!="attackerchosentoken"+"A"*20, "| preset cookie authenticates?", client().get("/api/cc/home", cookies={"__Host-bl_cc":"attackerchosentoken"+"A"*20}).status_code)
c=client(); csrf=login(c); tok=c.cookies.get("__Host-bl_cc")
r=c.post("/api/cc/auth/logout", headers=fresh(csrf)); print("logout:", r.status_code)
print("old cookie after logout:", client().get("/api/cc/home", cookies={"__Host-bl_cc":tok}).status_code)
a=client(); ca=login(a); b=client(); cb=login(b); tb=b.cookies.get("__Host-bl_cc")
sid=a.get("/api/cc/account/sessions").json()["sessions"]
other=[s_ for s_ in sid if not s_["current"]][0]["session_id"]
print("revoke other:", a.post(f"/api/cc/account/sessions/{other}/revoke", headers=fresh(ca), json={}).status_code)
print("revoked session usable?:", [client().get("/api/cc/home", cookies={"__Host-bl_cc":t}).status_code for t in [tb]])
# idle/absolute expiry
d=client(); login(d); 
with db.session() as s:
    row=s.query(OwnerSession).order_by(OwnerSession.id.desc()).first(); row.last_seen_at=auth._now()-datetime.timedelta(hours=2, seconds=5)
print("idle>2h:", d.get("/api/cc/home").status_code)
d=client(); login(d)
with db.session() as s:
    row=s.query(OwnerSession).order_by(OwnerSession.id.desc()).first(); row.expires_at=auth._now()-datetime.timedelta(seconds=5)
print("expired:", d.get("/api/cc/home").status_code)
# session list leaks other sessions' client_hash/token?
print("sessions view keys:", sorted(a.get("/api/cc/account/sessions").json()["sessions"][0].keys()))
# cookie w/ operator token as cookie
print("ops token as cookie:", client().get("/api/cc/home", cookies={"__Host-bl_cc":OPS}).status_code)
