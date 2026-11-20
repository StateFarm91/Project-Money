"""W4-FIRSTSALE B5: durable customer PDF delivery -- a paid download never resolves to nothing.

On a real Launch-0 CIR (the hexagon coaster set), with the release date pinned:

* certified PDFs kept in Postgres/SQLite survive the artifact directory being wiped (a
  redeploy), and the rollback drill's `deliverables_restorable` passes on them;
* with nothing held, a re-render from the certified CIR is accepted only when byte-identical to
  the certified sha256, and is then kept;
* a re-render that drifts is refused (DeliveryRefused) and never served;
* the first-customer gate reads PASS / FAIL / UNVERIFIABLE from what is actually held;
* receipt -> delivery link -> bytes -> sha256 match (shadow; no Etsy call).

Runs on SQLite; set BL_TEST_PG_URL=postgresql+psycopg2://... to run it on Postgres too.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_firstsale_deliverables.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import deliverables as D  # noqa: E402

SLUG = "hexagon-coaster-set"
RELEASED = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
_PDFS: dict = {}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _db(url: str | None = None):
    from brambleloop.core.db import Database
    from brambleloop.core.models import Base

    if url:
        db = Database(url)
        Base.metadata.drop_all(db.engine)
    else:
        db = Database(f"sqlite:///{tempfile.mkdtemp()}/d.sqlite")
    db.create_all()
    return db


def _release(db, art: Path, *, keep: bool):
    """A certified release as assets.build leaves it: rows, hashes, files (and kept rows)."""
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.core.models import (AuditLog, Job, JobStatus, Listing, ListingAsset,
                                         PatternVersion, Product)
    from brambleloop.products import launch0 as l0

    cir = l0.cir_for(l0.candidate(SLUG).variants[0].build)
    with db.session() as s:
        p = Product(slug=SLUG, title=cir.title, status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True, certificate={"granted": True},
                             created_at=RELEASED))
    if not _PDFS:
        _PDFS.update(D.render_certified_pdfs(db, SLUG, cir.version))
    store = ArtifactStore(art)
    frame = b"\x89PNG\r\n\x1a\n" + b"frame-bytes-of-the-certified-hero"
    for t, b in _PDFS.items():
        store.put(f"{SLUG}/{t}.pdf", b, "application/pdf", db=db if keep else None,
                  keep=D.keep_why(SLUG, cir.version, f"pdf:{t}") if keep else "")
    store.put(f"{SLUG}/frame-1.png", frame, "image/png", db=db if keep else None,
              keep="frame" if keep else "")
    hashes = {t: _sha(b) for t, b in _PDFS.items()}
    with db.session() as s:
        job = Job(agent="assets", job_type="assets.build", inputs={"slug": SLUG},
                  status=JobStatus.DONE,
                  outputs={"slug": SLUG, "version": cir.version, "pdf_sha256": hashes["US"],
                           "pdf_sha256_by_terminology": hashes})
        s.add(job)
        s.flush()
        s.add(AuditLog(actor="assets", action="assets.built", artifact=f"{SLUG}@{cir.version}",
                       job_id=job.id, detail={"pdf_sha256_by_terminology": hashes}))
        s.add(ListingAsset(product_slug=SLUG, version=cir.version, position=1,
                           asset_class="photo", role="hero", sha256=_sha(frame)))
        s.add(Listing(product_slug=SLUG, version=cir.version, title=cir.title,
                      description="d", tags=[], price_cad=4.0, state="draft"))
    return cir.version, store


def _wipe(art: Path) -> None:
    shutil.rmtree(art, ignore_errors=True)


def case_kept_bytes_survive_a_redeploy(url=None):
    from brambleloop.gates import first_customer as fc
    from brambleloop.launch import rollback

    db, art = _db(url), Path(tempfile.mkdtemp()) / "art"
    version, store = _release(db, art, keep=True)
    _wipe(art)                                                  # the redeploy
    for t, b in _PDFS.items():
        got = D.resolve_pdf(db, SLUG, version, t, store=store,
                            render=lambda *_a: (_ for _ in ()).throw(AssertionError("render")))
        assert got["bytes"] == b and got["source"] == "durable", got["source"]
    assert D.durable_state(db, SLUG, version)["state"] == D.PASS
    drill = rollback.rehearse(db, slug=SLUG, version=version, store=store)
    step = next(s for s in drill["steps"] if s["step"] == "deliverables_restorable")
    assert step["ok"], step
    chk = fc.check_fulfilment_and_download(store, db=db, slug=SLUG, version=version)
    assert chk.state == fc.PASS, chk


def case_rerender_must_be_byte_identical_then_kept(url=None):
    db, art = _db(url), Path(tempfile.mkdtemp()) / "art"
    version, store = _release(db, art, keep=False)
    _wipe(art)
    assert D.durable_state(db, SLUG, version)["state"] == D.FAIL
    from brambleloop.launch import rollback

    step = next(s for s in rollback.rehearse(db, slug=SLUG, version=version, store=store)
                ["steps"] if s["step"] == "deliverables_restorable")
    assert not step["ok"], "nothing is held and nothing is on disk: the drill must fail"
    out = D.secure_release(db, SLUG, version, store=store)       # real re-render
    assert all(p["held"] for p in out["pdfs"].values()), out
    assert all(p["source"].startswith("re-render") for p in out["pdfs"].values()), out
    assert out["frames_missing"], "a frame gone from disk is reported, never invented"
    assert D.durable_state(db, SLUG, version)["state"] == D.PASS


def case_drifting_rerender_is_refused_never_served(url=None):
    from brambleloop.gates import first_customer as fc

    db, art = _db(url), Path(tempfile.mkdtemp()) / "art"
    version, store = _release(db, art, keep=False)
    _wipe(art)
    drift = {t: b + b"%drift" for t, b in _PDFS.items()}
    try:
        D.resolve_pdf(db, SLUG, version, "US", store=store, render=lambda *_a: drift)
        raise AssertionError("a drifted re-render was served")
    except D.DeliveryRefused as exc:
        assert "not the certified" in str(exc)
    assert not D.held(db, _sha(drift["US"]))
    chk = fc.check_fulfilment_and_download(store, db=db, slug=SLUG, version=version)
    assert chk.state == fc.FAIL, chk
    # nothing certified at all is UNVERIFIABLE, never PASS
    chk = fc.check_fulfilment_and_download(store, db=db, slug="no-such", version="1.0.0")
    assert chk.state == fc.UNVERIFIABLE, chk
    # and without a database the store's own (ephemeral) answer stands
    assert fc.check_fulfilment_and_download(store).state == fc.FAIL


def case_purchase_to_download_rehearsal(url=None):
    db, art = _db(url), Path(tempfile.mkdtemp()) / "art"
    version, store = _release(db, art, keep=True)
    _wipe(art)
    receipt = {"receipt_id": 900001, "status": "Paid", "is_paid": True,
               "transactions": [{"transaction_id": 1, "listing_id": 4242, "is_digital": True}]}
    out = D.rehearse_purchase(db, receipt, {"4242": (SLUG, version)}, store=store)
    assert out["state"] == D.PASS and out["links"] == 2, out
    assert {f["terminology"] for f in out["files"]} == {"US", "UK"}
    assert all(f["served_sha256"] == f["certified_sha256"] for f in out["files"])
    assert out["etsy_called"] is False
    unpaid = dict(receipt, status="Open", is_paid=False)
    assert D.rehearse_purchase(db, unpaid, {"4242": (SLUG, version)})["state"] == D.FAIL
    unmapped = D.rehearse_purchase(db, receipt, {}, store=store)
    assert unmapped["state"] == D.FAIL


def test_kept_bytes_survive_a_redeploy():
    case_kept_bytes_survive_a_redeploy()


def test_rerender_must_be_byte_identical_then_kept():
    case_rerender_must_be_byte_identical_then_kept()


def test_drifting_rerender_is_refused_never_served():
    case_drifting_rerender_is_refused_never_served()


def test_purchase_to_download_rehearsal():
    case_purchase_to_download_rehearsal()


def test_assets_build_keeps_the_certified_pdfs_and_frames():
    import inspect

    from brambleloop.runtime import release

    src = inspect.getsource(release.handle_assets_build)
    assert src.count("keep=deliverables_mod.keep_why(") == 2, "PDFs and frames are kept"
    src = inspect.getsource(release.handle_launch_readiness)
    assert "deliverables_mod.secure_release(" in src


def test_on_postgres_when_available():
    url = os.environ.get("BL_TEST_PG_URL")
    if not url:
        print("     (BL_TEST_PG_URL unset: Postgres run skipped, SQLite only)")
        return
    for case in (case_kept_bytes_survive_a_redeploy,
                 case_rerender_must_be_byte_identical_then_kept,
                 case_drifting_rerender_is_refused_never_served,
                 case_purchase_to_download_rehearsal):
        case(url)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:1500])
            traceback.print_exc(limit=4)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
