"""The copy that survives losing the hosting provider, and what it has to prove first.

Requirement 51's second half. The in-database export already survives a container
replacement, a redeploy and a crash. It does not survive Railway, which is the failure the
requirement actually names, and a bucket address typed into a variable survives it exactly as
well as no bucket at all.

So the tests here are about the difference between a configured destination and a proven one:
a signing implementation checked against the vector AWS publishes rather than against itself,
an archive that is authenticated before it is decrypted, a round trip whose verdict comes from
the bytes that came back, and a retention policy that deletes from this system's own record
rather than from the store's opinion of what exists.
"""
from __future__ import annotations

import gzip
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core import offsite  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Product  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


CONFIGURED = {
    offsite.ENDPOINT_VAR: "https://s3.us-west-004.backblazeb2.com",
    offsite.BUCKET_VAR: "brambleloop-archive",
    offsite.KEY_ID_VAR: "004aabbccddeeff0000000001",
    offsite.SECRET_VAR: "K004xxxxxxxxxxxxxxxxxxxxxxxxxxx",
    offsite.ENCRYPTION_KEY_VAR: "a passphrase long enough to be stretched into a key",
    offsite.REGION_VAR: "us-west-004",
}


# ---------------------------------------------------------------------------
# Configuration is not capability


def test_an_unset_destination_is_not_configured() -> None:
    assert offsite.configured({}) is False
    assert offsite.target({}) is None


def test_a_half_configured_destination_is_refused_rather_than_guessed() -> None:
    for missing in (offsite.BUCKET_VAR, offsite.KEY_ID_VAR, offsite.SECRET_VAR):
        env = {k: v for k, v in CONFIGURED.items() if k != missing}
        try:
            offsite.target(env)
        except offsite.OffsiteNotConfigured:
            continue
        raise AssertionError(f"a destination with no {missing} was accepted")


def test_an_archive_is_never_written_unencrypted() -> None:
    env = {k: v for k, v in CONFIGURED.items() if k != offsite.ENCRYPTION_KEY_VAR}
    try:
        offsite.put("continuity/x.blarc", b"every row this company has", env=env)
    except offsite.OffsiteNotConfigured as exc:
        assert "unencrypted" in str(exc)
        return
    raise AssertionError("an archive went to a third-party bucket in the clear")


# ---------------------------------------------------------------------------
# Signing, checked against somebody else's arithmetic


def test_the_signing_key_matches_the_vector_aws_publishes() -> None:
    """AWS's own SigV4 example. Checking an implementation against itself proves nothing."""
    key = offsite.signing_key("wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
                              "20150830", "us-east-1", "iam")
    assert key.hex() == (
        "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9")


def test_the_authorization_header_carries_the_payload_hash_it_signed() -> None:
    dest = offsite.target(CONFIGURED)
    from datetime import datetime, timezone

    headers = offsite.authorization(dest, "PUT", "/brambleloop-archive/k", "", {}, b"body",
                                    datetime(2026, 9, 20, tzinfo=timezone.utc))
    assert headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=")
    assert "SignedHeaders=" in headers["authorization"]
    assert headers["x-amz-content-sha256"] == offsite._sha256(b"body")


# ---------------------------------------------------------------------------
# Sealing


def test_a_sealed_archive_round_trips() -> None:
    key = offsite.encryption_key(CONFIGURED)
    payload = b"row\n" * 1000
    blob = offsite.seal(payload, key)
    assert blob.startswith(offsite.ENCRYPTION_HEADER)
    assert payload not in blob
    assert offsite.unseal(blob, key) == payload


def test_one_flipped_bit_is_refused_rather_than_decrypted() -> None:
    key = offsite.encryption_key(CONFIGURED)
    blob = bytearray(offsite.seal(b"the whole company", key))
    blob[-5] ^= 0x01
    try:
        offsite.unseal(bytes(blob), key)
    except offsite.ArchiveCorrupt:
        return
    raise AssertionError("a tampered archive decrypted")


def test_the_wrong_passphrase_does_not_decrypt() -> None:
    blob = offsite.seal(b"payload", offsite.encryption_key(CONFIGURED))
    other = offsite.encryption_key({offsite.ENCRYPTION_KEY_VAR: "a different passphrase"})
    try:
        offsite.unseal(blob, other)
    except offsite.ArchiveCorrupt:
        return
    raise AssertionError("an archive decrypted under a key that did not seal it")


# ---------------------------------------------------------------------------
# The round trip, which is what the gate reads


class _Bucket:
    """An object store that actually stores. The archive's verdict has to come from bytes."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key, payload, *, env=None):
        self.objects[key] = payload
        return {"key": key, "bytes": len(payload), "bucket": "test", "host": "test"}

    def get(self, key, *, env=None):
        return self.objects[key]


def test_a_complete_round_trip_restores_the_company() -> None:
    db = _db()
    with db.session() as s:
        s.add(Product(slug="test-throw", title="Test throw"))

    bucket = _Bucket()
    record = offsite.archive(db, env=CONFIGURED, transport=(bucket.put, bucket.get))

    assert record["ok"] is True, record.get("reason")
    assert record["stage"] == "complete"
    assert record["tables_restored"] > 0
    assert record["survives"]["provider_loss"] is True
    assert offsite.usable(db) is True


def test_an_unconfigured_archive_records_a_failure_rather_than_skipping() -> None:
    """The gate reads these rows. A skipped run leaves the last `ok` standing."""
    db = _db()
    record = offsite.archive(db, env={})
    assert record["ok"] is False
    assert record["stage"] == "configuration"
    assert offsite.usable(db) is False
    with db.session() as s:
        assert s.query(AuditLog).filter_by(action=offsite.PROBE_ACTION).count() == 1


def test_an_archive_that_comes_back_different_is_not_a_backup() -> None:
    db = _db()
    bucket = _Bucket()

    def _corrupting_get(key, *, env=None):
        return gzip.compress(b"not what went up")

    record = offsite.archive(db, env=CONFIGURED, transport=(bucket.put, _corrupting_get))
    assert record["ok"] is False
    assert record["stage"] == "read_back"
    assert "worse than no backup" in record["reason"]


def test_an_upload_the_store_refused_is_named_as_a_credential_problem() -> None:
    db = _db()

    def _refuse(key, payload, *, env=None):
        raise offsite.OffsiteRefused("archive store 403: not authorized")

    record = offsite.archive(db, env=CONFIGURED,
                             transport=(_refuse, lambda k, env=None: b""))
    assert record["ok"] is False
    assert record["stage"] == "upload"
    assert "403" in record["reason"]


# ---------------------------------------------------------------------------
# Retention


def test_pruning_deletes_from_our_own_record_not_the_store_listing() -> None:
    db = _db()
    with db.session() as s:
        for i in range(5):
            s.add(AuditLog(actor="orchestrator", action=offsite.PROBE_ACTION,
                           artifact=f"k{i}", detail={"ok": True, "key": f"continuity/k{i}"}))
        # A row the archive never wrote, and an object it wrote but could not verify.
        s.add(AuditLog(actor="orchestrator", action=offsite.PROBE_ACTION,
                       artifact="failed", detail={"ok": False, "key": "continuity/bad"}))

    deleted: list[str] = []
    original = offsite._call
    offsite._call = lambda dest, method, key, payload=b"", **kw: (
        deleted.append(key) if method == "DELETE" else None) or b""
    try:
        result = offsite.prune(db, env=CONFIGURED, keep=2)
    finally:
        offsite._call = original

    assert result["kept"] == 2
    assert result["deleted"] == 3
    assert "continuity/bad" not in deleted


def test_the_state_reports_the_last_real_round_trip_not_the_variables() -> None:
    db = _db()
    state = offsite.state(db, env=CONFIGURED)
    assert state["configured"] is True
    assert state["usable"] is False          # configured, never proven
    assert "a backup nobody has restored is a hope" in state["why_a_round_trip"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
