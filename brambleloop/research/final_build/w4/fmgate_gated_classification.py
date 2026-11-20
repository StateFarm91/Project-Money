"""W4-FMGATE: classify every launch-critical row that was GATED on the deployed 0417f35 matrix.

Reads the matrix committed at 0417f35 (git show), the regenerated matrix on this branch and the
production gate snapshot (evidence_FMGATE_0417f35/prod_api_build_*.json `gates`), and writes
w4/FMGATE_GATED_CLASSIFICATION.json: for each of the 126 rows, the gate it was parked on, the
classification (GENUINE-OWNER / GENUINE-DATA / GENUINE-EXTERNAL / CLEARED / RE-KEYED /
MISCLASSIFIED), the evidence, and where the row stands now.

  python3 research/final_build/w4/fmgate_gated_classification.py
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
FB = HERE.parent
EV = HERE / "evidence_FMGATE_0417f35"
BASE = "0417f3516f30bb7c52926187fc475a0f46536e86"

# The production executor gate state at 2026-10-11T14:39Z (/api/build gates), quoted per key.
PROD_GATE = "prod /api/build gates.{k}.open=false (0417f35, 2026-10-11T14:39Z)"

# Per gate key: (classification, evidence). Keys that are not executor gates carry the
# reason the dependency is outside the company.
BY_KEY = {
    "etsy_api": ("GENUINE-OWNER", PROD_GATE + "; /api/queue/dead: listing.taxonomy_refresh "
                 "403 on the API-key-only path at 14:05Z and mjs.scan 403 'check "
                 "ETSY_SHARED_SECRET'; /api/status revenue: 'no recorded successful etsy.probe'"),
    "etsy_shop": ("GENUINE-OWNER", PROD_GATE + " (shop identifier set AND a recorded "
                  "successful etsy.probe; only the account holder opens a shop)"),
    "image_vision": ("GENUINE-OWNER", PROD_GATE + " (a recorded successful vision.probe; "
                     "owner model/vision provider funding)"),
    "transactions_r": ("GENUINE-OWNER", PROD_GATE + "; /api/status revenue.why: 'the stored "
                       "Etsy grant does not include it. Only the owner can add it, by "
                       "re-authorising the app in a browser'"),
    "insights_access": ("GENUINE-OWNER", PROD_GATE + " (owner Etsy Stats / Search Visibility "
                        "exports; no API)"),
    "tester_roster": ("GENUINE-OWNER", PROD_GATE + " (human pattern testers recruited by the "
                      "owner)"),
    "offsite_storage": ("GENUINE-OWNER", PROD_GATE + " (bucket + credential outside the "
                        "provider; consequential spend/account)"),
    "model_provider": ("GENUINE-OWNER", PROD_GATE + " (provider funding/credits)"),
    "physical_proof": ("GENUINE-OWNER", PROD_GATE + " (a physical worked sample; an "
                       "unavoidable physical action)"),
    "owned_surfaces": ("GENUINE-OWNER", PROD_GATE + " (a site/Pinterest account opened by "
                       "the owner)"),
    "ad_authority": ("GENUINE-OWNER", PROD_GATE + " (paid-media authority is consequential "
                     "spend)"),
    "live_listings": ("GENUINE-DATA", PROD_GATE + "; /api/verify nothing_published ok: no "
                      "listing exists to produce exposure"),
    "customers": ("GENUINE-DATA", PROD_GATE + "; /api/status revenue UNMEASURED: buyers create "
                  "orders"),
    "model_bearing_render": ("GENUINE-EXTERNAL", PROD_GATE + " (no provider renders a "
                             "model-bearing frame that passes the identity/product floors)"),
    "rendered_pages": ("GENUINE-EXTERNAL", PROD_GATE + " (Etsy pages/help centre answer 403 "
                       "to automated retrieval; never bypassed)"),
    "image_vision@external": ("GENUINE-EXTERNAL", PROD_GATE.format(k="image_vision")),
    "visual_v1_provider_capability": ("GENUINE-EXTERNAL", "no image provider offers the "
                                      "3D->conditioning->photoreal stage the row needs "
                                      "(VISUAL_STATUS / W4-VISUAL2); not an executor gate"),
    "no_messages_api": ("GENUINE-EXTERNAL", "Etsy Open API v3 has no conversations/messages "
                        "endpoint; buyer messages reach the company only via owner intake"),
    "customer_service_stats": ("GENUINE-EXTERNAL", "Etsy Customer Service Stats have no API"),
    "advertising_rules": ("GENUINE-EXTERNAL", "Etsy ads policy pages are 403 to automated "
                          "re-fetch; the dated reading is owner-recorded"),
    "provider_usage_api": ("GENUINE-OWNER", "prod /api/verify readbacks.estimate_drift."
                           "settlement_against_provider_billing = OWNER-GATED (provider admin "
                           "usage keys)"),
    "bank_and_payment_ledger_feed": ("GENUINE-OWNER", "no bank / Etsy payment-ledger / "
                                     "processor statement can be read without the owner's "
                                     "banking export (KYC/banking)"),
    "visual_paid_generation": ("GENUINE-OWNER", "OWNER_ACTIONS batch 'visual': paid image "
                               "generation (max CA$2.00) or physical sample photographs"),
    "credential_rotation": ("GENUINE-OWNER", "rotating the chat-exposed provider key is an "
                            "owner act; the register and owner card are wired (reached on "
                            "0417f35)"),
    "deploy_trigger_config": ("GENUINE-OWNER", "server-side deploy enforcement (Railway "
                              "'wait for CI' / branch protection) is a platform setting; the "
                              "runtime boot guard already forces SHADOW on an unproven build "
                              "(/api/status boot_guard enforced:true)"),
    "plane_violations": ("GENUINE-OWNER", "token-scope separation of build vs operate "
                         "credentials is an owner credential action"),
    "publication_authority": ("GENUINE-OWNER", "draft-to-live needs the owner's sealed "
                              "publication/activation grant"),
    "payout": ("GENUINE-OWNER", "Etsy Payments onboarding is KYC/banking"),
    "legal_and_tax": ("GENUINE-OWNER", "tax registration decisions are the owner's (CRA)"),
    "policy_settings": ("GENUINE-OWNER", "Etsy-side policy text is set in the owner's Shop "
                        "Manager; read-back needs the Etsy credential"),
    "etsy_ai_partner_guidance": ("GENUINE-OWNER", "help.etsy.com is 403 to automation; the "
                                 "owner reads the guidance"),
    "dashboard_truth.evidence": ("GENUINE-OWNER", "lane-recorded production evidence item "
                                 "the owner holds"),
    "spend_policy numbers": ("GENUINE-OWNER", "provider/department ceiling numbers are owner "
                             "spend policy (not changed by this lane)"),
    "casl_notification_authority": ("GENUINE-OWNER", "an external notification channel needs "
                                    "CASL review and owner authority"),
    "store_preview_v2_review": ("GENUINE-OWNER", "a taste decision only the owner makes"),
    "etsy_ads": ("GENUINE-DATA", "Etsy Ads data exists only once ads run on live listings"),
}

# Row-level outcomes of this lane (close_fmgate.py), with the evidence.
BY_ROW = {
    "F-172": ("CLEARED", "production_deploy cleared: /api/verify on 0417f35 re-proves shadow "
              "publication (phase_is_shadow, nothing_published, 185 refusals) -> COMPLETE"),
    "F-176": ("CLEARED", "production_window was the deploy: ops.truth.sweep row 26799 on "
              "0417f35 rollback_baseline recoverable:true, missing [] -> COMPLETE"),
    "F-158": ("CLEARED", "production_window was 'image never built from the lock': 0417f35 "
              "built with pip --require-hashes from requirements.lock, boot guard matched the "
              "digest incl. the lock -> COMPLETE (producer re-mapped to the boot guard)"),
    "F-144": ("MISCLASSIFIED", "production_deploy cleared; what remains is company work "
              "(per-feature readback manifest) and a red /api/verify -> OPEN"),
    "F-171": ("MISCLASSIFIED", "production_deploy cleared; remaining: extend /api/verify and "
              "fix the two red checks -> OPEN"),
    "F-718": ("MISCLASSIFIED", "production_window does not govern it: the model.frozen "
              "approval row is readable now (/api/audit?action=model.frozen id 5693); export "
              "into the repo is company work -> OPEN"),
    "F-733": ("MISCLASSIFIED", "as F-718 -> OPEN"),
    "F-135": ("RE-KEYED", "production_window -> owner live_restart_drill (the 24h window never "
              "records a lease-recovery drill)"),
    "F-850": ("RE-KEYED", "production_window -> owner live_restart_drill"),
    "F-540": ("RE-KEYED", "production_window -> owner etsy_api (rotation proof needs a working "
              "Etsy credential; Etsy answered 403)"),
    "F-518@v0.15": ("RE-KEYED", "production_window -> owner publication_authority (a live "
                    "rollback is an Etsy write under the owner's grant)"),
    "F-396": ("RE-KEYED", "production_window -> owner offsite_storage (the owner half of its "
              "two blockers)"),
    "F-924": ("RE-KEYED", "owner hosted_operating_history -> data (elapsed hosted history)"),
    "F-009": ("GENUINE-OWNER", "company half built here (/api/catalogue per-listing filters); "
              "real values need the node schema behind etsy_api"),
    "F-160": ("GENUINE-OWNER", "stale missing_part corrected: register reached on 0417f35"),
    "F-321": ("GENUINE-DATA", "stale missing_part corrected: product attribution since "
              "6d86a8b"),
    "F-588": ("GENUINE-OWNER", "stale missing_part corrected: UNKNOWN reaches readiness"),
}
WINDOW_DATA = ("RE-KEYED", "owner production_window -> data production_window: the owner "
               "authorised and the integrator performed the deploy (0417f35 unattended since "
               "13:59:48Z); the gate opens mechanically on autonomy.off_device_proof PROVEN "
               "over 24h; at 14:39Z unmet only on no_unexpected_dead_letters (ops.sentinel "
               "VARCHAR(200), taxonomy 403) -- repaired on this branch, so the gate can open "
               "24h after the successor deploy")
for _u in ("F-371", "F-380", "F-381", "F-495", "F-654", "F-701", "F-849", "F-880", "F-881",
           "F-895", "F-923"):
    BY_ROW[_u] = WINDOW_DATA

# Rows whose missing_part names a company sub-step beside the gate that this lane did not
# verify or build. They stay GATED (the gate is genuine) and are listed for the next lane.
COMPANY_SUBSTEP_UNVERIFIED = {
    "F-010": "periodic node/property schema diff (daily listing.taxonomy_refresh exists; the "
             "diff/alert half is unverified)",
    "F-059": "an explicit switch that makes real Etsy evidence override internal SEO scoring",
    "F-088": "per-version/descendant halting and confidence updates from tickets/refunds",
    "F-239": "mobile QA of the company's own storefront preview (Etsy pages are 403; the "
             "preview is not)",
    "F-293": "desktop/mobile inspection of the company's own storefront preview",
    "F-323": "per-sale contribution net of refunds/advertising/processing",
    "F-542": "read-back on the production publish path (the exercise path has it)",
    "F-557": "pre-sale/refund/safety/policy/abuse triage classes",
}


def main() -> int:
    old = json.loads(subprocess.run(
        ["git", "show", f"{BASE}:brambleloop/research/final_build/closure_matrix.json"],
        cwd=FB, capture_output=True, check=True).stdout)
    new = {r["uid"]: r for r in json.loads((FB / "closure_matrix.json").read_text())["matrix"]}
    build = json.loads(next(EV.glob("prod_api_build_*.json")).read_text())
    gates = build.get("gates") or {}
    rows = []
    for r in old["matrix"]:
        if r["launch_class"] != "LAUNCH-CRITICAL" or r["completion"] != "GATED":
            continue
        g = r.get("gate") or {}
        key = g.get("key")
        if r["uid"] in BY_ROW:
            cls, ev = BY_ROW[r["uid"]]
        else:
            k = key + "@external" if (key == "image_vision" and g.get("kind") == "external") \
                else key
            cls, ev = BY_KEY.get(k, ("UNCLASSIFIED", "no rule"))
            ev = ev.replace("{k}", key)
        prod = gates.get(key)
        n = new[r["uid"]]
        rows.append({
            "uid": r["uid"], "title": r["title"][:80],
            "was": {"kind": g.get("kind"), "key": key},
            "classification": cls, "evidence": ev,
            "prod_executor_gate_open": (prod or {}).get("open") if prod else None,
            "company_substep_unverified": COMPANY_SUBSTEP_UNVERIFIED.get(r["uid"]),
            "now": {"completion": n["completion"],
                    "gate": {"kind": (n.get("gate") or {}).get("kind"),
                             "key": (n.get("gate") or {}).get("key")}}})
    out = {"kind": "w4-FMGATE gated-row classification",
           "basis": {"matrix_before": f"{BASE[:12]}:closure_matrix.json",
                     "matrix_after": "this branch's regenerated closure_matrix.json",
                     "production_gates": "evidence_FMGATE_0417f35/prod_api_build_*.json"},
           "counts": {"rows": len(rows),
                      "classification": dict(Counter(x["classification"] for x in rows)),
                      "now": dict(Counter(x["now"]["completion"] for x in rows)),
                      "now_gate_kind": dict(Counter(x["now"]["gate"]["kind"] for x in rows
                                                    if x["now"]["completion"] == "GATED"))},
           "rows": rows}
    (HERE / "FMGATE_GATED_CLASSIFICATION.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["counts"], indent=1))
    unc = [x["uid"] for x in rows if x["classification"] == "UNCLASSIFIED"]
    if unc:
        print("UNCLASSIFIED:", unc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
