"""IMAGE-BLOCKED: a run stopped only by the provider's DAILY ceiling resumes the next UTC day.

Production 2026-11-22: 3 of 6 blocked FLUX runs read "budget stop: paid provider gate refused
before sending (provider_daily_ceiling)". Nothing was billed (the gate refuses before any I/O)
and the ceiling resets at the next UTC day, but `restartable` treated every budget stop as final,
so those galleries could never be made. Every other budget stop stays final; spend, calls and
attempts are never reset; the ceiling still applies on the new day.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_image_daily_ceiling_redrive.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import image_production as IP  # noqa: E402
from brambleloop.visual.image_records import ImageProductionRun, ensure_tables  # noqa: E402

DAILY = ("budget stop: paid provider gate refused before sending (provider_daily_ceiling): "
         "the provider's daily ceiling is reached")
CAP = ("budget stop: paid provider gate refused before sending (provider_monthly_ceiling): "
       "the provider's monthly ceiling is reached")
GALLERY = "budget stop: per-gallery cap CA$2.00 reached"


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='idc_')}/idc.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    ensure_tables(db)
    return db


def _blocked(db, slug, reason, *, when):
    key = IP.run_key(slug, "1.0.0", f"{slug}-release")
    with db.session() as s:
        s.add(ImageProductionRun(run_key=key, slug=slug, version="1.0.0",
                                 release=f"{slug}-release", listing=slug,
                                 stage="product_generation", status="blocked",
                                 blocked_reason=reason, stages={}, updated_at=when,
                                 attempts_exhausted=True))
    return key


def _follow(calls):
    def follow(inputs, key, *, session=None):
        calls.append((inputs, key))
        return object()
    return follow


YESTERDAY = datetime.now(timezone.utc) - timedelta(days=1)
NOW = datetime.now(timezone.utc)


def test_daily_ceiling_stop_waits_today_and_restarts_once_next_day():
    db = _db()
    today_key = _blocked(db, "coaster-a", DAILY, when=NOW)
    old_key = _blocked(db, "coaster-b", DAILY, when=YESTERDAY)
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert [r["run_key"] for r in out["restarted"]] == [old_key], out
    assert any(w["run_key"] == today_key for w in out["waiting"]), out
    assert len(calls) == 1, calls
    run = IP.get_run(db, old_key)
    assert run["state"] != "blocked", run
    # Spend and calls are never reset by the restart.
    assert run["generation_calls"] == 0 and run["spent_cad"] == 0.0


def test_other_budget_stops_stay_final():
    db = _db()
    for slug, reason in (("basket-m", CAP), ("basket-g", GALLERY)):
        key = _blocked(db, slug, reason, when=YESTERDAY)
        got = IP.restartable(db, key)
        assert got["restartable"] is False and "final" in got["why"], (slug, got)
    calls = []
    out = IP.redrive_capability_blocked(db, follow=_follow(calls))
    assert out["restarted"] == [] and calls == [], out


def test_daily_ceiling_reset_reads_the_utc_day():
    assert IP.daily_ceiling_reset({"blocked_reason": DAILY,
                                   "updated_at": YESTERDAY.isoformat()})
    assert not IP.daily_ceiling_reset({"blocked_reason": DAILY, "updated_at": NOW.isoformat()})
    assert not IP.daily_ceiling_reset({"blocked_reason": CAP,
                                       "updated_at": YESTERDAY.isoformat()})
    assert not IP.daily_ceiling_reset({"blocked_reason": DAILY, "updated_at": None})


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
