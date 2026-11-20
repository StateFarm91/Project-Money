#!/usr/bin/env python3
"""Helpers for .github/workflows/certify-and-promote.yml (ENG-AUTOPROMOTE).

The workflow moves the release loop (full suite -> `deploy_guard.py record` -> `deploy.sh`) onto
GitHub Actions so releases keep flowing with zero Claude usage. This module holds the two
decisions the workflow needs that are not already the guard's. It decides nothing the guard
decides: descent, release proof and the rollback rehearsal stay in `ops/deploy_guard.py`,
reached only through `ops/deploy.sh`.

  python3 ops/autopromote.py backup [--max-age-hours 24] [--wait 1200]
      Pre-deploy backup gate. Exit 0 = a verified backup exists (BACKUP OK), 1 = REFUSE.
  python3 ops/autopromote.py release-subject --sha <sha>
      The commit subject for the release-record commit, read from RELEASE_<sha>.json.
  python3 ops/autopromote.py history-append --sha <sha> --evidence "<text>"
      Append a commit production is observed running to DEPLOYED_HISTORY.json (idempotent).

THE BACKUP RULE, EXPLICITLY (ops/ROLLBACK_RUNBOOK.md, "Pre-release database backup"):

  The Railway `db-backup` service runs one dump-and-restore check each time it is deployed and
  prints `BK RESULT OK <path>` only when the dump restored. Actions can reach Railway only with
  an owner-issued project token in the GitHub secret RAILWAY_TOKEN (sent as the
  `Project-Access-Token` header; never printed, never written).

  1. RAILWAY_TOKEN absent  -> REFUSE. A backup is required and nothing can be triggered. The
     "a recent backup is good enough" exception cannot apply either: the only place the last
     `BK RESULT OK` can be read is the db-backup deploy log, which also needs the token.
     There is no unauthenticated path and no override.
  2. RAILWAY_TOKEN present -> redeploy db-backup, wait (default 20 min) for its new deployment
     to log `BK RESULT OK`. Seen -> BACKUP OK. The new run logs `BK RESULT FAIL`, or its
     deployment ends FAILED/CRASHED without OK -> REFUSE (a failed backup is never covered by
     an older one: something is wrong with the backup right now).
  3. RAILWAY_TOKEN present but the trigger or the wait did not produce a verdict (API error,
     timeout) -> fall back to the newest `BK RESULT OK` in the db-backup logs: accepted only
     if it is newer than --max-age-hours (default 24, the runbook's own limit). Otherwise
     REFUSE.

Read-only except the one db-backup redeploy in step 2. Never touches the app service.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HISTORY = REPO / "brambleloop" / "release" / "DEPLOYED_HISTORY.json"
RAILWAY_API = "https://backboard.railway.com/graphql/v2"
TOKEN_VAR = "RAILWAY_TOKEN"
# Railway ids are identifiers, not secrets (project brambleloop, environment production).
ENVIRONMENT_ID = os.environ.get("RAILWAY_ENVIRONMENT_ID", "d618b2fe-70ec-4541-852f-0b656c2eedaf")
BACKUP_SERVICE_ID = os.environ.get("RAILWAY_BACKUP_SERVICE_ID",
                                   "4dcbeb0b-e6d5-4aa6-a47e-67e26fc1c7dc")
OK_LINE = re.compile(r"\bBK RESULT OK\b(.*)")
FAIL_LINE = re.compile(r"\bBK RESULT (?!OK\b)(\S+)")
_SHA = re.compile(r"^[0-9a-f]{40}$")
TERMINAL_BAD = {"FAILED", "CRASHED", "REMOVED", "SKIPPED"}


def parse_ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def scan_logs(lines: list[dict]) -> dict:
    """{'ok': (ts, text) | None, 'fail': text | None} for one deployment's log lines."""
    ok = fail = None
    for ln in lines or []:
        msg = str(ln.get("message") or "")
        m = OK_LINE.search(msg)
        if m:
            ts = parse_ts(ln.get("timestamp"))
            if ok is None or (ts and (ok[0] is None or ts > ok[0])):
                ok = (ts, msg.strip())
        elif FAIL_LINE.search(msg):
            fail = msg.strip()
    return {"ok": ok, "fail": fail}


class Railway:
    """Minimal GraphQL client for the db-backup service. The token is held, never shown."""

    def __init__(self, token: str, post=None, environment_id: str = ENVIRONMENT_ID,
                 service_id: str = BACKUP_SERVICE_ID):
        self._token, self._post = token, post or self._urlopen
        self.env, self.svc = environment_id, service_id

    def _urlopen(self, body: dict) -> dict:
        import urllib.request

        req = urllib.request.Request(RAILWAY_API, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Project-Access-Token": self._token})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed https URL
            return json.loads(r.read().decode())

    def q(self, query: str, variables: dict) -> dict:
        out = self._post({"query": query, "variables": variables})
        if out.get("errors"):
            msgs = "; ".join(str(e.get("message"))[:200] for e in out["errors"])
            raise RuntimeError(f"Railway API error: {msgs}")
        return out.get("data") or {}

    def deployments(self, first: int = 10) -> list[dict]:
        d = self.q("query($s:String!,$e:String!,$n:Int!){deployments(first:$n,input:"
                   "{serviceId:$s,environmentId:$e}){edges{node{id status createdAt}}}}",
                   {"s": self.svc, "e": self.env, "n": first})
        return [e["node"] for e in ((d.get("deployments") or {}).get("edges") or [])]

    def logs(self, deployment_id: str) -> list[dict]:
        d = self.q("query($d:String!){deploymentLogs(deploymentId:$d,limit:5000)"
                   "{message timestamp}}", {"d": deployment_id})
        return d.get("deploymentLogs") or []

    def redeploy(self) -> None:
        self.q("mutation($s:String!,$e:String!){serviceInstanceRedeploy("
               "serviceId:$s,environmentId:$e)}", {"s": self.svc, "e": self.env})


def latest_ok(rw: Railway, first: int = 10) -> tuple[dt.datetime | None, str] | None:
    """The newest `BK RESULT OK` across recent db-backup deployments, or None."""
    best = None
    for dep in rw.deployments(first):
        ok = scan_logs(rw.logs(dep["id"]))["ok"]
        if ok and (best is None or (ok[0] and (best[0] is None or ok[0] > best[0]))):
            best = ok
    return best


def trigger_and_wait(rw: Railway, *, wait: float, interval: float = 20.0,
                     clock=time.monotonic, sleep=time.sleep) -> dict:
    """Redeploy db-backup and wait for its new deployment's verdict.

    {'verdict': 'OK'|'FAIL'|'UNKNOWN', ...}. FAIL is a backup that ran and failed; UNKNOWN is
    no verdict (API trouble, timeout)."""
    try:
        before = {d["id"] for d in rw.deployments(5)}
        rw.redeploy()
    except Exception as exc:  # noqa: BLE001 - no verdict; caller falls back to freshness
        return {"verdict": "UNKNOWN", "why": f"could not trigger db-backup: {exc}"[:300]}
    start, new_id, status = clock(), None, None
    while True:
        try:
            if new_id is None:
                fresh = [d for d in rw.deployments(5) if d["id"] not in before]
                if fresh:
                    new_id = fresh[0]["id"]
            if new_id is not None:
                status = next((d.get("status") for d in rw.deployments(5)
                               if d["id"] == new_id), status)
                found = scan_logs(rw.logs(new_id))
                if found["ok"]:
                    return {"verdict": "OK", "deployment": new_id, "line": found["ok"][1]}
                if found["fail"]:
                    return {"verdict": "FAIL", "deployment": new_id, "line": found["fail"]}
                if status in TERMINAL_BAD:
                    return {"verdict": "FAIL", "deployment": new_id,
                            "line": f"deployment ended {status} without BK RESULT OK"}
        except Exception as exc:  # noqa: BLE001 - keep polling until the deadline
            last_err = str(exc)[:200]
        else:
            last_err = None
        if clock() - start >= wait:
            return {"verdict": "UNKNOWN", "deployment": new_id,
                    "why": f"no BK RESULT after {wait:.0f}s"
                           + (f" (last error: {last_err})" if last_err else "")}
        sleep(interval)


def decide(token: str | None, *, max_age_hours: float, wait: float,
           railway_factory=Railway, now=None, **kw) -> dict:
    """The backup gate. Returns {'ok': bool, 'verdict': ..., 'why': ...}."""
    if not (token or "").strip():
        return {"ok": False, "verdict": "REFUSE",
                "why": f"{TOKEN_VAR} is not set: a pre-deploy backup is required and cannot be "
                       "triggered, and the last BK RESULT OK cannot be read either (the "
                       "db-backup log needs the same token). Add the secret "
                       "(OWNER_ACTIONS_AUTOPROMOTE.md) or take the backup by hand per "
                       "ops/ROLLBACK_RUNBOOK.md and dispatch again."}
    rw = railway_factory(token.strip())
    run = trigger_and_wait(rw, wait=wait, **kw)
    if run["verdict"] == "OK":
        return {"ok": True, "verdict": "BACKUP OK", "source": "triggered", **run}
    if run["verdict"] == "FAIL":
        return {"ok": False, "verdict": "REFUSE", "source": "triggered",
                "why": f"the triggered backup failed: {run.get('line')}", **run}
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        last = latest_ok(rw)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "verdict": "REFUSE", "trigger": run,
                "why": f"no backup verdict ({run.get('why')}) and the db-backup logs are "
                       f"unreadable ({str(exc)[:200]})"}
    if last is None or last[0] is None:
        return {"ok": False, "verdict": "REFUSE", "trigger": run,
                "why": f"no backup verdict ({run.get('why')}) and no dated BK RESULT OK in the "
                       "recent db-backup logs"}
    age_h = (now - last[0]).total_seconds() / 3600
    if 0 <= age_h <= max_age_hours:
        return {"ok": True, "verdict": "BACKUP OK", "source": "recent", "trigger": run,
                "line": last[1], "at": last[0].isoformat(), "age_hours": round(age_h, 2)}
    return {"ok": False, "verdict": "REFUSE", "trigger": run, "line": last[1],
            "age_hours": round(age_h, 2),
            "why": f"no backup verdict ({run.get('why')}) and the newest BK RESULT OK is "
                   f"{age_h:.1f} h old (limit {max_age_hours} h)"}


def history_append(sha: str, evidence: str, *, path: Path = HISTORY, observed: str = "") -> dict:
    """Append `sha` (a commit production reported running) to DEPLOYED_HISTORY; idempotent.

    Only an observed deploy is ever appended (the file's own rule: never edited to make a
    rollback pass). The caller passes production's own /api/status answer."""
    if not _SHA.match(sha or ""):
        return {"ok": False, "why": f"need a full 40-hex sha, got {sha!r}"}
    if len((evidence or "").strip()) < 10:
        return {"ok": False, "why": "evidence is required"}
    doc = json.loads(path.read_text())
    if any(e.get("sha") == sha for e in doc.get("deployed", [])):
        return {"ok": True, "changed": False, "sha": sha}
    doc.setdefault("deployed", []).append({
        "sha": sha,
        "observed": observed or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "evidence": evidence.strip()})
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return {"ok": True, "changed": True, "sha": sha}


_TOTAL = re.compile(r"^TOTAL PASSING: (\d+) ; suites failing: (\d+)\s*$", re.M)


def release_subject(sha: str, *, release_dir: Path = HISTORY.parent) -> str:
    """Commit subject for the release-record commit, from the tracked record (not memory)."""
    rec = json.loads((release_dir / f"RELEASE_{sha}.json").read_text())
    suite = json.loads((release_dir / rec["suite_record"]["path"]).read_text())
    totals = _TOTAL.findall((release_dir / rec["suite_log"]["path"]).read_text(errors="replace"))
    passing, failing = totals[-1] if totals else ("?", "?")
    return (f"Release record for {sha[:8]} (full suite {suite.get('run_id')}, {passing} passing, "
            f"{failing} failing, {suite.get('tree')}, release-eligible; certify-and-promote)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--max-age-hours", type=float,
                   default=float(os.environ.get("BACKUP_MAX_AGE_HOURS", "24")))
    b.add_argument("--wait", type=float, default=float(os.environ.get("BACKUP_WAIT_S", "1200")))
    h = sub.add_parser("history-append")
    h.add_argument("--sha", required=True)
    h.add_argument("--evidence", required=True)
    h.add_argument("--file", default=str(HISTORY))
    rs = sub.add_parser("release-subject")
    rs.add_argument("--sha", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "release-subject":
        print(release_subject(a.sha))
        return 0
    if a.cmd == "backup":
        out = decide(os.environ.get(TOKEN_VAR), max_age_hours=a.max_age_hours, wait=a.wait)
        print(json.dumps(out, sort_keys=True, default=str))
        print(f"autopromote backup: {out['verdict']}"
              + ("" if out["ok"] else f" -- {out['why']}"), file=sys.stderr)
        return 0 if out["ok"] else 1
    out = history_append(a.sha, a.evidence, path=Path(a.file))
    print(json.dumps(out, sort_keys=True))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
