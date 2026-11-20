"""W4-AGENTS W6 (F-239): the live shop's own text is checked at phone width.

The pre-launch preview measured the drafts; this measures what Etsy holds -- the live
announcement's phone opening and the live section titles -- from the stored getShop and
shop_sync readings. No reading (or a stale one) is UNKNOWN, never a pass; a failure is an
advisory row in the Storefront Director's review, never an automatic replacement.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_mobile_live_text.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.brand import storefront_preview as SP  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402
from brambleloop.store_foundation import director, live_state  # noqa: E402

_N = [0]
_TMP = tempfile.mkdtemp(prefix="w4mob_")
LONG = ("Welcome to our little studio of heirloom crochet patterns made for slow weekend "
        "evenings and cosy nurseries. New releases every month.")


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/m{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _readings(db, announcement, sections, *, age_days=0.0):
    at = time.time() - age_days * 86400
    shop = {"announcement": announcement, "title": "x"}
    etsy_ops.store_reading(db, live_state.SHOP_READING, {"observed_at": at, "shop": shop})
    etsy_ops.store_reading(db, live_state.SYNC_READING, {
        "observed_at": at, "shop": shop, "sections": [{"title": t} for t in sections]})


def _row(db):
    return next(r for r in director.review(db)["surfaces"] if r["surface"] == "mobile_live_text")


def test_no_reading_is_unknown_never_a_pass():
    db = _db()
    lt = SP.live_text(db)
    assert lt["ok"] is None and lt["announcement"]["state"] == "UNKNOWN"
    assert _row(db)["status"] == director.UNKNOWN


def test_a_fitting_live_announcement_and_short_sections_pass():
    db = _db()
    _readings(db, "Heirloom crochet patterns. New every month.", ["Home", "Baby"])
    lt = SP.live_text(db)
    assert lt["ok"] is True and lt["announcement"]["truncated"] is False
    assert lt["sections"]["titles"] == ["Home", "Baby"]
    assert _row(db)["status"] == director.OK


def test_a_live_opening_sentence_cut_on_a_phone_is_an_advisory_finding():
    db = _db()
    long_section = "Seasonal and Holiday Decorations For The Home"
    assert len(long_section) > SP.SECTION_LABEL_MAX
    _readings(db, LONG, ["Home", long_section])
    lt = SP.live_text(db)
    assert lt["ok"] is False and len(lt["problems"]) == 2, lt
    assert any("opening sentence" in p for p in lt["problems"])
    row = _row(db)
    assert row["status"] == "LIVE_FAILS_MOBILE" and row["actor"] == "ADVISORY"
    # advisory only: no proposal is drafted from it, and the live text is not replaced
    assert not [p for p in director.build_proposals(db) if p.get("surface") ==
                "mobile_live_text"]


def test_a_stale_reading_is_not_evidence():
    db = _db()
    _readings(db, LONG, ["Home"], age_days=30)
    lt = SP.live_text(db)
    assert lt["ok"] is None and lt["announcement"]["state"] == "STALE"
    assert lt["problems"] == []


def test_the_preview_reports_live_text_beside_the_simulation():
    db = _db()
    _readings(db, LONG, ["Home"])
    view = SP.preview(db)
    assert view["live_text"]["ok"] is False
    # the pre-launch verdict is the simulation's; live findings do not enter it
    assert not any(p.startswith("live ") for p in view["problems"])


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
