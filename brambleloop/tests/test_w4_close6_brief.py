"""W4-CLOSE6: F-666 Overnight Brief.

  F-666  "'While you were away' shows autonomous hours, tasks/experiments, products
          advanced/rejected, image candidates, Etsy findings, compute/ad spend, sales/profit,
          incidents and decisions."

The Overnight handoff on HOME (F-896, GET /api/cc/brief/morning) carried what changed,
completed tasks, money spent by kind, incidents, discoveries, the queue and decisions. It did
not carry autonomous hours, experiments, products advanced or rejected, image candidates, Etsy
findings, or sales and profit. `command_center/brief.py` composes those from durable rows and
the handoff renders them. Unmeasured sales stay UNMEASURED. An unreadable source makes its
section UNKNOWN; it is never shown as 0.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close6_brief.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app.command_center import brief  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, CostEntry, Experiment, Incident, Job, JobStatus, OwnerAction,
)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
SINCE = NOW - timedelta(hours=10)
NAMED = ("autonomous_hours", "tasks_and_experiments", "products", "image_candidates",
         "etsy_findings", "spend", "sales_and_profit", "incidents", "decisions")


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/brief.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _seed(db):
    old = SINCE - timedelta(hours=5)
    with db.session() as s:
        for h in (1, 1, 3, 7):                      # three distinct active hours
            s.add(Job(agent="listing", job_type="listing.seo", status=JobStatus.DONE,
                      inputs={}, created_at=SINCE, run_after=SINCE,
                      finished_at=SINCE + timedelta(hours=h, minutes=5)))
        s.add(Job(agent="market_radar", job_type="intel.gallery_analysis",
                  status=JobStatus.DEAD, inputs={}, created_at=SINCE, run_after=SINCE,
                  finished_at=SINCE + timedelta(hours=2)))
        s.add(Job(agent="listing", job_type="listing.seo", status=JobStatus.DONE, inputs={},
                  created_at=old, run_after=old, finished_at=old))      # before the window
        s.add(Experiment(name="title-length", kind="ab", hypothesis="h", state="running",
                         created_at=SINCE + timedelta(hours=1)))
        for action in ("cir.drafted", "gate.certified", "creative.returned_to_development",
                       "creative.grid_tournament", "assets.gallery_frames", "mjs.findings",
                       "mjs.findings"):
            s.add(AuditLog(actor="x", action=action, at=SINCE + timedelta(hours=1)))
        s.add(AuditLog(actor="x", action="cir.drafted", at=old))         # before the window
        s.add(CostEntry(agent="market_radar", kind="llm", amount_cad=0.50,
                        at=SINCE + timedelta(hours=1)))
        s.add(CostEntry(agent="ads", kind="ads", amount_cad=2.00,
                        at=SINCE + timedelta(hours=2)))
        s.add(CostEntry(agent="ads", kind="ads", amount_cad=9.00, at=old))
        s.add(Incident(severity="P2", signature="x", summary="dead letter: gallery timeout",
                       halts_publication=False, at=SINCE + timedelta(hours=2)))
        s.add(OwnerAction(requirement_key="k", action="Record the Etsy Ads eligibility",
                          reason="r", max_cost_cad=0, minutes=2, consequence_of_delay="c",
                          blocks="b", at=SINCE + timedelta(hours=3)))


def test_every_named_item_is_a_section_read_from_its_rows():
    db = _db()
    _seed(db)
    b = brief.brief(db, since=SINCE, now=NOW)
    sec = b["sections"]
    assert set(NAMED) <= set(sec), sorted(sec)
    assert all(sec[k]["status"] == brief.MEASURED and sec[k]["sources"] for k in NAMED), sec
    assert sec["autonomous_hours"]["active_hours"] == 3
    t = sec["tasks_and_experiments"]
    assert (t["completed"], t["dead"]) == (4, 1), t
    assert t["experiments_started"][0]["name"] == "title-length"
    assert sec["products"]["advanced"] == {"cir.drafted": 1, "gate.certified": 1}
    assert sec["products"]["rejected"] == {"creative.returned_to_development": 1}
    assert sec["image_candidates"]["events"] == {"creative.grid_tournament": 1,
                                                 "assets.gallery_frames": 1}
    assert sec["etsy_findings"]["events"] == {"mjs.findings": 2}
    sp = sec["spend"]
    assert (sp["compute_cad"], sp["ads_cad"]) == (0.5, 2.0), sp   # the old CA$9 is outside
    assert sec["incidents"]["opened"] == 1 and sec["incidents"]["still_open"] == 1
    d = sec["decisions"]
    assert d["new_for_you"][0]["source"].startswith("owner_actions:") and d["waiting_on_you"] == 1
    assert b["unknown"] == []


def test_unmeasured_sales_are_never_zero_and_an_unreadable_source_is_unknown():
    db = _db()
    b = brief.brief(db, since=SINCE, now=NOW)
    rev = b["sections"]["sales_and_profit"]["revenue"]
    assert rev["state"] != "MEASURED" and rev.get("value") in (None,), rev
    assert b["sections"]["sales_and_profit"]["profit"].startswith("UNMEASURED")
    from brambleloop.app.command_center import readers

    with patch.object(readers, "revenue", side_effect=RuntimeError("ledger down")):
        b = brief.brief(db, since=SINCE, now=NOW)
    s = b["sections"]["sales_and_profit"]
    assert s["status"] == brief.UNKNOWN and "RuntimeError" in s["reason"], s
    assert b["unknown"] == ["sales_and_profit"]
    assert b["sections"]["spend"]["status"] == brief.MEASURED, "one failure blanks nothing else"


def test_the_overnight_handoff_on_home_carries_every_named_item():
    db = _db()
    _seed(db)
    from brambleloop.app.command_center import tabs

    mb = tabs.morning_brief(db, hours=24)
    sec = mb["sections"]
    # F-896 already carried these; W4-CLOSE6 adds the rest of F-666's list.
    for k in ("what_changed", "completed", "money_spent", "incidents", "decisions_needed",
              "autonomous_hours", "experiments", "products_moved", "image_candidates",
              "etsy_findings", "sales_and_profit"):
        assert k in sec and sec[k]["status"] in ("OK", "BLOCKED", "DEGRADED"), (k, sec.get(k))
        assert sec[k]["sources"], k
    moved = {(i["direction"], i["action"]) for i in sec["products_moved"]["items"]}
    assert ("rejected", "creative.returned_to_development") in moved, moved
    sales = {i["label"]: i for i in sec["sales_and_profit"]["items"]}
    assert sales["revenue"]["state"] != "MEASURED" and sales["profit"]["state"] == "UNMEASURED"
    view = (ROOT / "src/brambleloop/app/command_center/static/js/views/home.js").read_text()
    for k in ("autonomous_hours", "experiments", "products_moved", "image_candidates",
              "etsy_findings", "sales_and_profit"):
        assert f'["{k}",' in view, f"the handoff card does not render {k}"


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 3, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
