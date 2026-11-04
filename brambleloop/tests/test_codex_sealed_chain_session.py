"""Caller-owned transaction checks for the existing sealed grant ledger."""
import hashlib
import hmac
import json

from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog, Incident
from brambleloop.core.sealed_chain import GrantLedger


def test_session_check_observes_uncommitted_revocation_and_rollback(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'ledger.db'}", scratch=True)
    db.create_all()

    def seal(value):
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hmac.new(b"test-fixture-only", raw, hashlib.sha256).hexdigest()

    ledger = GrantLedger(approved="fixture.approved", revoked="fixture.revoked",
                         rebased="fixture.rebased", principal="owner:fixture",
                         seal=seal, signature="fixture", label="fixture")
    grant_id = ledger.append(db, action=ledger.approved, artifact="subject",
                             detail={"principal": ledger.principal})
    with db._sessions() as session:
        assert ledger.refusal_in_session(session, grant_id) is None
        # A revocation in the caller's transaction must affect this check even
        # before commit; rollback restores the previous usable chain.
        session.add(AuditLog(actor=ledger.principal, action=ledger.revoked,
                             artifact=str(grant_id), detail={}))
        assert ledger.refusal_in_session(session, grant_id) is not None
        session.rollback()
        assert ledger.refusal_in_session(session, grant_id) is None

    revocation_id = ledger.revoke(db, grant_id)
    with db._sessions() as session:
        assert "revoked" in ledger.refusal_in_session(session, grant_id)
        assert ledger.refusal_in_session(session, revocation_id) is not None
    with db.session() as session:
        session.get(AuditLog, revocation_id).artifact = "999999"
    with db._sessions() as session:
        assert ledger.refusal_in_session(session, grant_id) is not None
    # The legacy decision API must also refuse; the altered unsigned artifact
    # must not conceal the signed revocation's target.
    assert ledger.refusal(db, grant_id) is not None
    from sqlalchemy import select
    with db.session() as session:
        assert session.scalar(select(Incident).where(Incident.signature == "fixture")) is not None


def test_session_check_refuses_identity_map_stale_actor(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'ledger.db'}", scratch=True)
    db.create_all()
    ledger = GrantLedger(approved="fixture.approved", revoked="fixture.revoked",
                         rebased="fixture.rebased", principal="owner:fixture",
                         seal=lambda value: hashlib.sha256(
                             json.dumps(value, sort_keys=True).encode()).hexdigest(),
                         signature="fixture", label="fixture")
    grant_id = ledger.append(db, action=ledger.approved, artifact="subject",
                             detail={"principal": ledger.principal})
    with db._sessions() as reader:
        assert reader.get(AuditLog, grant_id).actor == ledger.principal
        with db.session() as writer:
            writer.get(AuditLog, grant_id).actor = "other"
        assert ledger.refusal_in_session(reader, grant_id) is not None


def test_legacy_refusal_still_records_broken_chain_incident(tmp_path):
    from sqlalchemy import select
    from brambleloop.core.models import Incident

    db = Database(f"sqlite:///{tmp_path / 'ledger.db'}", scratch=True)
    db.create_all()
    ledger = GrantLedger(approved="fixture.approved", revoked="fixture.revoked",
                         rebased="fixture.rebased", principal="owner:fixture",
                         seal=lambda value: hashlib.sha256(
                             json.dumps(value, sort_keys=True).encode()).hexdigest(),
                         signature="fixture-chain-tamper", label="fixture")
    grant_id = ledger.append(db, action=ledger.approved, artifact="subject",
                             detail={"principal": ledger.principal})
    with db.session() as session:
        row = session.get(AuditLog, grant_id)
        row.detail = {**row.detail, "seal": "invalid"}
    assert ledger.refusal(db, grant_id) is not None
    with db.session() as session:
        assert session.scalar(select(Incident).where(
            Incident.signature == "fixture-chain-tamper")) is not None
