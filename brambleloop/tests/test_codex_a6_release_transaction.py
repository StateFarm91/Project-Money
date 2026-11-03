"""The proposed session interface does not commit or emit early effects."""
from sqlalchemy import select

from brambleloop.core.models import ArtefactProvenance, AuditLog, PatternVersion
from brambleloop.products import launch0
from brambleloop.publish import withholding
from brambleloop.runtime import pipeline
from test_w5_a6_frozen_knowledge import _store
from test_w5_integfix import _Ctx


def test_caller_owned_recertification_rolls_back_and_defers_effects():
    db, _ = _store()
    ctx = _Ctx(db)
    cir = launch0.cir_for("basket_small")
    pipeline._persist_release(ctx, cir, {"granted": True}, "a" * 64)
    withholding.record_reverification(db, cir.slug, cir.version,
                                      check="pdf", problem="pdf hash drift")
    assert not ctx.audits and not ctx.enqueued
    with db.session() as observer:
        prior = observer.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "certificate"))
        prior_sha = prior.sha256
        prior_audits = len(list(observer.scalars(select(AuditLog).where(
            AuditLog.action == "provenance.overwritten"))))

    with db._sessions() as session:
        session.begin()
        deferred = pipeline._persist_release(ctx, cir, {"granted": True}, "b" * 64,
                                             session=session)
        assert {event[0] for event in deferred} == {"enqueue", "audit"}
        assert not ctx.audits and not ctx.enqueued
        assert session.scalar(select(PatternVersion)).release_hash == "b" * 64
        changed = session.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "certificate"))
        assert changed.sha256 == "b" * 64
        assert len(list(session.scalars(select(AuditLog).where(
            AuditLog.action == "provenance.overwritten")))) > prior_audits
        with db.session() as observer:
            assert observer.scalar(select(PatternVersion)).release_hash == "a" * 64
        session.rollback()
    with db.session() as observer:
        assert observer.scalar(select(PatternVersion)).release_hash == "a" * 64
        assert observer.scalar(select(ArtefactProvenance).where(
            ArtefactProvenance.artefact_class == "certificate")).sha256 == prior_sha
        assert len(list(observer.scalars(select(AuditLog).where(
            AuditLog.action == "provenance.overwritten")))) == prior_audits
    assert not ctx.audits and not ctx.enqueued

    # A caller may choose to commit the database change, but must not mistake
    # returned in-memory intents for a durable outbox.
    with db._sessions() as session:
        with session.begin():
            deferred = pipeline._persist_release(ctx, cir, {"granted": True}, "b" * 64,
                                                 session=session)
    assert {event[0] for event in deferred} == {"enqueue", "audit"}
    assert not ctx.audits and not ctx.enqueued
    with db.session() as observer:
        assert observer.scalar(select(PatternVersion)).release_hash == "b" * 64


def test_first_release_provenance_rolls_back_with_the_release():
    db, _ = _store()
    ctx = _Ctx(db)
    cir = launch0.cir_for("basket_small")
    with db._sessions() as session:
        session.begin()
        assert pipeline._persist_release(ctx, cir, {"granted": True}, "a" * 64,
                                         session=session) == []
        assert session.scalar(select(PatternVersion)) is not None
        assert session.scalar(select(ArtefactProvenance)) is not None
        session.rollback()
    with db.session() as observer:
        assert observer.scalar(select(PatternVersion)) is None
        assert observer.scalar(select(ArtefactProvenance)) is None
        assert not list(observer.scalars(select(AuditLog).where(
            AuditLog.action == "provenance.overwritten")))
    assert not ctx.audits and not ctx.enqueued


def test_caller_owned_session_must_match_database_and_be_active():
    db, _ = _store()
    ctx = _Ctx(db)
    cir = launch0.cir_for("basket_small")
    with db._sessions() as session:
        try:
            pipeline._persist_release(ctx, cir, {}, "a" * 64, session=session)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted an inactive transaction")
    other, _ = _store()
    with other._sessions() as session:
        session.begin()
        try:
            pipeline._persist_release(ctx, cir, {}, "a" * 64, session=session)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted a session for a different database")
