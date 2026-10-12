"""W3 lane F wiring (Command Center providers and routes requested by other lanes).

* lane D: provider resolution goes through `autonomy.generators.provider_module` (static
  imports the reachability rule can see), and Laura's identity verifies with lane D's own
  `ensure()` -- the harness no longer re-pins anything;
* lane K4: `visibility` provider entry; lane K1: `search_evidence` entry -- both tolerate an
  unmerged module as UNKNOWN "not built", never an empty OK;
* launch verdict section from the newest `launch.assessed` row (PASS/FAIL/UNKNOWN; anything
  but `ready is True` is FAIL);
* lane H: Visual R&D governance section (identity review, paid plans, commercial, evolution);
* lane K8 W1: estate/CX routes mounted; `/api/cx/workspace` is a customer-data route
  (operator credential), so an anonymous read is refused;
* lane SPEND: Laura's production phrasing goes through `gateway.laura_phrase` (one prompt
  registration -- importing both modules no longer raises PromptIsImmutable).

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_laura_cc_providers.py
"""
from __future__ import annotations

import sys

import w3_laura_cc_harness as H  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import providers, tabs  # noqa: E402
from brambleloop.core.models import AuditLog  # noqa: E402

DB = H.DB


def test_provider_resolution_uses_lane_d_provider_module():
    from brambleloop.autonomy import generators

    seen = []
    real = generators.provider_module

    def spy(name):
        seen.append(name)
        return real(name)

    generators.provider_module = spy
    try:
        for key in ("seo", "improvement", "accounting", "visual_rnd", "slo", "autonomy"):
            providers.call(key, DB)
    finally:
        generators.provider_module = real
    assert seen and set(seen) >= {"brambleloop.seo.status",
                                  "brambleloop.learn.improvement_status",
                                  "brambleloop.finance.accounting.dashboard",
                                  "brambleloop.visual.rnd.status"}, seen


def test_identity_verifies_with_lane_d_ensure_without_any_repin():
    from brambleloop.laura.core import identity as ident

    assert H.LANE_D_REPINNED is False
    assert ident.sha256_of(ident.genesis()) == ident.GENESIS_SHA256
    cur = ident.ensure(DB)
    assert cur["sha256"] == ident.CURRENT_SHA256, cur["sha256"]
    assert ident.CURRENT_SHA256.startswith("20697b7c")
    from brambleloop.laura.agency import identity_view
    assert identity_view.identity(DB)["verified"]["status"] == "OK"


def test_visibility_and_search_evidence_tolerate_absence():
    assert providers.PROVIDERS["visibility"] == ("brambleloop.launch.visibility", "summary")
    assert providers.PROVIDERS["search_evidence"] == ("brambleloop.commerce.search_evidence",
                                                      "summary")
    for key, mod in (("visibility", "brambleloop.launch.visibility"),
                     ("search_evidence", "brambleloop.commerce.search_evidence")):
        saved = sys.modules.get(mod, "absent")
        sys.modules[mod] = None            # force ImportError even once the lane is merged
        try:
            e = providers.call(key, DB)
        finally:
            if saved == "absent":
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = saved
        assert e["status"] == "UNKNOWN" and e["reason"] == "not built", e
        live = providers.call(key, DB)     # merged or not, always a valid envelope
        assert live["status"] in providers.STATUSES and isinstance(live["items"], list)
    st = tabs.store(DB)["sections"]
    for k in ("launch_verdict", "visibility", "search_evidence"):
        assert k in st and st[k]["status"] in providers.STATUSES, (k, st.get(k))


def test_launch_verdict_reads_the_newest_assessment_honestly():
    e = tabs.launch_verdict(DB)
    assert e["status"] == "UNKNOWN" and "never run" in e["reason"], e
    with DB.session() as s:
        s.add(AuditLog(actor="system", action="launch.assessed", artifact="launch",
                       detail={"ready": False, "ours_to_do": ["a", "b"],
                               "blocked_on_owner": ["kyc"], "blocked_on_integration": []}))
    e = tabs.launch_verdict(DB)
    assert e["status"] == "BLOCKED" and e["items"][0]["verdict"] == "FAIL", e
    assert {i["title"]: i.get("count") for i in e["items"][1:]} == {
        "Ours to do": 2, "Blocked on owner": 1, "Blocked on integration": 0}
    with DB.session() as s:
        s.add(AuditLog(actor="system", action="launch.assessed", artifact="launch",
                       detail={"ready": "yes"}))          # not literally True -> not a pass
    e = tabs.launch_verdict(DB)
    assert e["status"] == "BLOCKED" and e["items"][0]["verdict"] == "FAIL", e
    with DB.session() as s:
        s.add(AuditLog(actor="system", action="launch.assessed", artifact="launch",
                       detail={"ready": True, "ours_to_do": []}))
    e = tabs.launch_verdict(DB)
    assert e["status"] == "OK" and e["items"][0]["verdict"] == "PASS", e


def test_visual_rnd_governance_section_never_reads_as_empty_ok():
    g = tabs.visual_rnd_governance(DB)
    assert g["status"] in providers.STATUSES
    if g["items"]:
        titles = [r["title"] for r in g["items"]]
        assert titles == ["Laura identity review queue", "Paid challengers: spend plans",
                          "Commercial hero objective", "Evolution (is Visual getting better?)"]
        for r in g["items"]:
            assert r["status"] != "OK" or r["detail"] not in ("", "UNKNOWN"), r
    else:
        assert g["status"] == "UNKNOWN" and g.get("reason"), g
    a = tabs.autonomy(DB)["sections"]
    assert "visual_rnd_governance" in a


def test_k8_estate_routes_are_mounted_and_customer_data_is_operator_only():
    from brambleloop.app import security

    # FastAPI keeps included routers out of `app.routes`; enumerate as the auth sweeps do.
    paths = {path for path, _m, _ in security.iter_api_routes(main.app)}
    for p in ("/api/etsy/estate", "/api/etsy/surfaces", "/api/cx/summary", "/api/cx/workspace"):
        assert p in paths, p
    assert "/api/cx/workspace" in main.CUSTOMER_DATA_ROUTES
    c = H.client()
    r = c.get("/api/cx/workspace")
    assert r.status_code in (401, 503), r.status_code
    r = c.get("/api/cx/workspace", headers={"Authorization": f"Bearer {H.OPS}"})
    assert r.status_code == 200, r.text[:200]
    assert c.get("/api/etsy/estate").status_code == 200


def test_phrasing_uses_the_spend_lane_task_and_one_prompt():
    from brambleloop.gateway import laura_phrase
    from brambleloop.laura.agency import phrasing

    assert phrasing.PROMPT is laura_phrase.PROMPT
    assert phrasing.ROUTING_TASK == laura_phrase.TASK == "laura.business_phrase"
    import os
    os.environ[phrasing.PHRASING_ENV] = "1"
    try:
        text, meta = phrasing.phrase(DB, "2 jobs ran; revenue is UNKNOWN.", facts={"jobs": 2})
    finally:
        os.environ.pop(phrasing.PHRASING_ENV, None)
    # No provider key in the harness: the deterministic answer stands, nothing is billed.
    assert text == "2 jobs ran; revenue is UNKNOWN." and meta["phrased"] is False, meta


if __name__ == "__main__":
    H.run(globals())
