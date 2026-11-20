"""W4-ETSYSURF: the bounded Etsy launch list in readiness, and the surface registry at runtime.

Rows: F-498 (Finite Parallel Launch), F-600 (Complete Etsy Autopilot Contract); F-546
(Etsy Feature Discovery) is evidenced by the existing weekly `etsy.openapi_reverify` cadence.
Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_etsysurf.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_etsysurf_")

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import etsy_surfaces as es  # noqa: E402
from brambleloop.launch import readiness as rd  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402

_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    return db


def _good_shop() -> dict:
    return {"icon_url_fullxfull": "x", "image_url_760x100": "x", "title": "Brambleloop",
            "announcement": "a", "digital_sale_message": "m", "policy_payment": "p",
            "policy_shipping": "s", "policy_refunds": "r", "policy_privacy": "pv",
            "policy_additional": None, "is_etsy_payments_onboarded": True,
            "is_vacation": False, "currency_code": "CAD", "digital_listing_count": 3}


def _record_shop(db, shop: dict, now: float):
    snap = {"observed_at": now, "shop": shop}
    status = es.assess_shop(snap, now=now)
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING, {**snap, "status": status.to_dict()})
    # W4-CLOSE6 (F-040): getShop has no About field; the owner's dated reading of the shop
    # page evidences it, and readiness holds without it (tests/test_w4_close6_shop.py).
    from datetime import datetime, timezone

    from brambleloop.commerce import shop_observations

    shop_observations.record(db, page="about", complete=True,
                             observed_at=datetime.fromtimestamp(now, timezone.utc).isoformat(),
                             values={"about_present": True, "matches_storefront": True},
                             statement="Shop page read: the About section shows")


def test_an_unobserved_shop_lists_every_first_sale_surface_and_waits_on_the_owner():
    req = rd.etsy_first_sale_surfaces(_db())
    n = len(es.first_sale_blockers())
    assert n > 0 and req.evidence["count"] == n
    assert req.ready is False and req.blocked_by == rd.BLOCKED_OWNER, req.blocked_by
    assert set(req.evidence["not_fresh"]) == {s.key for s in es.first_sale_blockers()}
    assert req.evidence["owner_actions_open"], "open owner actions are named"
    states = {r["evidence_state"] for r in req.evidence["surfaces"]}
    assert states <= {es.NO_EVIDENCE, es.NO_COLLECTOR}


def test_a_fresh_passing_shop_still_names_every_surface_without_a_reading():
    # W4-FIRSTSALE2: every first-sale surface now has a collector (the five that had none read
    # orders, taxonomy, deliverables and the owner's page observations). With only the shop
    # and census recorded, those five have NO_EVIDENCE and the item is still not ready; the
    # full ready / one-missing proof is tests/test_w4_firstsale2_surfaces.py.
    db = _db()
    now = time.time()
    _record_shop(db, _good_shop(), now)
    etsy_ops.store_reading(db, etsy_ops.CENSUS_READING, {"observed_at": now})
    req = rd.etsy_first_sale_surfaces(db, now=now)
    rows = {r["surface"]: r for r in req.evidence["surfaces"]}
    fresh = {k for k, r in rows.items() if r["evidence_state"] == es.FRESH}
    by_snapshot = {s.key for s in es.first_sale_blockers()
                   if s.collector in ("shop_snapshot", "listing_census")}
    assert fresh == by_snapshot, (fresh, by_snapshot)
    assert req.evidence["shop_checks_failing"] == []
    unread = {s.key for s in es.first_sale_blockers()} - by_snapshot
    assert unread and set(req.evidence["not_fresh"]) == unread
    assert {rows[k]["evidence_state"] for k in unread} == {es.NO_EVIDENCE}
    assert req.ready is False  # a surface with no reading is never assumed done


def test_a_failing_shop_check_is_named():
    db = _db()
    now = time.time()
    bad = {**_good_shop(), "policy_refunds": None, "is_vacation": True}
    _record_shop(db, bad, now)
    req = rd.etsy_first_sale_surfaces(db, now=now)
    assert set(req.evidence["shop_checks_failing"]) == {"policy_refunds_set", "not_on_vacation"}
    assert req.blocked_by == rd.BLOCKED_OWNER


def test_the_requirement_is_part_of_readiness_and_never_blocks_on_build():
    report = rd.assess(_db(), phase="shadow")
    req = next(r for r in report.requirements if r.key == "etsy_first_sale_surfaces")
    assert req.blocked_by in (rd.BLOCKED_OWNER, rd.BLOCKED_INTEGRATION)
    assert "etsy_first_sale_surfaces" not in {r.key for r in report.buildable}


def test_surfaces_api_exposes_coverage_work_plan_and_the_launch_list():
    src = (ROOT / "src" / "brambleloop" / "app" / "main.py").read_text(encoding="utf-8")
    body = src[src.index('@app.get("/api/etsy/surfaces")'):src.index('@app.get("/api/etsy")')]
    for needle in ('"coverage": etsy_surfaces.coverage()', '"work_plan": etsy_surfaces.work_plan()',
                   "etsy_first_sale_surfaces(db)"):
        assert needle in body, needle
    plan = es.work_plan()
    assert set(plan) == set(es.WORK_CLASSES) and sum(map(len, plan.values())) == es.coverage()["surfaces"]


def test_openapi_watch_is_already_a_weekly_cadence():
    """F-546: weekly fetch of Etsy's public OpenAPI document, verify_absence + fingerprint,
    incident on drift -- `runtime.etsy_ops.reverify_openapi` (W4-FM2, tested in
    test_w4_fm2_surface_reverify)."""
    from brambleloop.runtime.worker import CADENCES

    assert any(jt == "etsy.openapi_reverify" and period <= 7 * 24 * 3600
               for _n, _a, jt, period in CADENCES)
    src = (ROOT / "src" / "brambleloop" / "intel" / "etsy_surfaces.py").read_text()
    body = src[src.index("def openapi_reverify"):src.index("def openapi_reverify") + 4000]
    assert "verify_absence" in body and "document_fingerprint" in body


def test_openapi_watch_fingerprints_the_document_and_reports_a_change():
    """F-546: the weekly watch now carries the document fingerprint and whether the document
    changed since the last reading -- None before there is a previous fingerprint."""
    from datetime import datetime, timedelta, timezone

    import test_w4_fm2_surface_reverify as fx

    db = _db()
    now = datetime(2026, 10, 12, tzinfo=timezone.utc)
    first = etsy_ops.reverify_openapi(db, transport=fx._Transport(body=fx._document()), now=now)
    assert len(first["fingerprint"]) == 64 and first["document_changed"] is None
    later = now + timedelta(days=etsy_ops.OPENAPI_REVERIFY_DAYS + 1)
    same = etsy_ops.reverify_openapi(db, transport=fx._Transport(body=fx._document()),
                                     now=later)
    assert same["document_changed"] is False and same["status"] == es.OPENAPI_CURRENT
    later2 = later + timedelta(days=etsy_ops.OPENAPI_REVERIFY_DAYS + 1)
    prose = etsy_ops.reverify_openapi(
        db, transport=fx._Transport(body=fx._document(extra_text=" new prose")), now=later2)
    assert prose["document_changed"] is True and prose["status"] == es.OPENAPI_CURRENT
    from sqlalchemy import select

    from brambleloop.core.models import Incident

    with db.session() as s:  # a change that moved no verdict is still an incident to read
        inc = s.scalar(select(Incident).where(Incident.signature == etsy_ops.OPENAPI_CHANGED))
        assert inc is not None and inc.severity == "P3" and not inc.resolved


def test_dashboard_shows_the_surface_registry():
    src = (ROOT / "src" / "brambleloop" / "app" / "main.py").read_text(encoding="utf-8")
    assert '_block("Etsy surfaces", _etsy_surfaces)' in src


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
