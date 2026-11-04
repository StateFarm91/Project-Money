"""Knowledge evidence can be read in an authority caller's transaction."""
from unittest.mock import patch

from brambleloop.core.db import Database
from brambleloop.core.models import BenchmarkFingerprintRecord, DesignRule
from brambleloop.improve import design_knowledge, knowledge_gate
from brambleloop.products import launch0
from test_w5_a6_frozen_knowledge import _approved_rule, _store


def test_bound_verification_observes_pending_retirement_without_committing():
    db, _ = _store()
    approved = _approved_rule(db)
    cir = design_knowledge.freeze_pins(db, launch0.cir_for("basket_small"), [approved["pin"]])
    with db._sessions() as session:
        rule = session.get(DesignRule, approved["pin"]["rule_id"])
        rule.state = "retired"
        session.flush()
        # All nested database contexts must use this session. A new session
        # would both miss the pending retirement and violate the contract.
        with patch.object(db, "session", side_effect=AssertionError("opened another session")):
            why = knowledge_gate.refusal(db, cir, session=session)
        assert why and "does not verify" in why, why
        session.rollback()
    assert knowledge_gate.refusal(db, cir) is None


def test_foreign_or_inactive_session_is_refused():
    db, _ = _store()
    other = Database("sqlite:///:memory:", scratch=True)
    with other._sessions() as session:
        session.begin()
        try:
            design_knowledge.verify_pins(db, [], session=session)
        except ValueError as exc:
            assert "not bound" in str(exc)
        else:
            raise AssertionError("accepted a session for another database")
    with db._sessions() as session:
        try:
            design_knowledge.verify_pins(db, [], session=session)
        except ValueError as exc:
            assert "active transaction" in str(exc)
        else:
            raise AssertionError("accepted an inactive transaction")


def test_bound_verification_reads_pending_originality_corpus_from_same_transaction():
    db, _ = _store()
    approved = _approved_rule(db)
    cir = design_knowledge.freeze_pins(db, launch0.cir_for("basket_small"), [approved["pin"]])
    with db._sessions() as session:
        session.add(BenchmarkFingerprintRecord(benchmark_ref="new-corpus-entry"))
        session.flush()
        # Evaluation's nested corpus read must observe this transaction's
        # uncommitted write, and must not open a second session.
        with patch.object(db, "session", side_effect=AssertionError("opened another session")):
            why = knowledge_gate.refusal(db, cir, session=session)
        assert why and "does not verify" in why, why
        session.rollback()
    assert knowledge_gate.refusal(db, cir) is None


def test_previously_loaded_rule_is_refreshed_after_a_concurrent_retirement():
    db, _ = _store()
    approved = _approved_rule(db)
    cir = design_knowledge.freeze_pins(db, launch0.cir_for("basket_small"), [approved["pin"]])
    with db._sessions() as session:
        loaded = session.get(DesignRule, approved["pin"]["rule_id"])
        assert loaded.state == "approved"
        with db.session() as writer:
            writer.get(DesignRule, loaded.id).state = "retired"
        why = knowledge_gate.refusal(db, cir, session=session)
        assert why and "does not verify" in why, why


def test_pending_orm_changes_are_held_without_being_discarded():
    db, _ = _store()
    approved = _approved_rule(db)
    cir = design_knowledge.freeze_pins(db, launch0.cir_for("basket_small"), [approved["pin"]])
    with db._sessions() as session:
        rule = session.get(DesignRule, approved["pin"]["rule_id"])
        rule.state = "retired"
        why = knowledge_gate.refusal(db, cir, session=session)
        assert why and "history cannot be verified" in why, why
        assert rule.state == "retired" and rule in session.dirty
        session.rollback()
