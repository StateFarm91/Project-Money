#!/usr/bin/env python3
"""Print the competition day number. Start timestamp is immutable (COMPETITION_RULES.md)."""
from datetime import datetime, timezone
START = datetime(2026, 9, 15, 11, 0, 7, tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
day = (now - START).days + 1
print(f"Day {day} / 90  (now {now:%Y-%m-%dT%H:%M:%SZ}; start {START:%Y-%m-%dT%H:%M:%SZ})")
