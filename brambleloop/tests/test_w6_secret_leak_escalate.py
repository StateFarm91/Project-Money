"""W6 P0-SECRET-LEAK-ESCALATE: a secret caught by the F-159 log guard becomes ONE incident and
ONE owner rotation action, through the real health sweep run by a Worker on a SQLite file.

* a planted fake secret in a log line -> exactly one `secret_leak:` incident and one
  `secret_leak_rotation:` owner action naming the variable to rotate in Railway;
* a repeat sweep, and the same secret logged again, add nothing;
* the value is absent from every DB row (incl. audit rows and job outputs) and from every log
  line the process emitted -- asserted by scanning the SQLite file and the captured log;
* a secret no environment variable holds is still escalated, keyed on pattern+fingerprint;
* a clean log produces nothing.

Every "secret" below is assembled at runtime from fragments and is fake.
Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w6_secret_leak_escalate.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import io
import logging
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["BRAMBLELOOP_PHASE"] = "shadow"

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.build2 import reachability  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, Job, JobStatus, OwnerAction, Phase  # noqa: E402
from brambleloop.ops import log_secret_guard as G  # noqa: E402
from brambleloop.ops import secret_leak  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES, Worker  # noqa: E402

# Fake, assembled so this file carries no secret-shaped literal.
FAKE_KEY = "sk" + "-ant-" + "api03-" + "Zq7Wm2" * 7
FAKE_GH = "gh" + "p_" + "R4nd0mT0k3n" * 3 + "abc"
VAR = "ANTHROPIC_API_KEY"

LOG = io.StringIO()
_handler = logging.StreamHandler(LOG)
_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
logging.getLogger().addHandler(_handler)
logging.getLogger().setLevel(logging.INFO)
G.install()  # the real F-159 guard, attached to the handler above


def _db() -> tuple[Database, str]:
    path = os.path.join(tempfile.mkdtemp(prefix="w6_secret_"), "leak.sqlite")
    db = Database(f"sqlite:///{path}")
    db.create_all()
    Registry(db).seed_defaults()
    return db, path


def _sweep(db, key: str) -> dict:
    JobQueue(db).enqueue("orchestrator", "ops.health", {"cadence": "health_sweep"},
                         priority=0, idempotency_key=key)
    with db.session() as s:
        job_id = s.scalar(select(Job.id).where(Job.job_type == "ops.health",
                                               Job.status == JobStatus.PENDING))
    assert Worker(db, "w6-secret", phase=Phase.SHADOW, job_types=["ops.health"]).run_once()
    with db.session() as s:
        row = s.get(Job, job_id)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        return dict(row.outputs or {})


def _leaks(db):
    with db.session() as s:
        inc = [(i.signature, i.severity, i.resolved, dict(i.detail or {}))
               for i in s.scalars(select(Incident).where(
                   Incident.signature.like(secret_leak.SIGNATURE + "%")))]
        act = [(a.requirement_key, a.action, a.reason, a.max_cost_cad, a.minutes,
                a.consequence_of_delay, a.done)
               for a in s.scalars(select(OwnerAction).where(
                   OwnerAction.requirement_key.like(secret_leak.KEY_PREFIX + "%")))]
    return inc, act


def _dump(path: str) -> str:
    con = sqlite3.connect(path)
    try:
        return "\n".join(con.iterdump())
    finally:
        con.close()


def _assert_absent(value: str, path: str) -> None:
    tail = value[-20:]
    dump = _dump(path)
    assert value not in dump and tail not in dump, "secret value persisted in the DB"
    logged = LOG.getvalue()
    assert value not in logged and tail not in logged, "secret value reached the log output"


def test_a_clean_log_produces_nothing():
    G.GUARD.caught.clear()
    logging.getLogger("brambleloop.test").info("an ordinary line with no credential in it")
    db, _path = _db()
    out = _sweep(db, "clean-1")
    assert out["secret_leak"]["status"] == "CLEAN", out["secret_leak"]
    inc, act = _leaks(db)
    assert inc == [] and act == [], (inc, act)


def test_a_planted_secret_opens_one_incident_and_one_rotation_action_idempotently():
    G.GUARD.caught.clear()
    os.environ[VAR] = FAKE_KEY
    try:
        logging.getLogger("brambleloop.provider").error("provider echoed %s back", FAKE_KEY)
        db, path = _db()
        out = _sweep(db, "leak-1")
        assert out["secret_leak"]["status"] == "CAUGHT", out["secret_leak"]
        inc, act = _leaks(db)
        assert len(inc) == 1 and len(act) == 1, (inc, act)
        sig, sev, resolved, detail = inc[0]
        fp = G.fingerprint(FAKE_KEY)
        assert sig == f"secret_leak:var:{VAR}" and sev == "P1" and not resolved, inc
        assert detail["variable"] == VAR and fp in detail["fingerprints"], detail
        assert detail["owner_action"] == act[0][0] == f"secret_leak_rotation:var:{VAR}"
        key, action, reason, cost, minutes, consequence, done = act[0]
        assert action.startswith(f"Rotate {VAR} in Railway"), action
        assert cost == 0.0 and minutes > 0 and consequence and reason and not done
        _assert_absent(FAKE_KEY, path)

        # Repeat sweep: nothing new.
        _sweep(db, "leak-2")
        inc2, act2 = _leaks(db)
        assert len(inc2) == 1 and len(act2) == 1, (inc2, act2)
        # The same secret logged again, then swept: still one of each.
        logging.getLogger("brambleloop.provider").warning("again: %s", FAKE_KEY)
        _sweep(db, "leak-3")
        inc3, act3 = _leaks(db)
        assert len(inc3) == 1 and len(act3) == 1, (inc3, act3)
        _assert_absent(FAKE_KEY, path)
    finally:
        os.environ.pop(VAR, None)


def test_a_secret_no_variable_holds_is_keyed_on_pattern_and_fingerprint():
    G.GUARD.caught.clear()
    logging.getLogger("brambleloop.ci").error("token in a response: %s", FAKE_GH)
    db, path = _db()
    _sweep(db, "gh-1")
    _sweep(db, "gh-2")
    inc, act = _leaks(db)
    fp = G.fingerprint(FAKE_GH)
    assert [i[0] for i in inc] == [f"secret_leak:github_token:{fp}"], inc
    assert len(act) == 1 and "in Railway" in act[0][1] and "GITHUB_TOKEN" in act[0][1], act
    _assert_absent(FAKE_GH, path)


def test_the_escalation_rides_an_existing_cadence_and_is_reached():
    assert any(c[2] == "ops.health" for c in CADENCES)
    reachability.reachable.cache_clear()
    reachability._references.cache_clear()
    v = reachability.reached("ops/secret_leak.py")
    assert v["reached"], v


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{fails} failure(s)")
    sys.exit(1 if fails else 0)
