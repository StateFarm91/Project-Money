"""Launch-week Search Visibility watch (F-280), on the F-248 intake.

For the seven days after the phase first leaves shadow, a daily owner card asks for the
Search Visibility page to be read and recorded. In shadow it does nothing at all: there is no
live shop and so no page to read, and a card asking for one would be noise in the owner
queue. The moment of leaving shadow is the first time this job *observes* a non-shadow phase,
recorded write-once, because the phase flag has no history of its own.

One open card at a time (de-duplicated on its requirement key), and none on a day a reading
has already been recorded. Reading the page is the owner's because Etsy offers it through no
endpoint this application may call; nothing here scrapes it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..core.models import Phase
from .worker import JobContext, handlers

ACTION = "listing.search_visibility_watch"
WINDOW_DAYS = 7
CARD_KEY = "search_visibility:launch_week"
LEFT_SHADOW_KIND = "storefront.left_shadow"


def _aware(v: datetime) -> datetime:
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def left_shadow_at(db, *, phase, now: datetime) -> datetime | None:
    """When this job first saw the phase out of shadow; recorded once, never moved."""
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == LEFT_SHADOW_KIND, OperatingReading.period_key == "first"))
        if row is not None:
            return datetime.fromisoformat(row.payload["observed_at"])
        if Phase(phase) == Phase.SHADOW:
            return None
        s.add(OperatingReading(kind=LEFT_SHADOW_KIND, period_key="first", at=now,
                               payload={"observed_at": now.isoformat(),
                                        "phase": Phase(phase).value,
                                        "basis": "first observation by the watch job"}))
    return now


def watch(db, *, phase, now: datetime | None = None) -> dict:
    from sqlalchemy import select

    from ..commerce import search_visibility as sv
    from ..core.models import OwnerAction

    now = _aware(now or datetime.now(timezone.utc))
    if Phase(phase) == Phase.SHADOW:
        return {"active": False, "phase": Phase(phase).value,
                "why": "inactive in shadow: no live shop, no Search Visibility page to read"}
    started = _aware(left_shadow_at(db, phase=phase, now=now))
    day = (now - started).days
    if day >= WINDOW_DAYS:
        return {"active": False, "phase": Phase(phase).value, "left_shadow_at":
                started.isoformat(), "why": f"launch week ended on day {WINDOW_DAYS}"}
    latest = sv.latest_reading_at(db)
    read_today = latest is not None and latest.date() == now.date()
    card = None
    with db.session() as s:
        open_card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == CARD_KEY, OwnerAction.done == False))  # noqa: E712
        if read_today:
            if open_card is not None:
                open_card.done = True    # today's reading is on file; the ask is answered
        elif open_card is None:
            s.add(OwnerAction(
                requirement_key=CARD_KEY,
                action=(f"Launch week day {day + 1} of {WINDOW_DAYS} ({now.date().isoformat()}): "
                        f"open Shop Manager > Marketing > Search Visibility and record what "
                        f"it lists with POST /api/search-visibility (operator credential), "
                        f"complete=true if you read the whole page"),
                reason=("F-248/F-280: Etsy shows these recommendations only in Shop Manager; "
                        "no authorised endpoint returns them, and an item is cleared only "
                        "by a later recorded reading"),
                max_cost_cad=0.0, minutes=5,
                consequence_of_delay=("a listing Etsy has flagged during launch week stays "
                                      "flagged unseen through the days a new listing most "
                                      "needs search"),
                blocks="F-280 launch-week Search Visibility watch"))
            card = CARD_KEY
    return {"active": True, "phase": Phase(phase).value, "left_shadow_at": started.isoformat(),
            "day": day + 1, "of": WINDOW_DAYS, "read_today": read_today, "card_raised": card}


@handlers.register(ACTION)
def handle_search_visibility_watch(ctx: JobContext) -> dict:
    out = watch(ctx.db, phase=ctx.phase)
    ctx.audit(ACTION, detail=out)
    return out
