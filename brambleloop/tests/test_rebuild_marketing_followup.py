"""19h22: a verify pass that finds ONLY marketing_asset outstanding re-runs the attempt's own
marketing.schedule (same inputs, same rebuild token) once per pass. Production 2026-11-22:
marketing.schedule runs before listing.package and assets.build, so on every re-armed rebuild
it was refused on the product's own staleness (#173, #172) while the bundle and PDF rows
were still outstanding. Nothing ran it again, so each attempt ended rebuild-incomplete with
only marketing left. The marketing gate itself is unchanged."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, Phase  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import release as R  # noqa: E402
from brambleloop.runtime.worker import JobContext  # noqa: E402

MKT = {"slug": "cloud", "version": "1.0.0", "release": "r1", "rebuild": "tok",
       "launch": {"launch_on": "2026-11-22"}, "as_of": "2026-11-22"}


def _setup():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/m.db")
    db.create_all()
    Registry(db).seed_defaults()
    q = JobQueue(db)
    stage = q.enqueue("listing", "pricing.position", {"slug": "cloud"}, idempotency_key="st")
    mk = q.enqueue("growth", "marketing.schedule", MKT, idempotency_key="mk1")
    other = q.enqueue("growth", "marketing.schedule", dict(MKT, slug="other"),
                      idempotency_key="mk-other")
    verify = q.enqueue("listing", "chain.rebuild", {"product_slug": "cloud", "verify": 1,
                                                    "stage_job": stage.id},
                       idempotency_key="v1")
    with db.session() as s:
        for j in (mk, other):
            s.get(Job, j.id).status = JobStatus.DONE
        job = s.get(Job, verify.id)
        s.expunge(job)
    ctx = JobContext(job=job, db=db, queue=q, registry=Registry(db), phase=Phase.SHADOW)
    return db, ctx, stage


def _followups(db):
    with db.session() as s:
        return [dict(j.inputs) for j in s.scalars(select(Job).where(
            Job.job_type == "marketing.schedule",
            Job.idempotency_key.like("rebuild-mkt-followup:%")))]


def test_only_marketing_outstanding_reruns_the_attempts_own_marketing_once():
    db, ctx, stage = _setup()
    stale = ["marketing_asset:cloud:pin:a", "marketing_asset:cloud:email:b"]
    i = {"stage_job": stage.id}
    assert R._marketing_followup(ctx, "cloud", stale, i, 1) is not None
    got = _followups(db)
    assert got == [MKT], got                        # this product's own inputs and token
    assert R._marketing_followup(ctx, "cloud", stale, i, 1) is None     # once per pass
    assert len(_followups(db)) == 1
    with db.session() as s:
        assert s.scalar(select(AuditLog).where(
            AuditLog.action == "chain.rebuild_marketing_followup")) is not None


def test_nothing_is_rerun_while_other_classes_are_outstanding_or_unbound():
    db, ctx, stage = _setup()
    assert R._marketing_followup(ctx, "cloud", ["marketing_asset:x", "pdf:cloud@1.0.0"],
                                 {"stage_job": stage.id}, 1) is None
    assert R._marketing_followup(ctx, "cloud", [], {"stage_job": stage.id}, 1) is None
    assert R._marketing_followup(ctx, "cloud", ["marketing_asset:x"], {}, 1) is None
    assert R._marketing_followup(ctx, "nope", ["marketing_asset:x"],
                                 {"stage_job": stage.id}, 1) is None
    assert _followups(db) == []


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(exc))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
