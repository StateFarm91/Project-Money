"""#241 and #265: the launch experiment pack, persisted, owned and killable.

The proof audit (2026-09-26) found `launch_pack()` with no caller, experiments held in a
dict that died with the process, and no owner, expected value or "kill it if it cannot change
a decision". These run the `growth.experiments` handler through the worker against drafted
listings and read what it persisted.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, JobStatus, Listing, RegisteredExperiment  # noqa: E402
from brambleloop.growth import experiments as ex  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

for _var in ("BRAMBLELOOP_SITE_URL", "PINTEREST_ACCESS_TOKEN"):
    os.environ.pop(_var, None)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/exp.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, inputs: dict, key: str) -> dict:
    job = JobQueue(db).enqueue("experiment_steward", "growth.experiments", inputs,
                               idempotency_key=key)
    assert Worker(db, "exp").run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
        return dict(row.outputs)


def test_every_drafted_listing_launches_with_a_persisted_owned_pack():
    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug="fir", version="1.0.0", title="t", description="d",
                      price_cad=12.0))
    out = _run(db, {}, "e1")
    assert out["products"] == 1 and out["created"] == 5
    with db.session() as s:
        rows = {r.key: r for r in s.scalars(select(RegisteredExperiment))}
    assert set(rows) == {"fir:thumbnail", "fir:price", "fir:search", "fir:bundle",
                         "fir:pinterest_content"}
    for row in rows.values():
        assert row.owner and row.decision, row.key
        assert row.detail["on_success"] != row.detail["on_failure"]
        # Nothing measured, so nothing estimated.
        assert row.expected_value_cad is None
    assert rows["fir:price"].owner == "pricing" and "12.00" in rows["fir:price"].decision
    assert {r.state for k, r in rows.items() if k != "fir:pinterest_content"} == {"registered"}


def test_the_content_experiment_exists_as_a_definition_gated_on_owned_surfaces():
    db = _db()
    out = _run(db, {"slug": "moss", "price_cad": 9.0}, "e2")
    result = out["results"][0]
    assert result["owned_surfaces_open"] is False
    assert result["gated"] == ["moss:pinterest_content"]
    with db.session() as s:
        row = s.scalar(select(RegisteredExperiment).where(
            RegisteredExperiment.key == "moss:pinterest_content"))
        assert row.state == ex.GATED and row.gated_on == "owned_surfaces"
    try:
        ex.record_persisted(db, "moss:pinterest_content", 50.0, 30)
    except ex.ExperimentRefused as e:
        assert "gated" in str(e)
    else:
        raise AssertionError("a result was recorded for an experiment whose surface is absent")


def test_registration_is_write_once_so_a_threshold_cannot_move_afterwards():
    db = _db()
    _run(db, {"slug": "fir", "price_cad": 12.0}, "e3")
    again = _run(db, {"slug": "fir", "price_cad": 99.0}, "e4")
    assert again["created"] == 0
    loaded = ex.load(db, "fir:price")
    assert "12.00" in loaded.hypothesis and loaded.success_threshold == 0.02

    verdict = ex.record_persisted(db, "fir:price", 0.03, 600)
    assert verdict["verdict"] == "success"
    assert ex.load(db, "fir:price").state == ex.CONCLUDED


def test_an_experiment_that_cannot_change_a_decision_is_killed_not_run():
    db = _db()
    pointless = ex.Experiment(
        key="fir:ribbon_colour",
        hypothesis="a red ribbon in the hero frame changes clicks for this pattern",
        metric="listing_click_through_rate", design=ex.STAGGERED,
        success_threshold=0.02, failure_threshold=0.01, minimum_sample=500,
        stop_on=date(2026, 12, 1), owner="publishing",
        decision="which ribbon colour to use",
        on_success="keep the current hero frame", on_failure="keep the current hero frame")
    stored = ex.persist(db, pointless, product_slug="fir")
    assert stored["state"] == ex.KILLED and "cannot change a decision" in stored["killed_reason"]

    costly = ex.Experiment(
        key="fir:paid_boost", hypothesis="a paid boost moves conversion enough to pay for it",
        metric="conversion_rate", design=ex.HOLDOUT, success_threshold=0.03,
        failure_threshold=0.01, minimum_sample=200, stop_on=date(2026, 12, 1),
        owner="growth", cost_cad=40.0, expected_value_cad=10.0,
        decision="whether to boost", on_success="boost", on_failure="do not boost")
    assert ex.persist(db, costly)["state"] == ex.KILLED

    try:
        ex.persist(db, ex.Experiment(
            key="x", hypothesis="an experiment with nobody accountable for its answer",
            metric="m", design=ex.HOLDOUT, success_threshold=1, failure_threshold=0,
            minimum_sample=1, stop_on=date(2026, 12, 1), decision="d",
            on_success="a", on_failure="b"))
    except ex.ExperimentRefused as e:
        assert "no owner" in str(e)
    else:
        raise AssertionError("an ownerless experiment was persisted")


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
