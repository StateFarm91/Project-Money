"""J-autonomy repro (Q6): can a department inflate useful_completions_24h with identical work?"""
import os, tempfile, json
os.environ["BRAMBLELOOP_PHASE"]="shadow"
from brambleloop.core.db import Database
from brambleloop.agents.registry import Registry
from brambleloop.runtime.worker import Worker
from brambleloop.queue.durable import JobQueue
from brambleloop.autonomy import kpis
from brambleloop.core.models import Phase, Job
from sqlalchemy import select
import brambleloop.runtime.pipeline, brambleloop.autonomy.handlers
tmp=tempfile.mkdtemp(); db=Database(f"sqlite:///{tmp}/j.sqlite"); db.create_all(); Registry(db).seed_defaults()
q=JobQueue(db); w=Worker(db,"w",phase=Phase.SHADOW)
def run(agent,jt,inputs,n):
    for i in range(n):
        q.enqueue(agent,jt,{**inputs,"mission":f"m{i}"},idempotency_key=f"gaming:{jt}:{i}")
        while w.run_once(): pass
# 1) growth.distribution / scale.trajectory on unchanged (empty) data, 10 times
run("growth","growth.distribution",{},10)
run("coo" if False else "orchestrator","scale.trajectory",{},10)
# 2) KPI self-review x10 for the same department with no activity at all
run("coo","autonomy.department_review",{"department":"visual"},10)
with db.session() as s:
    for jt in ("growth.distribution","scale.trajectory","autonomy.department_review"):
        outs=[j.outputs for j in s.scalars(select(Job).where(Job.job_type==jt))]
        print(jt, "runs",len(outs),"distinct fingerprints",len({kpis.fingerprint(o) for o in outs}),
              "did_no_work:",sum(kpis.did_no_work(o) for o in outs))
for d in ("growth","executive","visual"):
    r=kpis.compute(db,d); print(d,"useful_completions_24h =",r["kpis"]["useful_completions_24h"]["value"],r["counted"]["useful_distinct"],"distinct useful of",r["counted"]["finished"])
# which keys differ between two runs?
with db.session() as s:
    a,b=[j.outputs for j in s.scalars(select(Job).where(Job.job_type=="growth.distribution").limit(2))]
print("keys differing between two identical-input growth.distribution runs:",[k for k in a if a[k]!=b.get(k)])
