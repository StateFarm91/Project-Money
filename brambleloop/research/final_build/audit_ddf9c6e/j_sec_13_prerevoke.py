from j_sec_common import *
exec(open("j_sec_05_grant.py").read().split("c=client(); csrf=login(c)")[0].split("from j_sec_common import *")[1])
from sqlalchemy import func
c=client(); csrf=login(c)
P=lambda path,js: c.post(path, headers=fresh(csrf), json=js)
body={"slug":"jprobe","version":"1.0.0","release":"rel"*10}
dg=P("/api/cc/actions/publication.preview", body).json()["result"]["digest"]
with db.session() as s: nxt=(s.scalar(select(func.max(AuditLog.id))) or 0)+2   # revoke row itself takes id+1
print("pre-revoking id", nxt, P("/api/cc/actions/publication.revoke", {"approval_id":nxt}).status_code)
r=P("/api/cc/actions/publication.approve", {**body,"expected_digest":dg,"reason":"probe"}); ident=r.json()["result"]["approval_id"]; print("new grant id", ident)
print("boundary:", pub.validate(db, ident, slug="jprobe", version="1.0.0", release="rel"*10))
