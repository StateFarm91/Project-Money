"""W4-FINHEALTH: finance session recovery, truthful ceiling check, dead-letter evidence.

1. Production `PendingRollbackError`: a Command Center finance read hands the accounting
   package a bare Session; a failed flush inside `_SessionDB.session()` left it poisoned, and
   `dashboard.summary` -- which catches a posting failure and carries on reading -- died on
   its next query. Reproduced here through the real provider path.
2. `every_agent_has_a_cost_ceiling`: a declared CA$0 ceiling is a permission of zero and is
   refused before the call; a ceiling nobody declared is still a failure.
3. Dead-letter evidence carries counts and the error head; rebuild keys fit VARCHAR(200).

Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_finhealth.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_finhealth_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the FINHEALTH harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from brambleloop.agents.registry import (DEFAULT_AGENTS, Registry,  # noqa: E402
                                         ceiling_audit, declared_daily_ceiling)
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Agent, CostEntry, Job, JobStatus  # noqa: E402
from brambleloop.finance.accounting import posting_rules, schema  # noqa: E402
from brambleloop.finance.accounting.models import AcctException  # noqa: E402

NOW = datetime.now(timezone.utc)
_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _poisoning_post_all(db, now=None):
    """A posting refresh that fails at flush, the way a Postgres-only constraint does."""
    db = schema.ensure(db)
    with db.session() as s:
        s.add(AcctException(key="finhealth-dup", kind="test", summary="first"))
        s.flush()
        s.add(AcctException(key="finhealth-dup", kind="test", summary="second"))
        s.flush()  # IntegrityError: unique key -> the session needs a rollback


# ---------------------------------------------------------------------------- 1. sessions

def test_session_wrapper_leaves_a_usable_session_after_a_failed_flush():
    db = _db()
    session = db.new_session()
    try:
        wrapped = schema.ensure(session)
        try:
            _poisoning_post_all(wrapped)
        except IntegrityError:
            pass
        else:
            raise AssertionError("the planted duplicate did not fail")
        # Before the fix this raised sqlalchemy.exc.PendingRollbackError.
        assert session.is_active
        assert session.scalar(select(Agent).limit(1)) is not None
        # Nothing from the failed block survives the recovery.
        assert session.scalars(select(AcctException)).all() == []
    finally:
        session.rollback()
        session.close()


def test_session_wrapper_does_not_roll_back_on_a_plain_python_error():
    """A non-database error leaves the transaction intact; only a lost one is rolled back."""
    db = _db()
    session = db.new_session()
    try:
        wrapped = schema.ensure(session)
        session.add(AcctException(key="kept", kind="test", summary="pending"))
        session.flush()
        try:
            with wrapped.session():
                raise ValueError("not a database failure")
        except ValueError:
            pass
        assert session.scalar(select(AcctException).where(AcctException.key == "kept"))
    finally:
        session.rollback()
        session.close()


def test_finance_summary_survives_a_failed_posting_refresh_via_the_provider_path():
    """The production shape: Command Center provider -> bare Session -> dashboard.summary."""
    from brambleloop.app.command_center import providers

    db = _db()
    real = posting_rules.post_all
    posting_rules.post_all = _poisoning_post_all
    try:
        out = providers.call("accounting", db)
    finally:
        posting_rules.post_all = real
    text = repr(out)
    assert "PendingRollbackError" not in text, out.get("reason")
    assert "Finance summary unavailable" not in text, out.get("reason")
    assert "posting refresh failed: IntegrityError" in (out.get("reason") or ""), out
    assert out.get("items"), "the summary rendered no figures"


# ---------------------------------------------------------------------------- 2. ceilings

def _seeded_rows(db):
    with db.session() as s:
        return [(a.name, a.daily_cost_ceiling_cad) for a in s.scalars(select(Agent))]


def test_declared_zero_ceilings_are_no_spend_not_missing():
    db = _db()
    declared_zero = sorted(d["name"] for d in DEFAULT_AGENTS
                           if float(d.get("daily_cost_ceiling_cad", 1)) == 0.0)
    # `laura` left this set on the owner's 2026-10-11 decision (CA$0.50/day,
    # DECISION_LOG D-W4-LAURA1-BUDGET); the no-spend semantics are unchanged for the rest.
    # `storefront_director` joined on W4-AGENTS: deterministic, no model, CA$0 by declaration.
    # `research_agent` joined on W4-AGENTS W3: internal retrieval only, CA$0 by declaration.
    # `accountant` joined on W4-C04 (F-607): keeps the books from rows, no model, CA$0.
    assert declared_zero == ["accountant", "coo", "learn", "research_agent",
                             "storefront_director"], declared_zero
    assert declared_daily_ceiling("laura") == 0.50
    out = ceiling_audit(_seeded_rows(db))
    assert out["ok"] is True, out
    assert out["declared_no_spend"] == ["accountant", "coo", "learn", "research_agent",
                                        "storefront_director"]  # F-607
    assert out["misconfigured"] == []


def test_undeclared_or_drifted_zero_ceiling_is_still_a_failure():
    db = _db()
    rows = [(n, 0.0 if n == "pricing" else c) for n, c in _seeded_rows(db)]
    out = ceiling_audit(rows)
    assert out["ok"] is False
    assert [m["agent"] for m in out["misconfigured"]] == ["pricing"], out
    assert declared_daily_ceiling("pricing") > 0
    out = ceiling_audit(_seeded_rows(db) + [("nobody_declared_me", 0.0)])
    assert out["ok"] is False and out["misconfigured"][0]["declared_cad"] is None
    out = ceiling_audit(_seeded_rows(db) + [("nan_agent", float("nan"))])
    assert out["ok"] is False and out["misconfigured"][0]["ceiling_cad"] is None
    assert ceiling_audit([])["ok"] is False


def test_a_no_spend_agent_that_spent_fails_and_shows_as_over():
    from brambleloop.finance import spend_report

    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="coo", amount_cad=0.01, kind="llm", detail={}))
    today = spend_report.per_agent_today(db)
    assert "coo" in [r["agent"] for r in today["over"]], today["over"]
    out = ceiling_audit(_seeded_rows(db),
                        {r["agent"]: r["spent_today_cad"] for r in today["agents"]})
    assert out["ok"] is False
    assert out["no_spend_agents_that_spent_today"][0]["agent"] == "coo"


def test_zero_ceiling_is_refused_before_the_call():
    """Was: `agent_daily_ceiling` returned None for CA$0, so check_budget skipped the agent."""
    from brambleloop.finance.reservations import outstanding
    from brambleloop.gateway import anthropic as gw

    db = _db()
    for name in ("learn", "coo"):
        permission = gw.agent_daily_ceiling(db, name)
        assert permission == {"agent": name, "daily_ceiling_cad": 0.0,
                              "spent_today_cad": 0.0}, permission
        try:
            gw.check_budget_cad(db, estimate_cad=0.001, agent=name, purpose="finhealth")
        except gw.AgentCeilingExceeded:
            pass
        else:
            raise AssertionError(f"{name} (CA$0) was allowed to spend")
    assert outstanding(db)["reservations"] == [], "a refused call left a reservation"
    # An agent with no row is still "unknown spender", not zero (test_model_spend_paths).
    assert gw.agent_daily_ceiling(db, "not_an_agent") is None


class _CountingProvider:
    """A stub provider that counts every request it is asked to make (the 'bill')."""

    name = "standin"
    model = "claude-haiku-4-5"

    def __init__(self):
        from brambleloop.gateway import anthropic as gw

        self.cost_per_1k_input_cad = round(1.0 / 1000 * gw.USD_TO_CAD, 8)
        self.cost_per_1k_output_cad = round(5.0 / 1000 * gw.USD_TO_CAD, 8)
        self.calls = 0

    def complete(self, system, user, *, max_tokens):
        import json

        from brambleloop.gateway.model_gateway import ModelResponse

        self.calls += 1
        return ModelResponse(text=json.dumps({"names": ["A", "B", "C"]}), provider=self.name,
                             model=self.model, input_tokens=len(user) // 4,
                             output_tokens=200, latency_ms=0.0)


def test_generic_gateway_path_never_calls_the_provider_for_a_zero_ceiling_agent():
    """Coordinator / LAURA1 finding: the general ModelGateway path refused a CA$0 agent only
    after the provider had answered (and billed). Every zero-ceiling agent, every path that
    goes through `check_budget_cad`: zero provider requests, zero cost rows, zero
    reservations, and an audited refusal."""
    from brambleloop.agents.registry import BudgetExceeded
    from brambleloop.core.models import AuditLog, SpendReservation
    from brambleloop.finance import spend_report
    from brambleloop.gateway.model_gateway import ModelGateway

    db = _db()
    reg = Registry(db)
    for name in ("learn", "coo"):
        stub = _CountingProvider()
        g = ModelGateway([stub], registry=reg)
        try:
            g.complete_json("concept.naming@1", agent=name,
                            values={"category": "c", "motifs": "m", "season": "s"})
        except BudgetExceeded:
            pass
        else:
            raise AssertionError(f"{name} (CA$0) got a model answer")
        assert stub.calls == 0, f"{name}: provider asked {stub.calls} time(s) -- billed"
    with db.session() as s:
        assert s.scalars(select(CostEntry)).all() == [], "a refused call was billed"
        assert s.scalars(select(SpendReservation)).all() == []
        refused = [a.detail for a in s.scalars(select(AuditLog))
                   if a.action == spend_report.REFUSED_ACTION]
    assert sorted(r["agent"] for r in refused) == ["coo", "learn"], refused
    assert {r["which"] for r in refused} == {"agent_daily_ceiling"}, refused
    # A positive-ceiling agent on the same path is unaffected.
    stub = _CountingProvider()
    ModelGateway([stub], registry=reg).complete_json(
        "concept.naming@1", agent="market_radar",
        values={"category": "c", "motifs": "m", "season": "s"})
    assert stub.calls == 1


# ---------------------------------------------------------------------------- 3. evidence

def test_dead_letter_digest_counts_and_names_the_error():
    from brambleloop.queue.durable import dead_letter_digest

    jobs = [Job(agent="intel", job_type="mjs.scan", status=JobStatus.DEAD,
                last_error=f"ReadFailed: 403 #{i}\nTraceback...", finished_at=NOW)
            for i in range(3)]
    jobs.append(Job(agent="orchestrator", job_type="ops.sentinel", status=JobStatus.DEAD,
                    last_error="DataError: " + "x" * 400, finished_at=NOW))
    out = dead_letter_digest(jobs)
    assert [(g["job_type"], g["count"]) for g in out] == [("mjs.scan", 3), ("ops.sentinel", 1)]
    assert "\n" not in out[0]["last_error"] and out[0]["last_error"].startswith("ReadFailed")
    assert len(out[1]["last_error"]) == 200
    assert dead_letter_digest([]) == []


def test_rebuild_idempotency_keys_fit_the_column_and_stay_deterministic():
    from brambleloop.ops.rebuild_graph import IDEMPOTENCY_KEY_MAX, _bounded_key

    stamp = "-".join(f"ref:{i:03d}=abcdef12" for i in range(40))
    a = _bounded_key("rebuild:product:some-slug:", stamp)
    assert len(a) <= IDEMPOTENCY_KEY_MAX == 200, len(a)
    assert a == _bounded_key("rebuild:product:some-slug:", stamp)
    assert a != _bounded_key("rebuild:product:some-slug:", stamp + "-x=1")
    assert a != _bounded_key("rebuild:product:other-slug:", stamp)
    short = _bounded_key("rebuild:product:s:", "r=abcdef12")
    assert short == "rebuild:product:s:r=abcdef12", "a key that fits must not change"


def test_estimate_drift_unreserved_share_is_none_without_token_calls():
    from brambleloop.finance import spend_report

    db = _db()
    d = spend_report.estimate_drift(db)
    assert d["token_priced_calls"] == 0
    assert d["calls_with_no_reservation_share"] is None, d


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    assert tests
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
