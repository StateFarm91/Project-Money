"""J-autonomy repro (Q4): one department blocked overnight; do others continue? does the block bind cadences?"""
import os, tempfile
from datetime import datetime, timedelta, timezone
os.environ["BRAMBLELOOP_PHASE"]="shadow"
from brambleloop.core.db import Database
from brambleloop.agents.registry import Registry
from brambleloop.runtime.worker import Worker, Scheduler
from brambleloop.queue.durable import JobQueue
from brambleloop.autonomy import orchestrator, memory
from brambleloop.core.models import Phase, Job
from sqlalchemy import select
import brambleloop.runtime.pipeline, brambleloop.autonomy.handlers
tmp=tempfile.mkdtemp(); db=Database(f"sqlite:///{tmp}/j.sqlite"); db.create_all(); Registry(db).seed_defaults()
q=JobQueue(db); w=Worker(db,"w",phase=Phase.SHADOW); base=datetime.now(timezone.utc)
memory.block_department(db,"support",reason="owner action: approve refund policy",owner_action="refund_policy",now=base)
for n in range(3):
    rep=orchestrator.tick(db,q,now=base+timedelta(hours=8*n))
    while w.run_once(): pass
    st={k:v.get("state") for k,v in rep["departments"].items()}
    print(n,"support:",st["support"],"| others GENERATED:",sum(1 for k,v in st.items() if k!="support" and v=="GENERATED"),"/10", {k:v for k,v in st.items() if v not in("GENERATED",)})
# does the block stop the blocked department's scheduled cadences?
s=Scheduler(db); en=s.tick(); 
with db.session() as ss:
    sup=[j.job_type for j in ss.scalars(select(Job)) if j.job_type.startswith("support.")]
print("support jobs run/queued while BLOCKED:",sup)
print("block row:",memory.active_block(db,"support")["body"])
