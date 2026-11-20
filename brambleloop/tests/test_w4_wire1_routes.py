"""WIRE1: the routes and hooks the C08 / C12 clusters left for app-owned files.

* F-748 / F-680 -- `GET /api/visual/studio` and `GET /api/visual/evidence/{slug}` are operator
  reads (never public); the owner reads the same models at `/api/cc/visual/...` (owner session).
* C12 owner entry -- `/api/cc/etsy/...` in `commerce.estate_api`: owner session for reads,
  owner session + step-up for every write (each records the owner's attestation of a Shop
  Manager page), with the signed-in owner audited; the operator token is not an owner session.
* F-527 -- `store_foundation.asset_health.check` carries the held-brand-asset sweep.
* F-733 -- the Laura reference stage resolves her from `visual.canonical_registry`.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_wire1_routes.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_wire1_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'w.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center.models import OwnerSession  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402

OPS = "w" * 40
PASS = "owner passphrase for the wire1 harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
os.environ.pop(auth.TOTP_VAR, None)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
NOW = datetime.now(timezone.utc)

VISUAL = {"/api/visual/studio": "/api/visual/studio",
          "/api/visual/evidence/{slug}": "/api/visual/evidence/cloudline-baby-blanket"}
CC_GET = ["/api/cc/visual/studio", "/api/cc/visual/evidence/cloudline-baby-blanket",
          "/api/cc/etsy/search-visibility", "/api/cc/etsy/registers",
          "/api/cc/etsy/listing/123/learning-window"]
SHARED = {"observed_at": (NOW - timedelta(hours=1)).isoformat(), "complete": True,
          "statement": "Shared Access shows one person",
          "items": [{"label": "helper", "permissions": ["listings"], "needs": ["listings"],
                     "granted_on": "2026-09-01",
                     "last_activity_on": (NOW - timedelta(days=2)).isoformat()}]}
CC_POST = {"/api/cc/etsy/registers/shared_access": SHARED,
           "/api/cc/etsy/dashboard/kpi-snapshot": {"start": "2026-09-01", "end": "2026-09-30",
                                                   "owner_reading": {"views": 10, "visits": 4,
                                                                     "read_on": "2026-10-01"}},
           "/api/cc/etsy/dashboard/traffic-sources": {
               "start": "2026-09-01", "end": "2026-09-30", "exported_on": "2026-10-01",
               "text": "Source,Visits\nEtsy search,12\n"},
           "/api/cc/etsy/search-visibility/1/remediated": {"ref": "commit abc"},
           "/api/cc/etsy/listing/123/learning-capture": {"day": 0, "source": "x"},
           "/api/cc/etsy/registers/apps": {"items": []}}


def anon():
    return TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)


def session():
    c = anon()
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def post(c, csrf, path, body):
    return c.post(path, json=body, headers={"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
                                            "X-CC-Timestamp": str(int(time.time()))})


def _expire_stepup(c):
    sid = c.get("/api/cc/auth/status").json()["session"]["session_id"]
    with DB.session() as s:
        s.scalar(select(OwnerSession).where(OwnerSession.public_id == sid)).stepup_until = (
            auth._now() - timedelta(seconds=1))


def test_visual_routes_are_operator_only_and_serve_the_read_models():
    for route, url in VISUAL.items():
        assert route not in security.PUBLIC_GET_ROUTES
        assert route in security.OPERATOR_GET_ROUTES
        assert security.requires_operator("GET", route)
        assert anon().get(url).status_code == 401, url
        assert anon().get(url, headers={"authorization": "Bearer wrong" + "x" * 30}
                          ).status_code == 401
        r = anon().get(url, headers={"authorization": f"Bearer {OPS}"})
        assert r.status_code == 200, (url, r.text[:300])
    body = anon().get("/api/visual/studio", headers={"authorization": f"Bearer {OPS}"}).json()
    for k in ("canonical", "best_provider_mode", "recent_yield", "rejected_drift_examples",
              "active_improvement_experiments", "listing_images"):
        assert k in body, k
    assert body["canonical"]["identity_id"].startswith("laura-r")
    ev = anon().get(VISUAL["/api/visual/evidence/{slug}"],
                    headers={"authorization": f"Bearer {OPS}"}).json()
    for k in ("real_benchmark_reference", "brambleloop_3d", "conditioning_passes",
              "generated_candidates", "rejected_candidates", "final_approved_asset"):
        assert k in ev, k


def test_cc_routes_refuse_anyone_without_the_owner_session_and_serve_the_owner():
    for path in CC_GET:
        assert security.owner_session_route(path)
        assert anon().get(path).status_code in (401, 403), path
        # the shared operator token is not an owner session
        assert anon().get(path, headers={"authorization": f"Bearer {OPS}"}
                          ).status_code in (401, 403), path
    for path, body in CC_POST.items():
        assert anon().post(path, json=body).status_code in (401, 403), path
    c, _csrf = session()
    for path in CC_GET:
        r = c.get(path)
        assert r.status_code == 200, (path, r.text[:300])
    regs = c.get("/api/cc/etsy/registers").json()
    assert set(regs) == {"apps", "shared_access", "partners"}
    sv = c.get("/api/cc/etsy/search-visibility").json()
    assert set(sv) == {"areas", "aging"}


def test_cc_writes_need_step_up_record_the_owner_and_refuse_bad_readings():
    from brambleloop.app.command_center.models import SecurityEvent

    c, csrf = session()
    _expire_stepup(c)
    for path, body in CC_POST.items():
        r = post(c, csrf, path, body)
        assert r.status_code == 403 and r.json().get("code") == "STEP_UP_REQUIRED", (path, r.text)
    assert post(c, csrf, "/api/cc/auth/step-up", {"passphrase": PASS}).status_code == 200
    r = post(c, csrf, "/api/cc/etsy/registers/shared_access", SHARED)
    assert r.status_code == 200, r.text
    r = post(c, csrf, "/api/cc/etsy/dashboard/kpi-snapshot",
             CC_POST["/api/cc/etsy/dashboard/kpi-snapshot"])
    assert r.status_code == 200 and r.json()["visits"]["value"] == 4, r.text
    r = post(c, csrf, "/api/cc/etsy/dashboard/traffic-sources",
             CC_POST["/api/cc/etsy/dashboard/traffic-sources"])
    assert r.status_code == 200, r.text
    # refusals are 400 with the module's reason, never a 500 and never recorded
    for path, body in (("/api/cc/etsy/registers/apps", {"items": [{"name": "Mystery"}],
                                                         "observed_at": NOW.isoformat(),
                                                         "complete": True, "statement": "x"}),
                       ("/api/cc/etsy/listing/123/learning-capture",
                        {"day": 0, "source": "x", "evidence": "e",
                         "observed_at": NOW.isoformat()}),
                       ("/api/cc/etsy/search-visibility/999/remediated", {"ref": ""})):
        r = post(c, csrf, path, body)
        assert r.status_code == 400, (path, r.status_code, r.text)
    assert post(c, csrf, "/api/cc/etsy/registers/nope", {}).status_code == 404
    regs = c.get("/api/cc/etsy/registers").json()
    with DB.session() as s:
        acts = [e.detail.get("action") for e in s.scalars(select(SecurityEvent).where(
            SecurityEvent.outcome == "ok")) if isinstance(e.detail, dict)]
    assert "etsy.register.shared_access" in acts and "etsy.dashboard.kpi_snapshot" in acts


def test_f527_storefront_asset_health_carries_the_held_brand_asset_sweep():
    import shutil

    from brambleloop.brand import asset_consistency as AC
    from brambleloop.store_foundation import asset_health as AH

    out = AH.check(DB)
    assert out["held_brand_assets"]["marks_checked"] >= 10
    assert out["live_colour_typography"] == "UNMEASURED"
    d = Path(_TMP) / "marks"
    shutil.copytree(AC.MASTERS, d)
    victim = sorted(d.glob("*-colour.svg"))[0]
    victim.write_text(victim.read_text() + '<text x="0">B</text>')
    saved = AC.MASTERS
    AC.MASTERS = d
    try:
        out = AH.check(DB)
    finally:
        AC.MASTERS = saved
    f = [x for x in out["findings"] if x["code"] == "MARK_LIVE_TEXT"]
    assert f and f[0]["route_to"] == "storefront_director"
    assert out["held_brand_assets"]["fixes"] == 1


def test_f733_the_laura_reference_stage_resolves_her_from_the_registry():
    import inspect

    from brambleloop.visual import image_production as IP

    src = inspect.getsource(IP)
    stage = src[src.index('if stage == "load_laura_references":'):
                src.index('if stage == "reserve_outfit":')]
    assert "canonical_registry.resolve(db)" in stage
    assert "canonical.IDENTITY_ID" not in stage and "canonical.verify()" not in stage


def test_the_route_contract_pin_moved_with_a_declaration():
    from brambleloop.core import contract_pins as C

    got = C.fingerprints()["api_routes"]
    changes = (ROOT.parent / "ops" / "CONTRACT_CHANGES.md").read_text()
    assert f"| {got} |" in changes, got


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
