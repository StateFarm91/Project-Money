"""F-488: critical-path movement is recorded when it changes and leads the dashboard
headline beside the launch-cleared count; with no reading it is UNMEASURED, not zero."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1pg_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/p.db"

from brambleloop.app import dashboard_truth as D  # noqa: E402
from brambleloop.build2 import critical_path as C  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402

db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
db.create_all()


def _a(n, head):
    return {"length": n, "critical_path": head, "gates_by_unblocked": [{"gate": "g", "unblocks": 3}]}


def test_unmeasured_before_any_reading():
    k = D._critical_path_kpi(db)
    assert k["value"] == "UNMEASURED" and k["alarm"] is True


def test_movement_is_recorded_on_change_only_and_shown():
    C.record_movement(db, analysis=_a(5, ["gate:g", "#1"]))
    C.record_movement(db, analysis=_a(5, ["gate:g", "#1"]))      # unchanged: no new event
    m = C.movement(db)
    assert m["length"] == 5 and m["previous"] is None
    C.record_movement(db, analysis=_a(3, ["gate:g", "#2"]))
    m = C.movement(db)
    assert (m["length"], m["previous"], m["delta"]) == (3, 5, -2)
    k = D._critical_path_kpi(db)
    assert k["value"] == "3 (-2)" and k["alarm"] is False and "gate:g" in k["why"]
    C.record_movement(db, analysis=_a(4, ["gate:g", "#3"]))
    assert D._critical_path_kpi(db)["alarm"] is True, "a growing path is an alarm"


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
