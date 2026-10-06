"""Independent audit A3-01 / A3-11 / A3-12 / A3-13: the web edge.

A3-01 (launch-blocking): an unauthenticated `POST /api/plan-cycle?as_of=<script>...` dead-
lettered with the payload quoted in its error, and the dashboard printed `Job.last_error` raw,
with no Content-Security-Policy, on the same origin where `/ops/teardown` kept the operator
token in `localStorage`. These tests make each link of that chain impossible on its own:

- every string and JSON column of every table is seeded with hostile markup, through the ORM
  (no route is trusted to have validated anything), and every HTML route is rendered: no raw
  `<script`, `<img`, or attribute break-out may appear, and the payload must be visibly present
  *escaped* -- so the test cannot pass by the page simply not rendering the data;
- every response carries a strict CSP (no inline script), nosniff, frame-ancestors 'none' and
  a Referrer-Policy; no HTML route carries an inline script;
- the teardown page never writes the token to `localStorage`;
- `as_of` is validated at the edge: garbage is a 400 and nothing is queued.

A3-11: a non-ASCII Authorization header is a refusal, not a 500.
A3-12: an unreachable database is reported on /health without its host or port.
A3-13: recording the same buyer message twice yields one case and one owner card.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_web_security.py
"""
from __future__ import annotations

import enum
import os
import re
import shutil
import socket
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="web_security_")
DB_FILE = os.path.join(_TMP, "ws.db")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the web-security harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, Float, Integer, Numeric  # noqa: E402
from sqlalchemy import LargeBinary, String, Text, func, insert, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, runner, security  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.db import Base  # noqa: E402
from brambleloop.core.models import Job, JobStatus, OwnerAction, SupportCase  # noqa: E402

TOKEN = "w" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}

# Each fragment is a different way out of an HTML context: a script element, an event handler
# on an injected element, a double-quoted attribute break-out and a single-quoted one.
HOSTILE = ("XSSPROBE\"'><script>alert('XSSPROBE')</script><img src=x onerror=alert(1)>"
           "\" onmouseover=\"alert(2)\" x=\"' onfocus='alert(3)' y='")

_STATE: dict = {}


def _value_for(col):
    t = col.type
    if isinstance(t, Enum):
        enum_cls = getattr(t, "enum_class", None)
        if enum_cls is not None:
            return list(enum_cls)[0]
        return list(t.enums)[0]
    if isinstance(t, JSON):
        return {"summary": HOSTILE, "why": HOSTILE, "detail": HOSTILE, "items": [HOSTILE]}
    if isinstance(t, Boolean):
        return False
    if isinstance(t, DateTime):
        return datetime.now(timezone.utc) - timedelta(hours=1)
    if isinstance(t, Date):
        return datetime.now(timezone.utc).date()
    if isinstance(t, (Float, Numeric)):
        return 1.0
    if isinstance(t, Integer):
        return 1
    if isinstance(t, (String, Text)):
        return HOSTILE
    if isinstance(t, LargeBinary):
        return HOSTILE.encode()
    return None


def _seed_every_table() -> dict[str, str]:
    """One hostile row per table, every text and JSON column carrying the payload."""
    failures: dict[str, str] = {}
    for table in Base.metadata.sorted_tables:
        row = {}
        for col in table.columns:
            if col.primary_key and isinstance(col.type, Integer):
                continue
            v = _value_for(col)
            if v is not None:
                row[col.name] = v
        try:
            with main.db.session() as s:
                s.execute(insert(table).values(**row))
        except Exception as e:  # noqa: BLE001 - a table that refuses the row is reported
            failures[table.name] = f"{type(e).__name__}: {str(e)[:120]}"
    return failures


def client() -> TestClient:
    if "c" in _STATE:
        return _STATE["c"]
    assert str(main.db.engine.url).endswith(DB_FILE), main.db.engine.url
    main.db.create_all()
    Registry(main.db).seed_defaults()
    _STATE["seed_failures"] = _seed_every_table()
    # The original vector, end to end through the queue: a job whose error quotes the payload.
    with main.db.session() as s:
        s.add(Job(agent="orchestrator", job_type="plan.cycle", inputs={"as_of": HOSTILE},
                  status=JobStatus.DEAD, attempts=3,
                  last_error=f"ValueError: Invalid isoformat string: {HOSTILE!r}"))
    runner.STATE.last_error = f"RuntimeError: {HOSTILE}"
    _STATE["c"] = TestClient(main.app, raise_server_exceptions=False)
    return _STATE["c"]


def _html_routes(c: TestClient) -> dict[str, str]:
    out = {}
    for path, methods, _ in security.iter_api_routes(main.app):
        if "GET" in methods and "{" not in path:
            resp = c.get(path, headers=AUTH)
            if "text/html" in resp.headers.get("content-type", ""):
                out[path] = resp.text
    return out


_RAW_BREAKOUTS = (
    re.compile(r"<script(?![^>]*\bsrc=\"/ops/teardown\.js\")", re.IGNORECASE),
    re.compile(r"<img", re.IGNORECASE),
    re.compile(r"\" onmouseover=", re.IGNORECASE),
    re.compile(r"' onfocus=", re.IGNORECASE),
)


def _breakouts(body: str) -> list[str]:
    hits = []
    for pat in _RAW_BREAKOUTS:
        for m in pat.finditer(body):
            hits.append(body[max(0, m.start() - 60):m.end() + 40].replace("\n", " "))
    return hits


# ---- A3-01: escaping --------------------------------------------------------


def test_every_html_route_escapes_hostile_database_content():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        pages = _html_routes(c)
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    assert "/" in pages and "/ops/teardown" in pages, sorted(pages)
    problems = {p: _breakouts(body)[:3] for p, body in pages.items() if _breakouts(body)}
    assert not problems, f"unescaped hostile content: {problems}"
    # The payload must have reached the dashboard, escaped. Otherwise this proved nothing.
    dash = pages["/"]
    assert "XSSPROBE" in dash, "the seeded payload never reached the dashboard"
    assert "&lt;script&gt;alert(" in dash, "the payload is not rendered escaped"
    # The job error (the A3-01 vector) and the runner error are both on the page, escaped.
    assert "Invalid isoformat string" in dash
    assert "RuntimeError: XSSPROBE&quot;" in dash or "RuntimeError: XSSPROBE" in dash


def test_the_dashboard_escapes_an_exception_message_from_a_failing_block():
    c = client()
    original = main.api_status

    def boom():
        raise RuntimeError(HOSTILE)

    from brambleloop.build2 import requirements as reqs

    saved = reqs.coverage
    reqs.coverage = boom
    # Presented credential: the customer-identifier scrub (which would also redact this
    # payload, since it is seeded as a customer_ref) stays out of the way of the escaping check.
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        body = c.get("/", headers=AUTH).text
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
        reqs.coverage = saved
        main.api_status = original
    assert "unavailable: RuntimeError: XSSPROBE" in body
    assert not _breakouts(body), _breakouts(body)[:3]


def test_the_oauth_callback_page_escapes_reflected_parameters():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        r = c.get("/api/etsy/oauth/callback",
                  params={"error": HOSTILE, "error_description": HOSTILE, "state": HOSTILE})
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    assert not _breakouts(r.text), _breakouts(r.text)[:3]


def test_esc_and_markup():
    assert security.esc("<a href=\"x\" onclick='y'>") == (
        "&lt;a href=&quot;x&quot; onclick=&#x27;y&#x27;&gt;")
    assert security.esc(None) == ""
    frag = security.Markup("<b>ok</b>")
    assert security.esc(frag) is frag
    assert security.safe_url("javascript:alert(1)") == ""
    assert security.safe_url("https://www.etsy.com/listing/1") == "https://www.etsy.com/listing/1"


# ---- A3-01: headers, inline script, the token --------------------------------


def _csp(resp) -> str:
    return resp.headers.get("content-security-policy", "")


def test_every_response_carries_the_security_headers():
    c = client()
    for path in ("/", "/ops/teardown", "/api/status", "/health", "/api/owner-actions",
                 "/does-not-exist"):
        r = c.get(path)
        csp = _csp(r)
        assert csp, (path, "no Content-Security-Policy")
        directives = {d.strip().split(" ")[0]: d.strip() for d in csp.split(";") if d.strip()}
        script = directives.get("script-src") or directives.get("default-src", "")
        assert "'unsafe-inline'" not in script and "'unsafe-eval'" not in script, (path, csp)
        assert directives.get("frame-ancestors") == "frame-ancestors 'none'", (path, csp)
        assert r.headers.get("x-content-type-options") == "nosniff", path
        assert r.headers.get("referrer-policy"), path
    # A route with a stricter policy of its own keeps it.
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        r = c.get("/api/etsy/oauth/callback", params={"state": "x"})
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    assert _csp(r).startswith("default-src 'none'; style-src 'unsafe-inline'"), _csp(r)


def test_no_html_route_carries_an_inline_script_or_handler():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        pages = _html_routes(c)
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    assert pages, "no HTML route was found to check"
    for path, body in pages.items():
        # A page with no <script> at all is the strongest pass: the assertion constrains only
        # scripts that exist, so an empty match set here is the behaviour, not a vacuous loop.
        for m in re.finditer(r"<script\b([^>]*)>", body, re.IGNORECASE):  # vacuity-ok: none = pass
            assert "src=" in m.group(1), (path, "inline <script> without src")
    # The dashboard has no script at all.
    assert "<script" not in pages["/"].lower()


def test_the_teardown_page_never_persists_the_operator_token():
    c = client()
    page = c.get("/ops/teardown").text
    js = c.get("/ops/teardown.js")
    assert js.status_code == 200
    assert "javascript" in js.headers.get("content-type", "")
    assert '<script src="/ops/teardown.js">' in page
    assert "onclick=" not in page
    assert "localStorage.setItem" not in js.text and "sessionStorage" not in js.text
    assert "localStorage.removeItem('bl_ops')" in js.text, "the legacy copy must be cleared"
    assert "a.href=p.url" not in js.text, "listing URLs must pass the https-only filter"


# ---- A3-01 / A3-02: as_of validated at the edge -------------------------------


def test_garbage_as_of_is_refused_before_anything_is_queued():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        with main.db.session() as s:
            before = s.scalar(select(func.count()).select_from(Job))
        for bad in (HOSTILE, "garbage-1", "2027-13-01", "2027-1-1", "99999-01-01",
                    "1900-01-01", "2027-01-20T00:00:00"):
            for path in ("/api/plan-cycle", "/api/seasonal/recompute"):
                r = c.post(path, params={"as_of": bad}, headers=AUTH)
                assert r.status_code == 400, (path, bad, r.status_code, r.text)
                assert "XSSPROBE" not in r.text
        with main.db.session() as s:
            after = s.scalar(select(func.count()).select_from(Job))
        assert after == before, "a refused as_of still queued a job"
        r = c.post("/api/plan-cycle", params={"as_of": "2027-01-20"}, headers=AUTH)
        assert r.status_code == 200 and r.json()["enqueued"] is True, r.text
        # And without the credential nothing is queued at all.
        r = c.post("/api/plan-cycle", params={"as_of": "2027-01-21"})
        assert r.status_code == 401, r.status_code
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


# ---- A3-11 -------------------------------------------------------------------


def test_a_non_ascii_authorization_header_is_a_refusal_not_a_500():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    os.environ["BRAMBLELOOP_LEARN_REVIEW_TOKEN"] = "r" * 40
    os.environ["BRAMBLELOOP_LEARN_REVIEWER_ID"] = "reviewer-1"
    try:
        bad = {"Authorization": "Bearer t\xe9".encode("latin-1")}
        assert c.get("/api/support", headers=bad).status_code == 401
        assert c.get("/api/learn/queue", headers=bad).status_code == 401
        assert c.post("/api/scheduler/tick", headers=bad).status_code == 401
        assert c.get("/api/owner/phase", headers=bad).status_code == 403
        r = c.post("/api/learn/lessons/x/review", headers=bad,
                   json={"revision": "r", "verdicts": {}, "evidence_ref": "e"})
        assert r.status_code == 401, r.status_code
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
        os.environ.pop("BRAMBLELOOP_LEARN_REVIEW_TOKEN", None)
        os.environ.pop("BRAMBLELOOP_LEARN_REVIEWER_ID", None)
    try:
        opsauth.check("Bearer t\xe9", env={opsauth.TOKEN_VAR: TOKEN})
    except opsauth.OpsAuthRefused:
        pass
    else:  # pragma: no cover
        raise AssertionError("a non-ASCII credential was accepted")


# ---- A3-12 -------------------------------------------------------------------


def test_health_does_not_disclose_the_database_address():
    c = client()

    class _Broken:
        def __enter__(self):
            raise RuntimeError('connection to server at "10.1.2.3", port 5432 failed: '
                               "password=SUPERSECRETPW timeout expired")

        def __exit__(self, *a):
            return False

    saved_session = main.db.session
    saved_err = runner.STATE.last_error
    main.db.session = lambda: _Broken()  # type: ignore[assignment]
    runner.STATE.last_error = ('OperationalError: connection to server at "10.1.2.3", '
                               "port 5432 failed")
    try:
        r = c.get("/health")
    finally:
        main.db.session = saved_session  # type: ignore[assignment]
        runner.STATE.last_error = saved_err
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "unreachable", body["db"]
    for secret in ("10.1.2.3", "5432", "SUPERSECRETPW"):
        assert secret not in r.text, secret
    assert body["runner"]["last_error"].startswith("OperationalError"), body["runner"]


# ---- A3-13 -------------------------------------------------------------------


def test_recording_the_same_buyer_message_twice_is_one_case():
    from brambleloop.support import response_watch

    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        body = {"event": "buyer_message", "customer_ref": "IDEMP-REF-1",
                "message": "hello, row 4 is confusing"}
        first = c.post("/api/support/messages", headers=AUTH, json=body).json()
        second = c.post("/api/support/messages", headers=AUTH, json=body).json()
        assert first["case_id"] == second["case_id"], (first, second)
        assert first["duplicate"] is False and second["duplicate"] is True
        timed = {**body, "received_at": "2026-10-01T00:00:00+00:00"}
        t1 = c.post("/api/support/messages", headers=AUTH, json=timed).json()
        t2 = c.post("/api/support/messages", headers=AUTH, json=timed).json()
        assert t1["case_id"] == t2["case_id"] and t2["duplicate"] is True
        assert t1["case_id"] != first["case_id"], "a different receipt time is a new message"
        other = c.post("/api/support/messages", headers=AUTH,
                       json={**body, "message": "a different question"}).json()
        assert other["case_id"] not in (first["case_id"], t1["case_id"])
        with main.db.session() as s:
            n = s.scalar(select(func.count()).select_from(SupportCase).where(
                SupportCase.customer_ref == "IDEMP-REF-1"))
        assert n == 3, n
        # One card per case, however many times the watch runs.
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        d1 = c.post("/api/support/messages", headers=AUTH,
                    json={**body, "customer_ref": "IDEMP-REF-2", "received_at": old}).json()
        d2 = c.post("/api/support/messages", headers=AUTH,
                    json={**body, "customer_ref": "IDEMP-REF-2", "received_at": old}).json()
        assert d1["case_id"] == d2["case_id"]
        response_watch.watch(main.db)
        response_watch.watch(main.db)
        with main.db.session() as s:
            cards = s.scalar(select(func.count()).select_from(OwnerAction).where(
                OwnerAction.requirement_key == response_watch.key_for(d1["case_id"])))
        assert cards == 1, cards
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


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
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    if _STATE.get("seed_failures"):
        print("tables that refused the hostile row:", _STATE["seed_failures"])
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
