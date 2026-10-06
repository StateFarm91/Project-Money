"""K11 runtime proof: the authority model on the real worker path (shadow, temp SQLite, no network).

Path exercised: queue -> Worker.run_once -> Registry.authorize (authority-class check) ->
`autonomy.orchestrate` handler -> orchestrator.tick -> authority.dag.tick. Then a "restart"
(new Database object on the same file) and a second orchestrate job recomputing READY work.

Seeding is explicit and labelled: three DAG items submitted through the public API
(`dag.submit`, submitter "laura"), because on an empty database no generator proposes protected
work. Nothing here publishes, spends or messages; phase stays shadow.

Run: PYTHONPATH=src python research/final_build/w3/K11_runtime_proof.py
Writes research/final_build/w3/evidence/K11_runtime_proof.json
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def _no_network(*a, **k):
    raise OSError("network closed for the K11 runtime proof")


socket.socket.connect = _no_network  # type: ignore[assignment]

from brambleloop.agents.registry import PermissionDenied, Registry  # noqa: E402
from brambleloop.authority import dag, policy  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, JobStatus  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers the handlers
from brambleloop.runtime.worker import Worker  # noqa: E402


def drain(db, budget_s: float) -> dict:
    w = Worker(db, "k11-proof")
    t0, n = time.time(), 0
    while time.time() - t0 < budget_s and w.run_once():
        n += 1
    return {"runs": n, "completed": w.stats.completed, "denied": w.stats.denied,
            "failed": w.stats.failed, "seconds": round(time.time() - t0, 1)}


def main() -> None:
    tmp = tempfile.mkdtemp(prefix="k11-proof-")
    out: dict = {"phase": "shadow", "network": "closed", "db": "temp sqlite",
                 "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                          capture_output=True, text=True,
                                          cwd=ROOT).stdout.strip()}
    try:
        db = Database(f"sqlite:///{tmp}/p.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        dag.submit(db, key="proof:publish", department="store_commerce",
                   job_type="store.publish", submitted_by="laura",
                   title="publish the first certified release (seeded)")
        dag.submit(db, key="proof:promote", department="growth",
                   job_type="growth.distribution", submitted_by="laura",
                   depends_on=["proof:publish"], title="distribution plan after publishing")
        dag.submit(db, key="proof:seo", department="growth", job_type="seo.cycle",
                   submitted_by="laura", priority=5, title="independent SEO cycle")
        q = JobQueue(db)
        q.enqueue("coo", "autonomy.orchestrate", {"wake": "k11_proof"},
                  idempotency_key="k11-proof-1")
        out["run1"] = drain(db, 240)
        out["after_run1"] = {i["key"]: {"state": i["state"], "reason": i["reason"][:160],
                                        "job_id": i["job_id"], "evidence": i["evidence"]}
                             for i in dag.items(db) if i["key"].startswith("proof:")}
        out["dag_summary_run1"] = {k: v for k, v in dag.summary(db).items() if k != "items"}
        with db.session() as s:
            out["store_publish_jobs"] = s.query(Job).filter(
                Job.job_type == "store.publish").count()
        # authority refusals on the real registry
        reg = Registry(db)
        refusals = {}
        for agent, jt in (("pricing", "pricing.experiment"), ("orchestrator", "store.publish")):
            try:
                reg.authorize(agent, jt)
                refusals[f"{agent}:{jt}"] = "ALLOWED"
            except PermissionDenied as e:
                refusals[f"{agent}:{jt}"] = str(e)[:200]
        refusals["build_runtime:store_operator:store.publish"] = policy.check_dispatch(
            db, reg.get("store_operator"), "store.publish",
            env={"BRAMBLELOOP_RUNTIME_ROLE": "build"})
        try:
            policy.grant(db, agent="pricing", action_class="PUBLISH", granted_by="laura",
                         owner_decision_id="x", step_up_verified=True)
            refusals["laura_self_grant"] = "ALLOWED"
        except policy.AuthorityRefused as e:
            refusals["laura_self_grant"] = str(e)[:200]
        out["authority_refusals"] = refusals
        db.engine.dispose()

        # restart: new process state on the same rows; the independent job completes
        db2 = Database(f"sqlite:///{tmp}/p.sqlite")
        seo = next(i for i in dag.items(db2) if i["key"] == "proof:seo")
        out["seo_job_status_before_restart_tick"] = None
        if seo["job_id"]:
            with db2.session() as s:
                j = s.get(Job, seo["job_id"])
                out["seo_job_status_before_restart_tick"] = j.status.value
        JobQueue(db2).enqueue("coo", "autonomy.orchestrate", {"wake": "k11_proof_restart"},
                              idempotency_key="k11-proof-2")
        out["run2_after_restart"] = drain(db2, 240)
        out["after_restart"] = {i["key"]: {"state": i["state"], "reason": i["reason"][:160],
                                           "job_id": i["job_id"],
                                           "evidence": i["evidence"]}
                                for i in dag.items(db2) if i["key"].startswith("proof:")}
        out["dag_summary_after_restart"] = {k: v for k, v in dag.summary(db2).items()
                                            if k != "items"}
        with db2.session() as s:
            out["jobs_total"] = s.query(Job).count()
            out["jobs_dead"] = s.query(Job).filter(Job.status == JobStatus.DEAD).count()
            out["store_publish_jobs_final"] = s.query(Job).filter(
                Job.job_type == "store.publish").count()
        db2.engine.dispose()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    dest = ROOT / "research/final_build/w3/evidence/K11_runtime_proof.json"
    dest.write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
