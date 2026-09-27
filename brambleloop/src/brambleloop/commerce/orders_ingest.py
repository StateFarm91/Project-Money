"""The order source: Etsy shop receipts into `customers`, `orders`, `order_versions` and the
ledger (C-64; #11, #12, #42, #269).

Certification defect C-64: every row that reads orders -- cohorts, lifetime value, the
version map, offer engineering, winner detection, repeat windows, referral, the growth-loop
registry, reinvestment -- was parked on "needs customers" while nothing in the running
system could ever write an order. `cohorts.record_order` had no caller and `getShopReceipts`
was never called, so the day a buyer arrived would have been a day like any other. This
module is the pipe, run on a cadence by `commerce.orders_ingest`.

**The gate is real and is checked before anything else.** Reading receipts needs the
`transactions_r` OAuth scope (Etsy's `getShopReceipts` security block), which only the owner
can grant by re-authorising the app in a browser, and a working Etsy credential (a recorded
successful `etsy.probe`). Both are read from rows: the scopes Etsy actually granted are on
the stored `oauth_credentials` row, and the probe is the audit row the `etsy_api` gate reads.
When either is missing the run records `UNMEASURED` with the reason and makes **no network
call** -- the client is not even constructed.

**What is written, and what is not.** A customer is the buyer's Etsy user id and nothing
else: no name, no email, no address, even though the receipt carries them. Each receipt line
becomes one order (`etsy:<receipt>:<transaction>`), idempotent on that reference; the version
the buyer received is recorded at sale time through `cohorts.record_order`; the money becomes
one `sale` ledger entry with the same evidence reference, which is what opens the `customers`
data gate. The transaction's own currency and amount are preserved beside the CAD figure,
with the rate, its date and whether it was measured (#269).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

SCOPE = "transactions_r"
OPERATION = "getShopReceipts"
SOURCE = "etsy_receipts"
PAGE = 100
MAX_PAGES = 20
# Receipts are re-read over this overlap so a receipt created while the last run was paging
# is not missed. Idempotent on the order reference, so the overlap costs nothing but a read.
OVERLAP = timedelta(days=2)
OWNER_ACTION_KEY = "reauthorise_transactions_r"

# Injection point for the receipt reader. None in production: the reader is built from the
# environment's Etsy credential, and only after the gate is open. Tests set this to a fake
# feed -- the gate is still checked first, so a test cannot read receipts the gate refuses.
reader_factory: Callable[[Any], Any] | None = None


class IngestRefused(ValueError):
    """A receipt this module cannot place: no buyer, no line, no currency."""


# ---------------------------------------------------------------------------
# The gate


def granted_scopes(db) -> tuple[str, ...]:
    """The scopes Etsy said it granted, from the stored credential row (never the token)."""
    from ..core.models import OAuthCredential

    with db.session() as s:
        row = s.get(OAuthCredential, "etsy")
        return tuple((row.scopes or "").split()) if row is not None else ()


def gate(db) -> dict:
    """Whether receipts may be read now, and exactly what is missing if not."""
    from ..intel import etsy_public

    missing: list[str] = []
    if not etsy_public.usable(db):
        missing.append("etsy_api: no recorded successful etsy.probe, so no working Etsy "
                       "credential has been demonstrated")
    if SCOPE not in granted_scopes(db):
        missing.append(f"{SCOPE}: the stored Etsy grant does not include it. Only the owner "
                       f"can add it, by re-authorising the app in a browser "
                       f"(owner action {OWNER_ACTION_KEY!r})")
    return {"open": not missing, "missing": missing, "scope": SCOPE,
            "operation": OPERATION}


# ---------------------------------------------------------------------------
# Reading


class EtsyReceiptReader:
    """The production reader: `EtsyClient.get_shop_receipts`, paged."""

    def __init__(self, client) -> None:
        self.client = client
        self.calls = 0  # network calls made, reported by every run

    def receipts(self, *, since: datetime | None) -> list[dict]:
        out: list[dict] = []
        min_created = int(since.timestamp()) if since is not None else None
        for page in range(MAX_PAGES):
            self.calls += 1
            got = self.client.get_shop_receipts(min_created=min_created, limit=PAGE,
                                                offset=page * PAGE)
            out.extend(got)
            if len(got) < PAGE:
                break
        return out


def _production_reader(db):
    from ..integrations.etsy import Credentials, EtsyClient
    from ..integrations.http import UrllibTransport

    transport = UrllibTransport()
    creds = Credentials.from_env(transport=transport, db=db)
    if creds is None:
        return None
    return EtsyReceiptReader(EtsyClient(transport, credentials=creds))


# ---------------------------------------------------------------------------
# Normalising one receipt


def _money(obj: Any) -> tuple[float, str] | None:
    if not isinstance(obj, dict) or "amount" not in obj:
        return None
    divisor = float(obj.get("divisor") or 1) or 1.0
    return float(obj["amount"]) / divisor, str(obj.get("currency_code") or "").upper()


def _when(receipt: dict) -> datetime:
    ts = receipt.get("create_timestamp") or receipt.get("created_timestamp")
    if ts is None:
        raise IngestRefused(f"receipt {receipt.get('receipt_id')!r} has no creation time")
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def lines(receipt: dict) -> list[dict]:
    """One dict per transaction line, with personal data dropped at the door."""
    rid = receipt.get("receipt_id")
    buyer = receipt.get("buyer_user_id")
    if rid is None or buyer in (None, ""):
        raise IngestRefused("a receipt needs its id and the buyer's Etsy user id")
    at = _when(receipt)
    refunded = bool(receipt.get("refunds"))
    out = []
    for t in receipt.get("transactions") or []:
        price = _money(t.get("price"))
        if price is None or not price[1]:
            raise IngestRefused(f"receipt {rid}: a line with no priced currency cannot be "
                                f"reconciled against anything")
        qty = max(1, int(t.get("quantity") or 1))
        out.append({
            "receipt_id": str(rid), "transaction_id": str(t.get("transaction_id")),
            "customer_ref": f"etsy-user-{buyer}",
            "listing_id": str(t.get("listing_id") or ""),
            "amount": round(price[0] * qty, 4), "currency": price[1],
            "at": at, "refunded": refunded,
        })
    return out


def _catalogue(db) -> dict[str, dict]:
    """Etsy listing id -> the product and version this company listed under it."""
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        return {r.etsy_listing_id: {"slug": r.product_slug, "version": r.version,
                                    "collection": r.version == "collection"}
                for r in s.scalars(select(Listing)) if r.etsy_listing_id}


def _seed(slug: str):
    from ..radar.opportunity import POOL

    return next((c for c in POOL if c.slug == slug), None)


def _to_cad(amount: float, currency: str, on: date) -> dict:
    """The CAD figure with its provenance, or a refusal for a currency with no rate."""
    from ..finance import currency as fx

    converted = fx.to_reporting(fx.Money(amount, currency), fx.assumed_rate(on))
    rate = converted["rate"]
    return {"cad": float(converted["reporting"]["amount"]),
            "usd_per_cad": rate["usd_per_cad"] if rate else None,
            "taken_on": rate["taken_on"] if rate else "",
            "measured": bool(rate and rate["measured"])}


# ---------------------------------------------------------------------------
# Writing


def _record_line(db, line: dict, listed: dict[str, dict]) -> dict:
    from sqlalchemy import select

    from ..commerce import cohorts
    from ..commerce.pricing import fees
    from ..core.models import LedgerEntry

    ref = f"etsy:{line['receipt_id']}:{line['transaction_id']}"
    target = listed.get(line["listing_id"])
    slug = target["slug"] if target else f"etsy-listing-{line['listing_id'] or 'unknown'}"
    version = "" if (not target or target["collection"]) else target["version"]
    seed = _seed(slug)
    category = seed.category if seed else ""
    season = (seed.season or "none") if seed else "none"
    offer = ("complete_collection" if target and target["collection"] else
             "seasonal_bundle" if seed and seed.is_bundle and seed.season else
             "mini_bundle" if seed and seed.is_bundle else "single_pattern")

    try:
        cad = _to_cad(line["amount"], line["currency"], line["at"].date())
    except Exception as exc:  # noqa: BLE001 - a currency with no rate is recorded, not guessed
        return {"ref": ref, "recorded": False, "why": str(exc)[:200]}
    price = round(cad["cad"], 2)
    f = fees(price) if price > 0 else None
    fee_total = round(f.total_fees, 2) if f else 0.0
    contribution = round(price - fee_total, 2) if not line["refunded"] else 0.0

    customer = cohorts.record_customer(
        db, line["customer_ref"], at=line["at"], acquisition_source="etsy",
        first_product_slug=slug, first_category=category, first_season=season)
    order = cohorts.record_order(
        db, line["customer_ref"], ref, product_slug=slug, at=line["at"], version=version,
        category=category, price_cad=price, revenue_cad=0.0 if line["refunded"] else price,
        contribution_cad=max(0.0, contribution), acquisition_source="etsy",
        refunded=line["refunded"], currency=line["currency"],
        amount_original=line["amount"], fx_usd_per_cad=cad["usd_per_cad"],
        fx_taken_on=cad["taken_on"], fx_measured=cad["measured"], fees_cad=fee_total,
        offer=offer, source=SOURCE,
        detail={"listing_id": line["listing_id"], "receipt_id": line["receipt_id"],
                "matched_listing": bool(target)})

    ledger = False
    with db.session() as s:
        if s.scalar(select(LedgerEntry).where(LedgerEntry.evidence_ref == ref)) is None:
            s.add(LedgerEntry(at=line["at"], category="sale",
                              description=f"Etsy receipt {line['receipt_id']} ({slug})",
                              gross_cad=price, fees_cad=fee_total,
                              refunds_cad=price if line["refunded"] else 0.0,
                              evidence_ref=ref))
            ledger = True
    return {"ref": ref, "recorded": True, "order_created": bool(order.get("created")),
            "customer_created": bool(customer.get("created")), "ledger": ledger,
            "matched_listing": bool(target), "version": version}


def _last_ingested(db) -> datetime | None:
    from sqlalchemy import func, select

    from ..core.models import Order

    with db.session() as s:
        last = s.scalar(select(func.max(Order.at)).where(Order.source == SOURCE))
    if last is None:
        return None
    return last if last.tzinfo else last.replace(tzinfo=timezone.utc)


def ingest(db, *, reader=None, now: datetime | None = None) -> dict:
    """One ingest run: gate, read, write. UNMEASURED with the reason when gated."""
    now = now or datetime.now(timezone.utc)
    state = gate(db)
    if not state["open"]:
        return {"ran": False, "reading": "UNMEASURED", "gate": state,
                "network_calls": 0,
                "why": ("receipts cannot be read: " + "; ".join(state["missing"])
                        + ". No order is invented and no count is reported as zero: the "
                          "order source is not connected, which is different from no "
                          "orders")}
    if reader is None:
        reader = reader_factory(db) if reader_factory is not None else _production_reader(db)
    if reader is None:
        return {"ran": False, "reading": "UNMEASURED", "gate": state, "network_calls": 0,
                "why": "no Etsy credential in this environment to build the receipt reader"}

    last = _last_ingested(db)
    since = (last - OVERLAP) if last is not None else None
    receipts = reader.receipts(since=since)
    listed = _catalogue(db)
    written, refused = [], []
    from .cohorts import CohortRefused

    for receipt in receipts:
        try:
            for line in lines(receipt):
                try:
                    written.append(_record_line(db, line, listed))
                except CohortRefused as exc:
                    # One line the cohort writer refuses (an amount that reconciles to
                    # nothing) is recorded as such; it does not stop the other receipts.
                    refused.append({"receipt_id": receipt.get("receipt_id"),
                                    "transaction_id": line["transaction_id"],
                                    "why": str(exc)[:200]})
        except IngestRefused as exc:
            refused.append({"receipt_id": receipt.get("receipt_id"), "why": str(exc)[:200]})
    created = [w for w in written if w.get("order_created")]
    return {
        "ran": True, "reading": "measured", "gate": state,
        "network_calls": getattr(reader, "calls", None),
        "since": since.isoformat() if since else None, "at": now.isoformat(),
        "receipts": len(receipts), "lines": len(written),
        "orders_created": len(created),
        "customers_created": sum(1 for w in written if w.get("customer_created")),
        "ledger_entries": sum(1 for w in written if w.get("ledger")),
        "versions_recorded": sum(1 for w in created if w.get("version")),
        "unmatched_listings": sorted({w["ref"] for w in written
                                      if w.get("recorded") and not w.get("matched_listing")}),
        "not_recorded": [w for w in written if not w.get("recorded")] + refused,
    }
