"""The durable half of the ceiling: money claimed before the call, released after it.

**What was wrong.** Every ceiling in this system is computed from `cost_entries`, and a cost
row is written *after* the provider has answered. `gateway.anthropic.check_budget` therefore
read a total, returned, and let a call run for seconds against a number that was already out
of date -- not by the caller's own spend, which `uncommitted_cad` now covers, but by every
other caller's. Two processes reading CA$99 of a CA$100 month both find room and both spend.
The 2026-09-24 audit measured the shape and could not fix it: there was nowhere durable to
put a reservation, and inventing one in memory would have been a guard that a redeploy
forgets. The overshoot was bounded by (concurrent callers) x (largest single estimate), and
`image_bench` can estimate double figures in one call. Several departments now run against
one database at once, so this is live rather than theoretical.

**Why a table and not a lock.** A lock held across a provider call serialises every model
call in the company behind the slowest one, and a lock the holder dies inside has to be
broken by exactly the same expiry logic this needs anyway. A reservation is also the thing
the owner's spend-accounting instruction asked for in the first place -- "keep the pre-call
reservation and the post-call reconciliation" -- and until now the pre-call half did not
exist as a record.

**Expiry is not a detail; it is the whole safety argument.** A holder that dies between
reserving and releasing would hold budget against a call that never happened, for the rest of
the month, and Railway replaces this container several times an hour. So a reservation carries
the caller's own bound on how long its call can take, and one past that bound counts for
nothing. The failure mode is a bounded over-reservation, never a permanent phantom charge.

**A caller does not reserve against itself.** `outstanding_cad` excludes the holder asking,
because that caller already accounts for its own in-flight spend through
`check_budget(uncommitted_cad=...)`. Counting both would charge a batching loop twice for the
same money and refuse work the ceiling has room for -- and a guard that refuses correct work
is a guard somebody turns off.
"""
from __future__ import annotations

import os
import socket
import threading
from datetime import datetime, timedelta, timezone

# How long a reservation stands if nobody releases it. It has to exceed the longest a single
# provider call can take, or a call that is still running loses its own protection: the
# gateway's own timeout is 60s and image generation polls for up to 120s, so this is set above
# both. Longer than necessary is not free either -- it is how long a dead holder keeps budget
# it will never spend -- so it is bounded by the worst call rather than by a comfortable
# margin above it.
DEFAULT_TTL_SECONDS = 300

# Rows are kept after release, because a reservation beside the bill it became is the
# reconciliation the spend policy asked for. They are pruned once both figures are in the
# ledger and nothing is reconciling them any more.
KEEP_RELEASED_HOURS = 48


def holder_id() -> str:
    """Who is asking: host, process, thread.

    Not an agent name. The question a reservation answers is "is the thing that took this
    still alive", and two threads of one process -- the web process runs a worker thread --
    are two callers that can race each other.
    """
    return f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def reserve(db, *, amount_cad: float, holder: str | None = None, agent: str = "",
            purpose: str = "", model: str = "", job_id: int | None = None,
            ttl_seconds: int = DEFAULT_TTL_SECONDS,
            now: datetime | None = None, detail: dict | None = None) -> int:
    """Claim `amount_cad` for one call. Returns the reservation id to release it with.

    Written before the call, which is the entire point: a reservation recorded afterwards is
    the `estimated_cad` column, and that already existed and stopped nothing.
    """
    from ..core.models import SpendReservation

    now = now or datetime.now(timezone.utc)
    ttl = max(1, int(ttl_seconds))
    with db.session() as s:
        row = SpendReservation(
            at=now, holder=holder or holder_id(), agent=agent, purpose=purpose, model=model,
            amount_cad=round(max(0.0, float(amount_cad)), 8),
            expires_at=now + timedelta(seconds=ttl), job_id=job_id,
            detail=dict(detail or {}))
        s.add(row)
        s.flush()
        return row.id


def release(db, reservation_id: int | None, *, actual_cad: float | None = None,
            now: datetime | None = None) -> bool:
    """Give the claim back, with what the call actually cost when the caller knows it.

    Returns whether a live reservation was released. `False` covers two different cases that
    are both worth not hiding: an id nobody reserved, and a reservation that had already
    expired -- which means the call outlived its own claim and other callers were, correctly,
    allowed to spend against the room it was holding.

    Tolerates `None` so a caller can release in a `finally` without first asking whether it
    ever got as far as reserving.
    """
    from ..core.models import SpendReservation

    if reservation_id is None:
        return False
    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.get(SpendReservation, int(reservation_id))
        if row is None or row.released_at is not None:
            return False
        row.released_at = now
        if actual_cad is not None:
            row.actual_cad = round(float(actual_cad), 8)
        return _aware(row.expires_at) is None or _aware(row.expires_at) > now


def outstanding(db, *, exclude_holder: str | None = None,
                now: datetime | None = None) -> dict:
    """Live reservations: what is claimed, by whom, and what has expired unreleased.

    Expired rows are reported and **not** counted. A reservation whose holder died is not
    money anybody is about to spend, and counting it would turn one killed container into a
    ceiling that never opens again.
    """
    with db.session() as s:
        return outstanding_in(s, exclude_holder=exclude_holder, now=now)


def outstanding_in(session, *, exclude_holder: str | None = None,
                   now: datetime | None = None) -> dict:
    """The same reading, against a session the caller already holds.

    Two entry points and one implementation. The health sweep is handed a session rather than
    a database -- deliberately, so every signal in one sweep reads one consistent snapshot --
    and a second copy of the "expired rows do not count" rule living there would be the defect
    this repository keeps naming: one value, two places, and they disagree the day one is
    changed.
    """
    from sqlalchemy import select

    from ..core.models import SpendReservation

    now = now or datetime.now(timezone.utc)
    live_cad, live = 0.0, []
    expired_cad, expired = 0.0, []
    mine_cad, mine = 0.0, 0
    for row in session.scalars(select(SpendReservation).where(
            SpendReservation.released_at.is_(None))):
        entry = {"id": row.id, "holder": row.holder, "agent": row.agent,
                 "purpose": row.purpose, "amount_cad": round(row.amount_cad or 0.0, 6),
                 "expires_at": (_aware(row.expires_at).isoformat()
                                if row.expires_at else None)}
        if _aware(row.expires_at) is not None and _aware(row.expires_at) <= now:
            expired.append(entry)
            expired_cad += float(row.amount_cad or 0.0)
            continue
        if exclude_holder and row.holder == exclude_holder:
            mine += 1
            mine_cad += float(row.amount_cad or 0.0)
            continue
        live.append(entry)
        live_cad += float(row.amount_cad or 0.0)
    return {
        "cad": round(live_cad, 6),
        "count": len(live),
        "reservations": live,
        "own_holder_cad": round(mine_cad, 6),
        "own_holder_count": mine,
        "expired_unreleased_cad": round(expired_cad, 6),
        "expired_unreleased": expired,
        "excluded_holder": exclude_holder or "",
        "why_own_is_excluded": (
            "the caller asking already carries its own in-flight spend through "
            "`check_budget(uncommitted_cad=...)`, and counting it twice would refuse work "
            "the ceiling has room for"),
        "why_expired_do_not_count": (
            "a reservation whose holder died is not money anybody is about to spend. "
            "Counting it would let one killed container close the ceiling for the rest of "
            "the month"),
    }


def outstanding_cad(db, *, exclude_holder: str | None = None,
                    now: datetime | None = None) -> float:
    """Just the number, for the guard that only needs the number."""
    return outstanding(db, exclude_holder=exclude_holder, now=now)["cad"]


def sweep(db, *, now: datetime | None = None,
          keep_released_hours: int = KEEP_RELEASED_HOURS) -> dict:
    """Close out expired reservations and prune the ones nothing is reconciling any more.

    Two separate jobs on purpose. An expired reservation is *marked* released rather than
    deleted, with the reason, because "the holder died holding CA$X" is the evidence that a
    call site is not releasing what it takes -- delete it and the next session finds an empty
    table and a ceiling that occasionally behaves oddly. Pruning then removes rows whose
    reservation and bill are both long since in the ledger.
    """
    from sqlalchemy import select

    from ..core.models import SpendReservation

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(1, int(keep_released_hours)))
    abandoned, abandoned_cad, pruned = 0, 0.0, 0
    with db.session() as s:
        for row in s.scalars(select(SpendReservation)):
            released = _aware(row.released_at)
            expires = _aware(row.expires_at)
            if released is None and expires is not None and expires <= now:
                row.released_at = now
                row.detail = {**(row.detail or {}),
                              "abandoned": True,
                              "why": ("the reservation expired without being released, so "
                                      "the holder died between claiming the money and "
                                      "spending it, or the call outlived its own claim")}
                abandoned += 1
                abandoned_cad += float(row.amount_cad or 0.0)
                continue
            if released is not None and released < cutoff:
                s.delete(row)
                pruned += 1
    return {
        "abandoned_closed": abandoned,
        "abandoned_cad": round(abandoned_cad, 6),
        "pruned": pruned,
        "keep_released_hours": keep_released_hours,
        "why_abandoned_are_recorded": (
            "a reservation nobody released is the evidence that a call site does not release "
            "what it takes. Deleting it leaves an empty table and a ceiling that behaves "
            "oddly once in a while"),
    }
