#!/usr/bin/env python3
"""W4-LEARN loops proof: experiment -> measured outcome -> accepted/rejected, on a scratch DB.

The database is seeded like production from the public GET snapshot
`research/final_build/w4/evidence/learn_prod_snapshot_20261011.json` (cadence table, incident
signatures, the 15 open proposals) plus the real shadow chain for the three Launch-0 CIRs, so
the teardown lab opens its delight proposals itself. Then, through the Worker:

  A. improve.mine     -- production-shaped stale-artefact incidents become family lessons and
                         the per-signature lessons production holds are superseded;
  B. improve.replay   -- 25 days of production-cadence job history: the six neighbours are
                         measured against the incumbent and REJECTED on the league rule (what
                         production recorded on 2026-10-11), then re-trialled 8 days later;
  C. improve.replay + improve.sandbox on the same history plus a SYNTHETIC contention burst
                         (labelled as such): a challenger wins, the evaluator approves, the
                         scoring tier promotes, and the next enqueue uses the promoted policy;
  D. improve.sandbox  -- the delight backlog: each proposal re-measured with the instrument that
                         raised it, waiting inside the TTL and REJECTED as expired-unexecuted
                         once the TTL has passed with the measured driver unchanged.

Fresh SQLite under $TMPDIR, SHADOW, no credentials, network closed:
    HTTPS_PROXY=http://127.0.0.1:9 PYTHONPATH=src python scripts/w4_learn_loops_proof.py OUT.json
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
tmp = Path(tempfile.mkdtemp(prefix="w4learn-loops-"))
# INTEG3 (test_w3_tmp_hygiene): the proof's scratch directory is removed when it exits.
import atexit  # noqa: E402
import shutil  # noqa: E402

atexit.register(shutil.rmtree, tmp, ignore_errors=True)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = str(tmp / "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for k in list(os.environ):
    if k.startswith(("ETSY", "ANTHROPIC", "OPENAI")):
        os.environ.pop(k)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (ConfigVersion, Improvement, Incident, Job,  # noqa: E402
                                     JobStatus, Lesson, Phase, Product)
from brambleloop.improve import backlog, bus, loops, replay, runner  # noqa: E402
from brambleloop.learn import runtime as _learn_runtime  # noqa: E402,F401
from brambleloop.products import launch0  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.swarm import orchestrate  # noqa: E402

SNAP = json.loads((ROOT / "research/final_build/w4/evidence/"
                   "learn_prod_snapshot_20261011.json").read_text())
NOW = datetime.now(timezone.utc)
out: dict = {"kind": "W4-LEARN loops proof", "phase": "shadow",
             "commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                      capture_output=True, text=True).stdout.strip(),
             "seeded_from": "learn_prod_snapshot_20261011.json (production public GETs)"}

db = Database(f"sqlite:///{tmp / 'company.sqlite'}", scratch=True)
db.create_all()
Registry(db).seed_defaults()
q = JobQueue(db)


def work(job_types: list[str], tag: str) -> list[dict]:
    w = Worker(db, f"proof-{tag}", phase=Phase.SHADOW, job_types=job_types,
               lease_seconds=900)
    done = []
    while w.run_once():
        pass
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type.in_(job_types),
                                             Job.idempotency_key.like(f"proof:{tag}%"))):
            done.append({"id": j.id, "job_type": j.job_type, "status": j.status.value,
                         "outputs": j.outputs})
    return done


# ---- 0. the real shadow chain: three Launch-0 CIRs; the teardown lab opens delight proposals
t0 = time.time()
for slug in launch0.LAUNCH0_SLUGS:
    cir = launch0.cir_for(launch0.candidate(slug).variants[0].build)
    q.enqueue("validator", "cir.compile", {"cir": cir.to_dict()}, priority=0,
              idempotency_key=f"proof:chain:{slug}")
w = Worker(db, "proof-chain", phase=Phase.SHADOW, lease_seconds=900)
n = 0
while n < 400 and w.run_once():
    n += 1
out["chain"] = {"jobs": n, "seconds": round(time.time() - t0, 1)}
with db.session() as s:
    out["chain"]["delight_proposals"] = [
        {"id": r.id, "cell": r.cell, "ref": r.baseline_ref, "baseline": r.baseline_value,
         "state": r.state} for r in s.scalars(select(Improvement))
        if (r.baseline_ref or "").startswith("delight:")]
    slugs = sorted(s.scalars(select(Product.slug)))
out["chain"]["products"] = slugs

# ---- A. lessons: production-shaped incidents and production's per-signature lessons --------
prod_stale = [sig for sig in SNAP["incidents"]["open_signatures"]
              if sig.startswith("stale-artefact:visual_truth:")][:12]
with db.session() as s:
    for i, sig in enumerate(prod_stale):
        # Production's signature shape, re-pointed at the products this chain certified.
        slug = slugs[i % len(slugs)]
        tail = sig.split("@", 1)[1] if "@" in sig else "1.0.0#1"
        s.add(Incident(severity="P1", signature=f"stale-artefact:visual_truth:{slug}@{tail}",
                       product_slug=slug, summary="visual truth is older than its upstreams",
                       detail={}))
legacy = []
with db.session() as s:
    sigs = [i.signature for i in s.scalars(select(Incident).where(
        Incident.signature.like("stale-artefact:%")))]
for sig in sigs:                                     # what production's bus holds today
    legacy.append(bus.publish(db, origin_cell="quality", subject="defect",
                              statement=f"Unresolved P1 incident {sig!r}: per-signature lesson "
                                        f"as production's miner wrote it",
                              evidence_ref=f"incident:{sig}"))
before = bus.compounding(db)
q.enqueue("orchestrator", "improve.mine", {}, idempotency_key="proof:mine:1")
mined = work(["improve.mine"], "mine")
after = bus.compounding(db)
out["A_lessons"] = {
    "incidents_seeded": len(sigs), "legacy_lessons": len(legacy),
    "before": {k: before[k] for k in ("lessons", "routed", "acted_on")},
    "after": {k: after[k] for k in ("lessons", "routed", "acted_on", "superseded")},
    "mine_job": {k: (mined[0]["outputs"] or {}).get(k) for k in ("read", "groups",
                                                                   "published", "reused")}
    if mined else None,
}

# ---- B. replay on production-cadence history: measured, rejected, re-trialled -------------
start = NOW - timedelta(days=25)
rows = 0
with db.session() as s:
    for c in SNAP["cadences"]:
        every = float(c["every_hours"])
        t = start
        while t < NOW - timedelta(hours=1):
            s.add(Job(agent=c["agent"], job_type=c["job_type"], inputs={}, priority=50,
                      status=JobStatus.DONE, created_at=t, run_after=t, started_at=t,
                      finished_at=t + timedelta(seconds=30)))
            rows += 1
            t += timedelta(hours=every)
q.enqueue("orchestrator", "improve.replay", {}, idempotency_key="proof:replay:1")
rep = work(["improve.replay"], "replay")[0]["outputs"]
reopen = replay.cycle(db, now=NOW + timedelta(days=1))
with db.session() as s:
    for c in s.scalars(select(ConfigVersion).where(ConfigVersion.retired_at.is_not(None))):
        c.retired_at = c.retired_at - timedelta(days=replay.RETRIAL_DAYS + 1)
retrial = replay.cycle(db, now=NOW + timedelta(days=1))
out["B_replay_production_history"] = {
    "jobs_seeded_from_cadences": rows, "cadences": len(SNAP["cadences"]),
    "production_recorded": SNAP["last_outputs"].get("improve_replay"),
    "jobs": rep.get("jobs"), "days": rep.get("days"),
    "compared": rep.get("compared"), "retired": len(rep.get("retired") or []),
    "proposed": rep.get("proposed"),
    "next_day_reopened": len(reopen.get("challengers_reopened") or []),
    "after_retrial_window": {"reopened": len(retrial.get("challengers_reopened") or []),
                             "compared": len(retrial.get("compared") or []),
                             "retired_again": len(retrial.get("retired") or [])},
}

# ---- C. the accept path: a SEPARATE scratch DB holding only a SYNTHETIC contention history -
# On production-shaped history (B) no policy can win: no production job carries a deadline or
# a value, so every neighbour ties at gain 0.000 -- the measured verdict production recorded.
# Mixing a 50-job burst into 30k cadence jobs leaves the gain under the 0.030 margin too, so
# the accept path is shown on its own database, labelled synthetic, through the same handlers.
db_main = db
db = Database(f"sqlite:///{tmp / 'accept.sqlite'}", scratch=True)
db.create_all()
Registry(db).seed_defaults()
q = JobQueue(db)
orchestrate.clear_policy_cache()
with db.session() as s:
    for d in range(5):
        b0 = (NOW - timedelta(days=6 - d)).replace(hour=1, minute=0, second=0, microsecond=0)
        for i in range(10):
            urgent = i >= 5
            s.add(Job(agent="orchestrator", job_type="improve.nightly",
                      inputs=({"deadline": (b0 + timedelta(hours=3)).isoformat()} if urgent
                              else {"deadline": (b0 + timedelta(days=25)).isoformat(),
                                    "value_cad": 500}),
                      priority=85, status=JobStatus.DONE, created_at=b0, run_after=b0,
                      started_at=b0, finished_at=b0 + timedelta(hours=1)))
q.enqueue("orchestrator", "improve.replay", {}, idempotency_key="proof:replayc:1")
repc = work(["improve.replay"], "replayc")[0]["outputs"]
q.enqueue("orchestrator", "improve.sandbox", {}, idempotency_key="proof:sandboxc:1")
sbc = work(["improve.sandbox"], "sandboxc")[0]["outputs"]
orchestrate.clear_policy_cache()
policy = orchestrate.priority_policy(db)
iid = (repc.get("proposed") or [{}])[0].get("improvement")
with db.session() as s:
    row = s.get(Improvement, iid) if iid else None
    accepted = ({"improvement": row.id, "state": row.state, "baseline": row.baseline_value,
                 "result": row.result_value, "approved_by": (row.evidence or {}).get(
                     "approved_by"), "executed": bool((row.evidence or {}).get("executed")),
                 "change": (row.evidence or {}).get("change", {}).get("config_id")}
                if row else None)
board_c = loops.scoreboard(db)
out["C_replay_accept_path_SYNTHETIC_contention"] = {
    "label": "SYNTHETIC: separate scratch DB, 5 days x 10 contention jobs (cert-test shape)",
    "compared": repc.get("compared"), "proposed": repc.get("proposed"),
    "retired": len(repc.get("retired") or []),
    "sandbox": {k: sbc.get(k) for k in ("tested", "approved", "promoted", "note")},
    "improvement": accepted, "active_priority_policy": policy.get("config_id"),
    "scoreboard_experiments": board_c["experiments"],
}
db = db_main
q = JobQueue(db)
orchestrate.clear_policy_cache()

# ---- D. the delight backlog: measured inside the TTL, expired after it ---------------------
q.enqueue("orchestrator", "improve.sandbox", {}, idempotency_key="proof:sandboxd:1")
sbd = work(["improve.sandbox"], "sandboxd")[0]["outputs"]
inside = backlog.evaluate(db, now=NOW + timedelta(days=1), audit=False)
past = runner.run(db, now=NOW + timedelta(days=backlog.DELIGHT_TTL_DAYS + 1))["backlog"]
with db.session() as s:
    closed = [{"id": r.id, "ref": r.baseline_ref, "state": r.state,
               "baseline": r.baseline_value,
               "measured": ((r.evidence or {}).get("backlog") or {}).get("reading"),
               "why": ((r.evidence or {}).get("why") or "")[:160]}
              for r in s.scalars(select(Improvement))
              if (r.baseline_ref or "").startswith("delight:")]
out["D_delight_backlog"] = {
    "sandbox_job_backlog": sbd.get("backlog"),
    "inside_ttl": {k: inside[k] for k in ("waiting", "verified", "expired")},
    "after_ttl": {k: past[k] for k in ("expired", "verified", "regressed", "open_before",
                                        "open_after")},
    "rows": closed,
}

board = loops.scoreboard(db)
out["scoreboard"] = {"count": board["count"], "experiments": board["experiments"],
                     "lessons": board["lessons"],
                     "loops": [{k: x.get(k) for k in ("loop", "status", "outcomes", "why")}
                               for x in board["loops"]]}
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str) + "\n")
print(json.dumps({"chain": out["chain"]["jobs"], "count": board["count"],
                  "experiments": board["experiments"]}, default=str))
