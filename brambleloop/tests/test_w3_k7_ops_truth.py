"""Wave-3 K7: ops truth -- jobs, provenance, incidents, assurance and the evidence contract.

F-337 F-338 F-343 (job watchdog / diagnosis / activity, via `ops.health.read`), F-115 F-161
F-162 F-167 (provenance invalidation, coverage, per-class graduation, backfill relevance, via
the `ops.sentinel` handler), F-168 F-195 F-392 (incidents), F-124 F-154 F-176 F-199
(assurance), F-121 F-122 F-127 F-203 F-623 F-665 (truth contract + drill, via the Command
Center provider), and the `ops.health` handler running the sweep end to end.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Incident, Job, JobStatus, Listing, OwnerAction, PatternVersion, Product)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
RESULTS: list[str] = []


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def ok(name):
    RESULTS.append(name)
    print(f"OK {name}")


# ---- jobs (F-337 / F-338 / F-343) -------------------------------------------------------

def _done(s, jt, secs, i):
    start = NOW - timedelta(hours=2, minutes=i)
    s.add(Job(agent="a", job_type=jt, status=JobStatus.DONE, inputs={"i": i}, outputs={},
              started_at=start, finished_at=start + timedelta(seconds=secs),
              created_at=start))


def test_duration_watchdog_flags_3x_and_diagnoses_without_restarting():
    from brambleloop.ops import health as H
    from brambleloop.ops import job_watch as W

    db = _db()
    with db.session() as s:
        for i in range(6):
            _done(s, "x.build", 60, i)
        s.add(Job(agent="a", job_type="x.build", status=JobStatus.RUNNING, inputs={"i": 99},
                  started_at=NOW - timedelta(minutes=10), created_at=NOW - timedelta(minutes=11),
                  lease_expires_at=NOW + timedelta(minutes=2)))
        s.add(Job(agent="a", job_type="y.rare", status=JobStatus.RUNNING, inputs={},
                  started_at=NOW - timedelta(hours=5), created_at=NOW - timedelta(hours=5)))
    with db.session() as s:
        w = W.watch(s, now=NOW)
        assert w["envelopes"]["x.build"]["median_s"] == 60.0
        assert [o["job_type"] for o in w["over_envelope"]] == ["x.build"], w
        d = w["over_envelope"][0]["diagnosis"]
        assert d["alive"] is True and d["destructive_action_taken"] is False
        assert d["verdict"] == "alive_not_advancing", d
        # Fewer than MIN_HISTORY samples: not judged, listed.
        assert [u["job_type"] for u in w["unassessable"]] == ["y.rare"]
        readings = H.read(s, runner_state={}, env={}, now=NOW, executing_worker=True,
                          from_cadence=True)
        jd = next(r for r in readings if r.signal == "job_durations")
        assert jd.state == H.DEGRADED, jd
        running = s.scalars(select(Job).where(Job.status == JobStatus.RUNNING)).all()
        assert len(running) == 2, "nothing was restarted or cancelled"
        v = H.verdict(readings)
        assert v["activity"]["state"] == W.EXECUTING, v["activity"]
    ok("F-337 3x rolling median flagged, diagnosed first, nothing restarted (via ops.health)")


def test_diagnosis_distinguishes_completed_blocked_duplicated():
    from brambleloop.ops import job_watch as W

    db = _db()
    with db.session() as s:
        dep = Job(agent="a", job_type="dep", status=JobStatus.PENDING, inputs={})
        s.add(dep)
        s.flush()
        a = Job(agent="a", job_type="t", status=JobStatus.RUNNING, inputs={"x": 1},
                outputs={"partial": True}, started_at=NOW)
        b = Job(agent="a", job_type="t2", status=JobStatus.RUNNING,
                inputs={"parent_job_id": dep.id}, started_at=NOW)
        c1 = Job(agent="a", job_type="t3", status=JobStatus.RUNNING,
                 inputs={"slug": "s", "cadence": "c1"}, started_at=NOW)
        c2 = Job(agent="a", job_type="t3", status=JobStatus.PENDING,
                 inputs={"slug": "s", "cadence": "c2"})
        s.add_all([a, b, c1, c2])
        s.flush()
        assert W.diagnose(s, a, now=NOW)["verdict"] == "completed_but_unobserved"
        assert a.outputs == {"partial": True}, "valid output is preserved"
        assert W.diagnose(s, b, now=NOW)["verdict"] == "blocked_on_dependency"
        dd = W.diagnose(s, c1, now=NOW)
        assert dd["verdict"] == "duplicated" and dd["duplicates"] == [c2.id]
    ok("F-338 completed-but-unobserved / blocked / duplicated told apart, output preserved")


def test_activity_never_counts_a_waiter_as_progress():
    from brambleloop.ops import job_watch as W

    db = _db()
    with db.session() as s:
        assert W.activity(s, now=NOW)["state"] == W.UNKNOWN
        # The health sweep running itself is not work executing.
        s.add(Job(agent="o", job_type="ops.health", status=JobStatus.RUNNING, inputs={},
                  started_at=NOW, lease_expires_at=NOW + timedelta(minutes=1)))
        s.flush()
        assert W.activity(s, now=NOW, observers_alive=1)["state"] == W.OBSERVER_WAITING
        s.add(Job(agent="a", job_type="t", status=JobStatus.DONE, inputs={}, outputs={},
                  started_at=NOW - timedelta(minutes=2), finished_at=NOW - timedelta(minutes=1)))
        s.flush()
        assert W.activity(s, now=NOW, observers_alive=1)["state"] == W.COMPLETED
        dep = Job(agent="a", job_type="dep", status=JobStatus.PENDING, inputs={})
        s.add(dep)
        s.flush()
        s.add(Job(agent="a", job_type="t2", status=JobStatus.RUNNING,
                  inputs={"wait_job_id": dep.id}, started_at=NOW,
                  lease_expires_at=NOW - timedelta(seconds=1)))
        s.flush()
        assert W.activity(s, now=NOW)["state"] == W.BLOCKED
    ok("F-343 executing/completed/observer-waiting/blocked/unknown; a waiter is not progress")


# ---- provenance (F-115 / F-161 / F-162 / F-167) ------------------------------------------

def _catalogue(db):
    with db.session() as s:
        s.add(Product(slug="hex-coaster", title="Hex"))
        s.flush()
        s.add(PatternVersion(product_id=1, version="1.0.0", cir_json={"rows": 1},
                             release_hash="a" * 64, certified=True))
        s.add(PatternVersion(product_id=1, version="2.0.0", cir_json={"rows": 2},
                             release_hash="b" * 64, certified=True))
        s.add(Listing(product_slug="hex-coaster", version="1.0.0", title="old", description="",
                      tags=[], price_cad=5.0))
        s.add(Listing(product_slug="hex-coaster", version="2.0.0", title="new", description="",
                      tags=[], price_cad=5.0))


def test_reengineering_invalidates_legacy_unprovenanced_artefacts():
    from brambleloop.ops import artefacts as P

    db = _db()
    _catalogue(db)
    with db.session() as s:
        vs = P.check(s, current=P.current_from_db(s), expected=P.expected_from_db(s))
    old = [v for v in vs if "@1.0.0" in v.artefact_key]
    new = [v for v in vs if "@2.0.0" in v.artefact_key]
    assert old and new
    assert all(P.retired(v) and v.to_dict()["invalidated"] for v in old), \
        [v.to_dict() for v in old]
    assert {v.state for v in new} == {P.UNPROVEN} and not any(P.retired(v) for v in new)
    assert all(v.state != P.FRESH for v in vs)
    with db.session() as s:
        g = P.graduation(s, current=P.current_from_db(s), expected=P.expected_from_db(s))
    # Retired legacy output leaves the instrumentation backlog; current output stays in it.
    assert g["unproven"] == len(new), (g["unproven"], len(new))
    assert sum(c["invalidated"] for c in g["coverage"]["by_class"].values()) == len(old)
    ok(f"F-115 {len(old)} legacy artefact(s) of a re-engineered design invalidated")


def test_coverage_ratio_and_per_class_graduation_via_sentinel():
    from brambleloop.agents.registry import Registry
    from brambleloop.ops import artefacts as P
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.release import handle_stale_artefact_sentinel
    from brambleloop.runtime.worker import JobContext

    db = _db()
    _catalogue(db)
    Registry(db).seed_defaults()
    with db.session() as s:
        cur = P.current_from_db(s)
        P.record(s, artefact_class="certificate", artefact_key="hex-coaster@2.0.0",
                 product_slug="hex-coaster",
                 inputs={"cir:hex-coaster": cur["cir:hex-coaster"],
                         "release:hex-coaster": cur["release:hex-coaster"]})
    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("orchestrator", "ops.sentinel", {}), db=db,
                     queue=queue, registry=Registry(db), phase=None)
    out = handle_stale_artefact_sentinel(ctx)
    assert out["coverage"]["denominator"] > out["coverage"]["numerator"] >= 1, out["coverage"]
    assert "certificate" in out["graduated_now"], out["graduated_now"]
    with db.session() as s:
        g = P.graduation(s, current=P.current_from_db(s), expected=P.expected_from_db(s))
    assert g["classes"]["certificate"]["absence_blocks"] is True
    assert g["coverage"]["by_class"]["pricing"]["ratio"] in (0.0,)
    assert g["coverage"]["by_class"]["twin"]["ratio"] == "UNMEASURED"
    # Graduated class: a certified release with no row now blocks its product.
    with db.session() as s:
        s.add(Product(slug="tri-mat", title="Tri"))
        s.flush()
        pid = s.scalar(select(Product.id).where(Product.slug == "tri-mat"))
        s.add(PatternVersion(product_id=pid, version="1.0.0", cir_json={"r": 3},
                             release_hash="c" * 64, certified=True))
    ctx = JobContext(job=queue.enqueue("orchestrator", "ops.sentinel", {"n": 2}), db=db,
                     queue=queue, registry=Registry(db), phase=None)
    out = handle_stale_artefact_sentinel(ctx)
    assert "tri-mat" in out["publication_blocked"], out["publication_blocked"]
    assert "hex-coaster" not in out["publication_blocked"], "ungraduated classes stay backlog"
    ok("F-161 coverage numerator/denominator by class; F-162 per-class graduation blocks")


def test_backfill_reports_launch_relevance_and_retirement():
    from brambleloop.ops import backfill

    db = _db()
    _catalogue(db)
    with db.session() as s:
        out = backfill.run(s, dry_run=True)
    rel = out["relevance"]
    assert rel["counts"]["retired"] >= 1, rel
    assert sum(rel["counts"].values()) == sum(out["left_unproven"].values())
    assert "hexagon-coaster-set" in rel["launch_scope"]
    ok(f"F-167 backfill split launch-relevant/retired/other: {rel['counts']}")


# ---- incidents (F-168 / F-195 / F-392) ---------------------------------------------------

def test_incident_actionability_and_owner_path():
    from brambleloop.ops import incident_lifecycle as L

    db = _db()
    with db.session() as s:
        s.add(Incident(signature="policy_stale:fees", severity="P2", summary="s",
                       detail={"last_seen": (NOW - timedelta(hours=1)).isoformat()}))
        s.add(Incident(signature="mystery:thing", severity="P3", summary="s",
                       at=NOW - timedelta(days=5), detail={}))
    with db.session() as s:
        snap = L.snapshot(s, now=NOW)
    rows = {r["signature"]: r for k in snap["by_kind"].values() for r in k["open"]}
    assert rows
    pol = rows["policy_stale:fees"]
    assert pol["remediation_owner"] == "owner" and "/api/policy/snapshot" in pol[
        "remediation_path"] and pol["applicability"] == "current"
    mys = rows["mystery:thing"]
    assert mys["needs_owner_path"] and mys["applicability"] == "UNCONFIRMED"
    assert snap["needs_owner_path"] == ["mystery:thing"]
    assert snap["unconfirmed"] == ["mystery:thing"]
    from brambleloop.app.command_center import readers
    cc = readers.incidents(db)
    assert all("remediation_owner" in i and "last_confirmed" in i for i in cc["items"])
    ok("F-195 incidents carry last-confirmed, applicability and remediation owner/path")


def test_incident_learning_and_recurrence():
    from brambleloop.ops import incident_lifecycle as L

    db = _db()
    with db.session() as s:
        s.add(Incident(signature="spend-anomaly:x", severity="P1", summary="s",
                       resolved=True, at=NOW - timedelta(days=2),
                       detail={"resolution": "reversed", "resolved_at": NOW.isoformat()}))
    with db.session() as s:
        ln = L.learning(s, now=NOW)
        assert [g["signature"] for g in ln["gaps"]] == ["spend-anomaly:x"]
        iid = s.scalar(select(Incident.id))
        try:
            L.record_learning(s, iid, root_cause="r", prevention_ref="", regression_ref="t")
            raise AssertionError("blank prevention accepted")
        except ValueError:
            pass
        L.record_learning(s, iid, root_cause="ceiling read the wrong table",
                          prevention_ref="finance.spend_policy ceiling", now=NOW,
                          regression_ref="tests/test_spend_governance.py")
    with db.session() as s:
        assert L.learning(s, now=NOW)["gaps"] == []
        s.add(Incident(signature="spend-anomaly:y", severity="P1", summary="again",
                       at=NOW + timedelta(minutes=1), detail={}))
    with db.session() as s:
        rec = L.learning(s, now=NOW + timedelta(minutes=2))["recurred_after_prevention"]
    assert [r["signature"] for r in rec] == ["spend-anomaly:y"], rec
    ok("F-392 learning required (root cause/prevention/regression); recurrence surfaced")


def test_systemic_halt_escalates_and_scopes_back():
    from brambleloop.gates.incidents import IncidentTracker
    from brambleloop.ops import incident_lifecycle as L

    db = _db()
    with db.session() as s:
        for slug in ("a", "b", "c", "d"):
            s.add(Product(slug=slug, title=slug))
        s.add(Incident(signature="stale-artefact:pdf:a", product_slug="a", severity="P1",
                       halts_publication=True, summary="s"))
    tracker = IncidentTracker(db)
    with db.session() as s:
        assert L.escalate_systemic(s, now=NOW)["systemic"] is False
    assert tracker.publication_halted("a") and not tracker.publication_halted("d")
    with db.session() as s:
        for slug in ("b", "c"):
            s.add(Incident(signature=f"stale-artefact:pdf:{slug}", product_slug=slug,
                           severity="P1", halts_publication=True, summary="s"))
    with db.session() as s:
        ev = L.escalate_systemic(s, now=NOW)
    assert ev["systemic"] and ev["opened"], ev
    assert tracker.publication_halted("d"), "systemic corruption halts every product"
    with db.session() as s:
        for row in s.scalars(select(Incident).where(Incident.product_slug.in_(("b", "c")))):
            row.resolved = True
    with db.session() as s:
        ev = L.escalate_systemic(s, now=NOW)
    assert not ev["systemic"] and ev["resolved"] == [L.SYSTEMIC_SIGNATURE]
    assert not tracker.publication_halted("d") and tracker.publication_halted("a")
    ok("F-168 halts stay per product; systemic evidence escalates company-wide and back")


# ---- assurance (F-124 / F-154 / F-176 / F-199) -------------------------------------------

def test_security_controls_configured_but_unproven_is_unavailable():
    from brambleloop.app.command_center import auth as cc_auth
    from brambleloop.ops import assurance as A

    db = _db()
    env = {"BRAMBLELOOP_OPS_TOKEN": "t" * 32,
           "BRAMBLELOOP_OWNER_PASSPHRASE_HASH": cc_auth.hash_passphrase("correct horse k7",
                                                                     iterations=100_000)}
    out = A.security_controls(db, env)
    by = {c["control"]: c for c in out["controls"]}
    assert by
    assert by["operator_credential"]["state"] == A.AVAILABLE
    assert by["default_deny_mutations"]["state"] == A.AVAILABLE
    assert by["csp_headers"]["state"] == A.AVAILABLE, by["csp_headers"]
    assert by["offsite_backup"]["state"] == A.UNAVAILABLE
    assert by["boot_guard"]["state"] == "NOT-APPLICABLE"
    login = by["owner_login"]
    assert login["configured"] is True
    assert login["state"] == A.UNPROVEN and not login["available"], login
    assert "owner_login" in out["unavailable"]
    short = A.security_controls(db, {"BRAMBLELOOP_OPS_TOKEN": "short"})
    sc = {c["control"]: c for c in short["controls"]}["operator_credential"]
    assert sc["configured"] and sc["state"] == A.UNAVAILABLE
    ok("F-154 controls probed functionally; configured-but-unproven reported unavailable")


def test_postconditions_read_back():
    from brambleloop.ops import assurance as A

    db = _db()
    first = {p["postcondition"]: p for p in A.postconditions(db, {})["postconditions"]}
    assert first
    assert first["restore_digest_matched"]["state"] == "NOT-YET-OBSERVED"
    assert first["jobs_completed"]["state"] == "NOT-YET-OBSERVED"
    assert first["deployed_tree_recorded"]["state"] == "NOT-APPLICABLE"
    with db.session() as s:
        s.add(Job(agent="a", job_type="t", status=JobStatus.DONE, inputs={}, outputs=None,
                  created_at=NOW))
        s.add(AuditLog(actor="w", action="continuity.verified", artifact="x", detail={}))
    out = A.postconditions(db, {})
    by = {p["postcondition"]: p for p in out["postconditions"]}
    assert by["jobs_completed"]["state"] == A.VIOLATED and out["status"] == "DEGRADED"
    assert by["restore_digest_matched"]["state"] == A.VERIFIED
    ok("F-124 postconditions read back; DONE-without-outputs is VIOLATED, never assumed")


def test_rollback_baseline_names_missing_components():
    from brambleloop.ops import assurance as A

    db = _db()
    b = A.rollback_baseline(db, {"BRAMBLELOOP_PHASE": "shadow", "ETSY_API_KEY": "secret-ish"})
    comp = b["components"]
    assert comp["schema"]["ok"] and comp["schema"]["tables"] > 10
    assert comp["config_names"]["names"] == ["BRAMBLELOOP_PHASE", "ETSY_API_KEY"]
    assert "secret-ish" not in repr(b), "config values never enter the baseline"
    assert "restore_proof" in b["missing"] and "code_sha" in b["missing"]
    assert b["recoverable"] is False
    r1 = A.record_baseline(db, {"BRAMBLELOOP_PHASE": "shadow"})
    r2 = A.record_baseline(db, {"BRAMBLELOOP_PHASE": "shadow"})
    assert r1["recorded"] and not r2["recorded"]
    ok(f"F-176 baseline digest recorded once; missing named: {b['missing']}")


def test_readiness_reproof_fails_a_stale_ready_verdict():
    from brambleloop.ops import assurance as A

    db = _db()
    assert A.readiness_reproof(db, survivors=[])["status"] == "UNKNOWN"
    with db.session() as s:
        s.add(AuditLog(actor="w", action="launch.assessed", artifact="launch",
                       detail={"ready": True}))
        s.add(Product(slug="p", title="p"))
        s.flush()
        s.add(PatternVersion(product_id=1, version="1.0.0", cir_json={}, release_hash="d" * 64,
                             certified=True, certificate={}))
    r = A.readiness_reproof(db, survivors=[])
    assert r["status"] == "BLOCKED" and r["reproof_failures"], r
    assert r["products"][0]["launch_cleared"] is False and "gauge_standard" in r[
        "products"][0]["failing"]
    ok("F-199 a past ready verdict the current standard no longer supports fails re-proof")


# ---- truth contract (F-121 / F-122 / F-127 / F-203 / F-623 / F-665) ----------------------

def test_vocabulary_rate_and_claims():
    from brambleloop.ops import truth as T

    assert T.rate(0, 0) == T.UNMEASURED and T.rate(0, 0, never_observed=True) == \
        T.NOT_YET_OBSERVED
    assert T.rate(1, 4) == 0.25 and T.rate(T.UNKNOWN, 3) == T.UNKNOWN
    assert len(T.NON_VALUES) == 5 and all(T.is_non_value(v) for v in T.NON_VALUES)
    assert not T.is_non_value(0) and not T.is_non_value(False)
    assert T.normalise("NOT_YET_WALKED") == T.NOT_YET_WALKED
    for kinds in ([], [{"kind": "configuration", "ref": "ETSY_API_KEY"}],
                  [{"kind": "code_exists", "ref": "x.py"}, {"kind": "no_errors", "ref": "log"}]):
        try:
            T.claim("etsy works", "OK", kinds)
        except T.ClaimRefused:
            continue
        raise AssertionError(kinds)
    T.claim("etsy works", "OK", [{"kind": "probe", "ref": "audit_log:7"}])
    T.claim("etsy unknown", "UNKNOWN", [])
    v = T.audit_summary("p", {"status": "OK", "sources": [], "items": [
        {"conversion_rate": 0.0, "visits": 0}]})
    assert {x["violation"] for x in v} == {"OK with no sources (F-121)",
                                           "0 rate on a zero denominator (F-122)"}, v
    w = T.observation_window([{"at": "2026-10-01T00:00:00+00:00"},
                              {"as_of": "2026-10-06T00:00:00+00:00"}])
    assert w["mixed_snapshot"] is True
    assert T.observation_window([{"x": 1}])["mixed_snapshot"] is None
    ok("F-127/F-122/F-121/F-203 shared non-values, rate, claim contract, snapshot window")


def test_cc_provider_drill_and_routes():
    from brambleloop.app.command_center import providers, tabs
    from brambleloop.ops import truth as T

    db = _db()
    out = providers.call("ops_truth", db)
    assert out["provider"] == "brambleloop.ops.truth.summary", out.get("reason")
    assert out["status"] in providers.STATUSES and out["items"] and out["sources"]
    secs = out["sections"]
    for k in ("owner_inventory", "owner_lifecycle", "data_gates", "tester_roster",
              "security_controls", "postconditions", "rollback_baseline",
              "provenance_coverage", "jobs", "incidents", "contract_audit"):
        assert k in secs and not str(secs[k].get("reason", "")).endswith("unreadable"), (
            k, secs[k].get("reason"))
    assert "observation_window" in out
    assert tabs.operations(db)["sections"]["truth"]["provider"].endswith("truth.summary")
    d = T.drill(db, "ops_truth", 0)
    ev = d["items"][0]["evidence"]
    for f in ("source", "timestamp", "transformation", "confidence", "reconciliation",
              "external_ids", "timestamp_basis"):
        assert f in ev, f
    assert T.drill(db, "nope", 0)["status"] == "UNKNOWN"
    # Routes exist under the owner-session prefix (default-deny for the whole prefix).
    from brambleloop.app import security
    from brambleloop.app.command_center.api import make_router

    paths = {getattr(r, "path", None) for r in make_router(db).routes}
    assert {"/api/cc/truth", "/api/cc/drill"} <= paths, paths
    assert security.owner_session_route("/api/cc/truth")
    assert security.owner_session_route("/api/cc/drill")
    ok("F-623/F-665 provider via Command Center; drill exposes the full evidence envelope")


def test_health_handler_runs_the_truth_sweep():
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.release import handle_health_sweep
    from brambleloop.runtime.worker import JobContext

    db = _db()
    Registry(db).seed_defaults()
    with db.session() as s:
        s.add(OwnerAction(requirement_key="lapsed", action="read it", reason="r",
                          expires_at=NOW - timedelta(minutes=1)))
        s.add(Job(agent="a", job_type="t", status=JobStatus.DONE, inputs={}, outputs=None,
                  created_at=NOW))
    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("orchestrator", "ops.health",
                                       {"cadence": "health_sweep"}),
                     db=db, queue=queue, registry=Registry(db), phase=None)
    out = handle_health_sweep(ctx)
    t = out["truth"]
    assert out["activity"] in ("work_executing", "work_completed", "observer_waiting",
                               "blocked", "unknown")
    assert len(t["owner_actions"]["expired"]) == 1, t
    assert t["postconditions"]["violated"] == ["jobs_completed"], t["postconditions"]
    assert t["rollback_baseline"]["recorded"] is True
    assert "systemic" in t and "error" not in t["systemic"], t["systemic"]
    with db.session() as s:
        inc = s.scalar(select(Incident).where(
            Incident.signature == "postcondition:jobs_completed"))
        assert inc is not None and not inc.resolved
        assert s.scalar(select(AuditLog).where(AuditLog.action == "ops.truth.sweep"))
    ok("runtime: the ops.health cadence handler runs the K7 sweep end to end")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert tests
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(RESULTS)} passed, {failed} failed")
    sys.exit(1 if failed else 0)
