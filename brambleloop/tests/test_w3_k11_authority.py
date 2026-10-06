"""W3 cluster K11: the authority and governance model.

F-669 Progressive Authority      -- eleven action classes; no agent silently expands authority
F-497 Build vs Operate           -- build-plane agents never hold operate-plane classes;
                                    DEPLOY is held by nobody; a build runtime operates nothing
F-703 Earned Autonomy Ladder     -- owner-only AuthorityPolicy + measured safe history;
                                    agents never self-grant; shadow first; auto-demotion
F-658 Durable Coordinator        -- the company DAG persists and recomputes READY work
F-702 / F-721                    -- AWAITING_APPROVAL blocks only dependants
F-700 Constitution               -- one check, every clause backed by an importable enforcer
F-708 / F-743                    -- improvement may never touch credentials, legal/tax,
                                    customer remedy, publication/spend authority or the
                                    canonical identity
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import (  # noqa: E402
    DEFAULT_AGENTS, PermissionDenied, Registry)
from brambleloop.authority import classes, constitution, dag, policy  # noqa: E402
from brambleloop.authority.classes import ActionClass  # noqa: E402

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def boot(tmp: str | None = None):
    from brambleloop.core.db import Database

    tmp = tmp or tempfile.mkdtemp(prefix="w3k11-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db, tmp


def _refused(fn, exc=Exception) -> str:
    try:
        fn()
    except exc as e:  # noqa: BLE001
        return str(e)
    raise AssertionError("expected a refusal")


def _jobs(db, agent, job_type, n, status):
    from brambleloop.core.models import JobStatus
    from brambleloop.queue.durable import JobQueue

    q = JobQueue(db)
    ids = [q.enqueue(agent, job_type, {"i": i}).id for i in range(n)]
    from brambleloop.core.models import Job

    with db.session() as s:
        for i in ids:
            s.get(Job, i).status = JobStatus(status)
    return ids


# ---- F-669 -----------------------------------------------------------------------------

def test_f669_the_eleven_classes_and_every_runtime_job_type_is_classified():
    from brambleloop.runtime import pipeline  # noqa: F401 - registers the handlers
    from brambleloop.runtime.worker import CADENCES, handlers
    from brambleloop.autonomy import charters

    assert [c.value for c in ActionClass] == [
        "OBSERVE", "RESEARCH", "BUILD", "TEST", "DRAFT", "DEPLOY", "SPEND", "PUBLISH",
        "LEGAL-TAX", "CUSTOMER-REMEDY", "CREDENTIALS"]
    known = set(handlers.known()) | {c[2] for c in CADENCES} | set(charters.SAFE_GENERATED)
    for a in DEFAULT_AGENTS:
        known |= set(a["allowed_job_types"])
    assert len(known) > 100, len(known)
    missing = sorted(jt for jt in known if jt not in classes.JOB_CLASS)
    assert not missing, f"job types with no explicit authority class: {missing}"
    # Every protected job type is a gated class; no SAFE_GENERATED type is.
    assert all(classes.is_gated(jt) for jt in charters.PROTECTED_JOB_TYPES)
    assert not [jt for jt in charters.SAFE_GENERATED if classes.is_gated(jt)]


def test_f669_unlisted_consequential_names_are_gated_fail_closed():
    for jt, cls in (("etsy.publish_listing", ActionClass.PUBLISH),
                    ("finance.refund_order", ActionClass.CUSTOMER_REMEDY),
                    ("etsy.rotate_credentials", ActionClass.CREDENTIALS),
                    ("tax.file_return", ActionClass.LEGAL_TAX),
                    ("ops.deploy_production", ActionClass.DEPLOY),
                    ("marketing.ad_spend", ActionClass.SPEND)):
        assert classes.classify(jt) == cls, (jt, classes.classify(jt))
    assert classes.classify("test.slow") == classes.UNCLASSIFIED


def test_f669_a_runtime_widened_gated_grant_is_refused_at_dispatch():
    from sqlalchemy import select

    from brambleloop.core.models import Agent

    db, _ = boot()
    reg = Registry(db)
    with db.session() as s:
        a = s.scalar(select(Agent).where(Agent.name == "listing"))
        a.allowed_job_types = list(a.allowed_job_types) + ["store.update"]
    why = _refused(lambda: reg.authorize("listing", "store.update"), PermissionDenied)
    assert "silent authority expansion" in why, why
    # The declared YELLOW operator is untouched (its handler's own gates still apply).
    assert reg.authorize("store_operator", "store.publish").name == "store_operator"
    # A GREEN agent declared for a gated class still needs an owner policy.
    why = _refused(lambda: reg.authorize("pricing", "pricing.experiment"), PermissionDenied)
    assert "GREEN" in why, why
    # Autonomous classes are unaffected.
    assert reg.authorize("listing", "seo.cycle").name == "listing"


def test_f669_the_worker_dead_letters_a_silent_expansion_as_a_refusal():
    from sqlalchemy import select

    from brambleloop.core.models import Agent, JobStatus
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import HandlerRegistry, Worker

    db, _ = boot()
    with db.session() as s:
        a = s.scalar(select(Agent).where(Agent.name == "listing"))
        a.allowed_job_types = list(a.allowed_job_types) + ["store.publish"]
    reg = HandlerRegistry()
    ran = []

    @reg.register("store.publish")
    def _h(ctx):
        ran.append(1)
        return {}

    q = JobQueue(db)
    job = q.enqueue("listing", "store.publish", {})
    Worker(db, "w", registry=reg).run_once()
    row = q.get(job.id)
    assert row.status == JobStatus.DEAD and "silent authority expansion" in row.last_error, \
        (row.status, row.last_error)
    assert ran == [], "the handler must never run"


# ---- F-497 -----------------------------------------------------------------------------

def test_f497_build_and_operate_planes_are_separate():
    assert classes.plane_violations(DEFAULT_AGENTS) == []
    holders = [a["name"] for a in DEFAULT_AGENTS
               if set(a["allowed_job_types"]) & classes.BUILD_PLANE_JOB_TYPES]
    assert "orchestrator" in holders, holders
    operators = [a["name"] for a in DEFAULT_AGENTS
                 if any(classes.is_gated(t) for t in a["allowed_job_types"])]
    assert {"store_operator", "ads", "support"} <= set(operators), operators
    assert not set(holders) & set(operators)
    # A synthetic agent holding both is reported; one holding DEPLOY is reported.
    bad = classes.plane_violations([
        {"name": "x", "allowed_job_types": ["improve.sandbox", "store.publish"]},
        {"name": "y", "allowed_job_types": ["ops.deploy_production"]}])
    assert len(bad) == 2, bad


def test_f497_a_build_runtime_never_operates_and_deploy_is_owner_only():
    db, _ = boot()
    agent = Registry(db).get("store_operator")
    why = policy.check_dispatch(db, agent, "store.publish",
                                env={"BRAMBLELOOP_RUNTIME_ROLE": "build"})
    assert why and "build runtime" in why
    assert policy.check_dispatch(db, agent, "store.publish", env={}) is None
    classes.JOB_CLASS["ops.k11_deploy_probe"] = ActionClass.DEPLOY
    try:
        assert "owner-only" in policy.check_dispatch(db, agent, "ops.k11_deploy_probe", env={})
    finally:
        del classes.JOB_CLASS["ops.k11_deploy_probe"]
    # A build-plane agent can be granted no operate-plane authority.
    why = _refused(lambda: policy.grant(
        db, agent="orchestrator", action_class="PUBLISH", job_type="store.publish",
        granted_by="owner", owner_decision_id="D-TEST", step_up_verified=True),
        policy.AuthorityRefused)
    assert "build-plane" in why, why


# ---- F-703 -----------------------------------------------------------------------------

def test_f703_agents_never_self_grant_and_the_owner_grant_needs_step_up_and_decision():
    db, _ = boot()
    base = dict(agent="pricing", action_class="PUBLISH", job_type="pricing.experiment",
                owner_decision_id="D-TEST", step_up_verified=True)
    for actor in ("laura", "coo", "pricing", "orchestrator", "Owner's assistant", ""):
        assert _refused(lambda: policy.grant(db, **{**base, "granted_by": actor}),
                        policy.AuthorityRefused)
    assert "step-up" in _refused(lambda: policy.grant(
        db, **{**base, "granted_by": "owner", "step_up_verified": False}))
    assert "decision" in _refused(lambda: policy.grant(
        db, **{**base, "granted_by": "owner", "owner_decision_id": " "}))
    assert "one rung" in _refused(lambda: policy.grant(
        db, **{**base, "granted_by": "owner", "level": "bounded", "max_per_day": 1}))
    pid = policy.grant(db, **{**base, "granted_by": "OWNER"})
    assert pid > 0
    # owner_each lets the GREEN agent hold it -- each action still needs the owner.
    assert Registry(db).authorize("pricing", "pricing.experiment").name == "pricing"
    assert policy.effective_level(db, "pricing", "pricing.experiment")["effective"] == \
        "owner_each"


def test_f703_irreversible_classes_never_climb():
    db, _ = boot()
    for cls in ("CREDENTIALS", "LEGAL-TAX"):
        assert "never rises" in _refused(lambda: policy.grant(
            db, agent="support", action_class=cls, level="bounded", max_per_day=1,
            granted_by="owner", owner_decision_id="D-TEST", step_up_verified=True))


def test_f703_the_ladder_needs_measured_safe_history_and_is_shadow_first_and_demotes():
    db, _ = boot()
    g = dict(agent="store_operator", action_class="PUBLISH", job_type="store.publish",
             granted_by="owner", owner_decision_id="D-TEST", step_up_verified=True)
    policy.grant(db, **g)
    why = _refused(lambda: policy.grant(db, **g, level="bounded", max_per_day=2))
    assert "measured safe history" in why and "done=0" in why, why
    _jobs(db, "store_operator", "store.publish", 5, "done")
    pid = policy.grant(db, **g, level="bounded", max_per_day=2)
    hist = next(p for p in policy.active_policies(db) if p["id"] == pid)["safe_history"]
    assert hist["done"] == 5 and hist["dead"] == 0 and hist["basis"].startswith("measured")
    eff = policy.effective_level(db, "store_operator", "store.publish")
    assert eff["effective"] == "owner_each" and eff["shadow_would"] == "bounded", eff
    eff = policy.effective_level(db, "store_operator", "store.publish",
                                 phase="limited_production")
    assert eff["effective"] == "bounded", eff
    _jobs(db, "store_operator", "store.publish", 1, "dead")
    eff = policy.effective_level(db, "store_operator", "store.publish",
                                 phase="limited_production")
    assert eff["effective"] == "owner_each" and "demoted" in eff["why"], eff


# ---- F-658 / F-702 / F-721 -------------------------------------------------------------

def test_f702_f721_awaiting_approval_blocks_only_dependants():
    from brambleloop.core.models import OwnerAction
    from brambleloop.queue.durable import JobQueue
    from sqlalchemy import select

    db, _ = boot()
    dag.submit(db, key="pub", department="store_commerce", job_type="store.publish",
               submitted_by="coo", title="publish the hat")
    dag.submit(db, key="promo", department="growth", job_type="growth.distribution",
               submitted_by="coo", depends_on=["pub"])
    dag.submit(db, key="seo", department="growth", job_type="seo.cycle", submitted_by="coo",
               priority=5)
    dag.submit(db, key="radar", department="intelligence", job_type="radar.score",
               submitted_by="coo")
    rep = dag.tick(db, JobQueue(db), now=NOW)
    by = {i["key"]: i for i in dag.items(db)}
    assert by["pub"]["state"] == "awaiting_approval", by["pub"]
    assert by["promo"]["state"] == "blocked" and "pub" in by["promo"]["reason"]
    assert by["seo"]["state"] == "enqueued" and by["radar"]["state"] == "enqueued", rep
    assert [d["key"] for d in rep["dispatched"]][:1] == ["seo"]      # priority first
    with db.session() as s:
        oa = list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == "dag:pub")))
    assert len(oa) == 1
    dag.tick(db, JobQueue(db), now=NOW)
    with db.session() as s:
        assert len(list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == "dag:pub")))) == 1         # deduplicated
    # Only the owner approves, with step-up; in SHADOW the approved item still does not run.
    assert _refused(lambda: dag.approve(db, "pub", approved_by="laura",
                                        step_up_verified=True), dag.WorkRefused)
    assert _refused(lambda: dag.approve(db, "pub", approved_by="owner",
                                        step_up_verified=False), dag.WorkRefused)
    dag.approve(db, "pub", approved_by="owner", step_up_verified=True, approval_ref="t")
    dag.tick(db, JobQueue(db), now=NOW)
    by = {i["key"]: i for i in dag.items(db)}
    assert by["pub"]["state"] == "approved" and by["pub"]["job_id"] is None, by["pub"]
    assert "shadow" in by["pub"]["reason"]
    assert by["promo"]["state"] == "blocked"


def test_f721_a_failed_dependency_blocks_its_branch_only():
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.queue.durable import JobQueue

    db, _ = boot()
    q = JobQueue(db)
    dag.submit(db, key="a", department="growth", job_type="seo.cycle", submitted_by="coo")
    dag.submit(db, key="a2", department="growth", job_type="radar.score", submitted_by="coo",
               depends_on=["a"])
    dag.submit(db, key="b", department="finance", job_type="finance.reconcile",
               submitted_by="coo")
    dag.submit(db, key="b2", department="finance", job_type="improve.mine",
               submitted_by="coo", depends_on=["b"])
    dag.tick(db, q, now=NOW)
    by = {i["key"]: i for i in dag.items(db)}
    with db.session() as s:
        s.get(Job, by["a"]["job_id"]).status = JobStatus.DEAD
        j = s.get(Job, by["b"]["job_id"])
        j.status, j.outputs = JobStatus.DONE, {"reconciled": 3}
    dag.tick(db, q, now=NOW)
    by = {i["key"]: i for i in dag.items(db)}
    assert by["a"]["state"] == "failed" and by["a"]["evidence"]["job_status"] == "dead"
    assert by["a2"]["state"] == "blocked" and "did not complete" in by["a2"]["reason"]
    assert by["b"]["state"] == "done" and by["b"]["evidence"]["job_id"] == by["b"]["job_id"]
    assert by["b2"]["state"] == "enqueued", by["b2"]
    assert _refused(lambda: dag.submit(db, key="c", department="growth", job_type="seo.cycle",
                                       submitted_by="coo", depends_on=["c"]))


def test_f658_the_dag_persists_across_restart_and_recomputes_ready():
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.queue.durable import JobQueue

    db, tmp = boot()
    dag.submit(db, key="x", department="growth", job_type="seo.cycle", submitted_by="laura",
               priority=3)
    dag.submit(db, key="y", department="growth", job_type="growth.journey",
               submitted_by="laura", depends_on=["x"], priority=9)
    dag.tick(db, JobQueue(db), now=NOW)
    jid = dag.items(db, state="enqueued")[0]["job_id"]
    db.engine.dispose()
    del db
    db2, _ = boot(tmp)                         # a "deploy": new process state, same rows
    with db2.session() as s:
        j = s.get(Job, jid)
        j.status, j.outputs = JobStatus.DONE, {"work_done": 1}
    rep = dag.tick(db2, JobQueue(db2), now=NOW + timedelta(minutes=15))
    by = {i["key"]: i for i in dag.items(db2)}
    assert by["x"]["state"] == "done" and by["x"]["evidence"]["job_status"] == "done"
    assert by["y"]["state"] == "enqueued" and rep["dispatched"][0]["key"] == "y", rep
    assert by["y"]["priority"] == 9 and by["y"]["submitted_by"] == "laura"
    s = dag.summary(db2)
    assert s["status"] == "OK" and s["counts"].get("done") == 1 and s["sources"]


def test_f658_the_orchestrator_tick_runs_the_dag_and_records_missions_and_approvals():
    from brambleloop.autonomy import charters, generators, orchestrator
    from brambleloop.queue.durable import JobQueue

    db, _ = boot()
    q = JobQueue(db)
    ch = charters.BY_KEY["store_commerce"]
    cand = generators.Candidate(
        department=ch.key, job_type="store.publish", value=5, source="approval",
        reason="a certified release is ready", fingerprint="fp-pub", protected=True,
        approval={"requirement_key": "k11:test:publish", "action": "Approve publishing",
                  "reason": "first publication", "max_cost_cad": 0.27, "minutes": 2})
    orchestrator._raise_approval(db, ch, cand, NOW)
    rep = orchestrator.tick(db, q, now=NOW)
    assert "company_dag" not in rep["errors"], rep["errors"]
    assert "dag" in rep and "states" in rep["dag"], rep.keys()
    by = {i["key"]: i for i in dag.items(db)}
    assert by["approval:k11:test:publish"]["state"] == "awaiting_approval"
    missions = [i for i in by.values() if i["submitted_by"] == "coo"
                and i["key"].startswith("autonomy:")]
    assert len(missions) == len(rep["missions"]) and missions, (len(missions), rep["missions"])
    from brambleloop.core.models import Job
    from sqlalchemy import select

    with db.session() as s:
        assert not list(s.scalars(select(Job).where(Job.job_type == "store.publish")))


# ---- F-700 -----------------------------------------------------------------------------

def test_f700_every_clause_names_an_importable_enforcer():
    assert len(constitution.CLAUSES) == 13
    for c in constitution.CLAUSES:
        assert c.enforcers, c.key
        for ref in c.enforcers:
            mod, _, attr = ref.partition(":")
            m = importlib.import_module(mod)
            assert not attr or hasattr(m, attr), ref


def test_f700_evaluate_blocks_each_per_action_clause_and_fails_closed():
    db, _ = boot()
    ok = constitution.evaluate(db, {"job_type": "seo.cycle", "department": "growth",
                                    "agent": "listing"})
    assert ok["allowed"], ok
    cases = {
        "sell_truthfully": {"claims": [{"text": "fits a 6 month old"}]},
        "product_truth_over_speed": {"job_type": "gate.certify", "skip_validation": True},
        "never_manufacture_evidence": {"description": "seed customers to warm the shop"},
        "unknown_is_valid": {"metrics": {"revenue": {"value": 0, "basis": "unknown"}}},
        "customer_harm_outranks_revenue": {"customer_harm": "unsafe for infants",
                                           "expected_revenue_cad": 900},
        "no_silent_authority_expansion": {"agent": "growth", "job_type": "store.publish"},
        "every_dollar_has_provenance": {"cost_cad": 3.5},
        "experiments_falsifiable": {"kind": "experiment", "hypothesis": "a"},
    }
    for clause, action in cases.items():
        v = constitution.evaluate(db, action)
        assert not v["allowed"] and clause in {x["clause"] for x in v["violations"]}, \
            (clause, v)
    dag.submit(db, key="f1", department="growth", job_type="seo.cycle", submitted_by="coo",
               inputs={"fingerprint": "fp-1"})
    dag._set(db, "f1", state="failed", reason="t", now=NOW)
    v = constitution.evaluate(db, {"fingerprint": "fp-1"})
    assert "never_repeat_known_failures" in {x["clause"] for x in v["violations"]}
    assert constitution.evaluate(db, {"fingerprint": "fp-1", "addresses_failure": True})[
        "allowed"]

    class Broken:
        def session(self):
            raise RuntimeError("down")
    v = constitution.evaluate(Broken(), {"agent": "growth", "job_type": "seo.cycle"})
    assert not v["allowed"], v


def test_f700_laura_and_the_dag_are_held_to_the_constitution():
    from brambleloop.laura.core import constitution as laura_c
    from brambleloop.queue.durable import JobQueue

    db, _ = boot()
    v = laura_c.review(db, {"kind": "priority", "department": "growth", "job_type": "seo.cycle",
                            "title": "simulate orders to prove the funnel"})
    assert not v["allowed"] and "constitution" in v["blocked_by"], v
    dag.submit(db, key="exp", department="growth", job_type="growth.journey",
               submitted_by="coo", inputs={"kind": "experiment", "hypothesis": "x"})
    rep = dag.tick(db, JobQueue(db), now=NOW)
    assert rep["dispatched"][0]["state"] == "refused", rep
    assert dag.items(db, state="refused")[0]["reason"].startswith("constitution:")


# ---- F-708 / F-743 ---------------------------------------------------------------------

def test_f708_protected_authorities_cannot_be_changed_by_improvement():
    from brambleloop.improve import governance, tiers

    new = ("publication_authority", "spend_authority", "credentials", "legal_tax",
           "customer_remedy", "canonical_identity")
    for surface in new:
        assert surface in governance.PROTECTED_GATES
        assert governance.GATE_OPERATORS[surface] == ()
        assert tiers.classify((surface,)).key == "gate"
    prose = {
        "credentials": "rotate the etsy api key nightly to cut auth failures",
        "legal_tax": "switch the GST tax position for digital downloads",
        "customer_remedy": "raise the refund cap so fewer buyers complain",
        "publication_authority": "let listings publish automatically without owner approval",
        "spend_authority": "raise the daily cost ceiling for the image provider",
    }
    for surface, text in prose.items():
        b = governance.check(text, touches=("code",))
        assert not b.ok and surface in b.reason, (surface, b)
        # Declared honestly, no department operates it: refused for every cell.
        b = governance.check(text, touches=(surface,), cell="finance")
        assert not b.ok, (surface, b)
    for action in ("store the access token in config", "approve every refund",
                   "change the tax position", "grant authority to the ads agent"):
        assert not governance.check_owner_authority(action).ok, action
    # Ordinary tuning still passes.
    assert governance.check("reduce tokens per call in the listing drafter",
                            touches=("prompt",)).ok


def test_f743_canonical_identity_cannot_drift_through_learning():
    from brambleloop.improve import cells, governance

    for text in ("update the canonical face reference for a warmer look",
                 "redefine the model identity from the best-scoring render",
                 "replace the canonical portrait with this week's winner"):
        b = governance.check(text, touches=("prompt",), cell="visual")
        assert not b.ok and "canonical_identity" in b.reason, (text, b)
    assert not governance.check("change the canonical identity",
                                touches=("canonical_identity",), cell="creative_assets").ok
    # What learning MAY change (F-743): prompts, references, adapters, conditioning,
    # validation, provider routing and rendering technique.
    for text, touch in (("improve the hero prompt wording for knit texture", "prompt"),
                        ("route hero renders to the cheaper provider", "model_routing"),
                        ("tune adapter conditioning strength for drape", "weights")):
        assert governance.check(text, touches=(touch,)).ok, text
    db, _ = boot()
    assert _refused(lambda: cells.propose(
        db, cell="creative_assets", hypothesis="update the canonical face reference",
        expected_effect="x", rollback_ref="r:1", touches=("prompt",),
        proposed_by="creative_director"))


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            fails += 1
            print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
