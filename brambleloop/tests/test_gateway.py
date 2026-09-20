"""Model Gateway tests (Master Plan section 27).

The gateway's job is not to make models smart. It is to make model calls accountable: pinned
prompts, strict output, recorded cost, real failover, and an absolute ceiling on what a model
is allowed to decide. Everything below tests one of those five.

No real provider is configured in this environment, and the suite is deliberately built so
that fact is visible rather than papered over: `EchoProvider` mocks the *transport*, never
judgement, and one test asserts that the system reports zero real providers rather than
implying an integration it does not have.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import BudgetExceeded, Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.resilience import MalformedModelOutput  # noqa: E402
from brambleloop.gateway import evals as eval_mod  # noqa: E402
from brambleloop.gateway import prompts as prompt_registry  # noqa: E402
from brambleloop.gateway.model_gateway import (  # noqa: E402
    DeterministicAuthorityViolation, EchoProvider, ModelGateway, NoProviderAvailable,
    available_providers,
)


def _echo(payload: dict | str, **kw) -> EchoProvider:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return EchoProvider(scripted=lambda s, u: text, **kw)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


# ---- the rule that outranks everything ------------------------------------


def test_a_model_may_not_decide_what_the_compiler_decides():
    """Section 27: deterministic validation wins even if every LLM disagrees."""
    try:
        ModelGateway.require_deterministic("is row 14's stitch count correct?")
    except DeterministicAuthorityViolation as e:
        assert "compiler is right" in str(e)
    else:
        raise AssertionError("a model was allowed authority over pattern correctness")


def test_no_prompt_asks_a_model_for_pattern_instructions():
    """Section 2. This is a standing constraint, so it is asserted, not just documented."""
    banned = ("stitch count", "how many stitches", "row-by-row", "write the pattern",
              "instructions for", "how to crochet")
    for p in prompt_registry.all_prompts():
        body = (p.system + " " + p.template).lower()
        for phrase in banned:
            assert phrase not in body, f"{p.ref} asks a model for pattern content: {phrase!r}"


# ---- pinning ---------------------------------------------------------------


def test_prompts_are_pinned_and_hashed():
    p = prompt_registry.get("concept.naming@1")
    assert p.ref == "concept.naming@1"
    assert len(p.sha256) == 64
    assert prompt_registry.get("concept.naming@1").sha256 == p.sha256


def test_a_released_prompt_cannot_be_edited_in_place():
    """Edit a prompt and last month's output becomes unexplainable."""
    from brambleloop.gateway.prompts import Prompt, PromptIsImmutable, register

    original = prompt_registry.get("concept.naming@1")
    try:
        register(Prompt(name=original.name, version=original.version,
                        system="something else entirely", template=original.template))
    except PromptIsImmutable as e:
        assert "new version" in str(e)
    else:
        raise AssertionError("a released prompt was edited in place")


def test_registering_the_same_prompt_twice_is_a_no_op():
    from brambleloop.gateway.prompts import register

    p = prompt_registry.get("listing.polish@1")
    assert register(p) is p


def test_a_missing_template_value_fails_loudly():
    """A silently empty placeholder asks a model about nothing and gets a confident answer."""
    p = prompt_registry.get("concept.naming@1")
    try:
        p.render(category="blanket")
    except KeyError as e:
        assert "missing template values" in str(e)
    else:
        raise AssertionError("a prompt rendered with missing values")


def test_the_prompt_reference_and_hash_travel_with_every_response():
    g = ModelGateway([_echo({"names": ["A", "B", "C"]})])
    out = g.complete_json("concept.naming@1", agent="market_radar",
                          values={"category": "c", "motifs": "m", "season": "s"})
    assert out["_meta"]["prompt"] == "concept.naming@1"
    assert len(out["_meta"]["prompt_sha256"]) == 64


# ---- strict output ---------------------------------------------------------


def test_prose_where_json_was_expected_is_rejected():
    g = ModelGateway([_echo("Sure! Here are some lovely names for your blanket.")])
    try:
        g.complete_json("concept.naming@1", agent="market_radar",
                        values={"category": "c", "motifs": "m", "season": "s"})
    except MalformedModelOutput:
        pass
    else:
        raise AssertionError("prose was accepted as a structured response")


def test_json_missing_a_required_field_is_rejected():
    g = ModelGateway([_echo({"something_else": 1})])
    try:
        g.complete_json("concept.naming@1", agent="market_radar",
                        values={"category": "c", "motifs": "m", "season": "s"})
    except MalformedModelOutput as e:
        assert "names" in str(e)
    else:
        raise AssertionError("a half-populated object travelled downstream")


def test_a_bad_provider_is_retried_then_abandoned_not_looped_on():
    g = ModelGateway([_echo("not json")], breaker_threshold=99)
    try:
        g.complete_json("concept.naming@1", agent="market_radar",
                        values={"category": "c", "motifs": "m", "season": "s"})
    except MalformedModelOutput:
        pass
    assert len(g.calls) == 2, f"expected exactly 2 attempts, got {len(g.calls)}"


# ---- failover --------------------------------------------------------------


def test_failover_moves_to_the_next_provider():
    broken = _echo({"names": ["A", "B", "C"]}, fail_times=99)
    broken.name = "broken"
    good = _echo({"names": ["A", "B", "C"]})
    good.name = "good"
    g = ModelGateway([broken, good])
    out = g.complete_json("concept.naming@1", agent="market_radar",
                          values={"category": "c", "motifs": "m", "season": "s"})
    assert out["_meta"]["provider"] == "good"
    assert any(not c.ok and c.provider == "broken" for c in g.calls)


def test_a_provider_that_is_down_opens_its_circuit_and_is_skipped():
    """An outage must not become thousands of doomed calls, each costing money and time."""
    broken = _echo({"names": ["A", "B", "C"]}, fail_times=99)
    broken.name = "broken"
    good = _echo({"names": ["A", "B", "C"]})
    good.name = "good"
    g = ModelGateway([broken, good], breaker_threshold=2)
    for _ in range(4):
        g.complete_json("concept.naming@1", agent="market_radar",
                        values={"category": "c", "motifs": "m", "season": "s"})
    assert "broken" in g.summary()["open_circuits"]
    attempts_on_broken = sum(c.provider == "broken" for c in g.calls)
    assert attempts_on_broken <= 3, f"kept hammering a dead provider {attempts_on_broken}x"


def test_with_no_provider_the_gateway_says_so_instead_of_pretending():
    g = ModelGateway([])
    try:
        g.complete_json("concept.naming@1", agent="market_radar",
                        values={"category": "c", "motifs": "m", "season": "s"})
    except NoProviderAvailable as e:
        assert "no API key exists" in str(e)
    else:
        raise AssertionError("a gateway with no providers returned something")


def test_the_system_is_honest_that_no_real_provider_is_configured():
    """Never claim an integration exists until it is verified."""
    assert available_providers() == [], available_providers()


# ---- cost ------------------------------------------------------------------


def test_model_cost_is_recorded_against_the_calling_agent():
    db = _db()
    reg = Registry(db)
    paid = _echo({"names": ["A", "B", "C"]})
    paid.cost_per_1k_input_cad = 3.0
    paid.cost_per_1k_output_cad = 15.0
    g = ModelGateway([paid], registry=reg)
    g.complete_json("concept.naming@1", agent="market_radar",
                    values={"category": "mosaic blanket", "motifs": "fir, star",
                            "season": "Christmas"})
    assert g.spend_cad() > 0
    assert reg.spend_today("market_radar") > 0


def test_a_runaway_model_loop_hits_the_agent_daily_ceiling():
    """The spend guard has to stop a loop before it is a bill, not after."""
    db = _db()
    reg = Registry(db)
    pricey = _echo({"names": ["A" * 4000, "B", "C"]})
    pricey.cost_per_1k_input_cad = 50.0
    pricey.cost_per_1k_output_cad = 200.0
    g = ModelGateway([pricey], registry=reg)
    hit = False
    for _ in range(50):
        try:
            g.complete_json("concept.naming@1", agent="market_radar",
                            values={"category": "x" * 4000, "motifs": "m", "season": "s"})
        except BudgetExceeded:
            hit = True
            break
    assert hit, "a runaway loop never hit the ceiling"


def test_the_summary_reports_what_actually_happened():
    good = _echo({"names": ["A", "B", "C"]})
    g = ModelGateway([good])
    g.complete_json("concept.naming@1", agent="market_radar",
                    values={"category": "c", "motifs": "m", "season": "s"})
    s = g.summary()
    assert s["calls"] == 1 and s["ok"] == 1 and s["failed"] == 0
    assert s["providers"] == ["echo"]


# ---- evals -----------------------------------------------------------------


def test_evals_pass_on_well_behaved_output():
    responses = {
        "concept.naming@1": {"names": ["Nordic Forest", "Winter Grove", "Pine Hollow"]},
        "listing.polish@1": {"description": eval_mod.SAMPLE_DESCRIPTION,
                             "changed_facts": False},
        "review.mining@1": {"themes": [{"theme": "row 4 count", "count": 2,
                                        "is_defect_report": True}]},
    }
    results = _run_scripted(responses)
    assert all(r.passed for r in results), [(r.case, r.problems) for r in results]


def test_evals_catch_a_name_that_makes_an_unsupported_claim():
    responses = {
        "concept.naming@1": {"names": ["Nordic Forest", "Easy 120cm Throw", "Pine Hollow"]},
        "listing.polish@1": {"description": eval_mod.SAMPLE_DESCRIPTION,
                             "changed_facts": False},
        "review.mining@1": {"themes": [{"theme": "t", "count": 1}]},
    }
    results = _run_scripted(responses)
    naming = next(r for r in results if "naming" in r.case)
    assert not naming.passed and any("unsupported claim" in p for p in naming.problems)


def test_evals_catch_a_polish_that_changed_the_facts():
    mangled = eval_mod.SAMPLE_DESCRIPTION.replace("90 x 122 cm", "120 x 150 cm")
    responses = {
        "concept.naming@1": {"names": ["A", "B", "C"]},
        "listing.polish@1": {"description": mangled, "changed_facts": False},
        "review.mining@1": {"themes": [{"theme": "t", "count": 1}]},
    }
    results = _run_scripted(responses)
    polish = next(r for r in results if "polish" in r.case)
    assert not polish.passed, polish
    assert any("invented" in p or "dropped" in p for p in polish.problems)


def test_evals_catch_invented_review_counts():
    responses = {
        "concept.naming@1": {"names": ["A", "B", "C"]},
        "listing.polish@1": {"description": eval_mod.SAMPLE_DESCRIPTION,
                             "changed_facts": False},
        "review.mining@1": {"themes": [{"theme": "made up", "count": 0}]},
    }
    results = _run_scripted(responses)
    mining = next(r for r in results if "mining" in r.case)
    assert not mining.passed and any("positive count" in p for p in mining.problems)


def _run_scripted(responses: dict[str, dict]):
    """Route each prompt to its scripted reply by matching the system text."""
    by_system = {prompt_registry.get(ref).system: json.dumps(body)
                 for ref, body in responses.items()}
    provider = EchoProvider(scripted=lambda system, user: by_system[system])
    return eval_mod.run_evals(ModelGateway([provider]))


def test_every_tier_routes_to_a_model_the_billing_table_prices():
    """The two tables cannot drift, because there is only one of them now.

    Found in production: the cheap tier routed to "claude-haiku-4-5" and the billing table
    held only "claude-haiku-4-5-20251001", so `PRICES.get(model, (0.0, 0.0))` priced every
    cheap call at nothing. A tournament generated eighty concepts and recorded CA$0.00, and
    the CA$25 monthly ceiling could never be reached by cheap work -- an unbounded budget
    that reports zero.
    """
    from brambleloop.gateway import routing
    from brambleloop.gateway.anthropic import PRICES_USD_PER_MTOK

    for key, tier in routing.TIERS.items():
        assert tier.model in PRICES_USD_PER_MTOK, (key, tier.model)
        assert tier.usd_per_1m_input > 0, key
        assert tier.usd_per_1m_output > 0, key


def test_the_estimate_and_the_bill_are_the_same_price():
    """Routing used to restate the prices and the two disagreed by a factor of three.

    This file said the deep tier cost USD 5/25 per million tokens; the provider billed 15/75.
    Every estimate in the system was a third of the truth, and the first live expedition --
    estimated at CA$0.15 a field -- cost CA$1.02. An estimate wrong in the cheap direction is
    worse than no estimate, because it is the number a budget decision gets made on.
    """
    from brambleloop.gateway import routing
    from brambleloop.gateway.anthropic import USD_TO_CAD, AnthropicProvider

    for key, tier in routing.TIERS.items():
        provider = AnthropicProvider(model=tier.model)
        # The provider prices per 1k tokens in CAD; the tier per 1M in USD. Same number.
        billed_in = provider.cost_per_1k_input_cad * 1000 / USD_TO_CAD
        billed_out = provider.cost_per_1k_output_cad * 1000 / USD_TO_CAD
        assert abs(billed_in - tier.usd_per_1m_input) < 0.01, (key, billed_in)
        assert abs(billed_out - tier.usd_per_1m_output) < 0.01, (key, billed_out)


def test_a_model_with_no_price_is_refused_rather_than_billed_at_zero():
    """"An unpriced call is an unbounded one" was already written, in one of two code paths.

    `_cost_for` raised for an unpriced model. `AnthropicProvider.__post_init__` silently
    defaulted to (0.0, 0.0) -- and the gateway used the silent one. Two code paths for one
    rule, and the quiet one wins by default.
    """
    from brambleloop.gateway.anthropic import AnthropicProvider, BudgetExceeded

    raised = None
    try:
        AnthropicProvider(model="claude-something-nobody-priced")
    except BudgetExceeded as e:
        raised = e
    assert raised is not None, "an unpriced model was constructed and would bill at zero"
    assert "unbounded" in str(raised)


def test_an_unpriced_tier_cannot_produce_an_estimate():
    """An estimate for a model nobody can bill is a guess wearing a decimal point."""
    from brambleloop.gateway import routing

    stray = routing.Tier("stray", "claude-not-in-the-table", vision=True, use_for="test")
    raised = None
    try:
        stray.cost_cad(1000, 1000)
    except routing.UnpricedTier as e:
        raised = e
    assert raised is not None
    assert "does not price" in str(raised)


def test_a_model_cost_is_attributable_to_the_job_that_spent_it():
    """#31: without a job id every cost is unattributed and every artefact looks like a floor.

    `registry.record_cost` always accepted a job id; the gateway simply never passed one, so
    `unit_costs()` could match no cost to the audit row that produced a pattern or a listing.
    The ratios were correct arithmetic over an empty attribution the whole time.
    """
    import tempfile

    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import CostEntry
    from brambleloop.gateway.model_gateway import ModelGateway

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/attrib.sqlite")
    db.create_all()
    registry = Registry(db)
    registry.seed_defaults()

    # A real job row: CostEntry.job_id is a foreign key, which is itself the guarantee that
    # an attributed cost points at work that actually happened rather than at a number.
    from brambleloop.queue.durable import JobQueue

    job = JobQueue(db).enqueue("market_radar", "radar.scan", {})

    priced = _echo({"names": ["A", "B", "C"]},
                   cost_per_1k_input_cad=0.01, cost_per_1k_output_cad=0.05)
    gateway = ModelGateway([priced], registry=registry, job_id=job.id)
    gateway.complete_json("concept.naming@1", agent="market_radar",
                          values={"category": "c", "motifs": "m", "season": "s"})

    with db.session() as s:
        rows = list(s.scalars(select(CostEntry)))
    assert rows, "no cost was recorded at all"
    assert all(r.job_id == job.id for r in rows), [(r.agent, r.job_id) for r in rows]


def test_a_call_priced_at_zero_still_leaves_the_tokens_it_spent():
    """The condition that hid the price bug, and made it unrecoverable afterwards.

    `_record` wrote a ledger row only when `cost > 0`, so a call mispriced at zero wrote no
    row at all -- not a zero, nothing. Eighty concepts were generated in production and left
    no trace, and with no stored tokens there was nothing to re-price the month from once the
    price was fixed. A zero-cost row carrying real token counts says something is wrong with
    the price; silence is indistinguishable from not having run.
    """
    import tempfile

    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import CostEntry
    from brambleloop.gateway.model_gateway import ModelGateway

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/zero.sqlite")
    db.create_all()
    registry = Registry(db)
    registry.seed_defaults()

    # A provider whose prices are zero is exactly what a missing price table entry produced.
    free = _echo({"names": ["A", "B", "C"]},
                 cost_per_1k_input_cad=0.0, cost_per_1k_output_cad=0.0)
    gateway = ModelGateway([free], registry=registry)
    gateway.complete_json("concept.naming@1", agent="market_radar",
                          values={"category": "c", "motifs": "m", "season": "s"})

    with db.session() as s:
        rows = list(s.scalars(select(CostEntry)))
    assert rows, "a call that billed nothing left no evidence that it happened"
    assert rows[0].amount_cad == 0.0
    assert rows[0].tokens_in or rows[0].tokens_out, "the tokens were not kept either"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
