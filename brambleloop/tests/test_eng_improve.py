"""ENG-IMPROVE slice 1: the automatic self-improvement team (owner directive 2026-11-20).

OFFLINE TEST -- NOT PRODUCTION EVIDENCE. No network, no spend, no model call.

Covers:
A. champion/challenger: a synthetic stream with a truly better variant is promoted; noise
   is not (many seeds); a significantly worse challenger is rejected;
B. automatic rollback: a promoted value that regresses against its holdback is rolled back
   and the previous champion restored, with the evidence on the trial;
C. the allowlist: non-tunable keys (gates, safety, spend, evidence floors, owner exceptions,
   undeclared keys) and out-of-bounds values are refused -- with a mutation test that the
   refusal suite catches a weakened guard;
D. share and spend caps; a stored out-of-bounds champion falls back to the default;
E. engineering change requests: dedupe, related prior requests, the lifecycle, and close
   only on a verified KPI (reopen otherwise);
F. the department x KPI x lesson-consumer table: a department with no consumer is a finding
   with a change request, never a pass; a consumer whose call site vanished is MISSING;
   KPIs are UNKNOWN on small samples; a no-op never reads as improvement;
G. the improve.monitor backoff lifts when a promotion arrives (diagnosis of the parked loops);
H. the improve.self_tune job runs through the registered handler and is idempotent.

Run: cd brambleloop && python3 tests/test_eng_improve.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

for _k in ("ETSY_API_KEY", "ETSY_SHARED_SECRET", "ANTHROPIC_API_KEY", "RAILWAY_GIT_COMMIT_SHA"):
    os.environ.pop(_k, None)

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Improvement, Incident, Job, JobStatus, Lesson)
from brambleloop.improve import department_loops as DL  # noqa: E402
from brambleloop.improve import ecr, self_improve, stats, tuning  # noqa: E402
from brambleloop.improve.self_models import (  # noqa: E402
    Challenger, EngineeringChangeRequest, PolicyValue)
from brambleloop.runtime import pipeline, release  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import CADENCES  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)
KEY = "research.focus_weight.amigurumi"


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='engimp-')}/i.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _stream(db, tid, p_champ, p_chall, n, *, seed, phase="trial", start=0):
    """Feed n units through the real assignment and record Bernoulli outcomes per arm."""
    rng = random.Random(seed)
    for i in range(start, start + n):
        a = tuning.assign(db, KEY, f"unit-{i}")
        assert a["trial"] == tid and a["phase"] == phase, a
        p = p_chall if a["arm"] == "challenger" else p_champ
        tuning.record(db, tid, a["arm"], f"unit-{i}", rng.random() < p, phase=phase)


# --- A. promotion needs a real gain -------------------------------------------------------

def test_a_truly_better_variant_is_promoted():
    db = _db()
    tid = tuning.start(db, KEY, 1.5, share=0.2, proposed_by="experiment_designer")
    _stream(db, tid, 0.40, 0.65, 1500, seed=7)
    out = tuning.judge(db, tid)
    assert out["decision"] == "promoted", out
    assert out["comparison"]["verdict"] == "BETTER"
    assert tuning.champion(db, KEY) == 1.5
    with db.session() as s:
        row = s.get(Challenger, tid)
        assert row.state == tuning.WATCHING and row.promoted_at is not None
        assert row.history[-1]["event"] == "promoted"
        assert row.history[-1]["comparison"]["z"] >= stats.PROMOTE_Z
        assert s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == tuning.ACTION, AuditLog.artifact == f"si_challenger:{tid}")) == 2


def test_a_noise_is_not_promoted():
    """Identical arms, judged after every 100 units (peeking) exactly as `judge` does -- at
    the newest fixed look -- across 40 seeds: no promotion."""
    promoted = 0
    for seed in range(40):
        rng = random.Random(seed)
        arms = {"champion": [], "challenger": []}
        for i in range(2000):
            arm = "challenger" if rng.random() < 0.2 else "champion"
            arms[arm].append(rng.random() < 0.5)
            if i % 100 != 99:
                continue
            look = stats.checkpoint(min(len(v) for v in arms.values()))
            if look is None:
                continue
            new = (sum(arms["challenger"][:look]), look)
            old = (sum(arms["champion"][:look]), look)
            if stats.compare(new, old)["verdict"] == "BETTER":
                promoted += 1
                break
    assert promoted == 0, promoted
    # and through the real tables, one seed end to end
    db = _db()
    tid = tuning.start(db, KEY, 0.8, share=0.2, proposed_by="experiment_designer")
    for chunk in range(8):
        _stream(db, tid, 0.5, 0.5, 250, seed=100 + chunk, start=chunk * 250)
        assert tuning.judge(db, tid)["decision"] in ("wait", "rejected"), chunk
    assert tuning.champion(db, KEY) == 1.0


def test_a_small_samples_decide_nothing_and_a_worse_challenger_stops():
    db = _db()
    tid = tuning.start(db, KEY, 1.5, share=0.2, proposed_by="experiment_designer")
    _stream(db, tid, 0.2, 1.0, 60, seed=1)          # huge gap, tiny challenger arm
    assert tuning.judge(db, tid)["comparison"]["verdict"] == "UNKNOWN"
    db2 = _db()
    tid2 = tuning.start(db2, KEY, 1.5, share=0.2, proposed_by="experiment_designer")
    _stream2 = random.Random(3)
    for i in range(1500):
        a = tuning.assign(db2, KEY, f"u{i}")
        p = 0.3 if a["arm"] == "challenger" else 0.6
        tuning.record(db2, tid2, a["arm"], f"u{i}", _stream2.random() < p)
    out = tuning.judge(db2, tid2)
    assert out["decision"] == "rejected", out
    assert tuning.champion(db2, KEY) == 1.0


def test_a_a_unit_is_counted_once():
    db = _db()
    tid = tuning.start(db, KEY, 1.5, share=0.2, proposed_by="x")
    assert tuning.record(db, tid, "champion", "u1", True)
    assert not tuning.record(db, tid, "champion", "u1", False)
    assert tuning.counts(db, tid, "trial")["champion"] == (1, 1)


# --- B. automatic rollback ----------------------------------------------------------------

def test_b_a_regressing_promotion_rolls_back():
    db = _db()
    tid = tuning.start(db, KEY, 1.5, share=0.2, proposed_by="experiment_designer")
    _stream(db, tid, 0.40, 0.65, 1500, seed=7)
    assert tuning.judge(db, tid)["decision"] == "promoted"
    # In production the promoted value now does worse than the holdback of the old one.
    _stream(db, tid, 0.60, 0.35, 1200, seed=11, phase="watch", start=10_000)
    out = tuning.judge(db, tid)
    assert out["decision"] == "rolled_back", out
    assert tuning.champion(db, KEY) == 1.0
    with db.session() as s:
        row = s.get(Challenger, tid)
        assert row.state == tuning.ROLLED_BACK and row.rolled_back_at is not None
        assert row.history[-1]["comparison"]["z"] <= -stats.REGRESSION_Z
        pv = s.get(PolicyValue, KEY)
        assert pv.source == f"rollback:si_challenger:{tid}" and pv.version == 2
    # nothing active any more: every unit gets the restored champion
    assert tuning.assign(db, KEY, "anything")["trial"] is None


def test_b_a_holding_promotion_settles():
    db = _db()
    tid = tuning.start(db, KEY, 1.5, share=0.2, proposed_by="experiment_designer")
    _stream(db, tid, 0.40, 0.65, 1500, seed=7)
    assert tuning.judge(db, tid)["decision"] == "promoted"
    _stream(db, tid, 0.40, 0.65, 1500, seed=12, phase="watch", start=20_000)
    assert tuning.judge(db, tid)["decision"] == "settled"
    assert tuning.champion(db, KEY) == 1.5


# --- C. the allowlist ---------------------------------------------------------------------

PROTECTED_KEYS = (
    "gate.certify.pass_threshold", "qa.certification_floor", "visual.identity_gate",
    "child_safety.small_parts", "finance.spend_ceiling_cad", "marketing.ads_daily_budget",
    "research.min_sample", "pricing.owner_exception", "seo.policy_hold",
    "engineering.cir_twin_tolerance", "ops.credential_rotation", "listing.publish_authority",
)


def _refusal_suite() -> list[str]:
    """Every refusal the guard must make. Returns what it failed to refuse."""
    missed = []
    for k in PROTECTED_KEYS:
        if tuning.check(k, 1.0).ok:
            missed.append(f"protected {k}")
    for k, v in (("research.unknown_weight", 1.0),          # undeclared
                 (KEY, 3.0), (KEY, 0.1), (KEY, float("nan")), (KEY, True), (KEY, "1.0"),
                 ("engineering.lesson_match_words", 2.5),     # integer key
                 ("visual.prompt_template", "scene_v9"),     # not a declared choice
                 ("pricing.test_arm", 0.99)):
        if tuning.check(k, v).ok:
            missed.append(f"{k}={v!r}")
    for kw in ({"share": 0.5}, {"share": 0}, {"spend_cap_cad": 50.0},
               {"spend_cap_cad": -1.0}):
        db = _db()
        try:
            tuning.start(db, KEY, 1.5, proposed_by="x", **kw)
            missed.append(f"start {kw}")
        except (ValueError, tuning.NotTunable):
            pass
    db = _db()
    for k, v in (("gate.certify.pass_threshold", 0.5), (KEY, 9.0), (KEY, 1.0)):
        try:
            tuning.start(db, k, v, proposed_by="x")
            missed.append(f"start {k}={v}")
        except (ValueError, tuning.NotTunable):
            pass
    return missed


def test_c_non_tunable_keys_are_refused():
    assert _refusal_suite() == []
    # every declared tunable passes the invariants guard at its default
    for t in tuning.TUNABLES:
        assert tuning.check(t.key, t.default).ok, t.key


def test_c_mutation_a_weakened_guard_is_caught():
    """Each mutant weakens one guard; the refusal suite must notice every one."""
    real_check, real_inv = tuning.check, tuning.invariants.protected_invariant
    real_inv_check = tuning.invariants.check
    real_by_key = dict(tuning.BY_KEY)
    mutants = {
        "allow_everything": lambda: setattr(tuning, "check",
                                            lambda k, v: tuning.invariants.Verdict(True, k)),
        "no_bounds_check": lambda: setattr(
            tuning.invariants, "check",
            lambda p, v, tunable=None: tuning.invariants.Verdict(True, p)),
        "widened_bounds": lambda: tuning.BY_KEY.__setitem__(
            KEY, tuning.Tunable(KEY, "research", "number", 1.0, 0.0, 100.0)),
        "protected_key_allowlisted": lambda: (
            setattr(tuning.invariants, "protected_invariant", lambda p: None),
            tuning.BY_KEY.__setitem__("finance.spend_ceiling_cad", tuning.Tunable(
                "finance.spend_ceiling_cad", "finance", "number", 1.0, 0.0, 9.0))),
    }
    survived = []
    for name, apply in mutants.items():
        try:
            apply()
            if not _refusal_suite():
                survived.append(name)
        finally:
            tuning.check = real_check
            tuning.invariants.protected_invariant = real_inv
            tuning.invariants.check = real_inv_check
            tuning.BY_KEY.clear()
            tuning.BY_KEY.update(real_by_key)
    assert survived == [], survived
    assert _refusal_suite() == []


def test_c_the_allowlist_refuses_to_load_with_a_protected_key():
    saved = tuning.TUNABLES
    try:
        tuning.TUNABLES = saved + (tuning.Tunable("qa.gate_pass_threshold", "qa", "number",
                                                  0.5, 0.1, 0.9),)
        tuning.BY_KEY["qa.gate_pass_threshold"] = tuning.TUNABLES[-1]
        try:
            tuning._assert_allowlist_safe()
            raise AssertionError("a protected key loaded")
        except RuntimeError as e:
            assert "qa.gate_pass_threshold" in str(e)
    finally:
        tuning.TUNABLES = saved
        tuning.BY_KEY.pop("qa.gate_pass_threshold", None)


# --- D. caps and the read guard -----------------------------------------------------------

def test_d_share_cap_and_spend_cap():
    db = _db()
    tid = tuning.start(db, KEY, 1.5, share=0.1, spend_cap_cad=1.0, proposed_by="x")
    arms = [tuning.assign(db, KEY, f"s{i}")["arm"] for i in range(2000)]
    share = arms.count("challenger") / len(arms)
    assert 0.07 < share < 0.13, share
    # the challenger arm records 1.00 of cost: it stops receiving work at once
    first = next(i for i, a in enumerate(arms) if a == "challenger")
    tuning.record(db, tid, "challenger", f"s{first}", True, cost_cad=1.0)
    after = [tuning.assign(db, KEY, f"s{i}")["arm"] for i in range(2000)]
    assert "challenger" not in after
    assert tuning.judge(db, tid)["decision"] == "spend_capped"
    # a zero cap means no recorded cost at all
    db2 = _db()
    t2 = tuning.start(db2, KEY, 1.5, share=0.2, spend_cap_cad=0.0, proposed_by="x")
    tuning.record(db2, t2, "challenger", "z", True, cost_cad=0.01)
    assert all(tuning.assign(db2, KEY, f"z{i}")["arm"] == "champion" for i in range(300))


def test_d_a_stored_value_outside_bounds_is_never_used():
    db = _db()
    with db.session() as s:
        s.add(PolicyValue(key=KEY, value={"v": 50.0}, version=3, source="tampered"))
    assert tuning.champion(db, KEY) == 1.0
    try:
        tuning.champion(db, "gate.certify.pass_threshold")
        raise AssertionError("read a non-tunable key")
    except tuning.NotTunable:
        pass


def test_d_a_noop_challenger_is_refused():
    db = _db()
    try:
        tuning.start(db, KEY, 1.0, proposed_by="x")
        raise AssertionError("no-op trial started")
    except ValueError:
        pass


# --- E. engineering change requests -------------------------------------------------------

def _file(db, **kw):
    args = dict(defect_class="recurring_defect", department="engineering",
                module="brambleloop.cir.compile", title="gauge rounding",
                problem="12 compile refusals share one rounding class",
                evidence={"count": 12, "examples": [{"job": 1}]},
                proposed_change="round once, at the end",
                acceptance_criteria=["the 12 fixtures compile"], priority="P2",
                expected_kpi_gain={"kpi": "engineering.useful_yield", "min_gain": 0.03},
                kpi_baseline={"successes": 40, "trials": 100})
    args.update(kw)
    return ecr.file(db, **args)


def test_e_dedupe_and_related():
    db = _db()
    a = _file(db)
    b = _file(db, evidence={"count": 15, "examples": [{"job": 2}]}, priority="P1")
    assert a["created"] and not b["created"] and a["id"] == b["id"]
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(EngineeringChangeRequest)) == 1
        row = s.get(EngineeringChangeRequest, a["id"])
        assert row.occurrences == 2 and row.priority == "P1"
        assert row.evidence["count"] == 15
        assert row.evidence["examples"] == [{"job": 1}, {"job": 2}]
    # a different class on the same module is a new request, related to the first
    c = _file(db, defect_class="missing_capability")
    assert c["created"] and c["related"] == [a["id"]]
    for bad in ({"defect_class": "vibes"}, {"priority": "P9"}, {"evidence": {}},
                {"acceptance_criteria": []}):
        try:
            _file(db, **bad)
            raise AssertionError(bad)
        except ecr.ECRRefused:
            pass


def _measure(rate, n):
    def m(since, until):
        return int(rate * n), n
    return m


def test_e_lifecycle_closes_only_on_a_verified_kpi():
    db = _db()
    rid = _file(db)["id"]
    for bad in (ecr.REVIEWED, ecr.DEPLOYED, ecr.VERIFIED):
        try:
            ecr.advance(db, rid, bad, by="integrator")
            raise AssertionError(bad)
        except ecr.ECRRefused:
            pass
    ecr.advance(db, rid, ecr.BUILDING, by="integrator")
    ecr.advance(db, rid, ecr.REVIEWED, by="reviewer")
    try:
        ecr.advance(db, rid, ecr.DEPLOYED, by="integrator")
        raise AssertionError("deploy without a commit")
    except ecr.ECRRefused:
        pass
    ecr.advance(db, rid, ecr.DEPLOYED, by="integrator", commit="abc123")
    try:
        ecr.advance(db, rid, ecr.VERIFIED, by="integrator")
        raise AssertionError("closed by hand")
    except ecr.ECRRefused:
        pass
    # too few post-deploy runs: still DEPLOYED, UNKNOWN
    assert ecr.verify(db, rid, measure=_measure(0.9, 5))["verdict"] == "UNKNOWN"
    # a measured gain: VERIFIED (closed), and it leaves the open listing
    assert ecr.verify(db, rid, measure=_measure(0.7, 200))["verdict"] == ecr.VERIFIED
    assert rid not in [r["id"] for r in ecr.listing(db)]
    # the same problem again after the close is a new request that names the old one
    again = _file(db)
    assert again["created"] and again["related"] == [rid]


def test_e_no_gain_after_deploy_reopens_with_the_evidence():
    db = _db()
    rid = _file(db)["id"]
    for st in (ecr.BUILDING, ecr.REVIEWED):
        ecr.advance(db, rid, st, by="i")
    ecr.advance(db, rid, ecr.DEPLOYED, by="i", commit="def456")
    # no measurable gain yet, not aged: wait
    assert ecr.verify(db, rid, measure=_measure(0.41, 200))["verdict"] == "wait"
    later = NOW + timedelta(days=ecr.VERIFY_MAX_DAYS + 1)
    out = ecr.verify(db, rid, measure=_measure(0.41, 200), now=later)
    assert out["verdict"] == ecr.REOPENED
    with db.session() as s:
        row = s.get(EngineeringChangeRequest, rid)
        assert row.state == ecr.REOPENED
        assert row.evidence["verifications"][-1]["commit"] == "def456"
    ecr.advance(db, rid, ecr.BUILDING, by="i")        # back to the builders
    # a worse KPI reopens at once
    db2 = _db()
    r2 = _file(db2)["id"]
    for st in (ecr.BUILDING, ecr.REVIEWED):
        ecr.advance(db2, r2, st, by="i")
    ecr.advance(db2, r2, ecr.DEPLOYED, by="i", commit="0ff")
    assert ecr.verify(db2, r2, measure=_measure(0.2, 200))["verdict"] == ecr.REOPENED


def test_e_readback_projection_carries_no_free_text():
    db = _db()
    _file(db, evidence={"count": 3, "examples": [{"lesson": 1, "subject": "SECRET-SUBJ",
                                                  "statement": "SECRET-STMT"}],
                        "note": "x" * 500})
    rb = ecr.readback(db)
    assert rb["open"] == 1
    text = str(rb)
    assert "SECRET-SUBJ" not in text and "SECRET-STMT" not in text and "x" * 100 not in text


# --- F. the department table --------------------------------------------------------------

def _jobs(db, prefix_jt, n_useful, n_noop, n_dead, *, at):
    with db.session() as s:
        for i in range(n_useful):
            s.add(Job(agent="x", job_type=prefix_jt, status=JobStatus.DONE,
                      outputs={"work_done": 1}, finished_at=at))
        for i in range(n_noop):
            s.add(Job(agent="x", job_type=prefix_jt, status=JobStatus.DONE,
                      outputs={"work_done": 0}, finished_at=at))
        for i in range(n_dead):
            s.add(Job(agent="x", job_type=prefix_jt, status=JobStatus.DEAD, finished_at=at))
        s.add(Job(agent="x", job_type=prefix_jt, status=JobStatus.DONE,
                  outputs={"credential_refused": True}, finished_at=at))   # excluded


def test_f_every_department_has_a_row_and_missing_consumers_are_findings():
    db = _db()
    tbl = DL.table(db, now=NOW)
    keys = {r["department"] for r in tbl["departments"]}
    assert {"research", "concept_creative", "engineering", "qa", "visual", "seo_listing",
            "pricing", "marketing", "finance", "ops"} <= keys
    missing = {f["department"] for f in tbl["findings"]
               if f["defect_class"] == "missing_consumer"}
    assert {"pricing", "ops"} <= missing, missing
    for r in tbl["departments"]:
        assert r["verdict"] in ("LOOP_CLOSED", "FINDING")
        if not r["consumers"] or not any(c["state"] == "ACTIVE" for c in r["consumers"]):
            assert r["verdict"] == "FINDING", r["department"]
    # a fresh database has no applied lessons: nothing is LOOP_CLOSED, nothing passes
    assert tbl["closed"] == 0
    filed = DL.file_findings(db, tbl)
    assert len(filed) == len(tbl["findings"]) and all(f["created"] for f in filed)
    again = DL.file_findings(db, DL.table(db, now=NOW))
    assert not any(f["created"] for f in again)            # deduplicated


def test_f_a_consumer_that_acted_is_active_and_a_vanished_call_site_is_missing():
    db = _db()
    with db.session() as s:
        s.add(Lesson(origin_cell="learn", subject="x", statement="s", evidence_ref="r",
                     confidence="measured", routed_to=["seo_search"],
                     acted_on_by=[{"cell": "seo_search", "how": "tag slot",
                                   "at": NOW.isoformat()}]))
    row = next(r for r in DL.table(db, now=NOW)["departments"]
               if r["department"] == "seo_listing")
    assert row["verdict"] == "LOOP_CLOSED" and row["lessons"] == {
        **row["lessons"], "learned": 1, "verified": 1, "applied": 1}
    gone = DL.Consumer("lesson", "brambleloop.runtime.release", "consume.never_called(",
                       "seo_search", "x")
    assert DL.consumer_state(db, gone, now=NOW)["state"] == "MISSING"


def test_f_kpi_is_measured_from_rows_and_unknown_when_small():
    db = _db()
    _jobs(db, "radar.score", 3, 1, 1, at=NOW - timedelta(days=2))
    k = DL.kpi(db, "research", now=NOW)
    assert (k["successes"], k["trials"]) == (3, 5) and k["state"] == "UNKNOWN"
    assert k["trend"]["trend"] == "UNKNOWN"
    _jobs(db, "radar.score", 30, 0, 0, at=NOW - timedelta(days=2))
    _jobs(db, "radar.score", 10, 20, 0, at=NOW - timedelta(days=20))
    k = DL.kpi(db, "research", now=NOW)
    assert k["state"] == "MEASURED" and k["trend"]["trend"] == "UP", k


def test_f_a_noop_never_reads_as_improvement():
    db = _db()
    _jobs(db, "pricing.check", 0, 60, 0, at=NOW - timedelta(days=2))
    _jobs(db, "pricing.check", 0, 60, 0, at=NOW - timedelta(days=20))
    p = self_improve.panel(db, now=NOW)
    row = next(r for r in p["departments"] if r["department"] == "pricing")
    assert row["kpi"]["value"] == 0.0 and row["improving"] == "NO"
    assert row["consumers"] == [{"module": None, "state": "MISSING"}]
    assert all(r["improving"] in ("UNKNOWN", "NO") for r in p["departments"])
    assert p["status"] == "DEGRADED"


# --- G. the parked improve.* loops --------------------------------------------------------

def test_g_monitor_backoff_lifts_when_a_promotion_arrives():
    db = _db()
    # BACKOFF-CAP: a backoff stands at most min(4x period, 6 h) from `since`
    since = NOW - timedelta(hours=3)
    sus = {"kind": orc.BACKOFF, "job_type": "improve.monitor", "level": 5, "factor": 32,
           "suspend_until": (NOW + timedelta(days=20)).isoformat(), "since": since.isoformat()}
    with db.session() as s:
        s.add(Incident(severity="P3", signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}improve.monitor",
                       summary="fixture", at=since, detail={"suspension": sus}))
    assert "improve.monitor" in orc.suspended_job_types(db, now=NOW)
    # ... a cell reading of a cell with nothing promoted is not input for the monitor
    with db.session() as s:
        s.add(Improvement(cell="quality", metric="m", hypothesis="h", state="proposed",
                          at=since - timedelta(days=1)))
    assert "improve.monitor" in orc.suspended_job_types(db, now=NOW)
    with db.session() as s:
        s.add(Improvement(cell="quality", metric="m", hypothesis="h2", state="promoted",
                          promoted_at=NOW - timedelta(hours=1)))
    assert "improve.monitor" not in orc.suspended_job_types(db, now=NOW)
    # and a self-tune promotion is input too
    db2 = _db()
    with db2.session() as s:
        s.add(Incident(severity="P3", signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}improve.monitor",
                       summary="fixture", at=since, detail={"suspension": sus}))
        s.add(Challenger(department="research", key=KEY, champion_value={"v": 1.0},
                         challenger_value={"v": 1.5}, state=tuning.WATCHING,
                         promoted_at=NOW - timedelta(hours=1), history=[]))
    assert "improve.monitor" not in orc.suspended_job_types(db2, now=NOW)


def test_g_sandbox_and_league_lift_on_their_inputs():
    db = _db()
    # BACKOFF-CAP: a backoff stands at most min(4x period, 6 h) from `since`
    since = NOW - timedelta(hours=3)
    for jt in ("improve.sandbox", "improve.league"):
        sus = {"kind": orc.BACKOFF, "job_type": jt, "level": 5, "factor": 32,
               "suspend_until": (NOW + timedelta(days=20)).isoformat(),
               "since": since.isoformat()}
        with db.session() as s:
            s.add(Incident(severity="P3", signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}{jt}",
                           summary="fixture", at=since, detail={"suspension": sus}))
    held = orc.suspended_job_types(db, now=NOW)
    assert {"improve.sandbox", "improve.league"} <= set(held)
    with db.session() as s:
        s.add(Improvement(cell="quality", metric="m", hypothesis="new", state="proposed",
                          at=NOW - timedelta(hours=2)))
    held = orc.suspended_job_types(db, now=NOW)
    assert "improve.sandbox" not in held and "improve.league" in held


# --- H. the job ---------------------------------------------------------------------------

def test_h_the_self_tune_job_is_registered_and_idempotent():
    assert any(jt == "improve.self_tune" for _n, _a, jt, _p in CADENCES)
    assert "improve.self_tune" in orc.FREE_JOB_TYPES
    from brambleloop.autonomy.departments import WORK_CLASS
    from brambleloop.authority.classes import JOB_CLASS
    from brambleloop.runtime.worker import handlers

    assert WORK_CLASS["improve.self_tune"] == "IMPROVE" and "improve.self_tune" in JOB_CLASS
    assert handlers.get("improve.self_tune") is not None
    db = _db()
    first = self_improve.cycle(db, now=NOW)
    assert first["ran"] and first["ecrs_filed"] and first["work_done"] == len(first["ecrs_filed"])
    second = self_improve.cycle(db, now=NOW)
    assert second["ecrs_filed"] == [] and second["work_done"] == 0
    assert sorted(second["ecrs_merged"]) == sorted(first["ecrs_filed"])
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(EngineeringChangeRequest)) == len(
            first["ecrs_filed"])


def test_h_a_parked_improve_loop_files_a_failing_loop_request():
    db = _db()
    # BACKOFF-CAP: a backoff stands at most min(4x period, 6 h) from `since`
    since = NOW - timedelta(hours=3)
    sus = {"kind": orc.BACKOFF, "job_type": "improve.mine", "level": 6, "factor": 32,
           "suspend_until": (NOW + timedelta(days=20)).isoformat(), "since": since.isoformat()}
    with db.session() as s:
        s.add(Incident(severity="P3", signature=f"{orc.BACKOFF_SIGNATURE_PREFIX}improve.mine",
                       summary="fixture", at=since, detail={"suspension": sus}))
    out = self_improve.cycle(db, now=NOW)
    assert out["parked_improve_loops"] == ["improve.mine"]
    rows = [r for r in ecr.listing(db) if r["defect_class"] == "failing_loop"]
    assert len(rows) == 1 and rows[0]["module"] == "improve.mine"


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
