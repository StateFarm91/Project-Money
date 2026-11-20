"""Wave-3 lane SPEND: the `laura.business_phrase` routing task (for lane F's optional phrasing).

Cheap tier, small output budget, no stronger fallback, its own allocation stop, ceiling-checked
before the call, billed through the gateway's single path, cached by content, and every answer
validated deterministically. No test here reaches a network or pays anything: the transport is
an `EchoProvider` stand-in.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_spend_laura_phrase.py
"""
from __future__ import annotations

from r2_autonomy_harness import boot, run_tests

STATEMENT = "We hold the price of the market basket at CA$12 this week."
FACTS = {"product": "market basket", "price_cad": 12}


def _factory(text, calls):
    def make(model):
        from brambleloop.gateway.model_gateway import EchoProvider

        def scripted(system, user):
            calls.append(model)
            return '{"text": "%s"}' % text

        return EchoProvider(name="anthropic", model=model, cost_per_1k_input_cad=0.001,
                            cost_per_1k_output_cad=0.001, scripted=scripted)
    return make


def _ledger(db, purpose):
    from sqlalchemy import select

    from brambleloop.core.models import CostEntry

    with db.session() as s:
        return list(s.scalars(select(CostEntry).where(CostEntry.purpose == purpose)))


def test_the_task_is_cheap_small_and_never_escalates():
    from brambleloop.finance import economics, spend_policy
    from brambleloop.gateway import failover, laura_phrase, routing

    task, tier = routing.route("laura.business_phrase")
    assert task.tier == routing.CHEAP and tier.model == routing.TIERS[routing.CHEAP].model
    assert task.max_output_tokens <= 256 and task.typical_input_tokens <= 1000
    assert failover.candidates("laura.business_phrase") == [tier.model]
    assert routing.estimate_cad("laura.business_phrase") < 0.01
    assert laura_phrase.PROMPT.max_output_tokens == task.max_output_tokens
    assert spend_policy.ALLOCATION[laura_phrase.PROMPT.ref] <= 0.02
    assert economics.classify(laura_phrase.PROMPT.ref)["economic_class"] == economics.SUPPORT
    # Other cheap tasks keep their approved stronger fallbacks.
    assert len(failover.candidates("listing_classify")) >= 1


def test_no_provider_returns_the_deterministic_sentence_and_spends_nothing():
    from brambleloop.gateway import laura_phrase

    db = boot()

    def none_factory(model):
        from brambleloop.gateway.model_gateway import NoProviderAvailable

        raise NoProviderAvailable("no key in this environment")

    out = laura_phrase.phrase(db, statement=STATEMENT, facts=FACTS,
                              provider_factory=none_factory)
    assert out["source"] == "deterministic" and out["text"] == STATEMENT, out
    assert not _ledger(db, laura_phrase.PROMPT.ref)


def test_a_reworded_answer_is_billed_once_then_served_from_cache():
    from brambleloop.gateway import laura_phrase

    db = boot()
    calls: list = []
    good = "This week the market basket stays at CA$12."
    out = laura_phrase.phrase(db, statement=STATEMENT, facts=FACTS,
                              provider_factory=_factory(good, calls))
    assert out["source"] == "model" and out["text"] == good, out
    billed = _ledger(db, laura_phrase.PROMPT.ref)
    assert len(billed) == 1 and billed[0].model == "claude-haiku-4-5", billed
    again = laura_phrase.phrase(db, statement=STATEMENT, facts=FACTS,
                                provider_factory=_factory(good, calls))
    assert again["source"] == "cache" and again["text"] == good, again
    assert len(calls) == 1 and len(_ledger(db, laura_phrase.PROMPT.ref)) == 1


def test_an_invented_figure_is_refused_and_the_plain_sentence_kept():
    from brambleloop.gateway import laura_phrase

    db = boot()
    out = laura_phrase.phrase(db, statement=STATEMENT, facts=FACTS,
                              provider_factory=_factory("Basket now CA$15, a bargain!", []))
    assert out["source"] == "deterministic" and out["text"] == STATEMENT, out
    assert "15" in out["reason"]
    # The refused call was still paid for and is on the ledger: never hidden.
    assert len(_ledger(db, laura_phrase.PROMPT.ref)) == 1
    assert laura_phrase.validate("x" * 700, statement=STATEMENT, facts=FACTS)


def test_a_spent_allocation_stops_before_any_call():
    from brambleloop.finance import spend_policy
    from brambleloop.gateway import laura_phrase

    db = boot()
    calls: list = []
    real = spend_policy.may_spend
    spend_policy.may_spend = lambda *a, **k: {"may_spend": False, "why": "share spent"}
    try:
        out = laura_phrase.phrase(db, statement=STATEMENT, facts=FACTS,
                                  provider_factory=_factory("anything", calls))
    finally:
        spend_policy.may_spend = real
    assert out["source"] == "deterministic" and "allocation" in out["reason"], out
    assert calls == []


def test_the_month_ceiling_parks_instead_of_paying():
    from brambleloop.gateway import failover, laura_phrase

    db = boot()
    calls: list = []
    real = failover._money
    failover._money = lambda *a, **k: {"month_spent_cad": 100.0, "month_ceiling_cad": 100.0,
                                       "agent_daily": None}
    try:
        out = laura_phrase.phrase(db, statement=STATEMENT, facts=FACTS,
                                  provider_factory=_factory("anything", calls))
    finally:
        failover._money = real
    assert out["source"] == "deterministic" and out["reason"].startswith("parked"), out
    assert calls == []


if __name__ == "__main__":
    run_tests(globals())
