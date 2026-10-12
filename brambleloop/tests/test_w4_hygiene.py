"""W4-HYGIENE: F-146 one cleanup trap, F-149 disk growth alarm, F-150 environment-failure
classification in run_tests.sh."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.ops import health  # noqa: E402

SCRIPT = ROOT / "run_tests.sh"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


# ---- F-146 -----------------------------------------------------------------------------------

def test_run_tests_has_exactly_one_exit_trap_and_int_term_only_mark_the_exit():
    code = [ln for ln in SCRIPT.read_text().splitlines() if not ln.lstrip().startswith("#")]
    traps = [ln.strip() for ln in code if re.match(r"\s*trap\s", ln)]
    exit_traps = [t for t in traps if re.search(r"\bEXIT\b", t) and not t.startswith("trap -")]
    assert exit_traps == ["trap _brambleloop_cleanup EXIT"], traps
    assert "trap 'exit 130' INT TERM" in traps


# ---- F-149 -----------------------------------------------------------------------------------

def _facts(temp, free):
    return {"temp_dirs_left_behind": temp,
            "filesystems": {"tmp": {"free_gb": free, "total_gb": 100.0}}}


def _series(db, points):
    for i, (temp, free) in enumerate(points):
        health.record_disk_sample(db, _facts(temp, free), now=NOW - timedelta(hours=len(points) - i))


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def test_too_few_samples_is_unknown_never_ok():
    db = _db()
    _series(db, [(1, 50.0), (1, 50.0)])
    assert health.disk_growth(db, now=NOW)["state"] == "UNKNOWN"


def test_a_steady_disk_is_ok():
    db = _db()
    _series(db, [(2, 50.0)] * 6)
    g = health.disk_growth(db, now=NOW)
    assert g["state"] == "OK" and g["projected_hours_to_full"] is None


def test_sustained_temp_dir_growth_alarms_before_the_disk_is_low():
    db = _db()
    _series(db, [(0, 50.0), (8, 50.0), (16, 50.0), (24, 50.0), (32, 50.0)])
    g = health.disk_growth(db, now=NOW)
    assert g["state"] == "ALARM" and "temp dirs rising" in g["why"], g


def test_a_disk_that_will_fill_within_a_day_alarms():
    db = _db()
    _series(db, [(1, 12.0), (1, 9.0), (1, 6.0), (1, 3.0)])
    g = health.disk_growth(db, now=NOW)
    assert g["state"] == "ALARM" and g["projected_hours_to_full"] <= 24, g


def test_one_sample_per_minute_and_unreadable_free_space_is_none():
    db = _db()
    assert health.record_disk_sample(db, _facts(1, 5.0), now=NOW) is not None
    assert health.record_disk_sample(db, _facts(1, 5.0), now=NOW) is None
    p = health.record_disk_sample(db, {"temp_dirs_left_behind": 0,
                                       "filesystems": {"tmp": {"error": "unreadable"}}},
                                  now=NOW + timedelta(minutes=1))
    assert p["free_gb"] is None


def test_the_health_sweep_records_the_sample_and_raises_the_growth_incident():
    src = (ROOT / "src/brambleloop/runtime/release.py").read_text()
    sweep = src[src.index("def handle_health_sweep"):]
    sweep = sweep[:sweep.index("\n@handlers.register")]
    assert "health.record_disk_sample(ctx.db, health.disk_facts())" in sweep
    assert 'signature="disk:growth"' in sweep


# ---- F-150 -----------------------------------------------------------------------------------

def _sandbox(suites: dict[str, str]) -> Path:
    repo = Path(tempfile.mkdtemp(prefix="hyg-"))
    (repo / "tests").mkdir()
    shutil.copy(SCRIPT, repo / "run_tests.sh")
    for name, body in suites.items():
        (repo / "tests" / name).write_text(body)
    (repo / ".gitignore").write_text("artifacts/\n")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
                  "-m", "s"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return repo


def test_a_failing_suite_that_names_an_environment_cause_is_classified():
    disk = ('import sys\nprint("OK   test_a")\n'
            'print("OSError: [Errno 28] No space left on device")\nsys.exit(1)\n')
    plain = 'import sys\nprint("OK   test_a")\nprint("FAIL test_b assertion")\nsys.exit(1)\n'
    repo = _sandbox({"test_disk.py": disk, "test_plain.py": plain})
    try:
        env = {k: v for k, v in os.environ.items()
               if k not in ("SUITES", "REQUIRE_CLEAN", "THEN_FULL", "ALLOW_PARALLEL",
                            "SUITE_RECORD_DIR", "JOBS")}
        r = subprocess.run(["bash", str(repo / "run_tests.sh")], capture_output=True, text=True,
                           env={**env, "PY": sys.executable, "JOBS": "1",
                                "SUITES": "test_disk,test_plain"}, timeout=120)
        assert r.returncode == 1, r.stdout + r.stderr
        assert "ENVIRONMENT FAILURE (disk)" in r.stdout
        assert r.stdout.count("ENVIRONMENT FAILURE") == 1, r.stdout
        [rec] = [json.loads(p.read_text()) for p in (repo / "artifacts/suite_runs").glob("*.json")]
        assert rec["environment_failures"] == ["tests/test_disk.py:disk"]
        assert rec["suites_failing"] == 2, "a classified failure is still a failure"
    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
