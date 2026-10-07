#!/usr/bin/env python3
"""W4-LEARN runtime proof: the real shadow chain for the Launch-0 CIRs, then the improvement
handlers (improve.mine, learn.scan, improve.measure) through the Worker, and the provider.

Fresh SQLite under $TMPDIR, SHADOW, no credentials. Run with the network closed:
    HTTPS_PROXY=http://127.0.0.1:9 PYTHONPATH=src python scripts/w4_learn_runtime_proof.py OUT.json
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
tmp = Path(tempfile.mkdtemp(prefix="w4learn-proof-"))
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = str(tmp / "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for k in list(os.environ):
    if k.startswith(("ETSY", "ANTHROPIC", "OPENAI")):
        os.environ.pop(k)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, Phase  # noqa: E402
from brambleloop.learn import runtime as _learn_runtime  # noqa: E402,F401
from brambleloop.products import launch0  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

db = Database(f"sqlite:///{tmp / 'company.sqlite'}", scratch=True)
db.create_all()
Registry(db).seed_defaults()
t0 = time.time()
for slug in launch0.LAUNCH0_SLUGS:
    cir = launch0.cir_for(launch0.candidate(slug).variants[0].build)
    JobQueue(db).enqueue("validator", "cir.compile", {"cir": cir.to_dict()}, priority=0,
                         idempotency_key=f"proof:{slug}")
w = Worker(db, "proof", phase=Phase.SHADOW, lease_seconds=900)
n = 0
while n < 400 and w.run_once():
    n += 1
chain = time.time() - t0
for jt, agent in (("improve.mine", "orchestrator"), ("learn.scan", "learn"),
                  ("improve.measure", "orchestrator")):
    JobQueue(db).enqueue(agent, jt, {}, idempotency_key=f"proof:{jt}")
w2 = Worker(db, "proof-improve", phase=Phase.SHADOW,
            job_types=["improve.mine", "learn.scan", "improve.measure"])
while w2.run_once():
    pass
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                      text=True).stdout.strip()
out = {"kind": "W4-LEARN runtime proof", "commit": head, "phase": "shadow",
       "database": "fresh sqlite (temp)", "chain_jobs": n, "chain_seconds": round(chain, 1)}
with db.session() as s:
    jobs: dict = {}
    for j in s.scalars(select(Job)):
        jobs.setdefault(j.job_type, {}).setdefault(j.status.value, 0)
        jobs[j.job_type][j.status.value] += 1
    out["jobs"] = jobs
    for act in ("improve.mine", "learn.scanned", "improve.measure"):
        a = s.scalars(select(AuditLog).where(AuditLog.action == act)
                      .order_by(AuditLog.id.desc())).first()
        out[act] = a.detail if a else None
from brambleloop.learn import improvement_status  # noqa: E402

summ = improvement_status.summary(db)
out["provider_cells"] = summ["cells"]
out["provider_presale"] = {k: {"value": v["value"], "reading": v["reading"],
                               "why": v.get("why"), "sample": v["sample"]}
                           for k, v in summ["presale"]["readings"].items()}
mine = out["improve.mine"] or {}
out["improve.mine"] = {k: mine.get(k) for k in ("read", "found", "dead", "dead_not_defects",
                                                 "blocked", "published")}
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str) + "\n")
db.engine.dispose()
import shutil  # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)
print("wrote", sys.argv[1])
