"""F-581/F-582: a software spend scope cannot get a limit without a recorded vendor
evaluation (capability gap, overlap checked, ROI above cost); other scopes are unchanged."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1ts_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/t.db"

from brambleloop.agents.registry import SpendGuard  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.finance import tool_decisions as T  # noqa: E402

db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
db.create_all()
EVAL = {"capability_gap": "no bulk listing editor for 400 variants",
        "overlap": [{"existing": "publish/listing_manager", "why_not_enough": "single listing"}],
        "expected_roi": {"value_cad_month": 60.0, "basis": "8 h/month saved at CA$7.50"},
        "data_quality": "reads listings via Etsy API", "permissions": "listings_w",
        "vendor_risk": "small vendor; export available", "build_vs_buy": "3 weeks to build"}


def _refused(fn):
    try:
        fn()
    except T.ToolSpendRefused as exc:
        return str(exc)
    raise AssertionError("accepted")


def test_other_scopes_are_unchanged():
    SpendGuard(db).set_limit("ads", 5.0, 50.0)


def test_software_scope_needs_an_evaluation_with_roi_above_cost():
    g = SpendGuard(db)
    assert "decision_ref" in _refused(lambda: g.set_limit("software:vela", 1.0, 30.0))
    assert "overlap" in _refused(lambda: T.record_evaluation(
        db, tool="vela", monthly_cost_cad=30, evaluation={**EVAL, "overlap": []},
        evaluated_by="owner"))
    assert "expected_roi" in _refused(lambda: T.record_evaluation(
        db, tool="vela", monthly_cost_cad=30,
        evaluation={**EVAL, "expected_roi": {"value_cad_month": 60}}, evaluated_by="owner"))
    weak = T.record_evaluation(db, tool="vela", monthly_cost_cad=80, evaluation=EVAL,
                               evaluated_by="owner")
    assert "does not exceed" in _refused(lambda: g.set_limit("software:vela", 3.0, 80.0,
                                                             decision_ref=weak))
    good = T.record_evaluation(db, tool="vela", monthly_cost_cad=30, evaluation=EVAL,
                               evaluated_by="owner")
    assert "not an evaluation" in _refused(lambda: g.set_limit("software:other", 1.0, 30.0,
                                                               decision_ref=good))
    g.set_limit("software:vela", 1.0, 30.0, decision_ref=good)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
