"""The rollback drill and the deliverable keeper agree on what a restore re-serves.

Production (Railway, ephemeral disk): every Launch-0 release's publication-approval
`rollback` section failed on `deliverables_restorable`. `launch.readiness` runs
`deliverables.secure_release` and then `rollback.rehearse`, but the two named different files:

* `secure_release` read the release-UNBOUND PDF set (the newest `assets.built` row of any
  release) and only the listing-set frames `certified_frames` returned;
* `rehearse` reads the set bound to the release on file (`PatternVersion.release_hash`), falls
  back to the newest built job for this slug@version, and reads the valid certificate's frames.

So when the newest build was not the one bound to the current release (a rebuild whose job
carried no release, or an older bound build), the keeper re-rendered/kept one set and the drill
demanded another that nothing had kept -- and after a redeploy wiped the disk the drill failed
for a release whose certified bytes were reproducible.

Cases:
1. bound set reproducible, newest build unbound: after a wipe, readiness's secure + drill
   PASS (it failed before the fix: the bound PDFs were never secured);
2. the bound set is NOT reproducible and nothing holds it: the drill still FAILS (the gate is
   not weakened; nothing is substituted);
3. a release with no recorded PDF at all is FAIL, never PASS.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_rollback_restore_set.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import deliverables as D  # noqa: E402

SLUG = "hexagon-coaster-set"
RELEASE = "r" * 64
RELEASED = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
_PDFS: dict = {}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/d.sqlite")
    db.create_all()
    return db


def _built(db, version, hashes, *, release):
    from brambleloop.core.models import AuditLog, Job, JobStatus

    with db.session() as s:
        job = Job(agent="publishing", job_type="assets.build",
                  inputs={"slug": SLUG, "version": version, "release": release},
                  status=JobStatus.DONE,
                  outputs={"slug": SLUG, "version": version, "pdf_sha256": hashes["US"],
                           "pdf_sha256_by_terminology": hashes})
        s.add(job)
        s.flush()
        s.add(AuditLog(actor="publishing", action="assets.built",
                       artifact=f"{SLUG}@{version}", job_id=job.id,
                       detail={"pdf_sha256_by_terminology": hashes}))


def _release(db, art: Path, *, bound_reproducible: bool):
    """A listed release whose bound build is older than an unbound rebuild; nothing kept."""
    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.core.models import Listing, ListingAsset, PatternVersion, Product
    from brambleloop.products import launch0 as l0

    cir = l0.cir_for(l0.candidate(SLUG).variants[0].build)
    with db.session() as s:
        p = Product(slug=SLUG, title=cir.title, status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True, certificate={"granted": True},
                             release_hash=RELEASE, created_at=RELEASED))
    if not _PDFS:
        _PDFS.update(D.render_certified_pdfs(db, SLUG, cir.version))
    real = {t: _sha(b) for t, b in _PDFS.items()}
    stale = {t: _sha(b"not-reproducible-" + t.encode()) for t in _PDFS}
    store = ArtifactStore(art)
    frame = b"\x89PNG\r\n\x1a\n" + b"frame-bytes-of-the-certified-hero"
    store.put(f"{SLUG}/frame-1.png", frame, "image/png", db=db,
              keep=D.keep_why(SLUG, cir.version, "frame"))
    # the build bound to the release on file (older), then an unbound rebuild (newer)
    _built(db, cir.version, real if bound_reproducible else stale, release=RELEASE)
    _built(db, cir.version, stale if bound_reproducible else real, release="")
    with db.session() as s:
        s.add(ListingAsset(product_slug=SLUG, version=cir.version, position=1,
                           asset_class="photo", role="hero", sha256=_sha(frame)))
        s.add(Listing(product_slug=SLUG, version=cir.version, title=cir.title,
                      description="d", tags=[], price_cad=4.0, state="draft"))
    return cir.version, store


def _readiness_drill(db, version, store) -> dict:
    """What `launch.readiness` does per listed release: secure, then rehearse."""
    from brambleloop.launch import rollback

    D.secure_release(db, SLUG, version, store=store)
    drill = rollback.rehearse(db, slug=SLUG, version=version, store=store)
    return next(s for s in drill["steps"] if s["step"] == "deliverables_restorable")


def case_bound_set_is_secured_and_drill_passes():
    db, art = _db(), Path(tempfile.mkdtemp()) / "art"
    version, store = _release(db, art, bound_reproducible=True)
    shutil.rmtree(art, ignore_errors=True)  # the redeploy
    step = _readiness_drill(db, version, store)
    assert step["ok"], step
    bound = D.certified(db, SLUG, version, RELEASE)["pdfs"]
    assert bound and all(D.held(db, h) for h in bound.values()), bound


def case_unreproducible_bound_set_still_fails():
    db, art = _db(), Path(tempfile.mkdtemp()) / "art"
    version, store = _release(db, art, bound_reproducible=False)
    shutil.rmtree(art, ignore_errors=True)
    step = _readiness_drill(db, version, store)
    assert not step["ok"], ("the certified bound PDFs exist nowhere and cannot be re-rendered: "
                            f"the drill must fail, {step}")
    assert step["missing_on_disk"], step


def case_no_recorded_pdf_is_not_pass():
    from brambleloop.core.models import Listing, PatternVersion, Product
    from brambleloop.launch import rollback

    db = _db()
    with db.session() as s:
        p = Product(slug=SLUG, title="t", status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={}, certified=True,
                             certificate={"granted": True}, release_hash=RELEASE))
        s.add(Listing(product_slug=SLUG, version="1.0.0", title="t", description="d",
                      tags=[], price_cad=4.0, state="draft"))
    out = D.secure_release(db, SLUG, "1.0.0")
    assert out["ok"] is False, out
    step = next(s for s in rollback.rehearse(db, slug=SLUG, version="1.0.0")["steps"]
                if s["step"] == "deliverables_restorable")
    assert step["ok"] is False and step["pdf_hashes"] == 0, step


def main() -> int:
    cases = [case_bound_set_is_secured_and_drill_passes,
             case_unreproducible_bound_set_still_fails,
             case_no_recorded_pdf_is_not_pass]
    failed = 0
    for c in cases:
        try:
            c()
            print(f"OK   {c.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {c.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(cases) - failed} OK, {failed} failing")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
