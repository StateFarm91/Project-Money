"""Two narrow follow-ups to resolve focused Growth-suite uncertainty; no app edits."""
import argparse,hashlib,inspect,json,os,runpy,socket,sys,tempfile,time,traceback
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
ap=argparse.ArgumentParser();ap.add_argument("--deps",required=True);ap.add_argument("--source-root");ap.add_argument("--source-sha",default="4edacff1f8b445a84749464dc1d7271e6c71173e");ap.add_argument("--suffix",default="");ap.add_argument("--only",choices=["route","bands"]);args=ap.parse_args()
if args.source_root:ROOT=Path(args.source_root).resolve()
sys.path[:0]=[str(Path(args.deps).resolve()),str(ROOT/"src"),str(ROOT)]
for k in list(os.environ):
    if k.startswith(("ANTHROPIC","OPENAI","ETSY","GEMINI","GOOGLE_API","DATABASE_URL","BRAMBLELOOP_DATABASE")):os.environ.pop(k,None)
os.environ.update(BRAMBLELOOP_PHASE="shadow",BRAMBLELOOP_REQUIRE_POSTGRES="0")
original_connect=socket.socket.connect
allowed_pairs=[]
def connect(self,address):
    caller=inspect.currentframe().f_back
    # Windows implements socketpair using a loopback handshake. Only that stdlib
    # call site is allowed, never application connections or hostname resolution.
    if (caller.f_code.co_name in ("socketpair","_fallback_socketpair") and
        Path(caller.f_code.co_filename).resolve()==Path(socket.__file__).resolve()
        and isinstance(address,tuple) and address[0] in ("127.0.0.1","::1")):
        allowed_pairs.append("stdlib.socketpair")
        return original_connect(self,address)
    raise RuntimeError("External/application network forbidden")
def blocked(*a,**k):raise RuntimeError("External/application network forbidden")
socket.socket.connect=connect;socket.socket.connect_ex=blocked;socket.create_connection=blocked
test_path=ROOT/"tests/test_cert_growth_ops.py"
fixtures=runpy.run_path(str(test_path),run_name="codex_isolated_growth_fixture")
results=[]
def run(name,fn):
    start=time.perf_counter()
    try:
        observed=fn();status="PASS";error=None
    except Exception:
        observed=None;status="FAIL";error=traceback.format_exc()
    results.append({"test":name,"status":status,"observed":observed,"error":error,"seconds":round(time.perf_counter()-start,3)})
    print(name,status,flush=True)
def route():
    fixtures["test_stats_ingest_benchmarks_and_scale_routes_read_the_database"]()
    return {"allowed_stdlib_socketpairs":len(allowed_pairs),"external_network":"denied"}
if args.only!="bands":run("existing_growth_route_with_local_socketpair",route)
observations={}
def bands():
    from sqlalchemy import select
    from brambleloop.core.models import OperatingReading,Job
    from brambleloop.seasonal import daily
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import growth_ops
    from brambleloop.swarm.orchestrate import BAND_BY_KIND
    db=fixtures["_db"]()
    slug=fixtures["FLAGSHIP"];today=fixtures["TODAY"]
    with db.session() as s:
        s.add(OperatingReading(kind=daily.KIND,period_key=today.isoformat(),
          payload={"fast_lane":{"admitted":[slug]}}))
    job=JobQueue(db).enqueue("listing","chain.rebuild",{"slug":slug},
      idempotency_key="codex-band-contract",priority=BAND_BY_KIND["seasonal_deadline"])
    customer=JobQueue(db).enqueue("customer_support","support.reply",{"case_id":999},
      idempotency_key="codex-customer-band",priority=BAND_BY_KIND["customer_incident"])
    before=job.priority
    result=growth_ops.steer(db,today=today)
    with db.session() as s:after=s.get(Job,job.id).priority
    observations.update(before=before,after=after,protected_truth_band=BAND_BY_KIND["truth_defect"],
                        moved=result["jobs_moved"])
    claimed=JobQueue(db).claim("codex-contract-verifier")
    observations.update(claimed_job_type=claimed.job_type,claimed_job_id=claimed.id,
                        waiting_customer_job_id=customer.id,customer_priority=customer.priority)
    db.engine.dispose()
    assert after>BAND_BY_KIND["truth_defect"],observations
    return observations
if args.only!="route":run("G02_single_fast_lane_steer_preserves_customer_truth_priority",bands)
payload={"base":args.source_sha,"results":results,
  "band_observations":observations,"test_sha256":hashlib.sha256(test_path.read_bytes()).hexdigest(),
  "source_sha256":hashlib.sha256((ROOT/"src/brambleloop/runtime/growth_ops.py").read_bytes()).hexdigest(),
  "paid_spend":0,"note":"No production source patched; exact existing route test rerun only. New queue-band assertion is separate from C75 idempotence."}
(HERE/("out/growth_followups"+args.suffix+".json")).write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8",newline="\n")
sys.exit(int(any(r["status"]!="PASS" for r in results)))
