from j_sec_common import *
import datetime, os
from sqlalchemy import select
from brambleloop.core.models import Product, PatternVersion, Listing, AuditLog
from brambleloop.ops import publication_authority as pub
os.environ[pub.KILL_SWITCH_VAR]="1"
with db.session() as s:
    p=Product(slug="jprobe", title="Probe", status="certified"); s.add(p); s.flush()
    s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"x":1}, release_hash="rel"*10, certified=True, certificate={"findings":[]}))
    s.add(Listing(product_slug="jprobe", version="1.0.0", title="t", description="d", tags=[], price_cad=5.0, state="draft", release_hash="rel"*10))
from unittest.mock import patch
from brambleloop.runtime import etsy_ops
patch.object(etsy_ops,"certified_payload",return_value={"title":"t"}).start()
patch.object(etsy_ops,"sent_fields",side_effect=lambda x:x).start()
c=client(); csrf=login(c)
P=lambda path,js: c.post(path, headers=fresh(csrf), json=js)
body={"slug":"jprobe","version":"1.0.0","release":"rel"*10}
r=P("/api/cc/actions/publication.preview", body); print("preview", r.status_code, (r.text[:300] if r.status_code!=200 else [(d['section'],d['state']) for d in r.json()['result']['display']]))
if r.status_code==200:
    dg=r.json()["result"]["digest"]
    r=P("/api/cc/actions/publication.approve", {**body,"expected_digest":dg,"reason":"probe"}); print("approve with failing evidence:", r.status_code, r.text[:200])
    if r.status_code==200:
        ident=r.json()["result"]["approval_id"]
        print("grant valid at execution boundary:", pub.validate(db, ident, slug="jprobe", version="1.0.0", release="rel"*10))
        card=[x for x in c.get("/api/cc/approvals").json()["cards"] if x["card_id"].startswith("publication:")]
        print("inbox card executable flag:", [(x["card_id"], x["executable"], x["recommendation"]) for x in card])
    r=P("/api/cc/actions/publication.revoke", {"approval_id":ident}); print("revoke:", r.status_code)
    print("boundary after revoke:", pub.validate(db, ident, slug="jprobe", version="1.0.0", release="rel"*10))
r=P("/api/cc/actions/publication.revoke", {"approval_id":999999}); print("revoke of NONEXISTENT approval id 999999:", r.status_code, r.json())
