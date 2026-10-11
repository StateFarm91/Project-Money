"""Seed the throwaway Postgres with a realistic offline release-chain run (mirrors
research/final_build/w4/pipe_chain_run.py, but on the app's own Postgres DB so the CC reads it).
Usage: python3 seed.py slug [slug ...]"""
import env  # noqa: F401  (sets env, loopback-only network)
import json
import sys
import time
from pathlib import Path

from sqlalchemy import select

from brambleloop.app import main
from brambleloop.agents.registry import Registry
from brambleloop.core.models import Job, OperatingReading, Phase
from brambleloop.intel import findings as F
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline, release  # noqa: F401 - registers handlers
from brambleloop.runtime.pipeline import _engineered_cir
from brambleloop.runtime.worker import Worker

t0 = time.time()
db = main.db
db.create_all()
with db.session() as s:
    fresh = s.scalar(select(Job).limit(1)) is None
if fresh:
    Registry(db).seed_defaults()
    mjs = Path(env.ROOT) / "research/final_build/w4/MJS_FINDINGS.json"
    payload = json.loads(mjs.read_text())
    with db.session() as s:
        s.add(OperatingReading(kind=F.KIND, period_key=str(payload.get("as_of")), payload=payload))
built = {}
for slug in sys.argv[1:]:
    cir = _engineered_cir(slug)
    built[slug] = cir.version if cir else "no design"
    if cir:
        JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                             idempotency_key=f"cert-{slug}", priority=0)
chain = ["gate.certify", "listing.draft", "assets.build", "pricing.position",
         "listing.seo", "launch.plan", "store.publish"]
worker = Worker(db, "ccverify-chain", phase=Phase.SHADOW, job_types=chain, lease_seconds=1800)
for _ in range(500):
    if not worker.run_once():
        break
jobs = {}
with db.session() as s:
    for j in s.scalars(select(Job)):
        k = f"{j.job_type}:{j.status.value}"
        jobs[k] = jobs.get(k, 0) + 1
out = {"built": built, "jobs": jobs, "seconds": round(time.time() - t0, 1)}
Path(env.SCR, "seed_result.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
