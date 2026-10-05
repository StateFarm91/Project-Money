#!/usr/bin/env python3
"""Print the commit production says it is running, or exit 1 (F-461).

Kept out of `ops/deploy_guard.py` on purpose: the guard makes no network call (a test reads
it for one). This is the one read the deploy path needs from production -- `/api/status`
`build.commit`, believed only when `build.known` -- and the hook and `ops/deploy.sh` pass its
answer to the guard as `BRAMBLELOOP_DEPLOYED_SHA`. Read-only GET; never deploys.

  python3 ops/deployed_sha.py            -> prints the sha, exit 0; or a reason on stderr, exit 1
"""
from __future__ import annotations

import json
import os
import sys

PRODUCTION_URL = os.environ.get("BRAMBLELOOP_PRODUCTION_URL",
                                "https://brambleloop-os-production.up.railway.app")
DEPLOYED_ENV = "BRAMBLELOOP_DEPLOYED_SHA"


def _fetch_json(url: str) -> dict:
    import urllib.request

    with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310 - fixed https URL
        return json.loads(r.read().decode("utf-8"))


def deployed_commit(*, env: dict | None = None, fetch=None,
                    url: str = PRODUCTION_URL) -> tuple[str | None, str]:
    """(sha, source) or (None, why). An env value wins; otherwise production is asked."""
    e = os.environ if env is None else env
    if e.get(DEPLOYED_ENV):
        return e[DEPLOYED_ENV], DEPLOYED_ENV
    fetch = fetch or _fetch_json
    try:
        status = fetch(url.rstrip("/") + "/api/status")
    except Exception as exc:  # noqa: BLE001 - unreachable production is unknown, not ALLOW
        return None, f"production /api/status unreadable ({type(exc).__name__})"
    build = (status or {}).get("build") or {}
    if not build.get("known") or not build.get("commit"):
        return None, "production /api/status does not know its own commit"
    return str(build["commit"]), "production /api/status"


def main() -> int:
    sha, source = deployed_commit()
    if sha is None:
        print(f"deployed commit unknown: {source}", file=sys.stderr)
        return 1
    print(sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
