"""W4-AGENTS cluster C2: canonical-model evidence (F-217, F-744, F-738, F-747; F-218 is in
test_w4_departments). No provider is called: everything reads committed files and rows.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_c2_visual.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, OperatingReading, Phase  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402
from brambleloop.visual import model_ledger as ML, model_promotion as MP  # noqa: E402
from brambleloop.visual import portability as PT  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="w4c2_")
_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/c{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _frame(db, *, version, identity="pass", realism="pass", usable=True, why="ok"):
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action="assets.model_photography", detail={
            "provider": "stub-provider", "image_ref": f"sha-{version}-{identity}-{realism}",
            "conditioned_on": {"pack_version": version, "reference_image": "face.jpg",
                               "body_reference_image": "torso.png"},
            "identity": {"verdict": identity, "face": {"verdict": identity},
                         "morphology": {"verdict": identity}},
            "motif": {"verdict": "match"}, "photographic_realism": {"verdict": realism},
            "spent_cad": 0.0, "usable_as_listing_asset": usable, "why": why}))


def test_f217_benchmark_reports_face_morphology_and_overall_separately():
    from brambleloop.gateway import image_bench as IB

    sub = IB.identity_subscores({"identity_match": 4.6})
    assert sub["face_identity"] == 4.6
    assert sub["whole_person_morphology"] == "UNMEASURED"
    assert sub["overall_identity"] == "UNMEASURED"     # a high face score hides nothing
    assert "min" in sub["rule"]


def test_f744_every_experiment_is_kept_as_a_durable_normalised_record():
    db = _db()
    _frame(db, version="15", identity="drift", usable=False, why="morphology drift on bust")
    _frame(db, version="15")
    first = ML.harvest(db)
    again = ML.harvest(db)
    assert first["harvested"] == 2 and again["harvested"] == 0          # idempotent
    rec = {r["source_audit_id"]: r for r in ML.ledger(db)}
    r0 = next(r for r in rec.values() if r["accepted"] is False)
    for key in ("canonical_version", "provider", "references", "output_hashes", "identity",
                "product_truth", "realism", "cost_cad", "accepted", "reason"):
        assert key in r0, key
    assert r0["canonical_version"] == "15" and r0["identity"]["verdict"] == "drift"
    assert r0["settings"] == "UNKNOWN"                    # never recorded: UNKNOWN, not guessed
    # the source audit rows can be pruned; the failed approach is still known
    with db.session() as s:
        for a in s.scalars(select(AuditLog).where(
                AuditLog.action == "assets.model_photography")):
            s.delete(a)
    fails = ML.failed_approaches(db)
    assert fails and fails[0]["rejections"] == 1 and "bust" in fails[0]["reasons"][0]
    assert ("model_ledger", "publishing", "visual.model_ledger", 86400) in CADENCES
    job = JobQueue(db).enqueue("publishing", "visual.model_ledger", {})
    Registry(db).authorize("publishing", "visual.model_ledger")
    out = handlers.get("visual.model_ledger")(JobContext(
        job=job, db=db, queue=JobQueue(db), registry=Registry(db), phase=Phase.SHADOW))
    assert out["harvested"] == 0 and out["already"] == 2


def test_f738_a_realism_win_with_identity_loss_is_refused_and_unknown_never_promotes():
    recs = ([{"canonical_version": "1", "identity": {"verdict": "pass"}, "realism": r}
             for r in ["pass"] * 3 + ["fail"] * 3]
            + [{"canonical_version": "2", "identity": {"verdict": v}, "realism": "pass"}
               for v in ["pass"] * 4 + ["drift"] * 2]
            + [{"canonical_version": "3", "identity": {"verdict": "pass"}, "realism": r}
               for r in ["pass"] * 5 + ["fail"]])
    inc, worse_id, better = (MP.summarise(recs, v) for v in ("1", "2", "3"))
    assert MP.compare(inc, worse_id)["verdict"] == "REFUSE"          # realism up, identity down
    win = MP.compare(inc, better)
    assert win["verdict"] == "PROMOTE" and win["owner_decision_required"] is True
    assert MP.compare(inc, inc)["verdict"] == "REFUSE"              # no realism gain
    few = MP.summarise(recs[:2], "1")
    assert MP.compare(few, better)["verdict"] == "UNKNOWN"
    rb = MP.regression(worse_id, inc)
    assert rb["rollback"] is True and rb["lost"] == ["identity_retention"]


def test_f747_identity_is_portable_without_any_provider():
    b = PT.bundle()
    assert b["all_frames_committed"] is True and set(b["frames"]) == {
        "neutral_portrait", "torso_fit_reference", "full_length_standing"}
    assert b["provider_neutral"] is True, b["vendor_terms_in_spec"]
    out = PT.restore_check(tempfile.mkdtemp(prefix="restore_", dir=_TMP))
    assert out["ok"] is True and all(out["restored"].values())


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
