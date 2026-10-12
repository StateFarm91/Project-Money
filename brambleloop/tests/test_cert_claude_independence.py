"""Claude-independence certification: the running company does not need this conversation.

Claude (in a coding session) builds and audits Brambleloop. It must not be the thing that
runs it. This suite proves that from the outside, with real OS processes:

* the production start command (`railway.json`: uvicorn `brambleloop.app.main:app`, whose
  startup hook starts the embedded worker and scheduler) is launched as a subprocess with a
  scrubbed environment -- no CLAUDE*/ANTHROPIC* variables, an empty HOME, a working directory
  outside the repository -- against a file-backed database;
* the chain runs by itself: scheduler tick -> durable queue -> worker claim -> permission
  layer -> handler -> follow-on jobs -> gates (capability refusals) and cost records -> audit
  rows linked to the job -> persisted state;
* the process is SIGKILLed mid-job (a platform eviction, no cleanup), a fresh process is
  started on the same database, and the orphaned work is reclaimed and finished by the new
  process -- nothing lost, no idempotency key duplicated, no cadence window scheduled twice;
* the split-service entry points (`scheduler_entry`, `worker_entry`) do the same job as
  separate processes, and the next cadence window is derived from durable state alone.

What this suite cannot do is restart the live Railway service: that disturbs production and
is the owner's to authorise. The production-side evidence is read-only (`runtime.started`
rows per boot, surfaced by /api/verify); the live restart drill is recorded as owner-gated
in research/BUILD2_CERTIFICATION.md rather than simulated here and called a pass.
"""
from __future__ import annotations

import ast
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, utcnow  # noqa: E402
from brambleloop.runtime.worker import CADENCES, Scheduler  # noqa: E402

PYTHON = str(ROOT / ".venv" / "bin" / "python")
if not Path(PYTHON).exists():  # pragma: no cover - fallback for a bare interpreter
    PYTHON = sys.executable
if not Path(PYTHON).exists() or "brambleloop" not in PYTHON:
    alt = Path("/home/user/Project-Money/brambleloop/.venv/bin/python")
    PYTHON = str(alt) if alt.exists() else sys.executable

RUNTIME_ROOTS = ("brambleloop.app.main", "brambleloop.app.runner",
                 "brambleloop.app.worker_entry", "brambleloop.app.scheduler_entry",
                 "brambleloop.runtime.worker", "brambleloop.runtime.pipeline",
                 "brambleloop.runtime.release")
# What a dependency on a Claude coding session would look like from inside the runtime.
SESSION_MARKERS = (".claude/", "claude.ai/code", "CLAUDE_", "HEARTBEAT_PROMPT",
                   "Claude-Session", "ops/lock")


def _scrubbed_env(url: str, home: str, **extra: str) -> dict:
    """Only what the container itself is given. Nothing from this session leaks through."""
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": home, "LANG": "C.UTF-8",
           "PYTHONPATH": str(SRC), "BRAMBLELOOP_DATABASE_URL": url,
           "BRAMBLELOOP_PHASE": "shadow", "BRAMBLELOOP_LOG_LEVEL": "WARNING",
           "PYTHONDONTWRITEBYTECODE": "1"}
    env.update(extra)
    for k in env:
        assert not k.upper().startswith(("CLAUDE", "ANTHROPIC")), k
    return env


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_web(url: str, tmp: str, port: int) -> subprocess.Popen:
    """The production start command, verbatim apart from host and port."""
    start = json.loads((ROOT / "railway.json").read_text())["deploy"]["startCommand"]
    assert start.startswith("uvicorn brambleloop.app.main:app"), start
    env = _scrubbed_env(url, tmp, BRAMBLELOOP_RUNNER_START_DELAY="0",
                        BRAMBLELOOP_SCHEDULER_INTERVAL="2", BRAMBLELOOP_IDLE_SLEEP="0.2")
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "brambleloop.app.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--workers", "1"],
        cwd=tmp, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _health(port: int, timeout: float = 90.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.5)
    return False


def _wait(pred, timeout: float, step: float = 1.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return False


def _wait_progressing(pred, progress, stall: float, cap: float, step: float = 1.0):
    """Wait for `pred` while the system keeps moving. A wall-clock deadline measures the
    host's load, not the product: under a loaded suite run the chain is merely slower. What
    must fail is a chain that STOPS -- no change in `progress()` for `stall` seconds -- or one
    that never arrives within the hard `cap`. Returns (reached, why)."""
    start = last_move = time.time()
    seen = progress()
    while time.time() - start < cap:
        if pred():
            return True, ""
        now = progress()
        if now != seen:
            seen, last_move = now, time.time()
        elif time.time() - last_move > stall:
            return False, f"stalled for {stall:.0f}s at {seen!r}"
        time.sleep(step)
    return False, f"still moving after the {cap:.0f}s cap; last {seen!r}"


def _aware(d):
    from datetime import timezone

    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _jobs(db: Database) -> list[Job]:
    with db.session() as s:
        return list(s.scalars(select(Job).order_by(Job.id)))


def _boots(db: Database) -> int:
    with db.session() as s:
        return s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "runtime.started")) or 0


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=15)


# ---- static: nothing in the runtime reaches for a coding session -----------------------------


def test_the_runtime_import_closure_names_no_claude_session_artefact():
    from brambleloop.build2 import reachability

    closure = set(reachability.reachable())
    assert set(RUNTIME_ROOTS) <= closure, sorted(set(RUNTIME_ROOTS) - closure)
    offenders = []
    for rel in sorted(closure):
        path = SRC / (rel.replace(".", "/") + ".py")
        if not path.exists():
            path = SRC / rel.replace(".", "/") / "__init__.py"
        text = path.read_text()
        tree = ast.parse(text)
        # String literals and imports only: a comment may cite CLAUDE.md as the rulebook.
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                hits = [m for m in SESSION_MARKERS if m in node.value]
                if hits and not (node.value.strip().startswith(("#", "\n")) or
                                 len(node.value) > 200):
                    offenders.append((rel, hits))
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                if any("claude_code" in n or "claude_agent_sdk" in n for n in names):
                    offenders.append((rel, names))
    assert not offenders, offenders
    assert len(closure) > 50, "the closure is suspiciously small; the scan proves nothing"


def test_the_deployed_image_and_start_command_carry_no_session_state():
    docker = (ROOT / "Dockerfile").read_text()
    assert ".claude" not in docker and "HEARTBEAT" not in docker
    copies = [ln.split()[1] for ln in docker.splitlines() if ln.startswith("COPY ")]
    # `release/` (A3-05) holds the tracked release records the runtime boot guard verifies
    # (brambleloop.ops.release_record): reviewed build evidence committed to the repository,
    # not state from any Claude session. It is admitted on that basis only, and the check
    # below keeps it so: nothing in it may reference a Claude session or its working files.
    assert set(copies) <= {"requirements.txt", "src", "release", "tests", "run_tests.sh"}, copies
    records = sorted(f for f in (ROOT / "release").rglob("*") if f.is_file())
    assert records, "the Dockerfile copies release/ but it holds no release record"
    for f in records:
        text = f.read_text(errors="replace").lower()
        for marker in (".claude", "claude.ai/code", "claude-session", "heartbeat"):
            assert marker not in text, (str(f), marker)
    deploy = json.loads((ROOT / "railway.json").read_text())["deploy"]
    assert "main:app" in deploy["startCommand"]
    assert deploy["restartPolicyType"] in ("ON_FAILURE", "ALWAYS")
    runner = (SRC / "brambleloop" / "app" / "runner.py").read_text()
    # The embedded worker and scheduler are on unless explicitly turned off.
    assert 'os.environ.get("BRAMBLELOOP_EMBEDDED_WORKER", "1") != "1"' in runner
    main = (SRC / "brambleloop" / "app" / "main.py").read_text()
    assert "runner.start(db)" in main


# ---- live processes: the chain, a kill, a restart --------------------------------------------


def test_production_start_command_runs_kills_and_resumes_without_this_session():
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/company.sqlite"
        db = Database(url)
        db.create_all()

        # ---- boot A: the runtime starts itself and does work nobody asked for by hand
        port = _free_port()
        a_started = utcnow()
        a = _start_web(url, tmp, port)
        try:
            assert _health(port), "the production start command never served /health"
            assert _wait(lambda: any(j.status is JobStatus.DONE for j in _jobs(db)), 120), \
                "worker A completed nothing"
            # Let the release chain run until it reaches the production gate: in shadow,
            # store.publish is refused by the capability layer. That refusal is the gate
            # doing its job, recorded on a real job the chain itself enqueued. Then catch
            # the worker mid-job for the kill.
            reached, why = _wait_progressing(
                lambda: any(j.job_type == "store.publish" and
                            (j.last_error or "").startswith("capability not enabled")
                            for j in _jobs(db)),
                lambda: sorted((j.job_type, str(j.status)) for j in _jobs(db)),
                stall=240, cap=1500)
            assert reached, "the chain never reached the publish gate: " + why
            _wait(lambda: any(j.status is JobStatus.RUNNING for j in _jobs(db)), 60, 0.2)
        finally:
            _kill(a)
        a_killed = utcnow()

        jobs = _jobs(db)
        name_a = f"web-{a.pid}"
        # A finished job's lease is cleared, so completion is attributed by time: nothing
        # else touched this database while boot A lived.
        _in_a = (lambda j: j.finished_at is not None
                 and a_started <= _aware(j.finished_at) <= a_killed)
        cadence_types = {jt for _n, _a, jt, _p in CADENCES}
        scheduled = {j.job_type for j in jobs if (j.idempotency_key or "").startswith("cadence:")}
        assert cadence_types <= scheduled, ("the embedded scheduler did not enqueue",
                                            sorted(cadence_types - scheduled))
        done_a = [j for j in jobs if j.status is JobStatus.DONE and _in_a(j)]
        assert done_a, "nothing completed under boot A's worker"
        follow_on = [j for j in jobs if not (j.idempotency_key or "").startswith(
            ("cadence:", "boot-"))]
        assert follow_on, "no handler enqueued follow-on work"
        with db.session() as s:
            linked = s.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.job_id.in_([j.id for j in done_a]))) or 0
            actors = set(s.scalars(select(AuditLog.actor).distinct()))
        assert linked > 0, "handlers ran but wrote no audit record linked to their job"
        assert len(actors) >= 3, actors
        # Gates and cost controls run inside the runtime: with no credentials in the container,
        # anything that would reach a paid or external capability is refused, and nothing costs.
        refused = [j for j in jobs if (j.last_error or "").startswith("capability not enabled")]
        assert refused and all(j.job_type == "store.publish" for j in refused), \
            [(j.job_type, (j.last_error or "")[:80]) for j in refused]
        assert all(j.status is JobStatus.DEAD for j in refused), "a refusal was retried"
        with db.session() as s:
            published = s.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "store.published")) or 0
            refusals = s.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "job.capability_not_enabled")) or 0
        assert published == 0 and refusals >= len(refused)
        assert sum(j.cost_cad or 0.0 for j in jobs) == 0.0
        assert _boots(db) == 1

        orphaned = [j for j in jobs if j.status is JobStatus.RUNNING]
        assert all(j.leased_by == name_a for j in orphaned), [j.leased_by for j in orphaned]
        before = {j.id: (j.job_type, j.idempotency_key, j.inputs) for j in jobs}
        cadence_keys_a = sorted(j.idempotency_key for j in jobs
                                if (j.idempotency_key or "").startswith("cadence:"))

        # A killed worker's lease is still live; time passes (deterministically, rather than
        # sleeping five minutes on the wall clock) and the lease expires.
        with db.session() as s:
            for j in orphaned:
                s.get(Job, j.id).lease_expires_at = utcnow() - timedelta(seconds=1)

        # ---- boot B: a fresh process on the same durable state
        port_b = _free_port()
        b_started = utcnow()
        b = _start_web(url, tmp, port_b)
        try:
            assert _health(port_b), "the restarted runtime never served /health"
            assert _wait(lambda: _boots(db) == 2, 30)
            ids = {j.id for j in orphaned}
            # Reclaimed: no orphan is left RUNNING under the dead process's lease, and each
            # has a new attempt that boot B started.
            assert _wait(lambda: all(
                j.leased_by != name_a and j.attempts >= 2
                for j in _jobs(db) if j.id in ids), 240), \
                "orphaned work was not reclaimed by the restarted worker"
            assert _wait(lambda: any(j.status is JobStatus.DONE and j.finished_at is not None
                                     and _aware(j.finished_at) >= b_started
                                     for j in _jobs(db)), 120), "worker B completed nothing"
        finally:
            _kill(b)

        after = {j.id: j for j in _jobs(db)}
        assert before, "boot A left no jobs: the identity checks below would be vacuous"
        assert cadence_keys_a, "boot A scheduled no cadence windows to check for duplicates"
        # Nothing lost: every job boot A knew about still exists with its identity intact.
        for jid, (jt, key, inputs) in before.items():
            assert jid in after, f"job {jid} ({jt}) vanished across the restart"
            assert (after[jid].job_type, after[jid].idempotency_key) == (jt, key)
            assert after[jid].inputs == inputs
        # Nothing duplicated: one row per idempotency key, and the restart's scheduler did not
        # re-enqueue a window boot A already had.
        keys = [j.idempotency_key for j in after.values() if j.idempotency_key]
        assert len(keys) == len(set(keys))
        for k in cadence_keys_a:
            assert sum(1 for j in after.values() if j.idempotency_key == k) == 1, k
        for j in orphaned:
            assert after[j.id].attempts >= 2, (j.job_type, after[j.id].attempts)

        # ---- the next window comes from durable state alone (no process remembers it)
        # Past the longest cadence period (30 days), so every window is a new one. A loop the
        # thrash breaker suspended (#34) is legitimately skipped and is excluded by name.
        horizon = utcnow() + timedelta(days=31)
        sched = Scheduler(db)
        fresh = sched.tick(horizon)
        expected = {n for n, _a, jt, _p in CADENCES if jt not in (sched.suspended or {})}
        assert set(fresh) >= expected, ("cadences did not continue", sorted(expected - set(fresh)))
        assert Scheduler(db).tick(horizon) == [], "a second scheduler duplicated the window"


def test_split_services_do_the_same_work_as_separate_processes():
    """worker_entry and scheduler_entry: the services Railway would run when split."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/split.sqlite"
        db = Database(url)
        db.create_all()
        sched = subprocess.run(
            [PYTHON, "-m", "brambleloop.app.scheduler_entry"], cwd=tmp, timeout=300,
            env=_scrubbed_env(url, tmp, BRAMBLELOOP_SCHEDULER_ONCE="1"),
            capture_output=True, text=True)
        assert sched.returncode == 0, sched.stderr[-2000:]
        queued = _jobs(db)
        assert {j.job_type for j in queued} >= {jt for _n, _a, jt, _p in CADENCES}
        work = subprocess.run(
            [PYTHON, "-m", "brambleloop.app.worker_entry"], cwd=tmp, timeout=600,
            env=_scrubbed_env(url, tmp, BRAMBLELOOP_MAX_SECONDS="45",
                              BRAMBLELOOP_WORKER_NAME="split-worker"),
            capture_output=True, text=True)
        assert work.returncode == 0, work.stderr[-2000:]
        done = [j for j in _jobs(db) if j.status is JobStatus.DONE]
        assert done, "the worker service completed nothing"
        assert not [j for j in _jobs(db) if j.status is JobStatus.RUNNING
                    and j.leased_by != "split-worker"]
        again = subprocess.run(
            [PYTHON, "-m", "brambleloop.app.scheduler_entry"], cwd=tmp, timeout=300,
            env=_scrubbed_env(url, tmp, BRAMBLELOOP_SCHEDULER_ONCE="1"),
            capture_output=True, text=True)
        assert again.returncode == 0
        keys = [j.idempotency_key for j in _jobs(db) if j.idempotency_key]
        assert len(keys) == len(set(keys)), "a second scheduler process duplicated work"


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:900]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
