"""v1.1 lane C: one-tap owner actions and emergency controls (F-886, F-889; §95 "revoke
publishing/spend authority after a plan is prepared but before execution: protected action
revalidates and refuses").

Every action goes through the real `/api/cc/*` routes with a real owner session, and every
effect is checked at the *existing* enforcement point, not in the command center:

* grants: `ops.activation_authority.validate` / `ops.publication_authority.validate` (the
  execution-boundary checks `store.activate` / `store.publish` call);
* department pause: `agents.registry.Registry.authorize` (what the worker calls first);
* spend pause: `agents.registry.SpendGuard.authorize_spend`;
* kill switch: `core.phase.resolve` over the sealed phase chain.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_cc_actions.py
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="v11_cc_actions_")
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
    raise OSError("network refused by the command-center harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import (  # noqa: E402
    BudgetExceeded, PermissionDenied, Registry, SpendGuard)
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth, emergency  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession, SecurityEvent  # noqa: E402
from brambleloop.core import opsauth, phase as phase_mod  # noqa: E402
from brambleloop.core.models import Agent, AuditLog, Improvement, SpendLimit  # noqa: E402
from brambleloop.ops import activation_authority as act  # noqa: E402
from brambleloop.ops import publication_authority as pub  # noqa: E402

OPS = "m" * 40
PASS = "owner passphrase for the action harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db

ACT_CONTENT = {"action": "store.activate", "listing_id": "123", "slug": "throw", "version": "1",
               "release": "release-1", "frames": [{"sha256": "abc"}]}
PUB_CONTENT = {"action": "store.publish", "slug": "throw", "version": "1",
               "release": "release-1", "payload": {"title": "Throw"}}


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def post(c, csrf, path, body):
    return c.post(path, json=body, headers=fresh(csrf))


def expire_stepup(c):
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))


def test_activation_grant_via_command_center_then_revoke_before_execution_refuses():
    c, csrf = session()
    with patch.object(act, "snapshot", return_value=ACT_CONTENT):
        r = post(c, csrf, "/api/cc/actions/activation.preview",
                 {"slug": "throw", "version": "1", "release": "release-1"})
        assert r.status_code == 200, r.text
        digest = r.json()["result"]["digest"]
        body = {"slug": "throw", "version": "1", "release": "release-1",
                "expected_digest": digest, "reason": "owner reviewed on phone"}
        # Without step-up the protected approval is refused and audited.
        expire_stepup(c)
        r = post(c, csrf, "/api/cc/actions/activation.approve", body)
        assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
        assert post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS}).status_code == 200
        # A stale digest is refused by the existing authority, verbatim, as a 409.
        r = post(c, csrf, "/api/cc/actions/activation.approve",
                 {**body, "expected_digest": "0" * 64})
        assert r.status_code == 409 and r.json()["code"] == "REFUSED_BY_AUTHORITY", r.text
        assert "preview changed" in r.json()["error"]
        r = post(c, csrf, "/api/cc/actions/activation.approve", body)
        assert r.status_code == 200, r.text
        ident = r.json()["result"]["approval_id"]

        def check():
            return act.validate(DB, ident, slug="throw", version="1", listing_id="123",
                                release="release-1")

        # The grant is the existing sealed, chained grant: valid at the execution boundary.
        assert check() is None
        with DB.session() as s:
            row = s.get(AuditLog, ident)
            assert row.action == act.APPROVED and row.actor == act.PRINCIPAL
            assert "command center" in row.detail["reason"]
            assert "seal" in row.detail
        # Revoke after the plan is prepared, before execution: execution refuses.
        r = post(c, csrf, "/api/cc/actions/activation.revoke", {"approval_id": ident})
        assert r.status_code == 200, r.text
        assert "revoked" in (check() or ""), check()


def test_publication_grant_is_revoked_by_the_publishing_pause():
    c, csrf = session()
    with patch.object(pub, "snapshot", return_value=PUB_CONTENT), \
            patch.dict(os.environ, {pub.KILL_SWITCH_VAR: "1"}):
        r = post(c, csrf, "/api/cc/actions/publication.preview",
                 {"slug": "throw", "version": "1", "release": "release-1"})
        assert r.status_code == 200, r.text
        assert r.json()["result"]["display"], "evidence must accompany a publication preview"
        digest = r.json()["result"]["digest"]
        r = post(c, csrf, "/api/cc/actions/publication.approve",
                 {"slug": "throw", "version": "1", "release": "release-1",
                  "expected_digest": digest, "reason": "owner reviewed evidence"})
        assert r.status_code == 200, r.text
        ident = r.json()["result"]["approval_id"]
        assert pub.validate(DB, ident, slug="throw", version="1", release="release-1") is None
        status = c.get("/api/cc/emergency").json()
        assert [g for g in status["publishing"]["live_grants"]
                if g["approval_id"] == ident], status["publishing"]
        r = post(c, csrf, "/api/cc/emergency/pause",
                 {"scope": "publishing", "reason": "stop all publishing now"})
        assert r.status_code == 200, r.text
        assert [g for g in r.json()["grants_revoked"] if g["approval_id"] == ident]
        why = pub.validate(DB, ident, slug="throw", version="1", release="release-1")
        assert why and "revoked" in why, why
    with DB.session() as s:
        assert s.scalar(select(Agent).where(Agent.name == "store_operator")).enabled is False
    try:
        Registry(DB).authorize("store_operator", "store.publish")
        raise AssertionError("store_operator still authorised after the publishing pause")
    except PermissionDenied:
        pass
    # Resume needs step-up, and then re-enables what the command center paused.
    expire_stepup(c)
    r = post(c, csrf, "/api/cc/emergency/resume", {"scope": "publishing", "reason": "resume"})
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED"
    assert post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS}).status_code == 200
    r = post(c, csrf, "/api/cc/emergency/resume", {"scope": "publishing", "reason": "resume"})
    assert r.status_code == 200 and "store_operator" in r.json()["agents_enabled"], r.text


def test_department_pause_stops_the_worker_authorising_its_jobs_but_not_monitoring():
    c, csrf = session()
    reg = Registry(DB)
    growth = reg.get("growth")
    job_type = growth.allowed_job_types[0]
    reg.authorize("growth", job_type)  # authorised before the pause
    r = post(c, csrf, "/api/cc/emergency/pause",
             {"scope": "department", "department": "growth", "reason": "growth misbehaving"})
    assert r.status_code == 200, r.text
    assert set(r.json()["agents_disabled"]) >= {"growth", "ads"}, r.json()
    try:
        reg.authorize("growth", job_type)
        raise AssertionError("a paused department's job was authorised")
    except PermissionDenied:
        pass
    # Monitoring/evidence departments refuse to pause.
    for dept in emergency.NEVER_PAUSED:
        r = post(c, csrf, "/api/cc/emergency/pause",
                 {"scope": "department", "department": dept, "reason": "try"})
        assert r.status_code == 409, (dept, r.text)
    orch = reg.get("orchestrator")
    reg.authorize("orchestrator", orch.allowed_job_types[0])
    # An agent disabled for another reason is not re-enabled by a resume.
    with DB.session() as s:
        s.scalar(select(Agent).where(Agent.name == "market_radar")).enabled = False
    r = post(c, csrf, "/api/cc/emergency/resume",
             {"scope": "company", "reason": "all clear now"})
    assert r.status_code == 200, r.text
    assert "growth" in r.json()["agents_enabled"]
    assert "market_radar" not in r.json()["agents_enabled"]
    with DB.session() as s:
        assert s.scalar(select(Agent).where(Agent.name == "market_radar")).enabled is False
        s.scalar(select(Agent).where(Agent.name == "market_radar")).enabled = True
    reg.authorize("growth", job_type)


def test_spend_pause_refuses_spend_and_resume_leaves_breach_pauses_alone():
    c, csrf = session()
    guard = SpendGuard(DB)
    guard.set_limit("llm", 5.0, 50.0)
    guard.set_limit("ads", 0.5, 1.0)
    guard.authorize_spend("llm", 0.1)
    try:
        guard.authorize_spend("ads", 2.0)  # breaches: the guard pauses the scope itself
    except BudgetExceeded:
        pass
    r = post(c, csrf, "/api/cc/emergency/pause", {"scope": "spend", "reason": "freeze spend"})
    assert r.status_code == 200, r.text
    assert r.json()["spend_scopes_paused"] == ["llm"], r.json()
    try:
        guard.authorize_spend("llm", 0.1)
        raise AssertionError("spend authorised while paused")
    except BudgetExceeded as exc:
        assert "paused" in str(exc)
    r = post(c, csrf, "/api/cc/emergency/resume", {"scope": "spend", "reason": "unfreeze"})
    assert r.status_code == 200, r.text
    assert r.json()["spend_scopes_unpaused"] == ["llm"]
    assert any("ads" in x for x in r.json()["left_alone"]), r.json()
    guard.authorize_spend("llm", 0.1)
    with DB.session() as s:
        assert s.scalar(select(SpendLimit).where(SpendLimit.scope == "ads")).paused is True


def test_kill_switch_records_shadow_and_pauses_the_company():
    c, csrf = session()
    r = post(c, csrf, "/api/cc/emergency/kill", {"reason": "something is wrong"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["effective_phase"] == "shadow"
    assert out["transition"].get("transition_id") or out["transition"].get("already_shadow")
    hist = phase_mod.history(DB, limit=5)
    assert hist and hist[0]["to"] == "shadow" and hist[0]["valid"], hist[:1]
    assert phase_mod.resolve(DB)["phase"] == "shadow"
    st = c.get("/api/cc/emergency").json()
    pausable = [d for d in st["departments"] if d["pausable"] and d["registered"]]
    assert len(pausable) >= 5, pausable
    for d in pausable:
        assert d["paused"], d
    assert st["departments"]
    for d in st["departments"]:
        if d["department"] in emergency.NEVER_PAUSED:
            assert not d["paused"], d
    # A second kill is idempotent (phase already shadow).
    r = post(c, csrf, "/api/cc/emergency/kill", {"reason": "again"})
    assert r.status_code == 200, r.text
    assert post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS}).status_code == 200
    assert post(c, csrf, "/api/cc/emergency/resume",
                {"scope": "company", "reason": "recovered"}).status_code == 200
    assert phase_mod.resolve(DB)["phase"] == "shadow", "resume must never raise the phase"


def test_improvement_approval_routes_through_cells():
    c, csrf = session()
    with DB.session() as s:
        row = Improvement(cell="visual", metric="m", hypothesis="h", state="proposed",
                          evidence={})
        s.add(row)
        s.flush()
        iid = row.id
    r = post(c, csrf, "/api/cc/actions/improvement.approve", {"id": iid, "why": "ok"})
    assert r.status_code == 409 and "says why" in r.json()["error"], r.text
    r = post(c, csrf, "/api/cc/actions/improvement.approve",
             {"id": iid, "why": "the sandbox result beats baseline"})
    assert r.status_code == 200, r.text
    with DB.session() as s:
        ev = s.get(Improvement, iid).evidence
    assert ev["owner_approval"]["by"] == "owner"
    with DB.session() as s:
        a = s.scalars(select(AuditLog).where(
            AuditLog.action == "cc.owner_action.improvement.approve")).first()
    assert a is not None and a.actor.startswith("owner:cc:s_")


def test_authority_refusals_are_audited():
    c, csrf = session()
    with DB.session() as s:
        before = s.query(SecurityEvent).filter(SecurityEvent.kind == "action").count()
    r = post(c, csrf, "/api/cc/actions/activation.revoke", {"approval_id": "nope"})
    assert r.status_code == 409, r.text
    r = post(c, csrf, "/api/cc/actions/not.a.thing", {})
    assert r.status_code == 404
    with DB.session() as s:
        after = s.query(SecurityEvent).filter(SecurityEvent.kind == "action").count()
    assert after == before + 2


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
