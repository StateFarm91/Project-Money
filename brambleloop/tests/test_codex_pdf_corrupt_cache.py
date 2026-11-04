"""Customer delivery can recover verified bytes without changing the cache."""
import hashlib
from unittest.mock import patch

import pytest
from brambleloop.commerce import deliverables
from brambleloop.core.artifacts import ArtifactStore
from brambleloop.core.models import AuditLog, DurableArtifact
from test_w4_firstsale_deliverables import _db


def test_pdf_resolver_uses_only_verified_durable_bytes_for_corrupt_local_cache(tmp_path):
    db = _db()
    payload = b"%PDF-1.4 sold file"
    sha = hashlib.sha256(payload).hexdigest()
    assert deliverables.keep(db, payload, "application/pdf", "test")
    with db.session() as session:
        session.add(AuditLog(actor="assets", action="assets.built", artifact="item@1",
                             detail={"pdf_sha256_by_terminology": {"US": sha}}))
    store = ArtifactStore(tmp_path)
    path = tmp_path / sha[:2] / sha
    path.parent.mkdir()
    path.write_bytes(b"corrupt")
    got = deliverables.resolve_pdf(db, "item", "1", store=store,
                                   render=lambda *_: pytest.fail("unexpected rerender"))
    assert got["bytes"] == payload and got["sha256"] == sha and got["source"] == "durable"
    assert path.read_bytes() == b"corrupt"
    with db.session() as session:
        session.get(DurableArtifact, sha).payload = b"also corrupt"
    with pytest.raises(deliverables.DeliveryRefused):
        deliverables.resolve_pdf(db, "item", "1", store=store, render=lambda *_: {"US": b"other"})
    assert path.read_bytes() == b"corrupt"


def test_corrupt_symlink_target_is_not_replaced(tmp_path):
    db = _db()
    payload = b"%PDF-1.4 good file"
    sha = hashlib.sha256(payload).hexdigest()
    assert deliverables.keep(db, payload, "application/pdf", "test")
    with db.session() as session:
        session.add(AuditLog(actor="assets", action="assets.built", artifact="item@1",
                             detail={"pdf_sha256_by_terminology": {"US": sha}}))
    store = ArtifactStore(tmp_path)
    path = tmp_path / sha[:2] / sha
    path.parent.mkdir()
    target = tmp_path / "other"
    target.write_bytes(b"unrelated")
    path.symlink_to(target)
    assert deliverables.resolve_pdf(db, "item", "1", store=store)["bytes"] == payload
    assert path.is_symlink() and target.read_bytes() == b"unrelated"


def test_pdf_resolver_works_when_cache_read_is_denied(tmp_path):
    db = _db()
    payload = b"%PDF-1.4 recoverable"
    sha = hashlib.sha256(payload).hexdigest()
    assert deliverables.keep(db, payload, "application/pdf", "test")
    with db.session() as session:
        session.add(AuditLog(actor="assets", action="assets.built", artifact="item@1",
                             detail={"pdf_sha256_by_terminology": {"US": sha}}))
    store = ArtifactStore(tmp_path)
    with patch.object(store, "get", side_effect=PermissionError("cache unavailable")):
        assert deliverables.resolve_pdf(db, "item", "1", store=store)["bytes"] == payload
