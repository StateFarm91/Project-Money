"""The bounded waiter: one per job, a wall-time bound, a duration watchdog, idle accounting.

F-334 / F-337 / F-340 / F-344. Driven with an injected clock, sleep and process table so a
forty-five-minute bound is exercised in milliseconds, against a real registry file and real logs.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

OPS = Path(__file__).resolve().parents[2] / "ops"
sys.path.insert(0, str(OPS))

import board as B  # noqa: E402
import registry as R  # noqa: E402
import waiter as W  # noqa: E402

HOST = {"boot_id": "same-host", "btime": 1, "pid1_start": 1}
FINISHED = re.compile(r"FINISHED AT (\S+)")
MARKER = "bash run_tests.sh --fake-marker"


class World:
    """A registry, a log, a process table and a clock that only moves when somebody sleeps."""

    def __init__(self, max_waiters: int = W.MAX_WAITERS):
        self.tmp = Path(tempfile.mkdtemp(prefix="waiter-"))
        self.now = time.time()
        self.sleeps: list[float] = []
        self.on_sleep = None
        self.table = [(os.getpid() + 54321, MARKER)]
        self.reg = R.Registry(self.tmp / "JOBS.json", epoch=lambda: dict(HOST),
                              git=lambda *a: (1, ""))
        self.w = W.Waiter(self.reg, self.tmp / "state", clock=lambda: self.now,
                          sleep=self._sleep, table=self.table, max_waiters=max_waiters)

    def _sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s
        if self.on_sleep:
            self.on_sleep(self)

    def enrol(self, name: str, *, lane: str = "suite", enrolled_ago_s: float = 0.0) -> Path:
        log = self.tmp / f"{name}.log"
        log.write_text("RUN STARTED\n")
        self.reg.enrol(B.Job(name=name, log=log, marker=MARKER, finished=FINISHED), lane=lane)
        if enrolled_ago_s:
            data = json.loads(self.reg.path.read_text())
            data["jobs"][name]["enrolled_utc"] = W._utc(self.now - enrolled_ago_s)
            self.reg.path.write_text(json.dumps(data))
        return log

    def finish(self, log: Path, *, ago_s: float = 0.0, code: int = 0) -> None:
        log.write_text(log.read_text() + f"TOTAL PASSING: 5 ; suites failing: {code}\n"
                       f"FINISHED AT {self.now - ago_s:.0f}\nEXIT {code}\n")
        self.table.clear()


def test_a_second_wait_for_the_same_job_attaches_instead_of_starting_a_second_waiter():
    world = World()
    world.enrol("suite-a")
    ok, lease, _ = world.w._acquire("suite-a", world.now + 60)     # a live waiter: this process
    assert ok and lease["pid"] == os.getpid()
    out = world.w.wait("suite-a", max_wall_s=60, poll_s=5)
    assert out["outcome"] == W.ATTACHED, out
    assert out["waiter"]["pid"] == os.getpid() and out["row"]["state"] == R.RUNNING
    assert world.sleeps == [], "an attached request polled anyway"
    assert len(list((world.tmp / "state" / "leases").glob("*.lease"))) == 1


def test_a_duplicate_lease_left_by_a_dead_waiter_is_detected_and_taken_over():
    world = World()
    log = world.enrol("suite-b")
    dead = subprocess.Popen(["true"])
    dead.wait()
    world.w._lease_path("suite-b").write_text(json.dumps(
        {"job": "suite-b", "pid": dead.pid, "pid_start": "1", "started_utc": "earlier"}))
    world.on_sleep = lambda wd: wd.finish(log)
    out = world.w.wait("suite-b", max_wall_s=600, poll_s=5)
    assert out["outcome"] == W.COMPLETED, out
    assert out["took_over_stale_waiter"] and str(dead.pid) in out["took_over_stale_waiter"]
    assert not world.w._lease_path("suite-b").exists(), "the lease outlived the wait"


def test_the_wall_time_bound_stops_observing_and_returns_the_registry_diagnosis():
    world = World()
    world.enrol("hung")
    out = world.w.wait("hung", max_wall_s=120, poll_s=15)
    assert out["outcome"] == W.BREACH, out
    assert out["waited_s"] >= 120 and sum(world.sleeps) <= 120 + 1e-6
    assert len(world.sleeps) <= 120 / 15 + 1, "polled past the bound"
    assert out["row"]["state"] == R.RUNNING and "registry" in out["why"]
    assert not world.w._lease_path("hung").exists()


def test_at_the_observer_cap_no_new_waiter_is_started():
    world = World(max_waiters=1)
    world.enrol("one")
    world.enrol("two")
    assert world.w._acquire("one", world.now + 60)[0]
    out = world.w.wait("two", max_wall_s=60, poll_s=5)
    assert out["outcome"] == W.OBSERVER_BOUND and len(out["live_waiters"]) == 1
    assert world.sleeps == [] and not world.w._lease_path("two").exists()


def test_an_unenrolled_job_is_not_waited_on():
    world = World()
    assert world.w.wait("never", max_wall_s=60)["outcome"] == W.UNENROLLED
    assert world.sleeps == []


def test_a_completion_records_its_duration_once_per_run_from_the_jobs_own_stamps():
    world = World()
    log = world.enrol("suite-c", enrolled_ago_s=300)
    world.finish(log, ago_s=100)                 # ran 200 s, finished 100 s ago
    out = world.w.wait("suite-c", max_wall_s=60)
    assert out["outcome"] == W.COMPLETED
    [rec] = world.w._lines("durations.jsonl")
    assert rec["op_class"] == "suite" and abs(rec["duration_s"] - 200) <= 2, rec
    world.w.wait("suite-c", max_wall_s=60)
    assert len(world.w._lines("durations.jsonl")) == 1, "the same run was recorded twice"


def test_the_watchdog_needs_history_then_fires_at_three_times_the_rolling_median():
    world = World()
    assert world.w.watchdog("suite", 10_000)["fired"] is False, "fired with no history"
    for i in range(W.MIN_HISTORY):
        world.w.record_duration("suite", f"j{i}", f"j{i}@x", 100.0, W.COMPLETED)
    assert world.w.normal("suite")["median_s"] == 100.0
    assert world.w.watchdog("suite", 299)["fired"] is False
    assert world.w.watchdog("suite", 301)["fired"] is True


def test_when_the_watchdog_fires_the_waiter_verifies_authoritative_state_before_waiting_on():
    world = World()
    for i in range(W.MIN_HISTORY):
        world.w.record_duration("suite", f"j{i}", f"j{i}@x", 100.0, W.COMPLETED)
    world.enrol("slow", enrolled_ago_s=1000)     # 10x the normal
    world.on_sleep = lambda wd: wd.table.clear()     # the process dies during the first poll
    out = world.w.wait("slow", max_wall_s=600, poll_s=5)
    [event] = out["watchdog"]
    assert event["fired"] and event["verified_state"] == R.RUNNING
    # The next poll finds no process and no sentinel: the waiter stops on the verdict.
    assert out["outcome"] == W.STOPPED and out["row"]["state"] == R.STALLED, out


def test_acknowledging_a_lane_accounts_its_idle_wall_clock_and_flags_a_reliability_incident():
    world = World()
    log = world.enrol("lane-x", lane="dept", enrolled_ago_s=3000)
    world.finish(log, ago_s=20 * 60)            # stood finished and unread for 20 minutes
    out = world.w.ack("lane-x")
    assert out["acknowledged"] is True
    assert abs(out["idle"]["idle_s"] - 1200) <= 2 and out["idle"]["incident"] is True
    rep = world.w.waste_report()
    assert rep["events"] == 1 and rep["reliability_incidents"], rep
    assert rep["spend_cad"].startswith("not applicable"), "idle time was mixed into spend"
    assert world.reg.recall("lane-x")["state"] == R.COMPLETE_REPORTED


def test_a_quick_acknowledgement_is_recorded_but_is_not_an_incident():
    world = World()
    log = world.enrol("lane-y", enrolled_ago_s=100)
    world.finish(log, ago_s=30)
    out = world.w.ack("lane-y")
    assert out["idle"]["incident"] is False and out["idle"]["idle_s"] <= 32
    assert world.w.waste_report()["reliability_incidents"] == []


def test_the_waiter_never_spawns_a_process():
    code = (OPS / "waiter.py").read_text().split('"""', 2)[2]
    for forbidden in ("subprocess", "Popen", "os.system", "os.fork", "os.exec", "pgrep"):
        assert forbidden not in code, f"waiter.py uses {forbidden}"


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
