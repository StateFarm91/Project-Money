"""Encryption at rest for the private context.

Primitive: AES-256-GCM (authenticated encryption) from the `cryptography` package already in
the environment (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`). Each record gets a
fresh random 96-bit nonce. The record's non-content metadata (record id, kind, provenance,
key index, creation time) is bound as associated data, so moving or relabelling a ciphertext
-- e.g. flipping its provenance column -- fails authentication exactly like a flipped byte.

Key: `BRAMBLELOOP_PRIVATE_MEMORY_KEY`, base64 (standard or URL-safe) of at least 32 random
bytes (generate with `python -c "import secrets,base64;print(base64.urlsafe_b64encode(
secrets.token_bytes(32)).decode())"`). Absent, undecodable, short or degenerate (one repeated
byte) -> `KeyUnavailable`; nothing is ever written in plaintext as a fallback. Separate
sub-keys are derived with HKDF-SHA256 for encryption, the blind key index, principal tags
and the key identifier, so no sub-key reveals another. The key itself never leaves this
module and never appears in a message, a row or a log.

Losing the key loses the private store: by design there is no recovery path that does not
hold the key (see the handoff's continuity notes).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .errors import IntegrityRefused, KeyMismatch, KeyUnavailable

ENV = "BRAMBLELOOP_PRIVATE_MEMORY_KEY"
MIN_KEY_BYTES = 32
NONCE_BYTES = 12
SCHEME = "aesgcm256-v1"
_SALT = b"brambleloop/laura-private/v1"


@dataclass(frozen=True)
class Keys:
    enc: bytes
    index: bytes
    tag: bytes
    key_id: str

    def __repr__(self) -> str:  # never print key material
        return f"Keys(key_id={self.key_id})"

    __str__ = __repr__


def _derive(master: bytes, label: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=_SALT,
                info=f"brambleloop/laura-private/{label}".encode()).derive(master)


def _decode(raw: str) -> bytes:
    raw = raw.strip()
    pad = "=" * (-len(raw) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return decoder(raw + pad)
        except (binascii.Error, ValueError):
            continue
    raise KeyUnavailable(f"{ENV} is not valid base64")


def load_keys(env=None) -> Keys:
    env = os.environ if env is None else env
    raw = env.get(ENV) or ""
    if not raw.strip():
        raise KeyUnavailable(f"{ENV} is not set: the private context refuses to store or read")
    master = _decode(raw)
    if len(master) < MIN_KEY_BYTES:
        raise KeyUnavailable(f"{ENV} must decode to at least {MIN_KEY_BYTES} bytes")
    if len(set(master)) <= 1:
        raise KeyUnavailable(f"{ENV} is degenerate (one repeated byte)")
    kid = _derive(master, "key-id")
    return Keys(enc=_derive(master, "enc"), index=_derive(master, "index"),
                tag=_derive(master, "principal-tag"),
                key_id=hashlib.sha256(kid).hexdigest()[:16])


def blind_index(keys: Keys, text: str) -> str:
    return hmac.new(keys.index, text.encode("utf-8"), hashlib.sha256).hexdigest()


def tag(keys: Keys, *parts: str) -> str:
    return hmac.new(keys.tag, "\x1f".join(parts).encode("utf-8"), hashlib.sha256).hexdigest()


def tags_equal(a: str, b: str) -> bool:
    return isinstance(a, str) and isinstance(b, str) and hmac.compare_digest(a, b)


def seal(keys: Keys, plaintext: bytes, aad: bytes) -> tuple[str, str]:
    nonce = secrets.token_bytes(NONCE_BYTES)
    ct = AESGCM(keys.enc).encrypt(nonce, plaintext, aad)
    return (base64.b64encode(nonce).decode("ascii"), base64.b64encode(ct).decode("ascii"))


def open_sealed(keys: Keys, key_id: str, nonce_b64: str, ct_b64: str, aad: bytes) -> bytes:
    if not tags_equal(key_id, keys.key_id):
        raise KeyMismatch("record was sealed under a different private key")
    try:
        nonce = base64.b64decode(nonce_b64, validate=True)
        ct = base64.b64decode(ct_b64, validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise IntegrityRefused("private record failed authentication") from None
    if len(nonce) != NONCE_BYTES:
        raise IntegrityRefused("private record failed authentication")
    try:
        return AESGCM(keys.enc).decrypt(nonce, ct, aad)
    except InvalidTag:
        raise IntegrityRefused("private record failed authentication") from None
