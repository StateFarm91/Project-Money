"""Refusals. Messages are fixed text: never a value, a key, a session token or ciphertext."""
from __future__ import annotations


class PrivateRefused(PermissionError):
    """Base class for every refusal raised by the private context."""


class KeyUnavailable(PrivateRefused):
    """BRAMBLELOOP_PRIVATE_MEMORY_KEY is absent or unusable: nothing is stored or read."""


class KeyMismatch(PrivateRefused):
    """A record was sealed under a different key than the one configured."""


class PrivateAccessRefused(PrivateRefused):
    """The caller is not a live, explicitly private owner context."""


class PrivateProvenanceRefused(PrivateRefused, ValueError):
    """Only owner-supplied text and genuine interaction records may be stored."""


class IntegrityRefused(PrivateRefused):
    """Ciphertext or its bound metadata failed authentication (tampered or corrupted)."""
