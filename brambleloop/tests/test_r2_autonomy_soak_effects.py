"""R2 autonomy, audit ddf9c6e M-3: the soak's "no duplicated external effect" criterion reads
effect records (reclaims, write-ahead intents, cost entries), so a SIGKILLed worker whose
successor re-applies an unguarded effect FAILS it -- it used to read PASS because only stale
completion refusals were counted.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_autonomy_soak_effects.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from r2_autonomy_harness import SRC, run_tests

CHILD = r'''
import os, sys, time
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
sys.path.insert(0, SRC)
from brambleloop.core.db import Database
from brambleloop.runtime.worker import Worker, handlers
from brambleloop.core.models import Phase
mode, name, guarded = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
db = Database(DB)
@handlers.register("ops.queue_check")
def h(ctx):
    if guarded:
        with ctx.effect("test.remote_write", f"job:{ctx.job.id}") as intent:
            open(EFF, "a").write(f"effect by {name}\n")
            if mode == "hang":
                time.sleep(120)
            intent.applied("remote:1")
    else:
        open(EFF, "a").write(f"effect by {name}\n")
        if mode == "hang":
            time.sleep(120)
    return {"ran": True, "moved": 1}
w = Worker(db, name, phase=Phase.SHADOW, lease_seconds=2)
w.run_once()
'''


def _sigkill_scenario(guarded: bool):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import utcnow
    from brambleloop.queue.durable import JobQueue

    tmp = tempfile.mkdtemp(prefix="r2-m3-")
    db_url, eff = f"sqlite:///{tmp}/k.sqlite", Path(tmp) / "effects.txt"
    child = Path(tmp) / "child.py"
    child.write_text(f"SRC={SRC!r}\nDB={db_url!r}\nEFF={str(eff)!r}\n" + CHILD)
    db = Database(db_url)
    db.create_all()
    Registry(db).seed_defaults()
    start = utcnow() - timedelta(seconds=1)
    JobQueue(db, lease_seconds=2).enqueue("orchestrator", "ops.queue_check", {"x": 1},
                                          idempotency_key="r2-m3-kill")
    env = dict(os.environ, PYTHONPATH=SRC)
    p = subprocess.Popen([sys.executable, str(child), "hang", "W1", "1" if guarded else "0"],
                         env=env)
    for _ in range(300):
        if eff.exists():
            break
        time.sleep(0.1)
    assert eff.exists(), "the first worker never reached its effect"
    os.kill(p.pid, signal.SIGKILL)
    p.wait()
    time.sleep(2.5)                                       # lease (2 s) expires
    subprocess.run([sys.executable, str(child), "ok", "W2", "1" if guarded else "0"],
                   env=env, capture_output=True, text=True, timeout=300)
    effects = eff.read_text().strip().splitlines()
    from brambleloop.ops import slo

    report = slo.soak_report(db, start=start, end=utcnow())
    crit = [c for c in report["criteria"] if c["criterion"].startswith(
        "no duplicated external effect")]
    assert len(crit) == 1, report["criteria"]
    return effects, crit[0]


def test_sigkill_double_apply_fails_the_soak_criterion():
    effects, crit = _sigkill_scenario(guarded=False)
    assert len(effects) == 2, effects                     # the repro: applied twice
    assert crit["result"] == "FAIL", crit
    assert crit["evidence"]["reclaimed_jobs"] == 1, crit
    assert crit["evidence"]["violations"], crit


def test_a_guarded_effect_is_not_repeated_and_the_criterion_holds():
    effects, crit = _sigkill_scenario(guarded=True)
    assert len(effects) == 1, effects                     # the successor was refused
    assert crit["evidence"]["reclaimed_jobs"] == 1, crit
    assert crit["evidence"]["duplicate_attempts_refused_by_guard"] >= 1, crit
    assert crit["evidence"]["uncertain_effects"] == 0, crit   # killed mid-effect: CLAIMED
    assert crit["result"] == "PASS", crit


if __name__ == "__main__":
    run_tests(globals())
