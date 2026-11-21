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

Exit codes: 0 every feature PASS; 10 every feature read back but some only WARN (degraded, a
success: ops/deploy.sh deploys on it); 5 any FAIL or UNKNOWN (UNKNOWN is never a pass); 4 production
unreachable; 2 usage. Read-only GETs; never deploys, never POSTs, never calls Railway.
A status-code readback (e.g. a gated route answers 401) proves the route exists and is gated
without needing the credential; an unknown path under the same prefix answers 404.

Operator-only reads (INTEG8, after SECPATCH made every unlisted GET operator-only): the rows on
`OPERATOR_ENDPOINTS` read a route an anonymous caller cannot. With the operator credential in
BRAMBLELOOP_OPS_TOKEN (sent as a bearer header to those routes only, never printed or written)
they are read like any other row. Without it they are NEEDS_OPERATOR -- not fetched, never a
pass -- so the report says which features still need an operator readback instead of reading
the anonymous 401 as a missing field (UNKNOWN) or a broken feature (FAIL).

W4-READBACK: when BRAMBLELOOP_READBACK_TOKEN is set, those rows are read instead from
`/api/readback/evidence` (`deploy_readback`: each route's status and only the row's projected
field), so the deploy readback does not need the full operator credential. The operator token
is the fallback when only it is set; with neither the rows stay NEEDS_OPERATOR.
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
NEEDS_OPERATOR = "NEEDS_OPERATOR"
# A degraded signal (review 6785727146 F1): not a pass, not a failure. A manifest row marked
# `WARN_ONLY` reads WARN where it would otherwise read FAIL.
WARN = "WARN"
WARN_ONLY = "warn"
# Review 6818959626 (E3 MED): WARN only when the route answered 200 AND carried the field
# with a false value. A crashing route (500), a refused one (401) or a missing field stays
# UNKNOWN -- a broken endpoint must never read as a merely degraded credential.
WARN_IF_READ = "warn_if_read"
# every feature read back, some WARN only: a success (ops/deploy.sh). Review 6791709875 nit 3:
# distinct from every code this script and ops/deploy.sh already use (deploy.sh's own 3 is
# "NO DEPLOY"; readback's 4 unreachable, 5 not done).
WARN_EXIT = 10


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
    ("worker 0 not held by a long handler", ["F-371"], "/api/verify",
     "checks[check=worker_handler_within_expected_time].ok",
     "true (false: a handler past 15 min -- alive but possibly hung)",
     lambda v, _s: v is True, WARN_ONLY),
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
    # WS5 E3: "usable" alone was true whenever the two variables were set (it read PASS for the
    # whole 403 period). The row now reads the server's judgement: a successful Etsy read in
    # the last 24 h, an openable OAuth grant, and every needed scope granted.
    # WARN_ONLY: an external credential state (an unpaid subscription, a revoked grant) is
    # reported honestly -- never PASS -- without blocking a code deploy (Main 6814167293).
    ("Etsy credential usable", ["F-437"], "/api/etsy", "credential.usable",
     "true (recent real read, OAuth grant openable, no scope missing)",
     lambda v, _s: v is True, WARN_IF_READ),
)

# SECPATCH made these GETs operator-only; their rows need the operator credential (above).
# test_w4_secpatch_public_surface asserts this set is exactly the manifest's operator-only
# endpoints, so a route moving either way fails a test rather than a deploy.
OPERATOR_ENDPOINTS = frozenset({"/api/departments", "/api/swarm/runtime", "/api/funding/packets",
                                "/api/offsite", "/api/continuity", "/api/etsy"})

# Where `ops/deploy.sh` writes each readback, and where the completion board reads it: a
# Final Master row the manifest names is not verified_complete unless the readback of the
# deployed commit passed for every feature that names it (F-144).
EVIDENCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "brambleloop",
                            "research", "final_build", "w4", "evidence_BOARD")


def evidence_path(sha: str, stamp: str) -> str:
    return os.path.normpath(os.path.join(EVIDENCE_DIR, f"prod_readback_{sha[:12]}_{stamp}.json"))


def rows_by_feature() -> dict[str, list[str]]:
    return {feature: list(rows) for feature, rows, *_ in MANIFEST}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """L4 (READBACK review): a bearer token is never carried to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise urllib.error.HTTPError(req.full_url, code, f"redirect refused: {code}", headers, fp)


def _token_url_ok(url: str) -> bool:
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    return parts.scheme == "https" or (parts.scheme == "http"
                                       and parts.hostname in ("localhost", "127.0.0.1"))


# eng/evidence-perf: GET /api/readback/evidence took 45-91 s in production and this client
# gave up at 60 s, so the readback read the evidence as UNKNOWN. The server is now bounded
# well under that; the client allows 120 s so a slow, cold or busy deploy is still read.
HTTP_TIMEOUT_S = 120


def _fetch(url: str, token: str | None = None) -> tuple[int | None, object]:
    headers = {"Accept": "application/json"}
    opener = urllib.request.build_opener()
    if token:
        if not _token_url_ok(url):
            raise SystemExit(f"refusing to send a token over a non-https URL: {url!r}")
        headers["Authorization"] = f"Bearer {token}"
        opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=HTTP_TIMEOUT_S) as r:  # noqa: S310 - https enforced when a token rides
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    try:
        return code, json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return code, None


def _from_evidence(body, endpoint: str) -> tuple[int | None, object]:
    """W4-READBACK: an operator row read from `/api/readback/evidence`'s `deploy_readback`
    section -- (the route's status, a body holding only the row's projected field). A list
    travels as its length only and is rebuilt as a list of that length, so a predicate on
    "a non-empty list" still applies and no element ever leaves the server."""
    row = ((body or {}).get("deploy_readback") or {}).get(endpoint) \
        if isinstance(body, dict) else None
    if not isinstance(row, dict) or not isinstance(row.get("status"), int):
        return None, None
    fields: dict = {}
    for k, v in (row.get("fields") or {}).items():
        if isinstance(v, dict) and isinstance(v.get("list_length"), int):
            v = [None] * v["list_length"]
        # WS5 E3: a dotted field ("credential.usable") is rebuilt nested, as `_dig` reads it.
        *parents, leaf = str(k).split(".")
        cur = fields
        for p in parents:
            cur = cur.setdefault(p, {}) if isinstance(cur.get(p, {}), dict) else {}
        cur[leaf] = v
    return row["status"], fields


def run(sha: str, *, url: str = PRODUCTION_URL, fetch=None, token: str | None = None,
        readback_token: str | None = None) -> dict:
    """The rows on OPERATOR_ENDPOINTS need a credential. In order of preference:

    * `readback_token` (BRAMBLELOOP_READBACK_TOKEN, W4-READBACK): the rows are read, projected,
      from `/api/readback/evidence`; the operator credential is not needed and not sent;
    * `token` (the operator credential): the routes themselves are read with it;
    * neither: NEEDS_OPERATOR, never a pass.

    `fetch(url)` reads a public route, `fetch(url, token)` an authenticated one."""
    fetch = fetch or _fetch
    cache: dict[str, tuple] = {}
    items = []
    reachable = False
    base = url.rstrip("/")
    for row in MANIFEST:
        feature, rows, endpoint, field, expected, pred = row[:6]
        bad = WARN if len(row) > 6 and row[6] in (WARN_ONLY, WARN_IF_READ) else FAIL
        strict = len(row) > 6 and row[6] == WARN_IF_READ
        operator = endpoint in OPERATOR_ENDPOINTS
        if operator and not token and not readback_token:
            items.append({"feature": feature, "rows": rows, "endpoint": endpoint,
                          "field": field, "expected": expected, "http": None, "value": None,
                          "verdict": NEEDS_OPERATOR,
                          "why": "operator-only route; no readback or operator credential "
                                 "was supplied"})
            continue
        if operator and readback_token:
            if EVIDENCE_ENDPOINT not in cache:
                try:
                    cache[EVIDENCE_ENDPOINT] = fetch(base + EVIDENCE_ENDPOINT, readback_token)
                except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN
                    cache[EVIDENCE_ENDPOINT] = (None, None, f"{type(exc).__name__}")
            ev = cache[EVIDENCE_ENDPOINT]
            if ev[0] is not None:
                reachable = True
            key = f"{EVIDENCE_ENDPOINT}#{endpoint}"
            cache[key] = (_from_evidence(ev[1], endpoint) if ev[0] == 200 else (None, None))
            got = cache[key]
            code, body = got[0], got[1]
            if code is None:
                verdict, value = UNKNOWN, None
            else:
                value = code if field == "@status" else _dig(body, field)
                verdict = ((bad if bad == WARN and not strict else UNKNOWN)
                           if value is None and field != "@status" else None)
                if verdict is None and strict and code != 200:
                    verdict = UNKNOWN
                if verdict is None:
                    try:
                        verdict = PASS if pred(value, sha) else bad
                    except Exception:  # noqa: BLE001
                        verdict = UNKNOWN
            items.append({"feature": feature, "rows": rows, "endpoint": endpoint,
                          "field": field, "expected": expected, "http": code,
                          "via": EVIDENCE_ENDPOINT,
                          "value": value if isinstance(value, (bool, int, str, type(None)))
                          else json.dumps(value)[:200], "verdict": verdict})
            continue
        if endpoint not in cache:
            try:
                cache[endpoint] = (fetch(base + endpoint, token) if operator
                                   else fetch(base + endpoint))
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
                # a warn-only row never escalates past WARN: an advisory a build does not
                # report yet is degraded evidence, not an unknown that forces containment.
                # A WARN_IF_READ row is the exception: a missing field is UNKNOWN.
                verdict = WARN if bad == WARN and not strict else UNKNOWN
            elif strict and code != 200:
                verdict = UNKNOWN
            else:
                try:
                    verdict = PASS if pred(value, sha) else bad
                except Exception:  # noqa: BLE001
                    verdict = UNKNOWN
        items.append({"feature": feature, "rows": rows, "endpoint": endpoint, "field": field,
                      "expected": expected, "http": code,
                      "value": value if isinstance(value, (bool, int, str, type(None)))
                      else json.dumps(value)[:200], "verdict": verdict})
    verdicts = {i["verdict"] for i in items}
    overall = (UNKNOWN if not reachable else FAIL if FAIL in verdicts else
               UNKNOWN if UNKNOWN in verdicts else
               NEEDS_OPERATOR if NEEDS_OPERATOR in verdicts else
               WARN if WARN in verdicts else PASS)
    import datetime as _dt

    return {"sha": sha, "url": url, "verdict": overall, "reachable": reachable,
            "read_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "features": items,
            # review 6789501427 LOW-1: a WARN row is degraded, not undone
            "not_done": [i["feature"] for i in items if i["verdict"] not in (PASS, WARN)],
            "warnings": [i["feature"] for i in items if i["verdict"] == WARN]}


# ---- W4-READBACK: the production evidence surface -----------------------------------------

READBACK_TOKEN_VAR = "BRAMBLELOOP_READBACK_TOKEN"
EVIDENCE_ENDPOINT = "/api/readback/evidence"
EVIDENCE_CHECKS = ("publishing_halt_clear", "stale_artefacts_rebuilding",
                   "no_repeated_paid_call_in_24h", "weekly_jobs_completing")
# The owner's research shops (`intel.scan_evidence.OWNER_SHOPS`, anchor included): eight
# until D-OWNER-NINTH-SHOP (2026-11-19) added ArtLoveDesing. This script is stdlib-only and
# cannot import the package, so the count is stated here and a test pins it to OWNER_SHOPS.
RESEARCH_SHOPS = 9
_NUMBER_WORDS = {8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
COMPETITOR_SCANS_ITEM = (f"competitor shops scanned "
                         f"({_NUMBER_WORDS.get(RESEARCH_SHOPS, str(RESEARCH_SHOPS))}-shop "
                         f"research network)")
# (item, evidence section, server judgement key or None)
EVIDENCE_ITEMS = (
    ("dead letters in 24 h by job type", "dead_letters_24h", "no_unexpected_dead_letters_in_24h"),
    ("listing-package releases recorded", "listing_package_releases",
     "no_unrecorded_listing_releases_in_24h"),
    ("publishing halt clear", "publishing_halt", "publishing_halt_clear"),
    ("stale artefacts rebuilding", "stale_artefact_rebuilds", "stale_artefacts_rebuilding"),
    ("repeated paid calls prevented", "paid_call_dedupe", "no_repeated_paid_call_in_24h"),
    ("weekly jobs completing", "weekly_jobs", "weekly_jobs_completing"),
    ("products progressing through certification", "certification_pipeline", None),
    ("autonomous company loop", "autonomy_loop", None),
    ("Etsy category resolvable (crochet offered by the chosen node)", "etsy_taxonomy", None),
    # WS2 R1: the research shops' scan state. Advisory: a WARN never fails the readback or a
    # deploy -- an Etsy refusal (or one seed shop gone) is reported, not turned into a FAIL.
    (COMPETITOR_SCANS_ITEM, "competitor_scans", None),
    # ENG watchlist-cadence: what the scheduler is holding back. Advisory, like the scans: a
    # suspension or a silent mandatory shop WARNs (the P1 incident is the escalation).
    ("scheduler holds and silent mandatory shops", "scheduler", None),
    # ENG-FIRSTLIST: which Launch-0 release could become the first Etsy draft. Advisory: no
    # candidate yet is the honest state before launch, so it WARNs and never fails a deploy.
    ("first Etsy draft candidates (Launch-0)", "first_listing_readiness", None),
    # ENG-MOTIF-BACKLOG: paid renders blocked by a refused motif check, and their recovery.
    # Advisory: renders still waiting (or a backlog never measured) WARN; never a deploy FAIL.
    ("paid renders recovered from refused motif checks", "motif_backlog_recovery", None),
    # ENG-VISUAL: the listing-image and PDF factory, counted from persisted rows. Advisory:
    # before launch nothing has a verified gallery or a read-back draft, so it WARNs and
    # never fails a deploy; an unreadable part is UNKNOWN, never 0.
    ("listing-image and PDF factory (visual pipeline)", "visual_pipeline", None),
    # ENG-LEARN: image + pattern learning loops. Advisory: a loop without enough evidence
    # reads UNKNOWN in its own section and WARNs here; it never fails a deploy.
    ("learning loops (image + pattern) progress", "learning", None),
    # ENG-DAILY: the daily production ledger. Advisory: a zero-output stage or an UNKNOWN
    # stage WARNs and never fails a deploy; an unreadable section is UNKNOWN, never a PASS.
    ("daily production ledger (14 UTC days)", "daily_ledger", None),
    # ENG-DEMAND-SUPPLY: the engines held concepts wait for, ranked by demand. Advisory: a
    # concept waiting for an engine WARNs with the top of the list; never a deploy FAIL.
    ("engine demand (build this engine next)", "engine_demand", None),
    # ENG-AUTOCODER: the in-production coding team. Advisory: OFF (the default) or blocked on
    # the owner's GitHub token WARNs and never fails a deploy; unreadable is UNKNOWN.
    ("autocoder (change requests -> reviewed auto/* branches)", "autocoder", None),
)


_VOCAB = re.compile(r"^[a-z][a-z0-9_.:@-]{0,79}$")


def _why_not_candidates(releases) -> str:
    """eng/publish-unhalt U5: the WARN named a count and no cause, so the operator could not
    tell a halt from a missing gallery from an unread policy without the raw JSON. Built only
    from the fixed-vocabulary fields the server already emits (section names, blocker source
    identifiers, booleans); anything else is dropped, never echoed."""
    if not isinstance(releases, list) or not releases:
        return ""
    parts, tally = [], {}
    for r in releases[:30]:
        if not isinstance(r, dict):
            continue
        why = []
        if r.get("on_etsy") is True:
            why.append("already_on_etsy")
        secs = r.get("publication_sections") or {}
        why += sorted(f"{k}={v}" for k, v in secs.items()
                      if isinstance(k, str) and v in ("FAIL", "UNKNOWN") and _VOCAB.match(k))
        if r.get("package_state") != "ready_for_owner_review":
            why.append(f"package={r.get('package_state') or 'none'}")
        elif r.get("package_is_current_release") is not True:
            why.append("package_not_current_release")
        why += [f"blocker:{s}" for s in (r.get("package_blocker_sources") or [])
                if isinstance(s, str) and _VOCAB.match(s)]
        for w in why:
            tally[w] = tally.get(w, 0) + 1
        rel = str(r.get("release") or "?")
        if _VOCAB.match(rel):
            parts.append(f"{rel}: {', '.join(why[:8]) or 'no reason emitted'}")
    common = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    return ("; most common: " + ", ".join(f"{k} x{n}" for k, n in common)
            + " | " + " | ".join(parts[:7])) if parts else ""


def _judge_section(name: str, section, judged) -> tuple[str, str]:
    """(verdict, short reason). UNKNOWN whenever the evidence is absent or unreadable."""
    if name == "scheduler":
        if not isinstance(section, dict) or section.get("readable") is not True:
            return WARN, ("section missing" if not isinstance(section, dict) else
                          f"unreadable ({section.get('error_class') or 'no reason given'})")
        held = [f"{r.get('job_type')}:{r.get('kind')}"
                for r in section.get("suspended_job_types") or []]
        silent = [f"{r.get('alias')}:{r.get('cause')}"
                  for r in section.get("unattempted_mandatory_shops") or []]
        blocked = [r.get("department") for r in section.get("blocked_departments") or []]
        if silent or held or blocked:
            return WARN, (f"silent mandatory shops {silent}; held {held}; "
                          f"blocked departments {blocked}")
        return PASS, "no job type held, no department blocked, every mandatory shop attempted"
    if name == "first_listing_readiness":
        if not isinstance(section, dict) or section.get("readable") is not True:
            return WARN, ("section missing" if not isinstance(section, dict) else
                          f"unreadable ({section.get('error_class') or 'no reason given'})")
        cands = section.get("draft_candidates") or []
        if cands:
            return PASS, f"draft candidates {cands}"
        return WARN, (f"no draft candidate among {section.get('certified_with_listing')} "
                      f"certified Launch-0 releases with a listing"
                      + _why_not_candidates(section.get("releases")))
    if name == "motif_backlog_recovery":
        if not isinstance(section, dict) or section.get("readable") is not True:
            return WARN, ("section missing" if not isinstance(section, dict) else
                          f"unreadable ({section.get('error_class') or 'no reason given'})")
        counts = section.get("counts") or {}
        if section.get("swept") is not True:
            return WARN, "the recovery sweep has never run: the backlog is UNKNOWN, not 0"
        waiting = [counts.get("renders_still_queued_budget"),
                   counts.get("renders_queued_retry"),
                   counts.get("renders_awaiting_first_recheck")]
        if not all(isinstance(w, int) for w in waiting):
            return WARN, f"counts unreadable: {counts}"
        summary = (f"found {counts.get('renders_found_blocked')}, passed "
                   f"{counts.get('renders_passed')}, failed {counts.get('renders_failed')}, "
                   f"queued(budget) {waiting[0]}, galleries completed "
                   f"{counts.get('products_gallery_completed')}, packages ready "
                   f"{counts.get('listing_packages_became_ready')}")
        return (WARN if sum(waiting) else PASS), summary
    if name == "visual_pipeline":
        return _judge_visual(section)
    if name == "learning":
        if not isinstance(section, dict) or section.get("readable") is not True:
            return WARN, ("section missing" if not isinstance(section, dict) else
                          f"unreadable ({section.get('error_class') or 'no reason given'})")
        return PASS, "learning loops readable"
    if name == "daily_ledger":
        return _judge_daily(section)
    if name == "engine_demand":
        if not isinstance(section, dict) or section.get("readable") is not True:
            return WARN, ("section missing" if not isinstance(section, dict) else
                          f"unreadable ({section.get('error_class') or 'no reason given'})")
        top = [f"{e.get('rank')}. {e.get('engine')} x{e.get('count')} "
               f"(demand {e.get('top_demand')})" for e in section.get("top_engines") or []]
        n = section.get("engines_needed")
        if not isinstance(n, int):
            return WARN, "engine count unreadable"
        return ((WARN if n else PASS),
                (f"{n} engine(s) needed: {top}" if n else "no concept waits for an engine"))
    if name == "autocoder":
        return _judge_autocoder(section)
    if name == "competitor_scans" and (not isinstance(section, dict)
                                       or section.get("readable") is not True):
        # WS2 R1: advisory -- a build without the section, or one that cannot read it, warns.
        return WARN, ("section missing" if not isinstance(section, dict) else
                      f"unreadable ({section.get('error_class') or 'no reason given'})")
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
    if name == "etsy_taxonomy":
        if section.get("refreshed") is not True:
            return UNKNOWN, "the taxonomy has never been refreshed"
        offers = {c: v.get("schema_offers_crochet")
                  for c, v in (section.get("category_choices") or {}).items()}
        if not offers:
            return UNKNOWN, "no category choices on the refresh row"
        no = sorted(c for c, v in offers.items() if v is False)
        unk = sorted(c for c, v in offers.items() if v is None)
        if no:
            return FAIL, f"the chosen node offers no 'Crochet' value for {no}"
        if unk:
            return UNKNOWN, f"no stored schema for {unk}"
        return PASS, f"refreshed {section.get('refreshed_at')}; {len(offers)} categories"
    if name == "competitor_scans":
        shops = section.get("shops")
        if not isinstance(shops, list) or not shops:
            return WARN, "no shops reported"
        credential = section.get("credential")
        unscanned = [f"{r.get('alias')}:{r.get('state')}"
                     + (f"/{r.get('failure_class')}" if r.get("failure_class") else "")
                     for r in shops if r.get("state") != "scanned"]
        # Review 6816970157 M2: a scanned shop whose newest success is stale is not current.
        # Review 6819096414 LOW-1: recomputed from the age and the limit as well as the
        # flag, and an unreadable age or limit is stale -- never trusted as current.
        def _stale(r):
            age, limit = r.get("success_age_hours"), r.get("stale_after_hours")
            numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool)
                          for v in (age, limit))
            return bool(r.get("stale")) or not numeric or age > limit

        unscanned += [f"{r.get('alias')}:stale({r.get('success_age_hours')}h>"
                      f"{r.get('stale_after_hours')}h)"
                      for r in shops if r.get("state") == "scanned" and _stale(r)]
        # D-OWNER-NINTH-SHOP: a server reporting fewer research shops than the owner named has
        # dropped one; that is never a PASS, however well the others scanned.
        missing = ([f"reported {len(shops)} shops, expected {RESEARCH_SHOPS}"]
                   if len(shops) != RESEARCH_SHOPS else [])
        if credential != "usable":
            return WARN, (f"Etsy read credential {credential}; {len(shops) - len(unscanned)}/"
                          f"{len(shops)} scanned" + (f"; {missing}" if missing else ""))
        if unscanned or missing:
            return WARN, (f"{len(shops) - len(unscanned)}/{len(shops)} scanned; "
                          f"{unscanned + missing}")
        return PASS, f"{len(shops)}/{len(shops)} scanned"
    if not isinstance(judged, bool):
        return UNKNOWN, "no server judgement"
    if name == "dead_letters_24h":
        types = [f"{g.get('job_type')}:{g.get('error_class')}x{g.get('count')}"
                 for g in section.get("by_type") or [] if not g.get("expected_refusal")]
        return (PASS if judged else FAIL), (f"unexpected: {types}" if types else "none unexpected")
    if name == "listing_package_releases":
        bad = [f"{g.get('release')}:{g.get('error_class')}x{g.get('final_attempt_failures')}"
               for g in section.get("by_release") or [] if g.get("final_attempt_failures")]
        return (PASS if judged else FAIL), (
            f"{section.get('degraded_sweeps')} degraded sweeps; unrecorded: {bad}"
            if not judged else "every release recorded")
    return (PASS if judged else FAIL), ""


def _judge_daily(section) -> tuple[str, str]:
    """ENG-DAILY: advisory, WARN or PASS when readable; UNKNOWN when missing or unreadable.

    PASS only when every stage's reading today is known and none is zero-output; a stage
    still "not yet due" is not a failure. Never PASS on UNKNOWN."""
    if not isinstance(section, dict):
        return UNKNOWN, "section missing"
    if section.get("readable") is not True:
        return UNKNOWN, f"unreadable ({section.get('error_class') or 'no reason given'})"
    status = section.get("stage_status_today")
    if not isinstance(status, dict) or not status:
        return WARN, "no stage readings today"
    zero = sorted(k for k, v in status.items() if v == "zero_output")
    unknown = sorted(k for k, v in status.items()
                     if v not in ("zero_output", "not_yet_due", "producing"))
    if zero or unknown:
        return WARN, ((f"zero output: {zero}" if zero else "")
                      + ("; " if zero and unknown else "")
                      + (f"unknown: {unknown}" if unknown else ""))
    due = sorted(k for k, v in status.items() if v == "not_yet_due")
    return PASS, (f"{len(status)} stages read; not yet due: {due}" if due
                  else f"{len(status)} stages producing")


def _judge_autocoder(section) -> tuple[str, str]:
    """ENG-AUTOCODER: advisory. PASS only when enabled and unblocked; OFF or blocked WARNs
    with the counts; missing or unreadable is UNKNOWN, never a PASS."""
    if not isinstance(section, dict):
        return UNKNOWN, "section missing"
    if section.get("readable") is not True:
        return UNKNOWN, f"unreadable ({section.get('error_class') or 'no reason given'})"
    counts = section.get("counts") or {}
    summary = ", ".join(f"{k} {counts.get(k)}" for k in (
        "open", "coding", "submitted", "certified", "deployed", "refused"))
    if section.get("enabled") is not True:
        return WARN, f"kill switch OFF; {summary}"
    if section.get("blocked") is not False:
        return WARN, f"enabled but blocked ({section.get('blockers')} blockers); {summary}"
    if section.get("within_month_ceiling") is False:
        return WARN, f"monthly sub-ceiling reached; {summary}"
    return PASS, f"enabled; {summary}; last run {section.get('last_run_outcome')}"


def _vp_n(part, key):
    """A count from a visual-pipeline part, or "UNKNOWN" -- an unreadable part is never 0."""
    if not isinstance(part, dict) or part.get("readable") is False:
        return "UNKNOWN"
    v = part.get(key)
    return v if isinstance(v, int) and not isinstance(v, bool) else "UNKNOWN"


def _judge_visual(section) -> tuple[str, str]:
    """ENG-VISUAL: advisory. PASS only when at least one draft was read back in full (both
    PDFs and every image); anything less WARNs with the exact numbers."""
    if not isinstance(section, dict) or section.get("readable") is not True:
        return WARN, ("section missing" if not isinstance(section, dict) else
                      f"unreadable ({section.get('error_class') or 'no reason given'})")
    pdf, gal = section.get("certified_pdfs"), section.get("galleries")
    img, idn = section.get("images"), section.get("laura_identity_checks")
    pkg, dr = section.get("listing_packages"), section.get("etsy_drafts")
    rec = (section.get("recovered_images") or {}).get("count", "UNKNOWN")
    meth = section.get("laura_identity_method") or {}
    why = (f"certified PDFs US+UK {_vp_n(pdf, 'with_us_and_uk_pdf_hashes')}/"
           f"{_vp_n(pdf, 'certified_releases')}; galleries valid {_vp_n(gal, 'valid')} "
           f"blocked {_vp_n(gal, 'blocked')} {(gal or {}).get('blocked_reasons_grouped') or {}}; "
           f"images verified {_vp_n(img, 'verified')} failed {_vp_n(img, 'failed')} "
           f"unmeasurable {_vp_n(img, 'unmeasurable')}; identity run {_vp_n(idn, 'run')} "
           f"passed {_vp_n(idn, 'passed')} failed {_vp_n(idn, 'failed')} not run "
           f"{_vp_n(idn, 'not_run')} (production qualified "
           f"{meth.get('production_qualified')}); recovered {rec}; listing-ready "
           f"{_vp_n(pkg, 'listing_ready')}; Etsy drafts {_vp_n(dr, 'drafts')} fully read "
           f"back {_vp_n(dr, 'fully_read_back')}")
    full = _vp_n(dr, "fully_read_back")
    return (PASS if isinstance(full, int) and full > 0 else WARN), why


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
            http, evidence = fetch(base + EVIDENCE_ENDPOINT, token)[:2]
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
    # Review 6816970157 L1: as `run`, a WARN row reads WARN overall (still not a failure).
    overall = (UNKNOWN if not reachable else FAIL if FAIL in verdicts else
               UNKNOWN if UNKNOWN in verdicts else WARN if WARN in verdicts else PASS)
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
    if out["verdict"] == WARN:
        warned = [i["item"] for i in out["items"] if i["verdict"] == WARN]
        print(f"readback --evidence: WARN ({len(out['items'])} items; degraded, not a "
              f"failure: {warned})", file=sys.stderr)
        return WARN_EXIT
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
    out = run(a.sha, url=a.url, token=os.environ.get("BRAMBLELOOP_OPS_TOKEN") or None,
              readback_token=(os.environ.get(READBACK_TOKEN_VAR) or "").strip() or None)
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
    if out["verdict"] == WARN:
        # review 6789501427 LOW-1: every feature read back; some rows are degraded (a long
        # worker-0 handler, or a build that predates an advisory check). A success, with its
        # own code so a caller can still tell it apart from a clean PASS.
        print(f"readback: WARN ({len(out['features'])} features read back on {a.sha[:12]}; "
              f"degraded, not a failure: {out['warnings']})")
        return WARN_EXIT
    if out["verdict"] != PASS:
        print(f"readback: {out['verdict']}: not done in production: {out['not_done']}",
              file=sys.stderr)
        return 5
    print(f"readback: PASS ({len(out['features'])} features read back on {a.sha[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
