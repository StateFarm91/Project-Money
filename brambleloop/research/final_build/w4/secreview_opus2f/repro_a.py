"""Repro for Subject A findings (run from a worktree's brambleloop/ with PYTHONPATH=src:tests)."""
import os, sys, tempfile
d = tempfile.mkdtemp(); os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = d + "/art"
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")
from sqlalchemy import select
from brambleloop.core.db import Database
from brambleloop.core.models import OwnerAction, Job, JobStatus
from brambleloop.publish import listing_package as LP
db = Database(f"sqlite:///{d}/a.sqlite"); db.create_all()
pkg = {"slug": "s", "version": "1.0.0", "release_hash": "R1" * 32, "state": LP.READY,
       "blockers": [], "copy": {"title": "T"}, "identity": {}, "gallery": [], "files": {},
       "disclosures": [], "fingerprint": "f1"}
# A-2: owner completes the review; the next unchanged sweep queues it again.
print("first record:", LP.record(db, pkg)["review_requested"])
with db.session() as s:
    a = s.scalar(select(OwnerAction)); a.done = True; a.state = "done"
r = LP.record(db, pkg)
with db.session() as s:
    n = len(list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == "listing_package:s@1.0.0"))))
print("A-2 after owner marked done, unchanged package re-requested:", r["review_requested"], "rows:", n)
# A-3: package content changes (new release hash, still READY): the open review is not refreshed.
r = LP.record(db, {**pkg, "release_hash": "R2" * 32, "fingerprint": "f2"})
with db.session() as s:
    open_ = list(s.scalars(select(OwnerAction).where(OwnerAction.done == False)))
print("A-3 changed:", r["changed"], "review_requested:", r["review_requested"],
      "open review still cites:", [o.reason.split("release ")[1][:12] for o in open_])
# A-1: an assets.build job that names no release is accepted for the certified release.
with db.session() as s:
    s.add(Job(agent="publishing", job_type="assets.build", status=JobStatus.DONE,
              inputs={"slug": "s", "version": "1.0.0"},
              outputs={"pdf_sha256_by_terminology": {"US": "OLD" * 20}}, idempotency_key="old"))
print("A-1 _files for release R1 from a release-less job:", LP._files(db, "s", "1.0.0", "R1" * 32))
from brambleloop.runtime import pipeline
print("A-1 canonical pipeline._certified_pdf_hashes for same:",
      pipeline._certified_pdf_hashes(db, "s", "1.0.0", "R1" * 32))
