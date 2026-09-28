"""run_tests.sh binds its result to git, guards against duplicate runs and runs targeted suites.

F-169 / F-170 / F-345 / F-346 / F-347. The real script is exercised -- copied byte for byte into
a throwaway git repository whose `tests/` holds three tiny dummy suites -- because the property
under test is the shell script's behaviour, and running the real twenty-minute suite to observe
it would be the redundant full rerun F-347 exists to prevent. Every run here uses the SUITES
filter, so nothing but the dummies is ever executed.
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

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "run_tests.sh"
PY = sys.executable

PASS = 'print("OK   test_one")\nprint("OK   test_two")\n'
FAIL = 'import sys\nprint("OK   test_one")\nprint("FAIL test_two boom")\nsys.exit(1)\n'
# Blocks until a release file appears, so a run can be observed while it is in progress.
GATE = ('import os, sys, time\n'
        'gate = os.environ["GATE_FILE"]\n'
        'open(gate + ".started", "w").close()\n'
        'deadline = time.time() + 60\n'
        'while not os.path.exists(gate) and time.time() < deadline:\n'
        '    time.sleep(0.05)\n'
        'print("OK   test_gated")\n')


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _sandbox() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="runtests-"))
    (repo / "tests").mkdir()
    shutil.copy(SCRIPT, repo / "run_tests.sh")
    (repo / "tests" / "test_pass.py").write_text(PASS)
    (repo / "tests" / "test_fail.py").write_text(FAIL)
    (repo / "tests" / "test_gate.py").write_text(GATE)
    (repo / ".gitignore").write_text("artifacts/\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "commit", "-q", "-m", "sandbox")
    return repo


def _run(repo: Path, suites: str, **env) -> subprocess.CompletedProcess:
    e = {**os.environ, "PY": PY, "JOBS": "2", "SUITES": suites, **env}
    if "ALLOW_PARALLEL" not in env:
        e.pop("ALLOW_PARALLEL", None)
    return subprocess.run(["bash", str(repo / "run_tests.sh")], capture_output=True, text=True,
                          env=e, timeout=120)


def _records(repo: Path) -> list[dict]:
    d = repo / "artifacts" / "suite_runs"
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))]


def test_the_log_opens_and_closes_with_sha_tree_state_utc_times_and_totals():
    repo = _sandbox()
    try:
        r = _run(repo, "test_pass")
        assert r.returncode == 0, r.stdout + r.stderr
        sha = _git(repo, "rev-parse", "HEAD")
        head = r.stdout.splitlines()[:6]
        assert head[0].startswith("RUN ID: ")
        assert head[1].startswith("RUN STARTED: ") and head[1].endswith("Z")
        assert head[2] == f"GIT SHA: {sha}"
        assert head[3] == "TREE: clean (0 changed paths)"
        assert "SCOPE: filtered (1 suites): tests/test_pass.py" in head[4]
        tail = r.stdout.splitlines()
        assert "TOTAL PASSING: 2 ; suites failing: 0" in tail
        assert any(l.startswith("RUN FINISHED: ") and l.endswith("Z") for l in tail)
        assert f"GIT SHA: {sha} (tree clean at start)" in tail
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_a_json_run_record_and_a_full_log_copy_are_written_where_the_log_says():
    repo = _sandbox()
    try:
        r = _run(repo, "test_pass,tests/test_fail.py")
        assert r.returncode == 1, r.stdout
        [rec] = _records(repo)
        assert rec["status"] == "failed" and rec["git_sha"] == _git(repo, "rev-parse", "HEAD")
        assert rec["git_sha_at_end"] == rec["git_sha"]
        assert rec["tree"] == "clean" and rec["scope"] == "filtered"
        assert rec["suites"] == ["tests/test_fail.py", "tests/test_pass.py"]
        assert rec["tests_passing"] == 3 and rec["tests_failing_reported"] == 1
        assert rec["suites_failing"] == 1 and rec["failing_suites"] == ["tests/test_fail.py"]
        assert rec["started_utc"] <= rec["finished_utc"] and rec["duration_s"] >= 0
        assert rec["exit_code"] == 1
        assert rec["release_eligible"] is False, "a filtered, failing run was release-eligible"
        log = (repo / rec["log"]).read_text()
        assert log.splitlines()[0] == f"RUN ID: {rec['run_id']}"
        assert "TOTAL PASSING: 3 ; suites failing: 1" in log and "FAIL test_two boom" in log
        assert f"RUN RECORD: {rec['record']}" in r.stdout
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_a_filtered_run_executes_only_the_named_suites_and_an_unknown_name_runs_nothing():
    repo = _sandbox()
    try:
        r = _run(repo, "test_pass")
        assert "== tests/test_pass.py" in r.stdout
        assert "test_fail" not in r.stdout and "test_gate" not in r.stdout
        bad = _run(repo, "test_pass test_nonexistent")
        assert bad.returncode == 2 and "unknown suite" in bad.stderr
        assert len(_records(repo)) == 1, "an unknown suite name still produced a run"
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_a_dirty_tree_is_recorded_as_dirty_and_refused_under_require_clean():
    repo = _sandbox()
    try:
        (repo / "tests" / "test_pass.py").write_text(PASS + "# edited\n")
        r = _run(repo, "test_pass")
        assert r.returncode == 0 and "TREE: dirty (1 changed paths)" in r.stdout
        assert _records(repo)[0]["tree"] == "dirty"
        refused = _run(repo, "test_pass", REQUIRE_CLEAN="1")
        assert refused.returncode == 3 and "REFUSED" in refused.stderr
        assert len(_records(repo)) == 1
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_a_second_identical_run_reports_the_running_one_and_exits_without_running():
    repo = _sandbox()
    gate = repo / "gate"
    try:
        e = {**os.environ, "PY": PY, "JOBS": "2", "SUITES": "test_gate", "GATE_FILE": str(gate)}
        e.pop("ALLOW_PARALLEL", None)
        first = subprocess.Popen(["bash", str(repo / "run_tests.sh")], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, env=e)
        deadline = time.time() + 30
        while not Path(str(gate) + ".started").exists() and time.time() < deadline:
            time.sleep(0.05)
        assert Path(str(gate) + ".started").exists(), "the first run never started its suite"
        running = _records(repo)
        assert [r["status"] for r in running] == ["running"]

        second = subprocess.run(["bash", str(repo / "run_tests.sh")], capture_output=True,
                                text=True, env=e, timeout=60)
        assert second.returncode == 75, second.stdout + second.stderr
        assert "SUITE ALREADY RUNNING" in second.stdout
        assert f"run_id={running[0]['run_id']}" in second.stdout
        assert '"status": "running"' in second.stdout, "the running record was not shown"
        assert len(_records(repo)) == 1, "the refused run wrote a record"

        # The deliberate override starts a second run while the first is still in progress.
        par = subprocess.Popen(["bash", str(repo / "run_tests.sh")], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True,
                               env={**e, "ALLOW_PARALLEL": "1"})
        deadline = time.time() + 30
        while len(_records(repo)) < 2 and time.time() < deadline:
            time.sleep(0.05)
        assert len(_records(repo)) == 2, "ALLOW_PARALLEL=1 did not start a second run"
        gate.write_text("go")
        par_out, _ = par.communicate(timeout=60)
        assert par.returncode == 0 and "ALLOW_PARALLEL=1" in par_out, par_out
        out, _ = first.communicate(timeout=60)
        assert first.returncode == 0, out
        assert not list((repo / "artifacts" / "suite_runs" / "locks").glob("*.lock")), \
            "the lock outlived the run"
        assert sorted(r["status"] for r in _records(repo)) == ["passed", "passed"]
    finally:
        gate.write_text("go")
        shutil.rmtree(repo, ignore_errors=True)


def test_a_stale_lock_from_a_dead_process_is_taken_over_and_said():
    repo = _sandbox()
    try:
        first = _run(repo, "test_pass")
        assert first.returncode == 0
        rec = _records(repo)[0]
        lock = repo / rec["lock"]
        assert rec["lock"] and not lock.exists(), "a finished run left its lock behind"
        # Plant the lock a run killed with -9 would leave: its pid is no longer alive.
        dead = subprocess.Popen(["true"])
        dead.wait()
        lock.write_text(f"run_id=ghost\npid={dead.pid}\npid_start=1\nstarted=x\n"
                        f"git_sha={rec['git_sha']}\nscope=x\nrecord=/nonexistent\n")
        again = _run(repo, "test_pass")
        assert again.returncode == 0, again.stdout + again.stderr
        assert "took over the stale lock of run ghost" in again.stdout
        assert [r["took_over_stale_lock_of"] for r in _records(repo)].count("ghost") == 1
        assert not lock.exists()
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_then_full_does_not_start_the_full_run_when_the_targeted_suites_fail():
    repo = _sandbox()
    try:
        r = _run(repo, "test_fail", THEN_FULL="1")
        assert r.returncode == 1
        assert "targeted suites failed; the full suite was not started" in r.stdout
        # The sandbox has 3 suites, below the full-run discovery floor of 100: had the full run
        # started, it would have said so on stderr.
        assert "discovery is not working" not in r.stderr
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_then_full_chains_into_the_unfiltered_run_when_the_targeted_suites_pass():
    repo = _sandbox()
    try:
        r = _run(repo, "test_pass", THEN_FULL="1")
        assert "targeted suites passed; starting the full suite" in r.stdout
        # The chained run is the real full-scope discovery, which refuses a 3-suite sandbox --
        # proof it ran unfiltered rather than re-running the targeted set.
        assert "suites found; the discovery is not working" in r.stderr
        assert r.returncode == 1
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_an_interrupted_run_is_recorded_as_interrupted_and_releases_its_lock():
    repo = _sandbox()
    gate = repo / "gate"
    try:
        e = {**os.environ, "PY": PY, "JOBS": "2", "SUITES": "test_gate", "GATE_FILE": str(gate)}
        e.pop("ALLOW_PARALLEL", None)
        p = subprocess.Popen(["bash", str(repo / "run_tests.sh")], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=e)
        deadline = time.time() + 30
        while not Path(str(gate) + ".started").exists() and time.time() < deadline:
            time.sleep(0.05)
        p.terminate()
        p.communicate(timeout=60)
        [rec] = _records(repo)
        assert rec["status"] == "interrupted" and rec["exit_code"] == 130, rec
        assert rec["release_eligible"] is False
        assert not (repo / rec["lock"]).exists(), "an interrupted run kept its lock"
    finally:
        gate.write_text("go")
        shutil.rmtree(repo, ignore_errors=True)


def test_only_a_full_clean_green_run_on_an_unmoved_head_can_be_release_eligible():
    # The flag is computed by the record writer inside the script; drive it through the real
    # writer by reading its rule off a filtered green run (never eligible) -- the full-scope
    # positive case is covered by tests/test_deploy_guard.py against a record fixture.
    repo = _sandbox()
    try:
        _run(repo, "test_pass")
        rec = _records(repo)[0]
        assert rec["status"] == "passed" and rec["tree"] == "clean"
        assert rec["release_eligible"] is False and rec["scope"] == "filtered"
        text = SCRIPT.read_text()
        assert 'rec["scope"] == "full"' in text and 'rec["tree"] == "clean"' in text
        assert 'end_sha == rec["git_sha"]' in text
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
