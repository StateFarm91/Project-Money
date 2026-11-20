"""W4-SECFIX (independent security review e3747c5, LOW-2): owner-recorded Marketplace Insights
figures are never served to an unauthenticated caller.

Marketplace Insights is the owner's own Shop Manager view: the search counts, listing counts,
related terms and the name of whoever recorded them are the shop's private demand research.
`GET /api/market-intel` (and the older `GET /api/insights`) served them to anyone who had the
URL. Both now take the operator credential (`security.OPERATOR_GET_ROUTES`).

Like `test_customer_data_auth.py`, this does not trust a hand list: sentinel readings are
recorded through the real write paths (`POST /api/insights/paste` with confirm, and
`intel.insights.record`), the market-intel refresh and the provenance stamp run over them, and
then *every* parameterless GET route the app registers is fetched without a credential and
must not contain any sentinel. A route that starts serving the figures fails here until it is
added to `OPERATOR_GET_ROUTES` (or stops carrying them).

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_secfix_insights_private.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="insights_private_")
DB_FILE = os.path.join(_TMP, "ins.db")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the insights-privacy harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402

TOKEN = "s" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}

# Distinctive values no route would produce by chance. The target-query reading reaches the
# market-intel payload and its lessons; the free keyword reaches only the Insights tables.
TARGET_COUNT = 7654321
FREE_COUNT = 8765432
FREE_KEYWORD = "zqsentinel granny blanket"
RELATED = "zqsentinel related term"
RECORDER = "OWNERSENTINEL-4471"
SENTINELS = {
    "target_count": [str(TARGET_COUNT), f"{TARGET_COUNT:,}"],
    "free_count": [str(FREE_COUNT), f"{FREE_COUNT:,}"],
    "free_keyword": [FREE_KEYWORD],
    "related_term": [RELATED],
    "recorded_by": [RECORDER],
}

_STATE: dict = {}


def _leaks(body: str) -> list[str]:
    low = body.lower()
    return [k for k, vs in SENTINELS.items() if any(v.lower() in low for v in vs)]


def client() -> TestClient:
    if "c" in _STATE:
        return _STATE["c"]
    from brambleloop.intel import insights, market_intel, serp
    from brambleloop.radar import provenance

    main.db.create_all()
    Registry(main.db).seed_defaults()
    c = TestClient(main.app)
    target = serp.target_queries()[0]["query"]
    _STATE["target"] = target
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        paste = (f"Search term: {target}\nSearches {TARGET_COUNT:,}\nListings 85,321\n"
                 f"Trend: up\nRelated searches\n{RELATED} 3.1K\n")
        r = c.post("/api/insights/paste", headers=AUTH,
                   json={"text": paste, "recorded_by": RECORDER, "confirm": True})
        assert r.status_code == 200 and r.json()["recorded"], r.text
        r = c.post("/api/insights/snapshot", headers=AUTH, json={
            "keyword": FREE_KEYWORD, "search_count": FREE_COUNT,
            "related_terms": [RELATED], "recorded_by": RECORDER})
        assert r.status_code == 200, r.text
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    assert any(x["keyword"] == FREE_KEYWORD for x in insights.snapshots(main.db))
    out = market_intel.refresh(main.db)
    assert out, "the market-intel refresh wrote nothing, so the sweep would prove nothing"
    latest = market_intel.latest(main.db) or {}
    assert _leaks(str(latest)), "the seeded figures never reached the market-intel payload"
    try:
        provenance.stamp_all(main.db)
    except Exception:  # noqa: BLE001 - the stamp is extra coverage, not the subject
        pass
    _STATE["c"] = c
    return c


def _get_routes() -> list[str]:
    out = []
    for path, methods, _ in security.iter_api_routes(main.app):
        if "GET" in methods and "{" not in path:
            out.append(path)
    return sorted(set(out))


def test_market_intel_and_insights_are_operator_routes():
    for path in ("/api/market-intel", "/api/insights"):
        assert path in security.OPERATOR_GET_ROUTES, path
        assert security.requires_operator("GET", path), path


def test_unauthenticated_get_of_market_intel_gets_no_pasted_figures():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN   # configured, not presented
    try:
        for path in ("/api/market-intel", "/api/insights"):
            for headers in ({}, {"Authorization": "Bearer " + "x" * 40}):
                r = c.get(path, headers=headers)
                assert r.status_code == 401, (path, headers, r.status_code)
                assert not _leaks(r.text), (path, _leaks(r.text))
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    # No credential configured at all: closed (503), still nothing served.
    for path in ("/api/market-intel", "/api/insights"):
        r = c.get(path)
        assert r.status_code == 503 and not _leaks(r.text), (path, r.status_code)


def test_the_operator_still_reads_both():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        r = c.get("/api/market-intel", headers=AUTH)
        assert r.status_code == 200, r.text
        assert "target_count" in _leaks(r.text), "the operator must still see the reading"
        r = c.get("/api/insights", headers=AUTH)
        assert r.status_code == 200 and "free_keyword" in _leaks(r.text), r.text
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


def test_no_public_get_route_serves_owner_recorded_insights():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN   # configured, not presented
    leaks: dict[str, list[str]] = {}
    errors: dict[str, str] = {}
    checked = 0
    try:
        for path in _get_routes():
            # W4-SECPATCH: reads are default-deny, so only ~a dozen GETs are public; every
            # route is fetched without the credential (a gated one must refuse, leaking none).
            if security.owner_session_route(path):
                continue
            try:
                r = c.get(path)
            except Exception as e:  # noqa: BLE001 - a crash serves nothing, but is reported
                errors[path] = type(e).__name__
                continue
            checked += 1
            found = _leaks(r.text)
            if found:
                leaks[path] = found
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    assert not leaks, f"public routes serving owner-recorded Insights: {leaks}"
    assert not errors, f"routes that raised instead of answering: {errors}"
    assert checked > 100, checked


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {str(e)[:1500]}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
