"""The `owned_surface.probe` producer: the evidence the `owned_surfaces` gate reads (W4-B2GATES).

`build2.executor._owned_surface_probed` opens the gate on the latest `owned_surface.probe`
audit row recording `ok: true` -- a demonstrated capability, not a variable being set (C-38).
Until now nothing in the codebase wrote that row, so the gate could never open: the owner
could open a site or a Pinterest account and the seven rows parked on it (#4 #10 #246 #247
#248 #251 #255) would have stayed parked for ever, which is the "gate reads evidence nobody
produces" failure `ops.capability_probes` was written to end.

What counts as ok, per surface (each probe is a read; nothing is published, posted or spent):

* **site** (`BRAMBLELOOP_SITE_URL`): the site serves the owner-published verification file
  `/.well-known/brambleloop-surface.txt` and its body contains `VERIFY_MARKER`. Serving a file
  somebody put there is the publish path of a static site working end to end; a URL that
  resolves to a parking page, an error document or someone else's site does not contain it.
* **pinterest** (`PINTEREST_ACCESS_TOKEN`): the token reads at least one board through the
  official API (`GET /v5/boards`). That is the destination a pin is published to, reachable
  with this credential; no pin is created (that would publish publicly), and the record says so.

Nothing configured -> `ok: false` with the reason, so the gate stays closed and says why.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

PROBE_ACTION = "owned_surface.probe"
SITE_VAR = "BRAMBLELOOP_SITE_URL"
PINTEREST_VAR = "PINTEREST_ACCESS_TOKEN"
VERIFY_PATH = "/.well-known/brambleloop-surface.txt"
VERIFY_MARKER = "brambleloop-owned-surface"
PINTEREST_BOARDS = "https://api.pinterest.com/v5/boards?page_size=1"
USER_AGENT = "BrambleloopStudio-surface-probe/1 (+owner-operated)"
TIMEOUT_S = 15
MAX_BYTES = 64 * 1024


def _default_fetch(url: str, headers: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # noqa: S310 - https/http only
            return int(r.status), r.read(MAX_BYTES)
    except urllib.error.HTTPError as exc:
        return int(exc.code), b""


def _site(url: str, fetch) -> dict:
    base = url.strip().rstrip("/")
    if not base.lower().startswith(("https://", "http://")):
        return {"surface": "site", "ok": False, "url": base,
                "reason": f"{SITE_VAR} is not an http(s) URL"}
    target = base + VERIFY_PATH
    try:
        status, body = fetch(target, None)
    except Exception as exc:  # noqa: BLE001 - unreachable is a reading, not a crash
        return {"surface": "site", "ok": False, "url": target,
                "reason": f"unreachable: {type(exc).__name__}"}
    found = VERIFY_MARKER.encode() in (body or b"")
    return {"surface": "site", "url": target, "status": status, "ok": status == 200 and found,
            "reason": ("" if status == 200 and found else
                       f"HTTP {status}" if status != 200 else
                       f"served, but the body does not contain {VERIFY_MARKER!r}"),
            "what_it_shows": "the site serves a file its owner published (static publish path)"}


def _pinterest(token: str, fetch) -> dict:
    try:
        status, body = fetch(PINTEREST_BOARDS, {"Authorization": f"Bearer {token}"})
    except Exception as exc:  # noqa: BLE001
        return {"surface": "pinterest", "ok": False,
                "reason": f"unreachable: {type(exc).__name__}"}
    boards = 0
    if status == 200:
        try:
            boards = len((json.loads(body or b"{}") or {}).get("items") or [])
        except ValueError:
            boards = 0
    return {"surface": "pinterest", "status": status, "boards_seen": boards,
            "ok": status == 200 and boards > 0,
            "reason": ("" if status == 200 and boards > 0 else
                       f"HTTP {status}" if status != 200 else
                       "the account has no board to publish a pin to"),
            "what_it_shows": "a board (the pin destination) is reachable with this token; "
                             "no pin was created"}


def probe(db, *, env: dict[str, str] | None = None, fetch=None,
          now: datetime | None = None) -> dict:
    """Probe every configured owned surface and write one `owned_surface.probe` row."""
    from ..core.models import AuditLog

    env = os.environ if env is None else env
    fetch = fetch or _default_fetch
    surfaces = []
    if (env.get(SITE_VAR) or "").strip():
        surfaces.append(_site(env[SITE_VAR], fetch))
    if (env.get(PINTEREST_VAR) or "").strip():
        surfaces.append(_pinterest(env[PINTEREST_VAR].strip(), fetch))
    ok = any(s["ok"] for s in surfaces)
    record = {"at": (now or datetime.now(timezone.utc)).isoformat(), "ok": ok,
              "surfaces": surfaces, "working": [s["surface"] for s in surfaces if s["ok"]],
              "reason": ("" if ok else
                         f"no owned surface configured ({SITE_VAR} / {PINTEREST_VAR})"
                         if not surfaces else
                         "; ".join(f"{s['surface']}: {s['reason']}" for s in surfaces))}
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=PROBE_ACTION,
                       artifact=",".join(x["surface"] for x in surfaces) or "none",
                       detail=record))
    return record
