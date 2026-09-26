"""#171: the release chain records what made every artefact, as it makes it, or refuses.

The 2026-09-26 audit of production found 275 derived artefacts and 275 without a provenance
row. Only the video planner ever called `ops.artefacts.record`; every chain handler wrote its
certificate, PDF, frames, listing, price and content pieces with nothing attached, so the
sentinel could only ever call the whole estate unproven. The tests here are about the fix
being structural rather than a reminder: the write path records lineage as it writes, the
artifact store refuses a watched class without it, and the worker checks after every job.

`tests/test_artefacts.py::test_the_sentinel_cadence_runs_against_artefacts_that_actually_exist`
still asserts four unproven artefacts, and it should: its rows are inserted behind the write
path's back. The gap it used to codify is closed here, by a real run.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_ART = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = _ART.name

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Agent, ArtefactProvenance, AuditLog, Job, JobStatus, Listing, ListingAsset,
    PatternVersion, Product,
)
from brambleloop.ops import artefacts as P  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: F401,E402  -- registers handlers
from brambleloop.runtime.worker import HandlerRegistry, Worker  # noqa: E402

SLUG = "hexagon-coaster-set"
_CHAIN: dict = {}


def _boot() -> Database:
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run_chain(db: Database | None = None) -> Database:
    """One certified product through the whole post-certification chain."""
    from brambleloop.products.vessels import build_hexagon_coaster

    db = db or _boot()
    JobQueue(db).enqueue("quality_director", "gate.certify",
                         {"cir": build_hexagon_coaster().to_dict()})
    w = Worker(db, "chain-worker")
    for _ in range(100):
        if not w.run_once():
            break
    return db


def _chain() -> Database:
    """The chain, run once and shared by the tests that only read it."""
    if not _CHAIN:
        _CHAIN["db"] = _run_chain()
    return _CHAIN["db"]


def _rows(db):
    with db.session() as s:
        return list(s.scalars(select(ArtefactProvenance)))


# --- the gap is closed by the write path, not by a reminder --------------------------------------

def test_the_chain_runs_green_with_the_write_path_in_place():
    db = _chain()
    with db.session() as s:
        broken = [(j.job_type, (j.last_error or "")[:100]) for j in s.scalars(select(Job))
                  if j.status in (JobStatus.FAILED, JobStatus.DEAD)
                  and j.job_type != "store.publish"]
        done = {j.job_type for j in s.scalars(select(Job)) if j.status == JobStatus.DONE}
    assert not broken, broken
    assert {"gate.certify", "assets.build", "listing.seo", "marketing.schedule"} <= done


def test_a_real_run_leaves_nothing_unproven():
    """expected_from_db minus the rows written is the empty set. This is the assertion the
    production audit could not make: 275 checked, 275 unproven."""
    db = _chain()
    with db.session() as s:
        expected = P.expected_from_db(s)
        have = {(r.artefact_class, r.artefact_key) for r in s.scalars(select(ArtefactProvenance))}
    missing = [e for e in expected if (e[0], e[1]) not in have]
    assert expected, "the chain produced nothing to account for"
    assert missing == [], missing
    classes = {e[0] for e in expected}
    assert {"certificate", "pdf", "chart", "visual_truth", "listing_copy", "seo", "pricing",
            "marketing_asset"} <= classes, classes


def test_every_artefact_reads_fresh_and_the_sentinel_may_enforce():
    db = _chain()
    with db.session() as s:
        current = P.current_from_db(s)
        expected = P.expected_from_db(s)
        out = P.sweep(s, current=current, expected=expected)
        gate = P.graduation(s, current=current, expected=expected)
    assert out["unproven"] == 0 and out["stale"] == 0
    assert out["fresh"] == out["checked"] > 0
    assert gate["may_enforce_unproven"] is True
    with db.session() as s:
        refused = [a for a in s.scalars(select(AuditLog)) if a.action == "provenance.refused"]
    assert refused == [], [a.detail for a in refused]


def test_the_pdfs_and_charts_in_the_job_outputs_are_counted():
    """They were not: the 275 was a lower bound over the tables somebody knew about."""
    db = _chain()
    with db.session() as s:
        expected = P.expected_from_db(s)
        build = next(j for j in s.scalars(select(Job))
                     if j.job_type == "assets.build" and j.status == JobStatus.DONE)
    keys = {(c, k) for c, k, _ in expected}
    for terminology, sha in build.outputs["pdf_sha256_by_terminology"].items():
        assert ("pdf", P.pdf_key(SLUG, "1.0.0", terminology)) in keys
        row = next(r for r in _rows(db)
                   if r.artefact_key == P.pdf_key(SLUG, "1.0.0", terminology))
        assert row.sha256 == sha, "the recorded hash is not the file the job produced"
    assert ("chart", P.chart_key(SLUG, "1.0.0", "chart")) in keys
    assert ("chart", P.chart_key(SLUG, "1.0.0", "legend")) in keys
    assert ("pricing", P.release_key(SLUG, "1.0.0")) in keys
    assert "lower bound" in P.expected_from_db.__doc__


# --- fingerprint parity ------------------------------------------------------------------------

def test_the_recorded_design_fingerprint_is_the_one_the_sweep_compares_against():
    """The trap: `CIR.fingerprint` is a 12-character hash of one serialisation and
    `current_from_db` publishes a 16-character hash of the stored JSON. A write path that
    recorded the former would make every artefact stale the moment it was built."""
    from brambleloop.cir.model import CIR

    db = _chain()
    with db.session() as s:
        current = P.current_from_db(s)
        pv = s.scalar(select(PatternVersion))
        cir_fp = CIR.from_dict(pv.cir_json).fingerprint()
    rows = _rows(db)
    assert rows
    for row in rows:
        assert row.inputs[f"cir:{SLUG}"] == current[f"cir:{SLUG}"], (row.artefact_class,
                                                                    row.artefact_key)
        assert row.inputs[f"cir:{SLUG}"] != cir_fp
        if f"release:{SLUG}" in row.inputs:
            assert row.inputs[f"release:{SLUG}"] == current[f"release:{SLUG}"]


def test_design_inputs_fingerprint_the_stored_json():
    db = _chain()
    with db.session() as s:
        pv = s.scalar(select(PatternVersion))
        inputs = P.design_inputs(s, SLUG, "1.0.0")
    assert inputs[f"cir:{SLUG}"] == P.fingerprint(pv.cir_json)
    assert inputs[f"release:{SLUG}"] == pv.release_hash[:16]
    assert inputs["chain:release"] == P.chain_fingerprint()


# --- what the lineage says ---------------------------------------------------------------------

def test_every_row_names_its_job_its_agent_and_its_authority():
    rows = _rows(_chain())
    assert rows
    for row in rows:
        assert row.source == "recorded"
        assert row.job_id is not None, row.artefact_key
        assert row.created_by, row.artefact_key
        assert row.publication_authority == "shadow"
        assert row.validation_status in {"certified", "passed", "problems", "blocked"}
        assert row.code_commit  # 'unknown' here, because no platform set one -- stated, not blank
    by_class = {r.artefact_class: r for r in rows}
    assert by_class["certificate"].created_by == "quality_director"
    assert by_class["certificate"].validation_status == "certified"
    assert by_class["listing_copy"].created_by == "listing"
    assert by_class["marketing_asset"].created_by == "growth"
    assert by_class["pdf"].created_by == "publishing"


def test_a_file_artefact_carries_the_hash_of_the_file_it_is():
    db = _chain()
    rows = _rows(db)
    with db.session() as s:
        assets = {a.id: a.sha256 for a in s.scalars(select(ListingAsset))}
    frames = [r for r in rows if r.artefact_class == "visual_truth"]
    assert len(frames) == len(assets) > 0
    for row in frames:
        asset_id = int(row.artefact_key.rsplit("#", 1)[1])
        assert row.sha256 == assets[asset_id]
    for row in rows:
        if row.artefact_class in P.FILE_CLASSES:
            assert len(row.sha256) == 64


def test_the_rebuild_graph_can_follow_the_parents():
    rows = _rows(_chain())
    by = {(r.artefact_class, r.artefact_key): r for r in rows}
    certificate = f"certificate:{P.release_key(SLUG, '1.0.0')}"
    assert certificate in by[("pdf", P.pdf_key(SLUG, "1.0.0", "US"))].parents
    assert certificate in by[("listing_copy", P.release_key(SLUG, "1.0.0"))].parents
    assert f"listing_copy:{P.release_key(SLUG, '1.0.0')}" in by[("seo", P.release_key(
        SLUG, "1.0.0"))].parents
    piece = next(r for r in rows if r.artefact_class == "marketing_asset")
    assert f"listing_copy:{P.release_key(SLUG, '1.0.0')}" in piece.parents


# --- deliberate stale-data injection through the real rows ---------------------------------------

def test_moving_the_stored_design_turns_the_whole_chain_stale_and_blocks_the_slug():
    """#173's condition on a real estate: the artefacts are untouched, only the design
    moved, and every one of them reports it. Run on its own database because it mutates."""
    from brambleloop.gates.incidents import IncidentTracker

    db = _run_chain()
    with db.session() as s:
        pv = s.scalar(select(PatternVersion))
        moved = dict(pv.cir_json)
        moved["title"] = moved.get("title", "") + " (re-engineered)"
        pv.cir_json = moved
    with db.session() as s:
        out = P.sweep(s, current=P.current_from_db(s), expected=P.expected_from_db(s))
    assert out["fresh"] == 0 and out["unproven"] == 0
    assert out["stale"] == out["checked"] > 0
    assert out["publication_blocked"] == [SLUG]
    assert IncidentTracker(db).publication_halted(SLUG) is True


# --- refusals ---------------------------------------------------------------------------------

def test_the_store_refuses_a_watched_class_without_lineage():
    store = ArtifactStore(tempfile.mkdtemp())
    try:
        store.put("x/pattern.pdf", b"%PDF", "application/pdf", artefact_class="pdf")
    except P.ProvenanceRefused as exc:
        assert "no lineage" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a PDF reached disk with no lineage")
    assert not any(Path(store.root).rglob("*")), "the bytes were written anyway"


def test_the_store_still_stores_unwatched_bytes_and_watched_ones_with_lineage():
    store = ArtifactStore(tempfile.mkdtemp())
    plain = store.put("scratch.bin", b"scratch", "application/octet-stream")
    assert store.exists(plain.sha256)
    lineage = P.Lineage(created_by="publishing", job_id=1)
    art = store.put("x/chart.png", b"png", "image/png", artefact_class="chart",
                    lineage=lineage)
    assert store.exists(art.sha256)
    assert lineage.for_file(art.sha256).sha256 == art.sha256
    try:
        store.put("x/y", b"y", "text/plain", artefact_class="vibes", lineage=lineage)
    except P.ProvenanceRefused as exc:
        assert "not an artefact class" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unwatched class was accepted")


def _refused(fn, fragment: str) -> None:
    try:
        fn()
    except P.ProvenanceRefused as exc:
        assert fragment in str(exc), str(exc)
    else:  # pragma: no cover
        raise AssertionError(f"accepted; expected a refusal mentioning {fragment!r}")


def test_record_lineage_refuses_what_it_cannot_vouch_for():
    db = _boot()
    inputs = {"cir:x": P.fingerprint({"rows": 1})}

    def rec(lineage, cls="listing_copy"):
        with db.session() as s:
            P.record_lineage(s, artefact_class=cls, artefact_key="x@1", product_slug="x",
                             inputs=inputs, lineage=lineage)

    _refused(lambda: rec(None), "no lineage")
    _refused(lambda: rec(P.Lineage(created_by="", job_id=1)), "missing ['created_by']")
    _refused(lambda: rec(P.Lineage(created_by="a")), "names no job")
    _refused(lambda: rec(P.Lineage(created_by="a", job_id=1, source="guessed")),
             "not a lineage source")
    _refused(lambda: rec(P.Lineage(created_by="a", source="backfilled")),
             "must cite the evidence")
    _refused(lambda: rec(P.Lineage(created_by="a", job_id=1), cls="pdf"), "sha256")
    _refused(lambda: rec(P.Lineage(created_by="a", job_id=1, parents=("hex.pdf",))),
             "not a parent artefact")
    _refused(lambda: rec(P.Lineage(created_by="a", job_id=1), cls="vibes"),
             "not an artefact class")
    rec(P.Lineage(created_by="a", job_id=1, parents=("certificate:x@1",)))
    assert len(_rows(db)) == 1


def test_a_backfilled_row_must_cite_its_evidence():
    db = _boot()
    ok = P.Lineage(created_by="a", source="backfilled", code_commit="unknown",
                   evidence={"job_id": 7, "audit_id": None, "matched_on": "Job.outputs"})
    with db.session() as s:
        P.record_lineage(s, artefact_class="chart", artefact_key="x@1#chart", product_slug="x",
                         inputs={"cir:x": P.fingerprint(1)}, lineage=ok.for_file("f" * 64))
    row = _rows(db)[0]
    assert row.source == "backfilled" and row.evidence["job_id"] == 7
    assert row.code_commit == "unknown"


# --- the worker's backstop ---------------------------------------------------------------------

def _allow(db, agent: str, job_type: str) -> None:
    with db.session() as s:
        row = s.scalar(select(Agent).where(Agent.name == agent))
        row.allowed_job_types = list(row.allowed_job_types or []) + [job_type]


def _bare_listing_registry() -> HandlerRegistry:
    registry = HandlerRegistry()

    @registry.register("test.bare_listing")
    def _handler(ctx):
        with ctx.db.session() as s:
            s.add(Listing(product_slug="bare", version="1.0.0", title="t", description="d",
                          tags=[], price_cad=5.0))
        return {"wrote": "a listing with no lineage"}

    return registry


def test_the_worker_refuses_a_handler_that_writes_a_listing_without_lineage():
    """Once the estate's backlog is closed, a job that leaves an artefact without a row does
    not complete. On a fresh database the backlog is closed by definition."""
    db = _boot()
    _allow(db, "listing", "test.bare_listing")
    JobQueue(db).enqueue("listing", "test.bare_listing", {})
    w = Worker(db, "w", registry=_bare_listing_registry())
    assert w.run_once() is True
    assert w.stats.failed == 1 and w.stats.completed == 0
    with db.session() as s:
        job = s.scalar(select(Job))
        actions = [(a.action, a.detail) for a in s.scalars(select(AuditLog))]
    assert job.status == JobStatus.DEAD, job.status
    assert "provenance refused" in (job.last_error or "")
    refused = [d for a, d in actions if a == "provenance.refused"]
    assert refused and refused[0]["enforcing"] is True
    assert refused[0]["missing"][0][0] in {"listing_copy", "seo", "pricing"}
    assert any(a == "job.provenance_refused" for a, _ in actions)


def test_before_the_backlog_is_closed_the_backstop_audits_and_lets_the_job_complete():
    """Failing a whole catalogue of jobs over instrumentation nobody had fitted is a
    different problem from a stale artefact, so an open backlog means log-only."""
    db = _boot()
    with db.session() as s:
        s.add(Product(slug="older", title="Older"))
        s.flush()
        s.add(PatternVersion(product_id=1, version="1.0.0", cir_json={"rows": 1},
                             release_hash="c" * 64, certified=True))   # prior, unproven
    _allow(db, "listing", "test.bare_listing")
    JobQueue(db).enqueue("listing", "test.bare_listing", {})
    w = Worker(db, "w", registry=_bare_listing_registry())
    assert w.run_once() is True
    assert w.stats.completed == 1
    with db.session() as s:
        refused = [a.detail for a in s.scalars(select(AuditLog))
                   if a.action == "provenance.refused"]
    assert refused and refused[0]["enforcing"] is False
    assert refused[0]["count"] == 3          # copy, seo and price on the one row


def test_the_backstop_excludes_the_offending_rows_when_asking_whether_to_enforce():
    """Read naively, the row that should fail the job is the row that says enforcement is
    premature, and the backlog is never closed."""
    db = _boot()
    with db.session() as s:
        s.add(Listing(product_slug="bare", version="1.0.0", title="t", description="d",
                      tags=[], price_cad=5.0))
    with db.session() as s:
        naive = P.graduation(s, current=P.current_from_db(s), expected=P.expected_from_db(s))
        missing = P.assert_instrumented(s, since=None)["missing"]
        gate = P.may_enforce_unproven(s, ignoring=missing)
    assert naive["may_enforce_unproven"] is False
    assert len(missing) == 3
    assert gate["may_enforce_unproven"] is True and gate["prior_unproven"] == 0


def test_assert_instrumented_only_looks_at_rows_created_since():
    from datetime import datetime, timedelta, timezone

    db = _boot()
    with db.session() as s:
        s.add(Listing(product_slug="bare", version="1.0.0", title="t", description="d",
                      tags=[], price_cad=5.0))
    with db.session() as s:
        now = P.assert_instrumented(s, since=datetime.now(timezone.utc) - timedelta(minutes=1))
        later = P.assert_instrumented(s, since=datetime.now(timezone.utc) + timedelta(hours=1))
    assert len(now["missing"]) == 3
    assert later["missing"] == []


def test_the_handlers_all_go_through_record_lineage_rather_than_record():
    """A handler that calls the lenient writer is a handler that can forget half the row."""
    import re

    for name in ("runtime/release.py", "runtime/pipeline.py"):
        text = (ROOT / "src" / "brambleloop" / name).read_text()
        assert not re.search(r"provenance\.record\(", text), name
    assert P.record_lineage.__doc__ and "Fail-closed" in P.record_lineage.__doc__


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
