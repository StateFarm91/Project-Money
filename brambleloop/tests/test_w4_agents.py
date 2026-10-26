"""W4-AGENTS: the Storefront Director as an operational agent, and its gated write path.

No request leaves the machine. Every Etsy transport here records calls; the core assertion is
that NO storefront write is sent in SHADOW mode or without the owner's verified grant.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_agents.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
for _k in list(os.environ):
    if _k.startswith("ETSY") or _k in ("BRAMBLELOOP_STOREFRONT_WRITES_AUTHORISED",):
        os.environ.pop(_k)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import (DEFAULT_AGENTS, FORBIDDEN_COMBINATIONS,  # noqa: E402
                                         PermissionDenied, Registry)
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, OwnerAction, Phase  # noqa: E402
from brambleloop.integrations import etsy as E  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime import etsy_ops, storefront_ops  # noqa: E402
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402
from brambleloop.store_foundation import director, live_state  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="w4agents_")
_N = [0]


def _db() -> Database:
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/a{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


class Recorder:
    def __init__(self):
        self.sent = []

    def request(self, method, url, *, headers, json=None, form=None, multipart=None):
        self.sent.append((method, url, dict(form or {})))
        return E.Response(status=200, body={"ok": True})


CREDS = E.Credentials(api_key="k", access_token="t", shop_id="shop-1")


class _Grant(E.OwnerGrant):
    """A storefront grant whose verification result the test controls."""

    def __init__(self, why):
        super().__init__(None, action=E.OwnerGrant.STOREFRONT, approval_id=1)
        self.why = why

    def refusal(self, *, action, listing_id="", change=None):
        return self.why if action == self.STOREFRONT else "wrong action"


def _refused(fn):
    try:
        fn()
    except E.EtsyNotPermitted as exc:
        return str(exc)
    raise AssertionError("expected a refusal")


# ---- the agent --------------------------------------------------------------------------


def test_storefront_director_is_registered_green_cad0_and_cannot_write():
    spec = next(a for a in DEFAULT_AGENTS if a["name"] == "storefront_director")
    assert spec["daily_cost_ceiling_cad"] == 0.0
    assert set(spec["allowed_job_types"]) == {"storefront.review", "content.draft"}
    assert "store.update" in FORBIDDEN_COMBINATIONS["storefront_director"]
    db = _db()
    reg = Registry(db)
    reg.authorize("storefront_director", "storefront.review")
    try:
        reg.authorize("storefront_director", "store.update")
        raise AssertionError("storefront_director must not hold store.update")
    except PermissionDenied:
        pass
    assert ("storefront_review", "storefront_director", "storefront.review",
            86400) in CADENCES
    for jt in ("storefront.review", "content.draft", "store.update"):
        assert handlers.get(jt) is not None, jt


def test_charters_still_valid_and_storefront_review_is_safe_generated():
    from brambleloop.autonomy import charters

    assert charters.validate() == []
    ch = charters.BY_KEY["store_commerce"]
    assert "storefront_director" in ch.agents and "storefront.review" in ch.generatable
    assert charters.department_of("storefront.review") == "store_commerce"
    assert "store.update" in charters.PROTECTED_JOB_TYPES


# ---- the client: no write in SHADOW, without a grant, or on a protected field -----------


def test_update_shop_refused_in_shadow_even_with_a_grant():
    t = Recorder()
    c = E.EtsyClient(t, credentials=CREDS, phase="shadow")
    why = _refused(lambda: c.update_shop({"announcement": "x"}, grant=_Grant(None)))
    assert "does not permit a storefront write" in why
    _refused(lambda: c.create_shop_section("Home", grant=_Grant(None)))
    assert t.sent == []


def test_update_shop_refused_without_grant_or_with_unverified_grant():
    t = Recorder()
    c = E.EtsyClient(t, credentials=CREDS, phase="production", owner_authorised=True,
                     shadow_writes_authorised=True)
    assert "Shadow Mode" in _refused(lambda: c.update_shop({"announcement": "x"}))
    assert "expired" in _refused(lambda: c.update_shop({"announcement": "x"},
                                                       grant=_Grant("grant expired")))
    _refused(lambda: c.create_shop_section("Home"))
    _refused(lambda: c.delete_shop_section("9"))
    assert t.sent == [], "no storefront request may leave without a verified grant"


def test_protected_title_and_eu_only_policy_refused_even_with_verified_grant():
    t = Recorder()
    c = E.EtsyClient(t, credentials=CREDS, phase="production", owner_authorised=True)
    assert "configured by the owner" in _refused(
        lambda: c.update_shop({"title": "New tagline"}, grant=_Grant(None)))
    assert "EU-located" in _refused(
        lambda: c.update_shop({"policy_additional": "terms"}, grant=_Grant(None)))
    try:
        c.update_shop({"icon": "x"}, grant=_Grant(None))
        raise AssertionError("unknown field must be rejected")
    except E.EtsyRejected:
        pass
    assert t.sent == []


def test_write_sent_only_with_verified_grant_in_publishing_phase():
    t = Recorder()
    c = E.EtsyClient(t, credentials=CREDS, phase="production", owner_authorised=True)
    c.update_shop({"announcement": "Hello"}, grant=_Grant(None))
    c.create_shop_section("Home", grant=_Grant(None))
    assert t.sent[0] == ("PUT", f"{c.BASE}/shops/shop-1", {"announcement": "Hello"})
    assert t.sent[1] == ("POST", f"{c.BASE}/shops/shop-1/sections", {"title": "Home"})
    try:
        c.create_shop_section("x" * 25, grant=_Grant(None))
        raise AssertionError("Etsy's 24-character section limit")
    except E.EtsyRejected:
        pass


def test_real_owner_grant_refuses_in_shadow_and_on_a_different_change():
    db = _db()
    g = E.OwnerGrant(db, action=E.OwnerGrant.STOREFRONT, approval_id=1,
                     change={"operation": "updateShop", "fields": {"announcement": "a"}})
    assert "does not permit" in g.refusal(action=E.OwnerGrant.STOREFRONT,
                                          change={"operation": "updateShop",
                                                  "fields": {"announcement": "a"}})
    from brambleloop.core import phase as phase_mod

    real = phase_mod.effective
    phase_mod.effective = lambda *a, **k: "production"
    try:
        assert "different change" in g.refusal(
            action=E.OwnerGrant.STOREFRONT,
            change={"operation": "updateShop", "fields": {"announcement": "b"}})
        # Same change, but no sealed grant row and the kill-switch is off: refused.
        assert g.refusal(action=E.OwnerGrant.STOREFRONT,
                         change={"operation": "updateShop", "fields": {"announcement": "a"}})
    finally:
        phase_mod.effective = real


def test_write_refusal_default_is_unchanged():
    assert "Shadow Mode" in live_state.write_refusal("announcement")
    assert "never overwrites" in live_state.write_refusal("title")


# ---- the handlers, end to end: SHADOW records proposals and writes nothing --------------


def _ctx(db, job: Job) -> JobContext:
    return JobContext(job=job, db=db, queue=JobQueue(db), registry=Registry(db),
                      phase=Phase.SHADOW)


def _run(db, agent, jt, inputs=None):
    job = JobQueue(db).enqueue(agent, jt, inputs or {})
    return handlers.get(jt)(_ctx(db, job))


def test_review_draft_and_apply_in_shadow_send_nothing():
    db = _db()
    shop = {"title": "x", "announcement": "", "digital_sale_message": "",
            "policy_shipping": "", "policy_additional": "something", "icon_url_fullxfull": "u"}
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING, {"observed_at": time.time(), "shop": shop})
    etsy_ops.store_reading(db, live_state.SYNC_READING, {
        "observed_at": time.time(), "shop": shop, "sections": []})
    constructed = []
    real_client = E.EtsyClient.__init__

    def spy(self, *a, **k):
        constructed.append(1)
        real_client(self, *a, **k)

    E.EtsyClient.__init__ = spy
    try:
        out = _run(db, "storefront_director", "storefront.review")
        assert "announcement" in out["agent_gaps"] and out["draft_job"]
        assert out["writes_performed"] == 0
        drafted = _run(db, "storefront_director", "content.draft", {"kind": "storefront"})
        assert drafted["recorded"] >= 2 and drafted["apply_jobs"], drafted
        assert "policy_shipping" in drafted["owner_steps"]
        # LISTREADY E3: never asked to clear policy_additional; Etsy holds the value.
        assert "policy_additional" not in drafted["owner_steps"]
        assert all(p["surface"] != "policy_additional" for p in director.proposals(db))
        props = director.proposals(db)
        ann = next(p for p in props if p["surface"] == "announcement")
        assert ann["valid"] and ann["source"].startswith("store_foundation.content")
        assert all("title" not in (p.get("change") or {}).get("fields", {}) for p in props)
        with db.session() as s:
            jobs = list(s.scalars(select(Job).where(Job.job_type == "store.update")))
        assert jobs and all(j.agent == "store_operator" for j in jobs)
        for j in jobs:
            res = handlers.get("store.update")(_ctx(db, j))
            assert res["written"] is False and res["held"] and res["etsy_calls"] == 0
            assert "SHADOW" in res["reason"]
        assert constructed == [], "no Etsy client may even be built in SHADOW"
        assert director.proposal(db, ann["digest"])["state"] == "held"
        # A second draft run records nothing new (idempotent on the change digest).
        again = _run(db, "storefront_director", "content.draft", {"kind": "storefront"})
        assert again["recorded"] == 0
    finally:
        E.EtsyClient.__init__ = real_client


def test_store_update_outside_shadow_without_grant_holds_and_raises_one_card():
    db = _db()
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING, {
        "observed_at": time.time(), "shop": {"announcement": ""}})
    _run(db, "storefront_director", "content.draft", {"kind": "storefront"})
    ann = next(p for p in director.proposals(db) if p["surface"] == "announcement")
    job = JobQueue(db).enqueue("store_operator", "store.update",
                               {"kind": "storefront", "proposal": ann["digest"][:20]},
                               idempotency_key="t1")
    ctx = _ctx(db, job)
    ctx.phase = Phase.PRODUCTION
    from brambleloop.core import phase as phase_mod

    real = phase_mod.effective
    phase_mod.effective = lambda *a, **k: "production"
    try:
        res = handlers.get("store.update")(ctx)
        res2 = handlers.get("store.update")(ctx)
    finally:
        phase_mod.effective = real
    assert res["written"] is False and res["etsy_calls"] == 0
    assert "kill-switch" in res["reason"] or "grant" in res["reason"]
    assert res2["written"] is False
    with db.session() as s:
        cards = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == "storefront:write_authority")))
    assert len(cards) == 1


def test_section_proposals_only_for_populated_categories():
    from brambleloop.store_foundation import navigation

    db = _db()
    etsy_ops.store_reading(db, live_state.SYNC_READING, {
        "observed_at": time.time(), "shop": {}, "sections": [{"title": "Home"}]})
    rev = director.review(db)
    sec = next(r for r in rev["surfaces"] if r["surface"] == "sections")
    public = [s["name"] for s in navigation.public_nav(db)]
    assert all(t in public for t in sec["missing"]) and "Home" not in sec["missing"]
    hidden = [s["name"] for s in navigation.hidden(db)]
    assert hidden, "Launch-0 leaves planned categories (Wearables, Gifts) unpopulated"
    for name in hidden:
        assert director.validate_change(db, {"operation": "createShopSection",
                                             "title": name})
    # A draft that claims something untrue is never proposed.
    bad = director.validate_change(db, {"operation": "updateShop", "fields": {
        "announcement": "Handmade by our AI agent, tested by thousands of makers!"}})
    assert bad


def test_unreviewed_storefront_is_a_laura_priority_and_a_valid_mission():
    from datetime import datetime, timezone

    from brambleloop.laura.agency import delegation, followon
    from brambleloop.laura.executive import loop

    db = _db()
    s = director.summary(db)
    assert s["status"] == "UNKNOWN"
    state = {"providers": {"storefront": {**s, "source": "brambleloop.store_foundation."
                                                     "director"}}}
    pr = loop.prioritise(state, now=datetime.now(timezone.utc))
    p = next(x for x in pr if x.subject == "storefront")
    assert p.job_type == "storefront.review" and p.department == "store_commerce"
    assert followon.green_allowed("store_commerce", "storefront.review") is None
    plan = delegation.plan(delegation.parse("Have the storefront draft the announcement"))
    assert plan["route"] == "mission" and plan["job_type"] == "storefront.review"
    assert delegation.plan(delegation.parse("Have store change the price"))["route"] == \
        "owner_action"
    assert delegation.plan(delegation.parse("Have branding replace the banner"))["route"] == \
        "refused"
    from brambleloop.autonomy import generators, orchestrator
    from brambleloop.autonomy import charters

    cand = generators.Candidate(department="store_commerce", job_type="storefront.review",
                                value=50, source="laura", reason="test", fingerprint="t",
                                evidence=[])
    m = orchestrator._enqueue_mission(db, JobQueue(db), charters.BY_KEY["store_commerce"],
                                      cand, datetime.now(timezone.utc))
    assert m["agent"] == "storefront_director"


def test_agent_doable_store_cards_are_superseded_not_asked():
    """L-5 (review of a14c9ef): OA-D1 is superseded only while the storefront grant card is
    open (so the owner still has the ask), closed only on live sections evidence, and
    otherwise still asked -- including reopening one that was superseded earlier."""
    from brambleloop.store_foundation import store_readiness as R

    db = _db()
    with db.session() as s:
        s.add(OwnerAction(requirement_key="store:OA-D1", action="Create sections"))
    # 1. no grant card, no evidence: still the owner's ask, never silently superseded
    out = R.sync_owner_actions(db, {})
    assert "OA-D1" not in out["skipped"]
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == "store:OA-D1"))
        assert row.done is False and row.state == "open"
    # LISTREADY: OA-E closes only on getShop evidence, so with none it is still asked.
    assert "store:OA-E" in out["created"]
    # 2. the grant card is open: OA-D1 is superseded by it
    with db.session() as s:
        s.add(OwnerAction(requirement_key=R.GRANT_CARD, action="Approve storefront writes"))
    out = R.sync_owner_actions(db, {})
    assert "store:OA-D1" not in out["created"] and "OA-D1" in out["skipped"]
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == "store:OA-D1"))
        assert row.done and row.state == "superseded" and "agent work" in row.state_reason
        assert R.GRANT_CARD in row.state_reason
        oac = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == "store:OA-C"))
        assert oac is not None and "drafted by the Storefront Director" in oac.action
        assert s.scalar(select(AuditLog.id).where(AuditLog.action ==
                                                  "owner_action.lifecycle")) is not None
        # 3. the grant card goes away (answered or withdrawn) with no evidence: reopened
        s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == R.GRANT_CARD)).done = True
    out = R.sync_owner_actions(db, {})
    assert "store:OA-D1" in out["updated"]
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == "store:OA-D1"))
        assert row.done is False and row.state == "open" and "reopened" in row.state_reason
    # 4. a FRESH shop_sync reading shows every section: closed on that evidence
    etsy_ops.store_reading(db, live_state.SYNC_READING, {
        "observed_at": time.time(), "shop": {"title": "x"},
        "sections": [{"title": t} for t in director.drafts(db)["sections"]["titles"]]})
    out = R.sync_owner_actions(db, {})
    assert "store:OA-D1" in out["closed"] and "shop_sync" in out["closed"]["store:OA-D1"]
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == "store:OA-D1"))
        assert row.done is True


def test_i4_validate_change_refuses_owner_and_eu_fields_by_set_not_wording():
    from unittest.mock import patch

    change = {"operation": "updateShop", "fields": {"announcement": "Hello from the studio."}}
    base = director.validate_change(None, change)
    # an agent-writable field the owner has now configured on the live shop is refused by
    # set membership, even when the refusal message no longer carries the old wording
    owned = live_state.OWNER_CONFIGURED | {live_state._key_for("announcement")}
    with patch.object(live_state, "OWNER_CONFIGURED", owned), \
            patch.object(live_state, "write_refusal", return_value="reworded refusal"):
        probs = director.validate_change(None, change)
    assert "reworded refusal" in probs and "reworded refusal" not in base, (probs, base)
    eu = live_state.EU_ONLY | {live_state._key_for("announcement")}
    with patch.object(live_state, "EU_ONLY", eu), \
            patch.object(live_state, "write_refusal", return_value=None):
        probs = director.validate_change(None, change)
    assert any("never software-writable" in p for p in probs), probs

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
