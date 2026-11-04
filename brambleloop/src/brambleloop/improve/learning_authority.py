"""Review-only Learning authority contract; no production caller is wired.

An independently trusted live anchor and a fence covering all evidence and
approval writers through commit are required. No production provider exists here.
"""
from __future__ import annotations

from typing import Callable, Protocol
from ..core.sealed_chain import GrantLedger

APPROVED = "learning.authority.approved.v1"
REVOKED = "learning.authority.revoked.v1"
REBASED = "learning.authority.rebased.v1"
DOMAIN = "brambleloop.learning.approval.v1"
PRINCIPAL = "owner:learning"
FIELDS = ("domain", "principal", "producer", "reviewer", "rule_id", "rule_version",
          "rule_digest", "evaluation_id", "evaluation_digest")


class AuthorityRefused(RuntimeError):
    """Required authority or action-time boundary is unavailable."""


class EvidenceFence(Protocol):
    def assert_held(self, session, expected: dict) -> None:
        """Raise unless authority, anchor and evidence writers are fenced through commit."""


class LiveAnchor(Protocol):
    def current_tail(self, session) -> tuple[int, str]:
        """Read independently protected live tail under the fence; stale snapshots refuse."""


def _ledger(verify: Callable[[dict, str], bool]) -> GrantLedger:
    def no_signing(_body):
        raise ValueError("this verifier has no signing credential")
    return GrantLedger(approved=APPROVED, revoked=REVOKED, rebased=REBASED,
                       principal=PRINCIPAL, seal=no_signing, verify=verify,
                       signature="learning-authority-v1", label="Learning owner authority")


def authorize_in_session(session, grant_id: int, expected: dict, *,
                         verify: Callable[[dict, str], bool] | None,
                         anchor: LiveAnchor | None, fence: EvidenceFence | None) -> None:
    """Refuse unless fenced family, live tail and exact signed grant all match.

    Caller derives expected values from fenced DB evidence and preserves the
    fence through commit. This cannot configure an anchor or acquire locks.
    """
    import re
    from sqlalchemy import select, text
    from ..core.models import AuditLog

    if verify is None or anchor is None or fence is None:
        raise AuthorityRefused("trusted verifier, live anchor and evidence fence are required")
    if not session.in_transaction() or session.new or session.dirty or session.deleted:
        raise AuthorityRefused("a clean, active caller-owned transaction is required")
    if type(grant_id) is not int or grant_id <= 0 or not isinstance(expected, dict):
        raise AuthorityRefused("invalid Learning grant identity or binding")
    if set(expected) != set(FIELDS):
        raise AuthorityRefused("complete Learning evidence binding is required")
    if expected["domain"] != DOMAIN or expected["principal"] != PRINCIPAL:
        raise AuthorityRefused("wrong Learning authority domain or principal")
    if (not isinstance(expected["producer"], str) or not expected["producer"].strip()
            or not isinstance(expected["reviewer"], str) or not expected["reviewer"].strip()
            or expected["producer"].strip().casefold() == expected["reviewer"].strip().casefold()):
        raise AuthorityRefused("producer and independent reviewer must be distinct")
    for name in ("rule_id", "rule_version", "evaluation_id"):
        if type(expected[name]) is not int or expected[name] <= 0:
            raise AuthorityRefused("invalid Learning evidence identifier")
    for name in ("rule_digest", "evaluation_digest"):
        if not isinstance(expected[name], str) or not re.fullmatch(r"[0-9a-f]{64}", expected[name]):
            raise AuthorityRefused("invalid Learning evidence digest")
    try:
        if session.bind.dialect.name == "postgresql":
            isolation = session.execute(text("SHOW transaction_isolation")).scalar_one()
            if str(isolation).lower() != "read committed":
                raise AuthorityRefused("Learning authorization requires READ COMMITTED")
        fence.assert_held(session, expected)
        current = anchor.current_tail(session)
        ledger = _ledger(verify)
        entries = list(session.scalars(select(AuditLog).where(
            AuditLog.action.in_(ledger.actions)).order_by(AuditLog.id)
            .execution_options(populate_existing=True)))
        if not entries or current != (entries[-1].id, (entries[-1].detail or {}).get("seal")):
            raise AuthorityRefused("Learning authority tail does not match live anchor")
        refusal = ledger.refusal_in_session(session, grant_id)
        if refusal:
            raise AuthorityRefused(refusal)
        grant = next((row for row in entries if row.id == grant_id), None)
        if grant is None or not isinstance(grant.detail, dict):
            raise AuthorityRefused("Learning grant is missing")
        if any(grant.detail.get(name) != expected[name] for name in FIELDS):
            raise AuthorityRefused("Learning grant does not match current evidence")
    except AuthorityRefused:
        raise
    except Exception as exc:
        raise AuthorityRefused("Learning authority evidence is unavailable") from exc


def guarded_database_action(session, grant_id: int, expected: dict, *, verify, anchor, fence,
                            action: Callable):
    """Invoke a DB-only callback in the caller transaction without committing.

    Callback must not commit or cause external effects; this cannot enforce that.
    Production requires a real fence, outbox, actor and revocation policy.
    """
    authorize_in_session(session, grant_id, expected, verify=verify, anchor=anchor, fence=fence)
    return action(session)
