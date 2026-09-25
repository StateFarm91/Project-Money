"""The copy that survives losing this provider, and the proof that it would.

Requirement 51. `continuity.retain` keeps an export in the database it describes, which
survives a container replacement, a redeploy and a crash -- the failures that actually
happen -- and not the provider disappearing, which is the failure this module is for.

**Written against the S3 API, so the provider is a URL rather than a code change.** Backblaze
B2, Cloudflare R2, Wasabi and AWS itself all speak it. That is the reliability answer as much
as the cost one: a continuity plan whose implementation is welded to one vendor has moved the
single point of failure rather than removed it, and the day this matters is the day that
vendor is the thing that went wrong.

**Signed by hand, because a dependency is a supply chain.** SigV4 is sixty lines of
well-specified hashing and this container already carries no cloud SDK. The signing is tested
against the signature AWS publishes for its own worked example, so the implementation is
checked against the specification rather than against itself.

**Encrypted before it leaves, with a key that is not the bucket's.** An archive is every row
this company has. Object storage credentials leak through misconfiguration more often than
through anything dramatic, so the bytes are AES-encrypted locally and the key lives in a
separate variable: a reader who obtains the bucket gets ciphertext, and a reader who obtains
the key without the bucket gets nothing at all.

**A backup nobody has restored is a hope.** `verify()` downloads what was just uploaded,
decrypts it, checks the digest and restores it into a scratch database -- and the gate this
module opens is that round trip having succeeded, not a URL being configured. #51's own
history is the argument: the gate used to read `BRAMBLELOOP_ARCHIVE_URL`, and a typed bucket
address that is wrong, or whose credentials are, survives losing the provider exactly as well
as no bucket at all.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

from .resilience import PermanentError, TransientError

# Endpoint, bucket and credentials. Four variables rather than one connection string: a
# string that has to be parsed is a string that can be half-right, and the failure of a
# half-right archive endpoint is silent until the day it is read.
ENDPOINT_VAR = "BRAMBLELOOP_ARCHIVE_URL"        # e.g. https://s3.us-west-004.backblazeb2.com
BUCKET_VAR = "BRAMBLELOOP_ARCHIVE_BUCKET"
KEY_ID_VAR = "BRAMBLELOOP_ARCHIVE_KEY_ID"
SECRET_VAR = "BRAMBLELOOP_ARCHIVE_SECRET"       # noqa: S105 - a variable name, not a secret
ENCRYPTION_KEY_VAR = "BRAMBLELOOP_ARCHIVE_ENCRYPTION_KEY"
REGION_VAR = "BRAMBLELOOP_ARCHIVE_REGION"

PROBE_ACTION = "continuity.offsite_write"
SERVICE = "s3"
DEFAULT_REGION = "us-west-004"

# How many archives to keep in the bucket. The database keeps its own few; this keeps more,
# because the whole point of this copy is the case where the database is gone and the only
# question left is how far back the newest readable archive is.
RETAIN_OFFSITE = 14

# Encryption is AES-256-CBC over the compressed export, with a random IV per object and an
# HMAC over the ciphertext. Written out rather than imported from a crypto library for the
# same reason as the signing: no new dependency in the container that holds the company.
# The HMAC is checked *before* decryption, because a decryption routine fed attacker-chosen
# ciphertext is a decryption routine being asked to be a parser.
ENCRYPTION_HEADER = b"BLOOP1"


class OffsiteNotConfigured(PermanentError):
    """No bucket. Not an outage: there is nowhere to write."""


class OffsiteRefused(PermanentError):
    """The store answered and the answer is not an accepted object."""


class ArchiveCorrupt(PermanentError):
    """What came back is not what went up."""


@dataclass(frozen=True)
class Target:
    endpoint: str
    bucket: str
    key_id: str
    secret: str
    region: str

    @property
    def host(self) -> str:
        return urllib.parse.urlparse(self.endpoint).netloc


def target(env: dict[str, str] | None = None) -> Target | None:
    """The configured destination, or None. Refuses a half-configured one.

    A half-right endpoint is worse than none: it reports a bucket exists and fails on the
    day somebody needs to read it, which is the only day this matters.
    """
    e = env if env is not None else os.environ
    parts = {name: (e.get(name) or "").strip()
             for name in (ENDPOINT_VAR, BUCKET_VAR, KEY_ID_VAR, SECRET_VAR)}
    present = [k for k, v in parts.items() if v]
    if not present:
        return None
    missing = [k for k, v in parts.items() if not v]
    if missing:
        raise OffsiteNotConfigured(
            f"{sorted(missing)} are missing while {sorted(present)} are set. A "
            f"half-configured archive destination reports that a bucket exists and fails on "
            f"the day somebody reads it, which is the only day this matters")
    return Target(endpoint=parts[ENDPOINT_VAR].rstrip("/"), bucket=parts[BUCKET_VAR],
                  key_id=parts[KEY_ID_VAR], secret=parts[SECRET_VAR],
                  region=(e.get(REGION_VAR) or DEFAULT_REGION).strip())


def configured(env: dict[str, str] | None = None) -> bool:
    try:
        return target(env) is not None
    except OffsiteNotConfigured:
        return False


# ---------------------------------------------------------------------------
# Encryption


def encryption_key(env: dict[str, str] | None = None) -> bytes | None:
    e = env if env is not None else os.environ
    raw = (e.get(ENCRYPTION_KEY_VAR) or "").strip()
    if not raw:
        return None
    # A passphrase rather than raw key bytes, because the owner is typing this on a phone.
    # Stretched rather than used directly: a typed passphrase has far less entropy than the
    # key it stands in for, and skipping the stretch is how that becomes the weak link.
    return hashlib.pbkdf2_hmac("sha256", raw.encode(), b"brambleloop-archive-v1", 200_000)


def _pad(data: bytes) -> bytes:
    pad = 16 - (len(data) % 16)
    return data + bytes([pad]) * pad


def _unpad(data: bytes) -> bytes:
    if not data or len(data) % 16:
        raise ArchiveCorrupt("ciphertext length is not a whole number of blocks")
    pad = data[-1]
    if pad < 1 or pad > 16 or data[-pad:] != bytes([pad]) * pad:
        raise ArchiveCorrupt("padding is not well formed, so this is not our plaintext")
    return data[:-pad]


def _aes_cbc(key: bytes, iv: bytes, data: bytes, *, decrypt: bool) -> bytes:
    """AES-256-CBC through the standard library's `ssl`-adjacent primitives.

    Python ships no AES, so this uses `cryptography` when present and refuses otherwise --
    rather than hand-rolling a cipher, which is the one thing in this file that must not be
    written from scratch. A wrong cipher is indistinguishable from a right one until it is
    attacked.
    """
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:  # pragma: no cover - exercised by the dependency being absent
        raise PermanentError(
            "archive encryption needs the `cryptography` package. Writing an unencrypted "
            "copy of every row this company has, to a third-party bucket, is not the "
            "fallback") from exc

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    engine = cipher.decryptor() if decrypt else cipher.encryptor()
    return engine.update(data) + engine.finalize()


def seal(payload: bytes, key: bytes) -> bytes:
    """Encrypt and authenticate. Header, IV, MAC, ciphertext -- in that order."""
    import secrets

    iv = secrets.token_bytes(16)
    ciphertext = _aes_cbc(key, iv, _pad(payload), decrypt=False)
    mac = hmac.new(key, ENCRYPTION_HEADER + iv + ciphertext, hashlib.sha256).digest()
    return ENCRYPTION_HEADER + iv + mac + ciphertext


def unseal(blob: bytes, key: bytes) -> bytes:
    """Authenticate, then decrypt. Never the other way round."""
    header = ENCRYPTION_HEADER
    if not blob.startswith(header):
        raise ArchiveCorrupt("this object was not written by this system")
    body = blob[len(header):]
    iv, mac, ciphertext = body[:16], body[16:48], body[48:]
    expected = hmac.new(key, header + iv + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ArchiveCorrupt(
            "the authentication tag does not match. The bytes changed in the bucket, or the "
            "key is the wrong one -- and decrypting anyway would be asking a decryption "
            "routine to act as a parser for attacker-chosen input")
    return _unpad(_aes_cbc(key, iv, ciphertext, decrypt=True))


# ---------------------------------------------------------------------------
# SigV4


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    key = _sign(f"AWS4{secret}".encode(), date_stamp)
    key = _sign(key, region)
    key = _sign(key, service)
    return _sign(key, "aws4_request")


def canonical_request(method: str, path: str, query: str, headers: dict, payload_hash: str
                      ) -> tuple[str, str]:
    ordered = sorted((k.lower(), " ".join(str(v).split())) for k, v in headers.items())
    canonical_headers = "".join(f"{k}:{v}\n" for k, v in ordered)
    signed_headers = ";".join(k for k, _ in ordered)
    request = "\n".join([method, path, query, canonical_headers, signed_headers,
                         payload_hash])
    return request, signed_headers


def authorization(target_: Target, method: str, path: str, query: str, headers: dict,
                  payload: bytes, now: datetime) -> dict:
    """Everything SigV4 requires, returned as the headers to send."""
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    payload_hash = _sha256(payload)

    send = dict(headers)
    send["host"] = target_.host
    send["x-amz-date"] = amz_date
    send["x-amz-content-sha256"] = payload_hash

    request, signed_headers = canonical_request(method, path, query, send, payload_hash)
    scope = f"{date_stamp}/{target_.region}/{SERVICE}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, _sha256(request.encode())])
    signature = hmac.new(signing_key(target_.secret, date_stamp, target_.region, SERVICE),
                         to_sign.encode(), hashlib.sha256).hexdigest()
    send["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={target_.key_id}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}")
    return send


def _call(target_: Target, method: str, key: str, payload: bytes = b"",
          *, timeout: float = 60.0, now: datetime | None = None) -> bytes:
    now = now or datetime.now(timezone.utc)
    path = f"/{target_.bucket}/{urllib.parse.quote(key, safe='/')}"
    headers = authorization(target_, method, path, "", {}, payload, now)
    url = f"{target_.endpoint}{path}"

    request = urllib.request.Request(url, data=payload or None, method=method)
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        if exc.code in (429, 500, 502, 503, 504):
            raise TransientError(f"archive store {exc.code}: {detail}") from exc
        raise OffsiteRefused(f"archive store {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TransientError(f"archive store unreachable: {exc.reason}") from exc


def put(key: str, payload: bytes, *, env: dict[str, str] | None = None) -> dict:
    """Write one object, encrypted. Raises rather than returning a failure."""
    dest = target(env)
    if dest is None:
        raise OffsiteNotConfigured(
            f"no {ENDPOINT_VAR} in this environment, so there is nowhere off this provider "
            f"to write. That is the state the gate describes, not a failure to retry")
    secret = encryption_key(env)
    if secret is None:
        raise OffsiteNotConfigured(
            f"no {ENCRYPTION_KEY_VAR}. An archive is every row this company has, and writing "
            f"it unencrypted to a third-party bucket is not the fallback for a missing key")

    sealed = seal(payload, secret)
    _call(dest, "PUT", key, sealed)
    return {"key": key, "bytes": len(sealed), "plaintext_bytes": len(payload),
            "sha256": _sha256(sealed), "bucket": dest.bucket, "host": dest.host}


def get(key: str, *, env: dict[str, str] | None = None) -> bytes:
    """Read one object back and decrypt it, authenticating first."""
    dest = target(env)
    if dest is None:
        raise OffsiteNotConfigured(f"no {ENDPOINT_VAR} in this environment")
    secret = encryption_key(env)
    if secret is None:
        raise OffsiteNotConfigured(f"no {ENCRYPTION_KEY_VAR} to decrypt with")
    return unseal(_call(dest, "GET", key), secret)


def delete(key: str, *, env: dict[str, str] | None = None) -> None:
    dest = target(env)
    if dest is None:
        raise OffsiteNotConfigured(f"no {ENDPOINT_VAR} in this environment")
    _call(dest, "DELETE", key)


def object_key(digest: str, now: datetime | None = None) -> str:
    """Where an archive lives in the bucket.

    Dated prefix then digest: the prefix makes a human listing readable oldest-to-newest, and
    the digest makes the name depend on the contents, so the same export written twice
    occupies one object rather than two that might differ.
    """
    now = now or datetime.now(timezone.utc)
    return f"continuity/{now.strftime('%Y/%m/%d')}/{digest[:16]}.blarc"


# ---------------------------------------------------------------------------
# The round trip, which is what the gate reads


def archive(db, *, env: dict[str, str] | None = None, work_dir: str | Path | None = None,
            now: datetime | None = None, transport=None) -> dict:
    """Export, encrypt, upload, read back, decrypt, restore, and record the result.

    Every step is in one function on purpose. An upload recorded as a success and a restore
    proven separately are two facts about two different objects; the only claim worth
    recording is that *this* object, as it now sits in that bucket, restores this company.

    The failure modes are named separately because they need different answers. Nowhere to
    write is a gate. A store that refused is a credential problem. A digest that came back
    wrong is corruption, and it is the one that must never be reported as a successful
    backup.
    """
    from pathlib import Path as _Path

    from . import continuity, workspace
    from .db import Database
    from .models import AuditLog

    now = now or datetime.now(timezone.utc)
    record: dict = {"at": now.isoformat(), "ok": False, "reason": "", "stage": "start"}
    send, fetch = (transport or (put, get))

    try:
        dest = target(env)
    except OffsiteNotConfigured as exc:
        dest = None
        record.update(reason=str(exc)[:400], stage="configuration")

    if dest is None and not record["reason"]:
        record.update(reason=f"no {ENDPOINT_VAR} in this environment", stage="configuration")

    if not record["reason"]:
        # Everything this directory holds -- the export, the compressed payload, the restored
        # copy and the scratch SQLite database the restore is proved into -- exists only for
        # the proof, and the proof is finished by the end of this block. It was
        # `tempfile.mkdtemp` with no prefix at all, so the leftovers were not even
        # attributable to this module in the disk signal's count.
        with workspace.work_dir(work_dir, prefix="offsite-") as work:
            root = _Path(work)
            root.mkdir(parents=True, exist_ok=True)
            export_path = root / "continuity.jsonl"
            try:
                record["stage"] = "export"
                result = continuity.export(db, export_path)
                payload, raw_bytes = continuity._compress(export_path)
                key = object_key(result.digest, now)

                record["stage"] = "upload"
                written = send(key, payload, env=env)

                record["stage"] = "read_back"
                came_back = fetch(key, env=env)
                if hashlib.sha256(came_back).hexdigest() != hashlib.sha256(payload).hexdigest():
                    raise ArchiveCorrupt(
                        "what came back is not what went up. A backup that differs from its "
                        "source is worse than no backup, because it is discovered on the day "
                        "it is needed")

                record["stage"] = "restore"
                import gzip

                restored_path = root / "restored.jsonl"
                restored_path.write_bytes(gzip.decompress(came_back))
                scratch = Database(f"sqlite:///{root / 'restore-proof.sqlite'}")
                scratch.create_all()
                counts = continuity.restore(restored_path, scratch)

                record.update({
                    "ok": True, "stage": "complete", "key": key,
                    "digest": result.digest, "raw_bytes": raw_bytes,
                    "stored_bytes": written["bytes"], "bucket": written.get("bucket", ""),
                    "host": written.get("host", ""),
                    "tables_restored": len(counts),
                    "rows_restored": sum(counts.values()),
                    "survives": {"container_replacement": True, "redeploy": True,
                                 "provider_loss": True},
                })
            except (PermanentError, TransientError) as exc:
                record["reason"] = f"{record['stage']}: {str(exc)[:360]}"

    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=PROBE_ACTION,
                       artifact=record.get("key", "") or "none", detail=record))
    return record


def prune(db, *, env: dict[str, str] | None = None, keep: int = RETAIN_OFFSITE) -> dict:
    """Forget the oldest offsite archives, from this system's own record of what it wrote.

    Deliberately driven from the audit rows rather than from a bucket listing. A listing is
    the store's opinion of what exists; the audit log is this company's record of what it
    put there, and deleting on somebody else's opinion is how a retention policy removes an
    object it did not write.
    """
    from sqlalchemy import desc, select

    from .models import AuditLog

    with db.session() as s:
        rows = [r for r in s.scalars(
            select(AuditLog).where(AuditLog.action == PROBE_ACTION)
            .order_by(desc(AuditLog.id)))
            if (r.detail or {}).get("ok") and (r.detail or {}).get("key")]

    keys, seen = [], set()
    for row in rows:
        key = row.detail["key"]
        if key not in seen:
            seen.add(key)
            keys.append(key)

    doomed, failures = keys[keep:], []
    for key in doomed:
        try:
            delete(key, env=env)
        except (PermanentError, TransientError) as exc:
            failures.append({"key": key, "why": str(exc)[:200]})
    return {"kept": min(len(keys), keep), "deleted": len(doomed) - len(failures),
            "failures": failures, "retain": keep,
            "why_from_our_own_record": (
                "a bucket listing is the store's opinion of what exists; the audit log is "
                "this company's record of what it put there, and deleting on somebody "
                "else's opinion removes objects nobody here wrote")}


def last_archive(db) -> dict | None:
    from sqlalchemy import desc, select

    from .models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == PROBE_ACTION)
                              .order_by(desc(AuditLog.id)).limit(1)))
    return dict(rows[0].detail or {}) if rows else None


def usable(db) -> bool:
    """Whether a full round trip has actually succeeded. The `offsite_storage` condition."""
    last = last_archive(db)
    return bool(last and last.get("ok"))


def state(db, *, env: dict[str, str] | None = None) -> dict:
    """What the off-provider copy is, whether it exists, and what it would cost."""
    try:
        dest = target(env)
        problem = ""
    except OffsiteNotConfigured as exc:
        dest, problem = None, str(exc)
    last = last_archive(db)

    return {
        "configured": dest is not None,
        "configuration_problem": problem,
        "bucket": dest.bucket if dest else None,
        "host": dest.host if dest else None,
        "encryption_key_present": encryption_key(env) is not None,
        "last_archive": last,
        "usable": bool(last and last.get("ok")),
        "retain_offsite": RETAIN_OFFSITE,
        "what_it_survives": (
            "losing this hosting provider. The in-database copy survives a container "
            "replacement, a redeploy and a crash; it does not survive the provider, which is "
            "the failure #51 names"),
        "why_a_round_trip": (
            "a backup nobody has restored is a hope. The gate reads export, upload, read "
            "back, decrypt and restore into a scratch database -- not a URL being set. A "
            "typed bucket address that is wrong, or whose credentials are, survives losing "
            "the provider exactly as well as no bucket at all"),
        "encryption": (
            "AES-256-CBC with a stretched passphrase, authenticated before decryption, with "
            "the key in a variable the bucket credentials do not include. A reader who "
            "obtains the bucket gets ciphertext"),
        "provider_neutral": (
            "written against the S3 API, so Backblaze B2, Cloudflare R2, Wasabi and AWS are "
            "a URL rather than a code change. A continuity plan welded to one vendor has "
            "moved the single point of failure rather than removed it"),
    }
