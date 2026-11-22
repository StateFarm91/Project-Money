"""Audit F-03: metadata and existence reads must never select the stored binary blobs.

GET /api/readback/evidence took 45-105 s in production and grew over time, while the same
build on the seeded production-shaped database (`test_evidence_perf.py`, no deploy handlers)
took ~1.4 s. The production route passes `deploy_handlers`, so `/api/continuity` runs in
process and calls `continuity.retained`, whose docstring promised "without reading the
payloads back" while `select(ContinuityArchive)` loaded every retained archive's gzip of the
whole database export. The same entity-select pattern loaded every kept PDF/image in the
deliverables retention listing, and `s.get(DurableArtifact, ...) is not None` loaded a blob
just to test that it exists.

Proved here with a `before_cursor_execute` probe on the engine (deterministic: it sees the
exact SQL sent to the database):

1. `continuity.retained` and the prune inside `continuity.retain` select no
   `continuity_archives.payload`, and `retained`'s output is unchanged;
2. the deliverables retention listing and prune, `artifacts._keep`'s idempotency check,
   `statements.archive`, `first_sale_surfaces.digital_files_reading` and the tournament-image
   allowlist select no `durable_artifacts.payload`;
3. the byte-reading paths (`write_retained`, `deliverables.held`, `artifacts._recover`,
   `statements.original`) still return the exact bytes, and a corrupt archive still refuses;
4. `production_evidence.evidence(db, deploy_handlers=...)`, with the real `api_continuity`
   handler and a 20 MB retained archive, never selects that payload.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_audit_blob_reads.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import contextlib
import hashlib
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_TMP = tempfile.mkdtemp()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'main.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import event, select  # noqa: E402

from brambleloop.core import continuity  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import ContinuityArchive, DurableArtifact  # noqa: E402

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)
# `payload` qualified by its table, and not `payload_sha256` (\b fails before the `_`).
_BLOB = re.compile(r"\b(continuity_archives|durable_artifacts)\.payload\b", re.I)


@contextlib.contextmanager
def _probe(db: Database):
    """Every SELECT that reads a blob column, as sent to the database."""
    hits: list[str] = []

    def before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and _BLOB.search(statement):
            hits.append(" ".join(statement.split())[:200])

    event.listen(db.engine, "before_cursor_execute", before)
    try:
        yield hits
    finally:
        event.remove(db.engine, "before_cursor_execute", before)


def _fresh() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/t.db")
    db.create_all()
    return db


def _probe_detects_a_blob_select(db: Database) -> None:
    """Guard against a vacuous pass: the probe must see an entity load of the blob."""
    with _probe(db) as hits, db.session() as s:
        list(s.scalars(select(ContinuityArchive)))
        list(s.scalars(select(DurableArtifact)))
    assert len(hits) == 2, hits


def _export(db: Database, tmp: str, n: int):
    path = Path(tmp) / f"export-{n}.jsonl"
    return path, continuity.export(db, path)


def test_retained_and_the_prune_in_retain_select_no_payload():
    db, tmp = _fresh(), tempfile.mkdtemp()
    _probe_detects_a_blob_select(db)
    ids = []
    for n in range(continuity.RETAINED_ARCHIVES + 2):
        path, result = _export(db, tmp, n)
        with _probe(db) as hits:
            held = continuity.retain(db, path, result)
        assert hits == [], hits
        ids.append(held["archive_id"])
    # the prune still keeps the newest RETAINED_ARCHIVES and reports the ones it removed
    assert held["retained"] == continuity.RETAINED_ARCHIVES, held
    assert held["pruned"] == [ids[-continuity.RETAINED_ARCHIVES - 1]], (held, ids)
    with db.session() as s:
        left = sorted(s.scalars(select(ContinuityArchive.id)))
    assert left == ids[-continuity.RETAINED_ARCHIVES:], (left, ids)

    with _probe(db) as hits:
        listed = continuity.retained(db)
    assert hits == [], hits
    # unchanged output: the same dicts the entity load produced, newest first
    with db.session() as s:
        rows = list(s.scalars(select(ContinuityArchive).order_by(
            ContinuityArchive.at.desc(), ContinuityArchive.id.desc())))
        expected = [{"archive_id": r.id, "at": r.at.isoformat(), "digest": r.digest,
                     "total_rows": r.total_rows, "stored_bytes": r.stored_bytes,
                     "raw_bytes": r.raw_bytes, "tables": len(r.manifest.get("tables", []))}
                    for r in rows]
    assert listed == expected and len(listed) == continuity.RETAINED_ARCHIVES, listed


def test_write_retained_still_returns_the_exact_bytes_and_refuses_corruption():
    db, tmp = _fresh(), tempfile.mkdtemp()
    path, result = _export(db, tmp, 0)
    original = path.read_bytes()
    archive_id = continuity.retain(db, path, result)["archive_id"]
    out = continuity.write_retained(db, archive_id, Path(tmp) / "back.jsonl")
    assert out.read_bytes() == original
    with db.session() as s:
        row = s.get(ContinuityArchive, archive_id)
        row.payload = row.payload[:-1] + bytes([row.payload[-1] ^ 1])
    try:
        continuity.write_retained(db, archive_id, Path(tmp) / "corrupt.jsonl")
    except ValueError as exc:
        assert "corrupt" in str(exc)
    else:
        raise AssertionError("a corrupt archive was written back")


def _kept(db: Database, payload: bytes, why: str) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    with db.session() as s:
        s.add(DurableArtifact(sha256=digest, content_type="application/pdf",
                              bytes_len=len(payload), payload=payload, why_kept=why))
    return digest


def test_the_deliverables_retention_listing_and_prune_select_no_payload():
    from brambleloop.commerce import deliverables

    db = _fresh()
    a = _kept(db, b"A" * 50_000, deliverables.keep_why("x", "1.0.0", "pattern"))
    b = _kept(db, b"B" * 70_000, deliverables.keep_why("y", "1.0.0", "pattern"))
    other = _kept(db, b"C" * 10, "the canonical model's reference pack")
    with _probe(db) as hits:
        plan = deliverables.retention_plan(db)
    assert hits == [], hits
    assert plan["kept_rows"] == 3, plan
    assert sorted((p["sha256"], p["bytes"]) for p in plan["prune"]) == sorted(
        [(a, 50_000), (b, 70_000)]), plan["prune"]
    with _probe(db) as hits:
        out = deliverables.prune(db)
    assert hits == [], hits
    assert out["pruned"] == 2, out
    with db.session() as s:
        assert list(s.scalars(select(DurableArtifact.sha256))) == [other]


def test_existence_checks_select_no_payload_and_byte_reads_are_exact():
    from brambleloop.commerce import deliverables
    from brambleloop.core import artifacts
    from brambleloop.finance.accounting import statements

    db = _fresh()
    blob = os.urandom(300_000)
    digest = hashlib.sha256(blob).hexdigest()
    assert artifacts._keep(db, digest, blob, "image/png", "first keep")
    with _probe(db) as hits:
        assert artifacts._keep(db, digest, blob, "image/png", "second keep")  # idempotent
    assert hits == [], hits
    # the byte paths really read the bytes, and the same bytes
    assert artifacts._recover(db, digest) == blob
    assert deliverables.held(db, digest) is True
    assert statements.original(db, digest) == blob

    pdf = b"%PDF-1.4 statement " + os.urandom(200_000)
    totals = {k: 1.0 for k in statements.METRICS}
    with _probe(db) as hits:
        first = statements.archive(db, period="2026-10", original=pdf,
                                   content_type="application/pdf", totals=totals, now=NOW)
        # a different month, same file: the row exists already, so the presence check runs
        again = statements.archive(db, period="2026-09", original=pdf,
                                   content_type="application/pdf", totals=totals, now=NOW)
    assert hits == [], hits
    assert first["original_held"] is True and again["original_held"] is True, (first, again)
    assert statements.original(db, first["sha256"]) == pdf


def test_digital_files_reading_and_the_tournament_allowlist_select_no_payload():
    from brambleloop.app import main
    from brambleloop.commerce import deliverables
    from brambleloop.launch import first_sale_surfaces as fss
    from brambleloop.visual import reference_pack

    db = _fresh()
    pdfs = {t: _kept(db, (t.encode() + b"-") * 4000, deliverables.keep_why("z", "1.0.0", t))
            for t in ("US", "UK")}
    real = deliverables.durable_state
    deliverables.durable_state = lambda *a, **k: {"state": deliverables.PASS, "pdfs": pdfs,
                                                  "why": "test"}
    seen = []
    import brambleloop.integrations.etsy_constraints as ec
    real_dfp = ec.digital_file_problems
    ec.digital_file_problems = lambda files: seen.append(sorted(n for _, n in files)) or []
    try:
        with _probe(db) as hits:
            reading = fss.digital_files_reading(db, releases=[("z", "1.0.0")], now=1.0)
    finally:
        deliverables.durable_state = real
        ec.digital_file_problems = real_dfp
    assert hits == [], hits
    assert reading["satisfied"] is True, reading
    assert seen == [sorted([len(b"US-") * 4000, len(b"UK-") * 4000])], seen

    mdb = main.db
    mdb.create_all()
    ref = _kept(mdb, b"R" * 9000, reference_pack.KEEP_REASON[:200])
    other = _kept(mdb, b"O" * 9000, deliverables.keep_why("z", "1.0.0", "pattern"))
    with _probe(mdb) as hits:
        assert main.tournament_image_refusal(ref) is None
        assert main.tournament_image_refusal(other) == "kept for another purpose"
    assert hits == [], hits


def test_evidence_with_deploy_handlers_never_selects_a_20mb_archive_payload():
    from brambleloop.app import main
    from brambleloop.ops import production_evidence as pe

    import _evidence_seed

    db = main.db
    db.create_all()
    _evidence_seed.seed(db, now=NOW)
    big = os.urandom(20 * 1024 * 1024)
    with db.session() as s:
        s.add(ContinuityArchive(format=1, digest="d" * 64,
                                payload_sha256=hashlib.sha256(big).hexdigest(), payload=big,
                                raw_bytes=len(big), stored_bytes=len(big), total_rows=1,
                                source="test", manifest={"tables": [{"name": "t"}]}))
    _probe_detects_a_blob_select(db)
    handlers = {"/api/departments": main.api_departments,
                "/api/swarm/runtime": main.api_swarm_runtime,
                "/api/funding/packets": main.api_funding_packets,
                "/api/offsite": main.api_offsite,
                "/api/continuity": main.api_continuity, "/api/etsy": main.api_etsy}
    with _probe(db) as hits:
        ev = pe.evidence(db, now=NOW, deploy_handlers=handlers)
    assert hits == [], hits
    assert ev["deploy_readback"]["/api/continuity"]["status"] == 200, ev["deploy_readback"]
    retained = main.api_continuity()["retained"]
    assert [r["stored_bytes"] for r in retained] == [len(big)], retained
    print(f"     deploy_readback: {ev['timing_ms'].get('deploy_readback')} ms")


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception:  # noqa: BLE001
            import traceback

            failed += 1
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
