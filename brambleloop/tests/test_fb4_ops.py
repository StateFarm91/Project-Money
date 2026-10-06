"""Final Build FB-4 OPS: owner-queue truth, claim/measurement disagreements, first response.

F-541  the Etsy re-authorisation raised by order ingest is the SAME owner action and incident
       the publish path raises, and `launch.readiness` never closes it while the condition
       holds; an authenticated read that works closes it.
F-160  the credential register's rotation cards reach the readiness owner queue and the
       dashboard's approval inbox.
F-125  a COMPLETE/INTEGRATED claim the measurement contradicts opens an incident, resolved
       when they agree again; the cadence exists.
F-043  a recorded buyer message unanswered at 24h / 36h raises an owner action + incident
       (escalated at 36h) and a recorded reply closes both; owner intake route is authenticated.
F-874  the KYC/tax step is not queued on a shadow shop's daily readiness run; it is queued at
       the step before first sale (a listing on Etsy).

No network, no model call, no secret. Run: cd brambleloop && PYTHONPATH=src $PY tests/test_fb4_ops.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="fb4ops_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP}/app.db"
for _k in list(os.environ):
    if _k.startswith(("ETSY", "BRAMBLELOOP_PUBLISH_AUTHORISED", "BRAMBLELOOP_SECRET_KEY",
                      "BRAMBLELOOP_OPS_TOKEN")):
        os.environ.pop(_k)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import DEFAULT_AGENTS, Registry  # noqa: E402
from brambleloop.commerce import orders_ingest  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, Incident, Job, JobStatus, Listing,  # noqa: E402
                                     OAuthCredential, OwnerAction, Phase, SupportCase)
from brambleloop.integrations.etsy_oauth import EtsyAuthNeedsOwner  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import etsy_ops, pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, Worker, handlers  # noqa: E402

NOW = datetime.now(timezone.utc)
_N = [0]


def _db() -> Database:
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/fb4_{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, job_type: str, inputs: dict | None = None, *, agent: str = "orchestrator") -> Job:
    job = JobQueue(db).enqueue(agent, job_type, inputs or {},
                               idempotency_key=f"run:{job_type}:{time.time_ns()}")
    assert Worker(db, f"w-{job_type}", phase=Phase.SHADOW, job_types=[job_type]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _owner(db, key: str) -> list[OwnerAction]:
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == key)))
        for r in rows:
            s.expunge(r)
        return rows


def _open_incidents(db, prefix: str = "") -> list[Incident]:
    with db.session() as s:
        rows = [i for i in s.scalars(select(Incident).where(Incident.resolved == False))  # noqa: E712
                if i.signature.startswith(prefix)]
        for r in rows:
            s.expunge(r)
        return rows


def _open_gate(db):
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", detail={"ok": True}))
        s.add(OAuthCredential(provider="etsy", refresh_token_sealed="sealed",
                              token_fingerprint="abcd1234",
                              scopes="listings_r listings_w shops_r transactions_r"))


class _Revoked:
    calls = 0

    def receipts(self, *, since):
        raise EtsyAuthNeedsOwner("Etsy refused the refresh grant with 400: invalid_grant")


class _Feed:
    calls = 0

    def receipts(self, *, since):
        return []


# ---- F-541 -----------------------------------------------------------------------------


def test_orders_and_publish_share_one_reauthorisation_key_and_incident():
    assert orders_ingest.AUTH_ACTION_KEY == etsy_ops.AUTH_KEY
    assert orders_ingest.AUTH_INCIDENT_SIGNATURE == etsy_ops.AUTH_INCIDENT
    db = _db()
    _open_gate(db)
    got = orders_ingest.ingest(db, reader=_Revoked(), now=NOW)
    assert got["auth_failure"]["owner_action"] == "queued"
    assert got["auth_failure"]["severity"] == "P1"
    etsy_ops.record_auth_needs_owner(db, "invalid_grant", where="store.publish")
    assert len(_owner(db, etsy_ops.AUTH_KEY)) == 1, "two rows for one browser step"
    incidents = _open_incidents(db, etsy_ops.AUTH_INCIDENT)
    assert len(incidents) == 1 and incidents[0].severity == "P1"
    assert incidents[0].detail["owner_action"] == etsy_ops.AUTH_KEY
    assert not _owner(db, orders_ingest.LEGACY_AUTH_ACTION_KEY)


def test_orders_auth_failure_survives_launch_readiness_and_closes_when_cleared():
    db = _db()
    _open_gate(db)
    orders_ingest.ingest(db, reader=_Revoked(), now=NOW)
    job = _run(db, "launch.readiness")
    assert job.status is JobStatus.DONE, job.last_error
    rows = _owner(db, etsy_ops.AUTH_KEY)
    assert len(rows) == 1 and not rows[0].done, "launch.readiness closed the re-authorisation"
    assert etsy_ops.AUTH_KEY not in (job.outputs or {}).get("owner_actions_closed", [])
    # The condition clears: an authenticated receipts read works.
    got = orders_ingest.ingest(db, reader=_Feed(), now=NOW + timedelta(hours=1))
    assert got["ran"] is True and got["auth_cleared"]["owner_actions_closed"] == 1
    assert _owner(db, etsy_ops.AUTH_KEY)[0].done
    assert not _open_incidents(db, etsy_ops.AUTH_INCIDENT)


def test_a_legacy_orders_row_is_held_open_by_its_incident_and_adopted_on_the_next_failure():
    db = _db()
    _open_gate(db)
    with db.session() as s:
        s.add(OwnerAction(requirement_key=orders_ingest.LEGACY_AUTH_ACTION_KEY,
                          action="Re-authorise (legacy row)", reason="old"))
        s.add(Incident(signature=orders_ingest.LEGACY_AUTH_INCIDENT_SIGNATURE, severity="P2",
                       summary="legacy", detail={
                           "owner_action": orders_ingest.LEGACY_AUTH_ACTION_KEY}))
    _run(db, "launch.readiness")
    assert not _owner(db, orders_ingest.LEGACY_AUTH_ACTION_KEY)[0].done
    orders_ingest.ingest(db, reader=_Revoked(), now=NOW)
    assert not _owner(db, orders_ingest.LEGACY_AUTH_ACTION_KEY), "legacy row not adopted"
    assert len(_owner(db, etsy_ops.AUTH_KEY)) == 1
    assert not _open_incidents(db, orders_ingest.LEGACY_AUTH_INCIDENT_SIGNATURE)


def test_readiness_never_closes_an_action_an_open_incident_names():
    db = _db()
    with db.session() as s:
        s.add(OwnerAction(requirement_key="some_other_subsystem_question",
                          action="Answer the question", reason="raised elsewhere"))
        s.add(Incident(signature="elsewhere:condition", severity="P2", summary="holds",
                       detail={"owner_action": "some_other_subsystem_question"}))
        # A3-03: the closer closes only keys it owns whose condition re-check passes.
        # `physical_calibration` is readiness-owned and its ask is withdrawn: it must close.
        s.add(OwnerAction(requirement_key="physical_calibration",
                          action="Satisfied thing", reason="was needed"))
        # A key nobody here owns is not "satisfied" just because it is not asked for.
        s.add(OwnerAction(requirement_key="nobody_raises_this_any_more",
                          action="Unowned thing", reason="was needed"))
    _run(db, "launch.readiness")
    assert not _owner(db, "some_other_subsystem_question")[0].done
    assert _owner(db, "physical_calibration")[0].done, "the closer stopped closing"
    assert not _owner(db, "nobody_raises_this_any_more")[0].done, \
        "the closer closed an action it does not own (A3-03)"


# ---- F-160 -----------------------------------------------------------------------------


def test_the_credential_rotation_card_reaches_the_owner_queue_and_the_dashboard():
    from brambleloop.build2 import executor
    from brambleloop.ops import credential_register

    pending = credential_register.owner_requests()
    assert pending, "the register has an unrotated credential"
    db = _db()
    job = _run(db, "launch.readiness")
    assert job.status is JobStatus.DONE, job.last_error
    for req in pending:
        rows = _owner(db, req.key)
        assert len(rows) == 1 and not rows[0].done and "Rotate" in rows[0].action
        assert "sk-" not in rows[0].action + rows[0].reason
    _run(db, "launch.readiness")
    assert all(len(_owner(db, r.key)) == 1 for r in pending), "the card duplicated"
    inbox = executor.approval_inbox(db, env={})
    keys = {c["requirement_key"] for c in inbox["cards"]}
    assert {r.key for r in pending} <= keys, "the rotation card is not on the dashboard"


# ---- F-125 -----------------------------------------------------------------------------


def test_a_claim_the_measurement_contradicts_opens_an_incident_until_they_agree():
    from brambleloop.build2 import closure, maturity

    db = _db()
    closure_rows = [{"id": 1, "state": closure.COMPLETE_PROVEN}]
    matrix = [{"uid": "F-900", "maturity": "INTEGRATED",
               "producer": "src/brambleloop/ops/never_wired.py::thing"},
              {"uid": "F-901", "maturity": "TESTED",
               "producer": "src/brambleloop/ops/never_wired.py::thing"},
              {"uid": "F-902", "maturity": "DEPLOYED",
               "producer": "src/brambleloop/runtime/release.py::handle_launch_readiness"}]

    def reached(module):
        return {"reached": module != "ops/never_wired.py", "why": "not imported by any root"}

    found = maturity.disagreements(db, closure_rows=closure_rows, matrix_rows=matrix,
                                   reached=reached)
    keys = {d["key"]: d for d in found["disagreements"]}
    assert "F-900" in keys and keys["F-900"]["measurement"] == "not reached"
    assert "F-901" not in keys, "a TESTED row claims nothing about running"
    assert "F-902" not in keys
    req = next(r for r in maturity.reg.load() if r.id == 1)
    if maturity.ladder(db, req)["rungs"][maturity.EXERCISED]["verdict"] == maturity.NO:
        assert keys["build2#1"]["measurement"] == "never ran"
    rec = maturity.record_disagreements(db, found)
    assert f"{maturity.DISAGREEMENT_PREFIX}F-900" in rec["opened"]
    again = maturity.record_disagreements(db, found)
    assert not again["opened"], "restated, not duplicated"
    assert len(_open_incidents(db, f"{maturity.DISAGREEMENT_PREFIX}F-900")) == 1
    cleared = maturity.disagreements(db, closure_rows=[], matrix_rows=matrix,
                                     reached=lambda m: {"reached": True, "why": "live"})
    out = maturity.record_disagreements(db, cleared)
    assert f"{maturity.DISAGREEMENT_PREFIX}F-900" in out["resolved"]
    assert not _open_incidents(db, maturity.DISAGREEMENT_PREFIX)


def test_with_no_job_rows_never_ran_is_a_blind_spot_not_a_disagreement():
    from brambleloop.build2 import maturity

    found = maturity.disagreements(None, matrix_rows=[], reached=lambda m: {"reached": True})
    assert not any(d["measurement"] == "never ran" for d in found["disagreements"])


def test_the_disagreement_check_runs_on_a_cadence_the_orchestrator_may_run():
    assert "ops.maturity_disagreements" in handlers.known()
    assert any(c[2] == "ops.maturity_disagreements" for c in CADENCES)
    orchestrator = next(a for a in DEFAULT_AGENTS if a["name"] == "orchestrator")
    assert "ops.maturity_disagreements" in orchestrator["allowed_job_types"]


# ---- F-043 -----------------------------------------------------------------------------


def test_a_buyer_message_unanswered_for_30_hours_is_an_owner_action_and_an_incident():
    from brambleloop.support import response_watch as rw

    db = _db()
    got = rw.record_buyer_message(db, customer_ref="buyer-1", message="Where is my PDF?",
                                  received_at=(NOW - timedelta(hours=30)).isoformat())
    cid = got["case_id"]
    assert 29.9 < got["hours_waiting"] < 30.1
    job = _run(db, "support.triage", agent="support")
    assert job.status is JobStatus.DONE, job.last_error
    assert cid in job.outputs["response_watch"]["raised"]
    rows = _owner(db, rw.key_for(cid))
    assert len(rows) == 1 and not rows[0].done and "48h" in rows[0].action
    inc = _open_incidents(db, f"{rw.SIGNATURE_PREFIX}case:{cid}")
    assert len(inc) == 1 and inc[0].severity == "P2"
    with db.session() as s:
        assert s.scalar(select(AuditLog).where(AuditLog.action == "support.response_watch"))
    # launch.readiness does not tidy it away
    _run(db, "launch.readiness")
    assert not _owner(db, rw.key_for(cid))[0].done
    # 37h: escalated, still one action
    out = rw.watch(db, now=NOW + timedelta(hours=7))
    assert cid in out["escalated"]
    assert _open_incidents(db, f"{rw.SIGNATURE_PREFIX}case:{cid}")[0].severity == "P1"
    assert len(_owner(db, rw.key_for(cid))) == 1
    # the reply is recorded: both close
    rw.record_reply_sent(db, cid)
    out = rw.watch(db)
    assert cid in out["closed"]
    assert _owner(db, rw.key_for(cid))[0].done
    assert not _open_incidents(db, f"{rw.SIGNATURE_PREFIX}case:{cid}")


def test_a_fresh_message_raises_nothing_and_a_late_reply_is_refused_as_impossible():
    from brambleloop.support import response_watch as rw

    db = _db()
    cid = rw.record_buyer_message(db, customer_ref="b", message="hi",
                                  received_at=(NOW - timedelta(hours=2)).isoformat())["case_id"]
    out = rw.watch(db)
    assert cid in out["watching"] and not out["raised"]
    try:
        rw.record_reply_sent(db, cid, sent_at=(NOW - timedelta(hours=3)).isoformat())
    except rw.MessageRefused:
        pass
    else:
        raise AssertionError("a reply before the message was accepted")
    try:
        rw.record_buyer_message(db, customer_ref="b", message="x",
                                received_at=(NOW + timedelta(hours=3)).isoformat())
    except rw.MessageRefused:
        pass
    else:
        raise AssertionError("a message from the future was accepted")
    # 49h: breached
    out = rw.watch(db, now=NOW + timedelta(hours=47))
    assert cid in out["breached"] and "breached" in _owner(db, rw.key_for(cid))[0].action


def test_the_owner_intake_route_requires_the_operator_credential():
    from fastapi.testclient import TestClient

    from brambleloop.app import main

    main.db.create_all()
    client = TestClient(main.app)
    r = client.post("/api/support/messages", json={"event": "buyer_message",
                                                   "customer_ref": "b", "message": "hi"})
    assert r.status_code in (401, 503), r.status_code
    with main.db.session() as s:
        assert s.scalar(select(SupportCase).where(SupportCase.customer_ref == "b")) is None
    token = "t" * 32  # a test-only operator token, set and removed here
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = token
    try:
        auth = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/support/messages", headers=auth, json={
            "event": "buyer_message", "customer_ref": "b", "message": "Where is my PDF?",
            "received_at": (NOW - timedelta(hours=25)).isoformat()})
        assert r.status_code == 200 and r.json()["recorded"], r.text
        cid = r.json()["case_id"]
        assert r.json()["hours_waiting"] >= 25
        r = client.post("/api/support/messages", headers=auth,
                        json={"event": "reply_sent", "case_id": cid})
        assert r.status_code == 200, r.text
        r = client.post("/api/support/messages", headers=auth,
                        json={"event": "reply_sent", "case_id": cid})
        assert r.status_code == 400, "a second first response was accepted"
        r = client.post("/api/support/messages", headers=auth, json={"event": "nonsense"})
        assert r.status_code == 400
    finally:
        os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)


# ---- F-874 -----------------------------------------------------------------------------


def test_a_shadow_shop_is_not_asked_for_kyc_until_the_step_before_first_sale():
    db = _db()
    job = _run(db, "launch.readiness")
    assert job.status is JobStatus.DONE, job.last_error
    legal = f"{etsy_ops.SURFACE_PREFIX}legal_and_tax_setup"
    assert not _owner(db, legal), "KYC/tax queued on a shadow shop's daily run"
    assert not _owner(db, f"{etsy_ops.SURFACE_PREFIX}payment_settings_setup")
    assert _owner(db, f"{etsy_ops.SURFACE_PREFIX}etsy_ads_off"), "the rest still seeds"
    _run(db, "launch.readiness")
    assert not _owner(db, legal)
    with db.session() as s:
        s.add(Listing(product_slug="p", version="1.0.0", title="t", description="d",
                      etsy_listing_id="123"))
    _run(db, "launch.readiness")
    rows = _owner(db, legal)
    assert len(rows) == 1 and not rows[0].done and rows[0].blocks == "first sale"


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
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
