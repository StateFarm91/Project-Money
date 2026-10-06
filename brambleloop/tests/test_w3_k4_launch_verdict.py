"""Wave-3 K4: launch verdict, demand capture and the visibility view.

F-300  a phase move up requires the launch readiness verdict, evaluated at transition time,
       answered as six questions; owner authority still first; rollback never needs readiness.
F-275  demand-capture plan per opening product (gates the transition).
F-276  Christmas search-compression checkpoints.
F-281  first-30-day learning plan (day 1/3/7/14/30) and its review snapshots.
F-286  launch success is multi-signal.
F-287  visibility view / Command Center provider contract.
F-288  recommendations carry evidence, listings, mechanism, cost, confidence, rollback.
F-289  traffic sources stay separate.

Hermetic: temporary SQLite, synthetic owner credential, no provider, model or network call.
One test runs the real (slow, ~1 min) readiness evaluation through the real transition path.
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core import phase as P  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Listing  # noqa: E402
from brambleloop.launch import demand, recommendations as R, success, visibility  # noqa: E402
from brambleloop.launch import readiness as rd  # noqa: E402
from phase_fixture import (record_phase_path, synthetic_evidence,  # noqa: E402
                           synthetic_readiness)

TOKEN = "w3-k4-synthetic-owner-credential-not-a-secret"
ENV = {"BRAMBLELOOP_OPS_TOKEN": TOKEN}


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/k4.sqlite")
    db.create_all()
    return db


def _transitions(db) -> list:
    with db.session() as s:
        return [dict(r.detail) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == P.TRANSITION).order_by(AuditLog.id))]


def _refused(fn, needle) -> str:
    try:
        fn()
    except ValueError as exc:
        assert needle in str(exc), exc
        return str(exc)
    raise AssertionError("accepted")


def _not_ready(db, to):
    return {"ready": False, "failing": ["findable:catalogue_depth"]}


# ---- F-300: the phase gate ---------------------------------------------------------------

def test_F300_real_readiness_evaluated_at_transition_refuses_shadow_to_staging():
    """The real path: no evaluator injected, the live verdict runs and refuses."""
    db = _db()
    seen = {}
    real = P.live_readiness

    def spy(db_, to):
        seen["verdict"] = real(db_, to)
        return seen["verdict"]

    with patch.dict(os.environ, ENV), patch.object(P, "live_readiness", spy):
        msg = _refused(lambda: P.record_transition(
            db, authorization=TOKEN, to="staging", reason="go",
            evidence_refs=synthetic_evidence(db)), "not ready at transition time")
    assert "requires readiness.ready" in msg
    assert _transitions(db) == []
    v = seen["verdict"]
    assert v["ready"] is False and v["assessed_at_phase"] == "staging"
    assert set(v["questions"]) == {k for k, _q, _s in rd.QUESTIONS} | {rd.OTHER_HARD_GATES}
    assert "phase" in v["excluded"] and v["demand_capture"]["complete"] is False
    assert any(f.startswith("findable:") for f in v["failing"]), v["failing"]
    # the self-satisfied requirement is excluded, never counted as failing
    assert not any(f.endswith(":phase") for f in v["failing"])


def test_F300_every_upward_step_requires_ready_and_ready_must_be_true():
    db = _db()
    with patch.dict(os.environ, ENV):
        for target in P.ORDER[1:]:
            _refused(lambda: P.record_transition(
                db, authorization=TOKEN, to=target, reason="up",
                evidence_refs=synthetic_evidence(db), readiness_verdict=_not_ready),
                "findable:catalogue_depth")
            for bad in (lambda d, t: {"ready": "yes"}, lambda d, t: None,
                        lambda d, t: {"ready": 1}):
                _refused(lambda: P.record_transition(
                    db, authorization=TOKEN, to=target, reason="up",
                    evidence_refs=synthetic_evidence(db), readiness_verdict=bad),
                    "not ready at transition time")

            def boom(d, t):
                raise RuntimeError("assessment crashed")

            _refused(lambda: P.record_transition(
                db, authorization=TOKEN, to=target, reason="up",
                evidence_refs=synthetic_evidence(db), readiness_verdict=boom),
                "could not be evaluated")
            P.record_transition(db, authorization=TOKEN, to=target, reason="up",
                                evidence_refs=synthetic_evidence(db),
                                readiness_verdict=synthetic_readiness)
    rows = _transitions(db)
    assert [r["to"] for r in rows] == list(P.ORDER[1:])
    for r in rows:
        rat = r["readiness_at_transition"]
        assert rat["ready"] is True and rat["evaluator"].endswith("synthetic_readiness")
        assert rat["synthetic_fixture"] is True


def test_F300_owner_authority_and_cheap_checks_run_before_readiness():
    db = _db()

    def must_not_run(d, t):
        raise AssertionError("readiness evaluated before authority / preconditions")

    with patch.dict(os.environ, ENV), patch.object(P, "live_readiness", must_not_run):
        for bad_auth in ("", "Bearer wrong"):
            try:
                P.record_transition(db, authorization=bad_auth, to="staging", reason="x",
                                    evidence_refs=synthetic_evidence(db))
                raise AssertionError("accepted without the owner credential")
            except opsauth.OpsAuthRefused:
                pass
        _refused(lambda: P.record_transition(db, authorization=TOKEN, to="limited_production",
                                             reason="skip", evidence_refs=synthetic_evidence(db)),
                 "one step at a time")
        _refused(lambda: P.record_transition(db, authorization=TOKEN, to="staging",
                                             reason="x", evidence_refs={}), "must cite")
        _refused(lambda: P.record_transition(db, authorization=TOKEN, to="staging", reason="x",
                                             evidence_refs={"readiness": "999998", "rollback": "999999"}),
                 "does not resolve")
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)
        try:
            P.record_transition(db, authorization=TOKEN, to="staging", reason="x",
                                evidence_refs={}, readiness_verdict=must_not_run)
            raise AssertionError("accepted with no owner credential configured")
        except opsauth.OpsAuthUnavailable:
            pass


def test_F300_rollback_to_shadow_never_requires_readiness():
    db = _db()

    def must_not_run(d, t):
        raise AssertionError("a rollback evaluated readiness")

    with patch.dict(os.environ, ENV):
        record_phase_path(db, TOKEN, "production")
        with patch.object(P, "live_readiness", must_not_run):
            out = P.record_transition(db, authorization=TOKEN, to="shadow",
                                      reason="incident rollback")
            assert out["direction"] == "down" and "readiness_at_transition" not in out
            record_phase_path(db, TOKEN, "limited_production")
            P.record_transition(db, authorization=TOKEN, to="staging", reason="step down")
            P.record_transition(db, authorization=TOKEN, to="shadow", reason="all the way")
        # over a broken chain the rebase to shadow also needs no readiness
        with db.session() as s:
            first = s.scalar(select(AuditLog).where(AuditLog.action == P.TRANSITION)
                             .order_by(AuditLog.id).limit(1))
            s.add(AuditLog(actor=first.actor, action=first.action, artifact=first.artifact,
                           detail=copy.deepcopy(first.detail)))
        with patch.object(P, "live_readiness", must_not_run):
            assert P.record_transition(db, authorization=TOKEN, to="shadow",
                                       reason="rebase")["rebase"] is True


def test_F300_verdict_is_sealed_into_the_chain():
    db = _db()
    env = {P.ENV_VAR: "staging"}
    with patch.dict(os.environ, ENV):
        record_phase_path(db, TOKEN, "staging")
        assert P.resolve(db, env)["phase"] == "staging"
        with db.session() as s:
            row = s.scalar(select(AuditLog).where(AuditLog.action == P.TRANSITION))
            d = copy.deepcopy(row.detail)
            d["readiness_at_transition"]["ready"] = "edited"
            row.detail = d
        r = P.resolve(db, env)
        assert r["phase"] == "shadow" and r["record"]["valid"] is False, r


def test_F300_phase_changed_during_evaluation_is_refused():
    db = _db()
    with patch.dict(os.environ, ENV):
        record_phase_path(db, TOKEN, "staging")

        def rollback_meanwhile(d, t):
            P.record_transition(d, authorization=TOKEN, to="shadow", reason="meanwhile")
            return synthetic_readiness(d, t)

        _refused(lambda: P.record_transition(
            db, authorization=TOKEN, to="limited_production", reason="up",
            evidence_refs=synthetic_evidence(db), readiness_verdict=rollback_meanwhile),
            "changed")
    assert [r["to"] for r in _transitions(db)] == ["staging", "shadow"]


def test_F300_six_questions_group_without_changing_the_verdict():
    reqs = [rd.Requirement(key=k, description=k, ready=True)
            for _q, _t, keys in rd.QUESTIONS for k in keys]
    reqs.append(rd.Requirement(key="brand_new_gate", description="x", ready=False,
                               blocked_by="build"))
    r = rd.Readiness(requirements=reqs)
    q = rd.questions(r, {"status": "PROVEN"})
    assert q["ready"] is False and r.ready is False
    assert q["answers"][rd.OTHER_HARD_GATES]["failing"] == ["brand_new_gate"]
    assert all(q["answers"][k]["pass"] for k, _t, _s in rd.QUESTIONS)
    r2 = rd.Readiness(requirements=reqs[:-1])
    assert rd.questions(r2, {"status": "PROVEN"})["ready"] is True
    assert rd.questions(r2, {"status": "NOT PROVEN"})["ready"] is False
    # analytics baseline failing answers "no" to both findable and ads-measurable
    reqs3 = [rd.Requirement(key=x.key, description=x.key, ready=x.key != "analytics_baseline")
             for x in reqs[:-1]]
    a = rd.questions(rd.Readiness(requirements=reqs3), {"status": "PROVEN"})["answers"]
    assert not a["findable"]["pass"] and not a["ads_measurable_bounded"]["pass"]
    assert a["clickable"]["pass"]


# ---- F-275 / F-281 / F-276 ------------------------------------------------------------------

def _listing(db, slug="granny-square-blanket", tags=("granny square blanket",)):
    with db.session() as s:
        s.add(Listing(product_slug=slug, version="1.0.0", title=f"{slug} pattern",
                      description="d", tags=list(tags), price_cad=9.0))


def test_F275_demand_capture_plan_names_every_gap_and_gates_the_transition():
    db = _db()
    empty = demand.capture_plan(db)
    assert empty["complete"] is False and empty["products_count"] == 0
    _listing(db)
    plan = demand.capture_plan(db)
    p = plan["products"][0]
    assert set(p) >= {"search_intents", "seasonal_runway", "storefront_placement",
                      "organic_readiness", "ads_plan", "measurement_checkpoints"}
    assert p["search_intents"] == ["granny square blanket"]
    assert [c["day"] for c in p["measurement_checkpoints"]] == list(demand.REVIEW_DAYS)
    joined = " ".join(p["gaps"])
    assert "no coverage baseline" in joined and "seasonal_runway" in joined
    assert "organic_readiness" in joined and plan["complete"] is False
    with db.session() as s:
        s.add(AuditLog(actor="o", action="listing.query_portfolio",
                       artifact="granny-square-blanket@1.0.0", detail={}))
        s.add(AuditLog(actor="o", action="launch.planned", artifact="granny-square-blanket",
                       detail={"launch_on": "2026-10-20", "compressed": True}))
    p2 = demand.capture_plan(db)["products"][0]
    assert p2["seasonal_runway"]["launch_on"] == "2026-10-20"
    assert not any("baseline" in g or "seasonal_runway" in g for g in p2["gaps"])


def test_F281_learning_plan_is_predefined_and_reviews_snapshot_once():
    db = _db()
    plan = demand.learning_plan(db)
    assert [r["day"] for r in plan["reviews"]] == [1, 3, 7, 14, 30]
    assert all(r["state"] == "SCHEDULED_RELATIVE" for r in plan["reviews"])
    assert set(plan["metrics"]) == {"impressions", "clicks", "favorites", "sales",
                                    "conversion", "search_terms", "ads", "support_friction",
                                    "contribution"}
    assert demand.record_due_reviews(db) == []
    with patch.dict(os.environ, ENV):
        record_phase_path(db, TOKEN, "limited_production")
        started = demand.launch_started_at(db)
        assert started is not None
        later = started + timedelta(days=3, hours=1)
        assert demand.record_due_reviews(db, now=later) == [1, 3]
        assert demand.record_due_reviews(db, now=later) == []
        states = {r["day"]: r["state"]
                  for r in demand.learning_plan(db, now=later)["reviews"]}
    # without the owner credential no transition verifies, so there is no recorded launch
    assert demand.launch_started_at(db) is None
    assert states == {1: "REVIEWED", 3: "REVIEWED", 7: "SCHEDULED", 14: "SCHEDULED",
                      30: "SCHEDULED"}
    with db.session() as s:
        snap = s.scalar(select(AuditLog).where(AuditLog.action == demand.REVIEW_ACTION)).detail
    # nothing observed: UNMEASURED, never zero
    assert snap["metrics"]["impressions"]["status"] == "UNMEASURED"
    assert snap["metrics"]["favorites"]["status"] == "UNMEASURED"


def test_F276_christmas_checkpoints_compress_never_relax():
    db = _db()
    early = demand.christmas_checkpoints(db, today=date(2026, 6, 1))
    assert early["compressed"] is False
    assert all(c["state"] in ("OPEN", "NOT_AUTHORISED") for c in early["checkpoints"])
    late = demand.christmas_checkpoints(db, today=date(2026, 10, 6))
    assert "query_strategy" in late["late"] and late["compressed"] is True
    assert "never relaxes" in late["urgency_rule"]
    keys = [c["checkpoint"] for c in late["checkpoints"]]
    assert keys == ["query_strategy", "gallery", "listings_indexed", "storefront",
                    "ads_learning", "engagement_window"]
    opens = date.fromisoformat(late["window_opens"])
    assert opens < date.fromisoformat(late["peak"]) < date(2026, 12, 25)
    # rolls to next year after Christmas
    assert demand.christmas_checkpoints(db, today=date(2026, 12, 28))["peak"] > "2027"


# ---- F-288 / F-286 / F-289 / F-287 --------------------------------------------------------

def test_F288_recommendations_refuse_vague_and_incomplete():
    good = R.Recommendation(
        action="Challenge the hero frame of granny-square@1 at thumbnail size",
        evidence=["stats"], affected_listings=["granny-square@1"], mechanism="m",
        cost_cad=0, confidence="medium", rollback="restore previous hero")
    assert R.validate(good).cost_cad == 0.0
    for bad in ("improve SEO", "Optimise listings.", "boost visibility", "fix it"):
        try:
            R.validate({**good.to_dict(), "action": bad})
            raise AssertionError(f"accepted {bad!r}")
        except R.RecommendationRefused:
            pass
    for missing in R.REQUIRED:
        d = good.to_dict()
        d[missing] = [] if missing in ("evidence", "affected_listings") else ""
        try:
            R.validate(d)
            raise AssertionError(f"accepted without {missing}")
        except R.RecommendationRefused:
            pass
    try:
        R.validate({**good.to_dict(), "confidence": "certain"})
        raise AssertionError("accepted an unknown confidence")
    except R.RecommendationRefused:
        pass


def test_F288_routing_follows_the_acceptance_tests_and_from_stats_is_validated():
    assert R.route(50, 5, 0)[0] == R.EXPOSURE            # inadequate exposure: UNMEASURED
    assert R.route(5000, 20, 0)[0] == R.CLICK            # impressions, weak clicks
    assert R.route(5000, 400, 0)[0] == R.CONVERSION      # healthy clicks, no sales
    assert R.route(5000, 400, 30)[0] == R.HOLD
    db = _db()
    assert R.from_stats(db)["status"] == "UNMEASURED"
    _listing(db)
    from brambleloop.runtime import growth_ops

    growth_ops.record(db, visibility.STATS_KIND, "2026-10-06", {
        "period_key": "2026-10-06", "joined": {
            "terms": [{"term": "granny square blanket", "impressions": 5000, "visits": 20,
                       "orders": 0},
                      {"term": "unrelated phrase", "impressions": 9000, "visits": 10,
                       "orders": 0}],
            "totals": {"impressions": 14000, "visits": 30, "orders": 0}}})
    out = R.from_stats(db)
    assert out["status"] == "measured" and len(out["recommendations"]) == 1
    rec = out["recommendations"][0]
    assert rec["route"] == R.CLICK and rec["affected_listings"] == ["granny-square-blanket@1.0.0"]
    assert rec["rollback"] and rec["mechanism"] and rec["evidence"]
    assert out["terms_not_linked_to_a_listing"] == ["unrelated phrase"]


def test_F286_success_needs_every_signal_not_live():
    db = _db()
    v = success.verdict(db)
    assert v["success"] is False and set(v["signals"]) == set(success.SIGNALS)
    assert "visibility" in v["unmeasured"]
    with db.session() as s:
        s.add(Listing(product_slug="x", version="1", title="t", description="d", tags=[],
                      price_cad=5.0, state="published", etsy_listing_id="123"))
    v = success.verdict(db)
    assert v["success"] is False and v["context_not_signals"]["live_listings"] == 1
    assert v["signals"]["product_truth"]["status"] == "PASS"


def test_F289_F287_visibility_provider_contract_and_separate_sources():
    db = _db()
    s = visibility.summary(db)
    assert set(s) >= {"status", "as_of", "basis", "items", "sources"}
    assert s["status"] == "UNKNOWN"   # launch.readiness never ran
    assert [i["key"] for i in s["items"]] == [k for k, _ in visibility.SECTIONS]
    ts = s["detail"]["sections"]["traffic_sources"]
    assert list(ts["channels"]) == ["etsy_organic", "etsy_ads", "offsite_ads", "owned_direct",
                                    "unattributed"]
    with db.session() as sess:
        sess.add(AuditLog(actor="orchestrator", action="launch.assessed",
                          detail={"ready": False, "questions": {"ready": False}}))
    s = visibility.summary(db)
    assert s["status"] == "BLOCKED"
    assert s["detail"]["sections"]["launch_verdict"]["state"] == "FAIL"
    with db.session() as sess:
        try:
            visibility.summary(sess)
            raise AssertionError("a bare Session was accepted")
        except AttributeError:
            pass


def test_routes_are_owner_only_and_registered_operator_gets():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from brambleloop.app import phase_api, security

    assert {"/api/owner/phase/verdict", "/api/owner/phase/visibility"} <= \
        security.OPERATOR_GET_ROUTES
    db = _db()
    app = FastAPI()
    app.include_router(phase_api.make_router(db))
    api = TestClient(app)
    auth = {"Authorization": f"Bearer {TOKEN}"}
    with patch.dict(os.environ, ENV), patch.object(P, "live_readiness", _not_ready):
        assert api.get("/api/owner/phase/visibility").status_code == 403
        assert api.get("/api/owner/phase/verdict").status_code == 403
        v = api.get("/api/owner/phase/visibility", headers=auth)
        assert v.status_code == 200 and "traffic_sources" in v.json()["sections"]
        r = api.get("/api/owner/phase/verdict", headers=auth).json()
        assert r["next"] == "staging" and r["verdict"]["ready"] is False
        # the transition route refuses on the live verdict
        body = {"to": "staging", "reason": "go", "evidence_refs": synthetic_evidence(db)}
        t = api.post("/api/owner/phase/transition", json=body, headers=auth)
        assert t.status_code == 409 and "readiness" in t.json()["detail"], t.text


def test_packet_renders_the_six_questions():
    from brambleloop.launch import packet as LP

    q = rd.questions(rd.Readiness(requirements=[
        rd.Requirement(key="catalogue_depth", description="c", ready=False)]), None)
    p = {"candidate_sha": "abc", "generated_at": datetime.now(timezone.utc).isoformat(),
         "verdict": "BLOCKED", "verdict_rule": "r",
         "phase": {"phase": "shadow", "env": "shadow", "recorded_phase": "shadow",
                   "agree": True},
         "products": [], "owner_queue": {"state": "FAIL", "owner_actions": [],
                                         "questions": q},
         "spend_limits": [], "recorded_suite": {}, "rollback_path": {},
         "activation_steps": []}
    md = LP.render_markdown(p)
    assert "Can buyers find it?" in md and "catalogue_depth" in md


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    only = sys.argv[1:]
    for fn in TESTS:
        if only and not any(o in fn.__name__ for o in only):
            continue
        try:
            fn()
            print("OK  ", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            import traceback

            failed += 1
            traceback.print_exc()
            print("FAIL", fn.__name__, repr(exc))
    print(f"{len(TESTS) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
