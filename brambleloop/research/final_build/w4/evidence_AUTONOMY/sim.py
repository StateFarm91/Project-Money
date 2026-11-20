"""Bounded shadow simulation: a DB seeded like production 0417f35 at 14:39Z (spent Anthropic
balance; model jobs parked +30 min), then three orchestrator ticks each followed by a worker
drain. No network (proxies closed by caller), no credentials, shadow phase."""
import json, sys, tempfile
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from brambleloop.agents.registry import Registry
from brambleloop.autonomy import orchestrator, rule1, generators
from brambleloop.core.db import Database
from brambleloop.core.models import Job, JobStatus, OwnerAction
from brambleloop.ops import funding
from brambleloop.runtime import pipeline, release  # noqa
from brambleloop.runtime.worker import Worker

url = sys.argv[1] if len(sys.argv) > 1 else f"sqlite:///{tempfile.mkdtemp()}/sim.sqlite"
db = Database(url); db.create_all(); Registry(db).seed_defaults()
now = datetime.now(timezone.utc)
with db.session() as s:
    s.add(OwnerAction(requirement_key=funding.REQUIREMENT_KEY,
                      action="Add credit to the Anthropic account.", reason="balance spent"))
    for i, (a, jt) in enumerate([("creative_director", "creative.tournament")] * 4 +
                                [("creative_director", "creative.grid_tournament"),
                                 ("market_radar", "intel.gallery_analysis"),
                                 ("publishing", "seasonal.cycle_proof")]):
        s.add(Job(agent=a, job_type=jt, inputs={"n": i}, priority=40, status=JobStatus.PENDING,
                  run_after=now + timedelta(minutes=30), idempotency_key=f"parked-{i}"))
out = {"ticks": []}
DEPTS = ("product_design", "intelligence", "visual")
for t in range(3):
    rep = orchestrator.tick(db)
    w = Worker(db, "sim")
    n = 0
    while n < 40 and w.run_once():
        n += 1
    out["ticks"].append({"states": {d: rep["departments"][d].get("state") for d in DEPTS},
                         "missions": {m["department"]: m["job_type"] for m in rep["missions"]
                                      if m["department"] in DEPTS},
                         "worker_claims": n})
m = rule1.measure(db, now=datetime.now(timezone.utc))["departments"]
out["rule1"] = {d: {k: m[d].get(k) for k in ("done", "useful", "noop", "dead", "useful_types",
                                             "idle_at_end", "rule1_defect")} for d in DEPTS}
with db.session() as s:
    out["parked_still_pending"] = len(list(s.scalars(select(Job.id).where(
        Job.idempotency_key.like("parked-%"), Job.status == JobStatus.PENDING))))
print(json.dumps(out, indent=1, default=str))
