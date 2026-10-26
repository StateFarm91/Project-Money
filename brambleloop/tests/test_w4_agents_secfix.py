"""W4-AGENTS fixes for the independent review of b5226f7 (M-1, M-2).

M-1: a storefront grant is approved (and the chain rebased) only through the owner's Command
     Center session with CSRF/nonce and a fresh step-up; the operator bearer has no approve
     or rebase route.
M-2: grant rows are signed with a web-only Ed25519 key that is not the approval credential;
     the worker verifies with the public key and cannot mint a grant (not even with the ops
     token); no worker-side module calls approve or rebase.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_agents_secfix.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import ast
import inspect
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
_TMP = tempfile.mkdtemp(prefix="w4_secfix_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "BRAMBLELOOP_STOREFRONT")):
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
from brambleloop.ops import storefront_authority as sfa  # noqa: E402

OPS = "q" * 40
PASS = "owner passphrase for the storefront harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
KEYS = sfa.generate_keypair()
CHANGE = {"operation": "updateShop", "fields": {"announcement": "Welcome to Brambleloop."}}
CONTENT = {"action": sfa.ACTION, "proposal": "p" * 20, "surface": "announcement",
           "change": CHANGE}


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


def _approve_via_cc(c, csrf):
    r = c.post("/api/cc/actions/storefront.preview", json={"proposal": "p" * 20},
               headers=fresh(csrf))
    assert r.status_code == 200, r.text
    digest = r.json()["result"]["digest"]
    return c.post("/api/cc/actions/storefront.approve", headers=fresh(csrf),
                  json={"proposal": "p" * 20, "expected_digest": digest,
                        "reason": "owner reviewed the announcement"})


# ---- M-1 -----------------------------------------------------------------------------------

def test_m1_approve_and_rebase_need_owner_session_csrf_and_fresh_stepup():
    assert approvals.ACTIONS["storefront.approve"][0] is True
    assert approvals.ACTIONS["storefront.rebase"][0] is True
    with patch.object(sfa, "snapshot", return_value=CONTENT), patch.dict(os.environ, KEYS):
        c, csrf = session()
        # no CSRF header: refused by the session gate
        r = c.post("/api/cc/actions/storefront.approve", json={"proposal": "p" * 20})
        assert r.status_code in (401, 403), r.text
        expire_stepup(c)
        r = _approve_via_cc(c, csrf)
        assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
        assert c.post("/api/cc/auth/step-up", json={"passphrase": PASS},
                      headers=fresh(csrf)).status_code == 200
        r = _approve_via_cc(c, csrf)
        assert r.status_code == 200, r.text
        ident = r.json()["result"]["approval_id"]
    with DB.session() as s:
        row = s.get(AuditLog, ident)
        assert row.actor == sfa.PRINCIPAL == "owner:command-center"
        assert row.detail["stepped_up"] is True and "command center" in row.detail["reason"]


def test_m1_the_operator_bearer_has_no_approve_or_rebase_route():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    bearer = {"Authorization": f"Bearer {OPS}"}
    for path in ("/api/owner/storefront/approve", "/api/owner/storefront/rebase"):
        r = c.post(path, headers=bearer,
                   json={"proposal": "p" * 20, "expected_digest": "x", "reason": "r"})
        assert r.status_code in (404, 405), (path, r.status_code, r.text)
    # the deny-only revoke route still exists for the operator (answers, not 404/405)
    r = c.post("/api/owner/storefront/999999/revoke", headers=bearer)
    assert r.status_code not in (404, 405), r.text
    assert "authorization" not in inspect.signature(sfa.approve).parameters
    try:
        sfa.approve(DB, actor="x", proposal="p", expected_digest="d", reason="r",
                    stepped_up=False)
        raise AssertionError("approve without step-up must refuse")
    except ValueError as exc:
        assert "step-up" in str(exc)


def test_m1_the_owner_card_points_at_the_command_center_route():
    src = (ROOT / "src/brambleloop/runtime/storefront_ops.py").read_text()
    assert "/api/owner/storefront/approve" not in src and "storefront.approve" in src


# ---- M-2 -----------------------------------------------------------------------------------

def test_m2_the_worker_verifies_with_the_public_key_and_cannot_sign():
    with patch.object(sfa, "snapshot", return_value=CONTENT), patch.dict(os.environ, KEYS):
        out = sfa.approve(DB, actor="owner", proposal="w" * 20,
                          expected_digest=sfa.digest(CONTENT), reason="r", stepped_up=True)
    worker = {sfa.VERIFY_KEY_VAR: KEYS[sfa.VERIFY_KEY_VAR], sfa.KILL_SWITCH_VAR: "1",
              opsauth.TOKEN_VAR: OPS}
    with patch.dict(os.environ, worker):
        os.environ.pop(sfa.SIGNING_KEY_VAR, None)
        assert sfa.validate(DB, out["approval_id"], change=CHANGE) is None
        assert "exact change" in sfa.validate(DB, out["approval_id"], change={
            "operation": "updateShop", "fields": {"announcement": "other"}})
        with patch.object(sfa, "snapshot", return_value=CONTENT):
            try:
                sfa.approve(DB, actor="worker", proposal="w" * 20,
                            expected_digest=sfa.digest(CONTENT), reason="r", stepped_up=True)
                raise AssertionError("the worker minted a grant")
            except ValueError as exc:
                assert "signing key" in str(exc)
    assert KEYS[sfa.SIGNING_KEY_VAR] != OPS and KEYS[sfa.VERIFY_KEY_VAR] != OPS


def test_m2_a_row_signed_with_another_key_never_verifies():
    other = sfa.generate_keypair()
    # Rows signed with the real key do not verify under another key pair: the chain is
    # refused (fail closed), so a key swapped into the environment can neither mint a new
    # grant nor validate an existing one.
    with patch.object(sfa, "snapshot", return_value=CONTENT), patch.dict(os.environ, other):
        try:
            sfa.approve(DB, actor="owner", proposal="z" * 20,
                        expected_digest=sfa.digest(CONTENT), reason="r", stepped_up=True)
            raise AssertionError("a foreign key appended to the chain")
        except ValueError as exc:
            assert "does not verify" in str(exc), exc
    with DB.session() as s:
        good = s.scalar(select(AuditLog.id).where(AuditLog.action == sfa.APPROVED)
                        .order_by(AuditLog.id.desc()))
    with patch.dict(os.environ, {sfa.VERIFY_KEY_VAR: other[sfa.VERIFY_KEY_VAR],
                                 sfa.KILL_SWITCH_VAR: "1"}):
        why = sfa.validate(DB, good, change=CHANGE)
    assert why and ("signature" in why or "chain" in why or "verify" in why), why


def test_m2_no_worker_side_module_calls_approve_rebase_or_reads_the_signing_key():
    src = ROOT / "src" / "brambleloop"
    bad = []
    for sub in ("runtime", "agents", "laura", "store_foundation", "autonomy", "queue"):
        for p in (src / sub).rglob("*.py"):
            text = p.read_text()
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in (
                        "approve", "rebase", "generate_keypair", "SIGNING_KEY_VAR") and \
                        "storefront_authority" in (ast.get_source_segment(text, node.value)
                                                   or ""):
                    bad.append(f"{p.relative_to(src)}: {node.attr}")
                if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
                        "storefront_authority") and any(
                        a.name in ("approve", "rebase", "generate_keypair", "_seal")
                        for a in node.names):
                    bad.append(f"{p.relative_to(src)}: import {node.names[0].name}")
            if "BRAMBLELOOP_STOREFRONT_SIGNING_KEY" in text:
                bad.append(f"{p.relative_to(src)}: names the signing key")
    assert not bad, bad


# ---- L-2 -----------------------------------------------------------------------------------

def _owner_text_proposal(text="Owner wrote this announcement by hand."):
    from brambleloop.runtime import etsy_ops
    from brambleloop.store_foundation import director, live_state

    shop = {"announcement": text, "digital_sale_message": "x"}
    etsy_ops.store_reading(DB, etsy_ops.SHOP_READING, {"observed_at": time.time(), "shop": shop})
    etsy_ops.store_reading(DB, live_state.SYNC_READING, {"observed_at": time.time(),
                                                         "shop": shop, "sections": []})
    for p in director.build_proposals(DB):
        director.record_proposal(DB, p)
    return next(p for p in director.proposals(DB) if p["surface"] == "announcement")


def test_l2_the_preview_shows_and_binds_the_live_text_it_replaces():
    p = _owner_text_proposal()
    assert p["replaces_live_text"] is True
    snap = sfa.snapshot(DB, p["digest"][:20])
    rep = snap["replaces"]["announcement"]
    assert rep["live_value"] == "Owner wrote this announcement by hand."
    assert rep["state"] == "FRESH" and rep["source"]
    # the digest the owner approves covers the replaced text
    other = dict(snap, replaces={"announcement": {**rep, "live_value": "something else"}})
    assert sfa.digest(other) != sfa.digest(snap)


def test_l2_execution_holds_when_the_live_text_changed_after_approval():
    import types

    from brambleloop.runtime import storefront_ops

    p = _owner_text_proposal("Text the owner had when approving.")
    snap = sfa.snapshot(DB, p["digest"][:20])
    with DB.session() as s:
        # read by id; kept off the signed chain so the other tests' chain stays valid
        row = AuditLog(actor=sfa.PRINCIPAL, action="test.storefront_grant_fixture",
                       artifact=f"storefront:{p['digest'][:20]}",
                       detail={"content": snap})
        s.add(row)
        s.flush()
        gid = row.id
    ctx = types.SimpleNamespace(db=DB)
    assert storefront_ops._replaced_since_approval(ctx, gid, p["change"]) is None
    _owner_text_proposal("The owner edited it again afterwards.")
    why = storefront_ops._replaced_since_approval(ctx, gid, p["change"])
    assert why and "changed since the owner approved" in why


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
