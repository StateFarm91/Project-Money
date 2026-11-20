"""ENG-IMPROVE: `GET /api/readback/ecrs` is read-only and gated by the readback token only.

OFFLINE TEST -- NOT PRODUCTION EVIDENCE.

* closed (503) when BRAMBLELOOP_READBACK_TOKEN is unset; 401 without it or with a wrong one;
* the OPERATOR token is refused on it;
* 200 with the readback token, listing open requests and no free-text evidence;
* every non-GET method is refused and the database is unchanged by any request;
* the readback token opens nothing else (the route is in security.READBACK_ROUTES only).

Run: cd brambleloop && python3 tests/test_eng_improve_readback.py
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="ecr_rb_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'rb.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.core import opsauth, readbackauth  # noqa: E402
from brambleloop.improve import ecr  # noqa: E402
from brambleloop.improve.self_models import EngineeringChangeRequest  # noqa: E402

OPS_TOKEN = "op" * 20
READBACK_TOKEN = "rb-" + "q9" * 20
URL = "/api/readback/ecrs"


@contextlib.contextmanager
def _env(**kw):
    saved = {k: os.environ.get(k) for k in kw}
    try:
        for k, v in kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _bearer(t):
    return {"Authorization": f"Bearer {t}"}


_C: dict = {}


def _client() -> TestClient:
    if "c" not in _C:
        main.db.create_all()
        Registry(main.db).seed_defaults()
        ecr.file(main.db, defect_class="missing_consumer", department="pricing",
                 module="(none)", title="Pricing: missing consumer",
                 problem="no consumer reads pricing lessons",
                 evidence={"lessons": {"learned": 2}, "examples": [
                     {"lesson": 9, "subject": "PRIVATE-SUBJECT"}]},
                 proposed_change="add one", acceptance_criteria=["table LOOP_CLOSED"])
        _C["c"] = TestClient(main.app, raise_server_exceptions=False,
                             base_url="https://testserver")
    return _C["c"]


def _fingerprint():
    with main.db.session() as s:
        n = s.scalar(select(func.count()).select_from(EngineeringChangeRequest))
        rows = [(r.state, r.occurrences, r.updated_at) for r in
                s.scalars(select(EngineeringChangeRequest))]
    return n, rows


def test_route_is_a_readback_route():
    assert URL in security.READBACK_ROUTES
    assert URL not in getattr(security, "PUBLIC_GET_ROUTES", ())
    paths = {getattr(r, "path", None) for r in main.app.routes}
    assert URL in paths


def test_closed_without_a_configured_token():
    c = _client()
    with _env(**{readbackauth.TOKEN_VAR: None, opsauth.TOKEN_VAR: OPS_TOKEN}):
        assert c.get(URL).status_code == 503
        assert c.get(URL, headers=_bearer(READBACK_TOKEN)).status_code == 503


def test_token_gated_and_operator_token_refused():
    c = _client()
    with _env(**{readbackauth.TOKEN_VAR: READBACK_TOKEN, opsauth.TOKEN_VAR: OPS_TOKEN}):
        assert c.get(URL).status_code == 401
        assert c.get(URL, headers=_bearer(READBACK_TOKEN[:-1])).status_code == 401
        assert c.get(URL, headers=_bearer(OPS_TOKEN)).status_code == 401
        r = c.get(URL, headers=_bearer(READBACK_TOKEN))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["open"] == 1 and body["requests"][0]["department"] == "pricing"
        assert "PRIVATE-SUBJECT" not in r.text and READBACK_TOKEN not in r.text
        assert r.headers.get("cache-control") == "no-store"


def test_read_only():
    c = _client()
    before = _fingerprint()
    with _env(**{readbackauth.TOKEN_VAR: READBACK_TOKEN, opsauth.TOKEN_VAR: OPS_TOKEN}):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            for h in ({}, _bearer(READBACK_TOKEN), _bearer(OPS_TOKEN)):
                r = c.request(method, URL, headers=h, json={"state": "VERIFIED"})
                assert r.status_code in (401, 403, 405), (method, h, r.status_code)
        for _ in range(3):
            assert c.get(URL, headers=_bearer(READBACK_TOKEN)).status_code == 200
    assert _fingerprint() == before


def test_the_readback_token_opens_no_operator_route():
    c = _client()
    with _env(**{readbackauth.TOKEN_VAR: READBACK_TOKEN, opsauth.TOKEN_VAR: OPS_TOKEN}):
        for path in ("/api/departments", "/api/swarm/runtime"):
            assert c.get(path, headers=_bearer(READBACK_TOKEN)).status_code in (401, 403, 503)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
