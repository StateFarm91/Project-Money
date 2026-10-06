"""Runtime proof: the real embedded runner (worker pool + scheduler) in-process, SHADOW phase,
against a throwaway SQLite file, for a bounded wall-clock window.

    python -m brambleloop.autonomy.proof --seconds 900 --out evidence.json

The parent process launches a child with a MINIMAL environment: no provider keys, no cloud
credentials, BRAMBLELOOP_PHASE=shadow, and every HTTP(S) proxy pointed at a closed local port,
so nothing in the run can reach the network or spend money. What the child records is what
the runtime did by itself: nothing is enqueued by this script after boot.

This is a short in-process run, not the 24-hour lights-out soak (§95/§16); it says so in its
own output.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

CLOSED_PROXY = "http://127.0.0.1:9"


def _child_env(src: str, seconds: int, db_path: str, out: str) -> dict:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": os.environ.get("HOME", "/tmp"),
           "PYTHONPATH": src,
           "BRAMBLELOOP_PHASE": "shadow",
           "BRAMBLELOOP_RUNNER_START_DELAY": "0",
           "BRAMBLELOOP_SCHEDULER_INTERVAL": "20",
           "BRAMBLELOOP_IDLE_SLEEP": "0.5",
           "BRAMBLELOOP_WORKER_NAME": "proof-runner",
           "BRAMBLELOOP_PROOF_SECONDS": str(seconds),
           "BRAMBLELOOP_PROOF_DB": db_path,
           "BRAMBLELOOP_PROOF_OUT": out,
           "HTTP_PROXY": CLOSED_PROXY, "HTTPS_PROXY": CLOSED_PROXY,
           "http_proxy": CLOSED_PROXY, "https_proxy": CLOSED_PROXY,
           "NO_PROXY": "", "no_proxy": ""}
    return env


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _counts(db) -> dict:
    from sqlalchemy import func, select

    from ..core.models import Job

    with db.session() as s:
        rows = s.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    return {getattr(k, "value", str(k)): int(n) for k, n in rows}


def child() -> int:
    seconds = int(os.environ["BRAMBLELOOP_PROOF_SECONDS"])
    out = Path(os.environ["BRAMBLELOOP_PROOF_OUT"])
    from ..agents.registry import Registry
    from ..core.db import Database

    db = Database(f"sqlite:///{os.environ['BRAMBLELOOP_PROOF_DB']}")
    db.create_all()
    Registry(db).seed_defaults()
    from ..app import runner

    started = datetime.now(timezone.utc)
    runner.start(db)
    samples = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        time.sleep(min(30, max(1, seconds - (time.monotonic() - t0))))
        st = runner.STATE.to_dict()
        samples.append({"at": datetime.now(timezone.utc).isoformat(), "jobs": _counts(db),
                        "worker_alive": st["worker_alive"],
                        "scheduler_last_tick": st["scheduler_last_tick"],
                        "worker_restarts": st["worker_restarts"],
                        "last_enqueued": st["scheduler_last_enqueued"][:20]})
    runner.stop(timeout=60)
    finished = datetime.now(timezone.utc)
    out.write_text(json.dumps(collect(db, started, finished, samples), indent=1,
                              default=str) + "\n")
    return 0


def collect(db, started, finished, samples) -> dict:
    from sqlalchemy import func, select

    from ..core.models import CostEntry, Job, OwnerAction
    from ..queue.durable import classify_dead_letter
    from . import charters, memory, status
    from .kpis import did_no_work, job_department

    with db.session() as s:
        jobs = list(s.execute(select(Job.id, Job.agent, Job.job_type, Job.status, Job.inputs,
                                     Job.outputs, Job.last_error, Job.attempts)).all())
        cost_n, cost_sum = s.execute(select(func.count(), func.coalesce(
            func.sum(CostEntry.amount_cad), 0.0))).one()
        owner_actions = s.scalar(select(func.count()).select_from(OwnerAction)) or 0
    by_type: dict[str, dict] = {}
    by_dept: dict[str, dict] = {}
    generated: dict[str, dict] = {}
    dead = []
    for j in jobs:
        st = getattr(j.status, "value", str(j.status))
        by_type.setdefault(j.job_type, {}).setdefault(st, 0)
        by_type[j.job_type][st] += 1
        d = job_department(j.job_type, j.inputs) or "unassigned"
        e = by_dept.setdefault(d, {"total": 0, "done": 0, "useful": 0, "dead": 0})
        e["total"] += 1
        e["done"] += st == "done"
        e["dead"] += st == "dead"
        e["useful"] += st == "done" and not did_no_work(j.outputs)
        if (j.inputs or {}).get("source") == "autonomy":
            g = generated.setdefault(d, {"jobs": [], "useful": 0})
            g["jobs"].append({"id": j.id, "job_type": j.job_type, "status": st,
                              "reason": (j.inputs or {}).get("reason", "")[:160]})
            g["useful"] += st == "done" and not did_no_work(j.outputs)
        if st == "dead":
            dead.append({"id": j.id, "job_type": j.job_type,
                         "class": classify_dead_letter(j.job_type, j.last_error or ""),
                         "error": (j.last_error or "").splitlines()[0][:200]
                         if j.last_error else ""})
    orch = [{"id": j.id, "status": getattr(j.status, "value", ""),
             "wake": (j.inputs or {}).get("wake") or (j.inputs or {}).get("cadence"),
             "enqueued": (j.outputs or {}).get("enqueued"),
             "states": (j.outputs or {}).get("states")}
            for j in jobs if j.job_type == "autonomy.orchestrate"]
    protected_any = {jt: by_type[jt] for jt in charters.PROTECTED_JOB_TYPES if jt in by_type}
    protected_generated = [x for d in generated.values() for x in d["jobs"]
                           if x["job_type"] in charters.PROTECTED_JOB_TYPES]
    return {
        "kind": "lane A runtime proof: embedded runner in-process, shadow, temp SQLite",
        "not_a_soak": ("bounded wall-clock window; it proves the hosted loop generates and "
                       "executes work by itself, not 24 h of uptime (§95 lights-out remains "
                       "an open certification gate)"),
        "started": started.isoformat(), "finished": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 1),
        "commit": os.environ.get("BRAMBLELOOP_PROOF_COMMIT", "unknown"),
        "environment": {"phase": os.environ.get("BRAMBLELOOP_PHASE"),
                        "network": f"all HTTP(S) proxies -> {CLOSED_PROXY} (closed)",
                        "credentials": "none: child env is PATH/HOME/PYTHONPATH + "
                                       "BRAMBLELOOP_* only",
                        "human_or_session_enqueues_after_boot": 0},
        "samples": samples,
        "jobs_total": len(jobs),
        "jobs_by_department": by_dept,
        "jobs_by_type": by_type,
        "orchestrator_runs": orch,
        "generated_by_orchestrator": generated,
        "missions": memory.recall(db, kind="mission", limit=500),
        "kpi_snapshots": [m["key"] for m in memory.recall(db, kind="kpi_snapshot",
                                                          limit=200)],
        "morning_briefs": [m["key"] for m in memory.recall(db, kind="morning_brief",
                                                           limit=10)],
        "dead_letters": dead,
        "protected_job_types_seen": protected_any,
        "protected_generated_by_orchestrator": protected_generated,
        "owner_actions": owner_actions,
        "spend": {"rows": int(cost_n), "amount_cad": float(cost_sum),
                  "basis": "measured" if cost_n else "no cost_entries rows"},
        "status_summary": status.summary(db, now=finished),
        "timeline_head": status.timeline(db, limit=40, now=finished)["items"],
    }


def main(argv: list[str]) -> int:
    if "--child" in argv:
        return child()
    seconds = int(argv[argv.index("--seconds") + 1]) if "--seconds" in argv else 600
    out = Path(argv[argv.index("--out") + 1]).resolve() if "--out" in argv else \
        Path("A_runtime_proof.json").resolve()
    src = str(Path(__file__).resolve().parents[2])
    with tempfile.TemporaryDirectory(prefix="bl-proof-") as tmp:
        env = _child_env(src, seconds, f"{tmp}/proof.sqlite", str(out))
        env["BRAMBLELOOP_PROOF_COMMIT"] = _commit()
        proc = subprocess.run([sys.executable, "-m", "brambleloop.autonomy.proof", "--child"],
                              env=env, cwd=tmp, timeout=seconds + 900)
        return proc.returncode


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
