"""W4-STORE: the live Etsy shop is authoritative -- snapshot, drift, owner-field protection,
the store.live_drift job and the store readiness register.

No request leaves the machine: live readings are stored getShop bodies and owner observations,
exactly as production stores them.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_w4_store_live_state.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
for _k in list(os.environ):
    if _k.startswith("ETSY"):
        os.environ.pop(_k)

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402
from brambleloop.store_foundation import content, live_state as L, store_readiness as R  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="w4store_")
_N = [0]


def _db() -> Database:
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/s{_N[0]}.db")
    db.create_all()
    return db


def _shop(db, body: dict, *, age_days: float = 0.0) -> None:
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING,
                           {"observed_at": time.time() - age_days * 86400, "shop": body})


def _ctx(db):
    audits = []
    return types.SimpleNamespace(db=db, audit=lambda action, detail=None: audits.append(
        (action, detail))), audits


def _row(report, field):
    rows = [r for r in report["fields"] if r["field"] == field]
    assert len(rows) == 1, field
    return rows[0]


LIVE_TITLE = "Patterns for a More Handmade Life"   # owner-set, differs from the repo draft


def test_owner_configured_fields_are_the_ones_the_owner_set():
    assert L.FIELDS
    for k in ("shop_icon", "shop_banner", "shop_title", "about_headline", "about_story",
              "laura_member_profile", "laura_member_role"):
        assert k in L.OWNER_CONFIGURED, k
    assert "announcement" not in L.OWNER_CONFIGURED
    assert {"title", "icon_url_fullxfull", "image_url_760x100"} <= L.OWNER_CONFIGURED_API_FIELDS


def test_nothing_read_is_unknown_never_a_match():
    report = L.drift(_db())
    assert report["fields"]
    for r in report["fields"]:
        assert r["status"] == L.UNKNOWN, r
        assert r["proposal"]["auto_apply"] is False and r["proposal"]["write_allowed"] is False
    assert report["writes_performed"] == 0
    assert _row(report, "about_story")["proposal"]["kind"] == L.OWNER_OBSERVE
    assert _row(report, "shop_title")["proposal"]["kind"] == L.OWNER_CONFIRM


def test_live_owner_title_is_authoritative_and_the_draft_is_the_stale_side():
    db = _db()
    _shop(db, {"shop_name": "BrambleloopStudio", "title": LIVE_TITLE, "announcement": "",
               "icon_url_fullxfull": "https://i.etsystatic.com/icon.jpg",
               "image_url_760x100": "https://i.etsystatic.com/banner.jpg",
               "digital_sale_message": "something the owner typed",
               "policy_additional": ""})
    report = L.drift(db)
    title = _row(report, "shop_title")
    assert title["status"] == L.LIVE_AUTHORITATIVE_DIFFERS, title
    assert title["proposal"]["kind"] == L.ADOPT_LIVE_INTO_REPO
    assert title["proposal"]["auto_apply"] is False and "draft_excerpt" not in title["proposal"]
    assert "never overwrites" in title["write_refusal"]
    assert _row(report, "shop_icon")["status"] == L.LIVE_SET_NOT_COMPARABLE
    assert _row(report, "shop_banner")["status"] == L.LIVE_SET_NOT_COMPARABLE
    assert _row(report, "shop_name")["status"] == L.MATCH
    assert _row(report, "policy_additional")["status"] == L.MATCH
    ann = _row(report, "announcement")
    assert ann["status"] == L.LIVE_MISSING and ann["proposal"]["kind"] == L.OWNER_ENTER
    dsm = _row(report, "digital_sale_message")
    assert dsm["status"] == L.DRIFT and dsm["proposal"]["kind"] == L.OWNER_REVIEW_UPDATE
    assert _row(report, "about_story")["status"] == L.UNKNOWN, "no API returns About"
    assert report["writes_performed"] == 0


def test_a_live_owner_field_blank_and_a_long_title_are_reported_not_fixed():
    db = _db()
    _shop(db, {"title": "x" * 60, "icon_url_fullxfull": None})
    report = L.drift(db)
    assert _row(report, "shop_icon")["status"] == L.LIVE_BLANK_OWNER_FIELD
    codes = [f["code"] for f in report["findings"]]
    assert "title_over_limit" in codes, codes


def test_owner_observation_evidences_about_and_laura_and_flags_compliance():
    db = _db()
    now = datetime.now(timezone.utc)
    out = L.record_observation(db, observed_at=now.isoformat(), statement="read the live About",
                               fields={"about_headline": "Meet Laura",
                                       "about_story": "Brambleloop makes crochet patterns.",
                                       "laura_member_profile": "Laura designs our patterns.",
                                       "laura_member_role": "Owner"})
    assert out["id"] and len(out["fields"]) == 4
    report = L.drift(db)
    assert _row(report, "about_headline")["live_source"] == "OWNER_OBSERVATION"
    assert _row(report, "laura_member_role")["status"] == L.LIVE_AUTHORITATIVE_DIFFERS
    codes = {f["code"] for f in report["findings"]}
    assert {"laura_in_owner_role", "laura_ai_not_disclosed"} <= codes, codes
    L.record_observation(db, observed_at=now.isoformat(), statement="fixed by owner",
                         fields={"laura_member_role": "Designer",
                                 "laura_member_profile": "Laura is Brambleloop's AI founder."})
    report = L.drift(db)
    assert _row(report, "laura_member_role")["status"] == L.MATCH
    codes = {f["code"] for f in report["findings"]}
    assert not ({"laura_in_owner_role", "laura_ai_not_disclosed"} & codes), codes


def test_observations_that_are_not_evidence_are_refused():
    db = _db()
    now = datetime.now(timezone.utc)
    bad = [dict(observed_at="yesterday", fields={"about_story": "x"}, statement="s"),
           dict(observed_at=(now + timedelta(days=1)).isoformat(), fields={"about_story": "x"},
                statement="s"),
           dict(observed_at=now.isoformat(), fields={"nonsense": "x"}, statement="s"),
           dict(observed_at=now.isoformat(), fields={"about_story": "x"}, statement=" "),
           dict(observed_at=now.isoformat(), fields={}, statement="s")]
    assert bad
    for kw in bad:
        try:
            L.record_observation(db, **kw)
        except L.ObservationRefused:
            continue
        raise AssertionError(f"accepted {kw}")


def test_a_stale_reading_is_marked_stale():
    db = _db()
    _shop(db, {"title": LIVE_TITLE}, age_days=30)
    snap = L.snapshot(db)
    assert snap["shop_title"]["state"] == L.STALE


def test_owner_fields_are_never_in_the_update_shop_payload_and_guard_refuses():
    from brambleloop.commerce import shop_package as P

    fields = P.api_shop_fields()
    assert fields, "something remains sendable"
    assert "title" not in fields and "policy_additional" not in fields
    for f in ("title", "shop_title", "icon_url_fullxfull", "about_story"):
        try:
            L.guard([f])
        except L.OwnerFieldProtected:
            continue
        raise AssertionError(f"guard let {f} through")
    L.guard(["announcement"])  # not owner-configured: allowed past the guard (still shadow)
    assert "Shadow Mode" in L.write_refusal("announcement")


def test_the_etsy_client_has_no_update_shop_write():
    from brambleloop.integrations.etsy import EtsyClient

    names = [n for n in dir(EtsyClient) if not n.startswith("__")]
    assert names
    assert not [n for n in names if "update_shop" in n or "shop_banner" in n], names


def test_content_model_reports_entered_on_etsy_from_live_evidence():
    db = _db()
    s = content.build(db)
    assert s["shop_title"].to_dict()["entered_on_etsy"] == "UNKNOWN"
    _shop(db, {"title": LIVE_TITLE, "announcement": ""})
    s = content.build(db)
    d = s["shop_title"].to_dict()
    assert d["entered_on_etsy"] == "SET" and d["live"]["owner_configured"] is True, d
    assert s["announcement"].to_dict()["entered_on_etsy"] == "BLANK"
    assert s["about"].to_dict()["entered_on_etsy"] == "UNKNOWN"
    auth = L.authoritative(db)
    assert auth["shop_title"]["use"] == "LIVE" and auth["shop_title"]["live"] == LIVE_TITLE
    assert auth["about_story"]["use"] == "REPO_DRAFT_NOT_VERIFIED_LIVE"


def test_live_drift_job_stores_report_and_handles_blank_owner_field_incident():
    db = _db()
    ctx, audits = _ctx(db)
    out = etsy_ops.handle_store_live_drift(ctx)
    assert out["writes_performed"] == 0 and out["unknown"] == len(L.FIELDS)
    assert etsy_ops.latest_reading(db, etsy_ops.LIVE_DRIFT_READING)["fields"]
    assert not out["incidents_opened"], "UNKNOWN opens nothing"
    _shop(db, {"title": LIVE_TITLE, "icon_url_fullxfull": ""})
    out = etsy_ops.handle_store_live_drift(ctx)
    sig = f"{etsy_ops.LIVE_OWNER_FIELD_BLANK}shop_icon"
    assert out["incidents_opened"] == [sig], out
    _shop(db, {"title": LIVE_TITLE, "icon_url_fullxfull": "https://i/icon"})
    etsy_ops.handle_store_live_drift(ctx)
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == sig))
        assert inc.resolved, "a later reading showing it set resolves it"
    assert audits and all(a[0] == "store.live_drift" for a in audits)


def test_store_readiness_register_is_complete_and_honest():
    rep = R.build(_db(), env={})
    register = rep["items"]
    assert register
    assert rep["owner_actions"]
    for it in register:
        assert it["status"] in R.STATUSES, it
        if it["status"] not in (R.PROVEN, R.NOT_APPLICABLE):
            assert it["remaining_gate"], f"{it['id']} has no exact gate"
    ids = {it["id"] for it in register}
    for need in ("SET-A1", "SET-C3", "TAX-1", "TAX-2", "POL-1", "IMG-1", "IMG-2", "LST-1",
                 "UPL-1", "ANA-1", "PUB-1", "LIVE-1", "LIVE-2", "LIVE-4"):
        assert need in ids, need
    c3 = next(it for it in register if it["id"] == "SET-C3")
    assert c3["status"] == R.EXTERNAL_GATED and c3["live"] == "UNKNOWN", c3
    assert next(it for it in register if it["id"] == "PUB-1")["status"] == R.OWNER_GATED
    assert rep["drift"]["writes_performed"] == 0
    md = R.render_md(rep)
    assert "UNKNOWN" in md and "OA-A1" in md
    for a in rep["owner_actions"]:
        assert a["action"] and a["why"] and a["max_cost"] and a["minutes"] > 0


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
            traceback.print_exc(limit=4)
    print(f"\n{len(names) - fails} passed, {fails} failed")
    sys.exit(1 if fails else 0)
