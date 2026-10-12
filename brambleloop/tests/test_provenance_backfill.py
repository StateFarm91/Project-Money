"""#171: lineage for the artefacts that already exist, from evidence on file, or not at all.

Production held 275 derived artefacts with no provenance row. The backfill ties each to the
job, audit row or output hash that proves what made it, and the rule under test is the one
that makes the number honest: **a backfilled row must cite the evidence it was derived from,
and where none exists the artefact stays unproven.** Writing 275 rows from the current slug
and the current design would make the sentinel's one honest count read zero for a reason that
has nothing to do with anything being proved.

Also here: the additive migration that carries the lineage columns onto a database created
before them, and the `/api/provenance` surface that reports the estate by class and source.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/api.sqlite"
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"

from sqlalchemy import select, text  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    ArtefactProvenance, AuditLog, ContentPiece, CostEntry, Job, JobStatus, Listing,
    ListingAsset, PatternVersion, Product,
)
from brambleloop.ops import artefacts as P  # noqa: E402
from brambleloop.ops import backfill as B  # noqa: E402

SLUG = "hex-coaster"
DESIGN = {"slug": SLUG, "rows": 12}
RELEASE = "a" * 64
F1, F2 = "1" * 64, "2" * 64
PDF_US, PDF_UK, CHART, LEGEND = "3" * 64, "4" * 64, "5" * 64, "6" * 64
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _seed(db, *, certificate_hash=RELEASE, with_audits=True) -> dict:
    """The production shape in miniature: every kind of row the backfill can match, and
    one of each kind it must not."""
    ids: dict = {}
    with db.session() as s:
        s.add(Product(slug=SLUG, title="Hex Coaster"))
        s.flush()
        s.add(PatternVersion(product_id=1, version="1.0.0", cir_json=DESIGN,
                             release_hash=RELEASE, certified=True,
                             certificate={"release_hash": certificate_hash,
                                          "doc_version": "2"}))
        certify = Job(agent="quality_director", job_type="gate.certify", inputs={},
                      status=JobStatus.DONE, started_at=NOW - timedelta(hours=3),
                      finished_at=NOW - timedelta(hours=3, minutes=-1))
        seo = Job(agent="listing", job_type="listing.seo", inputs={},
                  status=JobStatus.DONE, started_at=NOW - timedelta(hours=2),
                  finished_at=NOW - timedelta(hours=2, minutes=-1))
        build = Job(agent="publishing", job_type="assets.build",
                    inputs={"slug": SLUG, "version": "1.0.0", "release": RELEASE},
                    idempotency_key=f"assets:{SLUG}:1.0.0:{RELEASE[:12]}:c6",
                    status=JobStatus.DONE, started_at=NOW - timedelta(hours=2, minutes=30),
                    finished_at=NOW - timedelta(hours=2, minutes=29),
                    outputs={"slug": SLUG, "version": "1.0.0", "release": RELEASE,
                             "pdf_sha256": PDF_US,
                             "pdf_sha256_by_terminology": {"UK": PDF_UK, "US": PDF_US},
                             "chart_sha256": CHART, "legend_sha256": LEGEND,
                             "frames": [{"position": 1, "sha256": F1}]})
        content = Job(agent="growth", job_type="marketing.schedule",
                      inputs={"slug": SLUG, "version": "1.0.0", "release": RELEASE},
                      idempotency_key=f"content:{SLUG}:1.0.0:{RELEASE[:12]}:c6",
                      status=JobStatus.DONE, started_at=NOW - timedelta(hours=1),
                      finished_at=NOW - timedelta(minutes=55))
        s.add_all([certify, seo, build, content])
        s.flush()
        ids.update(certify=certify.id, seo=seo.id, build=build.id, content=content.id)
        if with_audits:
            a1 = AuditLog(actor="quality_director", action="gate.certified",
                          artifact=f"{SLUG}@1.0.0", job_id=certify.id)
            a2 = AuditLog(actor="listing", action="listing.seo_drafted",
                          artifact=f"{SLUG}@1.0.0", job_id=seo.id)
            s.add_all([a1, a2])
            s.flush()
            ids.update(audit_certified=a1.id, audit_seo=a2.id)
        s.add(CostEntry(agent="listing", job_id=seo.id, amount_cad=0.02,
                        provider="anthropic", model="claude-haiku-4-5"))
        s.add(Listing(product_slug=SLUG, version="1.0.0", title="Hex Coaster Set",
                      description="d", tags=["a", "b"], price_cad=6.0,
                      release_hash=RELEASE, chain_version="6"))       # superseded chain
        s.add(Listing(product_slug="nordic-bundle", version="collection", title="Bundle",
                      description="d", tags=[], price_cad=20.0, chain_version="7"))
        s.add(ListingAsset(product_slug=SLUG, version="1.0.0", position=1,
                           asset_class="render", role="hero", sha256=F1, approved=True))
        s.add(ListingAsset(product_slug=SLUG, version="1.0.0", position=2,
                           asset_class="render", role="detail", sha256=F2))   # no build
        s.add(ContentPiece(product_slug=SLUG, channel="pinterest", title="Inside",
                           created_at=NOW - timedelta(minutes=58)))
        s.add(ContentPiece(product_slug=SLUG, channel="email", title="Outside",
                           created_at=NOW - timedelta(days=2)))
    return ids


def _rows(db) -> dict:
    with db.session() as s:
        return {(r.artefact_class, r.artefact_key): r
                for r in s.scalars(select(ArtefactProvenance))}


# --- what is derived, and from what -------------------------------------------------------------

def test_every_class_with_evidence_is_backfilled_and_every_one_without_is_counted():
    db = _db()
    _seed(db)
    with db.session() as s:
        out = B.run(s)
    assert out["backfilled"] == {"certificate": 1, "chart": 2, "listing_copy": 1,
                                 "marketing_asset": 1, "pdf": 2, "pricing": 1, "seo": 1,
                                 "visual_truth": 1}, out["backfilled"]
    assert out["left_unproven"] == {"listing_copy": 1, "marketing_asset": 1, "pricing": 1,
                                    "seo": 1, "visual_truth": 1}, out["left_unproven"]
    assert list(out["why"]["visual_truth"]) == [B._UNPROVEN["no_build_output"]]
    assert list(out["why"]["marketing_asset"]) == [B._UNPROVEN["outside_job_window"]]
    assert list(out["why"]["listing_copy"]) == [B._UNPROVEN["collection"]]
    assert out["source"] == "backfilled" and out["code_commit"] == "unknown"


def test_a_backfilled_row_cites_the_evidence_it_was_derived_from():
    db = _db()
    ids = _seed(db)
    with db.session() as s:
        B.run(s)
    rows = _rows(db)
    key = P.release_key(SLUG, "1.0.0")

    cert = rows[("certificate", key)]
    assert cert.source == "backfilled" and cert.code_commit == "unknown"
    assert cert.evidence == {"job_id": ids["certify"], "audit_id": ids["audit_certified"],
                             "matched_on": cert.evidence["matched_on"]}
    assert "gate.certified" in cert.evidence["matched_on"]
    assert cert.job_id == ids["certify"] and cert.created_by == "quality_director"
    assert cert.sha256 == RELEASE and cert.validation_status == "certified"
    assert cert.inputs == {f"cir:{SLUG}": P.fingerprint(DESIGN),
                           f"release:{SLUG}": RELEASE[:16]}
    assert cert.cost_cad is None and cert.model == ""       # no cost entry: not invented

    copy = rows[("listing_copy", key)]
    assert copy.evidence["job_id"] == ids["seo"] and copy.evidence["audit_id"] == ids["audit_seo"]
    assert copy.cost_cad == 0.02 and copy.model == "claude-haiku-4-5"
    assert copy.provider == "anthropic"
    assert copy.inputs["chain:release"] == P.chain_fingerprint("6")
    assert rows[("seo", key)].parents == [f"listing_copy:{key}"]
    assert rows[("pricing", key)].parents == [f"certificate:{key}"]

    frame = rows[("visual_truth", P.visual_key(SLUG, "1.0.0", 1))]
    assert frame.sha256 == F1 and frame.evidence["job_id"] == ids["build"]
    assert "frames[].sha256" in frame.evidence["matched_on"]
    assert frame.inputs["chain:release"] == P.chain_fingerprint("6")   # parsed from the key

    pdf = rows[("pdf", P.pdf_key(SLUG, "1.0.0", "UK"))]
    assert pdf.sha256 == PDF_UK and pdf.evidence["job_id"] == ids["build"]
    assert rows[("chart", P.chart_key(SLUG, "1.0.0", "legend"))].sha256 == LEGEND

    piece = rows[("marketing_asset", P.marketing_key(SLUG, "pinterest", "Inside"))]
    assert piece.evidence["job_id"] == ids["content"]
    assert "marketing.schedule" in piece.evidence["matched_on"]
    assert ("marketing_asset", P.marketing_key(SLUG, "email", "Outside")) not in rows


def test_a_superseded_chain_reads_stale_afterwards_which_is_the_honest_reading():
    """The listing was built under chain 6 and the chain is 7. Backfilling it is not a
    claim that it is current; it is the record of what it was made from, and the sweep
    says what that means now."""
    db = _db()
    _seed(db)
    with db.session() as s:
        B.run(s)
        out = P.sweep(s, current=P.current_from_db(s), expected=P.expected_from_db(s))
    by_key = {(v["artefact_class"], v["artefact_key"]): v for v in out["verdicts"]}
    key = P.release_key(SLUG, "1.0.0")
    assert by_key[("certificate", key)]["state"] == P.FRESH
    assert by_key[("listing_copy", key)]["state"] == P.STALE
    assert by_key[("listing_copy", key)]["moved"] == ["chain:release"]
    # Frame #1 matched a build's output and was backfilled under chain 6, so it reads STALE
    # for the same reason as the listing copy (certification C-5: this was stated in the API
    # test's comment but asserted nowhere).
    frame1 = by_key[("visual_truth", P.visual_key(SLUG, "1.0.0", 1))]
    assert frame1["state"] == P.STALE, frame1
    assert "chain:release" in frame1["moved"], frame1
    assert by_key[("visual_truth", P.visual_key(SLUG, "1.0.0", 2))]["state"] == P.UNPROVEN
    assert out["rebuild"] == [SLUG]


def test_a_certificate_whose_stored_document_names_another_release_stays_unproven():
    db = _db()
    _seed(db, certificate_hash="b" * 64)
    with db.session() as s:
        out = B.run(s)
    assert "certificate" not in out["backfilled"]
    assert out["why"]["certificate"] == {B._UNPROVEN["certificate_hash_mismatch"]: 1}


def test_without_an_audit_row_the_job_is_unknown_and_the_artefact_stays_unproven():
    db = _db()
    _seed(db, with_audits=False)
    with db.session() as s:
        out = B.run(s)
    assert "certificate" not in out["backfilled"]
    assert "listing_copy" not in out["backfilled"]
    assert out["why"]["certificate"] == {B._UNPROVEN["no_audit_row"]: 1}
    assert out["why"]["seo"][B._UNPROVEN["no_audit_row"]] == 1
    # The frames and the PDFs cite the build job's own outputs, which need no audit row.
    assert out["backfilled"]["visual_truth"] == 1 and out["backfilled"]["pdf"] == 2


def test_a_listing_with_no_release_hash_cannot_say_what_it_was_built_from():
    db = _db()
    _seed(db)
    with db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
        listing.release_hash = ""
    with db.session() as s:
        out = B.run(s)
    assert out["why"]["listing_copy"] == {B._UNPROVEN["no_release_hash"]: 1,
                                          B._UNPROVEN["collection"]: 1}


def test_the_backfill_is_idempotent_and_never_overwrites_a_recorded_row():
    db = _db()
    _seed(db)
    key = P.release_key(SLUG, "1.0.0")
    with db.session() as s:
        P.record_lineage(s, artefact_class="certificate", artefact_key=key, product_slug=SLUG,
                         inputs={f"cir:{SLUG}": P.fingerprint({"recorded": "live"})},
                         lineage=P.Lineage(created_by="quality_director", job_id=99,
                                           validation_status="certified"))
    with db.session() as s:
        first = B.run(s)
        second = B.run(s)
    assert "certificate" not in first["backfilled"]
    assert second["backfilled"] == {} and second["left_unproven"] == first["left_unproven"]
    assert second["skipped_existing"] > first["skipped_existing"]
    row = _rows(db)[("certificate", key)]
    assert row.source == "recorded" and row.job_id == 99


def test_a_dry_run_reports_without_writing():
    db = _db()
    _seed(db)
    with db.session() as s:
        out = B.run(s, dry_run=True)
    assert out["dry_run"] is True and out["backfilled"]["certificate"] == 1
    assert _rows(db) == {}


def test_the_handler_runs_the_backfill_and_audits_the_counts():
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401  -- registers handlers
    from brambleloop.runtime.release import handle_provenance_backfill
    from brambleloop.runtime.worker import JobContext, handlers

    assert handlers.get("ops.provenance_backfill") is handle_provenance_backfill
    db = _db()
    Registry(db).seed_defaults()
    _seed(db)
    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("orchestrator", "ops.provenance_backfill", {}), db=db,
                     queue=queue, registry=Registry(db), phase=None)
    out = handle_provenance_backfill(ctx)
    assert out["backfilled"]["certificate"] == 1
    with db.session() as s:
        audit = [a.detail for a in s.scalars(select(AuditLog))
                 if a.action == "ops.provenance_backfill"]
    assert audit and audit[0]["backfilled"] == out["backfilled"]
    assert audit[0]["left_unproven"] == out["left_unproven"]


def test_state_names_the_rules_and_the_evidence_actions():
    out = B.state()
    assert out["evidence_actions"] == {"certificate": "gate.certified",
                                       "listing": "listing.seo_drafted"}
    assert "stays unproven" in out["note"]


# --- the migration ----------------------------------------------------------------------------

LINEAGE_COLUMNS = ("created_by", "job_id", "code_commit", "provider", "model", "cost_cad",
                   "sha256", "parents", "validation_status", "publication_authority",
                   "source", "evidence")


def test_the_lineage_columns_reach_a_database_created_before_them():
    """The deployed table predates every column here. `plan` must see them, `apply` must add
    them with the model's scalar defaults, and the two JSON columns stay NULL and are read
    with `or {}`."""
    from sqlalchemy import inspect

    from brambleloop.core.migrate import plan

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/old.sqlite"
        db = Database(url)
        assert db.create_all() == []
        with db.engine.begin() as conn:
            for column in LINEAGE_COLUMNS:
                conn.execute(text(f'ALTER TABLE artefact_provenance DROP COLUMN "{column}"'))
            conn.execute(text(
                "INSERT INTO artefact_provenance (artefact_class, artefact_key, product_slug, "
                "inputs, chain_version, built_at) VALUES ('pdf', 'old.pdf', 'hex', "
                "'{\"cir:hex\": \"abcdef0123456789\"}', '', '2026-09-01 00:00:00')"))
        old = Database(url)
        assert {c["name"] for c in inspect(old.engine).get_columns("artefact_provenance")
                }.isdisjoint(LINEAGE_COLUMNS)

        planned = {column for table, column, _ in plan(old.engine)
                   if table == "artefact_provenance"}
        assert planned == set(LINEAGE_COLUMNS), planned
        changes = old.create_all()
        backfilled = {c.split()[0].split(".")[1] for c in changes
                      if c.startswith("artefact_provenance.") and "backfilled" in c}
        assert backfilled == {"created_by", "code_commit", "provider", "model", "sha256",
                              "validation_status", "publication_authority", "source"}, backfilled

        with Database(url).session() as s:
            row = s.scalar(select(ArtefactProvenance))
            assert row.source == "recorded" and row.code_commit == "unknown"
            assert row.created_by == "" and row.validation_status == "unknown"
            assert row.publication_authority == "shadow"
            assert row.job_id is None and row.cost_cad is None
            assert (row.evidence or {}) == {} and (row.parents or []) == []
            # The old row still sweeps, and the summary reads it without a shape error.
            summary = P.summary(s, current={"cir:hex": "abcdef0123456789"}, expected=[])
        assert summary["by_source"] == {"recorded": 1}
        assert summary["unknown_fields"]["code_commit"] == 1
        assert Database(url).create_all() == [], "the migration is not idempotent"


# --- /api/provenance --------------------------------------------------------------------------

def test_the_api_reports_the_estate_by_class_source_and_unknown_fields():
    from fastapi.testclient import TestClient

    from brambleloop.app import main as app_main

    db = app_main.db
    db.create_all()
    with db.session() as s:
        for model in (ArtefactProvenance, ContentPiece, ListingAsset, Listing, AuditLog,
                      CostEntry, Job, PatternVersion, Product):
            for row in s.scalars(select(model)):
                s.delete(row)
    _seed(db)
    with db.session() as s:
        B.run(s)
    body = TestClient(app_main.app).get("/api/provenance").json()
    assert body["by_source"] == {"backfilled": 10}
    assert body["by_class"]["certificate"] == {"fresh": 1, "stale": 0, "unproven": 0}
    assert body["by_class"]["listing_copy"] == {"fresh": 0, "stale": 1, "unproven": 1}
    # One frame matched a build's output and was backfilled under chain 6, so it reads stale
    # (the sibling test states why); the other matched nothing and stays unproven.
    assert body["by_class"]["visual_truth"] == {"fresh": 0, "stale": 1, "unproven": 1}
    assert body["unknown_fields"]["code_commit"] == 10
    assert body["unknown_fields"]["model"] == 10 - 3      # the three listing rows had a cost entry
    assert body["enforcing"] is False
    assert body["estate"]["unproven"] == 5 and body["estate"]["checked"] == 15
    assert body["graduation"]["may_enforce_unproven"] is False
    assert body["sources"] == ["recorded", "backfilled"]


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
