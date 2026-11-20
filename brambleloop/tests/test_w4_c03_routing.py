"""W4-C03: outcome-based model routing.

Row (Final Master, quoted):
- F-710 "Claude, GPT/ChatGPT Work/Codex, Fable and future specialist models are bounded
  workers/capabilities under Brambleloop, not competing company coordinators. Route tasks by
  demonstrated quality, cost, latency, context, tool access and risk."
Runs are fixtures recorded through `improve.league.record_run`; no model call; spends nothing.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import ConfigVersion  # noqa: E402
from brambleloop.gateway import routing  # noqa: E402
from brambleloop.improve import bootstrap, league  # noqa: E402

_n = [0]
TASKS = [f"shared-{i}" for i in range(24)]
HOLD = [f"holdout-{i}" for i in range(6)]


def _db() -> Database:
    _n[0] += 1
    tmp = tempfile.mkdtemp(prefix="c03_routing_")
    db = Database(f"sqlite:///{tmp}/d{_n[0]}.sqlite")
    db.create_all()
    bootstrap.register_routing_incumbents(db)
    bootstrap.register_routing_challengers(db)
    return db


def _ids(db, task):
    key = f"{bootstrap.ROUTING_KEY_PREFIX}{task}"
    with db.session() as s:
        rows = list(s.scalars(select(ConfigVersion).where(ConfigVersion.key == key)))
        inc = next(r.id for r in rows if r.incumbent)
        ch = next(r.id for r in rows if not r.incumbent)
    return inc, ch


def _run(db, cid, q, *, cost, latency, ref, hq=None):
    league.record_run(db, cid, tasks={t: q for t in TASKS}, cost_cad=cost, reliability=0.99,
                      latency_s=latency, holdout={h: (hq if hq is not None else q) for h in HOLD},
                      run_ref=ref, recorded_by="evaluator")


def _on(flag: bool):
    if flag:
        os.environ[routing.OUTCOME_SWITCH] = "1"
    else:
        os.environ.pop(routing.OUTCOME_SWITCH, None)


def test_f710_routing_follows_demonstrated_outcomes_only_when_switched_on_and_approved():
    db = _db()
    task = "listing_copy"                                # declared standard
    inc, ch = _ids(db, task)
    _run(db, inc, 0.80, cost=0.010, latency=6.0, ref="fixture:inc:1")
    _run(db, ch, 0.90, cost=0.002, latency=2.0, ref="fixture:ch:1")
    try:
        _on(False)
        assert routing.effective_route(db, task)[1].key == routing.STANDARD
        _on(True)
        oc = routing.outcome_route(db, task)
        assert oc["chosen"] is None and "owner" in oc["candidates"][0]["why"], oc
        assert routing.effective_route(db, task)[1].key == routing.STANDARD
        league.record_owner_decision(db, ch, approved_by="owner",
                                     why="cheaper and better on the shared set")
        _t, tier, basis = routing.effective_route(db, task)
        assert tier.key == routing.CHEAP and basis["basis"] == "outcome", basis
        m = basis["outcome"]["candidates"][0]["measured"]
        assert m["quality"] == 0.9 and m["latency_s"] == 2.0 and m["cost_cad"] == 0.002
        # A later losing run reverses the route on the next read.
        _run(db, ch, 0.50, cost=0.002, latency=2.0, ref="fixture:ch:2")
        assert routing.effective_route(db, task)[1].key == routing.STANDARD
    finally:
        _on(False)


def test_f710_a_gate_task_moves_only_to_a_model_whose_contract_passes():
    db = _db()
    task = "asset_inspection"
    inc, ch = _ids(db, task)
    _run(db, inc, 0.80, cost=0.010, latency=6.0, ref="fixture:inc:g")
    _run(db, ch, 0.95, cost=0.002, latency=2.0, ref="fixture:ch:g")
    league.record_owner_decision(db, ch, approved_by="owner", why="measured better and cheaper")
    try:
        _on(True)
        oc = routing.outcome_route(db, task)
        assert oc["chosen"] is None and "contract" in oc["candidates"][0]["why"], oc
    finally:
        _on(False)


def test_f710_a_model_the_gateway_cannot_call_is_recorded_never_routed():
    db = _db()
    task = "listing_copy"
    inc, _ch = _ids(db, task)
    out = league.register(
        db, kind=bootstrap.ROUTING_KIND, key=f"{bootstrap.ROUTING_KEY_PREFIX}{task}",
        payload=json.dumps({"task": task, "tier": "cheap", "model": "gpt-x",
                            "provider": "openai"}, sort_keys=True),
        why_changed="a second provider's model measured on the same shared task set",
        affected_departments=("store_commerce",))
    _run(db, inc, 0.80, cost=0.010, latency=6.0, ref="fixture:inc:o")
    _run(db, out["id"], 0.99, cost=0.001, latency=1.0, ref="fixture:o:1")
    league.record_owner_decision(db, out["id"], approved_by="owner", why="best on every axis")
    try:
        _on(True)
        oc = routing.outcome_route(db, task)
        row = next(c for c in oc["candidates"] if c["config_id"] == out["id"])
        assert "no text adapter" in row["why"] and not row.get("routable"), row
        assert oc["chosen"] is None
    finally:
        _on(False)


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
