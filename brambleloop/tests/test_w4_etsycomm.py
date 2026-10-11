"""W4-ETSYCOMM: the Etsy connection failures in production, and the owner's route to fix them.

Production (0417f35, read 2026-10-11): every `etsy.probe` since 2026-10-07T12:00Z is HTTP 403
after 18 days of success with no deploy in between; `listing.taxonomy_refresh` dead-lettered on
the same 403 (job 11847); no taxonomy snapshot exists, so the search certificate refuses; and
the owner could neither re-test the key nor authorise the shop without the operator token.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_etsycomm.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="w4_etsycomm_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-ETSYCOMM harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, EtsyTaxonomySnapshot, Job, JobStatus, OAuthHandshake, Phase)
from brambleloop.integrations import etsy_taxonomy as T  # noqa: E402
from brambleloop.intel import etsy_public as ep  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

KEY = "keystringW4ETSYCOMM0001"
SECRET = "sharedsecretW4ETSYCOMM01"
REFUSED = "API key not found or not active, or incorrect shared secret for API key."
PASS = "owner passphrase for the etsy connect harness"
OPS = "e" * 40
SEAL = "a-test-sealing-key-of-quite-sufficient-length-0123456789"
REDIRECT = "https://brambleloop.example/api/etsy/oauth/callback"

os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()


def _db(name: str) -> Database:
    db = Database(f"sqlite:///{_TMP}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


@dataclass
class _R:
    status: int
    body: dict
    headers: dict = field(default_factory=dict)


class _Transport:
    """Answers every request with one status/body, or with the recorded taxonomy."""

    def __init__(self, status: int = 200, body: dict | None = None, *, taxonomy=False):
        self.status, self.body, self.taxonomy = status, body or {}, taxonomy
        self.requests: list[tuple[str, str, dict]] = []

    def request(self, method, url, *, headers, body=None, timeout=20.0, json=None,
                form=None, multipart=None):
        self.requests.append((method, url, dict(headers)))
        if self.taxonomy:
            if url.endswith("/seller-taxonomy/nodes"):
                return _R(200, FX.NODES_RESPONSE)
            return _R(200, FX.properties_response(int(url.rstrip("/").split("/")[-2])))
        return _R(self.status, self.body)


def _record_probe(db, detail: dict) -> None:
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", artifact="ping",
                       detail=detail))


def _run(db, agent: str, job_type: str, *, key: str) -> Job:
    JobQueue(db).enqueue(agent, job_type, {}, priority=0, idempotency_key=key)
    w = Worker(db, f"w4e-{job_type}", phase=Phase.SHADOW, job_types=[job_type])
    for _ in range(5):
        if not w.run_once():
            break
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.idempotency_key == key))
        s.expunge(job)
        return job


class _Env:
    """Set environment variables for one block and restore them after."""

    def __init__(self, **values):
        self.values, self.saved = values, {}

    def __enter__(self):
        for k, v in self.values.items():
            self.saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ---- 1. Etsy's refusal text is kept, and a credential echoed back is not ----------------------

def test_a_403_carries_etsys_own_reason_into_the_error_and_the_probe_row():
    db = _db("reason")
    env = {ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET}
    record = ep.probe(db, transport=_Transport(403, {"error": REFUSED}), env=env)
    assert record["ok"] is False and record["status"] == 403
    assert record["etsy_error"] == REFUSED, record
    assert REFUSED in record["reason"] and ep.SECRET_VAR in record["reason"]
    assert ep.last_probe(db)["etsy_error"] == REFUSED
    assert ep.auth_refused(ep.last_probe(db))


def test_a_credential_echoed_in_etsys_body_never_reaches_the_record():
    db = _db("echo")
    env = {ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET}
    echoed = {"error": f"bad header {KEY}:{SECRET} rejected"}
    record = ep.probe(db, transport=_Transport(403, echoed), env=env)
    blob = repr(record) + repr(ep.last_probe(db))
    assert KEY not in blob and SECRET not in blob, blob
    assert "***" in record["etsy_error"]


def test_a_body_with_no_error_field_records_no_invented_reason():
    db = _db("noreason")
    env = {ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET}
    record = ep.probe(db, transport=_Transport(403, {}), env=env)
    assert "etsy_error" not in record and "no reason text" in record["reason"]


# ---- 2. The taxonomy snapshot: least-privileged client, honest stand-aside ----------------------

def test_the_keystring_client_is_used_even_after_the_probe_succeeds():
    """Production has no ETSY_SHOP_ID, so the shop-credential client cannot be built; the
    refresh would have said 'no client' forever the day the key worked."""
    db = _db("prefer_key")
    _record_probe(db, {"ok": True, "application_id": 1})
    g = T.gate(db, env={"ETSY_KEYSTRING": KEY})
    assert g["open"] and g["via"] == "api_key_only", g
    transport = _Transport(taxonomy=True)
    saved = T.api_key_transport_factory
    T.api_key_transport_factory = lambda: transport
    try:
        with _Env(ETSY_KEYSTRING=KEY, ETSY_SHARED_SECRET=SECRET, ETSY_SHOP_ID=None):
            got = T.refresh(db)
    finally:
        T.api_key_transport_factory = saved
    assert got["ran"] and got["reading"] == "measured" and got["snapshot_id"], got
    assert len(transport.requests) == got["network_calls"] >= 2
    for method, url, headers in transport.requests:
        assert method == "GET" and "/seller-taxonomy/" in url
        assert "Authorization" not in headers and headers["x-api-key"] == f"{KEY}:{SECRET}"


def test_a_refused_key_makes_the_refresh_stand_aside_with_no_request_and_no_dead_letter():
    db = _db("refused_probe")
    _record_probe(db, {"ok": False, "status": 403, "reason": "ping returned HTTP 403"})

    def never():
        raise AssertionError("a transport was built for a key Etsy refused")

    saved = T.api_key_transport_factory
    T.api_key_transport_factory = never
    try:
        with _Env(ETSY_KEYSTRING=KEY, ETSY_SHARED_SECRET=SECRET):
            job = _run(db, "listing", T.JOB_TYPE, key="tax-refused")
    finally:
        T.api_key_transport_factory = saved
    assert job.status == JobStatus.DONE, (job.status, job.last_error)
    out = job.outputs
    assert out["ran"] is False and out["reading"] == "UNMEASURED"
    assert out["credential_refused"] is True and out["network_calls"] == 0
    with db.session() as s:
        assert s.scalar(select(EtsyTaxonomySnapshot)) is None
        row = s.scalar(select(AuditLog).where(AuditLog.action == "etsy.taxonomy_unmeasured"))
        assert row is not None and row.detail["credential_refused"] is True


def test_a_403_during_the_read_is_reported_not_dead_lettered():
    """Production job 11847: EtsyRejected on the API-key path, dead on its first attempt."""
    db = _db("refused_midread")
    saved = T.api_key_transport_factory
    T.api_key_transport_factory = lambda: _Transport(403, {"error": REFUSED})
    try:
        with _Env(ETSY_KEYSTRING=KEY, ETSY_SHARED_SECRET=SECRET):
            job = _run(db, "listing", T.JOB_TYPE, key="tax-midread")
    finally:
        T.api_key_transport_factory = saved
    assert job.status == JobStatus.DONE, (job.status, job.last_error)
    assert job.outputs["credential_refused"] is True
    assert job.outputs["etsy_error"] == REFUSED
    assert SECRET not in repr(job.outputs) and KEY not in repr(job.outputs)


def test_a_server_fault_on_the_taxonomy_still_raises_for_the_jobs_retries():
    from brambleloop.integrations.etsy import TransientError

    client = T.ApiKeyTaxonomyClient(_Transport(503, {}), api_key=KEY, shared_secret=SECRET)
    try:
        client._call("GET", "/seller-taxonomy/nodes", operation=T.NODES_OPERATION)
    except TransientError:
        pass
    else:
        raise AssertionError("a 503 was not transient")


# ---- 3. A probe that recovers queues the snapshot straight away -------------------------------

def _probe_job(db, transport, key):
    import brambleloop.integrations.http as http_mod

    saved = http_mod.UrllibTransport
    http_mod.UrllibTransport = lambda *a, **k: transport
    try:
        with _Env(**{ep.KEYSTRING_VAR: KEY, ep.SECRET_VAR: SECRET}):
            return _run(db, "market_radar", "etsy.probe", key=key)
    finally:
        http_mod.UrllibTransport = saved


def test_a_successful_probe_with_no_snapshot_queues_the_taxonomy_refresh():
    db = _db("recover")
    job = _probe_job(db, _Transport(200, {"application_id": 7}), "probe-ok")
    assert job.status == JobStatus.DONE and job.outputs["ok"] is True, job.last_error
    assert job.outputs["taxonomy_refresh_queued"] is True
    with db.session() as s:
        queued = list(s.scalars(select(Job).where(Job.job_type == T.JOB_TYPE)))
    assert len(queued) == 1 and len(queued[0].idempotency_key) <= 200


def test_a_failed_probe_queues_nothing_and_a_snapshot_stops_the_queueing():
    db = _db("noqueue")
    job = _probe_job(db, _Transport(403, {"error": REFUSED}), "probe-bad")
    assert job.outputs["ok"] is False and "taxonomy_refresh_queued" not in job.outputs
    with db.session() as s:
        s.add(EtsyTaxonomySnapshot(source="fixture", sha256="x" * 64, node_count=0,
                                   nodes=[], properties={}, detail={}))
    job = _probe_job(db, _Transport(200, {"application_id": 7}), "probe-ok2")
    assert job.outputs["ok"] is True and "taxonomy_refresh_queued" not in job.outputs
    with db.session() as s:
        assert s.scalar(select(Job).where(Job.job_type == T.JOB_TYPE)) is None


# ---- 4. The owner's buttons: session, CSRF, step-up, honest refusals, nothing secret ----------

def _session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def _fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def _clear_probes():
    with main.db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == "etsy.probe")):
            s.delete(row)


def test_the_buttons_refuse_without_a_session_or_without_csrf():
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    for path in ("/api/cc/etsy/recheck", "/api/cc/etsy/connect"):
        assert anon.post(path, json={}).status_code == 401
    assert anon.get("/api/cc/etsy").status_code == 401
    c, csrf = _session()
    for path in ("/api/cc/etsy/recheck", "/api/cc/etsy/connect"):
        r = c.post(path, json={}, headers={"X-CC-Nonce": uuid.uuid4().hex,
                                           "X-CC-Timestamp": str(int(time.time()))})
        assert r.status_code == 403, (path, r.status_code, r.text)


def test_recheck_queues_one_read_only_probe_and_is_audited():
    c, csrf = _session()
    r = c.post("/api/cc/etsy/recheck", json={}, headers=_fresh(csrf))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["enqueued"] is True
    with main.db.session() as s:
        job = s.get(Job, body["job_id"])
        assert job.job_type == "etsy.probe" and job.agent == "market_radar"
        assert s.scalar(select(AuditLog).where(AuditLog.action == "cc.etsy.recheck"))
    again = c.post("/api/cc/etsy/recheck", json={}, headers=_fresh(csrf)).json()
    assert again["enqueued"] is False  # one per minute


def test_connect_refuses_while_etsy_refuses_the_key():
    _clear_probes()
    _record_probe(main.db, {"ok": False, "status": 403, "at": "2026-10-11T12:00:41",
                            "reason": "ping returned HTTP 403", "etsy_error": REFUSED})
    with _Env(ETSY_KEYSTRING=KEY, ETSY_SHARED_SECRET=SECRET, ETSY_REDIRECT_URI=REDIRECT,
              BRAMBLELOOP_SECRET_KEY=SEAL):
        c, csrf = _session()
        st = c.get("/api/cc/etsy").json()
        assert st["api_key_probe"]["state"] == "FAILING" and st["can_connect"] is False
        assert st["api_key_probe"]["etsy_error"] == REFUSED
        r = c.post("/api/cc/etsy/connect", json={}, headers=_fresh(csrf))
    assert r.status_code == 409 and r.json()["code"] == "ETSY_KEY_REFUSED", r.text
    assert "etsy.com/developers/your-apps" in r.json()["error"]
    with main.db.session() as s:
        assert s.scalar(select(OAuthHandshake)) is None


def test_connect_refuses_with_the_configuration_problems_when_unconfigured():
    _clear_probes()
    with _Env(ETSY_KEYSTRING=KEY, ETSY_SHARED_SECRET=SECRET, ETSY_REDIRECT_URI=None,
              BRAMBLELOOP_SECRET_KEY=SEAL):
        c, csrf = _session()
        r = c.post("/api/cc/etsy/connect", json={}, headers=_fresh(csrf))
    assert r.status_code == 409 and r.json()["code"] == "ETSY_NOT_CONFIGURED", r.text
    assert "ETSY_REDIRECT_URI" in r.json()["error"]


def test_connect_needs_a_fresh_step_up():
    _clear_probes()
    with _Env(ETSY_KEYSTRING=KEY, ETSY_SHARED_SECRET=SECRET, ETSY_REDIRECT_URI=REDIRECT,
              BRAMBLELOOP_SECRET_KEY=SEAL):
        c, csrf = _session()
        with main.db.session() as s:
            for row in s.scalars(select(OwnerSession)):
                row.stepup_until = auth._now() - timedelta(minutes=1)
        r = c.post("/api/cc/etsy/connect", json={}, headers=_fresh(csrf))
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text


def test_connect_returns_etsys_consent_url_and_nothing_secret():
    _clear_probes()
    _record_probe(main.db, {"ok": True, "application_id": 1})
    with _Env(ETSY_KEYSTRING=KEY, ETSY_SHARED_SECRET=SECRET, ETSY_REDIRECT_URI=REDIRECT,
              BRAMBLELOOP_SECRET_KEY=SEAL):
        c, csrf = _session()
        r = c.post("/api/cc/etsy/connect", json={}, headers=_fresh(csrf))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authorize_url"].startswith("https://www.etsy.com/oauth/connect?")
    assert "transactions_r" in body["scopes"] and body["redirect_uri"] == REDIRECT
    assert set(body) >= {"authorize_url", "state_expires_at", "state_fingerprint"}
    text = r.text
    assert SECRET not in text and SEAL not in text
    assert "verifier" not in {k.lower() for k in body}
    with main.db.session() as s:
        hs = s.scalar(select(OAuthHandshake).order_by(OAuthHandshake.id.desc()))
        assert hs is not None
        for attr in ("verifier_sealed", "state_hash"):
            value = str(getattr(hs, attr, "") or "")
            if value:
                assert value not in text
        started = s.scalar(select(AuditLog).where(AuditLog.action == "etsy.oauth_started")
                           .order_by(AuditLog.id.desc()))
        assert started.detail["source"] == "command_center"
        assert started.detail["state_fingerprint"].startswith("***")


def test_the_store_tab_offers_both_buttons():
    static = ROOT / "src/brambleloop/app/command_center/static/js"
    store = (static / "views/store.js").read_text()
    api = (static / "api.js").read_text()
    assert "Re-check Etsy connection" in store and "Connect Etsy shop" in store
    assert "requiresStepUp: true" in store
    assert 'ETSY_CONSENT_HOST = "www.etsy.com"' in store and "hostname" in store
    assert "/etsy/recheck" in api and "/etsy/connect" in api


def _run_all() -> int:
    failures = 0
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failures += 1
            print(f"FAIL {name}: {exc}")
            traceback.print_exc()
    print(f"{len(tests) - failures} passed, {failures} failed")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run_all() else 0)
