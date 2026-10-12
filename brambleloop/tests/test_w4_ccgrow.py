"""W4-CCGROW: growth experiments -- F-504 attribution and F-126 superseded evidence.

* F-504: a concluded experiment carries its measured effect against the pre-registered
  expectation and an explicit retain / rollback / undecided (retain only on a causal success).
* F-126: a superseded experiment is retained with status, reason and successor, and is
  excluded from every aggregate (`balance`, `conclude_all`).

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ccgrow.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccgrow_")

from brambleloop.growth import experiments as X  # noqa: E402


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/v{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _exp(key: str, *, design=X.HOLDOUT, days=10) -> X.Experiment:
    return X.Experiment(key=key, hypothesis="a brighter hero lifts click-through on search",
                        metric="ctr", design=design, success_threshold=0.05,
                        failure_threshold=0.02, minimum_sample=100,
                        stop_on=date.today() + timedelta(days=days), owner="growth",
                        decision="keep or revert the hero", on_success="keep the hero",
                        on_failure="revert the hero")


ROW = SimpleNamespace(success_threshold=0.05, failure_threshold=0.02, higher_is_better=True)


def test_attribution_retains_only_a_causal_success():
    win = {"verdict": "success", "claimable": True, "observed": 0.07, "sample": 200}
    a = X.attribution(ROW, win, causal=True)
    assert a["retain_or_rollback"]["decision"] == X.RETAIN
    assert a["measured_effect"]["effect_vs_expected"] == 0.02
    assert a["measured_effect"]["basis"] == "measured"
    assoc = X.attribution(ROW, win, causal=False)
    assert assoc["retain_or_rollback"]["decision"] == X.UNDECIDED
    assert "association" in assoc["retain_or_rollback"]["why"]
    lose = {"verdict": "failure", "claimable": True, "observed": 0.01, "sample": 200}
    l_ = X.attribution(ROW, lose, causal=False)
    assert l_["retain_or_rollback"]["decision"] == X.ROLLBACK
    assert l_["measured_effect"]["effect_vs_expected"] == -0.04
    none = X.attribution(ROW, {"verdict": "no result yet", "claimable": False}, causal=True)
    assert none["measured_effect"]["observed"] == X.UNMEASURED
    assert none["measured_effect"]["effect_vs_expected"] == X.UNMEASURED
    assert none["retain_or_rollback"]["decision"] == X.UNDECIDED
    lower = SimpleNamespace(success_threshold=2.0, failure_threshold=5.0, higher_is_better=False)
    d = X.attribution(lower, {"verdict": "success", "claimable": True, "observed": 1.5,
                              "sample": 200}, causal=True)
    assert d["measured_effect"]["effect_vs_expected"] == 0.5   # >= 0 means at least as good


def test_supersede_retains_the_row_and_leaves_every_aggregate():
    from sqlalchemy import select

    from brambleloop.core.models import RegisteredExperiment

    db = _db()
    X.persist(db, _exp("hero-a", days=5))
    X.persist(db, _exp("hero-b", days=5))
    before = X.balance(db)
    assert before["quick"] == 2
    out = X.supersede(db, "hero-a", reason="hero changed under the test", superseded_by="hero-b")
    assert out["state"] == X.SUPERSEDED and out["superseded_by"] == "hero-b"
    with db.session() as s:
        row = s.scalar(select(RegisteredExperiment).where(RegisteredExperiment.key == "hero-a"))
        assert row is not None and row.state == X.SUPERSEDED            # retained, not deleted
        assert row.detail["superseded"]["reason"] == "hero changed under the test"
        assert row.detail["superseded"]["previous_state"] == X.REGISTERED
        assert row.success_threshold == 0.05                            # thresholds untouched
    after = X.balance(db)
    assert after["quick"] == 1 and all(d["key"] != "hero-a" for d in after.get("long_detail", []))
    ran = X.conclude_all(db)
    assert all(r["key"] != "hero-a" for r in ran["results"])
    assert ran["results"], "the live experiment is still examined"


def test_supersede_refuses_without_a_reason_or_a_registered_successor():
    db = _db()
    X.persist(db, _exp("p-1"))
    for kwargs in ({"reason": "", "superseded_by": "p-1"},
                   {"reason": "why", "superseded_by": "nope"},
                   {"reason": "why", "superseded_by": "p-1"}):
        try:
            X.supersede(db, "p-1", **kwargs)
        except X.ExperimentRefused:
            continue
        raise AssertionError(f"supersede accepted {kwargs}")


def test_api_experiments_reports_effect_decision_and_superseded():
    import inspect

    from brambleloop.app import main

    src = inspect.getsource(main.api_experiments)
    for k in ('"measured_effect"', '"retain_or_rollback"', '"superseded"', '"UNMEASURED"'):
        assert k in src, k
    conc = inspect.getsource(X.conclude_all)
    assert 'detail["measured_effect"]' in conc and 'detail["retain_or_rollback"]' in conc


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
