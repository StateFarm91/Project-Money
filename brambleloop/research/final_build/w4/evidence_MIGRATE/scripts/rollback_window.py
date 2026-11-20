"""Writes fcb982d makes during a rollback window, through fcb982d code, into the migrated DB.
Run with PYTHONPATH=<OLD>/brambleloop/src. Prints the ids written."""
import json

from sqlalchemy import select

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import (CostEntry, Job, LedgerEntry, Listing, ModelIdentity,
                                     OwnerAction, ArtefactProvenance)
from brambleloop.gateway import routing
from brambleloop.queue.durable import JobQueue

db = Database()
out = {}
Registry(db).audit("orchestrator", "rollback.window.write", detail={"drill": True})
q = JobQueue(db)
j = q.enqueue("orchestrator", "ops.tick", {"drill": True}, idempotency_key="rollback-drill-1")
c = q.claim("rollback-worker")
q.complete(c.id, {"ok": True}, cost_cad=0.01)
out["job"] = c.id
routing.record(db, list(routing.TASKS)[0], agent="orchestrator", tokens_in=100, tokens_out=20)
with db.session() as s:
    le = LedgerEntry(category="sale", description="rollback-window sale", gross_cad=12.5,
                     fees_cad=1.1, evidence_ref="drill")
    oa = OwnerAction(action="rollback-window owner action", reason="drill", max_cost_cad=0.0,
                     minutes=5)
    li = Listing(product_slug="drill-slug", version="1.0.0", title="Drill listing",
                 description="written by fcb982d during the rollback window", tags=["drill"],
                 price_cad=9.0)
    s.add_all([le, oa, li])
    s.flush()
    out.update(ledger=le.id, owner_action=oa.id, listing=li.id)
    # read every pre-existing table that gained columns, through the fcb982d ORM
    for m in (LedgerEntry, OwnerAction, CostEntry, Job, Listing, ModelIdentity,
              ArtefactProvenance):
        out[f"read_{m.__tablename__}"] = len(list(s.scalars(select(m))))
print(json.dumps(out))
