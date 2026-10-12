#!/usr/bin/env python3
"""A bounded, deduplicated waiter for enrolled jobs (F-334, F-337, F-340, F-344).

Usage:
  python3 ops/waiter.py wait <job> [--max-wall S] [--poll S] [--class C]
        -> 0 finished clean, 1 finished failed/unfinished, 4 attached to an existing waiter,
           5 wall-time bound breached, 6 observer bound reached, 2 unenrolled
  python3 ops/waiter.py ack <job>          acknowledge in the registry AND account the idle time
  python3 ops/waiter.py waste [--days N]   time lost to orchestration, and whether it is an incident
                                           (each incident opens an ops/incidents.py ledger entry)
  python3 ops/waiter.py normal <class>     the rolling normal duration of an operation class

WHY THIS EXISTS. `board.py` and `registry.py` made a job's verdict computable from its own
evidence, durably. What they deliberately do not do is wait -- and waiting is where this build
has lost the most wall-clock time: an `until pgrep -f run_tests.sh` loop that matched itself and
never ended, several waiters on the same suite each polling it, a monitor left running for hours
after its job had died. None of those cost a cent, and each cost more time than any model call.
So waiting is a primitive with four rules, each a requirement:

  ONE WAITER PER JOB (F-334). A waiter takes an O_CREAT|O_EXCL lease named for the job, as
  `ops/lock.py` does for sessions. A second request for the same job does not start a second
  poller: it ATTACHES -- it reads the job's durable verdict from the registry once, reports the
  live waiter that already holds the lease, and returns. A lease whose holder is gone (pid dead,
  or the pid reused by a process with a different start time) is a duplicate-or-stale record: it
  is detected, taken over atomically, and the takeover is reported.

  BOUNDED (F-340). Every wait has a maximum wall time, and the number of live waiters across all
  jobs is capped. A waiter never spawns a process -- it reads files through the registry. On a
  wall-time breach it stops waiting, releases its lease and returns the registry's authoritative
  diagnosis of the job instead of continuing to observe; at the observer cap it refuses to start.

  EXPECTED-DURATION WATCHDOG (F-337). Durations are recorded per operation class, from the
  job's enrolment to the finish the job itself stamped. With at least MIN_HISTORY samples, a job
  running past 3x the rolling median is flagged once: "verify authoritative state" -- and the
  waiter does exactly that, re-reading the registry with its process probe, and stops if the
  job is no longer RUNNING rather than waiting on a belief.

  TIME WASTE IS ACCOUNTED (F-344). When a finished job is acknowledged, the gap between the
  finish it stamped and the acknowledgement is idle wall-clock: time the lane stood finished
  with nobody acting. It is recorded separately from any compute or API spend, rolled up per
  day, and a single gap above IDLE_INCIDENT_S or a day above DAILY_INCIDENT_S is a RELIABILITY
  INCIDENT even though no money was spent.

State lives under brambleloop/artifacts/ops_waiters/ (git-ignored, survives a container restart
because the checkout does); WAITER_DIR overrides it.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import board as B                                                      # noqa: E402
import incidents as I                                                  # noqa: E402
import registry as R                                                   # noqa: E402

STATE_DIR = Path(os.environ.get("WAITER_DIR") or
                 _HERE.parent / "brambleloop" / "artifacts" / "ops_waiters")

MAX_WALL_S = 45 * 60          # no single wait may run unattended longer than this
MAX_WAITERS = 4               # live waiters across every job on this host
WATCHDOG_FACTOR = 3.0
MIN_HISTORY = 5
HISTORY = 20
IDLE_INCIDENT_S = 15 * 60
DAILY_INCIDENT_S = 60 * 60

COMPLETED = "completed"
ATTACHED = "attached"
BREACH = "wall_time_breach"
OBSERVER_BOUND = "observer_bound"
UNENROLLED = "unenrolled"
STOPPED = "stopped_not_running"

_EXIT = {COMPLETED: 0, ATTACHED: 4, BREACH: 5, OBSERVER_BOUND: 6, UNENROLLED: 2, STOPPED: 1}


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).replace(microsecond=0).isoformat()


def _epoch_of(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def proc_start(pid: int) -> str | None:
    """Field 22 of /proc/<pid>/stat, or None if the process is gone."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[19]
    except Exception:
        return None


class Waiter:
    def __init__(self, registry: R.Registry | None = None, state_dir: Path | str = STATE_DIR, *,
                 clock=time.time, sleep=time.sleep, table=None, max_waiters: int = MAX_WAITERS,
                 pid: int | None = None, ledger: "I.Ledger | None" = None):
        self.registry = registry or R.Registry()
        self.dir = Path(state_dir)
        # F-350: material delay opens a reliability-incident ledger entry. A waiter on a
        # private state dir (tests, a scratch run) keeps its ledger beside that state.
        self.ledger = ledger or I.Ledger(I.LEDGER if self.dir == Path(STATE_DIR)
                                         else self.dir / "RELIABILITY_INCIDENTS.jsonl")
        self.clock, self.sleep, self.table = clock, sleep, table
        self.max_waiters = max_waiters
        self.pid = pid or os.getpid()
        (self.dir / "leases").mkdir(parents=True, exist_ok=True)

    # -- leases (F-334) ------------------------------------------------------------------
    def _lease_path(self, job: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in job)
        return self.dir / "leases" / f"{safe}.lease"

    def _holder_alive(self, lease: dict) -> bool:
        pid = lease.get("pid")
        return bool(pid) and proc_start(int(pid)) == lease.get("pid_start")

    def _read_lease(self, path: Path) -> dict:
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def live_waiters(self) -> list[dict]:
        out = []
        for p in sorted((self.dir / "leases").glob("*.lease")):
            lease = self._read_lease(p)
            if self._holder_alive(lease):
                out.append(lease)
        return out

    def _acquire(self, job: str, deadline: float) -> tuple[bool, dict, str | None]:
        """(acquired, lease-or-holder, run id of a stale lease taken over)."""
        path = self._lease_path(job)
        mine = {"job": job, "pid": self.pid, "pid_start": proc_start(self.pid),
                "started_utc": _utc(self.clock()), "deadline_utc": _utc(deadline)}
        taken_over = None
        for _ in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                holder = self._read_lease(path)
                if self._holder_alive(holder):
                    return False, holder, None
                # Stale or duplicate record: the process that wrote it is gone. Move it aside
                # atomically so only one contender can win the retry.
                taken_over = f"pid {holder.get('pid')} started {holder.get('started_utc')}"
                try:
                    os.replace(path, path.with_suffix(f".stale.{self.pid}"))
                    path.with_suffix(f".stale.{self.pid}").unlink(missing_ok=True)
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w") as f:
                json.dump(mine, f)
            return True, mine, taken_over
        return False, self._read_lease(path), taken_over

    def _release(self, job: str) -> None:
        path = self._lease_path(job)
        if self._read_lease(path).get("pid") == self.pid:
            path.unlink(missing_ok=True)

    # -- durations (F-337) ---------------------------------------------------------------
    def _append(self, name: str, rec: dict) -> None:
        with open(self.dir / name, "a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")

    def _lines(self, name: str) -> list[dict]:
        try:
            text = (self.dir / name).read_text()
        except OSError:
            return []
        out = []
        for line in text.splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def record_duration(self, op_class: str, job: str, run_key: str, duration_s: float,
                        outcome: str) -> bool:
        """Once per (job, enrolment). Returns False when already recorded."""
        if any(r.get("run_key") == run_key for r in self._lines("durations.jsonl")):
            return False
        self._append("durations.jsonl", {"op_class": op_class, "job": job, "run_key": run_key,
                                         "duration_s": round(duration_s, 1), "outcome": outcome,
                                         "recorded_utc": _utc(self.clock())})
        return True

    def normal(self, op_class: str) -> dict:
        xs = [r["duration_s"] for r in self._lines("durations.jsonl")
              if r.get("op_class") == op_class and r.get("outcome") == COMPLETED]
        xs = xs[-HISTORY:]
        if len(xs) < MIN_HISTORY:
            return {"op_class": op_class, "samples": len(xs), "median_s": None,
                    "why": f"fewer than {MIN_HISTORY} completed runs: no envelope yet"}
        return {"op_class": op_class, "samples": len(xs), "median_s": statistics.median(xs)}

    def watchdog(self, op_class: str, running_for_s: float) -> dict:
        n = self.normal(op_class)
        if n["median_s"] is None:
            return {"fired": False, **n}
        threshold = WATCHDOG_FACTOR * n["median_s"]
        return {"fired": running_for_s > threshold, "threshold_s": threshold,
                "running_for_s": round(running_for_s, 1), **n}

    # -- time waste (F-344) --------------------------------------------------------------
    def account_idle(self, job: str, idle_s: float, cause: str, op_class: str = "") -> dict:
        rec = {"job": job, "op_class": op_class, "idle_s": round(max(idle_s, 0.0), 1),
               "cause": cause, "at_utc": _utc(self.clock()),
               "incident": idle_s > IDLE_INCIDENT_S}
        self._append("time_waste.jsonl", rec)
        if rec["incident"]:
            rec["ledger"] = self._ledger_open(
                f"material_delay:{job}:{rec['at_utc']}",
                f"{job} stood finished and unacknowledged for {rec['idle_s'] / 60:.0f} min "
                f"(threshold {IDLE_INCIDENT_S / 60:.0f}): {cause}"[:400],
                {"job": job, "idle_s": rec["idle_s"], "op_class": op_class})
        return rec

    def _ledger_open(self, signature: str, summary: str, evidence: dict) -> dict:
        try:
            return self.ledger.open("material_delay", signature, summary, evidence=evidence,
                                    source="ops/waiter.py")
        except Exception as exc:  # noqa: BLE001 - accounting must not stop an ack
            return {"opened": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

    def waste_report(self, days: int = 7) -> dict:
        since = self.clock() - days * 86400
        rows = [r for r in self._lines("time_waste.jsonl")
                if (_epoch_of(r.get("at_utc")) or 0) >= since]
        by_day: dict[str, float] = {}
        for r in rows:
            by_day[r["at_utc"][:10]] = by_day.get(r["at_utc"][:10], 0.0) + r["idle_s"]
        incidents = [r for r in rows if r.get("incident")] + [
            {"day": d, "idle_s": round(s, 1), "cause": "daily idle total above threshold"}
            for d, s in sorted(by_day.items()) if s > DAILY_INCIDENT_S]
        for d, total in sorted(by_day.items()):
            if total > DAILY_INCIDENT_S:
                self._ledger_open(f"material_delay:day:{d}",
                                  f"{total / 60:.0f} min of idle wall-clock on {d} (daily "
                                  f"threshold {DAILY_INCIDENT_S / 60:.0f})",
                                  {"day": d, "idle_s": round(total, 1)})
        return {"days": days, "idle_s_total": round(sum(r["idle_s"] for r in rows), 1),
                "idle_s_by_day": {d: round(s, 1) for d, s in sorted(by_day.items())},
                "events": len(rows), "reliability_incidents": incidents,
                "spend_cad": "not applicable: wall-clock loss is accounted apart from spend"}

    # -- the verbs -----------------------------------------------------------------------
    def _class(self, job: str, op_class: str | None) -> str:
        if op_class:
            return op_class
        rec = self.registry.load()["jobs"].get(job, {})
        return rec.get("lane") or ("suite" if "run_tests" in rec.get("marker", "") else job)

    def _finish_facts(self, job: str, row: dict) -> tuple[float | None, str]:
        """(duration from enrolment to the job's own finish, run key) where computable."""
        rec = self.registry.load()["jobs"].get(job, {})
        enrolled = _epoch_of(rec.get("enrolled_utc"))
        run_key = f"{job}@{rec.get('enrolled_utc')}"
        if enrolled is None or row.get("age_s") is None:
            return None, run_key
        finished = self.clock() - float(row["age_s"])
        return max(finished - enrolled, 0.0), run_key

    def wait(self, job: str, *, max_wall_s: float = MAX_WALL_S, poll_s: float = 15.0,
             op_class: str | None = None) -> dict:
        start = self.clock()
        first = self.registry.recall(job, now=start, table=self.table)
        if first["state"] == R.UNENROLLED:
            return {"outcome": UNENROLLED, "job": job, "row": first}
        if not self._lease_path(job).exists() and len(self.live_waiters()) >= self.max_waiters:
            return {"outcome": OBSERVER_BOUND, "job": job, "row": first,
                    "live_waiters": self.live_waiters(),
                    "why": (f"{self.max_waiters} waiters are already live; not starting another "
                            "observer. Read the registry instead: `python3 ops/registry.py`")}
        ok, lease, taken_over = self._acquire(job, start + max_wall_s)
        if not ok:
            return {"outcome": ATTACHED, "job": job, "row": first, "waiter": lease,
                    "why": "a live waiter already holds this job; its durable verdict is above"}
        cls = self._class(job, op_class)
        watch_events: list[dict] = []
        try:
            row = first
            while True:
                now = self.clock()
                if row["state"] != R.RUNNING:
                    outcome = COMPLETED if row["state"] in (
                        R.COMPLETE, R.COMPLETE_UNREPORTED, R.COMPLETE_REPORTED, R.FAILED,
                        R.INTEGRATED) else STOPPED
                    duration, run_key = self._finish_facts(job, row)
                    if duration is not None and outcome == COMPLETED and \
                            row["state"] != R.FAILED:
                        self.record_duration(cls, job, run_key, duration, COMPLETED)
                    return {"outcome": outcome, "job": job, "row": row, "op_class": cls,
                            "waited_s": round(now - start, 1), "watchdog": watch_events,
                            "took_over_stale_waiter": taken_over}
                if now - start >= max_wall_s:
                    # The bound. Stop observing and hand back the authoritative diagnosis --
                    # the registry's verdict with its process probe -- not another poll.
                    diag = self.registry.recall(job, now=now, table=self.table)
                    return {"outcome": BREACH, "job": job, "row": diag, "op_class": cls,
                            "waited_s": round(now - start, 1), "watchdog": watch_events,
                            "why": (f"waited {max_wall_s:.0f}s, the bound; stopped observing. "
                                    "Diagnose from the registry row, do not start another "
                                    "waiter"), "took_over_stale_waiter": taken_over}
                rec = self.registry.load()["jobs"].get(job, {})
                enrolled = _epoch_of(rec.get("enrolled_utc"))
                if enrolled is not None and not watch_events:
                    w = self.watchdog(cls, now - enrolled)
                    if w["fired"]:
                        verify = self.registry.recall(job, now=now, table=self.table)
                        watch_events.append({**w, "verified_state": verify["state"],
                                             "at_utc": _utc(now)})
                        if verify["state"] != R.RUNNING:
                            row = verify
                            continue
                self.sleep(min(poll_s, max(max_wall_s - (now - start), 0.01)))
                row = self.registry.recall(job, now=self.clock(), table=self.table)
        finally:
            self._release(job)

    def ack(self, job: str) -> dict:
        """Acknowledge in the registry, then account the idle gap the acknowledgement closes."""
        now = self.clock()
        row = self.registry.recall(job, now=now, table=self.table)
        out = self.registry.acknowledge(job, now=now, table=self.table)
        if out.get("acknowledged"):
            cls = self._class(job, None)
            idle = float(row.get("age_s") or 0.0)
            out["idle"] = self.account_idle(
                job, idle, cause=("finished and unacknowledged until now "
                                  f"(age from {row.get('age_source', 'unknown')})"), op_class=cls)
            duration, run_key = self._finish_facts(job, row)
            if duration is not None and row["state"] != R.FAILED:
                self.record_duration(cls, job, run_key, duration, COMPLETED)
        return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wait")
    w.add_argument("job")
    w.add_argument("--max-wall", type=float, default=MAX_WALL_S)
    w.add_argument("--poll", type=float, default=15.0)
    w.add_argument("--class", dest="op_class", default=None)
    a = sub.add_parser("ack")
    a.add_argument("job")
    ws = sub.add_parser("waste")
    ws.add_argument("--days", type=int, default=7)
    n = sub.add_parser("normal")
    n.add_argument("op_class")
    args = ap.parse_args(argv)
    waiter = Waiter()
    if args.cmd == "wait":
        out = waiter.wait(args.job, max_wall_s=args.max_wall, poll_s=args.poll,
                          op_class=args.op_class)
        print(json.dumps(out, indent=2, sort_keys=True, default=str))
        code = _EXIT[out["outcome"]]
        if out["outcome"] == COMPLETED and out["row"]["state"] == R.FAILED:
            code = 1
        return code
    if args.cmd == "ack":
        print(json.dumps(waiter.ack(args.job), indent=2, sort_keys=True, default=str))
        return 0
    if args.cmd == "waste":
        rep = waiter.waste_report(args.days)
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 1 if rep["reliability_incidents"] else 0
    print(json.dumps(waiter.normal(args.op_class), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
