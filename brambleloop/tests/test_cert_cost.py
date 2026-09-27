"""Certification G: cost governance, attacked with stand-in providers and temp SQLite DBs.

No network: every provider here is a counting stand-in and `images._post` is replaced for
the duration of each image test. Tests that expose a defect are left failing on purpose.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, CostEntry, SpendReservation  # noqa: E402
from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.finance import reservations, spend_policy, spend_report  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import images  # noqa: E402
from brambleloop.gateway.model_gateway import ModelGateway, ModelResponse  # noqa: E402

CHEAP = "claude-haiku-4-5"
VALUES = {"category": "c", "motifs": "m", "season": "s"}
IMG_ENV = {"BRAMBLELOOP_IMAGE_PROVIDER": "flux-2-pro", "BRAMBLELOOP_IMAGE_KEY": "stand-in"}


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _spend(db, cad, *, agent="gateway", provider="", department="", purpose="t"):
    with db.session() as s:
        s.add(CostEntry(agent=agent, amount_cad=cad, kind="llm", provider=provider,
                        department=department, purpose=purpose))


def _reservations(db) -> list:
    with db.session() as s:
        rows = list(s.scalars(select(SpendReservation)))
        for r in rows:
            s.expunge(r)
        return rows


def _refusals(db) -> list:
    with db.session() as s:
        return [dict(a.detail or {}) for a in s.scalars(select(AuditLog))
                if a.action == spend_report.REFUSED_ACTION]


@dataclass
class StandIn:
    """A counting provider. `fail` raises on every call."""

    name: str = "standin"
    model: str = CHEAP
    cost_per_1k_input_cad: float = round(1.0 / 1000 * gw.USD_TO_CAD, 8)
    cost_per_1k_output_cad: float = round(5.0 / 1000 * gw.USD_TO_CAD, 8)
    fail: bool = False
    calls: int = 0

    def complete(self, system, user, *, max_tokens):
        self.calls += 1
        if self.fail:
            raise TransientError("stand-in upstream failure")
        text = json.dumps({"names": ["A", "B", "C"]})
        return ModelResponse(text=text, provider=self.name, model=self.model,
                             input_tokens=len(user) // 4, output_tokens=200, latency_ms=0.0)


def _raises(fn, exc) -> BaseException:
    try:
        fn()
    except exc as e:  # noqa: PERF203
        return e
    raise AssertionError(f"accepted; expected {exc.__name__}")


class _Post:
    """Replace images._post with a counter; always restored."""

    def __init__(self, fail: bool = False):
        self.calls, self.fail = 0, fail

    def __call__(self, *a, **k):
        self.calls += 1
        if self.fail:
            raise TransientError("stand-in image provider down")
        import base64
        return {"data": [{"b64_json": base64.b64encode(b"\x89PNG stand-in").decode()}]}

    def __enter__(self):
        self._orig = images._post
        images._post = self
        return self

    def __exit__(self, *exc):
        images._post = self._orig
        return False


# --- monthly ceiling refuses before the provider ----------------------------------------------

def test_exhausted_month_refuses_before_the_model_provider_is_called():
    db = _db()
    _spend(db, spend_policy.CEILING_CAD - 0.0001)
    p = StandIn()
    g = ModelGateway([p], registry=Registry(db))
    _raises(lambda: g.complete_json("concept.naming@1", agent="market_radar", values=VALUES),
            gw.BudgetExceeded)
    assert p.calls == 0, "provider was called after the ceiling refused"
    assert _refusals(db) and _refusals(db)[0]["which"] == "monthly_ceiling"
    assert _reservations(db) == [], "a refused call left a reservation"


def test_exhausted_month_refuses_before_the_image_provider_is_called():
    db = _db()
    _spend(db, spend_policy.CEILING_CAD)
    with _Post() as post, tempfile.TemporaryDirectory() as work:
        _raises(lambda: images.generate("p", env=IMG_ENV, work_dir=work, db=db),
                gw.BudgetExceeded)
    assert post.calls == 0


# --- agent daily ceiling ----------------------------------------------------------------------

def test_agent_daily_ceiling_refuses_and_names_itself():
    db = _db()
    _spend(db, 0.99, agent="quality_director")
    e = _raises(lambda: gw.check_budget_cad(db, estimate_cad=0.05, agent="quality_director",
                                            holder="h1"), gw.AgentCeilingExceeded)
    assert "daily" in str(e)
    assert _refusals(db)[-1]["which"] == "agent_daily_ceiling"
    assert _reservations(db) == []


# --- concurrency ------------------------------------------------------------------------------

def test_two_holders_cannot_together_exceed_the_monthly_ceiling():
    db = _db()
    _spend(db, spend_policy.CEILING_CAD - 1.0)
    a = gw.check_budget_cad(db, estimate_cad=0.45, holder="A")
    b = gw.check_budget_cad(db, estimate_cad=0.45, holder="B")
    assert a["reservation_id"] and b["reservation_id"]
    _raises(lambda: gw.check_budget_cad(db, estimate_cad=0.45, holder="C"), gw.BudgetExceeded)
    # A second reservation by the SAME holder is not counted against itself: the holder is
    # trusted to pass its own in-flight spend as uncommitted_cad.
    same = _raises(lambda: gw.check_budget_cad(db, estimate_cad=0.45, holder="A",
                                               uncommitted_cad=0.45), gw.BudgetExceeded)
    assert same


def test_two_holders_cannot_together_exceed_an_agents_daily_ceiling():
    """The agent check reads billed spend + this caller's uncommitted only; other holders'
    live reservations for the same agent are ignored, so two concurrent callers for one
    agent each fit and together overshoot."""
    db = _db()                                   # quality_director: CA$1.00/day
    gw.check_budget_cad(db, estimate_cad=0.6, agent="quality_director", holder="A")
    _raises(lambda: gw.check_budget_cad(db, estimate_cad=0.6, agent="quality_director",
                                        holder="B"), gw.AgentCeilingExceeded)


def test_two_holders_cannot_together_exceed_a_provider_ceiling():
    db = _db()
    saved = dict(spend_policy.PROVIDER_CEILINGS_CAD)
    spend_policy.PROVIDER_CEILINGS_CAD["anthropic"] = 1.0
    try:
        gw.check_budget_cad(db, estimate_cad=0.6, provider="anthropic", holder="A")
        _raises(lambda: gw.check_budget_cad(db, estimate_cad=0.6, provider="anthropic",
                                            holder="B"), gw.BudgetExceeded)
    finally:
        spend_policy.PROVIDER_CEILINGS_CAD.clear()
        spend_policy.PROVIDER_CEILINGS_CAD.update(saved)


# --- failure, release, reconciliation ---------------------------------------------------------

def test_a_failing_model_provider_releases_without_billing():
    db = _db()
    p = StandIn(fail=True)
    g = ModelGateway([p], registry=Registry(db))
    _raises(lambda: g.complete_json("concept.naming@1", agent="market_radar", values=VALUES),
            Exception)
    rows = _reservations(db)
    assert p.calls == 2 and len(rows) == 2, (p.calls, len(rows))
    assert all(r.released_at is not None and r.actual_cad is None for r in rows)
    assert reservations.outstanding(db)["cad"] == 0.0
    assert gw.spent_this_month_cad(db) == 0.0


def test_a_failing_image_provider_releases_without_billing():
    db = _db()
    with _Post(fail=True) as post, tempfile.TemporaryDirectory() as work:
        _raises(lambda: images.generate("p", env=IMG_ENV, work_dir=work, db=db), Exception)
    (row,) = _reservations(db)
    assert post.calls == 1 and row.released_at is not None and row.actual_cad is None


def test_a_successful_image_render_releases_with_its_price():
    db = _db()
    with _Post() as post, tempfile.TemporaryDirectory() as work:
        out = images.generate("p", env=IMG_ENV, work_dir=work, db=db)
    (row,) = _reservations(db)
    assert post.calls == 1 and row.actual_cad == images.BY_KEY["flux-2-pro"].cad_per_image
    assert out["reservation_id"] == row.id


def test_release_returns_headroom_and_cannot_be_replayed():
    db = _db()
    base = gw.check_budget_cad(db, estimate_cad=0.0, holder="B", reserve=False)["headroom_cad"]
    a = gw.check_budget_cad(db, estimate_cad=2.0, holder="A")
    during = gw.check_budget_cad(db, estimate_cad=0.0, holder="B", reserve=False)
    assert round(base - during["headroom_cad"], 6) == 2.0
    assert gw.release_reservation(db, a["reservation_id"], actual_cad=1.7) is True
    after = gw.check_budget_cad(db, estimate_cad=0.0, holder="B", reserve=False)
    assert after["headroom_cad"] == base
    assert gw.release_reservation(db, a["reservation_id"], actual_cad=0.0) is False
    (row,) = _reservations(db)
    assert row.amount_cad == 2.0 and row.actual_cad == 1.7, "second release rewrote the bill"
    assert gw.release_reservation(db, None) is False and gw.release_reservation(db, 99999) is False


def test_gateway_records_estimate_beside_actual_and_the_ledger_reconciles():
    """The reservation row gets `actual_cad`, but the gateway's ledger row is written by
    `Registry.record_cost`, which sets neither `estimated_cad`, `provider`, `model` nor
    `purpose`. estimate_drift then counts every gateway call as 'carrying no reservation'."""
    db = _db()
    p = StandIn()
    g = ModelGateway([p], registry=Registry(db))
    out = g.complete_json("concept.naming@1", agent="market_radar", values=VALUES)
    (res,) = _reservations(db)
    assert res.actual_cad is not None and abs(res.actual_cad - out["_meta"]["cost_cad"]) < 1e-6
    assert res.amount_cad >= res.actual_cad, "estimate under the bill"
    with db.session() as s:
        (entry,) = list(s.scalars(select(CostEntry)))
        got = (entry.estimated_cad, entry.provider, entry.model, entry.purpose)
    assert got[0] and got[0] > 0 and got[1] == "standin" and got[2] == CHEAP, (
        f"gateway ledger row lacks reconciliation dimensions: estimated_cad={got[0]} "
        f"provider={got[1]!r} model={got[2]!r} purpose={got[3]!r}")
    drift = spend_report.estimate_drift(db)
    assert drift["calls_with_no_reservation"] == 0, drift["calls_with_no_reservation"]


def test_a_provider_ceiling_binds_on_spend_made_through_the_model_gateway():
    db = _db()
    saved = dict(spend_policy.PROVIDER_CEILINGS_CAD)
    p = StandIn()
    g = ModelGateway([p], registry=Registry(db))
    from brambleloop.gateway import prompts as _prompts
    prompt = _prompts.get("concept.naming@1")
    one = g._estimate_cad(prompt, p, prompt.render(**VALUES))
    cap = round(one * 1.5, 6)                    # room for exactly one call
    spend_policy.PROVIDER_CEILINGS_CAD["standin"] = cap
    try:
        for _ in range(30):
            try:
                g.complete_json("concept.naming@1", agent="market_radar", values=VALUES)
            except gw.BudgetExceeded:
                break
        spent = gw.spent_this_month_cad(db)
        assert spent <= cap + 1e-9, (
            f"provider 'standin' capped at CA${cap} was called {p.calls}x and "
            f"spent CA${spent:.6f}: the ledger rows carry no provider, so by_provider never "
            f"sees them")
    finally:
        spend_policy.PROVIDER_CEILINGS_CAD.clear()
        spend_policy.PROVIDER_CEILINGS_CAD.update(saved)


# --- unpriced / unknown -----------------------------------------------------------------------

def test_an_unpriced_anthropic_model_is_refused_not_priced_at_zero():
    db = _db()
    _raises(lambda: gw.check_budget(db, model="claude-imaginary-9", input_tokens=10,
                                    max_tokens=10, agent="market_radar"), gw.BudgetExceeded)
    assert _refusals(db)[-1]["which"] == "unpriced_model"
    _raises(lambda: gw.AnthropicProvider(model="claude-imaginary-9"), gw.BudgetExceeded)
    _raises(lambda: gw.estimate_cad("", input_tokens=1, output_tokens=1), gw.BudgetExceeded)


def test_the_model_gateway_refuses_an_unpriced_model_rather_than_pricing_it_at_zero():
    """`ModelGateway._estimate_cad` falls back to the provider's self-declared rates when the
    model is not in the price table. A provider declaring 0.0 is estimated at CA$0 and
    billed at CA$0 however many tokens it uses."""
    db = _db()
    p = StandIn(name="other", model="unpriced-model-x", cost_per_1k_input_cad=0.0,
                cost_per_1k_output_cad=0.0)
    g = ModelGateway([p], registry=Registry(db))
    try:
        g.complete_json("concept.naming@1", agent="market_radar", values=VALUES)
    except gw.BudgetExceeded:
        assert p.calls == 0
        return
    raise AssertionError(f"unpriced model called {p.calls}x and billed "
                         f"CA${gw.spent_this_month_cad(db):.4f}")


def test_unknown_image_providers_are_refused_before_any_request():
    with _Post() as post, tempfile.TemporaryDirectory() as work:
        _raises(lambda: images.generate("p", env=IMG_ENV, work_dir=work,
                                        provider_key="midjourney", db=_db()),
                images.ImagesRefused)
        _raises(lambda: images.generate("p", env={"BRAMBLELOOP_IMAGE_PROVIDER": "midjourney",
                                                  "BRAMBLELOOP_IMAGE_KEY": "k"},
                                        work_dir=work, db=_db()), images.ImagesRefused)
        _raises(lambda: images.generate("p", env={}, work_dir=work, db=_db()),
                images.ImagesNotConfigured)
    assert post.calls == 0


def test_a_nonsense_estimate_cannot_pass_a_full_month():
    """NaN compares False against the ceiling and a negative estimate subtracts from it."""
    db = _db()
    _spend(db, spend_policy.CEILING_CAD)
    passed = []
    for bad in (float("nan"), -5.0):
        try:
            gw.check_budget_cad(db, estimate_cad=bad, holder="A", reserve=False)
            passed.append(bad)
        except (gw.BudgetExceeded, ValueError):
            pass
    assert not passed, f"check_budget_cad passed a spent month with estimates {passed}"


def test_every_production_model_gateway_is_constructed_with_a_registry():
    """Without `registry` the gateway performs no ceiling check, no reservation and writes
    no ledger row ("the test configuration and no other")."""
    offenders = []
    for path in (ROOT / "src/brambleloop").rglob("*.py"):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"\bModelGateway\(\[", line) and "registry=" not in line:
                offenders.append(f"{path.relative_to(ROOT)}:{i}")
    assert not offenders, f"ModelGateway built without a registry (unbudgeted): {offenders}"


# --- empty tables are no cap; entries bind ----------------------------------------------------

def test_empty_provider_and_department_tables_report_no_cap():
    assert spend_policy.PROVIDER_CEILINGS_CAD == {}
    assert spend_policy.DEPARTMENT_ALLOCATION == {}
    st = spend_policy.state()
    assert st["provider_ceilings"].startswith("0 provider ceiling(s) set")
    assert "no cap, not a cap of zero" in st["provider_ceilings"]
    assert "no cap, not a cap of zero" in st["department_caps"]
    db = _db()
    out = spend_policy.may_spend(db, "unallocated_purpose", department="intel")
    assert out["may_spend"] is True and out["capped"] is False
    assert out["department_capped"] is False and "no cap" in out["why"]
    chk = gw.check_budget_cad(db, estimate_cad=0.01, provider="anthropic", reserve=False)
    assert chk["provider_ceiling_cad"] is None
    gov = spend_report.governance(db)
    assert gov["provider_ceilings_cad"] == {} and gov["department_allocations"] == {}


def test_an_entry_in_either_table_is_enforced():
    db = _db()
    _spend(db, 0.49, provider="anthropic", department="intel")
    saved_p = dict(spend_policy.PROVIDER_CEILINGS_CAD)
    saved_d = dict(spend_policy.DEPARTMENT_ALLOCATION)
    try:
        spend_policy.PROVIDER_CEILINGS_CAD["anthropic"] = 0.5
        spend_policy.DEPARTMENT_ALLOCATION["intel"] = 0.004       # CA$0.40 of 100
        _raises(lambda: gw.check_budget_cad(db, estimate_cad=0.02, provider="anthropic",
                                            holder="A"), gw.BudgetExceeded)
        assert _refusals(db)[-1]["which"] == "provider_ceiling"
        gw.check_budget_cad(db, estimate_cad=0.02, provider="gpt-image-2", holder="A",
                            reserve=False)   # other providers unaffected
        out = spend_policy.may_spend(db, "anything", department="intel")
        assert out["may_spend"] is False and out["department_capped"] is True, out
        st = spend_policy.state()
        assert st["provider_ceilings"].startswith("1 provider ceiling(s) set")
    finally:
        spend_policy.PROVIDER_CEILINGS_CAD.clear()
        spend_policy.PROVIDER_CEILINGS_CAD.update(saved_p)
        spend_policy.DEPARTMENT_ALLOCATION.clear()
        spend_policy.DEPARTMENT_ALLOCATION.update(saved_d)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:500])
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
