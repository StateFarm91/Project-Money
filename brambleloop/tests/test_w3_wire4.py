"""W3-WIRE4: the integrator wiring requests from wave-3 lanes K7, D, K11, F, B2, K1/K4.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_wire4.py

* K11  -- `/api/cc/authority/approve/{key}` and `/api/cc/authority/grant` are default-deny,
          step-up guarded, audited, and reach `authority.dag.approve` / `authority.policy.grant`;
          the two authority providers are wired; `create_all` registers the tables.
* F-5  -- an owner action with an UNKNOWN cost: stored with basis UNKNOWN, served as null,
          rendered "UNKNOWN", never CA$0.00, never batched as free, and Finance refuses to
          treat it as spend authority. The Laura voice listening action is in the one queue.
* K7   -- /api/owner-actions carries the packet fields, empty_state and parked; the dashboard
          says "nothing is waiting" only when the empty-queue guard proves it; table as-of.
* D    -- the four WORK_KEYS are declared in runtime/pipeline.py itself.
* B2   -- invariants protect the canonical brand assets; the banner's per-surface owner
          approval is scoped to one sha on one surface and flips nothing global.
* K1/K4 -- generators.provider_module resolves the two Command Center modules statically.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import w3_laura_cc_harness as H  # noqa: E402  (isolated DB, shadow, no network)

from sqlalchemy import select  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import providers  # noqa: E402

DB = H.DB
SRC = H.ROOT / "src" / "brambleloop"
BANNER_SHA = "048a199133f7589cc243cb876a7ee5b0f68b5d6530929a922c79de9eda64eb98"


def _ops() -> dict:
    return {"Authorization": "Bearer " + H.OPS}


# ---- K11 --------------------------------------------------------------------------------

def test_k11_create_all_registers_authority_tables():
    tree = ast.parse((SRC / "core" / "db.py").read_text())
    mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert "authority" in mods, mods
    from sqlalchemy import inspect

    names = set(inspect(DB.engine).get_table_names())
    assert {"authority_policies", "company_work_items"} <= names, sorted(names)[:5]


def test_k11_authority_routes_are_default_deny_and_step_up_guarded():
    from brambleloop.authority import dag

    dag.submit(DB, key="wire4:publish", department="store_commerce", job_type="store.publish",
               submitted_by="coo")
    anon = H.client()
    for path, body in (("/api/cc/authority/approve/wire4:publish", {}),
                       ("/api/cc/authority/grant", {"agent": "pricing"})):
        r = anon.post(path, json=body)
        assert r.status_code in (401, 403), (path, r.status_code)
    c, csrf = H.session()
    # no CSRF/nonce -> refused before the handler
    r = c.post("/api/cc/authority/approve/wire4:publish", json={})
    assert r.status_code == 403, r.status_code
    H.expire_stepup(c)
    for path in ("/api/cc/authority/approve/wire4:publish", "/api/cc/authority/grant"):
        r = H.post(c, csrf, path, {"agent": "pricing"})
        assert r.status_code == 403 and r.json().get("code") == "STEP_UP_REQUIRED", r.text
    with DB.session() as s:
        w = s.scalar(select(dag.WorkItem).where(dag.WorkItem.key == "wire4:publish"))
        assert w.approved_by in ("", None), w.approved_by


def test_k11_approve_and_grant_reach_the_domain_and_are_audited():
    from brambleloop.app.command_center.models import SecurityEvent
    from brambleloop.authority import dag, policy
    from brambleloop.core.models import AuditLog

    dag.submit(DB, key="wire4:publish2", department="store_commerce",
               job_type="store.publish", submitted_by="coo")
    c, csrf = H.session()  # a fresh login carries the step-up window
    r = H.post(c, csrf, "/api/cc/authority/approve/wire4:publish2", {"approval_ref": "OA-7"})
    assert r.status_code == 200, r.text
    assert r.json()["work_item"]["approved_by"] == "owner"
    r = H.post(c, csrf, "/api/cc/authority/approve/no-such-item", {})
    assert r.status_code == 409 and r.json().get("code") == "REFUSED_BY_AUTHORITY", r.text
    base = {"agent": "pricing", "action_class": "PUBLISH", "job_type": "pricing.experiment",
            "owner_decision_id": "D-WIRE4-TEST"}
    r = H.post(c, csrf, "/api/cc/authority/grant", {**base, "level": "bounded"})
    assert r.status_code == 409, r.text            # the ladder rises one rung at a time
    r = H.post(c, csrf, "/api/cc/authority/grant", {**base, "owner_decision_id": ""})
    assert r.status_code == 409 and "decision" in r.json()["error"].lower(), r.text
    r = H.post(c, csrf, "/api/cc/authority/grant", {**base, "level": "owner_each"})
    assert r.status_code == 200, r.text
    pid = r.json()["policy_id"]
    assert any(p["id"] == pid for p in policy.active_policies(DB, agent="pricing"))
    with DB.session() as s:
        acts = {a.action for a in s.scalars(select(AuditLog))}
        events = [e.detail for e in s.scalars(select(SecurityEvent))
                  if (e.detail or {}).get("action") in ("authority.approve",
                                                        "authority.grant")]
    assert {"work_item.approved", "authority.granted"} <= acts, acts
    assert len(events) == 2, events


def test_k11_authority_providers_are_wired():
    assert providers.PROVIDERS["authority_dag"] == ("brambleloop.authority.dag", "summary")
    assert providers.PROVIDERS["authority_policy"] == ("brambleloop.authority.policy",
                                                       "summary")
    for key in ("authority_dag", "authority_policy"):
        out = providers.call(key, DB)
        assert out["status"] in providers.STATUSES and "not built" not in str(
            out.get("reason")), out


# ---- F wiring 5: UNKNOWN cost in the one owner queue ---------------------------------------

def test_f5_voice_action_is_queued_with_unknown_cost_and_never_free():
    from brambleloop.build2 import executor
    from brambleloop.core.models import OwnerAction
    from brambleloop.laura.agency import voice_selection

    first = voice_selection.seed_owner_action(DB)
    again = voice_selection.seed_owner_action(DB)
    assert again["seeded"] is False and again["owner_action_id"] == first["owner_action_id"]
    with DB.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == "laura.voice.listen_shortlist")))
    assert len(rows) == 1 and rows[0].max_cost_basis == "UNKNOWN"
    assert rows[0].max_cost_known is None
    inbox = executor.approval_inbox(DB, env={})
    cards = [c for c in inbox["cards"] if c["requirement_key"] == "laura.voice.listen_shortlist"]
    assert len(cards) == 1, [c["requirement_key"] for c in inbox["cards"]]
    card = cards[0]
    assert card["max_cost_cad"] is None and card["max_cost_basis"] == "UNKNOWN", card
    assert "laura.voice.listen_shortlist" not in inbox["batched_free_and_quick"]
    assert not card["packet_complete"]
    assert card["urgency"].startswith("when costed")
    # ranked after every card whose cost is stated
    stated = [c["rank"] for c in inbox["cards"] if c["max_cost_cad"] is not None]
    assert all(r < card["rank"] for r in stated), (stated, card["rank"])

    r = H.client().get("/api/owner-actions", headers=_ops())
    assert r.status_code == 200, r.text
    body = r.json()
    a = [x for x in body["actions"] if x["requirement_key"] == "laura.voice.listen_shortlist"]
    assert a and a[0]["max_cost_cad"] is None and a[0]["max_cost_basis"] == "UNKNOWN"
    for k in ("why_software_cannot", "rank", "urgency", "max_cost_basis"):
        assert k in a[0], k
    assert "empty_state" in body and "parked" in body
    assert body["empty_state"]["state"] == "NOT-EMPTY"

    html = H.client().get("/", headers=_ops()).text
    row = html[html.index("Listen to the shortlisted Laura voice"):][:600]
    assert "UNKNOWN (no ceiling stated yet)" in row and "CA$0.00" not in row, row


def test_f5_finance_never_reads_an_unknown_ceiling_as_spend_authority():
    from brambleloop.core.models import OwnerAction
    from brambleloop.finance.accounting import policy as fpolicy

    with DB.session() as s:
        s.add(OwnerAction(requirement_key="wire4:unknown-ceiling", action="trial a provider",
                          max_cost_cad=0.0, max_cost_basis="UNKNOWN", done=True))
        s.add(OwnerAction(requirement_key="wire4:stated-ceiling", action="trial a provider",
                          max_cost_cad=10.0, done=True))
    with DB.session() as s:
        ok, why = fpolicy._authority(s, {"amount_cad": 1.0, "authority": {
            "type": "owner_action", "ref": "wire4:unknown-ceiling"}})
        assert ok is False and "UNKNOWN" in why, why
        ok, why = fpolicy._authority(s, {"amount_cad": 1.0, "authority": {
            "type": "owner_action", "ref": "wire4:stated-ceiling"}})
        assert ok is True, why


# ---- K7: dashboard empty state and as-of lines ----------------------------------------------

def _dashboard_with(inbox: dict) -> str:
    from brambleloop.build2 import executor

    real = executor.approval_inbox
    executor.approval_inbox = lambda *_a, **_k: inbox
    try:
        return H.client().get("/", headers=_ops()).text
    finally:
        executor.approval_inbox = real


def test_k7_dashboard_empty_queue_is_only_nothing_waiting_when_proven():
    base = {"cards": [], "external_capability_unavailable": []}
    html = _dashboard_with({**base, "empty_state": {
        "state": "UNPROVEN-EMPTY", "why": "no launch readiness assessment has ever been "
                                          "recorded"}})
    assert "queue empty but UNPROVEN: no launch readiness assessment" in html
    assert "nothing is waiting on the owner" not in html
    html = _dashboard_with({**base, "empty_state": {"state": "PROVEN-EMPTY", "why": "x"}})
    assert "nothing is waiting on the owner" in html and "UNPROVEN" not in html
    html = _dashboard_with(dict(base))                   # no guard result at all
    assert "queue empty but UNPROVEN" in html and "nothing is waiting on the owner" not in html


def test_k7_dashboard_tables_state_their_newest_row():
    html = H.client().get("/", headers=_ops()).text
    for h2 in ("Recent jobs", "Products", "Open incidents", "Audit trail"):
        seg = html[html.index(f"<h2>{h2}</h2>"):][:400]
        assert "(query time)" in seg and "newest row" in seg, (h2, seg)
    H.seed_company()
    html = H.client().get("/", headers=_ops()).text
    seg = html[html.index("<h2>Products</h2>"):][:400]
    assert "newest row no rows" not in seg and " UTC</div>" in seg, seg


# ---- D: WORK_KEYS declared in the pipeline itself -----------------------------------------

def test_d_work_keys_are_declared_in_runtime_pipeline():
    tree = ast.parse((SRC / "runtime" / "pipeline.py").read_text())
    declared = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "WORK_KEYS":
            declared = ast.literal_eval(node.value)
    assert declared, "WORK_KEYS not found"
    want = {"visual.rnd.cycle": ("work_done",),
            "finance.accounting.period_pack": ("work_done",),
            "laura.executive_tick": ("work_done",),
            "listing.outcomes": ("exports_processed", "recorded_listings")}
    assert len(want) == 4
    for k, v in want.items():
        assert declared.get(k) == v, (k, declared.get(k))


# ---- B2 -----------------------------------------------------------------------------------

def test_b2_invariants_protect_the_canonical_brand_assets():
    from brambleloop.improve import invariants as I

    for name in ("canonical_assets", "AUTHORISED_BRAND_CHANGES", "brand_role",
                 "brand.canonical_assets", "Brand-Role"):
        hit = I.protected_invariant(name)
        assert hit is not None and hit.key == "brand_canonical_assets", (name, hit)
        assert not I.check(name, 1, tunable={"param": name, "lo": 0, "hi": 9}).ok


def test_b2_banner_surface_approval_is_scoped_to_one_asset_and_one_surface():
    from brambleloop.store_foundation import owner_banner as OB
    from brambleloop.visual import canonical as C

    S = C.SURFACE_STOREFRONT_BANNER
    # global state untouched
    assert C.PUBLICATION_APPROVED == frozenset()
    assert C.asset_status(BANNER_SHA) == C.NOT_FOR_PUBLICATION
    assert C.customer_ready(BANNER_SHA)["customer_ready"] is False
    # scoped: this sha on this surface only
    assert C.asset_status(BANNER_SHA, surface=S) == C.SURFACE_APPROVED_CONDITIONAL
    assert C.asset_status(BANNER_SHA, surface="listing_image") == C.NOT_FOR_PUBLICATION
    entries = C.all_entries()
    assert entries, "manifest has no entries"
    for e in entries:                                 # every Laura frame is unaffected
        assert C.surface_approval(e["sha256"], S) is None, e["file"]
        assert C.asset_status(e["sha256"], surface=S) == C.asset_status(e["sha256"])
    approval = C.surface_approval(BANNER_SHA, S)
    assert approval["gates_waived_by_owner"] == ()
    assert approval["owner_approved"] == ("canonical_identity",)
    # PASS only when every condition passes; UNKNOWN never passes
    assert C.surface_publication(BANNER_SHA, S, {"a": "PASS"})["status"] == "PASS"
    assert C.surface_publication(BANNER_SHA, S, {"a": "PASS", "b": "UNKNOWN"})["status"] \
        == "UNKNOWN"
    assert C.surface_publication(BANNER_SHA, S, {"a": "FAIL"})["status"] == "FAIL"
    assert C.surface_publication(BANNER_SHA, S, {})["status"] == "UNKNOWN"
    assert C.surface_publication(BANNER_SHA, "listing_image", {"a": "PASS"})["status"] == \
        "FAIL"
    assert C.surface_publication("e" * 64, S, {"a": "PASS"})["status"] == "FAIL"
    # the assessment reads it, and the banner is still not publishable
    r = OB.assess()
    g = {x["gate"]: x for x in r["gates"]}["laura_publication_status"]
    assert g["status"] == "FAIL", g
    assert g["evidence"]["surface_status"] == C.SURFACE_APPROVED_CONDITIONAL
    assert g["evidence"]["asset_status"] == C.NOT_FOR_PUBLICATION
    assert "nav_categories_truth" in g["evidence"]["outstanding_failed"]
    assert "product_truth" in g["evidence"]["outstanding_unknown"]
    assert not set(g["evidence"]["outstanding_unknown"]) & set(r["unverified_assumptions"])
    assert r["publishable"] is False and r["status"] == "BLOCKED"


# ---- K1 / K4 ------------------------------------------------------------------------------

def test_k1_k4_provider_modules_resolve_statically():
    from brambleloop.autonomy import generators

    src = (SRC / "autonomy" / "generators.py").read_text()
    for mod in ("brambleloop.launch.visibility", "brambleloop.commerce.search_evidence",
                "brambleloop.authority.dag", "brambleloop.authority.policy"):
        assert f'module == "{mod}"' in src, mod
        assert generators.provider_module(mod).__name__ == mod


if __name__ == "__main__":
    H.run(globals())
