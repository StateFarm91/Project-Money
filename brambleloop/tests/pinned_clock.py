"""A pinned, still-ticking clock for test files whose scenario only exists on certain dates.

Not a suite itself. Some certification scenarios are calendar facts. A Christmas throw can still
launch for a confident beginner only until 2026-10-21. A USD sale seeded 'last month' stays inside
a trailing 30-day window only until about the 24th. A file that runs those scenarios on the wall
clock passes or fails depending on the day the suite runs (INTEG5/LISTREL, 2026-10-26).

`install(at)` moves every `datetime.now()` / `datetime.utcnow()` / `date.today()` that this process
reads to `at` plus the real time elapsed since install. The clock keeps ticking, so leases, back-offs
and run_after windows still pass, and the scenario is the same on every day the suite runs. Nothing
is skipped and no assertion changes: production code runs unmodified at a stated date.

How it works, as freezegun does: `datetime.datetime` and `datetime.date` are replaced, in the
`datetime` module and in every loaded `brambleloop` module namespace, by subclasses whose metaclass
answers `isinstance` for real instances. Every `brambleloop` module is imported first, so a module
loaded later still sees the pinned classes through the `datetime` module. Call `install` before
importing anything that computes a module-level "now".
"""
from __future__ import annotations

import datetime as _dt
import importlib
import pkgutil
import sys
import time

_REAL_DATETIME = _dt.datetime
_REAL_DATE = _dt.date
_STATE: dict = {}


def _offset() -> _dt.timedelta:
    return _dt.timedelta(seconds=time.monotonic() - _STATE["t0"])


class _Meta(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, cls._real)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, cls._real)


class PinnedDatetime(_REAL_DATETIME, metaclass=_Meta):
    _real = _REAL_DATETIME

    @classmethod
    def now(cls, tz=None):
        aware = _STATE["at"] + _offset()
        if tz is None:
            return aware.replace(tzinfo=None)     # the container's local time is UTC
        return aware.astimezone(tz)

    @classmethod
    def utcnow(cls):
        return (_STATE["at"] + _offset()).replace(tzinfo=None)

    @classmethod
    def today(cls):
        return cls.now()


class PinnedDate(_REAL_DATE, metaclass=_Meta):
    _real = _REAL_DATE

    @classmethod
    def today(cls):
        return (_STATE["at"] + _offset()).date()


def now() -> _dt.datetime:
    """The pinned 'now' (aware, UTC), for a test file's own module-level NOW."""
    return PinnedDatetime.now(_dt.timezone.utc)


def install(at: str) -> _dt.datetime:
    """Pin this process's clock to `at` (ISO 8601, with an offset). Idempotent."""
    if _STATE:
        return _STATE["at"]
    pinned = _REAL_DATETIME.fromisoformat(at)
    if pinned.tzinfo is None:
        raise ValueError("pin the clock with an explicit UTC offset")
    _STATE.update(at=pinned.astimezone(_dt.timezone.utc), t0=time.monotonic())
    import brambleloop

    for m in pkgutil.walk_packages(brambleloop.__path__, "brambleloop."):
        try:
            importlib.import_module(m.name)
        except Exception:  # noqa: BLE001 - a module that cannot import is not running here
            pass
    _dt.datetime, _dt.date = PinnedDatetime, PinnedDate
    for name, mod in list(sys.modules.items()):
        if not (name == "brambleloop" or name.startswith("brambleloop.")) or mod is None:
            continue
        for attr, val in list(vars(mod).items()):
            if val is _REAL_DATETIME:
                setattr(mod, attr, PinnedDatetime)
            elif val is _REAL_DATE:
                setattr(mod, attr, PinnedDate)
    return _STATE["at"]
