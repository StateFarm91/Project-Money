#!/usr/bin/env python3
"""The ops reliability-incident ledger: observer defects that cannot be closed by saying so (F-350).

Usage:
  python3 ops/incidents.py list [--all]
  python3 ops/incidents.py open <kind> <signature> <summary...>
  python3 ops/incidents.py close <id|signature> --root-cause TEXT \
        --prevention-test tests/test_x.py::test_name --fix-commit <sha>

WHY. The build's worst losses were not model spend; they were observer defects -- a finished
suite nobody re-read for 47 minutes, a waiter that matched itself and never ended, a lane
reported as progressing that had died, two sessions doing the same work. Until this file they
lived as prose in `board.py` / `registry.py` docstrings, and `waiter.py waste` could only set a
flag. A flag is closed by forgetting it.

THE RULE. An entry is opened with a kind and a signature (idempotent while open). It is closed
only with all three of:
  root_cause       what actually caused it, in words (not "fixed", not "flaky");
  prevention_test  `tests/<file>.py::<test function>` that EXISTS in brambleloop/tests -- the
                   test that would have caught it, so recurrence is a red suite, not a memory;
  fix_commit       a commit that EXISTS in this repository.
Anything missing or unverifiable is a refusal, and the entry stays open.

STORAGE. Append-only JSON lines (`open` / `restate` / `close` events) in
`ops/RELIABILITY_INCIDENTS.jsonl`, committed with the checkout: a reliability history that
lived in `/tmp` would be the defect it records. `RELIABILITY_LEDGER` overrides the path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
REPO = _HERE.parent
LEDGER = Path(os.environ.get("RELIABILITY_LEDGER") or _HERE / "RELIABILITY_INCIDENTS.jsonl")
TESTS_DIR = REPO / "brambleloop" / "tests"

KINDS = ("false_progress", "hidden_completion", "duplicate_work", "launch_delay",
         "material_delay", "observer_stall")
MIN_ROOT_CAUSE = 20
_TEST_REF = re.compile(r"^(tests/[A-Za-z0-9_./-]+\.py)::([A-Za-z_][A-Za-z0-9_]*)$")


class Refused(ValueError):
    """An open or close the ledger will not record, with the reason."""


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Ledger:
    def __init__(self, path: Path | str = LEDGER, *, repo: Path = REPO,
                 tests_dir: Path = TESTS_DIR, clock=_utc):
        self.path = Path(path)
        self.repo, self.tests_dir, self.clock = Path(repo), Path(tests_dir), clock

    # -- storage --------------------------------------------------------------------------
    def _events(self) -> list[dict]:
        try:
            text = self.path.read_text()
        except OSError:
            return []
        out = []
        for line in text.splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def _append(self, event: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")

    def entries(self) -> list[dict]:
        """Every entry, folded from its events, oldest first."""
        by_id: dict[int, dict] = {}
        for ev in self._events():
            iid = ev.get("id")
            if ev.get("event") == "open":
                by_id[iid] = {k: v for k, v in ev.items() if k != "event"} | {
                    "status": "open", "reports": 1}
            elif iid in by_id and ev.get("event") == "restate":
                by_id[iid]["reports"] += 1
                by_id[iid]["last_seen_utc"] = ev.get("at_utc")
            elif iid in by_id and ev.get("event") == "close":
                by_id[iid].update({k: ev.get(k) for k in (
                    "root_cause", "prevention_test", "fix_commit")})
                by_id[iid]["closed_utc"] = ev.get("at_utc")
                by_id[iid]["status"] = "closed"
        return [by_id[k] for k in sorted(by_id)]

    def open_entries(self) -> list[dict]:
        return [e for e in self.entries() if e["status"] == "open"]

    # -- verbs ----------------------------------------------------------------------------
    def open(self, kind: str, signature: str, summary: str, *, evidence: dict | None = None,
             source: str = "operator") -> dict:
        """Open one entry, or restate the open one with this signature. Never duplicates."""
        if kind not in KINDS:
            raise Refused(f"kind {kind!r} is not one of {KINDS}")
        if not str(signature).strip() or not str(summary).strip():
            raise Refused("signature and summary are required")
        for e in self.open_entries():
            if e["signature"] == signature:
                self._append({"event": "restate", "id": e["id"], "at_utc": self.clock()})
                return {"opened": False, "restated": True, "id": e["id"]}
        iid = max([e["id"] for e in self.entries()] or [0]) + 1
        self._append({"event": "open", "id": iid, "kind": kind, "signature": signature,
                      "summary": str(summary)[:500], "evidence": evidence or {},
                      "source": source, "opened_utc": self.clock()})
        return {"opened": True, "restated": False, "id": iid}

    def _find(self, ref) -> dict:
        for e in self.open_entries():
            if str(e["id"]) == str(ref) or e["signature"] == ref:
                return e
        raise Refused(f"no open reliability incident {ref!r}")

    def _test_exists(self, ref: str) -> str | None:
        m = _TEST_REF.match(ref or "")
        if not m:
            return "prevention_test must be `tests/<file>.py::<test function>`"
        path = self.tests_dir.parent / m.group(1)
        try:
            text = path.read_text()
        except OSError:
            return f"prevention_test file {m.group(1)} does not exist"
        if not re.search(rf"^\s*def {re.escape(m.group(2))}\(", text, re.M):
            return f"{m.group(1)} defines no test function {m.group(2)}"
        return None

    def _commit_exists(self, sha: str) -> str | None:
        if not re.fullmatch(r"[0-9a-fA-F]{7,40}", sha or ""):
            return "fix_commit must be a commit hash"
        r = subprocess.run(["git", "-C", str(self.repo), "cat-file", "-e", f"{sha}^{{commit}}"],
                           capture_output=True, text=True)
        return None if r.returncode == 0 else f"fix_commit {sha} is not a commit in this repository"

    def close(self, ref, *, root_cause: str, prevention_test: str, fix_commit: str) -> dict:
        """Close only with a root cause, an existing prevention test and an existing fix commit."""
        entry = self._find(ref)
        problems = []
        if len(str(root_cause or "").strip()) < MIN_ROOT_CAUSE:
            problems.append(f"root_cause must say what caused it (at least {MIN_ROOT_CAUSE} "
                            "characters)")
        why = self._test_exists(prevention_test)
        if why:
            problems.append(why)
        why = self._commit_exists(fix_commit)
        if why:
            problems.append(why)
        if problems:
            raise Refused(f"incident {entry['id']} stays open: " + "; ".join(problems))
        self._append({"event": "close", "id": entry["id"], "at_utc": self.clock(),
                      "root_cause": str(root_cause).strip(),
                      "prevention_test": prevention_test, "fix_commit": fix_commit})
        return {"closed": True, "id": entry["id"]}


def board_lines(ledger: Ledger | None = None, waste: dict | None = None) -> list[str]:
    """Lines for the lease/board print: open reliability incidents and unledgered waste."""
    ledger = ledger or Ledger()
    out = []
    rows = ledger.open_entries()
    if rows:
        out.append(f"{len(rows)} open RELIABILITY INCIDENT(S) (close only with root cause, "
                   "prevention test, fix commit):")
        for e in rows:
            out.append(f"  #{e['id']} [{e['kind']}] {e['signature']}: {e['summary']}"[:160])
    if waste and waste.get("reliability_incidents"):
        out.append(f"time waste: {waste.get('idle_s_total', 0) / 60:.0f} min idle in "
                   f"{waste.get('days')} days; {len(waste['reliability_incidents'])} "
                   "material-delay incident(s) (`python3 ops/waiter.py waste`)")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--all", action="store_true")
    op = sub.add_parser("open")
    op.add_argument("kind", choices=KINDS)
    op.add_argument("signature")
    op.add_argument("summary", nargs="+")
    cl = sub.add_parser("close")
    cl.add_argument("ref")
    cl.add_argument("--root-cause", required=True)
    cl.add_argument("--prevention-test", required=True)
    cl.add_argument("--fix-commit", required=True)
    a = ap.parse_args(argv)
    led = Ledger()
    try:
        if a.cmd == "list":
            rows = led.entries() if a.all else led.open_entries()
            print(json.dumps(rows, indent=2, sort_keys=True))
            return 1 if led.open_entries() else 0
        if a.cmd == "open":
            print(json.dumps(led.open(a.kind, a.signature, " ".join(a.summary)), sort_keys=True))
            return 0
        print(json.dumps(led.close(a.ref, root_cause=a.root_cause,
                                   prevention_test=a.prevention_test,
                                   fix_commit=a.fix_commit), sort_keys=True))
        return 0
    except Refused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
