"""APPROVE-ALL-V2: "Approve everything I can decide (N)", through the real `/api/cc/*` routes
with a real owner session (passphrase + TOTP), never by calling the handlers around the gate.

* the press needs the owner session, CSRF + nonce, a FRESH step-up (consumed by the press), the
  preview's digest and one confirm;
* each class is handled as D-APPROVE-ALL-V2 says: routine; spend at its stated amount inside the
  CA$100/month hard cap; owner-only decision cards (outside acts kept with their link);
  per-release publication / activation grants signed through the existing path and bound to the
  previewed content; physical-sample cards closed `owner_directed_without_attestation`;
* child safety and physical attestation are never moved by any press (mutation tests);
* the cap still holds and is never raised; every approval is audited; the counts are right.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_approve_all_v2.py
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

_TMP = tempfile.mkdtemp(prefix="aav2_")
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
    raise OSError("network refused by the approve-all-v2 harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import approvals  # noqa: E402
from brambleloop.app.command_center import approve_all as AA  # noqa: E402
from brambleloop.app.command_center import approve_everything as AE  # noqa: E402
from brambleloop.app.command_center import auth, mission  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.authority import standing_internal as SI  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog, Improvement, OwnerAction  # noqa: E402
from brambleloop.finance import spend_policy  # noqa: E402
from brambleloop.ops import activation_authority as act  # noqa: E402
from brambleloop.ops import owner_queue  # noqa: E402
from brambleloop.ops import publication_authority as pub  # noqa: E402

OPS = "v" * 40
PASS = "owner passphrase for approve all version two"
TOTP = base64.b32encode(b"approve-all-v2-totp-key!").decode().rstrip("=")
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ[auth.TOTP_VAR] = TOTP
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db

# key -> (expected bucket, max_cost_cad, max_cost_basis)
ROWS = {
    "store:etsy.openapi_review": (AE.ROUTINE, 0.0, "stated"),
    "listing_package:moss-throw@1:abc": (AE.ROUTINE, 0.0, "stated"),
    "benchmark_refresh:granny-square": (AE.SPEND, 3.00, "stated"),
    "knowledge_gap:amigurumi-eyes": (AE.SPEND, 2.00, "stated"),
    "benchmark_challenge": (AE.SPEND_OVER_CAP, 300.00, "stated"),
    "reinvestment:2026-11": (AE.SPEND_NO_AMOUNT, 0.0, "UNKNOWN"),
    "spend.ceiling.model_monthly": (AE.SPEND_CEILING_RAISE, 150.0, "stated"),
    "improve.upgrade:{imp}": (AE.DECISION, 0.0, "stated"),
    "etsy.auth:reauthorise": (AE.OUTSIDE, 0.0, "stated"),
    "payout": (AE.OUTSIDE, 0.0, "stated"),
    "brand_clearance": (AE.OUTSIDE, 0.0, "stated"),
    "etsy_surface:policy_violations_check": (AE.OUTSIDE, 0.0, "stated"),
    "storefront:write_authority": (AE.OUTSIDE, 0.0, "stated"),
    "something.nobody.named": (AE.OWNER_APPROVED, 0.0, "stated"),
    "decision.api_vision_equivalence": (AE.OWN_CARD, 0.0, "stated"),
    "first_public_listing:approve": (AE.PUBLISHING_COVERED, 0.0, "stated"),
    "phase": (AE.OWN_CARD, 0.0, "stated"),
    "correction_notice:moss-throw": (AE.OWN_CARD, 0.0, "stated"),
    "physical_evidence:moss-throw@1": (AE.PHYSICAL_DIRECTIVE, 0.0, "stated"),
    "physical_review:moss-throw@1:three": (AE.PHYSICAL_DIRECTIVE, 0.0, "stated"),
    "physical_calibration": (AE.PHYSICAL_DIRECTIVE, 0.0, "stated"),
    "physical_size_conflict:moss-throw@1": (AE.NEVER_PHYSICAL, 0.0, "stated"),
    "store:OA-BANNER": (AE.OUTSIDE, 0.0, "stated"),
    "childrens-decision:baby-rattle": (AE.NEVER_CHILD, 0.0, "stated"),
    "portfolio.rework:baby-safety-rattle": (AE.NEVER_CHILD, 0.0, "stated"),
}
NEVER = (AE.NEVER_CHILD, AE.NEVER_PHYSICAL)
SPENT_CAD = 95.0                 # month to date: CA$5 of headroom under the CA$100 cap

PUB_CONTENT = {"action": "store.publish", "slug": "moss-throw", "version": "1",
               "release": "rel-moss", "payload": {"title": "Moss Throw"}}
ACT_CONTENT = {"action": "store.activate", "slug": "hex-coaster", "version": "2",
               "release": "rel-hex", "listing_id": "555"}
PASSING = {k: {"state": pub.PASS, "why": "test packet"} for k in pub.GATED_SECTIONS
           + ("economics",)}
PASSING["summary"] = {"all_gated_sections_pass": True, "not_passing": [], "unknown": [],
                      "economics_basis": pub.PASS}


def _pub_card(slug="moss-throw", version="1", release="rel-moss"):
    return {"card_id": f"publication:{slug}@{version}", "kind": "PUBLICATION",
            "title": f"Create the Etsy draft for {slug}", "executable": True,
            "actions": [{"action": "publication.approve", "requires_step_up": True,
                         "params": {"slug": slug, "version": version, "release": release}}]}


def _act_card(slug="hex-coaster", version="2", release="rel-hex"):
    return {"card_id": f"activation:{slug}@{version}", "kind": "ACTIVATION",
            "title": f"Make {slug} public", "executable": True,
            "actions": [{"action": "activation.approve", "requires_step_up": True,
                         "params": {"slug": slug, "version": version, "release": release}}]}


class World:
    """The release side of the inbox, patched exactly as test_v11_cc_actions does: the cards
    the inbox would show, the content each grant binds, and a fully passing packet."""

    def __init__(self, pub_cards=None, act_cards=None, pub_content=None):
        self.pub_cards = [_pub_card()] if pub_cards is None else pub_cards
        self.act_cards = [_act_card()] if act_cards is None else act_cards
        self.pub_content = dict(pub_content or PUB_CONTENT)

    def __enter__(self):
        self._p = [patch.object(approvals, "_publication_cards", lambda db, limit=20:
                                [dict(c) for c in self.pub_cards]),
                   patch.object(approvals, "_activation_cards", lambda db, limit=20:
                                [dict(c) for c in self.act_cards]),
                   patch.object(pub, "snapshot", lambda db, s, v, r: dict(self.pub_content)),
                   patch.object(pub, "evidence", lambda db, s, v, r: PASSING),
                   patch.object(act, "snapshot", lambda db, s, v, r="": dict(ACT_CONTENT)),
                   patch.object(AE, "_spent_cad", lambda db, now: SPENT_CAD)]
        for p in self._p:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._p):
            p.stop()


def _code() -> str:
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


def step_up(c, csrf):
    r = post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS, "totp": _code()})
    assert r.status_code == 200, r.text


def expire_stepup(c):
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))


def seed(rows=None) -> dict:
    """Seed the owner queue; returns key -> id (with the improvement id substituted)."""
    rows = ROWS if rows is None else rows
    with DB.session() as s:
        s.execute(delete(OwnerAction))
        s.execute(delete(Improvement))
        imp = Improvement(cell="listing", metric="ctr", hypothesis="shorter titles convert")
        s.add(imp)
        s.flush()
        ids = {}
        for key, (_b, cost, basis) in rows.items():
            k = key.format(imp=imp.id)
            row = OwnerAction(requirement_key=k, action=f"do {k}", reason="r",
                              max_cost_cad=cost, max_cost_basis=basis)
            s.add(row)
            s.flush()
            ids[key] = row.id
        ids["_imp"] = imp.id
    return ids


def preview(c):
    r = c.get("/api/cc/approve-everything")
    assert r.status_code == 200, r.text
    return r.json()


def press(c, csrf, pv, confirm=True):
    return post(c, csrf, "/api/cc/approve-everything",
                {"expected_digest": pv["digest"], "confirm": confirm})


def states() -> dict:
    with DB.session() as s:
        return {r.id: owner_queue.effective_state(r) for r in s.scalars(select(OwnerAction))}


def mark() -> int:
    from sqlalchemy import func

    with DB.session() as s:
        return int(s.scalar(select(func.max(AuditLog.id))) or 0)


def audits(action: str, after: int = 0) -> list:
    with DB.session() as s:
        return [(r.actor, r.artifact, dict(r.detail or {}))
                for r in s.scalars(select(AuditLog).where(AuditLog.action == action,
                                                          AuditLog.id > after)
                                   .order_by(AuditLog.id))]


# ---------------------------------------------------------------------------------------------


def test_refuses_without_an_owner_session_and_without_csrf():
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.get("/api/cc/approve-everything").status_code in (401, 403)
    r = anon.post("/api/cc/approve-everything", json={"expected_digest": "x", "confirm": True})
    assert r.status_code in (401, 403), r.text
    seed()
    c, _csrf = session()
    with World():
        digest = preview(c)["digest"]
        r = c.post("/api/cc/approve-everything", json={"expected_digest": digest,
                                                       "confirm": True})
    assert r.status_code in (400, 401, 403), r.text


def test_the_press_needs_a_fresh_step_up_and_consumes_it():
    ids = seed()
    c, csrf = session()
    with World():
        pv = preview(c)
        assert pv["step_up_required"] and pv["confirm_required"], pv
        before = states()
        expire_stepup(c)
        r = press(c, csrf, pv)
        assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
        # Passphrase alone is no step-up when TOTP is configured; nor is a wrong code.
        assert post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS}).status_code in (401, 403)
        assert post(c, csrf, "/api/cc/auth/step-up",
                    {"passphrase": PASS, "totp": "000000"}).status_code in (401, 403)
        assert press(c, csrf, pv).status_code == 403
        assert states() == before, "nothing may move before the step-up"
        step_up(c, csrf)
        r = press(c, csrf, pv)
        assert r.status_code == 200, r.text
        # The step-up was spent: a second press (even on a fresh, valid digest) needs another.
        seed()
        pv2 = preview(c)
        r = press(c, csrf, pv2)
        assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
    assert ids


def test_one_confirm_and_the_exact_previewed_list_are_required():
    seed()
    c, csrf = session()
    with World():
        pv = preview(c)
        before = states()
        r = press(c, csrf, pv, confirm=False)
        assert r.status_code == 409 and "confirm" in r.json()["error"], r.text
        r = post(c, csrf, "/api/cc/approve-everything", {"expected_digest": "0" * 64,
                                                         "confirm": True})
        assert r.status_code == 409 and r.json()["code"] == "REFUSED_BY_AUTHORITY", r.text
        assert states() == before


def test_every_class_is_handled_as_the_decision_says():
    ids = seed()
    c, csrf = session()
    with World():
        pv = preview(c)
        got = {i["id"]: i["bucket"] for i in pv["acted"] + pv["kept"] if "id" in i}
        for key, (bucket, _cost, _basis) in ROWS.items():
            assert got[ids[key]] == bucket, (key, got[ids[key]], bucket)
        grants = sorted(i["bucket"] for i in pv["acted"] if "card_id" in i)
        assert grants == [AE.ACTIVATION_GRANT, AE.PUBLICATION_GRANT], grants
        outside = [k for k in pv["kept"] if k["bucket"] == AE.OUTSIDE]
        assert outside and all(k["link"]["card"].startswith("#/approvals/owner_action:")
                               for k in outside), outside
        assert all(k["reason"] for k in pv["kept"])
        r = press(c, csrf, pv)
        assert r.status_code == 200, r.text
    st = states()
    for key, (bucket, _c, _b) in ROWS.items():
        want = {AE.ROUTINE: None, AE.SPEND: owner_queue.SATISFIED,
                AE.DECISION: owner_queue.SATISFIED,
                AE.OWNER_APPROVED: owner_queue.SATISFIED,
                AE.PHYSICAL_DIRECTIVE: owner_queue.WITHDRAWN}.get(bucket, owner_queue.OPEN)
        if want is None:
            assert st[ids[key]] in owner_queue.CLOSED_STATES, (key, st[ids[key]])
        else:
            assert st[ids[key]] == want, (key, st[ids[key]], want)
    # The decision went through the improvement's own door (recorded on its row).
    with DB.session() as s:
        ev = s.get(Improvement, ids["_imp"]).evidence or {}
        assert ev.get("owner_approval", {}).get("by") == "owner", ev


def test_physical_sample_cards_close_by_directive_never_as_attested():
    ids = seed()
    c, csrf = session()
    with World():
        pv = preview(c)
        m = mark()
        assert press(c, csrf, pv).status_code == 200
    samples = [k for k, v in ROWS.items() if v[0] == AE.PHYSICAL_DIRECTIVE]
    assert len(samples) == 3, samples
    with DB.session() as s:
        for key in samples:
            row = s.get(OwnerAction, ids[key])
            assert owner_queue.effective_state(row) == owner_queue.WITHDRAWN
            assert row.state_reason.startswith(AE.WITHOUT_ATTESTATION), row.state_reason
            assert AE.DIRECTIVE_RENDERS in row.state_reason and "NOT attested" in row.state_reason
            # Never readable as the owner's attestation.
            assert SI.owner_closed(s, row) is False
    rows = {a[1]: a[2] for a in audits(AE.ROW_AUDIT_ACTION, m)}
    for key in samples:
        d = rows[f"owner_action:{ids[key]}"]
        assert d["resolution"] == AE.WITHOUT_ATTESTATION and d["attested"] is False
        assert d["sample_exists"] is False and d["owner_directive"] == AE.DIRECTIVE_RENDERS
    # Nothing anywhere claims a sample exists.
    for _a, _art, d in audits(AE.ROW_AUDIT_ACTION) + audits(AE.BATCH_AUDIT_ACTION):
        assert d.get("sample_exists") in (None, False) and d.get("attested") in (None, False)


def test_publication_and_activation_grants_bind_the_previewed_content():
    seed({"store:etsy.openapi_review": (AE.ROUTINE, 0.0, "stated")})
    c, csrf = session()
    with World():
        pv = preview(c)
        by = {i["bucket"]: i for i in pv["acted"] if "card_id" in i}
        assert by[AE.PUBLICATION_GRANT]["digest"] == pub.digest(PUB_CONTENT)
        assert by[AE.ACTIVATION_GRANT]["digest"] == act.digest(ACT_CONTENT)
        r = press(c, csrf, pv)
        assert r.status_code == 200, r.text
        got = {d["bucket"]: d["approval_id"] for d in r.json()["acted"] if "approval_id" in d}
        # The existing sealed, chained grants: valid at the execution boundary.
        # Valid at the execution boundary (with the global kill-switch, which no grant
        # overrides, opened for this check only).
        with patch.dict(os.environ, {pub.KILL_SWITCH_VAR: "1"}):
            why = pub.validate(DB, got[AE.PUBLICATION_GRANT], slug="moss-throw",
                               version="1", release="rel-moss")
        assert why is None, why
        why = act.validate(DB, got[AE.ACTIVATION_GRANT], slug="hex-coaster", version="2",
                           listing_id="555", release="rel-hex")
        assert why is None, why
        with DB.session() as s:
            row = s.get(AuditLog, got[AE.PUBLICATION_GRANT])
            assert row.action == pub.APPROVED and row.actor == pub.PRINCIPAL
            assert row.detail["digest"] == pub.digest(PUB_CONTENT) and "seal" in row.detail


def test_content_changed_after_the_preview_signs_nothing_and_moves_nothing():
    ids = seed()
    c, csrf = session()
    with World() as w:
        pv = preview(c)
        before = states()
        n_grants = len(audits(pub.APPROVED))
        w.pub_content = {**PUB_CONTENT, "payload": {"title": "Moss Throw (edited)"}}
        step_up(c, csrf)
        r = press(c, csrf, pv)
        assert r.status_code == 409, r.text
    assert states() == before and len(audits(pub.APPROVED)) == n_grants
    assert ids


def test_a_failing_door_mid_press_rolls_every_write_back():
    """One transaction: a grant refused after other rows were already moved undoes them."""
    ids = seed()
    c, csrf = session()
    with World():
        pv = preview(c)
        before = states()
        n = {a: len(audits(a)) for a in (pub.APPROVED, act.APPROVED, AE.ROW_AUDIT_ACTION,
                                         "owner_action.lifecycle")}
        with patch.object(act, "approve", side_effect=ValueError("ledger refused")):
            r = press(c, csrf, pv)
        assert r.status_code == 409 and "ledger refused" in r.json()["error"], r.text
    assert states() == before
    assert {a: len(audits(a)) for a in n} == n, "a refused press must leave no row behind"
    assert ids


def test_a_release_with_an_open_child_safety_row_is_never_signed():
    seed({"childrens-decision:moss-throw": (AE.NEVER_CHILD, 0.0, "stated")})
    c, _csrf = session()
    with World():
        pv = preview(c)
    assert not [i for i in pv["acted"] if i.get("slug") == "moss-throw"], pv["acted"]
    assert [k for k in pv["kept"] if k.get("card_id") == "publication:moss-throw@1"
            and k["bucket"] == AE.NEVER_CHILD], pv["kept"]


def test_child_safety_and_physical_attestation_survive_every_mutation():
    """Mutation tests: knock out each defence in turn; the others still keep the row."""

    class Row:
        def __init__(self, key, action="", cost=1.0):
            self.id, self.requirement_key, self.action = 1, key, action
            self.max_cost_cad, self.max_cost_basis = cost, "stated"

    child = [Row("childrens-decision:baby-rattle"), Row("portfolio.rework:baby-safety-rattle"),
             Row("ads.scale:toy-ball"), Row("benchmark_refresh:x", "buy a baby rattle pattern"),
             Row("improve.upgrade:7", "relax the small parts gate"),
             Row("store:etsy.openapi_review", "check the choking-hazard copy")]
    physical = [Row("physical_size_conflict:moss@1"), Row("tester.attest:moss@1"),
                Row("portfolio.rework:swatch-measured")]
    assert len(child) == 6 and len(physical) == 3
    for r in child:
        assert AE.route(r, spend_headroom=100.0)["bucket"] == AE.NEVER_CHILD, r.requirement_key
    for r in physical:
        assert AE.route(r, spend_headroom=100.0)["bucket"] == AE.NEVER_PHYSICAL, r.requirement_key
    everything = {"disposition": SI.ROUTINE_INTERNAL, "class": "engineering", "rule": "x",
                  "why": "mutant", "key": ""}
    mutants = {
        "classifier says everything is routine": patch.object(
            AA, "judge", lambda k: {"eligible": True, "category": None, "guarded": False,
                                    "verdict": everything}),
        "key guard removed": patch.object(AA, "guard", lambda k: None),
        "text guard removed": patch.object(AE, "_CHILD_TEXT", __import__("re").compile("$^")),
    }
    # Each defence is load-bearing (removing it lets one row through: the mutant is killed)...
    only = {"key guard removed": "portfolio.rework:safety-rattle",
            "text guard removed": "benchmark_refresh:x"}
    child.append(Row("portfolio.rework:safety-rattle"))
    assert len(only) == 2 and len(child) == 7
    for name, key in only.items():
        with mutants[name]:
            row = next(r for r in child if r.requirement_key == key)
            assert AE.route(row, spend_headroom=100.0)["bucket"] != AE.NEVER_CHILD, (
                f"{name}: the mutant survived, so this defence is untested")
    # ...and with the real defences every one of them holds.
    for r in child:
        assert AE.route(r, spend_headroom=100.0)["bucket"] == AE.NEVER_CHILD, r.requirement_key
    # The classifier is not the only line: mutated to "everything is routine", the key and
    # text guards still keep every child-safety row.
    with mutants["classifier says everything is routine"]:
        for r in child:
            assert AE.route(r, spend_headroom=100.0)["bucket"] == AE.NEVER_CHILD, r.requirement_key
    # The key guard alone holds child keys even when the classifier is mutated to routine.
    with mutants["classifier says everything is routine"]:
        for r in physical[:2]:
            assert AE.route(r)["bucket"] == AE.NEVER_PHYSICAL, r.requirement_key
    # And end to end: a mutated classifier still moves no child-safety or physical row.
    ids = seed()
    c, csrf = session()
    with World(), mutants["classifier says everything is routine"]:
        pv = preview(c)
        assert press(c, csrf, pv).status_code == 200
    st = states()
    for key, (bucket, _c, _b) in ROWS.items():
        if bucket in NEVER:
            assert st[ids[key]] == owner_queue.OPEN, (key, st[ids[key]])


def test_execute_rejudges_at_the_write_and_refuses_a_tampered_list():
    ids = seed()
    with World():
        pv = AE.preview(DB, include_cards=False)
        child_id = ids["childrens-decision:baby-rattle"]
        tampered = dict(pv)
        tampered["acted"] = pv["acted"] + [{"id": child_id, "bucket": AE.ROUTINE,
                                            "requirement_key": "childrens-decision:baby-rattle"}]
        from brambleloop.core import owner_grant_keys as ogk

        with patch.object(AE, "preview", lambda db, now=None, include_cards=True: tampered), \
                ogk.owner_request("t"):
            try:
                AE.execute(DB, actor="owner:cc:t", expected_digest=pv["digest"], confirm=True)
                raise AssertionError("a tampered list moved a child-safety row")
            except AE.Refused as exc:
                assert "changed class" in str(exc), exc
        try:
            AE.execute(DB, actor="standing_authority", expected_digest=pv["digest"],
                       confirm=True)
            raise AssertionError("a non-owner actor pressed the button")
        except AE.Refused:
            pass
    assert states()[child_id] == owner_queue.OPEN


def test_the_company_cap_holds_and_is_never_raised():
    assert spend_policy.ceiling_cad() == 100.0 and spend_policy.CEILING_CAD == 100.0
    ids = seed()
    c, csrf = session()
    with World():
        pv = preview(c)
        sp = pv["spend"]
        assert sp["company_cap_cad"] == 100.0 and sp["headroom_cad"] == 5.0, sp
        assert sp["approved_in_press_cad"] == 5.0, sp       # 3.00 + 2.00, never the 300
        m = mark()
        assert press(c, csrf, pv).status_code == 200
    assert spend_policy.ceiling_cad() == 100.0, "the cap must never be raised"
    st = states()
    assert st[ids["benchmark_challenge"]] == owner_queue.OPEN
    assert st[ids["spend.ceiling.model_monthly"]] == owner_queue.OPEN
    assert st[ids["reinvestment:2026-11"]] == owner_queue.OPEN
    spend = audits(AE.SPEND_AUDIT_ACTION, m)
    assert sorted(d["amount_cad"] for _a, _r, d in spend) == [2.0, 3.0], spend
    assert all(d["company_cap_cad"] == 100.0 and d["headroom_after_cad"] >= 0
               for _a, _r, d in spend)
    # With the month already at the cap, no spend row is approved at all.
    seed()
    with World(), patch.object(AE, "_spent_cad", lambda db, now: 100.0):
        pv = AE.preview(DB, include_cards=False)
    assert not [i for i in pv["acted"] if i["bucket"] == AE.SPEND], pv["acted"]
    # Unreadable spend approves no spend.
    with World(), patch.object(AE, "_spent_cad", side_effect=RuntimeError("ledger down")):
        pv = AE.preview(DB, include_cards=False)
    assert not [i for i in pv["acted"] if i["bucket"] == AE.SPEND] and pv["spend"]["error"]


def test_every_approval_is_audited_as_the_owner():
    ids = seed()
    c, csrf = session()
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with World():
        pv = preview(c)
        m = mark()
        r = press(c, csrf, pv)
        assert r.status_code == 200, r.text
        out = r.json()
    rows = audits(AE.ROW_AUDIT_ACTION, m)
    grants = audits(AE.GRANT_AUDIT_ACTION, m)
    assert len(rows) + len(grants) == out["acted_count"] == pv["count"], (rows, grants, out)
    for actor, _art, d in rows + grants:
        assert actor.startswith("owner:cc:") and d["step_up"] is True and d["session"] == sid
        assert d["batch"] == pv["digest"][:16]
    lifecycle = {a[1] for a in audits("owner_action.lifecycle", m)}
    for _a, art, _d in rows:
        assert art in lifecycle, art
    batch = audits(AE.BATCH_AUDIT_ACTION, m)
    assert len(batch) == 1 and batch[0][2]["acted"] == out["acted_count"]
    assert batch[0][2]["kept_by_bucket"][AE.NEVER_CHILD] == 2
    assert ids


def test_the_counts_the_owner_sees_are_right():
    ids = seed()
    c, _csrf = session()
    extra = [{"card_id": "gate:etsy_api", "kind": "GATE", "title": "Etsy API"},
             {"card_id": "policy:etsy_fees", "kind": "policy_review", "title": "Fees"}]
    real_inbox = approvals.inbox

    def inbox(db):
        out = real_inbox(db)
        return {**out, "cards": list(out["cards"]) + extra}

    with World(), patch.object(approvals, "inbox", inbox):
        pv = preview(c)
        home = mission.view(DB)["owner_queue"]
    n_rows = len(ROWS)
    cnt = pv["counts"]
    assert cnt["owner_rows_open"] == n_rows, cnt
    assert cnt["can_decide_now"] == pv["count"] == len(pv["acted"]), cnt
    assert cnt["stays_with_reason"] + sum(1 for i in pv["acted"] if "id" in i) == n_rows
    assert sum(pv["by_bucket"].values()) == len(pv["acted"]) + len(pv["kept"])
    # Cards that are not OwnerAction rows are counted apart, never as owner decisions.
    assert cnt["not_owner_action_rows"] >= len(extra), cnt
    assert all(not str(o["card_id"]).startswith("owner_action:")
               for o in pv["not_owner_action_rows"])
    expected_acted = sum(1 for b, _c, _b in ROWS.values()
                         if b in (AE.ROUTINE, AE.SPEND, AE.DECISION, AE.PHYSICAL_DIRECTIVE,
                                  AE.OWNER_APPROVED))
    assert sum(1 for i in pv["acted"] if "id" in i) == expected_acted
    # Mission Control shows the same "can decide" number the button shows.
    assert home["can_decide"] == pv["count"], home
    assert ids


def test_the_ui_shows_the_list_first_and_needs_step_up_and_confirm():
    js = (ROOT / "src/brambleloop/app/command_center/static/js/views/_mission.js").read_text()
    assert "Approve everything I can decide" in js
    assert "approveEverything" in js and "requiresStepUp: true" in js
    api = (ROOT / "src/brambleloop/app/command_center/static/js/api.js").read_text()
    assert "approve-everything" in api and "confirm: true" in api
    appr = (ROOT / "src/brambleloop/app/command_center/static/js/views/approvals.js").read_text()
    assert 'startsWith("owner_action:")' in appr, "non-owner-action cards leave the view"
    app = (ROOT / "src/brambleloop/app/command_center/static/js/app.js").read_text()
    assert 'startsWith("owner_action:")' in app, "the badge counts owner rows only"


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
