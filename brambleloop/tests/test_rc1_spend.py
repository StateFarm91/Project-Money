"""RC1 independent-audit spend findings B1-B5, C1 and F1, each as a permanent test.

Every test reproduces the audit's script (`spend1.py`, `spend2.py`, `sust1.py`) against the
fixed code and asserts the opposite of what the audit observed:

* B1 -- a malformed model answer the provider billed recorded 0 tokens and no cost row.
* B2 -- `images.generate` wrote no `CostEntry`; the ceiling counted only kind `llm`.
* B3 -- a render the provider accepted and then failed (link fetch, poll, empty body) was
  released as unbilled.
* B4 -- the ceiling check and the reservation were two steps; two holders both fitted.
* B5 -- a holder's own open reservations were not counted against the ceiling.
* C1 -- `sustainable_economics` passed on assumed volume and never said so.
* F1 -- `job_product` trusted `cir.slug` from job inputs; `shared` overrides were silent.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import base64
import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC", "ETSY", "BRAMBLELOOP")):
        os.environ.pop(_k)

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Agent, AuditLog, CostEntry, Listing, Product, SpendReservation)
from brambleloop.core.resilience import TransientError  # noqa: E402
from brambleloop.finance import reservations, spend_report, sustainability  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import images, prompts, routing  # noqa: E402
from brambleloop.gateway import model_gateway as mg  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="rc1-spend-")
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 50).decode()
IMAGE_KEY = "flux-2-pro"
PROVIDER = images.BY_KEY[IMAGE_KEY]
ENV = {images.PROVIDER_VAR: IMAGE_KEY, images.KEY_VAR: "k" * 20}


def _db(file: bool = True):
    url = f"sqlite:///{_TMP}/{os.urandom(4).hex()}.sqlite" if file else "sqlite://"
    db = Database(url)
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _count(db, **where) -> int:
    with db.session() as s:
        q = select(func.count()).select_from(CostEntry)
        for k, v in where.items():
            q = q.where(getattr(CostEntry, k) == v)
        return int(s.scalar(q) or 0)


def _reservation_rows(db):
    with db.session() as s:
        return [(r.amount_cad, r.actual_cad, r.released_at is not None)
                for r in s.scalars(select(SpendReservation).order_by(SpendReservation.id))]


class _PatchPost:
    """Swap `images._post` (and optionally `_get`) for the duration of a block."""

    def __init__(self, post, get=None):
        self.post, self.get = post, get

    def __enter__(self):
        self.saved = (images._post, images._get, images.BFL_POLL_SECONDS)
        images._post = self.post
        if self.get is not None:
            images._get = self.get
        images.BFL_POLL_SECONDS = 0.0
        return self

    def __exit__(self, *exc):
        images._post, images._get, images.BFL_POLL_SECONDS = self.saved
        return False


def _ok_post(*_a, **_k):
    return {"data": [{"b64_json": PNG}]}


# ---------------------------------------------------------------------------
# B1


class _Bad:
    """A provider that bills 3000 in / 1500 out and answers something that is not JSON."""
    name = "bad"
    model = "claude-haiku-4-5"
    cost_per_1k_input_cad = 0.5
    cost_per_1k_output_cad = 2.0

    def __init__(self, text="NOT JSON", in_tok=3000, out_tok=1500, exc=None):
        self.text, self.in_tok, self.out_tok, self.exc = text, in_tok, out_tok, exc

    def complete(self, system, user, *, max_tokens):
        if self.exc is not None:
            raise self.exc
        return mg.ModelResponse(text=self.text, provider="bad", model=self.model,
                                input_tokens=self.in_tok, output_tokens=self.out_tok,
                                latency_ms=1)


def _gateway(provider):
    db = _db()
    with db.session() as s:
        s.scalar(select(Agent).where(Agent.name == "cfo")).daily_cost_ceiling_cad = 50.0
    reg = Registry(db)
    ref = sorted(prompts._REGISTRY)[0]
    values = {k: "x" for k in prompts._placeholders(prompts._REGISTRY[ref].template)}
    return db, mg.ModelGateway([provider], registry=reg), ref, values


def test_b1_a_malformed_answer_the_provider_billed_is_recorded_and_counted():
    db, g, ref, values = _gateway(_Bad())
    try:
        g.complete_json(ref, agent="cfo", values=values)
        raise AssertionError("non-JSON output must not be returned")
    except mg.MalformedModelOutput:
        pass
    per_call = 3000 / 1000 * 0.5 + 1500 / 1000 * 2.0                       # CA$4.50
    assert [(c.input_tokens, c.output_tokens, c.ok) for c in g.calls] == [
        (3000, 1500, False), (3000, 1500, False)], g.calls
    assert _count(db) == 2, "both billed attempts must leave a ledger row"
    assert abs(gw.spent_this_month_cad(db) - 2 * per_call) < 1e-6
    # The reservations were released with the bill, not as unbilled.
    assert all(actual is not None and released
               for _a, actual, released in _reservation_rows(db)), _reservation_rows(db)


def test_b1_a_billed_attempt_with_no_usage_is_counted_at_the_estimate_not_zero():
    db, g, ref, values = _gateway(_Bad(in_tok=0, out_tok=0))
    try:
        g.complete_json(ref, agent="cfo", values=values, max_attempts_per_provider=1)
    except mg.MalformedModelOutput:
        pass
    with db.session() as s:
        rows = list(s.scalars(select(CostEntry)))
    assert len(rows) == 1 and rows[0].amount_cad > 0, [(r.amount_cad, r.detail) for r in rows]
    assert rows[0].detail["billing"] == "unknown_usage_counted_at_estimate"
    assert abs(rows[0].amount_cad - rows[0].estimated_cad) < 1e-6


def test_b1_a_timeout_after_sending_is_unknown_and_counted_a_refusal_is_not_billed():
    db, g, ref, values = _gateway(_Bad(exc=TimeoutError("read timed out")))
    try:
        g.complete_json(ref, agent="cfo", values=values, max_attempts_per_provider=1)
    except TimeoutError:
        pass
    with db.session() as s:
        row = s.scalar(select(CostEntry))
    assert row is not None and row.amount_cad > 0
    assert row.detail["billing"] == "unknown_counted_at_estimate"

    db2, g2, ref, values = _gateway(_Bad(exc=TransientError("anthropic 529: overloaded")))
    try:
        g2.complete_json(ref, agent="cfo", values=values, max_attempts_per_provider=1)
    except TransientError:
        pass
    assert _count(db2) == 0, "a request the provider refused outright did not bill"
    assert all(actual is None and released
               for _a, actual, released in _reservation_rows(db2))


# ---------------------------------------------------------------------------
# B2


def test_b2_every_render_writes_an_image_cost_row_and_the_ceiling_counts_it():
    db = _db()
    wd = tempfile.mkdtemp(dir=_TMP)
    with _PatchPost(_ok_post):
        got = [images.generate("x", env=ENV, db=db, work_dir=wd, provider_key=IMAGE_KEY)
               for _ in range(3)]
    assert _count(db, kind=routing.IMAGE_COST_KIND) == 3
    assert all(g["cost_entry_id"] for g in got)
    assert abs(gw.spent_this_month_cad(db) - 3 * PROVIDER.cad_per_image) < 1e-6
    assert abs(routing.spent_this_month(db) - 3 * PROVIDER.cad_per_image) < 1e-6
    month = spend_report.what_it_bought(db)
    assert month["by_provider"][IMAGE_KEY]["calls"] == 3, "the report reads what the ceiling reads"
    with db.session() as s:
        row = s.scalar(select(CostEntry).where(CostEntry.kind == routing.IMAGE_COST_KIND))
        assert row.detail["price_basis"] == "assumed" and row.detail["billing"] == "rendered"
        assert row.detail["reservation_id"] is not None


def test_b2_image_spend_closes_the_monthly_ceiling():
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="gateway", kind=routing.IMAGE_COST_KIND,
                        amount_cad=gw.monthly_ceiling_cad() - 0.01, purpose="renders"))
    try:
        gw.check_budget_cad(db, estimate_cad=0.02, purpose="t")
        raise AssertionError("a month spent on renders must refuse the next call")
    except gw.BudgetExceeded:
        pass
    # A separately governed kind is not this ceiling's money (listing fees have their own).
    db2 = _db()
    with db2.session() as s:
        s.add(CostEntry(agent="store_operator", kind="etsy_listing_fee", amount_cad=99.99))
    assert gw.spent_this_month_cad(db2) == 0.0
    # And an unknown, new kind is inside the ceiling until somebody says otherwise.
    assert routing.counts_against_monthly_ceiling("some_future_kind")


def test_b2_the_image_probe_does_not_count_a_render_twice():
    db = _db()
    calls = []

    def fake(prompt, **kw):
        calls.append(kw)
        return {"cad": PROVIDER.cad_per_image, "url": "", "cost_entry_id": 123}

    images.probe(db, env=ENV, generator=fake)
    assert _count(db) == 0, "generate already ledgered it; the probe must not add a second row"

    def fake_unledgered(prompt, **kw):
        return {"cad": PROVIDER.cad_per_image, "url": ""}

    images.probe(db, env=ENV, generator=fake_unledgered)
    assert _count(db, kind=routing.IMAGE_COST_KIND) == 1


# ---------------------------------------------------------------------------
# B3


def _link_post(*_a, **_k):
    return {"data": [{"url": "http://127.0.0.1:9/x.png"}]}


def test_b3_a_render_accepted_then_failed_is_billed_not_released_as_free():
    db = _db()
    wd = tempfile.mkdtemp(dir=_TMP)
    with _PatchPost(_link_post):
        try:
            images.generate("x", env=ENV, db=db, work_dir=wd, provider_key=IMAGE_KEY)
            raise AssertionError("an unfetchable link is no image")
        except images.ImagesRefused:
            pass
    assert _reservation_rows(db) == [(PROVIDER.cad_per_image, PROVIDER.cad_per_image, True)]
    with db.session() as s:
        row = s.scalar(select(CostEntry))
    assert row.kind == routing.IMAGE_COST_KIND and row.detail["billing"] == "accepted_then_failed"


def test_b3_poll_timeout_moderation_and_empty_body_are_billed():
    def submit(*_a, **_k):
        return {"polling_url": "https://poll.example/1"}

    cases = {
        "moderated": lambda *_a, **_k: {"status": "Content_Moderated"},
        "empty": lambda *_a, **_k: {"status": "Ready", "result": {}},
    }
    for label, get in cases.items():
        db = _db()
        with _PatchPost(submit, get):
            try:
                images.generate("x", env=ENV, db=db, work_dir=tempfile.mkdtemp(dir=_TMP),
                                provider_key=IMAGE_KEY)
                raise AssertionError(label)
            except images.ImagesRefused:
                pass
        assert _count(db, kind=routing.IMAGE_COST_KIND) == 1, label

    db = _db()
    saved = images.BFL_POLL_ATTEMPTS
    images.BFL_POLL_ATTEMPTS = 2
    try:
        with _PatchPost(submit, lambda *_a, **_k: {"status": "Pending"}):
            try:
                images.generate("x", env=ENV, db=db, work_dir=tempfile.mkdtemp(dir=_TMP),
                                provider_key=IMAGE_KEY)
                raise AssertionError("poll timeout")
            except TransientError:
                pass
    finally:
        images.BFL_POLL_ATTEMPTS = saved
    assert _count(db, kind=routing.IMAGE_COST_KIND) == 1, "a poll timeout after submit is billed"


def test_b3_a_refused_request_is_unbilled_and_a_read_timeout_is_counted():
    def refused(*_a, **_k):
        raise images.ImagesRefused("flux-2-pro 400: bad request")

    db = _db()
    with _PatchPost(refused):
        try:
            images.generate("x", env=ENV, db=db, work_dir=tempfile.mkdtemp(dir=_TMP),
                            provider_key=IMAGE_KEY)
        except images.ImagesRefused:
            pass
    assert _count(db) == 0 and _reservation_rows(db) == [(PROVIDER.cad_per_image, None, True)]

    def timed_out(*_a, **_k):
        raise TimeoutError("The read operation timed out")

    db = _db()
    with _PatchPost(timed_out):
        try:
            images.generate("x", env=ENV, db=db, work_dir=tempfile.mkdtemp(dir=_TMP),
                            provider_key=IMAGE_KEY)
        except TimeoutError:
            pass
    with db.session() as s:
        row = s.scalar(select(CostEntry))
    assert row is not None and row.detail["billing"] == "unknown_counted_at_estimate"


# ---------------------------------------------------------------------------
# B4


def _race(db, *, threads: int, estimate: float, widen: float) -> list[str]:
    """`threads` distinct holders check at once; `widen` stretches the read-to-write gap."""
    original = reservations.outstanding

    def slow(db_, **kw):
        out = original(db_, **kw)
        time.sleep(widen)
        return out

    results: list[str] = []
    start = threading.Barrier(threads)

    def worker(n):
        try:
            start.wait(timeout=10)
            gw.check_budget_cad(db, estimate_cad=estimate, agent="", purpose="race",
                                holder=f"h{n}")
            results.append("ok")
        except gw.BudgetExceeded:
            results.append("refused")

    reservations.outstanding = slow
    try:
        pool = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
        [t.start() for t in pool]
        [t.join(timeout=60) for t in pool]
    finally:
        reservations.outstanding = original
    return results


def test_b4_concurrent_holders_never_reserve_past_the_ceiling():
    # A file database, so every thread has its own connection and the database lock (not
    # only the process lock) is what serialises them. (An in-memory SQLite database is one
    # database per thread under SQLAlchemy's pool, so it cannot host a cross-thread race.)
    ceiling = gw.monthly_ceiling_cad()
    db = _db(file=True)
    results = _race(db, threads=8, estimate=30.0, widen=0.05)
    reserved = reservations.outstanding_cad(db)
    assert len(results) == 8, results
    assert reserved <= ceiling, (results, reserved)
    assert results.count("ok") == int(ceiling // 30.0), results


def test_b4_the_database_lock_holds_across_processes_not_only_threads():
    """The process lock is bypassed here: two *separate* engines on one file, as two
    containers would have, and the SQLite write lock alone must serialise them."""
    import brambleloop.gateway.anthropic as mod

    path = f"{_TMP}/{os.urandom(4).hex()}.sqlite"
    first = Database(f"sqlite:///{path}")
    first.create_all()
    Registry(first).seed_defaults()
    second = Database(f"sqlite:///{path}")
    saved = mod._PROCESS_BUDGET_LOCK

    class _NoLock:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    mod._PROCESS_BUDGET_LOCK = _NoLock()
    original = reservations.outstanding

    def slow(db_, **kw):
        out = original(db_, **kw)
        time.sleep(0.2)
        return out

    results: list[str] = []
    gate = threading.Barrier(2)

    def worker(db, n):
        try:
            gate.wait(timeout=10)
            gw.check_budget_cad(db, estimate_cad=60.0, purpose="race", holder=f"p{n}")
            results.append("ok")
        except gw.BudgetExceeded:
            results.append("refused")

    reservations.outstanding = slow
    try:
        pool = [threading.Thread(target=worker, args=(d, i))
                for i, d in enumerate((first, second))]
        [t.start() for t in pool]
        [t.join(timeout=60) for t in pool]
    finally:
        reservations.outstanding = original
        mod._PROCESS_BUDGET_LOCK = saved
    assert sorted(results) == ["ok", "refused"], results
    assert reservations.outstanding_cad(first) == 60.0


def test_b4_the_audit_two_holder_race_grants_one():
    db = _db()
    results = _race(db, threads=2, estimate=60.0, widen=0.2)
    assert sorted(results) == ["ok", "refused"], results
    assert reservations.outstanding_cad(db) == 60.0


def test_b4_a_refusal_is_still_recorded_once_the_lock_is_released():
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="gateway", kind="llm", amount_cad=99.99, purpose="x"))
    try:
        gw.check_budget_cad(db, estimate_cad=1.0, purpose="t")
    except gw.BudgetExceeded:
        pass
    assert spend_report.refusals(db)["by_ceiling"].get("monthly_ceiling") == 1


# ---------------------------------------------------------------------------
# B5


def test_b5_a_holders_own_open_reservations_count_against_the_ceiling():
    db = _db()
    granted = 0
    try:
        for _ in range(10):
            gw.check_budget_cad(db, estimate_cad=40.0, purpose="t", holder="one:1:1")
            granted += 1
    except gw.BudgetExceeded as exc:
        assert "own open reservations" in str(exc), str(exc)
    assert granted == 2, f"granted {granted} x CA$40 against CA$100"
    # Releasing gives the room back.
    with db.session() as s:
        ids = [r.id for r in s.scalars(select(SpendReservation))]
    for rid in ids:
        gw.release_reservation(db, rid)
    gw.check_budget_cad(db, estimate_cad=40.0, purpose="t", holder="one:1:1")


# ---------------------------------------------------------------------------
# C1


def _sust1(db, now):
    with db.session() as s:
        s.add(Listing(product_slug="p1", version="1.0.0", title="t", description="",
                      price_cad=8.0, state="draft", created_at=now - timedelta(days=20)))
        for i in range(25):
            s.add(CostEntry(at=now - timedelta(days=20 - i * 0.7), agent="a", kind="llm",
                            amount_cad=0.02, product_slug="p1" if i % 5 == 0 else "",
                            detail={"price_basis": "assumed"}))


def test_c1_the_verdict_states_its_basis_and_labels_volume_assumed():
    now = datetime.now(timezone.utc)
    db = _db()
    _sust1(db, now)
    v = sustainability.verdict(db, now=now)
    assert v["basis"] == "MODELLED" and v["criterion"].startswith("MODELLED")
    assert v["assumptions"]["volume_basis"] == "ASSUMED" and v["assumptions"]["may_only_block"]
    assert v["measured_orders"] == 0
    for sc in v["forecast"]["scenarios"].values():
        assert sc["basis"] == "MODELLED" and sc["volume_basis"] == "ASSUMED"
    assert v["checks"]["cost_coverage_complete"] and v["checks"]["unit_margin_positive"]
    assert v["sustainable"] is True and v["why"].startswith("MODELLED")
    be = sustainability.break_even(db)["products"]["p1"]
    assert be["reading"] == "computed_floor" and be["break_even_sales_is_floor"] is True


def test_c1_assumed_volume_cannot_grant_a_pass():
    now = datetime.now(timezone.utc)
    db = _db()
    _sust1(db, now)
    # A billed render the ledger never saw (the pre-B2 shape): cost coverage is incomplete.
    with db.session() as s:
        s.add(SpendReservation(at=now, holder="h", agent="gateway", purpose="image.generate",
                               model=IMAGE_KEY, amount_cad=0.0274, actual_cad=0.0274,
                               expires_at=now + timedelta(minutes=5), released_at=now,
                               detail={"provider": IMAGE_KEY}))
    saved = {k: dict(v) for k, v in sustainability.SCENARIOS.items()}
    try:
        for sc in sustainability.SCENARIOS.values():
            sc["sales_per_month"] = 1_000_000                  # any volume at all
        v = sustainability.verdict(db, now=now)
    finally:
        sustainability.SCENARIOS.clear()
        sustainability.SCENARIOS.update(saved)
    assert v["sustainable"] is False, v["why"]
    assert any("billed image render" in p for p in v["problems"]), v["problems"]


def test_c1_a_product_with_unknown_creation_cost_or_no_unit_margin_blocks():
    now = datetime.now(timezone.utc)
    db = _db()
    _sust1(db, now)
    with db.session() as s:
        s.add(Listing(product_slug="untagged", version="1.0.0", title="u", description="",
                      price_cad=8.0, state="draft", created_at=now))
    v = sustainability.verdict(db, now=now)
    assert v["sustainable"] is False and v["coverage"]["unknown_creation_cost_products"] == [
        "untagged"]

    db = _db()
    _sust1(db, now)
    with db.session() as s:
        s.scalar(select(Listing)).price_cad = 0.25        # fees eat the whole price
    v = sustainability.verdict(db, now=now)
    assert v["sustainable"] is False and not v["checks"]["unit_margin_positive"], v["problems"]


def test_c1_the_readiness_requirement_carries_the_basis():
    from brambleloop.launch.readiness import assess

    now = datetime.now(timezone.utc)
    db = _db()
    _sust1(db, now)
    by = {r.key: r for r in assess(db, phase="shadow").requirements}
    ev = by["sustainable_economics"].evidence
    assert ev["basis"] == "MODELLED" and ev["criterion"]
    assert all(s["volume_basis"] == "ASSUMED" for s in ev["scenarios"].values())
    assert ev["break_even"]["p1"]["break_even_sales_is_floor"] is True


# ---------------------------------------------------------------------------
# F1


def test_f1_a_cir_slug_in_job_inputs_is_checked_against_the_catalogue():
    db = _db()
    job = SimpleNamespace(inputs={"cir": {"slug": "ghost"}})
    assert spend_report.job_product(db, job) == "", "job inputs are data, not evidence"
    with db.session() as s:
        s.add(Product(slug="ghost", title="Ghost"))
    assert spend_report.job_product(db, job) == "ghost"


def test_f1_a_shared_override_inside_a_product_job_is_labelled_and_audited():
    db = _db()
    with spend_report.attributed_to("p1"):
        spend_report.record(db, agent="gateway", amount_cad=0.01, purpose="probe",
                            detail={"attribution": "shared"})
    with db.session() as s:
        row = s.scalar(select(CostEntry))
        audits = list(s.scalars(select(AuditLog).where(
            AuditLog.action == spend_report.SHARED_OVERRIDE_ACTION)))
    assert row.product_slug == "" and row.detail["shared_override_of"] == "p1"
    assert len(audits) == 1 and audits[0].artifact == "p1"


if __name__ == "__main__":
    fails = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_"):
                try:
                    fn()
                    print("OK  ", name)
                except Exception as e:  # noqa: BLE001
                    fails += 1
                    import traceback
                    traceback.print_exc()
                    print("FAIL", name, repr(e))
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    print(f"{fails} failing")
    sys.exit(1 if fails else 0)
