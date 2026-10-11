"""W4-SHOPSYNC: the live shop reconciled into CONFIRMED-LIVE / OWNER-CONFIRMED / UNVERIFIED.

Etsy is stubbed: every response is a recorded shape from the Open API v3 Shop, ShopSection,
ShopReturnPolicy and ShopListing schemas. The harness refuses real sockets.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_shopsync.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="w4_shopsync_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-SHOPSYNC harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, OwnerAction, Phase  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.store_foundation import live_state, shop_sync as S  # noqa: E402

KEY, SECRET = "keystringSHOPSYNC00001", "sharedsecretSHOPSYNC01"
ENV = {"ETSY_KEYSTRING": KEY, "ETSY_SHARED_SECRET": SECRET}
SHOP_ID = 55501234
PASS = "owner passphrase for the shop sync harness"
os.environ[opsauth.TOKEN_VAR] = "s" * 40
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()

SHOP = {"shop_id": SHOP_ID, "shop_name": "BrambleloopStudio",
        "title": "Modern crochet patterns, tested to the stitch",
        "announcement": "", "sale_message": "Thank you for your order!",
        "digital_sale_message": "Your PDF is in Purchases and reviews.",
        "icon_url_fullxfull": "https://i.etsystatic.com/isla/icon.jpg",
        "image_url_760x100": None, "policy_privacy": "We keep only what Etsy gives us.",
        "policy_refunds": "Digital downloads cannot be returned.",
        "is_vacation": False, "vacation_message": None,
        "is_etsy_payments_onboarded": True, "is_direct_checkout_onboarded": True,
        "currency_code": "CAD", "shop_location_country_iso": "CA",
        "policy_additional": None}
SECTIONS = {"count": 2, "results": [{"shop_section_id": 1, "title": "Home", "rank": 1},
                                    {"shop_section_id": 2, "title": "Baby", "rank": 2}]}
RETURNS = {"count": 1, "results": [{"return_policy_id": 9, "accepts_returns": False,
                                    "accepts_exchanges": False, "return_deadline": None}]}
FEATURED = {"count": 1, "results": [{"listing_id": 77, "featured_rank": 1, "title": "Throw"}]}


@dataclass
class _R:
    status: int
    body: dict
    headers: dict = field(default_factory=dict)


class _Etsy:
    """Answers the five shop-sync GETs; records every request."""

    def __init__(self, *, refuse: int | None = None, error: str = ""):
        self.refuse, self.error = refuse, error
        self.requests: list[tuple[str, str, dict]] = []

    def request(self, method, url, *, headers, body=None, timeout=20.0, json=None,
                form=None, multipart=None):
        self.requests.append((method, url, dict(headers)))
        if self.refuse:
            return _R(self.refuse, {"error": self.error})
        path = url.split("/v3/application", 1)[1].split("?")[0]
        if path == "/shops":
            return _R(200, {"count": 2, "results": [
                {"shop_id": 1, "shop_name": "BrambleloopStudios"},
                {"shop_id": SHOP_ID, "shop_name": "BrambleloopStudio"}]})
        if path == f"/shops/{SHOP_ID}":
            return _R(200, SHOP)
        if path.endswith("/sections"):
            return _R(200, SECTIONS)
        if path.endswith("/policies/return"):
            return _R(200, RETURNS)
        if path.endswith("/listings/featured"):
            return _R(200, FEATURED)
        return _R(404, {"error": "not stubbed"})


def _db(name: str) -> Database:
    db = Database(f"sqlite:///{_TMP}/{name}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _sync(db, etsy, env=None, now=None):
    saved = S.transport_factory
    S.transport_factory = lambda: etsy
    try:
        return S.sync(db, env=dict(ENV, **(env or {})), now=now)
    finally:
        S.transport_factory = saved


def _row(st, key):
    return next(r for r in st["settings"] if r["key"] == key)


# ---- reading ----------------------------------------------------------------------------

def test_the_operations_are_get_api_key_only_and_named_from_the_spec():
    assert set(S.OPERATIONS) == {"findShops", "getShop", "getShopSections",
                                 "getShopReturnPolicies", "getFeaturedListingsByShop"}
    db = _db("ops")
    etsy = _Etsy()
    got = _sync(db, etsy)
    assert got["ran"] and got["reading"] == "measured", got
    assert [c["operation"] for c in got["operations"]] == [
        "findShops", "getShop", "getShopSections", "getShopReturnPolicies",
        "getFeaturedListingsByShop"]
    assert len(etsy.requests) == 5
    for method, url, headers in etsy.requests:
        assert method == "GET" and url.startswith("https://openapi.etsy.com/v3/application/")
        assert "Authorization" not in headers and headers["x-api-key"] == f"{KEY}:{SECRET}"
    reader = S.ShopReader(_Etsy(), keystring=KEY)
    try:
        reader.get("updateShop")
    except PermissionError:
        pass
    else:
        raise AssertionError("a non-allowlisted operation was allowed")


def test_findshops_needs_an_exact_name_and_etsy_shop_id_skips_it():
    db = _db("resolve")
    etsy = _Etsy()
    got = _sync(db, etsy, env={"ETSY_SHOP_ID": str(SHOP_ID)})
    assert got["shop_id_source"] == "ETSY_SHOP_ID"
    assert [c["operation"] for c in got["operations"]][0] == "getShop"
    got = _sync(_db("resolve2"), _Etsy(), env={"ETSY_SHOP_NAME": "brambleloopstudio"})
    assert "exact match" in got["shop_id_source"]
    got = _sync(_db("resolve3"), _Etsy(), env={"ETSY_SHOP_NAME": "Brambleloop"})
    assert got["ran"] is False and "no shop named exactly" in got["why"]


def test_no_keystring_or_a_refused_probe_reads_nothing():
    db = _db("closed")

    def never():
        raise AssertionError("a transport was built")

    saved = S.transport_factory
    S.transport_factory = never
    try:
        assert S.sync(db, env={})["reading"] == "UNMEASURED"
        with db.session() as s:
            s.add(AuditLog(actor="market_radar", action="etsy.probe",
                           detail={"ok": False, "status": 403, "reason": "HTTP 403"}))
        got = S.sync(db, env=dict(ENV))
    finally:
        S.transport_factory = saved
    assert got["reading"] == "UNMEASURED" and got["credential_refused"] is True
    assert S.latest_sync(db) is None


def test_a_refusal_mid_sync_is_unmeasured_and_never_leaks_the_key():
    db = _db("refused")
    got = _sync(db, _Etsy(refuse=403, error=f"bad key {KEY}:{SECRET}"))
    assert got["ran"] is False and got["credential_refused"] is True
    assert KEY not in repr(got) and SECRET not in repr(got)
    assert S.latest_sync(db) is None
    assert all(r["state"] == S.UNVERIFIED for r in S.status(db)["settings"])


# ---- the three states -------------------------------------------------------------------

def test_api_readable_settings_become_confirmed_live_with_source_and_time():
    db = _db("states")
    now = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
    _sync(db, _Etsy(), now=now)
    st = S.status(db, now=now + timedelta(hours=1))
    for key in ("shop_name", "shop_icon", "tagline", "sections", "buyer_messages",
                "privacy_policy", "cancellation_policy", "payment_readiness", "vacation",
                "currency_location", "announcement"):
        r = _row(st, key)
        assert r["state"] == S.CONFIRMED_LIVE, (key, r)
        assert r["observed_at"] == now.isoformat() and r["source"], r
    # Blank on Etsy is still a confirmed live value, and says so.
    assert _row(st, "announcement")["value_present"] is False
    assert _row(st, "sections")["values"]["getShopSections.title"] == ["Home", "Baby"]
    # The API shows no banner: the owner may confirm it, so it is not CONFIRMED-LIVE.
    assert _row(st, "banner")["state"] == S.UNVERIFIED
    for key in ("about", "member_identity", "listing_order", "sold_visibility", "faq",
                "payout_details", "two_factor"):
        r = _row(st, key)
        assert r["state"] == S.UNVERIFIED and r["owner_confirmable"], (key, r)
        assert r["prefilled_statement"] and "evidence" in r
    assert sum(st["counts"].values()) == len(S.SETTINGS)


def test_a_stale_api_reading_is_unverified_not_confirmed():
    db = _db("stale")
    then = datetime(2026, 10, 1, tzinfo=timezone.utc)
    _sync(db, _Etsy(), now=then)
    r = _row(S.status(db, now=then + timedelta(days=S.API_MAX_AGE_DAYS + 1)), "shop_name")
    assert r["state"] == S.UNVERIFIED and "older than" in r["why"]


def test_owner_confirmation_prefills_the_evidence_already_on_file():
    db = _db("confirm")
    now = datetime.now(timezone.utc)
    _sync(db, _Etsy(), now=now)
    live_state.record_observation(db, observed_at=now - timedelta(days=1),
                                  fields={"about_headline": "Patterns that work",
                                          "about_story": "Every pattern is checked."},
                                  statement="read on my phone")
    with db.session() as s:
        s.add(OwnerAction(requirement_key="store:OA-OBS", action="Record the About text",
                          reason="r", minutes=5, done=True))
    st = S.status(db)
    ev = _row(st, "about")["evidence"]
    assert ev["observations"]["about_headline"]["value"] == "Patterns that work"
    assert ev["owner_actions"][0]["key"] == "store:OA-OBS"
    lo = _row(st, "listing_order")["evidence"]["api"]
    assert lo["getFeaturedListingsByShop.featured_rank"][0]["listing_id"] == 77
    out = S.confirm(db, "about", actor="owner:cc:s_test")
    assert out["state"] == S.OWNER_CONFIRMED
    r = _row(S.status(db), "about")
    assert r["state"] == S.OWNER_CONFIRMED and r["observed_at"] and r["statement"]
    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == S.CONFIRM_ACTION))
        assert row.detail["evidence"]["observations"]["about_story"]["value"]


def test_an_api_readable_setting_cannot_be_owner_confirmed_and_old_ones_expire():
    db = _db("refuse_confirm")
    for key in ("shop_name", "sections", "payment_readiness", "nope"):
        try:
            S.confirm(db, key, actor="owner")
        except S.ConfirmRefused:
            pass
        else:
            raise AssertionError(f"{key} was owner-confirmed")
    old = datetime.now(timezone.utc) - timedelta(days=S.OWNER_MAX_AGE_DAYS + 1)
    S.confirm(db, "two_factor", actor="owner", now=old)
    assert _row(S.status(db), "two_factor")["state"] == S.UNVERIFIED


def test_the_sync_feeds_the_live_drift_as_the_authoritative_side():
    db = _db("drift")
    _sync(db, _Etsy())
    snap = live_state.snapshot(db)
    assert snap["shop_title"]["source"] == "API_GETSHOP"
    assert snap["shop_title"]["value"] == SHOP["title"]
    report = live_state.drift(db)
    assert report["writes_performed"] == 0
    assert "shop_title" not in report["unknown"]


def test_the_daily_drift_job_runs_the_sync_and_never_dies_on_a_refusal():
    db = _db("job")
    saved = S.transport_factory
    for etsy, key in ((_Etsy(), "drift-ok"), (_Etsy(refuse=403, error="inactive"), "drift-403")):
        S.transport_factory = lambda e=etsy: e
        old = {k: os.environ.get(k) for k in ENV}
        os.environ.update(ENV)
        try:
            JobQueue(db).enqueue("orchestrator", "store.live_drift", {}, priority=0,
                                 idempotency_key=key)
            w = Worker(db, "w4s", phase=Phase.SHADOW, job_types=["store.live_drift"])
            for _ in range(3):
                if not w.run_once():
                    break
        finally:
            S.transport_factory = saved
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        with db.session() as s:
            job = s.scalar(select(Job).where(Job.idempotency_key == key))
            assert job.status == JobStatus.DONE, (key, job.status, job.last_error)
    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == S.SYNC_ACTION)
                              .order_by(AuditLog.id)))
    assert [r.detail["reading"] for r in rows] == ["measured", "UNMEASURED"]


# ---- the Command Center ---------------------------------------------------------------------

def _session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def _fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


def test_the_store_settings_routes_need_a_session_and_csrf():
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.get("/api/cc/store/settings").status_code == 401
    assert anon.post("/api/cc/store/settings/faq/confirm", json={}).status_code == 401
    c, csrf = _session()
    r = c.post("/api/cc/store/settings/faq/confirm", json={},
               headers={"X-CC-Nonce": uuid.uuid4().hex, "X-CC-Timestamp": str(int(time.time()))})
    assert r.status_code == 403, r.text


def test_one_tap_confirm_and_reread_from_the_phone():
    c, csrf = _session()
    st = c.get("/api/cc/store/settings").json()
    assert st["states"] == [S.CONFIRMED_LIVE, S.OWNER_CONFIRMED, S.UNVERIFIED]
    assert _row(st, "faq")["state"] == S.UNVERIFIED
    r = c.post("/api/cc/store/settings/faq/confirm", json={}, headers=_fresh(csrf))
    assert r.status_code == 200 and r.json()["state"] == S.OWNER_CONFIRMED, r.text
    assert _row(c.get("/api/cc/store/settings").json(), "faq")["state"] == S.OWNER_CONFIRMED
    r = c.post("/api/cc/store/settings/shop_name/confirm", json={}, headers=_fresh(csrf))
    assert r.status_code == 409 and r.json()["code"] == "NOT_OWNER_CONFIRMABLE"
    r = c.post("/api/cc/store/settings/sync", json={}, headers=_fresh(csrf))
    assert r.status_code == 200 and r.json()["enqueued"] is True
    with main.db.session() as s:
        assert s.get(Job, r.json()["job_id"]).job_type == "store.live_drift"


def test_the_store_tab_shows_the_three_states():
    js = ROOT / "src/brambleloop/app/command_center/static/js"
    store = (js / "views/store.js").read_text()
    for text in ("CONFIRMED-LIVE", "OWNER-CONFIRMED", "UNVERIFIED", "Live shop settings",
                 "Re-read from Etsy", "confirmStoreSetting"):
        assert text in store, text
    assert "/store/settings" in (js / "api.js").read_text()


def _run_all() -> int:
    failures = 0
    tests = [(n, f) for n, f in list(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failures += 1
            print(f"FAIL {name}: {exc}")
            traceback.print_exc()
    print(f"{len(tests) - failures} passed, {failures} failed")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run_all() else 0)
