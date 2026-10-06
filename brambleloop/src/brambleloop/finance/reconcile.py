"""What Etsy actually charged, matched to the orders it was charged on (F-558, F-609, F-273).

Until this module, every sale's `fees_cad` was `commerce.pricing.fees()` -- a model of the
transaction and payment-processing fees, with the Offsite Ads, regulatory and currency
conversion fees explicitly unmodelled -- stored in the same column a charged fee would sit
in. The books then summed it as "platform fees". A modelled fee that reads as charged is the
most comfortable kind of wrong: it is close, it is plausible, and it is never checked.

Etsy's payment-account ledger (`getShopPaymentAccountLedgerEntries`, `transactions_r`) is
the record of what was charged. This module turns its entries into fee amounts per order:

* **classify** each entry by its `ledger_type` into a fee kind, a credit, or `unclassified`.
  An unclassified entry is never counted as a fee: guessing that an entry we do not
  recognise is a fee would move contribution on a guess.
* **match** fee entries to orders by `reference_id` -- a transaction-level entry to its
  line, a receipt-level entry shared across the receipt's lines by price.
* **apply incrementally**: each order keeps the entry ids already applied, so a re-read of
  an overlapping window adds nothing and an Offsite Ads fee posted days after the sale is
  added when it appears. The first measured entry *replaces* the modelled figure; the basis
  flips from `modelled` to `measured` on the order and on its ledger row.

An Offsite Ads fee is also the one piece of evidence of acquisition source a receipt-reading
system gets for free: Etsy charges it only on a sale it attributes to an offsite ad. It sets
`offsite_ad_attributed`, is deducted from contribution, and attributes the order.

UNVERIFIED against a live shop (no `transactions_r` grant yet): the `ledger_type` strings
and the minor-unit `amount` below are read from Etsy's OpenAPI document and community
examples. `LEDGER_AMOUNT_DIVISOR` and `_FEE_KINDS` are the two places to correct on the
first real read; an entry that does not match stays unclassified and is reported, never
silently dropped or silently counted.

**What that means for the figures (RC1 audit E4, E5).** Because the mapping is unverified,
a fee read through it is not `measured`:

* Classification is an explicit allow-list (`_FEE_EXACT`, `_REFUND_EXACT`). Nothing is
  matched by substring -- `transaction_fee_refund` once read as a customer refund. An
  unknown type is `unclassified`, is never counted, and opens `UNCLASSIFIED_SIGNATURE`.
* An order's fees are `measured` only when every `EXPECTED_PER_ORDER` component has posted
  AND an owner-recorded verification of this exact mapping exists (`mapping_verified`).
  With a component missing the order is `partial`: the posted components plus the modelled
  figure for each missing one. With all present but no verification it is `unverified`
  (the `unverified_mapping` basis; `fees_basis` is a 12-character column).
* A fee entry larger than `FEE_ANOMALY_SHARE` of the order's price (a unit error reads as
  100x) is held as anomalous -- not applied -- and opens `ANOMALY_SIGNATURE`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

# Etsy's ledger `amount` is an integer; the document does not state its unit and the
# balance examples read as minor units (cents). A dict-shaped amount ({amount, divisor}) is
# honoured as Money. UNVERIFIED -- see the module docstring.
LEDGER_AMOUNT_DIVISOR = 100

# ledger_type (lower-cased) -> fee kind. An explicit allow-list: matched by exact value only
# (RC1 audit E5). Substring matching once booked `transaction_fee_refund` as a customer refund.
_FEE_EXACT = {
    "transaction": "transaction_fee",
    "transaction_quantity": "transaction_fee",
    "shipping_transaction": "transaction_fee",
    "processing_fee": "processing_fee",
    "payment_processing_fee": "processing_fee",
    "offsite_ads_fee": "offsite_ads_fee",
    "regulatory_operating_fee": "regulatory_fee",
    "currency_conversion_fee": "currency_conversion_fee",
    # Listing fees reference a listing, not a receipt, so they match no order and are
    # reported as unmatched; the auto-renewal charged on a sale may reference its
    # transaction, and then it is that order's cost.
    "listing": "listing_fee",
    "renew_sold": "listing_fee",
    "renew_sold_auto": "listing_fee",
    "renew_expired": "listing_fee",
}
# ledger_type (lower-cased) -> a customer refund paid out of the shop's account.
_REFUND_EXACT = {"refund": "refund"}
FEE_KINDS = frozenset(_FEE_EXACT.values())
# Order fee bases that came from Etsy's ledger. `unverified` is the stored form of the
# `unverified_mapping` basis (the column holds 12 characters).
MEASURED, PARTIAL_BASIS, UNVERIFIED = "measured", "partial", "unverified"
UNVERIFIED_MAPPING = "unverified_mapping"
LEDGER_FEE_BASES = (MEASURED, PARTIAL_BASIS, UNVERIFIED)
# A single fee entry, or an order's ledger fees in total, above this share of the order's
# price is held as anomalous. Etsy's fees on a sale (transaction 6.5%, processing ~3% +
# fixed, Offsite Ads 12-15%, regulatory, conversion) do not approach half the price; a unit
# error (cents read as dollars) reads as 100x.
FEE_ANOMALY_SHARE = 0.5
MAPPING_VERIFIED_ACTION = "owner.etsy_ledger_mapping.verified"
UNCLASSIFIED_SIGNATURE = "finance.reconciliation.ledger_unclassified"
ANOMALY_SIGNATURE = "finance.reconciliation.ledger_anomaly"
# Both of these must be present for an order's fees to count as fully reconciled; with one
# the state is `partial` (still measured, but the other fee may not have posted yet).
EXPECTED_PER_ORDER = ("transaction_fee", "processing_fee")

RECONCILED = "matched_etsy_ledger"
PARTIAL = "partial_etsy_ledger"


def classify(entry: dict) -> str:
    """Fee kind, `refund`, or `unclassified` -- by the explicit allow-list only."""
    lt = str(entry.get("ledger_type") or "").strip().lower()
    if lt in _FEE_EXACT:
        return _FEE_EXACT[lt]
    if lt in _REFUND_EXACT:
        return _REFUND_EXACT[lt]
    return "unclassified"


def mapping_fingerprint() -> str:
    """A digest of the type allow-list and the amount unit. A verification recorded for one
    mapping does not carry over to a changed one."""
    import hashlib
    import json

    body = json.dumps({"fees": _FEE_EXACT, "refunds": _REFUND_EXACT,
                       "divisor": LEDGER_AMOUNT_DIVISOR}, sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def record_mapping_verification(db, *, by: str, evidence: str) -> dict:
    """The owner's record that a live ledger read confirmed these type strings and the unit.

    Until one exists for the current `mapping_fingerprint`, fees read through the mapping
    carry the `unverified_mapping` basis, never `measured`.
    """
    from ..core.models import AuditLog

    if not str(by or "").strip() or not str(evidence or "").strip():
        raise ValueError("a mapping verification needs who verified it and the evidence")
    detail = {"fingerprint": mapping_fingerprint(), "divisor": LEDGER_AMOUNT_DIVISOR,
              "fee_types": sorted(_FEE_EXACT), "refund_types": sorted(_REFUND_EXACT),
              "evidence": str(evidence)[:1000], "by": str(by)[:80]}
    with db.session() as s:
        s.add(AuditLog(actor="owner", action=MAPPING_VERIFIED_ACTION, detail=detail))
    return detail


def mapping_verified(db) -> bool:
    """Whether the owner recorded a verification of exactly the current mapping."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == MAPPING_VERIFIED_ACTION)
                       .order_by(AuditLog.id.desc()).limit(1))
        return bool(row is not None and row.actor == "owner"
                    and (row.detail or {}).get("fingerprint") == mapping_fingerprint())


def fee_basis_text(basis: str, kinds, missing) -> str:
    """The words the order's contribution basis uses for its fees, matching `basis`."""
    if basis == MEASURED:
        return "MEASURED fees (Etsy ledger, owner-verified mapping)"
    if basis == UNVERIFIED:
        return (f"Etsy-ledger fees under an UNVERIFIED type/unit mapping "
                f"({UNVERIFIED_MAPPING}); not measured")
    return (f"PARTIAL fees: Etsy ledger for {', '.join(sorted(kinds)) or 'none'}, MODELLED "
            f"for {', '.join(sorted(missing)) or 'held anomalous entries'}")


def amount(entry: dict) -> tuple[float, str] | None:
    """The entry's signed amount in its own currency, or None when it has none."""
    raw = entry.get("amount")
    currency = str(entry.get("currency") or "").upper()
    if isinstance(raw, dict) and "amount" in raw:
        divisor = float(raw.get("divisor") or 1) or 1.0
        return float(raw["amount"]) / divisor, str(raw.get("currency_code") or currency).upper()
    if isinstance(raw, (int, float)):
        return float(raw) / LEDGER_AMOUNT_DIVISOR, currency
    return None


def normalise(entries: Iterable[dict]) -> list[dict]:
    """Etsy ledger entries -> {entry_id, kind, reference_id, charge, currency, at}.

    `charge` is positive for money Etsy took (a fee debit is negative on the ledger) and
    negative for a fee credit/reversal.
    """
    out = []
    for e in entries or []:
        amt = amount(e)
        if amt is None or e.get("entry_id") is None:
            continue
        ts = e.get("created_timestamp") or e.get("create_date")
        out.append({
            "entry_id": str(e.get("entry_id")), "kind": classify(e),
            "ledger_type": str(e.get("ledger_type") or ""),
            "reference_type": str(e.get("reference_type") or ""),
            "reference_id": str(e.get("reference_id") or ""),
            "charge": round(-amt[0], 4), "currency": amt[1] or "CAD",
            "at": (datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                   if isinstance(ts, (int, float)) else None),
        })
    return out


def _to_cad(charge: float, currency: str, on) -> tuple[float, bool]:
    """(CAD amount, rate measured?) -- CAD passes through; others at the dated assumed rate."""
    if (currency or "CAD").upper() == "CAD":
        return charge, True
    from . import currency as fx

    converted = fx.to_reporting(fx.Money(charge, currency), fx.assumed_rate(on))
    rate = converted["rate"]
    return float(converted["reporting"]["amount"]), bool(rate and rate["measured"])


def apply(db, entries: Iterable[dict], *, source: str = "etsy_receipts") -> dict:
    """Apply measured Etsy fees to the orders (and their sale ledger rows) they belong to."""
    from sqlalchemy import select

    from ..core.models import LedgerEntry, Order
    from . import sources

    norm = normalise(entries)
    from . import listing_costs
    listing_fee_entries = listing_costs.ingest_actual(db, norm)
    fees = [e for e in norm if e["kind"] in FEE_KINDS]
    refund_entries = [e for e in norm if e["kind"] == "refund"]
    by_ref: dict[str, list[dict]] = {}
    for e in fees:
        by_ref.setdefault(e["reference_id"], []).append(e)

    applied_orders, matched_ids = [], set()
    attributions = []
    anomalies: list[dict] = []
    verified = mapping_verified(db)
    from ..commerce.pricing import fees as model_fees

    with db.session() as s:
        orders = [o for o in s.scalars(select(Order).where(Order.source == source))]
        by_receipt: dict[str, list] = {}
        for o in orders:
            rid = str((o.detail or {}).get("receipt_id") or "")
            if rid:
                by_receipt.setdefault(rid, []).append(o)
        for rid, group in by_receipt.items():
            receipt_entries = by_ref.get(rid, [])
            total_price = sum(float(o.price_cad or 0.0) for o in group) or 1.0
            for o in group:
                txn = o.external_ref.rsplit(":", 1)[-1]
                share = (float(o.price_cad or 0.0) / total_price) if len(group) > 1 else 1.0
                candidates = ([(e, 1.0) for e in by_ref.get(txn, [])]
                              + [(e, share) for e in receipt_entries])
                detail = dict(o.detail or {})
                done = set(detail.get("fee_entries") or [])
                new = [(e, w) for e, w in candidates if e["entry_id"] not in done]
                matched_ids.update(e["entry_id"] for e, _ in candidates)
                if not new:
                    continue
                price = float(o.price_cad or 0.0)
                cap = FEE_ANOMALY_SHARE * price
                on = (o.at or datetime.now(timezone.utc)).date()
                # Per-kind ledger components, cumulative over every applied entry. A row
                # measured before components were kept carries its total as one lump.
                comps = {k: float(v) for k, v in (detail.get("fee_components") or {}).items()}
                if not comps and done:
                    comps = {"legacy_ledger_total": float(o.fees_cad or 0.0)}
                kinds = set(detail.get("fee_kinds") or [])
                held_here, accepted, fx_assumed = [], [], False
                for e, w in new:
                    cad, measured_rate = _to_cad(e["charge"] * w, e["currency"], on)
                    if price <= 0 or abs(cad) > cap:
                        held_here.append((e, cad))
                    else:
                        accepted.append((e, cad, measured_rate))
                trial = dict(comps)
                for e, cad, _m in accepted:
                    trial[e["kind"]] = trial.get(e["kind"], 0.0) + cad
                if accepted and sum(trial.values()) > cap:
                    # Together they exceed what Etsy could charge on this price: none of
                    # them is applied on a guess about which one is wrong.
                    held_here += [(e, cad) for e, cad, _m in accepted]
                    accepted, trial = [], dict(comps)
                for e, cad in held_here:
                    anomalies.append({"entry_id": e["entry_id"], "ledger_type": e["ledger_type"],
                                      "order": o.external_ref, "charge_cad": round(cad, 4),
                                      "order_price_cad": price,
                                      "why": (f"exceeds {FEE_ANOMALY_SHARE:.0%} of the order "
                                              f"price: held as anomalous (a unit error reads "
                                              f"as 100x)")})
                held_ids = sorted(set(detail.get("fee_entries_held") or [])
                                  | {e["entry_id"] for e, _ in held_here})
                detail["fee_entries_held"] = held_ids
                if not accepted and not comps:
                    # Nothing from the ledger is applied: the fee stays modelled.
                    o.detail = detail
                    continue
                offsite_prior = float(o.offsite_ads_fee_cad or 0.0) \
                    if "legacy_ledger_total" in comps else 0.0
                for e, cad, measured_rate in accepted:
                    fx_assumed = fx_assumed or not measured_rate
                    kinds.add(e["kind"])
                comps = {k: round(v, 4) for k, v in trial.items()}
                model = model_fees(price) if price > 0 else None
                missing = {}
                if model is not None:
                    if "transaction_fee" not in kinds:
                        missing["transaction_fee"] = model.transaction_fee
                    if "processing_fee" not in kinds:
                        missing["processing_fee"] = model.payment_fee
                complete = not missing and not held_ids
                basis = (MEASURED if complete and verified else
                         UNVERIFIED if complete else PARTIAL_BASIS)
                o.fees_cad = round(sum(comps.values()) + sum(missing.values()), 2)
                o.fees_basis = basis
                offsite = offsite_prior + sum(cad for e, cad, _m in accepted
                                              if e["kind"] == "offsite_ads_fee") \
                    if "legacy_ledger_total" in comps else comps.get("offsite_ads_fee", 0.0)
                o.offsite_ads_fee_cad = round(offsite, 2)
                if o.offsite_ads_fee_cad > 0:
                    o.offsite_ad_attributed = True
                # `revenue_cad` is already net of every refund the receipt carries (and 0
                # for a full refund or a cancellation). Signed: a refunded sale whose fees
                # stayed with Etsy is a loss, and the books keep it (CB2-O07).
                revenue = float(o.revenue_cad or 0.0)
                o.contribution_cad = round(revenue - o.fees_cad, 2)
                state = RECONCILED if not missing and not held_ids else PARTIAL
                detail["fee_entries"] = sorted(done | {e["entry_id"] for e, _c, _m in accepted})
                detail["fee_kinds"] = sorted(kinds)
                detail["fee_components"] = comps
                detail["fees_modelled_missing"] = {k: round(v, 4) for k, v in missing.items()}
                detail["fees_mapping"] = "owner_verified" if verified else UNVERIFIED_MAPPING
                detail["fees_fx_assumed"] = bool(detail.get("fees_fx_assumed") or fx_assumed)
                detail["fees_reconciliation"] = state
                money = dict(detail.get("money") or {})
                fx = (money.get("fx") or {}).get("basis") or "assumed"
                money["contribution_basis"] = (
                    "revenue net of refunds less " + fee_basis_text(basis, kinds, missing)
                    + f"; {fx} FX rate")
                money["fees"] = {**(money.get("fees") or {}),
                                 "basis": basis if basis != UNVERIFIED else UNVERIFIED_MAPPING,
                                 "why": fee_basis_text(basis, kinds, missing)}
                detail["money"] = money
                o.detail = detail
                row = s.scalar(select(LedgerEntry).where(
                    LedgerEntry.evidence_ref == o.external_ref))
                if row is not None:
                    row.fees_cad = o.fees_cad
                    row.fees_basis = basis
                    row.reconciliation_state = state
                applied_orders.append({"ref": o.external_ref, "fees_cad": o.fees_cad,
                                       "offsite_ads_fee_cad": o.offsite_ads_fee_cad,
                                       "state": state, "basis": basis})
                new_offsite = [e["entry_id"] for e, _c, _m in accepted
                               if e["kind"] == "offsite_ads_fee"]
                if new_offsite and o.acquisition_source in ("unknown", "etsy", ""):
                    attributions.append((o.external_ref, ",".join(new_offsite)))
        refunds = _apply_refunds(s, by_receipt, refund_entries, verified=verified)
    for ref, ids in attributions:
        sources.attribute(db, ref, "offsite_ads", by="finance.reconcile",
                          evidence=f"Etsy payment-account ledger Offsite Ads fee entry "
                                   f"{ids}: Etsy charges it only on a sale it attributes to "
                                   f"an offsite ad")
    unmatched = [e for e in fees if e["entry_id"] not in matched_ids]
    # F-608: a fee Etsy charged against a receipt or transaction this system has no order
    # for is a disagreement between Etsy and the internal orders -- an order we cannot see.
    # It becomes a reconciliation incident, never a silent line in a report.
    orphans = [e for e in unmatched if e["reference_type"].lower() in ORDER_REFERENCE_TYPES]
    # A refund Etsy paid out against an order this system does not have is the same
    # disagreement, and joins the same incident.
    orphans += [e for e in refund_entries if e["entry_id"] not in refunds["matched_ids"]
                and e["reference_type"].lower() in ORDER_REFERENCE_TYPES]
    incident = reconciliation_incident(db, orphans) if orphans else None
    unclassified = [e for e in norm if e["kind"] == "unclassified"]
    ledger_incidents = _ledger_incidents(db, unclassified, anomalies)
    return {
        "entries": len(norm), "fee_entries": len(fees),
        "listing_fee_entries_applied": listing_fee_entries,
        "unclassified": sorted({e["ledger_type"] for e in norm if e["kind"] == "unclassified"}),
        "orders_measured": len(applied_orders), "applied": applied_orders[:50],
        "offsite_attributed": [r for r, _ in attributions],
        # Fee entries that matched no order: a listing fee, a renewal, or an order this
        # system never ingested. Reported, never spread across orders.
        "unmatched_fee_entries": [{"entry_id": e["entry_id"], "kind": e["kind"],
                                   "reference": f"{e['reference_type']}:{e['reference_id']}",
                                   "charge": e["charge"], "currency": e["currency"]}
                                  for e in unmatched][:50],
        "refund_entries": len(refund_entries),
        "orders_refund_raised": refunds["raised"],
        "orders_refund_disagreeing": refunds["disagreeing"],
        "orphan_fee_entries": len(orphans),
        "reconciliation_incident": incident,
        "mapping": "owner_verified" if verified else UNVERIFIED_MAPPING,
        "anomalous_entries": anomalies[:50],
        "ledger_incidents": ledger_incidents,
    }


def _ledger_incidents(db, unclassified: list[dict], anomalies: list[dict]) -> dict:
    """Unknown ledger types and anomalous magnitudes are incidents, never guesses."""
    from ..ops import incident_lifecycle as lifecycle

    out = {}
    with db.session() as s:
        if unclassified:
            _inc, opened = lifecycle.open_or_restate(
                s, signature=UNCLASSIFIED_SIGNATURE, severity="P2",
                summary=(f"{len(unclassified)} Etsy ledger entr(ies) of a type not on the "
                         f"allow-list: not counted as a fee or a refund"),
                detail={"ledger_types": sorted({e["ledger_type"] for e in unclassified}),
                        "entry_ids": sorted({e["entry_id"] for e in unclassified})[:200]})
            out[UNCLASSIFIED_SIGNATURE] = "opened" if opened else "restated"
        if anomalies:
            _inc, opened = lifecycle.open_or_restate(
                s, signature=ANOMALY_SIGNATURE, severity="P2",
                summary=(f"{len(anomalies)} Etsy ledger fee entr(ies) implausibly large for "
                         f"their order: held, not applied"),
                detail={"entries": anomalies[:50]})
            out[ANOMALY_SIGNATURE] = "opened" if opened else "restated"
    return out


def _apply_refunds(s, by_receipt: dict[str, list], refund_entries: list[dict], *,
                   verified: bool = False) -> dict:
    """Etsy ledger refund entries onto the orders they paid back (Codex CB2-O07, FB-2 O).

    The receipt's own `refunds[]` is the order's refund (commerce.orders_ingest). The
    payment-account ledger is the record of money that actually left the shop. Each order
    keeps the refund entry ids already applied and their cumulative CAD amount
    (`detail.ledger_refund_cad`), so a re-read adds nothing. When the ledger has paid back
    MORE than the receipt says, the ledger wins -- money that left is not revenue -- and the
    order's revenue, contribution (signed, never clamped) and its sale ledger row's refund
    move to it. When it has paid back less, the receipt figure stands (the ledger can lag)
    and the disagreement is kept on the order by name.
    """
    from sqlalchemy import select

    from ..core.models import LedgerEntry

    by_ref: dict[str, list[dict]] = {}
    for e in refund_entries:
        by_ref.setdefault(e["reference_id"], []).append(e)
    matched_ids: set[str] = set()
    raised, disagreeing = [], []
    for rid, group in by_receipt.items():
        receipt_entries = by_ref.get(rid, [])
        total_price = sum(float(o.price_cad or 0.0) for o in group) or 1.0
        for o in group:
            txn = o.external_ref.rsplit(":", 1)[-1]
            share = (float(o.price_cad or 0.0) / total_price) if len(group) > 1 else 1.0
            candidates = ([(e, 1.0) for e in by_ref.get(txn, [])]
                          + [(e, share) for e in receipt_entries])
            if not candidates:
                continue
            detail = dict(o.detail or {})
            done = set(detail.get("refund_entries") or [])
            ledger_refund = float(detail.get("ledger_refund_cad") or 0.0)
            on = (o.at or datetime.now(timezone.utc)).date()
            for e, w in candidates:
                matched_ids.add(e["entry_id"])
                if e["entry_id"] in done:
                    continue
                # The sign of a refund entry's amount is UNVERIFIED against a live shop
                # (module docstring); a refund entry is money paid back either way.
                cad, _measured = _to_cad(abs(e["charge"]) * w, e["currency"], on)
                ledger_refund += cad
                done.add(e["entry_id"])
            price = float(o.price_cad or 0.0)
            ledger_refund = round(min(price, max(0.0, ledger_refund)), 2)
            stored = (detail.get("refund") or {}).get("cad")
            receipt_refund = round(float(stored) if stored is not None
                                   else price - float(o.revenue_cad or 0.0), 2)
            current_refund = round(price - float(o.revenue_cad or 0.0), 2)
            detail["refund_entries"] = sorted(done)
            detail["ledger_refund_cad"] = ledger_refund
            # Read through the same unverified type/unit mapping as the fees (E5).
            detail["ledger_refund_basis"] = MEASURED if verified else UNVERIFIED_MAPPING
            if ledger_refund > receipt_refund + 0.005:
                detail["refund_reconciliation"] = "raised_to_etsy_ledger"
                if ledger_refund <= current_refund + 0.005:
                    o.detail = detail
                    continue
                o.revenue_cad = round(price - ledger_refund, 2)
                o.contribution_cad = round(float(o.revenue_cad) - float(o.fees_cad or 0.0), 2)
                o.refunded = o.revenue_cad <= 0.005
                row = s.scalar(select(LedgerEntry).where(
                    LedgerEntry.evidence_ref == o.external_ref))
                if row is not None:
                    row.refunds_cad = ledger_refund
                raised.append(o.external_ref)
            elif ledger_refund < receipt_refund - 0.005:
                detail["refund_reconciliation"] = "receipt_exceeds_etsy_ledger"
                disagreeing.append(o.external_ref)
            else:
                detail["refund_reconciliation"] = "matched_etsy_ledger"
            o.detail = detail
    return {"matched_ids": matched_ids, "raised": raised, "disagreeing": disagreeing}


# Ledger references that name an order. A fee against one of these that matches no order
# means Etsy has an order this system does not.
ORDER_REFERENCE_TYPES = ("receipt", "transaction", "payment")
RECONCILIATION_SIGNATURE = "finance.reconciliation.etsy_vs_orders"


def reconciliation_incident(db, orphans: list[dict]) -> str:
    """Open (or add to) the one incident for Etsy fees with no internal order. Idempotent."""
    from sqlalchemy import select

    from ..core.models import Incident

    refs = sorted({f"{e['reference_type']}:{e['reference_id']}" for e in orphans})
    ids = sorted({e["entry_id"] for e in orphans})
    with db.session() as s:
        inc = s.scalar(select(Incident).where(Incident.signature == RECONCILIATION_SIGNATURE,
                                              Incident.resolved == False))  # noqa: E712
        if inc is None:
            s.add(Incident(signature=RECONCILIATION_SIGNATURE, severity="P2",
                           summary=(f"Etsy charged {len(ids)} fee(s) against "
                                    f"{len(refs)} order reference(s) with no internal order: "
                                    f"Etsy and the order ledger disagree"),
                           detail={"entry_ids": ids, "references": refs}))
            return "opened"
        detail = dict(inc.detail or {})
        known = set(detail.get("entry_ids") or [])
        new_ids = [i for i in ids if i not in known]
        if not new_ids:
            return "unchanged"
        detail["entry_ids"] = sorted(known | set(new_ids))
        detail["references"] = sorted(set(detail.get("references") or []) | set(refs))
        inc.detail = detail
        inc.report_count = int(inc.report_count or 1) + 1
        return "counted"


def fee_basis_summary(rows: Iterable[Any]) -> dict:
    """Sum `fees_cad` by basis over ledger rows: measured, modelled, unknown."""
    out = {"measured": 0.0, "modelled": 0.0, "partial": 0.0, "unverified": 0.0,
           "unknown": 0.0}
    for r in rows:
        basis = getattr(r, "fees_basis", None) or "unknown"
        out[basis if basis in out else "unknown"] += float(r.fees_cad or 0.0)
    return {k: round(v, 4) for k, v in out.items()}
