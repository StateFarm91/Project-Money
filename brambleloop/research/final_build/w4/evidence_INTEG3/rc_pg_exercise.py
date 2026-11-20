import sys
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
from brambleloop.core.db import Database
from brambleloop.integrations import etsy_webhooks as W
from brambleloop.creative import prospecting as P
db = Database(sys.argv[1])
db.create_all()
t0 = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
for i in range(5):
    W._refused(db, W.WebhookRefused("bad_signature", "x", status=401), now=t0 + timedelta(seconds=i))
W._refused(db, W.WebhookRefused("made_up_reason", "x", status=400), now=t0)
from sqlalchemy import select, func
from brambleloop.core.models import AuditLog
with db.session() as s:
    rows = s.execute(select(W.EtsyWebhookRefusal.reason, W.EtsyWebhookRefusal.count)).all()
    sampled = s.scalar(select(func.count()).where(AuditLog.action == W.REFUSAL_SAMPLE_ACTION))
print("refusal counters:", sorted(rows), "sampled audit rows:", sampled)
print("summary refused:", W.summary(db).get("refused") or W.summary(db))
slot = SimpleNamespace(arena=SimpleNamespace(event="halloween", pod="decor"), form="pillow")
print("offset0", P.brief_offset(db, slot), "after+3", P.advance_brief_offset(db, slot, 3),
      "after+2", P.advance_brief_offset(db, slot, 2))
