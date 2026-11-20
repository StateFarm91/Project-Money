"""W4-AGENTS2 batch 1: departments report what they produced, quality-reviewed, to Laura.

The department review (`autonomy.department_review` -> `kpis.compute` -> `kpi_snapshot` in
company memory, which Laura's executive loop reads) now carries each department's evidence:
values from the rows and readings its own jobs wrote, each citing its source, STALE when old,
UNKNOWN (never 0) when nothing recorded it, and REJECTED when it fails the quality review.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_department_evidence.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import charters, memory  # noqa: E402
from brambleloop.autonomy import department_evidence as DE  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import OperatingReading, Phase  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import JobContext, handlers  # noqa: E402

import brambleloop.autonomy.handlers  # noqa: E402,F401

_N = [0]
_TMP = tempfile.mkdtemp(prefix="w4de_")
NAMED = {"Storefront", "Growth", "Marketing", "Product Development", "Visual Production",
         "Market Intelligence", "Finance", "Customer Experience"}


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/e{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_every_named_department_has_an_evidence_reader_on_a_real_charter():
    covered = {n for names in DE.NAMED.values() for n in names}
    assert covered == NAMED
    assert set(DE.NAMED) == set(DE.READERS)
    assert set(DE.READERS) <= set(charters.BY_KEY)


def test_nothing_recorded_is_unknown_never_zero_and_every_item_passes_review():
    db = _db()
    for key in DE.READERS:
        ev = DE.collect(db, key)
        assert ev["items"], key
        assert ev["rejected"] == [], (key, ev["rejected"])
        for name, it in ev["items"].items():
            if it["status"] == DE.UNKNOWN:
                assert it["value"] is None, (key, name)
            else:
                assert it["sources"], (key, name)
    sf = DE.collect(db, "store_commerce")["items"]
    assert sf["agent_gaps"]["status"] == DE.UNKNOWN and sf["agent_gaps"]["value"] is None
    cx = DE.collect(db, "support")["items"]
    assert all(i["status"] == DE.UNKNOWN for i in cx.values())   # no case: not "0 open"


def test_a_reading_is_cited_and_goes_stale():
    db = _db()
    with db.session() as s:
        s.add(OperatingReading(kind="storefront.review", period_key="d1",
                               at=datetime.now(timezone.utc) - timedelta(days=5),
                               payload={"surfaces": [{"status": "OK"}, {"status": "UNKNOWN"}],
                                        "agent_gaps": ["announcement"], "owner_gaps": [],
                                        "unknown": ["sections"]}))
    sf = DE.collect(db, "store_commerce")["items"]
    assert sf["agent_gaps"]["value"] == 1 and sf["agent_gaps"]["status"] == DE.STALE
    assert sf["agent_gaps"]["sources"][0].startswith("operating_readings:")
    with db.session() as s:
        s.add(OperatingReading(kind="storefront.review", period_key="d2",
                               at=datetime.now(timezone.utc),
                               payload={"surfaces": [{"status": "OK"}], "agent_gaps": [],
                                        "owner_gaps": [], "unknown": []}))
    sf = DE.collect(db, "store_commerce")["items"]
    assert sf["agent_gaps"]["status"] == DE.OK and sf["surfaces_ok"]["value"] == 1


def test_the_quality_review_rejects_unsourced_unknown_valued_and_negative_items():
    out = DE.review({
        "a": {"value": 3, "status": DE.OK, "sources": []},
        "b": {"value": 0, "status": DE.UNKNOWN, "sources": []},
        "c": {"value": None, "status": DE.OK, "sources": ["x"]},
        "d": {"value": -1, "status": DE.OK, "sources": ["x"]},
        "e": {"value": 2, "status": DE.OK, "sources": ["x"]},
        "f": {"value": None, "status": DE.UNKNOWN, "sources": []},
    })
    assert {r["key"] for r in out["rejected"]} == {"a", "b", "c", "d"}
    assert out["passed"] == 2 and out["items"]["a"]["status"] == DE.REJECTED


def test_the_department_review_reports_the_evidence_to_lauras_snapshot():
    db = _db()
    job = JobQueue(db).enqueue("coo", "autonomy.department_review",
                               {"department": "store_commerce"})
    handlers.get("autonomy.department_review")(JobContext(
        job=job, db=db, queue=JobQueue(db), registry=Registry(db), phase=Phase.SHADOW))
    snaps = memory.recall(db, kind="kpi_snapshot", department="store_commerce", limit=1)
    assert snaps, "the review wrote a snapshot"
    ev = snaps[0]["body"]["evidence"]
    assert ev["departments"] == ["Storefront"] and "agent_gaps" in ev["items"]
    # a charter outside the eight carries no evidence block rather than a fake one
    from brambleloop.autonomy import kpis

    assert kpis.compute(db, "platform")["evidence"] is None
    with db.session() as s:
        assert s.scalar(select(OperatingReading)) is None        # it reads; it writes none


def test_no_cost_row_is_unknown_spend_and_the_morning_brief_carries_the_evidence():
    from datetime import datetime, timezone

    from brambleloop.autonomy.handlers import build_brief

    db = _db()
    fin = DE.collect(db, "finance")["items"]
    assert fin["recorded_spend_30d_cad"]["status"] == DE.UNKNOWN
    assert fin["recorded_spend_30d_cad"]["value"] is None          # never CA$0.00
    job = JobQueue(db).enqueue("coo", "autonomy.department_review", {"department": "finance"})
    handlers.get("autonomy.department_review")(JobContext(
        job=job, db=db, queue=JobQueue(db), registry=Registry(db), phase=Phase.SHADOW))
    brief = build_brief(db, now=datetime.now(timezone.utc))
    rows = {r["department"]: r for r in brief["department_evidence"]}
    assert rows["finance"]["named"] == ["Finance"]
    assert "recorded_spend_30d_cad" in rows["finance"]["unknown"]
    assert rows["finance"]["rejected"] == []


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
