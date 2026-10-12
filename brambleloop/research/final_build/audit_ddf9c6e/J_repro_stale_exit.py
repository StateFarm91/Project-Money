"""J-autonomy repro (Q5): one poisoned cadence aborts the whole Scheduler.tick; the supervisor then
os._exit(1)s the container every ~16 min (a restart loop) even though the web + worker are healthy."""
import os, tempfile
from datetime import datetime, timedelta, timezone
os.environ["BRAMBLELOOP_PHASE"]="shadow"
from brambleloop.core.db import Database
from brambleloop.agents.registry import Registry
from brambleloop.queue import durable
from brambleloop.runtime import worker as W
from brambleloop.app import runner
from sqlalchemy import select
from brambleloop.core.models import Job
tmp=tempfile.mkdtemp(); db=Database(f"sqlite:///{tmp}/j.sqlite"); db.create_all(); Registry(db).seed_defaults()
poison=W.CADENCES[5][2]; print("poisoned cadence:",W.CADENCES[5][0],poison,"of",len(W.CADENCES))
orig=durable.JobQueue.enqueue
def enq(self,agent,job_type,*a,**k):
    if job_type==poison: raise ValueError("handler-specific validation error (e.g. bad priority/band, schema drift)")
    return orig(self,agent,job_type,*a,**k)
durable.JobQueue.enqueue=enq
try: W.Scheduler(db).tick()
except Exception as e: print("Scheduler.tick raised:",type(e).__name__,e)
with db.session() as s: n=len(list(s.scalars(select(Job)))); 
print("cadences enqueued before abort:",n,"of",len(W.CADENCES),"(all later cadences starve every tick)")
# supervisor behaviour with a scheduler that never completes a tick
exits=[]; runner._exit=lambda c: exits.append(c)
t0=datetime.now(timezone.utc); runner.STATE.enabled=True; runner.STATE.scheduler_started_at=t0
runner.STATE.scheduler_last_tick=None
strikes=0
for minute in range(0,40):
    before=len(exits); strikes=runner.supervise_once(strikes,now=t0+timedelta(minutes=minute))
    if len(exits)>before: print(f"os._exit(1) fired at minute {minute} after boot (threshold {runner.SELF_EXIT_STALE_S:.0f}s + START_DELAY {runner._START_DELAY}s)"); break
print("restart policy: ON_FAILURE max 10 retries ->",__import__('json').load(open('railway.json'))['deploy'])
