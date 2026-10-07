"""W4-OWNER: build OWNER_ACTIONS.{md,json} and INCIDENTS.{md,json} from the real consumers.

Owner actions: `build2.executor.approval_inbox` (the Command Center approvals inbox) over a
database holding the nine owner actions production showed on 2026-10-06 (fcb982d,
`/api/owner-actions`), merged with the store lane's owner actions (STORE_READINESS on
origin/claude/w4-INTEG 7631026, vendored in store_owner_actions.json) and the visual lane's
costed paid-generation plans (VISUAL_STATUS on origin/claude/w4-VISUAL 32332f5).

Incidents: `tests/test_w4_owner_incidents.reproduce_production` -- the 18 incidents production
held open, seeded with the deployed signatures, then this build's real handlers run over them.

Run:  cd brambleloop && PYTHONPATH=src .venv/bin/python research/final_build/w4/owner/build_owner_docs.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]  # brambleloop/
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

OUT = HERE.parent  # research/final_build/w4/

# Store lane items: how each joins the packet. `merge_into` = the same decision as an existing
# runtime decision; `company_work` = not an owner ask (the company does it); `deferred` = not
# askable yet (its precondition is a later step).
STORE_MAP = {
    "OA-A1": {"merge_into": "transactions_scope"},
    "OA-OBS": {"batch": "etsy_account",
               "yes": "the drift job treats the live About/Laura fields as authoritative and "
                      "checks them (Laura disclosed as AI, not Owner) without touching them"},
    "OA-A2": {"company_work": "the shop state is read by etsy.shop_snapshot (getShop, shops_r) "
                              "once OA-A1 has re-authorised the app; no separate owner report "
                              "is needed"},
    "OA-B": {"batch": "etsy_account",
             "yes": "the account presents the legal holder; Laura never reads as the owner"},
    "OA-BANNER": {"batch": "etsy_account",
                  "yes": "the phone crop is evidenced and the IMG-2 banner findings are ruled "
                         "on; the live banner stays yours and is not replaced"},
    "OA-C": {"batch": "etsy_account",
             "yes": "announcement, location, custom order and sold-visibility trust surfaces "
                    "are set"},
    "OA-D1": {"batch": "etsy_account",
              "yes": "listings land in populated sections only (D-FB-18 item 3)"},
    "OA-E": {"batch": "etsy_account",
             "yes": "every buyer receives the download guidance at purchase"},
    "OA-F": {"batch": "etsy_account",
             "yes": "privacy, FAQ licence and cancellations are live; policy_consistency can "
                    "pass on read-back"},
    "OA-G1": {"batch": "etsy_account",
              "yes": "no third party sells printed copies of a pattern PDF beside ours"},
    "OA-G2": {"batch": "paid_media",
              "yes": "Offsite Ads enrolment is a recorded margin decision, not a default"},
    "OA-STATS": {"deferred": "askable only after the first listings are live (DATA-GATED on "
                             "go-live); produced then by the attribution intake"},
    "OA-LAUNCH": {"merge_into": "leave_shadow"},
}

VISUAL_ITEM = {
    "id": "visual_paid_generation", "batch": "visual",
    "decision": ("Approve up to CA$4.01 of paid image calls for the costed visual plans: P1 "
                 "photograph judging (gpt-5 d_judge, <=16 calls, max CA$1.00), P2 LIFESTYLE "
                 "protected composites for the 3 Launch-0 listings (flux-2-pro, 12+12 calls, "
                 "max CA$2.00), P3 first judged challenger per launch class (36 calls, max "
                 "CA$1.01). Approve per plan or all three; or decline and use the no-API "
                 "alternative (physical sample photo session, yarn ~CA$30 estimated)."),
    "why": ("each plan is a paid API call (consequential spend needs owner approval); none has "
            "been executed (VISUAL_STATUS: 8 GATED_SPEND, never executed)"),
    "evidence": ("research/final_build/w4/VISUAL_STATUS.md 'Owner-ready costed plans' on "
                 "origin/claude/w4-VISUAL 32332f5; visual/milestones.py milestone_d.assess"),
    "max_cost_cad": 4.01, "max_cost_basis": "stated plan ceilings (worst case), summed",
    "consequence_of_yes": ("milestone D's 7 judged items become PASS or FAIL; LIFESTYLE frames "
                           "for the 3 Launch-0 listings; one judged photographic challenger "
                           "per launch class"),
    "consequence_of_no": ("D stays PARTIAL with 7 UNKNOWN judgements; LIFESTYLE and the "
                          "photographic challengers stay queued (GATED_SPEND)"),
    "minutes": 3, "sources": ["lane VISUAL"],
}

# Build 2 OWNER-GATED rows that carry an executable company-side part (owner directive: never
# convert company work into an owner gate). Checked against the code on this branch.
MISLABELLED = [
    {"row": 242, "gate": "ad_authority", "no_owner_part": True,
     "owning_lane": "B2 (ledger) / growth",
     "executable_part": "the organic-first proof is computed by the daily ads.adjust cadence "
                        "(runtime/growth_ops.handle_ads_adjust, which runs whatever the ad "
                        "authority); what it waits for is organic ListingOutcome/order data, so "
                        "the row is DATA-GATED (live listings + transactions_r), not ad-gated"},
    {"row": 243, "gate": "ad_authority", "no_owner_part": True,
     "owning_lane": "B2 (ledger) / growth",
     "executable_part": "risk-adjusted allowable CAC is computed in ads.adjust and refused "
                        "under 20 orders: the blocker is order count (DATA-GATED), not ad "
                        "authority"},
    {"row": 244, "gate": "ad_authority", "no_owner_part": True,
     "owning_lane": "B2 (ledger) / growth",
     "executable_part": "the Offsite Ads economics guard is arithmetic over orders and fees "
                        "computed in ads.adjust; Offsite Ads is a fee on attributed sales, not "
                        "spend, so ad authority is not its gate (the enrolment choice is store "
                        "decision OA-G2); remaining blocker = order data"},
    {"row": 245, "gate": "ad_authority", "no_owner_part": True,
     "owning_lane": "B2 (ledger) / growth",
     "executable_part": "Share-and-Save/direct-link economics involve no spend at all; the "
                        "computation is company work and its remaining blocker is order data"},
    {"row": 10, "gate": "owned_surfaces", "owning_lane": "B2 / growth",
     "executable_part": "the ledger note says no free work has been made: drafting a free "
                        "lead-magnet asset through the product chain and running "
                        "growth/free_to_paid.check_asset on it needs no surface (it stays "
                        "unpublished in shadow); only publication waits on owned_surfaces"},
    {"row": 165, "gate": "benchmark_purchases", "owning_lane": "B2 (ledger)",
     "executable_part": "refresh detection (new category, strong competitor, format/market "
                        "shift) is software and already runs (intel.benchmark_refresh, "
                        "runtime/release.py); only buying the refreshed set is the owner's. "
                        "The row should be split: detection PROVEN, purchase OWNER-GATED"},
    {"row": 54, "gate": "insights_access", "owning_lane": "B2 (ledger)",
     "executable_part": "the pre-Etsy launch readiness gate is company software "
                        "(launch/readiness.assess, 2 tests, rollback rehearsal, search "
                        "baseline from listing.query_portfolio); an Insights reading is one "
                        "input that stays UNKNOWN until recorded. Gate = PROVEN, Insights "
                        "input = OWNER-GATED under insights_reading"},
]

# Genuine owner gates whose ledger rows list no focused test although software exists: the
# gate stays the owner's, the missing test mapping is company work for the ledger owner.
EVIDENCE_GAPS = [
    {"row": 254, "note": "tests/test_personalisation.py and runtime callers "
                         "(runtime/commerce_readings.py, products/launch0.py) exist but the "
                         "ledger lists 0 tests"},
    {"row": 263, "note": "scale/leading.py reports all ten indicators; ledger lists 0 tests"},
    {"row": 37, "note": "intel/insights_budget.py runs on commerce.readings; 0 tests mapped"},
    {"row": 14, "note": "commerce/benchmarks.py; 0 tests mapped"},
    {"row": 16, "note": "commerce/listing_tests.py, growth/experiments.py; 0 tests mapped"},
    {"row": 9, "note": "growth/creators.py; 0 tests mapped"},
    {"row": 51, "note": "core/continuity.py export path; 0 tests mapped"},
]

EXTRA_BATCHES = {"visual": {"id": "visual", "order": 9,
                            "title": "Paid image generation (visual plans)",
                            "why_batched": "three costed plans on one approval line"}}


def owner_actions() -> dict:
    from test_w4_owner_actions import PRODUCTION_9, _db, _seed_production

    from brambleloop.build2 import executor
    from brambleloop.ops import owner_queue as Q

    db = _db()
    ids = _seed_production(db)
    inbox = executor.approval_inbox(db, env={})
    packet = inbox["batches"]
    batches = {b["id"]: dict(b, items=[dict(i, sources=["runtime approval_inbox"])
                                       for i in b["items"]])
               for b in packet["batches"]}
    by_item = {i["id"]: i for b in batches.values() for i in b["items"]}

    def ensure_item(did: str) -> dict:
        """The packet item for decision `did`; built from the table if the runtime inbox did
        not surface it in this database (its gate parks nothing here)."""
        if did in by_item:
            return by_item[did]
        d = next(x for x in Q.DECISIONS if x["id"] == did)
        card = {"evidence": "ops/owner_queue.DECISIONS; executor gate(s) "
                            + ", ".join(d["gates"] or ("-",))}
        item = dict(Q.decision_fields(card, d), id=d["id"], batch=d["batch"],
                    gates=list(d["gates"]), requirement_keys=list(d["keys"]),
                    owner_action_ids=[], unblocks=[], ranks=[], sources=["ops/owner_queue"])
        bmeta = Q.BATCH_BY_ID[d["batch"]]
        batches.setdefault(d["batch"], {"id": bmeta["id"], "title": bmeta["title"],
                                        "why_batched": bmeta["why_batched"],
                                        "items": []})["items"].append(item)
        by_item[did] = item
        return item

    # Build 2 OWNER-GATED rows (lane B2 ledger): each row lands on exactly one decision.
    b2 = json.loads((HERE / "b2_owner_gated.json").read_text())["rows"]
    assert b2, "B2 owner-gated rows missing"
    b2_placed: dict[int, str] = {}
    not_owner = {m["row"] for m in MISLABELLED if m.get("no_owner_part")}
    for r in b2:
        if r["id"] in not_owner:
            b2_placed[r["id"]] = "NOT_AN_OWNER_DECISION (mislabelled_company_work)"
            continue
        d = Q.DECISION_BY_GATE.get(r["gate"])
        assert d is not None, f"B2 row {r['id']} gate {r['gate']} has no decision"
        item = ensure_item(d["id"])
        item.setdefault("b2_rows", []).append(r["id"])
        if "lane B2 ledger" not in item["sources"]:
            item["sources"].append("lane B2 ledger")
        b2_placed[r["id"]] = d["id"]
    assert len(b2_placed) == len(b2)

    # Gate-clearance lanes (W4-GATESI infra, W4-GATESB business): their per-gate actions are
    # folded onto the one decision that gate already belongs to, never a second card.
    # Vendored when the lanes push: owner/gate_clearance_{infra,business}.json.
    clearance_folded, clearance_not_owner, clearance_unmapped = [], [], []
    for name in ("infra", "business"):
        f = HERE / f"gate_clearance_{name}.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text())
        rows = data if isinstance(data, list) else (data.get("gates") or data.get("items")
                                                   or data.get("actions") or [])
        for g in rows:
            gate = g.get("gate") or g.get("key") or g.get("id")
            if gate == "customers" or str(g.get("classification", "")).upper().startswith(
                    ("DATA", "EXTERNAL")):
                clearance_not_owner.append({"lane": name, "gate": gate,
                                            "why": g.get("classification") or
                                            "customers is not an owner action"})
                continue
            d = Q.DECISION_BY_GATE.get(gate)
            if d is None:
                clearance_unmapped.append({"lane": name, "gate": gate})
                continue
            item = ensure_item(d["id"])
            item.setdefault("clearance", []).append({"lane": f"W4-GATES{name[0].upper()}",
                                                     "gate": gate, "detail": g})
            src = f"lane W4-GATES{'I' if name == 'infra' else 'B'}"
            if src not in item["sources"]:
                item["sources"].append(src)
            clearance_folded.append({"lane": name, "gate": gate, "decision": d["id"]})
    store = json.loads((HERE / "store_owner_actions.json").read_text())
    assert store, "store owner actions missing"
    company_work, deferred = [], []
    for a in store:
        m = STORE_MAP[a["id"]]
        if "merge_into" in m:
            item = ensure_item(m["merge_into"])
            item["sources"].append(f"lane STORE {a['id']}")
            item.setdefault("store_detail", []).append(a["action"])
            continue
        if "company_work" in m:
            company_work.append({"id": a["id"], "was": a["action"], "now": m["company_work"]})
            continue
        if "deferred" in m:
            deferred.append({"id": a["id"], "action": a["action"], "why": m["deferred"]})
            continue
        cost = a["max_cost"]
        cost_cad = 0.0 if cost == "CA$0" else None
        bmeta = Q.BATCH_BY_ID[m["batch"]]
        b = batches.setdefault(m["batch"], {"id": bmeta["id"], "title": bmeta["title"],
                                            "why_batched": bmeta["why_batched"], "items": []})
        b["items"].append({
            "id": a["id"], "batch": m["batch"], "decision": a["action"], "why": a["why"],
            "evidence": "research/final_build/w4/STORE_READINESS.md (origin/claude/w4-INTEG "
                        "7631026)",
            "max_cost_cad": cost_cad,
            "max_cost_basis": "stated" if cost_cad is not None else f"UNKNOWN ({cost})",
            "max_cost_display": f"CA${cost_cad:,.2f}" if cost_cad is not None else
            f"UNKNOWN ({cost})",
            "consequence_of_yes": m["yes"], "consequence_of_no": a["if_you_wait"],
            "minutes": a["minutes"], "sources": [f"lane STORE {a['id']}"],
            "fields_missing": []})
    vb = EXTRA_BATCHES["visual"]
    batches["visual"] = dict(vb, items=[dict(VISUAL_ITEM, max_cost_display="CA$4.01",
                                             fields_missing=[])])
    order = {b["id"]: b["order"] for b in Q.BATCHES}
    order["visual"] = EXTRA_BATCHES["visual"]["order"]
    out_batches = []
    for bid in sorted(batches, key=lambda k: order.get(k, 50)):
        b = batches[bid]
        costs = [i["max_cost_cad"] for i in b["items"]]
        unknown = any(c is None for c in costs)
        out_batches.append({
            "id": bid, "title": b["title"], "why_batched": b["why_batched"],
            "decisions": len(b["items"]),
            "minutes_total": sum(int(i["minutes"] or 0) for i in b["items"]),
            "max_cost_cad_total": None if unknown else round(sum(costs), 2),
            "max_cost_display": ("UNKNOWN (at least one item is not costed)" if unknown
                                 else f"CA${sum(costs):,.2f}"),
            "items": [{k: i.get(k) for k in (
                "id", "decision", "why", "evidence", "max_cost_cad", "max_cost_display",
                "max_cost_basis", "consequence_of_yes", "consequence_of_no", "minutes",
                "gates", "requirement_keys", "owner_action_ids", "b2_rows", "clearance", "sources",
                "store_detail",
                "fields_missing")} for i in b["items"]]})
    items = [i for b in out_batches for i in b["items"]]
    assert items and not [i for i in items if i["fields_missing"]]
    for i in items:
        assert i["max_cost_cad"] is not None or "UNKNOWN" in i["max_cost_display"], i["id"]
    before = len(PRODUCTION_9) + len(store) + 3 + len(inbox["cards"])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lane": "W4-OWNER",
        "sources": {"runtime": "build2.executor.approval_inbox (Command Center approvals inbox)",
                    "production_rows": "9 OwnerAction rows open on fcb982d 2026-10-06",
                    "store": "STORE_READINESS origin/claude/w4-INTEG 7631026",
                    "visual": "VISUAL_STATUS origin/claude/w4-VISUAL 32332f5"},
        "counts": {"before": {"production_owner_action_rows": len(PRODUCTION_9),
                              "runtime_gate_cards": len(inbox["cards"]),
                              "store_lane_items": len(store), "visual_lane_plans": 3,
                              "total_asks": before},
                   "after": {"batches": len(out_batches), "decisions": len(items),
                             "minutes_total": sum(b["minutes_total"] for b in out_batches)},
                   "converted_to_company_work": len(company_work) + 2,
                   "deferred": len(deferred)},
        "fields": ["decision", "why", "evidence", "max_cost_cad", "consequence_of_yes",
                   "consequence_of_no", "minutes"],
        "batches": out_batches,
        "converted_to_company_work": company_work + [
            {"id": "brand_clearance.knockout", "was": "run a trademark knock-out search",
             "now": "free public read-only search: company work; the owner decides only the "
                    "filing (launch/readiness.py TRADEMARK_SCREEN)"},
            {"id": "culture_feed", "was": "approval card for the culture_feed gate",
             "now": "opened by the company's own daily culture.sweep cadence "
                    "(owner_queue.COMPANY_OPENED_GATES); never shown as an owner ask"}],
        "no_longer_asked": [
            {"id": f"production owner action {ids['etsy_shop']} (etsy_shop)",
             "why": "the shop exists (executor gate etsy_shop, 2026-09-19); readiness now "
                    "reads the gate, so 'open the Etsy shop' is not asked again; KYC/payout/"
                    "tax become the etsy_kyc_payout confirmation"}],
        "deferred": deferred,
        "b2_owner_gated": {"rows": len(b2),
                           "decisions": len({v for v in b2_placed.values()
                                             if not v.startswith("NOT_")}),
                           "placement": {str(k): v for k, v in sorted(b2_placed.items())},
                           "source": json.loads((HERE / "b2_owner_gated.json").read_text())
                           ["source"]},
        "mislabelled_company_work": MISLABELLED,
        "gate_clearance": {"folded": clearance_folded, "not_owner": clearance_not_owner,
                           "unmapped": clearance_unmapped,
                           "pending": [n for n in ("infra", "business")
                                       if not (HERE / f"gate_clearance_{n}.json").exists()]},
        "b2_genuine_gate_evidence_gaps": EVIDENCE_GAPS,
    }


def _md_owner(d: dict) -> str:
    c = d["counts"]
    lines = ["# Owner actions -- decision packet (W4-OWNER)", "",
             f"Generated {d['generated_at']} by `research/final_build/w4/owner/"
             "build_owner_docs.py` from the runtime approvals inbox plus the STORE and VISUAL "
             "lanes. Phase stays SHADOW. UNKNOWN cost is never CA$0.", "",
             f"**Before:** {c['before']['total_asks']} separate asks "
             f"({c['before']['production_owner_action_rows']} production rows, "
             f"{c['before']['runtime_gate_cards']} gate cards, "
             f"{c['before']['store_lane_items']} store items, 3 visual plans). "
             f"**After:** {c['after']['decisions']} decisions in {c['after']['batches']} "
             f"batches, ~{c['after']['minutes_total']} owner minutes; "
             f"{c['converted_to_company_work']} converted back to company work, "
             f"{c['deferred']} deferred.", ""]
    for b in d["batches"]:
        lines += [f"## {b['title']} ({b['decisions']} decisions, {b['minutes_total']} min, "
                  f"max {b['max_cost_display']})", "", f"_{b['why_batched']}_", "",
                  "| id | decision | why | evidence | max cost | if yes | if no / delay | min |",
                  "|---|---|---|---|---|---|---|---|"]
        for i in b["items"]:
            cells = [i["id"], i["decision"], i["why"], i["evidence"] or "-",
                     i["max_cost_display"], i["consequence_of_yes"], i["consequence_of_no"],
                     str(i["minutes"])]
            lines.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ")
                                           for x in cells) + " |")
        lines.append("")
    lines += ["## Converted back to company work (not owner asks)", ""]
    lines += [f"- **{x['id']}**: was \"{x['was']}\" -> {x['now']}"
              for x in d["converted_to_company_work"]]
    lines += ["", "## No longer asked", ""]
    lines += [f"- **{x['id']}**: {x['why']}" for x in d["no_longer_asked"]]
    lines += ["", "## Deferred (not askable yet)", ""]
    lines += [f"- **{x['id']}** {x['action']}: {x['why']}" for x in d["deferred"]]
    b2 = d["b2_owner_gated"]
    lines += ["", f"## Build 2 OWNER-GATED rows ({b2['rows']} rows -> {b2['decisions']} "
              f"decisions above, each row exactly once)", "", f"Source: {b2['source']}.", ""]
    by_dec: dict[str, list[str]] = {}
    for row, did in b2["placement"].items():
        by_dec.setdefault(did, []).append(row)
    lines += [f"- `{did}`: #{', #'.join(rows)}" for did, rows in sorted(by_dec.items())]
    lines += ["", "## Mislabelled company work inside B2 owner gates", "",
              "| row | parked on | executable company part | owning lane |", "|---|---|---|---|"]
    lines += [f"| #{m['row']} | {m['gate']} | {m['executable_part']} | {m['owning_lane']} |"
              for m in d["mislabelled_company_work"]]
    gc = d["gate_clearance"]
    lines += ["", "## Gate-clearance lanes (W4-GATESI / W4-GATESB)", "",
              f"Folded onto existing decisions: {len(gc['folded'])}; not owner actions "
              f"(customers, data/external): {len(gc['not_owner'])}; unmapped: "
              f"{[u['gate'] for u in gc['unmapped']]}; pending (not yet pushed): "
              f"{gc['pending'] or 'none'}. Customers is never an owner action."]
    lines += ["", "Genuine owner gates with an unmapped test (company work for the ledger "
              "owner): " + "; ".join(f"#{g['row']} {g['note']}"
                                    for g in d["b2_genuine_gate_evidence_gaps"]) + "."]
    return "\n".join(lines) + "\n"


CLASS = {
    "seasonal.at_risk": ("stale/incoherent", "seasonal.sentinel re-keys by event+year and "
                         "reconciles; legacy un-keyed rows close by rule"),
    "seasonal.calendar_behind": ("stale", "seasonal.sentinel reconciles per occurrence"),
    "seasonal.preparation_late": ("stale", "seasonal.sentinel reconciles per stream"),
    "policy_stale": ("executable (company)", "ops.policy_watch reads the dated policy_knowledge reading and closes the row; readings dated 2026-09-26 go stale on the 30-day rule (2026-10-26) and are refreshed by a build session"),
    "stale-artefact": ("true condition", "artefacts sweep: closes when every artefact carries "
                       "a provenance row (company work, not owner)"),
    "build.stalled": ("stale", "build.tick reconciles on the watchdog verdict"),
}


def incidents() -> dict:
    from test_w4_owner_incidents import PRODUCTION_18, reproduce_production

    from brambleloop.ops import incident_lifecycle as L

    _db, out = reproduce_production()
    rows = []
    for sig, sev, slug in PRODUCTION_18:
        v = out["legacy"][sig]
        fam = L.kind_of(sig)
        cls, rule = CLASS.get(fam.split(":")[0], ("unclassified", ""))
        owner, path = L.REMEDIATION.get(fam, ("UNKNOWN", ""))
        rows.append({"signature": sig, "severity": sev, "product": slug, "family": fam,
                     "class": cls, "rule": rule, "remediation_owner": owner,
                     "remediation_path": path,
                     "status": "CLOSED" if v["resolved"] else "OPEN (condition true)",
                     "resolution": v["resolution"], "resolved_at": v["resolved_at"]})
    assert len(rows) == 18
    closed = sum(r["status"] == "CLOSED" for r in rows)
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "production /api/status open_incidents=18 (fcb982d, 2026-10-06); "
                      "reproduced by tests/test_w4_owner_incidents.py",
            "counts": {"before_open": 18, "after_closed_by_rule": closed,
                       "after_open": 18 - closed,
                       "owner_remediation": sum(r["remediation_owner"] == "owner"
                                                for r in rows),
                       "re_raised_current_year_keyed": len(out["new_open"])},
            "rules": ["duplicates close into the oldest row (incident_lifecycle."
                      "close_duplicates)", "a failed cadence closes once it enqueues again "
                      "(close_recovered_cadences)", "both run on every ops.health truth "
                      "sweep; closing never deletes; every close carries resolution and "
                      "resolved_at"],
            "incidents": rows, "re_raised": out["new_open"]}


def _md_incidents(d: dict) -> str:
    c = d["counts"]
    lines = ["# Incidents -- the 18 production held open (W4-OWNER)", "",
             f"Generated {d['generated_at']}. Source: {d['source']}.", "",
             f"**Before:** 18 open. **After (this build's handlers):** "
             f"{c['after_closed_by_rule']} closed by rule with a resolution and resolved_at, "
             f"{c['after_open']} open because its condition is true; "
             f"{c['owner_remediation']} need the owner; {c['re_raised_current_year_keyed']} "
             "current conditions re-raised year-keyed. Production converges after the next "
             "deploy (owner decision `production_window`).", "", "Rules: " +
             "; ".join(d["rules"]) + ".", "",
             "| signature | sev | class | remediation owner | status | resolution |",
             "|---|---|---|---|---|---|"]
    for r in d["incidents"]:
        lines.append("| " + " | ".join(str(x).replace("|", "/") for x in (
            r["signature"], r["severity"], r["class"], r["remediation_owner"], r["status"],
            (r["resolution"] or "-")[:220])) + " |")
    if d["re_raised"]:
        lines += ["", "## Re-raised by this build (current, year-keyed)", ""]
        lines += [f"- `{r['signature']}` ({r['severity']}): {r['summary'][:200]}"
                  for r in d["re_raised"]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    oa = owner_actions()
    (OUT / "OWNER_ACTIONS.json").write_text(json.dumps(oa, indent=1, default=str) + "\n")
    (OUT / "OWNER_ACTIONS.md").write_text(_md_owner(oa))
    inc = incidents()
    (OUT / "INCIDENTS.json").write_text(json.dumps(inc, indent=1, default=str) + "\n")
    (OUT / "INCIDENTS.md").write_text(_md_incidents(inc))
    print("OK owner_actions", json.dumps(oa["counts"]))
    print("OK incidents", json.dumps(inc["counts"]))
