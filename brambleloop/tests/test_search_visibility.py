"""F-248 Search Visibility intake and F-280 launch-week watch.

The rule under test: only a later, complete, recorded reading may clear an item -- a code or
listing change can only mark it REMEDIATED_PENDING. Intake is operator-guarded and refuses
while there is no live listing; the watch is inert in shadow and raises one daily owner card
for seven days after the phase leaves it.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_search_visibility.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import search_visibility as sv  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Listing, OwnerAction, Phase  # noqa: E402

T0 = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
TOKEN = "t" * 40


def _db(live=True) -> Database:
    db = Database("sqlite://", scratch=True)
    db.create_all()
    with db.session() as s:
        s.add(Listing(product_slug="p", version="1", title="t", description="d", tags=[],
                      price_cad=8.0, etsy_listing_id="1234567" if live else ""))
    return db


ITEM = {"scope": "listing", "listing_id": "1234567", "category": "Missing attributes",
        "remediation": "add the colour attribute"}


def test_intake_refuses_without_a_live_listing_and_refuses_unknown_listings():
    try:
        sv.record_reading(_db(live=False), observed_at=T0, items=[ITEM], complete=True)
        raise AssertionError("a reading for a shop with no live listing was accepted")
    except sv.SearchVisibilityRefused as e:
        assert "live_listings" in str(e)
    db = _db()
    try:
        sv.record_reading(db, observed_at=T0, items=[{**ITEM, "listing_id": "999"}],
                          complete=True)
        raise AssertionError("an unknown listing id was accepted")
    except sv.SearchVisibilityRefused as e:
        assert "not an Etsy listing" in str(e)
    try:
        sv.record_reading(db, observed_at=T0, items=[{**ITEM, "scope": "vibes"}],
                          complete=True)
        raise AssertionError("an unknown scope was accepted")
    except sv.SearchVisibilityRefused:
        pass


def test_a_code_change_never_clears_only_a_later_complete_reading_does():
    db = _db()
    out = sv.record_reading(db, observed_at=T0, items=[ITEM], complete=True)
    assert len(out["opened"]) == 1
    item = sv.items(db)[0]
    assert item["state"] == sv.OPEN
    sv.mark_remediated(db, item["id"], ref="commit abc123: colour attribute added")
    assert sv.items(db)[0]["state"] == sv.REMEDIATED_PENDING
    # no API path sets CLEARED except a reading
    row = sv.SearchVisibilityItem(state=sv.REMEDIATED_PENDING, history=[])
    for via in ("remediation", "code", "owner", ""):
        try:
            sv.transition(row, sv.CLEARED, via=via)
            raise AssertionError(f"CLEARED was set via {via!r}")
        except sv.SearchVisibilityRefused:
            pass
    # a partial reading that does not mention the item proves nothing
    sv.record_reading(db, observed_at=T0 + timedelta(days=1), items=[], complete=False)
    assert sv.items(db)[0]["state"] == sv.REMEDIATED_PENDING
    # a complete reading that is not later than the one that listed it cannot clear it
    sv.record_reading(db, observed_at=T0 - timedelta(hours=1), items=[], complete=True)
    assert sv.items(db)[0]["state"] == sv.REMEDIATED_PENDING
    # a later complete reading that no longer lists it clears it
    out = sv.record_reading(db, observed_at=T0 + timedelta(days=2), items=[], complete=True)
    assert out["cleared"] == [item["key"]]
    cleared = sv.items(db)[0]
    assert cleared["state"] == sv.CLEARED
    assert cleared["history"][-1]["via"] == sv.VIA_READING
    # and a later reading listing it again reopens it
    out = sv.record_reading(db, observed_at=T0 + timedelta(days=3), items=[ITEM], complete=True)
    assert out["reopened"] == [item["key"]]
    assert sv.items(db)[0]["state"] == sv.OPEN and sv.items(db)[0]["reopened"] == 1


def test_a_still_listed_item_is_not_cleared():
    db = _db()
    sv.record_reading(db, observed_at=T0, items=[ITEM], complete=True)
    shop = {"scope": "shop", "category": "Shop policies incomplete", "remediation": ""}
    sv.record_reading(db, observed_at=T0 + timedelta(days=1), items=[ITEM, shop],
                      complete=True)
    states = {r["category"]: r["state"] for r in sv.items(db)}
    assert states == {"Missing attributes": sv.OPEN, "Shop policies incomplete": sv.OPEN}


def test_the_route_is_operator_guarded():
    tmp = tempfile.mkdtemp(prefix="fb4_sv_")
    os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(tmp, 'sv.db')}"
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(tmp, "artifacts")
    os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
    from fastapi.testclient import TestClient

    from brambleloop.app import main

    main.db.create_all()
    client = TestClient(main.app)
    body = {"observed_at": T0.isoformat(), "items": [], "complete": True}
    os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)
    assert client.post("/api/search-visibility", json=body).status_code == 503
    os.environ["BRAMBLELOOP_OPS_TOKEN"] = TOKEN
    try:
        assert client.post("/api/search-visibility", json=body,
                           headers={"Authorization": "Bearer wrong"}).status_code == 401
        r = client.post("/api/search-visibility", json=body,
                        headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 409 and "live_listings" in r.json()["error"], r.json()
        with main.db.session() as s:
            s.add(Listing(product_slug="p", version="1", title="t", description="d", tags=[],
                          price_cad=8.0, etsy_listing_id="1234567"))
        r = client.post("/api/search-visibility",
                        json={**body, "items": [ITEM]},
                        headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200, r.json()
        assert r.json()["opened"]
        state = client.get("/api/search-visibility").json()
        assert len(state["open"]) == 1 and state["status"] == "READ"
    finally:
        os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)


def _cards(db):
    from sqlalchemy import select

    from brambleloop.runtime.storefront_watch import CARD_KEY

    with db.session() as s:
        return [(c.done, c.action) for c in s.scalars(
            select(OwnerAction).where(OwnerAction.requirement_key == CARD_KEY))]


def test_the_watch_is_inert_in_shadow_and_daily_for_seven_days_after():
    from brambleloop.runtime import storefront_watch as w
    from brambleloop.runtime.worker import CADENCES

    assert any(c[2] == w.ACTION for c in CADENCES)
    db = _db()
    out = w.watch(db, phase=Phase.SHADOW, now=T0)
    assert out["active"] is False and _cards(db) == []
    out = w.watch(db, phase=Phase.LIMITED_PRODUCTION, now=T0)
    assert out["active"] and out["day"] == 1 and len(_cards(db)) == 1
    # de-duplicated: the same day, or the next with the card still open, adds nothing
    w.watch(db, phase=Phase.LIMITED_PRODUCTION, now=T0 + timedelta(hours=3))
    w.watch(db, phase=Phase.LIMITED_PRODUCTION, now=T0 + timedelta(days=1))
    assert len(_cards(db)) == 1
    # a reading recorded today answers the open card
    sv.record_reading(db, observed_at=T0 + timedelta(days=1, hours=1), items=[], complete=True)
    w.watch(db, phase=Phase.LIMITED_PRODUCTION, now=T0 + timedelta(days=1, hours=2))
    assert _cards(db)[0][0] is True
    # the next day raises a fresh card
    out = w.watch(db, phase=Phase.LIMITED_PRODUCTION, now=T0 + timedelta(days=2))
    assert out["card_raised"] and len(_cards(db)) == 2
    # the window is anchored at the first observation and ends after seven days
    out = w.watch(db, phase=Phase.PRODUCTION, now=T0 + timedelta(days=7))
    assert out["active"] is False and "ended" in out["why"]


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback

                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
