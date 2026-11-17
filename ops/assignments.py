#!/usr/bin/env python3
"""Cross-session assignment dispatch over git (owner directive 2026-11-02, "restore reliable
Main <-> Secondary coordination").

`registry.py` and `board.py` track processes inside one container, and `dispatch.py` prints
advisory cards for READY build tasks. Neither can tell whether ANOTHER session received an
assignment, acted on it, or went quiet. This module is that missing layer. It adds an
acknowledgement and progress record to the existing COORDINATION.json `assignments` and needs
no cross-session tool. It is not a second management system.

Records, all on branch claude/w4-INTEG8-next:
  * COORDINATION.json `assignments[*]`: written by the integrator only. Holds a unique id,
    owner, priority, dependencies, branch, acceptance and state. `dispatch` holds posted_at,
    ack_due_by and checkpoint_due_by; `ownership_history` records every transfer.
  * dispatch/events/<worker>.jsonl: append-only, and only that worker writes its own file.
    Each line is {"at", "worker", "assignment", "event", "sha"?, "note"?}. One writer per file,
    so concurrent pushes never touch the same lines.

Event kinds a worker records:
  ack, start, heartbeat (no assignment means "alive"), checkpoint (needs a sha),
  review_requested (needs a sha), blocked, released.
The integrator records reviewed and integrated as `review_verdict` and `state` in
COORDINATION.json. Derived lifecycle stages:
  posted -> acknowledged -> started -> checkpoint_pushed -> review_requested -> reviewed -> integrated

Delivery is by POLLING only, never immediate. The integrator polls on its check-in cadence,
and each worker polls this file and PR #3 on its own wake.
  * `stale` lists overdue work and exits 1 if any exists.
  * `claim-check` refuses a worker that does not own the assignment, which prevents duplicate
    execution. `start`, `checkpoint` and `review_requested` run it automatically.
  * `reassign` requires the owner's authorization (I-THREE-OPERATOR-STRUCTURE). Overdue work
    is REPORTED to the owner with the specific limitation; it is never moved silently. Even with
    authorization, it refuses unsafe moves (a checkpoint under review) unless forced.

  python3 ops/assignments.py status [--json]
  python3 ops/assignments.py stale
  python3 ops/assignments.py event <worker> <assignment|-> <kind> [--sha SHA] [--note TEXT] [--push]
  python3 ops/assignments.py claim-check <assignment> <worker>
  python3 ops/assignments.py post <assignment> [--ack-hours 3] [--checkpoint-hours 8]   # integrator
  python3 ops/assignments.py reassign <assignment> <new_owner> --reason TEXT --owner-approved REF   # integrator, owner-authorized only
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENT_KINDS = ("ack", "start", "heartbeat", "checkpoint", "review_requested", "blocked", "released")
DEFAULT_ACK = timedelta(hours=3)          # one missed 2-hourly wake, plus margin
DEFAULT_CHECKPOINT = timedelta(hours=8)
STALE_PROGRESS = timedelta(hours=4)
INACTIVE = ("integrated", "done", "queued", "split", "superseded")
BRANCH = "claude/w4-INTEG8-next"


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s) -> datetime | None:
    if not s:
        return None
    s = str(s).strip().replace("Z", "+00:00")
    if len(s) == 22 and s[13] == ":" and s[16] == "+":      # 2026-11-02T18:05+00:00
        s = s[:16] + ":00" + s[16:]
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def load_coord(root: Path = ROOT) -> dict:
    return json.loads((root / "COORDINATION.json").read_text())


def save_coord(d: dict, root: Path = ROOT) -> None:
    (root / "COORDINATION.json").write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


def load_events(root: Path = ROOT) -> list[dict]:
    out: list[dict] = []
    for f in sorted((root / "dispatch" / "events").glob("*.jsonl")):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except ValueError:
                out.append({"worker": f.stem, "event": "corrupt", "note": f"{f.name}:{n}"})
                continue
            if e.get("worker") != f.stem:     # a worker may write only its own file
                e = {**e, "event": "forged", "note": f"{f.name}:{n} claims {e.get('worker')}"}
            out.append(e)
    return out


def _owner(a: dict) -> str:
    return str(a.get("owner", ""))


def _stage(a: dict, evs: list[dict]) -> str:
    if str(a.get("state")) in ("integrated", "done"):
        return "integrated"
    if a.get("review_verdict"):
        return "reviewed"
    kinds = {e["event"] for e in evs}
    for k, s in (("review_requested", "review_requested"), ("checkpoint", "checkpoint_pushed"),
                 ("start", "started"), ("ack", "acknowledged")):
        if k in kinds:
            return s
    return "posted"


def assess(a: dict, events: list[dict], t: datetime) -> dict:
    o = _owner(a)
    since = parse((a.get("ownership_history") or [{}])[-1].get("at"))
    mine = [e for e in events if e.get("worker") == o and e.get("event") in EVENT_KINDS]
    evs = [e for e in mine if e.get("assignment") == a.get("id")
           and not (since and (parse(e.get("at")) or since) < since)]
    times = [parse(e.get("at")) for e in evs if parse(e.get("at"))]
    last = max(times, default=None)
    seen = max((parse(e.get("at")) for e in mine if parse(e.get("at"))), default=None)
    d = a.get("dispatch") or {}
    posted = parse(d.get("posted_at")) or parse(a.get("assigned"))
    ack_due = parse(d.get("ack_due_by")) or (posted + DEFAULT_ACK if posted else None)
    cp_due = parse(d.get("checkpoint_due_by")) or (posted + DEFAULT_CHECKPOINT if posted else None)
    s = _stage(a, evs)
    overdue: list[str] = []
    if str(a.get("state")) not in INACTIVE and o and not o.startswith("UNASSIGNED"):
        if s == "posted" and ack_due and t > ack_due:
            overdue.append(f"no ack (posted {iso(posted)}, due {iso(ack_due)})")
        if s in ("posted", "acknowledged", "started") and cp_due and t > cp_due:
            overdue.append(f"no tested checkpoint (due {iso(cp_due)})")
        if s in ("acknowledged", "started") and last and t - last > STALE_PROGRESS:
            overdue.append(f"no progress since {iso(last)}")
        if evs and evs[-1]["event"] == "blocked":
            overdue.append("blocked: " + str(evs[-1].get("note", ""))[:120])
    return {"id": a.get("id"), "owner": o, "priority": a.get("priority"), "stage": s,
            "state": a.get("state"), "last_event": iso(last) if last else None,
            "worker_last_seen": iso(seen) if seen else None,
            "checkpoint_sha": next((e.get("sha") for e in reversed(evs) if e.get("sha")), None),
            "overdue": overdue,
            "delivery": delivery(a, evs),
            "justification_missing": [k for k in JUSTIFICATION if not (a.get("justification") or {}).get(k)],
            "safe_to_reassign": bool(overdue) and s in ("posted", "acknowledged", "started")}


LADDER = ("not_built", "built", "reviewed", "integrated", "certified", "deployed",
          "production_verified", "e2e_accepted")
JUSTIFICATION = ("capability", "handoff_or_defect", "component", "upstream", "downstream",
                 "acceptance", "path_to_production")


def delivery(a: dict, evs: list[dict]) -> str:
    """Owner contract 2026-11-02 s.8: BUILT -> REVIEWED -> INTEGRATED -> CERTIFIED -> DEPLOYED ->
    PRODUCTION-VERIFIED -> END-TO-END ACCEPTED. Each rung needs recorded evidence; the integrator
    writes the `delivery` fields (review_verdict SHIP, integrated_in, certified_run, deployed_sha,
    production_evidence, e2e_evidence). A worker's checkpoint event counts as BUILT."""
    dv = a.get("delivery") or {}
    rung = "built" if any(e["event"] == "checkpoint" for e in evs) else "not_built"
    if str(a.get("review_verdict", "")).upper().startswith(("SHIP", "ACCEPT")):
        rung = "reviewed"
    for key, name in (("integrated_in", "integrated"), ("certified_run", "certified"),
                      ("deployed_sha", "deployed"), ("production_evidence", "production_verified"),
                      ("e2e_evidence", "e2e_accepted")):
        if dv.get(key):
            rung = name
        else:
            break
    return rung


def status(root: Path = ROOT, t: datetime | None = None) -> list[dict]:
    t = t or now()
    events = load_events(root)
    return [assess(a, events, t) for a in load_coord(root).get("assignments", []) if a.get("id")]


def claim_check(aid: str, worker: str, root: Path = ROOT) -> tuple[bool, str]:
    for a in load_coord(root).get("assignments", []):
        if a.get("id") == aid:
            if _owner(a) != worker:
                return False, f"{aid} is owned by {_owner(a)!r}, not {worker!r}: do not work on it"
            if str(a.get("state")) in ("integrated", "done", "superseded"):
                return False, f"{aid} is {a.get('state')}"
            return True, f"{aid} is yours"
    return False, f"no assignment {aid!r}"


def append_event(worker: str, aid: str | None, kind: str, sha: str | None = None,
                 note: str | None = None, root: Path = ROOT, t: datetime | None = None) -> dict:
    if kind not in EVENT_KINDS:
        raise SystemExit(f"unknown event {kind!r}; one of {EVENT_KINDS}")
    if aid and kind in ("start", "checkpoint", "review_requested"):
        ok, why = claim_check(aid, worker, root)
        if not ok:
            raise SystemExit("REFUSED: " + why)
    if kind in ("checkpoint", "review_requested") and not sha:
        raise SystemExit(f"{kind} needs --sha")
    e = {"at": iso(t or now()), "worker": worker, "assignment": aid, "event": kind}
    if sha:
        e["sha"] = sha
    if note:
        e["note"] = note[:500]
    f = root / "dispatch" / "events" / f"{worker}.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a") as fh:
        fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return e


def post(aid: str, ack_h: float = 3, cp_h: float = 8, root: Path = ROOT,
         t: datetime | None = None) -> dict:
    t = t or now()
    d = load_coord(root)
    for a in d["assignments"]:
        if a.get("id") == aid:
            a["dispatch"] = {"posted_at": iso(t), "ack_due_by": iso(t + timedelta(hours=ack_h)),
                             "checkpoint_due_by": iso(t + timedelta(hours=cp_h))}
            save_coord(d, root)
            return a
    raise SystemExit(f"no assignment {aid!r}")


def reassign(aid: str, new_owner: str, reason: str, root: Path = ROOT,
             t: datetime | None = None, force: bool = False,
             owner_approved: str | None = None) -> dict:
    """Moves work only with the owner's authorization (I-THREE-OPERATOR-STRUCTURE). `stale`
    tells the integrator what to REPORT, not what to take. `owner_approved` names the owner
    message or decision that authorizes this transfer, and is recorded with it."""
    t = t or now()
    if not owner_approved:
        raise SystemExit("REFUSED: reassignment needs the owner's authorization "
                         "(--owner-approved <decision or message>); report the stall instead")
    d = load_coord(root)
    events = load_events(root)
    for a in d["assignments"]:
        if a.get("id") == aid:
            s = assess(a, events, t)
            if not force and not s["safe_to_reassign"]:
                raise SystemExit(f"REFUSED: {aid} is not safe to reassign "
                                 f"(stage {s['stage']}, overdue {s['overdue']})")
            a.setdefault("ownership_history", []).append(
                {"at": iso(t), "from": _owner(a), "to": new_owner, "reason": reason,
                 "stage_at_transfer": s["stage"], "checkpoint_sha": s["checkpoint_sha"],
                 "owner_approved": owner_approved})
            a["owner"] = new_owner
            a["state"] = "in_progress"
            a["dispatch"] = {"posted_at": iso(t), "ack_due_by": iso(t + DEFAULT_ACK),
                             "checkpoint_due_by": iso(t + DEFAULT_CHECKPOINT)}
            save_coord(d, root)
            return a
    raise SystemExit(f"no assignment {aid!r}")


def git_push(root: Path, message: str, paths: list[str]) -> None:
    def run(*c):
        return subprocess.run(c, cwd=root, check=True, capture_output=True, text=True)
    run("git", "add", *paths)
    run("git", "commit", "-q", "-m", message)
    for delay in (0, 2, 4, 8, 16):
        time.sleep(delay)
        try:
            run("git", "pull", "-q", "--rebase", "origin", BRANCH)
            run("git", "push", "-q", "origin", f"HEAD:{BRANCH}")
            return
        except subprocess.CalledProcessError:
            continue
    raise SystemExit("push failed after retries")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="cross-session assignment dispatch over git")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.add_argument("--json", action="store_true")
    sub.add_parser("stale")
    e = sub.add_parser("event")
    e.add_argument("worker"); e.add_argument("assignment"); e.add_argument("kind")
    e.add_argument("--sha"); e.add_argument("--note"); e.add_argument("--push", action="store_true")
    c = sub.add_parser("claim-check"); c.add_argument("assignment"); c.add_argument("worker")
    po = sub.add_parser("post"); po.add_argument("assignment")
    po.add_argument("--ack-hours", type=float, default=3)
    po.add_argument("--checkpoint-hours", type=float, default=8)
    r = sub.add_parser("reassign"); r.add_argument("assignment"); r.add_argument("new_owner")
    r.add_argument("--reason", required=True); r.add_argument("--force", action="store_true")
    r.add_argument("--owner-approved", default=None)
    a = p.parse_args(argv)
    if a.cmd == "status":
        rows = status()
        if a.json:
            print(json.dumps(rows, indent=2))
        else:
            for x in rows:
                flag = "  OVERDUE: " + "; ".join(x["overdue"]) if x["overdue"] else ""
                print(f"{x['id']:<27} {x['owner'][:16]:<16} P{x['priority'] or '-'} "
                      f"{x['stage']:<17} {x['delivery']:<19} seen={x['worker_last_seen'] or '-'}{flag}")
        return 0
    if a.cmd == "stale":
        rows = [x for x in status() if x["overdue"]]
        for x in rows:
            print(json.dumps(x))
        return 1 if rows else 0
    if a.cmd == "claim-check":
        ok, why = claim_check(a.assignment, a.worker)
        print(why)
        return 0 if ok else 1
    if a.cmd == "event":
        aid = None if a.assignment == "-" else a.assignment
        ev = append_event(a.worker, aid, a.kind, a.sha, a.note)
        print(json.dumps(ev))
        if a.push:
            git_push(ROOT, f"dispatch: {a.worker} {a.kind} {aid or ''}".strip(),
                     [f"dispatch/events/{a.worker}.jsonl"])
        return 0
    if a.cmd == "post":
        print(json.dumps(post(a.assignment, a.ack_hours, a.checkpoint_hours)["dispatch"]))
        return 0
    if a.cmd == "reassign":
        rec = reassign(a.assignment, a.new_owner, a.reason, force=a.force,
                       owner_approved=a.owner_approved)
        print(json.dumps(rec["ownership_history"][-1]))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
