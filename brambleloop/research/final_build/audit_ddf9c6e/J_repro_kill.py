"""J-autonomy repro (Q3): SIGKILL a real worker process mid-job, and a stale (alive) worker.
The 'external effect' is a line appended to a file by a generic handler (no handler-level guard)."""
import os, sys, time, signal, subprocess, tempfile, threading
from pathlib import Path
SRC=str(Path(__file__).resolve().parents[3]/"src")
tmp=tempfile.mkdtemp(); DB=f"sqlite:///{tmp}/k.sqlite"; EFF=Path(tmp)/"effects.txt"
child = f'''
import os,sys,time
os.environ["BRAMBLELOOP_PHASE"]="shadow"
sys.path.insert(0,{SRC!r})
from brambleloop.core.db import Database
from brambleloop.runtime.worker import Worker, handlers, JobContext
from brambleloop.core.models import Phase
mode=sys.argv[1]; name=sys.argv[2]
db=Database({DB!r})
@handlers.register("ops.queue_check")
def h(ctx):
    open({str(EFF)!r},"a").write(f"effect by {{name}} attempt={{ctx.job.attempts}} t={{time.time():.1f}}\\n")
    if mode=="hang": time.sleep(120)
    if mode=="slow": time.sleep(9)
    return {{"ran":True,"moved":1,"by":name}}
import brambleloop.runtime.worker as W
if mode=="slow": W._LeaseRenewal.start=lambda self: None   # renewal thread stalled (GC pause / starved)
w=Worker(db,name,phase=Phase.SHADOW,lease_seconds=3)
w.run_once(); print(name,"stats",w.stats,flush=True)
'''
Path(tmp,"child.py").write_text(child)
sys.path.insert(0,SRC); os.environ["BRAMBLELOOP_PHASE"]="shadow"
from brambleloop.core.db import Database
from brambleloop.agents.registry import Registry
from brambleloop.queue.durable import JobQueue
from brambleloop.core.models import Job, AuditLog
from sqlalchemy import select
db=Database(DB); db.create_all(); Registry(db).seed_defaults()
q=JobQueue(db,lease_seconds=3); q.enqueue("orchestrator","ops.queue_check",{"x":1},idempotency_key="kill-1")
env=dict(os.environ,PYTHONPATH=SRC)
p=subprocess.Popen([sys.executable,f"{tmp}/child.py","hang","W1"],env=env)
for _ in range(100):
    if EFF.exists(): break
    time.sleep(0.1)
os.kill(p.pid,signal.SIGKILL); p.wait(); print("W1 SIGKILLed; effects so far:",EFF.read_text().strip().splitlines())
time.sleep(3.5)
r=subprocess.run([sys.executable,f"{tmp}/child.py","ok","W2"],env=env,capture_output=True,text=True); print(r.stdout.strip(), r.stderr[-300:])
print("--- SIGKILL scenario: effect lines =",len(EFF.read_text().strip().splitlines())); print(EFF.read_text())
with db.session() as s:
    j=s.scalars(select(Job)).first(); print("job:",j.status.value,"attempts",j.attempts,j.outputs)
    print("queue.* refusal audit rows after SIGKILL scenario (what soak_report's 'no duplicated external effect' reads):",[a.action for a in s.scalars(select(AuditLog)) if a.action.startswith("queue.")])
# stale-but-alive worker
EFF.unlink(); q.enqueue("orchestrator","ops.queue_check",{"x":2},idempotency_key="kill-2")
p1=subprocess.Popen([sys.executable,f"{tmp}/child.py","slow","S1"],env=env,stdout=subprocess.PIPE,text=True)
time.sleep(4.5)   # S1 lease (3s) expired while S1 still running its handler
r=subprocess.run([sys.executable,f"{tmp}/child.py","ok","S2"],env=env,capture_output=True,text=True); print(r.stdout.strip())
print("S1:",p1.communicate()[0].strip())
print("--- stale scenario: effect lines =",len(EFF.read_text().strip().splitlines())); print(EFF.read_text())
with db.session() as s:
    j=s.scalars(select(Job).where(Job.id==2)).first(); print("job2:",j.status.value,j.outputs)
    print("audit:",[a.action for a in s.scalars(select(AuditLog)) if "stale" in a.action])
