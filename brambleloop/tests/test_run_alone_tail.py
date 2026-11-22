"""run_tests.sh runs the suites in scripts/suite_run_alone.txt ALONE, after the parallel phase.

test_mc_perf's verdicts are wall-clock route budgets of the machine itself, so under the
parallel phase a neighbouring suite's CPU decided them (inventory 20261122, shard idx 1: three
different routes over budget in three runs). The budgets are unchanged; only the schedule moves.
This drives the real runner in a sandbox with a fast suite and a 'timing' suite, and asserts
that the timing suite started only after every other suite had finished.

Run: cd brambleloop && python3 tests/test_run_alone_tail.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_KNOBS = ("SUITES", "THEN_FULL", "JOBS", "REQUIRE_CLEAN", "ATTACH", "ALLOW_PARALLEL",
          "TAKEOVER", "SUITE_REGISTRY", "CHECKPOINT", "CHECKPOINT_TOOL", "RESUME", "SHARD",
          "TMP_LEAK_STRICT")


def test_mc_perf_is_declared_run_alone():
    lines = [l.split("#", 1)[0].strip() for l in
             (ROOT / "scripts" / "suite_run_alone.txt").read_text().splitlines()]
    assert "tests/test_mc_perf.py" in [l for l in lines if l]


def test_a_run_alone_suite_starts_after_every_other_suite_finished():
    box = Path(tempfile.mkdtemp())
    try:
        (box / "tests").mkdir()
        (box / "scripts").mkdir()
        shutil.copy(ROOT / "run_tests.sh", box / "run_tests.sh")
        for helper in ("_tmp.py",):
            if (ROOT / "tests" / helper).exists():
                shutil.copy(ROOT / "tests" / helper, box / "tests" / helper)
        stamp = box / "stamps"
        stamp.mkdir()
        body = ("import os,sys,time,pathlib\n"
                "s=pathlib.Path(os.environ['STAMPS'])\n"
                "n=pathlib.Path(sys.argv[0]).stem\n"
                "(s/(n+'.start')).write_text(repr(time.time()))\n"
                "time.sleep({d})\n"
                "(s/(n+'.end')).write_text(repr(time.time()))\n"
                "print('OK   t')\nprint('1 passed, 0 failed')\n")
        for i in range(105):   # the runner refuses a discovery of fewer than 100 suites
            (box / "tests" / f"test_fill{i:03d}.py").write_text(body.format(d=0))
        (box / "tests" / "test_slowpar.py").write_text(body.format(d=1.5))
        (box / "tests" / "test_timing.py").write_text(body.format(d=0))
        (box / "scripts" / "suite_run_alone.txt").write_text("# test\ntests/test_timing.py\n")
        env = {k: v for k, v in os.environ.items() if k not in _KNOBS}
        env.update(STAMPS=str(stamp), JOBS="4", SUITE_REGISTRY="0", PY=sys.executable,
                   SUITES="tests/test_slowpar.py tests/test_timing.py tests/test_fill000.py",
                   TMPDIR=str(box))
        subprocess.run(["git", "init", "-q"], cwd=box, check=True)
        r = subprocess.run(["bash", "run_tests.sh"], cwd=box, env=env, capture_output=True,
                           text=True, timeout=300)
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
        start = float((stamp / "test_timing.start").read_text())
        others = [float((stamp / f"{n}.end").read_text()) for n in ("test_slowpar", "test_fill000")]
        assert start >= max(others), (start, others)
    finally:
        shutil.rmtree(box, ignore_errors=True)


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_")):
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name} {exc!r}"[:2000])
    print(f"{2 - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
