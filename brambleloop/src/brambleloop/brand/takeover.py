"""Seasonal storefront transitions, scheduled from the calendar and reverted by it too.

Requirement 131. Five surfaces -- banner, featured collections, thumbnails, bundles and shop
content -- should turn over ahead of each seasonal buying window, and the requirement is
explicit that they are scheduled from the Collection Calendar rather than whenever somebody
notices the date.

Three things make this more than a to-do list.

**Surfaces do not transition together.** A banner changes early because it is what a returning
visitor sees first and it costs nothing to be early. Thumbnails change late, because a
thumbnail that says December in October is a thumbnail competing against products the buyer
can still finish. Scheduling them on one date is how a shop ends up either premature or late
on everything at once.

**A takeover declares its end at the moment it is planned.** The failure is not the Christmas
banner going up late; it is the Christmas banner still being up in February, which says
nobody is home more loudly than an empty shop does. The end date comes from the same calendar
as the start, so it exists before anybody is busy.

**Brand continuity is what makes the shop feel alive rather than unstable.** A storefront that
changes its wordmark, its palette anchor, its photographic language and its voice every
quarter is not seasonal, it is unrecognisable -- and the timeliness it buys is worth less than
the recognition it spends. So a takeover may change what is shown and not what the shop is,
and the invariants are listed rather than trusted to taste.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..seasonal.calendar import MILESTONES

# What a takeover is allowed to change, and how far ahead of the event each surface turns.
# The lead days are read off the collection calendar's own milestones rather than chosen:
# a banner rides the promotional ramp, thumbnails ride the peak window.
_MILESTONE_DAYS = {name: days for name, days, _ in MILESTONES}


@dataclass(frozen=True)
class Surface:
    key: str
    what: str
    lead_days: int
    why: str


SURFACES: tuple[Surface, ...] = (
    Surface("banner", "shop banner and announcement",
            _MILESTONE_DAYS["promotional_ramp"],
            "what a returning visitor sees first, and the one surface where being early "
            "costs nothing"),
    Surface("featured_collection", "the collection pinned to the front of the shop",
            _MILESTONE_DAYS["listing_indexing_date"],
            "the collection is live and indexed at this point, and featuring it is what "
            "gives it its first traffic -- earlier would feature a page that does not "
            "exist, later wastes the weeks when search is still learning what it is"),
    Surface("bundles", "seasonal bundles and their pricing",
            _MILESTONE_DAYS["promotional_ramp"],
            "a bundle is a decision about what a buyer purchases together, and it needs to "
            "be live before the weeks when they actually buy"),
    Surface("shop_content", "About line, section names, seasonal copy",
            _MILESTONE_DAYS["peak_window_opens"],
            "copy is cheap to change and is read by the cautious buyer, who is the one "
            "deciding whether this shop is still trading"),
    Surface("thumbnails", "seasonal thumbnail treatment across the catalogue",
            _MILESTONE_DAYS["peak_window_opens"],
            "a thumbnail that says December in October competes against products the buyer "
            "can still finish, which is the opposite of what it is for"),
)

SURFACE_BY_KEY: dict[str, Surface] = {s.key: s for s in SURFACES}

# When a takeover ends. Read from the calendar's own tail milestone so the end is as scheduled
# as the start: the Christmas banner still up in February says nobody is home.
ENDS_DAYS_AFTER_EVENT = -_MILESTONE_DAYS["clearance_or_evergreen"]

# What a takeover may never change. A shop that reinvents itself every quarter is not
# seasonal, it is unrecognisable, and the timeliness is worth less than the recognition.
CONTINUITY_INVARIANTS: dict[str, str] = {
    "wordmark": "the shop's name and its setting; a reset wordmark resets the shop",
    "icon_mark": "the loop-and-bramble mark, which is what a returning buyer recognises "
                 "at 40 pixels in a list of favourites",
    "palette_anchor": "the cream ground and pine anchor; seasonal colour is an accent on "
                      "them rather than a replacement for them",
    "photographic_language": "flat daylight, real fabric, no collage and no stock gloss",
    "voice": "plain, specific and unexcited, which is the thing the About page earns trust "
             "with",
    "policy_text": "delivery, returns, licence, support and privacy, which are promises "
                   "rather than decoration",
    "canonical_logo": "the owner's hero artwork (D-FB-17), used exactly as supplied; replacing "
                      "it needs a new owner decision, never a seasonal plan",
    "canonical_banner": "the owner's banner composition (D-FB-17); a seasonal look may not "
                        "replace it without an owner decision naming the new file",
}


class TakeoverRefused(ValueError):
    """A takeover with no event, no end, or one that changes what the shop is."""


@dataclass
class Takeover:
    event: str
    event_date: date
    surfaces: tuple[str, ...]
    changes: dict[str, str]          # surface -> what it becomes
    changes_invariants: tuple[str, ...] = ()
    # D-FB-17: canonical brand role ("hero_logo" | "storefront_banner") -> sha256 of the file a
    # takeover would put in its place. Refused unless an owner decision names those bytes.
    replaces_assets: dict[str, str] = field(default_factory=dict)
    approval: dict | None = None


def schedule(event: str, event_date: date, *, today: date | None = None,
             surfaces: tuple[str, ...] | None = None) -> dict:
    """When each surface turns over for this event, and what is already late.

    Dates come from the collection calendar rather than from a judgement about how much
    warning feels right, which is the difference between a shop that transitions and a shop
    that reacts.
    """
    today = today or date.today()
    keys = surfaces or tuple(s.key for s in SURFACES)
    unknown = [k for k in keys if k not in SURFACE_BY_KEY]
    if unknown:
        raise TakeoverRefused(f"unknown storefront surface(s): {unknown}")

    ends_on = event_date + timedelta(days=ENDS_DAYS_AFTER_EVENT)
    rows = []
    for key in keys:
        surface = SURFACE_BY_KEY[key]
        starts_on = event_date - timedelta(days=surface.lead_days)
        rows.append({
            "surface": key, "what": surface.what, "why": surface.why,
            "lead_days": surface.lead_days,
            "transitions_on": starts_on.isoformat(),
            "reverts_on": ends_on.isoformat(),
            "days_until": (starts_on - today).days,
            "overdue": starts_on < today,
            "reverting_overdue": ends_on < today,
        })
    rows.sort(key=lambda r: r["transitions_on"])

    overdue = [r["surface"] for r in rows if r["overdue"] and not r["reverting_overdue"]]
    stale = [r["surface"] for r in rows if r["reverting_overdue"]]
    return {
        "event": event,
        "event_date": event_date.isoformat(),
        "today": today.isoformat(),
        "ends_on": ends_on.isoformat(),
        "surfaces": rows,
        "overdue": overdue,
        "past_its_revert_date": stale,
        "note": (
            f"this takeover is past its revert date on {len(stale)} surface(s): a seasonal "
            f"storefront left up after the occasion says nobody is home more loudly than an "
            f"empty shop does" if stale else
            f"{len(overdue)} surface(s) are past their transition date" if overdue else
            "every surface has a scheduled date and none has passed"),
    }


def check(takeover: Takeover) -> list[str]:
    """Everything that would make a takeover cost more recognition than it buys."""
    problems: list[str] = []

    if not takeover.event.strip():
        problems.append(
            "TAKEOVER_NOT_SCHEDULED: a takeover with no event is a storefront change "
            "somebody felt like making, and #131 schedules these from the calendar")

    for surface in takeover.surfaces:
        if surface not in SURFACE_BY_KEY:
            problems.append(f"TAKEOVER_UNKNOWN_SURFACE: {surface}")
        elif not takeover.changes.get(surface, "").strip():
            problems.append(
                f"TAKEOVER_SURFACE_EMPTY: {surface} is listed and says nothing, which is a "
                f"plan to change it later rather than a takeover")

    for invariant in takeover.changes_invariants:
        why = CONTINUITY_INVARIANTS.get(invariant)
        problems.append(
            f"TAKEOVER_BREAKS_CONTINUITY: {invariant} -- {why}"
            if why else
            f"TAKEOVER_BREAKS_CONTINUITY: {invariant}")

    from . import canonical_assets as CA

    for role, sha in (takeover.replaces_assets or {}).items():
        try:
            CA.require_brand_change_authorised(role, sha, takeover.approval,
                                               action=f"takeover {takeover.event!r}")
        except CA.BrandChangeRefused as exc:
            problems.append(f"TAKEOVER_REPLACES_CANONICAL_ASSET: {role} -- {exc}")

    return problems


def plan(event: str, event_date: date, changes: dict[str, str], *,
         today: date | None = None, changes_invariants: tuple[str, ...] = (),
         replaces_assets: dict[str, str] | None = None,
         approval: dict | None = None) -> dict:
    """A scheduled, checked takeover, refused rather than flagged if it breaks continuity."""
    takeover = Takeover(event=event, event_date=event_date,
                        surfaces=tuple(changes), changes=dict(changes),
                        changes_invariants=changes_invariants,
                        replaces_assets=dict(replaces_assets or {}), approval=approval)
    problems = check(takeover)
    if problems:
        raise TakeoverRefused("; ".join(problems))

    scheduled = schedule(event, event_date, today=today, surfaces=tuple(changes))
    scheduled["changes"] = dict(changes)
    scheduled["continuity_held"] = sorted(CONTINUITY_INVARIANTS)
    return scheduled


def calendar(events: dict[str, date], *, today: date | None = None) -> dict:
    """Every upcoming takeover in one list, soonest transition first."""
    today = today or date.today()
    plans = [schedule(name, when, today=today) for name, when in events.items()]
    plans.sort(key=lambda p: p["surfaces"][0]["transitions_on"] if p["surfaces"] else "")
    return {
        "today": today.isoformat(),
        "takeovers": plans,
        "overdue_surfaces": sum(len(p["overdue"]) for p in plans),
        "past_revert_date": sum(len(p["past_its_revert_date"]) for p in plans),
        "invariants": CONTINUITY_INVARIANTS,
        "note": ("Surfaces transition on different dates on purpose: a banner is early "
                 "because being early costs nothing, and thumbnails are late because one "
                 "saying December in October competes against what the buyer can still "
                 "finish (#131)."),
    }



# ---------------------------------------------------------------------------
# The executor (C-69, #131): scheduled takeovers applied on their date and reverted on theirs.
#
# The storefront this company holds is the drafted one (`brand.storefront`); the marketplace
# copy of it is written only when publishing is allowed. So a takeover is applied here to the
# stored storefront state -- one `operating_readings` row per event and surface, the state the
# storefront is rendered from -- on its transition date, checked against the storefront's own
# rules and the continuity invariants, and reverted on its revert date. A surface whose
# applied storefront fails its checks is reverted at once rather than left up.

STATE_KIND = "storefront.takeover"
APPLIED, REVERTED = "applied", "reverted"


def execute(db, plans: list[dict], *, today: date | None = None) -> dict:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    today = today or date.today()
    applied, reverted, refused = [], [], []
    with db.session() as s:
        rows = {r.period_key: r for r in s.scalars(select(OperatingReading).where(
            OperatingReading.kind == STATE_KIND))}
        for plan_ in plans:
            event, changes = plan_["event"], plan_.get("changes") or {}
            for surface in plan_["surfaces"]:
                import hashlib

                tag = hashlib.sha256(f"{event}|{plan_['event_date']}".encode()).hexdigest()[:8]
                key = f"{tag}:{surface['surface'][:11]}"
                starts = date.fromisoformat(surface["transitions_on"])
                ends = date.fromisoformat(surface["reverts_on"])
                row = rows.get(key)
                state = (row.payload or {}).get("state") if row is not None else None
                if starts <= today < ends and state != APPLIED:
                    change = changes.get(surface["surface"], "")
                    problems = _applied_problems(surface["surface"], change, db=db)
                    if problems:
                        refused.append({"event": event, "surface": surface["surface"],
                                        "problems": problems})
                        continue
                    payload = {"state": APPLIED, "event": event,
                               "surface": surface["surface"], "change": change,
                               "applied_on": today.isoformat(),
                               "reverts_on": ends.isoformat(),
                               "marketplace_write": "withheld: shadow mode drafts the "
                                                    "storefront and publishes nothing"}
                    if row is None:
                        s.add(OperatingReading(kind=STATE_KIND, period_key=key,
                                               payload=payload))
                    else:
                        row.payload = payload
                    applied.append(key)
        # Revert by date whatever today's plans contain: once an occasion has passed it is no
        # longer planned, and that is exactly when its banner must come down.
        for key, row in rows.items():
            p = dict(row.payload or {})
            if p.get("state") == APPLIED and today >= date.fromisoformat(p["reverts_on"]):
                row.payload = {**p, "state": REVERTED, "reverted_on": today.isoformat()}
                reverted.append(key)
    return {"applied": applied, "reverted": reverted, "refused": refused,
            "active": active(db, today=today)}


def _applied_problems(surface: str, change: str, db=None) -> list[str]:
    """The storefront's own checks, run on the storefront as the takeover would leave it.

    C-80 defect 18: every surface the storefront renders is checked as rendered -- the banner
    as the announcement, shop_content as seasonal copy on About, featured_collection as the
    pinned collection, which with a database must name a collection or a product that exists;
    a takeover that would pin nothing real is refused, not applied.
    """
    from . import storefront

    store = storefront.build_storefront()
    if surface == "banner":
        store.announcement = change
    elif surface == "shop_content":
        store.seasonal_copy = change
        store.about = f"{store.about}\n\n{change}"
    elif surface == "featured_collection":
        store.featured_collection = change
    problems = storefront.check_storefront(store)
    if not change.strip():
        problems.append(f"TAKEOVER_SURFACE_EMPTY: {surface}")
    if surface == "featured_collection" and db is not None and change.strip():
        from sqlalchemy import select

        from ..core.models import Collection, Product

        with db.session() as s:
            titles = {c.title for c in s.scalars(select(Collection))}
            slugs = {p.slug for p in s.scalars(select(Product))}
        named = {part.strip() for part in change.split(",") if part.strip()}
        if change.strip() not in titles and not (named & slugs):
            problems.append(f"TAKEOVER_FEATURED_COLLECTION_NAMES_NOTHING: {change[:80]!r} is "
                            f"neither a collection title nor a product this shop has")
    return problems


def active(db, *, today: date | None = None) -> dict[str, dict]:
    """The takeover changes live on the drafted storefront today, by surface."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    today = today or date.today()
    out: dict[str, dict] = {}
    with db.session() as s:
        for r in s.scalars(select(OperatingReading).where(
                OperatingReading.kind == STATE_KIND)):
            p = r.payload or {}
            if p.get("state") == APPLIED and date.fromisoformat(p["reverts_on"]) > today:
                out[p["surface"]] = {"event": p["event"], "change": p["change"],
                                     "reverts_on": p["reverts_on"]}
    return out
