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

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import Customer, Order, SupportCase  # noqa: E402
from sqlalchemy import select  # noqa: E402

TOKEN = "t" * 40

# Each free-text field a customer can author or that identifies them, marked so a leak is
# unmistakable in any response body.
SENTINELS = {
    "customer_ref": "CXSENTINEL-REF-7731",
    "search_term": "cxsentinel search phrase 5521",
    "question": "CXSENTINEL question: my stitch count is off in row 9",
    "answer": "CXSENTINEL answer text for the buyer",
    "external_ref": "CXSENTINEL-ORDER-9904",
    # A3-04: a buyer recorded through the real write path (POST /api/support/messages ->
    # response_watch), whose first-response owner card is then raised by the watch. The
    # derived OwnerAction and Incident rows were the blind spot: this file seeded only the
    # Customer/Order/SupportCase tables, and the card text quoted the buyer's identifier on
    # five unauthenticated routes while every assertion here stayed green.
    "recorded_ref": "CXSENTINEL-BUYER-4410",
    "recorded_message": "CXSENTINEL recorded message: row 12 has the wrong count",
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
    _seed_through_the_write_path(_STATE["c"])
    return _STATE["c"]


def _seed_through_the_write_path(c: TestClient) -> None:
    """Record a buyer message as the owner does, then let the watch derive its owner card."""
    from datetime import datetime, timedelta, timezone

    from brambleloop.support import response_watch

    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        received = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        r = c.post("/api/support/messages", headers={"Authorization": f"Bearer {TOKEN}"},
                   json={"event": "buyer_message", "customer_ref": SENTINELS["recorded_ref"],
                         "message": SENTINELS["recorded_message"], "received_at": received})
        assert r.status_code == 200, r.text
        _STATE["recorded_case"] = r.json()["case_id"]
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    watched = response_watch.watch(main.db)
    assert _STATE["recorded_case"] in watched["raised"], watched


def _get_routes() -> list[str]:
    """Every GET route the app registers that takes no path parameter, routers included.

    `security.iter_api_routes`, not `app.routes`: FastAPI 0.14x keeps included routers out of
    `app.routes`, and this sweep used to skip every one of them without saying so.
    """
    from brambleloop.app import security

    out = []
    for path, methods, _ in security.iter_api_routes(main.app):
        if "GET" in methods and "{" not in path:
            out.append(path)
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


def test_the_first_response_card_names_the_case_not_the_buyer():
    """A3-04 root fix: the owner card is stored without the buyer identifier at all."""
    from brambleloop.core.models import Incident, OwnerAction
    from brambleloop.support import response_watch

    client()
    case_id = _STATE["recorded_case"]
    with main.db.session() as s:
        card = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == response_watch.key_for(case_id)))
        assert card is not None, "the watch raised no card, so this proved nothing"
        stored = " ".join(str(getattr(card, c.name)) for c in OwnerAction.__table__.columns)
        incidents = " ".join(f"{i.summary} {i.detail}" for i in s.scalars(select(Incident)))
    assert f"support case {case_id}" in stored, stored
    assert not _leaks(stored), ("owner card stores a customer field", _leaks(stored))
    assert not _leaks(incidents), ("incident stores a customer field", _leaks(incidents))


def test_owner_card_routes_never_carry_the_recorded_buyer():
    """The five routes the audit found serving it, by name, plus the HTML dashboard."""
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN   # configured, not presented
    try:
        for path in ("/", "/api/build", "/api/console", "/api/owner-actions", "/api/war-room"):
            r = c.get(path)
            assert r.status_code == 200, (path, r.status_code)
            assert not _leaks(r.text), (path, _leaks(r.text))
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    body = c.get("/api/owner-actions").text
    assert f"support case {_STATE['recorded_case']}" in body, "the card itself must still show"


def test_a_card_that_does_quote_a_buyer_is_redacted_on_render():
    """Defence in depth: the next write path that forgets the rule is still not a leak."""
    from brambleloop.core.models import OwnerAction

    c = client()
    with main.db.session() as s:
        s.add(OwnerAction(requirement_key="test:redaction", action=(
            f"Reply to {SENTINELS['recorded_ref']} about {SENTINELS['customer_ref']}"),
            reason="test", max_cost_cad=0.0, minutes=1, consequence_of_delay="none",
            blocks="none"))
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        for path in ("/", "/api/owner-actions", "/api/console"):
            r = c.get(path)
            assert not _leaks(r.text), (path, _leaks(r.text))
        r = c.get("/api/owner-actions")
        assert "[customer]" in r.text and r.headers["content-type"].startswith(
            "application/json")
        r.json()  # still valid JSON after the scrub
        # The operator, presenting the credential, sees the row as stored.
        r = c.get("/api/owner-actions", headers={"Authorization": f"Bearer {TOKEN}"})
        assert SENTINELS["recorded_ref"] in r.text
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
        with main.db.session() as s:
            for row in s.scalars(select(OwnerAction).where(
                    OwnerAction.requirement_key == "test:redaction")):
                s.delete(row)


def test_the_enumeration_includes_the_dashboard_and_console():
    routes = set(_get_routes())
    for p in ("/", "/api/console", "/api/status", "/api/audit", "/api/jobs",
              "/api/storefront/preview", "/api/search-visibility", "/api/owner/phase"):
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
