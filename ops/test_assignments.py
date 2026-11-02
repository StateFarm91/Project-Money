"""Tests for ops/assignments.py: lifecycle, staleness, duplicate prevention, and interruption
with safe reassignment and recovery. Run: python3 ops/test_assignments.py"""
import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assignments as A  # noqa: E402

T0 = datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc)
FAILS = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def repo():
    d = Path(tempfile.mkdtemp())
    (d / "COORDINATION.json").write_text(json.dumps({"assignments": [
        {"id": "X1", "owner": "opus2", "priority": 2, "state": "in_progress", "assigned": A.iso(T0)},
        {"id": "Q1", "owner": "UNASSIGNED (next)", "priority": 2, "state": "queued"}]}))
    return d


def row(d, aid, t):
    return next(r for r in A.status(d, t) if r["id"] == aid)


d = repo()
A.post("X1", 3, 8, d, T0)
check(row(d, "X1", T0 + timedelta(hours=1))["stage"] == "posted", "freshly posted, not overdue yet")
check(not row(d, "X1", T0 + timedelta(hours=1))["overdue"], "within ack window: no alarm")
r = row(d, "X1", T0 + timedelta(hours=3, minutes=1))
check(r["overdue"] and r["safe_to_reassign"], "missed ack deadline: overdue and safe to reassign")
check(not row(d, "Q1", T0 + timedelta(hours=9))["overdue"], "queued/unassigned work never alarms")

# lifecycle
A.append_event("opus2", "X1", "ack", root=d, t=T0 + timedelta(minutes=30))
check(row(d, "X1", T0 + timedelta(hours=1))["stage"] == "acknowledged", "ack recorded")
A.append_event("opus2", "X1", "start", root=d, t=T0 + timedelta(minutes=31))
A.append_event("opus2", "X1", "checkpoint", sha="abc123", root=d, t=T0 + timedelta(hours=2))
r = row(d, "X1", T0 + timedelta(hours=2))
check(r["stage"] == "checkpoint_pushed" and r["checkpoint_sha"] == "abc123", "checkpoint with sha")
A.append_event("opus2", "X1", "review_requested", sha="abc123", root=d, t=T0 + timedelta(hours=2))
r = row(d, "X1", T0 + timedelta(hours=20))
check(r["stage"] == "review_requested" and not r["safe_to_reassign"],
      "work under review is never auto-reassigned")

# duplicate prevention
try:
    A.append_event("mainopus-worker", "X1", "start", root=d)
    check(False, "non-owner start refused")
except SystemExit as e:
    check("REFUSED" in str(e), "non-owner start refused")
try:
    A.append_event("opus2", "X1", "checkpoint", root=d)
    check(False, "checkpoint without sha refused")
except SystemExit:
    check(True, "checkpoint without sha refused")

# forged event in another worker's file is not counted
f = d / "dispatch" / "events" / "codex.jsonl"
f.write_text(json.dumps({"at": A.iso(T0), "worker": "opus2", "assignment": "X1", "event": "ack"}) + "\n")
check(any(e["event"] == "forged" for e in A.load_events(d)), "event written into another worker's file is marked forged")

# interruption and recovery: worker acks, starts, then goes silent
d2 = repo()
A.post("X1", 3, 8, d2, T0)
A.append_event("opus2", "X1", "ack", root=d2, t=T0 + timedelta(minutes=10))
A.append_event("opus2", "X1", "start", root=d2, t=T0 + timedelta(minutes=11))
t_dead = T0 + timedelta(hours=4, minutes=12)
r = row(d2, "X1", t_dead)
check(r["overdue"] and r["safe_to_reassign"], "silent after start for >4 h: stale and safe to reassign")
try:
    A.reassign("X1", "mainopus-worker", "too early", d2, T0 + timedelta(hours=1))
    check(False, "premature reassignment refused")
except SystemExit as e:
    check("REFUSED" in str(e), "premature reassignment refused")
A.reassign("X1", "mainopus-worker", "opus2 silent 4 h after start", d2, t_dead)
coord = A.load_coord(d2)["assignments"][0]
check(coord["owner"] == "mainopus-worker" and coord["ownership_history"][-1]["from"] == "opus2",
      "reassignment recorded with history")
ok, why = A.claim_check("X1", "opus2", d2)
check(not ok, "former owner now refused by claim-check (no duplicate execution)")
check(row(d2, "X1", t_dead)["stage"] == "posted", "old owner's events do not count for the new owner")
A.append_event("mainopus-worker", "X1", "ack", root=d2, t=t_dead + timedelta(minutes=5))
A.append_event("mainopus-worker", "X1", "start", root=d2, t=t_dead + timedelta(minutes=6))
A.append_event("mainopus-worker", "X1", "checkpoint", sha="def456", root=d2, t=t_dead + timedelta(hours=1))
r = row(d2, "X1", t_dead + timedelta(hours=1))
check(r["stage"] == "checkpoint_pushed" and not r["overdue"], "recovered under the new owner")

for x in (d, d2):
    shutil.rmtree(x)
print(f"\n{'FAILED ' + str(len(FAILS)) if FAILS else 'ALL PASSED'}")
sys.exit(1 if FAILS else 0)
