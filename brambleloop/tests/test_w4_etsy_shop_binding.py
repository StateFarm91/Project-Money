"""W4-ETSYSHOPID: the shop id is resolved from the owner's own grant, read-only, and bound
only when the shop is BrambleloopStudio.

Everything runs against a stub transport that records every request. Nothing here reaches
Etsy; the only POST any test allows is the OAuth token endpoint's refresh grant.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="shopbind_")
for _k in list(os.environ):
    if _k.startswith(("ETSY", "BRAMBLELOOP_SECRET_KEY")):
        os.environ.pop(_k)

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core import oauth_store  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, Job, Phase  # noqa: E402
from brambleloop.integrations import etsy_shop_binding, http as etsy_http  # noqa: E402
from brambleloop.integrations.etsy import Credentials, Response  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import etsy_ops  # noqa: E402
from brambleloop.runtime.worker import JobContext  # noqa: E402

SEAL = "s" * 48
ENV = {"ETSY_KEYSTRING": "fakekeystring", "ETSY_SHARED_SECRET": "fakesecret",
       "BRAMBLELOOP_SECRET_KEY": SEAL}
SCOPES = "listings_r listings_w listings_d shops_r shops_w transactions_r"
USER_ID = "424242"
SHOP_ID = "55501234"
_N = [0]


class StubEtsy:
    """Answers the refresh grant, getMe and getShopByOwnerUserId; records everything."""

    def __init__(self, *, shop_name: str = "BrambleloopStudio", scope_in_refresh: bool = False):
        self.shop_name = shop_name
        self.scope_in_refresh = scope_in_refresh
        self.requests: list[tuple[str, str]] = []
        self.refreshes = 0

    def request(self, method, url, *, headers, json=None, form=None, multipart=None):
        self.requests.append((method, url))
        if method == "POST" and "oauth/token" in url:
            self.refreshes += 1
            body = {"access_token": f"{USER_ID}.access-{self.refreshes}",
                    "token_type": "Bearer", "expires_in": 3600,
                    "refresh_token": f"{USER_ID}.refresh-{self.refreshes + 1}"}
            if self.scope_in_refresh:
                body["scope"] = SCOPES
            return Response(200, body)
        assert method == "GET", f"a write reached the transport: {method} {url}"
        assert headers.get("Authorization", "").startswith(f"Bearer {USER_ID}.access-")
        if url.endswith("/users/me"):
            return Response(200, {"user_id": int(USER_ID), "shop_id": int(SHOP_ID)})
        if url.endswith(f"/users/{USER_ID}/shops"):
            return Response(200, {"shop_id": int(SHOP_ID), "shop_name": self.shop_name,
                                  "user_id": int(USER_ID)})
        if url.endswith(f"/shops/{SHOP_ID}"):
            return Response(200, {"shop_id": int(SHOP_ID), "shop_name": self.shop_name})
        return Response(404, {"error": f"stub has no {url}"})

    def writes(self) -> list[tuple[str, str]]:
        return [(m, u) for m, u in self.requests if m != "GET" and "oauth/token" not in u]


def _db() -> Database:
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_N[0]}.db")
    db.create_all()
    return db


def _granted(db, token: str = f"{USER_ID}.refresh-1") -> None:
    oauth_store.save_refresh_token(db, token, scopes=SCOPES, source="authorization-code grant",
                                   new_grant=True, env=ENV)


def _audits(db, action: str) -> list[dict]:
    with db.session() as s:
        return [dict(r.detail or {}) for r in
                s.scalars(select(AuditLog).where(AuditLog.action == action))]


def _open_incidents(db) -> list[Incident]:
    with db.session() as s:
        return list(s.scalars(select(Incident).where(
            Incident.signature == etsy_shop_binding.INCIDENT_SIGNATURE,
            Incident.resolved == False)))  # noqa: E712


def test_a_stored_grant_resolves_the_shop_persists_it_and_audits_no_token():
    db = _db()
    _granted(db)
    stub = StubEtsy()
    assert Credentials.from_env(ENV, transport=stub, db=db) is None   # the production defect
    creds = etsy_shop_binding.ensure_credentials(db, transport=stub, env=ENV)
    assert creds is not None and creds.shop_id == SHOP_ID
    assert oauth_store.load_shop_binding(db)["shop_name"] == "BrambleloopStudio"
    assert stub.refreshes == 1 and not stub.writes()
    rows = _audits(db, "etsy.shop_resolved")
    assert len(rows) == 1 and rows[0]["shop_id"] == SHOP_ID
    assert rows[0]["how"] == "access_token_prefix + getShopByOwnerUserId"
    blob = repr(rows)
    assert "access-" not in blob and "refresh-" not in blob, "a token reached the audit row"
    # The rotation the resolution caused was persisted (compare-and-set) ...
    assert oauth_store.load_refresh_token(db, env=ENV) == f"{USER_ID}.refresh-2"
    # ... and a later build reads the stored shop: no second resolution.
    again = Credentials.from_env(ENV, transport=stub, db=db)
    assert again is not None and again.shop_id == SHOP_ID
    calls_before = len(stub.requests)
    assert etsy_shop_binding.ensure_credentials(db, transport=stub, env=ENV).shop_id == SHOP_ID
    assert not any("/users/" in u for _, u in stub.requests[calls_before:])


def test_the_resolved_credentials_can_read_the_shop_after_the_refresh():
    db = _db()
    _granted(db)
    stub = StubEtsy()
    creds = etsy_shop_binding.ensure_credentials(db, transport=stub, env=ENV)
    from brambleloop.integrations.etsy import EtsyClient

    client = EtsyClient(stub, credentials=creds, phase="shadow")
    assert client.get_me()["shop_id"] == int(SHOP_ID)     # shops_r known after a refresh
    assert client.get_shop()["shop_name"] == "BrambleloopStudio"
    assert stub.refreshes == 1, "the bound credentials reused the provider, no second refresh"
    assert not stub.writes()


def test_the_environment_shop_id_wins_and_nothing_is_resolved():
    db = _db()
    _granted(db)
    stub = StubEtsy()
    env = dict(ENV, ETSY_SHOP_ID="999")
    creds = etsy_shop_binding.ensure_credentials(db, transport=stub, env=env)
    assert creds is not None and creds.shop_id == "999"
    assert stub.requests == [] and oauth_store.load_shop_binding(db) is None
    oauth_store.save_shop_binding(db, shop_id=SHOP_ID, shop_name="BrambleloopStudio")
    assert Credentials.from_env(env, transport=stub, db=db).shop_id == "999"


def test_a_different_shop_is_refused_with_an_incident_and_never_bound():
    db = _db()
    _granted(db)
    stub = StubEtsy(shop_name="SomebodyElsesShop")
    assert etsy_shop_binding.ensure_credentials(db, transport=stub, env=ENV) is None
    assert oauth_store.load_shop_binding(db) is None
    assert Credentials.from_env(ENV, transport=stub, db=db) is None
    incidents = _open_incidents(db)
    assert len(incidents) == 1 and "SomebodyElsesShop" in incidents[0].summary
    assert _audits(db, "etsy.shop_resolution_refused")
    assert not _audits(db, "etsy.shop_resolved")
    assert not stub.writes()


def test_no_token_is_unchanged_none_and_no_request():
    db = _db()
    stub = StubEtsy()
    assert etsy_shop_binding.ensure_credentials(db, transport=stub, env=ENV) is None
    assert Credentials.from_env(ENV, transport=stub, db=db) is None
    assert Credentials.from_env(ENV, transport=stub) is None
    assert stub.requests == []


def test_a_rotation_by_another_worker_is_not_overwritten_and_the_next_build_resolves():
    db = _db()
    _granted(db)
    stub = StubEtsy()
    unbound = Credentials.from_env(ENV, transport=stub, db=db, require_shop=False)
    # Another worker rotates first: this process's compare-and-set must lose, not overwrite.
    oauth_store.save_refresh_token(db, f"{USER_ID}.refresh-9", source="refresh grant",
                                   expected_fingerprint=None, env=ENV)
    assert unbound.token_provider.token(operation="getMe")
    assert oauth_store.load_refresh_token(db, env=ENV) == f"{USER_ID}.refresh-9"
    # A provider loaded from the store again works, and the resolver binds after its refresh.
    stub2 = StubEtsy()
    stub2.refreshes = 8      # the stub's next issue is refresh-10, rotating refresh-9
    creds = etsy_shop_binding.ensure_credentials(db, transport=stub2, env=ENV)
    assert creds is not None and creds.shop_id == SHOP_ID
    assert oauth_store.load_refresh_token(db, env=ENV) == f"{USER_ID}.refresh-10"


def test_build_client_and_the_daily_credential_health_job_bind_the_shop():
    db = _db()
    Registry(db).seed_defaults()
    _granted(db)
    stub = StubEtsy()
    original = etsy_http.UrllibTransport
    saved = {k: os.environ.get(k) for k in ENV}
    os.environ.update(ENV)
    etsy_http.UrllibTransport = lambda: stub
    try:
        job = JobQueue(db).enqueue("orchestrator", "etsy.credential_health", {},
                                   idempotency_key=f"t:{time.time_ns()}")
        with db.session() as s:
            row = s.get(Job, job.id)
            s.expunge(row)
        ctx = JobContext(job=row, db=db, queue=JobQueue(db), registry=Registry(db),
                         phase=Phase.SHADOW)
        out = etsy_ops.handle_credential_health(ctx)
        client = etsy_ops.build_client(db, "shadow")
    finally:
        etsy_http.UrllibTransport = original
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    assert out["status"] == "HEALTHY", out
    assert client.credentials is not None and client.credentials.shop_id == SHOP_ID
    assert len(_audits(db, "etsy.shop_resolved")) == 1
    assert not stub.writes()


def test_presence_checks_accept_the_verified_binding_and_stay_honest_without_one():
    from brambleloop.build2 import executor
    from brambleloop.ops import dependencies
    from brambleloop.store_foundation import store_readiness

    bare = {"ETSY_KEYSTRING": "fakekeystring", "BRAMBLELOOP_SECRET_KEY": SEAL}
    etsy_dep = next(d for d in dependencies.DEPENDENCIES if d.key == "etsy_account")
    gate = next(g for g in executor.GATES if g.key == "etsy_shop")

    def checks(db):
        return {
            "id": etsy_shop_binding.shop_id_present(db, bare),
            "creds": etsy_shop_binding.credentials_present(db, bare),
            "dep": etsy_dep.present(bare, db),
            "gate_id": executor._shop_id_known(db, bare),
            "store": store_readiness._env_presence(bare, db)["ETSY_SHOP_ID"],
        }

    # Neither env var nor binding: every check says absent.
    db = _db()
    _granted(db)
    assert not any(checks(db).values()), checks(db)
    assert etsy_dep.present(bare) is False and etsy_dep.to_dict(bare)["configured"] is False
    # A binding whose name is not the expected shop is not a shop id (defence in depth).
    oauth_store.save_shop_binding(db, shop_id="777", shop_name="SomebodyElsesShop")
    assert not any(checks(db).values()), checks(db)
    assert Credentials.from_env(ENV, transport=StubEtsy(), db=db) is None
    # The verified binding plus the stored grant: equivalent to ETSY_SHOP_ID.
    oauth_store.save_shop_binding(db, shop_id=SHOP_ID, shop_name="BrambleloopStudio")
    assert all(checks(db).values()), checks(db)
    assert dependencies.map_state(db, bare)["dependencies"][
        [r["key"] for r in dependencies.map_state(db, bare)["dependencies"]].index(
            "etsy_account")]["configured"] is True
    # The gate still also needs a recorded successful probe: the binding is not a capability.
    assert gate.open(db, bare) == bool(executor._etsy_usable(db, bare))
    # The env var alone, with no db, still works as before.
    assert etsy_shop_binding.shop_id_present(None, dict(bare, ETSY_SHOP_ID="9"))
    assert not etsy_shop_binding.credentials_present(None, bare)


def test_launch_readiness_counts_the_bound_grant_as_a_credential():
    from brambleloop.launch import readiness

    saved = {k: os.environ.get(k) for k in ENV}
    os.environ.update(ENV)
    try:
        def etsy_item(db):
            return next(r for r in readiness.assess(db, phase="shadow").requirements
                        if r.key == "etsy_integration")

        db = _db()
        Registry(db).seed_defaults()
        _granted(db)
        absent = etsy_item(db)
        oauth_store.save_shop_binding(db, shop_id=SHOP_ID, shop_name="BrambleloopStudio")
        bound = etsy_item(db)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    assert absent.evidence["credentials_present"] is False
    assert bound.evidence["credentials_present"] is True
    # Still not ready: the round trip has not been proven. Presence is not proof.
    assert bound.ready is False


def _run_all() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
            import traceback

            traceback.print_exc()
        else:
            print(f"OK   {name}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run_all() else 0)
