"""An upgrade preparing its own evidence, and the two things it may never prepare.

Requirement 190. The governance half already existed -- `improve.tiers` classifies by touched
surface and holds the cooldown, ceiling and evidence each tier needs. What was missing is the
object in between, and the object is where the two interesting failures live.

A proposal that runs its own tests and reports them passed has reported an opinion in the
shape of a fact. And a proposal working around the clock will change underneath evidence
gathered hours earlier, at which point the evidence describes a version that no longer exists
-- which is invisible unless somebody is keeping a fingerprint.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import upgrades as P  # noqa: E402
from brambleloop.improve import tiers  # noqa: E402

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/pipeline.sqlite")
    db.create_all()
    return db


def _proposal(**kw) -> P.Proposal:
    args = dict(key="p1", author_role="cost_optimiser",
                hypothesis="lower the retry ceiling to cut wasted model spend",
                scope=("weights",), content="threshold = 3", rollback_to="threshold = 5")
    args.update(kw)
    return P.Proposal(**args)


def _evidence(proposal: P.Proposal, kind: str, **kw) -> P.Evidence:
    args = dict(kind=kind, run_ref=f"run-{kind}",
                against_fingerprint=proposal.fingerprint)
    args.update(kw)
    return P.Evidence(**args)


def _complete(db, proposal: P.Proposal) -> None:
    for kind in proposal.tier.requires:
        if kind == tiers.OWNER_APPROVAL:
            continue
        P.attach(proposal, _evidence(proposal, kind))


# ---- evidence is a run, not a field ---------------------------------------


def test_evidence_with_no_run_reference_is_refused():
    p = _proposal()
    try:
        P.Evidence(kind=tiers.BASELINE, run_ref="  ", against_fingerprint=p.fingerprint)
    except P.UpgradeRefused as e:
        assert "opinion in the shape of a fact" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a proposal vouched for itself")


def test_evidence_of_an_unrecognised_kind_is_refused():
    p = _proposal()
    try:
        P.Evidence(kind="we_tested_it", run_ref="r1", against_fingerprint=p.fingerprint)
    except P.UpgradeRefused as e:
        assert "not an evidence kind" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an invented evidence kind was accepted")


def test_evidence_must_name_the_version_it_describes():
    try:
        P.Evidence(kind=tiers.BASELINE, run_ref="r1", against_fingerprint="")
    except P.UpgradeRefused as e:
        assert "has since changed" in str(e)
    else:  # pragma: no cover
        raise AssertionError("evidence with no version was accepted")


# ---- evidence describes a version -----------------------------------------


def test_revising_a_proposal_invalidates_the_evidence_about_the_old_one():
    """The failure that only happens to something working while nobody watches."""
    db = _db()
    p = _proposal()
    _complete(db, p)
    assert P.status(p)["complete"] is True
    out = P.revise(p, "threshold = 2")
    assert sorted(out["evidence_invalidated"]) == sorted(p.tier.requires)
    after = P.status(p)
    assert after["complete"] is False
    assert after["evidence_have"] == []
    assert sorted(after["evidence_invalidated"]) == sorted(p.tier.requires)


def test_stale_evidence_cannot_be_attached_after_the_content_moved():
    p = _proposal()
    stale = _evidence(p, tiers.BASELINE)
    p.content = "threshold = 1"
    try:
        P.attach(p, stale)
    except P.UpgradeRefused as e:
        assert "no longer exists" in str(e)
    else:  # pragma: no cover
        raise AssertionError("evidence about a dead version was attached")


def test_revising_a_proposal_with_no_evidence_yet_says_so():
    p = _proposal()
    out = P.revise(p, "threshold = 4")
    assert out["evidence_invalidated"] == []
    assert "no evidence had been gathered yet" in out["why"]


# ---- bounded means bounded ------------------------------------------------


def test_a_proposal_with_no_declared_scope_is_not_bounded():
    try:
        _proposal(scope=())
    except P.UpgradeRefused as e:
        assert "decided afterwards" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an unbounded proposal was opened")


def test_a_run_touching_a_surface_outside_the_scope_is_refused():
    p = _proposal(scope=("weights",))
    try:
        P.attach(p, _evidence(p, tiers.BASELINE), touched=("spend_limit",))
    except P.UpgradeRefused as e:
        assert "a description, not a bound" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the bound widened to fit what happened")


def test_a_surface_the_classifier_does_not_know_is_refused():
    """An unclassifiable surface would take no tier, and therefore no cooldown at all."""
    try:
        _proposal(scope=("vibes",))
    except P.UpgradeRefused as e:
        assert "no tier" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an unclassifiable surface was accepted")


def test_a_run_inside_the_scope_is_fine():
    p = _proposal(scope=("weights", "ranking"))
    P.attach(p, _evidence(p, tiers.BASELINE), touched=("weights",))
    assert P.status(p)["evidence_have"] == [tiers.BASELINE]


# ---- who may open one -----------------------------------------------------


def test_a_judging_role_may_not_open_a_proposal():
    try:
        _proposal(author_role="evaluator")
    except P.UpgradeRefused as e:
        assert "may not open proposals" in str(e)
    else:  # pragma: no cover
        raise AssertionError("the judge opened its own proposal")


def test_a_hypothesis_nobody_could_disagree_with_is_refused():
    try:
        _proposal(hypothesis="make it better")
    except P.UpgradeRefused as e:
        assert "cannot be shown to have failed" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an undisprovable hypothesis was accepted")


# ---- auto-promotion reads the tier, never the proposal --------------------


def test_the_tier_decides_the_lane_and_the_proposal_has_no_say():
    cheap = _proposal(scope=("weights",))
    dear = _proposal(key="p2", scope=("spend_limit",), rollback_to="limit = 20 CAD")
    assert cheap.tier.key in P.PRE_AUTHORISED
    assert dear.tier.key not in P.PRE_AUTHORISED
    assert P.status(cheap)["route"] == "auto"
    assert P.status(dear)["route"] == "owner"


def test_there_is_no_field_a_proposal_can_set_to_reach_the_fast_lane():
    assert "confidence" not in P.Proposal.__dataclass_fields__
    assert "risk" not in P.Proposal.__dataclass_fields__
    assert "low_risk" not in P.Proposal.__dataclass_fields__


def test_a_gate_tier_proposal_never_auto_promotes_however_complete():
    db = _db()
    p = _proposal(key="p2", scope=("spend_limit",), rollback_to="limit = 20 CAD")
    _complete(db, p)
    out = P.may_auto_promote(db, p, now=NOW)
    assert out["may_auto_promote"] is False
    assert out["route"] == "owner"
    assert "not pre-authorised" in out["why"]


def test_a_pre_authorised_proposal_with_its_evidence_may_promote_itself():
    db = _db()
    p = _proposal()
    _complete(db, p)
    out = P.may_auto_promote(db, p, now=NOW)
    assert out["may_auto_promote"] is True and out["route"] == "auto"


def test_a_pre_authorised_proposal_missing_evidence_is_held_not_promoted():
    db = _db()
    p = _proposal()
    P.attach(p, _evidence(p, tiers.BASELINE))
    out = P.may_auto_promote(db, p, now=NOW)
    assert out["may_auto_promote"] is False and out["route"] == "held"


def test_a_proposal_that_weakens_the_gate_it_touches_is_refused_by_the_boundary():
    """`asset_truth` is both a classifiable surface and a protected gate, which is the case
    the boundary is actually for: loosening something unprotected is ordinary tuning."""
    db = _db()
    p = _proposal(key="p2", scope=("asset_truth",),
                  hypothesis="relax the asset truth check so more frames pass first time",
                  rollback_to="asset truth strictness = strict")
    _complete(db, p)
    out = P.may_auto_promote(db, p, now=NOW)
    assert out["may_auto_promote"] is False
    assert "not pre-authorised" in out["why"], "a gate tier never reaches the boundary check"

    # And the same weakening inside a pre-authorised tier, where the boundary is what stops
    # it rather than the tier.
    cheap = _proposal(key="p3", scope=("weights",),
                      hypothesis=("use a placeholder metric for the baseline so the scoring "
                                  "change can promote"))
    _complete(db, cheap)
    refused = P.may_auto_promote(db, cheap, now=NOW)
    assert refused["may_auto_promote"] is False and refused["route"] == "refused"
    assert "improvement boundary" in refused["why"]


# ---- the owner card -------------------------------------------------------


def test_the_card_carries_exact_impact_cost_and_rollback():
    db = _db()
    p = _proposal(key="p2", scope=("spend_limit",), rollback_to="daily ceiling = 20.00 CAD",
                  spend_cad=12.5)
    _complete(db, p)
    card = P.owner_card(p)
    assert card["queued"] is True
    assert card["impact"]["surfaces"] == ["spend_limit"]
    assert card["cost_cad"] == 12.5
    assert card["rollback_to"] == "daily ceiling = 20.00 CAD"
    assert card["evidence"]


def test_a_vague_rollback_is_refused():
    """'We can revert' is a hope with a plan's grammar."""
    db = _db()
    p = _proposal(key="p2", scope=("spend_limit",), rollback_to="we can revert")
    _complete(db, p)
    try:
        P.owner_card(p)
    except P.UpgradeRefused as e:
        assert "hope with a plan's grammar" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an unactionable rollback was queued")


def test_every_vague_word_is_caught():
    db = _db()
    for word in P.VAGUE:
        p = _proposal(key="p2", scope=("spend_limit",), rollback_to=word)
        _complete(db, p)
        try:
            P.owner_card(p)
        except P.UpgradeRefused:
            continue
        raise AssertionError(f"{word!r} passed as an exact rollback")


def test_an_owner_is_not_asked_to_be_the_check():
    db = _db()
    p = _proposal(key="p2", scope=("spend_limit",), rollback_to="daily ceiling = 20.00 CAD")
    P.attach(p, _evidence(p, tiers.BASELINE))
    try:
        P.owner_card(p)
    except P.UpgradeRefused as e:
        assert "being asked to be the check" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an owner was queued before the machine had finished")


def test_a_pre_authorised_change_is_not_queued_for_a_person():
    db = _db()
    p = _proposal()
    _complete(db, p)
    out = P.owner_card(p)
    assert out["queued"] is False
    assert "approve without reading" in out["why"]


def test_the_card_does_not_require_owner_approval_as_evidence_of_itself():
    """OWNER_APPROVAL is what the card is asking for; requiring it first is a loop."""
    db = _db()
    p = _proposal(key="p2", scope=("spend_limit",), rollback_to="daily ceiling = 20.00 CAD")
    _complete(db, p)
    assert tiers.OWNER_APPROVAL in p.tier.requires
    assert P.owner_card(p)["queued"] is True


def test_state_names_what_it_builds_on_rather_than_reimplementing_it():
    out = P.state()
    assert out["requirement"] == 190
    assert "improve.tiers" in out["builds_on"]
    assert any("no run reference" in r for r in out["refuses"])
    assert "confidence field here would undo it" in out["note"]


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
