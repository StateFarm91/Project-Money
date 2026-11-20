"""How often to look, decided by how often the shop actually changes.

Requirements 212, 213, 313. A fixed interval is wrong in both directions: too slow during a
seasonal release run, and pure waste during the eight quiet weeks that follow. #213 asks for
monitoring that adapts to observed posting behaviour, seasonal urgency and evidence freshness.

The adaptation is deliberately conservative in one direction only. Backing *off* when a shop
is quiet risks missing a release by a few hours; backing off when it is busy risks missing the
release entirely, so the busy case moves fast and the quiet case moves slowly. A cadence that
oscillates with each scan would also be its own problem, so the interval moves by at most one
step per decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

# The ladder. Six hours is the resting rate; ninety minutes is what a release run earns.
INTERVALS_SECONDS: tuple[int, ...] = (
    90 * 60, 3 * 60 * 60, 6 * 60 * 60, 12 * 60 * 60, 24 * 60 * 60,
)
DEFAULT_INDEX = 2  # six hours

# A shop that changed this many times in the last window is actively releasing.
BUSY_CHANGES = 3
QUIET_SCANS_BEFORE_BACKOFF = 4


@dataclass(frozen=True)
class Decision:
    interval_seconds: int
    index: int
    reason: str
    seasonal_pressure: bool

    @property
    def interval_hours(self) -> float:
        return round(self.interval_seconds / 3600.0, 2)

    def to_dict(self) -> dict:
        return {"interval_seconds": self.interval_seconds,
                "interval_hours": self.interval_hours, "index": self.index,
                "reason": self.reason, "seasonal_pressure": self.seasonal_pressure}


def seasonal_pressure(today: date | None = None, within_days: int = 45) -> bool:
    """Is a commercially meaningful event close enough to change what a scan is worth?

    Reuses the seasonal calendar rather than keeping a second one, because two calendars
    drift and the one that drifts is always the one nobody is looking at.
    """
    from ..radar.market import SEASONAL_EVENTS

    today = today or date.today()
    return any(0 <= (event.event_date - today).days <= within_days
               for event in SEASONAL_EVENTS)


def decide(*, current_index: int = DEFAULT_INDEX, changes_last_window: int = 0,
           consecutive_quiet_scans: int = 0, today: date | None = None) -> Decision:
    """Pick the next interval. Moves by one step at most, and speeds up faster than it slows.

    Asymmetric on purpose: being too slow during a release run means missing the thing the
    mission exists to see, while being too fast during a quiet week costs a few cheap calls
    against an unchanged catalogue that the fingerprint already makes nearly free.
    """
    pressure = seasonal_pressure(today)
    index = current_index

    if changes_last_window >= BUSY_CHANGES:
        index = max(0, current_index - 1)
        reason = (f"{changes_last_window} changes in the last window: the shop is releasing, "
                  f"and a slow cadence here misses the event the mission exists to catch")
    elif pressure and current_index > DEFAULT_INDEX:
        index = max(DEFAULT_INDEX, current_index - 1)
        reason = ("a commercially meaningful event is inside the planning window, so the "
                  "cadence returns to at least its resting rate")
    elif consecutive_quiet_scans >= QUIET_SCANS_BEFORE_BACKOFF and not pressure:
        index = min(len(INTERVALS_SECONDS) - 1, current_index + 1)
        reason = (f"{consecutive_quiet_scans} consecutive scans found nothing and no event is "
                  f"near: backing off rather than paying to confirm the same catalogue")
    else:
        reason = "no evidence to move the cadence in either direction"

    return Decision(INTERVALS_SECONDS[index], index, reason, pressure)


def observed_state(db, benchmark_key: str, *, window_hours: int = 48) -> dict:
    """What the audit log says about how this shop has been behaving.

    Read from recorded scans rather than held in memory, so a restart does not reset the
    company's sense of how busy its benchmark is.
    """
    from sqlalchemy import desc, select

    from ..core.models import BenchmarkObservation

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    with db.session() as s:
        rows = list(s.scalars(
            select(BenchmarkObservation)
            .where(BenchmarkObservation.benchmark_key == benchmark_key)
            .order_by(desc(BenchmarkObservation.id)).limit(40)))

    def _aware(value):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    recent = [r for r in rows if _aware(r.at) >= cutoff]
    changes = sum(len((r.detail or {}).get("changes") or []) for r in recent)

    quiet = 0
    for row in rows:                      # newest first
        if len((row.detail or {}).get("changes") or []) == 0:
            quiet += 1
        else:
            break

    return {"scans_in_window": len(recent), "changes_last_window": changes,
            "consecutive_quiet_scans": quiet}


def next_interval(db, benchmark_key: str, *, current_index: int = DEFAULT_INDEX,
                  today: date | None = None) -> Decision:
    state = observed_state(db, benchmark_key)
    return decide(current_index=current_index,
                  changes_last_window=state["changes_last_window"],
                  consecutive_quiet_scans=state["consecutive_quiet_scans"],
                  today=today)
