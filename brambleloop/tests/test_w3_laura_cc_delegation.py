"""W3 lane F: authorised delegation from a conversation (D-FB-16 item 7).

"I don't like that banner. Have Design make three more." must become a confirmed, audited,
non-protected department job carrying a brief -- and nothing before the owner confirms.
Protected requests route to the owner (step-up, owner action, never a job); spending money and
changing Laura's identity or the owner's canonical logo/banner are refused outright.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_cc_delegation.py
"""
from __future__ import annotations

import w3_laura_cc_harness as H  # noqa: E402

from sqlalchemy import select  # noqa: E402

from brambleloop.autonomy import memory  # noqa: E402
from brambleloop.core.models import AuditLog, Job, OwnerAction  # noqa: E402
from brambleloop.laura.agency import delegation, talk  # noqa: E402
from brambleloop.laura.agency.models import LauraFollowOn  # noqa: E402

DB = H.DB
BANNER = "I don't like that banner. Have Design make three more."


def _ask(c, csrf, q):
    r = H.post(c, csrf, "/api/cc/laura/ask", {"question": q})
    assert r.status_code == 200, r.text
    return r.json()


def _jobs():
    with DB.session() as s:
        return [(j.id, j.job_type, j.inputs) for j in s.scalars(select(Job))]


def test_parser_reads_department_task_count_and_antecedent():
    d = delegation.parse(BANNER)
    assert d == {"spoken_department": "design", "department": "product_design",
                 "task": "make three more banners", "count": 3}, d
    assert delegation.parse("Laura, ask the visual team to try 2 new hero crops")["count"] == 2
    assert delegation.parse("What did your company do overnight?") is None
    assert talk.classify(BANNER) == "delegate"
    assert talk.classify("How does the store look?") == "store"   # unchanged routing


def test_banner_delegation_needs_confirmation_then_becomes_an_audited_department_job():
    c, csrf = H.session()
    t = _ask(c, csrf, BANNER)
    assert t["intent"] == "delegate" and t["status"] == "ANSWERED", t
    assert "Product & Design" in t["answer"] and "three more banners" in t["answer"], t["answer"]
    assert "paid generation" in t["answer"] and "spend authority" in t["answer"], t["answer"]
    props = t["proposals"]
    assert len(props) == 1, props
    p = props[0]
    assert p["kind"] == "mission" and p["delegation"] and not p["requires_step_up"], p
    assert p["department"] == "product_design" and p["job_type"] == "autonomy.department_review"
    assert p["brief"]["count"] == 3 and p["brief"]["gated"], p["brief"]
    assert any("D-FB-17" in x for x in p["brief"]["constraints"]), p["brief"]
    assert any(f["source"] == "DECISION_LOG D-FB-17" for f in t["facts"]), t["facts"]
    before = _jobs()
    # Nothing happens until the owner confirms.
    body = {"turn_id": t["turn_id"], "proposal_key": p["key"]}
    r = H.post(c, csrf, "/api/cc/laura/follow-on", body)
    assert r.status_code == 400 and r.json()["code"] == "CONFIRMATION_REQUIRED", r.text
    assert _jobs() == before
    r = H.post(c, csrf, "/api/cc/laura/follow-on", {**body, "confirm": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["kind"] == "mission" and out["created"] and out["delegation"], out
    job_id = int(out["result_ref"].split(":")[1])
    with DB.session() as s:
        job = s.get(Job, job_id)
        assert job.job_type == "autonomy.department_review", job.job_type
        assert job.inputs["department"] == "product_design"
        assert job.inputs["requested_by"] == "laura"
        assert job.inputs["brief"]["task"] == "make three more banners"
        assert job.inputs["brief"]["count"] == 3
        audit = s.scalar(select(AuditLog).where(AuditLog.action == "laura.followon.mission",
                                                AuditLog.artifact == f"jobs:{job_id}"))
        assert audit is not None and audit.actor == "laura" and audit.detail["delegation"]
        assert s.scalar(select(LauraFollowOn).where(LauraFollowOn.turn_id == t["turn_id"]))
        assert s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key.like("laura:%banner%"))) is None
    # Idempotent: confirming twice does not create a second job.
    r2 = H.post(c, csrf, "/api/cc/laura/follow-on", {**body, "confirm": True})
    assert r2.status_code == 200 and r2.json()["created"] is False, r2.text
    assert len(_jobs()) == len(before) + 1


def test_protected_delegation_routes_to_the_owner_and_never_becomes_a_job():
    c, csrf = H.session()
    t = _ask(c, csrf, "Laura, have Store publish the harbour shawl listing")
    p = t["proposals"][0]
    assert p["kind"] == "owner_action" and p["job_type"] == "store.publish", p
    assert p["requires_step_up"], p
    H.expire_stepup(c)
    body = {"turn_id": t["turn_id"], "proposal_key": p["key"], "confirm": True}
    r = H.post(c, csrf, "/api/cc/laura/follow-on", body)
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    assert H.post(c, csrf, "/api/cc/auth/step-up", {"passphrase": H.PASS}).status_code == 200
    r = H.post(c, csrf, "/api/cc/laura/follow-on", body)
    assert r.status_code == 200 and r.json()["kind"] == "owner_action", r.text
    assert not [j for j in _jobs() if j[1] == "store.publish"]
    t2 = _ask(c, csrf, "Have marketing launch an ads campaign for the shawl")
    assert [x["job_type"] for x in t2["proposals"]] == ["ads.campaign"], t2["proposals"]
    assert t2["proposals"][0]["kind"] == "owner_action"


def test_spend_identity_and_canonical_brand_changes_are_refused_outright():
    c, csrf = H.session()
    before = _jobs()
    for q, needle in (("Ask finance to spend 50 dollars on yarn", "owner-only"),
                      ("Have visual replace your face with a new one", "D-FB-14"),
                      ("Have design replace the logo with something simpler", "D-FB-17")):
        t = _ask(c, csrf, q)
        assert t["intent"] == "delegate" and t["proposals"] == [], (q, t["proposals"])
        assert needle in t["answer"] and "nothing has been queued" in t["answer"], t["answer"]
    assert _jobs() == before


def test_unknown_department_is_unknown_and_blocked_department_is_not_routed_around():
    c, csrf = H.session()
    t = _ask(c, csrf, "Have the wizards make tea")        # not a department: not a delegation
    assert t["intent"] != "delegate"
    memory.remember(DB, "block:intelligence", kind="block", department="intelligence",
                    subject="owner block", state="active", body={"reason": "test block"},
                    sources=["test"])
    t = _ask(c, csrf, "Have research look into baby blanket demand")
    assert "blocked by you" in t["answer"], t["answer"]
    p = t["proposals"][0]
    r = H.post(c, csrf, "/api/cc/laura/follow-on",
               {"turn_id": t["turn_id"], "proposal_key": p["key"], "confirm": True})
    assert r.status_code == 409 and "blocked" in r.json()["error"], r.text


if __name__ == "__main__":
    H.run(globals())
