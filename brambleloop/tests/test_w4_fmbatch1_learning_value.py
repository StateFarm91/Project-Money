"""F-723: research spend above the threshold needs an expected learning value that clears the
floor; refusals are recorded; realised value is reported beside the expectation."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1lv_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/l.db"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_T, "a")

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.finance import learning_value as L  # noqa: E402

db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
db.create_all()
E = L.Expected(question="which traits sell", informs="blind_review", new_observations=40)


def _refused(**kw):
    try:
        L.require(db, **kw)
    except L.LearningValueRefused as exc:
        return str(exc)
    raise AssertionError(f"admitted: {kw}")


def test_below_threshold_or_non_research_needs_nothing():
    assert L.require(db, purpose="gallery_observation", amount_cad=0.1, expected=None)["required"] is False
    assert L.require(db, purpose="listing_copy", amount_cad=50, expected=None)["required"] is False


def test_refusals_above_threshold():
    assert "no expected" in _refused(purpose="gallery_observation", amount_cad=2.0, expected=None)
    assert "no new observation" in _refused(
        purpose="research.serp", amount_cad=2.0,
        expected=L.Expected(question="q", informs="d", new_observations=0))
    assert "name the question" in _refused(
        purpose="gallery_observation", amount_cad=2.0,
        expected=L.Expected(question=" ", informs="d", new_observations=10))
    assert "below the floor" in _refused(
        purpose="gallery_observation", amount_cad=10.0,
        expected=L.Expected(question="q", informs="d", new_observations=3))
    assert L.report(db)["refused"], "refusals are recorded"


def test_admitted_then_realised_is_reported():
    r = L.require(db, purpose="gallery_observation", amount_cad=2.0, expected=E, job_id=7)
    assert r["required"] and r["receipt"] and r["value_per_cad"] == 20.0
    rep = L.report(db)
    assert r["receipt"] in rep["unrealised"]
    line = next(x for x in rep["lines"] if x["receipt"] == r["receipt"])
    assert line["realised_observations"] == "UNREALISED"
    L.realise(db, r["receipt"], observations=30, cost_cad=1.6)
    rep = L.report(db)
    line = next(x for x in rep["lines"] if x["receipt"] == r["receipt"])
    assert line["realisation"] == 0.75 and r["receipt"] not in rep["unrealised"]
    assert rep["mean_realisation"] == 0.75


def test_gallery_handler_refuses_a_drained_backlog_before_spending():
    from types import SimpleNamespace

    from brambleloop.finance import spend_policy
    from brambleloop.gateway import anthropic as gw
    from brambleloop.intel import vision
    from brambleloop.runtime import release, worker

    audits, called = [], []
    saved = (gw.vision_usable, spend_policy.may_spend, spend_policy.work_that_fits,
             vision.pending_count, vision.per_image_estimate_cad, vision.analyse,
             worker.cadence_seconds)
    gw.vision_usable = lambda db: True
    spend_policy.may_spend = lambda db, p, **k: {"may_spend": True}
    spend_policy.work_that_fits = lambda db, **k: {"units": 20, "binding_ceiling": "x", "why": ""}
    vision.per_image_estimate_cad = lambda: 0.05
    vision.analyse = lambda *a, **k: called.append(1) or {}
    worker.cadence_seconds = lambda name: 3600
    ctx = SimpleNamespace(db=db, job=SimpleNamespace(id=1), should_yield=lambda: False,
                          audit=lambda a, **k: audits.append((a, k)))
    try:
        vision.pending_count = lambda db, key: {"unjudged": 0}
        out = release.handle_gallery_analysis(ctx)
        assert out["ran"] is False and "no new observation" in out["reason"], out
        assert not called, "a refused batch must not reach the vision call"
        vision.pending_count = lambda db, key: {"unjudged": 500}
        vision.analyse = lambda *a, **k: called.append(1) or {
            "judged": 18, "attempted": 20, "remaining": 482, "cost_cad": 0.9, "failures": []}
        out = release.handle_gallery_analysis(ctx)
        assert out["ran"] is True and called
    finally:
        (gw.vision_usable, spend_policy.may_spend, spend_policy.work_that_fits,
         vision.pending_count, vision.per_image_estimate_cad, vision.analyse,
         worker.cadence_seconds) = saved
    line = L.report(db)["lines"][0]
    assert line["expected_observations"] == 20 and line["realised_observations"] == 18


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
