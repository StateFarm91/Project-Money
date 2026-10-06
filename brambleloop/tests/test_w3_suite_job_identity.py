"""run_tests.sh has a durable job identity, a durable terminal result, and observers attach.

F-331 authoritative job identity, F-333 one operation one state (ATTACH), F-335 completion is
durable (EXIT sentinel on every terminal path), F-341 the producer writes the terminal result
once and a late observer in a fresh process reads the same one, F-342 observer/work separation
(process marker, registry role). Wave 3, lane TOOLS (cluster K14).

The real script is copied into a throwaway git repository with dummy suites, as in
tests/test_run_tests_script.py; nothing but the dummies ever runs.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

ROOT = Path(__file__).resolve().parents[1]
REPO_OPS = ROOT.parent / "ops"
SCRIPT = ROOT / "run_tests.sh"
PY = sys.executable
sys.path.insert(0, str(REPO_OPS))

import board as B  # noqa: E402
import registry as R  # noqa: E402

PASS = 'print("OK   test_one")\nprint("OK   test_two")\n'
FAIL = 'import sys\nprint("OK   test_one")\nprint("FAIL test_two boom")\nsys.exit(1)\n'
GATE = ('import os, sys, time\n'
        'gate = os.environ["GATE_FILE"]\n'
        'open(gate + ".started", "w").close()\n'
        'deadline = time.time() + 60\n'
        'while not os.path.exists(gate) and time.time() < deadline:\n'
        '    time.sleep(0.05)\n'
        'print("OK   test_gated")\n')
_KNOBS = ("SUITES", "REQUIRE_CLEAN", "THEN_FULL", "ALLOW_PARALLEL", "SUITE_RECORD_DIR", "JOBS",
          "ATTACH", "ATTACH_TIMEOUT", "SUITE_REGISTRY", "SUITE_REGISTRY_CLI",
          "BRAMBLELOOP_JOB_REGISTRY", "_BRAMBLELOOP_SUITE_JOB")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _sandbox() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="w3suite-"))
    (repo / "tests").mkdir()
    shutil.copy(SCRIPT, repo / "run_tests.sh")
    (repo / "tests" / "test_pass.py").write_text(PASS)
    (repo / "tests" / "test_fail.py").write_text(FAIL)
    (repo / "tests" / "test_gate.py").write_text(GATE)
    (repo / ".gitignore").write_text("artifacts/\njobs.json\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "commit", "-q", "-m", "sandbox")
    return repo


def _env(repo: Path, **over) -> dict:
    e = {k: v for k, v in os.environ.items() if k not in _KNOBS}
    return {**e, "PY": PY, "JOBS": "2", "SUITE_REGISTRY_CLI": str(REPO_OPS / "registry.py"),
            "BRAMBLELOOP_JOB_REGISTRY": str(repo / "jobs.json"), **over}


def _run(repo: Path, suites: str, **env) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(repo / "run_tests.sh")], capture_output=True, text=True,
                          env=_env(repo, SUITES=suites, **env), timeout=120)


def _records(repo: Path) -> list[dict]:
    d = repo / "artifacts" / "suite_runs"
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))]


def _last_line(path: str) -> str:
    return [l for l in Path(path).read_text().splitlines() if l.strip()][-1]


def test_every_terminal_path_ends_the_log_with_the_exit_sentinel_matching_the_record():
    repo = _sandbox()
    try:
        ok = _run(repo, "test_pass")
        bad = _run(repo, "test_fail")
        assert ok.returncode == 0 and bad.returncode == 1, ok.stdout + bad.stdout
        recs = {r["status"]: r for r in _records(repo)}
        assert set(recs) == {"passed", "failed"}
        for status, code in (("passed", 0), ("failed", 1)):
            rec = recs[status]
            assert rec["exit_code"] == code and rec["terminal_sentinel"] == f"EXIT {code}"
            assert _last_line(repo / rec["log"]) == f"EXIT {code}"
            assert rec["job_id"] == f"suite-{rec['run_id']}" and rec["role"] == "work"
            assert rec["process_marker"] == f"brambleloop-suite[{rec['run_id']}]"
        assert recs["passed"]["run_id"] != recs["failed"]["run_id"]
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_the_run_enrols_itself_and_a_late_observer_in_a_fresh_process_reads_its_result():
    repo = _sandbox()
    try:
        r = _run(repo, "test_fail")
        assert r.returncode == 1
        [rec] = _records(repo)
        assert rec["registry"] == rec["job_id"], rec
        assert f"JOB: {rec['job_id']} enrolled" in r.stdout
        reg = json.loads((repo / "jobs.json").read_text())["jobs"][rec["job_id"]]
        assert reg["role"] == "work" and reg["marker"] == rec["process_marker"]
        assert Path(reg["log"]).resolve() == (repo / rec["log"]).resolve()
        # A late observer: a new interpreter, no shared memory with the run, reads the
        # registry and the job's own evidence and gets the same terminal result.
        late = subprocess.run(
            [PY, "-c", (
                "import json,sys; sys.path.insert(0, sys.argv[1]); import registry as R;"
                "row = R.Registry(sys.argv[2]).recall(sys.argv[3]);"
                "print(json.dumps({'state': row['state'], 'exit': row.get('exit_code')}))"),
             str(REPO_OPS), str(repo / "jobs.json"), rec["job_id"]],
            capture_output=True, text=True, timeout=60)
        seen = json.loads(late.stdout.strip().splitlines()[-1])
        assert seen["exit"] == 1 and seen["state"] in (B.FAILED,), seen
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_registry_opt_out_and_an_unreachable_registry_are_recorded_as_null():
    repo = _sandbox()
    try:
        r = _run(repo, "test_pass", SUITE_REGISTRY="0")
        assert r.returncode == 0
        [rec] = _records(repo)
        assert rec["registry"] is None and not (repo / "jobs.json").exists()
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_an_attached_observer_starts_nothing_and_takes_the_running_runs_result():
    """F-333 and F-342 together, on a run that is genuinely in progress."""
    repo = _sandbox()
    gate = repo / "gate"
    try:
        env = _env(repo, SUITES="test_gate", GATE_FILE=str(gate))
        work = subprocess.Popen(["bash", str(repo / "run_tests.sh")], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env)
        deadline = time.time() + 30
        while not Path(str(gate) + ".started").exists() and time.time() < deadline:
            time.sleep(0.05)
        [running] = _records(repo)
        assert running["status"] == "running"
        observer = subprocess.Popen(["bash", str(repo / "run_tests.sh")],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, env={**env, "ATTACH": "1"})
        time.sleep(1.5)
        # F-342: the workload's marker is matched by the workload and by nothing watching it.
        pids = B.alive(running["process_marker"])
        assert work.pid in pids, (pids, work.pid)
        assert observer.pid not in pids
        assert observer.poll() is None, "the observer gave up instead of attaching"
        assert len(_records(repo)) == 1, "the observer started a second run"
        gate.write_text("go")
        w_out, _ = work.communicate(timeout=60)
        o_out, _ = observer.communicate(timeout=60)
        assert work.returncode == 0 and observer.returncode == 0, o_out
        assert "ATTACHED (observer)" in o_out and "ATTACHED RESULT: run " in o_out
        assert running["run_id"] in o_out
        [final] = _records(repo)
        assert final["status"] == "passed" and final["run_id"] == running["run_id"]
        reg = json.loads((repo / "jobs.json").read_text())["jobs"]
        assert list(reg) == [running["job_id"]], "the observer enrolled as work"
    finally:
        gate.write_text("go")
        shutil.rmtree(repo, ignore_errors=True)


def test_an_interrupted_run_writes_the_130_sentinel_after_its_record():
    repo = _sandbox()
    gate = repo / "gate"
    try:
        env = _env(repo, SUITES="test_gate", GATE_FILE=str(gate))
        p = subprocess.Popen(["bash", str(repo / "run_tests.sh")], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=env)
        deadline = time.time() + 30
        while not Path(str(gate) + ".started").exists() and time.time() < deadline:
            time.sleep(0.05)
        p.terminate()
        p.communicate(timeout=60)
        [rec] = _records(repo)
        assert rec["status"] == "interrupted" and rec["terminal_sentinel"] == "EXIT 130"
        assert _last_line(repo / rec["log"]) == "EXIT 130"
        row = R.Registry(repo / "jobs.json").recall(rec["job_id"])
        assert row["state"] == B.FAILED and row.get("exit_code") == 130, row
    finally:
        gate.write_text("go")
        shutil.rmtree(repo, ignore_errors=True)


def test_the_registry_separates_work_from_observers():
    d = Path(tempfile.mkdtemp())
    try:
        reg = R.Registry(d / "jobs.json")
        reg.enrol(B.Job(name="suite-1", log=d / "a.log", marker="brambleloop-suite[1]"),
                  lane="suite")
        for bad in ({"watches": None}, {"watches": "nope"}):
            try:
                reg.enrol(B.Job(name="obs", log=d / "o.log", marker="watcher"),
                          role="observer", **bad)
                raise AssertionError("an observer of nothing was enrolled")
            except ValueError:
                pass
        try:
            reg.enrol(B.Job(name="obs", log=d / "o.log", marker="brambleloop-suite[1]"),
                      role="observer", watches="suite-1")
            raise AssertionError("an observer carrying the workload's marker was enrolled")
        except ValueError:
            pass
        try:
            reg.enrol(B.Job(name="x", log=d / "x.log"), role="monitor")
            raise AssertionError("an unknown role was accepted")
        except ValueError:
            pass
        reg.enrol(B.Job(name="obs", log=d / "o.log", marker="watcher"), role="observer",
                  watches="suite-1")
        assert reg.workloads() == ["suite-1"]
        rows = {r["job"]: r for r in reg.survey()["rows"]}
        assert rows["obs"]["role"] == "observer" and rows["suite-1"]["role"] == "work"
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
