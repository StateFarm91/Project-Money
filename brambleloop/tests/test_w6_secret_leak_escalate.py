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


def test_an_owner_resolved_and_rotated_catch_stays_quiet_but_any_growth_reopens():
    from brambleloop.ops import incident_lifecycle

    G.GUARD.caught.clear()
    os.environ[VAR] = FAKE_KEY
    rotated = FAKE_KEY[:-6] + "ZZZZZZ"
    try:
        logging.getLogger("brambleloop.provider").error("provider echoed %s back", FAKE_KEY)
        db, path = _db()
        _sweep(db, "res-1")
        sig = f"secret_leak:var:{VAR}"

        def resolve_all(why):
            with db.session() as s:
                incident_lifecycle.resolve_signatures(
                    s, [i[0] for i in _leaks(db)[0] if not i[2]], resolution=why)
                for a in s.scalars(select(OwnerAction).where(
                        OwnerAction.requirement_key.like(secret_leak.KEY_PREFIX + "%"))):
                    a.done = True

        # Resolved but NOT rotated (the variable still holds the value): it reopens.
        resolve_all("owner: rotated (claimed)")
        _sweep(db, "res-2")
        assert [i[2] for i in _leaks(db)[0]].count(False) == 1, _leaks(db)[0]

        # Rotated for real (the variable now holds a new value), resolved: quiet.
        resolve_all("owner: rotated")
        os.environ[VAR] = rotated
        out = _sweep(db, "res-3")
        assert [i[2] for i in _leaks(db)[0]].count(False) == 0, _leaks(db)[0]
        assert out["secret_leak"]["acknowledged"], out["secret_leak"]

        # The revoked value is logged again: the count grew, so it reopens (delta N-M1).
        logging.getLogger("brambleloop.provider").error("old key again %s", FAKE_KEY)
        _sweep(db, "res-4")
        assert [i[2] for i in _leaks(db)[0]].count(False) == 1, _leaks(db)[0]

        # The new value leaks: a new, separate open incident on the variable.
        logging.getLogger("brambleloop.provider").error("new key echoed %s", rotated)
        _sweep(db, "res-5")
        open_sigs = [i[0] for i in _leaks(db)[0] if not i[2]]
        assert sig in open_sigs and len(open_sigs) == 2, open_sigs
        _assert_absent(FAKE_KEY, path)
        _assert_absent(rotated, path)
    finally:
        os.environ.pop(VAR, None)


def test_acknowledgement_needs_every_fingerprint_covered_at_no_higher_count():
    from brambleloop.ops import incident_lifecycle

    db, _path = _db()
    with db.session() as s:
        incident_lifecycle.open_or_restate(
            s, signature="secret_leak:x:aa", severity="P1", summary="t",
            detail={"fingerprints": {"aa": 2}})
        incident_lifecycle.resolve_signatures(s, ["secret_leak:x:aa"], resolution="owner")
        f = secret_leak._resolved_for_same_catch
        assert f(s, "secret_leak:x:aa", {"aa": 2}) is True
        assert f(s, "secret_leak:x:aa", {"aa": 3}) is False          # grew
        assert f(s, "secret_leak:x:aa", {"aa": 1, "bb": 1}) is False  # partly new
        assert f(s, "secret_leak:x:aa", {}) is False


def test_only_an_explicit_clean_status_reads_clean():
    db, _path = _db()
    with db.session() as s:
        assert secret_leak.escalate(s, summary={"status": "CLEAN"})["status"] == "CLEAN"
        assert secret_leak.escalate(s, summary={})["status"] == "UNKNOWN"
        assert secret_leak.escalate(s, summary={"status": "caught"})["status"] == "UNKNOWN"


def test_a_failed_escalation_of_a_caught_secret_still_opens_an_incident():
    G.GUARD.caught.clear()
    logging.getLogger("brambleloop.ci").error("token in a response: %s", FAKE_GH)
    db, path = _db()
    real = secret_leak.escalate

    def boom(*a, **k):
        raise RuntimeError("escalation broke")

    secret_leak.escalate = boom
    try:
        out = _sweep(db, "fail-1")
        _sweep(db, "fail-2")
    finally:
        secret_leak.escalate = real
    assert out["secret_leak"]["escalation"] == "FAILED", out["secret_leak"]
    inc, _act = _leaks(db)
    assert [(i[0], i[1], i[2]) for i in inc] == [(secret_leak.ESCALATION_FAILED, "P1", False)], inc
    _assert_absent(FAKE_GH, path)
    # The next sweep that escalates closes the fallback; the per-credential row carries it.
    _sweep(db, "fail-3")
    inc = {i[0]: i[2] for i in _leaks(db)[0]}
    assert inc[secret_leak.ESCALATION_FAILED] is True, inc
    assert [k for k, r in inc.items() if not r and k != secret_leak.ESCALATION_FAILED], inc


def test_a_failed_escalation_with_a_clean_guard_opens_nothing():
    G.GUARD.caught.clear()
    db, _path = _db()
    real = secret_leak.escalate

    def boom(*a, **k):
        raise RuntimeError("escalation broke")

    secret_leak.escalate = boom
    try:
        out = _sweep(db, "cleanfail-1")
    finally:
        secret_leak.escalate = real
    assert out["secret_leak"]["status"] == "UNKNOWN", out["secret_leak"]
    assert _leaks(db)[0] == []


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
