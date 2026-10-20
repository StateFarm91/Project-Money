"""W4-FIRSTSALE2: every first-sale Etsy surface has a truthful collector (W4-CLOSE6 §11).

Production's `etsy_first_sale_surfaces` listed messages, orders, legal_and_tax, digital_files
and taxonomy_and_attributes with no collector, so the item could never be ready. Proven here:

* the item CAN reach ready when every input is genuinely satisfied (a passing fresh shop
  snapshot, a fresh census, a completed receipt read with the gate open, every Launch-0 release
  filed on a node of Etsy's tree with complete attributes, every release's certified PDFs held,
  and the owner's dated complete readings of Messages and Legal and tax);
* it can NOT when any one input is missing (each removed in turn), nor when a reading measured
  the requirement unmet (FAILING), nor when a reading is old (STALE);
* `orders` no longer names the obsolete `reauthorise_transactions_r`; that action is raised only
  while the orders gate is actually closed.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_firstsale2_surfaces.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from brambleloop.commerce import shop_observations as so  # noqa: E402
from brambleloop.intel import etsy_surfaces as es  # noqa: E402
from brambleloop.launch import first_sale_surfaces as fss  # noqa: E402
from brambleloop.launch import readiness as rd  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402

INPUTS = ("shop", "census", "orders", "taxonomy", "digital", "messages", "legal_and_tax")
NODE = 424242           # an illustrative node id, present in the fixture tree


def _good_shop() -> dict:
    return {"icon_url_fullxfull": "x", "image_url_760x100": "x", "title": "Brambleloop",
            "announcement": "a", "digital_sale_message": "m", "policy_payment": "p",
            "policy_shipping": "s", "policy_refunds": "r", "policy_privacy": "pv",
            "policy_additional": None, "is_etsy_payments_onboarded": True,
            "is_vacation": False, "currency_code": "CAD", "digital_listing_count": 3}


def _world(skip: str = "", *, now: float, mutate: dict | None = None):
    """A database with every first-sale input genuinely satisfied, except `skip`."""
    from brambleloop.core.db import Database
    from brambleloop.core.models import (AuditLog, DurableArtifact, EtsyTaxonomySnapshot,
                                         ListingSearchProfile, OAuthCredential,
                                         PatternVersion, Product)
    from brambleloop.commerce import deliverables as D

    mutate = mutate or {}
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/fs2.sqlite")
    db.create_all()
    at = datetime.fromtimestamp(now, tz=timezone.utc)
    if skip != "shop":
        snap = {"observed_at": now, "shop": _good_shop()}
        status = es.assess_shop(snap, now=now)
        etsy_ops.store_reading(db, etsy_ops.SHOP_READING, {**snap, "status": status.to_dict()})
    if skip != "census":
        etsy_ops.store_reading(db, etsy_ops.CENSUS_READING, {"observed_at": now})
    releases = fss.launch0_releases()
    with db.session() as s:
        if skip != "orders":
            s.add(AuditLog(actor="market_radar", action="etsy.probe",
                           detail={"ok": True, "application_id": "fixture"}))
            scopes = "listings_r listings_w listings_d shops_r shops_w" + (
                "" if mutate.get("orders_gate_closed") else " transactions_r")
            s.add(OAuthCredential(provider="etsy", scopes=scopes))
            s.add(AuditLog(actor="cfo", action="commerce.orders_ingested", at=at,
                           detail={"ran": True, "reading": "measured", "receipts": 0,
                                   "gate_missing": []}))
        if skip != "taxonomy":
            s.add(EtsyTaxonomySnapshot(
                fetched_at=at, confirmed_at=at, source="etsy_open_api_v3", sha256="f" * 64,
                node_count=1, nodes=[{"id": NODE, "name": "Patterns", "path_ids": [NODE],
                                      "path_names": ["Patterns"], "child_ids": []}],
                properties={}, detail={}))
            for i, (slug, version) in enumerate(releases):
                attrs_ok = not (mutate.get("one_attribute_gap") and i == 0)
                s.add(ListingSearchProfile(
                    product_slug=slug, version=version, category_status="CHOSEN",
                    taxonomy_id=NODE, taxonomy_path=["Patterns"],
                    certificate={"checks": {"attributes": {"ok": attrs_ok}}}))
        for slug, version in releases:
            p = s.scalar(__import__("sqlalchemy").select(Product).where(Product.slug == slug))
            if p is None:
                p = Product(slug=slug, title=slug)
                s.add(p)
                s.flush()
            s.add(PatternVersion(product_id=p.id, version=version, cir_json={},
                                 certified=True, created_at=at))
            if skip == "digital":
                continue
            pdfs = {t: f"%PDF- {slug}@{version} {t}".encode() for t in ("US", "UK")}
            s.add(AuditLog(actor="assets", action="assets.built", artifact=f"{slug}@{version}",
                           detail={"pdf_sha256_by_terminology":
                                   {t: hashlib.sha256(b).hexdigest() for t, b in pdfs.items()}}))
            for t, b in pdfs.items():
                if mutate.get("one_pdf_missing") and (slug, version) == releases[0] and t == "UK":
                    continue
                s.add(DurableArtifact(sha256=hashlib.sha256(b).hexdigest(), payload=b,
                                      bytes_len=len(b),
                                      why_kept=D.keep_why(slug, version, f"pdf:{t}")))
    obs_at = at - timedelta(days=mutate.get("observation_age_days", 0))
    if skip != "messages":
        so.record(db, page="messages", observed_at=obs_at, complete=True,
                  values={"notifications_inbox": "owner@example.invalid",
                          "reply_window_hours": 24},
                  statement="Etsy message notifications go to the owner's inbox; 24 h replies",
                  now=at)
    if skip != "legal_and_tax":
        so.record(db, page="legal_and_tax", observed_at=obs_at, complete=True,
                  values={"identity_verified": not mutate.get("identity_unverified"),
                          "tax_position": "small supplier, not registered for GST/HST",
                          "decided_on": "2026-10-01"},
                  statement="Identity verification complete; small-supplier position chosen",
                  now=at)
    return db


def _req(db, now):
    return rd.etsy_first_sale_surfaces(db, now=now)


def _states(req) -> dict:
    return {r["surface"]: r["evidence_state"] for r in req.evidence["surfaces"]}


def test_every_first_sale_surface_has_a_collector_and_orders_names_no_stale_action():
    blockers = es.first_sale_blockers()
    assert blockers and all(s.collector for s in blockers), \
        [s.key for s in blockers if not s.collector]
    assert all(s.collector in es.COLLECTORS and s.max_age_days for s in blockers)
    orders = next(s for s in blockers if s.key == "orders")
    assert orders.owner_action is None
    assert "reauthorise_transactions_r" not in {a.key for a in es.owner_queue()}
    assert es.check_registry() == [], es.check_registry()


def test_ready_when_every_input_is_genuinely_satisfied():
    now = float(int(time.time()))  # whole seconds: exact through datetime
    req = _req(_world(now=now), now)
    assert set(_states(req).values()) == {es.FRESH}, _states(req)
    assert req.ready is True and req.blocked_by is None, req.evidence
    assert req.evidence["owner_actions_open"] == []


SURFACE_OF = {"shop": None, "census": "listings", "orders": "orders",
              "taxonomy": "taxonomy_and_attributes", "digital": "digital_files",
              "messages": "messages", "legal_and_tax": "legal_and_tax"}


def test_not_ready_when_any_one_input_is_missing():
    now = float(int(time.time()))  # whole seconds: exact through datetime
    checked = 0
    for missing in INPUTS:
        req = _req(_world(missing, now=now), now)
        assert req.ready is False, missing
        surface = SURFACE_OF[missing]
        if surface:
            assert _states(req)[surface] == es.NO_EVIDENCE, (missing, _states(req))
            others = {k: v for k, v in _states(req).items() if k != surface}
            assert set(others.values()) == {es.FRESH}, (missing, others)
        else:
            assert {s for s, v in _states(req).items() if v != es.FRESH} >= {"your_shop"}
        checked += 1
    assert checked == len(INPUTS)


def test_a_reading_of_an_unmet_requirement_is_failing_never_fresh():
    now = float(int(time.time()))  # whole seconds: exact through datetime
    cases = {"identity_unverified": "legal_and_tax", "one_attribute_gap":
             "taxonomy_and_attributes", "one_pdf_missing": "digital_files",
             "orders_gate_closed": "orders"}
    for flag, surface in cases.items():
        req = _req(_world(now=now, mutate={flag: True}), now)
        assert req.ready is False, flag
        assert _states(req)[surface] == es.FAILING, (flag, _states(req))
    req = _req(_world(now=now, mutate={"orders_gate_closed": True}), now)
    row = next(r for r in req.evidence["surfaces"] if r["surface"] == "orders")
    assert row["owner_action"] == "reauthorise_transactions_r", row
    assert req.blocked_by == rd.BLOCKED_OWNER


def test_old_readings_are_stale():
    now = float(int(time.time()))  # whole seconds: exact through datetime
    req = _req(_world(now=now, mutate={"observation_age_days": 120}), now)
    assert _states(req)["legal_and_tax"] == es.STALE      # 90-day tolerance
    assert _states(req)["messages"] == es.STALE           # 30-day tolerance
    assert req.ready is False
    later = now + 3 * 86400                               # tree and receipts age past tolerance
    req = _req(_world(now=now), later)
    assert _states(req)["orders"] == es.STALE
    assert _states(req)["taxonomy_and_attributes"] == es.STALE
    assert req.ready is False


def test_observation_intake_validates_and_closes_only_on_met_values():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/o.sqlite")
    db.create_all()
    now = datetime.now(timezone.utc)
    for bad in ({"notifications_inbox": "", "reply_window_hours": 24}, {}):
        try:
            so.record(db, page="messages", observed_at=now, complete=True, values=bad,
                      statement="s", now=now)
            raise AssertionError(f"accepted {bad}")
        except so.ObservationRefused:
            pass
    try:
        so.record(db, page="legal_and_tax", observed_at=now, complete=True,
                  values={"identity_verified": "yes"}, statement="s", now=now)
        raise AssertionError("accepted a non-boolean identity_verified")
    except so.ObservationRefused:
        pass
    out = so.record(db, page="messages", observed_at=now, complete=True,
                    values={"notifications_inbox": "x@example.invalid", "reply_window_hours": 0},
                    statement="s", now=now)
    assert out["owner_action"]["done"] is False
    assert fss.observation_reading(db, "messages")["satisfied"] is False
    so.record(db, page="messages", observed_at=now, complete=False,
              values={"notifications_inbox": "x@example.invalid", "reply_window_hours": 24},
              statement="s", now=now)
    assert fss.observation_reading(db, "messages")["satisfied"] is False   # incomplete
    assert fss.observation_reading(db, "legal_and_tax") is None            # never observed


def test_an_empty_database_is_never_ready_and_nothing_reads_fresh():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/e.sqlite")
    db.create_all()
    req = _req(db, float(int(time.time())))
    assert req.ready is False
    assert set(_states(req).values()) <= {es.NO_EVIDENCE}, _states(req)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}", flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc(limit=5)
            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:1500], flush=True)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
