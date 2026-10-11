"""W4-B2GATES: owner gates whose evidence nothing in the running system could write.

The audit of the 102 gated Build 2 rows (research/final_build/w4/B2_GATES_AUDIT.md) found
four genuine owner gates whose opening condition reads a record no door in the running system
could write. Each would have stayed closed after the owner did their part:

* `owned_surfaces` (#4 #10 #246 #247 #248 #251 #255): the gate reads `owned_surface.probe`
  rows. Nothing wrote one. `growth.owned_surface.probe` is now run by `ops.capability_probes`.
* `acceptance_ruling` (#189 #221 #222 #320): the gate reads a done OwnerAction under
  `decision.api_vision_equivalence`. Nothing created one. There is now a Command Center action,
  `acceptance.rule`, which needs step-up.
* `ad_authority` (#294 #295): the gate reads SpendLimit('ads'), and `SpendGuard.set_limit` had
  no caller. There is now a Command Center action, `ads.set_limit`. It needs step-up and is
  capped at `paid_media.CONSERVATIVE_CAPS`.
* `tester_roster` (#9 #43 #250): the gate reads a CreatorProfile agreement, and
  `tester_programme.record_agreement` had no caller. There is now an operator route,
  POST /api/tester/agreement.

#244 and #245 cited only a test, so the closure saw no machinery. The registry `proof` now names
commerce/paid_media.py and runtime/growth_ops.py. Their state and parking are unchanged.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_b2gates.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_b2gates_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'g.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "PINTEREST", "BRAMBLELOOP_SITE_URL", "RAILWAY")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-B2GATES harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

OPS = "b" * 40


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/d{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _gate(db, key):
    from brambleloop.build2 import executor

    return executor.GATE_BY_KEY[key].open(db, {})


# ---- owned_surfaces ------------------------------------------------------------------------

def _fake(responses):
    calls = []

    def fetch(url, headers):
        calls.append((url, headers))
        return responses[url] if url in responses else (404, b"")

    return fetch, calls


def test_owned_surface_probe_opens_the_gate_only_on_demonstrated_capability():
    from brambleloop.core.models import AuditLog
    from brambleloop.growth import owned_surface as OS

    db = _db()
    rec = OS.probe(db, env={})
    assert rec["ok"] is False and "no owned surface configured" in rec["reason"]
    assert _gate(db, "owned_surfaces") is False
    url = "https://example.test/.well-known/brambleloop-surface.txt"
    # a site that answers 200 but not with the owner-published marker: not a publish path
    fetch, _ = _fake({url: (200, b"<html>parked domain</html>")})
    rec = OS.probe(db, env={OS.SITE_VAR: "https://example.test/"}, fetch=fetch)
    assert rec["ok"] is False and "does not contain" in rec["reason"]
    assert _gate(db, "owned_surfaces") is False
    fetch, calls = _fake({url: (200, b"brambleloop-owned-surface\n")})
    rec = OS.probe(db, env={OS.SITE_VAR: "https://example.test"}, fetch=fetch)
    assert rec["ok"] is True and rec["working"] == ["site"] and calls[0][0] == url
    assert _gate(db, "owned_surfaces") is True
    # the latest probe decides: a later failure closes it again
    fetch, _ = _fake({url: (503, b"")})
    OS.probe(db, env={OS.SITE_VAR: "https://example.test"}, fetch=fetch)
    assert _gate(db, "owned_surfaces") is False
    with db.session() as s:
        n = s.query(AuditLog).filter(AuditLog.action == OS.PROBE_ACTION).count()
    assert n == 4


def test_pinterest_needs_a_board_and_the_token_is_never_recorded():
    from brambleloop.core.models import AuditLog
    from brambleloop.growth import owned_surface as OS

    db = _db()
    secret = "pina_SECRET_TOKEN_VALUE"
    fetch, calls = _fake({OS.PINTEREST_BOARDS: (200, json.dumps({"items": []}).encode())})
    rec = OS.probe(db, env={OS.PINTEREST_VAR: secret}, fetch=fetch)
    assert rec["ok"] is False and "no board" in rec["reason"]
    assert calls[0][1] == {"Authorization": f"Bearer {secret}"}
    fetch, _ = _fake({OS.PINTEREST_BOARDS: (200, json.dumps({"items": [{"id": "1"}]}).encode())})
    rec = OS.probe(db, env={OS.PINTEREST_VAR: secret}, fetch=fetch)
    assert rec["ok"] is True and "no pin was created" in rec["surfaces"][0]["what_it_shows"]
    assert _gate(db, "owned_surfaces") is True
    with db.session() as s:
        details = [json.dumps(a.detail) for a in s.query(AuditLog).all()]
    assert not any(secret in d for d in details)


def test_capability_probes_handler_runs_the_owned_surface_probe():
    src = (ROOT / "src/brambleloop/runtime/release.py").read_text()
    i = src.index('@handlers.register("ops.capability_probes")')
    body = src[i:i + 4000]
    assert '"owned_surfaces": owned_surface.probe(ctx.db)' in body
    from brambleloop.build2 import executor

    assert "growth.owned_surface.probe" in executor.GATE_BY_KEY["owned_surfaces"].how


# ---- acceptance_ruling + ad_authority (Command Center doors) ------------------------------

def test_acceptance_ruling_door_opens_the_gate_and_refuses_bad_input():
    from brambleloop.app.command_center import approvals as A

    db = _db()
    assert _gate(db, "acceptance_ruling") is False
    for body, why in (({"ruling": "maybe", "reason": "x"}, "ruling must be one of"),
                      ({"ruling": "api_vision_satisfies"}, "reason required")):
        try:
            A.execute(db, "acceptance.rule", body, actor="s_test")
            raise AssertionError("expected a refusal")
        except A.ActionRefused as exc:
            assert why in str(exc), exc
    assert _gate(db, "acceptance_ruling") is False
    out = A.execute(db, "acceptance.rule",
                    {"ruling": "browser_required", "reason": "the wording means a browser"},
                    actor="s_test")
    assert out["result"]["ruling"] == "browser_required" and out["audit_id"]
    assert _gate(db, "acceptance_ruling") is True
    assert A.ACTIONS["acceptance.rule"][0] is True  # step-up required
    card = A._gate_card({"gate": "acceptance_ruling", "what": "w", "how_it_is_checked": "h"})
    rulings = [a["params"]["ruling"] for a in card["actions"] if a["action"] == "acceptance.rule"]
    assert sorted(rulings) == sorted(A.ACCEPTANCE_RULINGS) and card["executable"] is True


def test_ads_limit_door_is_capped_and_spends_nothing():
    from brambleloop.app.command_center import approvals as A
    from brambleloop.commerce.paid_media import CONSERVATIVE_CAPS as caps
    from brambleloop.core.models import CostEntry, SpendLimit

    db = _db()
    assert _gate(db, "ad_authority") is False
    for body in ({"daily_cap_cad": caps.daily_cad + 0.01, "lifetime_cap_cad": 10, "reason": "r"},
                 {"daily_cap_cad": 2, "lifetime_cap_cad": caps.campaign_cad + 1, "reason": "r"},
                 {"daily_cap_cad": 0, "lifetime_cap_cad": 10, "reason": "r"},
                 {"daily_cap_cad": 2, "lifetime_cap_cad": 1, "reason": "r"},
                 {"daily_cap_cad": 2, "lifetime_cap_cad": 10}):
        try:
            A.execute(db, "ads.set_limit", body, actor="s_test")
            raise AssertionError(f"expected a refusal for {body}")
        except A.ActionRefused:
            pass
    assert _gate(db, "ad_authority") is False
    out = A.execute(db, "ads.set_limit", {"daily_cap_cad": caps.daily_cad,
                                          "lifetime_cap_cad": caps.campaign_cad,
                                          "reason": "listing is ready to sell"}, actor="s_test")
    assert out["result"]["spent"] == 0.0
    assert _gate(db, "ad_authority") is True
    with db.session() as s:
        lim = s.query(SpendLimit).filter(SpendLimit.scope == "ads").one()
        assert lim.daily_cap_cad == caps.daily_cad and lim.lifetime_cap_cad == caps.campaign_cad
        assert s.query(CostEntry).count() == 0
    card = A._gate_card({"gate": "ad_authority", "what": "w", "how_it_is_checked": "h"})
    act = [a for a in card["actions"] if a["action"] == "ads.set_limit"][0]
    assert act["requires_step_up"] and act["params"]["daily_cap_cad"] == caps.daily_cad


# ---- tester_roster (operator intake route) ------------------------------------------------

def test_tester_agreement_route_opens_the_gate_only_with_consent():
    from fastapi.testclient import TestClient

    from brambleloop.app import main
    from brambleloop.core import opsauth

    os.environ[opsauth.TOKEN_VAR] = OPS
    main.db.create_all()
    c = TestClient(main.app)
    good = {"handle_ref": "ravelry:tester-one", "specialties": ["home_decor"],
            "express_consent": True, "consent_source": "Ravelry DM 2026-10-11, kept in inbox"}
    assert c.post("/api/tester/agreement", json=good).status_code == 401
    h = {"Authorization": f"Bearer {OPS}"}
    assert _gate(main.db, "tester_roster") is False
    r = c.post("/api/tester/agreement", json={**good, "express_consent": "yes"}, headers=h)
    assert r.status_code == 400 and "express consent" in r.json()["error"], r.text
    r = c.post("/api/tester/agreement", json={**good, "consent_source": ""}, headers=h)
    assert r.status_code == 400, r.text
    assert _gate(main.db, "tester_roster") is False
    r = c.post("/api/tester/agreement", json=good, headers=h)
    assert r.status_code == 200 and r.json()["recorded"] is True, r.text
    assert _gate(main.db, "tester_roster") is True


# ---- evidence mapping ---------------------------------------------------------------------

def test_244_245_name_their_machinery_and_stay_data_gated():
    from brambleloop.build2 import closure, requirements as reg

    by = {r.id: r for r in reg.load()}
    for rid in (244, 245):
        r = by[rid]
        assert "commerce/paid_media.py" in r.proof and "runtime/growth_ops.py" in r.proof
        row = closure.classify(r, gate_open={"customers": False})
        assert row["state"] == closure.DATA_GATED and row["gate"] == "customers", row["why"]
        assert "commerce/paid_media.py" in row["proof"]["existing"]
        assert row["proof"]["reached"], row["proof"]


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
