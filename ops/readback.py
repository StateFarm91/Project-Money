#!/usr/bin/env python3
"""F-144: the per-feature production readback gate, run after every deploy (W4-SMOKE).

"Tests pass locally" is not "the feature runs in production". Each launch-critical operational
feature below names the production endpoint and the field that proves it is live, the predicate
the value must meet, and the Final Master rows it evidences. After `ops/verify_deploy.py`
confirms production runs the pushed sha, `ops/deploy.sh` runs this; a feature whose readback
does not PASS is not done, and the deploy exits 5 saying which one.

  python3 ops/readback.py --sha <40-hex> [--url URL] [--json OUT]
  python3 ops/readback.py --evidence [--url URL] [--json OUT]

`--evidence` (W4-READBACK) reads the production evidence surface: the anonymous `/api/verify`
`evidence_checks`, and `GET /api/readback/evidence` with the read-only credential taken from
the environment variable BRAMBLELOOP_READBACK_TOKEN (never printed, never an argument). It
prints the evidence and judges each item PASS / FAIL / UNKNOWN; UNKNOWN (no token, an
unreadable section, a missing field) is never a pass.

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
    # W4-CLOSE6: features whose production failures no readback caught. GET /api/departments
    # answered 500 on b931d17 for hours (CLOSE5 F-487) while every row above read PASS.
    ("department health served", ["F-487"], "/api/departments", "@status", "200",
     lambda v, _s: v == 200),
    ("swarm runtime served", ["F-487"], "/api/swarm/runtime", "@status", "200",
     lambda v, _s: v == 200),
    ("model-credit funding packet served", ["F-871"], "/api/funding/packets", "packets",
     "a non-empty list", lambda v, _s: isinstance(v, list) and len(v) > 0),
    ("off-site archive configured", ["F-152"], "/api/offsite", "configured", "true",
     lambda v, _s: v is True),
    ("continuity proof passing", ["F-628"], "/api/continuity", "last_proof_ok", "true",
     lambda v, _s: v is True),
    ("Etsy credential usable", ["F-437"], "/api/etsy", "usable", "true",
     lambda v, _s: v is True),
)

# Where `ops/deploy.sh` writes each readback, and where the completion board reads it: a
# Final Master row the manifest names is not verified_complete unless the readback of the
# deployed commit passed for every feature that names it (F-144).
EVIDENCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "brambleloop",
                            "research", "final_build", "w4", "evidence_BOARD")


def evidence_path(sha: str, stamp: str) -> str:
    return os.path.normpath(os.path.join(EVIDENCE_DIR, f"prod_readback_{sha[:12]}_{stamp}.json"))


def rows_by_feature() -> dict[str, list[str]]:
    return {feature: list(rows) for feature, rows, *_ in MANIFEST}


def _fetch(url: str, headers: dict | None = None) -> tuple[int | None, object]:
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               **(headers or {})})
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
    import datetime as _dt

    return {"sha": sha, "url": url, "verdict": overall, "reachable": reachable,
            "read_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "features": items,
            "not_done": [i["feature"] for i in items if i["verdict"] != PASS]}


# ---- W4-READBACK: the production evidence surface -----------------------------------------

READBACK_TOKEN_VAR = "BRAMBLELOOP_READBACK_TOKEN"
EVIDENCE_ENDPOINT = "/api/readback/evidence"
EVIDENCE_CHECKS = ("publishing_halt_clear", "stale_artefacts_rebuilding",
                   "no_repeated_paid_call_in_24h", "weekly_jobs_completing")
# (item, evidence section, server judgement key or None)
EVIDENCE_ITEMS = (
    ("dead letters in 24 h by job type", "dead_letters_24h", "no_unexpected_dead_letters_in_24h"),
    ("publishing halt clear", "publishing_halt", "publishing_halt_clear"),
    ("stale artefacts rebuilding", "stale_artefact_rebuilds", "stale_artefacts_rebuilding"),
    ("repeated paid calls prevented", "paid_call_dedupe", "no_repeated_paid_call_in_24h"),
    ("weekly jobs completing", "weekly_jobs", "weekly_jobs_completing"),
    ("products progressing through certification", "certification_pipeline", None),
    ("autonomous company loop", "autonomy_loop", None),
)


def _judge_section(name: str, section, judged) -> tuple[str, str]:
    """(verdict, short reason). UNKNOWN whenever the evidence is absent or unreadable."""
    if not isinstance(section, dict):
        return UNKNOWN, "section missing"
    if section.get("readable") is not True:
        return UNKNOWN, f"unreadable ({section.get('error_class') or 'no reason given'})"
    if name == "certification_pipeline":
        outcomes = section.get("certify_outcomes_7d") or {}
        certified = (outcomes.get("gate.certified") or {}).get("count")
        if not isinstance(certified, int):
            return UNKNOWN, "no certification counts"
        return ((PASS if certified > 0 else FAIL),
                f"{certified} certified in 7 d; by stage {section.get('count_by_stage')}")
    if name == "autonomy_loop":
        stages = section.get("stages")
        if not isinstance(stages, list) or not stages:
            return UNKNOWN, "no stages"
        missing = [s.get("stage") for s in stages if not s.get("evidenced")]
        return ((PASS if not missing else FAIL),
                f"{len(stages) - len(missing)}/{len(stages)} stages show useful work"
                + (f"; none in {missing}" if missing else ""))
    if not isinstance(judged, bool):
        return UNKNOWN, "no server judgement"
    if name == "dead_letters_24h":
        types = [f"{g.get('job_type')}:{g.get('error_class')}x{g.get('count')}"
                 for g in section.get("by_type") or [] if not g.get("expected_refusal")]
        return (PASS if judged else FAIL), (f"unexpected: {types}" if types else "none unexpected")
    return (PASS if judged else FAIL), ""


def run_evidence(*, url: str = PRODUCTION_URL, fetch=None, env=None) -> dict:
    """Read and judge the evidence surface. The token is read here and never returned."""
    fetch = fetch or _fetch
    env = os.environ if env is None else env
    token = (env.get(READBACK_TOKEN_VAR) or "").strip()
    base = url.rstrip("/")
    items = []
    reachable = False

    try:
        code, body = fetch(base + "/api/verify")[:2]
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN
        code, body = None, None
        public_error = type(exc).__name__
    else:
        public_error = ""
    reachable = reachable or code is not None
    public = {c.get("check"): c.get("ok") for c in (body or {}).get("evidence_checks") or []
              if isinstance(c, dict)} if isinstance(body, dict) else {}
    for name in EVIDENCE_CHECKS:
        v = public.get(name)
        verdict = PASS if v is True else FAIL if v is False else UNKNOWN
        items.append({"item": f"/api/verify {name}", "verdict": verdict,
                      "detail": "" if v is not None else (public_error or "check not served")})

    evidence = None
    http = None
    why = ""
    if not token:
        why = f"{READBACK_TOKEN_VAR} is not set in this environment"
    else:
        try:
            http, evidence = fetch(base + EVIDENCE_ENDPOINT,
                                   {"Authorization": "Bearer " + token})[:2]
        except Exception as exc:  # noqa: BLE001
            why = f"unreachable ({type(exc).__name__})"
        else:
            reachable = reachable or http is not None
            if http != 200 or not isinstance(evidence, dict):
                why = f"HTTP {http}: refused or unavailable"
                evidence = None
    judged = (evidence or {}).get("server_judgement") or {}
    for item, section, key in EVIDENCE_ITEMS:
        if evidence is None:
            verdict, detail = UNKNOWN, why
        else:
            verdict, detail = _judge_section(section, evidence.get(section),
                                             judged.get(key) if key else None)
        items.append({"item": item, "section": section, "verdict": verdict, "detail": detail})
    verdicts = {i["verdict"] for i in items}
    overall = (UNKNOWN if not reachable else FAIL if FAIL in verdicts else
               UNKNOWN if UNKNOWN in verdicts else PASS)
    import datetime as _dt

    out = {"url": url, "verdict": overall, "reachable": reachable,
           "read_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "token_present": bool(token), "evidence_http": http,
           "items": items, "evidence": evidence}
    return _redact(out, token)


def _redact(value, token: str):
    """Defence in depth: the token never leaves this process, even if a server echoed it."""
    if not token:
        return value
    if isinstance(value, dict):
        return {_redact(k, token): _redact(v, token) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, token) for v in value]
    if isinstance(value, str) and token in value:
        return value.replace(token, "[redacted]")
    return value


def main_evidence(a) -> int:
    out = run_evidence(url=a.url)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
            f.write("\n")
    print(json.dumps(out["evidence"], indent=1, sort_keys=True))
    for i in out["items"]:
        print(f"{i['verdict']:7} {i['item']}" + (f" ({i['detail']})" if i["detail"] else ""),
              file=sys.stderr)
    if not out["reachable"]:
        print("readback --evidence: production unreachable; nothing verified", file=sys.stderr)
        return 4
    if out["verdict"] != PASS:
        n = {v: sum(1 for i in out["items"] if i["verdict"] == v) for v in (PASS, FAIL, UNKNOWN)}
        print(f"readback --evidence: {out['verdict']} (PASS {n[PASS]}, FAIL {n[FAIL]}, "
              f"UNKNOWN {n[UNKNOWN]}; UNKNOWN is not a pass)", file=sys.stderr)
        return 5
    print(f"readback --evidence: PASS ({len(out['items'])} items)", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sha", default="")
    ap.add_argument("--evidence", action="store_true",
                    help=f"read the evidence surface (token from ${READBACK_TOKEN_VAR})")
    ap.add_argument("--url", default=PRODUCTION_URL)
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    if a.evidence:
        return main_evidence(a)
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
