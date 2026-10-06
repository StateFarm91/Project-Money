"""Wave-3 K8: shop policy consistency, options registry, security posture, surface inventory,
policy violations, refund/cancellation root cause and the CX workspace.

Rows: F-537, F-585, F-592, F-514, F-568, F-535, F-689. The shop-side checks run through the
real `etsy.shop_snapshot` / `etsy.credential_health` handlers against `tests/fake_etsy.py`;
the CX side runs against a temp database seeded with synthetic orders and cases. No request
leaves the machine, nothing is sent to any buyer, and real Etsy transactions stay gated on
the owner's `transactions_r` re-authorisation -- these are fakes, labelled as such.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_k8_shop_cx.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from sqlalchemy import select  # noqa: E402

from tests import test_etsy_readback_observe as rb  # noqa: E402
from brambleloop.commerce import (cx_root_cause, orders_ingest,  # noqa: E402
                                  policy_consistency, policy_violations, shop_observations,
                                  shop_options, shop_package, shop_security,
                                  surface_inventory)
from brambleloop.core.models import (Customer, Incident, Order, OwnerAction,  # noqa: E402
                                     SupportCase)
from brambleloop.runtime import etsy_ops  # noqa: E402
from brambleloop.support import workspace  # noqa: E402
from tests.fake_etsy import FakeEtsy  # noqa: E402

NOW = datetime.now(timezone.utc)
SENTINEL = "zq-sentinel-buyer-words"


def _canonical_shop() -> dict:
    canon = policy_consistency.canonical()
    return {**rb.GOOD_SHOP, **canon}


def _incident(db, sig):
    with db.session() as s:
        row = s.scalar(select(Incident).where(Incident.signature == sig)
                       .order_by(Incident.id.desc()))
        if row is not None:
            s.expunge(row)
        return row


# ---- F-537 -------------------------------------------------------------------------------


def test_policy_text_matching_its_canonical_source_is_consistent():
    out = policy_consistency.check(_canonical_shop())
    assert out["fields"] and all(f["status"] == policy_consistency.MATCH
                                 for f in out["fields"]), out["fields"]
    assert not out["contradictions"]
    assert out["consistent"] is (not shop_package.check_package())
    assert set(out["facts"]) and all(v["owner"] for v in out["facts"].values())


def test_a_contradiction_in_live_text_is_named_against_its_fact_and_owner():
    shop = {**_canonical_shop(), "policy_refunds": "Returns accepted within 30 days.",
            "policy_shipping": "Ships within 3 business days with a tracking number."}
    out = policy_consistency.check(shop)
    facts = {c["fact"] for c in out["contradictions"]}
    assert {"digital_no_returns_but_fixes", "nothing_is_shipped"} <= facts, out
    assert out["consistent"] is False and "policy_refunds" in out["differs"]
    unread = policy_consistency.check(None)
    assert unread["consistent"] is None and all(
        f["status"] == policy_consistency.NOT_RETURNED for f in unread["fields"])


def test_the_shop_snapshot_opens_and_closes_the_policy_incident_on_readings():
    db = rb._db()
    with FakeEtsy(shop_body=dict(rb.GOOD_SHOP)) as fake:
        with rb._Patched(fake):
            job = rb._run(db, "etsy.shop_snapshot")
        assert job.outputs["policy_consistent"] is False, job.outputs
        row = _incident(db, f"{etsy_ops.SHOP_INCIDENTS}policy_inconsistent")
        assert row and not row.resolved and not row.halts_publication
        stored = etsy_ops.latest_reading(db, etsy_ops.SHOP_READING)
        assert stored["policy_consistency"]["fields"] and stored["options_registry"]["controls"]
        assert etsy_ops.latest_reading(db, etsy_ops.INVENTORY_READING)["items"]
        if not shop_package.check_package():
            fake.shop_body.update(policy_consistency.canonical())
            with rb._Patched(fake):
                job = rb._run(db, "etsy.shop_snapshot")
            assert job.outputs["policy_consistent"] is True, job.outputs
            assert _incident(db, f"{etsy_ops.SHOP_INCIDENTS}policy_inconsistent").resolved


# ---- F-585 -------------------------------------------------------------------------------


def test_options_registry_judges_api_controls_and_reports_browser_only_as_unobserved():
    out = shop_options.evaluate({**rb.GOOD_SHOP, "languages": ["en-US"],
                                 "shop_location_country_iso": "CA",
                                 "shop_name": "Brambleloop"})
    by = {c["key"]: c for c in out["controls"]}
    assert by["vacation_mode"]["status"] == "OK" and by["shop_currency"]["status"] == "OK"
    assert by["close_shop"]["status"] == "UNOBSERVED" and by["close_shop"]["channel"] == \
        "browser_only"
    assert all(c["authority"] == "owner" and c["consequence"] for c in out["controls"])
    drift = shop_options.evaluate({**rb.GOOD_SHOP, "is_vacation": True,
                                   "shop_name": "Other"}, {"shop_name": "Brambleloop"})
    assert "vacation_mode" in drift["drift"] and "shop_name" in drift["drift"], drift
    obs = {"values": {"controls": {"close_shop": "open"},
                      "labels": ["Close your shop", "Brand new Etsy toggle"]}}
    ui = shop_options.evaluate(rb.GOOD_SHOP, None, obs)
    assert "options_page_changed" in ui["drift"] and ui["ui_change"]["new_labels"] == \
        ["Brand new Etsy toggle"]


# ---- shop observations + F-568 ---------------------------------------------------------


def test_an_observation_must_be_dated_complete_and_shaped():
    db = rb._db()
    bad = [dict(page="apps", observed_at="yesterday", complete=True, values={"apps": []},
                statement="x"),
           dict(page="apps", observed_at=(NOW + timedelta(days=1)).isoformat(),
                complete=True, values={"apps": []}, statement="x"),
           dict(page="apps", observed_at=NOW.isoformat(), complete="yes",
                values={"apps": []}, statement="x"),
           dict(page="apps", observed_at=NOW.isoformat(), complete=True, values={},
                statement="x"),
           dict(page="nope", observed_at=NOW.isoformat(), complete=True, values={},
                statement="x")]
    assert bad
    for kw in bad:
        try:
            shop_observations.record(db, **kw)
            raise AssertionError(f"accepted {kw}")
        except shop_observations.ObservationRefused:
            pass
    assert shop_observations.latest(db, "apps")["state"] == "UNOBSERVED"


def test_an_empty_apps_reading_closes_its_owner_action_and_a_listed_app_reopens_it():
    db = rb._db()
    etsy_ops.seed_owner_queue(db)

    def done():
        with db.session() as s:
            return s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == "etsy_surface:apps_none_installed")).done

    assert done() is False
    shop_observations.record(db, page="apps", observed_at=NOW.isoformat(), complete=True,
                             values={"apps": []}, statement="Apps page empty")
    assert done() is True
    shop_observations.record(db, page="apps", observed_at=NOW.isoformat(), complete=True,
                             values={"apps": ["SomeInventoryApp"]}, statement="one app")
    assert done() is False
    assert shop_observations.latest(db, "apps")["state"] == "FRESH"


def test_policy_violation_items_become_ranked_incidents_with_escalation_and_closure_proof():
    db = rb._db()
    with db.session() as s:
        s.add(Incident(signature=f"{etsy_ops.POLICY_SUSPECTED}123", severity="P1",
                       halts_publication=True, summary="vanished",
                       detail={"first_seen": (NOW - timedelta(days=1)).isoformat()}))
    items = [{"kind": "ip_claim", "listing_id": "123",
              "source_text": "A rights owner reported this listing for copyright."},
             {"kind": "warning", "source_text": "Your listing title may mislead buyers.",
              "deadline": "2026-10-20"}]
    out = shop_observations.record(db, page="policy_violations", observed_at=NOW.isoformat(),
                                   complete=True, values={"items": items},
                                   statement="two notices")
    pv = out["policy_violations"]
    assert len(pv["opened"]) == 2 and len(pv["legal_escalations"]) == 1, pv
    ranked = policy_violations.open_items(db)
    assert [r["severity"] for r in ranked] == ["P1", "P2"] and ranked[0]["halts"]
    assert ranked[0]["remediation_owner"] == "owner" and ranked[1]["deadline"] == "2026-10-20"
    row = _incident(db, ranked[0]["signature"])
    assert row.detail["source_text"].startswith("A rights owner")
    assert "ours" in row.detail["deadline_basis"] and row.detail["closure_proof"]
    with db.session() as s:
        assert s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == f"legal_review:{ranked[0]['signature']}"))
    # An incomplete reading closes nothing; a complete empty one closes all, and the
    # census alarm that opened before it.
    shop_observations.record(db, page="policy_violations", observed_at=NOW.isoformat(),
                             complete=False, values={"items": []}, statement="partial")
    assert len(policy_violations.open_items(db)) == 2
    later = (NOW + timedelta(seconds=1)).isoformat()
    shop_observations.record(db, page="policy_violations", observed_at=later, complete=True,
                             values={"items": []}, statement="empty",
                             now=NOW + timedelta(seconds=2))
    assert policy_violations.open_items(db) == []
    assert _incident(db, f"{etsy_ops.POLICY_SUSPECTED}123").resolved


def test_a_violation_past_its_deadline_is_restated_overdue_with_an_owner_action():
    db = rb._db()
    past = (NOW - timedelta(days=1)).isoformat()
    shop_observations.record(db, page="policy_violations", observed_at=NOW.isoformat(),
                             complete=True, statement="one notice",
                             values={"items": [{"kind": "listing_removed", "listing_id": "5",
                                                "source_text": "Listing removed.",
                                                "deadline": past}]})
    out = policy_violations.escalate_overdue(db)
    assert len(out["overdue"]) == 1, out
    row = _incident(db, out["overdue"][0])
    assert row.summary.startswith("OVERDUE") and row.detail["overdue_since"]
    with db.session() as s:
        assert s.scalar(select(OwnerAction).where(OwnerAction.requirement_key ==
                                                  f"policy_violation_overdue:{row.signature}"))
    assert policy_violations.escalate_overdue(db)["overdue"] == out["overdue"]


# ---- F-592 -------------------------------------------------------------------------------


def test_security_posture_flags_unexpected_scopes_and_a_credential_replaced_outside_refresh():
    prev = {"status": "HEALTHY", "stored": True, "scopes": ["listings_r", "shops_r"],
            "token_fingerprint": "***aaaa", "rotations": 3,
            "updated_at": NOW.isoformat()}
    cur = {**prev, "scopes": ["listings_r", "shops_r", "billing_w"],
           "token_fingerprint": "***bbbb", "access_token": "must-never-appear-1234567890"}
    out = shop_security.posture(cur, prev, now=NOW)
    checks = {f["check"] for f in out["findings"] if f.get("suspicious")}
    assert {"scopes", "authorization"} <= checks, out["findings"]
    assert "must-never-appear" not in repr(out) and out["exposes_credentials"] is False
    clean = shop_security.posture(
        {**prev, "rotations": 4, "token_fingerprint": "***cccc"}, prev, now=NOW,
        observations={"apps": {"state": "FRESH", "observation": {"values": {"apps": []}}},
                      "shared_access": {"state": "FRESH",
                                        "observation": {"values": {"people": []}}}})
    assert clean["status"] == "OK", clean
    stale = shop_security.posture({**prev, "updated_at": (NOW - timedelta(days=40))
                                   .isoformat()}, prev, now=NOW)
    assert any(f["check"] == "rotation" for f in stale["findings"])
    assert stale["unverified"] == ["apps", "shared_access"]


def test_credential_health_carries_the_posture_and_opens_its_incident():
    db = rb._db()
    with FakeEtsy() as fake:
        with rb._Patched(fake, no_credentials=True):
            rb._run(db, "etsy.credential_health")
    reading = etsy_ops.latest_reading(db, etsy_ops.CREDENTIAL_READING)
    assert reading["security_posture"]["status"] in ("UNVERIFIED", "FINDINGS")
    assert reading["security_posture"]["exposes_credentials"] is False
    posture = etsy_ops._security_posture(db, {**reading, "observed_at": 1.0, "stored": True,
                                              "status": "HEALTHY",
                                              "scopes": ["listings_r", "billing_w"]})
    assert posture["findings"]
    row = _incident(db, f"{etsy_ops.SECURITY_INCIDENT}posture")
    assert row and row.severity == "P1" and not row.resolved


# ---- F-514 -------------------------------------------------------------------------------


def test_the_inventory_is_served_with_a_channel_per_surface_and_every_named_surface():
    inv = surface_inventory.served()
    assert inv["count"] >= 30 and inv["missing_named"] == [], inv["missing_named"]
    channels = {r["channel"] for r in inv["surfaces"]}
    assert channels <= {"api", "browser_only", "owner_only", "unsupported",
                        "not_applicable", "unknown"} and "owner_only" in channels
    db = rb._db()
    assert surface_inventory.summary(db)["status"] == "UNKNOWN"
    etsy_ops.store_reading(db, etsy_ops.CREDENTIAL_READING,
                           {"observed_at": 1.0, "scopes": ["listings_r"]})
    check = surface_inventory.reverify(db)
    assert any("does not hold" in p for p in check["problems"]), check["problems"]
    assert any("evidence is" in p for p in check["problems"])
    summ = surface_inventory.summary(db)
    assert summ["status"] == "DEGRADED" and summ["basis"] == "measured" and summ["sources"]


# ---- F-535 -------------------------------------------------------------------------------


def _order(db, ref, *, product="nordic", reasons=(), state="fully_refunded", case_id=None,
           customer="etsy-user-1", reviewed=False, stars=None):
    with db.session() as s:
        cust = s.scalar(select(Customer).where(Customer.customer_ref == customer))
        if cust is None:
            cust = Customer(customer_ref=customer)
            s.add(cust)
            s.flush()
        detail = {"state": state, "refund": {"cad": 0.0 if state == "paid" else 5.0,
                                             "reasons": list(reasons)}}
        if stars:
            detail["review_stars"] = stars
        s.add(Order(customer_id=cust.id, external_ref=ref, product_slug=product,
                    refunded=state != "paid", support_case_id=case_id, reviewed=reviewed,
                    detail=detail, source="fake"))


def test_refund_reasons_are_captured_at_ingest():
    receipt = {"receipt_id": 9, "buyer_user_id": 4, "status": "fully refunded",
               "is_paid": True, "create_timestamp": 1_790_000_000,
               "transactions": [{"transaction_id": 1, "listing_id": 7, "quantity": 1,
                                 "price": {"amount": 500, "divisor": 100,
                                           "currency_code": "CAD"}}],
               "refunds": [{"amount": {"amount": 500, "divisor": 100, "currency_code": "CAD"},
                            "reason": "Buyer thought it was a finished blanket",
                            "note_from_issuer": ""}]}
    lines = orders_ingest.lines(receipt)
    assert lines[0]["refund_reasons"] == ["Buyer thought it was a finished blanket"], lines


def test_every_refund_and_case_gets_a_code_and_owner_and_repetition_opens_an_investigation():
    db = rb._db()
    for i in range(3):
        _order(db, f"r{i}", reasons=["I thought I was buying the blanket"])
    _order(db, "r9", reasons=[], state="cancelled")
    with db.session() as s:
        s.add(SupportCase(customer_ref="etsy-user-2", product_slug="nordic",
                          question="The file won't open on my phone"))
    out = cx_root_cause.run(db)
    assert out["assigned"] == {"orders": 4, "cases": 1}, out
    with db.session() as s:
        codes = {o.external_ref: o.detail["root_cause"] for o in s.scalars(select(Order))}
        case = s.scalar(select(SupportCase)).detail["root_cause"]
    assert codes["r0"]["code"] == "expected_physical_item" and codes["r0"]["owner"]
    assert codes["r9"]["code"] == cx_root_cause.UNRECORDED and codes["r9"]["owner"] == "owner"
    assert codes["r9"]["kind"] == "cancellation"
    assert case["code"] == "download_access" and case["investigation"] == "deliverable"
    sig = f"{cx_root_cause.PREFIX}nordic:expected_physical_item"
    assert out["repeated"]["opened"] == [sig], out["repeated"]
    row = _incident(db, sig)
    assert row.detail["investigation"] == "listing" and row.detail["count"] == 3
    assert "blanket" not in row.summary and "blanket" not in repr(row.detail)
    again = cx_root_cause.run(db)
    assert again["assigned"] == {"orders": 0, "cases": 0} and not again["repeated"]["opened"]
    with db.session() as s:
        s.delete(s.scalar(select(Order).where(Order.external_ref == "r0")))
    cx_root_cause.run(db)
    assert _incident(db, sig).resolved


def test_the_daily_order_readings_carry_the_root_cause_reading():
    from brambleloop.commerce import order_readings

    db = rb._db()
    _order(db, "r1", reasons=["Too expensive for what it is"])
    reading = order_readings.read(db)
    assert reading["root_cause"]["assigned"]["orders"] == 1, reading["root_cause"]
    assert reading["root_cause"]["by_code"] == {"price_value": 1}


# ---- F-689 -------------------------------------------------------------------------------


def test_the_workspace_joins_messages_orders_reviews_and_refunds_per_buyer():
    db = rb._db()
    with db.session() as s:
        case = SupportCase(customer_ref="etsy-user-1", product_slug="nordic",
                           question=f"{SENTINEL} row 12 is wrong", escalated=True)
        s.add(case)
        s.flush()
        cid = case.id
    _order(db, "o1", reasons=["mistake in row 12"], case_id=cid)
    _order(db, "o2", state="paid", reviewed=True, stars=5)
    cx_root_cause.run(db)
    ws = workspace.workspace(db, customer_ref="etsy-user-1")
    assert ws["count"] == 1, ws
    b = ws["buyers"][0]
    assert b["messages"][0]["question"].startswith(SENTINEL)
    assert {o["order"] for o in b["orders"]} == {"o1", "o2"}
    assert b["reviews"] == [{"order": "o2", "stars": 5}]
    assert b["refunds"][0]["reason_code"] == "pattern_error" and b["refunds"][0]["owner"]
    assert ws["nothing_sent"] is True and "risks" in ws and "upstream_fixes" in ws
    summ = workspace.summary(db)
    assert summ["status"] in ("OK", "DEGRADED") and summ["items"]
    text = repr(summ)
    assert SENTINEL not in text and "etsy-user-1" not in text
    item = summ["items"][0]
    assert item["orders"]["reviewed"] == 1 and item["reviews"]["mean_stars"] == 5.0
    assert item["refund_causes"]["pattern_error"] == 1
    assert workspace.summary(rb._db())["status"] == "UNKNOWN"


def test_support_mining_carries_the_workspace_summary():
    from brambleloop.support.department import CustomerExperience

    db = rb._db()
    with db.session() as s:
        s.add(SupportCase(customer_ref="etsy-user-3", question=f"{SENTINEL} where is it"))
    out = CustomerExperience(db).mine_cases()
    assert out["workspace"]["items"][0]["messages"]["cases"] == 1
    assert SENTINEL not in repr(out["workspace"])


# ---- routes ------------------------------------------------------------------------------


def test_routes_guard_customer_content_and_writes_with_the_operator_credential():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from brambleloop.commerce.estate_api import CUSTOMER_DATA_ROUTES, make_router

    db = rb._db()
    with db.session() as s:
        s.add(SupportCase(customer_ref="etsy-user-4", question=f"{SENTINEL} hello"))
    app = FastAPI()
    app.include_router(make_router(db))
    client = TestClient(app)
    prior = os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)
    try:
        assert client.get("/api/cx/workspace").status_code == 503
        os.environ["BRAMBLELOOP_OPS_TOKEN"] = rb.PUBLISH_FIXTURE_TOKEN
        assert client.get("/api/cx/workspace").status_code == 401
        assert client.get("/api/cx/workspace",
                          headers={"authorization": f"Bearer {'w' * 40}"}
                          ).status_code == 401
        ok = client.get("/api/cx/workspace",
                        headers={"authorization": f"Bearer {rb.PUBLISH_FIXTURE_TOKEN}"})
        assert ok.status_code == 200 and SENTINEL in ok.text
        for path in ("/api/cx/summary", "/api/etsy/surfaces", "/api/etsy/estate",
                     "/api/etsy/listing-lifecycle?listing_id=1"):
            r = client.get(path)
            assert r.status_code == 200 and SENTINEL not in r.text, (path, r.status_code)
        body = {"page": "shared_access", "observed_at": NOW.isoformat(), "complete": True,
                "values": {"people": []}, "statement": "empty"}
        assert client.post("/api/etsy/shop-observation", json=body).status_code == 401
        r = client.post("/api/etsy/shop-observation", json=body,
                        headers={"authorization": f"Bearer {rb.PUBLISH_FIXTURE_TOKEN}"})
        assert r.status_code == 200 and r.json()["page"] == "shared_access", r.text
        r = client.post("/api/etsy/shop-observation", json={**body, "observed_at": "x"},
                        headers={"authorization": f"Bearer {rb.PUBLISH_FIXTURE_TOKEN}"})
        assert r.status_code == 400
        assert client.get("/api/etsy/policy-violations").status_code == 401
        assert CUSTOMER_DATA_ROUTES == frozenset({"/api/cx/workspace"})
    finally:
        os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)
        if prior is not None:
            os.environ["BRAMBLELOOP_OPS_TOKEN"] = prior


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
