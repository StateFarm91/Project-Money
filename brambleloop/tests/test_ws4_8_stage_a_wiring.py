"""WS4-8: the Stage A use path -- a standing activation grant through `store.activate`.

* `handle_store_activate` accepts a `seg:` grant the policy issuer bound to THIS job, and only
  through every guard it applies to an owner's per-product approval: the phase gate, the
  publishing kill switch, the spend reservation, the write-ahead `etsy.activate` intent
  (`<listing>:seg:<id>`), `use_refusal` at the client, and a read-back.
* L-B: after `store.activated` and a read-back showing the listing `active`, the listing is in
  SP lineage, so the rollback plan finds it. A failed read-back records nothing.
* A listing the owner activated is never in Stage A lineage.
* A retried job never activates or charges twice; a crash after the Etsy request reconciles
  from the read-back.
* `policy.activation_schedule` is a recorded no-op while Stage A is off, and otherwise queues
  at most one standing activation inside the policy's decision, pace and fee ceilings.

Stub Etsy only (tests/fake_etsy.py); no network.
Run: cd brambleloop && python3 tests/test_ws4_8_stage_a_wiring.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  (per-process temp sandbox, removed at exit)
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# run_tests.sh sets no PYTHONPATH: src (and tests) before any brambleloop import.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from tests import test_etsy_readback_observe as rb  # noqa: E402  (fake Etsy and fixtures)
import _owner_grant; _owner_grant.scoped_owner_approvals()  # noqa: E402,E702

from brambleloop.core.models import (AuditLog, CostEntry, Incident, Job,  # noqa: E402
                                     JobStatus, Listing, Phase)
from brambleloop.integrations.etsy import EtsyClient  # noqa: E402
from brambleloop.ops import standing_activation as SA  # noqa: E402
from brambleloop.ops import standing_activation_flow as F  # noqa: E402
from brambleloop.ops import standing_boundary as SB  # noqa: E402
from brambleloop.ops import standing_grants as SG  # noqa: E402
from brambleloop.ops import standing_issuer as SI  # noqa: E402
from brambleloop.ops import standing_policy as SP  # noqa: E402
from brambleloop.ops import standing_withdrawal as SW  # noqa: E402
from brambleloop.queue import effects  # noqa: E402

TOKEN = "test-owner-credential-32-characters"
AID = 4242
SHOP = {"state": SB.PASS, "value": "70001", "why": None}
NAME = {"state": SB.PASS, "value": "BrambleloopStudio", "why": None}
_SAVED: dict = {}
_FAKES: list = []


def _keys():
    pairs = SP.generate_keypairs()
    for var in (SP.ISSUER_KEY_VAR, SP.ISSUER_VERIFY_KEY_VAR):
        _SAVED.setdefault(var, os.environ.get(var))
        os.environ[var] = pairs[var]


def _unkeys():
    while _FAKES:
        _FAKES.pop().__exit__(None, None, None)
    SG._PROCESS.update(issuer=False, job=False, issuer_key_at_boot=False)
    for k, v in _SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _effective(state=SP.EFFECTIVE, actions=("store.publish", "store.activate")):
    def eff(db=None, now=None, **_kw):
        return {"state": state, "why": "owner suspended" if state != SP.EFFECTIVE else None,
                "approval_id": AID, "seal": "policy-seal", "activation_id": 1,
                "approved_at": "2026-11-01T00:00:00+00:00",
                "content": {"version": 1, "actions": list(actions),
                            "spend": {"max_listing_fees_cad_per_30d": 4.0, "ads": "NONE"}}}
    return eff


class _StageA:
    """Stage A switched on (as the reviewed code change would), an EFFECTIVE policy naming
    store.activate, and a name-verified shop. `on=False` leaves the shipped switch alone."""

    def __init__(self, *, on=True, state=SP.EFFECTIVE):
        self.on, self.state = on, state

    def __enter__(self):
        self.p = [patch.object(SP, "effective", _effective(self.state)),
                  patch.object(SI, "_shop_id", lambda db: dict(SHOP)),
                  patch.object(SI, "_shop_name", lambda: dict(NAME))]
        if self.on:
            self.p.append(patch.object(SA, "STAGE_A_ENABLED", True))
        for p in self.p:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self.p):
            p.stop()


def _mint(db, slug, version, release, job_id):
    """`standing_activation.issue` as the issuer runs it, every issue-time gate passing
    (Mode T, the decision); the signature, snapshot, slot and grant row are real."""
    decided = {"decision": "ACTIVATE", "reasons": [], "approval_id": AID, "class_id": "c",
               "effective_risk": "low", "counts": {"today": [], "7d": 0, "30d": 0}}
    with _StageA(), patch.object(SG, "issuer_signing_refusal", lambda env=None: None), \
            patch.object(SG, "mode_report", lambda db_, now=None, env=None: {"mode": "T",
                                                                             "reasons": []}), \
            patch.object(SA, "decide", lambda *a, **k: dict(decided)):
        return SA.issue(db, slug=slug, version=version, release=release, job_id=job_id)


def _world():
    """A certified release whose verified draft is on the fake Etsy, with its renewal off."""
    db = rb._db()
    fake = rb.FakeEtsy()
    fake.__enter__()
    _FAKES.append(fake)
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN}):
        p, lid = rb._published(db, fake)
    fake.listings[str(lid)]["should_auto_renew"] = False
    with db.session() as s:
        release = s.scalar(select(Listing.release_hash).where(
            Listing.product_slug == p["slug"])) or ""
    return db, fake, p, str(lid), release


def _enqueue(db, inputs, *, cancel=True):
    """Queue one store.activate job; by default park any other pending one first (a verified
    publish queues its own), so the worker runs the job the test names."""
    from brambleloop.queue.durable import JobQueue

    if cancel:
        with db.session() as s:
            for other in s.scalars(select(Job).where(Job.job_type == "store.activate",
                                                     Job.status == JobStatus.PENDING)):
                other.status = JobStatus.CANCELLED
    return JobQueue(db).enqueue("store_operator", "store.activate", inputs,
                                idempotency_key=f"t:{time.time_ns()}")


def _run(db, fake, job, *, phase=Phase.LIMITED_PRODUCTION, on=True, activate=None):
    """Run one queued store.activate job through the real worker, as rb._run does."""
    from brambleloop.core import phase as phase_mod
    from brambleloop.runtime.worker import Worker

    orig = rb._gates_pass()
    env = {"BRAMBLELOOP_OPS_TOKEN": TOKEN, "BRAMBLELOOP_PUBLISH_AUTHORISED": "1"}
    if phase is not Phase.SHADOW:
        env["BRAMBLELOOP_PHASE"] = phase.value
    try:
        with patch.dict(os.environ, env), _StageA(on=on), rb._Patched(fake), \
                (patch.object(EtsyClient, "activate", activate) if activate else _Null()):
            if phase is not Phase.SHADOW and not phase_mod.latest_recorded(db)["recorded"]:
                from phase_fixture import record_phase_path
                record_phase_path(db, TOKEN, phase.value)
            assert Worker(db, f"w-{job.id}", phase=phase,
                          job_types=["store.activate"]).run_once()
    finally:
        rb._restore(orig)
    with db.session() as s:
        row = s.get(Job, job.id)
        s.expunge(row)
        return row


def _handler(db, fake, job, *, activate=None):
    """Call the handler directly with this job (a retry of the same job, in-process)."""
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import JobContext, handlers

    orig = rb._gates_pass()
    env = {"BRAMBLELOOP_OPS_TOKEN": TOKEN, "BRAMBLELOOP_PUBLISH_AUTHORISED": "1",
           "BRAMBLELOOP_PHASE": "limited_production"}
    try:
        with patch.dict(os.environ, env), _StageA(), rb._Patched(fake), \
                (patch.object(EtsyClient, "activate", activate) if activate else _Null()):
            from brambleloop.core import phase as phase_mod
            if not phase_mod.latest_recorded(db)["recorded"]:
                from phase_fixture import record_phase_path
                record_phase_path(db, TOKEN, "limited_production")
            with db.session() as s:
                j = s.get(Job, job.id)
                s.expunge(j)
            ctx = JobContext(job=j, db=db, queue=JobQueue(db), registry=Registry(db),
                             phase=Phase.LIMITED_PRODUCTION)
            return handlers.get("store.activate")(ctx)
    finally:
        rb._restore(orig)


class _Null:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def _standing_job(db, p, release):
    return _enqueue(db, {"slug": p["slug"], "version": p["version"], "release": release,
                         "standing_activation": True})


def _audits(db, action):
    with db.session() as s:
        return [(a.id, dict(a.detail or {})) for a in s.scalars(
            select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))]


def _fees(db):
    with db.session() as s:
        return list(s.scalars(select(CostEntry).where(CostEntry.kind == "etsy_listing_fee")))


def _plan_live(db):
    with _StageA(state=SP.SUSPENDED_STATE):
        out = SW.plan(db)
    assert out["planned"], out
    return [x["listing_id"] for x in out["live"]]


# ---- the use path ----------------------------------------------------------------------------

def test_a_standing_grant_activates_through_the_handler_and_enters_lineage():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _standing_job(db, p, release)
        gid = _mint(db, p["slug"], p["version"], release, job.id)["grant_id"]
        done = _run(db, fake, job)
        assert done.status is JobStatus.DONE, (done.status, done.last_error)
        assert done.outputs["activated"] is True and done.outputs["lineage_recorded"], \
            done.outputs
        assert fake.listings[lid]["state"] == "active"
        with db.session() as s:
            g = s.get(SG.StandingGrant, gid)
            assert g.consumed_job_id == job.id                      # consumed by this job
            assert s.scalar(select(Listing.state).where(
                Listing.product_slug == p["slug"])) == "active"
            intent = s.get(effects.EffectIntent,
                           effects.key_for("etsy.activate", f"{lid}:seg:{gid}"))
            assert intent is not None and intent.state == effects.APPLIED
            assert intent.job_type == "store.activate" and intent.job_id == job.id
        assert len(_fees(db)) == 1                                  # the reserved listing fee
        activated = _audits(db, "store.activated")
        verified = _audits(db, SA.ACTIVATED)
        assert len(activated) == 1 and activated[0][1]["authority"] == "standing"
        assert len(verified) == 1 and verified[0][1]["grant_id"] == gid
        assert verified[0][0] > activated[0][0], "lineage is recorded after store.activated"
        used = _audits(db, "store.activation_authority_used")
        assert used[-1][1]["approval_id"] == f"seg:{gid}"
        # L-B contract: the rollback plan of a stopped policy finds the Stage A listing.
        assert _plan_live(db) == [lid]
        assert SW.lineage_of_live(db, lid)["grant_id"] == gid
    finally:
        _unkeys()


def test_the_shipped_switch_refuses_a_consumed_grant_at_the_handler():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _standing_job(db, p, release)
        _mint(db, p["slug"], p["version"], release, job.id)
        assert SA.STAGE_A_ENABLED is False
        done = _run(db, fake, job, on=False)
        assert done.outputs["activated"] is False and SA.OFF in done.outputs["reasons"][0], \
            done.outputs
        assert fake.listings[lid]["state"] == "draft" and not _fees(db)
        assert not _audits(db, SA.ACTIVATED)
    finally:
        _unkeys()


def test_shadow_refuses_before_any_etsy_read_or_grant_use():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _standing_job(db, p, release)
        gid = _mint(db, p["slug"], p["version"], release, job.id)["grant_id"]
        before = len(fake.requests)
        done = _run(db, fake, job, phase=Phase.SHADOW)
        assert done.status is JobStatus.DEAD and "SHADOW" in (done.last_error or "")
        assert len(fake.requests) == before and fake.listings[lid]["state"] == "draft"
        with db.session() as s:
            assert s.get(SG.StandingGrant, gid).consumed_at is None
    finally:
        _unkeys()


def test_no_grant_for_this_job_is_no_authority():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        other = _standing_job(db, p, release)
        _mint(db, p["slug"], p["version"], release, other.id)        # bound to another job
        job = _standing_job(db, p, release)
        done = _run(db, fake, job)
        assert done.outputs["activated"] is False
        assert "no standing activation grant has been issued" in done.outputs["reasons"][0]
        assert fake.listings[lid]["state"] == "draft" and not _fees(db)
        # A refused request's reason is what the job reports.
        job2 = _standing_job(db, p, release)
        with db.session() as s:
            s.add(AuditLog(actor="policy_issuer", action=F.HELD, artifact="x",
                           detail={"request_id": 1, "job_id": job2.id, "why": "pace: per day"}))
        done = _run(db, fake, job2)
        assert "refused this job" in done.outputs["reasons"][0] and \
            "pace: per day" in done.outputs["reasons"][0]
    finally:
        _unkeys()


def test_a_standing_job_carries_one_authority():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _enqueue(db, {"slug": p["slug"], "version": p["version"], "release": release,
                            "standing_activation": True, "owner_activation_approval_id": 1})
        _mint(db, p["slug"], p["version"], release, job.id)
        done = _run(db, fake, job)
        assert done.outputs["activated"] is False and "one authority" in \
            done.outputs["reasons"][0]
        assert fake.listings[lid]["state"] == "draft"
    finally:
        _unkeys()


def test_a_failed_read_back_records_nothing_as_activated():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _standing_job(db, p, release)
        _mint(db, p["slug"], p["version"], release, job.id)
        real = EtsyClient.activate

        def accepted_not_applied(self, listing_id, **kw):
            out = real(self, listing_id, **kw)                    # Etsy answers 2xx...
            fake.listings[str(listing_id)]["state"] = "inactive"  # ...and it is not live
            return out
        done = _run(db, fake, job, activate=accepted_not_applied)
        assert done.outputs["activated"] is False, done.outputs
        assert not _audits(db, "store.activated") and _audits(db, "store.activate_incomplete")
        assert not _audits(db, SA.ACTIVATED), "a failed read-back put a listing in lineage"
        assert _plan_live(db) == [] and SW.lineage_of_live(db, lid) is None
    finally:
        _unkeys()


def test_record_activated_refuses_a_read_back_of_another_listing_or_state():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _standing_job(db, p, release)
        gid = _mint(db, p["slug"], p["version"], release, job.id)["grant_id"]
        with _StageA():
            assert F.claim(db, gid, job_id=job.id) is None
        assert SA.record_activated(db, gid, listing_id=lid, after={"listing_id": lid,
                                                                   "state": "draft"}) is False
        assert SA.record_activated(db, gid, listing_id=lid, after={"listing_id": "9",
                                                                   "state": "active"}) is False
        assert not _audits(db, SA.ACTIVATED)
    finally:
        _unkeys()


def test_an_owner_activated_listing_is_never_in_stage_a_lineage():
    from brambleloop.ops import activation_authority as authority

    _keys()
    try:
        db, fake, p, lid, release = _world()
        with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": TOKEN}):
            content = authority.snapshot(db, p["slug"], p["version"])
            approval = authority.approve(db, authorization=TOKEN, slug=p["slug"],
                                         version=p["version"],
                                         expected_digest=authority.digest(content),
                                         reason="owner reviewed this exact test draft")
        job = _enqueue(db, {"slug": p["slug"], "version": p["version"],
                            "owner_activation_approval_id": approval["approval_id"]})
        done = _run(db, fake, job)
        assert done.outputs["activated"] is True, done.outputs
        assert _audits(db, "store.activated")[-1][1]["authority"] == "owner"
        assert not _audits(db, SA.ACTIVATED)
        assert _plan_live(db) == [] and SW.lineage_of_live(db, lid) is None
    finally:
        _unkeys()


# ---- idempotence and crash safety -------------------------------------------------------------

def test_a_retried_job_never_activates_or_charges_twice():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _standing_job(db, p, release)
        _mint(db, p["slug"], p["version"], release, job.id)
        sent = []
        real = EtsyClient.activate

        def counting(self, listing_id, **kw):
            sent.append(listing_id)
            return real(self, listing_id, **kw)
        assert _handler(db, fake, job, activate=counting)["activated"] is True
        again = _handler(db, fake, job, activate=counting)        # the same job, re-run
        assert again["activated"] is False and again["reasons"] == ["already active"]
        # Even with the local record lost, the intent and the read-back stop a second send.
        with db.session() as s:
            s.scalar(select(Listing).where(Listing.product_slug == p["slug"])).state = "published"
        third = _handler(db, fake, job, activate=counting)
        assert third["activated"] is True and third.get("reconciled") is True, third
        assert len(sent) == 1 and len(_fees(db)) == 1
    finally:
        _unkeys()


def test_a_crash_after_the_etsy_request_reconciles_from_the_read_back():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _standing_job(db, p, release)
        gid = _mint(db, p["slug"], p["version"], release, job.id)["grant_id"]
        sent = []
        real = EtsyClient.activate

        def crash_after_send(self, listing_id, **kw):
            sent.append(listing_id)
            real(self, listing_id, **kw)                          # Etsy applied it...
            raise ConnectionError("worker lost the response")      # ...and we never heard
        try:
            _handler(db, fake, job, activate=crash_after_send)
            raise AssertionError("the crash must propagate")
        except ConnectionError:
            pass
        assert fake.listings[lid]["state"] == "active" and not _audits(db, SA.ACTIVATED)
        with db.session() as s:
            assert s.get(effects.EffectIntent, effects.key_for(
                "etsy.activate", f"{lid}:seg:{gid}")).state == effects.UNCERTAIN
        out = _handler(db, fake, job, activate=crash_after_send)   # the retry
        assert out["activated"] is True and out["reconciled"] is True and \
            out["lineage_recorded"] is True, out
        assert len(sent) == 1 and len(_fees(db)) == 1
        assert _audits(db, "store.activated")[-1][1]["reconciled"] is True
        assert _plan_live(db) == [lid]
        with db.session() as s:
            open_ = [i.signature for i in s.scalars(select(Incident).where(
                Incident.resolved.is_(False))) if i.signature.startswith("effect.reconcile:")]
        assert open_ == [], open_
    finally:
        _unkeys()


def test_a_crash_before_etsy_applied_is_never_resent():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _standing_job(db, p, release)
        _mint(db, p["slug"], p["version"], release, job.id)
        sent = []

        def crash_unsent(self, listing_id, **kw):
            sent.append(listing_id)
            raise ConnectionError("lost before Etsy applied it")
        try:
            _handler(db, fake, job, activate=crash_unsent)
        except ConnectionError:
            pass
        try:
            _handler(db, fake, job, activate=crash_unsent)
            raise AssertionError("an attempt of unknown outcome must not be repeated")
        except effects.EffectRefused:
            pass
        assert len(sent) == 1 and fake.listings[lid]["state"] == "draft"
        assert not _audits(db, SA.ACTIVATED) and len(_fees(db)) == 1
    finally:
        _unkeys()


def test_the_client_refuses_a_standing_grant_without_the_handlers_intent():
    """`use_refusal` at the client keeps its intent check: the handler's pre-checks use
    `at_effect=False`; the client's check immediately before the request does not."""
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _standing_job(db, p, release)
        gid = _mint(db, p["slug"], p["version"], release, job.id)["grant_id"]
        with _StageA():
            assert F.claim(db, gid, job_id=job.id) is None
        effects.ensure_table(db)
        remote = {"should_auto_renew": False}
        with _StageA():
            kw = dict(slug=p["slug"], version=p["version"], listing_id=lid, release=release,
                      job_id=job.id, remote=remote)
            assert "used only through store.activate" in SA.use_refusal(db, f"seg:{gid}", **kw)
            assert SA.use_refusal(db, f"seg:{gid}", at_effect=False, **kw) is None
            assert "should_auto_renew" in SA.use_refusal(
                db, f"seg:{gid}", at_effect=False, **{**kw, "remote": {}})
    finally:
        _unkeys()


def test_claim_consumes_once_and_only_for_its_own_job():
    _keys()
    try:
        db, fake, p, lid, release = _world()
        job = _standing_job(db, p, release)
        gid = _mint(db, p["slug"], p["version"], release, job.id)["grant_id"]
        with _StageA():
            assert "issued for job" in F.claim(db, gid, job_id=job.id + 1)
            assert F.claim(db, gid, job_id=job.id) is None
            assert F.claim(db, gid, job_id=job.id) is None             # a retry: same job
            assert "consumed by job" in F.claim(db, gid, job_id=job.id + 1)
        assert len(_audits(db, SG.CONSUMED)) == 1
    finally:
        _unkeys()


# ---- what the enqueuer schedules --------------------------------------------------------------

class _Enq:
    def __init__(self, db):
        from brambleloop.queue.durable import JobQueue

        self.q, self.calls = JobQueue(db), []

    def __call__(self, agent, job_type, inputs, **kw):
        from brambleloop.queue.durable import DuplicateJob

        self.calls.append((agent, job_type, dict(inputs), kw))
        try:
            return self.q.enqueue(agent, job_type, inputs, **kw)
        except DuplicateJob:
            return None


def _sched_world():
    db, fake, p, lid, release = _world()
    _FAKES.remove(fake)
    fake.__exit__(None, None, None)
    with db.session() as s:
        for other in s.scalars(select(Job).where(Job.job_type == "store.activate")):
            other.status = JobStatus.CANCELLED
    return db, p, lid, release


def _decide_as(decision, reasons=()):
    return lambda *a, **k: {"decision": decision, "reasons": list(reasons),
                            "approval_id": AID, "counts": {"today": [], "7d": 0, "30d": 0}}


def _lineage(state=SB.PASS):
    return lambda *a, **k: {"state": state, "value": {}, "why": None if state == SB.PASS
                            else "not this policy's draft"}


def test_while_stage_a_is_off_the_scheduler_is_a_recorded_no_op():
    db, p, lid, release = _sched_world()
    enq = _Enq(db)
    assert SA.STAGE_A_ENABLED is False
    out = F.schedule(db, enqueue=enq)
    assert out["scheduled"] == [] and out["skipped"] == SA.OFF and enq.calls == []
    assert _audits(db, F.SKIPPED)[-1][1]["why"] == SA.OFF
    assert not _audits(db, F.REQUESTED) and not _audits(db, SA.SHADOW_DECISION)
    # Switched on, but no approved policy in effect, or one that does not name the action.
    with _StageA(state=SP.SUSPENDED_STATE):
        assert "no approved standing policy" in F.schedule(db, enqueue=enq)["skipped"]
    with patch.object(SA, "STAGE_A_ENABLED", True), \
            patch.object(SP, "effective", _effective(actions=("store.publish",))):
        assert "does not name store.activate" in F.schedule(db, enqueue=enq)["skipped"]
    assert enq.calls == []


def test_the_scheduler_queues_one_standing_activation_and_asks_the_issuer():
    db, p, lid, release = _sched_world()
    enq = _Enq(db)
    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    with _StageA(), patch.object(SA, "lineage", _lineage()), \
            patch.object(SA, "decide", _decide_as("ACTIVATE")):
        out = F.schedule(db, enqueue=enq, now=now)
        assert len(out["scheduled"]) == 1, out
        agent, jt, inputs, kw = enq.calls[0]
        assert (agent, jt) == ("store_operator", "store.activate")
        assert inputs == {"slug": p["slug"], "version": p["version"], "release": release,
                          "standing_activation": True}
        assert kw["run_after"] == now + F.ISSUE_DELAY
        req = F.pending_requests(db)
        assert [r["job_id"] for r in req] == [out["scheduled"][0]["job_id"]]
        # Outstanding work (the live job and the unanswered request) holds the next pass.
        again = F.schedule(db, enqueue=enq, now=now + timedelta(hours=1))
        assert again["scheduled"] == [] and again["outstanding"] >= 1 and len(enq.calls) == 1
    # One shadow decision per release and decision, however many passes.
    rows = _audits(db, SA.SHADOW_DECISION)
    assert len(rows) == 1 and rows[0][1]["decision"] == "ACTIVATE"


def test_the_scheduler_never_queues_more_than_one_a_pass():
    db, p, lid, release = _sched_world()
    enq = _Enq(db)
    two = [(p["slug"], p["version"], release), ("second-coaster", "1.0.0", "b" * 64)]
    with _StageA(), patch.object(SA, "lineage", _lineage()), \
            patch.object(SA, "decide", _decide_as("ACTIVATE")), \
            patch.object(F, "candidates", lambda db_: list(two)):
        out = F.schedule(db, enqueue=enq)
    assert len(out["scheduled"]) == 1 and len(enq.calls) == 1, out
    assert len(_audits(db, SA.SHADOW_DECISION)) == 2


def test_the_policy_decision_pace_and_fee_ceilings_bind_the_scheduler():
    db, p, lid, release = _sched_world()
    enq = _Enq(db)
    for reasons in (["at most 1 activation(s) per day"], ["at most 3 activations per 7 days"],
                    ["listing fees would pass CA$4.00 in 30 days"],
                    ["Stage A shadow gate: Stage A shadow is short: 2 of 7 shadow days"]):
        with _StageA(), patch.object(SA, "lineage", _lineage()), \
                patch.object(SA, "decide", _decide_as("HOLD", reasons)):
            out = F.schedule(db, enqueue=enq)
        assert out["scheduled"] == [] and enq.calls == [], (reasons, out)
    # The shadow decision ignores only Stage A's own shadow gate: a pace hold is a HOLD, a
    # short shadow alone is a would-ACTIVATE (the evidence that gate counts).
    decided = sorted(d["decision"] for _, d in _audits(db, SA.SHADOW_DECISION))
    assert decided == ["ACTIVATE", "HOLD"], decided
    # A draft this policy did not create is never a candidate, whatever the decision says.
    with _StageA(), patch.object(SA, "lineage", _lineage(SB.FAIL)), \
            patch.object(SA, "decide", _decide_as("ACTIVATE")):
        assert F.schedule(db, enqueue=enq)["scheduled"] == [] and enq.calls == []


def test_the_real_pace_ceiling_holds_the_scheduler():
    """The real `decide` pace read (not a stand-in): a slot already used today holds."""
    db, p, lid, release = _sched_world()
    enq = _Enq(db)
    from brambleloop.ops import standing_shadow_gate as G

    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    SA.ensure_tables(db)
    with db.session() as s:
        s.add(SA.StandingActivationSlot(policy_row_id=AID, day=now.date().isoformat(),
                                        slot_no=1, at=now))
    with _StageA(), patch.object(SA, "lineage", _lineage()), \
            patch.object(G, "g_shadow", lambda *a, **k: {"verdict": "MET", "approval_id": AID}), \
            patch.object(SA, "a_shadow", lambda *a, **k: {"state": SB.PASS, "why": None}), \
            patch.object(SI, "read_facts", lambda *a, **k: {}), \
            patch.object(SB, "classify", lambda c, f: {"in_policy": True, "reasons": []}):
        out = F.schedule(db, enqueue=enq, now=now)
        assert out["scheduled"] == [] and enq.calls == [], out
        assert "per day" in " ".join(out["decisions"][0]["reasons"])
        tomorrow = F.schedule(db, enqueue=enq, now=now + timedelta(days=1))
        assert len(tomorrow["scheduled"]) == 1, tomorrow


def test_the_handler_registered_is_the_scheduler_and_records_work():
    from brambleloop.runtime import worker as W
    from brambleloop.runtime.pipeline import WORK_KEYS

    assert W.handlers.get(F.JOB_TYPE) is not None
    assert any(c[2] == F.JOB_TYPE and c[1] == "publishing" for c in W.CADENCES)
    assert WORK_KEYS[F.JOB_TYPE] == ("work_done",)


# ---- the issuer's answer ----------------------------------------------------------------------

def test_the_issuer_binds_a_grant_only_to_a_live_standing_job_for_this_release():
    _keys()
    try:
        db, p, lid, release = _sched_world()
        ok = _standing_job(db, p, release)
        owner = _enqueue(db, {"slug": p["slug"], "version": p["version"], "release": release},
                         cancel=False)
        assert F.job_refusal(db, ok.id, p["slug"], p["version"], release) is None
        assert "did not ask" in F.job_refusal(db, owner.id, p["slug"], p["version"], release)
        assert "another release" in F.job_refusal(db, ok.id, p["slug"], p["version"], "z" * 64)
        assert "no job" in F.job_refusal(db, 99999, p["slug"], p["version"], release)
        with db.session() as s:
            s.get(Job, ok.id).status = JobStatus.DONE
        assert "is done" in F.job_refusal(db, ok.id, p["slug"], p["version"], release)
        # Shipped: every request is answered, with a recorded refusal.
        live = _standing_job(db, p, release)
        rid = F.request(db, slug=p["slug"], version=p["version"], release=release,
                        job_id=live.id)
        ans = F.answer(db, F.pending_requests(db)[0])
        assert ans == {"request_id": rid, "issued": False, "why": SA.OFF}, ans
        assert F.pending_requests(db) == []
        assert "refused this job" in F.grant_for_job(db, live.id)["why"]
        # Switched on, the issuer's answer is the real `issue` (Mode T is the first refusal).
        live2 = _standing_job(db, p, release)
        F.request(db, slug=p["slug"], version=p["version"], release=release, job_id=live2.id)
        with _StageA(), patch.object(SG, "issuer_signing_refusal", lambda env=None: None):
            ans = F.answer(db, F.pending_requests(db)[0])
        assert ans["issued"] is False and "Mode T" in ans["why"], ans
        # And with every issue-time gate passing, a grant bound to that job, request answered.
        live3 = _standing_job(db, p, release)
        rid3 = F.request(db, slug=p["slug"], version=p["version"], release=release,
                         job_id=live3.id)
        decided = {"decision": "ACTIVATE", "reasons": [], "approval_id": AID,
                   "counts": {"today": [], "7d": 0, "30d": 0}}
        with _StageA(), patch.object(SG, "issuer_signing_refusal", lambda env=None: None), \
                patch.object(SG, "mode_report", lambda *a, **k: {"mode": "T", "reasons": []}), \
                patch.object(SA, "decide", lambda *a, **k: dict(decided)):
            ans = F.answer(db, F.pending_requests(db)[0])
        assert ans["issued"] is True and F.grant_for_job(db, live3.id)["grant_id"] == \
            ans["grant_id"], ans
        assert _audits(db, SA.ISSUED)[-1][1]["request_id"] == rid3
        assert F.pending_requests(db) == []
    finally:
        _unkeys()


def test_the_issuer_answer_refuses_a_job_that_is_not_live_even_when_every_gate_passes():
    """`answer` checks the job before `issue`: with every issue-time gate passing, a request
    naming a finished or non-standing job is HELD and no grant exists."""
    _keys()
    try:
        db, p, lid, release = _sched_world()
        done_job = _standing_job(db, p, release)
        with db.session() as s:
            s.get(Job, done_job.id).status = JobStatus.DONE
        owner_job = _enqueue(db, {"slug": p["slug"], "version": p["version"],
                                  "release": release}, cancel=False)
        decided = {"decision": "ACTIVATE", "reasons": [], "approval_id": AID,
                   "counts": {"today": [], "7d": 0, "30d": 0}}
        for job in (done_job, owner_job):
            F.request(db, slug=p["slug"], version=p["version"], release=release,
                      job_id=job.id)
            with _StageA(), patch.object(SG, "issuer_signing_refusal", lambda env=None: None), \
                    patch.object(SG, "mode_report", lambda *a, **k: {"mode": "T",
                                                                     "reasons": []}), \
                    patch.object(SA, "decide", lambda *a, **k: dict(decided)):
                ans = F.answer(db, F.pending_requests(db)[0])
            assert ans["issued"] is False and "job is not valid" in ans["why"], ans
            assert F.grant_for_job(db, job.id)["grant_id"] is None
    finally:
        _unkeys()


def test_the_issuer_tick_answers_activation_requests():
    from brambleloop.app import issuer_entry

    db, p, lid, release = _sched_world()
    job = _standing_job(db, p, release)
    F.request(db, slug=p["slug"], version=p["version"], release=release, job_id=job.id)
    from brambleloop.ops import slo
    with patch.object(slo, "acquire_lease", lambda *a, **k: True), \
            patch.object(SG, "issuer_heartbeat", lambda *a, **k: None):
        out = issuer_entry.tick(db, holder="t")
    assert any(a.get("why") == SA.OFF for a in out["answered"]), out
    assert F.pending_requests(db) == []


def test_every_new_audit_action_has_a_retention_decision():
    from brambleloop.ops import retention

    assert retention.unknown_read_actions() == []
    for action in (F.REQUESTED, F.HELD, F.SKIPPED, F.SCHEDULED, SA.ISSUED):
        assert action in retention.KNOWN_READ_ACTIONS, action


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback

                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
