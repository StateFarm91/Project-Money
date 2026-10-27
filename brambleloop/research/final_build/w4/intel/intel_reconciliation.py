#!/usr/bin/env python3
"""W4-INTELREC: competitive-intelligence and autonomous-learning requirement reconciliation.

Deterministic, from committed evidence only:
  * acceptance text: build2/requirements.json (Build 2 v1.4.3, the original #1-#320 bodies) and
    research/final_build/master_registry*.json (Final Master v1.0/v1.1, parsed from the PDFs);
  * Master Plan v1.2 sections that have no registry ID, quoted from spec/01 (text extracted
    with pdftotext);
  * status: research/final_build/w4/FM_LEDGER.json and BUILD2_LEDGER.json;
  * deployed: whether the producing module exists in production b2e49455 (`git cat-file`);
  * executing: evidence_INTELREC/prod_job_counts_2026-10-26T1724Z.json (an anonymous /api/jobs
    capture taken before SECPATCH closed the route; no token was used).

Anything this cannot prove from those files is written "no evidence" or "needs operator
readback" -- never inferred.

  python3 research/final_build/w4/intel/intel_reconciliation.py   (from brambleloop/)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
W4 = ROOT / "research" / "final_build" / "w4"
HERE = Path(__file__).resolve().parent
EV = HERE / "evidence"
PROD = "b2e49455"          # production: 051dbee2 + SECPATCH
# Review 720b291 N-10: the SHA is verified via /health (coordinator readback, 21:50Z); the
# 17:24Z captures predate it and name 051dbee2.
PROD_EVIDENCE = ("verified via /health at 2026-10-26T21:50Z (coordinator readback; "
                 "evidence/prod_health_2026-10-26T2150Z.json)")
CAPTURES_BUILD = "051dbee2 (pre-SECPATCH)"
# Coordinator note 2026-10-27: a source-coverage limitation, not a search error.
SOURCE_COVERAGE = ("the reconciliation searched every in-repo source; Master v5 "
                   "(Brambleloop_Master_v5_Direct.pdf, owner-recovered) was not available to it. "
                   "Its Addendum v3 requires permanent MadelineMaeCo monitoring, and later "
                   "addenda specify the Plush Culture Radar, Trend-to-Crochet and the Product "
                   "Family Engine; their requirement wording is to be imported when the owner "
                   "supplies the document. Master v5 implementation is reserved for the next "
                   "phase.")
COMBINED = "67920948"      # claude/w4-INTEG7, the combined candidate this branch is cut from
INTELREC = "HEAD"          # this branch (unreviewed batch 4 code)

STEPS = ("specified", "implemented", "tested", "integrated", "reviewed", "deployed",
         "scheduled_executing", "valid_evidence", "feeds_decisions", "verified")

# requirement -> (topic, job types that execute it, extra module paths)
B2 = {
    205: ("watchlist", ["intel.benchmark_health"], ["intel/benchmarks.py"]),
    206: ("mjs", ["intel.benchmark_health"], ["intel/benchmarks.py"]),
    207: ("mjs", ["mjs.scan"], ["intel/observe.py"]),
    208: ("mjs", ["mjs.scan"], ["intel/observe.py"]),
    209: ("imagery", ["intel.gallery_analysis"], ["intel/vision.py"]),
    210: ("mjs", ["intel.pod_learning"], ["intel/pods.py"]),
    211: ("mjs", ["mjs.scan"], ["intel/mission_runtime.py"]),
    212: ("mjs", ["mjs.scan"], ["intel/observe.py"]),
    213: ("mjs", ["mjs.scan"], ["intel/observe.py"]),
    214: ("mjs", ["mjs.scan"], ["intel/mission_runtime.py"]),
    215: ("differentiation", ["creative.tournament"], ["intel/mission_runtime.py"]),
    216: ("differentiation", ["creative.tournament"], ["creative/breakthrough.py"]),
    217: ("mjs", ["mjs.scan"], ["intel/mechanisms.py"]),
    218: ("differentiation", ["creative.blind_review", "creative.grid_tournament"],
          ["creative/blind_review.py"]),
    219: ("watchlist", ["intel.panel_discovery"], ["intel/panel.py", "intel/panel_discovery.py"]),
    220: ("watchlist", [], ["intel/panel.py"]),
    224: ("mjs", ["mjs.scan"], ["intel/observe.py"]),
    225: ("mjs", ["mjs.scan"], ["intel/observe.py"]),
    226: ("learning", ["intel.pod_learning"], ["intel/pod_learning.py"]),
    227: ("differentiation", ["creative.tournament"], ["intel/panel.py"]),
    301: ("mjs", ["mjs.scan"], ["intel/benchmarks.py"]),
    302: ("mjs", ["mjs.scan"], ["intel/capacity.py"]),
    303: ("catalogue", ["mjs.scan"], ["intel/market_map.py", "intel/observe.py"]),
    304: ("imagery", ["intel.gallery_analysis"], ["intel/vision.py"]),
    305: ("differentiation", [], ["gates/originality.py"]),
    306: ("differentiation", ["creative.tournament"], ["intel/panel.py"]),
    307: ("seasonal", ["mjs.seasonal_sentinel"], ["intel/mission_runtime.py"]),
    309: ("seasonal", ["mjs.scan", "mjs.seasonal_sentinel"], ["intel/mission_runtime.py"]),
    310: ("seasonal", ["mjs.seasonal_sentinel"], ["intel/mission_runtime.py"]),
    311: ("seasonal", ["mjs.seasonal_sentinel"], ["intel/mission_runtime.py"]),
    312: ("mjs", ["intel.pod_learning"], ["intel/pods.py"]),
    313: ("mjs", ["mjs.scan"], ["intel/observe.py"]),
    314: ("opportunities", ["radar.score"], ["intel/coverage.py"]),
    315: ("differentiation", ["creative.blind_review"], ["creative/blind_review.py"]),
    316: ("learning", ["intel.pod_learning"], ["intel/pod_learning.py"]),
    317: ("library", [], ["intel/purchase_selection.py"]),
    318: ("mjs", [], ["intel/mission.py"]),
    319: ("mjs", ["mjs.scan"], ["intel/mission.py"]),
    320: ("mjs", ["mjs.scan"], ["intel/acceptance.py"]),
    281: ("seasonal", ["mjs.seasonal_sentinel"], ["intel/mission_runtime.py"]),
    299: ("seasonal", ["seasonal.engine"], ["seasonal/benchmark_matrix.py"]),
    2: ("opportunities", ["radar.scan", "radar.score"], ["radar/arbitrage.py"]),
    22: ("amplification", [], []),
    38: ("trends", ["radar.scan"], ["radar/provenance.py"]),
    67: ("imagery", ["creative.image_benchmark"], []),
    98: ("learning", ["mjs.scan"], ["intel/learning.py"]),
    121: ("seasonal", ["seasonal.engine"], []),
    128: ("trends", ["seasonal.harvest"], []),
    133: ("culture", ["culture.sweep"], []),
    134: ("culture", ["culture.sweep"], []),
    136: ("culture", ["culture.sweep"], []),
    140: ("culture", ["culture.sweep"], []),
    144: ("culture", ["culture.sweep"], []),
    147: ("culture", ["culture.sweep"], []),
    148: ("library", ["teardown.enforce"], []),
    149: ("library", [], []),
    165: ("library", ["intel.benchmark_refresh"], ["intel/benchmark_refresh.py"]),
    167: ("library", [], []),
    277: ("trends", ["seasonal.engine"], []),
    286: ("seasonal", ["seasonal.engine"], []),
    295: ("amplification", [], []),
}
FM = {
    "F-061": ("library", [], []), "F-069": ("library", ["intel.benchmark_refresh"], []),
    "F-191": ("mjs", ["mjs.scan"], []), "F-192": ("mjs", ["mjs.scan"], []),
    "F-224": ("imagery", ["creative.photo_principles"], []),
    "F-351": ("families", ["intel.children_portfolio"], []),
    "F-367": ("watchlist", ["intel.children_portfolio"], []),
    "F-373": ("learning", [], []), "F-384": ("learning", [], []),
    "F-390": ("learning", ["seasonal.harvest"], []), "F-399": ("learning", [], []),
    "F-401": ("research_agent", ["research.sweep"], ["intel/research_agent.py"]),
    "F-418": ("research_agent", [], []),
    "F-429": ("research_agent", ["research.flag_architecture"], ["intel/research_agent.py"]),
    "F-430": ("research_agent", [], []),
    "F-436": ("research_agent", ["research.investigate"], ["intel/research_agent.py"]),
    # W4-INTELREC C05 (CLUSTERS.md): rows built or wired in this cluster.
    "F-402": ("research_agent", ["research.investigate"], ["intel/research_agent.py"]),
    "F-404": ("research_agent", ["research.sweep"], ["intel/research_agent.py"]),
    "F-406": ("research_agent", ["research.investigate", "learn.scan"],
              ["intel/research_agent.py", "intel/research_fetch.py"]),
    "F-231": ("imagery", ["creative.photo_principles"], ["intel/gallery_grammar.py"]),
    "F-565": ("opportunities", ["intel.serp_capture"], ["intel/insights_score.py"]),
    # W4-INTELREC C06: the children's catalogue rows (C1 creative.children + launch.mix).
    "F-353": ("families", ["intel.children_portfolio"], ["creative/children.py"]),
    "F-358": ("families", ["intel.children_portfolio"], ["creative/children.py"]),
    "F-359": ("families", ["intel.children_portfolio"], ["creative/children.py"]),
    "F-365": ("families", ["intel.children_portfolio"], ["creative/children.py"]),
    "F-366": ("families", [], ["launch/mix.py", "creative/children.py"]),
    "F-370": ("families", [], ["launch/mix.py"]),
    "F-440": ("differentiation", [], []), "F-447": ("research_agent", [], []),
    "F-478": ("research_agent", [], []), "F-673": ("opportunities", [], []),
    "F-705": ("learning", ["improve.mine", "improve.weekly"], []),
    "F-780": ("differentiation", [], []), "F-781": ("differentiation", [], []),
    "F-785": ("differentiation", [], []), "F-789": ("differentiation", [], []),
    "F-796": ("library", [], []), "F-797": ("library", [], []),
}
# Master Plan v1.2 (spec/01) and owner directives with no registry ID. Quoted verbatim.
UNREGISTERED = [
    {"id": "MP1.2-s4", "topic": "watchlist", "source": "spec/01_Brambleloop_Master_Plan_v1.2.pdf s4",
     "text": ("Maintain longitudinal profiles for serious competitors: catalogue mix, launches, "
              "visible bestseller/review signals, pricing, promotions, bundles, hero photography, "
              "recurring model use, video, free-vs-paid content, launch timing, websites, "
              "YouTube/Pinterest, praise and complaints. Agents: Discovery, Digital Twin Builder, "
              "Change Detector, Review Miner, White-Space, Category Analyst, Trend Forecaster and "
              "Seasonality Engine. Learn why winners work; never copy protected expression."),
     "jobs": ["mjs.scan", "mjs.reviews"],
     "ledger": "OMISSION: no FM or Build 2 row carries 'longitudinal profiles for serious "
               "competitors' beyond MJs (#303 is MJs-only); tracked only as a BUILD_STATE section"},
    {"id": "MP1.2-s5", "topic": "amplification", "source": "spec/01 s5",
     "text": ("Winner Amplification turns proven demand into matching products, bundles, sizes, "
              "colourways, tutorials, content and controlled ad expansion."),
     "jobs": ["creative.family_engine"], "modules": ["creative/family_engine.py"],
     "tests": ["tests/test_w4_intelrec_amplify.py"],
     "ledger": "OMISSION as a named row: DEPARTMENTS.md records that no row is named 'Product "
               "Family Engine'; covered in part by #22, #295, #111 and F-351"},
    {"id": "MP1.2-s9", "topic": "pricing", "source": "spec/01 s9",
     "text": ("Create Market Price Scanner, Price Positioning Agent, Promotion Agent, Price "
              "Experiment Agent, Bundle Economist and Revenue Optimizer. Observe comparable price, "
              "complexity, charts/video, seller maturity, category, season, bundle size, visible "
              "promotion and our conversion."),
     "jobs": ["mjs.scan"],
     "ledger": "OMISSION: no FM/B2 row names a competitor price/promotion scanner; competitor "
               "price_cad and on_sale are stored per benchmark listing (intel/observe.py)"},
    {"id": "MP1.2-s16-cadence", "topic": "watchlist", "source": "spec/01 cadence paragraph",
     "text": ("6-hour meaningful market/store/ad signal review; daily sales/traffic/pricing/ads/"
              "support/competitor/pipeline/cash review"),
     "jobs": ["radar.scan", "mjs.scan"], "ledger": "cadence only; no row"},
    {"id": "SEEDS-05", "topic": "seeds", "source": "spec/05_Competitor_and_Market_Seeds.txt",
     "text": 'Use these as initial research targets, not designs to copy. ... Research objectives: category mix and whitespace; release cadence and seasonality; product ladders and bundles; regular vs promotional pricing observations; first-image/thumbnail patterns; use of recurring human models; PDF + video positioning; reviews: delight, confusion, missing features; external traffic/content ecosystems; bestseller/trending signals where publicly visible; do NOT copy protected designs, charts, text or photography',
     "jobs": [], "modules": ["radar/market.py"],
     "ledger": "OMISSION: the seed list and its ten research objectives have no ledger row; "
               "radar/market.COMPETITORS holds one dated profile per seed shop (observed "
               "2026-09-17), which is a snapshot, not monitoring"},
    {"id": 'SEEDS-05-HANJAN', "topic": "seeds", "source": "spec/05_Competitor_and_Market_Seeds.txt",
     "text": "HanJanCrochet shop\nhttps://www.etsy.com/ca/shop/HanJanCrochet?ref=shop_profile&listing_id=4564723597\n\nHanJan Fall Crochet Blanket example\nhttps://www.etsy.com/ca/listing/4564723597/pattern-video-fall-crochet-blanket",
     "jobs": ['intel.panel_discovery'], "modules": ['radar/market.py', 'intel/second_market.py', 'intel/panel_discovery.py'],
     "ledger": "OMISSION: no ledger row for the seed. Code: a dated static profile (radar/market.COMPETITORS, observed 2026-09-17) and a second-market candidate (intel/second_market.CANDIDATES, D-W4-GATESB-1) that intel.panel_discovery joins and scans weekly once getShop verifies its stated market. Production: panel_discovery ran 3 times (last job 27000) and the second_market_benchmark gate reads OPEN at 17:24Z, so some non-US benchmark has observed listings; whether it is HanJanCrochet needs operator readback"},
    {"id": 'SEEDS-05-IVYLOOP', "topic": "seeds", "source": "spec/05_Competitor_and_Market_Seeds.txt",
     "text": "IvyLoop shop\nhttps://www.etsy.com/ca/shop/IvyLoop?ref=shop_profile&listing_id=4554452706",
     "jobs": [], "modules": ['radar/market.py'],
     "ledger": "OMISSION: no ledger row. Code: radar/market.COMPETITORS profile reads 'Seeded by owner; profile to be filled on first live scan' / 'Not yet observed' -- never registered, never scanned"},
    {"id": 'SEEDS-05-MJS', "topic": "seeds", "source": "spec/05_Competitor_and_Market_Seeds.txt",
     "text": "MJsOffTheHookDesigns shop\nhttps://www.etsy.com/ca/shop/MJsOffTheHookDesigns?ref=shop_profile&listing_id=1812302425\n\nMJs Autumn's Charm example\nhttps://www.etsy.com/ca/listing/1812302425/crochet-pattern-video-autumns-charm",
     "jobs": ['mjs.scan'], "modules": ['intel/benchmarks.py'],
     "ledger": "covered: became the #301 anchor (Build 2 #205-#320)"},
    {"id": 'SEEDS-05-LOVEANDSTITCH', "topic": "seeds", "source": "spec/05_Competitor_and_Market_Seeds.txt",
     "text": "LoveandStitchDesigns\nhttps://www.etsy.com/ca/shop/LoveandStitchDesigns?ref=shop_profile&listing_id=1296978586\n\nEveryday Striped example\nhttps://www.etsy.com/ca/listing/754562757/crochet-pattern-video-everyday-striped",
     "jobs": [], "modules": ['radar/market.py'],
     "ledger": "OMISSION: no ledger row. Code: a dated static profile only (observed 2026-09-17: garments, recurring human model, 55% display discount); never registered or scanned; its name feeds seo.truth's competitor-name refusal and commerce.pricing_intel"},
    {"id": 'SEEDS-05-FIREFLY', "topic": "seeds", "source": "spec/05_Competitor_and_Market_Seeds.txt",
     "text": "FireflyCrochets\nhttps://www.etsy.com/ca/shop/FireflyCrochets?ref=shop_profile&listing_id=735974986\n\nChristmas Moose / Reindeer example\nhttps://www.etsy.com/ca/listing/735974986/christmas-crochet-moose-pattern-reindeer",
     "jobs": [], "modules": ['radar/market.py'],
     "ledger": "OMISSION: no ledger row. Code: a dated static profile only (observed 2026-09-17: character amigurumi, low price point); never registered or scanned"},
    {"id": 'SEEDS-05-SEARCH', "topic": "seeds", "source": "spec/05_Competitor_and_Market_Seeds.txt",
     "text": "Current crochet-pattern search seed\nhttps://www.etsy.com/search?as_prefix=crochet&q=crochet%20pattern&order=most_relevant&view_type=gallery&explicit=1&is_star_seller=true&is_merch_library=true",
     "jobs": ['intel.serp_capture'], "modules": ['intel/serp.py'],
     "ledger": "partly covered: the rendered search page answers software with 403 (B-268/B-500); the sanctioned substitute is the API search index (intel.serp_capture, 16 production runs), labelled PROXY"},
    {"id": "OWNER-2026-10-26-WATCHLIST", "topic": "watchlist",
     "source": "owner directive relayed by the coordinator, 2026-10-26",
     "text": ("Watchlist (permanent, exact): MJsOffTheHookDesigns (Mrs J) "
              "https://www.etsy.com/shop/MJsOffTheHookDesigns; MadelineMaeCo "
              "https://www.etsy.com/shop/MadelineMaeCo; ZKBDESIGNER "
              "https://www.etsy.com/ca/shop/ZKBDESIGNER; TheEasyDesign "
              "https://www.etsy.com/ca/shop/TheEasyDesign. Keep the original special monitoring "
              "for Mrs J and MadelineMaeCo. The two new shops are permanent benchmarks, not "
              "replacements. Never assume a shop is AI-operated without evidence."),
     "jobs": ["intel.watchlist_scan", "intel.watchlist_compare", "intel.opportunity_review"],
     "modules": ["intel/watchlist.py", "runtime/intel_ops.py"],
     "tests": ["tests/test_w4_intelrec_watchlist.py"],
     "ledger": "NEW in this repository's ledger on 2026-10-26. MadelineMaeCo special "
               "monitoring is specified in Master v5 Addendum v3 (owner-recovered, not in "
               "repo); the requirement wording is to be imported when the owner supplies the "
               "document. Source-coverage limitation: the reconciliation searched every "
               "in-repo source; Master v5 was not available to it"},
    {"id": "SPEC13-LAURA", "topic": "laura",
     "source": "spec/13_Laura_CEO_Autonomy_and_Private_Laura_Venice_2026-10-20.md",
     "text": "Laura observes company state and delegates through the COO (D-FB-13).",
     "jobs": ["laura.executive_tick"], "modules": ["laura/executive/loop.py"],
     "ledger": "Laura's PROVIDERS (laura/executive/loop.py) carry no intelligence/competitor "
               "provider: competitor findings never reach her OBSERVE step"},
]


# Step 9 by topic, from the production job counts and the code (laura/executive/loop.py,
# runtime/pipeline.py, creative/intake.py). None = partial or needs readback.
_TOURNAMENTS = ("feeds mission tournaments (creative.tournament executed 191 times in "
                "production, last job 33597) and lesson nudges in radar.score (544 executed); "
                "does NOT reach engineering in production since cir.draft job 24731 (the intake "
                "decision runs inside the tournament; its creative.winner_intake audits need operator "
                "readback). Laura observed no intelligence provider before INTELREC")
CHAIN = {
    "mjs": (None, _TOURNAMENTS), "catalogue": (None, _TOURNAMENTS),
    "imagery": (None, _TOURNAMENTS), "seasonal": (None, _TOURNAMENTS),
    "differentiation": (None, _TOURNAMENTS), "opportunities": (None, _TOURNAMENTS),
    "watchlist": (False, "MadelineMaeCo, ZKBDESIGNER and TheEasyDesign were not observed in "
                         "production. The code-declared registry is Mrs J only "
                         "(intel/benchmarks.REGISTRY == (MJS,) at b2e49455); panel members "
                         "join only from evidence (intel.panel_discovery, 3 runs) -- the "
                         "second_market_benchmark gate reads open, so at least one non-US "
                         "panel member is observed; which needs operator readback"),
    "laura": (False, "laura/executive/loop.py PROVIDERS had no intelligence provider: competitor "
                     "findings reached Laura only as idle-queue generator candidates"),
    "research_agent": (False, "research.sweep / research.investigate are in the combined "
                              "candidate only; 0 executions in production"),
    "seeds": (None, "a seed shop is a research target (spec/05); it feeds decisions only as "
                    "the static radar/market profile read by pricing_intel and seo.truth, "
                    "or -- for a shop panel discovery joined -- through the observed rows; "
                    "rejoining the permanent watchlist is an owner decision"),
    "library": (False, "the benchmark library is owner-gated: no benchmark has been purchased "
                        "(production /api/benchmark-selection: purchased 0), so there is "
                        "nothing to tear down or learn from yet"),
    "amplification": (False, "creative.family_engine is in the combined candidate only; Winner "
                             "Amplification needs orders, and production has none"),
}



# The rows a stored listing count is valid evidence for (review M-5, INDEPENDENT_SECREVIEW_
# INTELREC.md): the full-catalogue baseline, the listing-by-listing audit, baseline-then-
# change detection and high-priority change detection.
COUNT_EVIDENCES = frozenset({"B2#207", "B2#208", "B2#212", "B2#313"})

def _git_has(rev: str, rel: str) -> bool:
    if not rel:
        return False
    return subprocess.run(["git", "cat-file", "-e", f"{rev}:brambleloop/src/brambleloop/{rel}"],
                          cwd=ROOT, capture_output=True).returncode == 0


def _producer_modules(text: str) -> list[str]:
    """Module paths named in a ledger `producer` string ('a.py::f; b/c.py (note)')."""
    import re

    out = []
    for m in re.findall(r"([A-Za-z0-9_/]+\.py)", text):
        m = m.replace("src/brambleloop/", "")
        if "/" in m:
            out.append(m)
    return out


def _jobs(job_types, counts) -> dict:
    out = {}
    for jt in job_types:
        c = counts.get(jt)
        out[jt] = ({"n": c["n"], "last_id": c["last_id"], "by_status": c["by_status"]}
                   if c else {"n": 0})
    return out


def build() -> dict:
    b2_text = {r["id"]: r for r in json.loads(
        (ROOT / "src/brambleloop/build2/requirements.json").read_text())}
    b2_led = {r["id"]: r for r in json.loads((W4 / "BUILD2_LEDGER.json").read_text())["rows"]}
    reg = json.loads((ROOT / "research/final_build/master_registry.json").read_text())
    reg = reg["requirements"] if isinstance(reg, dict) else reg
    reg = list(reg) + list(json.loads(
        (ROOT / "research/final_build/master_registry_v1_1.json").read_text())["requirements"])
    fm_text = {r["id"]: r for r in reg}
    fm_led = {r["uid"]: r for r in json.loads((W4 / "FM_LEDGER.json").read_text())["rows"]}
    counts = json.loads((EV / "prod_job_counts_2026-10-26T1724Z.json").read_text())["jobs"]
    sel = json.loads((EV / "prod_benchmark_selection_2026-10-26T1356Z.json").read_text())
    rows = []

    def status(rid, topic, title, text, source, modules, tests, integrated, verified,
               job_types, ledger_state):
        deployed_mods = [m for m in modules if _git_has(PROD, m)]
        combined_only = [m for m in modules if not _git_has(PROD, m) and _git_has(COMBINED, m)]
        intelrec_only = [m for m in modules if not _git_has(COMBINED, m)
                         and _git_has(INTELREC, m)]
        ex = _jobs(job_types, counts)
        running = {k: v for k, v in ex.items() if v.get("n")}
        s = {
            "specified": {"ok": True, "evidence": source},
            "implemented": {"ok": bool(modules),
                            "evidence": modules or "no evidence (no producing module named)"},
            "tested": {"ok": bool(tests), "evidence": tests[:6] or "no evidence"},
            "integrated": {"ok": bool(integrated), "evidence": integrated or "no evidence"},
            "reviewed": {"ok": None, "evidence": "no per-row evidence: independent reviews are "
                                                 "per branch (INDEPENDENT_SECREVIEW_*), not per "
                                                 "requirement"},
            "deployed": {"ok": bool(deployed_mods) if modules else None,
                         "evidence": ({"in_production_b2e49455": deployed_mods,
                                       "combined_candidate_only": combined_only,
                                       "intelrec_only_unreviewed": intelrec_only}
                                      if modules else "no module to check")},
            "scheduled_executing": {"ok": bool(running) if job_types else None,
                                    "evidence": ex if job_types else
                                    "no job type executes this (API/gate/policy row)"},
            "valid_evidence": {"ok": None, "evidence": "needs operator readback"},
            "feeds_decisions": {"ok": None, "evidence": "needs operator readback"},
            "verified": {"ok": bool(verified), "evidence": verified or "no evidence"},
        }
        last = max((v.get("last_id") or 0 for v in ex.values()), default=0)
        missing, blocker = [], None
        if not modules:
            missing.append("code: no producing module")
        if modules and not deployed_mods:
            missing.append("activation: deploy " + ", ".join(combined_only + intelrec_only))
            blocker = blocker or "not deployed"
        if job_types and not running:
            missing.append("activation: no production execution of " + ", ".join(job_types))
            blocker = blocker or "never executed in production"
        if not verified:
            missing.append("evidence: ledger not PROVEN -- " + str(ledger_state)[:160])
            blocker = blocker or str(ledger_state)[:200]
        missing.append("external evidence: operator readback of what the runs produced")
        rows.append({
            "id": rid, "topic": topic, "title": title, "acceptance_text": text,
            "ledger_state": ledger_state,
            "implementation_path": modules or [],
            "branch_sha": {"production": f"b2e49455: {deployed_mods}",
                           "combined": f"claude/w4-INTEG7 67920948: {combined_only}",
                           "intelrec": f"claude/w4-INTELREC HEAD: {intelrec_only}"},
            "tests": tests[:8],
            "integration": integrated or "no runtime consumer recorded",
            "security_review": ("UNREVIEWED (INTELREC batch 4)" if intelrec_only else
                                "branch-level release reviews of the deployed lineage; no "
                                "per-requirement record" if deployed_mods else
                                "combined-candidate lane reviews (AGENTS a14c9ef/b199cdb, "
                                "FMBATCH1 cbd4ff1, INTEG7 967502d); no per-requirement record"
                                if combined_only else "none"),
            "deployment": ("production b2e49455" if deployed_mods else
                           "combined candidate only" if combined_only else
                           "INTELREC only" if intelrec_only else "n/a (no module)"),
            "last_production_execution": (f"job id {last} (snapshot 2026-10-26T17:24Z, "
                                          f"taken from {CAPTURES_BUILD})"
                                          if last else "none in the snapshot"),
            "evidence_quality": ("production job record" if running else
                                 "code + tests (offline)" if tests else
                                 "code only" if modules else "spec only"),
            "missing_work": missing, "acceptance_blocker": blocker or
            "operator readback of production output", "steps": s})

    for rid, (topic, jobs, extra) in sorted(B2.items()):
        t = b2_text[rid]
        led = b2_led.get(rid, {})
        ev = led.get("evidence") or {}
        mods = sorted(set((ev.get("tested_modules") or []) + (ev.get("artefacts") or [])
                          + extra))
        integ = [c["module"] + ": " + c["why"][:120] for c in ev.get("runtime_consumers") or []]
        ver = (f"ledger {led.get('state')} / {led.get('closure_state')}"
               if led.get("state") == "PROVEN" else None)
        status(f"B2#{rid}", topic, t["title"], t["body"],
               "spec/08_Brambleloop_Queued_Upgrades_v1.4.3_MASTER.pdf (build2/requirements.json)",
               mods, ev.get("tests") or [], integ, ver, jobs,
               f"{led.get('state')} ({led.get('closure_state')}): {led.get('why', '')[:160]}")
    for rid, (topic, jobs, extra) in sorted(FM.items()):
        t = fm_text.get(rid, {})
        led = fm_led.get(rid, {})
        mods = sorted(set(_producer_modules(led.get("producer") or "")) | set(extra))
        integ = ([f"maturity {led.get('maturity')}; consumer: {str(led.get('consumer'))[:160]}"]
                 if led.get("maturity") in ("INTEGRATED", "DEPLOYED", "EXERCISED",
                                            "PRODUCTION-OBSERVED", "COMMERCIALLY-EVIDENCED")
                 else [])
        ver = (f"ledger {led.get('status')} at {led.get('maturity')}"
               if led.get("status") in ("PROVEN", "COMPLETE") else None)
        status(rid, topic, t.get("title", led.get("title", "")),
               t.get("full_text") or t.get("text", ""),
               f"Final Master {t.get('version', '')} (research/final_build/master_registry*.json)",
               mods, led.get("tests") or [], integ, ver, jobs,
               f"{led.get('status')} at {led.get('maturity')}")
    for u in UNREGISTERED:
        status(u["id"], u["topic"], u["id"], u["text"], u["source"], u.get("modules", []),
               u.get("tests", []), [], None,
               u["jobs"], u["ledger"])

    # Evidence the public snapshots do give (step 8), and the chain (step 9).
    # Review M-5: the listing-count reading evidences only the requirements whose acceptance
    # text is the catalogue scan itself; every other row needs its own operator readback.
    for r in rows:
        if r["id"] in COUNT_EVIDENCES and \
                "mjs.scan" in r["steps"]["scheduled_executing"]["evidence"]:
            r["steps"]["valid_evidence"] = {
                "ok": True, "evidence": (f"production /api/benchmark-selection "
                                         f"{sel['source'][-25:]}: {sel['benchmark']} observed "
                                         f"{sel['observed']} listings (catalogue read through "
                                         f"the official API)")}
    for r in rows:
        why = CHAIN.get(r["topic"])
        if why:
            r["steps"]["feeds_decisions"] = {"ok": why[0], "evidence": why[1]}
    return {"generated_by": "research/final_build/w4/intel/intel_reconciliation.py",
            "production": PROD, "production_evidence": PROD_EVIDENCE,
            "captures_build": CAPTURES_BUILD, "source_coverage": SOURCE_COVERAGE,
            "combined_candidate": "claude/w4-INTEG7 67920948",
            "steps": list(STEPS), "rows": rows,
            "summary": summarise(rows)}


def summarise(rows) -> dict:
    out = {}
    for step in STEPS:
        c = {"yes": 0, "no": 0, "unknown": 0}
        for r in rows:
            ok = r["steps"][step]["ok"]
            c["yes" if ok else "unknown" if ok is None else "no"] += 1
        out[step] = c
    return {"requirements": len(rows), "by_step": out,
            "omissions": [r["id"] for r in rows if str(r["ledger_state"]).startswith(
                ("OMISSION", "NEW"))],
            "seed_shops": [r["id"] for r in rows if r["id"].startswith("SEEDS-05-")]}


def _mark(ok) -> str:
    return "Y" if ok else "?" if ok is None else "N"


def render_md(data: dict) -> str:
    rows = data["rows"]
    sm = data["summary"]
    out = ["# Traceability: competitive intelligence and autonomous learning (W4-INTELREC)", "",
           "Generated by `intel_reconciliation.py` from committed evidence. Do not edit by "
           "hand; rerun the generator.",
           "",
           f"- **Rows:** {sm['requirements']}. They are Build 2 v1.4.3, Final Master v1.0/v1.1, "
           "the Master Plan v1.2 sections, the spec/05 seeds, spec/13 and the owner "
           "directive of 2026-10-26.",
           f"- **Production:** {data['production']}, {data['production_evidence']}. "
           f"Deployment (step 6) is a code fact at that SHA (`git cat-file`). The 17:24Z "
           f"captures behind steps 7 and 8 were taken from {data['captures_build']}.",
           f"- **Combined candidate:** {data['combined_candidate']}.",
           f"- **Source coverage:** {data['source_coverage']}",
           "",
           "**Stage key.** The ten stages appear in this order:",
           "",
           "1. specified",
           "2. implemented",
           "3. tested",
           "4. integrated",
           "5. reviewed",
           "6. deployed",
           "7. scheduled and executing",
           "8. valid evidence",
           "9. feeds decisions",
           "10. verified",
           "",
           "Each is marked `Y` (evidence), `N` (evidence of absence), or `?` (no per-row "
           "record, or needs operator readback). `?` is never counted as `Y`.", "",
           "## Counts by stage (these reconcile to the rows)", "",
           "| stage | Y | N | ? |", "|---|---|---|---|"]
    for st, c in sm["by_step"].items():
        out.append(f"| {st} | {c['yes']} | {c['no']} | {c['unknown']} |")
    out += ["", "## Omitted from the ledger (flagged separately)", ""]
    for r in rows:
        if r["id"] in sm["omissions"]:
            out.append(f"- **{r['id']}:** {r['ledger_state']}")
    out += ["", "## Summary table", "",
            "| ID | Title | Stages 1-10 | Deployment | Last production execution | Evidence quality | Acceptance blocker |",
            "|---|---|---|---|---|---|---|"]
    for r in rows:
        st = "".join(_mark(r["steps"][k]["ok"]) for k in STEPS)
        title = str(r["title"]).replace("|", "/")[:60]
        blocker = str(r["acceptance_blocker"]).replace("|", "/")[:120]
        out.append(f"| {r['id']} | {title} | `{st}` | {r['deployment']} | "
                   f"{r['last_production_execution']} | {r['evidence_quality']} | {blocker} |")
    out += ["", "## Rows", ""]
    for r in rows:
        out += [f"### {r['id']}: {r['title']}", "",
                f"**Original acceptance wording (verbatim):** {r['acceptance_text']}", "",
                f"- **Implementation path:** {', '.join(r['implementation_path']) or 'none'}",
                f"- **Branch and SHA:** production {r['branch_sha']['production']}; "
                f"combined {r['branch_sha']['combined']}; "
                f"INTELREC {r['branch_sha']['intelrec']}",
                f"- **Tests:** {', '.join(r['tests']) or 'none recorded'}",
                f"- **Integration:** {r['integration'] if isinstance(r['integration'], str) else '; '.join(r['integration'])[:400]}",
                f"- **Security review:** {r['security_review']}",
                f"- **Deployment:** {r['deployment']}",
                f"- **Last production execution:** {r['last_production_execution']}",
                f"- **Evidence quality:** {r['evidence_quality']}",
                f"- **Ledger:** {r['ledger_state']}",
                f"- **Missing work:** {'; '.join(r['missing_work'])}",
                f"- **Exact acceptance blocker:** {r['acceptance_blocker']}",
                f"- **Stages:** `{''.join(_mark(r['steps'][k]['ok']) for k in STEPS)}`",
                ""]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    data = build()
    (HERE / "TRACEABILITY.md").write_text(render_md(data))
    (HERE / "TRACEABILITY.json").write_text(json.dumps(data, indent=1) + "\n")
    json.dump(data["summary"], sys.stdout, indent=1)
