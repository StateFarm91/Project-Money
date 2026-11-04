"""Offline visual spend checks, including the real generation entry point."""
import pytest

from brambleloop.visual import spend_plan as SP


def plan(**changes):
    p = SP.build(hypothesis="test", provider_model="stub", call_count=2,
                 max_spend_cad=1.0, pass_criteria=["pass"], fail_criteria=["fail"])
    p.update(changes)
    return p


def record_test_candidate(db, key, cost, token):
    from brambleloop.visual import image_production as IP
    cand = {"slug": "item", "version": "1", "release": "a" * 64,
            "role": "test", "cost_cad": cost, "_paid_call_token": token}
    verdict = {"sha256": "f" * 64, "listing": "item", "technical_status": "UNKNOWN",
               "publishable": False, "checks": {"binding": {}}}
    return IP.record_candidate(db, cand, verdict, method="autonomous", run=key,
                               stage="product_generation")["candidate_id"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, True, "1", 10**1000])
def test_bad_plan_amounts_are_refused(bad):
    with pytest.raises(SP.PlanRefused):
        SP.validate(plan(max_spend_cad=bad))
    with pytest.raises(SP.PlanRefused):
        SP.validate(plan(price_cad_per_call=bad))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, True, "1", 10**1000])
def test_bad_runtime_amounts_are_refused(bad):
    with pytest.raises(SP.PlanRefused):
        SP.guard(plan(), spent_cad=bad, calls_made=0, next_cost_cad=0.1)
    with pytest.raises(SP.PlanRefused):
        SP.guard(plan(), spent_cad=0, calls_made=0, next_cost_cad=bad)


@pytest.mark.parametrize("bad", [-1, True, 0.5, "0"])
def test_invalid_call_counter_is_refused(bad):
    with pytest.raises(SP.PlanRefused):
        SP.guard(plan(), spent_cad=0, calls_made=bad, next_cost_cad=0.1)


def test_normal_free_and_paid_amounts_still_obey_ceiling():
    SP.guard(plan(), spent_cad=0, calls_made=0, next_cost_cad=0)
    SP.guard(plan(), spent_cad=0.4, calls_made=1, next_cost_cad=0.6)
    with pytest.raises(SP.PlanRefused):
        SP.guard(plan(), spent_cad=0.4, calls_made=1, next_cost_cad=0.61)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True, "0.1"])
def test_actual_generation_refuses_invalid_provider_cost_before_call(bad):
    import test_w4_ownerimg as O
    from brambleloop.visual import image_production as IP

    class Generator:
        paid = True
        max_cost_cad_per_call = bad
        def generate(self, **kw):
            raise AssertionError("provider must not be invoked")

    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    with pytest.raises(IP.BudgetStop):
        IP._generate(db, key, Generator(), slug="item", version="1", release="a" * 64,
                     role="test", stage="product_generation", brief="", refs=[],
                     outfit=None, laura=False, judges=None, plan_attempt=1)
    assert IP.get_run(db, key)["generation_calls"] == 0


def test_paid_generation_requires_a_price_even_with_gate_open(monkeypatch):
    import test_w4_ownerimg as O
    from brambleloop.visual import gallery
    from brambleloop.visual import image_production as IP

    class UnpricedGenerator:
        paid = True
        def generate(self, **kw):
            raise AssertionError("provider must not be invoked")

    monkeypatch.setattr(gallery, "gates_now", lambda *a, **kw: {"image_generation": True})
    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    with pytest.raises(IP.BudgetStop, match="positive maximum cost"):
        IP._generate(db, key, UnpricedGenerator(), slug="item", version="1", release="a" * 64,
                     role="test", stage="product_generation", brief="", refs=[],
                     outfit=None, laura=False, judges=None, plan_attempt=1)
    assert IP.get_run(db, key)["generation_calls"] == 0


@pytest.mark.parametrize("field", ["generation_calls", "spent_cad"])
def test_corrupt_persisted_counter_is_refused_before_generator(field):
    import test_w4_ownerimg as O
    from sqlalchemy import update
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.image_records import ImageProductionRun

    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    with db.session() as session:
        session.execute(update(ImageProductionRun).where(ImageProductionRun.run_key == key)
                        .values(**{field: -1}))
    with pytest.raises(IP.BudgetStop):
        IP._generate(db, key, O.StubGenerator(), slug="item", version="1", release="a" * 64,
                     role="test", stage="product_generation", brief="", refs=[],
                     outfit=None, laura=False, judges=None, plan_attempt=1)


@pytest.mark.parametrize("receipt", [None, float("nan"), -1.0])
def test_unresolved_paid_receipt_blocks_future_calls(monkeypatch, receipt):
    import test_w4_ownerimg as O
    from brambleloop.visual import gallery
    from brambleloop.visual import image_production as IP

    class PaidStub(O.StubGenerator):
        paid, max_cost_cad_per_call = True, 0.1
        def generate(self, **kw):
            out = super().generate(**kw)
            out["cost_cad"] = receipt
            return out

    monkeypatch.setattr(gallery, "gates_now", lambda *a, **kw: {"image_generation": True})
    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    gen = PaidStub()
    args = dict(slug="item", version="1", release="a" * 64, role="test",
                stage="product_generation", brief="", refs=[], outfit=None,
                laura=False, judges=None, plan_attempt=1)
    with pytest.raises(IP.BudgetStop, match="invalid or missing cost"):
        IP._generate(db, key, gen, **args)
    with pytest.raises(IP.BudgetStop, match="unresolved cost"):
        IP._generate(db, key, gen, **args)
    assert gen.calls == 1 and IP.get_run(db, key)["generation_calls"] == 1


def test_paid_settlement_records_actual_cost_and_overrun_holds():
    import test_w4_ownerimg as O
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    token = IP._begin_generation(db, key, stage="product_generation", paid=True, next_cost=0.1)
    IP._settle_paid_generation(db, key, token, 0.08)
    assert IP.get_run(db, key)["spent_cad"] == 0.08
    # A receipt alone cannot release the hold or be applied twice.
    with pytest.raises(IP.BudgetStop, match="unresolved cost"):
        IP._begin_generation(db, key, stage="product_generation", paid=True, next_cost=0.1)
    with pytest.raises(IP.BudgetStop, match="already processed"):
        IP._settle_paid_generation(db, key, token, 0.08)
    assert IP.get_run(db, key)["spent_cad"] == 0.08
    wrong = record_test_candidate(db, key, 0.08, "different-call")
    with pytest.raises(IP.BudgetStop, match="candidate or receipt"):
        IP._complete_paid_generation(db, key, token, wrong)
    IP._complete_paid_generation(db, key, token, record_test_candidate(db, key, 0.08, token))
    assert IP._best(db, listing="item", role="test", run=key)["sha256"] == "f" * 64
    token = IP._begin_generation(db, key, stage="product_generation", paid=True, next_cost=0.1)
    with pytest.raises(IP.BudgetStop, match="exceeded"):
        IP._settle_paid_generation(db, key, token, 0.2)
    assert IP.get_run(db, key)["spent_cad"] == 0.28
    with pytest.raises(IP.BudgetStop, match="unresolved cost"):
        IP._begin_generation(db, key, stage="product_generation", paid=True, next_cost=0.1)


def test_free_settlement_does_not_erase_paid_spend_or_unknown_cost_hold():
    import test_w4_ownerimg as O
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    IP._begin_generation(db, key, stage="product_generation", paid=False, next_cost=0)
    paid = IP._begin_generation(db, key, stage="product_generation", paid=True, next_cost=0.1)
    IP._settle_paid_generation(db, key, paid, 0.08)
    IP._complete_paid_generation(db, key, paid, record_test_candidate(db, key, 0.08, paid))
    IP._settle_free_generation(db, key, 0)
    assert IP.get_run(db, key)["spent_cad"] == 0.08
    paid = IP._begin_generation(db, key, stage="product_generation", paid=True, next_cost=0.1)
    with pytest.raises(IP.BudgetStop, match="invalid or nonzero cost"):
        IP._settle_free_generation(db, key, None)
    IP._settle_paid_generation(db, key, paid, 0.05)
    IP._complete_paid_generation(db, key, paid, record_test_candidate(db, key, 0.05, paid))
    with pytest.raises(IP.BudgetStop, match="unresolved cost"):
        IP._begin_generation(db, key, stage="product_generation", paid=False, next_cost=0)
    assert IP.get_run(db, key)["spent_cad"] == 0.13


def test_paid_dispatch_exception_leaves_a_durable_hold(monkeypatch):
    import test_w4_ownerimg as O
    from brambleloop.visual import gallery
    from brambleloop.visual import image_production as IP

    class Interrupted(O.StubGenerator):
        paid, max_cost_cad_per_call = True, 0.1
        def generate(self, **kw):
            self.calls += 1
            raise RuntimeError("unknown provider outcome")

    monkeypatch.setattr(gallery, "gates_now", lambda *a, **kw: {"image_generation": True})
    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    gen = Interrupted()
    args = dict(slug="item", version="1", release="a" * 64, role="test",
                stage="product_generation", brief="", refs=[], outfit=None,
                laura=False, judges=None, plan_attempt=1)
    assert "provider_error" in IP._generate(db, key, gen, **args)
    with pytest.raises(IP.BudgetStop, match="unresolved cost"):
        IP._generate(db, key, gen, **args)
    assert gen.calls == 1


def test_ordinary_stage_checkpoint_preserves_unresolved_paid_marker():
    import test_w4_ownerimg as O
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    IP._begin_generation(db, key, stage="product_generation", paid=True, next_cost=0.1)
    IP._update(db, key, stage="product_generation", record={"outputs": {"note": "checkpoint"}})
    assert IP._stage_data(db, key)["_pending_paid_call"]["maximum_cad"] == 0.1
    with pytest.raises(IP.BudgetStop, match="unresolved cost"):
        IP._begin_generation(db, key, stage="product_generation", paid=True, next_cost=0.1)


def test_candidate_record_failure_after_receipt_keeps_paid_hold(monkeypatch):
    import test_w4_ownerimg as O
    from brambleloop.visual import gallery
    from brambleloop.visual import image_production as IP

    class Paid(O.StubGenerator):
        paid, max_cost_cad_per_call = True, 0.1
        def generate(self, **kw):
            result = super().generate(**kw)
            result["cost_cad"] = 0.08
            return result

    monkeypatch.setattr(gallery, "gates_now", lambda *a, **kw: {"image_generation": True})
    def interrupted(*args, **kwargs):
        raise RuntimeError("candidate storage interrupted")
    monkeypatch.setattr(IP, "record_candidate", interrupted)
    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    gen = Paid()
    args = dict(slug="item", version="1", release="a" * 64, role=IP.ANCHOR_ROLE,
                stage="product_generation", brief="", refs=[], outfit=None,
                laura=False, judges=O.StubJudges(), plan_attempt=1)
    with pytest.raises(RuntimeError, match="candidate storage interrupted"):
        IP._generate(db, key, gen, **args)
    assert IP.get_run(db, key)["spent_cad"] == 0.08
    with pytest.raises(IP.BudgetStop, match="unresolved cost"):
        IP._generate(db, key, gen, **args)
    assert gen.calls == 1


def test_fake_paid_generation_produces_a_selectable_candidate(monkeypatch):
    import test_w4_ownerimg as O
    from brambleloop.visual import gallery
    from brambleloop.visual import image_production as IP

    class Paid(O.StubGenerator):
        paid, max_cost_cad_per_call = True, 0.1
        def generate(self, **kw):
            result = super().generate(**kw)
            result["cost_cad"] = 0.08
            return result

    monkeypatch.setattr(gallery, "gates_now", lambda *a, **kw: {"image_generation": True})
    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    gen = Paid()
    result = IP._generate(db, key, gen, slug="item", version="1", release="a" * 64,
                          role=IP.ANCHOR_ROLE, stage="product_generation", brief="", refs=[],
                          outfit=None, laura=False, judges=O.StubJudges(), plan_attempt=1)
    selected = IP._best(db, listing="item", role=IP.ANCHOR_ROLE, run=key)
    assert selected["candidate_id"] == result["candidate_id"]
    assert IP.get_run(db, key)["spent_cad"] == 0.08 and gen.calls == 1
    # Earlier isolated development checkpoints stored this metadata as a scalar.
    from brambleloop.visual.image_records import ImageCandidate
    with db.session() as session:
        row = session.get(ImageCandidate, result["candidate_id"])
        row.checks = {**row.checks, "_paid_call_token": "legacy-test-value"}
    assert IP._best(db, listing="item", role=IP.ANCHOR_ROLE, run=key)["candidate_id"] == result["candidate_id"]


def test_real_stage_retry_reuses_candidate_after_follow_enqueue_failure(monkeypatch):
    import test_w4_ownerimg as O
    from brambleloop.visual import gallery
    from brambleloop.visual import image_production as IP

    class Paid(O.StubGenerator):
        paid, max_cost_cad_per_call = True, 0.1
        def generate(self, **kw):
            result = super().generate(**kw)
            result["cost_cad"] = 0.08
            return result

    monkeypatch.setattr(gallery, "gates_now", lambda *a, **kw: {"image_generation": True})
    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    gen = Paid()
    inputs = {"slug": "item", "version": "1", "release": "a" * 64,
              "stage": "product_generation"}
    tried = []
    def interrupted(i, k):
        tried.append((i, k))
        raise RuntimeError("follow enqueue failed")
    with pytest.raises(RuntimeError, match="follow enqueue failed"):
        IP.run_stage(db, inputs, follow=interrupted, generator=gen, judges=O.StubJudges())
    sent = []
    result = IP.run_stage(db, inputs, follow=lambda i, k: sent.append((i, k)),
                          generator=gen, judges=O.StubJudges())
    assert result["next"] == "fidelity_gate" and len(sent) == 1 and sent[0] == tried[0]
    assert gen.calls == 1 and IP.get_run(db, key)["generation_calls"] == 1
    assert IP.get_run(db, key)["spent_cad"] == 0.08
    # A distinct correction round is a new stage invocation, not a replay.
    IP.run_stage(db, {**inputs, "round": 1}, follow=lambda i, k: sent.append((i, k)),
                 generator=gen, judges=O.StubJudges())
    assert gen.calls == 2


def test_stage_replay_does_not_bypass_an_unrelated_pending_paid_call(monkeypatch):
    import test_w4_ownerimg as O
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    gen = O.StubGenerator()
    inputs = {"slug": "item", "version": "1", "release": "a" * 64,
              "stage": "product_generation"}
    IP.run_stage(db, inputs, follow=lambda i, k: None, generator=gen, judges=O.StubJudges())
    IP._begin_generation(db, key, stage="other", paid=True, next_cost=0.1)
    result = IP.run_stage(db, inputs, follow=lambda i, k: None, generator=gen,
                          judges=O.StubJudges())
    assert "unresolved cost" in result["blocked_reason"]
    assert gen.calls == 1


def test_stage_recovers_candidate_after_marker_completion_interruption(monkeypatch):
    import test_w4_ownerimg as O
    from brambleloop.visual import gallery
    from brambleloop.visual import image_production as IP

    class Paid(O.StubGenerator):
        paid, max_cost_cad_per_call = True, 0.1
        def generate(self, **kw):
            result = super().generate(**kw)
            result["cost_cad"] = 0.08
            return result

    monkeypatch.setattr(gallery, "gates_now", lambda *a, **kw: {"image_generation": True})
    db = O.make_db()
    key = IP._ensure_run(db, "item", "1", "a" * 64, "")
    inputs = {"slug": "item", "version": "1", "release": "a" * 64,
              "stage": "product_generation"}
    gen = Paid()
    complete = IP._complete_paid_generation
    def interrupted(*args):
        raise RuntimeError("completion interrupted")
    monkeypatch.setattr(IP, "_complete_paid_generation", interrupted)
    with pytest.raises(RuntimeError, match="completion interrupted"):
        IP.run_stage(db, inputs, follow=lambda i, k: None, generator=gen, judges=O.StubJudges())
    assert IP.get_run(db, key)["spent_cad"] == 0.08
    monkeypatch.setattr(IP, "_complete_paid_generation", complete)
    result = IP.run_stage(db, inputs, follow=lambda i, k: None, generator=gen,
                          judges=O.StubJudges())
    assert result["next"] == "fidelity_gate" and gen.calls == 1
    assert "_pending_paid_call" not in IP._stage_data(db, key)


def test_stage_retry_holds_when_recorded_candidate_bytes_change(monkeypatch):
    import test_w4_ownerimg as O
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.visual import image_production as IP

    db = O.make_db()
    IP._ensure_run(db, "item", "1", "a" * 64, "")
    inputs = {"slug": "item", "version": "1", "release": "a" * 64,
              "stage": "product_generation"}
    gen = O.StubGenerator()
    IP.run_stage(db, inputs, follow=lambda i, k: None, generator=gen, judges=O.StubJudges())
    monkeypatch.setattr(ArtifactStore, "get", lambda *args, **kwargs: b"changed bytes")
    result = IP.run_stage(db, inputs, follow=lambda i, k: None, generator=gen,
                          judges=O.StubJudges())
    assert "artifact changed" in result["blocked_reason"] and gen.calls == 1
