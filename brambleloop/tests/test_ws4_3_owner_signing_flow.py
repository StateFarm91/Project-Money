"""WS4-3: the standing policy's owner signing flow through the Command Center (design §1.7).

Approve, activate, resume and rebase are owner acts: owner session, CSRF/nonce, a fresh
step-up, and signed only inside the owner request that the action route enters for exactly
those four. Preview reads; revoke and suspend only tighten. The operator bearer has no route
that grants. Every job process scrubs the policy signing key.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws4_3_owner_signing_flow.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
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
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="ws4_3_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "BRAMBLELOOP_STOREFRONT", "BRAMBLELOOP_POLICY")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import approvals, auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from test_ws4_policy_object import content  # noqa: E402

OPS = "w" * 40
PASS = "owner passphrase for the standing policy harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
_PAIRS = sp.generate_keypairs()
KEYS = {sp.SIGNING_KEY_VAR: _PAIRS[sp.SIGNING_KEY_VAR],
        sp.VERIFY_KEY_VAR: _PAIRS[sp.VERIFY_KEY_VAR]}
SIGNING = ("standing_policy.approve", "standing_policy.activate", "standing_policy.resume",
           "standing_policy.rebase")
TIGHTENING_OR_READ = ("standing_policy.preview", "standing_policy.revoke",
                      "standing_policy.suspend")


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def expire_stepup(c):
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))


def stepup(c, csrf):
    assert c.post("/api/cc/auth/step-up", json={"passphrase": PASS},
                  headers=fresh(csrf)).status_code == 200


def _new_content():
    return content(policy_id=f"sp-{uuid.uuid4()}")


def _preview(c, csrf, body):
    r = c.post("/api/cc/actions/standing_policy.preview", json={"content": body},
               headers=fresh(csrf))
    assert r.status_code == 200, r.text
    return r.json()["result"]


def _approve(c, csrf, body, **over):
    pv = _preview(c, csrf, body)
    payload = {"content": body, "expected_digest": pv["digest"],
               "confirmation": pv["confirmation"], "reason": "owner read the statement"}
    payload.update(over)
    return c.post("/api/cc/actions/standing_policy.approve", json=payload,
                  headers=fresh(csrf))


def test_actions_declare_step_up_exactly_for_the_granting_acts():
    for a in SIGNING:
        assert approvals.ACTIONS[a][0] is True, a
    for a in TIGHTENING_OR_READ:
        assert approvals.ACTIONS[a][0] is False, a


def test_the_route_enters_the_owner_request_only_for_the_four_granting_acts():
    from brambleloop.app.command_center import api as cc_api  # noqa: F401

    src = (ROOT / "src" / "brambleloop" / "app" / "command_center" / "api.py").read_text()
    seg = src[src.index("STANDING_POLICY_SIGNING_ACTIONS = ("):]
    declared = seg[:seg.index(")") + 1]
    for a in SIGNING:
        assert f'"{a}"' in declared, a
    for a in TIGHTENING_OR_READ:
        assert f'"{a}"' not in declared, a
    assert "elif action in STANDING_POLICY_SIGNING_ACTIONS:" in src
    # the publication/activation set is unchanged (WS4-0 F6 pins it separately)
    own = src[src.index("OWNER_GRANT_SIGNING_ACTIONS = ("):]
    assert "standing_policy" not in own[:own.index(")") + 1]


def test_preview_reads_and_records_nothing():
    with patch.dict(os.environ, KEYS):
        c, csrf = session()
        body = _new_content()
        pv = _preview(c, csrf, body)
        assert pv["digest"] == sp.statement_digest(body) and pv["ceiling_refusals"] == []
        assert pv["confirmation"] == sp.confirmation_phrase(body)
        assert pv["deployment_mode"] == "S" and "configured" in pv["key_health"]
        bad = {**body, "frequency": {**body["frequency"], "max_per_day": 9}}
        assert _preview(c, csrf, bad)["ceiling_refusals"]
    with DB.session() as s:
        assert s.scalar(select(AuditLog.id).where(AuditLog.action == sp.APPROVED,
                                                  AuditLog.artifact == body["policy_id"])) \
            is None


def test_approve_needs_a_fresh_step_up_and_signs_inside_the_owner_request():
    with patch.dict(os.environ, KEYS):
        c, csrf = session()
        body = _new_content()
        r = c.post("/api/cc/actions/standing_policy.approve", json={"content": body})
        assert r.status_code in (401, 403), r.text          # no CSRF/nonce
        expire_stepup(c)
        r = _approve(c, csrf, body)
        assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
        stepup(c, csrf)
        r = _approve(c, csrf, body, confirmation="AUTHORISE")
        assert r.status_code == 409 and "type exactly" in r.text, r.text
        r = _approve(c, csrf, body, expected_digest="0" * 64)
        assert r.status_code == 409 and "digest mismatch" in r.text, r.text
        r = _approve(c, csrf, body, reason="")
        assert r.status_code == 409 and "reason" in r.text, r.text
        r = _approve(c, csrf, body)
        assert r.status_code == 200, r.text
        ident = r.json()["result"]["approval_id"]
    with DB.session() as s:
        row = s.get(AuditLog, ident)
        assert row.action == sp.APPROVED and row.actor == sp.PRINCIPAL
        assert row.detail["stepped_up"] is True and "command center" in row.detail["reason"]
        assert row.detail["content"] == body
    with patch.dict(os.environ, KEYS):
        assert sp.LEDGER.refusal(DB, ident) is None


def test_the_same_approval_outside_the_route_is_refused():
    """The route's owner request is what makes signing possible: calling the module from any
    other code path (a job, a script, the bearer) cannot sign."""
    with patch.dict(os.environ, KEYS):
        body = _new_content()
        try:
            sp.approve(DB, body, digest=sp.statement_digest(body),
                       typed_confirmation=sp.confirmation_phrase(body), stepped_up=True,
                       owner_session="x", actor="x", reason="r")
        except ValueError as exc:
            assert "Command Center request" in str(exc)
        else:
            raise AssertionError("signed outside the owner request")


def test_activation_through_the_route_is_refused_until_mode_t():
    with patch.dict(os.environ, KEYS):
        c, csrf = session()
        stepup(c, csrf)
        ident = _approve(c, csrf, _new_content()).json()["result"]["approval_id"]
        r = c.post("/api/cc/actions/standing_policy.activate", json={"approval_id": ident},
                   headers=fresh(csrf))
        assert r.status_code == 409 and "Mode T" in r.text, r.text
        r = c.post("/api/cc/actions/standing_policy.activate",
                   json={"approval_id": ident + 10_000}, headers=fresh(csrf))
        assert r.status_code == 404, r.text
        with DB.session() as s:
            assert s.scalar(select(AuditLog.id).where(AuditLog.action == sp.ACTIVATED)) is None


def test_revoke_and_suspend_tighten_without_step_up_and_resume_is_refused_while_unknown():
    with patch.dict(os.environ, KEYS):
        c, csrf = session()
        stepup(c, csrf)
        body = _new_content()
        ident = _approve(c, csrf, body).json()["result"]["approval_id"]
        expire_stepup(c)
        r = c.post("/api/cc/actions/standing_policy.suspend", headers=fresh(csrf),
                   json={"policy_id": body["policy_id"], "reason": "owner pause"})
        assert r.status_code == 200, r.text
        r = c.post("/api/cc/actions/standing_policy.suspend", headers=fresh(csrf),
                   json={"policy_id": "sp-not-a-policy", "reason": "x"})
        assert r.status_code == 404, r.text
        r = c.post("/api/cc/actions/standing_policy.revoke", headers=fresh(csrf),
                   json={"approval_id": ident})
        assert r.status_code == 200, r.text
        assert sp.LEDGER.refusal(DB, ident) and "revoked" in sp.LEDGER.refusal(DB, ident)
        r = c.post("/api/cc/actions/standing_policy.resume", headers=fresh(csrf),
                   json={"policy_id": body["policy_id"]})
        assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
        stepup(c, csrf)
        r = c.post("/api/cc/actions/standing_policy.resume", headers=fresh(csrf),
                   json={"policy_id": body["policy_id"]})
        assert r.status_code == 409 and "UNKNOWN" in r.text, r.text
        # a revoke naming something that is not a policy approval is not found, not sealed
        r = c.post("/api/cc/actions/standing_policy.revoke", headers=fresh(csrf),
                   json={"approval_id": ident + 10_000})
        assert r.status_code == 404, r.text


def test_rebase_needs_step_up_and_a_reason():
    with patch.dict(os.environ, KEYS):
        c, csrf = session()
        expire_stepup(c)
        r = c.post("/api/cc/actions/standing_policy.rebase", headers=fresh(csrf),
                   json={"reason": "re-anchor"})
        assert r.status_code == 403, r.text
        stepup(c, csrf)
        r = c.post("/api/cc/actions/standing_policy.rebase", headers=fresh(csrf),
                   json={"reason": ""})
        assert r.status_code == 409, r.text
        r = c.post("/api/cc/actions/standing_policy.rebase", headers=fresh(csrf),
                   json={"reason": "owner re-anchors the policy chain"})
        assert r.status_code == 200, r.text


def test_the_operator_bearer_has_no_standing_policy_route():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    bearer = {"Authorization": f"Bearer {OPS}"}
    for path in ("/api/owner/standing_policy/approve", "/api/owner/standing_policy/activate",
                 "/api/owner/standing_policy/resume", "/api/owner/standing_policy/rebase",
                 "/api/cc/actions/standing_policy.approve"):
        r = c.post(path, headers=bearer, json={"content": _new_content()})
        assert r.status_code in (401, 403, 404, 405), (path, r.status_code, r.text)
    with DB.session() as s:
        assert s.scalar(select(AuditLog.id).where(
            AuditLog.action.in_((sp.APPROVED, sp.ACTIVATED, sp.RESUMED)),
            AuditLog.actor != sp.PRINCIPAL)) is None


def test_every_job_process_entry_scrubs_the_policy_signing_key():
    src = ROOT / "src" / "brambleloop" / "app"
    for name in ("worker_entry.py", "hq_worker.py", "runner.py"):
        assert "_sp.mark_job_process()" in (src / name).read_text(), name
    from brambleloop.app import hq_worker

    with patch.dict(os.environ, KEYS):
        try:
            assert sp.SIGNING_KEY_VAR in os.environ
            hq_worker._mark_job_process()
            assert sp.SIGNING_KEY_VAR not in os.environ
            assert sp.signing_refusal() and "runs jobs" in sp.signing_refusal()
        finally:
            sp._JOB_PROCESS["is"] = False
            from brambleloop.core import owner_grant_keys
            from brambleloop.ops import storefront_authority

            owner_grant_keys._JOB_PROCESS["is"] = False
            storefront_authority._JOB_PROCESS["is"] = False


def test_the_inbox_card_states_the_policy_and_offers_only_what_is_possible():
    with patch.dict(os.environ, KEYS):
        c, csrf = session()
        stepup(c, csrf)
        body = _new_content()
        ident = _approve(c, csrf, body).json()["result"]["approval_id"]
        cards = [k for k in approvals.inbox(DB)["cards"] if k.get("kind") == "STANDING_POLICY"]
        assert len(cards) == 1, cards
        card = cards[0]
        assert card["card_id"] == f"standing_policy:{body['policy_id']}"
        assert card["statement"] == sp.render_statement(body)
        assert card["digest"] == sp.statement_digest(body) and card["deployment_mode"] == "S"
        # Not activatable (Mode T, shadow, phase...): the card says why and offers no activate.
        assert card["executable"] is False and "Mode T" in card["not_executable_reason"]
        acts = [a["action"] for a in card["actions"]]
        assert "standing_policy.activate" not in acts and "standing_policy.revoke" in acts
        # Revoking the approval leaves a card that offers nothing that grants.
        r = c.post("/api/cc/actions/standing_policy.revoke", headers=fresh(csrf),
                   json={"approval_id": ident})
        assert r.status_code == 200, r.text
        card = [k for k in approvals.inbox(DB)["cards"]
                if k.get("card_id") == f"standing_policy:{body['policy_id']}"][0]
        assert not any(a["action"] in SIGNING for a in card["actions"]), card["actions"]


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
