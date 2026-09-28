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

**Money truth (Final Build cluster D).** Four things changed, each because the earlier
version wrote a proxy that read as a fact:

* The acquisition source is `unknown` (F-283, F-289). It used to be `etsy` on every order,
  which every downstream reader took for organic search. A receipt does not say how the
  buyer arrived; `finance.sources.attribute` moves an order out of `unknown` on evidence
  only, and the first sale is kept as a record (`finance.sources.record_first_sale`).
* The sale's fee is marked `modelled` (F-609). It is `commerce.pricing.fees()` output until
  Etsy's payment-account ledger is read, and a modelled fee is never presented as charged.
  The ledger row also carries its source, external id, currency, original amount,
  classification and reconciliation state.
* When the reader can read the payment-account ledger (the same `transactions_r` grant),
  the fees Etsy actually charged replace the model, per order, and an Offsite Ads fee sets
  `offsite_ad_attributed`, is deducted from contribution and attributes the order (F-558,
  F-273; `finance.reconcile`). When it cannot, the fees stay modelled and labelled.
* A credential failure that only the owner can fix (`EtsyAuthNeedsOwner`: a refused or
  spent refresh token, a revoked grant, a missing scope) becomes one idempotent owner action
  and one incident instead of a failed job retried on a cadence (F-541).
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
# F-541: the owner action and incident an auth failure raises. One key for every failure
# class, because every class ends in the same place -- the owner re-approving the app.
AUTH_ACTION_KEY = "etsy.oauth.reauthorise"
AUTH_INCIDENT_SIGNATURE = "etsy.oauth.needs_owner"
LEDGER_OPERATION = "getShopPaymentAccountLedgerEntries"
# How far back the payment-account ledger is read on a run with no earlier order: fees post
# after the sale, so the window reaches past the receipt window.
LEDGER_LOOKBACK = timedelta(days=45)
# Receipt statuses whose money did not stay with the shop.
NOT_KEPT_STATUSES = ("canceled", "cancelled", "fully refunded")

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


INGEST_AUDIT = "commerce.orders_ingested"


def source_state(db) -> dict:
    """Whether sales figures can be called measured, for the books (F-608).

    Measured needs both halves: the gate open (the source is connected) *and* a completed
    read recorded (`commerce.orders_ingested` with `ran: true`). A connected source that has
    never been read has told us nothing yet, and zero orders from it would be a zero nobody
    observed.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog

    state = gate(db)
    last_read = None
    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == INGEST_AUDIT)
                             .order_by(AuditLog.id.desc()).limit(50)):
            if (row.detail or {}).get("ran") is True:
                last_read = row.at.isoformat() if row.at else None
                break
    measured = state["open"] and last_read is not None
    if measured:
        why = ""
    elif not state["open"]:
        why = ("the order source is not connected: " + "; ".join(state["missing"])
               + ". Sales are UNMEASURED, which is different from zero sales")
    else:
        why = ("the order source is connected but no completed receipt read is recorded "
               "yet, so there is no observation to report")
    return {"open": state["open"], "missing": state["missing"], "last_read_at": last_read,
            "measured": measured, "why": why, "owner_action": OWNER_ACTION_KEY}


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

    def ledger_entries(self, *, min_created: datetime, max_created: datetime) -> list[dict]:
        """Etsy's payment-account ledger over a window (F-558): what Etsy actually charged.

        A thin read on the client's existing transport and scope check. `EtsyClient` has no
        public method for this operation yet (integrations/etsy.py belongs to another
        cluster), so the request goes through the client's own `_call`, which applies the
        same credential, the same per-operation scope refusal and the same error taxonomy.
        Etsy requires both bounds.
        """
        from ..integrations.etsy import Authority

        creds = self.client._require(Authority.READ)
        out: list[dict] = []
        for page in range(MAX_PAGES):
            self.calls += 1
            body = self.client._call(
                "GET", f"/shops/{creds.shop_id}/payment-account/ledger-entries",
                operation=LEDGER_OPERATION, authority=Authority.READ,
                query={"min_created": int(min_created.timestamp()),
                       "max_created": int(max_created.timestamp()),
                       "limit": PAGE, "offset": page * PAGE}).body
            got = body.get("results") if isinstance(body, dict) else None
            got = list(got) if isinstance(got, list) else []
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
    status = str(receipt.get("status") or "").strip().lower()
    # A cancelled or fully refunded receipt kept no money, whatever its refunds list says.
    refunded = bool(receipt.get("refunds")) or status in NOT_KEPT_STATUSES
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
            "at": at, "refunded": refunded, "status": status,
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
    from ..core.models import LedgerEntry, Order

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

    # F-283: a receipt does not say how the buyer arrived. `unknown` until evidence says
    # otherwise (finance.sources.attribute); "etsy" asserted a channel nobody knew.
    customer = cohorts.record_customer(
        db, line["customer_ref"], at=line["at"], acquisition_source="unknown",
        first_product_slug=slug, first_category=category, first_season=season)
    order = cohorts.record_order(
        db, line["customer_ref"], ref, product_slug=slug, at=line["at"], version=version,
        category=category, price_cad=price, revenue_cad=0.0 if line["refunded"] else price,
        contribution_cad=max(0.0, contribution), acquisition_source="unknown",
        refunded=line["refunded"], currency=line["currency"],
        amount_original=line["amount"], fx_usd_per_cad=cad["usd_per_cad"],
        fx_taken_on=cad["taken_on"], fx_measured=cad["measured"], fees_cad=fee_total,
        offer=offer, source=SOURCE,
        detail={"listing_id": line["listing_id"], "receipt_id": line["receipt_id"],
                "matched_listing": bool(target), "receipt_status": line.get("status", ""),
                "fees_model": "commerce.pricing.fees (transaction + payment processing + "
                              "amortised listing; offsite/regulatory/conversion unmodelled)"})

    ledger = False
    with db.session() as s:
        if order.get("created"):
            # F-609: the fee on a new order is the model's until the ledger replaces it.
            # `offsite_ads_fee_cad` stays None (not read), never 0.0 (read, none charged).
            row = s.scalar(select(Order).where(Order.external_ref == ref))
            if row is not None and (row.fees_basis or "unknown") != "measured":
                row.fees_basis = "modelled"
        if s.scalar(select(LedgerEntry).where(LedgerEntry.evidence_ref == ref)) is None:
            s.add(LedgerEntry(at=line["at"], category="sale",
                              description=f"Etsy receipt {line['receipt_id']} ({slug})",
                              gross_cad=price, fees_cad=fee_total,
                              refunds_cad=price if line["refunded"] else 0.0,
                              evidence_ref=ref, source=SOURCE, external_id=ref,
                              currency=line["currency"], amount_original=line["amount"],
                              classification="sale", basis="measured",
                              fees_basis="modelled",
                              reconciliation_state="unreconciled"))
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

    from ..integrations.etsy_oauth import EtsyAuthNeedsOwner

    last = _last_ingested(db)
    since = (last - OVERLAP) if last is not None else None
    try:
        receipts = reader.receipts(since=since)
    except EtsyAuthNeedsOwner as exc:
        raised = needs_owner(db, exc, operation=OPERATION, now=now)
        return {"ran": False, "reading": "UNMEASURED", "gate": state,
                "network_calls": getattr(reader, "calls", None), "auth_failure": raised,
                "why": ("the Etsy credential needs the owner (" + raised["failure_class"]
                        + "): " + str(exc)[:300] + ". Receipts were not read; no order is "
                        "invented and nothing is retried until the owner re-authorises")}
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
    fees = _reconcile_fees(db, reader, since=since, now=now)
    from ..finance import sources

    first = sources.record_first_sale(db)
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
        "fees": fees,
        "first_sale": ({k: first.get(k) for k in ("external_ref", "acquisition_source",
                                                  "created")} if first else None),
    }


# ---------------------------------------------------------------------------
# Measured fees (F-558, F-609, F-273)


def _reconcile_fees(db, reader, *, since: datetime | None, now: datetime) -> dict:
    """Read Etsy's payment-account ledger and replace modelled fees with charged ones.

    Only when the reader can read it. When it cannot -- a reader without the method, or a
    read Etsy refuses -- the fees stay `modelled` and the run says so; the orders written
    above are not undone because a fee could not be measured.
    """
    from ..finance import reconcile
    from ..integrations.etsy_oauth import EtsyAuthNeedsOwner

    read = getattr(reader, "ledger_entries", None)
    if read is None:
        return {"read": False, "basis": "modelled",
                "why": "this reader cannot read the payment-account ledger, so every fee "
                       "on these orders is commerce.pricing.fees() output, labelled modelled"}
    start = (since - LEDGER_LOOKBACK) if since is not None else (now - LEDGER_LOOKBACK)
    try:
        entries = read(min_created=start, max_created=now)
    except EtsyAuthNeedsOwner as exc:
        raised = needs_owner(db, exc, operation=LEDGER_OPERATION, now=now)
        return {"read": False, "basis": "modelled", "auth_failure": raised,
                "why": f"the payment-account ledger read needs the owner: {str(exc)[:200]}"}
    except Exception as exc:  # noqa: BLE001 - a fee read failing leaves fees modelled
        return {"read": False, "basis": "modelled",
                "why": f"the payment-account ledger read failed ({type(exc).__name__}: "
                       f"{str(exc)[:200]}); fees stay modelled and labelled"}
    return {"read": True, **reconcile.apply(db, entries, source=SOURCE)}


# ---------------------------------------------------------------------------
# Credential failures only the owner can fix (F-541)


def failure_class(exc: Exception) -> str:
    """Which of the Master's OAuth failure classes an `EtsyAuthNeedsOwner` is."""
    text = str(exc).lower()
    if "cannot perform" in text or ("missing" in text and "scope" in text):
        return "scope_drift"
    if "invalid_grant" in text:
        return "refresh_refused"
    if "revoked" in text or " 401" in text or " 403" in text:
        return "access_revoked"
    if "refresh grant" in text:
        return "refresh_refused"
    if "seal" in text or "encryption" in text or "decrypt" in text:
        return "sealing_key_changed"
    if "no refresh token" in text or "no etsy token" in text:
        return "no_credential"
    return "needs_owner"


def needs_owner(db, exc: Exception, *, operation: str, now: datetime | None = None) -> dict:
    """One owner action and one incident for an Etsy credential only the owner can fix.

    Idempotent on `AUTH_ACTION_KEY` and `AUTH_INCIDENT_SIGNATURE`: a six-hourly cadence
    hitting the same revoked grant restates the open action and counts another report on
    the open incident; it never adds a second row, and it never re-opens an action the
    owner has closed (their "done" is theirs -- if the failure recurs after it, the incident
    count says so).
    """
    from sqlalchemy import select

    from ..core.models import Incident, OwnerAction

    now = now or datetime.now(timezone.utc)
    kind = failure_class(exc)
    message = str(exc)[:600]
    fields = {
        "action": ("Re-authorise the Brambleloop Etsy app in a browser (start at "
                   "/api/etsy/oauth/start) with the full scope set, including transactions_r. "
                   f"Etsy refused {operation}: {kind}."),
        "reason": ("Etsy grants and restores OAuth access only through the "
                   "authorization-code flow, which needs the account holder at a consent "
                   f"screen. No code path avoids it. Failure: {message}"),
        "max_cost_cad": 0.0, "minutes": 6,
        "consequence_of_delay": ("Orders, payments and fees cannot be read: sales stay "
                                 "UNMEASURED and every order-reading decision waits."),
        "blocks": "order ingest, fee reconciliation, first-sale record",
    }
    result = {"failure_class": kind, "operation": operation, "owner_action": None,
              "incident": None}
    with db.session() as s:
        action = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == AUTH_ACTION_KEY))
        if action is None:
            s.add(OwnerAction(requirement_key=AUTH_ACTION_KEY, **fields))
            result["owner_action"] = "queued"
        elif action.done:
            result["owner_action"] = "already_decided"
        else:
            for name, value in fields.items():
                setattr(action, name, value)
            result["owner_action"] = "restated"
        incident = s.scalar(select(Incident).where(
            Incident.signature == AUTH_INCIDENT_SIGNATURE,
            Incident.resolved == False))  # noqa: E712
        if incident is None:
            s.add(Incident(signature=AUTH_INCIDENT_SIGNATURE, severity="P2",
                           summary=f"Etsy credential needs the owner ({kind}) on {operation}",
                           detail={"failure_class": kind, "operation": operation,
                                   "first_at": now.isoformat(), "last_at": now.isoformat(),
                                   "message": message, "owner_action": AUTH_ACTION_KEY}))
            result["incident"] = "opened"
        else:
            incident.report_count = int(incident.report_count or 1) + 1
            detail = dict(incident.detail or {})
            classes = sorted((set(detail.get("classes") or [detail.get("failure_class")])
                              | {kind}) - {None})
            detail.update({"last_at": now.isoformat(), "message": message,
                           "classes": classes})
            incident.detail = detail
            result["incident"] = "counted"
    return result
