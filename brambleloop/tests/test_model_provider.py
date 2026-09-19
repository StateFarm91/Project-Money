"""The real model provider: a key that is not a capability, and a ceiling checked in advance.

The owner supplied an Anthropic key on 2026-09-19. The first call it made returned "Your
credit balance is too low to access the Anthropic API" -- the key authenticates and the
account cannot serve a request. That is the case these tests are built around, because it is
the one an environment-variable check gets wrong: it would report the model provider
available and un-park four requirements onto work that cannot run.

No test here makes a network call. The provider is exercised through a stand-in that raises
exactly what the real one raised.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.build2 import executor as E  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.gateway import anthropic as A  # noqa: E402
from brambleloop.gateway.model_gateway import ModelResponse  # noqa: E402

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/model.sqlite")
    db.create_all()
    return db


class _Stub(A.AnthropicProvider):
    """A provider with a key, whose call does whatever the test needs it to do."""

    def __init__(self, outcome, model: str = A.PROBE_MODEL):
        super().__init__(model=model)
        self._outcome = outcome

    @staticmethod
    def key() -> str:
        return "present-but-not-a-capability"

    def complete(self, system, user, *, max_tokens):  # noqa: D102
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _ok_response() -> ModelResponse:
    return ModelResponse(text="ok", provider="anthropic", model=A.PROBE_MODEL,
                         input_tokens=9, output_tokens=2, latency_ms=120.0)


# ---- a key is not a capability -------------------------------------------


def test_a_key_that_cannot_serve_a_request_does_not_open_the_gate():
    """The verbatim failure this account returns, and the gate it must not open."""
    db = _db()
    billing = A.ProviderUnusable(
        "anthropic 400: Your credit balance is too low to access the Anthropic API.")

    record = A.probe(db, provider=_Stub(billing), now=NOW)

    assert record["ok"] is False
    assert "credit balance is too low" in record["reason"]
    assert A.usable(db) is False
    assert E.GATE_BY_KEY["model_provider"].open(db, {}) is False


def test_a_successful_call_opens_the_gate_with_nobody_remembering():
    db = _db()

    record = A.probe(db, provider=_Stub(_ok_response()), now=NOW)

    assert record["ok"] is True
    assert A.usable(db) is True
    assert E.GATE_BY_KEY["model_provider"].open(db, {}) is True


def test_no_probe_ever_run_is_unknown_rather_than_unavailable():
    state = A.state(_db())
    assert state["last_probe"] is None
    assert state["usable"] is False
    assert "not the same as unavailable" in state["note"]


def test_the_provider_records_what_it_was_told_rather_than_a_paraphrase():
    """A key that authenticates and an account that cannot pay are different failures, and
    only the provider's own words distinguish them."""
    db = _db()
    A.probe(db, provider=_Stub(TransientError("anthropic 529: overloaded")), now=NOW)

    assert "529" in A.last_probe(db)["reason"]


# ---- the ceiling ----------------------------------------------------------


def test_the_ceiling_cannot_be_raised_by_configuration():
    import os

    previous = os.environ.get("BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD")
    try:
        os.environ["BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD"] = "500"
        assert A.monthly_ceiling_cad() == A.DEFAULT_MONTHLY_CEILING_CAD
        os.environ["BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD"] = "5"
        assert A.monthly_ceiling_cad() == 5.0
    finally:
        if previous is None:
            os.environ.pop("BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD", None)
        else:
            os.environ["BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD"] = previous


def test_a_call_that_would_cross_the_ceiling_is_refused_before_it_is_made():
    from brambleloop.core.models import CostEntry

    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="orchestrator", kind="llm", amount_cad=24.99, at=NOW))

    try:
        A.check_budget(db, model="claude-opus-5", input_tokens=1000, max_tokens=4000,
                       now=NOW)
    except A.BudgetExceeded as e:
        assert "rather than found on the invoice" in str(e)
    else:
        raise AssertionError("a call was allowed past the monthly ceiling")


def test_an_unpriced_model_is_an_unbounded_call_and_is_refused():
    try:
        A.estimate_cad("some-new-model", input_tokens=10, output_tokens=10)
    except A.BudgetExceeded as e:
        assert "unbounded" in str(e)
    else:
        raise AssertionError("a model with no price on file was allowed to be called")


def test_the_estimate_is_padded_rather_than_optimistic():
    """A ceiling that trusts an optimistic estimate is crossed before anybody notices."""
    raw_usd = (1_000_000 / 1_000_000) * A.PRICES_USD_PER_MTOK["claude-sonnet-5"][0]
    padded = A.estimate_cad("claude-sonnet-5", input_tokens=1_000_000, output_tokens=0)

    assert A.ESTIMATE_PADDING > 1.0
    assert padded > raw_usd * A.USD_TO_CAD


def test_the_budget_assumes_the_whole_output_allowance_is_used():
    """Budgeting for the usual case is how a ceiling becomes a target."""
    db = _db()
    small = A.check_budget(db, model="claude-sonnet-5", input_tokens=10, max_tokens=10,
                           now=NOW)
    large = A.check_budget(db, model="claude-sonnet-5", input_tokens=10, max_tokens=4000,
                           now=NOW)
    assert large["estimate_cad"] > small["estimate_cad"]


def test_spend_is_counted_from_rows_and_scoped_to_this_month():
    from brambleloop.core.models import CostEntry

    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="orchestrator", kind="llm", amount_cad=1.0, at=NOW))
        s.add(CostEntry(agent="orchestrator", kind="llm", amount_cad=9.0,
                        at=datetime(2026, 8, 19, tzinfo=timezone.utc)))
        s.add(CostEntry(agent="orchestrator", kind="hosting", amount_cad=7.0, at=NOW))

    assert A.spent_this_month_cad(db, now=NOW) == 1.0


def test_a_successful_probe_is_charged_to_the_ledger():
    db = _db()
    A.probe(db, provider=_Stub(_ok_response()), now=NOW)

    from sqlalchemy import select

    from brambleloop.core.models import CostEntry

    with db.session() as s:
        rows = list(s.scalars(select(CostEntry).where(CostEntry.kind == "llm")))

    assert len(rows) == 1
    assert rows[0].detail["price_basis"] == "assumed"
    assert rows[0].tokens_in == 9


def test_a_failed_probe_is_not_charged_for_tokens_it_never_used():
    db = _db()
    A.probe(db, provider=_Stub(A.ProviderUnusable("anthropic 400: no credit")), now=NOW)

    assert A.spent_this_month_cad(db, now=NOW) == 0.0


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
