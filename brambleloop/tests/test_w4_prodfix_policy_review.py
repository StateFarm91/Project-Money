"""W4-PRODFIX: the owner's Command Center door for a platform-policy change review.

`platform_policy.unreviewed_changes` blocks publishing and the marketing rebuild until a
material policy change is reviewed and re-tested; `review_change` had no caller. The door is
`/api/cc/actions/policy.review` (owner session + CSRF + nonce, step-up), after
`policy.review_preview` shows the change. No bearer path, no public route.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_prodfix_policy_review.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
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

_TMP = tempfile.mkdtemp(prefix="prodfix_policy_")
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

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import approvals, auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog, PolicySnapshot  # noqa: E402
from brambleloop.gates import platform_policy  # noqa: E402
from brambleloop.publish import release_gates  # noqa: E402

OPS = "p" * 40
PASS = "owner passphrase for the policy review harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
SOURCE = "listing_image_rules"
TESTED = "re-ran the listing image gate on hexie-coaster-set frames against the new rules"


def _seed_change():
    with DB.session() as s:
        for r in s.scalars(select(PolicySnapshot)):
            s.delete(r)
        s.add(PolicySnapshot(source=SOURCE, version="2026-10-01:page", checked_on="2026-10-01",
                             digest="a" * 64, summary="old: 5 images minimum",
                             material_change=False, affects=["creative_assets", "publishing"]))
        s.add(PolicySnapshot(source=SOURCE, version="2026-10-22:page", checked_on="2026-10-23",
                             digest="b" * 64, summary="new: alt text required on every image",
                             material_change=True, affects=["creative_assets", "publishing"]))


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def post(c, csrf, action, body):
    return c.post(f"/api/cc/actions/{action}", json=body, headers=fresh(csrf))


def expire_stepup(c):
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))


def _preview(c, csrf):
    r = post(c, csrf, "policy.review_preview", {"source": SOURCE})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def _body(shown, **over):
    return {"source": SOURCE, "confirm": "reviewed and tested", "tested": TESTED,
            "expected_digest": shown["review_digest"], **over}


def test_refused_without_a_session_and_with_only_the_operator_bearer():
    _seed_change()
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    for headers in ({}, {"Authorization": f"Bearer {OPS}"}):
        r = c.post("/api/cc/actions/policy.review",
                   json={"source": SOURCE, "confirm": "reviewed and tested", "tested": TESTED},
                   headers=headers)
        assert r.status_code in (401, 403), (headers, r.status_code, r.text)
    assert platform_policy.unreviewed_changes(DB), "nothing may have been recorded"


def test_refused_without_step_up():
    _seed_change()
    c, csrf = session()
    shown = _preview(c, csrf)                              # the preview needs no step-up
    assert shown["changed"]["summary"].startswith("new:")
    assert shown["before"]["summary"].startswith("old:")
    expire_stepup(c)
    r = post(c, csrf, "policy.review", _body(shown))
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    assert platform_policy.unreviewed_changes(DB)


def test_the_review_clears_the_policy_block_and_records_exactly_what_was_confirmed():
    _seed_change()
    stale = release_gates.staleness(DB, slug="hexie-coaster-set")
    assert stale["policy_changes_unreviewed"] == [SOURCE]
    c, csrf = session()
    shown = _preview(c, csrf)
    for bad in (_body(shown, confirm="ok"), _body(shown, confirm="REVIEWED AND TESTED"),
                _body(shown, tested=""),
                _body(shown, expected_digest="0" * 64)):
        r = post(c, csrf, "policy.review", bad)
        assert r.status_code == 409 and r.json()["code"] == "REFUSED_BY_AUTHORITY", r.text
    assert platform_policy.unreviewed_changes(DB)
    r = post(c, csrf, "policy.review", _body(shown))
    assert r.status_code == 200, r.text
    assert platform_policy.unreviewed_changes(DB) == []
    after = release_gates.staleness(DB, slug="hexie-coaster-set")
    assert after["policy_changes_unreviewed"] == []
    assert not any("platform policy changed" in x for x in after["reasons"])
    with DB.session() as s:
        snap = s.scalar(select(PolicySnapshot).where(PolicySnapshot.material_change.is_(True)))
        assert snap.detail["reviewed_by"] == "owner:command-center"
        assert snap.detail["tested"] == TESTED
        rec = s.scalar(select(AuditLog).where(AuditLog.action == "policy.change_reviewed"))
        assert rec is not None
        assert rec.detail["confirmed"] == "reviewed and tested"
        assert rec.detail["tested"] == TESTED
        assert rec.detail["shown"]["changed"]["summary"] == "new: alt text required on every image"
        assert rec.detail["review_digest"] == shown["review_digest"]
        assert s.scalar(select(AuditLog).where(
            AuditLog.action == "cc.owner_action.policy.review")) is not None
    r = post(c, csrf, "policy.review", _body(shown))       # nothing left to review
    assert r.status_code == 404, r.text


def test_the_action_is_owner_only_step_up_and_shows_in_the_inbox():
    assert approvals.ACTIONS["policy.review"][0] is True
    assert approvals.ACTIONS["policy.review_preview"][0] is False
    _seed_change()
    cards = [c for c in approvals.inbox(DB)["cards"] if c.get("kind") == "policy_review"]
    assert [c["card_id"] for c in cards] == [f"policy:{SOURCE}"]
    paths = {r.path for r in main.app.routes if "policy" in getattr(r, "path", "")}
    assert not any(p.startswith("/api/") and not p.startswith("/api/cc/") and "review" in p
                   for p in paths), paths


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
