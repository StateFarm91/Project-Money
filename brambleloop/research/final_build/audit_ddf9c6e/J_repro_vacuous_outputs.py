"""J-autonomy repro (Q1): what did 'useful' generated missions actually output on an EMPTY database?"""
import os, tempfile, json
from datetime import datetime, timedelta, timezone
os.environ["BRAMBLELOOP_PHASE"]="shadow"
from brambleloop.core.db import Database
from brambleloop.agents.registry import Registry
from brambleloop.runtime.worker import Worker
from brambleloop.queue.durable import JobQueue
from brambleloop.autonomy import orchestrator, kpis
from brambleloop.core.models import Phase, Job
from sqlalchemy import select
import brambleloop.runtime.pipeline, brambleloop.autonomy.handlers
tmp=tempfile.mkdtemp(); db=Database(f"sqlite:///{tmp}/j.sqlite"); db.create_all(); Registry(db).seed_defaults()
q=JobQueue(db); w=Worker(db,"j-worker",phase=Phase.SHADOW)
base=datetime.now(timezone.utc)
for n in range(3):
    orchestrator.tick(db,q,now=base+timedelta(hours=7*n))
    while w.run_once(): pass
seen=set()
with db.session() as s:
    for j in s.scalars(select(Job).order_by(Job.id)):
        if (j.inputs or {}).get("source")!="autonomy" or j.job_type in seen: continue
        seen.add(j.job_type)
        print(f"{j.job_type:34s} status={j.status.value:5s} did_no_work={kpis.did_no_work(j.outputs)!s:5s} outputs={json.dumps(j.outputs,default=str)[:230]}")
