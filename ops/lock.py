#!/usr/bin/env python3
"""Lease lock for unattended sessions (see AUTOMATIONS.md).
Usage: python3 ops/lock.py acquire <session_id>   -> exit 0 if acquired (writes ops/LOCK), 3 if another live lease exists
       python3 ops/lock.py refresh <session_id>   -> exit 0 if the lease was extended, 3 if this session does not hold it
       python3 ops/lock.py release <session_id>
       python3 ops/lock.py status
A lease older than STALE_HOURS is treated as dead and may be taken over (the takeover is noted on stdout for DAILY_LOG).

Two corrections, both found while auditing what happens when several sessions run at once.

`acquire` used to read the file and then write it, which is two steps and not a lock: two
sessions that both find no lease both write one, the second overwrites the first, and both
believe they hold it. The take is now a single `O_CREAT|O_EXCL` create, which the filesystem
either allows once or refuses -- so the loser is told, rather than discovering it later by
the work being done twice. Taking over a stale lease is the same create against a temporary
name followed by an atomic rename, so the decision and the write cannot be separated by
another session's.

And a lease could be stolen from a session that was still working: `STALE_HOURS` measures
time since the lease was *acquired*, so any session running longer than the stale window was
declared dead while it ran. The lease now carries a heartbeat that `refresh` moves, and
staleness is measured from the last heartbeat -- so a long session keeps its lease by saying
it is alive, and a session that has actually died still loses it after STALE_HOURS.
"""
import datetime
import json
import os
import pathlib
import sys

LOCK = pathlib.Path(__file__).resolve().parent / "LOCK"
STALE_HOURS = 3
now = datetime.datetime.now(datetime.timezone.utc)


def read():
    if not LOCK.exists():
        return None
    try:
        return json.loads(LOCK.read_text())
    except Exception:
        return None


def _lease(session):
    stamp = now.isoformat()
    return json.dumps({"session": session, "acquired_utc": stamp, "heartbeat_utc": stamp})


def _age_hours(lease):
    """Hours since this lease last said it was alive.

    From the heartbeat, falling back to the acquisition time for a lease written by the
    older version of this file. A malformed or missing timestamp reads as infinitely old
    rather than raising: an unreadable lease must not be able to wedge every future session
    out, and it must not crash the caller either -- this script's exit code is the answer.
    """
    for key in ("heartbeat_utc", "acquired_utc"):
        raw = (lease or {}).get(key)
        if not raw:
            continue
        try:
            return (now - datetime.datetime.fromisoformat(raw)).total_seconds() / 3600
        except (TypeError, ValueError):
            continue
    return float("inf")


def _create_exclusively(payload):
    """Create the lock file only if it does not exist. Returns False if somebody won first."""
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as fh:
        fh.write(payload)
    return True


cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
sid = sys.argv[2] if len(sys.argv) > 2 else "unknown"
cur = read()

if cmd == "status":
    print(json.dumps(cur) if cur else "no lock")
    sys.exit(0)

if cmd == "acquire":
    if _create_exclusively(_lease(sid)):
        print("acquired")
        sys.exit(0)
    cur = read()
    if cur and cur.get("session") == sid:
        LOCK.write_text(_lease(sid))
        print("acquired")
        sys.exit(0)
    age = _age_hours(cur)
    if age < STALE_HOURS:
        held = (cur or {}).get("session", "an unreadable lease")
        print(f"held by {held} for {age:.1f}h; exiting")
        sys.exit(3)
    # Stale. Write beside it and rename over it, so the takeover is one filesystem step.
    tmp = LOCK.with_suffix(f".takeover.{os.getpid()}")
    tmp.write_text(_lease(sid))
    os.replace(tmp, LOCK)
    print(f"stale lease ({age:.1f}h) from {(cur or {}).get('session')} taken over")
    sys.exit(0)

if cmd == "refresh":
    if cur and cur.get("session") == sid:
        lease = dict(cur)
        lease["heartbeat_utc"] = now.isoformat()
        LOCK.write_text(json.dumps(lease))
        print("refreshed")
        sys.exit(0)
    print(f"not held by this session (held by {(cur or {}).get('session')})")
    sys.exit(3)

if cmd == "release":
    if cur and cur.get("session") == sid:
        LOCK.unlink()
        print("released")
    else:
        print("not held by this session")
    sys.exit(0)

print(f"unknown command {cmd!r}")
sys.exit(2)
