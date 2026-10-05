"""The ops reliability-incident ledger and the registry ack that accounts idle time.

F-350: an observer defect is a ledger entry that closes only with a root cause, a prevention
test that exists, and a fix commit that exists; material delay found by the waiter opens one.
F-344: `ops/registry.py ack` (the heartbeat's step-3 command) accounts the lane's idle
wall-clock exactly as `waiter.py ack` does, and the board prints the incidents.

Against real files in a temp dir and this repository's own git history. No network.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT.parent / "ops"
sys.path.insert(0, str(OPS))

import board as B  # noqa: E402
import incidents as I  # noqa: E402
import registry as R  # noqa: E402
import waiter as W  # noqa: E402

HOST = {"boot_id": "same-host", "btime": 1, "pid1_start": 1}
MARKER = "bash run_tests.sh --fake-marker"
import re  # noqa: E402

FINISHED = re.compile(r"FINISHED AT (\S+)")
HEAD = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                      text=True).stdout.strip()
THIS_TEST = "tests/test_reliability_ledger.py::test_close_refuses_without_all_three_and_accepts_with_them"


def _ledger() -> I.Ledger:
    return I.Ledger(Path(tempfile.mkdtemp(prefix="relled-")) / "ledger.jsonl")


def test_open_is_idempotent_by_signature_and_kinds_are_closed():
    led = _ledger()
    a = led.open("hidden_completion", "suite-x:unread", "suite finished, nobody re-read it")
    b = led.open("hidden_completion", "suite-x:unread", "again")
    assert a["opened"] and not b["opened"] and b["restated"] and a["id"] == b["id"]
    assert len(led.open_entries()) == 1 and led.open_entries()[0]["reports"] == 2
    try:
        led.open("vibes", "s", "x")
    except I.Refused:
        pass
    else:
        raise AssertionError("an unknown kind was accepted")


def test_close_refuses_without_all_three_and_accepts_with_them():
    assert HEAD, "this test needs the repository's git history"
    led = _ledger()
    iid = led.open("false_progress", "lane-q:dead-but-green", "lane read as running")["id"]
    bad = [
        dict(root_cause="flaky", prevention_test=THIS_TEST, fix_commit=HEAD),
        dict(root_cause="the observer read a stale sidecar instead of the log",
             prevention_test="tests/test_nope.py::test_missing", fix_commit=HEAD),
        dict(root_cause="the observer read a stale sidecar instead of the log",
             prevention_test="tests/test_reliability_ledger.py::test_not_defined_here",
             fix_commit=HEAD),
        dict(root_cause="the observer read a stale sidecar instead of the log",
             prevention_test=THIS_TEST, fix_commit="deadbeefdeadbeefdeadbeef"),
        dict(root_cause="the observer read a stale sidecar instead of the log",
             prevention_test="not a test reference", fix_commit=HEAD),
    ]
    for kwargs in bad:
        try:
            led.close(iid, **kwargs)
        except I.Refused:
            continue
        raise AssertionError(f"closed without a valid {kwargs}")
    assert led.open_entries(), "a refused close closed it anyway"
    out = led.close(iid, root_cause="the observer read a stale sidecar instead of the log",
                    prevention_test=THIS_TEST, fix_commit=HEAD)
    assert out["closed"] and not led.open_entries()
    closed = led.entries()[0]
    assert closed["fix_commit"] == HEAD and closed["prevention_test"] == THIS_TEST


def _world():
    tmp = Path(tempfile.mkdtemp(prefix="relwait-"))
    now = [time.time()]
    table = [(os.getpid() + 54321, MARKER)]
    reg = R.Registry(tmp / "JOBS.json", epoch=lambda: dict(HOST), git=lambda *a: (1, ""))
    w = W.Waiter(reg, tmp / "state", clock=lambda: now[0], sleep=lambda s: None, table=table)
    return tmp, now, table, reg, w


def _enrol_finished(tmp, reg, now, table, name, ago_s):
    log = tmp / f"{name}.log"
    log.write_text("RUN STARTED\n")
    reg.enrol(B.Job(name=name, log=log, marker=MARKER, finished=FINISHED), lane="dept")
    log.write_text(log.read_text() + "TOTAL PASSING: 5 ; suites failing: 0\n"
                   f"FINISHED AT {now[0] - ago_s:.0f}\nEXIT 0\n")
    table.clear()


def test_material_delay_found_by_the_waiter_opens_a_ledger_entry():
    tmp, now, table, reg, w = _world()
    assert w.ledger.path.parent == tmp / "state", "a test waiter wrote the real ledger"
    _enrol_finished(tmp, reg, now, table, "lane-late", 20 * 60)
    out = w.ack("lane-late")
    assert out["idle"]["incident"] and out["idle"]["ledger"]["opened"]
    rows = w.ledger.open_entries()
    assert len(rows) == 1 and rows[0]["kind"] == "material_delay"
    assert "lane-late" in rows[0]["signature"]
    w.waste_report()
    assert len(w.ledger.open_entries()) == 1, "the waste report duplicated the entry"


def test_registry_ack_accounts_idle_time_through_the_waiter():
    tmp, now, table, reg, w = _world()
    _enrol_finished(tmp, reg, now, table, "lane-20", 20 * 60)
    out = R.ack_and_account(reg, "lane-20", waiter=w)
    assert out["acknowledged"] is True
    assert abs(out["idle"]["idle_s"] - 1200) <= 2 and out["idle"]["incident"] is True
    assert w.waste_report()["events"] == 1
    assert reg.recall("lane-20")["state"] == R.COMPLETE_REPORTED


def test_the_registry_cli_ack_goes_through_the_waiter():
    src = (OPS / "registry.py").read_text()
    cli = src[src.index("def _cli("):]
    assert "ack_and_account(reg, argv[2])" in cli
    assert "reg.acknowledge(argv[2])" not in cli, "the CLI ack bypasses idle accounting"


def test_the_board_prints_open_reliability_incidents_and_waste():
    tmp, now, table, reg, w = _world()
    _enrol_finished(tmp, reg, now, table, "lane-slow", 30 * 60)
    w.ack("lane-slow")
    lines = R.reliability_lines(ledger=w.ledger, waste=w.waste_report())
    text = "\n".join(lines)
    assert "RELIABILITY INCIDENT" in text and "lane-slow" in text
    assert "material-delay" in text
    assert R.reliability_lines(ledger=_ledger(), waste={"reliability_incidents": []}) == []
    lock_src = (OPS / "lock.py").read_text()
    assert "registry.reliability_lines()" in lock_src, "the lease print does not show them"


def test_the_ledger_cli_refuses_a_bare_close():
    env = dict(os.environ, RELIABILITY_LEDGER=str(Path(tempfile.mkdtemp()) / "l.jsonl"))
    subprocess.run([sys.executable, str(OPS / "incidents.py"), "open", "duplicate_work",
                    "two-sessions:same-lane", "two", "sessions", "ran", "it"],
                   env=env, check=True, capture_output=True)
    r = subprocess.run([sys.executable, str(OPS / "incidents.py"), "close", "1",
                        "--root-cause", "x", "--prevention-test", "y", "--fix-commit", "z"],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 2 and "refused" in r.stderr
    r = subprocess.run([sys.executable, str(OPS / "incidents.py"), "list"], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 1 and json.loads(r.stdout)[0]["status"] == "open"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                with redirect_stdout(io.StringIO()):
                    fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
