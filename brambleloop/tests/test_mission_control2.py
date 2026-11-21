"""MISSION-CONTROL-2: the one-screen home, the full inventory's proof column, and the owner's
"Approve all eligible" button -- through the real `/api/cc/*` routes with a real owner session
(passphrase + TOTP), never by calling the handlers around the gate.

* every new endpoint refuses without an owner session;
* the approval refuses without a fresh step-up (passphrase + TOTP), with a wrong TOTP, without
  CSRF/nonce, and on a stale preview digest;
* it approves every row the classifier marks routine or auto-close, and never a child-safety
  hold, a physical-sample attestation, a spend-above-ceiling ask or public-publishing authority
  (each listed separately with its reason), nor a row the key guard catches;
* every approval is audited (lifecycle row, per-row approve-all row, one batch row);
* the home's six P0 verdicts come from the existing readers and are never a pass by default;
* the catalogue stays server-side paginated and searchable over ALL rows and carries `proof`.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_mission_control2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import base64
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

_TMP = tempfile.mkdtemp(prefix="mc2_")
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
    raise OSError("network refused by the mission-control harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import approve_all as AA  # noqa: E402
from brambleloop.app.command_center import auth, catalogue, mission  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.authority import standing_internal as SI  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog, OwnerAction  # noqa: E402
from brambleloop.ops import owner_queue  # noqa: E402

OPS = "q" * 40
PASS = "owner passphrase for mission control two"
TOTP = base64.b32encode(b"mission-control-2-totp!!").decode().rstrip("=")
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ[auth.TOTP_VAR] = TOTP
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db

ROUTINE = ("store:etsy.openapi_review", "model.routes_invalid", "improve.stop_list:weekly",
           "portfolio.rework:moss-throw", "improve.retirement:weekly_review")
AUTO = ("listing_package:moss-throw@1:abc",)
# The four categories the owner named, plus the rest of the genuine classes, and one row the
# classifier marks ROUTINE whose key names a child-safety subject (the key guard catches it).
EXCLUDED = {
    "childrens-decision:baby-rattle": AA.CHILD_SAFETY,
    "physical_evidence:moss-throw@1": AA.PHYSICAL_SAMPLE,
    "physical_review:moss-throw@1:three": AA.PHYSICAL_SAMPLE,
    "spend.ceiling.model_monthly": AA.SPEND_ABOVE_CEILING,
    "ads.scale:moss-throw": AA.SPEND_ABOVE_CEILING,
    "benchmark_challenge": AA.SPEND_ABOVE_CEILING,
    "first_public_listing:moss-throw@1": AA.PUBLIC_PUBLISHING,
    "standing_policy.hold:moss-throw@1:abcdef": AA.PUBLIC_PUBLISHING,
    "phase": AA.PUBLIC_PUBLISHING,
    "payout": AA.OWNER_ONLY,
    "storefront:write_authority": AA.OWNER_ONLY,
    "etsy_surface:messages_watch": AA.OWNER_ONLY,
    "something.nobody.named": AA.OWNER_ONLY,
    "portfolio.rework:baby-safety-rattle": AA.CHILD_SAFETY,
}
def _code() -> str:
    """The current TOTP code. Each step is accepted once (replay protection), so the harness
    clears the spent-step markers first -- the equivalent of waiting for the next 30 s step.
    The real passphrase + code check still runs on every login and step-up."""
    from brambleloop.app.command_center.models import RequestNonce

    auth.ensure_tables(DB)
    with DB.session() as s:
        s.execute(delete(RequestNonce).where(
            RequestNonce.session_public_id == auth.TOTP_OWNER_KEY))
    return auth.totp_code(TOTP)


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS, "totp": _code()})
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


def seed():
    with DB.session() as s:
        s.execute(delete(OwnerAction))
        for key in ROUTINE + AUTO + tuple(EXCLUDED):
            s.add(OwnerAction(requirement_key=key, action=f"do {key}", reason="r"))


def rows():
    with DB.session() as s:
        return {r.requirement_key: (owner_queue.effective_state(r), r.state_reason or "")
                for r in s.scalars(select(OwnerAction))}


def audits(action):
    with DB.session() as s:
        return [(r.actor, r.artifact, dict(r.detail or {})) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


# ---- auth ------------------------------------------------------------------------------------

def test_every_new_endpoint_refuses_without_an_owner_session():
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    paths = ("/api/cc/mission", "/api/cc/approve-all", "/api/cc/catalogue?q=x&page=2")
    for path in paths:
        r = anon.get(path)
        assert r.status_code in (401, 403), (path, r.status_code, r.text)
    r = anon.post("/api/cc/approve-all", json={"expected_digest": "x"})
    assert r.status_code in (401, 403), r.text
    # The operator token is not an owner session either.
    r = anon.post("/api/cc/approve-all", json={"expected_digest": "x"},
                  headers={"Authorization": f"Bearer {OPS}"})
    assert r.status_code in (401, 403), r.text
    assert len(paths) == 3


def test_approve_all_needs_csrf_and_a_nonce():
    seed()
    c, csrf = session()
    digest = c.get("/api/cc/approve-all").json()["digest"]
    r = c.post("/api/cc/approve-all", json={"expected_digest": digest})
    assert r.status_code in (400, 401, 403), r.text
    assert all(st == owner_queue.OPEN for st, _ in rows().values())


def test_step_up_is_enforced_passphrase_and_totp():
    seed()
    c, csrf = session()
    pv = c.get("/api/cc/approve-all").json()
    assert pv["step_up_required"] is True and pv["eligible_count"] == len(ROUTINE + AUTO), pv
    expire_stepup(c)
    r = post(c, csrf, "/api/cc/approve-all", {"expected_digest": pv["digest"]})
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    assert all(st == owner_queue.OPEN for st, _ in rows().values()), rows()
    # Passphrase alone is not a step-up when TOTP is configured; neither is a wrong code.
    r = post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS})
    assert r.status_code in (401, 403), r.text
    r = post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS, "totp": "000000"})
    assert r.status_code in (401, 403), r.text
    r = post(c, csrf, "/api/cc/approve-all", {"expected_digest": pv["digest"]})
    assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    r = post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS, "totp": _code()})
    assert r.status_code == 200, r.text
    r = post(c, csrf, "/api/cc/approve-all", {"expected_digest": pv["digest"]})
    assert r.status_code == 200, r.text
    assert r.json()["approved_count"] == len(ROUTINE + AUTO)
    # The refusals were recorded as security events, and nothing moved before the step-up.
    assert audits(AA.BATCH_AUDIT_ACTION), "the batch is audited"


def test_a_stale_preview_digest_is_refused_and_moves_nothing():
    seed()
    c, csrf = session()                    # login is a fresh step-up
    pv = c.get("/api/cc/approve-all").json()
    with DB.session() as s:               # the queue changes after the owner looked
        s.add(OwnerAction(requirement_key="model.vendor_switch_routed_only", action="x"))
    r = post(c, csrf, "/api/cc/approve-all", {"expected_digest": pv["digest"]})
    assert r.status_code == 409 and r.json()["code"] == "REFUSED_BY_AUTHORITY", r.text
    r = post(c, csrf, "/api/cc/approve-all", {})
    assert r.status_code == 409, r.text
    assert all(st == owner_queue.OPEN for st, _ in rows().values()), rows()


# ---- exclusions and audit --------------------------------------------------------------------

def test_approves_every_eligible_row_and_never_an_excluded_one():
    seed()
    c, csrf = session()
    pv = c.get("/api/cc/approve-all").json()
    got = {e["requirement_key"]: e["category"] for e in pv["excluded"]
           if e.get("requirement_key") in EXCLUDED}
    assert got == EXCLUDED, {k: (got.get(k), v) for k, v in EXCLUDED.items() if got.get(k) != v}
    for e in pv["excluded"]:
        assert e["reason"] == AA.EXCLUDED[e["category"]] and e["reason"], e
    guarded = [e for e in pv["excluded"] if e.get("guarded")]
    assert [e["requirement_key"] for e in guarded] == ["portfolio.rework:baby-safety-rattle"]
    assert SI.classify("portfolio.rework:baby-safety-rattle")["disposition"] == SI.ROUTINE_INTERNAL
    for cat in (AA.CHILD_SAFETY, AA.PHYSICAL_SAMPLE, AA.SPEND_ABOVE_CEILING,
                AA.PUBLIC_PUBLISHING):
        assert pv["excluded_by_category"][cat] >= 2, (cat, pv["excluded_by_category"])
    r = post(c, csrf, "/api/cc/approve-all", {"expected_digest": pv["digest"]})
    assert r.status_code == 200, r.text
    after = rows()
    approved_keys = ROUTINE + AUTO
    assert len(approved_keys) == 6 and len(EXCLUDED) == 14
    for key in approved_keys:
        st, why = after[key]
        assert st in owner_queue.CLOSED_STATES, (key, st)
        assert "Approve all eligible" in why, why
    for key in EXCLUDED:
        assert after[key][0] == owner_queue.OPEN, (key, after[key])
    # A second press approves nothing more and still never touches an exclusion.
    pv2 = c.get("/api/cc/approve-all").json()
    assert pv2["eligible_count"] == 0, pv2["eligible"]
    r = post(c, csrf, "/api/cc/approve-all", {"expected_digest": pv2["digest"]})
    assert r.status_code == 200 and r.json()["approved_count"] == 0, r.text
    assert all(rows()[k][0] == owner_queue.OPEN for k in EXCLUDED)


def test_every_approval_is_audited_as_the_owner():
    seed()
    before_life = len(audits("owner_action.lifecycle"))
    before_row = len(audits(AA.ROW_AUDIT_ACTION))
    c, csrf = session()
    pv = c.get("/api/cc/approve-all").json()
    r = post(c, csrf, "/api/cc/approve-all", {"expected_digest": pv["digest"]})
    assert r.status_code == 200, r.text
    n = len(ROUTINE + AUTO)
    life = audits("owner_action.lifecycle")[before_life:]
    per = audits(AA.ROW_AUDIT_ACTION)[before_row:]
    assert len(life) == n and len(per) == n, (len(life), len(per))
    batch = audits(AA.BATCH_AUDIT_ACTION)[-1]
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    for actor, artifact, d in per:
        assert actor.startswith("owner:cc:") and d["step_up"] is True and d["session"] == sid
        assert d["batch"] == batch[2]["digest"][:16] and d["requirement_key"] in ROUTINE + AUTO
        assert artifact.startswith("owner_action:")
    assert all(a.startswith("owner:cc:") for a, _x, _d in life)
    assert batch[2]["approved"] == n and sorted(batch[2]["approved_ids"]) == sorted(
        int(a.split(":")[1]) for _x, a, _d in per)
    assert batch[2]["excluded_by_category"][AA.CHILD_SAFETY] >= 2
    # Never written as the standing authority: this is the owner's own act.
    assert not [x for x in audits(SI.AUDIT_ACTION) if x[1] in {a for _x, a, _d in per}]


def test_execute_refuses_a_non_owner_actor_and_rejudges_at_the_write():
    seed()
    pv = AA.preview(DB, include_cards=False)
    try:
        AA.execute(DB, actor="standing_authority", expected_digest=pv["digest"])
        raise AssertionError("a non-owner actor approved the owner queue")
    except AA.Refused:
        pass
    # A row whose kind the classifier would now exclude is skipped at the write, not approved.
    real = AA.judge

    def flip(key):
        j = real(key)
        if key == "model.routes_invalid":
            return {**j, "eligible": False, "category": AA.OWNER_ONLY}
        return j
    pv = AA.preview(DB, include_cards=False)
    calls = {"n": 0}

    def flip_after_preview(key):
        calls["n"] += 1
        return flip(key) if calls["n"] > pv["eligible_count"] + len(EXCLUDED) else real(key)
    with patch.object(AA, "judge", side_effect=flip_after_preview):
        out = AA.execute(DB, actor="owner:cc:test", expected_digest=pv["digest"])
    assert {s["id"] for s in out["skipped"]} and out["approved_count"] == pv["eligible_count"] - 1
    assert rows()["model.routes_invalid"][0] == owner_queue.OPEN


def test_guard_and_judge_are_mutation_killing():
    assert AA.guard("childrens-decision:x") == AA.CHILD_SAFETY
    assert AA.guard("improve.retirement:weekly_review") is None      # 'retire' is not a hold
    assert AA.guard("story.board:refresh") is None                    # 'toy' needs a boundary
    assert AA.guard("plush:toy") == AA.CHILD_SAFETY
    assert AA.guard("ads.scale:x") == AA.SPEND_ABOVE_CEILING
    assert AA.guard("leads.scan") is None
    assert AA.judge("phase")["category"] == AA.PUBLIC_PUBLISHING
    assert AA.judge("")["eligible"] is False                          # fail closed
    assert AA.judge(None)["eligible"] is False
    for r in SI.KIND_RULES:
        if r["disposition"] == SI.GENUINE_EXCEPTION:
            key = r["pattern"] + ("x" if r["match"] == "prefix" else "")
            assert AA.judge(key)["eligible"] is False, key
    assert any(r["disposition"] == SI.GENUINE_EXCEPTION for r in SI.KIND_RULES)


# ---- the home ----------------------------------------------------------------------------------

def test_mission_home_has_six_live_verdicts_and_todays_counts():
    seed()
    c, _csrf = session()
    r = c.get("/api/cc/mission")
    assert r.status_code == 200, r.text
    m = r.json()
    ids = [x["id"] for x in m["conditions"]]
    assert ids == [cid for cid, _t, _s in mission.CONDITIONS] and len(ids) == 6, ids
    for cond in m["conditions"]:
        assert cond["verdict"] in ("PASS", "FAIL", "UNKNOWN") and cond["why"], cond
        assert cond["sources"], cond
    # An empty company passes nothing it cannot prove.
    by = {x["id"]: x["verdict"] for x in m["conditions"]}
    for cid in ("running", "research", "certified", "etsy"):
        assert by[cid] != "PASS", (cid, by)
    assert by["safety"] == "PASS", m["conditions"]       # shadow, nothing on Etsy, no revenue
    assert m["overall"] != "PASS"
    labels = [t["id"] for t in m["today"]]
    assert labels == [i for i, _l, _k in mission.TODAY], labels
    for t in m["today"]:
        assert t["value"] == "UNKNOWN" or isinstance(t["value"], int), t
    assert m["owner_queue"]["eligible"] == len(ROUTINE + AUTO)
    assert m["owner_queue"]["never_bulk"] == len(EXCLUDED)


def test_a_failing_reader_is_unknown_never_a_pass():
    with patch("brambleloop.app.verify_checks.publication_checks",
               side_effect=RuntimeError("boom")):
        v = mission.view(DB)
    by = {x["id"]: x for x in v["conditions"]}
    assert by["safety"]["verdict"] == "UNKNOWN" and "RuntimeError" in by["safety"]["why"]
    with patch("brambleloop.ops.daily_ledger.ledger", side_effect=RuntimeError("boom")):
        v = mission.view(DB)
    assert {t["value"] for t in v["today"]} == {"UNKNOWN"}
    assert {x["id"]: x["verdict"] for x in v["conditions"]}["factory"] != "PASS"
    assert mission._running({"state": "UNKNOWN"})["verdict"] == "UNKNOWN"
    assert mission._running({"state": "healthy", "health": {"fresh": True,
                                                            "state": "healthy"}})["verdict"] == "PASS"
    assert mission._running({"state": "x", "health": {"fresh": True,
                                                      "state": "degraded"}})["verdict"] == "FAIL"
    assert mission._factory({"state": "OK", "count_by_stage": {"a": 3}}, 0)["verdict"] == "FAIL"
    assert mission._factory({"state": "OK", "count_by_stage": {"a": 3}}, 2)["verdict"] == "PASS"
    assert mission._etsy({"state": "OK", "remote_total": 0})["verdict"] == "FAIL"


# ---- the inventory ---------------------------------------------------------------------------

def _items(n):
    return [{"slug": f"prod-{i:03d}", "version": "1", "head": True, "title": f"Product {i:03d}",
             "state": "research_candidate", "label": "Research candidate", "why": "w",
             "holds": ([{"kind": "physical", "why": "sample"}] if i % 7 == 0 else []),
             "physical_sample": {"status": "not_required"},
             "tiers": {"internal": {"complete": False}, "private_draft": {"ready": False},
                       "public": {"ready": False}},
             "evidence": {"stages": [], "job_ids": []}} for i in range(n)]


def test_inventory_is_server_side_paginated_and_searchable_over_all_rows():
    items = _items(130)
    rec = {"products": {}, "versions": [], "listings": {}, "intents": {}}
    inv = {"items": items, "total": len(items), "gate_mode": "recorded"}
    snap = {"rec": rec, "inv": inv, "now": mission._now()}
    idx = catalogue.build_index(DB, snap=snap)
    p1 = catalogue.query(idx, {"page_size": "50"})
    assert p1["matching"] == 130 and p1["pages"] == 3 and len(p1["items"]) == 50
    p3 = catalogue.query(idx, {"page_size": "50", "page": "3"})
    assert len(p3["items"]) == 30 and p3["items"][-1]["slug"] == "prod-129"
    assert {i["slug"] for i in p1["items"]}.isdisjoint({i["slug"] for i in p3["items"]})
    hit = catalogue.query(idx, {"q": "product 12"})
    assert {i["slug"] for i in hit["items"]} == {f"prod-{n:03d}" for n in
                                                  range(120, 130)}, hit["matching"]
    assert catalogue.query(idx, {"q": "prod-007"})["matching"] == 1
    held = catalogue.query(idx, {"held": "physical", "page_size": "200"})
    assert held["matching"] == len([i for i in range(130) if i % 7 == 0])
    for row in p1["items"]:
        assert set(row) >= {"stage", "proof", "holds", "next_action"}, sorted(row)
        assert row["proof"]["summary"] == "no proof recorded yet"
        assert "certificate" in row["proof"]["missing"]
    assert p1["items"] and held["items"]
    assert catalogue.query(idx, {"page": "999", "page_size": "50"})["page"] == 3


def test_proof_names_what_exists_and_what_is_missing():
    ev = {"certificate": {"release_hash": "r"}, "pdf": {"sha256_by_terminology":
                                                        {"US": "a", "UK": "b"}},
          "gallery": None, "listing_package": {"listing_id": 1},
          "etsy": {"read_back": "not_verified"}}
    p = catalogue.proof(ev)
    assert p["certificate"] and p["pdf_us"] and p["pdf_uk"] and p["listing_package"]
    assert not p["gallery"] and not p["etsy_read_back"]
    assert p["missing"] == ["gallery", "etsy_read_back"]
    assert catalogue.proof({})["summary"] == "no proof recorded yet"


def test_catalogue_route_pages_with_an_owner_session():
    c, _csrf = session()
    r = c.get("/api/cc/catalogue?page=1&page_size=10&q=zzz-nothing")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["page"] == 1 and body["page_size"] == 10 and body["matching"] == 0
    assert body["items"] == []


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
