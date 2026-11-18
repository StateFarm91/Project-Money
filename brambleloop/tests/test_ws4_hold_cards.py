"""WS4 §4.2: a live HOLD becomes one deduplicated owner card (M6 item 9).

The card leads to today's per-product approval, is keyed to the exact release (re-holding
restates it; a new release supersedes it), and closes on evidence. Shadow runs never open
cards, and nothing here can sign or issue.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select, update  # noqa: E402

from brambleloop.core import owner_grant_keys  # noqa: E402
from brambleloop.core.models import AuditLog, Listing, OwnerAction  # noqa: E402
from brambleloop.ops import owner_queue  # noqa: E402
from brambleloop.ops import standing_issuer as SI  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from test_ws4_issuer_shadow import SLUG, VERSION, _release  # noqa: E402
from test_ws4_policy_object import (NOW, _ModeT, _activate_raw, _approve, _db,  # noqa: E402
                                    _restore, content)

REL_A, REL_B = "a" * 64, "b" * 64


def _cards(db, *, open_only=True):
    with db.session() as s:
        q = select(OwnerAction).where(OwnerAction.requirement_key.like(
            f"{SI.HOLD_KEY_PREFIX}%"))
        if open_only:
            q = q.where(OwnerAction.done == False)  # noqa: E712
        return [(r.requirement_key, r.state, r.action, r.reason) for r in s.scalars(q)]


def _held_rows(db):
    with db.session() as s:
        return [dict(r.detail or {}) for r in s.scalars(select(AuditLog).where(
            AuditLog.action == SI.HELD))]


def test_a_hold_writes_its_row_and_one_card_leading_to_the_per_product_approval():
    try:
        db, c = _db(), content()
        out = SI.record_hold(db, slug=SLUG, version=VERSION, release=REL_A,
                             reasons=["price: FAIL"], content=c, approval_id=7, now=NOW)
        assert out["key"] == f"standing_policy.hold:{SLUG}@{VERSION}:{REL_A[:12]}"
        cards = _cards(db)
        assert len(cards) == 1 and cards[0][1] == owner_queue.OPEN, cards
        assert "publication.preview" in cards[0][2] and "publication.approve" in cards[0][2]
        assert "price: FAIL" in cards[0][3] and c["owner_statement_digest"][:12] in cards[0][3]
        row = _held_rows(db)[0]
        assert row["release"] == REL_A and row["reasons"] == ["price: FAIL"]
        assert row["policy_version"] == c["version"] and row["approval_id"] == 7
        assert row["owner_statement_digest"] == c["owner_statement_digest"]
    finally:
        _restore()


def test_re_holding_the_same_release_restates_one_card():
    try:
        db, c = _db(), content()
        first = SI.record_hold(db, slug=SLUG, version=VERSION, release=REL_A,
                               reasons=["x: FAIL"], content=c, now=NOW)
        second = SI.record_hold(db, slug=SLUG, version=VERSION, release=REL_A,
                                reasons=["y: UNKNOWN"], content=c, now=NOW)
        assert first["card_id"] == second["card_id"]
        cards = _cards(db)
        assert len(cards) == 1 and "y: UNKNOWN" in cards[0][3], cards
        assert len(_held_rows(db)) == 2
    finally:
        _restore()


def test_a_new_release_supersedes_the_old_card():
    try:
        db, c = _db(), content()
        SI.record_hold(db, slug=SLUG, version=VERSION, release=REL_A, reasons=["x"],
                       content=c, now=NOW)
        out = SI.record_hold(db, slug=SLUG, version=VERSION, release=REL_B, reasons=["x"],
                             content=c, now=NOW)
        assert out["superseded"] == [SI.hold_key(SLUG, VERSION, REL_A)]
        open_ = _cards(db)
        assert [k for k, *_ in open_] == [SI.hold_key(SLUG, VERSION, REL_B)], open_
        closed = [x for x in _cards(db, open_only=False) if x[0].endswith(REL_A[:12])]
        assert closed[0][1] == owner_queue.SUPERSEDED, closed
        # Another product's card is untouched.
        SI.record_hold(db, slug="other-mat", version=VERSION, release=REL_A, reasons=["x"],
                       content=c, now=NOW)
        assert len(_cards(db)) == 2
    finally:
        _restore()


def test_cards_close_on_evidence():
    try:
        db, c = _db(), content()
        _release(db, release=REL_A)
        SI.record_hold(db, slug=SLUG, version=VERSION, release=REL_A, reasons=["x"],
                       content=c, now=NOW)
        assert SI.close_settled_holds(db, now=NOW)["closed"] == []      # still the candidate
        SI.record_hold(db, slug="gone-mat", version=VERSION, release=REL_B, reasons=["x"],
                       content=c, now=NOW)
        out = SI.close_settled_holds(db, now=NOW)
        assert out["closed"] == [SI.hold_key("gone-mat", VERSION, REL_B)], out
        # The owner published it: satisfied.
        with db.session() as s:
            s.execute(update(Listing).where(Listing.product_slug == SLUG)
                      .values(etsy_listing_id="4400123"))
        SI.close_settled_holds(db, now=NOW)
        states = {k: st for k, st, *_ in _cards(db, open_only=False)}
        assert states[SI.hold_key(SLUG, VERSION, REL_A)] == owner_queue.SATISFIED, states
        assert states[SI.hold_key("gone-mat", VERSION, REL_B)] == owner_queue.SUPERSEDED
        assert _cards(db) == []
    finally:
        _restore()


def test_without_an_effective_policy_decide_writes_nothing():
    try:
        db, c = _db(), content()
        _approve(db, c)
        _release(db, release=REL_A)
        out = SI.decide(db, SLUG, VERSION, REL_A, now=NOW)
        assert out["decision"] is None and out["card"] is None, out
        assert _cards(db) == [] and _held_rows(db) == []
    finally:
        _restore()


def test_a_live_hold_on_an_effective_policy_opens_its_card():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        _release(db, release=REL_A)
        with _ModeT():
            out = SI.decide(db, SLUG, VERSION, REL_A, now=NOW + timedelta(days=1))
        assert out["decision"] == "HOLD" and out["card"]["key"] == SI.hold_key(
            SLUG, VERSION, REL_A), out
        # Live, the activation-time facts are read for real; their readers are Mode T, so
        # they hold rather than being assumed as in shadow.
        assert any(r.startswith("kill_switch: UNKNOWN") for r in out["reasons"]), out
        assert _held_rows(db)[0]["approval_id"] == a
    finally:
        _restore()


def test_a_live_in_policy_decision_is_refused_and_never_signed():
    try:
        db, c = _db(), content()
        a = _approve(db, c)
        _activate_raw(db, a, c)
        _release(db, release=REL_A)

        def all_pass(db_, slug, version, release, content_, *, shadow=True):
            from test_ws4_boundary import facts

            return facts(slug=slug)

        def no_signing(*_a, **_k):
            raise AssertionError("decide tried to sign")

        with _ModeT(), patch.object(SI, "read_facts", all_pass), \
                patch.object(sp, "_sign", no_signing), \
                patch.object(owner_grant_keys, "sign", no_signing):
            out = SI.decide(db, SLUG, VERSION, REL_A, now=NOW + timedelta(days=1))
        assert out["decision"] == "ISSUE_REFUSED" and out["card"] is None, out
        assert _cards(db) == [] and _held_rows(db) == []
    finally:
        _restore()


def test_shadow_runs_never_open_cards():
    try:
        db, c = _db(), content()
        _approve(db, c)
        _release(db, release=REL_A)
        assert SI.shadow_run(db, now=NOW)["recorded"] == 1
        assert _cards(db) == [] and _held_rows(db) == []
    finally:
        _restore()


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
