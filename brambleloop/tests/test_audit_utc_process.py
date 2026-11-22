"""F-12: the process time zone is UTC whatever the host's TZ says.

Daily cadence keys, caps, idempotency keys and seasonal windows call ``date.today()``, the
process-local date. Importing ``brambleloop`` must pin the process zone to UTC so that date
cannot drift from the UTC timestamps stored beside it. Each check runs in a fresh subprocess
whose host zone is UTC+14 and then UTC-11: at any instant at least one of the two has a local
date different from UTC's, and both have a non-zero ``time.timezone``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_PROBE = (
    "import datetime, time\n"
    "import brambleloop\n"
    "today = datetime.date.today()\n"
    "utc = datetime.datetime.now(datetime.timezone.utc).date()\n"
    "assert today == utc, (str(today), str(utc))\n"
    "assert time.timezone == 0, time.timezone\n"
    "print('PROBE_OK')\n"
)


def _probe(zone: str) -> None:
    env = {**os.environ, "TZ": zone, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run([sys.executable, "-c", _PROBE], env=env, cwd=str(ROOT),
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "PROBE_OK" in r.stdout, (zone, r.stdout, r.stderr[-800:])


def test_import_pins_utc_under_a_utc_plus_14_host():
    _probe("Pacific/Kiritimati")


def test_import_pins_utc_under_a_utc_minus_11_host():
    _probe("Pacific/Pago_Pago")


def test_the_container_image_sets_tz_utc():
    lines = [ln.strip() for ln in (ROOT / "Dockerfile").read_text().splitlines()]
    assert any(ln.startswith("ENV ") and "TZ=UTC" in ln.split() for ln in lines), \
        "Dockerfile must set ENV TZ=UTC"


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
