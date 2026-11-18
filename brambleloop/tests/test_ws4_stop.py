"""WS4 stop watch (design §5.1, §7.1 T-SW-1..3; §9 M6 increment 8).

T-SW-1: one test per stop condition, each raised by a real row, plus "unreadable means stop".
T-SW-2: a suspension is sticky, and resume refuses while a condition holds.
T-SW-3: stop-watch silence beyond the policy's limit (never above 30 min) blocks issue.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select  # noqa: E402

from brambleloop.core import owner_grant_keys  # noqa: E402
from brambleloop.core.models import (AuditLog, Customer, Incident, Job,  # noqa: E402
                                     JobStatus, Order)
from brambleloop.ops import standing_boundary as SB  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from brambleloop.ops import standing_stop as ST  # noqa: E402
from test_ws4_policy_object import (NOW, _ModeT, _activate_raw, _approve, _db,  # noqa: E402
                                    _refused, _restore, content)

SLUG = "lineage-coaster"
LINEAGE = {"products": {SLUG}, "listing_ids": {"4400001"}, "why": "test lineage"}
FRESH = {"current": [], "stale": [], "never_checked": [], "changed_unreviewed": [],
         "all_fresh": True}


class _Clear:
    """Every source that this test DB cannot satisfy by rows alone reads clear: the
    platform-policy readings are fresh and the phase publishes. Each test then raises
    exactly one condition with a real row."""

    def __enter__(self):
        self._p = [patch("brambleloop.gates.platform_policy.freshness",
                         return_value=dict(FRESH)),
                   patch("brambleloop.core.phase.effective",
                         return_value="limited_production")]
        for p in self._p:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self._p:
            p.stop()


def _incident(db, signature, *, severity="P1", resolved=False, slug=None):
    with db.session() as s:
        s.add(Incident(signature=signature, severity=severity, summary="fixture",
                       resolved=resolved, product_slug=slug))


def _held(db, c, *, lin=None, activated=True, spend=False):
    """The holding reasons. Spend under a non-empty lineage always reads UNKNOWN today (its
    own test pins that), so the other lineage tests leave it out unless asked."""
    out = ST._reasons(ST.conditions(db, c, now=NOW, activated=activated, lin=lin))
    return out if spend or lin is None else [r for r in out if not r.startswith("spend:")]


def _one(reasons, name):
    assert len(reasons) == 1 and reasons[0].startswith(f"{name}: "), reasons
    return reasons[0]


def test_control_with_every_source_clear_nothing_holds():
    try:
        db, c = _db(), content()
        with _Clear():
            assert _held(db, c) == []
            assert _held(db, c, lin=LINEAGE) == []
            conds = ST.conditions(db, c, now=NOW)
        assert len(conds) == 11, sorted(conds)
        # The real lineage is empty today, and says why.
        assert ST.lineage(db, c["policy_id"])["products"] == set()
    finally:
        _restore()


def test_open_defect_incident_on_a_lineage_product_stops():
    try:
        db, c = _db(), content()
        _incident(db, f"support.defect:{SLUG}:1.0.0:row3")
        _incident(db, "support.defect:other-slug:1.0.0:row3")
        with _Clear():
            _one(_held(db, c, lin=LINEAGE), "open_defect_incident_on_policy_product")
            # A defect on a product outside the lineage does not stop the policy.
            assert _held(db, c, lin={**LINEAGE, "products": {"third"}}) == []
    finally:
        _restore()


def test_refunds_in_seven_days_and_the_thirty_day_rate_stop():
    try:
        db, c = _db(), content()       # refunds_7d_count 2, refund_rate_30d_pct 10.0
        with db.session() as s:
            cust = Customer(customer_ref="buyer-1")
            s.add(cust)
            s.flush()
            for i in range(20):
                s.add(Order(customer_id=cust.id, external_ref=f"o-{i}", product_slug="x",
                            at=NOW - timedelta(days=20), refunded=False,
                            detail={"state": "paid"}))
            s.add(Order(customer_id=cust.id, external_ref="r-1", product_slug="x",
                        at=NOW - timedelta(days=1), refunded=True))
        with _Clear():
            assert _held(db, c) == []          # 1 refund in 7 d; 1/21 = 4.8 %
            with db.session() as s:
                s.add(Order(customer_id=1, external_ref="r-2", product_slug="x",
                            at=NOW - timedelta(days=2), refunded=True))
            r = _one(_held(db, c), "refunds")
            assert "2 refund(s) in 7 days" in r, r
        # The rate alone: three old refunds out of 23 orders in 30 days is 13 %.
        db2 = _db()
        with db2.session() as s:
            cust = Customer(customer_ref="buyer-2")
            s.add(cust)
            s.flush()
            for i in range(20):
                s.add(Order(customer_id=cust.id, external_ref=f"p-{i}", product_slug="x",
                            at=NOW - timedelta(days=15), detail={"state": "paid"}))
            for i in range(3):
                s.add(Order(customer_id=cust.id, external_ref=f"q-{i}", product_slug="x",
                            at=NOW - timedelta(days=20), refunded=True))
        with _Clear():
            r = _one(_held(db2, c), "refunds")
            assert "refund rate 13.0%" in r and "in 7 days" not in r, r
    finally:
        _restore()


def test_any_etsy_policy_notice_or_suspected_takedown_stops():
    try:
        for sig in ("etsy.policy_violation:abc", "policy_violation_suspected:4400009"):
            db, c = _db(), content()
            _incident(db, sig, severity="P2")
            with _Clear():
                _one(_held(db, c), "etsy_policy_notice_any")
            # Resolved is not open.
            db, c = _db(), content()
            _incident(db, sig, severity="P2", resolved=True)
            with _Clear():
                assert _held(db, c) == []
    finally:
        _restore()


def test_a_stale_never_read_or_changed_platform_policy_reading_stops():
    try:
        db, c = _db(), content()
        with patch("brambleloop.core.phase.effective", return_value="limited_production"):
            # This database has no policy reading at all: never read is a stop.
            r = _one(_held(db, c), "platform_policy_fresh")
            assert "never read" in r, r
            with patch("brambleloop.gates.platform_policy.freshness", return_value={
                    **FRESH, "changed_unreviewed": ["etsy_seller_policy"]}):
                assert "changed, unreviewed" in _one(_held(db, c), "platform_policy_fresh")
    finally:
        _restore()


def test_spend_under_a_non_empty_lineage_is_unknown_and_stops():
    try:
        db, c = _db(), content()
        with _Clear():
            r = _held(db, c, lin=LINEAGE, spend=True)
            assert len(r) == 1, r
            assert _held(db, c) == []
        assert r[0].startswith("spend: UNKNOWN"), r
    finally:
        _restore()


def test_dead_letters_in_the_last_hour_stop():
    try:
        db, c = _db(), content()        # dead_letters_60m 5
        with db.session() as s:
            for i in range(5):
                s.add(Job(agent="a", job_type="x.y", status=JobStatus.DEAD,
                          last_error="RuntimeError: boom", finished_at=NOW - timedelta(
                              minutes=10 if i < 4 else 90)))
        with _Clear():
            assert _held(db, c) == []         # four inside the hour, one outside
            with db.session() as s:
                s.add(Job(agent="a", job_type="x.y", status=JobStatus.DEAD,
                          last_error="RuntimeError: boom",
                          finished_at=NOW - timedelta(minutes=5)))
            assert "5 unexpected dead letter" in _one(_held(db, c), "dead_letters_60m")
    finally:
        _restore()


def test_any_open_p0_and_any_authority_tamper_stop():
    try:
        db, c = _db(), content()
        _incident(db, "anything:at-all", severity="P0")
        with _Clear():
            _one(_held(db, c), "open_p0_any")
        db, c = _db(), content()
        _incident(db, "authority_chain_tamper:store.publish", severity="P1")
        with _Clear():
            _one(_held(db, c), "authority_tamper_any")
    finally:
        _restore()


def test_publish_incomplete_and_census_drift_on_lineage_stop():
    try:
        db, c = _db(), content()
        _incident(db, f"store.publish_incomplete:{SLUG}@1.0.0")
        with _Clear():
            _one(_held(db, c, lin=LINEAGE), "publish_incomplete_any")
            assert [x for x in _held(db, c, lin={**LINEAGE, "products": {"o"}})
                    if not x.startswith("spend:")] == []
        db, c = _db(), content()
        _incident(db, "etsy.listing_drift:4400001")
        _incident(db, "etsy.listing_drift:9999999")
        with _Clear():
            r = _one([x for x in _held(db, c, lin=LINEAGE) if not x.startswith("spend:")],
                     "census_drift_on_policy_listing")
            assert "4400001" in r and "9999999" not in r, r
    finally:
        _restore()


def test_phase_below_limited_production_stops_an_activated_policy_only():
    try:
        db, c = _db(), content()
        with patch("brambleloop.gates.platform_policy.freshness", return_value=dict(FRESH)), \
                patch("brambleloop.core.phase.effective", return_value="shadow"):
            assert "below limited_production" in _one(_held(db, c), "phase_publishes")
            # Before activation (the shadow period) the phase is assumed, and named so.
            assert _held(db, c, activated=False) == []
            conds = ST.conditions(db, c, now=NOW, activated=False)
            assert "assumed for shadow" in conds["phase_publishes"]["why"]
    finally:
        _restore()


def test_every_unreadable_source_is_a_stop():
    """T-SW-1: a source that raises reads UNKNOWN, and UNKNOWN holds."""
    try:
        db, c = _db(), content()
        sources = {"_refunds": "refunds", "_etsy_notices": "etsy_policy_notice_any",
                   "_platform_policy": "platform_policy_fresh",
                   "_dead_letters": "dead_letters_60m", "_p0": "open_p0_any",
                   "_tamper": "authority_tamper_any", "_phase": "phase_publishes",
                   "_defects": "open_defect_incident_on_policy_product",
                   "_publish_incomplete": "publish_incomplete_any",
                   "_census_drift": "census_drift_on_policy_listing"}
        with _Clear():
            for fn, name in sources.items():
                with patch.object(ST, fn, side_effect=RuntimeError("db gone")):
                    held = [x for x in _held(db, c, lin=LINEAGE) if not x.startswith("spend:")]
                r = _one(held, name)
                assert "UNKNOWN" in r and "RuntimeError" in r, r
            # The lineage itself unreadable stops every lineage-scoped condition.
            with patch.object(ST, "lineage", side_effect=RuntimeError("x")):
                held = _held(db, c)
            assert {h.split(":")[0] for h in held} == {
                "open_defect_incident_on_policy_product", "spend", "publish_incomplete_any",
                "census_drift_on_policy_listing"}, held
        # Content failing the code ceilings is itself a stop.
        bad = dict(c, frequency={**c["frequency"], "max_per_day": 99})
        assert ST._reasons(ST.conditions(db, bad, now=NOW))[0].startswith("policy_content")
    finally:
        _restore()


def test_t_sw_2_an_activated_policy_is_suspended_stickily_and_resume_refuses_while_held():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        _incident(db, "synthetic:p0-drill", severity="P0")
        with _Clear():
            out = ST.run(db, now=NOW)
            assert out == {"policies": 1, "holding": 1, "suspended": 1, "would_suspend": 0}
            with _ModeT():
                eff = sp.effective(db, now=NOW)
            assert eff["state"] == sp.SUSPENDED_STATE and "open_p0_any" in eff["why"], eff
            with db.session() as s:
                inc = s.scalar(select(Incident).where(
                    Incident.signature == f"{ST.INCIDENT_PREFIX}{c['policy_id']}"))
                assert inc is not None and inc.severity == "P1" and not inc.resolved
            # Resume (the default reader is the stop watch) refuses while the P0 is open.
            with owner_grant_keys.owner_request("s"):
                _refused(sp.resume, db, c["policy_id"], stepped_up=True, owner_session="s",
                         actor="owner", now=NOW, contains="open_p0_any")
            # The condition clears; the suspension does NOT clear by itself.
            with db.session() as s:
                for i in s.scalars(select(Incident).where(Incident.severity == "P0")):
                    i.resolved = True
            later = NOW + timedelta(minutes=5)
            assert ST.run(db, now=later)["suspended"] == 0
            with _ModeT():
                assert sp.effective(db, now=later)["state"] == sp.SUSPENDED_STATE
            last = ST.last_reading(db, c["policy_id"])
            assert last["action"] == "already_suspended" and last["holding"] == []
            with db.session() as s:
                n = len(list(s.scalars(select(AuditLog.id).where(
                    AuditLog.action == sp.SUSPENDED))))
            assert n == 1, n                              # one suspension, not one per tick
            # Only the owner's resume, with every condition clear and a fresh reading.
            with owner_grant_keys.owner_request("s"), \
                    patch.object(ST, "_now", lambda now=None: now or later):
                sp.resume(db, c["policy_id"], stepped_up=True, owner_session="s",
                          actor="owner", now=later)
            with _ModeT():
                assert sp.effective(db, now=later)["state"] == sp.EFFECTIVE
    finally:
        _restore()


def test_resume_refuses_when_the_stop_watch_is_silent():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        sp.suspend(db, c["policy_id"], reason="owner pause", by="owner")
        with _Clear(), owner_grant_keys.owner_request("s"):
            r = _refused(sp.resume, db, c["policy_id"], stepped_up=True, owner_session="s",
                         actor="owner", now=NOW, contains="stop_watch_silence")
            assert "UNKNOWN" in r and "no reading" in r, r
            assert ST.holding(db, "sp-not-a-policy") and "UNKNOWN" in ST.holding(
                db, "sp-not-a-policy")[0]
    finally:
        _restore()


def test_shadow_policies_are_read_and_would_suspend_but_are_never_suspended():
    try:
        db, c = _db(), content()
        _approve(db, c)
        _incident(db, "synthetic:p0", severity="P0")
        with _Clear():
            out = ST.run(db, now=NOW)
        assert out == {"policies": 1, "holding": 1, "suspended": 0, "would_suspend": 1}, out
        last = ST.last_reading(db, c["policy_id"])
        assert last["action"] == "would_suspend" and last["activated"] is False
        assert last["assumed"] == ["phase_publishes"]
        with db.session() as s:
            assert s.scalar(select(AuditLog.id).where(AuditLog.action == sp.SUSPENDED)) is None
            assert s.scalar(select(Incident.id).where(
                Incident.signature.like(f"{ST.INCIDENT_PREFIX}%"))) is None
        # With no approved policy the stop watch reads nothing.
        db2 = _db()
        assert ST.run(db2, now=NOW)["policies"] == 0
    finally:
        _restore()


def test_t_sw_3_silence_beyond_the_policy_limit_blocks_issue():
    from brambleloop.ops import standing_issuer as SI

    try:
        db, c = _db(), content()
        _approve(db, c)
        f = ST.silence(db, c, now=NOW)
        assert f["state"] == SB.UNKNOWN, f              # never read
        with _Clear():
            ST.run(db, now=NOW)
        assert ST.silence(db, c, now=NOW + timedelta(minutes=29))["state"] == SB.PASS
        assert ST.silence(db, c, now=NOW + timedelta(minutes=31))["state"] == SB.FAIL
        assert ST.silence(db, c, now=NOW - timedelta(minutes=1))["state"] == SB.UNKNOWN
        tight = content(stop_conditions={**c["stop_conditions"],
                                         "stop_watch_max_silence_minutes": 10})
        assert ST.silence_limit_minutes(tight) == 10
        assert ST.silence(db, tight, now=NOW + timedelta(minutes=11))["state"] == SB.FAIL
        # A limit above the code ceiling is never honoured.
        assert ST.silence_limit_minutes({"stop_conditions": {
            "stop_watch_max_silence_minutes": 600}}) == sp.MAX_STOP_WATCH_SILENCE_MINUTES
        # The issuer reads both facts inline; a silent watch holds the decision.
        with _Clear():
            facts = ST.issue_facts(db, c, now=NOW + timedelta(minutes=45))
        assert facts["stop_watch_fresh"]["state"] == SB.FAIL
        assert facts["stop_conditions_clear"]["state"] == SB.PASS
        verdict = SB.classify(c, {**__import__("test_ws4_boundary").facts(), **facts})
        assert not verdict["in_policy"] and any("stop_watch_fresh" in r
                                                for r in verdict["reasons"])
        assert "stop_watch_fresh" not in SI.NOT_BUILT_YET
        assert "stop_conditions_clear" not in SI.NOT_BUILT_YET
    finally:
        _restore()


def test_the_issuer_reads_a_holding_condition_as_a_hold():
    from brambleloop.ops import standing_issuer as SI

    try:
        db, c = _db(), content()
        _incident(db, "synthetic:p0", severity="P0")
        with _Clear():
            facts = SI.read_facts(db, "x", "1.0.0", "r", c, shadow=True)
        f = facts["stop_conditions_clear"]
        assert f["state"] == SB.FAIL and "open_p0_any" in f["why"], f
        with patch.object(SI, "_stop_facts", side_effect=RuntimeError("x")):
            facts = SI.read_facts(db, "x", "1.0.0", "r", c, shadow=True)
        assert facts["stop_conditions_clear"]["state"] == SB.UNKNOWN
        assert facts["stop_watch_fresh"]["state"] == SB.UNKNOWN
    finally:
        _restore()


def test_the_stop_watch_only_ever_seals_deny_direction_rows():
    """Whatever it seals is an exact suspension (deny-only); with no signing key at all it
    still suspends, under the ops-token suspension seal that can never grant."""
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        _incident(db, "synthetic:p0", severity="P0")
        sealed = []
        real = sp._sign

        def watch(detail):
            sealed.append(sp._deny_only(detail))
            return real(detail)

        def no_grant(*_a, **_k):
            raise AssertionError("the stop watch tried to sign an owner grant")

        with _Clear(), patch.object(sp, "_sign", watch), \
                patch.object(owner_grant_keys, "sign", no_grant):
            assert ST.run(db, now=NOW)["suspended"] == 1
        assert sealed and all(sealed), sealed
        # No signing key: the suspension is still written, under the deny-only HMAC.
        db2, c2 = _db(), content()
        a2 = _approve(db2, c2)
        _activate_raw(db2, a2, c2)
        _incident(db2, "synthetic:p0", severity="P0")

        def keyless(_d):
            raise ValueError("standing policy signing key unavailable")

        with _Clear(), patch.object(sp, "_sign", keyless):
            assert ST.run(db2, now=NOW)["suspended"] == 1
        with db2.session() as s:
            row = s.scalar(select(AuditLog).where(AuditLog.action == sp.SUSPENDED))
            assert str((row.detail or {}).get("seal", "")).startswith("h:"), row.detail
        with db.session() as s:
            written = {r.action for r in s.scalars(select(AuditLog).where(
                AuditLog.actor == ST.ACTOR))}
        assert written <= {sp.SUSPENDED, ST.READING}, written
    finally:
        _restore()


def test_the_issuer_sees_a_read_back_publish_incomplete_incident():
    """Check 16 reads the read-back incident (`etsy_ops.open_publish_incomplete`) as well as
    the publish job's own row: before this increment it read only the audit row."""
    from brambleloop.ops import standing_issuer as SI

    try:
        db = _db()
        assert SI._no_publish_incomplete(db, SLUG, "1.0.0")["state"] == SB.PASS
        _incident(db, f"store.publish_incomplete:{SLUG}@1.0.0", resolved=True)
        out = SI._no_publish_incomplete(db, SLUG, "1.0.0")
        assert out["state"] == SB.FAIL and "read-back incident" in out["why"], out
        assert SI._no_publish_incomplete(db, SLUG, "2.0.0")["state"] == SB.PASS
    finally:
        _restore()


def test_the_job_is_an_observe_cadence_every_five_minutes():
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.authority.classes import JOB_CLASS, ActionClass
    from brambleloop.runtime import pipeline  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import CADENCES, handlers

    assert JOB_CLASS["policy.stop_watch"] == ActionClass.OBSERVE
    assert [p for _c, _a, job, p in CADENCES if job == "policy.stop_watch"] == [300]
    assert handlers.get("policy.stop_watch") is not None
    publishing = next(a for a in DEFAULT_AGENTS if a["name"] == "publishing")
    assert "policy.stop_watch" in publishing["allowed_job_types"]


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
