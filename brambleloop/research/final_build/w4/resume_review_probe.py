#!/usr/bin/env python3
"""W4-RESUMEREVIEW: adversarial probes of the W4-B1 restart-safe runner (f1cde398).

Independent review harness, NOT a release suite (deliberately outside tests/test_*.py, so the
runner's glob never picks it up). Each probe builds a throwaway git repository holding the
real `run_tests.sh` and `scripts/suite_checkpoint.py` copied byte for byte, plus tiny synthetic
suites, drives a run / kill / tamper / resume sequence, and prints one line per probe:

    HELD     <probe>: <what was observed>     -- the runner enforced the policy
    EXPOSED  <probe>: <what was observed>     -- the runner accepted something the policy forbids

ADAPTED BY W4-RESUMEFIX (2026-10-27) to the fixed runner's on-disk layout, verdict logic
otherwise unchanged: (1) a suite's result is the append-only attempt `tests_<suite>.s1.json`/`.out`
(was `tests_<suite>.json`/`.out`); (2) the harness's counter/gate files and the run secrets live
OUTSIDE the sandbox repository (F4 binds every git-ignored file in the tree, so harness state
written there mid-run would refuse every resume); (3) P03c had no HELD branch (it printed EXPOSED
unconditionally) -- it is HELD when the failed suite is not re-run, the run fails and the record
agrees with itself; (4) P09 passes the same environment to both segments (F4 binds the whole
environment; with different ones the resume is refused before finalize is ever reached) and
pre-seeds the flaky counter so every suite passes. The original is commit 503a29cd.

The process exits 0 when every probe ran to completion (whatever it found) and 1 if a probe
could not run. Run from brambleloop/:  nice -n 19 python3 research/final_build/w4/resume_review_probe.py
"""
from __future__ import annotations

import importlib.util
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
ROOT = Path(__file__).resolve().parents[3]           # brambleloop/
PY = sys.executable
KNOBS = ("SUITES", "REQUIRE_CLEAN", "THEN_FULL", "ALLOW_PARALLEL", "SUITE_RECORD_DIR", "JOBS",
         "RESUME", "SHARD", "CHECKPOINT", "CHECKPOINT_TOOL", "TMP_LEAK_STRICT", "PYTHONPATH",
         "SUITE_RUNKEY_DIR")
WORK = Path(tempfile.mkdtemp(prefix="resume-review-"))
RESULTS: list[tuple[str, str, str]] = []

SUITES = {
    # five passing assertions: lets a truncated output be seen in TOTAL PASSING
    "test_multi.py": "".join(f'print("OK   test_m{i}")\n' for i in range(5)),
    # held open until the probe releases (or kills) it
    "test_gate.py": ('import os, time\n'
                     'g = os.environ["GATE_FILE"]\n'
                     'open(g + ".started", "w").close()\n'
                     'end = time.time() + 60\n'
                     'while not os.path.exists(g) and time.time() < end:\n'
                     '    time.sleep(0.05)\n'
                     'act = os.environ.get("GATE_ACTION")\n'
                     'if act:\n'
                     '    exec(open(act).read())\n'
                     'print("OK   test_gated")\n'),
    # fails on its first execution, passes on every later one
    "test_flaky.py": ('import os, sys\n'
                      'p = os.environ["COUNT_DIR"] + "/flaky"\n'
                      'n = len(open(p).read()) if os.path.exists(p) else 0\n'
                      'open(p, "a").write("x")\n'
                      'if n == 0:\n'
                      '    print("FAIL test_flaky first attempt"); sys.exit(1)\n'
                      'print("OK   test_flaky")\n'),
    # leaves one file in its own TMPDIR
    "test_leaky.py": ('import os, tempfile\n'
                      'open(os.path.join(tempfile.gettempdir(), "left-behind"), "w").write("x")\n'
                      'print("OK   test_leaky")\n'),
    # depends on an untracked helper, a git-ignored fixture and an installed module
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
}


def git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True,
                          check=True).stdout.strip()


def st(repo: Path) -> Path:
    """Harness state (counters, gate) outside the sandbox repository (W4-RESUMEFIX)."""
    return repo.parent / f"{repo.name}-state"


def sandbox(name: str, n_filler: int = 0) -> Path:
    repo = WORK / name
    (repo / "tests").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "fixtures").mkdir()
    st(repo).mkdir()
    shutil.copy(ROOT / "run_tests.sh", repo / "run_tests.sh")
    shutil.copy(ROOT / "scripts" / "suite_checkpoint.py", repo / "scripts" / "suite_checkpoint.py")
    for f, body in SUITES.items():
        (repo / "tests" / f).write_text(body)
    for i in range(n_filler):
        (repo / "tests" / f"test_z{i:03d}.py").write_text(f'print("OK   test_z{i}")\n')
    (repo / "tests" / "helper_untracked.py").write_text("VALUE = 1\n")
    (repo / "fixtures" / "value.txt").write_text("1\n")
    (repo / "requirements.lock").write_text("fixture==1.0\n")
    # helper_untracked.py is left untracked on purpose; fixtures/ is git-ignored on purpose
    (repo / ".gitignore").write_text("artifacts/\ncount/\ngate*\nfixtures/\nvenv/\n__pycache__/\n")
    git(repo, "init", "-q")
    git(repo, "add", "-A", "--", ".", ":!tests/helper_untracked.py")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "s")
    return repo


def env(repo: Path, **over) -> dict:
    e = {k: v for k, v in os.environ.items() if k not in KNOBS}
    return {**e, "PY": PY, "JOBS": "2", "SUITE_REGISTRY": "0",
            "COUNT_DIR": str(st(repo)), "GATE_FILE": str(st(repo) / "gate"),
            "SUITE_RUNKEY_DIR": str(repo.parent / f"{repo.name}-keys"), **over}


def run(repo: Path, **over) -> subprocess.CompletedProcess:
    return subprocess.run(["nice", "-n", "19", "bash", str(repo / "run_tests.sh")],
                          capture_output=True, text=True, env=env(repo, **over), timeout=300,
                          cwd=repo)


def runs(repo: Path) -> Path:
    return repo / "artifacts" / "suite_runs"


def ckdir(repo: Path, rid: str) -> Path:
    return runs(repo) / rid


def record(repo: Path, rid: str) -> dict:
    return json.loads((runs(repo) / f"{rid}.json").read_text())


def suite_json(repo: Path, rid: str, suite: str) -> dict:
    return json.loads((ckdir(repo, rid) / f"tests_{suite}.s1.json").read_text())


def killed_run(repo: Path, suites: str, sig=signal.SIGKILL, wait_done=(), **over) -> str:
    """Start a CHECKPOINT=1 run, wait until the gate suite is running and `wait_done` suites
    have a terminal checkpoint, then send `sig` to the whole process group (a container
    restart takes every process). Returns the run id."""
    for p in (st(repo) / "gate", st(repo) / "gate.started"):
        p.unlink(missing_ok=True)
    seen = {d.name for d in runs(repo).iterdir()} if runs(repo).is_dir() else set()
    p = subprocess.Popen(["nice", "-n", "19", "bash", str(repo / "run_tests.sh")],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         env=env(repo, SUITES=suites, CHECKPOINT="1", **over), cwd=repo,
                         start_new_session=True)
    end = time.time() + 120
    rid = None
    while time.time() < end:
        if runs(repo).is_dir():
            dirs = [d for d in runs(repo).iterdir()
                    if d.is_dir() and d.name != "locks" and d.name not in seen]
            if dirs:
                rid = dirs[0].name
        ready = (st(repo) / "gate.started").exists() and rid is not None
        if ready:
            for s in wait_done:
                try:
                    if suite_json(repo, rid, s)["status"] not in ("passed", "failed"):
                        ready = False
                except (OSError, ValueError, KeyError):
                    ready = False
        if ready:
            break
        time.sleep(0.05)
    else:
        os.killpg(p.pid, signal.SIGKILL)
        raise RuntimeError("killed_run: the run never reached the kill point")
    time.sleep(0.2)
    os.killpg(p.pid, sig)
    p.wait(timeout=60)
    if sig != signal.SIGKILL:
        time.sleep(0.5)
    (st(repo) / "gate").write_text("open")                 # so a resumed gate suite completes
    return rid


def note(verdict: str, probe: str, detail: str) -> None:
    if verdict == "HELD":
        # W4-RESUMEFIX: most details are the reviewer's narrative of the EXPOSED case with the
        # observed values interpolated; read the values, not the prose.
        detail = "[observed values; prose describes the pre-fix EXPOSED case] " + detail
    RESULTS.append((verdict, probe, detail))
    print(f"{verdict:8} {probe}: {detail}", flush=True)


def report_has(repo: Path, rid: str, text: str) -> bool:
    return text in (runs(repo) / f"{rid}.log").read_text()


# ---- probes ---------------------------------------------------------------------------------

def p01_kill9_mid_suite():
    repo = sandbox("p01")
    rid = killed_run(repo, "test_multi,test_gate", wait_done=("test_multi.py",))
    st_rec = record(repo, rid)["status"]
    gate = ("running" if (ckdir(repo, rid) / "tests_test_gate.py.s1.running").exists()
            and not (ckdir(repo, rid) / "tests_test_gate.py.s1.json").exists() else "terminal")
    r = run(repo, SUITES="test_multi,test_gate", RESUME=rid)
    rec = record(repo, rid)
    by = {s["suite"]: s for s in rec["suite_results"]}
    held = (gate == "running" and "1 of 2 suites" in r.stdout and r.returncode == 0
            and by["tests/test_gate.py"]["segment"] == 2 and by["tests/test_multi.py"]["segment"] == 1
            and rec["tests_passing"] == 6)
    note("HELD" if held else "EXPOSED", "P01 kill -9 mid-suite, resume",
         f"record after SIGKILL={st_rec!r}; interrupted suite checkpoint={gate!r}; resume "
         f"reran {'1 of 2' if '1 of 2 suites' in r.stdout else '?'}; gate segment="
         f"{by['tests/test_gate.py']['segment']}; tests_passing={rec['tests_passing']} (expect 6); "
         f"resumed={rec.get('resumed')} release_eligible={rec.get('release_eligible')}")


def p01b_sigterm_orphans_suite():
    repo = sandbox("p01b")
    for p in (st(repo) / "gate", st(repo) / "gate.started"):
        p.unlink(missing_ok=True)
    pr = subprocess.Popen(["bash", str(repo / "run_tests.sh")], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, env=env(repo, SUITES="test_gate",
                                                             CHECKPOINT="1"), cwd=repo)
    end = time.time() + 60
    while not (st(repo) / "gate.started").exists() and time.time() < end:
        time.sleep(0.05)
    time.sleep(0.3)
    pr.send_signal(signal.SIGTERM)                     # the runner only, as `kill <pid>` does
    pr.wait(timeout=30)
    time.sleep(0.5)
    alive = subprocess.run(["pgrep", "-f", str(repo / "tests" / "test_gate.py")],
                           capture_output=True, text=True).stdout.split()
    (st(repo) / "gate").write_text("open")
    time.sleep(0.5)
    note("EXPOSED" if alive else "HELD", "P01b SIGTERM to the runner leaves the suite running",
         f"suite processes still alive after the runner exited on SIGTERM: {len(alive)}"
         + ("; an orphan of the interrupted segment can run alongside the resumed one"
            if alive else "; the interrupted suite died with the runner"))


def p02_torn_checkpoint_writes():
    # (a) a json that a crash left empty (no fsync before rename)
    repo = sandbox("p02a")
    rid = killed_run(repo, "test_multi,test_gate", wait_done=("test_multi.py",))
    (ckdir(repo, rid) / "tests_test_multi.py.s1.json").write_text("")
    r = run(repo, SUITES="test_multi,test_gate", RESUME=rid)
    a_ok = "2 of 2 suites" in r.stdout and r.returncode == 0
    note("HELD" if a_ok else "EXPOSED", "P02a kill during checkpoint json write (empty json)",
         f"resume reran {'2 of 2' if '2 of 2 suites' in r.stdout else 'not all'}; exit {r.returncode}"
         f"{'' if a_ok else '; ' + (r.stdout + r.stderr)[-300:]}")
    # (b) json committed, .out torn (finish writes .out non-atomically and fsyncs nothing)
    repo = sandbox("p02b")
    rid = killed_run(repo, "test_multi,test_gate", wait_done=("test_multi.py",))
    o = ckdir(repo, rid) / "tests_test_multi.py.s1.out"
    o.write_text("".join(o.read_text().splitlines(True)[:2]))
    r = run(repo, SUITES="test_multi,test_gate", RESUME=rid)
    rec = record(repo, rid)
    note("EXPOSED" if r.returncode == 0 and rec["tests_passing"] != 6 else "HELD",
         "P02b torn .out under an intact 'passed' json",
         f"resume exit {r.returncode}, status {rec['status']}, tests_passing="
         f"{rec['tests_passing']} (true value 6); json ok_count="
         f"{suite_json(repo, rid, 'test_multi.py')['ok_count']} disagrees with the .out and "
         "nothing compares them")
    # (c) .out missing under a 'passed' json -> neither rerun nor reported: stuck
    repo = sandbox("p02c")
    rid = killed_run(repo, "test_multi,test_gate", wait_done=("test_multi.py",))
    (ckdir(repo, rid) / "tests_test_multi.py.s1.out").unlink()
    r1 = run(repo, SUITES="test_multi,test_gate", RESUME=rid)
    r2 = run(repo, SUITES="test_multi,test_gate", RESUME=rid)
    stuck = ("1 of 2 suites" in r1.stdout and "NO OUTPUT: this suite never ran" in r1.stdout
             and "0 of 2 suites" in r2.stdout and r2.returncode != 0)
    note("EXPOSED" if stuck else "HELD", "P02c .out lost under a 'passed' json",
         f"resume 1: reran {'1 of 2' if '1 of 2 suites' in r1.stdout else '?'}, the suite "
         f"reported 'never ran', exit {r1.returncode}; resume 2: reran "
         f"{'0 of 2' if '0 of 2 suites' in r2.stdout else '?'}, exit {r2.returncode}: the run "
         "can never be completed by resuming, and suite_results still says "
         f"{suite_json(repo, rid, 'test_multi.py')['status']!r}")


def p03_corruption():
    # (a) truncated json
    repo = sandbox("p03a")
    rid = killed_run(repo, "test_multi,test_gate", wait_done=("test_multi.py",))
    j = ckdir(repo, rid) / "tests_test_multi.py.s1.json"
    j.write_bytes(j.read_bytes()[:40])
    r = run(repo, SUITES="test_multi,test_gate", RESUME=rid)
    note("HELD" if "2 of 2 suites" in r.stdout else "EXPOSED", "P03a truncated suite json",
         f"invalid JSON read as 'no result' -> reran {'2 of 2' if '2 of 2 suites' in r.stdout else '?'}")
    # (b) one byte flipped inside the .out: FAIL marker turned into an OK marker
    repo = sandbox("p03b")
    repo.joinpath("tests", "test_multi.py").write_text(
        SUITES["test_multi.py"] + 'print("SKIP test_m5 not on this platform")\n')
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qam", "skip")
    rid = killed_run(repo, "test_multi,test_gate", wait_done=("test_multi.py",))
    o = ckdir(repo, rid) / "tests_test_multi.py.s1.out"
    o.write_text(o.read_text().replace("SKIP test_m5", "OK   test_m5"))
    r = run(repo, SUITES="test_multi,test_gate", RESUME=rid)
    rec = record(repo, rid)
    note("EXPOSED" if rec["tests_passing"] == 7 and rec["tests_skipped_reported"] == 0 else "HELD",
         "P03b edited .out (a SKIP rewritten as OK)",
         f"accepted silently: tests_passing={rec['tests_passing']} (true 6), "
         f"tests_skipped_reported={rec['tests_skipped_reported']} (true 1)")
    # (c) status 'failed' -> 'passed' only
    repo = sandbox("p03c")
    rid = killed_run(repo, "test_flaky,test_gate", wait_done=("test_flaky.py",))
    j = ckdir(repo, rid) / "tests_test_flaky.py.s1.json"
    d = json.loads(j.read_text())
    before = d["status"]
    d["status"] = "passed"
    j.write_text(json.dumps(d, indent=2, sort_keys=True))
    runs_before = len((st(repo) / "flaky").read_text())
    r = run(repo, SUITES="test_flaky,test_gate", RESUME=rid)
    rec = record(repo, rid)
    by = {s["suite"]: s for s in rec["suite_results"]}
    held = (len((st(repo) / "flaky").read_text()) == runs_before and r.returncode != 0
            and by["tests/test_flaky.py"]["status"] == "failed"
            and "tests/test_flaky.py" in rec["failing_suites"])
    note("HELD" if held else "EXPOSED", "P03c json status edited failed->passed",
         f"was {before!r}; the suite was NOT rerun (executions {runs_before}->"
         f"{len((st(repo) / 'flaky').read_text())}); the report used the stale exit "
         f"code and failed the run (exit {r.returncode}) but suite_results says "
         f"{by['tests/test_flaky.py']['status']!r} while failing_suites={rec['failing_suites']}"
         " -- the record contradicts itself")
    # (d) full forgery: status, exit_code, ok_count and .out
    repo = sandbox("p03d")
    rid = killed_run(repo, "test_flaky,test_gate", wait_done=("test_flaky.py",))
    j = ckdir(repo, rid) / "tests_test_flaky.py.s1.json"
    d = json.loads(j.read_text())
    d.update(status="passed", exit_code=0, ok_count=1)
    j.write_text(json.dumps(d, indent=2, sort_keys=True))
    (ckdir(repo, rid) / "tests_test_flaky.py.s1.out").write_text("OK   test_flaky\n")
    r = run(repo, SUITES="test_flaky,test_gate", RESUME=rid)
    rec = record(repo, rid)
    note("EXPOSED" if r.returncode == 0 and rec["status"] == "passed" else "HELD",
         "P03d forged pass (json + .out rewritten)",
         f"resume exit {r.returncode}, record {rec['status']}, suites_failing "
         f"{rec['suites_failing']}; the suite failed the only time it ran and was counted "
         "passed; no HMAC, hash or chain is checked")


def p04_source_changes():
    # (a) tracked file edited
    repo = sandbox("p04a")
    rid = killed_run(repo, "test_inputs,test_gate", wait_done=("test_inputs.py",))
    (repo / "tests" / "test_multi.py").write_text('print("OK   changed")\n')
    r = run(repo, SUITES="test_inputs,test_gate", RESUME=rid)
    note("HELD" if r.returncode == 4 and "dirty_content_sha256" in r.stderr else "EXPOSED",
         "P04a tracked source edited between kill and resume",
         f"exit {r.returncode}; {r.stderr.strip().splitlines()[0][:110] if r.stderr.strip() else ''}")
    # (b) untracked helper edited: only its name is in the key
    repo = sandbox("p04b")
    rid = killed_run(repo, "test_inputs,test_gate", wait_done=("test_inputs.py",))
    (repo / "tests" / "helper_untracked.py").write_text("VALUE = 2  # edited\n")
    r = run(repo, SUITES="test_inputs,test_gate", RESUME=rid)
    fresh = subprocess.run([PY, "tests/test_inputs.py"], cwd=repo, capture_output=True, text=True)
    note("EXPOSED" if r.returncode == 0 and fresh.returncode != 0 else "HELD",
         "P04b untracked file edited between kill and resume",
         f"resume exit {r.returncode} (accepted); the same suite run fresh now exits "
         f"{fresh.returncode}: {fresh.stdout.strip()}")
    # (c) git-ignored fixture edited
    repo = sandbox("p04c")
    rid = killed_run(repo, "test_inputs,test_gate", wait_done=("test_inputs.py",))
    (repo / "fixtures" / "value.txt").write_text("2\n")
    r = run(repo, SUITES="test_inputs,test_gate", RESUME=rid)
    fresh = subprocess.run([PY, "tests/test_inputs.py"], cwd=repo, capture_output=True, text=True)
    note("EXPOSED" if r.returncode == 0 and fresh.returncode != 0 else "HELD",
         "P04c git-ignored fixture edited between kill and resume",
         f"resume exit {r.returncode} (accepted); fresh run exits {fresh.returncode}: "
         f"{fresh.stdout.strip()}")
    # (d) the commit itself moved
    repo = sandbox("p04d")
    rid = killed_run(repo, "test_inputs,test_gate", wait_done=("test_inputs.py",))
    (repo / "tests" / "test_multi.py").write_text('print("OK   changed")\n')
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qam", "m")
    r = run(repo, SUITES="test_inputs,test_gate", RESUME=rid)
    note("HELD" if r.returncode == 4 and "git_sha" in r.stderr else "EXPOSED",
         "P04d new commit between kill and resume", f"exit {r.returncode}; refused on git_sha")


def p05_env_changes():
    # (a) lockfile edited
    repo = sandbox("p05a")
    rid = killed_run(repo, "test_inputs,test_gate", wait_done=("test_inputs.py",))
    (repo / "requirements.lock").write_text("fixture==2.0\n")
    r = run(repo, SUITES="test_inputs,test_gate", RESUME=rid)
    note("HELD" if r.returncode == 4 and "locks.requirements.lock" in r.stderr else "EXPOSED",
         "P05a lockfile edited", f"exit {r.returncode}; refused on locks.requirements.lock")
    # (b) a package changed inside the same venv (pip install without touching the lock)
    repo = sandbox("p05b")
    subprocess.run([PY, "-m", "venv", "--without-pip", "--system-site-packages",
                    str(repo / "venv")], check=True)
    vpy = str(repo / "venv" / "bin" / "python")
    site = subprocess.run([vpy, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                          capture_output=True, text=True, check=True).stdout.strip()
    Path(site, "depmod.py").write_text("VALUE = 1\n")
    rid = killed_run(repo, "test_inputs,test_gate", wait_done=("test_inputs.py",), PY=vpy)
    Path(site, "depmod.py").write_text("VALUE = 2  # v2\n")          # "pip install depmod==2"
    r = run(repo, SUITES="test_inputs,test_gate", RESUME=rid, PY=vpy)
    fresh = subprocess.run([vpy, "tests/test_inputs.py"], cwd=repo, capture_output=True, text=True)
    note("EXPOSED" if r.returncode == 0 and fresh.returncode != 0 else "HELD",
         "P05b installed package changed in the same venv (lock untouched)",
         f"resume exit {r.returncode} (accepted: the key holds the interpreter path, version "
         f"and prefix, not the installed set); fresh run exits {fresh.returncode}: "
         f"{fresh.stdout.strip()}")
    # (c) PYTHONPATH (not in the env fingerprint) redirects an import
    repo = sandbox("p05c")
    rid = killed_run(repo, "test_inputs,test_gate", wait_done=("test_inputs.py",))
    alt = WORK / "alt-p05c"; alt.mkdir()
    (alt / "depmod.py").write_text("VALUE = 2\n")
    r = run(repo, SUITES="test_inputs,test_gate", RESUME=rid, PYTHONPATH=str(alt))
    fresh = subprocess.run([PY, "tests/test_inputs.py"], cwd=repo, capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": str(alt)})
    note("EXPOSED" if r.returncode == 0 and fresh.returncode != 0 else "HELD",
         "P05c PYTHONPATH changed between kill and resume",
         f"resume exit {r.returncode} (accepted); fresh run under the new environment exits "
         f"{fresh.returncode}")
    # (d) an in-fingerprint flag
    repo = sandbox("p05d")
    rid = killed_run(repo, "test_inputs,test_gate", wait_done=("test_inputs.py",))
    r = run(repo, SUITES="test_inputs,test_gate", RESUME=rid, BRAMBLELOOP_X="1")
    note("HELD" if r.returncode == 4 and "env" in r.stderr else "EXPOSED",
         "P05d BRAMBLELOOP_* flag added", f"exit {r.returncode}; refused on env")


def p06_copied_checkpoints():
    # (a) a result copied in from another run of the same SHA
    repo = sandbox("p06a")
    (st(repo) / "flaky").write_text("x")          # run A: the flaky suite passes
    (st(repo) / "gate").write_text("open")                  # run A's gate suite passes at once
    run(repo, SUITES="test_flaky,test_gate", CHECKPOINT="1")
    rid_a = sorted(d.name for d in runs(repo).iterdir() if d.is_dir() and d.name != "locks")[0]
    (st(repo) / "flaky").unlink()                 # run B's flaky suite will fail
    rid_b = killed_run(repo, "test_flaky,test_gate", wait_done=("test_flaky.py",))
    b_status = suite_json(repo, rid_b, "test_flaky.py")["status"]
    for ext in (".json", ".out"):
        shutil.copy(ckdir(repo, rid_a) / f"tests_test_flaky.py.s1{ext}",
                    ckdir(repo, rid_b) / f"tests_test_flaky.py.s1{ext}")
    execs_before = len((st(repo) / "flaky").read_text())
    r = run(repo, SUITES="test_flaky,test_gate", RESUME=rid_b)
    rec = record(repo, rid_b)
    by = {s["suite"]: s for s in rec["suite_results"]}
    note("EXPOSED" if r.returncode == 0 and rec["status"] == "passed"
         and len((st(repo) / "flaky").read_text()) == execs_before else "HELD",
         "P06a suite result copied from another run_id",
         f"run B's own result was {b_status!r}; A's 'passed' copied over it was accepted "
         f"(exit {r.returncode}; flaky executions {execs_before}->"
         f"{len((st(repo) / 'flaky').read_text())}, i.e. not rerun); run B's record "
         f"lists it as segment {by['tests/test_flaky.py']['segment']} of run {rid_b}: a "
         "result carries no run id, host or hash, so nothing distinguishes the copy")
    # (b) a whole checkpoint directory copied to a fresh id and resumed
    repo = sandbox("p06b")
    rid = killed_run(repo, "test_multi,test_gate", wait_done=("test_multi.py",))
    fake = "20990101T000000Z-1"
    shutil.copytree(ckdir(repo, rid), ckdir(repo, fake))
    r = run(repo, SUITES="test_multi,test_gate", RESUME=fake)
    man = json.loads((ckdir(repo, fake) / "manifest.json").read_text())
    note("EXPOSED" if r.returncode == 0 else "HELD", "P06b checkpoint dir copied to another run id",
         f"RESUME={fake} accepted (exit {r.returncode}); its manifest still says run_id "
         f"{man['run_id']!r} and nothing compares it")


def p07_flake_laundering():
    repo = sandbox("p07")
    r1 = run(repo, SUITES="test_flaky,test_multi", CHECKPOINT="1")   # completes, NOT interrupted
    rid = sorted(d.name for d in runs(repo).iterdir() if d.is_dir() and d.name != "locks")[0]
    first = record(repo, rid)
    r2 = run(repo, SUITES="test_flaky,test_multi", RESUME=rid)
    rec = record(repo, rid)
    out = (ckdir(repo, rid) / "tests_test_flaky.py.s1.out").read_text()
    note("EXPOSED" if r1.returncode == 1 and r2.returncode == 0 and rec["status"] == "passed"
         else "HELD", "P07 RESUME of a completed, failed run (retry-until-green)",
         f"run 1 completed {first['status']} (exit {r1.returncode}, no interruption); RESUME "
         f"reran only the failure, which passed: record now {rec['status']}, failing_suites="
         f"{rec['failing_suites']}; the checkpointed output of the failed attempt was "
         f"overwritten (now: {out.strip()!r}); only segments[0].finished_utc hints it ran")


def p08_leak_strict_erased():
    repo = sandbox("p08")
    rid = killed_run(repo, "test_leaky,test_gate", wait_done=("test_leaky.py",),
                     TMP_LEAK_STRICT="1")
    leaky_status = suite_json(repo, rid, "test_leaky.py")["status"]
    r = run(repo, SUITES="test_leaky,test_gate", RESUME=rid, TMP_LEAK_STRICT="1")
    rec = record(repo, rid)
    repo2 = sandbox("p08ctl")
    (st(repo2) / "gate").write_text("open")                 # gate already open: straight through
    c = run(repo2, SUITES="test_leaky,test_gate", TMP_LEAK_STRICT="1")
    note("EXPOSED" if c.returncode != 0 and r.returncode == 0 else "HELD",
         "P08 TMP_LEAK_STRICT failure erased by resume",
         f"a fresh strict run fails the leaky suite (exit {c.returncode}); the checkpoint wrote "
         f"{leaky_status!r} before the leak census ran, restore writes '0 0' for the leak, and the "
         f"resumed run passes (exit {r.returncode}, tmp_leak_entries="
         f"{rec['tmp_leak_entries']})")


def p09_release_downgrade_fails_open():
    _p09(control=True)
    _p09(control=False)


def _p09(control: bool):
    repo = sandbox("p09ctl" if control else "p09", n_filler=100)   # >= 100: a full-scope run
    git(repo, "add", "tests/helper_untracked.py")      # a clean tree, as a release run needs
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "c")
    act = st(repo) / "act.py"
    act.write_text("import os, glob\n"
                   "for m in glob.glob(os.environ['CKROOT'] + '/*/manifest.json'):\n"
                   "    os.unlink(m)\n")
    # full scope cannot be driven through killed_run's SUITES filter; done inline
    for p in (st(repo) / "gate", st(repo) / "gate.started"):
        p.unlink(missing_ok=True)
    (st(repo) / "flaky").write_text("x")
    same = dict(CKROOT=str(runs(repo)), GATE_ACTION=str(act) if not control else "")
    e = env(repo, CHECKPOINT="1", JOBS="4", **same)
    e.pop("SUITES", None)
    p = subprocess.Popen(["nice", "-n", "19", "bash", str(repo / "run_tests.sh")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=e, cwd=repo,
                         start_new_session=True)
    end = time.time() + 120
    while not (st(repo) / "gate.started").exists() and time.time() < end:
        time.sleep(0.05)
    time.sleep(1.0)
    os.killpg(p.pid, signal.SIGKILL); p.wait()
    rid = sorted(d.name for d in runs(repo).iterdir() if d.is_dir() and d.name != "locks")[0]
    # the resumed segment: the gate suite (which reruns) removes the manifest before finalize
    # reads it -- standing in for any finalize failure (ENOSPC, a crash, a SIGKILL after
    # write_record), all of which are ignored by run_tests.sh
    (st(repo) / "gate").write_text("open")
    e = env(repo, RESUME=rid, JOBS="4", **same)
    r = subprocess.run(["nice", "-n", "19", "bash", str(repo / "run_tests.sh")],
                       capture_output=True, text=True, env=e, cwd=repo, timeout=300)
    rec = record(repo, rid)
    spec = importlib.util.spec_from_file_location("dg", ROOT.parent / "ops" / "deploy_guard.py")
    dg = importlib.util.module_from_spec(spec); spec.loader.exec_module(dg)
    picked = dg.latest_suite(runs(repo), sha=git(repo, "rev-parse", "HEAD"), eligible_only=True)
    log_ok = dg._log_confirms(picked, repo) if picked else "n/a"
    if control:
        note("HELD" if rec.get("release_eligible") is False and rec.get("resumed") is True
             and picked is None else "EXPOSED", "P09-control resumed full run, finalize intact",
             f"exit {r.returncode}; release_eligible={rec.get('release_eligible')}, resumed="
             f"{rec.get('resumed')}; deploy_guard eligible pick: "
             f"{'this run' if picked else 'nothing'}")
        return
    note("EXPOSED" if rec.get("release_eligible") is True and picked else "HELD",
         "P09 the resumed-run downgrade fails open",
         f"resumed full run exit {r.returncode}; record release_eligible="
         f"{rec.get('release_eligible')}, resumed={rec.get('resumed')!r}, checkpoint key "
         f"present={'checkpoint' in rec}; deploy_guard.latest_suite(eligible_only=True) "
         f"returned {'this resumed run' if picked else 'nothing'}; _log_confirms -> {log_ok!r}")


def p09b_guard_reads_no_provenance():
    src = (ROOT.parent / "ops" / "deploy_guard.py").read_text()
    note("EXPOSED" if "resumed" not in src and "checkpoint" not in src else "HELD",
         "P09b deploy_guard reads no resume provenance",
         "ops/deploy_guard.py contains neither 'resumed' nor 'checkpoint'; release_eligible "
         "is the only bit between a resumed run and `record`")


def p10_aggregation():
    repo = sandbox("p10")
    rid = killed_run(repo, "test_multi,test_leaky,test_gate",
                     wait_done=("test_multi.py", "test_leaky.py"))
    r = run(repo, SUITES="test_multi,test_leaky,test_gate", RESUME=rid)
    rec = record(repo, rid)
    log = (runs(repo) / f"{rid}.log").read_text()
    names = [s["suite"] for s in rec["suite_results"]]
    exact = (rec["tests_passing"] == 7 and len(names) == len(set(names)) == 3
             and log.count("== tests/test_multi.py") == 1
             and log.count("TOTAL PASSING") == 1)
    note("HELD" if exact else "EXPOSED", "P10 union of fresh and resumed results",
         f"tests_passing={rec['tests_passing']} (expect 7), suites listed once each="
         f"{len(names) == len(set(names))}, one TOTAL line={log.count('TOTAL PASSING') == 1}")
    note("EXPOSED" if rec["tmp_leak_entries"] == 0 else "HELD",
         "P10b leak census of resumed suites",
         f"tmp_leak_entries={rec['tmp_leak_entries']} although test_leaky leaked 1 entry in "
         "segment 1: restore writes '0 0' for every reused suite")


def main() -> int:
    probes = [p01_kill9_mid_suite, p01b_sigterm_orphans_suite, p02_torn_checkpoint_writes,
              p03_corruption, p04_source_changes, p05_env_changes, p06_copied_checkpoints,
              p07_flake_laundering, p08_leak_strict_erased, p09_release_downgrade_fails_open,
              p09b_guard_reads_no_provenance,
              p10_aggregation]
    only = set(sys.argv[1:])
    broken = 0
    for p in probes:
        if only and not any(p.__name__.startswith(o) for o in only):
            continue
        try:
            p()
        except Exception as exc:                        # a probe that cannot run is reported
            broken += 1
            note("ERROR", p.__name__, f"{type(exc).__name__}: {exc}")
    held = sum(1 for v, _, _ in RESULTS if v == "HELD")
    exposed = sum(1 for v, _, _ in RESULTS if v == "EXPOSED")
    print(f"\nPROBES: {held} held, {exposed} exposed, {broken} could not run")
    shutil.rmtree(WORK, ignore_errors=True)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
