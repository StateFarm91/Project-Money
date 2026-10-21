"""Review F7 (W4-LISTREADY): the owner's KYC/tax and message-inbox readings are the owner's.

`messages` and `legal_and_tax` are owner attestations (identity verification and the tax
position close `legal_and_tax_setup`). They were accepted on the shared operator credential,
so any automation holding it could attest `identity_verified: true`. Now:

* the operator route `POST /api/etsy/shop-observation` refuses those two pages (403
  OWNER_SESSION_REQUIRED) and still serves the other, non-attesting pages exactly as before
  (test_k8_shop_cx covers `shared_access`);
* `POST /api/cc/etsy/shop-observation` takes them behind the owner session and step-up, and
  records the signed-in owner as `recorded_by` -- not a claim in the body;
* a `decided_on` after the reading is refused.

Exercised through the real routes with a real owner session (the experiments harness).
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
_TMP = tempfile.mkdtemp(prefix="w4_owner_obs_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.commerce import shop_observations as SO  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402

OPS = "o" * 40
PASS = "owner passphrase for the observation harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
NOW = datetime.now(timezone.utc)

LEGAL = {"page": "legal_and_tax", "observed_at": (NOW - timedelta(minutes=5)).isoformat(),
         "complete": True, "statement": "read in Shop Manager on my phone",
         "values": {"identity_verified": True, "tax_position": "small supplier",
                    "decided_on": (NOW - timedelta(days=1)).date().isoformat()}}
MESSAGES = {"page": "messages", "observed_at": (NOW - timedelta(minutes=5)).isoformat(),
            "complete": True, "statement": "Settings > Emails",
            "values": {"notifications_inbox": "owner@example.invalid", "reply_window_hours": 24}}


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def post(c, csrf, path, body):
    return c.post(path, json=body, headers={"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
                                            "X-CC-Timestamp": str(int(time.time()))})


def _readings(page):
    with DB.session() as s:
        return [r for r in s.scalars(select(AuditLog).where(
            AuditLog.action == SO.ACTION, AuditLog.artifact == f"etsy_page:{page}"))]


def test_the_operator_credential_cannot_attest_kyc_tax_or_the_inbox():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    delivery = {"page": "delivery_policy", "observed_at": LEGAL["observed_at"],
                "complete": True, "statement": "Policy settings",
                "values": {"editable_delivery_box": False}}
    for body in (LEGAL, MESSAGES, delivery):              # R1: delivery_policy included
        r = c.post("/api/etsy/shop-observation", json=body,
                   headers={"authorization": f"Bearer {OPS}"})
        assert r.status_code == 403 and r.json()["code"] == "OWNER_SESSION_REQUIRED", r.text
        assert _readings(body["page"]) == []
    # a non-attesting page keeps its operator path (the existing flow)
    other = {"page": "shared_access", "observed_at": LEGAL["observed_at"], "complete": True,
             "values": {"people": []}, "statement": "empty"}
    assert c.post("/api/etsy/shop-observation", json=other,
                  headers={"authorization": f"Bearer {OPS}"}).status_code == 200


def test_the_owner_route_needs_step_up_and_records_the_signed_in_owner():
    c, csrf = session()
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))
    r = post(c, csrf, "/api/cc/etsy/shop-observation", LEGAL)
    assert r.status_code == 403 and r.json().get("code") == "STEP_UP_REQUIRED", r.text
    assert _readings("legal_and_tax") == []
    assert post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS}).status_code == 200
    r = post(c, csrf, "/api/cc/etsy/shop-observation", {**LEGAL, "recorded_by": "someone"})
    assert r.status_code == 200, r.text
    rows = _readings("legal_and_tax")
    assert len(rows) == 1 and rows[0].actor.startswith("owner:cc:"), rows[0].actor
    r = post(c, csrf, "/api/cc/etsy/shop-observation", MESSAGES)
    assert r.status_code == 200, r.text
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.post("/api/cc/etsy/shop-observation", json=LEGAL).status_code in (401, 403)


def test_a_decision_dated_after_its_reading_is_refused():
    future = dict(LEGAL["values"], decided_on=(NOW + timedelta(days=3)).date().isoformat())
    try:
        SO.record(DB, page="legal_and_tax", observed_at=LEGAL["observed_at"], complete=True,
                  values=future, statement="x", recorded_by="owner:test")
        raise AssertionError("a future decided_on was accepted")
    except SO.ObservationRefused as exc:
        assert "future" in str(exc)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
