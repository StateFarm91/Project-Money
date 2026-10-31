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

Follow-up 1. The eight registry data_gated rows (#23 #82 #89 #94 #98 #140 #296 #298) showed no
gate, only a sentence of prose. Each now has a named data gate in `executor.DATA_GATE_FOR`. The
gate reads the runtime record that row's own machinery reads, at that machinery's minimum. Its
state is unchanged while the gate is closed.

Follow-up 2. #35 and #39 are classified OWNER-GATED, because in practice a person opens them by
reading the owner's policy pages. `kind_of('rendered_pages')` stays EXTERNAL.

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
            "express_consent": True, "consent_source": "Ravelry DM 2026-10-11, kept in inbox",
            # SECREVIEW R6: the tester terms are mandatory on this route.
            "relationship": "none", "qualification": "https://www.ravelry.com/projects/x/y"}
    assert c.post("/api/tester/agreement", json=good).status_code == 401
    h = {"Authorization": f"Bearer {OPS}"}
    assert _gate(main.db, "tester_roster") is False
    r = c.post("/api/tester/agreement", json={**good, "express_consent": "yes"}, headers=h)
    assert r.status_code == 400 and "express consent" in r.json()["error"], r.text
    r = c.post("/api/tester/agreement", json={**good, "consent_source": ""}, headers=h)
    assert r.status_code == 400, r.text
    # SECREVIEW R6: missing or disallowed independence/qualification is refused (400).
    for bad in ({k: v for k, v in good.items() if k != "relationship"},
                {k: v for k, v in good.items() if k != "qualification"},
                {**good, "relationship": "my husband"},
                {**good, "relationship": "my mom"},
                {**good, "relationship": "coworker"},
                {**good, "qualification": "  "}):
        r = c.post("/api/tester/agreement", json=bad, headers=h)
        assert r.status_code == 400, (bad, r.text)
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


# ---- the eight prose-only data gates, now named and checkable ------------------------------

def test_every_registry_data_gated_row_has_a_named_checkable_gate():
    from brambleloop.build2 import closure, executor, requirements as reg

    data_rows = sorted(r.id for r in reg.load() if r.status == reg.DATA_GATED)
    assert data_rows == sorted(executor.DATA_GATE_FOR), (data_rows, executor.DATA_GATE_FOR)
    for rid, key in executor.DATA_GATE_FOR.items():
        assert key in closure.DATA_GATES and closure.kind_of(key) == closure.DATA_GATED
        g = executor.GATE_BY_KEY[key]
        assert g.what and g.how and g.requirement_ids == ()  # owner-gate table untouched
    db = _db()
    led = closure.ledger(db)
    rows = {r["id"]: r for r in led["rows"]}
    for rid, key in executor.DATA_GATE_FOR.items():
        r = rows[rid]
        assert r["state"] == "DATA-GATED", (rid, r["state"])  # no status change, gates closed
        assert r["gate"]["key"] == key and r["gate"]["kind"] == closure.DATA_GATED
        assert r["gate"]["state"] == "closed" and r["gate"]["opens_when"]
    # the owner queue lists them as data waits with the rows they hold, never as cards
    inbox = executor.approval_inbox(db, env={})
    waits = {d["gate"]: d["unblocks"] for d in inbox["waiting_on_data"]}
    for rid, key in executor.DATA_GATE_FOR.items():
        assert rid in waits.get(key, []), (key, waits.get(key))
    assert not {c["gate"] for c in inbox["cards"]} & set(executor.DATA_GATE_FOR.values())


def _order(s, ref, slug, **detail):
    from brambleloop.core.models import Customer, Order

    c = Customer(customer_ref=f"c-{ref}")
    s.add(c)
    s.flush()
    s.add(Order(customer_id=c.id, external_ref=ref, product_slug=slug, price_cad=20.0,
                revenue_cad=20.0, detail={"state": "paid", **detail}))


def test_each_data_gate_opens_on_its_real_record_at_the_machinerys_minimum():
    from datetime import datetime, timezone

    from brambleloop.core.models import (CultureObservation, LearningObservation,
                                         ListingOutcome, SeasonHarvest)

    db = _db()
    keys = ("listing_traffic", "style_outcomes", "concept_outcomes", "market_outcomes",
            "learning_sources", "lead_lag_series", "seasonal_orders", "season_harvest")
    assert not any(_gate(db, k) for k in keys)

    def outcome(slug, impressions, visits, style="flat-lay"):
        return ListingOutcome(product_slug=slug, period_start="2026-10-01",
                              period_end="2026-10-07", impressions=impressions, visits=visits,
                              hero_style=style, source="etsy stats (test)")

    with db.session() as s:
        s.add(outcome("a", 50, 0))
    assert not _gate(db, "listing_traffic")  # impressions without a visit are not traffic
    with db.session() as s:
        s.add(outcome("b", 60, 5))
    assert _gate(db, "listing_traffic") and not _gate(db, "market_outcomes")
    assert not _gate(db, "style_outcomes")  # 2 listings, 110 impressions
    with db.session() as s:
        s.add(outcome("c", 100, 5))
    assert _gate(db, "style_outcomes")  # 3 listings, 210 impressions on one style
    with db.session() as s:
        _order(s, "o-1", "b")
    assert _gate(db, "market_outcomes") and not _gate(db, "concept_outcomes")
    with db.session() as s:
        s.add(outcome("d", 0, 190))
        for i in range(2, 21):
            _order(s, f"o-{i}", "b")
        _order(s, "o-unpaid", "b", state="unpaid")  # not countable, never counted
    assert _gate(db, "concept_outcomes")  # 200 visits, 20 countable orders
    assert not _gate(db, "seasonal_orders")  # every order so far is unassigned
    with db.session() as s:
        _order(s, "o-xmas", "b", season="Christmas")
    assert _gate(db, "seasonal_orders")
    now = datetime.now(timezone.utc)
    with db.session() as s:
        s.add(LearningObservation(domain="techniques", source="craft (test)", citation="c1",
                                  observed_on=now, summary="s"))
    assert not _gate(db, "learning_sources")
    with db.session() as s:
        s.add(LearningObservation(domain="customer_pain", source="reviews (test)",
                                  citation="c2", observed_on=now, summary="s"))
    assert _gate(db, "learning_sources")
    with db.session() as s:
        for ch, on in (("reference", "2026-09-01"), ("reference", "2026-09-08"),
                       ("etsy", "2026-09-01")):
            s.add(CultureObservation(signal_key="topic:test", channel=ch, observed_on=on,
                                     interest=1.0, source="test"))
    assert not _gate(db, "lead_lag_series")  # one marketplace reading cannot lead anything
    with db.session() as s:
        s.add(CultureObservation(signal_key="topic:test", channel="etsy",
                                 observed_on="2026-09-15", interest=2.0, source="test"))
    assert _gate(db, "lead_lag_series")
    with db.session() as s:
        s.add(SeasonHarvest(event="Christmas", occurrence="2025-12-25", status="not_passed"))
    assert not _gate(db, "season_harvest")
    with db.session() as s:
        s.add(SeasonHarvest(event="Valentine's Day", occurrence="2026-02-14",
                            status="measured"))
    assert _gate(db, "season_harvest")


def test_an_opened_data_gate_unparks_its_row_and_a_closed_one_keeps_it_data_gated():
    from brambleloop.build2 import closure, requirements as reg

    r = {x.id: x for x in reg.load()}[298]
    assert closure.classify(r, gate_open={"season_harvest": False})["state"] == closure.DATA_GATED
    row = closure.classify(r, gate_open={"season_harvest": True})
    assert row["state"] == closure.OPEN and "season_harvest has opened" in row["why"]
    unchecked = closure.classify(r)
    assert unchecked["state"] == closure.DATA_GATED and "NOT checked live" in unchecked["why"]


# ---- #35 / #39: classified by who opens the gate ------------------------------------------

def test_35_39_are_owner_gated_by_a_person_reading_the_policy_pages():
    from brambleloop.build2 import closure, executor, requirements as reg

    by = {x.id: x for x in reg.load()}
    for rid in (35, 39):
        row = closure.classify(by[rid], gate_open={"rendered_pages": False})
        assert row["gate"] == "rendered_pages" and row["state"] == closure.OWNER_GATED
        assert "the owner" in row["opened_by"] and "POST /api/policy/snapshot" in row["opened_by"]
        assert row["gate_kind_of"] == closure.EXTERNAL_BLOCKED  # gate kind itself unchanged
    led = closure.ledger(gate_open={"rendered_pages": False}, gate_source="test")
    rows = {r["id"]: r for r in led["rows"]}
    for rid in (35, 39):
        assert rows[rid]["state"] == "OWNER-GATED"
        assert rows[rid]["gate"]["kind"] == closure.OWNER_GATED
        assert "policy_page_reading" in rows[rid]["gate"]["opened_by"]
    # the person path is real: the owner decision names it and the gate's check reads it
    from brambleloop.ops import owner_queue as Q

    assert "/api/policy/snapshot" in Q.DECISION_BY_GATE["rendered_pages"]["decision"]
    assert "page_readings_status" in executor.GATE_BY_KEY["rendered_pages"].how or \
        "POST /api/policy/snapshot" in executor.GATE_BY_KEY["rendered_pages"].how


# ---- invariant: an owner card claims only rows its action can actually open ---------------

def test_every_owner_card_unblocks_only_rows_parked_on_its_own_gate():
    """W4-B2GATES (#94). The model_provider card said it unblocked #94; the ledger parks #94
    on the data gate market_outcomes (a sale), which no API key opens. For every owner card,
    each row in `unblocks` must be a ledger row whose gate key IS the card's gate, and the
    decision batches built from the cards must make the same claim."""
    from brambleloop.build2 import closure, executor

    db = _db()
    rows = {r["id"]: r for r in closure.ledger(db)["rows"]}
    inbox = executor.approval_inbox(db, env={})
    cards = [c for c in inbox["cards"] if c.get("gate")]
    assert cards, "expected owner cards on a fresh database"
    for c in cards:
        assert c["unblocks"], c["gate"]
        for rid in c["unblocks"]:
            g = (rows[rid].get("gate") or {}).get("key")
            assert g == c["gate"], (c["gate"], rid, g, rows[rid]["state"])
    card_gate = {c["gate"]: set(c["unblocks"]) for c in cards}
    for b in inbox["batches"]["batches"]:
        for item in b["items"]:
            for rid in item["unblocks"]:
                if not isinstance(rid, int):
                    continue  # a merged legacy row's requirement key, not a ledger row
                g = (rows[rid].get("gate") or {}).get("key")
                assert g in item["gates"] and rid in card_gate.get(g, set()), (item["id"], rid, g)
    # the specific defect: #94 is claimed by nothing an owner act opens
    assert all(94 not in c["unblocks"] for c in cards)
    assert executor.gate_for(94) is None and 94 not in executor.gated_requirements()
    assert rows[94]["gate"]["key"] == "market_outcomes"
    # and model_provider, which now unblocks nothing, is listed as such, not asked
    assert "model_provider" not in card_gate
    assert "model_provider" in {s["gate"] for s in inbox.get("suppressed_unblocks_nothing")
                                or []}, sorted(inbox)


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
