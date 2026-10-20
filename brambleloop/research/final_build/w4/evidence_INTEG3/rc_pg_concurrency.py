"""INTEG3 (M1): 8 threads x 25 refusals on PostgreSQL; the single-transaction upsert must count
exactly and sample one audit row per reason. Usage: PYTHONPATH=src python rc_pg_concurrency.py URL"""
import sys, threading
from sqlalchemy import func, select, text
from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog
from brambleloop.integrations import etsy_webhooks as W
db = Database(sys.argv[1]); db.create_all()
with db.engine.begin() as c:
    c.execute(text("DELETE FROM etsy_webhook_refusals"))
    c.execute(text("DELETE FROM audit_log WHERE action = :a"), {"a": W.REFUSAL_SAMPLE_ACTION})
def go():
    for _ in range(25):
        W._refused(db, W.WebhookRefused("bad_signature", "x", status=401))
ts = [threading.Thread(target=go) for _ in range(8)]
[t.start() for t in ts]; [t.join() for t in ts]
with db.session() as s:
    n = s.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == W.REFUSAL_SAMPLE_ACTION))
print("counted:", W.summary(db)["refused"], "expected bad_signature=200; sampled audit rows:", n)
