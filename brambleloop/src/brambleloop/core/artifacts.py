"""Artifact store: content-addressed files with their hashes recorded in the database.

Master Plan section 13 lists object storage as core infrastructure. None is provisioned, so
this writes to a local directory -- which on a container platform is ephemeral, and saying so
plainly matters more than the storage itself.

The split is deliberate. The *bytes* live on disk and may not survive a restart; the *hash*
lives in Postgres and does. That means the system can always answer "is the PDF we are about
to ship the one that was certified?", and when a file is gone it knows it is gone rather than
silently serving a different one. Swapping in S3 later changes `_write` and nothing else.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DIR = os.environ.get("BRAMBLELOOP_ARTIFACT_DIR", "artifacts")


class ArtifactMissing(FileNotFoundError):
    """A recorded artifact is not on disk. Expected on ephemeral storage; never ignored."""


@dataclass(frozen=True)
class StoredArtifact:
    key: str
    sha256: str
    bytes_len: int
    content_type: str
    path: str
    durable: bool

    def to_dict(self) -> dict:
        return {"key": self.key, "sha256": self.sha256, "bytes": self.bytes_len,
                "content_type": self.content_type, "durable": self.durable}


class ArtifactStore:
    def __init__(self, root: str | os.PathLike | None = None):
        self.root = Path(root or DEFAULT_DIR)
        # Local disk is durable on a developer machine and ephemeral in a container. We only
        # claim durability where object storage is actually configured, which it is not.
        self.durable = False

    def put(self, key: str, payload: bytes, content_type: str, *,
            db=None, keep: str = "") -> StoredArtifact:
        """Store the bytes. With `db` and `keep`, also store them where a restart cannot
        reach them, and say in `keep` why this one is worth a database row."""
        digest = hashlib.sha256(payload).hexdigest()
        path = self.root / digest[:2] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            tmp = path.with_suffix(".partial")
            tmp.write_bytes(payload)
            tmp.replace(path)  # atomic: a reader never sees a half-written artifact
        kept = bool(db is not None and keep) and _keep(db, digest, payload,
                                                       content_type, keep)
        return StoredArtifact(key=key, sha256=digest, bytes_len=len(payload),
                              content_type=content_type, path=str(path),
                              durable=self.durable or kept)

    def get(self, sha256: str, *, db=None) -> bytes:
        path = self.root / sha256[:2] / sha256
        if not path.exists():
            recovered = _recover(db, sha256) if db is not None else None
            if recovered is not None:
                # Put it back on disk so the next read is a file read again.
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".partial")
                tmp.write_bytes(recovered)
                tmp.replace(path)
                return recovered
            raise ArtifactMissing(
                f"artifact {sha256[:12]} is recorded but not on disk. Object storage is not "
                f"provisioned, so files do not survive a container restart; the hash is "
                f"durable and the bytes are not. Re-render from the certified CIR."
            )
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != sha256:
            raise ArtifactMissing(
                f"artifact {sha256[:12]} is corrupt on disk (reads back as {actual[:12]})")
        return data

    def exists(self, sha256: str) -> bool:
        return (self.root / sha256[:2] / sha256).exists()


def _keep(db, digest: str, payload: bytes, content_type: str, why: str) -> bool:
    """Write the bytes to Postgres as well as to disk. Idempotent on the digest."""
    from sqlalchemy import select

    from .models import DurableArtifact

    try:
        with db.session() as s:
            if s.get(DurableArtifact, digest) is not None:
                return True
            s.add(DurableArtifact(sha256=digest, content_type=content_type,
                                  bytes_len=len(payload), payload=payload,
                                  why_kept=why[:200]))
            # Read back through the same session so a write that silently did nothing is
            # not reported as durable -- "kept" is a claim about the database, and this
            # module's whole design is that it only claims durability where it has it.
            s.flush()
            return s.scalar(select(DurableArtifact.sha256).where(
                DurableArtifact.sha256 == digest)) == digest
    except Exception:                                        # pragma: no cover - defensive
        # A keep that fails must not fail the render. The file is still on disk and the
        # hash is still recorded; what is lost is the restart guarantee, and reporting
        # `durable=False` is exactly how this module says so.
        return False


def _recover(db, sha256: str) -> bytes | None:
    """The kept bytes, if this artifact was one of the few worth keeping."""
    from .models import DurableArtifact

    try:
        with db.session() as s:
            row = s.get(DurableArtifact, sha256)
            if row is None:
                return None
            payload = bytes(row.payload)
    except Exception:                                        # pragma: no cover - defensive
        return None
    if hashlib.sha256(payload).hexdigest() != sha256:        # pragma: no cover - defensive
        return None
    return payload
