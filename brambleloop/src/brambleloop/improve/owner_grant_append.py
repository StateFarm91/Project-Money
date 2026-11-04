"""Review-only, transaction-composable owner grant append.

No production route, key, trusted anchor or fence is configured here. The
caller must supply independently trusted implementations whose guarantees hold
through the surrounding database transaction and its commit. In particular,
anchor advancement must roll back atomically with that transaction; an ordinary
mutable database row or a process-local variable is not a production anchor.
"""
from __future__ import annotations

from typing import Protocol


class OwnerDecision(Protocol):
    def assert_exact_decision(self, session, binding: dict) -> None:
        """Require fresh owner step-up and explicit acceptance of this exact binding.

        A generic step-up or existing unsigned approval row is insufficient.
        """


class WritableAnchor(Protocol):
    def current_tail(self, session) -> tuple[int, str]: ...
    def advance_tail(self, session, old: tuple[int, str], new: tuple[int, str]) -> None:
        """Compare-and-swap protected tail atomically with the caller transaction."""


def append_owner_grant_in_session(db, session, rule_id: int, *, sign, verify,
                                  anchor: WritableAnchor | None, fence,
                                  owner_decision: OwnerDecision | None) -> int:
    """Append a signed Learning grant after validating current approved evidence.

    This function does not obtain the fence, authenticate the owner, configure
    keys or commit. An injected fixture implementation proves only composition,
    not that production authority is available. No externally supplied evidence
    digests are accepted. The caller must propagate exceptions so every write,
    including the independently protected anchor advance, rolls back together.
    """
    from sqlalchemy import select
    from ..core.models import AuditLog, DesignRule
    from ..core.sealed_chain import GrantLedger, next_link
    from ..teardown.review import principal
    from . import design_knowledge as knowledge
    from .learning_authority import (APPROVED, DOMAIN, PRINCIPAL, REBASED, REVOKED,
                                     AuthorityRefused)
    from .read_session import bind_read_session

    if (not callable(sign) or not callable(verify) or anchor is None
            or fence is None or owner_decision is None):
        raise AuthorityRefused("exact owner decision, signer, verifier, live anchor and fence required")
    if type(rule_id) is not int or rule_id <= 0:
        raise AuthorityRefused("invalid Learning rule identity")
    try:
        bound_db = bind_read_session(db, session)
        connection = session.connection()
        if connection.dialect.name == "sqlite":
            # SQLite's legacy transaction mode does not BEGIN on SELECT. A
            # first-write savepoint would otherwise commit on RELEASE, escaping
            # a later outer rollback. This is not a cross-writer fence.
            raw = connection.connection.driver_connection
            if not raw.in_transaction:
                connection.exec_driver_sql("BEGIN")
        rule = session.scalar(select(DesignRule).where(DesignRule.id == rule_id)
                              .with_for_update().execution_options(populate_existing=True))
        if (rule is None or rule.state != "approved" or not rule.approved_at
                or not isinstance(rule.producer, str) or not rule.producer.strip()
                or principal(rule.approved_by or "") != "owner"
                or principal(rule.producer) == principal(rule.approved_by)):
            raise AuthorityRefused("current independently reviewed rule required")
        approval = session.scalar(select(AuditLog).where(
            AuditLog.action == "design_knowledge.rule_approved",
            AuditLog.artifact == f"design-rule:{rule.id}",
            AuditLog.actor == rule.approved_by).order_by(AuditLog.id.desc())
            .with_for_update().execution_options(populate_existing=True))
        detail = approval.detail if approval is not None and isinstance(approval.detail, dict) else {}
        evaluation_id = detail.get("evaluation_id")
        if type(evaluation_id) is not int or evaluation_id <= 0:
            raise AuthorityRefused("current approval evaluation is missing")
        digest = knowledge.rule_digest(rule)
        binding = {"domain": DOMAIN, "principal": PRINCIPAL, "producer": rule.producer,
                   "reviewer": rule.approved_by, "rule_id": rule.id,
                   "rule_version": rule.version, "rule_digest": digest,
                   "evaluation_id": evaluation_id,
                   "evaluation_digest": detail.get("evaluation_digest")}
        owner_decision.assert_exact_decision(session, binding)
        fence.assert_held(session, binding)
        # Re-check all current provenance and evaluation only after the caller's
        # fence is confirmed; neither decision nor digest is taken from a request.
        if rule.active_slot != knowledge.scope_slot(rule.scope):
            raise AuthorityRefused("Learning rule is no longer active")
        knowledge._revalidate_provenance(session, rule)
        evaluation_digest = knowledge._assert_evaluation(bound_db, session, rule, evaluation_id)
        if detail.get("rule_digest") != digest or evaluation_digest != binding["evaluation_digest"]:
            raise AuthorityRefused("Learning approval evidence changed")
        ledger = GrantLedger(approved=APPROVED, revoked=REVOKED, rebased=REBASED,
                             principal=PRINCIPAL, seal=sign, verify=verify,
                             signature="learning-authority-v1", label="Learning owner authority")
        entries = list(session.scalars(select(AuditLog).where(AuditLog.action.in_(ledger.actions))
                                       .order_by(AuditLog.id).with_for_update()
                                       .execution_options(populate_existing=True)))
        rows = []
        for row in entries:
            if (row.actor != PRINCIPAL or not isinstance(row.detail, dict)
                    or row.detail.get("event") != row.action):
                raise AuthorityRefused("Learning authority family metadata is inconsistent")
            rows.append((row.id, dict(row.detail)))
        old = (entries[-1].id, entries[-1].detail.get("seal")) if entries else (0, "")
        if anchor.current_tail(session) != old:
            raise AuthorityRefused("Learning authority live anchor does not match the family")
        chain = ledger._walk(rows)
        if not chain.get("valid"):
            raise AuthorityRefused("Learning authority family does not verify")
        body = {**binding, "event": APPROVED, **next_link(rows, chain)}
        body["seal"] = sign(body)
        if ledger.verify_row(body):
            raise AuthorityRefused("Learning owner signature does not verify")
        # If the caller catches an anchor refusal, the grant must not remain
        # pending and later be committed without its corresponding tail.
        with session.begin_nested():
            grant = AuditLog(actor=PRINCIPAL, action=APPROVED,
                             artifact=f"design-rule:{rule.id}", detail=body)
            session.add(grant)
            session.flush()
            anchor.advance_tail(session, old, (grant.id, body["seal"]))
            grant_id = grant.id
        return grant_id
    except AuthorityRefused:
        raise
    except Exception as exc:
        raise AuthorityRefused("Learning grant evidence or protected append unavailable") from exc
