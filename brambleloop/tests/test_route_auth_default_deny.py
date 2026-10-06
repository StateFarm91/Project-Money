"""Independent audit A3-02: every mutating route is closed to anyone without the operator
credential, by default.

The defect: ten POST routes (scheduler/tick, plan-cycle, chain-rebuild, launch-readiness,
continuity/verify, dead-letters/requeue, etsy/probe, mjs/scan, model/probe, seasonal/recompute)
answered 200 to an anonymous caller -- queue flooding, forced model and Etsy calls, a full
export-and-restore proof on demand, and an unauthenticated re-drive of dead letters beside the
authenticated `/api/queue/requeue`. Each route had decided for itself whether to check.

The fix is one application-wide dependency (`app.security.operator_gate`). This test walks
`app.routes` -- never a hand list -- and fails if:

- any route with a non-GET method lacks the gate in its dependency tree, or is exempt without
  being on `security.PUBLIC_MUTATING_ROUTES` (with a written reason);
- an allow-list entry names a route that does not exist (a stale exemption is a hole waiting
  for a route to be re-added under the old name);
- any gated route, called for real, answers anything but 503 (token unset), 401/403 (no or
  wrong credential) -- or changes the database while refusing.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_route_auth_default_deny.py
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="default_deny_")
DB_FILE = os.path.join(_TMP, "dd.db")
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
    raise OSError("network refused by the default-deny harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import AuditLog, Job, SupportCase  # noqa: E402

TOKEN = "g" * 40

# The routes the audit found open. Named so that a regression on any of them reads plainly.
AUDIT_A3_02 = (
    "/api/scheduler/tick", "/api/plan-cycle", "/api/chain-rebuild", "/api/launch-readiness",
    "/api/continuity/verify", "/api/dead-letters/requeue", "/api/etsy/probe", "/api/mjs/scan",
    "/api/model/probe", "/api/seasonal/recompute", "/api/physical-test", "/api/physical-photo",
)

_STATE: dict = {}


def client() -> TestClient:
    if "c" in _STATE:
        return _STATE["c"]
    assert str(main.db.engine.url).endswith(DB_FILE), main.db.engine.url
    main.db.create_all()
    Registry(main.db).seed_defaults()
    _STATE["c"] = TestClient(main.app, raise_server_exceptions=False)
    return _STATE["c"]


def _dependency_calls(dependant) -> set:
    out = set()
    stack = [dependant]
    while stack:
        d = stack.pop()
        for sub in d.dependencies:
            out.add(sub.call)
            stack.append(sub)
    return out


def _mutating() -> list[tuple[str, str, object]]:
    """(method, path, dependant) for every non-GET route, routers included."""
    out = []
    for path, methods, dependant in security.iter_api_routes(main.app):
        for m in sorted(methods - security.SAFE_METHODS):
            out.append((m, path, dependant))
    return out


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def _db_fingerprint() -> tuple:
    with main.db.session() as s:
        return (s.scalar(select(func.count()).select_from(Job)),
                s.scalar(select(func.count()).select_from(AuditLog)),
                s.scalar(select(func.count()).select_from(SupportCase)))


def test_every_mutating_route_has_the_gate_or_a_written_exemption():
    routes = _mutating()
    assert len(routes) >= 40, f"enumeration found only {len(routes)} mutating routes"
    missing = []
    for method, path, dependant in routes:
        if (method, path) in security.PUBLIC_MUTATING_ROUTES:
            assert len(security.PUBLIC_MUTATING_ROUTES[(method, path)]) > 40, (
                f"{method} {path} is exempt without a real reason")
            continue
        if security.operator_gate not in _dependency_calls(dependant):
            missing.append(f"{method} {path} (gate not in dependency tree)")
        elif not security.requires_operator(method, path):
            missing.append(f"{method} {path} (gate present but not enforced)")
    assert not missing, f"mutating routes reachable without the operator credential: {missing}"


def test_the_allow_lists_name_real_routes():
    registered = {(m, p) for m, p, _ in _mutating()}
    # The routers are in the enumeration (FastAPI 0.14x hides them from `app.routes`).
    for p in ("/api/owner/phase/transition", "/api/owner/publication/approve",
              "/api/owner/activation/approve", "/api/owner/ledger-mapping/verify",
              "/api/search-visibility",
              "/api/learn/graph/edges"):
        assert ("POST", p) in registered, p
    stale = [k for k in security.PUBLIC_MUTATING_ROUTES if k not in registered]
    assert not stale, f"exemptions for routes that do not exist: {stale}"
    gets = {p for p, methods, _ in security.iter_api_routes(main.app) if "GET" in methods}
    stale_gets = sorted(p for p in security.OPERATOR_GET_ROUTES | set(security.PUBLIC_GET_NOTES)
                        if p not in gets)
    assert not stale_gets, stale_gets
    for p in main.CUSTOMER_DATA_ROUTES:
        assert p in security.OPERATOR_GET_ROUTES, p
    for p in AUDIT_A3_02:
        assert ("POST", p) in registered, p


def _want(path: str) -> int:
    """403 on the owner routers (their established contract), 401 everywhere else."""
    routers = ("/api/owner/phase", "/api/owner/publication/", "/api/owner/activation/",
               "/api/owner/ledger-mapping")
    return 403 if path.startswith(routers) else 401


def test_refusal_status_matches_each_routes_contract():
    assert security.refusal_status("/api/owner/decision") == 401
    assert security.refusal_status("/api/owner/phase/transition") == 403
    assert security.refusal_status("/api/owner/publication/{approval_id}/revoke") == 403
    assert security.refusal_status("/api/owner/ledger-mapping/verify") == 403
    assert security.refusal_status("/api/scheduler/tick") == 401


def _call(c, method, path, headers):
    return c.request(method, _concrete(path), headers=headers, json={})


def test_every_gated_route_refuses_and_changes_nothing():
    c = client()
    before = _db_fingerprint()
    wrong = {"Authorization": "Bearer " + "x" * 40}
    bad = []
    try:
        # Token unset: closed to everybody, 503.
        os.environ.pop(opsauth.TOKEN_VAR, None)
        for method, path, _ in _mutating():
            if (method, path) in security.PUBLIC_MUTATING_ROUTES:
                continue
            r = _call(c, method, path, {"Authorization": f"Bearer {TOKEN}"})
            if r.status_code != 503:
                bad.append(f"unset {method} {path} -> {r.status_code}")
        # Token set: no credential and a wrong one are both refused.
        os.environ[opsauth.TOKEN_VAR] = TOKEN
        for method, path, _ in _mutating():
            if (method, path) in security.PUBLIC_MUTATING_ROUTES:
                continue
            want = _want(path)
            for headers in ({}, wrong):
                r = _call(c, method, path, headers)
                if r.status_code != want:
                    bad.append(f"{method} {path} {bool(headers)} -> {r.status_code}")
                elif TOKEN in r.text:
                    bad.append(f"{method} {path} echoed the token")
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)
    assert not bad, bad
    assert _db_fingerprint() == before, "a refused request changed the database"


def test_the_audit_routes_work_with_the_credential():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    auth = {"Authorization": f"Bearer {TOKEN}"}
    try:
        for path in ("/api/scheduler/tick", "/api/chain-rebuild", "/api/continuity/verify",
                     "/api/dead-letters/requeue", "/api/etsy/probe", "/api/mjs/scan",
                     "/api/model/probe", "/api/seasonal/recompute", "/api/launch-readiness"):
            r = c.post(path, headers=auth)
            assert r.status_code == 200, (path, r.status_code, r.text[:200])
            assert r.status_code == 200 and c.post(path).status_code == 401, path
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


def test_operator_gets_refuse_without_the_credential():
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        for path in sorted(security.OPERATOR_GET_ROUTES):
            r = c.get(_concrete(path))
            want = _want(path)
            assert r.status_code == want, (path, r.status_code)
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


def test_public_reads_stay_public():
    """The dashboard's read-only views are still an absent owner opening a URL."""
    c = client()
    os.environ[opsauth.TOKEN_VAR] = TOKEN
    try:
        for path in ("/", "/health", "/api/status", "/api/owner-actions", "/ops/teardown"):
            assert c.get(path).status_code in (200, 503), path
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
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
