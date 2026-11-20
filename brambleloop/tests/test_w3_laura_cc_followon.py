"""W3 lane F: Laura creates authorised follow-on work; protected work is gated.

* a GREEN proposal becomes an internal mission through the COO orchestrator's enqueue
  boundary -- only with explicit confirmation, idempotently, audited as Laura's, visible in
  company memory and the timeline;
* a protected proposal (store.publish) needs a fresh owner step-up, becomes an owner action
  and never a job;
* a proposal Laura did not store, or a stored one tampered to name a job type outside the
  GREEN allowlist, is refused by the authority boundary;
* a department the owner blocked is not routed around.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_cc_followon.py
"""
from __future__ import annotations

import w3_laura_cc_harness as H  # noqa: E402

from sqlalchemy import select  # noqa: E402

from brambleloop.autonomy import memory  # noqa: E402
from brambleloop.core.models import AuditLog, Job, OwnerAction  # noqa: E402
from brambleloop.laura.agency.models import LauraTurn  # noqa: E402

DB = H.DB
H.seed_company()


def _ask(c, csrf, q):
    r = H.post(c, csrf, "/api/cc/laura/ask", {"question": q})
    assert r.status_code == 200, r.text
    return r.json()


def _jobs(job_type):
    with DB.session() as s:
        return list(s.scalars(select(Job).where(Job.job_type == job_type)))


def test_green_follow_on_becomes_an_orchestrator_mission():
    c, csrf = H.session()
    t = _ask(c, csrf, "What did your company do overnight?")
    prop = next(p for p in t["proposals"] if p["job_type"] == "autonomy.morning_handoff")
    assert prop["kind"] == "mission" and not prop["requires_step_up"], prop
    body = {"turn_id": t["turn_id"], "proposal_key": prop["key"]}
    before = len(_jobs("autonomy.morning_handoff"))
    # No explicit confirmation -> refused, nothing created.
    r = H.post(c, csrf, "/api/cc/laura/follow-on", body)
    assert r.status_code == 400 and r.json()["code"] == "CONFIRMATION_REQUIRED", r.text
    assert len(_jobs("autonomy.morning_handoff")) == before
    r = H.post(c, csrf, "/api/cc/laura/follow-on", {**body, "confirm": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "mission" and out["created"] and out["result_ref"].startswith("jobs:")
    job_id = int(out["result_ref"].split(":")[1])
    with DB.session() as s:
        job = s.get(Job, job_id)
        assert job.job_type == "autonomy.morning_handoff" and job.agent == "coo", job.agent
        assert job.inputs["requested_by"] == "laura" and job.inputs["source"] == "autonomy"
        assert job.inputs["laura_turn"] == t["turn_id"]
        audit = s.scalar(select(AuditLog).where(AuditLog.action == "laura.followon.mission",
                                                AuditLog.artifact == out["result_ref"]))
        assert audit is not None and audit.actor == "laura"
        assert audit.detail["confirmed_by"].startswith("owner:cc:")
    missions = memory.recall(DB, kind="mission", department="executive")
    assert any(m["body"].get("job_id") == job_id for m in missions), missions
    assert any(e["kind"] == "laura.followon" for e in memory.events(DB, limit=20))
    # Idempotent: confirming the same proposal again creates nothing new.
    r = H.post(c, csrf, "/api/cc/laura/follow-on", {**body, "confirm": True})
    assert r.status_code == 200 and r.json()["created"] is False, r.text
    assert len(_jobs("autonomy.morning_handoff")) == before + 1


def test_protected_follow_on_needs_step_up_and_never_becomes_a_job():
    c, csrf = H.session()
    t = _ask(c, csrf, "What should we launch next?")
    prop = next(p for p in t["proposals"] if p["job_type"] == "store.publish")
    assert prop["kind"] == "owner_action" and prop["requires_step_up"], prop
    body = {"turn_id": t["turn_id"], "proposal_key": prop["key"], "confirm": True}
    H.expire_stepup(c)
    r = H.post(c, csrf, "/api/cc/laura/follow-on", body)
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    with DB.session() as s:
        assert s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "laura:store.publish:harbour-shawl")) is None
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    r = H.post(c, csrf, "/api/cc/laura/follow-on", body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "owner_action", out
    with DB.session() as s:
        oa = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "laura:store.publish:harbour-shawl"))
        assert oa is not None and not oa.done and "Laura asks for your decision" in oa.action
    assert _jobs("store.publish") == []          # Laura never enqueues a protected job
    # It is now in the owner's Approvals inbox, where the act needs its own grant.
    cards = c.get("/api/cc/approvals").json()["cards"]
    assert any("Laura asks for your decision" in (x.get("title") or "") for x in cards), cards


def test_unknown_or_tampered_proposals_are_refused():
    c, csrf = H.session()
    t = _ask(c, csrf, "What did you learn?")
    r = H.post(c, csrf, "/api/cc/laura/follow-on",
               {"turn_id": t["turn_id"], "proposal_key": "mission:platform:shell.exec",
                "confirm": True})
    assert r.status_code == 404, r.text
    r = H.post(c, csrf, "/api/cc/laura/follow-on",
               {"turn_id": 999999, "proposal_key": "x", "confirm": True})
    assert r.status_code == 404, r.text
    # A stored proposal tampered in the database to name a non-GREEN job type is re-checked
    # at creation time and refused by the authority boundary.
    with DB.session() as s:
        row = s.get(LauraTurn, t["turn_id"])
        props = [dict(p) for p in row.proposals]
        assert props
        props[0] = {**props[0], "job_type": "etsy.listing_write", "key": "mission:learn:evil"}
        row.proposals = props
    r = H.post(c, csrf, "/api/cc/laura/follow-on",
               {"turn_id": t["turn_id"], "proposal_key": "mission:learn:evil", "confirm": True})
    assert r.status_code == 409 and r.json()["code"] == "REFUSED_BY_AUTHORITY", r.text
    assert _jobs("etsy.listing_write") == []


def test_blocked_department_is_not_routed_around():
    c, csrf = H.session()
    t = _ask(c, csrf, "How does your store look?")
    prop = next(p for p in t["proposals"] if p["department"] == "store_commerce"
                and p["kind"] == "mission")
    memory.block_department(DB, "store_commerce", reason="owner is redesigning the shop")
    try:
        r = H.post(c, csrf, "/api/cc/laura/follow-on",
                   {"turn_id": t["turn_id"], "proposal_key": prop["key"], "confirm": True})
        assert r.status_code == 409, r.text
        assert "blocked" in r.json()["error"], r.text
    finally:
        memory.unblock_department(DB, "store_commerce")


if __name__ == "__main__":
    H.run(globals())
