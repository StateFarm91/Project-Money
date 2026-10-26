"""W4-SECPATCH (2026-10-26): nothing owner-only is served to an unauthenticated caller.

The defect, confirmed in production at 13:53Z: an unauthenticated GET of `/` returned the
whole owner inbox (each action's title, instructions, cost, minutes, consequence), incident
text, the model spend against its ceiling, job and timeline rows, gate/closure internals and
unpublished product slugs. The same content was on ~160 other public GETs
(`/api/owner-actions`, `/api/build`, `/api/incidents`, `/api/jobs`, `/api/spend-report`, ...),
because every GET not on `OPERATOR_GET_ROUTES` was public by default.

The fix: reads are default-deny too (`security.PUBLIC_GET_ROUTES` is an allow-list), `/` is a
page with no data, and the routes the deploy readback reads answer an unauthenticated caller
with an allow-listed projection (`security.PUBLIC_PROJECTIONS`).

A temp database is seeded with sentinel owner actions, an incident, spend, jobs and an
unpublished product. Then, with no cookie and no token:

1. every route the app registers -- enumerated, never a hand list -- either refuses or answers
   without any sentinel;
2. `/` is exactly the static public page (no counts, no embedded state, no script);
3. the static HTML/JS bundles (`/cc/` PWA shell, `/ops/teardown(.js)`, OpenAPI) carry none;
4. the public readback endpoints carry only their projected fields, and every field
   `ops/readback.py`, `ops/deployed_sha.py` and `ops/verify_deploy.py` read is still there;
5. with the operator credential the full views are unchanged (the operator loop still works).

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_w4_secpatch_public_surface.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REPO / "ops"))

_TMP = tempfile.mkdtemp(prefix="secpatch_")
DB_FILE = os.path.join(_TMP, "sp.db")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)
SHA = "0123456789abcdef0123456789abcdef01234567"
os.environ["BRAMBLELOOP_COMMIT"] = SHA


def _no_network(*_a, **_k):
    raise OSError("network refused by the secpatch harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    CostEntry, Incident, Job, Listing, OwnerAction, Product)

TOKEN = "s" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}

# Distinctive strings, one per kind of owner-only content the production fetch returned.
OA_KEY = "secpatch_sentinel_requirement_8812"
OA_TITLE = "SECPATCH-OA-TITLE-4417 rotate the sentinel credential"
OA_CONSEQUENCE = "SECPATCH-CONSEQUENCE-2290 the sentinel stays blocked"
OA_REASON = "SECPATCH-OA-REASON-6604"
INCIDENT_SIG = "secpatch-incident-signature-5531"
INCIDENT_TEXT = "SECPATCH-INCIDENT: shop security posture, the stored credential changed 6620"
JOB_TYPE = "secpatch.sentinel_job_7781"
JOB_ERROR = "SECPATCH-JOB-ERROR-3381"
SLUG = "secpatch-unpublished-slug-9077"
PRODUCT_TITLE = "SECPATCH Unpublished Product Title 1144"
SPEND = 61.2345
SENTINELS = (OA_KEY, OA_TITLE, OA_CONSEQUENCE, OA_REASON, INCIDENT_SIG, INCIDENT_TEXT, JOB_TYPE,
             JOB_ERROR, SLUG, PRODUCT_TITLE)
# Field names that carry spend, inbox, incident, job or gate content in the full views.
PRIVATE_KEYS = ("spent_this_month_cad", "monthly_ceiling_cad", "agent_opex_cad", "spend",
                "revenue", "owner_actions_open", "open_incidents", "approval_inbox", "gates",
                "queue", "dead_letters", "listings", "evidence", "readbacks", "boot_enqueues",
                "products", "certified_versions", "watchdog", "lanes", "record")

# What an anonymous caller may see of each public JSON read: exactly the fields the deploy
# path reads (ops/verify_deploy.py, ops/deployed_sha.py, ops/readback.py) plus liveness words.
# Written out here, independently of `security.PUBLIC_PROJECTIONS`, so widening that table is
# a test change somebody has to make on purpose.
PUBLIC_FIELDS = {
    "/health": {"status": True, "version": True, "db": True,
                "build": {"commit": True, "commit_short": True, "known": True},
                "runner": {"worker_alive": True}},
    "/api/status": {"version": True,
                    "build": {"commit": True, "commit_short": True, "known": True},
                    "boot_guard": {"enforced": True, "ok": True}},
    "/api/verify": {"ok": True, "checks": [{"check": True, "ok": True}]},
    "/api/verify/smoke": {"verdict": True, "as_of": True},
    "/api/build": {"final_master": {"launch_ready": True}},
    "/api/catalogue": {"published": True},
}

_STATE: dict = {}


def _is_public(path: str) -> bool:
    """Behavioural: what the gate actually lets through without a credential."""
    return not security.requires_operator("GET", path) and not security.owner_session_route(path)


def client() -> TestClient:
    if "c" in _STATE:
        return _STATE["c"]
    assert str(main.db.engine.url).endswith(DB_FILE), main.db.engine.url
    main.db.create_all()
    Registry(main.db).seed_defaults()
    with main.db.session() as s:
        s.add(OwnerAction(requirement_key=OA_KEY, action=OA_TITLE, reason=OA_REASON,
                          max_cost_cad=77.77, minutes=43, consequence_of_delay=OA_CONSEQUENCE,
                          blocks=OA_KEY))
        s.add(Incident(severity="P1", signature=INCIDENT_SIG, summary=INCIDENT_TEXT,
                       product_slug=SLUG, detail={"why": INCIDENT_TEXT}))
        s.add(Product(slug=SLUG, title=PRODUCT_TITLE, status="concept"))
        s.add(Listing(product_slug=SLUG, version="1.0.0", title=PRODUCT_TITLE,
                      description=PRODUCT_TITLE, tags=[SLUG], price_cad=9.0))
        s.add(Job(agent="coo", job_type=JOB_TYPE, inputs={"slug": SLUG},
                  last_error=JOB_ERROR))
        s.add(CostEntry(agent="coo", kind="llm", amount_cad=SPEND, provider="anthropic",
                        product_slug=SLUG, purpose="secpatch"))
        s.commit()
    _STATE["c"] = TestClient(main.app, raise_server_exceptions=False,
                             base_url="https://testserver")
    return _STATE["c"]


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def _leaks(text: str) -> list[str]:
    return [s for s in SENTINELS if s.lower() in text.lower()]


def _get_routes() -> list[str]:
    return sorted({p for p, methods, _ in security.iter_api_routes(main.app)
                   if "GET" in methods})


def _with_token(fn):
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        return fn()
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


def test_the_operator_view_really_holds_the_sentinels():
    """Non-vacuity: the seeded content is what the full views show, so its absence below is
    the gate working, not the seed missing."""
    c = client()

    def run():
        assert OA_TITLE in c.get("/api/owner-actions", headers=AUTH).text
        assert INCIDENT_TEXT in c.get("/api/incidents", headers=AUTH).text
        assert JOB_TYPE in c.get("/api/jobs", headers=AUTH).text
        assert SLUG in c.get("/api/catalogue", headers=AUTH).text
        status = c.get("/api/status", headers=AUTH).json()
        assert "spend" in status and status.get("open_incidents", 0) >= 1, sorted(status)
        page = c.get("/", headers=AUTH).text
        assert OA_TITLE in page or INCIDENT_TEXT in page or JOB_TYPE in page, page[:300]
    _with_token(run)


def test_every_route_without_a_credential_refuses_or_leaks_nothing():
    c = client()
    bad = []

    def sweep(token_set: bool):
        for path in _get_routes():
            r = c.get(_concrete(path))
            public = _is_public(path)
            if not public:
                want = ({401, 403} if token_set else {503})
                if security.owner_session_route(path):
                    # The Command Center's own session gate (untouched); its one public read
                    # (/api/cc/auth/status) says only whether a session exists.
                    want = {200, 401, 403, 503}
                if r.status_code not in want:
                    bad.append(f"{path}: {r.status_code} without a credential "
                               f"(token {'set' if token_set else 'unset'})")
            leaked = _leaks(r.text)
            if leaked:
                bad.append(f"{path}: leaked {leaked}")

    sweep(False)
    _with_token(lambda: sweep(True))
    assert not bad, bad


def test_the_named_leak_routes_are_closed():
    c = client()

    def run():
        for path in ("/api/owner-actions", "/api/incidents", "/api/jobs", "/api/spend-report",
                     "/api/closure", "/api/departments", "/api/benchmark-selection",
                     "/api/storefront/preview", "/api/finance", "/api/audit",
                     "/api/queue/dead", "/api/console", "/api/war-room", "/api/calendar"):
            r = c.get(path)
            assert r.status_code == 401, (path, r.status_code, r.text[:200])
    _with_token(run)


def test_root_is_the_static_public_page():
    c = client()

    def check():
        r = c.get("/")
        assert r.status_code == 200, r.status_code
        assert not _leaks(r.text), _leaks(r.text)
        for word in ("Consequence", "Max cost", "CA$", "incident", "Incident", "job", "Job",
                     "gate", "Gate", "spend", "Spend", "owner action", "Launch readiness"):
            assert word not in r.text, f"{word!r} on the public page"
        body = re.sub(r"<[^>]+>", "", r.text.split("<body>", 1)[1])
        assert not re.search(r"\d", body), "a number (a count) on the public page"
        assert "<script" not in r.text.lower()
        assert not _leaks(r.text)
    check()
    _with_token(check)
    # A wrong credential is not the operator credential.
    wrong = _with_token(lambda: c.get("/", headers={"Authorization": "Bearer " + "x" * 40}))
    assert wrong.text == c.get("/").text, "a wrong token saw more than the public page"


def test_no_unauthenticated_page_carries_owner_inbox_text():
    """FMBATCH1 62fcf5ed's sweep, kept: no owner-action or access-request text on any public
    route; the public `/` links the owner session and shows no count."""
    from brambleloop.launch import access

    c = client()
    texts = []
    for r in access.pending_requests(dict(os.environ)):
        texts += [t[:60] for t in (r.action, r.purpose, r.consequence_of_declining)
                  if len(t) >= 24]

    def run():
        leaks = []
        for path in [p for p in _get_routes() if _is_public(p)]:
            body = c.get(_concrete(path)).text
            leaks += [(path, t[:40]) for t in texts + [OA_TITLE, OA_REASON, OA_CONSEQUENCE]
                      if t in body]
        assert not leaks, leaks
        home = c.get("/").text
        assert 'href="/cc/"' in home, "the public page links the owner session"
    run()
    _with_token(run)


def test_owner_text_scrub_is_defence_in_depth():
    """Even a public route that rendered an owner text would have it redacted."""
    assert hasattr(security, "build_owner_scrubber"), "no owner-text scrub installed"
    scrub = security.build_owner_scrubber([OA_TITLE, INCIDENT_TEXT, "short"])
    out = scrub(f"<td>{OA_TITLE}</td> {INCIDENT_TEXT[:48]}... short")
    assert OA_TITLE not in out and INCIDENT_TEXT[:48] not in out and "short" in out, out


def test_static_bundles_carry_no_embedded_state():
    c = client()
    static = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"
    paths = ["/cc/", "/ops/teardown", "/ops/teardown.js", "/openapi.json", "/docs"]
    paths += ["/cc/" + str(p.relative_to(static)) for p in static.rglob("*")
              if p.is_file() and p.suffix in {".html", ".js", ".css", ".webmanifest"}]

    def run():
        bad = []
        for p in paths:
            r = c.get(p)
            if r.status_code == 200 and _leaks(r.text):
                bad.append((p, _leaks(r.text)))
        assert not bad, bad
    run()
    _with_token(run)


def _keys(value, prefix=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield prefix + k
            yield from _keys(v, prefix + k + ".")
    elif isinstance(value, list):
        for v in value:
            yield from _keys(v, prefix)


def _spec_keys(spec, prefix=""):
    return set(_keys(_skeleton(spec), prefix))


def _skeleton(spec):
    if spec is True:
        return None
    if isinstance(spec, dict):
        return {k: _skeleton(v) for k, v in spec.items()}
    if isinstance(spec, list):
        return [_skeleton(spec[0])]
    return None


def test_public_readback_endpoints_are_projected():
    c = client()

    def run(token_set: bool):
        bad = []
        for path, spec in PUBLIC_FIELDS.items():
            r = c.get(path)
            assert r.status_code in (200, 503), (path, r.status_code)
            body = r.json()
            extra = set(_keys(body)) - _spec_keys(spec)
            if extra:
                bad.append(f"{path}: unprojected fields {sorted(extra)}")
            for k in PRIVATE_KEYS:
                if k in set(p.rsplit(".", 1)[-1] for p in _keys(body)):
                    bad.append(f"{path}: private key {k}")
            if re.search(r"61\.23|77\.77|80\.1|CA\$", r.text):
                bad.append(f"{path}: a spend figure")
            if _leaks(r.text):
                bad.append(f"{path}: leaked {_leaks(r.text)}")
            # The operator's view is the full one (the operator loop is unaffected).
            if token_set:
                full = c.get(path, headers=AUTH).json()
                if not set(_keys(full)) - _spec_keys(spec):
                    bad.append(f"{path}: the operator view is not the full view")
        assert not bad, bad
    run(False)
    _with_token(lambda: run(True))


def test_deploy_readback_still_reads_every_field():
    """ops/readback.py, ops/deployed_sha.py and ops/verify_deploy.py, unauthenticated."""
    import deployed_sha
    import readback
    import verify_deploy

    c = client()

    def fetch_json(url):
        return c.get(url.replace(deployed_sha.PRODUCTION_URL, "")).json()

    def fetch(url):
        r = c.get(url.replace(readback.PRODUCTION_URL, ""))
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, None

    def run():
        sha, source = deployed_sha.deployed_commit(env={}, fetch=fetch_json)
        assert sha == SHA, (sha, source)
        out = readback.run(SHA, fetch=fetch)
        unknown = [i for i in out["features"] if i["verdict"] == readback.UNKNOWN]
        # Every field readback reads is present for an anonymous caller (a FAIL here would be
        # the sandbox's own state, e.g. no worker running; UNKNOWN would be a missing field).
        assert not unknown, unknown
        by = {i["feature"]: i for i in out["features"]}
        assert by["release identity"]["verdict"] == readback.PASS, by["release identity"]
        assert by["launch packet route deployed and operator-gated"]["verdict"] == readback.PASS
        commit, note = verify_deploy.read_commit(fetch_json, verify_deploy.PRODUCTION_URL)
        assert commit == SHA, (commit, note)
    _with_token(run)


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:2500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
