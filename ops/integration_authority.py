#!/usr/bin/env python3
"""F-711 Single Integration Authority -- one authoritative integration path, as a computation.

The requirement: "There is one authoritative integration path. External AI workers may propose,
implement or review isolated work but cannot independently redefine company state, merge
conflicting work or deploy outside granted authority."

The parts that already existed:
  * deploy: a push to the production branch passes `ops/deploy_guard.py` (F-461) and the
    owner's per-SHA approval; nothing here changes that door.
  * merge: `ops/integrate.py` is the merge queue (F-459/F-460) -- conflict refusal, the
    contract checklist, compare-and-swap on the local target, and it never pushes.

What was missing: nothing stopped a worker session from pushing its own merge straight onto
an integration branch (`claude/w4-INTEG*`), force-pushing one, or deleting one. The
integration branch is the company's candidate state; a worker that writes it has redefined
that state without the integrator. This module is the rule as a check, applied by the
pre-push hook through `deploy_guard.pre_push` to every ref being pushed:

  1. a ref that is not an integration branch is a worker's own lane: ALLOW (lanes are where
     isolated work is proposed, implemented and reviewed);
  2. an integration branch may be updated only by the integrator role
     (`BRAMBLELOOP_ROLE=integrator`, set by the integrator session, never by a lane);
  3. even the integrator may not delete an integration branch or rewrite its history: the
     pushed commit must descend from the commit the remote holds. A remote commit this
     checkout does not have cannot be shown to be an ancestor, so it is refused, not assumed.

It is a local guard (a determined worker can bypass a hook); its purpose is that no session
does it by accident or by belief. Read-only git only; no network.

  python3 ops/integration_authority.py decide < pre-push-lines   -> exit 0 ALLOW, 1 REFUSE
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROLE_ENV = "BRAMBLELOOP_ROLE"
INTEGRATOR = "integrator"
INTEGRATION_REF = re.compile(r"^refs/heads/claude/w4-INTEG[0-9A-Za-z-]*$")
ZERO = "0" * 40
REPO = Path(__file__).resolve().parents[1]


def is_integration_ref(ref: str) -> bool:
    return bool(INTEGRATION_REF.match(ref or ""))


def _descends(repo: Path, old: str, new: str) -> bool | None:
    """True/False when git can answer; None when `old` is not in this checkout."""
    have = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{old}^{{commit}}"],
                          capture_output=True)
    if have.returncode != 0:
        return None
    r = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", old, new],
                       capture_output=True)
    return r.returncode == 0


def decide_ref(local_ref: str, local_sha: str, remote_ref: str, remote_sha: str, *,
               env: dict | None = None, repo: Path = REPO) -> dict:
    env = os.environ if env is None else env
    if not is_integration_ref(remote_ref):
        return {"remote_ref": remote_ref, "verdict": "ALLOW", "authority": "lane"}
    reasons = []
    role = (env.get(ROLE_ENV) or "").strip()
    if role != INTEGRATOR:
        reasons.append(f"{remote_ref} is an integration branch: only the integrator "
                       f"({ROLE_ENV}={INTEGRATOR}) updates it; a worker proposes through "
                       "its own lane and ops/integrate.py (role seen: "
                       f"{role or 'none'})")
    if local_sha == ZERO:
        reasons.append("deleting an integration branch redefines company state; refused")
    elif remote_sha != ZERO:
        d = _descends(repo, remote_sha, local_sha)
        if d is None:
            reasons.append(f"the remote holds {remote_sha[:12]}, which this checkout does not "
                           "have; fetch first -- a fast-forward cannot be shown")
        elif not d:
            reasons.append("not a fast-forward: the push would rewrite integrated history")
    return {"remote_ref": remote_ref, "verdict": "REFUSE" if reasons else "ALLOW",
            "authority": "integration", "reasons": reasons}


def decide(lines, *, env: dict | None = None, repo: Path = REPO) -> dict:
    out = []
    for raw in lines:
        parts = raw.split()
        if len(parts) == 4:
            out.append(decide_ref(*parts, env=env, repo=repo))
    refused = [d for d in out if d["verdict"] == "REFUSE"]
    return {"verdict": "REFUSE" if refused else "ALLOW", "decisions": out}


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "decide":
        res = decide(sys.stdin.read().splitlines())
        print(json.dumps(res, indent=1))
        return 0 if res["verdict"] == "ALLOW" else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
