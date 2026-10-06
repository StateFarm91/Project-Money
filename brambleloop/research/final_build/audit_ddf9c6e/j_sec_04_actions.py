from j_sec_common import *
import datetime, json
from sqlalchemy import select
from brambleloop.core.models import Agent, SpendLimit, AuditLog
from brambleloop.app.command_center import emergency
c=client(); csrf=login(c)
def P(path, js, cl=c, cs=None): 
    r=cl.post(path, headers=fresh(cs or csrf), json=js); return r
print("agents:", len(list(db.session().__enter__().scalars(select(Agent)))) )
with db.session() as s:
    s.add(SpendLimit(scope="breached", daily_cap_cad=1, lifetime_cap_cad=1, paused=True))   # paused by a cap breach
    s.add(SpendLimit(scope="healthy", daily_cap_cad=1, lifetime_cap_cad=1, paused=False))
    a=s.scalar(select(Agent).where(Agent.name=="listing")); a.enabled=False   # disabled for another reason
print("== pause company (no step-up needed)")
r=P("/api/cc/emergency/pause",{"scope":"company","reason":"drill"}); print(r.status_code, {k:r.json().get(k) for k in("agents_disabled","spend_scopes_paused","still_running")} if r.status_code==200 else r.json())
print("== resume company needs stepup; expire stepup then try")
with db.session() as s:
    from brambleloop.app.command_center.models import OwnerSession
    for row in s.query(OwnerSession): row.stepup_until=auth._now()-datetime.timedelta(seconds=1)
r=P("/api/cc/emergency/resume",{"scope":"company","reason":"drill over"}); print("no stepup:", r.status_code, r.json().get("code"))
r=P("/api/cc/auth/step-up",{"passphrase":PASS}); print("stepup:", r.status_code)
r=P("/api/cc/emergency/resume",{"scope":"company","reason":"drill over"}); print("resume:", r.status_code, r.json().get("agents_enabled"), "unpaused:", r.json().get("spend_scopes_unpaused"), "left_alone:", r.json().get("left_alone"))
with db.session() as s:
    print("breached scope still paused:", s.scalar(select(SpendLimit.paused).where(SpendLimit.scope=="breached")), "| listing agent (disabled other reason) enabled:", s.scalar(select(Agent.enabled).where(Agent.name=="listing")))
print("== kill switch")
r=P("/api/cc/emergency/kill",{"reason":"drill"}); print(r.status_code, (r.json().get("effective_phase") if r.status_code==200 else r.json()))
print("== pause w/ weird scopes / department injection")
for js in [{"scope":"phase","reason":"abc"},{"scope":"department","department":"executive","reason":"abc"},{"scope":"department","department":None,"reason":"abc"},{"scope":["company"],"reason":"abc"},{"scope":"company","reason":123},{"scope":"company"}]:
    r=P("/api/cc/emergency/pause",js); print(js, r.status_code, (r.json().get("code") if r.status_code!=200 else "ok"))
print("== department block/unblock")
with db.session() as s:
    pass
for d in ["executive","finance","platform","product_truth","nonsense","../x"]:
    r=P(f"/api/cc/departments/{d}/block",{"reason":"owner test"}); print("block",d,r.status_code)
from brambleloop.autonomy import memory
print("executive active block recorded:", bool(memory.active_block(db,"executive")))
with db.session() as s:
    for row in s.query(OwnerSession): row.stepup_until=auth._now()-datetime.timedelta(seconds=1)
print("unblock without stepup:", P("/api/cc/departments/executive/unblock",{}).status_code)
P("/api/cc/auth/step-up",{"passphrase":PASS}); print("unblock with stepup:", P("/api/cc/departments/executive/unblock",{}).status_code)
print("== protected actions via CC with unready/nonexistent release")
for act,js in [("publication.approve",{"slug":"nope","version":"1.0.0","release":"","expected_digest":"x","reason":"yes"}),
               ("publication.approve",{"slug":"nope","version":"1.0.0","release":"","expected_digest":"x"}),
               ("activation.approve",{"slug":"nope","version":"1.0.0","release":"","expected_digest":"x","reason":"yes"}),
               ("publication.revoke",{"approval_id":999999}),("publication.revoke",{"approval_id":"abc"}),
               ("improvement.approve",{"id":999999,"reason":"r"}),("challenger.approve",{"id":"zz"}),
               ("nonexistent.action",{})]:
    r=P(f"/api/cc/actions/{act}",js); print(act, r.status_code, r.json().get("code"), (r.json().get("error") or "")[:110])
print("audit rows cc.owner_action.*:", db.session().__enter__().scalar(select(__import__('sqlalchemy').func.count()).select_from(AuditLog).where(AuditLog.action.like("cc.owner_action.%"))))
