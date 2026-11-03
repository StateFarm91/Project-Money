"""Real-worker coverage for removal of a previously frozen knowledge marker."""
import dataclasses

from brambleloop.cir import knowledge
from brambleloop.core.models import JobStatus
from brambleloop.improve import design_knowledge, knowledge_gate
from test_w5_a6_frozen_knowledge import _approved_rule, _draft, _run, _store


def test_same_version_with_removed_markers_is_held_after_retirement():
    db, path = _store()
    approved = _approved_rule(db)
    pinned = _draft(db, path)
    assert knowledge_gate.has_pins(pinned)
    stripped = dataclasses.replace(pinned, provenance=dataclasses.replace(
        pinned.provenance, primitives_used=tuple(
            p for p in pinned.provenance.primitives_used if not p.startswith(knowledge.PREFIX))))
    design_knowledge.review_rule(db, approved.get("rule_id", approved.get("id")),
                                 reviewer="owner", decision="retire", reason="retire")
    for job, agent in (("cir.revise", "crochet_engineer"), ("gate.certify", "quality_director")):
        status, out, error = _run(db, path, job, {"cir": stripped.to_dict()}, agent)
        assert status == JobStatus.DONE, (out, error)
        assert out.get("refused") == "design_knowledge", out
        assert "markers are missing" in out["reasons"][0], out


def test_unrelated_unpinned_version_remains_eligible_for_baseline_checks():
    db, path = _store()
    _approved_rule(db)
    pinned = _draft(db, path)
    fresh = dataclasses.replace(pinned, version="99.0.0", provenance=dataclasses.replace(
        pinned.provenance, primitives_used=tuple(
            p for p in pinned.provenance.primitives_used if not p.startswith(knowledge.PREFIX))))
    # This is not proof of the candidate's lineage: new-version lineage remains
    # a separate open issue, but this change does not invent a cross-version link.
    assert knowledge_gate.refusal(db, fresh) is None


if __name__ == "__main__":
    test_same_version_with_removed_markers_is_held_after_retirement()
    test_unrelated_unpinned_version_remains_eligible_for_baseline_checks()
    print("2 passed")
