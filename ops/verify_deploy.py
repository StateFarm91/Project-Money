#!/usr/bin/env python3
"""After a push to the production branch, wait until production runs the pushed commit (RELENG).

A push to the production branch is the deploy only if the host notices it. On 2026-10-11 the
push of 0417f35 (13:34:43Z, a fast-forward from fcb982d) created no Railway deployment at all;
it was found by hand and deployed manually at 13:58. `ops/deploy.sh` used to stop at
`git push`, so "pushed" was silently being read as "deployed". This closes that gap: it polls
production `/health` `build.commit` until it equals the pushed sha, and says plainly when it
never does.

  python3 ops/verify_deploy.py <sha> [--timeout 900] [--interval 15] [--url URL]

Exit codes:
  0  production reports <sha> (`build.known` true)            -> DEPLOYED
  3  timed out; production still reports another commit         -> NO_DEPLOY (the 2026-10-11 case)
  4  timed out; production never answered /health with a commit -> UNVERIFIED
  2  usage error

Read-only GETs; never deploys, never retries a push, never calls Railway. What to do on 3/4 is
in `ops/ROLLBACK_RUNBOOK.md` ("A push that did not deploy").
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

PRODUCTION_URL = os.environ.get("BRAMBLELOOP_PRODUCTION_URL",
                                "https://brambleloop-os-production.up.railway.app")
DEFAULT_TIMEOUT = 900.0   # a cold Railpack build + healthcheck has taken ~100-110 s; 15 min is ample
DEFAULT_INTERVAL = 15.0
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _fetch_json(url: str) -> dict:
    import urllib.request

    with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310 - fixed https URL
        return json.loads(r.read().decode("utf-8"))


def read_commit(fetch, url: str) -> tuple[str | None, str]:
    """(commit, note): the commit /health says it runs, or (None, why it could not be read)."""
    try:
        body = fetch(url.rstrip("/") + "/health")
    except Exception as exc:  # noqa: BLE001 - mid-deploy 502s are expected, keep polling
        return None, f"/health unreadable ({type(exc).__name__})"
    build = (body or {}).get("build") or {}
    if not build.get("known") or not build.get("commit"):
        return None, "/health does not know its own commit"
    return str(build["commit"]), "ok"


def wait_for(sha: str, *, fetch=None, url: str = PRODUCTION_URL,
             timeout: float = DEFAULT_TIMEOUT, interval: float = DEFAULT_INTERVAL,
             clock=time.monotonic, sleep=time.sleep) -> dict:
    """Poll until production reports `sha` or `timeout` elapses. Returns a verdict dict."""
    fetch = fetch or _fetch_json
    start = clock()
    first = last = None
    note = "never polled"
    polls = 0
    while True:
        commit, note = read_commit(fetch, url)
        polls += 1
        if commit is not None:
            first = first or commit
            last = commit
            if commit == sha:
                return {"verdict": "DEPLOYED", "sha": sha, "polls": polls,
                        "seconds": round(clock() - start, 1)}
        if clock() - start >= timeout:
            break
        sleep(interval)
    waited = round(clock() - start, 1)
    if last is None:
        return {"verdict": "UNVERIFIED", "sha": sha, "polls": polls, "seconds": waited,
                "why": f"production never reported a commit: {note}"}
    return {"verdict": "NO_DEPLOY", "sha": sha, "polls": polls, "seconds": waited,
            "production_commit": last, "production_commit_at_start": first,
            "why": ("production still reports a different commit after the timeout: the host "
                    "most likely never started a deployment for the pushed commit (as on "
                    "2026-10-11), or its build/healthcheck failed")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sha")
    ap.add_argument("--timeout", type=float,
                    default=float(os.environ.get("DEPLOY_VERIFY_TIMEOUT", DEFAULT_TIMEOUT)))
    ap.add_argument("--interval", type=float,
                    default=float(os.environ.get("DEPLOY_VERIFY_INTERVAL", DEFAULT_INTERVAL)))
    ap.add_argument("--url", default=PRODUCTION_URL)
    a = ap.parse_args(argv)
    if not _SHA.match(a.sha):
        print(f"verify_deploy: need a full 40-hex sha, got {a.sha!r}", file=sys.stderr)
        return 2
    out = wait_for(a.sha, url=a.url, timeout=a.timeout, interval=a.interval)
    print(json.dumps(out, sort_keys=True), file=sys.stderr)
    if out["verdict"] == "DEPLOYED":
        print(f"verify_deploy: DEPLOYED {a.sha} (production /health build.commit matches)")
        return 0
    if out["verdict"] == "NO_DEPLOY":
        print(f"verify_deploy: NO DEPLOY for {a.sha} after {out['seconds']} s -- production "
              f"still reports {out['production_commit']}. The branch now holds a commit "
              "production is not running. Check the host's deployment list for this sha; "
              "if none exists, the push did not trigger a deployment (see "
              "ops/ROLLBACK_RUNBOOK.md, 'A push that did not deploy').", file=sys.stderr)
        return 3
    print(f"verify_deploy: UNVERIFIED {a.sha} after {out['seconds']} s -- {out['why']}",
          file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
