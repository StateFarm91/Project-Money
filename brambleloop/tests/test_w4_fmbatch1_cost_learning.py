"""F-389: cost learning proposes cheaper routes (only on recorded equivalence) and flags
context drift, from measured spend."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.finance import spend_report as R  # noqa: E402
from brambleloop.gateway import routing  # noqa: E402
from brambleloop.improve import bootstrap, cost_learning as CL  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _task_with_cheaper():
    return next(k for k, t in routing.TASKS.items() if t.tier in bootstrap.CHEAPER_TIER)


def test_spend_ranks_opportunities_and_no_evidence_is_not_proposable():
    db = _db()
    key = _task_with_cheaper()
    task = routing.TASKS[key]
    for _ in range(6):
        R.record(db, agent="market_radar", amount_cad=0.4, purpose=key,
                 tokens_in=task.typical_input_tokens * 3)
    out = CL.opportunities(db)
    row = next(r for r in out["routes"] if r["task"] == key)
    assert row["calls_month"] == 6 and abs(row["spent_cad_month"] - 2.4) < 1e-9
    assert row["saving_per_call_cad"] > 0
    assert row["projected_saving_cad_month"] == round(row["saving_per_call_cad"] * 6, 6)
    assert row["status"] == "needs_evidence" and row["missing_evidence"]
    assert key not in out["proposable"]
    assert out["routes"][0]["task"] == key          # the only task with spend ranks first
    ctx = next(c for c in out["context"] if c["task"] == key)
    assert ctx["ratio"] == 3.0 and "larger than declared" in ctx["finding"]


def test_recorded_equivalence_makes_it_proposable_and_is_not_applied():
    db = _db()
    key = _task_with_cheaper()
    task = routing.TASKS[key]
    cheaper = routing.TIERS[bootstrap.CHEAPER_TIER[task.tier]]
    declared = routing.TIERS[task.tier]
    for model in (declared.model, cheaper.model):
        routing.record_route_evidence(db, key, model, floors={"accuracy": True},
                                      items=routing.MIN_EVIDENCE_ITEMS, eval_ref="eval:1")
    out = CL.run(db)
    assert key in out["proposable"]
    t, tier, basis = routing.effective_route(db, key)
    assert tier.model == declared.model and basis["basis"] == "declared"   # not applied
    with db.session() as s:
        assert s.query(AuditLog).filter(AuditLog.action == CL.ACTION).count() == 1


def test_few_calls_are_unmeasured_context():
    db = _db()
    key = _task_with_cheaper()
    R.record(db, agent="x", amount_cad=0.1, purpose=key, tokens_in=10)
    ctx = next(c for c in CL.opportunities(db)["context"] if c["task"] == key)
    assert ctx["state"] == "UNMEASURED"


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
