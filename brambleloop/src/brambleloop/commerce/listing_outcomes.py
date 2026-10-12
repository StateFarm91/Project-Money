"""Listing outcomes, actually written: the producer the funnel readers were waiting for (K3).

Wave-3 cluster K3 (F-258, F-259, F-260, F-261, F-282, F-297). Every funnel reader in this
company -- the weekly portfolio review's stage diagnosis (#47), the experiment conclusion
step (#265/#266), style and outcome learning (#82/#89), the SEO measurement loop, the war
room, the run-rate -- reads `ListingOutcome`. Until this module, nothing at runtime wrote a
row: `creative.style_learning.record_outcome` existed and had no caller, so every one of
those readers was correct only in the trivial sense that an empty table is always
UNMEASURED.

Two sources, each read only as far as it honestly goes:

1. **The owner's listing-level Etsy Stats export** (impressions, visits, favourites, carts,
   orders per listing per period). Etsy shows these in the seller dashboard and no API scope
   this company holds returns impressions. `submit_export` reads the CSV strictly -- a row it
   cannot read refuses the whole export with its line number, blank is never zero -- and
   resolves every row to one of *our* listings before anything is stored. The stored export
   is an inbox row; the scheduled producer (`produce`) records it through
   `style_learning.record_outcome` (the one writer, which refuses impossible counts and tags
   the hero style) and reads every row back to prove the round trip.

2. **The Etsy API, read-only** (`getListingsByShop`, `listings_r`): each active listing's
   cumulative `views` and `num_favorers`. Two daily snapshots give a period's visits and
   favourites as a difference. The API exposes no impressions and no carts, so those stay
   UNKNOWN, and because `ListingOutcome.impressions` is a measured count (never a guess),
   an API period is stored as a reading and never as a `ListingOutcome` row: a visits
   number with an invented impressions denominator is the click-through rate this company
   must never print. No credentials (today) is UNKNOWN, never zero.

`measurement_status` is F-297: automated optimisation (ad eligibility, the steer's winner
credit) may act only once an organic listing reading has been recorded *by this intake* and
read back intact -- and, for paid media, a paid one too. A fixture or a hand-inserted row is
not proof that measurement works.

GREEN: reads the database and (when a credential exists) Etsy read-only; writes
`listing_outcomes` and `operating_readings`. Spends nothing, publishes nothing, messages
nobody.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

UNKNOWN = "UNKNOWN"

#: The inbox of owner exports, one row per export (period_key = "x:" + sha prefix).
EXPORT_KIND = "listing_outcomes.export"
#: The daily API snapshot of cumulative views/favourites per listing id.
SNAPSHOT_KIND = "listing_outcomes.api_snapshot"
#: The producer's daily reading: per-listing funnel, sources, measurement status.
READING_KIND = "listing_outcomes.reading"

#: Every `ListingOutcome.source` this intake writes starts with one of these. Measurement is
#: proven only by rows that carry one -- never by a fixture or a hand-inserted row.
EXPORT_SOURCE = "owner_export:"
INTAKE_PREFIXES: tuple[str, ...] = (EXPORT_SOURCE,)

#: Traffic sources that make a period paid (`runtime.growth_ops.AD_SOURCES` is the same set;
#: restated here so this library does not import the runtime).
PAID_SOURCES: tuple[str, ...] = ("etsy_ads", "offsite_ads", "paid_ads")

# Listing-level Stats columns and the headings they are accepted under (lower-cased). "views"
# is deliberately accepted for nothing: on Etsy a listing's views are page views, the
# search-term export uses the word for impressions, and a column whose meaning depends on
# which export it came from is refused by name rather than guessed.
COLUMNS: dict[str, tuple[str, ...]] = {
    "listing": ("listing id", "listing_id", "etsy listing id", "slug", "listing slug",
                "listing", "listing title", "title"),
    "impressions": ("impressions", "search impressions", "times shown"),
    "visits": ("visits", "listing visits", "clicks"),
    "favourites": ("favourites", "favorites", "favs"),
    "carts": ("carts", "added to cart", "add to cart", "cart adds"),
    "orders": ("orders", "sales", "purchases"),
    "traffic_source": ("traffic source", "traffic_source", "channel"),
}
REQUIRED: tuple[str, ...] = ("listing", "impressions", "visits")


class OutcomeRefused(ValueError):
    """An export that cannot be read, or that names a listing that is not ours."""


# ---------------------------------------------------------------------------
# Parsing (strict)


def _header_map(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise OutcomeRefused("the CSV has no header row")
    lowered = {f.strip().lower(): f for f in fieldnames if f}
    if "views" in lowered and not any(a in lowered for a in COLUMNS["impressions"]):
        raise OutcomeRefused(
            "the export has a 'views' column and no impressions column. Listing views are "
            "page views, not impressions; export with the impressions column, or the "
            "click-through rate would be computed against the wrong denominator")
    found: dict[str, str] = {}
    for key, aliases in COLUMNS.items():
        for alias in aliases:
            if alias in lowered:
                found[key] = lowered[alias]
                break
    missing = [k for k in REQUIRED if k not in found]
    if missing:
        raise OutcomeRefused(
            f"the export has no column for {missing}; headings seen: {fieldnames}. Accepted: "
            f"{ {k: list(COLUMNS[k]) for k in missing} }")
    return found


def _count(raw: str | None, *, line: int, what: str) -> int:
    text = (raw or "").strip().replace(",", "")
    if text == "":
        raise OutcomeRefused(f"line {line}: {what} is blank; blank is not zero")
    try:
        value = int(text)
    except ValueError as exc:
        raise OutcomeRefused(f"line {line}: {what} {raw!r} is not a whole number") from exc
    if value < 0:
        raise OutcomeRefused(f"line {line}: {what} {value} is negative")
    return value


def parse_export(text: str) -> list[dict]:
    """Read a listing-level Stats export into rows, refusing anything malformed.

    An optional column that is present must be filled on every row (blank is not zero); an
    optional column that is absent is UNKNOWN for every row (None), never zero. Visits never
    exceed impressions and orders never exceed visits. A listing appears once.
    """
    reader = csv.DictReader(io.StringIO(text or ""))
    cols = _header_map(reader.fieldnames)
    rows: list[dict] = []
    seen: dict[str, int] = {}
    for n, raw in enumerate(reader, start=2):
        ref = (raw.get(cols["listing"]) or "").strip()
        if not ref:
            raise OutcomeRefused(f"line {n}: the listing is blank")
        if ref.lower() in seen:
            raise OutcomeRefused(f"line {n}: {ref!r} already appeared on line "
                                 f"{seen[ref.lower()]}; a listing listed twice is counted twice")
        seen[ref.lower()] = n
        row: dict[str, Any] = {"listing": ref, "line": n}
        row["impressions"] = _count(raw.get(cols["impressions"]), line=n, what="impressions")
        row["visits"] = _count(raw.get(cols["visits"]), line=n, what="visits")
        for key in ("favourites", "carts", "orders"):
            row[key] = (_count(raw.get(cols[key]), line=n, what=key) if key in cols else None)
        src = (raw.get(cols["traffic_source"]) or "").strip().lower() \
            if "traffic_source" in cols else ""
        row["traffic_source"] = src or None
        if row["visits"] > row["impressions"]:
            raise OutcomeRefused(f"line {n}: {row['visits']} visits from {row['impressions']} "
                                 f"impressions; a listing cannot be visited more often than "
                                 f"it was shown")
        if row["orders"] is not None and row["orders"] > row["visits"]:
            raise OutcomeRefused(f"line {n}: {row['orders']} orders from {row['visits']} visits")
        rows.append(row)
    if not rows:
        raise OutcomeRefused("the export has a header and no rows")
    return rows


def _listing_index(db) -> dict[str, tuple[str, str]]:
    """Every way an export may name one of our listings -> (slug, version)."""
    from sqlalchemy import select

    from ..core.models import Listing

    index: dict[str, tuple[str, str]] = {}
    ambiguous: set[str] = set()
    with db.session() as s:
        for r in s.scalars(select(Listing).where(Listing.version != "collection")
                           .order_by(Listing.id)):
            keys = {r.product_slug.lower()}
            if r.etsy_listing_id:
                keys.add(str(r.etsy_listing_id).lower())
            if r.title:
                keys.add(r.title.strip().lower())
            for k in keys:
                prior = index.get(k)
                if prior is not None and prior[0] != r.product_slug:
                    ambiguous.add(k)
                index[k] = (r.product_slug, r.version)
    for k in ambiguous:
        index.pop(k, None)
    return index


def _resolve(db, rows: list[dict]) -> list[dict]:
    index = _listing_index(db)
    out = []
    slugs: dict[str, int] = {}
    for r in rows:
        hit = index.get(r["listing"].lower())
        if hit is None:
            raise OutcomeRefused(
                f"line {r['line']}: {r['listing']!r} is not one of this shop's listings (by "
                f"Etsy listing id, slug or exact title). An outcome credited to the wrong "
                f"product is worse than no outcome")
        if hit[0] in slugs:
            raise OutcomeRefused(f"line {r['line']}: {r['listing']!r} is the same product as "
                                 f"line {slugs[hit[0]]}")
        slugs[hit[0]] = r["line"]
        out.append({**r, "slug": hit[0], "version": hit[1]})
    return out


def _period(period_start: str, period_end: str) -> tuple[date, date]:
    try:
        start, end = date.fromisoformat(period_start), date.fromisoformat(period_end)
    except (TypeError, ValueError) as exc:
        raise OutcomeRefused(f"period dates must be ISO dates: {exc}") from exc
    if end < start:
        raise OutcomeRefused("a period cannot end before it starts")
    return start, end


# ---------------------------------------------------------------------------
# Intake (what the owner route calls)


def submit_export(db, text: str, *, period_start: str, period_end: str,
                  submitted_by: str = "owner", now: datetime | None = None) -> dict:
    """Validate an owner listing-level Stats export now, and queue it for the producer.

    Everything that can be refused is refused here, synchronously, so the owner sees the line
    that is wrong: the shape, every count, the period, and every listing resolved to one of
    ours. A valid export is stored as an inbox reading (idempotent on its content and period)
    and recorded into `listing_outcomes` by the next `produce` run.
    """
    from sqlalchemy import select

    from ..core.models import OperatingReading

    start, end = _period(period_start, period_end)
    if end > (now or datetime.now(timezone.utc)).date():
        raise OutcomeRefused("a period that has not finished cannot have been measured")
    rows = _resolve(db, parse_export(text))
    digest = hashlib.sha256(f"{period_start}|{period_end}|{text}".encode()).hexdigest()
    key = "x:" + digest[:16]
    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        existing = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == EXPORT_KIND, OperatingReading.period_key == key))
        if existing is not None:
            return {"queued": False, "export": key,
                    "status": (existing.payload or {}).get("status"),
                    "why": "this export for this period was already submitted"}
        s.add(OperatingReading(kind=EXPORT_KIND, period_key=key, at=now, payload={
            "status": "pending", "sha256": digest, "submitted_by": submitted_by,
            "submitted_at": now.isoformat(), "period_start": start.isoformat(),
            "period_end": end.isoformat(), "rows": rows}))
    return {"queued": True, "export": key, "rows": len(rows),
            "listings": sorted(r["slug"] for r in rows)}


def _record_export(db, key: str, payload: dict) -> dict:
    """Write one queued export through the one writer, then read every row back."""
    from sqlalchemy import select

    from ..core.models import ListingOutcome
    from ..creative import style_learning

    source = f"{EXPORT_SOURCE}{payload['sha256'][:16]}"
    ps, pe = payload["period_start"], payload["period_end"]
    try:
        rows = _resolve(db, [{k: r[k] for k in ("listing", "line", "impressions", "visits",
                                                 "favourites", "carts", "orders",
                                                 "traffic_source")}
                             for r in payload.get("rows") or []])
    except OutcomeRefused as e:
        return {"status": "refused", "why": str(e)}
    recorded, refused = [], []
    for r in rows:
        try:
            style_learning.record_outcome(
                db, product_slug=r["slug"], version=r["version"], period_start=ps,
                period_end=pe, impressions=r["impressions"], visits=r["visits"],
                favourites=r["favourites"], orders=r["orders"], source=source)
        except style_learning.StyleLearningRefused as e:
            refused.append({"line": r["line"], "slug": r["slug"], "why": str(e)})
            continue
        detail = {"export": key, "line": r["line"], "carts": r["carts"],
                  "basis": "measured", "source_kind": "owner_listing_stats_export"}
        if r["traffic_source"]:
            detail["traffic_source"] = r["traffic_source"]
            detail["paid"] = r["traffic_source"] in PAID_SOURCES
        with db.session() as s:
            row = s.scalar(select(ListingOutcome).where(
                ListingOutcome.product_slug == r["slug"], ListingOutcome.period_start == ps,
                ListingOutcome.period_end == pe))
            row.detail = {**dict(row.detail or {}), **detail}
        recorded.append(r)
    # The round trip: every recorded row read back from the table, field by field.
    mismatches = []
    with db.session() as s:
        for r in recorded:
            row = s.scalar(select(ListingOutcome).where(
                ListingOutcome.product_slug == r["slug"], ListingOutcome.period_start == ps,
                ListingOutcome.period_end == pe))
            got = None if row is None else {
                "impressions": row.impressions, "visits": row.visits,
                "favourites": row.favourites, "orders": row.orders, "source": row.source,
                "carts": (row.detail or {}).get("carts")}
            want = {"impressions": r["impressions"], "visits": r["visits"],
                    "favourites": r["favourites"], "orders": r["orders"], "source": source,
                    "carts": r["carts"]}
            if got != want:
                mismatches.append({"slug": r["slug"], "wrote": want, "read": got})
    return {"status": "recorded" if recorded and not refused else
                      ("partial" if recorded else "refused"),
            "recorded": [r["slug"] for r in recorded], "refused": refused,
            "paid": sorted(r["slug"] for r in recorded if r["traffic_source"] in PAID_SOURCES),
            "organic": sorted(r["slug"] for r in recorded
                              if r["traffic_source"] not in PAID_SOURCES),
            "round_trip": {"checked": len(recorded), "mismatches": mismatches,
                           "ok": bool(recorded) and not mismatches},
            "source": source}


def drain_exports(db, *, now: datetime | None = None) -> list[dict]:
    """Record every pending export. Each is marked with what happened, never re-recorded."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        pending = [(r.period_key, dict(r.payload or {})) for r in s.scalars(
            select(OperatingReading).where(OperatingReading.kind == EXPORT_KIND)
            .order_by(OperatingReading.id))
            if (r.payload or {}).get("status") == "pending"]
    results = []
    for key, payload in pending:
        out = _record_export(db, key, payload)
        with db.session() as s:
            row = s.scalar(select(OperatingReading).where(
                OperatingReading.kind == EXPORT_KIND, OperatingReading.period_key == key))
            row.payload = json.loads(json.dumps(
                {**payload, **out, "processed_at": now.isoformat()}, default=str))
        results.append({"export": key, **{k: out.get(k) for k in
                                          ("status", "recorded", "refused", "round_trip")}})
    return results


# ---------------------------------------------------------------------------
# The Etsy API, read-only


def _count_or_none(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None


def api_snapshot(db, client, *, now: datetime | None = None) -> dict:
    """Today's cumulative views/favourites per active listing, and the period since the last.

    Read-only (`getListingsByShop`, state=active). No client or no credential is UNKNOWN and
    stores nothing. Deltas are computed only against an earlier day's snapshot and only for
    a listing present in both; a cumulative count that went *down* is not a negative period
    (Etsy recounts), so that listing's period is UNKNOWN rather than a clipped zero.
    """
    from sqlalchemy import select

    from ..core.models import Listing, OperatingReading

    now = now or datetime.now(timezone.utc)
    if client is None or getattr(client, "credentials", None) is None:
        return {"status": UNKNOWN, "why": "no Etsy credential; nothing was read, so views, "
                                          "visits and favourites are UNKNOWN, never zero"}
    try:
        observed = client.get_shop_listings(state="active")
    except Exception as e:  # noqa: BLE001 - an unread shop is UNKNOWN, never clean
        return {"status": UNKNOWN, "why": f"the read failed: {type(e).__name__}: {str(e)[:200]}"}
    snap = {}
    for r in observed:
        lid = str(r.get("listing_id") or "")
        if lid:
            snap[lid] = {"views": _count_or_none(r.get("views")),
                         "favourites": _count_or_none(r.get("num_favorers"))}
    today = now.date().isoformat()
    with db.session() as s:
        prev = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == SNAPSHOT_KIND, OperatingReading.period_key < today)
            .order_by(OperatingReading.period_key.desc()).limit(1))
        prev_day, prev_snap = (prev.period_key, dict((prev.payload or {}).get("listings") or {})) \
            if prev is not None else (None, {})
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == SNAPSHOT_KIND, OperatingReading.period_key == today))
        payload = {"observed_at": now.isoformat(), "listings": snap,
                   "operation": "getListingsByShop(state=active)"}
        if row is None:
            s.add(OperatingReading(kind=SNAPSHOT_KIND, period_key=today, payload=payload, at=now))
        else:
            row.payload, row.at = payload, now
        ours = {str(r.etsy_listing_id): r.product_slug
                for r in s.scalars(select(Listing).where(Listing.etsy_listing_id != ""))}
    periods = {}
    for lid, cur in snap.items():
        before = prev_snap.get(lid)
        entry = {"listing_id": lid, "slug": ours.get(lid), "period_start": prev_day,
                 "period_end": today, "impressions": UNKNOWN, "carts": UNKNOWN,
                 "impressions_why": "the Etsy API exposes no impressions",
                 "carts_why": "the Etsy API exposes no cart adds"}
        for field, name in (("views", "visits"), ("favourites", "favourites")):
            a, b = (before or {}).get(field), cur.get(field)
            if before is None or a is None or b is None:
                entry[name] = UNKNOWN
                entry[f"{name}_why"] = ("no earlier snapshot to difference against"
                                        if before is None else "not returned by Etsy")
            elif b < a:
                entry[name] = UNKNOWN
                entry[f"{name}_why"] = f"the cumulative count fell from {a} to {b}"
            else:
                entry[name] = b - a
        periods[lid] = entry
    return {"status": "OK", "observed": len(snap), "previous_snapshot": prev_day,
            "periods": periods,
            "basis": "measured (cumulative counts differenced); impressions and carts UNKNOWN"}


# ---------------------------------------------------------------------------
# Measurement proven (F-297)


def measurement_status(db) -> dict:
    """Whether organic and paid listing evidence has been recorded *and read back* here.

    Proven means: a `ListingOutcome` row written by this intake (its source carries an intake
    prefix) and an export reading whose round trip checked out. A row inserted by anything
    else -- a fixture, a migration, a hand -- proves nothing about whether measurement works.
    """
    from sqlalchemy import select

    from ..core.models import ListingOutcome, OperatingReading

    with db.session() as s:
        exports = [dict(r.payload or {}) for r in s.scalars(
            select(OperatingReading).where(OperatingReading.kind == EXPORT_KIND))]
        rows = [(r.source or "", dict(r.detail or {})) for r in s.scalars(select(ListingOutcome))]
    proven_sources = {e.get("source") for e in exports
                      if (e.get("round_trip") or {}).get("ok")}
    intake = [(src, d) for src, d in rows
              if src.startswith(INTAKE_PREFIXES) and src in proven_sources]
    organic = [1 for _, d in intake if not d.get("paid")]
    paid = [1 for _, d in intake if d.get("paid")]
    return {
        "organic": bool(organic), "paid": bool(paid),
        "organic_rows": len(organic), "paid_rows": len(paid),
        "exports": len(exports), "basis": "measured" if intake else "unknown",
        "why": ("organic listing evidence recorded and read back" if organic else
                "no listing-level outcome has been recorded by the intake and read back, so "
                "no optimiser may act on listing performance yet (#297)"),
        "paid_why": ("paid listing evidence recorded and read back" if paid else
                     "no paid (Etsy Ads / Offsite Ads) listing period has been recorded and "
                     "read back; paid optimisation stays off (#297)"),
    }


# ---------------------------------------------------------------------------
# The producer


def funnel(db, *, api: dict | None = None) -> list[dict]:
    """Per listing: the recorded funnel, the API period and the stage it is failing at.

    The stage is `growth.portfolio.classify` on the recorded totals -- the same diagnosis the
    weekly review runs -- so this reading and the review never disagree. A listing with no
    recorded period is UNMEASURED (the neutral new-listing prior, F-259), not failed.
    """
    from sqlalchemy import select

    from ..core.models import Listing, ListingOutcome
    from ..growth.portfolio import NO_EVIDENCE, SEO_PROBLEM, SkuMetrics, classify

    with db.session() as s:
        listings = {r.product_slug: r for r in s.scalars(select(Listing).where(
            Listing.version != "collection").order_by(Listing.id))}
        outcomes: dict[str, list] = {}
        for r in s.scalars(select(ListingOutcome)):
            outcomes.setdefault(r.product_slug, []).append(
                {"impressions": r.impressions, "visits": r.visits, "favourites": r.favourites,
                 "orders": r.orders, "carts": (r.detail or {}).get("carts"),
                 "period_start": r.period_start, "period_end": r.period_end,
                 "source": r.source})
    api_by_slug = {p["slug"]: p for p in ((api or {}).get("periods") or {}).values()
                   if p.get("slug")}
    out = []
    for slug in sorted(set(listings) | set(outcomes)):
        rows = outcomes.get(slug) or []

        def total(key):
            vals = [r[key] for r in rows]
            return sum(vals) if all(v is not None for v in vals) else UNKNOWN

        entry: dict[str, Any] = {"slug": slug, "periods": len(rows),
                                 "state": listings[slug].state if slug in listings else None,
                                 "api_period": api_by_slug.get(slug)}
        if not rows:
            entry.update({k: UNKNOWN for k in ("impressions", "visits", "favourites",
                                                "carts", "orders")})
            entry["stage"] = "UNMEASURED"
            entry["why"] = ("no recorded period: a listing begins UNMEASURED, neither a "
                            "success nor a failure (F-259)")
        else:
            entry.update({k: total(k) for k in ("impressions", "visits", "favourites",
                                                 "carts", "orders")})
            if entry["orders"] == UNKNOWN:
                entry["orders"] = _orders_in_periods(db, slug, rows)
            entry["sources"] = sorted({r["source"] for r in rows})
            c = classify(SkuMetrics(
                slug=slug, impressions=int(entry["impressions"]), clicks=int(entry["visits"]),
                favourites=int(entry["favourites"]) if entry["favourites"] != UNKNOWN else 0,
                orders=int(entry["orders"]) if entry["orders"] != UNKNOWN else 0))
            entry["stage"] = c.label
            entry["why"] = c.reason
            if entry["orders"] == UNKNOWN and c.label not in (NO_EVIDENCE, SEO_PROBLEM):
                # Visibility and click stages are read; the conversion stage needs an order
                # count, and an unknown one is not zero.
                entry["stage"] = "CONVERSION_UNMEASURED"
                entry["why"] = ("exposure and clicks are recorded; orders are UNKNOWN, so the "
                                "conversion stage is not diagnosed")
            entry["interventions"] = list(c.interventions)
        out.append(entry)
    return out


def _orders_in_periods(db, slug: str, rows: list[dict]):
    """Countable orders inside the recorded periods, or UNKNOWN when no order source is live."""
    from sqlalchemy import select

    from ..commerce import orders_ingest
    from ..core.models import Order
    from ..scale.runrate import orders_source_live

    if not orders_source_live(db)["live"]:
        return UNKNOWN
    spans = [(r["period_start"], r["period_end"]) for r in rows]
    with db.session() as s:
        got = orders_ingest.countable_orders(s, select(Order).where(Order.product_slug == slug))
        n = 0
        for o in got:
            at = o.at if o.at is None or o.at.tzinfo else o.at.replace(tzinfo=timezone.utc)
            if at is not None and any(a <= at.date().isoformat() <= b for a, b in spans):
                n += 1
    return n


def produce(db, *, client=None, now: datetime | None = None) -> dict:
    """The scheduled producer: record queued exports, read the API, store the funnel."""
    from ..runtime.growth_ops import record

    now = now or datetime.now(timezone.utc)
    drained = drain_exports(db, now=now)
    api = api_snapshot(db, client, now=now)
    rows = funnel(db, api=api)
    status = measurement_status(db)
    reading = {"as_of": now.isoformat(), "exports": drained, "api": api,
               "listings": rows, "measurement": status,
               "recorded_listings": sorted({s for d in drained for s in (d.get("recorded") or [])}),
               "basis": "measured" if status["basis"] == "measured" else "unknown",
               "note": ("" if any(r["periods"] for r in rows) else
                        "no listing has a recorded period: every listing is UNMEASURED, and "
                        "that is the reading, not a zero")}
    record(db, READING_KIND, now.date().isoformat(), reading)
    return reading


def latest(db) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(OperatingReading.kind == READING_KIND)
                       .order_by(desc(OperatingReading.at), desc(OperatingReading.id)).limit(1))
        return dict(row.payload or {}) if row is not None else None
