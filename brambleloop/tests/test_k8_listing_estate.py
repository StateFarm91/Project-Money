"""Wave-3 K8: the listing estate, daily delivery verification, renewals, lifecycle, rollback.

Rows: F-553 (estate manager), F-544 (image/file drift), F-559 (daily file re-read on live
listings), F-250 (recency non-gaming: the renewal rule now has a caller), F-545 (one listing
lifecycle trail), F-518 (a defined rollback with stop conditions for a live listing field).

Everything Etsy-shaped runs against `tests/fake_etsy.py` through the real
`etsy.listing_census` handler (fixtures shared with tests/test_etsy_readback_observe.py).
No request leaves the machine and nothing here establishes how Etsy itself behaves.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_k8_listing_estate.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from tests import test_etsy_readback_observe as rb  # noqa: E402
from brambleloop.commerce import (listing_estate, listing_lifecycle,  # noqa: E402
                                  listing_rollback)
from brambleloop.core.models import AuditLog, Incident  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402
from tests.fake_etsy import FakeEtsy  # noqa: E402


def _census(db, fake):
    with rb._Patched(fake):
        return rb._run(db, "etsy.listing_census")


# ---- F-553 / F-559: the estate row and the daily file re-read ----------------------------


def test_census_estate_rows_carry_files_images_properties_expiry_and_fee():
    db = rb._db()
    with FakeEtsy() as fake:
        _p, lid = rb._published(db, fake)
        job = _census(db, fake)
    assert job.outputs["delivery"] == {lid: listing_estate.DELIVERY_VERIFIED}, job.outputs
    assert not job.outputs["field_drift"], job.outputs
    reading = etsy_ops.latest_reading(db, etsy_ops.CENSUS_READING)
    rows = [r for r in reading["estate"] if r["listing_id"] == lid]
    assert rows, reading["estate"]
    row = rows[0]
    assert row["ours"] and row["slug"] and row["intended_state"] == "draft"
    assert row["files"] and all(f["filename"] for f in row["files"])
    assert row["images"]["read"] and row["images"]["count"] >= 1
    assert row["delivery"] == listing_estate.DELIVERY_VERIFIED
    assert row["renewal"]["mode"] in ("auto_renew_on_expiry", "manual", "unknown")
    assert row["renewal_fee"]["basis"] in ("modelled", "unknown")
    assert "properties" in row and "post_purchase_availability" not in row
    assert reading["renewals"]["rule"] == "publish.release_gates.renewal_decision"
    life = etsy_ops.latest_reading(db, etsy_ops.LIFECYCLE_READING)
    assert life["by_action"].get("create", 0) >= 1 and "test_listings" in life


def test_a_customer_file_removed_on_etsy_is_delivery_failure_and_drift_never_overwritten():
    db = rb._db()
    with FakeEtsy() as fake:
        _p, lid = rb._published(db, fake)
        fake.files[lid] = fake.files[lid][1:]          # one terminology variant vanished
        mark = len(fake.requests)
        job = _census(db, fake)
        writes = [r for r in fake.requests[mark:] if r["method"] != "GET"]
    assert job.outputs["delivery"][lid] == listing_estate.DELIVERY_FAILED, job.outputs
    assert job.outputs["field_drift"] == [lid] and not writes
    incident = rb._open_incidents(db, etsy_ops.LISTING_DRIFT)[0]
    assert incident.halts_publication and "files:" in " ".join(incident.detail["drift"])
    assert incident.detail["rollback_plan"] is not None
    events = [e for e in listing_lifecycle.trail(db, lid) if e["action"] == "observe_drift"]
    assert len(events) == 1 and events[0]["actor"] == "etsy.listing_census", events


def test_an_image_removed_on_etsy_is_drift():
    db = rb._db()
    with FakeEtsy() as fake:
        _p, lid = rb._published(db, fake)
        fake.images[lid] = fake.images[lid][:-1]
        job = _census(db, fake)
    assert job.outputs["field_drift"] == [lid], job.outputs
    drift = rb._open_incidents(db, etsy_ops.LISTING_DRIFT)[0].detail["drift"]
    assert any(d.startswith("images:") for d in drift), drift


def test_an_unreadable_file_list_is_unverified_never_verified():
    class Client:
        def get_listing_files(self, lid):
            raise ConnectionError("network down")

    out = listing_estate.delivery_check(Client(), "1", [{"name": "a.pdf", "size": 3}])
    assert out["status"] == listing_estate.DELIVERY_UNVERIFIED
    none = listing_estate.delivery_check(Client(), "1", None)
    assert none["status"] == listing_estate.DELIVERY_UNVERIFIED and none["problems"]


# ---- F-518: the rollback plan and its stop conditions -----------------------------------


def test_a_title_edited_on_etsy_gets_a_defined_rollback_plan_that_is_not_executed():
    db = rb._db()
    with FakeEtsy() as fake:
        _p, lid = rb._published(db, fake)
        original = fake.listings[lid]["title"]
        fake.listings[lid]["title"] = "Somebody edited this by hand"
        _census(db, fake)
        assert fake.listings[lid]["title"] == "Somebody edited this by hand"
    plan = rb._open_incidents(db, etsy_ops.LISTING_DRIFT)[0].detail["rollback_plan"]
    assert plan["restore"] == {"title": original}, plan
    assert plan["executes_automatically"] is False and len(plan["stop_conditions"]) == 4
    assert plan["remote_fingerprint"]


class _FakeClient:
    def __init__(self, listing):
        self.listing = dict(listing)
        self.updates = []

    def get_listing(self, lid):
        return dict(self.listing)

    def update_listing(self, lid, fields, *, grant=None):
        self.updates.append(dict(fields))
        self.listing.update(fields)
        return dict(self.listing)


def _plan(remote):
    return listing_rollback.plan(listing_id="77", slug="s", version="1",
                                 certified={"title": "Certified", "tags": ["a", "b"],
                                            "price": 4.0},
                                 remote=remote)


def test_rollback_refuses_in_shadow_and_without_grant_and_records_each_refusal():
    db = rb._db()
    remote = {"title": "Edited", "tags": ["a", "b"], "price": 5.0}
    plan = _plan(remote)
    assert plan["restore"] == {"title": "Certified"}, plan
    assert any(s.startswith("price:") for s in plan["owner_steps"]), plan
    client = _FakeClient(remote)
    try:
        listing_rollback.execute(db, client, plan, grant=object())
        raise AssertionError("a shadow-phase rollback was sent")
    except listing_rollback.RollbackRefused as e:
        assert "shadow" in str(e)
    orig = listing_rollback._live_phase
    listing_rollback._live_phase = lambda db: "limited_production"
    try:
        try:
            listing_rollback.execute(db, client, plan, grant=None)
            raise AssertionError("a rollback without the owner's grant was sent")
        except listing_rollback.RollbackRefused as e:
            assert "grant" in str(e)
        client.listing["title"] = "Edited again"          # somebody changed it after the plan
        try:
            listing_rollback.execute(db, client, plan, grant=object())
            raise AssertionError("a stale plan overwrote a newer change")
        except listing_rollback.RollbackRefused as e:
            assert "changed again" in str(e)
    finally:
        listing_rollback._live_phase = orig
    assert not client.updates
    refusals = [e for e in listing_lifecycle.trail(db, "77") if e["action"] == "rollback"]
    assert len(refusals) == 3 and all(e["result"].startswith("refused") for e in refusals)


def test_rollback_with_every_condition_clear_restores_and_reads_back():
    db = rb._db()
    remote = {"title": "Edited", "tags": ["a", "b"], "price": 4.0}
    plan = _plan(remote)
    client = _FakeClient(remote)
    orig = listing_rollback._live_phase
    listing_rollback._live_phase = lambda db: "limited_production"
    try:
        out = listing_rollback.execute(db, client, plan, grant=object())
    finally:
        listing_rollback._live_phase = orig
    assert out["restored"] and client.updates == [{"title": "Certified"}]
    last = listing_lifecycle.trail(db, "77")[-1]
    assert last["result"] == "restored" and last["before"] == {"title": "Edited"}
    assert last["after"] == {"title": "Certified"}


# ---- F-250: renewals ----------------------------------------------------------------------


def test_renewal_rule_now_has_a_caller_recency_renewal_refused_expiry_proposed():
    now = time.time()
    day = 86400
    prev = [{"listing_id": "1", "ours": True, "state": "active", "ending_timestamp": now + 30 * day},
            {"listing_id": "2", "ours": True, "state": "active", "ending_timestamp": now + 30 * day},
            {"listing_id": "9", "ours": False, "state": "active", "ending_timestamp": now}]
    rows = [listing_estate.estate_row({"listing_id": "1", "state": "active",
                                       "ending_timestamp": now + 120 * day,
                                       "should_auto_renew": False}, {"slug": "a"}, now=now),
            listing_estate.estate_row({"listing_id": "2", "state": "active",
                                       "ending_timestamp": now + 120 * day}, {"slug": "b"},
                                      now=now),
            listing_estate.estate_row({"listing_id": "3", "state": "expired",
                                       "ending_timestamp": now - day}, {"slug": "c"}, now=now),
            listing_estate.estate_row({"listing_id": "4", "state": "active",
                                       "ending_timestamp": now + 5 * day,
                                       "should_auto_renew": True}, {"slug": "d"}, now=now),
            listing_estate.estate_row({"listing_id": "9", "state": "active",
                                       "ending_timestamp": now + 120 * day}, None, now=now)]
    out = listing_estate.renewal_review(prev, rows,
                                        material_changes={"2": "b: certified version 2"})
    assert [f["listing_id"] for f in out["refused_renewals"]] == ["1"], out
    assert "F-250" in out["refused_renewals"][0]["why"]
    assert [p["listing_id"] for p in out["proposals"]] == ["3"]
    assert out["proposals"][0]["allowed"] and out["proposals"][0]["executed"] is False
    assert [e["listing_id"] for e in out["expiring"]] == ["4"]
    assert rows[3]["renewal"]["mode"] == "auto_renew_on_expiry"


# ---- F-545: one trail -----------------------------------------------------------------------


def test_the_trail_unifies_publish_activation_and_test_listing_rows():
    db = rb._db()
    with FakeEtsy() as fake:
        _p, lid = rb._published(db, fake)
    with db.session() as s:
        s.add(AuditLog(actor="etsy_exercise", action="etsy.exercise_draft_created",
                       detail={"listing_id": "555"}))
        s.add(AuditLog(actor="etsy_exercise", action="etsy.exercise_draft_created",
                       detail={"listing_id": "556"}))
        s.add(AuditLog(actor="etsy_exercise", action="etsy.exercise_draft_removed",
                       detail={"listing_id": "555"}))
    events = listing_lifecycle.trail(db, lid)
    assert events and events[0]["action"] == "create" and events[0]["result"] == "verified"
    assert events[0]["after"]["files_sent"], events[0]
    tests = listing_lifecycle.test_listings(db)
    assert tests["created"] == 2 and tests["confirmed_deleted"] == 1
    assert tests["stranded"] == ["556"], tests
    try:
        listing_lifecycle.record(db, action="update", listing_id=lid, actor="x", evidence="")
        raise AssertionError("a lifecycle row without evidence was accepted")
    except listing_lifecycle.LifecycleRefused:
        pass
    assert listing_lifecycle.summary(db)["by_action"]["create"] >= 1


if __name__ == "__main__":
    fails = 0
    names = [n for n in list(globals()) if n.startswith("test_")]
    assert names
    for name in names:
        try:
            globals()[name]()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            import traceback

            fails += 1
            print("FAIL", name, repr(e)[:600])
            traceback.print_exc(limit=6)
    print(f"\n{len(names) - fails} passed, {fails} failed")
    sys.exit(1 if fails else 0)
