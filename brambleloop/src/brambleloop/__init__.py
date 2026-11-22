"""Brambleloop.

F-12: CLAUDE.md fixes every date and time in UTC. Daily cadence keys, caps, idempotency keys
and seasonal windows across the package call ``date.today()``, which is the *process-local*
date; it equals the UTC date only while no ``TZ`` is set. One ``TZ`` on a host or laptop
would shift every one of them by up to a day against the UTC timestamps stored beside them.
The process zone is therefore pinned to UTC here, where the package is first imported, so
the local date and the UTC date cannot disagree. Explicit zones (``ZoneInfo(...)``) are
unaffected.
"""
import os as _os
import time as _time

_os.environ["TZ"] = "UTC"
if hasattr(_time, "tzset"):
    _time.tzset()
