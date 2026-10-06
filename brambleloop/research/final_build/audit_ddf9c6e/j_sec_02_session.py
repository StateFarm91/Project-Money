from j_sec_common import *
c = client()
for p in ["/cc/store-preview/","/cc/store-preview/x","/cc/store-preview.html","/cc//store-preview"]:
    r=c.get(p); print("unauth",repr(p), r.status_code, r.text[:60].replace("\n"," "))
csrf=login(c)
H=lambda **o: fresh(csrf, **o)
body={"scope":"spend","reason":"test pause"}
def post(path, hdr, json=body, cl=c): return cl.post(path, headers=hdr, json=json)
print("--- CSRF")
print("no csrf hdr:", post("/api/cc/emergency/pause", fresh(None)).status_code)
print("forged csrf:", post("/api/cc/emergency/pause", fresh("0"*64)).status_code)
print("csrf of other session:", end=" ")
c2=client(); csrf2=login(c2); print(post("/api/cc/emergency/pause", fresh(csrf2)).status_code, "(c session, c2 csrf)")
print("wrong Origin:", post("/api/cc/emergency/pause", H(Origin="https://evil.example")).status_code)
print("Sec-Fetch-Site cross-site:", post("/api/cc/emergency/pause", H(**{"Sec-Fetch-Site":"cross-site"})).status_code)
print("Origin null:", post("/api/cc/emergency/pause", H(Origin="null")).status_code)
print("Origin match prefix evil testserver.evil:", post("/api/cc/emergency/pause", H(Origin="https://testserver.evil.com")).status_code)
print("Origin http scheme downgrade:", post("/api/cc/emergency/pause", H(Origin="http://testserver")).status_code)
print("no Origin/no Sec-Fetch (curl-like) w/ valid cookie+csrf:", post("/api/cc/emergency/pause", H()).status_code)
print("--- nonce/timestamp")
h=H(); r1=post("/api/cc/home/seen", h, {}); r2=post("/api/cc/home/seen", h, {}); print("replay:", r1.status_code, r2.status_code, r2.json().get("code"))
print("skew +200:", post("/api/cc/home/seen", H(**{"X-CC-Timestamp":str(int(time.time())+200)}), {}).status_code)
print("skew -200:", post("/api/cc/home/seen", H(**{"X-CC-Timestamp":str(int(time.time())-200)}), {}).status_code)
print("skew +100 ok:", post("/api/cc/home/seen", H(**{"X-CC-Timestamp":str(int(time.time())+100)}), {}).status_code)
print("ts nan:", post("/api/cc/home/seen", H(**{"X-CC-Timestamp":"nan"}), {}).status_code, "inf:", post("/api/cc/home/seen", H(**{"X-CC-Timestamp":"inf"}), {}).status_code)
print("short nonce:", post("/api/cc/home/seen", H(**{"X-CC-Nonce":"abc"}), {}).status_code)
# nonce reuse across sessions (same nonce string by 2 sessions) -> global unique?
n=uuid.uuid4().hex
a=c.post("/api/cc/home/seen", headers=fresh(csrf, **{"X-CC-Nonce":n}), json={}); b=c2.post("/api/cc/home/seen", headers=fresh(csrf2, **{"X-CC-Nonce":n}), json={})
print("same nonce, two sessions:", a.status_code, b.status_code, "(409 on 2nd = cross-session nonce collision oracle)")
# nonce replay after retention purge (nonce >10min, ts window 120s): can old nonce be replayed w/ stale ts? ts window blocks.
print("--- rate limit mutations 30/min")
codes=[post("/api/cc/home/seen", H(), {}).status_code for _ in range(35)]; print(codes.count(200), codes.count(429))
print("--- step-up")
import datetime
from brambleloop.app.command_center.models import OwnerSession
def expire_stepup(cl_sess_pid=None):
    with db.session() as s:
        for row in s.query(OwnerSession).all(): row.stepup_until = auth._now()-datetime.timedelta(seconds=1)
expire_stepup()
time.sleep(0.1)
# nonce rate limit window resets only after a min; use new client/session to avoid 429
c3=client(); csrf3=login(c3); expire_stepup()
for path,js in [("/api/cc/actions/publication.approve",{"slug":"x","version":"1","reason":"r"}),
                ("/api/cc/actions/activation.approve",{"slug":"x","version":"1","reason":"r"}),
                ("/api/cc/actions/improvement.approve",{"id":1}),("/api/cc/actions/challenger.approve",{"id":1}),
                ("/api/cc/emergency/resume",{"scope":"company","reason":"abc"}),
                ("/api/cc/departments/store/unblock",{}),
                ("/api/cc/operations/recovery/restart-job",{"job_id":1}),("/api/cc/operations/recovery/release-lease",{"name":"x"}),("/api/cc/operations/recovery/rerun-cycle",{"cadence":"daily"})]:
    r=c3.post(path, headers=fresh(csrf3), json=js); print(path, r.status_code, r.json().get("code"))
# step-up ordering: body invalid + no stepup
r=c3.post("/api/cc/actions/publication.approve", headers=fresh(csrf3), content=b"notjson"); print("badjson no stepup:", r.status_code, r.json().get("code"))
# does step-up with wrong passphrase 5x revoke
for i in range(5):
    r=c3.post("/api/cc/auth/step-up", headers=fresh(csrf3), json={"passphrase":"wrong"}); print("stepup wrong", i, r.status_code, r.json().get("error"))
r=c3.get("/api/cc/home"); print("after 5 bad stepups session:", r.status_code)
# stepup w/ correct passphrase works; bypass via missing/non-string
c4=client(); csrf4=login(c4)
for v in [None, "", [], {"a":1}, 0, True, PASS+"x"]:
    r=c4.post("/api/cc/auth/step-up", headers=fresh(csrf4), json={"passphrase":v}); print("stepup passphrase=",repr(v), r.status_code)
    if r.status_code==403 or r.status_code==429: break
