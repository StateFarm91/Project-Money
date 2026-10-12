#!/usr/bin/env python3
"""F-144: the per-feature production readback gate, run after every deploy (W4-SMOKE).

"Tests pass locally" is not "the feature runs in production". Each launch-critical operational
feature below names the production endpoint and the field that proves it is live, the predicate
the value must meet, and the Final Master rows it evidences. After `ops/verify_deploy.py`
confirms production runs the pushed sha, `ops/deploy.sh` runs this; a feature whose readback
does not PASS is not done, and the deploy exits 5 saying which one.

  python3 ops/readback.py --sha <40-hex> [--url URL] [--json OUT]

Exit codes: 0 every feature PASS; 5 any FAIL or UNKNOWN (UNKNOWN is never a pass); 4 production
unreachable; 2 usage. Read-only GETs; never deploys, never POSTs, never calls Railway.
A status-code readback (e.g. a gated route answers 401) proves the route exists and is gated
without needing the credential; an unknown path under the same prefix answers 404.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

PRODUCTION_URL = os.environ.get("BRAMBLELOOP_PRODUCTION_URL",
                                "https://brambleloop-os-production.up.railway.app")
_SHA = re.compile(r"^[0-9a-f]{40}$")
PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"


def _dig(body, path: str):
    cur = body
    for part in path.split("."):
        if cur is None:
            return None
        m = re.fullmatch(r"(\w+)\[check=([\w.]+)\]", part)
        if m:
            cur = cur.get(m.group(1)) if isinstance(cur, dict) else None
            cur = next((c for c in cur or [] if isinstance(c, dict)
                        and c.get("check") == m.group(2)), None)
            continue
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


# (feature, rows, endpoint, field or "@status", expected description, predicate(value, sha))
MANIFEST = (
    ("release identity", ["F-144", "F-169"], "/health", "build",
     "build.known is true and build.commit is the deployed sha",
     lambda v, sha: isinstance(v, dict) and v.get("known") is True and v.get("commit") == sha),
    ("boot guard proves the release record", ["F-169", "F-158"], "/api/status", "boot_guard",
     "enforced and ok", lambda v, _s: isinstance(v, dict) and v.get("enforced") is True
     and v.get("ok") is True),
    ("embedded worker alive", ["F-371", "F-880"], "/health", "runner.worker_alive",
     "true", lambda v, _s: v is True),
    ("shadow phase holds", ["F-172"], "/api/verify", "checks[check=phase_is_shadow].ok",
     "true", lambda v, _s: v is True),
    ("nothing published in shadow", ["F-172"], "/api/verify",
     "checks[check=nothing_published].ok", "true", lambda v, _s: v is True),
    ("publication refusals recorded", ["F-172"], "/api/verify",
     "checks[check=publication_was_actually_attempted_and_refused].ok", "true",
     lambda v, _s: v is True),
    ("no unexpected dead letters", ["F-171", "F-144"], "/api/verify",
     "checks[check=no_unexpected_dead_letters_in_24h].ok", "true", lambda v, _s: v is True),
    ("every agent has a cost ceiling", ["F-171"], "/api/verify",
     "checks[check=every_agent_has_a_cost_ceiling].ok", "true", lambda v, _s: v is True),
    ("smoke matrix (probes, continuity, cadences, queue, search)", ["F-171"],
     "/api/verify/smoke", "verdict", "PASS", lambda v, _s: v == "PASS"),
    ("Final Master launch gate served", ["F-840"], "/api/build", "final_master.launch_ready",
     "a boolean (the gate is computed, whatever its value)", lambda v, _s: isinstance(v, bool)),
    ("catalogue says nothing is published", ["F-172"], "/api/catalogue", "published",
     "false", lambda v, _s: v is False),
    ("launch packet route deployed and operator-gated", ["F-878"], "/api/launch/packet",
     "@status", "401 (route exists, credential required)", lambda v, _s: v == 401),
)


def _fetch(url: str) -> tuple[int | None, object]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed https URL
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    try:
        return code, json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return code, None


def run(sha: str, *, url: str = PRODUCTION_URL, fetch=None) -> dict:
    fetch = fetch or _fetch
    cache: dict[str, tuple] = {}
    items = []
    reachable = False
    for feature, rows, endpoint, field, expected, pred in MANIFEST:
        if endpoint not in cache:
            try:
                cache[endpoint] = fetch(url.rstrip("/") + endpoint)
            except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never a pass
                cache[endpoint] = (None, None, f"{type(exc).__name__}: {str(exc)[:120]}")
        got = cache[endpoint]
        code, body = got[0], got[1]
        if code is not None:
            reachable = True
        if code is None:
            verdict, value = UNKNOWN, None
        else:
            value = code if field == "@status" else _dig(body, field)
            if value is None and field != "@status":
                verdict = UNKNOWN
            else:
                try:
                    verdict = PASS if pred(value, sha) else FAIL
                except Exception:  # noqa: BLE001
                    verdict = UNKNOWN
        items.append({"feature": feature, "rows": rows, "endpoint": endpoint, "field": field,
                      "expected": expected, "http": code,
                      "value": value if isinstance(value, (bool, int, str, type(None)))
                      else json.dumps(value)[:200], "verdict": verdict})
    verdicts = {i["verdict"] for i in items}
    overall = (UNKNOWN if not reachable else FAIL if FAIL in verdicts else
               UNKNOWN if UNKNOWN in verdicts else PASS)
    return {"sha": sha, "url": url, "verdict": overall, "reachable": reachable,
            "features": items,
            "not_done": [i["feature"] for i in items if i["verdict"] != PASS]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sha", required=True)
    ap.add_argument("--url", default=PRODUCTION_URL)
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    if not _SHA.match(a.sha):
        print(f"readback: need a full 40-hex sha, got {a.sha!r}", file=sys.stderr)
        return 2
    out = run(a.sha, url=a.url)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
            f.write("\n")
    for i in out["features"]:
        print(f"{i['verdict']:7} {i['feature']} ({i['endpoint']} {i['field']} = "
              f"{i['value']!r}; expected {i['expected']})", file=sys.stderr)
    if not out["reachable"]:
        print("readback: production unreachable; nothing verified", file=sys.stderr)
        return 4
    if out["verdict"] != PASS:
        print(f"readback: {out['verdict']}: not done in production: {out['not_done']}",
              file=sys.stderr)
        return 5
    print(f"readback: PASS ({len(out['features'])} features read back on {a.sha[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
