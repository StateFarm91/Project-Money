"""PHYSFIX (SECREVIEW 8da830d R28 follow-up): the owner lift of a size halt, end to end.

Through the real Command Center route `POST /api/cc/actions/physical_size.lift`, on the app's
own database, with a real size halt and a real corrected re-release made in full by an
independent tester:

- refused without an owner session (and the ops token is not a way in);
- refused with an owner session but no fresh step-up;
- refused with a session and step-up but no reason;
- accepted with all three plus qualifying evidence -- the halt is lifted, the failed release
  is withheld, and the action is audited.

Pattern: `test_w4_launchfix.test_cc_policy_form_needs_a_session_csrf_and_step_up`.
Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_physfix_size_lift_http.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

_TMP = tempfile.mkdtemp(prefix="physfix_lift_http_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'lift.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the PHYSFIX lift harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog, Incident  # noqa: E402
from brambleloop.gates.incidents import IncidentTracker  # noqa: E402
from brambleloop.publish import withholding  # noqa: E402

PASS = "owner passphrase for the physfix lift harness"
OPS = "P" * 40
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()

import test_physfix as T  # noqa: E402  (after the app's database is configured)

URL = "/api/cc/actions/physical_size.lift"


def _session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def _fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def test_the_size_halt_lift_needs_a_session_step_up_reason_and_evidence():
    from brambleloop.app.command_center.models import OwnerSession

    T._agree_testers(main.db)
    cir, fixed, inc_id, good_row = T.halted_and_corrected(main.db)
    tracker = IncidentTracker(main.db)
    body = {"incident_id": inc_id, "physical_test_id": good_row,
            "reason": "1.3.1 re-made by an independent tester at the stated size"}

    # 1. No owner session -- and the operator token is not one.
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.post(URL, json=body).status_code == 401
    assert anon.post(URL, json=body,
                     headers={"Authorization": f"Bearer {OPS}"}).status_code == 401
    assert tracker.publication_halted(cir.slug)

    # 2. An owner session whose step-up is not fresh.
    c, csrf = _session()
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with main.db.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))
    r = c.post(URL, json=body, headers=_fresh(csrf))
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    assert tracker.publication_halted(cir.slug)

    # 3. A session with a fresh step-up, but no reason.
    c, csrf = _session()
    r = c.post(URL, json={k: v for k, v in body.items() if k != "reason"},
               headers=_fresh(csrf))
    assert r.status_code == 409 and r.json()["code"] == "REFUSED_BY_AUTHORITY", r.text
    assert "reason" in r.text, r.text
    assert tracker.publication_halted(cir.slug)
    # ...nor with all three on evidence that does not qualify (the halted release's own
    # failing make).
    with main.db.session() as s:
        failing = s.get(Incident, inc_id).detail["physical_test_id"]
    r = c.post(URL, json=dict(body, physical_test_id=failing), headers=_fresh(csrf))
    assert r.status_code == 409 and "does not qualify" in r.text, r.text
    assert tracker.publication_halted(cir.slug)

    # 4. Session, fresh step-up, reason and qualifying evidence: lifted, withheld, audited.
    r = c.post(URL, json=body, headers=_fresh(csrf))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["result"]["lifted"] is True and out["audit_id"], out
    assert out["result"]["withheld"] == [f"{cir.slug}@{cir.version}"], out
    assert not tracker.publication_halted(cir.slug)
    with main.db.session() as s:
        assert s.get(Incident, inc_id).resolved
        audit = s.get(AuditLog, out["audit_id"])
        assert audit.action == "cc.owner_action.physical_size.lift", audit.action
        assert audit.actor.startswith("owner:cc:"), audit.actor
    assert withholding.reasons(main.db, cir.slug, cir.version)["reasons"].get(
        withholding.PHYSICAL_SIZE_FAILED), "the failed release was not withheld"
    print("OK   test_the_size_halt_lift_needs_a_session_step_up_reason_and_evidence")


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            fails += 1
            print("FAIL", name, repr(exc)[:300])
    print(f"{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
