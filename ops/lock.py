#!/usr/bin/env python3
"""Lease lock for unattended sessions (see AUTOMATIONS.md).
Usage: python3 ops/lock.py acquire <session_id>   -> exit 0 if acquired (writes ops/LOCK), 3 if another live lease exists
       python3 ops/lock.py release <session_id>
       python3 ops/lock.py status
A lease older than STALE_HOURS is treated as dead and may be taken over (the takeover is noted on stdout for DAILY_LOG)."""
import sys, json, pathlib, datetime
LOCK = pathlib.Path(__file__).resolve().parent / "LOCK"; STALE_HOURS = 3
now = datetime.datetime.now(datetime.timezone.utc)
def read():
    if not LOCK.exists(): return None
    try: return json.loads(LOCK.read_text())
    except Exception: return None
cmd = sys.argv[1] if len(sys.argv) > 1 else "status"; sid = sys.argv[2] if len(sys.argv) > 2 else "unknown"
cur = read()
if cmd == "status":
    print(json.dumps(cur) if cur else "no lock"); sys.exit(0)
if cmd == "acquire":
    if cur and cur.get("session") != sid:
        age = (now - datetime.datetime.fromisoformat(cur["acquired_utc"])).total_seconds() / 3600
        if age < STALE_HOURS: print(f"held by {cur['session']} for {age:.1f}h; exiting"); sys.exit(3)
        print(f"stale lease ({age:.1f}h) from {cur['session']} taken over")
    LOCK.write_text(json.dumps({"session": sid, "acquired_utc": now.isoformat()})); print("acquired"); sys.exit(0)
if cmd == "release":
    if cur and cur.get("session") == sid: LOCK.unlink(); print("released")
    else: print("not held by this session")
    sys.exit(0)
