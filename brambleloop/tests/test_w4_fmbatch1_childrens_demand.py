"""F-357: children's sub-category demand windows from monthly reference series (stubbed feed),
UNMEASURED until a year exists, monthly re-read only, and surfaced in the seasonal war room."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
_T = tempfile.mkdtemp(prefix="fmb1kd_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_T}/k.db"


def _no_network(*_a, **_k):
    raise OSError("network refused: tests use a stubbed feed")


socket.socket.connect = _no_network  # type: ignore[assignment]

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.culture import feeds  # noqa: E402
from brambleloop.seasonal import childrens_demand as K  # noqa: E402

db = Database(os.environ["BRAMBLELOOP_DATABASE_URL"])
db.create_all()
TODAY = date(2026, 10, 26)
calls = []


def stub(url):
    calls.append(url)
    assert "/monthly/" in url and url.startswith(feeds.BASE)
    if "Infant_clothing" in url:
        raise feeds.FeedRefused("no such article")
    items = []
    for y in (2024, 2025):
        for m in range(1, 13):
            v = 1000 + (900 if m in (4, 5) else 0)   # spring baby-shower season
            items.append({"timestamp": f"{y}{m:02d}0100", "views": v})
    return {"items": items}


def test_unmeasured_before_any_series():
    w = K.windows(db, today=TODAY)["subcategories"]
    assert all(v["state"] == "UNMEASURED" for v in w.values())


def test_sweep_records_series_names_failures_and_derives_windows():
    out = K.sweep_if_due(db, today=TODAY, get=stub)
    assert sorted(out["recorded"]) == ["amigurumi_toys", "baby_blankets", "baby_shower_gifts"]
    assert out["failures"][0]["subcategory"] == "baby_garments"
    w = K.windows(db, today=TODAY)["subcategories"]
    shower = w["baby_shower_gifts"]
    assert shower["state"] == "MEASURED" and shower["peak_months"] == [4, 5]
    assert shower["next_peak"] == "2027-04-01" and shower["seasonal"] is True
    assert shower["list_by"] < shower["next_peak"]
    assert w["baby_blankets"]["lead_days"] > w["amigurumi_toys"]["lead_days"]
    assert w["baby_garments"]["state"] == "UNMEASURED"


def test_monthly_gate_and_short_series():
    n = len(calls)
    assert K.sweep_if_due(db, today=TODAY, get=stub)["skipped"]
    assert len(calls) == n, "a second read in the same month makes no call"
    short = K.window_for([{"month": "202501", "views": 5}] * 5, 4.0, TODAY)
    assert short["state"] == "UNMEASURED"


def test_war_room_carries_the_windows():
    from brambleloop.seasonal import leadtime

    plans = leadtime.catalogue_plans(db, today=TODAY)
    assert plans["childrens_demand_windows"]["subcategories"]["baby_shower_gifts"][
        "peak_months"] == [4, 5]


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
