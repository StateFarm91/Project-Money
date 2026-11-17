"""WS5 E6: an unknown draft-create outcome is resolved from the shop's drafts (option B).

The resolver matches on content and never adopts on ambiguity:
* exactly one draft with the certified title and price, created after the intent, is adopted
  through `draft_intent.checkpoint`, and the incident resolves;
* two such drafts, a price mismatch, or a draft older than the intent are escalated to one
  owner card, and nothing is adopted;
* no candidate is released only after two complete empty reads at least 30 minutes apart;
* an unread shop changes nothing;
* a fresh CREATING intent (a create in flight) is never touched; a stale one is.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws5_e6_draft_resolver.py
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

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Listing, OwnerAction  # noqa: E402
from brambleloop.publish import draft_intent as DI  # noqa: E402
from brambleloop.publish import draft_resolver as R  # noqa: E402

NOW = datetime(2026, 11, 17, 3, 0, tzinfo=timezone.utc)
SLUG, VERSION, RELEASE = "linen-ridge-dishcloth", "1.0.0", "r" * 64
TITLE, PRICE = "Linen Ridge Dishcloth Crochet Pattern", 6.5


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='e6_')}/e6.sqlite")
    db.create_all()
    return db


def _audit(db):
    def write(action, artifact=None, detail=None, **_kw):
        with db.session() as s:
            s.add(AuditLog(actor="test", action=action, artifact=artifact, detail=detail or {}))
    return write


def _stuck(db, *, state="RECONCILE_REQUIRED", at=NOW - timedelta(minutes=20), title=TITLE):
    """A certified listing whose create outcome is unknown, with its halting incident."""
    with db.session() as s:
        s.add(Listing(product_slug=SLUG, version=VERSION, title=title, description="d",
                      tags=[], price_cad=PRICE, release_hash=RELEASE, state="draft"))
    key, token = DI.claim(db, slug=SLUG, version=VERSION, release=RELEASE,
                          content_digest="c" * 64)
    with db.session() as s:
        row = s.get(DI.DraftIntent, key)
        row.state, row.at = state, at
    if state == "RECONCILE_REQUIRED":
        DI.reconcile(db, SLUG, VERSION, "fixture: interrupted create")
    return key


def _draft(lid, *, title=TITLE, price=PRICE, created=NOW - timedelta(minutes=15)):
    return {"listing_id": lid, "state": "draft", "title": title,
            "price": {"amount": int(round(price * 100)), "divisor": 100, "currency_code": "CAD"},
            "original_creation_timestamp": int(created.timestamp())}


def _incident(db):
    with db.session() as s:
        return s.scalar(select(Incident).where(Incident.signature.like("draft-create:%")))


def _cards(db):
    with db.session() as s:
        return list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key.like(R.CARD_PREFIX + "%"))))


def _actions(db, action):
    with db.session() as s:
        return list(s.scalars(select(AuditLog).where(AuditLog.action == action)))


def test_exactly_one_content_match_is_adopted_through_the_checkpoint():
    db = _db()
    key = _stuck(db)
    out = R.resolve(db, [_draft("9001"), _draft("9002", title="Something Else")],
                    audit=_audit(db), now=NOW)
    assert [i["outcome"] for i in out["intents"]] == ["adopted"], out
    with db.session() as s:
        intent = s.get(DI.DraftIntent, key)
        listing = s.scalar(select(Listing).where(Listing.product_slug == SLUG))
        assert (intent.remote_id, intent.state) == ("9001", "CREATED")
        assert listing.etsy_listing_id == "9001"
    assert _incident(db).resolved is True
    assert len(_actions(db, R.ADOPTED)) == 1 and out["writes_to_etsy"] == 0


def test_two_identical_drafts_are_escalated_never_adopted():
    db = _db()
    key = _stuck(db)
    out = R.resolve(db, [_draft("9001"), _draft("9002")], audit=_audit(db), now=NOW)
    assert out["intents"][0]["outcome"] == "escalated"
    assert sorted(out["intents"][0]["candidates"]) == ["9001", "9002"]
    with db.session() as s:
        assert s.get(DI.DraftIntent, key).remote_id is None
    inc = _incident(db)
    assert inc.resolved is False and len(inc.detail["candidates"]) == 2
    cards = _cards(db)
    assert len(cards) == 1 and "9001" in cards[0].action and "9002" in cards[0].action
    # A second run restates the one card; it never opens another.
    R.resolve(db, [_draft("9001"), _draft("9002")], audit=_audit(db), now=NOW)
    assert len([c for c in _cards(db) if not c.done]) == 1


def test_a_price_mismatch_or_an_older_draft_is_escalated_not_adopted():
    for drafts in ([_draft("9001", price=7.0)],
                   [_draft("9001", created=NOW - timedelta(hours=3))],
                   [_draft("9001"), _draft("9002", price=9.0)]):
        db = _db()
        key = _stuck(db)
        out = R.resolve(db, drafts, audit=_audit(db), now=NOW)
        assert out["intents"][0]["outcome"] == "escalated", (drafts, out)
        with db.session() as s:
            assert s.get(DI.DraftIntent, key).remote_id is None


def test_no_candidate_is_released_only_after_two_empty_reads_thirty_minutes_apart():
    db = _db()
    key = _stuck(db)
    first = R.resolve(db, [], audit=_audit(db), now=NOW)
    assert first["intents"][0]["outcome"] == "awaiting_second_read"
    soon = R.resolve(db, [], audit=_audit(db), now=NOW + timedelta(minutes=10))
    assert soon["intents"][0]["outcome"] == "awaiting_second_read"
    with db.session() as s:
        assert s.get(DI.DraftIntent, key) is not None
    assert _incident(db).resolved is False
    late = R.resolve(db, [], audit=_audit(db), now=NOW + timedelta(minutes=31))
    assert late["intents"][0]["outcome"] == "released"
    with db.session() as s:
        assert s.get(DI.DraftIntent, key) is None
    assert _incident(db).resolved is True and len(_actions(db, R.RELEASED)) == 1


def test_the_release_thresholds_are_pinned():
    assert (R.EMPTY_READS, R.EMPTY_SPAN) == (2, timedelta(minutes=30))
    assert (R.CREATE_SKEW, R.STALE_CREATING) == (timedelta(minutes=10), timedelta(hours=2))


def test_a_listing_rebound_to_another_release_is_escalated_not_matched():
    db = _db()
    key = _stuck(db)
    with db.session() as s:
        s.scalar(select(Listing).where(Listing.product_slug == SLUG)).release_hash = "x" * 64
    out = R.resolve(db, [_draft("9001")], audit=_audit(db), now=NOW)
    assert out["intents"][0]["outcome"] == "escalated", out
    assert "certified release" in _incident(db).detail["resolver"]
    with db.session() as s:
        assert s.get(DI.DraftIntent, key).remote_id is None


def test_a_draft_already_bound_elsewhere_is_never_a_candidate():
    db = _db()
    _stuck(db)
    with db.session() as s:
        s.add(Listing(product_slug="other", version="1.0.0", title=TITLE, description="d",
                      tags=[], price_cad=PRICE, etsy_listing_id="9001"))
    out = R.resolve(db, [_draft("9001")], audit=_audit(db), now=NOW)
    assert out["intents"][0]["outcome"] == "awaiting_second_read", out


def test_an_unread_shop_changes_nothing():
    db = _db()
    key = _stuck(db)

    class Broken:
        credentials = object()

        def get_shop_listings(self, **_kw):
            raise RuntimeError("network down")

    out = R.run(db, audit=_audit(db), client=Broken(), now=NOW)
    assert out["read"] is False and "network down" in out["why"]
    with db.session() as s:
        row = s.get(DI.DraftIntent, key)
        assert row.remote_id is None and not (row.detail or {}).get("empty_reads")
    assert _incident(db).resolved is False


def test_a_read_at_the_paging_limit_is_treated_as_incomplete():
    db = _db()
    key = _stuck(db)

    class Full:
        credentials = object()

        def get_shop_listings(self, **kw):
            assert (kw["limit"], kw["max_pages"]) == (R.PAGE, R.MAX_PAGES)
            return [_draft(str(10000 + i), title="Other") for i in range(R.PAGE * R.MAX_PAGES)]

    out = R.run(db, audit=_audit(db), client=Full(), now=NOW)
    assert out["read"] is False and "incomplete" in out["why"], out
    with db.session() as s:
        assert not (s.get(DI.DraftIntent, key).detail or {}).get("empty_reads")


def test_a_fresh_create_in_flight_is_untouched_and_a_stale_one_is_resolved():
    db = _db()
    _stuck(db, state="CREATING", at=NOW - timedelta(minutes=5))
    assert R.unresolved(db, now=NOW) == []
    out = R.run(db, audit=_audit(db), client=None, now=NOW)
    assert out["read"] is False and out["intents"] == []
    db = _db()
    _stuck(db, state="CREATING", at=NOW - timedelta(hours=3))
    out = R.resolve(db, [_draft("9001", created=NOW - timedelta(hours=2, minutes=55))],
                    audit=_audit(db), now=NOW)
    assert out["intents"][0]["outcome"] == "adopted", out


def test_the_job_is_registered_scheduled_and_read_only():
    from brambleloop.agents.registry import DEFAULT_AGENTS
    from brambleloop.authority import classes
    from brambleloop.runtime import pipeline  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import CADENCES, handlers

    assert handlers.get("store.draft_reconcile") is not None
    assert ("store_draft_reconcile", "orchestrator", "store.draft_reconcile",
            3600) in CADENCES
    orch = next(a for a in DEFAULT_AGENTS if a["name"] == "orchestrator")
    assert "store.draft_reconcile" in orch["allowed_job_types"]
    assert classes.JOB_CLASS["store.draft_reconcile"] == classes.JOB_CLASS["store.live_drift"]


# ---- review 6954619488 (E6 HIGH + MEDIUM) ------------------------------------------------------

def test_an_html_escaped_title_from_etsy_still_matches_the_certified_title():
    """Etsy returns titles HTML-escaped; the held draft must still be found, never released."""
    db = _db()
    title = "Hat & Scarf Set Crochet Pattern"
    key = _stuck(db, title=title)
    for etsy_title in ("Hat &amp; Scarf Set Crochet Pattern",
                       "Hat &amp;  Scarf Set   Crochet Pattern "):
        assert R.norm_title(etsy_title) == R.norm_title(title)
    out = R.resolve(db, [_draft("9101", title="Hat &amp; Scarf Set Crochet Pattern")],
                    audit=_audit(db), now=NOW)
    assert [i["outcome"] for i in out["intents"]] == ["adopted"], out
    with db.session() as s:
        assert s.get(DI.DraftIntent, key).remote_id == "9101"
    # A title differing in any letter is still a different title.
    assert R.norm_title("Hat & Scarf Set") != R.norm_title("Hat & Scarves Set")


def test_a_listing_activated_by_hand_is_escalated_and_the_intent_is_never_released():
    db = _db()
    key = _stuck(db)
    active = {**_draft("9201"), "state": "active"}
    first = R.resolve(db, [active], audit=_audit(db), now=NOW)
    later = R.resolve(db, [active], audit=_audit(db), now=NOW + R.EMPTY_SPAN + timedelta(minutes=1))
    assert [i["outcome"] for i in first["intents"] + later["intents"]] == ["escalated",
                                                                           "escalated"]
    with db.session() as s:
        row = s.get(DI.DraftIntent, key)
        assert row is not None and row.remote_id is None and not (row.detail or {}).get(
            "empty_reads")
    assert _incident(db).resolved is False and len(_cards(db)) == 1
    assert "active" in _incident(db).detail["candidates"][0]["why"]
    assert not _actions(db, R.RELEASED)


def test_run_reads_every_listing_state_before_deciding():
    db = _db()
    _stuck(db)
    asked = []

    class Shop:
        credentials = object()

        def get_shop_listings(self, *, state, limit, max_pages):
            asked.append(state)
            # Etsy's rows carry their state; the resolver must not assume "draft".
            return [{**_draft("9301"), "state": "inactive"}] if state == "inactive" else []

    out = R.run(db, audit=_audit(db), client=Shop(), now=NOW)
    assert asked == list(R.LISTING_STATES) == ["draft", "active", "inactive", "expired",
                                               "sold_out"]
    assert [i["outcome"] for i in out["intents"]] == ["escalated"], out
    assert not _actions(db, R.RELEASED)


if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception:  # noqa: BLE001
                fails += 1
                print("FAIL", name)
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
