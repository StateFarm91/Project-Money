"""A realistic SYNTHETIC shadow dataset, for tests and the runtime proof only.

Drives the real writers -- `commerce.orders_ingest.ingest` with a fake receipt reader,
`finance.reconcile.apply` with fake Etsy payment-account ledger entries,
`finance.spend_report.record`, `finance.listing_costs.reserve`, `finance.reservations` --
on a throwaway SQLite database, so the accounting package is exercised against rows shaped
exactly as production would write them. No network: the readers are in-memory objects.

`seed` refuses any database that is not SQLite: this must never write synthetic sales,
fees or credentials into a real company database.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


class SyntheticRefused(RuntimeError):
    pass


class _Feed:
    def __init__(self, receipts, entries=None):
        self._r, self._e = receipts, entries

    def receipts(self, *, since):
        return list(self._r)


class _LedgerFeed(_Feed):
    def ledger_entries(self, *, min_created, max_created):
        return list(self._e or [])


def _receipt(rid, buyer, listing, cents, at, *, currency="CAD", lines=1, status="paid",
             refunds=None):
    ts = int(at.timestamp())
    return {"receipt_id": rid, "buyer_user_id": buyer, "status": status, "is_paid": True,
            "create_timestamp": ts, "update_timestamp": ts, "refunds": refunds or [],
            "transactions": [{"transaction_id": rid * 10 + i, "listing_id": listing,
                              "quantity": 1, "price": {"amount": cents, "divisor": 100,
                                                       "currency_code": currency}}
                             for i in range(lines)]}


def _entry(eid, ledger_type, ref_type, ref_id, cents, at):
    return {"entry_id": eid, "ledger_type": ledger_type, "reference_type": ref_type,
            "reference_id": str(ref_id), "amount": cents, "currency": "CAD",
            "created_timestamp": int(at.timestamp())}


def connect_order_source(db, *, read: bool = True) -> None:
    """The rows `orders_ingest.gate`/`source_state` read. Synthetic; temp DBs only."""
    from ...core.models import AuditLog, OAuthCredential

    _guard(db)
    with db.session() as s:
        s.add(AuditLog(actor="market_radar", action="etsy.probe", detail={"ok": True}))
        s.add(OAuthCredential(provider="etsy", refresh_token_sealed="sealed-synthetic",
                              token_fingerprint="synthetic0001",
                              scopes="listings_r shops_r transactions_r"))


def disconnect_order_source(db) -> None:
    """Simulate the owner's grant being revoked: the scope is gone from the stored grant."""
    from sqlalchemy import select

    from ...core.models import OAuthCredential

    _guard(db)
    with db.session() as s:
        for c in s.scalars(select(OAuthCredential)):
            c.scopes = "listings_r shops_r"


def _guard(db):
    url = str(getattr(getattr(db, "engine", None), "url", ""))
    if not url.startswith("sqlite"):
        raise SyntheticRefused("synthetic accounting data is only ever written to a "
                               "throwaway SQLite database")


def seed(db, *, now: datetime | None = None) -> dict:
    """Two months of a small shop. Returns the references it wrote."""
    from ...commerce import orders_ingest
    from .. import reconcile, reservations, spend_report

    _guard(db)
    now = now or datetime.now(timezone.utc)
    prev = (now.replace(day=1) - timedelta(days=10)).replace(hour=12)
    cur = now - timedelta(days=2)
    connect_order_source(db)
    receipts = [
        _receipt(1001, 501, 9001, 1200, prev),                       # CA$12 pattern
        _receipt(1002, 502, 9002, 850, prev + timedelta(days=1)),    # CA$8.50
        _receipt(1003, 503, 9001, 1200, prev + timedelta(days=2), lines=2),  # bundle of 2
        _receipt(1004, 504, 9003, 900, prev + timedelta(days=3), currency="USD"),
        _receipt(1005, 505, 9002, 850, cur, status="partially refunded",
                 refunds=[{"amount": {"amount": 400, "divisor": 100,
                                      "currency_code": "CAD"}}]),
        _receipt(1006, 506, 9001, 1200, cur, status="fully refunded"),
        _receipt(1007, 507, 9003, 1500, cur + timedelta(hours=3)),
    ]
    # Etsy charged fees for the first receipts (transaction + processing), read later.
    entries = [
        _entry(70001, "transaction", "transaction", 10010, -78, prev),
        _entry(70002, "payment_processing_fee", "receipt", 1001, -61, prev),
        _entry(70003, "transaction", "transaction", 10020, -55, prev),
        _entry(70004, "payment_processing_fee", "receipt", 1002, -50, prev),
    ]
    ing = orders_ingest.ingest(db, reader=_LedgerFeed(receipts, entries), now=now)
    rec = reconcile.apply(db, entries)
    # Operating spend, as the gateways record it.
    rows = []
    for i, (kind, amt, prov, model, purpose, slug, dept, at) in enumerate([
            ("llm", 0.4231, "anthropic", "claude-opus", "pattern_validation", "moss-stitch-cowl",
             "product", prev),
            ("llm", 0.0179, "anthropic", "claude-haiku", "seo_copy", "moss-stitch-cowl",
             "growth", prev + timedelta(days=1)),
            ("image", 0.32, "openai", "gpt-image", "hero_render", "granny-square-tote",
             "design", prev + timedelta(days=2)),
            ("llm", 1.1042, "anthropic", "claude-opus", "trend_research", "", "intel",
             cur - timedelta(days=1)),
            ("image", 0.64, "bfl", "flux", "hero_render", "granny-square-tote", "design",
             cur),
            ("hosting", 7.0, "railway", "", "hosting", "", "ops", prev.replace(day=1)),
            ("benchmark", 6.5, "etsy", "", "benchmark_purchase", "", "intel",
             prev + timedelta(days=4)),
    ]):
        cid = spend_report.record(db, agent=f"{dept}_agent", amount_cad=amt, purpose=purpose,
                                  provider=prov, model=model, department=dept,
                                  product_slug=slug, kind=kind, estimated_cad=round(amt * 1.1, 4),
                                  detail={"price_basis": "measured",
                                          "charge_id": f"syn-{kind}-{i}"})
        rows.append(cid)
    from ...core.models import CostEntry

    with db.session() as s:
        for cid, at in zip(rows, [prev, prev + timedelta(days=1), prev + timedelta(days=2),
                                  cur - timedelta(days=1), cur, prev.replace(day=1),
                                  prev + timedelta(days=4)]):
            s.get(CostEntry, cid).at = at
        # A modelled listing-fee exposure (written by listing_costs.reserve in production).
        s.add(CostEntry(agent="store_operator", kind="etsy_listing_fee", amount_cad=0.28,
                        estimated_cad=0.28, at=cur,
                        detail={"listing_id": "9003", "basis": "modelled",
                                "state": "reserved_unreconciled"}))
    rid = reservations.reserve(db, amount_cad=0.75, agent="product_agent",
                               purpose="pattern_validation", ttl_seconds=3600, now=now)
    from sqlalchemy import select

    from ...core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="cfo", action="commerce.orders_ingested",
                       detail={"ran": True, "reading": "measured", "synthetic": True}, at=now))
    return {"ingest": {k: ing.get(k) for k in ("reading", "written", "reconciled", "held")
                       if k in ing},
            "fees_applied": {k: rec.get(k) for k in ("applied_orders", "unmatched")
                             if k in rec},
            "cost_rows": rows, "reservation": rid, "prev_period": prev.strftime("%Y-%m"),
            "current_period": now.strftime("%Y-%m")}


def runtime_proof(out_dir: str) -> dict:
    """Seed a temp SQLite DB, run the Accountant cycle, and write evidence files.

    `python3 -m brambleloop.finance.accounting.shadow_dataset <out_dir>` (PYTHONPATH=src).
    Writes E_trial_balance.json, E_drill_profit.json, E_summary.json, E_books_agreement.json,
    E_duplicate_injection.json, E_spend_challenge.json and E_cycle.json.
    """
    import json
    import tempfile
    from pathlib import Path

    from ...agents.registry import Registry
    from ...core.db import Database
    from . import controller, dashboard, policy, posting_rules, reconciliation, views

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="acct_proof_")
    db = Database(f"sqlite:///{tmp}/shadow.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    now = datetime.now(timezone.utc)
    seeded = seed(db, now=now)
    cycle = controller.run_cycle(db, now=now)
    tb = views.trial_balance(db)
    tb_prev = views.trial_balance(db, period=seeded["prev_period"])
    agree = reconciliation.compare_with_books(db, until=now)
    summ = dashboard.summary(db, now=now)
    drill = dashboard.drill(db, "profit", now=now)
    # Section 95 injection on the same dataset: duplicate payment, fee and refund lines.
    t = now - timedelta(days=1)
    before = views.accrual(db)["_micros"]
    reconciliation.import_statement(db, "etsy_ledger", [
        {"external_id": "proof-fee-1", "at": t, "kind": "fee", "amount": -0.78,
         "reference": "1001"},
        {"external_id": "proof-refund-1", "at": t, "kind": "refund", "amount": -4.0,
         "reference": "1005"},
        {"external_id": "proof-payout-1", "at": t, "kind": "payout", "amount": -20.0,
         "reference": "payout-A"}], now=now)
    dup = reconciliation.import_statement(db, "etsy_ledger", [
        {"external_id": "proof-fee-1-dup", "at": t, "kind": "fee", "amount": -0.78,
         "reference": "1001"},
        {"external_id": "proof-refund-1-dup", "at": t, "kind": "refund", "amount": -4.0,
         "reference": "1005"},
        {"external_id": "proof-payout-1-dup", "at": t, "kind": "payout", "amount": -20.0,
         "reference": "payout-A"}], now=now)
    reconciliation.match(db, now=now)
    posting_rules.post_all(db, now=now)
    after = views.accrual(db)["_micros"]
    challenge = policy.check_spend(db, {
        "proposer": "growth", "kind": "ads", "amount_cad": 40.0,
        "purpose": "Etsy Ads test for the moss stitch cowl", "product_slug": "moss-stitch-cowl",
        "expected_contribution_cad": 20.0}, now=now)
    files = {
        "E_cycle.json": {"seeded": seeded, "cycle": cycle},
        "E_trial_balance.json": {"all_time": tb, "previous_period": tb_prev},
        "E_books_agreement.json": agree,
        "E_summary.json": summ,
        "E_drill_profit.json": {**drill, "rows": drill["rows"][:40],
                                "rows_total": len(drill["rows"])},
        "E_duplicate_injection.json": {
            "duplicates_flagged": dup["duplicates"],
            "statement_lines": reconciliation.statement_lines(db),
            "accrual_micros_before": before, "accrual_micros_after": after,
            "unchanged": before == after},
        "E_spend_challenge.json": challenge,
    }
    for name, body in files.items():
        (out / name).write_text(json.dumps(body, indent=2, default=str))
    return {"dir": str(out), "files": sorted(files), "db": f"{tmp}/shadow.sqlite"}


if __name__ == "__main__":  # pragma: no cover - runtime proof entry point
    import sys

    print(runtime_proof(sys.argv[1] if len(sys.argv) > 1 else "evidence"))
