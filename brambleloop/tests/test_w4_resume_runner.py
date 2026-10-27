"""W4-B1: run_tests.sh checkpoints each suite, resumes a killed run, refuses a mismatched
resume, and shards deterministically.

The real script and the real checkpoint tool are copied byte for byte into a throwaway git
repository whose `tests/` holds tiny dummy suites (the pattern of test_run_tests_script.py), so
the property under test -- the runner's behaviour across a kill -- is observed without running
the real suite. Every run uses the SUITES filter.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

# Counts its own executions, so "a passing suite is not re-run on resume" is observable.
COUNTED = ('import os\n'
           'p = os.environ["COUNT_DIR"] + "/pass"\n'
           'open(p, "a").write("x")\n'
           'print("OK   test_counted")\n')
FAIL = 'import sys\nprint("OK   test_one")\nprint("FAIL test_two boom")\nsys.exit(1)\n'
GATE = ('import os, sys, time\n'
        'gate = os.environ["GATE_FILE"]\n'
        'open(gate + ".started", "w").close()\n'
        'deadline = time.time() + 60\n'
        'while not os.path.exists(gate) and time.time() < deadline:\n'
        '    time.sleep(0.05)\n'
        'print("OK   test_gated")\n')
_KNOBS = ("SUITES", "REQUIRE_CLEAN", "THEN_FULL", "ALLOW_PARALLEL", "SUITE_RECORD_DIR", "JOBS",
          "RESUME", "SHARD", "CHECKPOINT", "CHECKPOINT_TOOL")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _sandbox() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="resume-"))
    (repo / "tests").mkdir()
    (repo / "scripts").mkdir()
    shutil.copy(ROOT / "run_tests.sh", repo / "run_tests.sh")
    shutil.copy(ROOT / "scripts" / "suite_checkpoint.py", repo / "scripts" / "suite_checkpoint.py")
    (repo / "tests" / "test_counted.py").write_text(COUNTED)
    (repo / "tests" / "test_fail.py").write_text(FAIL)
    (repo / "tests" / "test_gate.py").write_text(GATE)
    for i in range(8):
        (repo / "tests" / f"test_s{i}.py").write_text(f'print("OK   test_s{i}")\n')
    (repo / "requirements.lock").write_text("fixture==1.0\n")
    (repo / ".gitignore").write_text("artifacts/\ncount/\ngate*\n")
    (repo / "count").mkdir()
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "commit", "-q", "-m", "sandbox")
    return repo


def _env(repo: Path, **over) -> dict:
    e = {k: v for k, v in os.environ.items() if k not in _KNOBS}
    return {**e, "PY": PY, "JOBS": "2", "SUITE_REGISTRY": "0",
            "COUNT_DIR": str(repo / "count"), "GATE_FILE": str(repo / "gate"), **over}


def _run(repo: Path, **env) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(repo / "run_tests.sh")], capture_output=True, text=True,
                          env=_env(repo, **env), timeout=120, cwd=repo)


def _record(repo: Path) -> dict:
    [rec] = [json.loads(p.read_text())
             for p in sorted((repo / "artifacts" / "suite_runs").glob("*.json"))]
    return rec


def _killed_run(repo: Path) -> str:
    """Start a checkpointed run, let the counted suite finish, then SIGKILL the whole run
    while the gate suite is mid-run -- what a container restart does. Returns the run id."""
    p = subprocess.Popen(["bash", str(repo / "run_tests.sh")], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, cwd=repo, start_new_session=True,
                         env=_env(repo, SUITES="test_counted,test_gate", CHECKPOINT="1"))
    deadline = time.time() + 60
    ck = repo / "artifacts" / "suite_runs"
    while time.time() < deadline:
        done = list(ck.glob("*/tests_test_counted.py.json"))
        if (Path(str(repo / "gate") + ".started").exists() and done
                and json.loads(done[0].read_text()).get("status") == "passed"):
            break
        time.sleep(0.05)
    else:
        os.killpg(p.pid, signal.SIGKILL)
        raise AssertionError("the run never reached the kill point")
    os.killpg(p.pid, signal.SIGKILL)
    p.communicate(timeout=30)
    return _record(repo)["run_id"]


def test_resume_after_a_kill_reruns_only_what_did_not_pass_and_the_record_is_complete():
    repo = _sandbox()
    try:
        run_id = _killed_run(repo)
        ck = repo / "artifacts" / "suite_runs" / run_id
        # The killed run's record still says running; the interrupted suite is not passed.
        assert _record(repo)["status"] == "running"
        gate = json.loads((ck / "tests_test_gate.py.json").read_text())
        assert gate["status"] == "running" and gate["exit_code"] is None, gate
        (repo / "gate").write_text("go")
        r = _run(repo, SUITES="test_counted,test_gate", RESUME=run_id)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "RESUME: run " + run_id + "; 1 of 2 suites" in r.stdout, r.stdout
        assert (repo / "count" / "pass").read_text() == "x", "a passed suite was re-run"
        rec = _record(repo)
        assert rec["run_id"] == run_id and rec["status"] == "passed"
        assert rec["resumed"] is True and rec["release_eligible"] is False
        assert "owner certification-policy" in rec["release_eligible_reason"]
        names = [s["suite"] for s in rec["suite_results"]]
        assert names == sorted(set(names)) == ["tests/test_counted.py", "tests/test_gate.py"]
        by = {s["suite"]: s for s in rec["suite_results"]}
        assert by["tests/test_counted.py"]["segment"] == 1
        assert by["tests/test_gate.py"]["segment"] == 2
        assert all(s["status"] == "passed" and s["started_utc"] and s["finished_utc"]
                   for s in rec["suite_results"])
        cp = rec["checkpoint"]
        assert len(cp["segments"]) == 2 and len(cp["gaps"]) == 1
        assert cp["gaps"][0]["to_utc"] == cp["segments"][1]["started_utc"]
        assert rec["tests_passing"] == 2 and rec["suites_failing"] == 0
        # Every suite is reported once in the log, the reused one from its checkpoint.
        log = (repo / rec["log"]).read_text()
        assert log.count("== tests/test_counted.py") == 1 and "OK   test_counted" in log
    finally:
        (repo / "gate").write_text("go")
        shutil.rmtree(repo, ignore_errors=True)


def test_a_failed_suite_is_rerun_on_resume_and_a_passed_one_is_not():
    repo = _sandbox()
    try:
        r = _run(repo, SUITES="test_counted,test_fail", CHECKPOINT="1")
        assert r.returncode == 1
        run_id = _record(repo)["run_id"]
        r2 = _run(repo, SUITES="test_counted,test_fail", RESUME=run_id)
        assert r2.returncode == 1 and "1 of 2 suites" in r2.stdout
        assert (repo / "count" / "pass").read_text() == "x"
        rec = _record(repo)
        assert [s["status"] for s in rec["suite_results"]] == ["passed", "failed"]
        assert rec["release_eligible"] is False
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_a_mismatched_lock_or_jobs_refuses_the_resume_and_runs_nothing():
    repo = _sandbox()
    try:
        r = _run(repo, SUITES="test_counted,test_fail", CHECKPOINT="1")
        rec0 = _record(repo)
        before = (repo / "artifacts" / "suite_runs" / f"{rec0['run_id']}.json").read_text()
        (repo / "requirements.lock").write_text("fixture==2.0\n")
        r = _run(repo, SUITES="test_counted,test_fail", RESUME=rec0["run_id"])
        assert r.returncode == 4, r.stdout + r.stderr
        assert "locks.requirements.lock" in r.stderr and "nothing was run" in r.stderr
        assert (repo / "count" / "pass").read_text() == "x"
        after = (repo / "artifacts" / "suite_runs" / f"{rec0['run_id']}.json").read_text()
        assert after == before, "a refused resume touched the original record"
        (repo / "requirements.lock").write_text("fixture==1.0\n")
        r = _run(repo, SUITES="test_counted,test_fail", RESUME=rec0["run_id"], JOBS="3")
        assert r.returncode == 4 and "jobs" in r.stderr, r.stderr
        r = _run(repo, SUITES="test_counted", RESUME=rec0["run_id"])
        assert r.returncode == 4 and "suites_sha256" in r.stderr, r.stderr
        r = _run(repo, SUITES="test_counted", RESUME="no-such-run")
        assert r.returncode == 4 and "no checkpoint manifest" in r.stderr
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_shards_are_deterministic_disjoint_and_never_release_eligible():
    repo = _sandbox()
    try:
        names = ",".join(f"test_s{i}" for i in range(8))
        got = []
        for i in range(3):
            r = _run(repo, SUITES=names, SHARD=f"{i}/3")
            if r.returncode == 2 and "holds no suites" in r.stderr:
                got.append([])
                continue
            assert r.returncode == 0, r.stdout + r.stderr
            recs = sorted((repo / "artifacts" / "suite_runs").glob("*.json"),
                          key=lambda p: p.stat().st_mtime)
            rec = json.loads(recs[-1].read_text())
            assert rec["release_eligible"] is False and rec["checkpoint"]["shard"] == f"{i}/3"
            got.append(rec["suites"])
        flat = [s for g in got for s in g]
        assert sorted(flat) == sorted(f"tests/test_s{i}.py" for i in range(8))
        assert len(flat) == len(set(flat))
        # Same answer again, and the assignment of a suite does not depend on the others.
        out = subprocess.run([PY, str(ROOT / "scripts" / "suite_checkpoint.py"), "shard", "1/3",
                              "tests/test_s1.py"], capture_output=True, text=True).stdout.split()
        assert ("tests/test_s1.py" in out) == ("tests/test_s1.py" in got[1])
        assert _run(repo, SUITES=names, SHARD="3/3").returncode == 2
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_without_the_flags_nothing_changes():
    repo = _sandbox()
    try:
        r = _run(repo, SUITES="test_counted")
        assert r.returncode == 0
        rec = _record(repo)
        assert "checkpoint" not in rec and "resumed" not in rec
        assert not (repo / "artifacts" / "suite_runs" / rec["run_id"]).exists()
    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
