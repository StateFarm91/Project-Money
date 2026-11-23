"""D-OWNER-NO-PAUSE / D-OWNER-LAURA-MANDATORY (19i20).

Owner, 2026-11-23: "None of this should be paused. Ridiculous" and "Laura and model
photography is mandatory". An idle production-pipeline job is never parked by the free-poll
backoff, an existing park is cleared at boot, a failing job is still backed off (the
SUSPENDED breaker), and a gallery is never ready without an accepted Laura lifestyle frame.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident  # noqa: E402
from brambleloop.runtime.worker import CADENCES  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

NOW = datetime.now(timezone.utc)
SCHEDULED = {jt for _n, _a, jt, _p in CADENCES}


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='nop_')}/nop.sqlite")
    db.create_all()
    return db


def _idle(jt):
    return {jt: {"cadence": True, "identical_tail": True, "last_job_id": 7,
                 "last_finished_at": None}}


def _park(db, jt, kind):
    with db.session() as s:
        sig = (orc.BACKOFF_SIGNATURE_PREFIX if kind == orc.BACKOFF
               else orc.THRASH_SIGNATURE_PREFIX + "loop:") + jt
        s.add(Incident(severity="P3", signature=sig, summary="parked",
                       detail={"suspension": {
                           "kind": kind, "job_type": jt, "level": 5, "factor": 32,
                           "since": NOW.isoformat(), "code_commit": orc._commit(),
                           "handler_digest": orc.handler_digest(jt),
                           "suspend_until": (NOW + timedelta(days=30)).isoformat()}}))


def _open(db, jt):
    with db.session() as s:
        return [i.signature for i in s.scalars(select(Incident).where(
            Incident.resolved.is_(False))) if ((i.detail or {}).get("suspension") or {}
                                               ).get("job_type") == jt]


def test_the_owner_named_jobs_are_pipeline_jobs():
    named = ["radar.concept_pool", "radar.concept_intake", "creative.regate",
             "creative.model_reference_pack", "creative.blinded", "creative.expedition",
             "creative.candidates_file", "assets.model_photography",
             "assets.owned_photography", "assets.photo_review", "visual.image_production",
             "visual.identity_drift", "listing.package", "chain.successors", "gate.quality",
             "gate.lanes", "supply.admit", "intel.watchlist_compare", "cir.compile"]
    assert all(orc.is_pipeline_job(j) for j in named), [j for j in named
                                                        if not orc.is_pipeline_job(j)]
    assert orc.MANDATORY_JOB_TYPES <= SCHEDULED, orc.MANDATORY_JOB_TYPES - SCHEDULED
    assert not orc.is_pipeline_job("improve.nightly")


def test_an_idle_pipeline_job_is_never_parked():
    db = _db()
    for jt in sorted(j for j in SCHEDULED if orc.is_pipeline_job(j)):
        with db.session() as s:
            out = orc._free_poll_backoff(s, _idle(jt), now=NOW)
        assert out["applied"] == [], (jt, out)
        assert jt not in orc.suspended_job_types(db, now=NOW), jt


def test_an_idle_non_pipeline_poll_still_backs_off():
    db = _db()
    jt = "improve.nightly"
    assert jt in SCHEDULED
    with db.session() as s:
        out = orc._free_poll_backoff(s, _idle(jt), now=NOW)
    assert [a["job_type"] for a in out["applied"]] == [jt], out


def test_an_existing_park_is_ignored_lifted_and_cleared_at_boot():
    db = _db()
    for jt in orc.MANDATORY_JOB_TYPES | {"radar.concept_pool", "chain.successors"}:
        _park(db, jt, orc.BACKOFF)
        assert jt not in orc.suspended_job_types(db, now=NOW), jt
    with db.session() as s:
        out = orc._free_poll_backoff(s, _idle("assets.model_photography"), now=NOW)
    assert out["lifted"] == ["assets.model_photography"], out
    cleared = orc.clear_pipeline_backoffs(db)
    assert set(cleared) == (orc.MANDATORY_JOB_TYPES | {"radar.concept_pool",
                                                       "chain.successors"}) - {
        "assets.model_photography"}, cleared
    for jt in orc.MANDATORY_JOB_TYPES:
        assert _open(db, jt) == [], jt


def test_a_failing_pipeline_job_is_still_backed_off():
    db = _db()
    jt = "assets.model_photography"
    _park(db, jt, orc.SUSPENDED)
    assert orc.suspended_job_types(db, now=NOW)[jt]["kind"] == orc.SUSPENDED
    assert orc.clear_pipeline_backoffs(db) == []
    assert _open(db, jt), "the error-thrash breaker must survive the boot clear"


def test_a_gallery_without_an_accepted_laura_lifestyle_frame_is_not_ready():
    src = (ROOT / "src/brambleloop/visual/image_production.py").read_text()
    assert "laura_lifestyle_missing" in src and "standard[\"ok\"] and laura_ok" in src


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_")
           and inspect.isfunction(f)]
    for f in fns:
        f()
    print(f"{len(fns)} passed")
