"""Write GATE_CLEARANCE_BUSINESS.{json,md} (lane W4-GATESB).

Sources: the code's own clearance packets (build2.gate_clearance, quality.tester_programme,
quality.tester_kit, intel.second_market) and production read-only snapshots committed in
evidence_GATESB/ (deployed fcb982d, read 2026-10-07). No network, no writes outside this dir.

    PYTHONPATH=src python research/final_build/w4/gate_clearance_business.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.build2 import gate_clearance as GC  # noqa: E402
from brambleloop.commerce.paid_media import CONSERVATIVE_CAPS  # noqa: E402
from brambleloop.intel import second_market  # noqa: E402
from brambleloop.quality import tester_kit, tester_programme  # noqa: E402

EV = HERE / "evidence_GATESB"


def _benchmark() -> dict:
    sel = json.loads((EV / "prod_benchmark_selection_13_300_fcb982d.json").read_text())
    import html

    picks = [{"n": i, "listing_ref": p["listing_ref"], "department": p["pod"],
              "title": html.unescape(p["title"]), "price_cad": p["price_cad"], "url": p["url"]}
             for i, p in enumerate(sel["selected"], start=1)]
    total = round(sum(p["price_cad"] for p in picks), 2)
    assert picks and total == sel["total_cad"]
    return {
        "gate": "benchmark_purchases", "requirements": [163, 165, 168, 315, 317],
        "status": "OWNER-ACTION",
        "reconciliation": ("the gate text said 'roughly ten'; the owner approved thirteen at a "
                           "CA$300 ceiling on 2026-09-20 (B-501, B-512) and intake enforces "
                           "SET_SIZE=13 / SET_BUDGET_CAD=300. The required set is the 13 below, "
                           "chosen by purchase_selection's deterministic facet coverage (B-485, "
                           "B-507/B-509): 428 of 441 observed listings become redundant; a "
                           "10-pick set would leave bags, home_decor and ornaments uncovered"),
        "source": ("GET /api/benchmark-selection?target=13&budget_cad=300 (production fcb982d, "
                   "read-only, 2026-10-07) -> evidence_GATESB/"
                   "prod_benchmark_selection_13_300_fcb982d.json"),
        "picks": picks, "total_cad": total, "budget_cad": 300.0,
        "price_basis": "observed listing price in CAD; tax and any sale price on the day "
                       "excluded",
        "delivery": GC.benchmark_delivery(),
        "owner_action": {"action": "buy the 13 listings above and upload each download at "
                                   "/ops/teardown", "max_cost_cad": 300.0,
                         "expected_cost_cad": total, "minutes": 75,
                         "consequence_of_waiting": "#168/#315 benchmark challenge cannot "
                         "measure our deliverables; it stays a release blocker; #317 has "
                         "nothing to analyse"},
        "never": "no competitor content is copied into products; files stay quarantined",
    }


def _physical() -> dict:
    manifest = json.loads((HERE / "tester_kit" / "KIT_MANIFEST.json").read_text())
    return {
        "gate": "physical_proof", "requirements": [64], "status": "NOT-YET-ASKABLE",
        "precondition": "a tester who agreed (tester_roster) -- answer item 3 first",
        "pattern": {k: manifest[k] for k in ("slug", "version", "title", "risk_class",
                                             "required", "scope", "content_hash",
                                             "finished_size_cm", "yarn_metres_by_colour")},
        "why_this_pattern": tester_kit.__doc__.split("**Which pattern.**")[1].split(
            "**What is never")[0].strip(),
        "kit_files": manifest["files"],
        "materials": manifest["materials"],
        "materials_total_cad_estimated": manifest["materials_total_cad_estimated"],
        "max_cost_cad": manifest["max_cost_cad"], "cost_basis": manifest["cost_basis"],
        "person_needed": manifest["person_needed"], "protocol": manifest["protocol"],
        "records": manifest["record_fields"], "intake": manifest["intake"],
        "owner_action": {"action": "approve commissioning the first agreed tester for this "
                                   "make (not the owner)", "max_cost_cad":
                         manifest["max_cost_cad"], "minutes": 5},
    }


def _tester() -> dict:
    return {"gate": "tester_roster", "requirements": [9, 43, 250], "status": "OWNER-ACTION",
            **tester_programme.packet(),
            "owner_action": {"action": "CONFIRM the prepared public tester call (not sent)",
                             "channel": tester_programme.CHANNEL["primary"],
                             "max_cost_cad": 0.0, "minutes": tester_programme.OWNER_MINUTES,
                             "consequence_of_waiting": "no tester -> no physical proof (#64); "
                             "Class B/C products stay blocked from live sale"},
            "intake": "quality.tester_programme.record_agreement (express consent required)"}


def _second_market() -> dict:
    return {"gate": "second_market_benchmark", "requirements": [268],
            "status": "COMPANY-SELECTED (observation pending)",
            "decision": second_market.DECISION_ID,
            "why_company_not_owner": ("B-482/B-508: a choice of shop, no credential, no "
                                      "spend; nothing in the Final Master reserves it"),
            **second_market.state(),
            "next": ("the weekly intel.panel_discovery cadence verifies each shop via getShop "
                     "and scans it on the existing credential once this build is deployed; "
                     "the gate opens on observed listings in a second market"),
            "owner_action": None}


def _owned() -> dict:
    surfaces = {k: v for k, v in GC.MISSING_SURFACES.items()}
    return {"gate": "owned_surfaces", "requirements": sorted(GC.OWNED_SURFACE_NEEDS),
            "status": "PARTLY CLEARED (Etsy shop recognised) + OWNER-ACTION",
            "cleared_portion": {
                "surface": "Etsy shop BrambleloopStudio",
                "evidence": json.loads((EV / "prod_build_gates_fcb982d.json").read_text())
                ["gates"]["etsy_shop"],
                "satisfies": {str(k): v["etsy_satisfies"]
                              for k, v in GC.OWNED_SURFACE_NEEDS.items()}},
            "missing": surfaces,
            "per_requirement_needs": {str(k): list(v["needs"])
                                      for k, v in GC.OWNED_SURFACE_NEEDS.items()},
            "owner_action": {"max_cost_cad": round(sum(v["max_cost_cad"]
                                                       for v in surfaces.values()), 2),
                             "minutes": sum(v["minutes"] for v in surfaces.values()),
                             "minimum_to_open_gate": "site or Pinterest whose publish path "
                                                     "passes owned_surface.probe"}}


def _customers() -> dict:
    return {"gate": "customers", "status": "DATA-GATED (external: buyers)",
            "requirements_note": ("29 rows + #242-245 (re-parked from ad_authority: ads.adjust "
                                  "computes them daily; they wait on order data)"),
            "change": ("approval_inbox lists it under waiting_on_data, never as an owner card; "
                       "gate text no longer reads as an owner grant; closure.DATA_GATES. "
                       "Production fcb982d still showed 'grant real orders' as an owner card "
                       "(evidence_GATESB/prod_console_owner_cards_fcb982d.json) -- fixed on "
                       "deploy"),
            "test": "tests/test_w4_gatesb.py::test_customers_is_data_gated_and_never_an_owner_card",
            "owner_action": None}


def _ads() -> dict:
    return {"gate": "ad_authority", "requirements": [294, 295], "status": "NOT-YET-ASKABLE",
            "definition_of_ready": list(GC.AD_READY_DEFINITION),
            "recommendation_when_ready": {"daily_cad": CONSERVATIVE_CAPS.daily_cad,
                                          "campaign_cad": CONSERVATIVE_CAPS.campaign_cad,
                                          "monthly_cad": CONSERVATIVE_CAPS.monthly_cad,
                                          "max_test_loss_cad":
                                              CONSERVATIVE_CAPS.max_test_loss_cad,
                                          "max_cac_cad": CONSERVATIVE_CAPS.max_cac_cad,
                                          "logic": "build2.gate_clearance.ad_readiness"},
            "structure": "one Etsy Ads campaign over the ready listings (max "
                         f"{GC.MAX_ADVERTISED_LISTINGS}), highest net first; Etsy exposes no "
                         "seller targeting beyond listing choice and daily budget; measured "
                         "by ads.adjust; organic-first proof (#242) gates scaling",
            "guardrails_in_code": ["paid_media.authorise_spend", "paid_media.should_pause",
                                   "growth_ops ads.campaign hard refusal while gate closed",
                                   "SpendLimit('ads') positive unpaused cap"],
            "spend_now": 0.0, "owner_action": None}


def _listings() -> dict:
    return {"gate": "live_listings", "status": "NOT-YET-ASKABLE (company work first)",
            "company_work": ("lane W4-PIPE moves the strongest products through the final "
                             "publication gate (ops.publication_authority evidence); see "
                             "PRODUCT_INVENTORY on claude/w4-PIPE"),
            "owner_action_after": ("per product with complete publication evidence: approve "
                                   "its sealed 24h publication grant (D-FB-10) and leave "
                                   "shadow for that listing (decision leave_shadow)"),
            "owner_action": None}


def build() -> dict:
    gates = [_benchmark(), _physical(), _tester(), _second_market(), _owned(), _customers(),
             _ads(), _listings()]
    asks = [g for g in gates if g.get("owner_action") and str(g["status"]).startswith(
        ("OWNER", "PARTLY"))]
    return {"lane": "W4-GATESB", "generated_for": "owner authorisation 2026-10-07",
            "gates": gates,
            "owner_confirmation_items": [{"gate": g["gate"], **g["owner_action"]}
                                         for g in asks],
            "totals": {"owner_minutes_now": sum(int(g["owner_action"].get("minutes") or 0)
                                                for g in asks),
                       "max_cost_cad_now": round(sum(float(g["owner_action"].get(
                           "max_cost_cad") or 0) for g in asks), 2)}}


def render(d: dict) -> str:
    L = ["# Business gate clearance (W4-GATESB)", "",
         "Owner authorisation 2026-10-07. Per gate: cleared / owner action (exact cost, links, "
         "minutes) / not yet askable (and why) / data-gated. Nothing was bought, sent, "
         "published or spent.", "",
         "| gate | status | owner minutes | max CA$ |", "|---|---|---|---|"]
    for g in d["gates"]:
        oa = g.get("owner_action") or {}
        L.append(f"| {g['gate']} | {g['status']} | {oa.get('minutes', '-')} | "
                 f"{oa.get('max_cost_cad', '-') if oa else '-'} |")
    L += ["", f"Asked now: ~{d['totals']['owner_minutes_now']} min, up to "
              f"CA${d['totals']['max_cost_cad_now']:.2f}.", ""]
    b = d["gates"][0]
    L += ["## 1. benchmark_purchases -- buy these 13 (OWNER ACTION)", "", b["reconciliation"],
          "", "| # | department | listing | CA$ | link |", "|---|---|---|---|---|"]
    for p in b["picks"]:
        L.append(f"| {p['n']} | {p['department']} | {p['title'][:70]} | {p['price_cad']:.2f} "
                 f"| {p['url']} |")
    L += [f"| | | **total** | **{b['total_cad']:.2f}** | ceiling CA$300 |", "",
          "Delivery (existing intake, nothing new):", ""]
    L += [f"{i}. {s}" for i, s in enumerate(b["delivery"]["steps"], start=1)]
    L += ["", f"API: POST {b['delivery']['api']} (multipart: listing_ref, files, optional "
              "paid_cad, licence_terms). Gate opens on the first intake. Never copied into "
              "products.", ""]
    p = d["gates"][1]
    L += ["## 2. physical_proof -- kit ready (NOT YET ASKABLE: needs a tester first)", "",
          f"Pattern: **{p['pattern']['title']}** `{p['pattern']['slug']}@"
          f"{p['pattern']['version']}` (content {p['pattern']['content_hash'][:16]}), "
          f"{p['pattern']['risk_class']}; scope {p['pattern']['scope']}.", "",
          p["why_this_pattern"], "",
          "Printable kit: `research/final_build/w4/tester_kit/` -- "
          + ", ".join(p["kit_files"]), "", "Materials (ESTIMATED CA$):", ""]
    L += [f"- {m['item']} -- {m['quantity']} -- CA${m['est_cad']:.2f}" for m in p["materials"]]
    L += [f"- materials total ~CA${p['materials_total_cad_estimated']:.2f}; approval ceiling "
          f"CA${p['max_cost_cad']:.2f} ({p['cost_basis']})", "",
          f"Person: {p['person_needed']['who']}. Skill: {p['person_needed']['skill']}. "
          f"Time: {p['person_needed']['time']}.", "", "Protocol:", ""]
    L += [f"{i}. {s}" for i, s in enumerate(p["protocol"], start=1)]
    L += ["", "Records -> intake: " + "; ".join(f"{r['label']} -> `{r['api']}`"
                                                for r in p["records"]),
          "", f"Entered via {p['intake']['test']}; photo via {p['intake']['photo']}. "
              f"{p['intake']['gate_opens_when']}.", ""]
    t = d["gates"][2]
    L += ["## 3. tester_roster -- CONFIRM before anything is sent (OWNER ACTION)", "",
          f"Channel: {t['channel']['primary']}. Why: {t['channel']['why_this_channel']}. "
          f"Needs: {t['channel']['account_needed']}.", "",
          "### Exact post (not sent)", "", f"**{t['outreach']['title']}**", "",
          t["outreach"]["body"], "", "### Consent text (intake form)", "",
          t["consent_text"], "", "### Intake form", ""]
    L += [f"- `{f['field']}`{' (required)' if f['required'] else ''}: {f['label']}"
          for f in t["intake_fields"]]
    L += ["", "Offered: " + "; ".join(t["offer"]["gets"]) + ". Never: "
          + "; ".join(t["offer"]["never"]) + ".", "",
          f"Owner steps: {t['owner_steps']}. ~{t['owner_minutes']} min, CA$0 (each make's "
          "fee is item 2's approval).", ""]
    s = d["gates"][3]
    L += ["## 4. second_market_benchmark -- COMPANY-SELECTED (no owner action)", "",
          f"Decision {s['decision']}: {s['why_company_not_owner']}.", ""]
    for c in s["candidates"]:
        e = c["evidence"]
        L.append(f"- **{c['shop_name']}** ({c['expected_market']}): {e['stated_location']}, "
                 f"~{e['lifetime_sales']:,} sales, ~{e['years_on_etsy']} yrs; {c['why']}. "
                 f"Evidence: {e['source']} ({e['read_on']}).")
    L += ["", f"Alternates: " + ", ".join(f"{a['shop_name']} ({a['market']}, "
                                          f"~{a['lifetime_sales']:,})"
                                          for a in s["alternates"]) + ".",
          "", s["next"] + ".", ""]
    o = d["gates"][4]
    L += ["## 5. owned_surfaces -- Etsy shop recognised; still missing (OWNER ACTION)", "",
          f"Cleared portion: {o['cleared_portion']['surface']} -- production gate etsy_shop "
          f"open={o['cleared_portion']['evidence'].get('open')} ("
          f"{o['cleared_portion']['evidence'].get('how_it_is_checked')}).", ""]
    L += [f"- #{k}: Etsy satisfies {v}" for k, v in o["cleared_portion"]["satisfies"].items()]
    L += ["", "Missing, each required because:", ""]
    L += [f"- **{k}** ({v['what']}): {v['why']}. Step: {v['owner_step']}. "
          f"CA${v['max_cost_cad']:.2f} ({v['cost_basis']}), {v['minutes']} min."
          for k, v in o["missing"].items()]
    L += ["", f"Minimum to open the gate: {o['owner_action']['minimum_to_open_gate']}.", ""]
    c = d["gates"][5]
    L += ["## 6. customers -- DATA-GATED (buyers), not an owner authorisation", "",
          c["change"] + ".", f"Test: `{c['test']}`. {c['requirements_note']}.", ""]
    a = d["gates"][6]
    r = a["recommendation_when_ready"]
    L += ["## 7. ad_authority -- prepared, NOT YET ASKABLE, no spend", "",
          "Ready means: " + "; ".join(a["definition_of_ready"]) + ".", "",
          f"Recommendation the day it is ready ({r['logic']}): CA${r['daily_cad']:.2f}/day, "
          f"CA${r['campaign_cad']:.2f} per campaign, CA${r['monthly_cad']:.2f}/month, max test "
          f"loss CA${r['max_test_loss_cad']:.2f}, max CAC CA${r['max_cac_cad']:.2f} "
          "(paid_media.CONSERVATIVE_CAPS, already enforced in code).", "",
          f"Structure: {a['structure']}. Guardrails: " + "; ".join(a["guardrails_in_code"])
          + ".", ""]
    li = d["gates"][7]
    L += ["## 8. live_listings -- company work first", "", li["company_work"] + ".",
          "Then: " + li["owner_action_after"] + ".", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    data = build()
    (HERE / "GATE_CLEARANCE_BUSINESS.json").write_text(json.dumps(data, indent=1,
                                                                  default=str) + "\n")
    (HERE / "GATE_CLEARANCE_BUSINESS.md").write_text(render(data))
    (HERE / "tester_kit" / "OUTREACH.md").write_text(
        "# Tester call -- prepared, NOT SENT (owner confirmation required)\n\n"
        f"Channel: {tester_programme.CHANNEL['primary']}\n\n"
        f"**{tester_programme.OUTREACH_POST['title']}**\n\n"
        f"{tester_programme.OUTREACH_POST['body']}\n\n## Consent text\n\n"
        f"{tester_programme.CONSENT_TEXT}\n")
    print("wrote GATE_CLEARANCE_BUSINESS.{json,md}, tester_kit/OUTREACH.md",
          data["totals"])
