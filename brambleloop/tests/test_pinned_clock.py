"""tests/pinned_clock.py: the pinned clock pins, keeps ticking, and stays type-compatible."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import datetime as real_dt  # noqa: E402

REAL_DATETIME, REAL_DATE = real_dt.datetime, real_dt.date

import pinned_clock  # noqa: E402

AT = pinned_clock.install("2026-10-20T12:00:00+00:00")

from datetime import date, datetime, timezone  # noqa: E402  (the pinned classes)


def test_now_and_today_read_the_pinned_date_everywhere():
    from brambleloop.creative import prospecting

    assert AT == REAL_DATETIME(2026, 10, 20, 12, tzinfo=real_dt.timezone.utc)
    assert date.today() == REAL_DATE(2026, 10, 20)
    assert datetime.now(timezone.utc).date() == REAL_DATE(2026, 10, 20)
    assert prospecting.date.today() == REAL_DATE(2026, 10, 20)   # a module bound at import
    assert abs((datetime.now(timezone.utc) - AT).total_seconds()) < 60


def test_the_clock_keeps_ticking():
    a = datetime.now(timezone.utc)
    time.sleep(0.05)
    assert datetime.now(timezone.utc) > a


def test_real_instances_still_pass_isinstance_and_arithmetic_works():
    real = REAL_DATETIME(2026, 1, 1, tzinfo=real_dt.timezone.utc)
    assert isinstance(real, datetime) and isinstance(REAL_DATE(2026, 1, 1), date)
    assert isinstance(datetime.now(timezone.utc), REAL_DATETIME)
    assert (datetime.now(timezone.utc) - real).days > 200
    assert datetime.fromisoformat("2026-10-21T00:00:00+00:00") > AT


def test_a_naive_pin_is_refused():
    saved = dict(pinned_clock._STATE)
    pinned_clock._STATE.clear()
    try:
        pinned_clock.install("2026-10-20T12:00:00")
    except ValueError:
        pass
    else:
        raise AssertionError("a pin without a UTC offset was accepted")
    finally:
        pinned_clock._STATE.clear()
        pinned_clock._STATE.update(saved)


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
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
