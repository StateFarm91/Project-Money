"""J-autonomy repro: (Q1/Q6) self-review is vacuously 'useful' and inflates the useful KPI.
Drives the real orchestrator tick + real Worker on an empty temp DB with simulated time."""
import os, sys, tempfile, json
from datetime import datetime, timedelta, timezone
os.environ["BRAMBLELOOP_PHASE"]="shadow"
from brambleloop.core.db import Database
from brambleloop.agents.registry import Registry
from brambleloop.runtime.worker import Worker
from brambleloop.queue.durable import JobQueue
from brambleloop.autonomy import orchestrator, kpis, charters, memory
from brambleloop.core.models import Phase
import brambleloop.runtime.pipeline  # handlers
import brambleloop.autonomy.handlers
tmp=tempfile.mkdtemp(); db=Database(f"sqlite:///{tmp}/j.sqlite"); db.create_all(); Registry(db).seed_defaults()
q=JobQueue(db); w=Worker(db,"j-worker",phase=Phase.SHADOW)
# only autonomy tick; no scheduler cadences => "near-empty queue"
base=datetime.now(timezone.utc)
for n in range(8):
    now=base+timedelta(hours=7*n)
    rep=orchestrator.tick(db,q,now=now)
    while w.run_once(): pass
    print(n,{k:v.get("state") for k,v in rep["departments"].items()})
print("--- missions by dept/type/outcome")
orchestrator.reconcile_missions(db, now=base+timedelta(hours=60))
from collections import Counter
c=Counter((m["department"],m["body"]["job_type"],m["state"]) for m in memory.recall(db,kind="mission",limit=500))
for k,v in sorted(c.items()): print(k,v)
print("--- KPI useful_completions_24h per dept (real now)")
for ch in charters.CHARTERS:
    r=kpis.compute(db,ch.key)
    print(ch.key, r["kpis"]["useful_completions_24h"]["value"], r["counted"])
