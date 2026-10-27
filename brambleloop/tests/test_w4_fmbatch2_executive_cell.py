"""F-601 (rest): the Executive / COO department has its own improvement cell, measured from
the executive plan it acts on -- NotMeasured with no plan, never a defaulted zero."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.autonomy import executive_plan, memory  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import cells, freshness, measure, profiles  # noqa: E402


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmb2ex-')}/t.sqlite")
    db.create_all()
    return db


def _plan(db, path):
    memory.remember(db, executive_plan.MEMORY_KEY, kind="executive.plan",
                    department="executive", subject="plan", state="ok",
                    body={"as_of": "2026-10-26T00:00:00+00:00", "critical_path": path},
                    sources=["test"])


def test_the_executive_cell_is_declared_everywhere_a_cell_must_be():
    c = cells.BY_KEY["executive"]
    assert c.metric == "critical_path_parked_requirements" and c.higher_is_better is False
    assert measure.MEASURERS["executive"] is measure.measure_executive
    assert freshness.CELL_WORLD["executive"] == freshness.OPERATIONAL
    assert profiles.CELL_AGENT["executive"] == "coo"


def test_no_stored_plan_is_not_measured_rather_than_zero():
    out = measure.measure_executive(_db())
    assert isinstance(out, measure.NotMeasured) and "executive:plan" in out.reason


def test_the_number_is_the_requirements_parked_on_the_stored_critical_path():
    db = _db()
    _plan(db, [{"gate": "etsy_api", "kind": "owner", "unblocks": 7},
               {"gate": "model_provider", "kind": "external", "unblocks": 3},
               {"gate": "orders", "kind": "data", "unblocks": 0}])
    m = measure.measure_executive(db)
    assert isinstance(m, measure.Measurement)
    assert m.value == 10.0 and m.sample == 3
    assert m.detail["by_kind"] == {"data": 0, "external": 3, "owner": 7}
    _plan(db, [])                                    # an empty critical path is a real 0
    m = measure.measure_executive(db)
    assert m.value == 0.0 and m.sample == 1 and m.detail["gates"] == 0
    cells.record_capability(db, "executive", m.value, sample=m.sample)
    assert cells.latest_capability(db, "executive") == 0.0


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
