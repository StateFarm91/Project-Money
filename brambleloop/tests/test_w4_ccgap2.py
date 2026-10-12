"""W4-CCGAP2: the CC gaps CC_GAP_c131f07.md §4 left open.

* FU-7: a non-OK card whose provider gave no reason now says which of its own items are not OK
  (read from the items, nothing invented) -- and still says the provider gave none.
* FU-5: Laura's "Needs you" count is the Approvals count (the same inbox, the same number), not
  the number of evidence lines (which capped at 10, added P0/P1 incidents, and counted "nothing
  is open" as 1). P0/P1 incidents are reported apart.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ccgap2.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccgap2_")


def test_reasonless_degraded_card_names_its_not_ok_items():
    from brambleloop.app.command_center import providers as P

    out = P.validate({"status": "DEGRADED", "items": [
        {"department": "seo", "status": "DEGRADED"}, {"name": "finance", "state": "UNKNOWN"},
        {"title": "store", "status": "OK"}, {"agent": "coo", "state": "sleeping"},
        {"key": "a", "status": "BLOCKED"}, {"key": "b", "status": "FAIL"}]}, "x")
    r = out["reason"]
    assert r.startswith(P.NO_REASON), r                           # still honest about the source
    assert "4 of 6 not OK: seo (DEGRADED), finance (UNKNOWN), a (BLOCKED), +1 more" in r, r
    none_bad = P.validate({"status": "BLOCKED", "items": [{"title": "x", "status": "OK"}]}, "y")
    assert "none of its 1 items is marked not OK" in none_bad["reason"]
    empty = P.validate({"status": "UNKNOWN", "items": []}, "z")
    assert empty["reason"] == f"{P.NO_REASON}; status UNKNOWN with no items reported"
    kept = P.validate({"status": "DEGRADED", "reason": "real reason", "items": []}, "w")
    assert kept["reason"] == "real reason"
    ok = P.validate({"status": "OK", "items": []}, "v")
    assert not ok.get("reason")


def test_agents_card_does_not_append_the_derived_placeholder_to_its_own_reasons():
    from brambleloop.app.command_center import providers as P, tabs
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/a.sqlite")
    db.create_all()
    items = [{"agent": "never_ran", "state": "sleeping"}]
    env = {"status": "OK", "items": items, "reason": P.derived_reason("DEGRADED", items)}
    out = tabs.agents_card(db, env)
    assert "1 agent(s) have no recorded job" in out["reason"], out["reason"]
    assert P.NO_REASON not in out["reason"], out["reason"]


def test_laura_needs_you_equals_the_approvals_count():
    from brambleloop.app.command_center import approvals
    from brambleloop.core.db import Database
    from brambleloop.laura.agency import talk

    db = Database(f"sqlite:///{_TMP}/l.sqlite")
    db.create_all()
    box = approvals.inbox(db)
    ov = talk.overview(db)
    nu = ov["needs_you"]
    assert nu["count"] == box["open"] == nu["decisions_open"], (nu["count"], box["open"])
    assert nu["same_as"].startswith("Approvals")
    assert isinstance(nu["p0_p1_incidents"], int)
    js = (ROOT / "src" / "brambleloop" / "app" / "command_center" / "static" / "js" / "views"
          / "laura.js").read_text(encoding="utf-8")
    assert "needs.p0_p1_incidents" in js


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
