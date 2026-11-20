"""W4-C03: the fallback contract binds gate tasks, and the shadow failover drill.

Rows (Final Master, quoted):
- F-095 "Define required structured output, vision, context, quality, latency and cost before
  a fallback can satisfy a gate."
- F-097 "Once a fallback exists, periodically route safe sampled work through it and compare
  quality/cost/latency."
No model call (the drill's `call` is a fixture); spends nothing.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.gateway import failover, routing  # noqa: E402
from brambleloop.gateway import fallback_contract as FC  # noqa: E402

_n = [0]
GATE = "asset_inspection"          # standard tier; approved stronger fallback exists


def _db() -> Database:
    _n[0] += 1
    tmp = tempfile.mkdtemp(prefix="c03_fallback_")
    db = Database(f"sqlite:///{tmp}/d{_n[0]}.sqlite")
    db.create_all()
    return db


def _primary_down(db, task):
    primary = failover.candidates(task)[0]
    for _ in range(failover.DOWN_AFTER_CONSECUTIVE):
        failover.record_attempt(db, provider="anthropic", model=primary, ok=False,
                                error=TimeoutError("read timed out"))


# ---- F-095 ----------------------------------------------------------------------------------

def test_f095_gate_tasks_are_declared_tasks():
    for key in FC.GATE_TASKS:
        assert key in routing.TASKS, key
        assert FC.is_gate_task(key)
    assert not FC.is_gate_task("listing_classify")


def test_f095_an_unmeasured_same_provider_fallback_cannot_satisfy_a_gate():
    db = _db()
    _primary_down(db, GATE)
    d = failover.decide(db, GATE)
    assert d.action == failover.PARK, d.to_dict()       # before: CALL on the approval alone
    row = d.candidates[1]
    assert row["contract"] == FC.UNKNOWN and row.get("contract_refused") is True
    gate = FC.may_route(db, provider="anthropic", primary_provider="anthropic",
                        model=row["model"], task_key=GATE)
    assert gate["allowed"] is False and "quality" in gate["basis"] and "latency" in gate["basis"]
    # Measured quality and latency inside the contract: now it may stand in.
    tier = FC.contract_for(GATE)["tier"]
    FC.record_eval(db, provider="anthropic", model=row["model"], tier=tier, passed=20,
                   total=20, source="gateway/evals golden tasks")
    FC.record_latency(db, provider="anthropic", model=row["model"], tier=tier, p95_s=9.0,
                      samples=40)
    ok = failover.decide(db, GATE)
    assert ok.action == failover.CALL and ok.chosen == row["model"], ok.to_dict()


def test_f095_a_non_gate_task_keeps_the_reviewed_same_provider_approval():
    db = _db()
    _primary_down(db, "listing_classify")
    d = failover.decide(db, "listing_classify")
    assert d.action == failover.CALL and d.candidates[1]["contract"] == FC.UNKNOWN


# ---- F-097 ----------------------------------------------------------------------------------

ITEMS = [{"id": f"listing-{i}", "text": f"item {i}"} for i in range(200)]


def _call(disagree_every=0, latency=2.0):
    calls = []

    def call(provider, model, item):
        calls.append((provider, model, item["id"]))
        n = int(item["id"].split("-")[1])
        label = "hat"
        if disagree_every and model != failover.candidates("listing_classify")[0] \
                and n % disagree_every == 0:
            label = "scarf"
        return {"output": {"category": label}, "cost_cad": 0.001, "latency_s": latency}
    return call, calls


def test_f097_the_drill_is_off_unless_switched_on_and_makes_no_call():
    db = _db()
    os.environ.pop(FC.DRILL_SWITCH, None)
    call, calls = _call()
    out = FC.failover_drill(db, task_key="listing_classify", items=ITEMS, call=call)
    assert out["ran"] is False and FC.DRILL_SWITCH in out["why"] and calls == []


def test_f097_a_gate_or_owner_facing_task_is_never_sampled():
    db = _db()
    call, calls = _call()
    for task in (GATE, "laura.converse", "stitch_counts"):
        out = FC.failover_drill(db, task_key=task, items=ITEMS, call=call, enabled=True)
        assert out["ran"] is False, (task, out)
    assert calls == []
    out = FC.failover_drill(db, task_key="benchmark_challenge", items=ITEMS, call=call,
                            enabled=True)
    assert out["ran"] is False


def test_f097_sampled_work_is_compared_and_feeds_the_contract():
    db = _db()
    call, calls = _call(latency=3.0)
    tier = FC.contract_for("listing_classify")["tier"]
    fb = failover.candidates("listing_classify")[1]
    before = FC.evaluate(db, provider="anthropic", model=fb, task_key="listing_classify")
    assert before["checks"]["quality"]["verdict"] == FC.UNKNOWN
    out = FC.failover_drill(db, task_key="listing_classify", items=ITEMS, call=call,
                            enabled=True, rate=0.2, limit=FC.MIN_EVAL_SAMPLES)
    assert out["ran"] is True and out["sampled"] == FC.MIN_EVAL_SAMPLES, out
    assert 0 < out["sampled"] < len(ITEMS) and len(calls) == 2 * out["sampled"]
    c = out["comparison"]
    assert c["quality"]["agreement"] == 1.0 and c["p95_latency_s"]["fallback"] == 3.0
    assert set(c["cost_cad_per_call"]) == {"primary", "fallback"}
    assert out["passed"] is True and out["contract_after"] == FC.PASS, out
    assert out["counts_for_provider_dependency"] is False
    with db.session() as s:
        actions = [a.action for a in s.scalars(select(AuditLog))]
    assert FC.DRILL_ACTION in actions
    assert "provider.fallback_drill" not in actions      # same provider: not F-093 evidence
    # A disagreeing fallback fails its drill and its contract.
    db2 = _db()
    call2, _ = _call(disagree_every=3)
    bad = FC.failover_drill(db2, task_key="listing_classify", items=ITEMS, call=call2,
                            enabled=True, rate=0.2, limit=FC.MIN_EVAL_SAMPLES)
    assert bad["passed"] is False and bad["contract_after"] == FC.FAIL, bad
    assert bad["comparison"]["quality"]["agreement"] < FC.MIN_EVAL_PASS_RATE
    assert tier


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
