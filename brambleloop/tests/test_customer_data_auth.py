"""F-696 / F-689: customer, order and support content is never readable without the operator
credential.

The defect this closes: `/api/support` served customer question and answer text to anyone who
could reach the dashboard. The fix is not only to guard that one route -- the next route that
joins an order or quotes a customer would reopen the same hole -- so this test enumerates
*every* GET route the application registers and checks each against seeded sentinels.

A temp-file database is seeded with a Customer, an Order and a SupportCase whose free-text
fields carry distinctive sentinel strings. Then:

1. every route named in `main.CUSTOMER_DATA_ROUTES` refuses without the credential (401 with a
   token configured, 503 with none), refuses a wrong credential, and serves the data with the
   right one;
2. every *other* parameterless GET route -- enumerated from `main.app.routes`, never from a
   hand list -- is fetched without a credential and must not contain any sentinel. A route that
   starts returning customer text fails here until it is added to `CUSTOMER_DATA_ROUTES`.

The TestClient is used without its context manager so the startup hook never runs; the network
is refused at the socket.

Run: cd brambleloop && $PY tests/test_customer_data_auth.py
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="customer_auth_")
DB_FILE = os.path.join(_TMP, "cx.db")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the customer-data harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import Customer, Order, SupportCase  # noqa: E402

TOKEN = "t" * 40

# Each free-text field a customer can author or that identifies them, marked so a leak is
# unmistakable in any response body.
SENTINELS = {
    "customer_ref": "CXSENTINEL-REF-7731",
    "search_term": "cxsentinel search phrase 5521",
    "question": "CXSENTINEL question: my stitch count is off in row 9",
    "answer": "CXSENTINEL answer text for the buyer",
    "external_ref": "CXSENTINEL-ORDER-9904",
}

_STATE: dict = {}


def client() -> TestClient:
    if "c" in _STATE:
        return _STATE["c"]
    assert str(main.db.engine.url).endswith(DB_FILE), main.db.engine.url
    main.db.create_all()
    Registry(main.db).seed_defaults()
    with main.db.session() as s:
        cust = Customer(customer_ref=SENTINELS["customer_ref"],
                        search_term=SENTINELS["search_term"], first_product_slug="seed")
        s.add(cust)
        s.flush()
        case = SupportCase(customer_ref=SENTINELS["customer_ref"], product_slug="seed",
                           version="1.0.0", question=SENTINELS["question"],
                           answer=SENTINELS["answer"])
        s.add(case)
        s.flush()
        s.add(Order(customer_id=cust.id, external_ref=SENTINELS["external_ref"],
                    product_slug="seed", search_term=SENTINELS["search_term"],
                    support_case_id=case.id))
        s.commit()
    _STATE["c"] = TestClient(main.app)
    return _STATE["c"]


def _get_routes() -> list[str]:
    """Every GET route the app registers that takes no path parameter."""
    out = []
    for r in main.app.routes:
        if isinstance(r, APIRoute) and "GET" in r.methods and "{" not in r.path:
            out.append(r.path)
    return sorted(set(out))


def _leaks(body: str) -> list[str]:
    return [k for k, v in SENTINELS.items() if v.lower() in body.lower()]


def test_support_route_is_declared_customer_bearing():
    assert "/api/support" in main.CUSTOMER_DATA_ROUTES
    registered = set(_get_routes())
    for path in main.CUSTOMER_DATA_ROUTES:
        assert path in registered, f"{path} is declared customer-bearing but not registered"


def test_customer_routes_are_closed_when_no_credential_is_configured():
    c = client()
    os.environ.pop(opsauth.TOKEN_VAR, None)
    for path in sorted(main.CUSTOMER_DATA_ROUTES):
        r = c.get(path, headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 503, (path, r.status_code)
        assert not _leaks(r.text), (path, _leaks(r.text))


def test_customer_routes_refuse_a_missing_or_wrong_credential():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        for path in sorted(main.CUSTOMER_DATA_ROUTES):
            for headers in ({}, {"Authorization": "Bearer " + "x" * 40}):
                r = c.get(path, headers=headers)
                assert r.status_code == 401, (path, headers, r.status_code)
                assert not _leaks(r.text), (path, _leaks(r.text))
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


def test_customer_routes_serve_the_operator_with_the_credential():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        r = c.get("/api/support", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200, r.status_code
        assert "question" in _leaks(r.text), "the operator must still see the case text"
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


def test_no_other_get_route_returns_customer_fields_without_the_credential():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN   # configured, but not presented
    leaks: dict[str, list[str]] = {}
    errors: dict[str, str] = {}
    try:
        for path in _get_routes():
            if path in main.CUSTOMER_DATA_ROUTES:
                continue
            try:
                r = c.get(path)
            except Exception as e:  # noqa: BLE001 -- a route that crashes serves nothing
                errors[path] = f"{type(e).__name__}"
                continue
            found = _leaks(r.text)
            if found:
                leaks[path] = found
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    assert not leaks, f"unauthenticated routes returning customer fields: {leaks}"
    # A route that crashed was not checked, so a crash is a failure of this test too.
    assert not errors, f"routes that raised instead of answering: {errors}"
    # Enumeration must actually have covered the surface, not silently skipped it.
    assert len(_get_routes()) > 100, len(_get_routes())


def test_the_enumeration_includes_the_dashboard_and_console():
    routes = set(_get_routes())
    for p in ("/", "/api/console", "/api/status", "/api/audit", "/api/jobs"):
        assert p in routes, p


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
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1200]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
