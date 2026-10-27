#!/usr/bin/env python3
"""F-153 / F-157: commit-signing truth for a release range, read from git (operator tooling).

F-153: "If signing is claimed, prove signatures are generated and independently verifiable;
%G?=N or empty key means unavailable." F-157: "Intentional unsigned commits are explicit in
release evidence when signing is required."

`audit(repo, base, head)` reads `%G? %GK` for every commit in `base..head` and reports:
  * `claimed`  -- whether this environment says it signs (commit.gpgsign / user.signingkey);
  * `status`   -- `verified` (every commit G), `unavailable` (no commit carries a signature and
                  no signing key is configured: the honest default here), `partial`, or
                  `claimed_but_unsigned` (signing is configured and a commit is N -- the claim
                  is false);
  * `unsigned` -- every commit that is not G, by sha and %G?, so release evidence lists them;
  * `allowed_signers` -- whether gpg.ssh.allowedSignersFile is set and readable, which is what
                  makes an SSH signature independently verifiable.
`ops/deploy_guard.py record` writes this into the release record. With
`BRAMBLELOOP_SIGNING_REQUIRED=1` a range with any non-G commit is refused there.
Never signs, never reads a private key, never pushes.

  python3 ops/signing_audit.py --base <sha> --head <sha> [--repo DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

GOOD = "G"
REQUIRED_VAR = "BRAMBLELOOP_SIGNING_REQUIRED"


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def _key_usable(key: str) -> bool:
    """An empty value, or a key path whose file is missing or empty, is no key (F-153)."""
    if not key:
        return False
    if key.startswith("key::") or key.startswith("ssh-"):
        return True
    p = Path(os.path.expanduser(key))
    if p.exists() or "/" in key:
        return p.is_file() and p.stat().st_size > 0
    return True                                   # a GPG key id


def audit(repo: Path, base: str | None, head: str, *, limit: int = 0) -> dict:
    rng = f"{base}..{head}" if base else head
    extra = [f"-n{limit}"] if limit else []
    lines = [ln for ln in _git(repo, "log", *extra, "--format=%H %G? %GK", rng).splitlines()
             if ln]
    commits = []
    for ln in lines:
        parts = ln.split(" ")
        commits.append({"sha": parts[0], "status": parts[1] if len(parts) > 1 else "N",
                        "key": parts[2] if len(parts) > 2 and parts[2] else None})
    raw_key = _git(repo, "config", "user.signingkey")
    key = _key_usable(raw_key)
    gpgsign = _git(repo, "config", "--bool", "commit.gpgsign") == "true"
    claimed = key and gpgsign
    unsigned = [{"sha": c["sha"], "status": c["status"]} for c in commits
                if c["status"] != GOOD]
    allowed = _git(repo, "config", "gpg.ssh.allowedSignersFile")
    allowed_ok = bool(allowed) and Path(os.path.expanduser(allowed)).is_file()
    if not commits:
        status = "empty_range"
    elif not unsigned:
        status = "verified"
    elif claimed:
        status = "claimed_but_unsigned"
    elif len(unsigned) == len(commits):
        status = "unavailable"
    else:
        status = "partial"
    return {"range": rng, "commits": len(commits), "claimed": claimed,
            "signing_key_configured": key,
            "signing_key_setting_present": bool(raw_key), "gpgsign": gpgsign, "status": status, "unsigned": unsigned,
            "allowed_signers": {"configured": bool(allowed), "readable": allowed_ok},
            "independently_verifiable": status == "verified" and allowed_ok,
            "why": {"verified": "every commit carries a good signature",
                    "unavailable": "no commit is signed and no usable signing key is configured: "
                                   "signing is unavailable here, and is not claimed",
                    "claimed_but_unsigned": "signing is configured but commits read %G? != G: "
                                            "the claim is false",
                    "partial": "some commits are signed and some are not",
                    "empty_range": "no commit in the range"}[status]}


def required(env=None) -> bool:
    e = env if env is not None else os.environ
    return str(e.get(REQUIRED_VAR) or "").strip() == "1"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="")
    ap.add_argument("--head", required=True)
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    a = ap.parse_args(argv)
    out = audit(Path(a.repo), a.base or None, a.head)
    print(json.dumps(out, indent=1))
    return 1 if (required() and out["unsigned"]) or out["status"] == "claimed_but_unsigned" else 0


if __name__ == "__main__":
    raise SystemExit(main())
