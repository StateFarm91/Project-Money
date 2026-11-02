"""Versioned design knowledge, proposed from existing learning evidence.

The store accepts only registered rule identifiers and structured provenance. A
proposal is not an approval; evaluation and independent approval must be added
before any rule is made active or used by a design consumer.
"""
from __future__ import annotations

import re

from sqlalchemy import func, select

from ..core.models import DesignRule, Incident, Lesson, TeardownFinding


class DesignKnowledgeRefused(ValueError):
    """The proposal cannot be represented safely as design knowledge."""


# Rule meanings belong to our own implementation. Source text and arbitrary
# instructions cannot be embedded as a parameter.
RULES = {"include_finishing_checklist": frozenset()}
# Expand only alongside a consumer that understands the new scope.
SCOPE_VALUES = {"writer_section": frozenset({"finishing"})}
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SOURCES = {"lesson": Lesson, "finding": TeardownFinding, "incident": Incident}


def propose(db, *, key: str, statement: dict, scope: dict, provenance: list,
            producer: str, supersedes: int | None = None) -> dict:
    """Persist a proposal; its evidence must already exist in the learning system."""
    if not isinstance(key, str) or not _TOKEN.fullmatch(key):
        raise DesignKnowledgeRefused("invalid rule key")
    if not isinstance(producer, str) or not producer.strip() or len(producer) > 120:
        raise DesignKnowledgeRefused("producer is required")
    from ..teardown.library import check_derived

    check_derived(producer)
    if not isinstance(statement, dict) or set(statement) != {"rule", "parameters"}:
        raise DesignKnowledgeRefused("statement needs a registered rule and parameters")
    rule, parameters = statement["rule"], statement["parameters"]
    if not isinstance(rule, str) or rule not in RULES or not isinstance(parameters, dict):
        raise DesignKnowledgeRefused("unknown rule or invalid parameters")
    if set(parameters) != RULES[rule]:
        raise DesignKnowledgeRefused("parameters do not match the rule vocabulary")
    if (not isinstance(scope, dict) or not scope or not set(scope) <= set(SCOPE_VALUES)
            or any(not isinstance(v, str) or v not in SCOPE_VALUES[k]
                   for k, v in scope.items())):
        raise DesignKnowledgeRefused("invalid structured scope")
    if not isinstance(provenance, list) or not provenance:
        raise DesignKnowledgeRefused("evidence is required")
    evidence = []
    with db.session() as session:
        for item in provenance:
            if (not isinstance(item, dict) or set(item) != {"kind", "id"}
                    or not isinstance(item.get("kind"), str)
                    or item.get("kind") not in _SOURCES or type(item.get("id")) is not int
                    or item["id"] <= 0):
                raise DesignKnowledgeRefused("invalid evidence reference")
            source = session.get(_SOURCES[item["kind"]], item["id"])
            if source is None:
                raise DesignKnowledgeRefused("evidence does not exist")
            # Existing findings have no review state yet; do not silently treat
            # them as reviewed while that independent-review path is being built.
            if item["kind"] == "finding" and getattr(source, "review_state", None) != "reviewed":
                raise DesignKnowledgeRefused("finding has not been independently reviewed")
            if item in evidence:
                raise DesignKnowledgeRefused("duplicate evidence")
            evidence.append(dict(item))
        previous = session.get(DesignRule, supersedes) if supersedes is not None else None
        if supersedes is not None and (previous is None or previous.key != key):
            raise DesignKnowledgeRefused("superseded version must belong to this rule")
        version = (session.scalar(select(func.max(DesignRule.version))
                                  .where(DesignRule.key == key)) or 0) + 1
        row = DesignRule(key=key, version=version, statement=dict(statement), scope=dict(scope),
                         provenance=evidence, producer=producer.strip(), state="proposed",
                         supersedes=supersedes)
        session.add(row)
        session.flush()
        return {"id": row.id, "key": row.key, "version": row.version, "state": row.state}
