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

**A receipt is a state, not an event (CB2-O01, CB2-O02).** Etsy's receipt carries `status`
(`paid`, `completed`, `open`, `payment processing`, `canceled`, `fully refunded`,
`partially refunded`), `is_paid`, `refunds[]` (each an amount) and `update_timestamp`. Only
a receipt Etsy says was paid, in a recognised state, becomes a sale. An unpaid or cancelled
one is held as such and never a sale; a state this module does not recognise is held as
`unknown` -- it is written nowhere and reported by name, because "unknown" is not "paid".
A refund, whenever it arrives, is reconciled onto the transaction line it belongs to: linked
to its transaction when the refund names one, otherwise allocated across the receipt's lines
in proportion to their price and capped at each line's own amount. The order row's revenue,
refund and contribution are the receipt's *current* truth, updated idempotently by source
revision (`update_timestamp`), never added to twice.

**Old receipts are re-read (CB2-O01).** A durable cursor (the newest `update_timestamp`
seen, kept as an `operating_readings` row) drives `min_last_modified`, so a refund on a
receipt from months ago is picked up by the next run; and every `FULL_SWEEP_EVERY` a run
reads the whole receipt history again, so a change the cursor could miss is reconciled at
worst that much later.

**One transaction per receipt line (CB2-O05).** The customer, the order, the version map
row and the ledger entry are written inside one database transaction. A crash between them
rolls the line back; the next run writes it exactly once. A line that already exists is
reconciled in place and its dependent rows repaired if any is missing.

**First purchase is derived, not encountered (CB2-O04).** After every line the buyer's
first-purchase facts and repeat flags are re-derived from their earliest paid order, and at
the end of a run the validation cohort is re-ranked by earliest purchase, so a backfill that
arrives newest-first yields the same cohorts as one that arrives in order.

**What is written, and what is not.** A customer is the buyer's Etsy user id and nothing
else: no name, no email, no address, even though the receipt carries them. Each receipt line
becomes one order (`etsy:<receipt>:<transaction>`); the version the buyer received is the one
recorded as listed under that Etsy listing *at the time of the sale* -- from the immutable
listing/publication history -- or explicitly unknown (CB2-O03), never the listing's current
version. A receipt says nothing about where the buyer came from, so the acquisition source
is `unknown` with its basis recorded, never assumed organic (CB2-O06). Money keeps its
provenance: fees are *modelled* from the fee schedule until Etsy's ledger replaces them, the
FX rate says whether it was measured or assumed, and a loss is recorded as a loss (CB2-O07).

**Money truth (Final Build cluster D), kept through the CB2-O port.** Four things changed,
each because the earlier version wrote a proxy that read as a fact:

* The acquisition source is `unknown` (F-283, F-289). A receipt does not say how the buyer
  arrived; `finance.sources.attribute` moves an order out of `unknown` on evidence only, and
  the first sale is kept as a record (`finance.sources.record_first_sale`).
* The sale's fee is marked `modelled` (F-609). It is `commerce.pricing.fees()` output until
  Etsy's payment-account ledger is read, and a modelled fee is never presented as charged.
  The ledger row also carries its source, external id, currency, original amount,
  classification and reconciliation state.
* When the reader can read the payment-account ledger (the same `transactions_r` grant),
  the fees Etsy actually charged replace the model, per order, and an Offsite Ads fee sets
  `offsite_ad_attributed`, is deducted from contribution and attributes the order (F-558,
  F-273; `finance.reconcile`). When it cannot, the fees stay modelled and labelled. A
  receipt reconciled later (a refund) keeps the measured fee: only revenue moves.
* A credential failure that only the owner can fix (`EtsyAuthNeedsOwner`: a refused or
  spent refresh token, a revoked grant, a missing scope) becomes one idempotent owner action
  and one incident instead of a failed job retried on a cadence (F-541).

**A reader whose `since` is not a last-modified watermark (FB-2 O).** The production reader
declares `SINCE_IS_LAST_MODIFIED`. Any other reader may filter by creation time, under which
an incremental read silently loses a refund on an old receipt; such a reader is asked from
no later than `CHANGE_WINDOW` ago, so every receipt still open to a refund or a case is
re-read on every run, not only on the weekly sweep.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

SCOPE = "transactions_r"
OPERATION = "getShopReceipts"
SOURCE = "etsy_receipts"
PAGE = 100
MAX_PAGES = 20
# Receipts are re-read over this overlap so a receipt modified while the last run was paging
# is not missed. Idempotent on the order reference and source revision, so the overlap costs
# nothing but a read.
OVERLAP = timedelta(days=2)
# How often a run reads the whole receipt history rather than what changed since the cursor.
FULL_SWEEP_EVERY = timedelta(days=7)
CURSOR_KIND = "commerce.orders_ingest"
CURSOR_KEY = "cursor"
OWNER_ACTION_KEY = "reauthorise_transactions_r"
# F-541: the owner action and incident an auth failure raises. One key for every failure
# class, because every class ends in the same place -- the owner re-approving the app --
# and the SAME key and incident the publish/read-back path raises
# (`runtime.etsy_ops.AUTH_KEY` / `AUTH_INCIDENT`; a test asserts they are equal). These used
# to be a second pair ("etsy.oauth.reauthorise", P2) which `launch.readiness` silently
# closed on its next run; the legacy pair is adopted on the next failure.
AUTH_ACTION_KEY = "etsy.auth:reauthorise"
AUTH_INCIDENT_SIGNATURE = "etsy.auth_needs_owner"
LEGACY_AUTH_ACTION_KEY = "etsy.oauth.reauthorise"
LEGACY_AUTH_INCIDENT_SIGNATURE = "etsy.oauth.needs_owner"
LEDGER_OPERATION = "getShopPaymentAccountLedgerEntries"
# How far back the payment-account ledger is read on a run with no earlier order: fees post
# after the sale, so the window reaches past the receipt window.
LEDGER_LOOKBACK = timedelta(days=45)
# How far back a receipt can still change (a refund, a case, a chargeback): Etsy's case and
# payment-dispute windows sit inside it. A reader whose `since` may be a creation filter is
# always asked from at least this far back.
CHANGE_WINDOW = timedelta(days=180)

# Etsy's receipt states, as its v3 `ShopReceipt.status` names them.
SALE_STATES: frozenset[str] = frozenset({"paid", "completed", "fully refunded",
                                         "partially refunded"})
UNPAID_STATES: frozenset[str] = frozenset({"open", "payment processing"})
CANCELLED_STATES: frozenset[str] = frozenset({"canceled", "cancelled"})
# What this module records as the line's state.
PAID, PARTIALLY_REFUNDED, FULLY_REFUNDED, CANCELLED, UNPAID, UNKNOWN = (
    "paid", "partially_refunded", "fully_refunded", "cancelled", "unpaid", "unknown")
# A paid receipt whose refund cannot be read (RC1 audit E1, E6): Etsy says "partially
# refunded" but carries no refund amount, or a refund is in a currency other than the
# receipt's. Revenue for the order is UNKNOWN -- neither the full price nor zero -- so the
# line is held (`HELD_KIND`) and a reconciliation incident is raised; it is never booked as
# a paid sale.
UNRECONCILED = "unreconciled"
# Lines that are fully voided: they stay as rows (history and audit) but are never counted
# as orders, customers or the first sale (RC1 audit E2).
VOIDED_STATES: frozenset[str] = frozenset({"fully_refunded", "cancelled"})
# Lines held outside the order tables until they can be booked truthfully: one durable
# `operating_readings` row whose payload maps order reference -> held record. Read by the
# books, which refuse to call sales `measured` while any held record is unresolved.
HELD_KIND = "commerce.orders_held"
HELD_KEY = "held"
HELD_UNCONVERTED = "unconverted_currency"     # RC1 audit E3
HELD_UNRECONCILED = "unreconciled_refund"     # RC1 audit E1, E6
UNCONVERTED_INCIDENT = "commerce.orders.unconverted_currency"
UNRECONCILED_INCIDENT = "commerce.orders.unreconciled_receipt"
ANOMALY_INCIDENT = "commerce.orders.receipt_anomaly"
# States that are written as orders. Cancelled is written only when a sale was recorded
# before the cancellation arrived: the row is then voided, not deleted.
SALE_LINE_STATES: frozenset[str] = frozenset({PAID, PARTIALLY_REFUNDED, FULLY_REFUNDED})
ATTRIBUTION_BASIS = "etsy_receipt"

# Injection point for the receipt reader. None in production: the reader is built from the
# environment's Etsy credential, and only after the gate is open. Tests set this to a fake
# feed -- the gate is still checked first, so a test cannot read receipts the gate refuses.
reader_factory: Callable[[Any], Any] | None = None
# Test seam for the crash test (CB2-O05): called inside a line's transaction after the order
# and before the ledger entry. None in production.
mid_line_hook: Callable[[dict], None] | None = None


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
    """The production reader: `EtsyClient.get_shop_receipts`, paged.

    `since` is a *last-modified* watermark: Etsy's `min_last_modified` returns every receipt
    created or changed after it, which is what a refund on an old receipt needs. None reads
    the whole history (bounded by `MAX_PAGES`).
    """

    # Etsy's `min_last_modified` returns receipts created *or changed* after `since`.
    SINCE_IS_LAST_MODIFIED = True

    def __init__(self, client) -> None:
        self.client = client
        self.calls = 0  # network calls made, reported by every run

    def receipts(self, *, since: datetime | None) -> list[dict]:
        out: list[dict] = []
        modified = int(since.timestamp()) if since is not None else None
        for page in range(MAX_PAGES):
            self.calls += 1
            got = self.client.get_shop_receipts(min_last_modified=modified, limit=PAGE,
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


def _ts(value) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def _when(receipt: dict) -> datetime:
    at = _ts(receipt.get("create_timestamp") or receipt.get("created_timestamp"))
    if at is None:
        raise IngestRefused(f"receipt {receipt.get('receipt_id')!r} has no creation time")
    return at


def revision(receipt: dict) -> int:
    """The receipt's source revision: its update time, else its creation time."""
    return int(receipt.get("update_timestamp") or receipt.get("updated_timestamp")
               or receipt.get("create_timestamp") or receipt.get("created_timestamp") or 0)


def receipt_state(receipt: dict) -> tuple[str, str]:
    """(state, why) for the receipt as a whole, from Etsy's own `status` and `is_paid`.

    Recognised states only. A status this module has not seen, a paid status contradicted
    by `is_paid: false`, or a receipt with no status at all is `unknown` and held: it is
    reported by name and written nowhere until somebody teaches this function what it means.
    """
    status = str(receipt.get("status") or "").strip().lower()
    is_paid = receipt.get("is_paid")
    if status in CANCELLED_STATES:
        return CANCELLED, f"status {status!r}"
    if status in UNPAID_STATES:
        return UNPAID, f"status {status!r}"
    if status in SALE_STATES:
        if is_paid is False:
            return UNKNOWN, f"status {status!r} but is_paid is false: contradictory"
        return PAID, f"status {status!r}" + ("" if is_paid else ", is_paid absent")
    if not status:
        return UNKNOWN, "no status on the receipt"
    if is_paid is False:
        return UNPAID, f"unrecognised status {status!r} with is_paid false"
    return UNKNOWN, f"unrecognised status {status!r}"


def _refunds(receipt: dict, amounts: dict[str, float],
             currency: str = "") -> tuple[dict[str, float], list[str]]:
    """(refunded amount per transaction line in the receipt's currency, problems).

    A refund naming a transaction is that line's. The rest is the receipt's and is allocated
    across its lines in proportion to their price, capped at each line's amount -- a
    line-appropriate figure rather than "every line refunded" (CB2-O01). A receipt whose
    status is `fully refunded` with no refund rows is treated as refunded in full.

    A refund in another currency than the receipt's is never read as the receipt's currency
    (RC1 audit E6), and a `partially refunded` status with no readable refund amount is a
    disagreement (E1): both come back as problems, and the caller holds the receipt.
    """
    status = str(receipt.get("status") or "").strip().lower()
    out = {tid: 0.0 for tid in amounts}
    pooled = 0.0
    problems: list[str] = []
    for r in receipt.get("refunds") or []:
        if not isinstance(r, dict):
            continue
        money = _money(r.get("amount"))
        if money is None or money[0] <= 0:
            continue
        if currency and money[1] != currency:
            if status != "fully refunded":
                problems.append(f"a refund of {money[0]:.2f} {money[1] or '(no currency)'} on "
                                f"a receipt in {currency}: it is not read as {currency}")
            continue
        tid = r.get("transaction_id")
        if tid is not None and str(tid) in out:
            out[str(tid)] += money[0]
        else:
            pooled += money[0]
    remaining = {tid: max(0.0, amounts[tid] - out[tid]) for tid in amounts}
    total_remaining = sum(remaining.values())
    if pooled > 0 and total_remaining > 0:
        share = min(1.0, pooled / total_remaining)
        for tid in amounts:
            out[tid] += remaining[tid] * share
    if status == "fully refunded":
        out = {tid: amounts[tid] for tid in amounts}
    elif status == "partially refunded" and sum(out.values()) <= 0.0:
        problems.append("status 'partially refunded' but the receipt carries no refund "
                        "amount in its own currency: how much was refunded is UNKNOWN")
    return {tid: round(min(amounts[tid], v), 4) for tid, v in out.items()}, problems


def lines(receipt: dict) -> list[dict]:
    """One dict per transaction line, with personal data dropped at the door.

    Every line carries the receipt's state, its own refund amount and the receipt's source
    revision, so the writer can reconcile it against what was recorded before.
    """
    rid = receipt.get("receipt_id")
    buyer = receipt.get("buyer_user_id")
    if rid is None or buyer in (None, ""):
        raise IngestRefused("a receipt needs its id and the buyer's Etsy user id")
    at = _when(receipt)
    state, why = receipt_state(receipt)
    rev = revision(receipt)
    priced: list[tuple[dict, float, str, int]] = []
    for t in receipt.get("transactions") or []:
        price = _money(t.get("price"))
        if price is None or not price[1]:
            raise IngestRefused(f"receipt {rid}: a line with no priced currency cannot be "
                                f"reconciled against anything")
        qty = max(1, int(t.get("quantity") or 1))
        priced.append((t, round(price[0] * qty, 4), price[1], qty))
    tids = [str(t.get("transaction_id")) for t, _a, _c, _q in priced]
    if len(set(tids)) != len(tids):
        # Two lines with one transaction id cannot both be keyed by it; which one is real is
        # not knowable here, so the receipt is refused whole and raised (RC1 audit E6).
        dupes = sorted({x for x in tids if tids.count(x) > 1})
        raise IngestRefused(f"receipt {rid}: duplicate transaction_id(s) {dupes}; a line "
                            f"would be silently lost")
    currencies = {c for _t, _a, c, _q in priced}
    if len(currencies) > 1:
        raise IngestRefused(f"receipt {rid}: lines in several currencies {sorted(currencies)}")
    amounts = {str(t.get("transaction_id")): amount for t, amount, _c, _q in priced}
    problems: list[str] = []
    if state == PAID:
        refunds, problems = _refunds(receipt, amounts, next(iter(currencies), ""))
    else:
        refunds = {k: 0.0 for k in amounts}
    if problems:
        state, why = UNRECONCILED, "; ".join(problems)
    # K8 F-535: what Etsy's refund rows say about why (reason / note_from_issuer), per line
    # when the refund names the transaction, else the receipt's. Text only, no buyer data.
    reasons: dict[str, list[str]] = {}
    for r in receipt.get("refunds") or []:
        if not isinstance(r, dict):
            continue
        said = [str(r.get(k)).strip()[:300] for k in ("reason", "note_from_issuer")
                if str(r.get(k) or "").strip()]
        if said:
            reasons.setdefault(str(r.get("transaction_id") or "*"), []).extend(said)
    out = []
    for t, amount, currency, qty in priced:
        tid = str(t.get("transaction_id"))
        refund = refunds.get(tid, 0.0)
        line_state = state
        if state == PAID and refund > 0:
            line_state = FULLY_REFUNDED if refund >= amount - 0.005 else PARTIALLY_REFUNDED
        out.append({
            "receipt_id": str(rid), "transaction_id": tid,
            "customer_ref": f"etsy-user-{buyer}",
            "listing_id": str(t.get("listing_id") or ""),
            "amount": amount, "currency": currency, "quantity": qty,
            "refund": refund, "state": line_state, "state_why": why,
            "at": at, "paid_at": _ts(t.get("paid_timestamp")) or at,
            "revision": rev, "status": str(receipt.get("status") or "").strip().lower(),
            "refund_reasons": reasons.get(tid, []) + reasons.get("*", []),
            # Kept for readers of the old shape; the state is the truth.
            "refunded": line_state == FULLY_REFUNDED,
        })
    return out


# ---------------------------------------------------------------------------
# What was listed under an Etsy listing id, and when (CB2-O03)


def listing_history(db) -> dict[str, list[dict]]:
    """Etsy listing id -> the versions listed under it, each with when it took effect.

    The effective time is the `store.published` audit row for that release when one exists
    (the publication is the immutable event) and the listing row's creation time otherwise.
    Sorted oldest first, so `version_at` can pick the version in force at a sale.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog, Listing

    published: dict[str, datetime] = {}
    with db.session() as s:
        for a in s.scalars(select(AuditLog).where(AuditLog.action == "store.published")):
            if a.artifact and a.at is not None:
                at = a.at if a.at.tzinfo else a.at.replace(tzinfo=timezone.utc)
                if a.artifact not in published or at < published[a.artifact]:
                    published[a.artifact] = at
        out: dict[str, list[dict]] = {}
        for r in s.scalars(select(Listing)):
            if not r.etsy_listing_id:
                continue
            created = r.created_at if r.created_at is None or r.created_at.tzinfo else \
                r.created_at.replace(tzinfo=timezone.utc)
            key = f"{r.product_slug}@{r.version}"
            at = published.get(key) or created
            out.setdefault(r.etsy_listing_id, []).append({
                "slug": r.product_slug, "version": r.version,
                "collection": r.version == "collection",
                "effective_from": at,
                "basis": "store.published" if key in published else "listing_row_created_at"})
    for entries in out.values():
        entries.sort(key=lambda e: (e["effective_from"] or datetime.min.replace(
            tzinfo=timezone.utc), e["version"]))
    return out


def version_at(history: dict[str, list[dict]], listing_id: str, at: datetime) -> dict:
    """The product and version listed under `listing_id` when the sale happened.

    The newest entry whose effective time is at or before the sale. A sale that predates
    every recorded entry names the product (a listing id belongs to one product) but its
    version is unknown, and says so, rather than the version listed later.
    """
    entries = history.get(listing_id) or []
    if not entries:
        return {"slug": "", "version": "", "collection": False, "matched": False,
                "basis": "unmatched: no listing of ours carries this Etsy listing id"}
    in_force = [e for e in entries if e["effective_from"] is None or e["effective_from"] <= at]
    if not in_force:
        first = entries[0]
        return {"slug": first["slug"], "version": "", "collection": first["collection"],
                "matched": True,
                "basis": (f"unknown: the sale predates the earliest recorded version "
                          f"({first['version']}, {first['basis']})")}
    e = in_force[-1]
    return {"slug": e["slug"], "version": "" if e["collection"] else e["version"],
            "collection": e["collection"], "matched": True, "basis": e["basis"]}


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
            "measured": bool(rate and rate["measured"]),
            "source": (rate.get("source") if rate else None) or "assumed"}


def _fee_provenance() -> dict:
    from . import fee_schedule as FS

    return {"basis": "estimated",
            "why": ("modelled from the fee schedule's dated reading of Etsy's fee pages, not "
                    "read back from a settlement; Offsite Ads and currency fees are not in it"),
            "claims": {k: {"evidence": c.evidence, "checked_on": c.checked_on}
                       for k, c in (("transaction", FS.TRANSACTION),
                                    ("payment_processing", FS.PAYMENT_PROCESSING),
                                    ("listing", FS.LISTING))}}


# ---------------------------------------------------------------------------
# Writing


def money_for(line: dict) -> dict:
    """Price, refund, fees and contribution in CAD, each with its provenance (CB2-O07)."""
    from .pricing import fees

    cad = _to_cad(line["amount"], line["currency"], line["at"].date())
    rate = cad["cad"] / line["amount"] if line["amount"] else 0.0
    price = round(cad["cad"], 2)
    refund = round(line["refund"] * rate, 2) if line["state"] != CANCELLED else price
    refund = min(price, refund)
    revenue = round(price - refund, 2)
    f = fees(price) if price > 0 else None
    fee_total = round(f.total_fees, 2) if f else 0.0
    # The fee stays with the platform when the money goes back; a refunded sale is a loss of
    # its fees and is recorded as one. Nothing here clamps it.
    contribution = round(revenue - fee_total, 2)
    return {"price_cad": price, "refund_cad": refund, "revenue_cad": revenue,
            "fees_cad": fee_total, "contribution_cad": contribution,
            "fx": {"usd_per_cad": cad["usd_per_cad"], "taken_on": cad["taken_on"],
                   "measured": cad["measured"],
                   "basis": "measured" if cad["measured"] else "assumed",
                   "source": cad["source"]},
            "fees": _fee_provenance(),
            "contribution_basis": ("revenue net of refunds less ESTIMATED fees; "
                                   + ("measured" if cad["measured"] else "assumed")
                                   + " FX rate")}


def _reconcile_existing(s, order, line: dict, money: dict, ledger) -> list[str]:
    """Bring an existing order (and its ledger entry) to the receipt's current truth.

    Keyed by the line's source revision: an older or equal revision with the same refund
    state changes nothing, a newer one sets (never adds) the refund, revenue, contribution
    and state. Idempotent under any number of re-reads.
    """
    detail = dict(order.detail or {})
    # A refund Etsy's ledger already showed paid out (finance.reconcile) is not undone by a
    # receipt that has not caught up: the larger of the two stands.
    receipt_refund_cad = money["refund_cad"]
    ledger_refund = float(detail.get("ledger_refund_cad") or 0.0)
    if ledger_refund > money["refund_cad"] + 0.005:
        refund = min(money["price_cad"], ledger_refund)
        money = {**money, "refund_cad": round(refund, 2),
                 "revenue_cad": round(money["price_cad"] - refund, 2)}
        money["contribution_cad"] = round(money["revenue_cad"] - money["fees_cad"], 2)
    stored_rev = int(detail.get("source_revision") or 0)
    same = (abs(float(order.revenue_cad or 0.0) - money["revenue_cad"]) < 0.005
            and detail.get("state") == line["state"])
    if line["revision"] < stored_rev or (line["revision"] == stored_rev and same):
        return []
    changed: list[str] = []
    if detail.get("state") != line["state"]:
        changed.append(f"state {detail.get('state')} -> {line['state']}")
    if abs(float(order.revenue_cad or 0.0) - money["revenue_cad"]) >= 0.005:
        changed.append(f"revenue {float(order.revenue_cad or 0.0):.2f} -> "
                       f"{money['revenue_cad']:.2f}")
    order.revenue_cad = money["revenue_cad"]
    # A fee Etsy's ledger already measured (finance.reconcile, F-558) is kept: a refund moves
    # revenue, never the charged fee back to the model. Contribution is revenue net of
    # refunds less whichever fee is on the row, signed -- a loss stays a loss (CB2-O07).
    # Any fee taken from Etsy's ledger (measured, partial, or under an unverified mapping)
    # is kept with the basis and text `finance.reconcile` gave it (RC1 audit E4, E5).
    from ..finance import reconcile

    measured = (order.fees_basis or "unknown") in reconcile.LEDGER_FEE_BASES
    fees_cad = float(order.fees_cad or 0.0) if measured else money["fees_cad"]
    prior_money = detail.get("money") or {}
    order.fees_cad = round(fees_cad, 2)
    order.contribution_cad = round(money["revenue_cad"] - fees_cad, 2)
    order.refunded = line["state"] in (FULLY_REFUNDED, CANCELLED)
    order.detail = {**detail, "state": line["state"], "state_why": line["state_why"],
                    "receipt_status": line.get("status", ""),
                    "source_revision": line["revision"],
                    # What the RECEIPT says was refunded; a larger refund Etsy's ledger
                    # showed is `ledger_refund_cad`, and revenue follows the larger.
                    "refund": {"amount_original": line["refund"], "cad": receipt_refund_cad,
                               "currency": line["currency"],
                               "reasons": list(line.get("refund_reasons") or [])},
                    "money": {"fx": money["fx"],
                              "fees": (prior_money.get("fees") or money["fees"]) if measured
                              else money["fees"],
                              "contribution_basis": (
                                  money["contribution_basis"] if not measured else
                                  prior_money.get("contribution_basis")
                                  or money["contribution_basis"])}}
    if ledger is not None:
        ledger.refunds_cad = money["refund_cad"]
        if not measured:
            ledger.fees_cad = money["fees_cad"]
    return changed or ["revision"]


# ---------------------------------------------------------------------------
# Held lines: recorded, never booked until they can be (RC1 audit E1, E3, E6)


def _held_row(s, create: bool = False):
    from sqlalchemy import select

    from ..core.models import OperatingReading

    row = s.scalar(select(OperatingReading).where(OperatingReading.kind == HELD_KIND,
                                                  OperatingReading.period_key == HELD_KEY))
    if row is None and create:
        row = OperatingReading(kind=HELD_KIND, period_key=HELD_KEY, payload={"records": {}})
        s.add(row)
    return row


def _hold(s, line: dict, ref: str, reason: str, why: str, *, order_recorded: bool) -> bool:
    """Record (or refresh) a held line. Returns False when a newer revision is already held.

    The record keeps the receipt's own currency and amount, and CAD as None -- UNKNOWN, never
    zero. Keyed by order reference, so re-reads are idempotent.
    """
    row = _held_row(s, create=True)
    records = dict((row.payload or {}).get("records") or {})
    old = records.get(ref) or {}
    if old and not old.get("resolved") and int(old.get("revision") or 0) > line["revision"]:
        return False
    records[ref] = {
        "ref": ref, "reason": reason, "why": why[:400], "state": line["state"],
        "receipt_status": line.get("status", ""), "revision": line["revision"],
        "at": line["paid_at"].isoformat(), "customer_ref": line["customer_ref"],
        "listing_id": line["listing_id"], "currency": line["currency"],
        "amount_original": line["amount"], "refund_original": line["refund"],
        "cad": None, "revenue_cad": None, "order_recorded": order_recorded,
        "first_held_at": old.get("first_held_at") if old and not old.get("resolved")
        else datetime.now(timezone.utc).isoformat(),
        "resolved": False}
    row.payload = {**(row.payload or {}), "records": records}
    row.at = datetime.now(timezone.utc)
    return True


def _release(s, ref: str, line: dict, resolution: str) -> bool:
    """Resolve a held record once the line has been booked at a revision at least as new."""
    row = _held_row(s)
    if row is None:
        return False
    records = dict((row.payload or {}).get("records") or {})
    old = records.get(ref)
    if not old or old.get("resolved") or int(old.get("revision") or 0) > line["revision"]:
        return False
    records[ref] = {**old, "resolved": True, "resolution": resolution,
                    "resolved_at": datetime.now(timezone.utc).isoformat()}
    row.payload = {**(row.payload or {}), "records": records}
    return True


def held(db, *, since: datetime | None = None, until: datetime | None = None,
         unresolved_only: bool = True) -> list[dict]:
    """Held lines, optionally within a sale-time window. Read by the books."""
    with db.session() as s:
        row = _held_row(s)
        records = list(((row.payload or {}).get("records") or {}).values()) if row else []
    out = []
    for r in records:
        if unresolved_only and r.get("resolved"):
            continue
        at = datetime.fromisoformat(r["at"]) if r.get("at") else None
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if at is not None and ((since is not None and at < _aware(since))
                               or (until is not None and at > _aware(until))):
            continue
        out.append(dict(r))
    return sorted(out, key=lambda r: (r.get("at") or "", r["ref"]))


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The one definition of a countable order (rc1-ORD2 item 3)
#
# Every reader that counts orders or sums their money -- the books, cohorts, order readings,
# the per-channel table, the dashboard, growth -- decides through `standing` below, so an
# order that becomes unreconciled or voided after it was recorded drops out of all of them
# at once instead of only out of the books.
#
# * `countable` -- a live sale: paid or partially refunded, revenue stated by its receipt,
#   not held. It counts as an order and its revenue and contribution are summed.
# * `voided`    -- refunded in full or cancelled. Never an order, a customer or revenue; its
#   contribution (the fee Etsy kept, a loss) stays in contribution sums (CB2-O07, E2).
# * `unreconciled` / `held` -- revenue UNKNOWN (E1/E3/E6). Nothing of it is counted or summed.

STANDING_COUNTABLE, STANDING_VOIDED = "countable", "voided"
STANDING_UNRECONCILED, STANDING_HELD = "unreconciled", "held"


def held_refs(session) -> frozenset[str]:
    """References of every unresolved held line, read inside the caller's session."""
    row = _held_row(session)
    records = ((row.payload or {}).get("records") or {}) if row is not None else {}
    return frozenset(ref for ref, r in records.items() if not (r or {}).get("resolved"))


def standing(order, held: frozenset[str] | set[str] = frozenset()) -> str:
    """countable | voided | unreconciled | held for one Order row."""
    detail = order.detail or {}
    state = detail.get("state")
    if order.external_ref in held:
        return STANDING_HELD
    if state == UNRECONCILED or detail.get("revenue_unknown"):
        return STANDING_UNRECONCILED
    if bool(order.refunded) or state in VOIDED_STATES:
        return STANDING_VOIDED
    if state is not None and state not in (PAID, PARTIALLY_REFUNDED):
        # unpaid / unknown / anything unrecognised is not a sale.
        return STANDING_UNRECONCILED
    return STANDING_COUNTABLE


def countable(order, held: frozenset[str] | set[str] = frozenset()) -> bool:
    """Counts as an order, a customer's purchase and revenue."""
    return standing(order, held) == STANDING_COUNTABLE


def in_books(order, held: frozenset[str] | set[str] = frozenset()) -> bool:
    """Its money is in the sums: countable, or voided (revenue 0, the retained-fee loss)."""
    return standing(order, held) in (STANDING_COUNTABLE, STANDING_VOIDED)


def countable_orders(session, query=None) -> list:
    """The countable Order rows of `query` (default: every order)."""
    from sqlalchemy import select

    from ..core.models import Order

    held = held_refs(session)
    return [o for o in session.scalars(query if query is not None else select(Order))
            if countable(o, held)]


def booked_orders(session, query=None) -> list:
    """The Order rows of `query` whose money is in the books (countable or voided)."""
    from sqlalchemy import select

    from ..core.models import Order

    held = held_refs(session)
    return [o for o in session.scalars(query if query is not None else select(Order))
            if in_books(o, held)]


def _raise_held_incidents(db, refused: list[dict], now: datetime) -> dict:
    """One idempotent incident per held reason, resolved when nothing of it is held."""
    from ..ops import incident_lifecycle as lifecycle

    open_held = held(db)
    out = {}
    plan = (
        (UNCONVERTED_INCIDENT, [r for r in open_held if r["reason"] == HELD_UNCONVERTED],
         "paid sale(s) in a currency with no rate on file are held unconverted: their CAD "
         "value is UNKNOWN and sales cannot read as measured until a rate is recorded"),
        (UNRECONCILED_INCIDENT, [r for r in open_held if r["reason"] == HELD_UNRECONCILED],
         "receipt(s) whose status and refunds disagree are held UNRECONCILED: revenue for "
         "those orders is UNKNOWN until Etsy states the refund"),
    )
    with db.session() as s:
        for signature, rows, summary in plan:
            if rows:
                _inc, opened = lifecycle.open_or_restate(
                    s, signature=signature, severity="P2",
                    summary=f"{len(rows)} {summary}",
                    detail={"refs": [r["ref"] for r in rows][:200],
                            "amounts": [{"ref": r["ref"], "currency": r["currency"],
                                         "amount_original": r["amount_original"],
                                         "why": r["why"][:200]} for r in rows][:50]},
                    now=now)
                out[signature] = "opened" if opened else "restated"
            elif lifecycle.resolve_signatures(
                    s, [signature], now=now,
                    resolution="no held line of this kind remains: every one was booked "
                               "or voided at a newer receipt revision"):
                out[signature] = "resolved"
        if refused:
            _inc, opened = lifecycle.open_or_restate(
                s, signature=ANOMALY_INCIDENT, severity="P2",
                summary=(f"{len(refused)} receipt line(s) could not be placed and were not "
                         f"written (duplicate transaction ids, no buyer, no currency, an "
                         f"amount that reconciles to nothing): nothing was guessed"),
                detail={"refused": refused[:50]}, now=now)
            out[ANOMALY_INCIDENT] = "opened" if opened else "restated"
    return out


def _record_line(db, line: dict, history: dict[str, list[dict]]) -> dict:
    """One receipt line, written or reconciled inside ONE transaction (CB2-O05)."""
    from sqlalchemy import select

    from ..commerce import cohorts
    from ..core.models import LedgerEntry, Order

    ref = f"etsy:{line['receipt_id']}:{line['transaction_id']}"
    listed = version_at(history, line["listing_id"], line["at"])
    slug = listed["slug"] or f"etsy-listing-{line['listing_id'] or 'unknown'}"
    version = listed["version"]
    seed = _seed(slug)
    category = seed.category if seed else ""
    season = (seed.season or "none") if seed else "none"
    offer = ("complete_collection" if listed["collection"] else
             "seasonal_bundle" if seed and seed.is_bundle and seed.season else
             "mini_bundle" if seed and seed.is_bundle else "single_pattern")

    with db.session() as s:
        existing = s.scalar(select(Order).where(Order.external_ref == ref))
        if line["state"] == UNRECONCILED:
            # E1/E6: revenue is UNKNOWN. A new line is held, not booked; a recorded order is
            # marked unreconciled (its row stays, the books exclude it) -- never rewritten to
            # a figure nobody stated.
            if existing is not None:
                detail = dict(existing.detail or {})
                if line["revision"] < int(detail.get("source_revision") or 0):
                    return {"ref": ref, "recorded": True, "order_created": False,
                            "reconciled": [], "state": detail.get("state"),
                            "matched_listing": listed["matched"], "version": version,
                            "version_known": bool(version)}
                existing.detail = {**detail, "state": UNRECONCILED,
                                   "state_why": line["state_why"],
                                   "receipt_status": line.get("status", ""),
                                   "source_revision": line["revision"],
                                   "revenue_unknown": True}
            _hold(s, line, ref, HELD_UNRECONCILED, line["state_why"],
                  order_recorded=existing is not None)
            return {"ref": ref, "recorded": existing is not None, "held": UNRECONCILED,
                    "why": f"{UNRECONCILED}: {line['state_why']}"}
        if line["state"] not in SALE_LINE_STATES and existing is None:
            # Unpaid, cancelled-before-recording or unknown: held, written nowhere.
            return {"ref": ref, "recorded": False, "held": line["state"],
                    "why": f"{line['state']}: {line['state_why']}; not a sale"}
        if line["state"] in (UNPAID, UNKNOWN) and existing is not None:
            # A recorded sale whose receipt now reads unpaid or unrecognised is a
            # contradiction to hold, not a row to silently rewrite.
            return {"ref": ref, "recorded": False, "held": line["state"],
                    "why": (f"{line['state']}: {line['state_why']}; a recorded sale is not "
                            f"rewritten from a state this module does not recognise")}
        try:
            money = money_for(line)
        except Exception as exc:  # noqa: BLE001 - a currency with no rate is recorded, not guessed
            # E3: a paid sale in a currency with no rate is HELD with its own currency and
            # amount and CAD as UNKNOWN -- never dropped, never converted at a made-up rate.
            if line["state"] in SALE_LINE_STATES:
                _hold(s, line, ref, HELD_UNCONVERTED, str(exc)[:300], order_recorded=False)
                return {"ref": ref, "recorded": False, "held": HELD_UNCONVERTED,
                        "currency": line["currency"], "amount_original": line["amount"],
                        "why": str(exc)[:200]}
            if line["state"] == CANCELLED and _release(
                    s, ref, line, "voided: the receipt was cancelled before it could be "
                                  "converted"):
                return {"ref": ref, "recorded": False, "held": CANCELLED,
                        "why": "cancelled; the held unconverted line is voided"}
            return {"ref": ref, "recorded": False, "why": str(exc)[:200]}

        detail = {"listing_id": line["listing_id"], "receipt_id": line["receipt_id"],
                  "matched_listing": listed["matched"], "version_basis": listed["basis"],
                  "season": season, "state": line["state"], "state_why": line["state_why"],
                  "receipt_status": line.get("status", ""),
                  "fees_model": ("commerce.pricing.fees (transaction + payment processing + "
                                 "amortised listing; offsite/regulatory/conversion "
                                 "unmodelled)"),
                  "source_revision": line["revision"],
                  "refund": {"amount_original": line["refund"], "cad": money["refund_cad"],
                             "currency": line["currency"],
                             "reasons": list(line.get("refund_reasons") or [])},
                  "attribution": {"basis": ATTRIBUTION_BASIS, "marketplace": "etsy",
                                  "channel": "unknown", "confidence": "none",
                                  "why": ("an Etsy receipt carries no acquisition channel: "
                                          "the buyer may have arrived from search, Etsy "
                                          "Ads, Offsite Ads, a pin or a link, and nothing "
                                          "on the receipt says which")},
                  "money": {"fx": money["fx"], "fees": money["fees"],
                            "contribution_basis": money["contribution_basis"]}}
        customer = cohorts.record_customer(
            db, line["customer_ref"], at=line["paid_at"], acquisition_source="unknown",
            first_product_slug=slug, first_category=category, first_season=season,
            session=s)
        order = cohorts.record_order(
            db, line["customer_ref"], ref, product_slug=slug, at=line["paid_at"],
            version=version, category=category, price_cad=money["price_cad"],
            revenue_cad=money["revenue_cad"], contribution_cad=money["contribution_cad"],
            acquisition_source="unknown",
            refunded=line["state"] in (FULLY_REFUNDED, CANCELLED),
            currency=line["currency"], amount_original=line["amount"],
            fx_usd_per_cad=money["fx"]["usd_per_cad"], fx_taken_on=money["fx"]["taken_on"],
            fx_measured=money["fx"]["measured"], fees_cad=money["fees_cad"], offer=offer,
            source=SOURCE, detail=detail, session=s)
        if order.get("created"):
            # F-609: the fee on a new order is the model's until the ledger replaces it.
            # `offsite_ads_fee_cad` stays None (not read), never 0.0 (read, none charged).
            row = s.scalar(select(Order).where(Order.external_ref == ref))
            if row is not None and (row.fees_basis or "unknown") != "measured":
                row.fees_basis = "modelled"
        if mid_line_hook is not None:
            mid_line_hook(line)
        ledger_row = s.scalar(select(LedgerEntry).where(LedgerEntry.evidence_ref == ref))
        ledger = False
        if ledger_row is None:
            ledger_row = LedgerEntry(
                at=line["paid_at"], category="sale",
                description=(f"Etsy receipt {line['receipt_id']} ({slug}); fees modelled, "
                             f"FX {money['fx']['basis']}"),
                gross_cad=money["price_cad"], fees_cad=money["fees_cad"],
                refunds_cad=money["refund_cad"], evidence_ref=ref, source=SOURCE,
                external_id=ref, currency=line["currency"], amount_original=line["amount"],
                classification="sale", basis="measured", fees_basis="modelled",
                reconciliation_state="unreconciled")
            existing_order = s.scalar(select(Order).where(Order.external_ref == ref))
            from ..finance import reconcile as _rec

            if existing_order is not None and \
                    existing_order.fees_basis in _rec.LEDGER_FEE_BASES:
                # Repairing a ledger row lost to a crash after the fee was read from Etsy.
                ledger_row.fees_cad = float(existing_order.fees_cad or 0.0)
                ledger_row.fees_basis = existing_order.fees_basis
            s.add(ledger_row)
            ledger = True
        reconciled: list[str] = []
        if not order.get("created"):
            row = s.scalar(select(Order).where(Order.external_ref == ref))
            reconciled = _reconcile_existing(s, row, line, money, ledger_row)
        current = s.scalar(select(Order).where(Order.external_ref == ref))
        if current is not None and (current.detail or {}).get("state") == line["state"]:
            if (current.detail or {}).get("revenue_unknown"):
                current.detail = {k: v for k, v in (current.detail or {}).items()
                                  if k != "revenue_unknown"}
            _release(s, ref, line, f"booked as {line['state']} at receipt revision "
                                   f"{line['revision']}")
        cohorts.reconcile_customer(db, line["customer_ref"], session=s)
    return {"ref": ref, "recorded": True, "order_created": bool(order.get("created")),
            "customer_created": bool(customer.get("created")), "ledger": ledger,
            "reconciled": reconciled, "state": line["state"],
            "matched_listing": listed["matched"], "version": version,
            "version_known": bool(version), "refund_cad": money["refund_cad"]}


# ---------------------------------------------------------------------------
# The cursor


def cursor(db) -> dict:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == CURSOR_KIND,
                                                      OperatingReading.period_key == CURSOR_KEY))
        return dict(row.payload or {}) if row is not None else {}


def _save_cursor(db, payload: dict) -> None:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == CURSOR_KIND,
                                                      OperatingReading.period_key == CURSOR_KEY))
        if row is None:
            row = OperatingReading(kind=CURSOR_KIND, period_key=CURSOR_KEY)
            s.add(row)
        row.payload = payload
        row.at = datetime.now(timezone.utc)


def _plan_read(state: dict, now: datetime) -> tuple[datetime | None, str]:
    """Where to read from: the cursor less the overlap, or everything on a sweep."""
    last_modified = state.get("last_modified")
    last_sweep = state.get("last_full_sweep")
    if not last_modified:
        return None, "initial: no cursor yet, reading the whole history"
    if not last_sweep or now - datetime.fromisoformat(last_sweep) >= FULL_SWEEP_EVERY:
        return None, (f"reconciliation sweep: the whole history is re-read every "
                      f"{FULL_SWEEP_EVERY.days} days so a change the cursor missed is found")
    return datetime.fromisoformat(last_modified) - OVERLAP, "cursor: receipts modified since"


def ingest(db, *, reader=None, now: datetime | None = None) -> dict:
    """One ingest run: gate, read, write, reconcile. UNMEASURED with the reason when gated."""
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

    before = cursor(db)
    since, mode = _plan_read(before, now)
    # A reader that does not declare its `since` a last-modified watermark may filter by
    # creation time; an incremental read through it would lose a refund on an old receipt.
    # It is asked from no later than the change window (FB-2 O; Codex O01 old-modified).
    read_since = since
    if since is not None and not getattr(reader, "SINCE_IS_LAST_MODIFIED", False):
        read_since = min(since, now - CHANGE_WINDOW)
        mode += (f"; the reader does not declare `since` a last-modified watermark, so it is "
                 f"asked from {CHANGE_WINDOW.days} days back (the change window)")
    try:
        receipts = reader.receipts(since=read_since)
    except EtsyAuthNeedsOwner as exc:
        raised = needs_owner(db, exc, operation=OPERATION, now=now)
        return {"ran": False, "reading": "UNMEASURED", "gate": state,
                "network_calls": getattr(reader, "calls", None), "auth_failure": raised,
                "why": ("the Etsy credential needs the owner (" + raised["failure_class"]
                        + "): " + str(exc)[:300] + ". Receipts were not read; no order is "
                        "invented and nothing is retried until the owner re-authorises")}
    # F-541: the read worked, so a re-authorisation request raised by an earlier refusal no
    # longer describes the shop; it closes on this evidence, never on a readiness sweep.
    auth_cleared = resolve_needs_owner(db, operation=OPERATION, now=now)
    history = listing_history(db)
    written, refused, held_lines = [], [], []
    from .cohorts import CohortRefused

    newest = int(datetime.fromisoformat(before["last_modified"]).timestamp()) \
        if before.get("last_modified") else 0
    for receipt in receipts:
        try:
            for line in lines(receipt):
                try:
                    got = _record_line(db, line, history)
                except CohortRefused as exc:
                    # One line the cohort writer refuses (an amount that reconciles to
                    # nothing) is recorded as such; it does not stop the other receipts.
                    refused.append({"receipt_id": receipt.get("receipt_id"),
                                    "transaction_id": line["transaction_id"],
                                    "why": str(exc)[:200]})
                    continue
                (held_lines if got.get("held") else written).append(got)
            newest = max(newest, revision(receipt))
        except IngestRefused as exc:
            refused.append({"receipt_id": receipt.get("receipt_id"), "why": str(exc)[:200]})
    # The run completed: the cursor may move. Held receipts (unpaid, unknown) are re-read
    # when Etsy changes them, because that changes their update_timestamp.
    after = {"last_modified": (datetime.fromtimestamp(newest, tz=timezone.utc).isoformat()
                               if newest else before.get("last_modified")),
             "last_full_sweep": (now.isoformat() if since is None
                                 else before.get("last_full_sweep")),
             "runs": int(before.get("runs") or 0) + 1, "last_run": now.isoformat(),
             "last_mode": mode}
    _save_cursor(db, after)
    from . import cohorts

    held_incidents = _raise_held_incidents(db, refused, now)
    validation = cohorts.reconcile_validation_cohort(db) if written else None
    created = [w for w in written if w.get("order_created")]
    fees = _reconcile_fees(db, reader, since=since, now=now)
    from ..finance import sources

    first = sources.record_first_sale(db)
    return {
        "ran": True, "reading": "measured", "gate": state,
        "network_calls": getattr(reader, "calls", None),
        "since": read_since.isoformat() if read_since else None, "read_mode": mode,
        "cursor": after, "at": now.isoformat(),
        "receipts": len(receipts), "lines": len(written),
        "orders_created": len(created),
        "orders_reconciled": sum(1 for w in written if w.get("reconciled")),
        "reconciliations": [{"ref": w["ref"], "changes": w["reconciled"]}
                            for w in written if w.get("reconciled")],
        "customers_created": sum(1 for w in written if w.get("customer_created")),
        "ledger_entries": sum(1 for w in written if w.get("ledger")),
        "versions_recorded": sum(1 for w in created if w.get("version")),
        "versions_unknown": sorted(w["ref"] for w in written
                                   if w.get("recorded") and not w.get("version_known")),
        "unmatched_listings": sorted({w["ref"] for w in written
                                      if w.get("recorded") and not w.get("matched_listing")}),
        "held": held_lines,
        "held_by_state": {st: sum(1 for h in held_lines if h["held"] == st)
                          for st in sorted({h["held"] for h in held_lines})},
        "not_recorded": [w for w in written if not w.get("recorded")] + refused,
        # RC1 audit E1/E3/E6: lines held (not booked) because their CAD value or refund is
        # UNKNOWN. Durable (`held()`), each with an incident; the books read them.
        "held_unresolved": [{k: r.get(k) for k in ("ref", "reason", "currency",
                                                     "amount_original", "why")}
                            for r in held(db)],
        "held_incidents": held_incidents,
        "fees": fees,
        "first_sale": ({k: first.get(k) for k in ("external_ref", "acquisition_source",
                                                  "created")} if first else None),
        "validation_cohort": validation,
        "auth_cleared": auth_cleared,
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

    Routed through `runtime.etsy_ops.record_auth_needs_owner` (F-541): one key, one incident
    and one severity for the one remedy, whichever path met the refusal first. Idempotent:
    a six-hourly cadence hitting the same revoked grant restates the open action and counts
    another report on the open incident; it never adds a second row, and it never re-opens
    an action the owner has closed while the incident is still open (their "done" is theirs
    -- if the failure recurs after it, the incident count says so).
    """
    from sqlalchemy import select

    from ..core.models import Incident, OwnerAction
    from ..ops import incident_lifecycle as lifecycle
    from ..runtime import etsy_ops

    now = now or datetime.now(timezone.utc)
    kind = failure_class(exc)
    # Adopt the legacy pair (written before the paths were unified) rather than leave a
    # second request for the same browser step beside the canonical one.
    with db.session() as s:
        legacy = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == LEGACY_AUTH_ACTION_KEY,
            OwnerAction.done == False)))  # noqa: E712
        canonical = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == AUTH_ACTION_KEY,
            OwnerAction.done == False))  # noqa: E712
        for row in legacy:
            if canonical is None:
                row.requirement_key = AUTH_ACTION_KEY
                canonical = row
            else:
                from ..ops import owner_queue
                owner_queue.close(row, owner_queue.SUPERSEDED,
                                  f"merged into {AUTH_ACTION_KEY}")
                row.reason = (row.reason or "") + (f" [merged into {AUTH_ACTION_KEY}, which "
                                                   f"carries the same step]")
        if s.scalar(select(Incident).where(
                Incident.signature == LEGACY_AUTH_INCIDENT_SIGNATURE,
                Incident.resolved == False)) is not None:  # noqa: E712
            lifecycle.resolve_signatures(
                s, [LEGACY_AUTH_INCIDENT_SIGNATURE], now=now,
                resolution=f"merged into {AUTH_INCIDENT_SIGNATURE} (one remedy, one incident)")
    got = etsy_ops.record_auth_needs_owner(db, exc, where=f"orders_ingest.{operation}",
                                           now=now)
    return {"failure_class": kind, "operation": operation,
            "owner_action": got["state"],
            "owner_action_key": got["owner_action"],
            "incident": "opened" if got["incident_opened"] else "counted",
            "incident_signature": got["incident"], "severity": "P1"}


def resolve_needs_owner(db, *, operation: str, now: datetime | None = None) -> dict:
    """An authenticated read of `operation` succeeded: the condition no longer holds.

    Closes the shared re-authorisation action and incident through
    `etsy_ops.resolve_auth_needs_owner`, which keeps them open when the failure was a scope
    the stored grant still lacks.
    """
    from ..runtime import etsy_ops

    return etsy_ops.resolve_auth_needs_owner(
        db, evidence=(f"an authenticated {operation} read succeeded at "
                      f"{(now or datetime.now(timezone.utc)).isoformat()}"),
        granted_scopes=granted_scopes(db))
