"""Opt-in PostgreSQL snapshot tests; use only an empty disposable database."""
import os

import pytest
from sqlalchemy import inspect, select, text

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import DesignRule
from brambleloop.improve import design_knowledge, knowledge_gate
from brambleloop.products import launch0
from test_w5_a6_frozen_knowledge import _approved_rule


def test_committed_retirement_and_repeatable_read_snapshot_are_held():
    url = os.getenv("BRAMBLELOOP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("requires an empty disposable PostgreSQL database")
    db = Database(url, scratch=True)
    if db.engine.dialect.name != "postgresql":
        pytest.fail("BRAMBLELOOP_TEST_POSTGRES_URL must name PostgreSQL")
    assert not inspect(db.engine).get_table_names(), "database must be empty"
    db.create_all()
    with db.session() as session:
        assert session.scalar(select(DesignRule.id).limit(1)) is None, "database must be empty"
    Registry(db).seed_defaults()
    approved = _approved_rule(db)
    cir = design_knowledge.freeze_pins(db, launch0.cir_for("basket_small"), [approved["pin"]])
    rule_id = approved["pin"]["rule_id"]
    with db._sessions() as reader:
        rule = reader.get(DesignRule, rule_id)
        assert rule.state == "approved"
        with db.session() as writer:
            writer.get(DesignRule, rule_id).state = "retired"
        assert "does not verify" in knowledge_gate.refusal(db, cir, session=reader)
    with db.session() as writer:
        writer.get(DesignRule, rule_id).state = "approved"
    with db._sessions() as reader:
        reader.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        assert reader.get(DesignRule, rule_id).state == "approved"
        with db.session() as writer:
            writer.get(DesignRule, rule_id).state = "retired"
        why = knowledge_gate.refusal(db, cir, session=reader)
        assert why and "cannot be verified" in why, why
