"""W4-C12 wiring: Search Visibility aging, boost-window captures and the dashboard task harvest
run on the schedule through the normal path -- cadence, registry, charter, WORK_KEYS, action
class, swarm band and the generated autonomy map -- and each handler is read-only or
record-only. Fixtures only; no Etsy call, CA$0."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import DEFAULT_AGENTS, Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Customer, Incident, Order, OwnerAction, Phase  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import etsy_ops, pipeline  # noqa: E402,F401
from brambleloop.runtime import c12_ops as W  # noqa: E402
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="w4c12w_")
_N = [0]
JOBS = ((W.AGING, "listing", "search_visibility_aging"),
        (W.CAPTURES, "listing", "window_captures"),
        (W.HARVEST, "orchestrator", "dashboard_harvest"))


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/w{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _run(db, agent, jt):
    job = JobQueue(db).enqueue(agent, jt, {})
    Registry(db).authorize(agent, jt)
    return handlers.get(jt)(JobContext(job=job, db=db, queue=JobQueue(db),
                                       registry=Registry(db), phase=Phase.SHADOW))


def test_each_job_is_wired_through_the_normal_path():
    from brambleloop.authority import classes
    from brambleloop.autonomy import charters, map as amap
    from brambleloop.runtime.pipeline import WORK_KEYS
    from brambleloop.swarm import orchestrate

    committed = json.loads((ROOT / "src/brambleloop/autonomy/autonomy_map.json").read_text())
    live = amap.build()
    assert committed["counts"] == live["counts"], (committed["counts"], live["counts"])
    text = json.dumps(committed)
    assert JOBS
    for jt, agent, name in JOBS:
        assert (name, agent, jt, 86400) in CADENCES, jt
        assert jt in next(a for a in DEFAULT_AGENTS if a["name"] == agent)["allowed_job_types"]
        assert classes.classify(jt) == classes.ActionClass.OBSERVE and not classes.is_gated(jt)
        assert WORK_KEYS[jt] == ("work_done",)
        assert orchestrate.JOB_BANDS[jt] == "housekeeping"
        assert charters.department_of(jt) == "store_commerce", (jt, charters.department_of(jt))
        assert jt in text, f"{jt} missing from the committed autonomy map"
        assert handlers.get(jt) is not None


def test_search_visibility_aging_records_and_opens_one_incident():
    from brambleloop.commerce import search_visibility as sv

    db = _db()
    old = datetime.now(timezone.utc) - timedelta(days=20)
    sv.record_reading(db, observed_at=old, complete=True, require_live=False,
                      items=[{"scope": "shop", "category": "shop_policies"}])
    item = sv.items(db)[0]
    sv.mark_remediated(db, item["id"], ref="fix:policies", at=old + timedelta(days=1))
    sv.record_reading(db, observed_at=old + timedelta(days=10), complete=True,
                      require_live=False,
                      items=[{"scope": "shop", "category": "shop_policies"}])
    out = _run(db, "listing", W.AGING)
    assert out["overdue"] == 1 and len(out["incidents_opened"]) == 1 and out["work_done"] >= 1
    again = _run(db, "listing", W.AGING)
    assert again["incidents_opened"] == []                    # de-duplicated
    with db.session() as s:
        assert len(list(s.scalars(select(Incident)))) == 1


def test_window_captures_reads_the_lifecycle_trail():
    from brambleloop.commerce import listing_lifecycle as lc

    db = _db()
    assert _run(db, "listing", W.CAPTURES) == {"listings": 0, "due": [], "work_done": 0}
    lc.record(db, action="activate", listing_id="4401", actor="owner",
              evidence="etsy listing page", result="verified")
    out = _run(db, "listing", W.CAPTURES)
    assert out["listings"] == 1 and [d["day"] for d in out["due"]] == [0]


def test_dashboard_harvest_turns_stored_orders_into_one_owner_task():
    db = _db()
    with db.session() as s:
        c = Customer(customer_ref="buyer-1")
        s.add(c)
        s.flush()
        s.add(Order(customer_id=c.id, external_ref="R1", product_slug="moss",
                    at=datetime.now(timezone.utc), revenue_cad=9.5, refunded=False,
                    detail={"receipt_status": "paid"}))
    out = _run(db, "orchestrator", W.HARVEST)
    assert len(out["opened"]) == 1 and out["opened"][0].endswith("order:R1")
    assert "messages_needing_response" in out["unavailable"]
    assert _run(db, "orchestrator", W.HARVEST)["opened"] == []          # one task, not two
    with db.session() as s:
        assert len([a for a in s.scalars(select(OwnerAction))
                    if a.requirement_key.endswith("order:R1")]) == 1


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
