"""W4-ETSYREVIEW: F-599 -- an Etsy API document change queues one batched owner review card.

Coordinator ruling 2026-10-12: the review is a non-interrupting owner-action card in the
existing queue, batched with the Etsy-account decisions, with exact action / reason / cost /
minutes / consequence. Fixture documents only; no network, no Etsy write.
Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_etsyreview.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_etsyreview_")

from sqlalchemy import select  # noqa: E402

import test_w4_fm2_surface_reverify as fx  # noqa: E402
from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import OwnerAction  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402

NOW = datetime(2026, 10, 12, tzinfo=timezone.utc)
STEP = timedelta(days=etsy_ops.OPENAPI_REVERIFY_DAYS + 1)
_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _cards(db):
    with db.session() as s:
        return [(r.id, r.done, r.minutes, r.max_cost_cad, r.reason, r.consequence_of_delay)
                for r in s.scalars(select(OwnerAction).where(
                    OwnerAction.requirement_key == etsy_ops.OPENAPI_REVIEW_KEY))]


def test_an_unchanged_document_queues_nothing():
    db = _db()
    etsy_ops.reverify_openapi(db, transport=fx._Transport(body=fx._document()), now=NOW)
    etsy_ops.reverify_openapi(db, transport=fx._Transport(body=fx._document()), now=NOW + STEP)
    assert _cards(db) == []


def test_a_change_queues_one_complete_card_and_a_later_change_restates_it():
    db = _db()
    etsy_ops.reverify_openapi(db, transport=fx._Transport(body=fx._document()), now=NOW)
    etsy_ops.reverify_openapi(db, transport=fx._Transport(
        body=fx._document(extra_text=" prose")), now=NOW + STEP)
    cards = _cards(db)
    assert len(cards) == 1, cards
    _id, done, minutes, cost, reason, consequence = cards[0]
    assert done is False and minutes == 15 and cost == 0.0
    assert "fingerprint" in reason and consequence
    etsy_ops.reverify_openapi(db, transport=fx._Transport(
        body=fx._document(add=["createAdCampaign"])), now=NOW + 2 * STEP)
    again = _cards(db)
    assert len(again) == 1 and again[0][0] == _id and "DRIFTED" in again[0][4], again


def test_the_card_is_batched_with_the_etsy_account_decisions_not_pushed():
    from brambleloop.ops import owner_queue

    db = _db()
    etsy_ops.reverify_openapi(db, transport=fx._Transport(
        body=fx._document(add=["createAdCampaign"])), now=NOW)
    card = {"requirement_key": etsy_ops.OPENAPI_REVIEW_KEY, "action": "x", "reason": "y",
            "max_spend_cad": 0.0, "minutes": 15, "consequence_of_no_action": "z"}
    assert owner_queue._store_batch(card) == "etsy_account"
    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == etsy_ops.OPENAPI_REVIEW_KEY))
        assert row is not None and "not a first-sale blocker" in row.blocks


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
