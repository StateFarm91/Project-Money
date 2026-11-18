"""WS4-7 cost evidence: resident memory and CPU of the two processes Mode T requires.

Runs, against a throwaway local PostgreSQL cluster under the owner runbook's roles:

* the policy-issuer service (`python -m brambleloop.app.issuer_entry`) as `bl_issuer`, with a
  short pass interval and grant requests arriving (each answered: Mode S, so refused), and
* the separate worker service (`python -m brambleloop.app.worker_entry`) as `bl_worker`, fed a
  `plan.cycle` every few minutes -- the full offline pipeline the suite drives (radar, CIR draft
  and compile, certification, listing draft with image rendering, publish refused in SHADOW).

No provider key, no network call, no spend: SHADOW with no credentials. Samples VmRSS of each
process tree every 5 s and CPU time from /proc, then prints JSON.

Run: cd brambleloop && PYTHONPATH=src:tests python3 scripts/ws4_7_measure_rss.py [seconds]
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, os.path.join(HERE, "..", "tests"))

import _tmp; _tmp.install()  # noqa: E402,E702

from sqlalchemy import text  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.ops import standing_grants as SG  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from test_ws4_7_postgres import _cluster  # noqa: E402

CLK = os.sysconf("SC_CLK_TCK")


def _tree(pid: int) -> list[int]:
    out, todo = [], [pid]
    while todo:
        p = todo.pop()
        out.append(p)
        try:
            with open(f"/proc/{p}/task/{p}/children") as fh:
                todo += [int(x) for x in fh.read().split()]
        except OSError:
            pass
    return out


def _rss_kib(pid: int) -> int:
    total = 0
    for p in _tree(pid):
        try:
            with open(f"/proc/{p}/status") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        total += int(line.split()[1])
        except OSError:
            pass
    return total


def _cpu_s(pid: int) -> float:
    total = 0.0
    for p in _tree(pid):
        try:
            with open(f"/proc/{p}/stat") as fh:
                f = fh.read().rsplit(")", 1)[1].split()
            total += (int(f[11]) + int(f[12]) + int(f[13]) + int(f[14])) / CLK
        except (OSError, IndexError, ValueError):
            pass
    return total


def main(seconds: int) -> dict:
    with _cluster() as (url, bindir):
        admin_url = url.format(user="postgres", db="postgres")
        from sqlalchemy import create_engine

        eng = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with eng.connect() as c:
            c.execute(text("CREATE DATABASE ws47_cost"))
        eng.dispose()
        owner = Database(url.format(user="postgres", db="ws47_cost"))
        owner.create_all()
        with owner.engine.begin() as c:
            for stmt in SG.runbook_sql("postgres", "x", "y"):
                c.execute(text(stmt))
        keys = sp.generate_keypairs()
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("BRAMBLELOOP_", "DATABASE_URL", "ETSY_"))}
        base["PYTHONPATH"] = os.pathsep.join([os.path.join(HERE, "..", "src"),
                                              os.path.join(HERE, "..", "tests")])
        issuer_env = dict(base, BRAMBLELOOP_DATABASE_URL=url.format(user="bl_issuer",
                                                                     db="ws47_cost"),
                          BRAMBLELOOP_EMBEDDED_WORKER="0", BRAMBLELOOP_ISSUER_INTERVAL="10",
                          **{sp.ISSUER_KEY_VAR: keys[sp.ISSUER_KEY_VAR],
                             sp.ISSUER_VERIFY_KEY_VAR: keys[sp.ISSUER_VERIFY_KEY_VAR]})
        worker_env = dict(base, BRAMBLELOOP_DATABASE_URL=url.format(user="bl_worker",
                                                                     db="ws47_cost"),
                          BRAMBLELOOP_EMBEDDED_WORKER="0",
                          **{sp.ISSUER_VERIFY_KEY_VAR: keys[sp.ISSUER_VERIFY_KEY_VAR],
                             sp.VERIFY_KEY_VAR: keys[sp.VERIFY_KEY_VAR]})
        logdir = os.environ.get("WS47_LOGDIR") or os.environ.get("TMPDIR", "/tmp")
        logs = {n: open(os.path.join(logdir, f"ws47_{n}.log"), "w")
                for n in ("issuer", "worker")}
        procs = {
            "issuer": subprocess.Popen([sys.executable, "-m", "brambleloop.app.issuer_entry"],
                                       env=issuer_env, stdout=logs["issuer"],
                                       stderr=subprocess.STDOUT),
            "worker": subprocess.Popen([sys.executable, "-m", "brambleloop.app.worker_entry"],
                                       env=worker_env, stdout=logs["worker"],
                                       stderr=subprocess.STDOUT),
        }
        samples = {n: [] for n in procs}
        cpu0 = {}
        start = time.monotonic()
        cycle, req = 0, 0
        try:
            while time.monotonic() - start < seconds:
                t = time.monotonic() - start
                if t >= cycle * 180:                     # a plan.cycle every 3 minutes
                    JobQueue(owner).enqueue("orchestrator", "plan.cycle",
                                            {"as_of": f"2026-11-{18 + cycle % 10:02d}"})
                    cycle += 1
                if t >= req * 30:                        # a grant request every 30 s
                    SG.request_grant(owner, slug=f"measure-{req}", version="1.0.0",
                                     release="a" * 64, job_id=req + 1)
                    req += 1
                for n, p in procs.items():
                    if p.poll() is not None:
                        raise RuntimeError(f"{n} exited early ({p.returncode})")
                    if n not in cpu0 and t >= 60:
                        cpu0[n] = (_cpu_s(p.pid), t)
                    samples[n].append((round(t, 1), _rss_kib(p.pid)))
                time.sleep(5)
            cpu = {n: (_cpu_s(p.pid) - cpu0[n][0]) / (time.monotonic() - start - cpu0[n][1])
                   for n, p in procs.items()}
        finally:
            for p in procs.values():
                p.terminate()
            for p in procs.values():
                try:
                    p.wait(30)
                except subprocess.TimeoutExpired:
                    p.kill()
        with owner.session() as s:
            jobs = dict(s.execute(text(
                "SELECT status, count(*) FROM jobs GROUP BY status")).all())
            types = s.execute(text("SELECT count(DISTINCT job_type) FROM jobs")).scalar()
            held = s.execute(text("SELECT count(*) FROM audit_log WHERE action = :a"),
                             {"a": SG.HELD}).scalar()
            by_type = [tuple(r) for r in s.execute(text(
                "SELECT job_type, status, count(*) FROM jobs GROUP BY job_type, status "
                "ORDER BY 1, 2"))]
            errors = [tuple(r) for r in s.execute(text(
                "SELECT job_type, left(last_error, 160) FROM jobs WHERE last_error IS NOT NULL "
                "AND last_error <> '' LIMIT 8"))]
        out = {"seconds": seconds, "plan_cycles": cycle, "grant_requests": req,
               "grant_requests_answered_held": held, "jobs_by_status": jobs,
               "distinct_job_types": types, "jobs_by_type": by_type, "job_errors": errors}
        for n, rows in samples.items():
            mib = [k / 1024 for _t, k in rows]
            steady = [k / 1024 for t, k in rows if t >= seconds / 2]
            out[n] = {"peak_rss_mib": round(max(mib), 1),
                      "steady_rss_mib_median_2nd_half": round(statistics.median(steady), 1),
                      "avg_vcpu_after_60s": round(cpu[n], 4), "samples": len(rows)}
        return out


if __name__ == "__main__":
    print(json.dumps(main(int(sys.argv[1]) if len(sys.argv) > 1 else 660), indent=2,
                     default=str))
