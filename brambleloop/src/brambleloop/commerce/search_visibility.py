"""Etsy Search Visibility readings, recorded by the owner, with a lifecycle code cannot fake.

F-248: capture the Search Visibility recommendations Etsy shows a seller (Shop Manager >
Marketing > Search Visibility) -- date, listing, shop/listing/service scope, category,
remediation and lifecycle -- where **code changes alone can never mark one resolved**.
F-280: during launch week, inspect them daily (`runtime.storefront_watch`).

The page has no API among the endpoints this application is authorised for, so the readings
are the owner's, entered through `POST /api/search-visibility` (operator credential). And
they exist only for a live shop: intake refuses while the `live_listings` gate is closed,
and a listing-scoped item must name an Etsy listing id this company actually has. A reading
for a shop that does not exist would be fiction with a timestamp.

The lifecycle, and the one rule that matters:

    OPEN --(a remediation is shipped: code/listing change)--> REMEDIATED_PENDING
    OPEN | REMEDIATED_PENDING --(a later, complete reading no longer lists it)--> CLEARED
    CLEARED --(a later reading lists it again)--> OPEN (reopened)

Only a recorded reading clears an item, and only a reading *later* than the last one that
listed it, and only a *complete* one (the owner read the whole page): a partial reading that
does not mention an item proves nothing about it. `mark_remediated` -- the path a code change
takes -- may set REMEDIATED_PENDING and nothing else; `transition` refuses CLEARED to every
caller but `record_reading`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.models import Base, utcnow

OPEN = "OPEN"
REMEDIATED_PENDING = "REMEDIATED_PENDING"
CLEARED = "CLEARED"
STATES = (OPEN, REMEDIATED_PENDING, CLEARED)

SCOPES = ("shop", "listing", "service")
# F-560: Etsy's three Search Visibility areas, exactly. Each scope is one area.
AREA_BY_SCOPE = {"listing": "listings", "shop": "shop", "service": "customer_service"}
AREAS = ("listings", "shop", "customer_service")
# F-516: who owns the fix when the owner's reading does not say.
OWNER_BY_SCOPE = {"listing": "store_commerce", "shop": "store_commerce", "service": "support"}
# F-561: how long Etsy is allowed to take to refresh an item after a fix before it is an
# alert. An assumption, labelled: Etsy publishes no refresh interval for this page.
REFRESH_WINDOW_DAYS = 7
REFRESH_WINDOW_BASIS = "assumed; Etsy publishes no Search Visibility refresh interval"
STALE_READING_DAYS = 7
AGING_SIGNATURE = "search-visibility-not-cleared"
VIA_READING = "reading"
LIVE_GATE = "live_listings"


class SearchVisibilityRefused(ValueError):
    """A reading that cannot be true, or a transition only a reading may make."""


class SearchVisibilityReading(Base):
    """One owner reading of the Search Visibility page."""

    __tablename__ = "search_visibility_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(40), default="owner")
    items: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")


class SearchVisibilityItem(Base):
    """One recommendation, followed from the reading that first listed it to its clearing."""

    __tablename__ = "search_visibility_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200), index=True)
    scope: Mapped[str] = mapped_column(String(20))
    listing_id: Mapped[str] = mapped_column(String(32), default="")
    category: Mapped[str] = mapped_column(String(120))
    remediation: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(24), default=OPEN, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_reading_id: Mapped[int] = mapped_column(Integer)
    remediated_ref: Mapped[str] = mapped_column(Text, default="")
    cleared_by_reading_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reopened: Mapped[int] = mapped_column(Integer, default=0)
    history: Mapped[list] = mapped_column(JSON, default=list)
    # W4-C12 (F-516/F-517/F-561), additive columns: Etsy's own severity wording when the page
    # shows one (never an internal SEO score), the department that owns the fix, when the
    # remediation shipped, the re-check that cleared it and the time it took.
    severity: Mapped[str] = mapped_column(String(40), default="")
    owner: Mapped[str] = mapped_column(String(40), default="")
    remediated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                           nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                             nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation: Mapped[dict | None] = mapped_column(JSON, nullable=True)


def ensure_tables(db) -> None:
    for model in (SearchVisibilityReading, SearchVisibilityItem):
        model.__table__.create(db.engine, checkfirst=True)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _key(scope: str, listing_id: str, category: str) -> str:
    return f"{scope}:{listing_id or '-'}:{category.strip().lower()}"


def live_gate_open(db) -> bool:
    try:
        from ..build2.executor import GATE_BY_KEY

        return bool(GATE_BY_KEY[LIVE_GATE].open(db))
    except Exception:  # noqa: BLE001 - an unreadable gate is not an open one
        return False


def _known_listing_ids(db) -> set[str]:
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        return {i for i in s.scalars(select(Listing.etsy_listing_id)) if i}


def _validate(db, items: list[dict]) -> list[dict]:
    known = _known_listing_ids(db)
    clean = []
    for i, raw in enumerate(items):
        scope = str(raw.get("scope", "")).strip().lower()
        category = str(raw.get("category", "")).strip()
        listing_id = str(raw.get("listing_id") or "").strip()
        if scope not in SCOPES:
            raise SearchVisibilityRefused(f"item {i}: scope must be one of {SCOPES}")
        if not category:
            raise SearchVisibilityRefused(f"item {i}: a recommendation names its category")
        if scope == "listing":
            if not listing_id:
                raise SearchVisibilityRefused(f"item {i}: a listing item names its listing")
            if listing_id not in known:
                raise SearchVisibilityRefused(
                    f"item {i}: listing {listing_id!r} is not an Etsy listing this shop has")
        elif listing_id:
            raise SearchVisibilityRefused(f"item {i}: a {scope} item names no listing")
        if "score" in raw or "seo_score" in raw:
            raise SearchVisibilityRefused(
                f"item {i}: an internal score is not Etsy's finding; record what the page "
                f"says (F-516)")
        clean.append({"scope": scope, "listing_id": listing_id, "category": category,
                      "remediation": str(raw.get("remediation") or "").strip(),
                      "severity": str(raw.get("severity") or "").strip()[:40],
                      "owner": str(raw.get("owner") or OWNER_BY_SCOPE[scope]).strip()[:40]})
    return clean


def transition(item: SearchVisibilityItem, state: str, *, via: str, ref: str = "",
               at: datetime | None = None) -> None:
    """The only place an item's state changes. CLEARED is the reading's alone."""
    if state not in STATES:
        raise SearchVisibilityRefused(f"{state!r} is not a state: {STATES}")
    if state == CLEARED and via != VIA_READING:
        raise SearchVisibilityRefused(
            "only a later recorded Search Visibility reading may clear an item; a code or "
            "listing change can only mark it REMEDIATED_PENDING (F-248)")
    at = at or datetime.now(timezone.utc)
    item.history = list(item.history or []) + [
        {"at": at.isoformat(), "from": item.state, "to": state, "via": via, "ref": ref}]
    item.state = state


def record_reading(db, *, observed_at: datetime, items: list[dict], complete: bool,
                   source: str = "owner", note: str = "", require_live: bool = True) -> dict:
    """File one reading and apply it to the item lifecycle."""
    from sqlalchemy import select

    ensure_tables(db)
    if require_live and not live_gate_open(db):
        raise SearchVisibilityRefused(
            "the live_listings gate is closed: there is no live listing, so there is no "
            "Search Visibility page to have read")
    observed_at = _aware(observed_at)
    now = datetime.now(timezone.utc)
    if observed_at > now:
        raise SearchVisibilityRefused("a reading cannot be observed in the future")
    clean = _validate(db, items)
    opened, reopened, seen, cleared = [], [], [], []
    with db.session() as s:
        reading = SearchVisibilityReading(observed_at=observed_at, complete=bool(complete),
                                          source=source, items=clean, note=note[:2000])
        s.add(reading)
        s.flush()
        listed = set()
        for it in clean:
            key = _key(it["scope"], it["listing_id"], it["category"])
            listed.add(key)
            row = s.scalar(select(SearchVisibilityItem).where(SearchVisibilityItem.key == key)
                           .order_by(SearchVisibilityItem.id.desc()).limit(1))
            if row is None:
                row = SearchVisibilityItem(key=key, scope=it["scope"],
                                           listing_id=it["listing_id"],
                                           category=it["category"],
                                           remediation=it["remediation"], state=OPEN,
                                           severity=it["severity"], owner=it["owner"],
                                           last_checked_at=observed_at,
                                           first_seen_at=observed_at, last_seen_at=observed_at,
                                           last_seen_reading_id=reading.id,
                                           history=[{"at": observed_at.isoformat(),
                                                     "to": OPEN, "via": VIA_READING,
                                                     "ref": f"reading:{reading.id}"}])
                s.add(row)
                opened.append(key)
                continue
            if row.state == CLEARED:
                by = s.get(SearchVisibilityReading, row.cleared_by_reading_id or 0)
                if by is not None and observed_at <= _aware(by.observed_at):
                    seen.append(key)    # an older reading, entered late: history only
                    continue
            if observed_at >= _aware(row.last_seen_at):
                row.last_seen_at, row.last_seen_reading_id = observed_at, reading.id
            if it["remediation"]:
                row.remediation = it["remediation"]
            if it["severity"] and it["severity"] != (row.severity or ""):
                # Etsy changed its own reading of the item: history, not a resolution.
                row.history = list(row.history or []) + [
                    {"at": observed_at.isoformat(), "changed": "severity",
                     "from": row.severity, "to": it["severity"], "via": VIA_READING,
                     "ref": f"reading:{reading.id}"}]
                row.severity = it["severity"]
            if row.last_checked_at is None or observed_at > _aware(row.last_checked_at):
                row.last_checked_at = observed_at
            if row.state == CLEARED:
                transition(row, OPEN, via=VIA_READING, ref=f"reading:{reading.id}",
                           at=observed_at)
                row.reopened = (row.reopened or 0) + 1
                row.cleared_by_reading_id = None
                reopened.append(key)
            else:
                seen.append(key)
        if complete:
            for row in s.scalars(select(SearchVisibilityItem).where(
                    SearchVisibilityItem.state != CLEARED)):
                if row.key in listed:
                    continue
                if observed_at <= _aware(row.last_seen_at):
                    continue    # not later than the reading that listed it
                transition(row, CLEARED, via=VIA_READING, ref=f"reading:{reading.id}",
                           at=observed_at)
                row.cleared_by_reading_id = reading.id
                # F-517: the closure proof -- the re-check that no longer lists it, and how
                # long the item took to clear from first sight and from the shipped fix.
                row.cleared_at, row.last_checked_at = observed_at, observed_at
                first = _aware(row.first_seen_at)
                fixed = _aware(row.remediated_at) if row.remediated_at else None
                row.confirmation = {
                    "reading_id": reading.id, "observed_at": observed_at.isoformat(),
                    "complete": True, "source": source,
                    "hours_from_first_seen": round((observed_at - first).total_seconds()
                                                   / 3600, 2),
                    "hours_from_remediation": (round((observed_at - fixed).total_seconds()
                                                     / 3600, 2) if fixed else None),
                    "remediated_ref": row.remediated_ref or None}
                cleared.append(row.key)
        rid = reading.id
    return {"reading_id": rid, "observed_at": observed_at.isoformat(), "complete": complete,
            "opened": opened, "reopened": reopened, "still_listed": seen, "cleared": cleared}


def mark_remediated(db, item_id: int, *, ref: str, at: datetime | None = None) -> dict:
    """A remediation shipped (a code or listing change). Never clears; a reading must."""
    ensure_tables(db)
    if not ref.strip():
        raise SearchVisibilityRefused("name the change that remediates the item")
    with db.session() as s:
        row = s.get(SearchVisibilityItem, item_id)
        if row is None:
            raise SearchVisibilityRefused(f"no Search Visibility item {item_id}")
        if row.state == CLEARED:
            raise SearchVisibilityRefused("the item is already cleared by a reading")
        at = _aware(at) if at else datetime.now(timezone.utc)
        transition(row, REMEDIATED_PENDING, via="remediation", ref=ref, at=at)
        row.remediated_ref = ref
        row.remediated_at = at
        return {"id": row.id, "key": row.key, "state": row.state}


def items(db, *, state: str | None = None) -> list[dict]:
    from sqlalchemy import select

    ensure_tables(db)
    with db.session() as s:
        q = select(SearchVisibilityItem).order_by(SearchVisibilityItem.id)
        if state:
            q = q.where(SearchVisibilityItem.state == state)
        return [{"id": r.id, "key": r.key, "scope": r.scope, "listing_id": r.listing_id,
                 "category": r.category, "remediation": r.remediation, "state": r.state,
                 "first_seen_at": _aware(r.first_seen_at).isoformat(),
                 "last_seen_at": _aware(r.last_seen_at).isoformat(),
                 "cleared_by_reading_id": r.cleared_by_reading_id, "reopened": r.reopened,
                 "area": AREA_BY_SCOPE.get(r.scope), "severity": r.severity or None,
                 "owner": r.owner or OWNER_BY_SCOPE.get(r.scope),
                 "remediated_at": _iso(r.remediated_at),
                 "last_checked_at": _iso(r.last_checked_at),
                 "cleared_at": _iso(r.cleared_at), "confirmation": r.confirmation,
                 "history": list(r.history or [])} for r in s.scalars(q)]


def _iso(v: datetime | None) -> str | None:
    return _aware(v).isoformat() if v else None


def latest_reading_at(db) -> datetime | None:
    from sqlalchemy import func, select

    ensure_tables(db)
    with db.session() as s:
        at = s.scalar(select(func.max(SearchVisibilityReading.observed_at)))
    return _aware(at) if at else None


def state(db) -> dict:
    rows = items(db)
    latest = latest_reading_at(db)
    return {"live_gate": LIVE_GATE, "live_gate_open": live_gate_open(db),
            "readings_on_file": latest is not None,
            "latest_reading_at": latest.isoformat() if latest else None,
            "open": [r for r in rows if r["state"] == OPEN],
            "remediated_pending": [r for r in rows if r["state"] == REMEDIATED_PENDING],
            "cleared": len([r for r in rows if r["state"] == CLEARED]),
            "status": ("UNMEASURED" if latest is None else "READ"),
            "rule": ("only a later, complete recorded reading clears an item; a code change "
                     "can only mark it REMEDIATED_PENDING")}


# ---- F-560: the three areas, each independently green / amber / red ------------------------

def _latest_complete_at(db) -> datetime | None:
    from sqlalchemy import func, select

    with db.session() as s:
        at = s.scalar(select(func.max(SearchVisibilityReading.observed_at)).where(
            SearchVisibilityReading.complete.is_(True)))
    return _aware(at) if at else None


def areas(db, *, now: datetime | None = None) -> dict:
    """Listings, Shop and Customer Service, each from Etsy's own findings (F-560).

    red: an item Etsy lists is OPEN. amber: every listed item has a shipped fix waiting for
    Etsy to re-check (REMEDIATED_PENDING), or the newest complete reading is older than
    STALE_READING_DAYS. green: a complete reading no older than that lists nothing in the
    area. UNMEASURED: no complete reading exists -- never green by default.
    """
    ensure_tables(db)
    now = now or datetime.now(timezone.utc)
    rows = items(db)
    complete_at = _latest_complete_at(db)
    out = {}
    for area in AREAS:
        mine = [r for r in rows if r["area"] == area and r["state"] != CLEARED]
        if complete_at is None and not mine:
            status, why = "UNMEASURED", "no complete Search Visibility reading is on file"
        elif any(r["state"] == OPEN for r in mine):
            status, why = "red", f"{sum(r['state'] == OPEN for r in mine)} open finding(s)"
        elif mine:
            status, why = "amber", f"{len(mine)} fix(es) waiting for Etsy's re-check"
        elif (now - complete_at).days > STALE_READING_DAYS:
            status, why = "amber", (f"the newest complete reading is "
                                    f"{(now - complete_at).days} days old")
        else:
            status, why = "green", "the newest complete reading lists nothing here"
        out[area] = {"status": status, "why": why,
                     "findings": [{k: r[k] for k in ("id", "category", "state", "severity",
                                                     "owner", "first_seen_at",
                                                     "last_checked_at")} for r in mine],
                     "as_of": complete_at.isoformat() if complete_at else None}
    return {"areas": out, "basis": "owner-recorded first-party readings of Etsy's page"}


# ---- F-561: aging, re-check and the refresh-window alert -----------------------------------

def aging(db, *, now: datetime | None = None, raise_incidents: bool = True) -> dict:
    """How long each finding has been open; a fix Etsy has not cleared in its window alerts."""
    from sqlalchemy import select

    from ..core.models import Incident

    ensure_tables(db)
    now = now or datetime.now(timezone.utc)
    report, overdue = [], []
    for r in items(db):
        if r["state"] == CLEARED:
            continue
        first = datetime.fromisoformat(r["first_seen_at"])
        entry = {"id": r["id"], "key": r["key"], "state": r["state"],
                 "open_days": round((now - first).total_seconds() / 86400, 2)}
        if r["state"] == REMEDIATED_PENDING and r["remediated_at"]:
            fixed = datetime.fromisoformat(r["remediated_at"])
            checked = datetime.fromisoformat(r["last_checked_at"]) if r["last_checked_at"] \
                else None
            entry["days_since_fix"] = round((now - fixed).total_seconds() / 86400, 2)
            entry["rechecked_since_fix"] = bool(checked and checked > fixed)
            if not entry["rechecked_since_fix"]:
                entry["needs"] = "a complete re-read of the Search Visibility page"
            elif entry["days_since_fix"] > REFRESH_WINDOW_DAYS:
                entry["needs"] = (f"Etsy still lists it {entry['days_since_fix']} days after "
                                  f"the fix (window {REFRESH_WINDOW_DAYS} days, "
                                  f"{REFRESH_WINDOW_BASIS})")
                overdue.append(entry)
        report.append(entry)
    opened = []
    if raise_incidents:
        with db.session() as s:
            for e in overdue:
                sig = f"{AGING_SIGNATURE}:{e['key']}"[:120]
                if s.scalar(select(Incident).where(Incident.signature == sig,
                                                   Incident.resolved.is_(False))) is None:
                    s.add(Incident(severity="P2", signature=sig, halts_publication=False,
                                   summary=(f"Etsy Search Visibility still lists {e['key']} "
                                            f"{e['days_since_fix']} days after its fix; the "
                                            f"fix may not address what Etsy reads"),
                                   detail={"owner": "store_commerce", "item": e["id"]}))
                    opened.append(sig)
            still = {f"{AGING_SIGNATURE}:{e['key']}"[:120] for e in overdue}
            for inc in s.scalars(select(Incident).where(
                    Incident.signature.like(f"{AGING_SIGNATURE}:%"),
                    Incident.resolved.is_(False))):
                if inc.signature not in still:
                    inc.resolved = True     # cleared by a reading, or no longer overdue
    return {"items": report, "overdue": overdue, "incidents_opened": opened,
            "refresh_window_days": REFRESH_WINDOW_DAYS, "basis": REFRESH_WINDOW_BASIS}
