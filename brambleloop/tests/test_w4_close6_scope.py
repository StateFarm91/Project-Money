"""W4-CLOSE6: F-872 Etsy Scope Reauthorization -- proven by readback before trusted use.

  F-872  "Required OAuth scopes such as transactions_r are explicitly reauthorized and proven
          by readback before trusted use."

The mapping held this row on "readback of a real receipt after reauthorisation not yet
possible". In production b931d17 the owner re-authorised:
- Until 2026-10-13 every `commerce.orders_ingested` run read UNMEASURED with zero network
  calls; the gate was closed.
- From 2026-10-13T03:28Z every run reads `measured` after an authenticated getShopReceipts
  read (two calls, zero receipts: the shop has had no sale).

(research/final_build/w4/evidence_CLOSE6/prod_api_orders_ingested_20261020T1321Z.json.)

These tests pin "before trusted use":
- no receipt is read unless the stored grant lists the scope AND a working credential has been
  demonstrated;
- a read Etsy refuses for scope is never trusted;
- a read that worked, even of zero receipts, is the readback that clears a re-authorisation
  request.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close6_scope.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_money_truth as mt  # noqa: E402  (its fixtures: _db, _open_gate, Revoked)
from sqlalchemy import select  # noqa: E402

from brambleloop.commerce import orders_ingest  # noqa: E402
from brambleloop.core.models import AuditLog, OAuthCredential, OwnerAction  # noqa: E402


class Empty:
    """An authenticated receipt read that worked and found nothing (production today)."""

    calls = 0

    def receipts(self, *, since):
        Empty.calls += 1
        return []


class Untouchable:
    calls = 0

    def receipts(self, *, since):
        Untouchable.calls += 1
        raise AssertionError("a receipt read was attempted before the scope was proven")


def test_no_receipt_is_read_until_scope_and_a_working_credential_are_both_proven():
    for grant_scope, probe in ((False, True), (True, False), (False, False)):
        db = mt._db()
        with db.session() as s:
            if probe:
                s.add(AuditLog(actor="market_radar", action="etsy.probe", detail={"ok": True}))
            s.add(OAuthCredential(provider="etsy", refresh_token_sealed="sealed",
                                  token_fingerprint="abcd1234",
                                  scopes="listings_r shops_r"
                                  + (" transactions_r" if grant_scope else "")))
        assert orders_ingest.gate(db)["open"] is False, (grant_scope, probe)
        got = orders_ingest.ingest(db, reader=Untouchable())
        assert got["ran"] is False and got["reading"] == "UNMEASURED", got
    assert Untouchable.calls == 0


def test_a_scope_refusal_is_never_trusted_and_a_working_read_clears_the_request():
    db = mt._db()
    mt._open_gate(db)
    refused = orders_ingest.ingest(db, reader=mt.Revoked(
        "this token cannot perform getShopReceipts: it is missing ['transactions_r']."))
    assert refused["reading"] == "UNMEASURED" and refused["ran"] is False
    assert refused["auth_failure"]["failure_class"] == "scope_drift"
    with db.session() as s:
        assert s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == orders_ingest.AUTH_ACTION_KEY,
            OwnerAction.done == False)) is not None  # noqa: E712
    ok = orders_ingest.ingest(db, reader=Empty())
    assert ok["ran"] is True and ok["reading"] == "measured" and ok["receipts"] == 0, ok
    with db.session() as s:
        still = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == orders_ingest.AUTH_ACTION_KEY,
            OwnerAction.done == False))  # noqa: E712
    assert still is None, "the readback that worked closes the re-authorisation request"


def test_production_switched_from_unproven_to_read_back_after_reauthorisation():
    ev = json.loads((ROOT / "research/final_build/w4/evidence_CLOSE6/"
                     "prod_api_orders_ingested_20261020T1321Z.json").read_text())
    rows = sorted(ev["rows"], key=lambda r: r["at"])
    assert len(rows) >= 10
    first_measured = next(i for i, r in enumerate(rows) if r["detail"]["reading"] == "measured")
    before, after = rows[:first_measured], rows[first_measured:]
    assert before and all(r["detail"]["reading"] == "UNMEASURED"
                          and r["detail"]["network_calls"] == 0 for r in before)
    assert after and all(r["detail"]["reading"] == "measured"
                         and r["detail"]["network_calls"] > 0 for r in after)


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 3, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
