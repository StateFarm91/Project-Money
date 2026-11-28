"""ENG-MEMORY-STREAM: continuity and offsite archiving hold a bounded amount, not the database.

Production hit its 8 GB limit on 2026-11-27. Web, the scheduler and the workers share one
process, and the two daily whole-database jobs (`ops.continuity`, `ops.offsite_archive`) each
held the export several times over -- every row of `durable_artifacts` (image and PDF bytes)
loaded whole and then hex-encoded, the export read whole to gzip it, six whole copies in the
offsite round trip, 500-row restore batches of blobs -- and they could run at the same time.

These tests seed many blob rows and measure peak Python allocation with `tracemalloc`:

* export, restore, compress and the retained-archive write-back stay far below the total blob
  size (they are fully streaming: the bound is a few rows plus the restore batch cap);
* the offsite round trip holds at most one full copy of the sealed object (the transport
  moves `bytes`) plus bounded streaming overhead -- not the six copies it used to;
* the streamed formats are byte-identical to the one-shot ones they replace;
* the two jobs are mutually exclusive, and a job that finds the other running is handed back
  to the queue un-counted rather than failed.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import gc
import gzip
import hashlib
import os
import shutil
import sys
import tempfile
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.core import continuity, offsite  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import DurableArtifact, Job, JobStatus  # noqa: E402

MB = 1024 * 1024
BLOB_ROWS = 48
BLOB_BYTES = 1 * MB
TOTAL_BLOB = BLOB_ROWS * BLOB_BYTES

CONFIGURED = {
    offsite.ENDPOINT_VAR: "https://s3.example.invalid",
    offsite.BUCKET_VAR: "archive",
    offsite.KEY_ID_VAR: "id",
    offsite.SECRET_VAR: "not-a-secret",
    offsite.ENCRYPTION_KEY_VAR: "a passphrase long enough to be stretched into a key",
    offsite.REGION_VAR: "us-west-004",
}

_SEEDED: dict = {}


def _seeded() -> tuple[Database, Path]:
    """One file-backed database holding BLOB_ROWS incompressible blobs (like images)."""
    if "db" in _SEEDED:
        return _SEEDED["db"], _SEEDED["dir"]
    work = Path(tempfile.mkdtemp(prefix="memstream-"))
    db = Database(f"sqlite:///{work / 'source.sqlite'}")
    db.create_all()
    for i in range(BLOB_ROWS):
        data = os.urandom(BLOB_BYTES)
        with db.session() as s:
            s.add(DurableArtifact(sha256=hashlib.sha256(data).hexdigest(),
                                  content_type="image/png", bytes_len=len(data),
                                  payload=data, why_kept=f"memory test {i}"))
        del data
    _SEEDED.update(db=db, dir=work)
    return db, work


def _peak(fn, *args, **kwargs):
    gc.collect()
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        out = fn(*args, **kwargs)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return out, peak


def _report(label: str, peak: int) -> None:
    print(f"    {label}: peak {peak / MB:.1f} MB over {TOTAL_BLOB / MB:.0f} MB of blobs")


class _Bucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key, payload, *, env=None):
        self.objects[key] = payload
        return {"key": key, "bytes": len(payload), "bucket": "test", "host": "test"}

    def get(self, key, *, env=None):
        return self.objects[key]


# ---------------------------------------------------------------------------
# Peak memory


def test_export_streams_blob_rows_instead_of_loading_the_table():
    db, work = _seeded()
    dest = work / "export-peak.jsonl"
    result, peak = _peak(continuity.export, db, dest)
    _report("export", peak)
    rows = {t.name: t.rows for t in result.tables}
    assert rows["durable_artifacts"] == BLOB_ROWS
    # A few rows (yield_per) each held as bytes, hex, JSON line and its encoding.
    assert peak < TOTAL_BLOB * 0.35, f"export peaked at {peak / MB:.1f} MB"
    dest.unlink()


def test_restore_batches_by_bytes_not_only_by_rows():
    db, work = _seeded()
    src = work / "export-restore.jsonl"
    continuity.export(db, src)
    cap = continuity.RESTORE_BATCH_BYTES
    continuity.RESTORE_BATCH_BYTES = 8 * MB     # the bound follows the cap, not the data
    try:
        target = Database(f"sqlite:///{work / 'restore-peak.sqlite'}", scratch=True)
        counts, peak = _peak(continuity.restore, src, target)
        target.engine.dispose()
    finally:
        continuity.RESTORE_BATCH_BYTES = cap
    _report("restore (8 MB batch cap)", peak)
    assert counts["durable_artifacts"] == BLOB_ROWS
    assert peak < TOTAL_BLOB * 0.5, f"restore peaked at {peak / MB:.1f} MB"
    src.unlink()


def test_the_restore_byte_cap_flushes_a_batch_of_blobs_early():
    db, work = _seeded()
    src = work / "export-batches.jsonl"
    continuity.export(db, src)
    target = Database(f"sqlite:///{work / 'restore-batches.sqlite'}", scratch=True)
    target.create_all()
    batches: list[int] = []
    from sqlalchemy import event

    @event.listens_for(target.engine, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO DURABLE_ARTIFACTS"):
            batches.append(len(params) if executemany else 1)

    counts = continuity.restore(src, target)
    target.engine.dispose()
    assert counts["durable_artifacts"] == BLOB_ROWS
    # 48 one-megabyte rows (two megabytes each as hex) under a 32 MB cap: never one batch.
    assert len(batches) > 1 and max(batches) <= 17, batches
    src.unlink()


def test_compress_streams_and_is_byte_identical_to_gzip_compress():
    _, work = _seeded()
    raw_path = work / "raw.bin"
    with raw_path.open("wb") as fh:
        for _ in range(24):
            fh.write(os.urandom(MB // 2) + b"x" * (MB // 2))
    packed, peak = _peak(continuity.compress_file, raw_path, work / "raw.bin.gz",
                         mtime=1_700_000_000)
    _report("compress (24 MB file)", peak)
    assert peak < 8 * MB, f"compress peaked at {peak / MB:.1f} MB"
    raw = raw_path.read_bytes()
    oneshot = gzip.compress(raw, 6, mtime=1_700_000_000)
    assert (work / "raw.bin.gz").read_bytes() == oneshot
    assert packed.raw_bytes == len(raw) and packed.stored_bytes == len(oneshot)
    assert packed.sha256 == hashlib.sha256(oneshot).hexdigest()
    del raw, oneshot
    raw_path.unlink()
    (work / "raw.bin.gz").unlink()


def test_the_streamed_seal_is_the_same_format_both_ways():
    _, work = _seeded()
    key = offsite.encryption_key(CONFIGURED)
    for size in (0, 1, 15, 16, 17, offsite.STREAM_CHUNK, offsite.STREAM_CHUNK + 3):
        data = os.urandom(size)
        (work / "p").write_bytes(data)
        info = offsite.seal_file(work / "p", work / "s", key)
        blob = (work / "s").read_bytes()
        assert blob.startswith(offsite.ENCRYPTION_HEADER)
        assert offsite.unseal(blob, key) == data                    # old reader, new writer
        assert len(blob) == len(offsite.seal(data, key))
        assert info["sha256"] == hashlib.sha256(blob).hexdigest()
        out: list[bytes] = []
        got = offsite.unseal_to(offsite.seal(data, key), key, out.append)  # new reader
        assert b"".join(out) == data and got["bytes"] == size
        assert got["sha256"] == hashlib.sha256(data).hexdigest()
    bad = bytearray(offsite.seal(b"the whole company", key))
    bad[-1] ^= 1
    try:
        offsite.unseal_to(bytes(bad), key, lambda b: None)
    except offsite.ArchiveCorrupt:
        pass
    else:
        raise AssertionError("a tampered object decrypted")


def test_the_offsite_round_trip_holds_at_most_one_sealed_copy():
    db, work = _seeded()
    bucket = _Bucket()
    cap = continuity.RESTORE_BATCH_BYTES
    continuity.RESTORE_BATCH_BYTES = 8 * MB     # as above: the restore's share follows the cap
    try:
        record, peak = _peak(offsite.archive, db, env=CONFIGURED,
                             transport=(bucket.put, bucket.get), work_dir=work / "offsite")
    finally:
        continuity.RESTORE_BATCH_BYTES = cap
    assert record["ok"] is True, record.get("reason")
    assert record["rows_restored"] >= BLOB_ROWS
    stored = record["stored_bytes"]
    _report(f"offsite archive (sealed object {stored / MB:.1f} MB, kept by the test bucket)",
            peak)
    # The test bucket keeps the uploaded object, so one sealed copy is unavoidable here; the
    # rest -- export, gzip, seal, read-back check, decrypt, gunzip, restore -- is streaming.
    assert peak < stored + 0.5 * TOTAL_BLOB, (
        f"offsite archive peaked at {peak / MB:.1f} MB with a {stored / MB:.1f} MB object")
    # And the object is the same format the one-shot reader opens.
    [blob] = bucket.objects.values()
    opened = offsite.unseal(blob, offsite.encryption_key(CONFIGURED))
    assert hashlib.sha256(blob).hexdigest() == record["ciphertext_sha256"]
    assert gzip.decompress(opened).startswith(b'{"__brambleloop_export__"')


def test_retain_and_write_back_hold_only_the_compressed_copy():
    db, work = _seeded()
    src = work / "export-retain.jsonl"
    result = continuity.export(db, src)
    retained, peak_in = _peak(continuity.retain, db, src, result)
    _report(f"retain (compressed {retained['stored_bytes'] / MB:.1f} MB)", peak_in)
    # One compressed copy (the column value) plus the driver's bind; never the raw export.
    assert peak_in < retained["stored_bytes"] * 2 + 8 * MB, peak_in
    assert peak_in < retained["raw_bytes"], peak_in
    out, peak_out = _peak(continuity.write_retained, db, retained["archive_id"],
                          work / "written-back.jsonl")
    _report("write_retained", peak_out)
    assert peak_out < retained["stored_bytes"] * 2 + 8 * MB, peak_out
    assert hashlib.sha256(out.read_bytes()).digest() == hashlib.sha256(
        src.read_bytes()).digest()
    src.unlink()
    out.unlink()


# ---------------------------------------------------------------------------
# Mutual exclusion


def _small_db() -> Database:
    from brambleloop.agents.registry import Registry

    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='memstream-lease-')}/l.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_the_two_continuity_jobs_exclude_each_other():
    db = _small_db()
    with continuity.exclusive(db, "ops.continuity:1"):
        # Same process, any holder: refused at once, never waited for.
        try:
            with continuity.exclusive(db, "ops.offsite_archive:2"):
                raise AssertionError("both continuity jobs held the lease")
        except continuity.ContinuityBusy:
            pass
    # Released: the other may now run.
    with continuity.exclusive(db, "ops.offsite_archive:2"):
        pass

    # Another process (a split topology) holds the database lease: refused as well.
    from brambleloop.ops import slo

    assert slo.acquire_lease(db, continuity.EXCLUSIVE_LEASE, "other-host:99", ttl_s=600)
    try:
        with continuity.exclusive(db, "ops.continuity:3"):
            raise AssertionError("ran while another process held the continuity lease")
    except continuity.ContinuityBusy as exc:
        assert "other-host:99" in str(exc)
    slo.release_lease(db, continuity.EXCLUSIVE_LEASE, "other-host:99")


def test_a_job_that_finds_the_other_running_is_requeued_uncounted():
    from brambleloop.ops import slo
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import release  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    db = _small_db()
    assert slo.acquire_lease(db, continuity.EXCLUSIVE_LEASE, "ops.continuity:running",
                             ttl_s=600)
    q = JobQueue(db)
    for jt in ("ops.offsite_archive", "ops.continuity"):
        q.enqueue("orchestrator", jt, {}, idempotency_key=f"mem-{jt}")
        assert Worker(db, "mem-w", job_types=[jt]).run_once()
    with db.session() as s:
        jobs = list(s.scalars(select(Job).where(
            Job.job_type.in_(["ops.offsite_archive", "ops.continuity"]))))
        assert len(jobs) == 2
        for job in jobs:
            assert job.status == JobStatus.PENDING, (job.job_type, job.status, job.last_error)
            assert int(job.attempts or 0) == 0, (job.job_type, job.attempts)
            created = job.created_at.replace(tzinfo=None)
            run_after = job.run_after.replace(tzinfo=None)
            assert (run_after - created).total_seconds() >= \
                continuity.EXCLUSIVE_RETRY_AFTER_S - 5, (job.job_type, created, run_after)
    slo.release_lease(db, continuity.EXCLUSIVE_LEASE, "ops.continuity:running")


def _cleanup() -> None:
    if "dir" in _SEEDED:
        _SEEDED["db"].engine.dispose()
        shutil.rmtree(_SEEDED["dir"], ignore_errors=True)
        _SEEDED.clear()


if __name__ == "__main__":
    fails = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_"):
                try:
                    fn()
                    print("OK  ", name)
                except Exception as e:  # noqa: BLE001
                    fails += 1
                    print("FAIL", name, repr(e))
    finally:
        _cleanup()
    sys.exit(1 if fails else 0)
