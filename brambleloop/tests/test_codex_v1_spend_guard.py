"""Offline visual spend checks, including the real generation entry point."""
import pytest

from brambleloop.visual import spend_plan as SP


def plan(**changes):
    p = SP.build(hypothesis="test", provider_model="stub", call_count=2,
                 max_spend_cad=1.0, pass_criteria=["pass"], fail_criteria=["fail"])
    p.update(changes)
    return p


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
    IP._settle_free_generation(db, key, 0)
    assert IP.get_run(db, key)["spent_cad"] == 0.08
    paid = IP._begin_generation(db, key, stage="product_generation", paid=True, next_cost=0.1)
    with pytest.raises(IP.BudgetStop, match="invalid or nonzero cost"):
        IP._settle_free_generation(db, key, None)
    IP._settle_paid_generation(db, key, paid, 0.05)
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
