"""Runtime proof for Laura's executive layer: the real embedded runner, SHADOW, temp SQLite.

    python -m brambleloop.laura.executive.proof --seconds 600 --out D_runtime_proof.json

Reuses `autonomy.proof`'s isolated child (no credentials, every HTTP(S) proxy pointed at a
closed port, BRAMBLELOOP_PHASE=shadow, nothing enqueued by this script after boot) and adds
what Laura did: every executive tick with its honest useful/no-op verdict, her priorities,
her decisions by kind, the review verdicts of what she delegated, and the protected-job and
spend counts. A bounded window, not a soak.
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

from ...autonomy import proof as base


def laura_section(db) -> dict:
    from sqlalchemy import select

    from ...autonomy import charters
    from ...core.models import Job, JobStatus
    from ...runtime.pipeline import did_no_work
    from .. import identity
    from . import loop

    with db.session() as s:
        ticks = list(s.execute(select(Job.id, Job.status, Job.inputs, Job.outputs,
                                      Job.started_at, Job.finished_at, Job.last_error)
                               .where(Job.job_type == loop.EXEC_JOB).order_by(Job.id)).all())
        delegated = [(j.id, j.job_type, j.status) for j in s.execute(
            select(Job.id, Job.job_type, Job.status, Job.inputs)).all()
            if (j.inputs or {}).get("laura")]
    rows = []
    for t in ticks:
        st = getattr(t.status, "value", str(t.status))
        out = t.outputs or {}
        rows.append({"job_id": t.id, "status": st,
                     "trigger": (t.inputs or {}).get("wake") or (t.inputs or {}).get("cadence"),
                     "finished": t.finished_at.isoformat() if t.finished_at else None,
                     "work_done": out.get("work_done"),
                     "verdict": ("useful" if st == "done" and not did_no_work(out, loop.EXEC_JOB)
                                 else "noop" if st == "done" else st),
                     "decisions_by_kind": out.get("decisions_by_kind"),
                     "delegated": out.get("delegated"), "reviewed": out.get("reviewed"),
                     "idle": out.get("idle"), "error": (t.last_error or "")[:200]})
        coo = [{"id": j.id, "status": getattr(j.status, "value", str(j.status)),
                "created": j.created_at.isoformat() if j.created_at else None,
                "run_after": j.run_after.isoformat() if j.run_after else None,
                "started": j.started_at.isoformat() if j.started_at else None,
                "attempts": j.attempts, "error": (j.last_error or "")[:200]}
               for j in s.scalars(select(Job).where(Job.job_type == "autonomy.orchestrate"))]
        running = [{"id": j.id, "job_type": j.job_type,
                    "started": j.started_at.isoformat() if j.started_at else None}
                   for j in s.scalars(select(Job).where(Job.status == JobStatus.RUNNING))]
    summ = loop.summary(db)
    return {
        "identity": identity.summary(db),
        "coo_orchestrate_jobs": coo,
        "running_at_end": running,
        "ticks": rows,
        "ticks_total": len(rows),
        "ticks_useful": sum(r["verdict"] == "useful" for r in rows),
        "ticks_noop": sum(r["verdict"] == "noop" for r in rows),
        "ticks_failed_or_open": sum(r["verdict"] not in ("useful", "noop") for r in rows),
        "decisions_by_kind": summ.get("decisions_by_kind"),
        "delegation_review_outcomes": summ.get("delegation_outcomes"),
        "open_priorities": summ.get("items"),
        "recent_decisions": loop.history(db, limit=40),
        "delegated_jobs": [{"id": i, "job_type": jt, "status": getattr(st, "value", str(st))}
                           for i, jt, st in delegated],
        "delegated_protected": [jt for _i, jt, _s in delegated
                                if jt in charters.PROTECTED_JOB_TYPES],
        "delegated_outside_safe": [jt for _i, jt, _s in delegated
                                   if jt not in charters.SAFE_GENERATED],
    }


def child() -> int:
    seconds = int(os.environ["BRAMBLELOOP_PROOF_SECONDS"])
    out = Path(os.environ["BRAMBLELOOP_PROOF_OUT"])
    from ...agents.registry import Registry
    from ...app import runner
    from ...core.db import Database

    db = Database(f"sqlite:///{os.environ['BRAMBLELOOP_PROOF_DB']}")
    db.create_all()
    Registry(db).seed_defaults()
    started = datetime.now(timezone.utc)
    runner.start(db)
    samples = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        time.sleep(min(30, max(1, seconds - (time.monotonic() - t0))))
        st = runner.STATE.to_dict()
        samples.append({"at": datetime.now(timezone.utc).isoformat(),
                        "jobs": base._counts(db), "worker_alive": st["worker_alive"],
                        "scheduler_last_tick": st["scheduler_last_tick"],
                        "worker_restarts": st["worker_restarts"]})
    runner.stop(timeout=60)
    finished = datetime.now(timezone.utc)
    report = base.collect(db, started, finished, samples)
    report["kind"] = ("W3 lane D runtime proof: Laura's executive tick inside the embedded "
                      "runner, shadow, temp SQLite, closed network")
    for k in ("missions", "timeline_head"):          # keep the evidence file small
        report[k] = report[k][:40] if isinstance(report.get(k), list) else report.get(k)
    report["laura"] = laura_section(db)
    out.write_text(json.dumps(report, indent=1, default=str) + "\n")
    return 0


def main(argv: list[str]) -> int:
    if "--child" in argv:
        return child()
    seconds = int(argv[argv.index("--seconds") + 1]) if "--seconds" in argv else 600
    out = Path(argv[argv.index("--out") + 1]).resolve() if "--out" in argv else \
        Path("D_runtime_proof.json").resolve()
    src = str(Path(__file__).resolve().parents[3])
    with tempfile.TemporaryDirectory(prefix="bl-laura-proof-") as tmp:
        env = base._child_env(src, seconds, f"{tmp}/proof.sqlite", str(out))
        env["BRAMBLELOOP_PROOF_COMMIT"] = base._commit()
        proc = subprocess.run([sys.executable, "-m", "brambleloop.laura.executive.proof",
                               "--child"], env=env, cwd=tmp, timeout=seconds + 900)
        return proc.returncode


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
