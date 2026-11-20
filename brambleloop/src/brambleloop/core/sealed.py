"""Sealing a secret so that the database can hold it and the database alone cannot spend it.

This exists because of one fact about OAuth that has no comfortable answer: **Etsy issues a
new refresh token on every refresh and spends the old one.** So the company's only write
credential is a value that changes, by itself, roughly every hour, and it must be written
somewhere the *running service* can update.

The candidates, and why each was rejected or chosen:

* **A repository file.** Refused outright by CLAUDE.md, and rightly: a credential in git is a
  credential in every clone, every CI log and every backup of the repository forever.
* **A Railway environment variable.** This is where every other secret in this system lives,
  and it is the right place for a secret a *human* sets. It is the wrong place for this one:
  the application cannot rewrite its own environment. `os.environ["X"] = ...` changes one
  process's copy and is gone on the next container start -- and this platform replaces the
  container several times an hour. A refresh token that rotates in memory and is not written
  down anywhere durable works until the next deploy and then needs the owner's browser again.
* **A container file.** Ephemeral on this platform for exactly the reason `core.db` refuses
  to start on SQLite: the disk does not survive a restart.
* **Postgres.** The one store this service can write, that survives a restart, and that the
  whole company already treats as its memory. It is the only candidate that satisfies "the
  running service must be able to update it".

Postgres on its own is not good enough, and this module is the difference. The database is
*read* in several places that a credential must never reach: `core.continuity.export` writes
every table into a portable file that `/api/continuity/export` serves as a download,
`core.backup` shells out to `pg_dump`, and anyone with the connection string can select from
it. A refresh token stored as a plain column is a refresh token in all of those.

So the token is **sealed**: encrypted with AES-256-GCM under a key derived from a secret that
stays in the environment, where secrets already live. The split is the point --

    the key lives where this system already keeps secrets (an environment variable a human
    sets and the app never rewrites), and the ciphertext lives where this system can write
    (Postgres, which rotates as often as Etsy demands).

-- and it means a database dump, a continuity export, a console session or a stolen backup
yields ciphertext and nothing else. Neither half is a credential by itself.

**No plaintext fallback.** If the key is absent this module refuses rather than storing the
value in the clear. That is the same direction `core.opsauth` chose for a missing operator
token: unconfigured means closed, because the opposite default is how a secret ends up in a
table during the window between deploying this and remembering to set the variable.

Sealing is also *context-bound*: the context string is authenticated with the ciphertext, so
a sealed PKCE verifier cannot be pasted into the column that holds a sealed refresh token and
unsealed there. Two different secrets in two different columns stay two different secrets.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets

# The environment variable holding the key material. A passphrase, not a formatted key: the
# owner should be able to paste 48 characters from a password manager without also having to
# produce valid base64 of exactly 32 bytes.
KEY_VAR = "BRAMBLELOOP_SECRET_KEY"

# Below this a passphrase is guessable, and the failure is silent -- everything works, and
# the sealing is decorative. Checked at use time rather than trusted, for the same reason
# `opsauth.MIN_TOKEN_LENGTH` is: a placeholder is exactly what gets left in an environment.
MIN_KEY_LENGTH = 32

# Stamped into every sealed value so a future change of algorithm can be recognised rather
# than mis-decrypted. A value whose version this build does not know is refused, not guessed.
SEAL_VERSION = "v1"

# Domain separation for the key derivation: the same passphrase used for something else in
# future derives a different key here.
_KDF_DOMAIN = b"brambleloop.sealed.v1|"

NONCE_BYTES = 12   # AES-GCM's standard nonce length; a fresh one per seal, never reused.


class SealUnavailable(RuntimeError):
    """There is no sealing key, so nothing may be stored. Never a reason to store plaintext."""


class SealBroken(ValueError):
    """A sealed value did not open: the key changed, or the bytes are not what they claim."""


def fingerprint(secret: str) -> str:
    """Eight hex characters of a SHA-256, so two secrets can be told apart in a report.

    Identical by construction to `integrations.http.fingerprint` and
    `integrations.etsy_oauth.fingerprint`, and restated rather than imported for the same
    reason those two are restated: `core` must not import `integrations`, and one shared
    identity for a secret across every report in this system is worth three lines.
    """
    if not secret:
        return "absent"
    return hashlib.sha256(secret.encode()).hexdigest()[:8]


def configured(env: dict[str, str] | None = None) -> bool:
    e = env if env is not None else os.environ
    return len((e.get(KEY_VAR) or "").strip()) >= MIN_KEY_LENGTH


def key_health(env: dict[str, str] | None = None) -> dict:
    """Whether sealing is usable, without revealing anything about the key.

    The fingerprint is included deliberately: it is how an operator tells "the key is set" from
    "the key is the *same* key the stored ciphertext was sealed under", which is the difference
    between a working deployment and one that will fail to unseal at the worst moment.
    """
    e = env if env is not None else os.environ
    raw = (e.get(KEY_VAR) or "").strip()
    return {
        "variable": KEY_VAR,
        "configured": bool(raw),
        "usable": len(raw) >= MIN_KEY_LENGTH,
        "min_length": MIN_KEY_LENGTH,
        "key_fingerprint": fingerprint(raw) if raw else "absent",
        "reason": ("" if len(raw) >= MIN_KEY_LENGTH
                   else "not set" if not raw
                   else f"shorter than {MIN_KEY_LENGTH} characters"),
    }


def _key(env: dict[str, str] | None = None) -> bytes:
    e = env if env is not None else os.environ
    raw = (e.get(KEY_VAR) or "").strip()
    if len(raw) < MIN_KEY_LENGTH:
        raise SealUnavailable(
            f"{KEY_VAR} is not set to a usable value ({MIN_KEY_LENGTH} characters or more), "
            f"so nothing can be sealed and nothing will be stored in the clear. It is set in "
            f"the hosting environment, never in this repository.")
    return hashlib.sha256(_KDF_DOMAIN + raw.encode("utf-8")).digest()


def _aead(key: bytes):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - `cryptography` is in requirements.txt
        raise SealUnavailable(
            "the `cryptography` package is not importable, so a secret cannot be sealed. It "
            "is in requirements.txt; a deployment without it must not fall back to storing "
            "credentials in the clear.") from exc
    return AESGCM(key)


def seal(plaintext: str, *, context: str, env: dict[str, str] | None = None) -> str:
    """Encrypt a secret for storage in a database column.

    `context` is authenticated but not encrypted: it binds the ciphertext to the thing it is.
    A sealed PKCE verifier moved into the refresh-token column fails to open rather than
    opening as the wrong secret.
    """
    if not plaintext:
        raise ValueError("refusing to seal an empty value: an empty credential is an absent "
                         "credential, and storing one hides that fact")
    nonce = secrets.token_bytes(NONCE_BYTES)
    blob = _aead(_key(env)).encrypt(nonce, plaintext.encode("utf-8"),
                                    context.encode("utf-8"))
    return f"{SEAL_VERSION}:{base64.urlsafe_b64encode(nonce + blob).decode()}"


def unseal(sealed: str, *, context: str, env: dict[str, str] | None = None) -> str:
    """Open a sealed value, or refuse. Never returns a partial or guessed result."""
    text = (sealed or "").strip()
    if not text:
        raise SealBroken("nothing to unseal: the stored value is empty")
    version, _, payload = text.partition(":")
    if version != SEAL_VERSION or not payload:
        raise SealBroken(
            f"sealed value carries format {version!r}, which this build does not know how to "
            f"open. Refusing to guess at a credential.")
    try:
        raw = base64.urlsafe_b64decode(payload.encode())
        nonce, blob = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
        return _aead(_key(env)).decrypt(nonce, blob, context.encode("utf-8")).decode("utf-8")
    except SealUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure here is the same answer
        # Deliberately opaque about *why*. The distinction between "wrong key", "wrong
        # context" and "corrupt bytes" is an oracle, and none of the three is actionable
        # differently by a caller: all of them mean re-authorise.
        raise SealBroken(
            f"a sealed value did not open ({type(exc).__name__}). Either {KEY_VAR} is not the "
            f"key this value was sealed under, or the stored bytes are damaged. The secret "
            f"cannot be recovered from here; it has to be issued again.") from None
