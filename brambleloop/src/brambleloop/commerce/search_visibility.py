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
        clean.append({"scope": scope, "listing_id": listing_id, "category": category,
                      "remediation": str(raw.get("remediation") or "").strip()})
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
                cleared.append(row.key)
        rid = reading.id
    return {"reading_id": rid, "observed_at": observed_at.isoformat(), "complete": complete,
            "opened": opened, "reopened": reopened, "still_listed": seen, "cleared": cleared}


def mark_remediated(db, item_id: int, *, ref: str) -> dict:
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
        transition(row, REMEDIATED_PENDING, via="remediation", ref=ref)
        row.remediated_ref = ref
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
                 "history": list(r.history or [])} for r in s.scalars(q)]


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
