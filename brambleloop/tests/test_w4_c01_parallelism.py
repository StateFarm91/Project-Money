"""F-865 Bounded Parallelism: live work lanes are bounded (disjoint ownership and one
integrator already enforced), and the survey measures integrated work per window per lane
slot, not agent count."""
import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

OPS = str(Path(__file__).resolve().parents[2] / "ops")
sys.path.insert(0, OPS)
import board as B  # noqa: E402
import registry as R  # noqa: E402


def _reg(d):
    return R.Registry(Path(d) / "JOBS.json", git=lambda *a: (1, ""))


def _job(d, n):
    return B.Job(name=n, log=Path(d) / f"{n}.log")


def test_the_bound_refuses_one_lane_too_many_and_frees_on_integration():
    assert R.DEFAULT_MAX_WORK_LANES == 6 and R.max_work_lanes({}) == 6
    with TemporaryDirectory() as d:
        reg = _reg(d)
        for i in range(6):
            reg.enrol(_job(d, f"w{i}"))
        reg.enrol(_job(d, "w0"))                       # re-enrolling a live lane: no growth
        reg.enrol(_job(d, "obs"), role="observer", watches="w1")   # observers do not count
        try:
            reg.enrol(_job(d, "w6"))
            raise AssertionError("a seventh live work lane was enrolled")
        except R.ParallelismBound as exc:
            assert "bound of 6" in str(exc)
        data = reg.load()
        data["jobs"]["w2"]["integrated"] = {"commit": "a" * 40,
                                            "recorded_utc": R.utc()}
        reg._save(data)
        assert reg.enrol(_job(d, "w6"))                # an integrated lane frees its slot
        reg.forget("w3")
        assert reg.enrol(_job(d, "w7"))                # so does a forgotten one


def test_the_bound_is_configurable_but_never_below_one():
    assert R.max_work_lanes({R.MAX_WORK_LANES_ENV: "4"}) == 4
    for bad in ("0", "-2", "many"):
        try:
            R.max_work_lanes({R.MAX_WORK_LANES_ENV: bad})
            raise AssertionError(bad)
        except ValueError:
            pass


def test_throughput_counts_integrated_work_in_the_window_not_agents():
    now = time.time()
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    new = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    data = {"jobs": {
        "a": {"role": "work", "integrated": {"commit": "x", "recorded_utc": new}},
        "b": {"role": "work", "integrated": {"commit": "y", "recorded_utc": old}},
        "c": {"role": "work", "integrated": None},
        "d": {"role": "work"},
        "o": {"role": "observer", "integrated": {"commit": "z", "recorded_utc": new}},
    }}
    t = R.throughput(data, now=now, env={})
    assert t["integrated"] == ["a"] and t["integrated_count"] == 1
    assert t["live_work_lanes"] == ["c", "d"] and t["bound"] == 6
    assert t["integrated_per_slot"] == round(1 / 6, 4)
    with TemporaryDirectory() as d:
        reg = _reg(d)
        reg.enrol(_job(d, "a"))
        assert reg.survey()["throughput"]["live_work_lanes"] == ["a"]


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
