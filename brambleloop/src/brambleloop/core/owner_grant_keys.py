"""WS4-0a (design ddde00cc §2.2, F-A): owner publication and activation grants are Ed25519.

Before this module, `ops.publication_authority._seal` and `ops.activation_authority._seal` were
HMAC-SHA256 under `BRAMBLELOOP_OPS_TOKEN`, and verifying a grant recomputed that HMAC. Every
process that verifies a grant (the worker, at `runtime/pipeline.py` and the Etsy client) held
the token, so every such process could also MINT an owner grant.

Now a grant row is signed with an Ed25519 private key and verified with its public key:

* `BRAMBLELOOP_OWNER_GRANT_SIGNING_KEY` -- base64 of the raw 32-byte private key. Held by the
  web process only. A dedicated worker process scrubs it at startup (`mark_job_process`, called
  from `app.worker_entry` and `app.hq_worker`) and can never sign.
* `BRAMBLELOOP_OWNER_GRANT_VERIFY_KEY` -- base64 of the raw 32-byte public key. All the worker
  needs: it verifies, and cannot produce a signature.

`generate_keypair()` prints a fresh pair for the operator to set as environment variables;
no key is ever written to the repository, an issue, a log or a test.

Domain separation: every signature covers ``<family domain>\\n<canonical JSON>``, so a
publication row can never verify as an activation row (or as a storefront grant, which keeps
its own key pair).

What may be signed (`sign`):
* an approval or a rebase -- the two rows that GRANT or re-anchor authority -- only inside the
  owner's Command Center request (`owner_request`, entered by the action route after session,
  CSRF/nonce and step-up), never through the operator bearer route;
* a revocation -- it can only tighten -- from any process that may sign at all;
* nothing at all in a process marked as a job process.

Mode S (one Railway service, the embedded worker on; today): the web process also runs job
handlers, so nothing separates the signing key from job code in the same container -- exactly
as the ops token is not separated today. WS4-0a therefore does not make Mode S stronger, and
is honest about it (`deployment_note`); it does not make it weaker either, and the owner's
per-product approval of the first real listing (design §9 M2) stays possible. In Mode T (the
worker as its own service, an owner spend decision, §9 M4) the worker holds only the verify key
and F-A is closed.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
from contextlib import contextmanager

SIGNING_KEY_VAR = "BRAMBLELOOP_OWNER_GRANT_SIGNING_KEY"
VERIFY_KEY_VAR = "BRAMBLELOOP_OWNER_GRANT_VERIFY_KEY"
EMBEDDED_VAR = "BRAMBLELOOP_EMBEDDED_WORKER"
ALG = "ed25519"
# Review 6817118202 F2: the ONLY body signed outside the owner request is a revocation, and it
# must be exactly a revocation (GrantLedger.revoke's keys plus the chain link): an approval
# body cannot be relabelled "revoked" to dodge the gate.
_REVOCATION_KEYS = frozenset({"principal", "approval_id", "grant_seal", "revoked_at", "event",
                              "seq", "prev_id", "prev_seal"})
_REVOCATION_OPTIONAL = frozenset({"rebase"})

_JOB_PROCESS = {"is": False}
_OWNER_REQUEST: contextvars.ContextVar = contextvars.ContextVar("owner_grant_request",
                                                               default=None)


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      default=str)


def _b64key(var: str) -> bytes:
    import base64

    raw = os.environ.get(var, "").strip()
    if not raw:
        raise ValueError(f"{var} is not set in this process")
    key = base64.b64decode(raw, validate=True)
    if len(key) != 32:
        raise ValueError(f"{var} must be a base64 32-byte Ed25519 key")
    return key


def mark_job_process() -> bool:
    """Called at a dedicated worker's startup: this process runs jobs and may never sign an
    owner grant. Scrubs the signing key from the environment. Returns whether one was set."""
    _JOB_PROCESS["is"] = True
    return os.environ.pop(SIGNING_KEY_VAR, None) is not None


def signing_refusal() -> str | None:
    if _JOB_PROCESS["is"]:
        return "this process runs jobs, so it may never sign an owner grant"
    return None


def deployment_note() -> str:
    """What the key separation achieves in this deployment, stated plainly."""
    if os.environ.get(EMBEDDED_VAR, "1") == "1":
        return ("Mode S: job handlers share the web process, so the owner-grant signing key is "
                "not separated from job code (as the ops token is not). Separation needs the "
                "worker as its own service (Mode T, an owner decision), with the signing key "
                "set on the web service only, never on the worker.")
    return ("Mode T: the worker holds only the verify key; no job process can sign an owner "
            "grant. The signing key must never be SET on the worker service at all: the "
            "start-up scrub is hygiene, not a boundary (/proc/self/environ keeps the original "
            "environment).")


@contextmanager
def owner_request(session_public_id: str):
    """Set by the Command Center action route only, after session, CSRF/nonce and step-up."""
    token = _OWNER_REQUEST.set(str(session_public_id or ""))
    try:
        yield
    finally:
        _OWNER_REQUEST.reset(token)


def in_owner_request() -> bool:
    return bool(_OWNER_REQUEST.get())


# Review 5060fcc7 INFO-4: the event is matched exactly (a whole `owner.<family>.revoked`
# name), not by suffix, so "...approved\n.revoked" is not a revocation either.
_REVOCATION_EVENT = re.compile(r"owner\.[a-z_]+\.revoked")


def _is_revocation(detail: dict) -> bool:
    d = detail or {}
    keys = set(d)
    event = d.get("event")
    return (isinstance(event, str) and _REVOCATION_EVENT.fullmatch(event) is not None
            and _REVOCATION_KEYS <= keys <= (_REVOCATION_KEYS | _REVOCATION_OPTIONAL))


def _granting(detail: dict) -> bool:
    """Everything but an exact revocation body needs the owner's request context."""
    return not _is_revocation(detail)


def sign(domain: str, detail: dict) -> str:
    """Ed25519 signature (hex) over the domain and the canonical JSON of `detail`."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    why = signing_refusal()
    if why:
        raise ValueError(f"owner grant signing refused: {why}")
    if _granting(detail) and not in_owner_request():
        raise ValueError("an owner grant or rebase is signed only inside the owner's Command "
                         "Center request (session, CSRF/nonce and step-up), never through the "
                         "operator bearer route")
    try:
        key = Ed25519PrivateKey.from_private_bytes(_b64key(SIGNING_KEY_VAR))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"owner grant signing key unavailable: {exc}") from None
    return key.sign(f"{domain}\n{_json(detail)}".encode()).hex()


def verify(domain: str, detail: dict, seal: str) -> bool:
    """True only for a valid Ed25519 signature by the configured key over this domain.
    A missing or malformed verify key raises ValueError (callers refuse)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64key(VERIFY_KEY_VAR))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"owner grant verify key unavailable: {exc}") from None
    if not is_signature(seal):
        return False
    try:
        pub.verify(bytes.fromhex(str(seal)), f"{domain}\n{_json(detail)}".encode())
        return True
    except (InvalidSignature, ValueError):
        return False


_SIG_HEX = frozenset("0123456789abcdef")


def is_signature(seal) -> bool:
    """Review 6817118202 F5: an Ed25519 signature is exactly 128 lowercase hex characters."""
    s = str(seal or "")
    return len(s) == 128 and set(s) <= _SIG_HEX


def legacy_hmac_seal(seal) -> bool:
    """A 64-hex seal is the retired pre-WS4-0 HMAC scheme (an Ed25519 signature is 128 hex)."""
    s = str(seal or "")
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def generate_keypair() -> dict:
    """A fresh (signing, verify) pair as base64, for the operator to set. Never committed."""
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    raw_priv = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                 serialization.NoEncryption())
    raw_pub = key.public_key().public_bytes(serialization.Encoding.Raw,
                                            serialization.PublicFormat.Raw)
    return {SIGNING_KEY_VAR: base64.b64encode(raw_priv).decode(),
            VERIFY_KEY_VAR: base64.b64encode(raw_pub).decode()}


if __name__ == "__main__":  # pragma: no cover - operator tool: prints a fresh pair once
    for name, value in generate_keypair().items():
        print(f"{name}={value}")
