"""Dedicated capacity per event, and the evidence an extra team has to bring.

Requirement 287. Major commercially relevant events get persistent strike teams; additional
events get one when demand evidence supports it. The second clause is the whole of the design,
because a team is cheap to create and expensive to staff, and the failure is not that somebody
creates a bad team -- it is that six teams exist, each holding a slice of the same finite
capacity, and every one of them is under-resourced by exactly as much as the others are
notional.

So three rules, all arithmetic.

**A team is capacity or it is a name.** Creating one allocates a share, and the shares are
checked against one. A team with no capacity exists on an org chart and nowhere a product
comes from.

**A standing team exists because the event is named, and any other needs rows.** Christmas,
Halloween and Easter are standing programmes. A fourth team needs recorded demand evidence --
observations, not enthusiasm -- and the count is a floor rather than a conversation.

**A team disbands when its occasion is over, not when somebody remembers.** The compression
programme already knows when an event has passed the buyer's last practical make date; a team
whose event is there releases its capacity automatically, which is how the next occasion gets
staffed without anybody rebalancing by hand.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .compression import (
    MIN_PRIORITY_SHARE, POST_OCCASION, PRIORITY_PROGRAMMES, programme,
)

# Events that always have a team, because the calendar says they are the commercial year.
STANDING_EVENTS: tuple[str, ...] = ("Christmas", "Halloween", "Easter")

# Recorded observations an event needs before it earns a team of its own. Small on purpose:
# the point is that the number is above zero and counted, not that the bar is high.
DEMAND_EVIDENCE_FLOOR = 3

# Capacity that never belongs to any event team. Evergreen work and the run of the company
# continue through every season, and a seasonal programme that consumes everything leaves a
# shop that is excellent in December and absent in February.
EVERGREEN_RESERVE = 0.25


class TeamRefused(ValueError):
    """A team with no capacity, no evidence, or one that would overrun the company."""


@dataclass(frozen=True)
class Team:
    event: str
    share: float
    standing: bool
    why: str


def demand_evidence(db, event: str) -> int:
    """How many recorded observations mention this event. Rows, not enthusiasm."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, LearningObservation

    needle = event.split(" ")[0].lower()
    count = 0
    with db.session() as s:
        for row in s.scalars(select(LearningObservation)):
            if needle in (row.summary or "").lower():
                count += 1
        for row in s.scalars(select(BenchmarkListing)):
            if needle in ((row.title or "") + " " + (row.seasonal or "")).lower():
                count += 1
    return count


def may_create(db, event: str) -> dict:
    """Whether this event has earned a team of its own."""
    if event in STANDING_EVENTS:
        return {"event": event, "allowed": True, "standing": True, "evidence": None,
                "why": "a standing programme: the calendar says this is the commercial year"}
    found = demand_evidence(db, event)
    return {
        "event": event, "allowed": found >= DEMAND_EVIDENCE_FLOOR, "standing": False,
        "evidence": found, "floor": DEMAND_EVIDENCE_FLOOR,
        "why": (f"{found} recorded observation(s) mention it, against a floor of "
                f"{DEMAND_EVIDENCE_FLOOR}. A team is cheap to create and expensive to staff, "
                f"so the fourth one brings rows rather than enthusiasm"),
    }


def allocate(db, *, today: date | None = None, extra_events: tuple[str, ...] = (),
             samples: int = 0) -> dict:
    """Which teams exist today and what share of capacity each holds.

    A team whose occasion has passed the buyer's last practical make date releases its
    capacity here rather than when somebody remembers, which is how the next occasion gets
    staffed without a manual rebalance.
    """
    today = today or date.today()
    wanted = list(STANDING_EVENTS) + [e for e in extra_events if e not in STANDING_EVENTS]

    teams: list[Team] = []
    disbanded: list[dict] = []
    refused: list[dict] = []

    for event in wanted:
        permission = may_create(db, event)
        if not permission["allowed"]:
            refused.append(permission)
            continue
        try:
            plan = programme(event, today=today, samples=samples)
        except Exception as exc:  # noqa: BLE001 - an event off the calendar is not a crash
            refused.append({"event": event, "allowed": False, "why": str(exc)[:200]})
            continue
        if plan["mode"]["mode"] == POST_OCCASION:
            disbanded.append({"event": event,
                              "why": ("past the buyer's last practical make date, so its "
                                      "capacity returns to the pool automatically")})
            continue
        share = plan["capacity"]["share"] or MIN_PRIORITY_SHARE
        teams.append(Team(event=event, share=share,
                          standing=permission["standing"],
                          why=plan["mode"]["what"]))

    total = round(sum(t.share for t in teams), 3)
    available = round(1.0 - EVERGREEN_RESERVE, 3)
    scaled = teams
    scaling = 1.0
    if total > available and total > 0:
        # Scaled rather than refused: the company does not stop having occasions because two
        # of them overlap, and a proportional cut keeps the priority order the programmes
        # already established.
        scaling = available / total
        scaled = [Team(event=t.event, share=round(t.share * scaling, 3),
                       standing=t.standing, why=t.why) for t in teams]

    return {
        "today": today.isoformat(),
        "teams": [{"event": t.event, "share": t.share, "standing": t.standing,
                   "doing": t.why} for t in scaled],
        "requested_total": total,
        "allocated_total": round(sum(t.share for t in scaled), 3),
        "evergreen_reserve": EVERGREEN_RESERVE,
        "scaled_by": round(scaling, 3),
        "disbanded": disbanded,
        "refused": refused,
        "note": (
            "no event team is active today, which happens only between occasions and means "
            "the whole capacity is on evergreen work" if not scaled else
            f"{len(scaled)} team(s) hold {round(sum(t.share for t in scaled), 3)} of "
            f"capacity, with {EVERGREEN_RESERVE} reserved for evergreen work: a seasonal "
            f"programme that consumes everything leaves a shop excellent in December and "
            f"absent in February"
            + (f". Shares were scaled by {scaling:.2f} because the occasions overlap"
               if scaling < 1.0 else "")),
    }


def check(allocation: dict) -> None:
    """Refuse an allocation that would leave teams notional or the company unstaffed."""
    if allocation["allocated_total"] > round(1.0 - EVERGREEN_RESERVE, 3) + 1e-6:
        raise TeamRefused(
            f"teams hold {allocation['allocated_total']} of capacity against "
            f"{1.0 - EVERGREEN_RESERVE} available. Six teams each under-resourced by exactly "
            f"as much as the others are notional is the failure #287 guards against")
    for team in allocation["teams"]:
        if team["share"] <= 0:
            raise TeamRefused(
                f"the {team['event']} team holds no capacity. A team with no capacity exists "
                f"on an org chart and nowhere a product comes from")
    for event in PRIORITY_PROGRAMMES:
        active = [t for t in allocation["teams"] if t["event"] == event]
        disbanded = [d for d in allocation["disbanded"] if d["event"] == event]
        if not active and not disbanded:
            raise TeamRefused(
                f"{event} is a priority programme with no team and no recorded reason for "
                f"not having one")
