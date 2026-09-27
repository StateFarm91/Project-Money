"""Certification E: provenance, attacked at the real write boundaries.

Temp SQLite databases and a temp artifact directory only. Tests that expose a defect are
left failing on purpose.
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

_ART = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = _ART.name

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Agent, ArtefactProvenance, AuditLog, ContentPiece, Job, JobStatus, Listing,
    ListingAsset, PatternVersion, Product,
)
from brambleloop.ops import artefacts as P  # noqa: E402
from brambleloop.ops import backfill  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime.worker import HandlerRegistry, Worker  # noqa: E402

FP = P.fingerprint({"rows": 1})


def _boot() -> Database:
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _rows(db) -> list:
    with db.session() as s:
        out = list(s.scalars(select(ArtefactProvenance)))
        for r in out:
            s.expunge(r)
        return out


def _audits(db, action: str) -> list:
    with db.session() as s:
        return [dict(a.detail or {}) for a in s.scalars(select(AuditLog))
                if a.action == action]


def _refused(fn, fragment: str = "") -> str:
    try:
        fn()
    except P.ProvenanceRefused as exc:
        assert fragment in str(exc), str(exc)
        return str(exc)
    raise AssertionError(f"accepted; expected a ProvenanceRefused mentioning {fragment!r}")


def _rec(db, *, cls="listing_copy", key="x@1", inputs=None, lineage=None):
    with db.session() as s:
        return P.record_lineage(s, artefact_class=cls, artefact_key=key, product_slug="x",
                                inputs={"cir:x": FP} if inputs is None else inputs,
                                lineage=lineage or P.Lineage(created_by="listing", job_id=1))


# --- record_lineage: valid, missing, malformed -----------------------------------------------

def test_valid_lineage_writes_one_complete_row():
    db = _boot()
    _rec(db, lineage=P.Lineage(created_by="listing", job_id=7, parents=("certificate:x@1",)))
    (row,) = _rows(db)
    assert (row.created_by, row.job_id, row.source) == ("listing", 7, "recorded")
    assert row.inputs == {"cir:x": FP} and row.parents == ["certificate:x@1"]


def test_missing_and_malformed_lineage_is_refused_and_writes_nothing():
    db = _boot()
    cases = [
        (dict(lineage=None), ""),
        (dict(inputs={}), "no inputs"),
        (dict(inputs={"vibes:x": FP}), "not an upstream kind"),
        (dict(inputs={"cir": FP}), "not an upstream reference"),
        (dict(inputs={"cir:x y": FP}), "not an upstream reference"),
        (dict(inputs={"cir:x": "v1.0.0"}), "not a fingerprint"),
        (dict(inputs={"cir:x": "ABCDEF12"}), "not a fingerprint"),
        (dict(inputs={"cir:x": "abc"}), "not a fingerprint"),
        (dict(inputs={"cir:x": "g" * 16}), "not a fingerprint"),
        (dict(inputs={"cir:x": ""}), "not a fingerprint"),
        (dict(cls="vibes"), "not an artefact class"),
        (dict(cls="pdf"), "sha256"),
        (dict(cls="pdf", lineage=P.Lineage(created_by="a", job_id=1, sha256="F" * 64)),
         "sha256"),
        (dict(lineage=P.Lineage(created_by="a", job_id=1, parents=("nope",))),
         "not a parent"),
        (dict(lineage=P.Lineage(created_by="a", job_id=1, publication_authority="")),
         "missing"),
        (dict(lineage=P.Lineage(created_by="a", source="backfilled",
                                evidence={"matched_on": "x"})), "must cite"),
    ]
    for kwargs, fragment in cases:
        if kwargs.get("lineage", 1) is None:
            _refused(lambda: _with_none(db), "no lineage")
            continue
        _refused(lambda k=kwargs: _rec(db, **k), fragment)
    assert _rows(db) == [], "a refused write left a row"


def _with_none(db):
    with db.session() as s:
        P.record_lineage(s, artefact_class="listing_copy", artefact_key="x@1",
                         product_slug="x", inputs={"cir:x": FP}, lineage=None)


def test_conflicting_lineage_for_the_same_artefact_is_not_an_untraced_overwrite():
    """Same class+key recorded twice with different inputs by different jobs. Observed: the
    second call silently replaces inputs, job, creator and built_at on the one row; no
    history, no audit, no refusal. The first derivation is unrecoverable."""
    db = _boot()
    _rec(db, inputs={"cir:x": "1" * 16}, lineage=P.Lineage(created_by="listing", job_id=1))
    _rec(db, inputs={"cir:x": "2" * 16}, lineage=P.Lineage(created_by="intruder", job_id=99))
    rows = _rows(db)
    assert len(rows) == 1
    traced = any("1" * 16 in str(a) for a in _audits(db, "provenance.overwritten")) or \
        len(rows) > 1 or any("1" * 16 in str(r.evidence) for r in rows)
    assert traced, (f"first lineage (job 1, cir 111..) overwritten without trace; row now "
                    f"job={rows[0].job_id} by={rows[0].created_by} inputs={rows[0].inputs}")


def test_a_backfill_cannot_downgrade_a_recorded_row():
    """A `backfilled` write on a key the build already `recorded` replaces the build's own
    lineage with inferred evidence. backfill.run skips existing keys, but record_lineage --
    the fail-closed boundary -- does not."""
    db = _boot()
    _rec(db, lineage=P.Lineage(created_by="listing", job_id=5))
    try:
        _rec(db, lineage=P.Lineage(created_by="orchestrator", source="backfilled",
                                   code_commit="unknown",
                                   evidence={"job_id": 1, "matched_on": "guess"}))
    except P.ProvenanceRefused:
        return
    (row,) = _rows(db)
    assert row.source == "recorded" and row.job_id == 5, (
        f"recorded row downgraded to source={row.source} job={row.job_id}")


# --- stale lineage -----------------------------------------------------------------------------

def test_stale_and_unknown_inputs_read_stale_never_fresh_and_sweep_blocks():
    db = _boot()
    with db.session() as s:
        s.add(Product(slug="x", title="X"))
        s.flush()
        s.add(PatternVersion(product_id=1, version="1", cir_json={"rows": 2},
                             release_hash="c" * 64, certified=True))
    _rec(db, inputs={"cir:x": FP})                               # built from rows=1
    _rec(db, key="x@2", inputs={"cir:x": P.fingerprint({"rows": 2}), "policy:etsy": "a" * 16})
    with db.session() as s:
        current = P.current_from_db(s)
        verdicts = {v.artefact_key: v for v in P.check(s, current=current)}
    assert current["cir:x"] != FP
    assert verdicts["x@1"].state == P.STALE and verdicts["x@1"].moved == ("cir:x",)
    assert verdicts["x@2"].state == P.STALE and "policy:etsy" in verdicts["x@2"].unknown
    with db.session() as s:
        out = P.sweep(s, current=current)
    assert out, out
    from brambleloop.core.models import Incident
    with db.session() as s:
        incidents = [i for i in s.scalars(select(Incident)) if i.product_slug == "x"]
    assert incidents and all(getattr(i, "halts_publication", True) for i in incidents), incidents


# --- ArtifactStore.put ------------------------------------------------------------------------

def test_store_refuses_a_watched_class_with_no_lineage_and_writes_no_bytes():
    store = ArtifactStore(tempfile.mkdtemp())
    for cls in sorted(P.ARTEFACT_CLASSES):
        _refused(lambda c=cls: store.put("k", b"%PDF-1", "application/pdf",
                                         artefact_class=c), "no lineage")
    _refused(lambda: store.put("k", b"x", "text/plain", artefact_class="vibes",
                               lineage=P.Lineage(created_by="a", job_id=1)), "not an artefact")
    assert not any(Path(store.root).rglob("*")), "bytes reached disk"


def test_store_refuses_malformed_lineage_not_only_absent_lineage():
    """put() checks `lineage is None` and nothing else. A dict, a string, or a Lineage with an
    empty creator and no job all get a watched PDF onto disk."""
    store = ArtifactStore(tempfile.mkdtemp())
    accepted = []
    for bad in ({}, "trust me", P.Lineage(created_by="", job_id=None)):
        try:
            store.put(f"k{len(accepted)}", b"%PDF-" + repr(bad).encode(), "application/pdf",
                      artefact_class="pdf", lineage=bad)
        except P.ProvenanceRefused:
            continue
        accepted.append(repr(bad)[:40])
    assert not accepted, f"ArtifactStore.put stored a pdf with malformed lineage: {accepted}"


# --- the worker backstop -----------------------------------------------------------------------

def _allow(db, agent: str, job_type: str) -> None:
    with db.session() as s:
        row = s.scalar(select(Agent).where(Agent.name == agent))
        row.allowed_job_types = list(row.allowed_job_types or []) + [job_type]


def _registry(record_inputs_only: bool = False) -> HandlerRegistry:
    reg = HandlerRegistry()

    @reg.register("cert.listing")
    def _handler(ctx):
        with ctx.db.session() as s:
            s.add(Listing(product_slug="bare", version="1.0.0", title="t", description="d",
                          tags=[], price_cad=5.0))
            s.flush()
            if record_inputs_only:
                for cls in ("listing_copy", "seo", "pricing"):
                    P.record(s, artefact_class=cls, artefact_key=P.release_key("bare", "1.0.0"),
                             product_slug="bare", inputs={"cir:bare": FP})
        return {"ok": True}

    return reg


def _run(db, reg) -> tuple[Worker, object]:
    _allow(db, "listing", "cert.listing")
    JobQueue(db).enqueue("listing", "cert.listing", {})
    w = Worker(db, "cert", registry=reg)
    assert w.run_once() is True
    with db.session() as s:
        job = s.scalar(select(Job))
        s.expunge(job)
    return w, job


def test_worker_audits_and_fails_a_listing_without_lineage_when_enforcement_is_on():
    db = _boot()
    with db.session() as s:
        assert P.may_enforce_unproven(s)["may_enforce_unproven"] is True
    w, job = _run(db, _registry())
    refused = _audits(db, "provenance.refused")
    assert refused and refused[0]["enforcing"] is True, refused
    assert job.status == JobStatus.DEAD and w.stats.completed == 0, job.status
    assert _audits(db, "job.provenance_refused")


def test_worker_only_audits_when_a_prior_backlog_keeps_enforcement_off():
    db = _boot()
    with db.session() as s:
        s.add(Listing(product_slug="old", version="0.1", title="t", description="d", tags=[],
                      price_cad=0.0))
    w, job = _run(db, _registry())
    refused = _audits(db, "provenance.refused")
    assert refused and refused[0]["enforcing"] is False, refused
    assert job.status == JobStatus.DONE


def test_worker_rejects_rows_written_through_the_lineage_free_writer():
    """The backstop checks that a provenance row EXISTS, not that it carries lineage. A handler
    that calls the low-level `P.record` (inputs only: created_by='', job_id=None, commit
    unknown) satisfies it, and the job completes with enforcement on."""
    db = _boot()
    w, job = _run(db, _registry(record_inputs_only=True))
    rows = _rows(db)
    assert rows and all(r.created_by == "" and r.job_id is None for r in rows)
    assert job.status != JobStatus.DONE or _audits(db, "provenance.refused"), (
        f"job completed ({job.status}) with {len(rows)} lineage-free provenance rows and no "
        f"provenance.refused audit")


# --- backfill ----------------------------------------------------------------------------------

def _estate(db):
    with db.session() as s:
        s.add(Product(slug="x", title="X"))
        s.flush()
        # certified, certificate names the release, but no gate.certified audit row
        s.add(PatternVersion(product_id=1, version="1", cir_json={"r": 1},
                             release_hash="a" * 64, certified=True,
                             certificate={"release_hash": "a" * 64}))
        # certified, certificate names a DIFFERENT hash (with a matching audit row)
        s.add(PatternVersion(product_id=1, version="2", cir_json={"r": 2},
                             release_hash="b" * 64, certified=True,
                             certificate={"release_hash": "f" * 64}))
        s.add(AuditLog(actor="quality_director", action="gate.certified", artifact="x@2"))
        s.add(Listing(product_slug="x", version="1", title="t", description="d", tags=[],
                      price_cad=4.0, release_hash=""))             # no release hash
        s.add(Listing(product_slug="x", version="9", title="t", description="d", tags=[],
                      price_cad=4.0, release_hash="a" * 64))       # no stored release
        s.add(Listing(product_slug="x", version="2", title="t2", description="d", tags=[],
                      price_cad=0.0, release_hash="b" * 64))       # no audit row
        s.add(ListingAsset(product_slug="x", version="1", position=1, asset_class="hero",
                           role="hero", sha256=None))
        s.add(ListingAsset(product_slug="x", version="1", position=2, asset_class="hero",
                           role="hero", sha256="d" * 64))           # no build output
        s.add(ContentPiece(product_slug="x", channel="pinterest", title="p", body="b"))


def test_backfill_never_writes_without_evidence_and_leaves_the_rest_unproven():
    db = _boot()
    _estate(db)
    with db.session() as s:
        dry = backfill.run(s, dry_run=True)
    assert _rows(db) == [] and dry["backfilled"] == {}, dry
    with db.session() as s:
        report = backfill.run(s)
    assert report["backfilled"] == {}, report
    assert _rows(db) == [], [(r.artefact_class, r.artefact_key) for r in _rows(db)]
    with db.session() as s:
        verdicts = P.check(s, current=P.current_from_db(s), expected=P.expected_from_db(s))
    assert verdicts and all(v.state == P.UNPROVEN for v in verdicts), \
        [(v.artefact_class, v.artefact_key, v.state) for v in verdicts]
    left = sum(report["left_unproven"].values())
    assert left == len(verdicts), (left, len(verdicts), report["why"])


def test_backfill_writes_only_evidenced_rows_and_each_cites_its_evidence():
    db = _boot()
    _estate(db)
    with db.session() as s:
        s.add(AuditLog(actor="quality_director", action="gate.certified", artifact="x@1"))
    with db.session() as s:
        report = backfill.run(s)
    rows = _rows(db)
    assert report["backfilled"] == {"certificate": 1}, report
    (row,) = rows
    assert row.artefact_key == "x@1" and row.source == "backfilled"
    assert row.evidence.get("matched_on") and row.evidence.get("audit_id") is not None
    assert row.code_commit == "unknown"
    with db.session() as s:
        again = backfill.run(s)
    assert again["backfilled"] == {} and len(_rows(db)) == 1


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:500])
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
