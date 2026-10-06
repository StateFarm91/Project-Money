"""W3 lane D: Laura's continuity (spec/07 item 13; D-FB-13 model independence).

Across a model/provider swap, a process restart, a scheduler restart and a context reset her
identity, charter, policies and history are unchanged, and the same company state yields the
same executive decisions whichever cognition label is configured.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.laura import executive, identity  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Scheduler, Worker  # noqa: E402

MODEL_ENV = "BRAMBLELOOP_LAURA_MODEL"


def boot(path: str) -> Database:
    db = Database(f"sqlite:///{path}")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def drain(db, limit=60):
    w = Worker(db, "w3d-cont")
    for _ in range(limit):
        if not w.run_once():
            break


def snapshot(db) -> dict:
    cur = identity.current(db)
    rec = cur["record"]
    hist = executive.history(db, limit=10_000)
    return {"sha": cur["sha256"], "version": cur["version"], "name": rec["name"],
            "role": rec["role"], "charter": rec["charter"], "authority": rec["authority"],
            "constitution": rec["constitution"], "voice": rec["voice"],
            "visual": rec["visual_identity"]["identity_id"],
            "history": {h["key"]: [h["kind"], h["subject"], h["reason"], h["at"],
                                   h["identity_sha256"]] for h in hist},
            "priorities": {p["key"]: p["created_at"] for p in executive.priorities(db,
                                                                                  limit=500)}}


def assert_continuous(before: dict, after: dict, where: str):
    for k in ("sha", "version", "name", "role", "charter", "authority", "constitution",
              "voice", "visual"):
        assert before[k] == after[k], f"{where}: {k} changed"
    for key, row in before["history"].items():
        assert after["history"].get(key) == row, f"{where}: history {key} changed or lost"
    for key, created in before["priorities"].items():
        assert after["priorities"].get(key) == created, f"{where}: priority {key} lost"


def _with_model(model):
    old = os.environ.get(MODEL_ENV)
    if model is None:
        os.environ.pop(MODEL_ENV, None)
    else:
        os.environ[MODEL_ENV] = model
    return old


def test_continuity_across_model_swap_restart_scheduler_and_context_reset():
    tmp = tempfile.mkdtemp(prefix="w3d-cont-")
    path = f"{tmp}/company.sqlite"
    old = _with_model("provider-a/model-1")
    try:
        db = boot(path)
        executive.tick(db)
        drain(db)
        executive.tick(db)
        s0 = snapshot(db)
        assert s0["history"], "no history to preserve"
        assert {h["cognition"]["model"] for h in executive.history(db)} == {
            "provider-a/model-1"}

        # 1. model / provider swap
        _with_model("provider-b/model-9")
        drain(db)                  # results arrive, so the post-swap tick has work to review
        r = executive.tick(db)
        s1 = snapshot(db)
        assert_continuous(s0, s1, "model swap")
        new = [h for h in executive.history(db) if h["key"] not in s0["history"]]
        assert new, "the post-swap tick recorded nothing"
        assert all(h["cognition"]["model"] == "provider-b/model-9" for h in new)
        assert r["identity_sha256"] == s0["sha"]

        # 2. process restart: a fresh interpreter on the same durable store
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), MODEL_ENV: "provider-c/model-2"}
        code = ("import json,sys; from brambleloop.core.db import Database; "
                "import brambleloop.runtime.pipeline; "
                "from brambleloop.laura import identity, executive; "
                f"db=Database('sqlite:///{path}'); r=executive.tick(db); "
                "c=identity.current(db); "
                "print(json.dumps({'sha': c['sha256'], 'v': c['version'], "
                "'n': len(executive.history(db, limit=10000)), 'tick_sha': "
                "r['identity_sha256']}))")
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                             text=True, timeout=600, cwd=tmp)
        assert out.returncode == 0, out.stderr[-2000:]
        child = json.loads(out.stdout.strip().splitlines()[-1])
        assert child["sha"] == child["tick_sha"] == s0["sha"] and child["v"] == 2, child  # genesis + D-FB-14
        s2 = snapshot(db)
        assert_continuous(s1, s2, "process restart")

        # 3. scheduler restart: a new Scheduler enqueues her cadence; the worker runs it
        enq = Scheduler(boot(path)).tick()
        assert "laura_executive" in enq, enq
        drain(Database(f"sqlite:///{path}"))
        s3 = snapshot(db)
        assert_continuous(s2, s3, "scheduler restart")

        # 4. context reset: every Laura module re-imported, a new Database object
        import brambleloop.laura.core.constitution as c_mod
        import brambleloop.laura.core.identity as i_mod
        import brambleloop.laura.executive.loop as l_mod

        for mod in (i_mod, c_mod, l_mod):
            importlib.reload(mod)
        db4 = Database(f"sqlite:///{path}")
        s4 = snapshot(db4)
        assert_continuous(s3, s4, "context reset")
        assert identity.summary(db4)["status"] == "OK"
    finally:
        _with_model(old)


def test_same_state_same_decisions_whichever_model_is_configured():
    tmp = tempfile.mkdtemp(prefix="w3d-det-")
    base = f"{tmp}/base.sqlite"
    db = boot(base)
    executive.tick(db)
    drain(db)
    db.engine.dispose()
    outcomes = {}
    for model in ("provider-a/model-1", "provider-b/model-9"):
        p = f"{tmp}/{model.replace('/', '_')}.sqlite"
        shutil.copy(base, p)
        old = _with_model(model)
        try:
            dbm = Database(f"sqlite:///{p}")
            r = executive.tick(dbm, now=None)
            outcomes[model] = (sorted(k for k in r["decisions_by_kind"].items()),
                               sorted(p["key"] for p in r["priorities"]),
                               sorted(json.dumps(o, sort_keys=True) for o in r["outcomes"]))
        finally:
            _with_model(old)
    a, b = outcomes.values()
    assert a == b, outcomes
    assert a[0], "the tick did nothing to compare"


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
