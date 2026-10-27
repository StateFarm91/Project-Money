"""W4-B1 + W4-RESUMEFIX: the restart-safe runner fails closed.

The real `run_tests.sh` and `scripts/suite_checkpoint.py` are copied byte for byte into throwaway
git repositories whose `tests/` hold tiny synthetic suites, so the runner's behaviour across a
kill, a tamper or an environment change is observed without running the real suite.

The `test_p*` functions are the 26 adversarial probes of the independent review
(`research/final_build/w4/RESUME_REVIEW.md`, `resume_review_probe.py`), ported as regression
tests: each asserts the HELD outcome. Before W4-RESUMEFIX 16 of them were EXPOSED. The other
tests pin F1-F8 directly, including the review's required kill between the terminal record write
and the checkpoint's last step, and that a plain (non-checkpoint) full run is still certified.

Test-harness note: a suite's execution counter and its gate file live OUTSIDE the sandbox
repository (they were inside it in the review's probe). F4 now binds every git-ignored file under
the tree, so harness state written into the tree during a run would refuse every resume -- which
is correct runner behaviour, and not what these tests are about.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_resume_runner.py [name-prefix...]
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
PY = sys.executable
KNOBS = ("SUITES", "REQUIRE_CLEAN", "THEN_FULL", "ALLOW_PARALLEL", "SUITE_RECORD_DIR", "JOBS",
         "RESUME", "SHARD", "CHECKPOINT", "CHECKPOINT_TOOL", "TMP_LEAK_STRICT", "PYTHONPATH",
         "SUITE_RUNKEY_DIR")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DG = _load("deploy_guard_resumefix", REPO_ROOT / "ops" / "deploy_guard.py")
CK = _load("suite_checkpoint_resumefix", ROOT / "scripts" / "suite_checkpoint.py")
sys.path.insert(0, str(ROOT / "src"))
from brambleloop.ops import release_record as RR  # noqa: E402

SUITES = {
    "test_multi.py": "".join(f'print("OK   test_m{i}")\n' for i in range(5)),
    "test_gate.py": ('import os, time\n'
                     'g = os.environ["GATE_FILE"]\n'
                     'open(g + ".started", "w").close()\n'
                     'end = time.time() + 60\n'
                     'while not os.path.exists(g) and time.time() < end:\n'
                     '    time.sleep(0.05)\n'
                     'act = os.environ.get("GATE_ACTION")\n'
                     'if act and os.path.exists(act):\n'
                     '    exec(open(act).read())\n'
                     'print("OK   test_gated")\n'),
    "test_flaky.py": ('import os, sys\n'
                      'p = os.environ["COUNT_DIR"] + "/flaky"\n'
                      'n = len(open(p).read()) if os.path.exists(p) else 0\n'
                      'open(p, "a").write("x")\n'
                      'if n == 0:\n'
                      '    print("FAIL test_flaky first attempt"); sys.exit(1)\n'
                      'print("OK   test_flaky")\n'),
    "test_leaky.py": ('import os, tempfile\n'
                      'open(os.path.join(tempfile.gettempdir(), "left-behind"), "w").write("x")\n'
                      'print("OK   test_leaky")\n'),
    "test_inputs.py": ('import os, sys\n'
                       'sys.path.insert(0, os.path.dirname(__file__))\n'
                       'import helper_untracked\n'
                       'fx = open(os.path.join(os.path.dirname(__file__), "..", "fixtures",\n'
                       '                       "value.txt")).read().strip()\n'
                       'try:\n'
                       '    import depmod; dv = depmod.VALUE\n'
                       'except ImportError:\n'
                       '    dv = 1\n'
                       'ok = helper_untracked.VALUE == 1 and fx == "1" and dv == 1\n'
                       'print(("OK   " if ok else "FAIL ") + "test_inputs "\n'
                       '      f"helper={helper_untracked.VALUE} fixture={fx} depmod={dv}")\n'
                       'sys.exit(0 if ok else 1)\n'),
    "test_counted.py": ('import os\n'
                        'open(os.environ["COUNT_DIR"] + "/counted", "a").write("x")\n'
                        'print("OK   test_counted")\n'),
    # reads the clock: in the F7 final-segment set by the review's criteria
    "test_clock.py": ('import os\nfrom datetime import datetime\n'
                      'open(os.environ["COUNT_DIR"] + "/clock", "a").write("x")\n'
                      'assert datetime.now().year > 2000\n'
                      'print("OK   test_clock")\n'),
}
# A CHECKPOINT_TOOL wrapper that can hang or fail one subcommand, so a run can be killed or
# failed at an exact step (the F1 kill between the record write and the checkpoint's last step).
WRAPPER = ('import os, sys, time\n'
           'cmd = sys.argv[1]\n'
           'flag = os.path.join(os.environ["COUNT_DIR"], "hang_" + cmd)\n'
           'if os.path.exists(flag):\n'
           '    open(flag + ".reached", "w").close()\n'
           '    time.sleep(120)\n'
           'if os.path.exists(os.path.join(os.environ["COUNT_DIR"], "fail_" + cmd)):\n'
           '    sys.exit(1)\n'
           'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n'
           'import suite_checkpoint\n'
           'sys.exit(suite_checkpoint.main())\n')


class Box:
    """One sandbox: a git repo, plus harness state and run secrets outside it."""

    def __init__(self, name: str, n_filler: int = 0):
        self.base = Path(tempfile.mkdtemp(prefix=f"rf-{name}-"))
        self.repo = self.base / "repo"
        self.state = self.base / "state"
        self.keys = self.base / "keys"
        self.state.mkdir()
        r = self.repo
        for d in ("tests", "scripts", "fixtures"):
            (r / d).mkdir(parents=True)
        shutil.copy(ROOT / "run_tests.sh", r / "run_tests.sh")
        shutil.copy(ROOT / "scripts" / "suite_checkpoint.py", r / "scripts" / "suite_checkpoint.py")
        (r / "scripts" / "ck_wrap.py").write_text(WRAPPER)
        for f, body in SUITES.items():
            (r / "tests" / f).write_text(body)
        for i in range(n_filler):
            (r / "tests" / f"test_z{i:03d}.py").write_text(f'print("OK   test_z{i}")\n')
        (r / "tests" / "helper_untracked.py").write_text("VALUE = 1\n")
        (r / "fixtures" / "value.txt").write_text("1\n")
        (r / "requirements.lock").write_text("fixture==1.0\n")
        (r / ".gitignore").write_text("artifacts/\nfixtures/\nvenv/\n__pycache__/\n")
        self.git("init", "-q")
        self.git("add", "-A", "--", ".", ":!tests/helper_untracked.py")
        self.git("commit", "-qm", "s")

    def git(self, *a: str) -> str:
        return subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c",
                               "user.email=t@example.invalid", *a], capture_output=True,
                              text=True, check=True).stdout.strip()

    def commit(self, msg: str) -> None:
        self.git("commit", "-qam", msg)

    def env(self, **over) -> dict:
        e = {k: v for k, v in os.environ.items() if k not in KNOBS}
        return {**e, "PY": PY, "JOBS": "2", "SUITE_REGISTRY": "0",
                "COUNT_DIR": str(self.state), "GATE_FILE": str(self.state / "gate"),
                "SUITE_RUNKEY_DIR": str(self.keys), **over}

    def run(self, **over) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.repo / "run_tests.sh")], capture_output=True,
                              text=True, env=self.env(**over), timeout=300, cwd=self.repo)

    def popen(self, **over) -> subprocess.Popen:
        return subprocess.Popen(["bash", str(self.repo / "run_tests.sh")],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                env=self.env(**over), cwd=self.repo, start_new_session=True)

    @property
    def runs(self) -> Path:
        return self.repo / "artifacts" / "suite_runs"

    def ck(self, rid: str) -> Path:
        return self.runs / rid

    def record(self, rid: str) -> dict:
        return json.loads((self.runs / f"{rid}.json").read_text())

    def only_record(self) -> dict:
        recs = sorted(self.runs.glob("*.json"))
        assert len(recs) == 1, recs
        return json.loads(recs[0].read_text())

    def attempt(self, rid: str, suite: str, seg: int = 1, ext: str = ".json") -> Path:
        return self.ck(rid) / f"tests_{suite}.s{seg}{ext}"

    def count(self, name: str) -> int:
        p = self.state / name
        return len(p.read_text()) if p.exists() else 0

    def run_ids(self) -> list[str]:
        if not self.runs.is_dir():
            return []
        return sorted(d.name for d in self.runs.iterdir() if d.is_dir() and d.name != "locks")

    def killed_run(self, suites: str, wait_done=(), **over) -> str:
        """A CHECKPOINT=1 run SIGKILLed (the whole process group, as a container restart does)
        once the gate suite is running and the `wait_done` suites have a terminal attempt."""
        for p in (self.state / "gate", self.state / "gate.started"):
            p.unlink(missing_ok=True)
        seen = set(self.run_ids())
        p = self.popen(SUITES=suites, CHECKPOINT="1", **over)
        end = time.time() + 120
        rid = None
        while time.time() < end:
            new = [x for x in self.run_ids() if x not in seen]
            rid = new[0] if new else None
            if (self.state / "gate.started").exists() and rid is not None and all(
                    self.attempt(rid, s).exists() for s in wait_done):
                break
            time.sleep(0.05)
        else:
            os.killpg(p.pid, signal.SIGKILL)
            out, _ = p.communicate(timeout=60)
            raise AssertionError("killed_run never reached the kill point: " + (out or ""))
        time.sleep(0.2)
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate(timeout=60)
        (self.state / "gate").write_text("open")
        return rid

    def close(self) -> None:
        (self.state / "gate").write_text("open")
        shutil.rmtree(self.base, ignore_errors=True)


def _log(b: Box, rid: str) -> str:
    return (b.runs / f"{rid}.log").read_text()


# ==== the review's probes, now regression tests (every one must be HELD) ======================

def test_p01_kill9_mid_suite_resume_reruns_only_the_interrupted_suite():
    b = Box("p01")
    try:
        rid = b.killed_run("test_multi,test_gate", wait_done=("test_multi.py",))
        assert b.record(rid)["status"] == "running"
        assert (b.ck(rid) / "tests_test_gate.py.s1.running").exists()
        assert not b.attempt(rid, "test_gate.py").exists()
        r = b.run(SUITES="test_multi,test_gate", RESUME=rid)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "1 of 2 suites" in r.stdout, r.stdout
        rec = b.record(rid)
        by = {s["suite"]: s for s in rec["suite_results"]}
        assert by["tests/test_gate.py"]["segment"] == 2
        assert by["tests/test_multi.py"]["segment"] == 1
        assert rec["tests_passing"] == 6 and rec["resumed"] is True
        assert rec["release_eligible"] is False
    finally:
        b.close()


def test_p01b_sigterm_to_the_runner_leaves_no_suite_running():
    b = Box("p01b")
    try:
        pr = subprocess.Popen(["bash", str(b.repo / "run_tests.sh")], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, cwd=b.repo,
                              env=b.env(SUITES="test_gate", CHECKPOINT="1"))
        end = time.time() + 60
        while not (b.state / "gate.started").exists() and time.time() < end:
            time.sleep(0.05)
        time.sleep(0.3)
        pr.send_signal(signal.SIGTERM)
        pr.wait(timeout=30)
        time.sleep(0.5)
        alive = subprocess.run(["pgrep", "-f", str(b.repo / "tests" / "test_gate.py")],
                               capture_output=True, text=True).stdout.split()
        assert alive == [], f"orphaned suite processes: {alive}"
        rec = b.only_record()
        assert rec["status"] == "interrupted" and rec["release_eligible"] is False
    finally:
        b.close()


def test_p02a_empty_attempt_json_is_no_result_and_reruns():
    b = Box("p02a")
    try:
        rid = b.killed_run("test_multi,test_gate", wait_done=("test_multi.py",))
        b.attempt(rid, "test_multi.py").write_text("")
        r = b.run(SUITES="test_multi,test_gate", RESUME=rid)
        assert "2 of 2 suites" in r.stdout and r.returncode == 0, r.stdout + r.stderr
        assert b.record(rid)["tests_passing"] == 6
    finally:
        b.close()


def test_p02b_torn_out_under_a_passed_attempt_is_no_result_and_reruns():
    b = Box("p02b")
    try:
        rid = b.killed_run("test_multi,test_gate", wait_done=("test_multi.py",))
        o = b.attempt(rid, "test_multi.py", ext=".out")
        o.write_text("".join(o.read_text().splitlines(True)[:2]))
        r = b.run(SUITES="test_multi,test_gate", RESUME=rid)
        rec = b.record(rid)
        assert r.returncode == 0 and "2 of 2 suites" in r.stdout, r.stdout + r.stderr
        assert rec["tests_passing"] == 6, rec["tests_passing"]
        # F2: the torn attempt is kept; the re-run is a new attempt beside it.
        assert b.attempt(rid, "test_multi.py", 2).exists() and o.exists()
    finally:
        b.close()


def test_p02c_lost_out_under_a_passed_attempt_reruns_instead_of_sticking():
    b = Box("p02c")
    try:
        rid = b.killed_run("test_multi,test_gate", wait_done=("test_multi.py",))
        b.attempt(rid, "test_multi.py", ext=".out").unlink()
        r1 = b.run(SUITES="test_multi,test_gate", RESUME=rid)
        assert r1.returncode == 0 and "2 of 2 suites" in r1.stdout, r1.stdout + r1.stderr
        assert "NO OUTPUT" not in r1.stdout
        rec = b.record(rid)
        assert rec["tests_passing"] == 6 and rec["status"] == "passed"
    finally:
        b.close()


def test_p03a_truncated_attempt_json_reruns():
    b = Box("p03a")
    try:
        rid = b.killed_run("test_multi,test_gate", wait_done=("test_multi.py",))
        j = b.attempt(rid, "test_multi.py")
        j.write_bytes(j.read_bytes()[:40])
        r = b.run(SUITES="test_multi,test_gate", RESUME=rid)
        assert "2 of 2 suites" in r.stdout and r.returncode == 0, r.stdout + r.stderr
    finally:
        b.close()


def test_p03b_an_edited_out_is_detected_and_rerun():
    b = Box("p03b")
    try:
        (b.repo / "tests" / "test_multi.py").write_text(
            SUITES["test_multi.py"] + 'print("SKIP test_m5 not on this platform")\n')
        b.commit("skip")
        rid = b.killed_run("test_multi,test_gate", wait_done=("test_multi.py",))
        o = b.attempt(rid, "test_multi.py", ext=".out")
        o.write_text(o.read_text().replace("SKIP test_m5", "OK   test_m5"))
        r = b.run(SUITES="test_multi,test_gate", RESUME=rid)
        rec = b.record(rid)
        assert r.returncode == 0, r.stdout + r.stderr
        assert rec["tests_passing"] == 6 and rec["tests_skipped_reported"] == 1, rec
    finally:
        b.close()


def _failed_then_tampered(name: str, forge_out: bool):
    b = Box(name)
    rid = b.killed_run("test_flaky,test_gate", wait_done=("test_flaky.py",))
    j = b.attempt(rid, "test_flaky.py")
    d = json.loads(j.read_text())
    assert d["status"] == "failed"
    d["status"] = "passed"
    if forge_out:
        d.update(exit_code=0, ok_count=1)
        b.attempt(rid, "test_flaky.py", ext=".out").write_text("OK   test_flaky\n")
    j.write_text(json.dumps(d, indent=2, sort_keys=True))
    before = b.count("flaky")
    r = b.run(SUITES="test_flaky,test_gate", RESUME=rid)
    return b, rid, r, before


def test_p03c_a_failed_to_passed_edit_is_refused_and_the_record_is_self_consistent():
    b, rid, r, before = _failed_then_tampered("p03c", forge_out=False)
    try:
        rec = b.record(rid)
        by = {s["suite"]: s for s in rec["suite_results"]}
        assert b.count("flaky") == before, "a failed suite was re-run"
        assert r.returncode != 0 and rec["status"] == "failed"
        assert by["tests/test_flaky.py"]["status"] == "failed"
        assert "tests/test_flaky.py" in rec["failing_suites"]
        failed_names = {s["suite"] for s in rec["suite_results"] if s["status"] == "failed"}
        assert failed_names == set(rec["failing_suites"]), (failed_names, rec["failing_suites"])
    finally:
        b.close()


def test_p03d_a_full_forgery_is_not_counted():
    b, rid, r, before = _failed_then_tampered("p03d", forge_out=True)
    try:
        rec = b.record(rid)
        assert r.returncode != 0 and rec["status"] == "failed" and rec["suites_failing"] >= 1
        assert b.count("flaky") == before
        assert "CHECKPOINT: the failed attempt of segment 1 cannot be shown" in r.stdout
    finally:
        b.close()


def _refused_resume(b: Box, rid: str, field: str, **over) -> subprocess.CompletedProcess:
    r = b.run(SUITES="test_inputs,test_gate", RESUME=rid, **over)
    assert r.returncode == 4, r.stdout + r.stderr
    assert field in r.stderr and "nothing was run" in r.stderr, r.stderr
    return r


def test_p04a_tracked_edit_is_refused():
    b = Box("p04a")
    try:
        rid = b.killed_run("test_inputs,test_gate", wait_done=("test_inputs.py",))
        (b.repo / "tests" / "test_multi.py").write_text('print("OK   changed")\n')
        _refused_resume(b, rid, "dirty_content_sha256")
    finally:
        b.close()


def test_p04b_untracked_edit_is_refused():
    b = Box("p04b")
    try:
        rid = b.killed_run("test_inputs,test_gate", wait_done=("test_inputs.py",))
        (b.repo / "tests" / "helper_untracked.py").write_text("VALUE = 2  # edited\n")
        _refused_resume(b, rid, "tree_inputs.untracked")
    finally:
        b.close()


def test_p04c_ignored_fixture_edit_is_refused():
    b = Box("p04c")
    try:
        rid = b.killed_run("test_inputs,test_gate", wait_done=("test_inputs.py",))
        (b.repo / "fixtures" / "value.txt").write_text("2\n")
        _refused_resume(b, rid, "tree_inputs.ignored")
    finally:
        b.close()


def test_p04d_new_commit_is_refused():
    b = Box("p04d")
    try:
        rid = b.killed_run("test_inputs,test_gate", wait_done=("test_inputs.py",))
        (b.repo / "tests" / "test_multi.py").write_text('print("OK   changed")\n')
        b.commit("m")
        _refused_resume(b, rid, "git_sha")
    finally:
        b.close()


def test_p05a_lockfile_edit_is_refused():
    b = Box("p05a")
    try:
        rid = b.killed_run("test_inputs,test_gate", wait_done=("test_inputs.py",))
        (b.repo / "requirements.lock").write_text("fixture==2.0\n")
        _refused_resume(b, rid, "locks.requirements.lock")
    finally:
        b.close()


def test_p05b_installed_package_change_in_the_same_venv_is_refused():
    b = Box("p05b")
    try:
        subprocess.run([PY, "-m", "venv", "--without-pip", "--system-site-packages",
                        str(b.repo / "venv")], check=True)
        vpy = str(b.repo / "venv" / "bin" / "python")
        site = subprocess.run([vpy, "-c", "import sysconfig; print(sysconfig.get_paths()"
                               "['purelib'])"], capture_output=True, text=True,
                              check=True).stdout.strip()
        Path(site, "depmod.py").write_text("VALUE = 1\n")
        rid = b.killed_run("test_inputs,test_gate", wait_done=("test_inputs.py",), PY=vpy)
        Path(site, "depmod.py").write_text("VALUE = 2  # v2\n")
        _refused_resume(b, rid, "installed.sha256", PY=vpy)
    finally:
        b.close()


def test_p05c_pythonpath_change_is_refused():
    b = Box("p05c")
    try:
        rid = b.killed_run("test_inputs,test_gate", wait_done=("test_inputs.py",))
        alt = b.base / "alt"
        alt.mkdir()
        (alt / "depmod.py").write_text("VALUE = 2\n")
        _refused_resume(b, rid, "env.PYTHONPATH", PYTHONPATH=str(alt))
    finally:
        b.close()


def test_p05d_new_environment_flag_is_refused():
    b = Box("p05d")
    try:
        rid = b.killed_run("test_inputs,test_gate", wait_done=("test_inputs.py",))
        _refused_resume(b, rid, "env.BRAMBLELOOP_X", BRAMBLELOOP_X="1")
    finally:
        b.close()


def test_p06a_a_result_copied_from_another_run_is_not_counted():
    b = Box("p06a")
    try:
        (b.state / "flaky").write_text("x")             # run A: the flaky suite passes
        (b.state / "gate").write_text("open")
        b.run(SUITES="test_flaky,test_gate", CHECKPOINT="1")
        rid_a = b.run_ids()[0]
        (b.state / "flaky").unlink()                    # run B: it fails
        rid_b = b.killed_run("test_flaky,test_gate", wait_done=("test_flaky.py",))
        assert json.loads(b.attempt(rid_b, "test_flaky.py").read_text())["status"] == "failed"
        for ext in (".json", ".out"):
            b.attempt(rid_b, "test_flaky.py", ext=ext).unlink()
            shutil.copy(b.attempt(rid_a, "test_flaky.py", ext=ext),
                        b.attempt(rid_b, "test_flaky.py", ext=ext))
        before = b.count("flaky")
        r = b.run(SUITES="test_flaky,test_gate", RESUME=rid_b)
        rec = b.record(rid_b)
        assert r.returncode != 0 and rec["status"] == "failed", r.stdout + r.stderr
        assert b.count("flaky") == before
    finally:
        b.close()


def test_p06b_a_checkpoint_directory_copied_to_another_run_id_is_refused():
    b = Box("p06b")
    try:
        rid = b.killed_run("test_multi,test_gate", wait_done=("test_multi.py",))
        fake = "20990101T000000Z-1"
        shutil.copytree(b.ck(rid), b.ck(fake))
        shutil.copy(b.runs / f"{rid}.json", b.runs / f"{fake}.json")
        r = b.run(SUITES="test_multi,test_gate", RESUME=fake)
        assert r.returncode == 4 and "no run secret" in r.stderr, r.stdout + r.stderr
        # Even with a key file for the fake id, the manifest names another run.
        shutil.copy(b.keys / rid, b.keys / fake)
        r = b.run(SUITES="test_multi,test_gate", RESUME=fake)
        assert r.returncode == 4 and "never adopted by another run id" in r.stderr, r.stderr
    finally:
        b.close()


def test_p07_a_completed_failed_run_cannot_be_resumed_to_green():
    """Replaces W4-B1's `test_a_failed_suite_is_rerun_on_resume_and_a_passed_one_is_not`,
    which asserted C2 -- retry-until-green -- as intended behaviour (see RESUMEFIX.md)."""
    b = Box("p07")
    try:
        r1 = b.run(SUITES="test_flaky,test_multi", CHECKPOINT="1")
        assert r1.returncode == 1
        rid = b.run_ids()[0]
        r2 = b.run(SUITES="test_flaky,test_multi", RESUME=rid)
        assert r2.returncode == 4 and "RESUME continues only an interrupted run" in r2.stderr, (
            r2.stdout + r2.stderr)
        rec = b.record(rid)
        assert rec["status"] == "failed" and rec["failing_suites"] == ["tests/test_flaky.py"]
        assert b.count("flaky") == 1, "the failure was re-run"
        assert "FAIL test_flaky" in b.attempt(rid, "test_flaky.py", ext=".out").read_text()
    finally:
        b.close()


def test_p08_a_tmp_leak_strict_failure_survives_resume():
    b = Box("p08")
    try:
        rid = b.killed_run("test_leaky,test_gate", wait_done=("test_leaky.py",),
                           TMP_LEAK_STRICT="1")
        att = json.loads(b.attempt(rid, "test_leaky.py").read_text())
        assert att["status"] == "failed" and att["leak_entries"] == 1, att
        r = b.run(SUITES="test_leaky,test_gate", RESUME=rid, TMP_LEAK_STRICT="1")
        rec = b.record(rid)
        assert r.returncode != 0 and rec["status"] == "failed", r.stdout
        assert rec["tmp_leak_entries"] == 1 and "tests/test_leaky.py" in rec["failing_suites"]
    finally:
        b.close()


def _p09(control: bool):
    b = Box("p09ctl" if control else "p09", n_filler=100)
    try:
        b.git("add", "tests/helper_untracked.py")
        b.commit("c")
        (b.state / "flaky").write_text("x")             # every suite passes in this probe
        act = b.state / "act.py"
        if not control:                                 # stands in for any finalize failure
            act.write_text("import os, glob\n"
                           "for m in glob.glob(os.environ['CKROOT'] + '/*/manifest.json'):\n"
                           "    os.unlink(m)\n")
        # The same environment in both segments (F4 binds it).
        common = dict(JOBS="4", CKROOT=str(b.runs), GATE_ACTION=str(act))
        e = b.env(CHECKPOINT="1", **common)
        e.pop("SUITES", None)
        p = subprocess.Popen(["bash", str(b.repo / "run_tests.sh")], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, env=e, cwd=b.repo, start_new_session=True)
        end = time.time() + 120
        while not (b.state / "gate.started").exists() and time.time() < end:
            time.sleep(0.05)
        time.sleep(1.0)
        os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        rid = b.run_ids()[0]
        (b.state / "gate").write_text("open")
        e = b.env(RESUME=rid, **common)
        e.pop("SUITES", None)
        r = subprocess.run(["bash", str(b.repo / "run_tests.sh")], capture_output=True,
                           text=True, env=e, cwd=b.repo, timeout=300)
        rec = b.record(rid)
        picked = DG.latest_suite(b.runs, sha=b.git("rev-parse", "HEAD"), eligible_only=True)
        assert rec["release_eligible"] is False and rec["checkpoint_mode"] == "resume", rec
        assert picked is None, "the deploy guard picked a resumed run"
        assert DG.resume_provenance(rec, b.runs), "no provenance refusal"
        if control:
            assert r.returncode == 0 and rec["resumed"] is True, r.stdout[-3000:] + r.stderr
        else:
            assert r.returncode != 0 and rec["status"] == "failed", r.stdout[-3000:]
            assert "CHECKPOINT FINALIZE FAILED" in r.stdout
    finally:
        b.close()


def test_p09_control_resumed_full_run_with_finalize_intact_is_never_eligible():
    _p09(control=True)


def test_p09_a_finalize_failure_fails_the_run_and_never_fails_open():
    _p09(control=False)


def test_p09b_the_deploy_guard_reads_resume_provenance():
    src = (REPO_ROOT / "ops" / "deploy_guard.py").read_text()
    assert "resumed" in src and "checkpoint" in src and "D-W4-OWNER-RESUME-POLICY" in src


def test_p10_union_of_fresh_and_resumed_results_and_the_leak_census():
    b = Box("p10")
    try:
        rid = b.killed_run("test_multi,test_leaky,test_gate",
                           wait_done=("test_multi.py", "test_leaky.py"))
        r = b.run(SUITES="test_multi,test_leaky,test_gate", RESUME=rid)
        assert r.returncode == 0, r.stdout + r.stderr
        rec = b.record(rid)
        log = _log(b, rid)
        names = [s["suite"] for s in rec["suite_results"]]
        assert rec["tests_passing"] == 7 and len(names) == len(set(names)) == 3
        assert log.count("== tests/test_multi.py") == 1 and log.count("TOTAL PASSING") == 1
        assert rec["tmp_leak_entries"] == 1, rec["tmp_leak_entries"]       # P10b
    finally:
        b.close()


# ==== F1: fail closed from the first write; the guards refuse provenance, no override =========

def _wrapped_kill(name: str, hang: str):
    b = Box(name)
    (b.state / f"hang_{hang}").write_text("x")
    p = b.popen(SUITES="test_multi", CHECKPOINT="1", CHECKPOINT_TOOL="scripts/ck_wrap.py")
    end = time.time() + 120
    while not (b.state / f"hang_{hang}.reached").exists() and time.time() < end:
        time.sleep(0.05)
    assert (b.state / f"hang_{hang}.reached").exists(), "the run never reached the hang"
    os.killpg(p.pid, signal.SIGKILL)
    p.communicate(timeout=60)
    (b.state / f"hang_{hang}").unlink()
    return b, b.only_record()


def test_f1_kill_between_the_terminal_record_write_and_the_checkpoint_seal():
    b, rec = _wrapped_kill("f1seal", "seal")
    try:
        assert rec["status"] == "passed", rec["status"]          # the terminal write happened
        assert rec["release_eligible"] is False and rec["checkpoint_mode"] == "checkpoint"
        assert "D-W4-OWNER-RESUME-POLICY" in rec["release_eligible_reason"]
        assert DG.latest_suite(b.runs, eligible_only=True) is None
        # Even with the bit flipped by hand, the provenance refuses it.
        forged = dict(rec, release_eligible=True)
        (b.runs / f"{rec['run_id']}.json").write_text(json.dumps(forged))
        assert DG.latest_suite(b.runs, eligible_only=True) is None
        assert DG._log_confirms(forged, b.repo) is not None
        r = b.run(SUITES="test_multi", RESUME=rec["run_id"], CHECKPOINT_TOOL="scripts/ck_wrap.py")
        assert r.returncode == 4 and "not interrupted" in r.stderr, r.stderr
    finally:
        b.close()


def test_f1_kill_during_finalize_leaves_a_never_eligible_record():
    b, rec = _wrapped_kill("f1fin", "finalize")
    try:
        assert rec["status"] == "running" and rec["release_eligible"] is False
        assert rec["checkpoint_mode"] == "checkpoint" and "checkpoint" in rec
        assert DG.latest_suite(b.runs, eligible_only=True) is None
    finally:
        b.close()


def test_f1_a_failing_finalize_fails_the_run():
    b = Box("f1fail")
    try:
        (b.state / "fail_finalize").write_text("x")
        r = b.run(SUITES="test_multi", CHECKPOINT="1", CHECKPOINT_TOOL="scripts/ck_wrap.py")
        rec = b.only_record()
        assert r.returncode != 0 and rec["status"] == "failed", r.stdout
        assert "CHECKPOINT FINALIZE FAILED" in r.stdout and rec["release_eligible"] is False
    finally:
        b.close()


LAYOUT = {"prefix": "", "dirs": ("tests/",), "files": ("run_tests.sh",), "release": "release"}


def test_f1_an_ordinary_full_run_is_still_certified_and_a_checkpoint_run_is_not():
    """A plain full run behaves exactly as before: eligible, recorded, ALLOW."""
    b = Box("f1plain", n_filler=100)
    try:
        for f in list((b.repo / "tests").glob("*.py")):
            if not f.name.startswith("test_z"):
                f.unlink()
        b.git("add", "-A")
        b.commit("plain")
        sha = b.git("rev-parse", "HEAD")
        r = b.run(REQUIRE_CLEAN="1", JOBS="4", SUITES="")
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr
        rec = b.only_record()
        assert rec["release_eligible"] is True and rec["scope"] == "full"
        present = [k for k in DG.RESUME_PROVENANCE_KEYS if k in rec]
        assert present == [], present
        assert "CHECKPOINT" not in _log(b, rec["run_id"])
        assert DG.latest_suite(b.runs, sha=sha, eligible_only=True)["run_id"] == rec["run_id"]
        out = DG.record_release(sha, repo=b.repo, record_dir=b.runs, log_base=b.repo,
                                layout=LAYOUT)
        assert out["ok"], out
        b.git("add", "-A")
        b.commit("R")
        verdict = DG.check(b.git("rev-parse", "HEAD"), sha, repo=b.repo, record_dir=b.runs,
                           log_base=b.repo, layout=LAYOUT)
        assert verdict["verdict"] == "ALLOW", verdict
        # A checkpointed full run of the same tree, its bit forged to true: refused.
        r = b.run(CHECKPOINT="1", JOBS="4", SUITES="")
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr
        recs = [json.loads(p.read_text()) for p in b.runs.glob("*.json")]
        ck = [x for x in recs if x.get("checkpoint_mode")]
        assert len(recs) == 2 and len(ck) == 1 and ck[0]["release_eligible"] is False
        forged = dict(ck[0], release_eligible=True, started_utc="2999-01-01T00:00:00Z")
        (b.runs / f"{ck[0]['run_id']}.json").write_text(json.dumps(forged))
        picked = DG.latest_suite(b.runs, eligible_only=True)
        assert picked is not None and picked["run_id"] == rec["run_id"]
        refused = DG.resume_provenance(forged, b.runs)
        assert refused and "D-W4-OWNER-RESUME-POLICY" in refused[0]
    finally:
        b.close()


def _tracked_fixture(tmp: Path, suite: dict, log: str):
    rd = tmp / "release"
    (rd / "suite_runs").mkdir(parents=True)
    sb, lb = json.dumps(suite).encode(), log.encode()
    (rd / "suite_runs" / "r.json").write_bytes(sb)
    (rd / "suite_runs" / "r.log").write_bytes(lb)
    rec = {"sha": "a" * 40, "release_eligible": True,
           "suite_record": {"path": "suite_runs/r.json", "sha256": hashlib.sha256(sb).hexdigest()},
           "suite_log": {"path": "suite_runs/r.log", "sha256": hashlib.sha256(lb).hexdigest()}}

    def read(rel):
        p = rd / rel
        return p.read_bytes() if p.is_file() else None
    return rd, rec, read


def test_f1_tracked_records_with_resume_provenance_are_refused_by_both_guards():
    good = {"run_id": "R1", "git_sha": "a" * 40, "release_eligible": True, "status": "passed",
            "scope": "full", "failing_suites": [], "suites_failing": 0, "job_id": "suite-R1"}
    log = f"RUN ID: R1\nGIT SHA: {'a' * 40}\nTOTAL PASSING: 3 ; suites failing: 0\n"
    tmp = Path(tempfile.mkdtemp(prefix="rf-tracked-"))
    try:
        rd, rec, read = _tracked_fixture(tmp / "ok", good, log)
        assert RR.check_record(rec, rd) == []
        assert DG._record_problems(rec, read, tmp / "nowhere") == []
        cases = {"resumed": (dict(good, resumed=True), log),
                 "resumed_false": (dict(good, resumed=False), log),
                 "checkpoint": (dict(good, checkpoint={}), log),
                 "checkpoint_mode": (dict(good, checkpoint_mode="resume"), log),
                 "shard": (dict(good, shard="0/2"), log),
                 "suite_results": (dict(good, suite_results=[]), log),
                 "log": (good, log.replace("TOTAL", "CHECKPOINT MODE: resume\nTOTAL"))}
        assert len(cases) == 7
        for name, (suite, text) in cases.items():
            rdx, recx, readx = _tracked_fixture(tmp / name, suite, text)
            why_rr = RR.check_record(recx, rdx)
            why_dg = DG._record_problems(recx, readx)
            assert any("D-W4-OWNER-RESUME-POLICY" in w for w in why_rr), (name, why_rr)
            assert any("D-W4-OWNER-RESUME-POLICY" in w for w in why_dg), (name, why_dg)
        # A plain record whose run id has a checkpoint directory beside it.
        (tmp / "ok" / "artifacts" / "suite_runs" / "R1").mkdir(parents=True)
        assert any("checkpoint directory" in w for w in RR.check_record(rec, rd))
        assert any("checkpoint directory" in w for w in DG._record_problems(
            rec, read, tmp / "ok" / "artifacts" / "suite_runs"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_f1_both_guards_share_the_provenance_rule_and_neither_has_an_override():
    assert DG.RESUME_PROVENANCE_KEYS == RR.RESUME_PROVENANCE_KEYS
    assert DG._CKPT_LOG.pattern == RR._CKPT_LOG.pattern
    srcs = [(REPO_ROOT / "ops" / "deploy_guard.py").read_text(),
            (ROOT / "src" / "brambleloop" / "ops" / "release_record.py").read_text()]
    assert len(srcs) == 2
    for src in srcs:
        low = src.lower()
        assert "owner_approved" not in low and "verify_resumed" not in low, \
            "no bypass of D-W4-OWNER-RESUME-POLICY may exist without a fresh review"
    rec = {"run_id": "x", "resumed": True, "owner_approved": True, "release_eligible": True}
    assert DG.resume_provenance(rec) and RR.resume_provenance(rec)


# ==== F2, F3, F7, F8 ===========================================================================

def test_f2_an_earlier_failure_is_never_rerun_in_a_resumed_segment():
    b = Box("f2")
    try:
        rid = b.killed_run("test_flaky,test_gate", wait_done=("test_flaky.py",))
        r = b.run(SUITES="test_flaky,test_gate", RESUME=rid)
        assert "already failed in this run and are NOT re-run" in r.stderr, r.stderr
        assert r.returncode == 1 and b.count("flaky") == 1
        rec = b.record(rid)
        by = {s["suite"]: s for s in rec["suite_results"]}
        assert by["tests/test_flaky.py"]["attempts"] == [{"segment": 1, "status": "failed"}]
        assert by["tests/test_gate.py"]["segment"] == 2
    finally:
        b.close()


def test_f3_the_run_secret_lives_outside_the_repo_mode_600_and_tampering_is_refused():
    b = Box("f3")
    try:
        rid = b.killed_run("test_multi,test_gate", wait_done=("test_multi.py",))
        key = b.keys / rid
        assert key.is_file() and (key.stat().st_mode & 0o777) == 0o600
        assert (b.keys.stat().st_mode & 0o777) == 0o700
        assert b.repo.resolve() not in key.resolve().parents
        res = json.loads(b.attempt(rid, "test_multi.py").read_text())
        assert res["run_id"] == rid and res["segment"] == 1 and res["host"]["hostname"]
        assert len(res["out_sha256"]) == 64 and res["counts"]["ok"] == 5 and res["mac"]
        man_p = b.ck(rid) / "manifest.json"
        good = man_p.read_text()
        man = json.loads(good)
        assert len(man["chain"]) >= 2 and man["chain"][1]["kind"] == "result"
        man["chain"][1]["status"] = "failed"                     # tamper the chain itself
        man_p.write_text(json.dumps(man))
        r = b.run(SUITES="test_multi,test_gate", RESUME=rid)
        assert r.returncode == 4 and "MAC does not verify" in r.stderr, r.stderr
        man_p.write_text(good)
        key.chmod(0o644)
        r = b.run(SUITES="test_multi,test_gate", RESUME=rid)
        assert r.returncode == 4 and "not mode 600" in r.stderr, r.stderr
        key.chmod(0o600)
        r = b.run(SUITES="test_multi,test_gate", RESUME=rid)
        assert r.returncode == 0, r.stdout + r.stderr
        r = b.run(SUITES="test_counted", CHECKPOINT="1",
                  SUITE_RUNKEY_DIR=str(b.repo / "keys-in-repo"))
        assert r.returncode == 4 and "inside the repository" in r.stderr, r.stdout + r.stderr
    finally:
        b.close()


def test_f7_clock_sensitive_suites_rerun_together_in_the_final_segment():
    b = Box("f7")
    try:
        rid = b.killed_run("test_clock,test_multi,test_gate",
                           wait_done=("test_clock.py", "test_multi.py"))
        assert b.count("clock") == 1
        r = b.run(SUITES="test_clock,test_multi,test_gate", RESUME=rid)
        assert r.returncode == 0 and "2 of 3 suites" in r.stdout, r.stdout + r.stderr
        assert b.count("clock") == 2
        rec = b.record(rid)
        by = {s["suite"]: s for s in rec["suite_results"]}
        assert by["tests/test_clock.py"]["segment"] == 2
        assert by["tests/test_clock.py"]["final_segment_set"] is True
        assert by["tests/test_multi.py"]["segment"] == 1
    finally:
        b.close()


def test_f7_a_resume_that_crosses_the_utc_date_is_refused():
    b = Box("f7date")
    old_cwd, old_env = os.getcwd(), os.environ.get("SUITE_RUNKEY_DIR")
    real_now = CK._now
    try:
        rid = b.killed_run("test_multi,test_gate", wait_done=("test_multi.py",))
        os.chdir(b.repo)
        os.environ["SUITE_RUNKEY_DIR"] = str(b.keys)
        CK._now = lambda: datetime.now(timezone.utc) + timedelta(days=1)

        class A:
            dir = f"artifacts/suite_runs/{rid}"
            record_dir = "artifacts/suite_runs"
            run_id = rid
            jobs, scope, shard = "2", "x", ""
            suites = ["tests/test_multi.py", "tests/test_gate.py"]
        try:
            CK.resume_state(A)
        except CK.Refused as exc:
            assert "cross the UTC date" in str(exc), exc
        else:
            raise AssertionError("a resume on the next UTC day was accepted")
    finally:
        CK._now = real_now
        os.chdir(old_cwd)
        if old_env is None:
            os.environ.pop("SUITE_RUNKEY_DIR", None)
        else:
            os.environ["SUITE_RUNKEY_DIR"] = old_env
        b.close()


def test_f7_the_declared_final_segment_set_covers_every_matching_suite():
    old = os.getcwd()
    try:
        os.chdir(ROOT)
        suites = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_*.py"))
        assert len(suites) > 700
        detected = CK.detect_timing_sensitive(suites)
        declared = CK.declared_final_set(str(ROOT / CK.FINAL_SET_FILE))
    finally:
        os.chdir(old)
    assert len(detected) > 150 and "tests/test_w4_resume_runner.py" in detected
    missing = sorted(detected - declared)
    assert not missing, f"declare these in {CK.FINAL_SET_FILE}: {missing}"


def test_f8_a_second_resume_of_the_same_run_is_refused_even_with_allow_parallel():
    b = Box("f8")
    try:
        rid = b.killed_run("test_multi,test_gate", wait_done=("test_multi.py",))
        for p in (b.state / "gate", b.state / "gate.started"):
            p.unlink(missing_ok=True)
        first = b.popen(SUITES="test_multi,test_gate", RESUME=rid)
        end = time.time() + 60
        while not (b.state / "gate.started").exists() and time.time() < end:
            time.sleep(0.05)
        second = b.run(SUITES="test_multi,test_gate", RESUME=rid, ALLOW_PARALLEL="1")
        assert second.returncode == 75 and "already has a live segment" in second.stderr, (
            second.stdout + second.stderr)
        (b.state / "gate").write_text("open")
        out, _ = first.communicate(timeout=120)
        assert first.returncode == 0, out
        rec = b.record(rid)
        assert set(rec["failing_suites"]) == {
            s["suite"] for s in rec["suite_results"] if s["status"] == "failed"}
    finally:
        b.close()


# ==== kept from W4-B1 ==========================================================================

def test_a_mismatched_lock_or_jobs_refuses_the_resume_and_runs_nothing():
    b = Box("mismatch")
    try:
        rid = b.killed_run("test_counted,test_gate", wait_done=("test_counted.py",))
        before = (b.runs / f"{rid}.json").read_text()
        (b.repo / "requirements.lock").write_text("fixture==2.0\n")
        r = b.run(SUITES="test_counted,test_gate", RESUME=rid)
        assert r.returncode == 4, r.stdout + r.stderr
        assert "locks.requirements.lock" in r.stderr and "nothing was run" in r.stderr
        assert b.count("counted") == 1
        assert (b.runs / f"{rid}.json").read_text() == before
        (b.repo / "requirements.lock").write_text("fixture==1.0\n")
        r = b.run(SUITES="test_counted,test_gate", RESUME=rid, JOBS="3")
        assert r.returncode == 4 and "jobs" in r.stderr, r.stderr
        r = b.run(SUITES="test_counted", RESUME=rid)
        assert r.returncode == 4 and "suites_sha256" in r.stderr, r.stderr
        r = b.run(SUITES="test_counted", RESUME="no-such-run")
        assert r.returncode == 4 and "no run secret" in r.stderr, r.stderr
    finally:
        b.close()


def test_shards_are_deterministic_disjoint_and_never_release_eligible():
    b = Box("shards")
    try:
        names = [f"test_s{i}" for i in range(8)]
        for n in names:
            (b.repo / "tests" / f"{n}.py").write_text(f'print("OK   {n}")\n')
        b.git("add", "-A", "--", ".", ":!tests/helper_untracked.py")
        b.commit("shards")
        got = []
        for i in range(3):
            seen = set(b.run_ids())
            r = b.run(SUITES=",".join(names), SHARD=f"{i}/3")
            if r.returncode == 2 and "holds no suites" in r.stderr:
                got.append([])
                continue
            assert r.returncode == 0, r.stdout + r.stderr
            [rid] = [x for x in b.run_ids() if x not in seen]
            rec = b.record(rid)
            assert rec["release_eligible"] is False and rec["checkpoint"]["shard"] == f"{i}/3"
            assert rec["checkpoint_mode"] == "shard"
            got.append(rec["suites"])
        flat = [s for g in got for s in g]
        assert sorted(flat) == sorted(f"tests/{n}.py" for n in names)
        assert len(flat) == len(set(flat))
        out = subprocess.run([PY, str(ROOT / "scripts" / "suite_checkpoint.py"), "shard", "1/3",
                              "tests/test_s1.py"], capture_output=True, text=True).stdout.split()
        assert ("tests/test_s1.py" in out) == ("tests/test_s1.py" in got[1])
        assert b.run(SUITES=",".join(names), SHARD="3/3").returncode == 2
    finally:
        b.close()


def test_without_the_flags_nothing_changes():
    b = Box("plain")
    try:
        r = b.run(SUITES="test_counted")
        assert r.returncode == 0
        rec = b.only_record()
        present = [k for k in DG.RESUME_PROVENANCE_KEYS + ("release_eligible_reason",) if k in rec]
        assert present == [], present
        assert not (b.runs / rec["run_id"]).exists() and not b.keys.exists()
        assert not re.search(r"^(CHECKPOINT|RESUME)", _log(b, rec["run_id"]), re.M)
    finally:
        b.close()


if __name__ == "__main__":
    only = sys.argv[1:]
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and (not only or any(name.startswith(o) for o in only)):
            t = time.time()
            try:
                fn()
                print("OK  ", name, f"({time.time() - t:.1f}s)", flush=True)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:3000], flush=True)
    sys.exit(1 if fails else 0)
