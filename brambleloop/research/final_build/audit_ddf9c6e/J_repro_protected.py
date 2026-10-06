"""J-autonomy repro (Q2): hostile next_work provider output + direct enqueue-boundary attacks."""
import os, tempfile, json, types
from datetime import datetime, timezone
os.environ["BRAMBLELOOP_PHASE"]="shadow"
from brambleloop.core.db import Database
from brambleloop.agents.registry import Registry
from brambleloop.queue.durable import JobQueue
from brambleloop.autonomy import orchestrator, charters, generators
from brambleloop.core.models import Job
from sqlalchemy import select
import importlib
tmp=tempfile.mkdtemp(); db=Database(f"sqlite:///{tmp}/j.sqlite"); db.create_all(); Registry(db).seed_defaults()
q=JobQueue(db); now=datetime.now(timezone.utc)
PROT=set(charters.PROTECTED_JOB_TYPES)
evil = [
 {"job_type":"store.publish","key":"x","kind":"run_cycle","ready":True,"id":"store.publish","blocked_by":[]},
 {"job_type":"ads.campaign","key":"ads.eligibility_tick","kind":"internal","spend_cad":0,"id":"ads.campaign"},
 {"job_type":"support.reply","key":"seo.run_cycle","kind":"internal","external_effect":False,"id":"a"},
 {"job_type":"improve.sandbox","key":"store.publish/../../x"*30,"kind":"x","id":"b"},
 {"job_type":"store.publish\u0000","key":"seo.review:store.publish","kind":"internal"},
]
def fake_next_work(db): return evil
for label,(mod,fn) in {"learn":("brambleloop.learn.improvement_status","next_work"),
    "finance":("brambleloop.finance.accounting.dashboard","next_work"),
    "seo":("brambleloop.seo.status","next_work"),"ads":("brambleloop.growth.ads_readiness","next_work")}.items():
    setattr(importlib.import_module(mod), fn, fake_next_work)
rep=orchestrator.tick(db,q,now=now)
with db.session() as s:
    types_=[(j.agent,j.job_type) for j in s.scalars(select(Job))]
print("enqueued types:",sorted({t for _,t in types_}))
print("PROTECTED ENQUEUED:", [t for _,t in types_ if t in PROT])
print("errors:",rep["errors"])
# direct boundary attacks
ch=charters.BY_KEY["store_commerce"]
for jt,prot in [("store.publish",False),("seo.cycle",True),("pricing.experiment",False),("support.reply",False),("not.a.job",False)]:
    c=generators.Candidate(department="store_commerce",job_type=jt,value=99,source="x",reason="r",fingerprint="f"+jt,protected=prot)
    try: orchestrator._enqueue_mission(db,q,ch,c,now); print(jt,prot,"ENQUEUED")
    except orchestrator.ProtectedActionRefused as e: print(jt,prot,"refused:",e)
# mutate generatable? charters are frozen dataclasses with tuple
try: ch.generatable += ("store.publish",)
except Exception as e: print("charter immutable:",type(e).__name__)
# Is PROTECTED set complete vs agent registry/phase layer protected types?
from brambleloop.agents import registry as R
import inspect
print([n for n in dir(R) if "PROTECT" in n.upper() or "FORBID" in n.upper()])
