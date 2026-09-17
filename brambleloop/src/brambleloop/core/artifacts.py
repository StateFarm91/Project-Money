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

    def put(self, key: str, payload: bytes, content_type: str) -> StoredArtifact:
        digest = hashlib.sha256(payload).hexdigest()
        path = self.root / digest[:2] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            tmp = path.with_suffix(".partial")
            tmp.write_bytes(payload)
            tmp.replace(path)  # atomic: a reader never sees a half-written artifact
        return StoredArtifact(key=key, sha256=digest, bytes_len=len(payload),
                              content_type=content_type, path=str(path),
                              durable=self.durable)

    def get(self, sha256: str) -> bytes:
        path = self.root / sha256[:2] / sha256
        if not path.exists():
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
