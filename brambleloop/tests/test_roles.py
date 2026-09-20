"""The agents whose only job is other agents, and the ways such a swarm flatters itself.

Requirement 179. The requirement's own last clause is the danger: an improvement swarm graded
on changes made will make changes, find forty findings, promote twelve, and leave every
capability curve where it was. So the central test here is that `proposals_made` is
arithmetically unable to reach a score -- a policy saying so would be a policy, and this is a
function that cannot do it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.improve import roles as R  # noqa: E402


# ---- the roster -----------------------------------------------------------


def test_every_role_the_requirement_names_exists():
    for key in ("evaluator", "failure_miner", "experiment_designer",
                "prompt_tool_challenger", "cost_optimiser", "reliability_engineer",
                "creative_critic", "lesson_router"):
        assert key in R.BY_KEY, key
    assert len(R.ROLES) == 8


def test_no_role_both_proposes_and_judges():
    for r in R.ROLES:
        assert not (R.PROPOSE in r.powers and R.JUDGE in r.powers), r.key


def test_a_role_that_proposed_and_judged_would_be_refused_at_construction():
    try:
        R.Role("both", "Both", "do everything", (R.PROPOSE, R.JUDGE), "nothing",
               "wishful thinking")
    except R.RoleRefused as e:
        assert "at the person level" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a role was allowed to grade its own homework")


def test_every_role_is_measured_by_an_uplift_and_not_a_count():
    for r in R.ROLES:
        assert r.measured_by.strip()
        lowered = r.measured_by.lower()
        assert "number of" not in lowered and "how many it made" not in lowered, r.key


def test_the_creative_critic_only_annotates():
    critic = R.role("creative_critic")
    assert critic.powers == (R.ANNOTATE,)
    assert "deterministic validation wins" in critic.note


def test_an_invented_role_is_refused():
    try:
        R.role("vibes_officer")
    except R.RoleRefused as e:
        assert "not a meta-agent role" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an invented role was accepted")


# ---- nobody grades their own homework -------------------------------------


def test_a_judge_may_not_rule_on_its_own_proposal():
    out = R.may_judge(judge="evaluator", author="evaluator")
    assert out["may_judge"] is False
    assert "authored this proposal" in out["why"]


def test_a_role_without_judging_power_cannot_judge():
    out = R.may_judge(judge="failure_miner", author="cost_optimiser")
    assert out["may_judge"] is False and "no judging power" in out["why"]


def test_the_evaluator_may_rule_on_somebody_elses_proposal():
    assert R.may_judge(judge="evaluator", author="failure_miner")["may_judge"] is True


# ---- opposed objectives ---------------------------------------------------


def test_the_cost_optimiser_may_not_buy_its_savings_from_reliability():
    out = R.check_proposal(author="cost_optimiser", trades=("reliability",))
    assert out["ok"] is False
    assert "budget nobody agreed to" in out["why"]


def test_the_reliability_engineer_may_not_buy_uptime_from_the_business():
    out = R.check_proposal(author="reliability_engineer", trades=("contribution",))
    assert out["ok"] is False


def test_the_two_opposed_roles_guard_against_each_other():
    cost = R.role("cost_optimiser")
    reliability = R.role("reliability_engineer")
    assert "reliability" in cost.must_not_trade
    assert "contribution" in reliability.must_not_trade


def test_no_role_may_trade_deterministic_validation():
    for r in R.ROLES:
        if R.PROPOSE not in r.powers and R.ANNOTATE not in r.powers:
            continue
        out = R.check_proposal(author=r.key, trades=("deterministic_validation",))
        assert out["ok"] is False, r.key
        assert "may not be traded by any role" in out["why"]


def test_an_open_trade_vocabulary_is_refused():
    try:
        R.check_proposal(author="cost_optimiser", trades=("efficiency",))
    except R.RoleRefused as e:
        assert "whatever the proposal needs it to mean" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an undefined trade was accepted")


def test_a_permitted_trade_passes():
    out = R.check_proposal(author="cost_optimiser", trades=("latency",))
    assert out["ok"] is True


def test_a_proposal_that_weakens_a_gate_is_refused_by_the_existing_boundary():
    out = R.check_proposal(
        author="cost_optimiser", trades=("cost",),
        hypothesis="skip the asset truth gate to save a model call")
    assert out["ok"] is False
    assert "improvement boundary" in out["why"]


def test_a_judging_role_cannot_propose():
    try:
        R.check_proposal(author="evaluator", trades=("cost",))
    except R.RoleRefused as e:
        assert "may not propose" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the judge proposed a change")


# ---- scored on uplift, and nothing else -----------------------------------


def test_activity_cannot_become_a_score():
    """The requirement's last clause, as arithmetic rather than as a policy."""
    busy = R.Activity(role_key="failure_miner", proposals_made=40, proposals_kept=0,
                      realised_uplift=0.0)
    quiet = R.Activity(role_key="failure_miner", proposals_made=1, proposals_kept=1,
                       realised_uplift=0.2)
    assert R.scorecard(busy)["score"] == 0.0
    assert R.scorecard(quiet)["score"] == 0.2


def test_the_count_is_reported_and_stated_to_be_excluded():
    card = R.scorecard(R.Activity(role_key="failure_miner", proposals_made=9,
                                  proposals_kept=2, realised_uplift=0.1))
    assert card["proposals_made"] == 9
    assert "cannot enter this number" in card["why"]


def test_a_rejected_proposal_scores_zero_and_never_negative():
    card = R.scorecard(R.Activity(role_key="experiment_designer", proposals_made=5,
                                  proposals_kept=0, realised_uplift=0.0))
    assert card["score"] == 0.0
    assert card["score"] >= 0.0
    busy = R.scorecard(R.Activity(role_key="experiment_designer", proposals_made=1,
                                  proposals_kept=0, realised_uplift=0.0))
    assert busy["score"] == card["score"], "proposing more was penalised"


def test_kept_but_unrealised_is_pending_rather_than_zero_uplift():
    """Scoring a recent change as zero uplift retires an agent for being recent."""
    card = R.scorecard(R.Activity(role_key="lesson_router", proposals_made=3,
                                  proposals_kept=2, realised_uplift=0.0))
    assert card["reading"] == R.REALISATION_PENDING
    assert "retire an agent for being recent" in card["why"]


def test_nothing_proposed_is_unmeasured_rather_than_a_failure():
    card = R.scorecard(R.Activity(role_key="lesson_router"))
    assert card["reading"] == R.UNMEASURED
    assert "not the same as having tried and failed" in card["why"]


def test_more_kept_than_proposed_is_refused():
    try:
        R.Activity(role_key="failure_miner", proposals_made=1, proposals_kept=4)
    except R.RoleRefused as e:
        assert "kept of" in str(e)
    else:  # pragma: no cover
        raise AssertionError("more changes were kept than were proposed")


# ---- the swarm together ---------------------------------------------------


def test_the_report_names_unstaffed_roles_rather_than_omitting_them():
    out = R.swarm_report([R.Activity(role_key="failure_miner", proposals_made=2,
                                     proposals_kept=1, realised_uplift=0.3)])
    assert out["of"] == 8 and out["measured_roles"] == 1
    assert len(out["unstaffed"]) == 7
    assert "lesson_router" in out["unstaffed"]


def test_a_busy_swarm_that_moved_nothing_totals_zero():
    busy = [R.Activity(role_key=r.key, proposals_made=25, proposals_kept=0)
            for r in R.ROLES if R.PROPOSE in r.powers or R.ANNOTATE in r.powers]
    out = R.swarm_report(busy)
    assert out["total_uplift"] == 0.0
    assert "moved no capability curve reports zero" in out["note"]


def test_state_lists_the_refusals_and_the_modules_it_operates():
    out = R.state()
    assert out["requirement"] == 179
    assert "improve.roi" in out["operates"]
    assert any("proposes and judges" in r for r in out["refuses"])
    assert "arithmetic impossibility" in out["note"]


# ---- the roster is the single source of the eight ------------------------


def test_every_role_has_an_agent_and_every_meta_agent_has_a_role():
    """Two lists of the same eight drift, and the drift is silent: an agent with no role has
    authority over nothing, and a role with no agent is a job description nobody holds."""
    from brambleloop.agents.registry import DEFAULT_AGENTS

    declared = {a["name"] for a in DEFAULT_AGENTS
                if R.ROLE_JOB_TYPE in a.get("allowed_job_types", [])}
    assert declared == set(R.BY_KEY), declared ^ set(R.BY_KEY)


def test_every_role_has_a_cadence_and_the_cadence_names_the_role_as_its_agent():
    from brambleloop.runtime.worker import CADENCES

    rows = [c for c in CADENCES if c[2] == R.ROLE_JOB_TYPE]
    assert {c[1] for c in rows} == set(R.BY_KEY)
    assert len(rows) == len(R.ROLES)


def test_the_meta_agents_are_green_and_cheap():
    """A meta-agent that can spend real money to decide whether somebody else should have
    spent money is the wrong shape."""
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.core.models import Authority

    for entry in DEFAULT_AGENTS:
        if R.ROLE_JOB_TYPE not in entry.get("allowed_job_types", []):
            continue
        assert entry["authority"] == Authority.GREEN, entry["name"]
        assert entry["daily_cost_ceiling_cad"] <= 0.5, entry["name"]


def test_a_meta_agent_may_run_nothing_but_its_own_job_type():
    from brambleloop.agents.registry import DEFAULT_AGENTS

    for entry in DEFAULT_AGENTS:
        if R.ROLE_JOB_TYPE not in entry.get("allowed_job_types", []):
            continue
        assert entry["allowed_job_types"] == [R.ROLE_JOB_TYPE], entry["name"]


def test_every_role_says_what_it_reads():
    assert set(R.ROLE_READS) == set(R.BY_KEY)
    for key, reads in R.ROLE_READS.items():
        assert reads.strip(), key


def test_a_pass_by_an_agent_that_is_not_a_role_is_refused():
    """The agent *is* the role here, so an agent with no role has no rows it answers for."""
    import tempfile

    from brambleloop.core.db import Database
    from brambleloop.runtime import release

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/roles.sqlite")
    db.create_all()

    class Ctx:
        def __init__(self):
            self.db = db
            self.job = type("J", (), {"agent": "orchestrator", "inputs": {}})()

        def audit(self, *a, **k):
            pass

    try:
        release.handlers.get(R.ROLE_JOB_TYPE)(Ctx())
    except ValueError as e:
        assert "is not a meta-agent role" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a non-role agent did a role's work")


def test_every_role_reports_unmeasured_on_an_empty_database_rather_than_activity():
    """A swarm reporting activity against no rows would be reporting on work it invented."""
    import tempfile

    from brambleloop.core.db import Database
    from brambleloop.runtime import release

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/roles.sqlite")
    db.create_all()
    handler = release.handlers.get(R.ROLE_JOB_TYPE)

    for role in R.ROLES:
        class Ctx:
            def __init__(self, key):
                self.db = db
                self.job = type("J", (), {"agent": key, "inputs": {}})()

            def audit(self, *a, **k):
                pass

        out = handler(Ctx(role.key))
        assert out["role"] == role.key
        assert out["proposed"] == 0, "a meta-agent proposed something on an empty database"
        assert out["scorecard"]["reading"] == R.UNMEASURED
        assert out["scorecard"]["score"] == 0.0


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
