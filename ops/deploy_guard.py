#!/usr/bin/env python3
"""Refuse a production deploy that could overwrite newer verified state or is not proven (F-461).

Usage:
  python3 ops/deploy_guard.py check --candidate <rev> --deployed <sha>   -> exit 0 ALLOW, 1 REFUSE
  python3 ops/deploy_guard.py latest-suite [--sha <rev>] [--eligible]    -> the newest run record
  python3 ops/deploy_guard.py pre-push <remote> <url>  (stdin: git pre-push lines) -> 0 / 1

ON THE DEPLOY PATH (F-461, wired). Production deploys on a push to the production branch
(`PRODUCTION_BRANCH`; Railway builds it). Two doors lead there and both pass through `check`:

* `ops/hooks/pre-push` (installed by `ops/install_hooks.sh`, which sets `core.hooksPath`):
  git hands it every ref being pushed; any update to the production branch is checked and a
  REFUSE aborts the push. Pushes to any other branch are not deploys and pass untouched.
* `ops/deploy.sh`: the one sanctioned deploy command. It runs `check` on HEAD against the
  deployed commit and pushes to the production branch only on ALLOW.

The deployed commit comes from `--deployed`, else `BRAMBLELOOP_DEPLOYED_SHA` -- which the hook
and `ops/deploy.sh` fill from `ops/deployed_sha.py` (production's own `/api/status`,
`build.commit`, only when `build.known`). This module itself makes no network call. If nobody
says, the deployed commit is unknown and the verdict is REFUSE.

THIS SCRIPT NEVER DEPLOYS. It reads git and the suite run records and prints a verdict; the
integrator (the only role allowed to deploy) runs it and acts on the answer. It makes no network
call and starts no process other than read-only `git`. Deploy serialisation was a rule --
integrator-only deploys, departments GET-only in production -- and a rule is what a second
session racing the first does not know about. A guard is the rule as a computation.

TWO REFUSALS, BOTH COMPUTED

1. The candidate must be the deployed commit or a DESCENDANT of it. Seven workers develop in
   parallel on branches cut from different bases; deploying one of them whose history does not
   contain what production is running would silently roll production back -- overwrite a newer
   verified state with an older one. `git merge-base --is-ancestor <deployed> <candidate>`
   answers it. The deployed commit is an argument, read by the caller from production's own
   `/api/verify`; if it is unknown, or is not in this repository, descent cannot be established
   and the answer is REFUSE, not "probably fine". Unknown stays unknown.

2. The candidate must have a GREEN, RELEASE-ELIGIBLE full-suite record for that exact SHA:
   `run_tests.sh` writes one per run (F-345) and sets `release_eligible` only for a full,
   clean-tree, unmoved-HEAD, zero-failing run. The record is not believed on its own: its log
   must still exist, must name the same run and SHA in its header, and must carry the TOTAL line
   with `suites failing: 0` -- the job's own words, re-read, not the record's summary of them.
   Missing, red, filtered, dirty, or contradicted by its log: REFUSE.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRODUCTION_BRANCH = "claude/repository-setup-nc9x6o"
PRODUCTION_REF = f"refs/heads/{PRODUCTION_BRANCH}"
DEPLOYED_ENV = "BRAMBLELOOP_DEPLOYED_SHA"
ZERO = "0" * 40
RECORD_DIR = REPO / "brambleloop" / "artifacts" / "suite_runs"
_TOTAL = re.compile(r"^TOTAL PASSING: (\d+) ; suites failing: (\d+)\s*$", re.M)


def _git(repo: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def resolve(repo: Path, rev: str) -> str | None:
    if not rev:
        return None
    code, out = _git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    return out if code == 0 and out else None


def records(record_dir: Path = RECORD_DIR) -> list[dict]:
    """Every readable run record, newest first. An unreadable one is skipped, and counted."""
    out = []
    for p in sorted(Path(record_dir).glob("*.json")):
        try:
            rec = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        rec["_path"] = str(p)
        out.append(rec)
    out.sort(key=lambda r: (r.get("started_utc") or "", r.get("run_id") or ""), reverse=True)
    return out


def latest_suite(record_dir: Path = RECORD_DIR, *, sha: str | None = None,
                 eligible_only: bool = False) -> dict | None:
    """The newest run record, optionally for one SHA and/or release-eligible only."""
    for rec in records(record_dir):
        if sha and rec.get("git_sha") != sha:
            continue
        if eligible_only and not rec.get("release_eligible"):
            continue
        return rec
    return None


def _log_confirms(rec: dict, base: Path) -> str | None:
    """None if the record's own log backs it; otherwise why not."""
    raw = rec.get("log") or ""
    log = Path(raw) if Path(raw).is_absolute() else base / raw
    try:
        text = log.read_text(errors="replace")
    except OSError:
        return f"the run's log {raw!r} is gone, so the record cannot be re-derived"
    if f"RUN ID: {rec.get('run_id')}" not in text or f"GIT SHA: {rec.get('git_sha')}" not in text:
        return "the log does not name this run and SHA; record and log disagree"
    totals = _TOTAL.findall(text)
    if not totals:
        return "the log has no TOTAL line; the run did not finish"
    if int(totals[-1][1]) != 0:
        return f"the log says suites failing: {totals[-1][1]}"
    return None


def check(candidate: str, deployed: str | None, *, repo: Path = REPO,
          record_dir: Path = RECORD_DIR, log_base: Path | None = None) -> dict:
    reasons: list[str] = []
    cand = resolve(repo, candidate)
    if cand is None:
        reasons.append(f"candidate {candidate!r} is not a commit in this repository")

    dep = resolve(repo, deployed or "")
    if not deployed:
        reasons.append("deployed commit unknown: descent cannot be established (read it from "
                       "production /api/verify and pass --deployed)")
    elif dep is None:
        reasons.append(f"deployed commit {deployed!r} is not in this repository; fetch it "
                       "before deciding -- descent cannot be established")
    elif cand is not None:
        code, _ = _git(repo, "merge-base", "--is-ancestor", dep, cand)
        if code == 1:
            reasons.append(f"candidate {cand[:12]} is not a descendant of deployed {dep[:12]}: "
                           "deploying it would roll production back")
        elif code != 0:
            reasons.append("git could not compute ancestry; refusing rather than guessing")

    suite = None
    if cand is not None:
        suite = latest_suite(record_dir, sha=cand)
        if suite is None:
            reasons.append(f"no suite run record for {cand[:12]}: run REQUIRE_CLEAN=1 "
                           "./run_tests.sh on exactly this commit")
        else:
            eligible = latest_suite(record_dir, sha=cand, eligible_only=True)
            if eligible is None:
                reasons.append(
                    f"latest suite for {cand[:12]} is {suite.get('status')} "
                    f"(scope {suite.get('scope')}, tree {suite.get('tree')}, failing "
                    f"{suite.get('suites_failing')}): not release-eligible")
            else:
                suite = eligible
                why = _log_confirms(eligible, log_base or (repo / "brambleloop"))
                if why:
                    reasons.append(why)
    return {
        "verdict": "REFUSE" if reasons else "ALLOW",
        "candidate": cand, "deployed": dep,
        "suite_run": None if suite is None else {k: suite.get(k) for k in (
            "run_id", "status", "git_sha", "scope", "tree", "tests_passing",
            "suites_failing", "finished_utc", "log", "release_eligible")},
        "reasons": reasons,
        "note": "verdict only; this script never deploys (F-461)",
    }


def deployed_from(explicit: str | None = None, env: dict | None = None) -> tuple[str | None, str]:
    """The deployed commit the caller supplied: `--deployed`, else `BRAMBLELOOP_DEPLOYED_SHA`.

    This module never asks production itself (no network, by test). `ops/deployed_sha.py`
    reads production's `/api/status`; the hook and `ops/deploy.sh` run it and pass the answer
    in. Nothing supplied is unknown, and `check` refuses on unknown.
    """
    import os

    if explicit:
        return explicit, "argument"
    e = os.environ if env is None else env
    if e.get(DEPLOYED_ENV):
        return e[DEPLOYED_ENV], DEPLOYED_ENV
    return None, (f"deployed commit not supplied: pass --deployed or set {DEPLOYED_ENV} "
                  "(ops/deployed_sha.py reads it from production /api/status)")


def pre_push(lines, *, deployed: str | None = None, env: dict | None = None,
             repo: Path = REPO, record_dir: Path = RECORD_DIR, checker=None) -> dict:
    """Decide a `git push` from the lines git gives a pre-push hook.

    Each line is `<local ref> <local sha> <remote ref> <remote sha>`. Only updates to the
    production branch are deploys; each is run through `check` and any REFUSE refuses the
    push. Deleting the production branch is refused outright.
    """
    checker = checker or check
    decisions = []
    for raw in lines:
        parts = raw.split()
        if len(parts) != 4:
            continue
        local_ref, local_sha, remote_ref, _remote_sha = parts
        if remote_ref != PRODUCTION_REF:
            decisions.append({"remote_ref": remote_ref, "verdict": "NOT_A_DEPLOY"})
            continue
        if local_sha == ZERO:
            decisions.append({"remote_ref": remote_ref, "verdict": "REFUSE",
                              "reasons": ["deleting the production branch is not a deploy "
                                          "this guard can prove safe"]})
            continue
        dep, source = deployed_from(deployed, env)
        out = checker(local_sha, dep, repo=repo, record_dir=record_dir)
        out = {**out, "remote_ref": remote_ref, "local_ref": local_ref,
               "deployed_source": source}
        if dep is None:
            out["reasons"] = list(out.get("reasons") or []) + [source]
            out["verdict"] = "REFUSE"
        decisions.append(out)
    refused = [d for d in decisions if d["verdict"] == "REFUSE"]
    return {"verdict": "REFUSE" if refused else "ALLOW", "decisions": decisions,
            "production_ref": PRODUCTION_REF,
            "note": "verdict only; the push itself is git's (F-461)"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--candidate", default="HEAD")
    c.add_argument("--deployed", default="")
    c.add_argument("--records", default=str(RECORD_DIR))
    c.add_argument("--repo", default=str(REPO))
    pp = sub.add_parser("pre-push")
    pp.add_argument("remote", nargs="?", default="")
    pp.add_argument("url", nargs="?", default="")
    pp.add_argument("--deployed", default="")
    pp.add_argument("--records", default=str(RECORD_DIR))
    pp.add_argument("--repo", default=str(REPO))
    ls = sub.add_parser("latest-suite")
    ls.add_argument("--sha", default="")
    ls.add_argument("--eligible", action="store_true")
    ls.add_argument("--records", default=str(RECORD_DIR))
    a = ap.parse_args(argv)
    if a.cmd == "check":
        out = check(a.candidate, deployed_from(a.deployed or None)[0], repo=Path(a.repo),
                    record_dir=Path(a.records))
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0 if out["verdict"] == "ALLOW" else 1
    if a.cmd == "pre-push":
        out = pre_push(sys.stdin.read().splitlines(), deployed=a.deployed or None,
                       repo=Path(a.repo), record_dir=Path(a.records))
        print(json.dumps(out, indent=2, sort_keys=True), file=sys.stderr)
        if out["verdict"] != "ALLOW":
            print("deploy_guard: REFUSED push to the production branch (F-461); see reasons "
                  "above. Push to a work branch instead.", file=sys.stderr)
        return 0 if out["verdict"] == "ALLOW" else 1
    sha = resolve(REPO, a.sha) if a.sha else None
    rec = latest_suite(Path(a.records), sha=sha or (a.sha or None), eligible_only=a.eligible)
    print(json.dumps(rec, indent=2, sort_keys=True) if rec else "no matching suite run record")
    return 0 if rec else 1


if __name__ == "__main__":
    raise SystemExit(main())
