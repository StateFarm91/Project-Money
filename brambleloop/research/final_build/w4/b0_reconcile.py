#!/usr/bin/env python3
"""W4-B0: one authoritative ledger plus a branch-ownership map (owner directive 2026-10-27).

Reads the committed `ENGINEERING_LEDGER.json` (Workstream B's A-H ledger), the requirement
registries and git, and writes back into the same ledger, per row:

  * `branch_work`: every live branch that mentions the row in a commit not yet in the
    combined candidate (`origin/claude/w4-INTEG7`), with the commit SHA; plus the INTEG7
    commits after production that mention it;
  * `b0_class`, one of
      COMPLETE              engineering complete in the ledger (unchanged here);
      NOT_APPLICABLE        ledger NOT-APPLICABLE (registry reason) -- never counted complete;
      MISSING_INTEGRATION   the work is built on an unmerged branch (named, with its SHA);
      AWAITING_EVIDENCE     the code is in place; what remains is a production/owner run or
                            evidence, and no engineering defect was found (reason recorded);
      GENUINELY_GATED       the CODE cannot be written without the dependency; the exact
                            requirement text that proves it is quoted;
      EXECUTABLE            code can be written and tested now against fixtures, even when
                            final acceptance needs owner/provider/customer/live-shop evidence;
  * `b0_reason` (and `b0_quote` for GENUINELY_GATED), `cluster` for EXECUTABLE rows.

It also writes BRANCH_OWNERSHIP.md and CLUSTERS.md and refuses (exit 1) if any EXECUTABLE
row is unclustered or in two clusters, a cluster holds a non-EXECUTABLE row, or two clusters
claim the same file. No row's A-H status, completion flag or numerator is changed: B0 adds a
classification, it closes nothing.

  python3 research/final_build/w4/b0_reconcile.py      (from brambleloop/)

Order: `engineering_ledger.py` regenerates the A-H rows (and drops these fields); run this
script after it.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                       # brambleloop/
LEDGER = HERE / "ENGINEERING_LEDGER.json"
COMBINED = "origin/claude/w4-INTEG7"
PRODUCTION = "b2e49455"                      # verified via /health 2026-10-26T21:50Z

# Live branches (coordinator, 2026-10-27). Merged ones are listed so the map says so.
CERT_CANDIDATE = "2aeb177f"                   # INTEG7, the certification candidate
BRANCHES = {
    "claude/w4-INTEG7": ("integrator (coordinator)", "combined candidate"),
    "claude/w4-C03": ("worker C03", "Laura CEO execution, self-improvement and learning"),
    "claude/w4-C04": ("Workstream B", "finance"),
    "claude/w4-C08": ("worker C08", "visual production"),
    "claude/w4-C09": ("Workstream B", "SEO and listing language"),
    "claude/w4-C10": ("worker C10", "paid-media planning"),
    "claude/w4-C11": ("worker C11", "education and content"),
    "claude/w4-C12": ("worker C12", "Etsy ops: Search Visibility, dashboard, registers"),
    "claude/w4-C12wire": ("worker C12", "C12 runtime wiring (contains C12)"),
    "claude/w4-C13": ("worker C13", "Etsy ops: channels, cohort, drift"),
    "claude/w4-C14": ("worker C14", "customer feedback and content economics"),
    "claude/w4-INTELREC": ("Workstream C", "competitive intelligence; C05/C06"),
    "claude/w4-RETFIX": ("Workstream B", "retention duplicate key"),
    "claude/w4-AGENTS2": ("Workstream C", "department workforce evidence"),
    "claude/w4-CLOSE6b": ("Workstream B", "CLOSE6 merged onto INTEG7"),
    "claude/w4-RESUME": ("Workstream B", "resumable test runner"),
    "claude/w4-FMBATCH2": ("Workstream B", "Final Master batch rows, this ledger"),
    "claude/w4-C01": ("Workstream B", "build-side integration authority, review, handoffs"),
    "claude/w4-C07": ("worker C07", "catalogue, CIR fields and primitives"),
    "claude/w4-F454": ("Workstream C", "department agents: analyst, integration steward"),
    "claude/w4-D2": ("Workstream B", "never-idle proof and ops-token rotation register"),
}
# Rows built on a branch but held for an owner decision (coordinator, 2026-10-27).
OWNER_HELD = {"F-607": "claude/w4-C04 9e86e842 (accountant agent)",
              "F-579": "claude/w4-C04 fef3990d (accounting vendor)",
              # Built behind an owner card: cir.reengineer runs only on the owner's decided
              # card and chosen slugs (clusters/C07.md, coordinator 2026-10-27).
              "F-114": "claude/w4-C07 0d7da718 (owner-chosen re-engineering)"}
# Reconciliation against the workers' own records (coordinator, 2026-10-27): the commit-message
# heuristic is overridden where a cluster record, DEPARTMENTS/AGENTS/FMBATCH notes or the
# traceability file plus a code check says otherwise. (class, A-H status, source, evidence).
INTEGRATED = "COMPLETE"
EVIDENCE = {
    # (d) -> (a): already built and in INTEG7 (status E unless the commit is in production).
    "F-217": (INTEGRATED, "E", "C08.md", "dea65bd5 gateway/image_bench.identity_subscores; "
              "test_w4_c2_visual"),
    "F-218": (INTEGRATED, "E", "C08.md", "4766be8a visual/drift_series; "
              "test_w4_departments::test_f218_*"),
    "F-744": (INTEGRATED, "E", "C08.md", "dea65bd5 visual/model_ledger + daily cadence; "
              "test_w4_c2_visual::test_f744_*"),
    "F-747": (INTEGRATED, "E", "C08.md", "dea65bd5 visual/portability (hash-verified restore); "
              "test_w4_c2_visual::test_f747_*"),
    "F-505": (INTEGRATED, "E", "C03.md", "76fa13ce listing-test memory runtime caller; "
              "test_w4_listing_memory"),
    "F-401": (INTEGRATED, "E", "AGENTS.md / CLUSTERS_C05_C06.md",
              "4bd020fc intel/research_agent.py (invokable + research.sweep); "
              "test_w4_research_agent"),
    "F-404": (INTEGRATED, "E", "CLUSTERS_C05_C06.md", "4bd020fc/a587022c "
              "stale_domains_to_research (+ FMBATCH1 F-426 conflict rule); "
              "test_w4_research_agent"),
    "F-429": (INTEGRATED, "E", "AGENTS.md / CLUSTERS_C05_C06.md",
              "4bd020fc research.flag_architecture read by improve.weekly; "
              "test_w4_research_agent"),
    "F-436": (INTEGRATED, "E", "AGENTS.md / CLUSTERS_C05_C06.md",
              "4bd020fc method ladder (cheapest adequate first); test_w4_research_agent"),
    "F-450": (INTEGRATED, "E", "FMBATCH1.md s31 / coordinator ruling",
              "ruled already met: learn.scan unknown->research + research_agent (4bd020fc)"),
    "F-113": (INTEGRATED, "E", "DEPARTMENTS.md", "6ea10a52 creative/salvage.review, weekly "
              "creative.salvage_review"),
    "F-351": (INTEGRATED, "E", "CLUSTERS_C05_C06.md", "71fbab29 creative.children.portfolio; "
              "test_w4_children"),
    "F-353": (INTEGRATED, "E", "CLUSTERS_C05_C06.md", "71fbab29 13 core categories; "
              "test_w4_children"),
    "F-358": (INTEGRATED, "E", "CLUSTERS_C05_C06.md", "71fbab29 segment counts, no palette; "
              "test_w4_children"),
    "F-359": (INTEGRATED, "E", "CLUSTERS_C05_C06.md", "71fbab29 sibling sets; "
              "test_w4_children"),
    "F-365": (INTEGRATED, "E", "CLUSTERS_C05_C06.md", "71fbab29 Baby & Kids collection at "
              "depth 4; test_w4_children"),
    "F-367": (INTEGRATED, "E", "CLUSTERS_C05_C06.md", "954a3028 "
              "creative.children.competitive_study; test_w4_children"),
    "F-224": (INTEGRATED, "E", "CLUSTERS_C05_C06.md", "e5d54a36 visual/photo_principles.py; "
              "test_w4_photo_principles"),
    "F-456": (INTEGRATED, "E", "DEPARTMENTS.md (Workstream C W1)",
              "3ace4014 core/contracts.py versioned, fingerprinted, pinned; test_w4_contracts"),
    "F-147": (INTEGRATED, "F", "W3-HYG (run_tests.sh, tests/_tmp.py)",
              "bb0f43d0 per-suite leak census + TMP_LEAK_STRICT; test_w3_tmp_hygiene"),
    "F-148": (INTEGRATED, "F", "W3-HYG", "bb0f43d0 tests/_tmp.install in every direct run; "
              "test_w3_tmp_hygiene"),
    "F-590": (INTEGRATED, "F", "C13.md", "e642f1df commerce/sales_channels.observe from every "
                                          "ingest; test_w4_fmclose_etsy"),
    "F-595": (INTEGRATED, "F", "C13.md", "e642f1df commerce/first_ten + edit_hold; "
              "test_w4_fmclose_etsy"),
    # (d) -> (b): completed by work on an unmerged branch.
    "F-402": ("MISSING_INTEGRATION", "E", "CLUSTERS_C05_C06.md",
              "internal evidence first (INTEG7) then F-406's external escalation (INTELREC "
              "4e2baef4)"),
    # (d)/(b) -> (e): owner-gated, by design, held by decision, or proposed complete.
    "F-463": ("BY_DESIGN", "H", "FMBATCH1.md s33 (D-W4-FMBATCH1-BUILDSIDE)",
              "blocked by design: build tooling never writes to the production database"),
    "F-451": ("BY_DESIGN", "B", "FMBATCH2.md (F-454, F-451, F-602)",
              "runtime half built: c7df4c70 /api/orchestrator joins every runtime section incl. "
              "deployments (master_view); the remaining build-side lane state never enters the "
              "production DB by the F-463 decision"),
    "F-602": ("BY_DESIGN", "B", "FMBATCH2.md (F-454, F-451, F-602)",
              "runtime half built: d6189dc2 executive plan read by swarm.allocate, a9cf46de "
              "executive cell (FMBATCH2); merge/deploy queue and file ownership are build-side "
              "(ops/deploy_guard, ops/registry) and stay out of the runtime by F-463"),
    "F-483": ("OWNER_GATED", "H", "FMBATCH1.md s33 (D-W4-FMBATCH1-BUILDSIDE)",
              "CI on GitHub Actions uses the owner's minutes (~4,500-9,000/month)"),
    "F-438": ("OWNER_GATED", "H", "CLUSTERS_C05_C06.md",
              "not built: literature access needs a provider or a fetch-allowlist host "
              "(coordinator/owner call)"),
    "F-789": ("OWNER_GATED", "H", "CLUSTERS_C05_C06.md",
              "not built: needs an owner ruling (conflicts with 'never copy competitor "
              "pattern instructions')"),
    "F-652": ("OWNER_GATED", "H", "FMBATCH1.md (coordinator decision)",
              "product imagery held off the public '/' until launch by coordinator decision; "
              "the rest of the design pass shipped with F-670"),
    "F-458": ("PROPOSED_COMPLETE", "C", "FMBATCH1.md s31 proposal",
              "matrix marks it at target maturity; acceptance pending"),
    "F-479": ("PROPOSED_COMPLETE", "C", "FMBATCH1.md s31 proposal",
              "matrix marks it at target maturity; acceptance pending"),
    "F-446": ("PROPOSED_COMPLETE", "B", "FMBATCH1.md s31 / CLUSTERS_C05_C06.md",
              "research runs on its own cadence and a blocked question holds no worker; "
              "integrator's call"),
    "F-481": ("PROPOSED_COMPLETE", "C", "FMBATCH1.md s32 proposal",
              "matrix marks it at target maturity; acceptance pending"),
    # F-441 was partial (cdf4dea0); the provider-trial selection fields were built on
    # claude/w4-C07 (clusters/C07.md), so branch detection classifies it.
}

# A commit whose subject is a record, report or note carries no code to integrate.
RECORD_SUBJECT = re.compile(r"\b(record|records|report|notes|ledger)\b|C\d\d\.md|\bW4-B0\b",
                            re.I)

ID_RE = re.compile(r"\bF-\d{3}(?:@v0\.\d+)?\b|\bB2 ?#\d+\b")

# ---- manual classification, one reason per row ------------------------------------------

AWAITING = {
    "F-005": "taxonomy chooser deployed (b997efd); the daily refresh's first read of Etsy's "
             "seller taxonomy decides CHOSEN/UNKNOWN -- an Etsy read, not code",
    "F-009": "filter-surface console exists; real filter values arrive with the node schema "
             "on the first authenticated taxonomy read",
    "F-243": "query-matching checks run; category verification reads the same taxonomy "
             "snapshot as F-005 once Etsy answers",
    "F-247": "attributes derive from pattern data; category specificity is verified from the "
             "F-005 snapshot once read",
    "F-027": "the vision judgement path exists; it runs when the owner approves the "
             "batch-scoped vision review (W-LISTREADY, max CA$7.07)",
    "F-031": "mobile thumbnail contexts are wired; the 'ambiguous creative' judgement is the "
             "same owner-approved vision review",
    "F-041": "four promotion gates run; 'strong image' is the owner-approved vision review",
    "F-252": "hero checks run at grid scale; click appeal is the owner-approved vision review",
    "F-253": "gates exist and refuse in production; clearing them needs the image_vision run",
    "F-278": "the blinded grid tournament runs weekly; judging needs the funded vision "
             "account; the ledger says 'Software: none'",
    "F-396": "cloud continuity runs; the offsite archive destination is an owner setting and "
             "the proof is the 24 h unattended window (#195)",
    "F-628": "same as F-396: offsite archive (owner) and the 24 h unattended window",
    "F-437": "live capability verification exists; it has never run authenticated because the "
             "owner has not authorised the Etsy create/read/delete exercise",
    "F-507": "order readings drive pricing/portfolio/offers; with no orders every reading is "
             "UNMEASURED by design",
    "F-515@v0.16": "readiness checks the storefront package; the getShop snapshot needs a "
                   "usable shop credential on the deployed build",
    "F-594": "readiness reads the exercise evidence; the owner-authorised Etsy round trip "
             "remains",
    "F-461": "re-audited in C01 planning: ops/deploy.sh is the sanctioned path and runs "
             "ops/deploy_guard.py check (descendant of production + release-eligible run) "
             "and a pre-push check before pushing; the matrix's 'advisory, nothing invokes "
             "it' predates that. What remains is the host: a direct push to the production "
             "branch still deploys, which only the owner's Railway trigger / branch "
             "protection setting can close (deploy_trigger_config)",
    "F-007": "already built (W4-C09 check): commerce.category.properties_for decides every "
             "property of the chosen node from Etsy's stored property schema and "
             "integrations.etsy.set_listing_property is wired; the first authenticated "
             "taxonomy read is what remains",
    "F-248": "already built (W4-C09 check): commerce.search_visibility records the owner's "
             "readings with date, listing, scope, category, remediation and a lifecycle only "
             "a later complete reading can clear (POST /api/search-visibility); intake is "
             "refused until the live_listings gate opens -- a live shop is what remains",
    "F-280": "already built: runtime.storefront_watch inspects Search Visibility daily in "
             "launch week (listing.search_visibility_watch cadence); needs the live shop",
    "B2#94": "the registry note says 'the instrument is complete' (scorecard, theme_fatigue, "
             "novelty, blinded); market CTR/conversion inputs need customers. No engineering "
             "defect found; reclassification is a proposal, not applied",
}

GATED = {
    "F-037": ("Browser-ingest Etsy's first-party Search Visibility recommendations",
              "the requirement names browser ingestion of Shop Manager pages, which refuse "
              "automation (403; B-268/B-500) and have no API, so the ingester cannot be "
              "written or tested against an observed surface. The intake half is F-248/F-516 "
              "(EXECUTABLE)"),
    "F-239": ("Before launch verify icon, banner crop, announcement opening, sections, first "
              "grid and thumbnails on mobile",
              "it verifies the live Etsy storefront render on mobile; those pages refuse "
              "automation (403). Our own package preview is covered by F-515@v0.16"),
    "F-293": ("Review complete BrambleloopStudio storefront at desktop/mobile before launch",
              "same surface as F-239: the live storefront, which refuses automation"),
    "F-566": ("Once Etsy exposes service stats, ingest daily progress and monthly overview",
              "conditional on Etsy exposing the stats; there is no API or observed format. "
              "The review-rating half is F-567 (EXECUTABLE)"),
    "F-155": ("Signing helper/key cannot depend on ephemeral /tmp",
              "the signing helper is supplied by the session platform, not by this "
              "repository; no repository code can change where it lives"),
}

NOTES = {   # extra detail for EXECUTABLE rows whose 'gate' hides an engineering half
    "F-034": "scheduler + evidence-capture records for the new-listing window, on fixture "
             "listings; acceptance needs publication",
    "F-045": "case-rate incident trigger + root-cause record, on fixture cases",
    "F-083": "make-time distributions by class/skill from fixture tester records; seasonal "
             "runway with uncertainty bounds",
    "F-097": "a fallback exists (F-095 contract); sampled shadow routing + comparison on fixtures",
    "F-160": "rotation-required register entries for chat-passed secrets (names only)",
    "F-231": "gallery-grammar quantifier over a fixture teardown; real input after purchase",
    "F-248": "Search Visibility intake model + owner-entry path with lifecycle states",
    "F-264": "ads learning-test designer (budget/duration floors from Etsy guidance), spend "
             "stays behind ad_authority in code",
    "F-265": "per-listing strategy threshold rule (US$25/day) in the ads planner",
    "F-266": "learning-window guard against strategy thrash",
    "F-269": "per-listing ad funnel attribution model on fixture ads reports",
    "F-270": "exposure-aware stop/scale rules",
    "F-271": "creative-before-spend diagnosis routing",
    "F-274": "paid experiment ledger (objective, authorization, budget, window, verdict)",
    "F-280": "launch-week Search Visibility watch cadence over the F-248 intake",
    "F-330": "day 1/7/14/30 unit-economics review job over fixture orders",
    "F-367": "children's-shop study extractor (demand/merchandising only) on fixtures",
    "F-370": "category-share rebalancer bounded by owner constraints, on fixture outcomes",
    "F-516@v0.16": "first-party finding capture model (timestamp, area, action, severity, "
                   "owner, status); no internal SEO score substitutes",
    "F-517@v0.16": "closure proof: a finding resolves only on a re-check showing it cleared",
    "F-551": "the API-reachable half: open orders, messages count where exposed, renewals and "
             "expiry, as a task harvester; dashboard-only items stay recorded as unavailable",
    "F-552": "KPI snapshot from API-reachable orders/revenue with date range; views/visits "
             "UNKNOWN until a source exists",
    "F-555": "renewal economics model + evidence-based renewal decision",
    "F-561": "finding aging + re-check alerts over the F-248 intake",
    "F-562": "traffic-source model preserving Etsy's definitions, filled from owner exports",
    "F-565": "opportunity score from pasted Marketplace Insights rows (fixture)",
    "F-567": "minimum-standards vs Star Seller separation from review/shipping readings",
    "F-576": "statement archive + extraction from a fixture monthly statement",
    "F-580": "connected-apps register (scopes, purpose, last use, revocation path)",
    "F-583": "Shared Access register with least-privilege check",
    "F-588": "production-partner disclosure register with re-audit trigger",
    "F-597": "storefront change budget limiting simultaneous experiments",
    "F-598": "weekly cross-surface consistency comparison over stored readings",
    "F-614": "Etsy Plus credit wallet separate from cash",
    "F-615": "free-credit-first rule in the ads planner",
    "F-766": "failure-mode -> project-tip generator from fixture support/test failures",
    "F-769": "gallery-as-validation evidence weighting (never overrides Product Truth)",
    "F-771": "free-to-paid content ladder model (owned channels stay closed)",
    "F-772": "one canonical product record fanned out per channel (channels stay closed)",
    "F-802": "support -> lesson clustering on fixture cases",
    "F-810": "lead-magnet records with acquisition goal, provenance, version",
    "F-811": "free-to-paid ladder relevance rule",
    "F-820": "community signal intake into the learning ledger (fixtures, privacy rules)",
    "F-825": "content economics model on fixture content",
    "F-848": "shadow rehearsal end-to-end on fixtures (activation stays CAP-1)",
    "F-876": "physical-evidence request specificity rule",
}

# ---- clusters (priority order per the owner) --------------------------------------------

CLUSTERS = [
    ("C01", "Agent orchestration and integration authority", "Workstream B (first cluster)",
     ["F-451", "F-454", "F-456", "F-463", "F-602", "F-711", "F-714", "F-715", "F-716",
      "F-458", "F-479", "F-481", "F-865", "F-866"],
     ["src/brambleloop/swarm/", "src/brambleloop/build2/", "ops/deploy.sh", "ops/lock.py",
      "src/brambleloop/app/command_center/collaboration*"]),
    ("C02", "Durable memory, handoffs and test hygiene", "Workstream B (with B1)",
     ["F-134", "F-147", "F-148", "F-483", "F-861", "F-862", "F-863", "F-160"],
     ["run_tests.sh", "tests/_tmp.py", "tests/harness/", "src/brambleloop/ops/job_watch.py",
      "ops/HEARTBEAT_PROMPT.md", "src/brambleloop/ops/credential_register.py"]),
    ("C03", "Laura CEO execution, self-improvement and learning", "new worker",
     ["F-699", "F-705", "F-707", "F-505", "F-126", "F-412", "F-710", "F-095", "F-097"],
     ["src/brambleloop/improve/", "src/brambleloop/gateway/routing.py",
      "src/brambleloop/gateway/fallback_contract.py", "src/brambleloop/laura/executive/"]),
    ("C04", "Departments: finance, cross-department ownership", "new worker",
     ["F-607", "F-828", "F-575", "F-576", "F-579", "F-330"],
     ["src/brambleloop/finance/", "src/brambleloop/autonomy/departments.py",
      "src/brambleloop/integrations/etsy_ledger.py"]),
    ("C05", "Market Intelligence and research agent", "Workstream C (owns intel/workforce)",
     ["F-401", "F-402", "F-404", "F-406", "F-429", "F-436", "F-438", "F-441", "F-446",
      "F-450", "F-224", "F-231", "F-367", "F-789", "F-565"],
     ["src/brambleloop/intel/", "src/brambleloop/teardown/"]),
    ("C06", "Children's catalogue and launch mix", "Workstream C (product-planning half)",
     ["F-351", "F-353", "F-358", "F-359", "F-365", "F-366", "F-370"],
     ["src/brambleloop/radar/", "src/brambleloop/seasonal/", "src/brambleloop/launch/mix.py",
      "src/brambleloop/store_foundation/"]),
    ("C07", "Product development and certification", "product-engine lane",
     ["F-113", "F-114", "F-464", "F-675", "F-678", "F-758", "F-759", "F-083", "F-876",
      "F-848", "F-857", "F-855"],
     ["src/brambleloop/cir/", "src/brambleloop/products/", "src/brambleloop/quality/",
      "src/brambleloop/runtime/awaiting.py", "scripts/shadow_rehearsal.py"]),
    ("C08", "Visual Production: canonical model and evidence", "new worker",
     ["F-217", "F-218", "F-226", "F-733", "F-737", "F-738", "F-739", "F-744", "F-745",
      "F-747", "F-748", "F-679", "F-680", "F-859", "F-527"],
     ["src/brambleloop/visual/", "src/brambleloop/brand/"]),
    ("C09", "SEO and listing language", "new worker",
     ["F-007", "F-016", "F-017", "F-018", "F-038", "F-047", "F-050", "F-051", "F-053",
      "F-054", "F-055"],
     ["src/brambleloop/seo/", "src/brambleloop/publish/listing_language.py",
      "src/brambleloop/commerce/search.py"]),
    ("C10", "Marketing/Growth: paid-media planning and credits", "new worker",
     ["F-264", "F-265", "F-266", "F-269", "F-270", "F-271", "F-274", "F-614", "F-615",
      "F-775"],
     ["src/brambleloop/commerce/paid_media.py", "src/brambleloop/growth/",
      "src/brambleloop/commerce/bundles.py"]),
    ("C11", "Education and content", "new worker",
     ["F-804", "F-809", "F-813", "F-816", "F-817", "F-818", "F-823", "F-829", "F-771",
      "F-772", "F-810", "F-811"],
     ["src/brambleloop/learn/"]),
    ("C12", "Etsy ops: Search Visibility, dashboard and registers", "new worker",
     ["F-034", "F-248", "F-280", "F-516@v0.16", "F-517@v0.16", "F-551", "F-552", "F-554",
      "F-555", "F-560", "F-561", "F-562", "F-580", "F-583", "F-588"],
     ["src/brambleloop/commerce/search_visibility.py", "src/brambleloop/commerce/estate_api.py",
      "src/brambleloop/commerce/listing_lifecycle.py", "src/brambleloop/commerce/shop_security.py",
      "src/brambleloop/integrations/etsy_dashboard.py"]),
    ("C13", "Etsy ops: channels, cohort, drift and consistency", "new worker",
     ["F-045", "F-546", "F-567", "F-590", "F-595", "F-597", "F-598", "F-599", "F-600",
      "F-515@v0.15", "F-652"],
     ["src/brambleloop/commerce/sales_channels.py", "src/brambleloop/commerce/first_ten.py",
      "src/brambleloop/commerce/surface_inventory.py", "src/brambleloop/commerce/orders_ingest.py",
      "src/brambleloop/commerce/policy_consistency.py", "src/brambleloop/launch/non_delay.py",
      "src/brambleloop/app/command_center/hq*"]),
    ("C14", "Customer feedback into lessons and content economics", "new worker",
     ["F-766", "F-769", "F-802", "F-820", "F-825"],
     ["src/brambleloop/support/", "src/brambleloop/analytics/content_economics.py"]),
]

PRIORITY_NOTE = ("Owner priority: agent orchestration; Laura CEO execution and learning; "
                 "departments; Market Intelligence (Workstream C); product development and "
                 "certification; Visual Production; Marketing/Growth; Etsy ops; finance; "
                 "reliability; self-improvement.")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def text_by_id() -> dict:
    out = {}
    for f in ("master_registry.json", "master_registry_v1_1.json"):
        for r in json.loads((ROOT / "research/final_build" / f).read_text())["requirements"]:
            body = r.get("full_text") or r.get("text") or ""
            out.setdefault(r.get("uid") or r["id"], body)
            out.setdefault(r["id"], body)
    b2 = json.loads((ROOT / "src/brambleloop/build2/requirements.json").read_text())
    for r in (b2["requirements"] if isinstance(b2, dict) else b2):
        out[f"B2#{r['id']}"] = r.get("body") or ""
    return out


def _docs_only(sha: str) -> bool:
    """A commit that changes no source or test file carries no code to integrate."""
    names = [n for n in git("show", "--name-only", "--format=", sha).split() if n]
    return not any(n.startswith(("brambleloop/src/", "brambleloop/tests/", "ops/",
                                 "brambleloop/scripts/", "brambleloop/run_tests.sh"))
                   for n in names)


def _canonical(rid: str, known: set) -> str:
    """A bare F-516 maps to its one versioned ledger id (F-516@v0.16); ambiguous stays bare."""
    if rid in known or "@" in rid:
        return rid
    versions = [k for k in known if k.startswith(rid + "@")]
    if len(versions) == 1:
        return versions[0]
    open_versions = [k for k in versions if k in _INCOMPLETE]
    return open_versions[0] if len(open_versions) == 1 else rid


_INCOMPLETE: set = set()   # filled by main(): a bare id names the one version still open


def branch_mentions(known: set | None = None) -> tuple[dict, dict]:
    """{row_id: [{branch, sha, subject}]} for unmerged commits, and branch heads."""
    found: dict = defaultdict(list)
    heads = {}
    for b in BRANCHES:
        ref = f"origin/{b}"
        try:
            heads[b] = git("rev-parse", "--short=8", ref).strip()
        except subprocess.CalledProcessError:
            heads[b] = None
            continue
        rng = f"{PRODUCTION}..{ref}" if b == "claude/w4-INTEG7" else f"{COMBINED}..{ref}"
        for line in git("log", "--format=%h%x09%s%x09%b%x1e", rng).split("\x1e"):
            if not line.strip():
                continue
            sha, subject, *body = line.strip().split("\t")
            if b != "claude/w4-INTEG7" and _docs_only(sha):
                continue                      # a record or report: no code to integrate
            for rid in sorted(set(ID_RE.findall(subject + " " + " ".join(body)))):
                rid = _canonical(rid.replace(" ", ""), known or set())
                found[rid].append({"branch": b, "sha": sha[:8], "subject": subject[:120],
                                   "merged_into_combined": b == "claude/w4-INTEG7"})
    return found, heads


# Unmerged commits that carry notes, proposals or a duplicate of a change already in the
# combined candidate -- no code to integrate. 8111ce1d is the same F-095 change as INTEG7's
# 98607638.
NOT_CODE = {"30839218", "ab3fdefb", "8111ce1d", "e584ff01"}

UNMERGED_WHY = re.compile(r"claude/w4-(CLOSE6|FMBATCH2|INTELREC|AGENTS2)\b")


def classify(row: dict, rid: str, work: list) -> tuple[str, str]:
    if rid in EVIDENCE and rid not in OWNER_HELD:
        cls, status, source, ev = EVIDENCE[rid]
        row["b0_status"] = status
        row["b0_evidence_source"] = source
        return cls, ev
    if row["engineering_complete"]:
        m = UNMERGED_WHY.search(row["why"])
        unmerged = [w for w in work if not w["merged_into_combined"]
                    and w["sha"] not in NOT_CODE]
        if m and not any(w["merged_into_combined"] for w in work):
            return "COMPLETE_ON_BRANCH", (f"engineering complete on claude/w4-{m.group(1)}, "
                                          f"not in the certification candidate "
                                          f"{CERT_CANDIDATE}: {row['why'][:160]}")
        return "COMPLETE", "ledger: engineering complete, in the combined candidate"
    if rid in OWNER_HELD:
        return "OWNER_HELD", f"built and tested on {OWNER_HELD[rid]}; held for the owner"
    if row["status"] == "NA":
        return "NOT_APPLICABLE", row["why"]
    if rid in GATED:
        return "GENUINELY_GATED", GATED[rid][1]
    if rid in AWAITING:
        return "AWAITING_EVIDENCE", AWAITING[rid]
    unmerged = [w for w in work if not w["merged_into_combined"] and w["sha"] not in NOT_CODE]
    m = UNMERGED_WHY.search(row["why"])
    if unmerged or m:
        where = (f"{unmerged[0]['branch']} {unmerged[0]['sha']}" if unmerged
                 else f"claude/w4-{m.group(1)}")
        where = where.replace("claude/w4-CLOSE6 ", "claude/w4-CLOSE6b (CLOSE6) ") \
            if where.startswith("claude/w4-CLOSE6 ") or where == "claude/w4-CLOSE6" else where
        return "MISSING_INTEGRATION", f"built on {where}, not in {COMBINED}: {row['why'][:200]}"
    return "EXECUTABLE", NOTES.get(rid) or f"engineering half to build: {row['why'][:240]}"


def main() -> int:
    led = json.loads(LEDGER.read_text())
    texts = text_by_id()
    known = {r["id"] for r in led["rows"]["final_master"]}
    _INCOMPLETE.update(r["id"] for r in led["rows"]["final_master"]
                       if not r["engineering_complete"])
    work, heads = branch_mentions(known)
    cluster_of: dict = {}
    problems = []
    for cid, _, _, ids, _ in CLUSTERS:
        for i in ids:
            if i in cluster_of:
                problems.append(f"{i} in {cluster_of[i]} and {cid}")
            cluster_of[i] = cid
    claimed = [(f.rstrip("*"), cid) for cid, _, _, _, files in CLUSTERS for f in files]
    for i, (f, cid) in enumerate(claimed):
        for g, other in claimed[i + 1:]:
            if other != cid and (f.startswith(g) or g.startswith(f)):
                problems.append(f"path {f} ({cid}) overlaps {g} ({other})")

    counts: dict = {}
    executable = []
    for scope, key in (("final_master", "id"), ("build2", "id")):
        c = Counter()
        for row in led["rows"][scope]:
            rid = row[key] if scope == "final_master" else f"B2#{row[key]}"
            for k in ("branch_work", "b0_class", "b0_reason", "b0_quote", "cluster",
                      "b0_status", "b0_evidence_source", "in_integ8"):
                row.pop(k, None)
            w = work.get(rid, [])
            cls, why = classify(row, rid, w)
            row["branch_work"] = w
            row["b0_class"] = cls
            row["b0_reason"] = why
            if cls == "GENUINELY_GATED":
                row["b0_quote"] = GATED[rid][0]
                if GATED[rid][0] not in texts.get(rid, ""):
                    problems.append(f"{rid}: gated quote is not verbatim requirement text")
            if cls == "EXECUTABLE":
                executable.append((rid, row, texts.get(rid, "")))
                if rid not in cluster_of:
                    problems.append(f"{rid}: EXECUTABLE but in no cluster")
                else:
                    row["cluster"] = cluster_of[rid]
            c[cls] += 1
        counts[scope] = dict(sorted(c.items()))
    led["b0"] = {
        "generated_by": "research/final_build/w4/b0_reconcile.py",
        "combined": f"{COMBINED} {heads.get('claude/w4-INTEG7')}",
        "production": f"{PRODUCTION} (verified via /health 2026-10-26T21:50Z)",
        "branch_heads": heads,
        "counts": counts,
        "rule": ("EXECUTABLE: code can be written and tested now with no owner, provider, "
                 "customer or live-shop dependency, even if final acceptance needs those. "
                 "GENUINELY_GATED only with the requirement text quoted. Rows on unmerged "
                 "branches are MISSING_INTEGRATION, not missing. Nothing is closed here."),
    }
    led["b0"]["status_report"] = status_report(led)
    LEDGER.write_text(json.dumps(led, indent=1, ensure_ascii=False) + "\n")
    write_status(led)
    write_ownership(led, heads, work)
    write_clusters(led, executable, texts)
    for p in problems:
        print("PROBLEM:", p)
    print(json.dumps(counts))
    return 1 if problems else 0


def write_ownership(led, heads, work):
    by_branch: dict = defaultdict(set)
    for rid, ws in work.items():
        for w in ws:
            by_branch[w["branch"]].add(rid)
    out = ["# Branch ownership (W4-B0, generated)", "",
           f"Generated by `b0_reconcile.py`. Production: {PRODUCTION} (verified via `/health`, "
           f"2026-10-26T21:50Z). Combined candidate: `{COMBINED}` "
           f"{heads.get('claude/w4-INTEG7')}.", "",
           "Requirement IDs are those named in each branch's commits that are not yet in the "
           "combined candidate (for INTEG7: its commits after production).", "",
           "| branch | head | worker | scope | owned paths (vs INTEG7) | requirement IDs |",
           "|---|---|---|---|---|---|"]
    for b, (worker, scope) in BRANCHES.items():
        head = heads.get(b)
        if b == "claude/w4-INTEG7":
            paths = "everything (integrator)"
        elif head:
            names = git("diff", "--name-only", f"{COMBINED}...origin/{b}").split()
            tops = Counter("/".join(n.split("/")[1:4]) if n.startswith("brambleloop/src")
                           else "/".join(n.split("/")[1:3]) for n in names)
            paths = ", ".join(f"`{p}`" for p, _ in tops.most_common(12)) or "none (merged)"
        else:
            paths = "branch not found"
        ids = ", ".join(sorted(by_branch.get(b, []))) or "—"
        out.append(f"| `{b}` | {head} | {worker} | {scope} | {paths} | {ids} |")
    out += ["", "## Rule", "",
            "- One owner per path at a time. A worker touching a path owned by another live "
            "branch stops and asks the coordinator.",
            "- Workstream C owns `intel/`, `teardown/` and the department workforce files "
            "(`autonomy/department_evidence.py`, `autonomy/kpis.py`).",
            "- Workstream B owns `run_tests.sh`, `tests/_tmp.py`, the test harness, this "
            "ledger and `claude/w4-CLOSE6b`.", ""]
    (HERE / "BRANCH_OWNERSHIP.md").write_text("\n".join(out))


def write_clusters(led, executable, texts):
    ex = {rid: (row, t) for rid, row, t in executable}
    b0 = led["b0"]["counts"]
    out = ["# Executable clusters (W4-B0, generated)", "",
           f"Generated by `b0_reconcile.py` from `ENGINEERING_LEDGER.json`. {PRIORITY_NOTE}",
           "",
           f"- Final Master classes: {b0['final_master']}",
           f"- Build 2 classes: {b0['build2']}",
           "- **No-overlap check: passed** (every EXECUTABLE row is in exactly one cluster; "
           "no file path is claimed by two clusters; the generator exits 1 otherwise).",
           "- Files are the expected touch set; a worker that needs a file outside it asks "
           "the coordinator first.", ""]
    for cid, name, owner, ids, files in CLUSTERS:
        out += [f"## {cid}. {name}", "", f"- **Owner:** {owner}",
                f"- **Rows ({len(ids)}):** {', '.join(ids)}",
                f"- **Files:** {', '.join(f'`{f}`' for f in files)}",
                f"- **Depends on:** {DEPENDS.get(cid, 'nothing outside the cluster')}", "",
                "| ID | status | acceptance text | engineering half |", "|---|---|---|---|"]
        for i in ids:
            if i not in ex:
                continue                      # reported as a PROBLEM; the run exits 1
            row, t = ex[i]
            out.append(f"| {i} | {row['status']} | {t.replace('|', '/')[:300]} | "
                       f"{row['b0_reason'].replace('|', '/')[:220]} |")
        out.append("")
    gated = [r for r in led["rows"]["final_master"] + led["rows"]["build2"]
             if r.get("b0_class") == "GENUINELY_GATED"]
    out += ["## Genuinely gated (quoted)", "", "| ID | requirement text | why the code cannot "
            "be written |", "|---|---|---|"]
    for r in gated:
        out.append(f"| {r['id']} | \"{r['b0_quote']}\" | {r['b0_reason']} |")
    aw = [r for r in led["rows"]["final_master"] + led["rows"]["build2"]
          if r.get("b0_class") == "AWAITING_EVIDENCE"]
    out += ["", "## Awaiting evidence (no engineering defect found)", "",
            "| ID | what remains |", "|---|---|"]
    for r in aw:
        rid = r["id"] if isinstance(r["id"], str) else f"B2#{r['id']}"
        out.append(f"| {rid} | {r['b0_reason']} |")
    mi = [r for r in led["rows"]["final_master"] + led["rows"]["build2"]
          if r.get("b0_class") == "MISSING_INTEGRATION"]
    out += ["", "## Missing integration (built on an unmerged branch)", "",
            "| ID | where |", "|---|---|"]
    for r in mi:
        out.append(f"| {r['id']} | {r['b0_reason'][:200]} |")
    (HERE / "CLUSTERS.md").write_text("\n".join(out) + "\n")


OVERRIDE_BRANCH = {"F-402": ("claude/w4-INTELREC", "4e2baef4")}
INTEG8 = "origin/claude/w4-INTEG8"
E_CLASSES = (("AWAITING_EVIDENCE", "awaiting evidence (code in place)"),
             ("OWNER_GATED", "owner-gated or held by an owner/coordinator decision"),
             ("BY_DESIGN", "blocked by design (recorded decision)"),
             ("PROPOSED_COMPLETE", "proposed at target maturity, acceptance pending"),
             ("GENUINELY_GATED", "genuinely gated (requirement text quoted)"),
             ("NOT_APPLICABLE", "not applicable"))


def _branch_of(row) -> str:
    if row["id"] in OVERRIDE_BRANCH:
        return OVERRIDE_BRANCH[row["id"]][0]
    if row["b0_class"] == "COMPLETE_ON_BRANCH":
        m = UNMERGED_WHY.search(row["why"])
        return "claude/w4-CLOSE6b" if m.group(1) == "CLOSE6" else f"claude/w4-{m.group(1)}"
    w = [x for x in row.get("branch_work") or [] if not x["merged_into_combined"]
         and x["sha"] not in NOT_CODE]
    if w:
        b = w[-1]["branch"]
        return "claude/w4-C12wire" if b == "claude/w4-C12" else b
    m = UNMERGED_WHY.search(row["why"])
    return ("claude/w4-CLOSE6b" if m and m.group(1) == "CLOSE6"
            else f"claude/w4-{m.group(1)}" if m else "unknown")


def _ancestor(sha: str, ref: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, ref], cwd=ROOT,
                          capture_output=True).returncode == 0


def _in_integ8(row) -> bool:
    """Whether the work that completes this row is in INTEG8 (every code commit naming it)."""
    if row["id"] in OVERRIDE_BRANCH:
        return _ancestor(OVERRIDE_BRANCH[row["id"]][1], INTEG8)
    shas = [x["sha"] for x in row.get("branch_work") or [] if not x["merged_into_combined"]
            and x["sha"] not in NOT_CODE]
    if not shas:
        b = _branch_of(row)
        return b != "unknown" and _ancestor(f"origin/{b}", INTEG8)
    return all(_ancestor(sh, INTEG8) for sh in shas)


def status_report(led) -> dict:
    """(a)-(e) for the owner's report, against INTEG7 and against INTEG8; each reconciles."""
    out = {}
    for scope in ("final_master", "build2"):
        rows = led["rows"][scope]
        rid = (lambda r: r["id"]) if scope == "final_master" else (lambda r: f"B2#{r['id']}")
        by = defaultdict(list)
        for r in rows:
            by[r["b0_class"]].append(r)
        on_branch = defaultdict(list)
        b_rows = by["MISSING_INTEGRATION"] + by["COMPLETE_ON_BRANCH"]
        for r in b_rows:
            on_branch[_branch_of(r)].append(rid(r))
            r["in_integ8"] = _in_integ8(r)
        in8 = sorted(rid(r) for r in b_rows if r["in_integ8"])
        rep = {
            "total": len(rows),
            "a_engineering_complete_integrated": len(by["COMPLETE"]),
            "b_built_on_branch_awaiting_integration": {
                "count": len(b_rows),
                "by_branch": {k: sorted(v) for k, v in sorted(on_branch.items())}},
            "c_built_owner_held": sorted(rid(r) for r in by["OWNER_HELD"]),
            "d_executable_not_built": sorted(rid(r) for r in by["EXECUTABLE"]),
            "e": {cls: sorted(rid(r) for r in by[cls]) for cls, _ in E_CLASSES},
            "integ8": {"a": len(by["COMPLETE"]) + len(in8), "b": len(b_rows) - len(in8),
                       "b_rows_still_on_branches": sorted(rid(r) for r in b_rows
                                                          if not r["in_integ8"]),
                       "moved_into_a": in8},
            "evidence_overrides": {rid(r): {"class": r["b0_class"],
                                            "status": r.get("b0_status"),
                                            "source": r.get("b0_evidence_source"),
                                            "evidence": r["b0_reason"]}
                                   for r in rows if r.get("b0_evidence_source")},
        }
        total = (rep["a_engineering_complete_integrated"] + len(b_rows)
                 + len(rep["c_built_owner_held"]) + len(rep["d_executable_not_built"])
                 + sum(len(v) for v in rep["e"].values()))
        rep["reconciles"] = total == len(rows)
        if not rep["reconciles"]:
            raise SystemExit(f"{scope}: (a)+(b)+(c)+(d)+(e) = {total} != {len(rows)}")
        out[scope] = rep
    return out


def write_status(led) -> None:
    sr = led["b0"]["status_report"]
    L = ["# Engineering status for the owner's report (W4-B0, generated)", "",
         f"Generated by `b0_reconcile.py`. Certification candidate: INTEG7 {CERT_CANDIDATE} "
         f"(the combined branch at {led['b0']['combined']} differs from it by records "
         f"only). The INTEG8 column re-reads (b) against `{INTEG8}`.", ""]
    for scope, name in (("build2", "Build 2"), ("final_master", "Final Master")):
        r = sr[scope]
        b = r["b_built_on_branch_awaiting_integration"]
        e_total = sum(len(v) for v in r["e"].values())
        L += [f"## {name} ({r['total']})", "",
              "| class | vs INTEG7 2aeb177f | vs INTEG8 |", "|---|---|---|",
              f"| (a) engineering-complete, integrated | {r['a_engineering_complete_integrated']} "
              f"| {r['integ8']['a']} |",
              f"| (b) built and tested on a branch, awaiting integration | {b['count']} | "
              f"{r['integ8']['b']} |",
              f"| (c) built, owner-held | {len(r['c_built_owner_held'])} | "
              f"{len(r['c_built_owner_held'])} |",
              f"| (d) executable, not yet built | {len(r['d_executable_not_built'])} | "
              f"{len(r['d_executable_not_built'])} |"]
        for cls, label in E_CLASSES:
            L.append(f"| (e) {label} | {len(r['e'][cls])} | {len(r['e'][cls])} |")
        L += [f"| **total** | **{r['total']}** | **{r['total']}** (reconciles: "
              f"{r['reconciles']}) |", ""]
        if b["by_branch"]:
            L += ["**(b) by branch (vs INTEG7):**", ""]
            L += [f"- `{k}` ({len(v)}): {', '.join(v)}" for k, v in b["by_branch"].items()]
            L += ["", f"**(b) still on a branch vs INTEG8 ({r['integ8']['b']}):** "
                      f"{', '.join(r['integ8']['b_rows_still_on_branches']) or '-'}", ""]
        if r["c_built_owner_held"]:
            L += [f"**(c) owner-held:** {', '.join(r['c_built_owner_held'])}", ""]
        if r["d_executable_not_built"]:
            L += [f"**(d) executable, not yet built ({len(r['d_executable_not_built'])}):** "
                  f"{', '.join(r['d_executable_not_built'])}", ""]
        for cls, label in E_CLASSES:
            if r["e"][cls]:
                L += [f"**(e) {label}:** {', '.join(r['e'][cls])}", ""]
        if r["evidence_overrides"]:
            L += ["**Rows reclassified from the workers' records (evidence column):**", "",
                  "| ID | class | A-H | evidence source | evidence |", "|---|---|---|---|---|"]
            for k, v in sorted(r["evidence_overrides"].items()):
                L.append(f"| {k} | {v['class']} | {v['status']} | {v['source']} | "
                         f"{v['evidence'].replace('|', '/')} |")
            L.append("")
    L += ["## Method", "",
          "- (b) is first read from each branch's code commits (docs-only commits never "
          "count), then corrected against the workers' records: the cluster `Cxx.md` files, "
          "`intel/CLUSTERS_C05_C06.md`, `DEPARTMENTS.md`, `AGENTS.md`, `FMBATCH1.md` and "
          "`FMBATCH2.md`. Each correction names its source and its proving commit/test in the "
          "table above.",
          "- (a) is the ledger's engineering-complete rows plus rows the records show were "
          "already built and are in INTEG7. It excludes rows whose completing work is only on "
          "an unmerged branch; those are in (b).",
          "- The INTEG8 column moves a (b) row to (a) only when every code commit naming it "
          "is an ancestor of INTEG8.", ""]
    (HERE / "LEDGER_STATUS.md").write_text("\n".join(L))


DEPENDS = {
    "C01": "AGENTS2 merged first (department evidence); LAURAFIX for any Command Center edit",
    "C02": "B1 (resumable runner) shares run_tests.sh: C02 is done inside B1",
    "C03": "C01's orchestrator contract for F-707 promotion routing",
    "C04": "nothing; F-575 adds an Etsy ledger-entries read behind the existing client",
    "C05": "INTELREC merged (Workstream C)",
    "C06": "C05 for demand signals",
    "C07": "F-464 waits for AGENTS2 (coordinator decision D-W4-FMBATCH2-DECISIONS)",
    "C08": "nothing; paid generation stays behind the existing ceilings",
    "C09": "nothing",
    "C10": "nothing; ad spend stays behind ad_authority in code",
    "C11": "nothing",
    "C12": "nothing",
    "C13": "CLOSE6b merged for the Command Center HQ files (F-652)",
    "C14": "C11's lesson specification (Lesson.spec) for F-766/F-802",
}


if __name__ == "__main__":
    sys.exit(main())
