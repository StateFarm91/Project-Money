"""P0-PAID-PROVIDER-OWNER-GATE (W5-V0): a provider key never authorises a paid image or vision
call. Owner directive 2026-11-02, after production (0967c3ee) rendered on api.bfl.ai from the
capability-probe cadence with a key set and no owner activation.

Every test runs on a real SQLite FILE. A fake transport replaces the only functions that do
network I/O for paid calls (`images._post`/`_get`, `AnthropicProvider._send`,
`urllib.request.urlopen` for `visual.d_judge`) and records every attempted call; a refusal is
asserted to have made ZERO of them. Jobs run through the real Worker with registered handlers.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w5_v0_paid_provider_gate.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import base64
import io
import json
import os
import secrets
import socket
import sys
import tempfile
import time
import traceback
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="w5_v0_gate_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'app.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.pop("BRAMBLELOOP_MODEL_MONTHLY_CEILING_CAD", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "OPENAI", "BRAMBLELOOP_IMAGE_KEY",
                      "BRAMBLELOOP_IMAGE_PROVIDER", "BRAMBLELOOP_RESEARCH_JUDGE")):
        os.environ.pop(_k)
for _k in ("BRAMBLELOOP_TRUSTED_PROXY_HOPS", "BRAMBLELOOP_CLIENT_IP_HEADER",
           "BRAMBLELOOP_PUBLIC_ORIGIN"):
    os.environ.pop(_k, None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W5-V0 harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app.command_center import auth as cc_auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, Phase  # noqa: E402
from brambleloop.gateway import anthropic as gw  # noqa: E402
from brambleloop.gateway import images  # noqa: E402
from brambleloop.gateway import paid_provider_gate as G  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

FLUX = "flux-3-image"
KEY_VALUE = "test-not-a-secret-" + secrets.token_hex(6)
ENV = {"BRAMBLELOOP_IMAGE_KEY_BFL": KEY_VALUE, "BRAMBLELOOP_IMAGE_PROVIDER": FLUX}
FLUX_CAD = images.BY_KEY[FLUX].cad_per_image          # the 1k-tier reservation
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)   # mid-month, for the unit checks


def _png_b64() -> str:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (8, 8), (120, 120, 120)).save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode()


PNG = _png_b64()


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='v0-db-', dir=_TMP)}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _session(db, *, stepup: bool = True, revoked: bool = False, at: datetime | None = None,
             stepup_expired: bool = False) -> str:
    cc_auth.ensure_tables(db)
    now = at or datetime.now(timezone.utc)
    pid = "s_" + secrets.token_hex(8)
    until = (now - timedelta(minutes=1) if stepup_expired else
             now + timedelta(minutes=5) if stepup else None)
    with db.session() as s:
        s.add(OwnerSession(public_id=pid, token_hash=secrets.token_hex(32),
                           created_at=now, last_seen_at=now,
                           expires_at=now + timedelta(days=1), stepup_until=until,
                           revoked_at=now if revoked else None))
    return pid


def _activate(db, provider=FLUX, scope=G.GENERATION, *, at: datetime | None = None, **kw):
    ceilings = dict(daily_ceiling_cad=5.0, monthly_ceiling_cad=20.0, per_gallery_cad=5.0)
    ceilings.update(kw)
    return G.activate(db, provider=provider, scope=scope, by="owner:test",
                      session_public_id=_session(db, at=at), now=at, **ceilings)


def _revoke(db, provider=FLUX, scope=G.GENERATION, *, at=None):
    return G.revoke(db, provider=provider, scope=scope, by="owner:test",
                    session_public_id=_session(db, at=at), reason="test", now=at)


class Wire:
    """The fake transport: every attempted paid network call is recorded, none leaves."""

    def __init__(self, vision_answer: str = "photograph"):
        self.calls: list[tuple] = []
        self.answer = vision_answer

    def __enter__(self):
        self._saved = (images._post, images._get, gw.AnthropicProvider._send,
                       urllib.request.urlopen)
        wire = self

        def post(url, headers, payload, *, label, timeout):
            wire.calls.append(("image.POST", label, url))
            return {"data": [{"b64_json": PNG}]}

        def get(url, headers, *, label, timeout):
            wire.calls.append(("image.GET", label, url))
            raise AssertionError("no poll expected")

        def send(provider, payload, key, *, timeout=None):
            wire.calls.append(("anthropic", provider.model))
            return provider._read({"content": [{"type": "text", "text": wire.answer}],
                                   "usage": {"input_tokens": 120, "output_tokens": 2}},
                                  time.time())

        def urlopen(req, *a, **k):
            wire.calls.append(("urlopen", getattr(req, "full_url", str(req))))
            raise AssertionError("the d_judge request must never reach here in a refusal")

        images._post, images._get = post, get
        gw.AnthropicProvider._send = send
        urllib.request.urlopen = urlopen
        return self

    def __exit__(self, *exc):
        (images._post, images._get, gw.AnthropicProvider._send,
         urllib.request.urlopen) = self._saved
        return False


@contextmanager
def _env(**values):
    saved = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _render(db, prompt="A plain grey swatch, product photograph.", **kw):
    with tempfile.TemporaryDirectory(dir=_TMP) as wd:
        return images.generate(prompt, env=ENV, provider_key=FLUX, work_dir=wd, db=db,
                               purpose="test.render", **kw)


def _refused(fn, *, code: str, exc=G.PaidCallRefused):
    try:
        fn()
    except exc as e:
        got = getattr(e, "code", "")
        assert got == code, f"refused with {got!r} ({e}), expected {code!r}"
        return e
    raise AssertionError(f"expected a refusal {code!r}; the call was allowed")


def _calls_rows(db):
    G.ensure_tables(db)
    with db.session() as s:
        return [(r.provider, r.status, r.idem_key) for r in s.scalars(
            select(G.PaidProviderCall).order_by(G.PaidProviderCall.id))]


def _stub_other_probes():
    from brambleloop.culture import feeds
    from brambleloop.growth import owned_surface
    from brambleloop.intel import browser

    saved = (browser.probe, feeds.probe, owned_surface.probe)
    stub = (lambda db, **kw: {"ok": False, "reason": "stubbed in W5-V0"})
    browser.probe = feeds.probe = owned_surface.probe = stub

    def restore():
        browser.probe, feeds.probe, owned_surface.probe = saved
    return restore


def _run_capability_probes(db, key: str):
    JobQueue(db).enqueue("orchestrator", "ops.capability_probes", {}, priority=0,
                         idempotency_key=key)
    Worker(db, "w-v0", phase=Phase.SHADOW, job_types=["ops.capability_probes"]).run_once()
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.idempotency_key == key))
        return job.status, job.last_error


# ---- 1. a key is not an activation ----------------------------------------------------------

def test_key_without_activation_the_capability_probe_makes_no_call_and_the_gate_stays_shut():
    db = _db()
    restore = _stub_other_probes()
    try:
        with _env(**ENV), Wire() as wire:
            status, err = _run_capability_probes(db, "probe-1")
        assert status == JobStatus.DONE, err
        assert wire.calls == [], wire.calls                  # ZERO network calls
    finally:
        restore()
    last = images.last_probe(db)
    assert last["ok"] is False and last["state"] == G.NOT_ACTIVATED, last
    assert "not activated" in last["reason"] or G.NOT_ACTIVATED in last["reason"]
    assert last["provider"] == FLUX
    assert images.usable(db) is False
    from brambleloop.build2 import executor

    assert executor._rendered_pages_usable(db, ENV) is False
    # Nothing was reserved or billed for it.
    assert _calls_rows(db) == []


def test_key_without_activation_a_render_and_a_paid_production_generator_are_refused():
    db = _db()
    with Wire() as wire:
        e = _refused(lambda: _render(db), code=G.NOT_ACTIVATED, exc=images.ImagesGateRefused)
        assert "not activated" in str(e) and wire.calls == []
        # submit_render (the deferred path) meets the same gate.
        with tempfile.TemporaryDirectory(dir=_TMP):
            _refused(lambda: images.submit_render("x", provider_key=FLUX, env=ENV, db=db,
                                                  purpose="test.render"),
                     code=G.NOT_ACTIVATED, exc=images.ImagesGateRefused)
        assert wire.calls == []
    assert G.generation_gate_reason(db).startswith(G.NOT_ACTIVATED)
    # The image-production orchestrator refuses a paid generator, naming the reason.
    blocked = _production_with_paid_generator(db)
    assert "image_generation gate closed" in blocked and G.NOT_ACTIVATED in blocked, blocked


def test_a_historical_successful_probe_row_alone_never_opens_either_gate():
    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=images.PROBE_ACTION, artifact=FLUX,
                       detail={"ok": True, "provider": FLUX,
                               "at": datetime.now(timezone.utc).isoformat()}))
        s.add(AuditLog(actor="orchestrator", action=gw.VISION_PROBE_ACTION,
                       detail={"ok": True, "at": datetime.now(timezone.utc).isoformat()}))
    assert images.usable(db) is False and gw.vision_usable(db) is False
    # Activation alone (no probe made under it) does not open it either.
    _activate(db)
    _activate(db, G.ANTHROPIC_VISION, G.VISION)
    assert images.usable(db) is False and gw.vision_usable(db) is False


def test_a_probe_only_activation_proves_the_provider_but_does_not_open_generation():
    db = _db()
    _activate(db, scope=G.PROBE, daily_ceiling_cad=1.0, monthly_ceiling_cad=1.0,
              per_gallery_cad=1.0)
    with Wire() as wire:
        rec = images.probe(db, env=ENV)
        assert rec["ok"] is True and len(wire.calls) == 1, rec
        # ...but ordinary generation is a different scope and is refused, nothing sent.
        _refused(lambda: _render(db, "a different prompt"), code=G.NOT_ACTIVATED,
                 exc=images.ImagesGateRefused)
        assert len(wire.calls) == 1
    assert images.usable(db) is False
    _activate(db)                                            # generation activated too
    assert images.usable(db) is True


# ---- 2. with activation: once, within ceilings, never re-billed --------------------------

def test_activation_allows_the_probe_once_and_an_identical_request_is_not_rebilled():
    db = _db()
    act = _activate(db, daily_ceiling_cad=1.0, monthly_ceiling_cad=5.0, per_gallery_cad=1.0)
    restore = _stub_other_probes()
    try:
        with _env(**ENV), Wire() as wire:
            status, err = _run_capability_probes(db, "probe-a")
            assert status == JobStatus.DONE, err
            assert [c[0] for c in wire.calls] == ["image.POST"], wire.calls
            last = images.last_probe(db)
            assert last["ok"] is True and last["activation_id"] == act["id"], last
            assert images.usable(db) is True
            # The next cadence reuses the success: nothing sent, nothing billed.
            status, err = _run_capability_probes(db, "probe-b")
            assert status == JobStatus.DONE, err
            assert len(wire.calls) == 1
            # Outside a job, the identical probe request is made once a day, then refused.
            first = images.probe(db, env=ENV)
            assert first["ok"] is True and len(wire.calls) == 2
            again = images.probe(db, env=ENV)
            assert again["ok"] is False and again["state"] == "already_billed", again
            assert len(wire.calls) == 2                       # not sent, not re-billed
    finally:
        restore()
    rows = _calls_rows(db)
    assert [r[1] for r in rows] == [G.BILLED, G.BILLED], rows
    # Revocation closes the gate, and the cadence stops reusing the old success: the next
    # probe runs, finds no activation, and sends nothing.
    _revoke(db)
    assert images.usable(db) is False
    with Wire() as wire:
        out = images.probe_if_due(db, env=ENV)
        assert not out.get("reused") and out["state"] == G.REVOKED, out
        assert wire.calls == []


def test_a_success_is_not_reused_once_its_activation_is_revoked():
    db = _db()
    _activate(db)
    with Wire() as wire:
        assert images.probe(db, env=ENV)["ok"] is True and len(wire.calls) == 1
        assert images.probe_if_due(db, env=ENV)["reused"] is True and len(wire.calls) == 1
        _revoke(db)
        out = images.probe_if_due(db, env=ENV)
        assert not out.get("reused") and out["state"] == G.REVOKED, out
        assert len(wire.calls) == 1
    assert images.usable(db) is False


def test_reservation_cannot_underfund_or_back_two_paid_attempts():
    db = _db()
    _activate(db, at=NOW, daily_ceiling_cad=2, monthly_ceiling_cad=5, per_gallery_cad=2)
    tiny = _reserve(db, estimate=0.001)
    _refused(lambda: _authorize(db, "underfunded", estimate=0.4, reservation=tiny),
             code="reservation_underfunded")
    assert not _calls_rows(db)
    enough = _reserve(db, estimate=0.4)
    ticket = _authorize(db, "first-attempt", estimate=0.4, reservation=enough)
    _refused(lambda: _authorize(db, "other-attempt", estimate=0.4, reservation=enough),
             code="reservation_already_used")
    G.settle(db, ticket, G.RELEASED)
    _refused(lambda: _authorize(db, "retry", estimate=0.4, reservation=enough),
             code="reservation_already_used")
    assert len(_calls_rows(db)) == 1


def test_concurrent_calls_cannot_share_one_company_reservation():
    import threading

    db = _db()
    _activate(db, at=NOW, daily_ceiling_cad=2, monthly_ceiling_cad=5, per_gallery_cad=2)
    held = _reserve(db, estimate=0.4)
    ready = threading.Barrier(2)
    results = []
    def attempt(fp):
        ready.wait()
        try:
            results.append(("allowed", _authorize(db, fp, estimate=0.4, reservation=held)))
        except G.PaidCallRefused as exc:
            results.append(("refused", exc.code))
    threads = [threading.Thread(target=attempt, args=(f"race-{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(v[0] for v in results) == ["allowed", "refused"], results
    assert next(v[1] for v in results if v[0] == "refused") == "reservation_already_used"
    assert len(_calls_rows(db)) == 1


def test_invalid_or_missing_usage_never_credits_provider_budget():
    for usage in (None, 0, -1, float("nan"), float("inf")):
        db = _db()
        _activate(db, at=NOW, daily_ceiling_cad=0.5, monthly_ceiling_cad=5, per_gallery_cad=2)
        ticket = _authorize(db, f"usage-{usage}", estimate=0.4)
        G.settle(db, ticket, G.BILLED, actual_cad=usage)
        _refused(lambda: _authorize(db, "next", estimate=0.4),
                 code="provider_daily_ceiling")
        with db.session() as session:
            row = session.get(G.PaidProviderCall, ticket["call_id"])
            if usage is None or usage == 0:
                assert row.status == G.BILLED and row.actual_cad == 0.4
            else:
                assert row.status == G.UNCERTAIN


def test_legacy_invalid_usage_never_credits_provider_budget():
    db = _db()
    _activate(db, at=NOW, daily_ceiling_cad=0.5, monthly_ceiling_cad=5, per_gallery_cad=2)
    ticket = _authorize(db, "legacy-invalid", estimate=0.4)
    with db.session() as session:
        row = session.get(G.PaidProviderCall, ticket["call_id"])
        row.status = G.BILLED
        row.actual_cad = -1
    _refused(lambda: _authorize(db, "next-legacy", estimate=0.4),
             code="provider_daily_ceiling")


def test_retention_never_reuses_paid_reservation_identity():
    from brambleloop.finance import reservations
    from brambleloop.core.models import SpendReservation

    db = _db()
    _activate(db, at=NOW, daily_ceiling_cad=2, monthly_ceiling_cad=5, per_gallery_cad=2)
    held = _reserve(db, estimate=0.4)
    ticket = _authorize(db, "first-id", estimate=0.4, reservation=held)
    G.settle(db, ticket, G.RELEASED)
    reservations.release(db, held["reservation_id"], now=NOW)
    reservations.sweep(db, now=NOW + timedelta(days=3))
    with db.session() as session:
        assert session.get(SpendReservation, held["reservation_id"]) is not None
    fresh = _reserve(db, estimate=0.4)
    assert fresh["reservation_id"] != held["reservation_id"]
    assert _authorize(db, "new-id", estimate=0.4, reservation=fresh)


def test_probe_scope_cannot_authorize_arbitrary_generation_or_vision():
    db = _db()
    _activate(db, scope=G.PROBE)
    _activate(db, provider=G.ANTHROPIC_VISION, scope=G.PROBE)
    with _env(**ENV, ANTHROPIC_API_KEY=KEY_VALUE), Wire() as wire:
        _refused(lambda: _render(db, "Commercial hero photo", gate_scope=G.PROBE),
                 code="probe_scope_mismatch", exc=images.ImagesGateRefused)
        provider = gw.AnthropicProvider()
        with G.call_scope(G.PROBE):
            _refused(lambda: provider.see("", "Describe the commercial product", ["https://example.test/a"],
                                          max_tokens=gw.VISION_PROBE_MAX_TOKENS),
                     code="probe_scope_mismatch", exc=gw.VisionGateRefused)
        assert wire.calls == [], wire.calls


def test_uncovered_company_exposure_survives_release_and_restart():
    from brambleloop.finance import reservations
    from brambleloop.core.db import Database

    db = _db()
    _activate(db, at=NOW, daily_ceiling_cad=2, monthly_ceiling_cad=5, per_gallery_cad=2)
    held = _reserve(db, estimate=0.4)
    _authorize(db, "orphan", estimate=0.4, reservation=held)
    reservations.release(db, held["reservation_id"], now=NOW)
    reopened = Database(str(db.engine.url))
    with reopened.session() as session:
        assert G.uncovered_company_exposure(session, now=NOW) == 0.4
    saved = gw.monthly_ceiling_cad
    try:
        gw.monthly_ceiling_cad = lambda: 0.5
        try:
            _reserve(reopened, estimate=0.2)
            raise AssertionError("orphaned paid attempt freed the company ceiling")
        except gw.BudgetExceeded:
            pass
    finally:
        gw.monthly_ceiling_cad = saved


def test_uncovered_company_exposure_survives_expiry_and_rejects_bad_history():
    db = _db()
    _activate(db, at=NOW, daily_ceiling_cad=2, monthly_ceiling_cad=5, per_gallery_cad=2)
    held = _reserve(db, estimate=0.4)
    ticket = _authorize(db, "expired-orphan", estimate=0.4, reservation=held)
    with db.session() as session:
        assert G.uncovered_company_exposure(session, now=NOW) == 0.0
        assert G.uncovered_company_exposure(session, now=NOW + timedelta(hours=1)) == 0.4
        row = session.get(G.PaidProviderCall, ticket["call_id"])
        row.estimate_cad = -1
    with db.session() as session:
        try:
            G.uncovered_company_exposure(session, now=NOW + timedelta(hours=1))
            raise AssertionError("invalid historical estimate freed the company ceiling")
        except ValueError:
            pass


def test_probe_only_vision_cannot_switch_to_a_more_expensive_model():
    db = _db()
    _activate(db, provider=G.ANTHROPIC_VISION, scope=G.PROBE)
    with _env(ANTHROPIC_API_KEY=KEY_VALUE), Wire() as wire:
        provider = gw.AnthropicProvider(model="claude-opus-5")
        with G.call_scope(G.PROBE):
            _refused(lambda: provider.see("", gw.VISION_PROBE_PROMPT, ["https://example.invalid/x"],
                                          max_tokens=gw.VISION_PROBE_MAX_TOKENS),
                     code="probe_scope_mismatch", exc=gw.VisionGateRefused)
        assert wire.calls == []


def test_concurrent_release_does_not_free_company_headroom():
    from brambleloop.finance import reservations
    import threading

    db = _db()
    _activate(db, at=NOW, daily_ceiling_cad=2, monthly_ceiling_cad=5, per_gallery_cad=2)
    held = _reserve(db, estimate=0.4)
    _authorize(db, "release-race", estimate=0.4, reservation=held)
    ready = threading.Barrier(2)
    result = []
    saved = gw.monthly_ceiling_cad
    def release():
        ready.wait()
        reservations.release(db, held["reservation_id"], now=NOW)
    def reserve():
        ready.wait()
        try:
            _reserve(db, estimate=0.2)
            result.append("allowed")
        except gw.BudgetExceeded:
            result.append("refused")
    try:
        gw.monthly_ceiling_cad = lambda: 0.5
        threads = [threading.Thread(target=release), threading.Thread(target=reserve)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=15)
        assert all(not thread.is_alive() for thread in threads)
        assert result == ["refused"], result
    finally:
        gw.monthly_ceiling_cad = saved


def test_legacy_attempts_cannot_share_cover_or_use_a_future_reservation():
    db = _db()
    _activate(db, at=NOW, daily_ceiling_cad=2, monthly_ceiling_cad=5, per_gallery_cad=2)
    held = _reserve(db, estimate=0.4)
    ticket = _authorize(db, "legacy-first", estimate=0.4, reservation=held)
    with db.session() as session:
        first = session.get(G.PaidProviderCall, ticket["call_id"])
        session.add(G.PaidProviderCall(activation_id=first.activation_id, provider=first.provider,
            scope=first.scope, gallery=first.gallery, run_key=first.run_key, idem_key="legacy-second",
            fingerprint="legacy-second", purpose=first.purpose, estimate_cad=0.4,
            status=G.RESERVED, reservation_id=first.reservation_id, at=first.at))
    with db.session() as session:
        assert G.uncovered_company_exposure(session, now=NOW) == 0.4
        # A reservation whose ID was later reused cannot cover an earlier attempt.
        from brambleloop.core.models import SpendReservation
        session.get(SpendReservation, held["reservation_id"]).at = NOW + timedelta(seconds=1)
    with db.session() as session:
        assert G.uncovered_company_exposure(session, now=NOW + timedelta(seconds=2)) == 0.8


def test_uncovered_attempt_stays_counted_when_it_settles_after_month_boundary():
    from brambleloop.finance import reservations
    db = _db()
    _activate(db, at=NOW, daily_ceiling_cad=2, monthly_ceiling_cad=5, per_gallery_cad=2)
    held = _reserve(db, estimate=0.4)
    ticket = _authorize(db, "month-boundary", estimate=0.4, reservation=held)
    reservations.release(db, held["reservation_id"], now=NOW)
    next_month = datetime(2026, 12, 1, 0, 1, tzinfo=timezone.utc)
    with db.session() as session:
        row = session.get(G.PaidProviderCall, ticket["call_id"])
        row.status = G.BILLED
        row.actual_cad = 0.4
        row.settled_at = next_month
    with db.session() as session:
        assert G.uncovered_company_exposure(session, now=next_month) == 0.4


def test_probe_only_vision_rejects_an_unobserved_image_source():
    from brambleloop.core.models import BenchmarkListing
    db = _db()
    with db.session() as session:
        session.add(BenchmarkListing(benchmark_key="fixture", listing_ref="known-image",
            audit_state="audited", detail={"image_urls": ["https://example.invalid/known"]}))
    _activate(db, provider=G.ANTHROPIC_VISION, scope=G.PROBE)
    with _env(ANTHROPIC_API_KEY=KEY_VALUE), Wire() as wire:
        provider = gw.AnthropicProvider(model=gw.VISION_PROBE_MODEL)
        gw.check_budget_cad(db, estimate_cad=0.1, agent="gateway", purpose="test.vision")
        with G.call_scope(G.PROBE):
            _refused(lambda: provider.see("", gw.VISION_PROBE_PROMPT, ["https://example.invalid/unobserved"],
                                          max_tokens=gw.VISION_PROBE_MAX_TOKENS),
                     code="probe_scope_mismatch", exc=gw.VisionGateRefused)
        assert wire.calls == []
        result = gw.vision_probe(db, image_url="https://example.invalid/known")
        assert result["ok"] is True, result
        assert len(wire.calls) == 1


def test_probe_only_reference_step_cannot_use_an_arbitrary_image():
    db = _db()
    _activate(db, scope=G.PROBE)
    with _env(**ENV), Wire() as wire, tempfile.TemporaryDirectory(dir=_TMP) as wd:
        other = Path(wd) / "other.png"
        other.write_bytes(base64.b64decode(PNG))
        _refused(lambda: images.generate(
            "The same mug as the reference image, now on a wooden table.",
            env=ENV, provider_key=FLUX, work_dir=wd, db=db,
            purpose="image.reference_probe", reference_urls=[str(other)], gate_scope=G.PROBE),
            code="probe_scope_mismatch", exc=images.ImagesGateRefused)
        result = images.reference_probe(db, FLUX, env=ENV, work_dir=wd)
        assert result["ok"] is False and "generation activation" in result["why"], result
        assert wire.calls == [], wire.calls


# ---- 3. every limit refuses independently ---------------------------------------------------

def _reserve(db, estimate=FLUX_CAD, provider=FLUX, now=NOW):
    return gw.check_budget_cad(db, estimate_cad=estimate, agent="gateway",
                               purpose="test.render", provider=provider, model=provider,
                               now=now)


def _authorize(db, fp, *, estimate=FLUX_CAD, gallery="g1", now=NOW, provider=FLUX,
               scope=G.GENERATION, reservation=None):
    res = reservation if reservation is not None else _reserve(db, estimate, provider, now)
    return G.authorize(db, provider=provider, scope=scope, estimate_cad=estimate,
                       fingerprint=fp, reservation_id=res["reservation_id"],
                       purpose="test.render", gallery=gallery, now=now)


def _billed(db, fp, **kw):
    t = _authorize(db, fp, **kw)
    G.settle(db, t, G.BILLED)
    return t


def test_provider_daily_ceiling_refuses():
    db = _db()
    _activate(db, at=NOW, daily_ceiling_cad=0.10, monthly_ceiling_cad=5.0, per_gallery_cad=5.0)
    _billed(db, "a", estimate=0.06)
    _refused(lambda: _authorize(db, "b", estimate=0.06, gallery="g2"),
             code="provider_daily_ceiling")
    # The next UTC day has room again (same month, same activation).
    _billed(db, "c", estimate=0.06, now=NOW + timedelta(days=1), gallery="g3")


def test_provider_monthly_ceiling_refuses():
    db = _db()
    _activate(db, at=NOW - timedelta(days=3), daily_ceiling_cad=0.10,
              monthly_ceiling_cad=0.15, per_gallery_cad=5.0)
    _billed(db, "a", estimate=0.09, now=NOW - timedelta(days=2), gallery="g1")
    _refused(lambda: _authorize(db, "b", estimate=0.07, gallery="g2"),
             code="provider_monthly_ceiling")
    _billed(db, "c", estimate=0.05, gallery="g3")            # fits: 0.14 <= 0.15


def test_per_gallery_limit_refuses_only_that_gallery():
    db = _db()
    _activate(db, at=NOW, per_gallery_cad=0.10)
    _billed(db, "a", estimate=0.06, gallery="run-1")
    _refused(lambda: _authorize(db, "b", estimate=0.06, gallery="run-1"),
             code="per_gallery_limit")
    _billed(db, "c", estimate=0.06, gallery="run-2")


def test_company_monthly_budget_refuses():
    """The company month (`anthropic.monthly_ceiling_cad`, reused) is read again at the gate:
    a call holding a live reservation is refused once billed spend plus every live reservation
    is past the ceiling. The ledger row is stamped with the wall clock, so this reads now."""
    from brambleloop.finance import spend_report

    db = _db()
    now = datetime.now(timezone.utc)
    _activate(db, at=now)
    held = _reserve(db, 0.07, now=now)                       # a live reservation first
    _billed(db, "before", estimate=0.07, now=now, gallery="g0")
    spend_report.record(db, agent="gateway", amount_cad=gw.monthly_ceiling_cad(),
                        estimated_cad=gw.monthly_ceiling_cad(), purpose="test.other",
                        provider="anthropic", model="m", department="gateway", kind="llm")
    _refused(lambda: _authorize(db, "a", estimate=0.07, reservation=held, now=now),
             code="company_monthly_budget")


def test_identical_billed_request_is_never_bought_twice_and_uncertain_counts_as_billed():
    db = _db()
    _activate(db, at=NOW)
    _billed(db, "same")
    _refused(lambda: _authorize(db, "same"), code="already_billed")
    t = _authorize(db, "unknown-outcome")
    G.settle(db, t, G.UNCERTAIN)
    _refused(lambda: _authorize(db, "unknown-outcome"), code="already_billed")
    _billed(db, "different")                                 # a different request is fine


def test_retry_ceiling_refuses_the_third_attempt_of_one_request():
    db = _db()
    _activate(db, at=NOW, max_attempts_per_request=2)
    for _ in range(2):
        t = _authorize(db, "flaky")
        G.settle(db, t, G.RELEASED)                          # declined, never billed
    _refused(lambda: _authorize(db, "flaky"), code="retry_ceiling")
    _billed(db, "other")


def test_run_call_ceiling_refuses_past_the_activation_limit():
    db = _db()
    _activate(db, at=NOW, max_calls_per_run=2)
    _billed(db, "one", estimate=0.01)
    _billed(db, "two", estimate=0.01)
    _refused(lambda: _authorize(db, "three", estimate=0.01), code="run_call_ceiling")


def test_a_call_with_no_live_budget_reservation_is_refused():
    db = _db()
    _activate(db, at=NOW)
    _refused(lambda: G.authorize(db, provider=FLUX, scope=G.GENERATION, estimate_cad=0.07,
                                 fingerprint="x", reservation_id=None, now=NOW),
             code="no_budget_reservation")
    held = _reserve(db, 0.07)
    gw.release_reservation(db, held["reservation_id"], actual_cad=None, now=NOW)
    _refused(lambda: _authorize(db, "x", estimate=0.07, reservation=held),
             code="no_budget_reservation")
    # An expired (abandoned) reservation is no evidence either.
    stale = _reserve(db, 0.07)
    _refused(lambda: _authorize(db, "y", estimate=0.07, reservation=stale,
                                now=NOW + timedelta(hours=2)),
             code="no_budget_reservation")


def test_an_activation_row_without_step_up_evidence_authorises_nothing():
    """A row written around `activate` (no verified step-up stored) is not an activation."""
    db = _db()
    G.ensure_tables(db)
    with db.session() as s:
        s.add(G.PaidProviderActivation(
            provider=FLUX, scope=G.GENERATION, activated_by="not-the-owner", step_up={},
            daily_ceiling_cad=5.0, monthly_ceiling_cad=5.0, per_gallery_cad=5.0,
            expires_at=NOW + timedelta(days=5)))
    assert G.activation_state(db, FLUX, G.GENERATION, now=NOW)["active"] is False
    _refused(lambda: _authorize(db, "x"), code=G.NOT_ACTIVATED)


# ---- 4. expiry, revocation, and revocation between reserve and call ------------------------

def test_expired_and_revoked_activations_refuse():
    db = _db()
    _activate(db, at=NOW, expires_at=NOW + timedelta(hours=1))
    _billed(db, "a")
    _refused(lambda: _authorize(db, "b", now=NOW + timedelta(hours=2)),
             code=G.EXPIRED)
    db2 = _db()
    _activate(db2, at=NOW)
    _billed(db2, "a")
    _revoke(db2, at=NOW)
    _refused(lambda: _authorize(db2, "b"), code=G.REVOKED)
    assert G.activation_state(db2, FLUX, G.GENERATION, now=NOW)["active"] is False


def test_revocation_between_the_reservation_and_the_call_refuses_with_nothing_sent():
    db = _db()
    _activate(db)
    real = G.authorize

    def authorize_then_owner_revokes(*a, **k):
        ticket = real(*a, **k)
        _revoke(db)
        return ticket

    G.authorize = authorize_then_owner_revokes
    try:
        with Wire() as wire:
            _refused(lambda: _render(db), code=G.REVOKED, exc=images.ImagesGateRefused)
            assert wire.calls == []
    finally:
        G.authorize = real
    assert [r[1] for r in _calls_rows(db)] == [G.RELEASED]
    # And the direct form: a ticket confirmed after revocation is refused and released.
    db2 = _db()
    _activate(db2)
    t = _authorize(db2, "z", now=datetime.now(timezone.utc))
    _revoke(db2)
    _refused(lambda: G.confirm(db2, t), code=G.REVOKED)


def test_a_render_under_activation_is_sent_once_and_settled_billed():
    db = _db()
    _activate(db)
    with Wire() as wire:
        out = _render(db)
        assert out["provider"] == FLUX and len(wire.calls) == 1
    rows = _calls_rows(db)
    assert len(rows) == 1 and rows[0][1] == G.BILLED


# ---- 5. fail closed on missing or unreadable accounting evidence ---------------------------

class _Unreadable:
    """A database whose every read fails, as an unreachable or corrupted store does."""

    def __init__(self, real):
        self.engine = real.engine

    def session(self):
        raise RuntimeError("database is locked / unreadable")


def test_missing_or_unreadable_accounting_store_refuses():
    _refused(lambda: G.authorize(None, provider=FLUX, scope=G.GENERATION, estimate_cad=0.07,
                                 fingerprint="x", reservation_id=1),
             code="accounting_store_missing")
    db = _db()
    _activate(db)
    held = _reserve(db, 0.07, now=datetime.now(timezone.utc))
    _refused(lambda: G.authorize(_Unreadable(db), provider=FLUX, scope=G.GENERATION,
                                 estimate_cad=0.07, fingerprint="x",
                                 reservation_id=held["reservation_id"]),
             code="accounting_store_unreadable")
    assert G.activation_state(_Unreadable(db), FLUX, G.GENERATION)["active"] is False
    assert images.usable(_Unreadable(db)) is False
    # A paid vision call with no accounting evidence in its context is never sent.
    G.take_budget()                     # the image reservation above is not vision evidence
    with _env(ANTHROPIC_API_KEY=KEY_VALUE), Wire() as wire:
        _refused(lambda: gw.AnthropicProvider(model=gw.VISION_PROBE_MODEL).see(
            "", "describe", ["https://example.invalid/a.jpg"], max_tokens=8),
            code="accounting_store_missing", exc=gw.VisionGateRefused)
        assert wire.calls == []


# ---- 6. activation needs step-up evidence; every change is audited -------------------------

def test_activation_without_step_up_evidence_is_rejected_and_changes_are_audited():
    db = _db()
    ceil = dict(daily_ceiling_cad=1.0, monthly_ceiling_cad=5.0, per_gallery_cad=1.0)
    for pid in ("", "s_nobody", _session(db, stepup=False), _session(db, revoked=True),
                _session(db, stepup_expired=True)):
        try:
            G.activate(db, provider=FLUX, scope=G.GENERATION, by="owner:test",
                       session_public_id=pid, **ceil)
        except G.ActivationRefused as exc:
            assert "step-up" in str(exc), exc
        else:
            raise AssertionError(f"activated without step-up evidence ({pid!r})")
    assert G.activation_state(db, FLUX, G.GENERATION)["active"] is False
    for bad in (dict(ceil, daily_ceiling_cad="nan"), dict(ceil, per_gallery_cad=0),
                dict(ceil, monthly_ceiling_cad=gw.monthly_ceiling_cad() + 1)):
        try:
            G.activate(db, provider=FLUX, scope=G.GENERATION, by="owner:test",
                       session_public_id=_session(db), **bad)
        except G.ActivationRefused:
            pass
        else:
            raise AssertionError(f"activation accepted {bad}")
    try:
        G.activate(db, provider="not-a-provider", scope=G.GENERATION, by="owner:test",
                   session_public_id=_session(db), **ceil)
        raise AssertionError("unknown provider activated")
    except G.ActivationRefused:
        pass
    a = _activate(db)
    assert a["step_up"]["session_public_id"].startswith("s_") and a["status"] == "active"
    b = _activate(db)                                        # supersedes the first
    _revoke(db)
    with db.session() as s:
        acts = [r.detail for r in s.scalars(select(AuditLog).where(
            AuditLog.action == G.ACTION_ACTIVATED).order_by(AuditLog.id))]
        revs = [r.detail for r in s.scalars(select(AuditLog).where(
            AuditLog.action == G.ACTION_REVOKED))]
    assert [d["id"] for d in acts] == [a["id"], b["id"]] and acts[1]["superseded"] == [a["id"]]
    assert all(d["step_up"]["session_public_id"] for d in acts)
    assert len(revs) == 1 and revs[0]["revoked"] == [b["id"]] and revs[0]["step_up"]
    # Revocation also demands step-up.
    try:
        G.revoke(db, provider=FLUX, scope=G.GENERATION, by="owner:test",
                 session_public_id=_session(db, stepup=False))
        raise AssertionError("revoked without step-up")
    except G.ActivationRefused:
        pass


def test_the_owner_route_requires_step_up_and_audits():
    import r2_security_harness as H  # the real app, owner login, CSRF and nonce

    c = H.client()
    csrf = H.login(c)
    body = {"provider": FLUX, "scope": "generation", "daily_ceiling_cad": 1.0,
            "monthly_ceiling_cad": 5.0, "per_gallery_cad": 1.0}
    with H.DB.session() as s:
        for row in s.scalars(select(OwnerSession)):
            row.stepup_until = None
    r = c.post("/api/cc/paid-providers/activate", json=body, headers=H.fresh(csrf))
    assert r.status_code == 403 and "STEP_UP_REQUIRED" in r.text, r.text
    assert G.activation_state(H.DB, FLUX, G.GENERATION)["active"] is False
    with H.DB.session() as s:
        for row in s.scalars(select(OwnerSession)):
            row.stepup_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    r = c.post("/api/cc/paid-providers/activate", json=body, headers=H.fresh(csrf))
    assert r.status_code == 200, r.text
    assert G.activation_state(H.DB, FLUX, G.GENERATION)["active"] is True
    view = c.get("/api/cc/paid-providers", headers=H.fresh(csrf)).json()
    assert view["key_is_not_activation"]
    r = c.post("/api/cc/paid-providers/revoke", json={"provider": FLUX, "scope": "generation"},
               headers=H.fresh(csrf))
    assert r.status_code == 200, r.text
    assert G.activation_state(H.DB, FLUX, G.GENERATION)["active"] is False


# ---- 7. paid vision obeys the same gate -----------------------------------------------------

def test_vision_probe_and_vision_judge_calls_obey_the_gate():
    db = _db()
    with _env(ANTHROPIC_API_KEY=KEY_VALUE), Wire() as wire:
        rec = gw.vision_probe(db, image_url="https://example.invalid/g.jpg")
        assert rec["ok"] is False and rec["state"] == G.NOT_ACTIVATED and wire.calls == []
        assert gw.vision_usable(db) is False
        # A vision judge (any `provider.see` after the usual reservation) is refused too.
        provider = gw.AnthropicProvider(model=gw.VISION_PROBE_MODEL)
        gw.check_budget(db, model=provider.model, input_tokens=6000, max_tokens=8,
                        agent="gateway", purpose="test.vision")
        _refused(lambda: provider.see("", "judge", ["https://example.invalid/g.jpg"],
                                      max_tokens=8),
                 code=G.NOT_ACTIVATED, exc=gw.VisionGateRefused)
        assert wire.calls == []

        from brambleloop.core.models import BenchmarkListing
        with db.session() as session:
            session.add(BenchmarkListing(benchmark_key="fixture", listing_ref="probe-fixture",
                audit_state="audited", detail={"image_urls": ["https://example.invalid/g.jpg"]}))
        act = _activate(db, G.ANTHROPIC_VISION, G.VISION)
        rec = gw.vision_probe(db, image_url="https://example.invalid/g.jpg")
        assert rec["ok"] is True and rec["activation_id"] == act["id"], rec
        assert len(wire.calls) == 1 and gw.vision_usable(db) is True
        gw.check_budget(db, model=provider.model, input_tokens=6000, max_tokens=8,
                        agent="gateway", purpose="test.vision")
        out = provider.see("", "judge", ["https://example.invalid/g2.jpg"], max_tokens=8)
        assert out.text == "photograph" and len(wire.calls) == 2
        # One reservation, one call: a second call with no fresh reservation is refused.
        _refused(lambda: provider.see("", "judge", ["https://example.invalid/g3.jpg"],
                                      max_tokens=8),
                 code="accounting_store_missing", exc=gw.VisionGateRefused)
        assert len(wire.calls) == 2
        # The owner's vision ceiling binds the judge: a day already spent refuses.
        _activate(db, G.ANTHROPIC_VISION, G.VISION, daily_ceiling_cad=0.0001)
        gw.check_budget(db, model=provider.model, input_tokens=6000, max_tokens=8,
                        agent="gateway", purpose="test.vision")
        _refused(lambda: provider.see("", "judge", ["https://example.invalid/g4.jpg"],
                                      max_tokens=8),
                 code="provider_daily_ceiling", exc=gw.VisionGateRefused)
        assert len(wire.calls) == 2
        _revoke(db, G.ANTHROPIC_VISION, G.VISION)
        assert gw.vision_usable(db) is False
    vrows = [r for r in _calls_rows(db) if r[0] == G.ANTHROPIC_VISION]
    assert [r[1] for r in vrows] == [G.BILLED, G.BILLED], vrows


def test_the_openai_research_judge_obeys_the_gate():
    from brambleloop.visual import d_judge

    db = _db()
    img = Path(_TMP) / "judge.png"
    img.write_bytes(base64.b64decode(PNG))
    with _env(OPENAI_API_KEY=KEY_VALUE, BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD="5"), \
            Wire() as wire:
        try:
            d_judge.see(str(img), db=db)
            raise AssertionError("the research judge was allowed without activation")
        except d_judge.JudgeSpendRefused as exc:
            assert G.NOT_ACTIVATED in str(exc), exc
        assert wire.calls == []


def test_openai_judge_invalid_usage_counts_worst_case_not_credit():
    from brambleloop.visual import d_judge
    import json

    db = _db()
    _activate(db, provider=G.OPENAI_VISION, scope=G.VISION)
    img = Path(_TMP) / "invalid-usage-judge.png"
    img.write_bytes(base64.b64decode(PNG))
    original_urlopen, original_spent = urllib.request.urlopen, d_judge._spent_usd
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps({"usage": {"prompt_tokens": -100, "completion_tokens": 1},
                               "choices": [{"message": {"content": "{}"}}]}).encode()
    try:
        urllib.request.urlopen = lambda *a, **k: Response()
        d_judge._spent_usd = 0
        with _env(OPENAI_API_KEY=KEY_VALUE, BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD="5"):
            gw.check_budget_cad(db, estimate_cad=0.1, agent="gateway", purpose="test.judge")
            result = d_judge.see(str(img), db=db)
        assert d_judge._spent_usd == d_judge._worst_case_usd(), d_judge._spent_usd
        assert result["cost_usd"] > 0 and "worst-case" in result["price_basis"], result
    finally:
        urllib.request.urlopen = original_urlopen
        d_judge._spent_usd = original_spent


def test_ambiguous_transport_errors_remain_counted_for_all_paid_vision_and_image_calls():
    from brambleloop.visual import d_judge
    import json

    db = _db()
    _activate(db)
    _activate(db, provider=G.ANTHROPIC_VISION, scope=G.VISION)
    _activate(db, provider=G.OPENAI_VISION, scope=G.VISION)
    original_post, original_send, original_urlopen = images._post, gw.AnthropicProvider._send, urllib.request.urlopen
    original_spent = d_judge._spent_usd
    img = Path(_TMP) / "ambiguous-judge.png"
    img.write_bytes(base64.b64decode(PNG))
    class BadResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return b"not-json-despite-200"
    def bad_post(*args, **kwargs): raise ConnectionResetError("after possible send")
    def bad_vision(*args, **kwargs): raise gw.TransientError("wrapped network error")
    try:
        images._post = bad_post
        gw.AnthropicProvider._send = bad_vision
        urllib.request.urlopen = lambda *args, **kwargs: BadResponse()
        d_judge._spent_usd = 0
        with _env(**ENV, ANTHROPIC_API_KEY=KEY_VALUE, OPENAI_API_KEY=KEY_VALUE,
                  BRAMBLELOOP_RESEARCH_JUDGE_CAP_USD="5"):
            try: _render(db, "ambiguous image request")
            except ConnectionResetError: pass
            else: raise AssertionError("image transport did not fail")
            gw.check_budget_cad(db, estimate_cad=0.1, agent="gateway", purpose="test.vision")
            try: gw.AnthropicProvider().see("", "judge", ["https://example.invalid/image"], max_tokens=8)
            except gw.TransientError: pass
            else: raise AssertionError("vision transport did not fail")
            gw.check_budget_cad(db, estimate_cad=0.1, agent="gateway", purpose="test.openai")
            try: d_judge.see(str(img), db=db)
            except json.JSONDecodeError: pass
            else: raise AssertionError("malformed 200 did not fail")
        rows = _calls_rows(db)
        assert len(rows) == 3 and all(row[1] == G.UNCERTAIN for row in rows), rows
    finally:
        images._post, gw.AnthropicProvider._send, urllib.request.urlopen = original_post, original_send, original_urlopen
        d_judge._spent_usd = original_spent


# ---- 8. the owner queue says a key is not activation, by name only ------------------------

def test_owner_queue_card_explains_key_is_not_activation_without_secret_values():
    from brambleloop.ops import owner_queue

    db = _db()
    with _env(**ENV):
        cards = owner_queue.enrich_cards(db, [{"gate": "image_generation", "kind": "OWNER"}])
    card = cards[0]
    assert "key alone activates nothing" in card["why_software_cannot"]
    act = card["activation"]
    assert act["key_is_not_activation"] and act["activated_providers"] == []
    assert FLUX in act["providers_with_key_but_not_activated"]
    assert act["activation_state"][FLUX] == G.NOT_ACTIVATED
    assert KEY_VALUE not in json.dumps(card, default=str)
    _activate(db)
    with _env(**ENV):
        card = owner_queue.enrich_cards(db, [{"gate": "image_generation"}])[0]
    assert card["activation"]["activated_providers"] == [FLUX]


# ---- image production harness (the orchestrator's own job loop) -----------------------------

def _production_with_paid_generator(db) -> str:
    from brambleloop.core.models import PatternVersion, Product
    from brambleloop.creative.pattern_refs import release_hash_of
    from brambleloop.visual import image_production as IP
    from brambleloop.visual.launch_imagery import _listing_parts

    cir = _listing_parts("cloudline-baby-blanket")[1][0]
    rel = release_hash_of(cir)
    with db.session() as s:
        p = Product(slug=cir.slug, title=cir.title or cir.slug)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True, release_hash=rel))
        j = Job(agent="synthetic", job_type="assets.build", inputs={"release": rel})
        s.add(j)
        s.flush()
        s.add(AuditLog(actor="synthetic", action="assets.built",
                       artifact=f"{cir.slug}@{cir.version}", job_id=j.id,
                       detail={"pdf_sha256_by_terminology": {"US": "a" * 64, "UK": "b" * 64}}))

    class Judges:
        def __getattr__(self, _name):
            return lambda *a, **k: {"status": "PASS", "why": "stub"}

    class PaidGenerator:
        name, paid, max_cost_cad_per_call = "paid-stub", True, 0.07
        calls = 0

        def prepare_references(self, **kw):
            return [{"kind": "pattern_derived", "data": base64.b64decode(PNG),
                     "label": "layout"}]

        def generate(self, **kw):
            PaidGenerator.calls += 1
            raise AssertionError("a paid generator was called with the gate closed")

    q = JobQueue(db)

    def follow(inputs, key):
        from brambleloop.queue.durable import DuplicateJob

        try:
            return q.enqueue(IP.AGENT, IP.JOB_TYPE, inputs, idempotency_key=key)
        except DuplicateJob:
            return None

    IP.trigger(follow, slug=cir.slug, version=cir.version, release=rel)
    for _ in range(30):
        job = q.claim("v0-worker", job_types=[IP.JOB_TYPE])
        if job is None:
            break
        IP.run_stage(db, dict(job.inputs), follow=follow, generator=PaidGenerator(),
                     judges=Judges())
        q.complete(job.id, outputs={}, worker="v0-worker", lease_token=job.lease_token)
    run = IP.get_run(db, IP.run_key(cir.slug, cir.version, rel))
    assert run["state"] == "blocked" and PaidGenerator.calls == 0, run
    assert run["spent_cad"] == 0.0 and run["generation_calls"] == 0
    return run["blocked_reason"]


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as exc:  # noqa: BLE001
            fails += 1
            traceback.print_exc()
            print("FAIL", name, f"{type(exc).__name__}: {str(exc)[:600]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
