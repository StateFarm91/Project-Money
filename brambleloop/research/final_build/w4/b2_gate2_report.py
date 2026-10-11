"""Write the per-row table of research/final_build/w4/B2_GATE2_REPORT.md from the ledger.

Usage: python research/final_build/w4/b2_gate2_report.py   (after build2_ledger.py)
Reads BUILD2_LEDGER.json (regenerated from production readings of 2026-10-11) and joins each
gated row to the per-gate audit below: what evidence is missing, what produces it and whether
that producer runs in production (read-only GETs in evidence_B2GATE2), the exact action that
opens the gate, and whether that action is genuinely the owner's / an outsider's or the
company's. Writes the table between the TABLE markers of B2_GATE2_REPORT.md.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

OWNER, EXTERNAL, DATA, COMPANY = ("owner", "external", "data (buyers/time)",
                                  "company-executable")
NOT_DEPLOYED = "built on claude/w4-B2GATES (cbf3153), NOT in production 0417f35"

# gate -> (missing evidence, producer, in production?, exact opening action, who)
GATES: dict[str, tuple[str, str, str, str, str]] = {
    "customers": (
        "a LedgerEntry with gross_cad > 0 and an order evidence_ref",
        "commerce.orders_ingest -> LedgerEntry",
        "deployed; never ran: /api/verify ledger_entries 0, revenue_cad 0.0 (ingest gate "
        "closed: transactions_r not granted, etsy.probe refused)",
        "a live listing (live_listings) + transactions_r + a working Etsy credential, then a "
        "buyer pays", DATA),
    "image_vision": (
        "a vision.probe with ok:true",
        "ops.capability_probes -> gateway.anthropic.vision_probe",
        "runs: latest 2026-10-11T14:05Z ok:false 'credit balance is too low'",
        "owner adds Anthropic credit (fund_model, max CA$25, 5 min)", OWNER),
    "live_listings": (
        "a Listing with an etsy_listing_id",
        "store.publish (runtime.pipeline) under a per-listing grant",
        "runs: 185 refusals in shadow, listings_with_etsy_id 0 (/api/verify)",
        "owner: leave_shadow + per-listing publication grant (+ payout/KYC, listing fees); "
        "the Etsy credential must also read again (etsy.probe 403 since 2026-10-07)", OWNER),
    "owned_surfaces": (
        "an owned_surface.probe row with ok:true",
        "ops.capability_probes -> growth.owned_surface.probe",
        f"{NOT_DEPLOYED}; production has 0 owned_surface.probe rows",
        "deploy the B2GATES door; owner opens a site serving "
        "/.well-known/brambleloop-surface.txt or sets PINTEREST_ACCESS_TOKEN", OWNER),
    "insights_access": (
        "one InsightsSnapshot",
        "POST /api/insights/snapshot -> intel.insights.record",
        "deployed; GET /api/insights: 0 snapshots",
        "owner reads Shop Manager > Marketing > Marketplace Insights and posts it (10 min, "
        "CA$0)", OWNER),
    "benchmark_purchases": (
        "one BenchmarkProduct",
        "POST /api/teardown/intake -> teardown.library.register",
        "deployed; gate closed in /api/build",
        "owner buys the 13 approved MJs patterns (max CA$300) and uploads them at "
        "/ops/teardown", OWNER),
    "model_bearing_render": (
        "an assets.model_photography record passing all six floors",
        "daily assets.model_photography handler",
        "runs; no passing record (provider ceiling: 0/16 gpt-image-1.5, 0/7 gemini)",
        "none available: an image provider that renders a certified crochet structure; "
        "no further paid draws are authorised", EXTERNAL),
    "acceptance_ruling": (
        "a done OwnerAction decision.api_vision_equivalence",
        "Command Center action acceptance.rule (step-up)",
        f"{NOT_DEPLOYED}; production shows the card with no door to answer it",
        "deploy the B2GATES door; owner rules yes/no (2 min, CA$0)", OWNER),
    "tester_roster": (
        "a CreatorProfile with delivered > 0 or a recorded permission",
        "POST /api/tester/agreement -> tester_programme.record_agreement",
        f"{NOT_DEPLOYED}",
        "deploy the door; owner confirms tester_outreach (max CA$185); a tester agrees",
        OWNER),
    "transactions_r": (
        "the Etsy grant lists transactions_r AND the latest etsy.probe ok",
        "Etsy OAuth (/api/etsy/oauth/start) + etsy.probe",
        "runs: etsy.probe ok until 2026-10-07T06:00Z, HTTP 403 every probe since 12:00Z",
        "owner: fix the Etsy credential (app active in the developer console; Railway "
        "ETSY_SHARED_SECRET = current shared secret), then re-authorise with transactions_r "
        "(card now says both)", OWNER),
    "rendered_pages": (
        "a current, audited, named-person page reading of each of the 5 etsy.com/legal sources",
        "POST /api/policy/snapshot -> platform_policy.record_page_reading; company half "
        "gates.policy_access (robots + Help Center change signals, NEW here)",
        "intake deployed, 0 readings (/api/policy never_checked all); policy_access not "
        "deployed",
        "owner accepts the PROPOSAL policy_page_reading and records the 5 readings (15 min "
        "per 30 days, CA$0) -- or declines and the rows stay parked", OWNER),
    "ad_authority": (
        "SpendLimit('ads') with a positive, unpaused daily cap",
        "Command Center action ads.set_limit (step-up, <= CONSERVATIVE_CAPS)",
        f"{NOT_DEPLOYED}; not askable until a listing is ready to sell",
        "after live_listings and transactions_r: owner sets <= CA$3/day, CA$25 lifetime",
        OWNER),
    "offsite_storage": (
        "an offsite archive that made the full round trip",
        "ops.offsite_archive cadence -> core.offsite.archive",
        "deployed; gate closed in /api/build",
        "owner creates a Backblaze B2 private bucket + restricted key and sets the five "
        "BRAMBLELOOP_ARCHIVE_* variables (15 min, max CA$1/month)", OWNER),
    "physical_proof": (
        "a PhysicalTest with completed_at",
        "POST /api/physical-test -> physical.record",
        "deployed; gate closed in /api/build",
        "owner confirms tester_outreach; an independent tester makes the sample", OWNER),
    "production_window": (
        "autonomy.launch_item PROVEN: a 24 h window passing all five conditions",
        "computed from production rows (/api/build off_device_proof)",
        "runs: 4/5 met (722 jobs, 109 types, 25 h spread, scheduler 25 h); unmet "
        "no_unexpected_dead_letters = 12 (ops.sentinel varchar(200) key overflow, "
        "listing.taxonomy_refresh Etsy 403, mjs.scan 403 before the PRODDIAG deploy)",
        "company: fixes exist on claude/w4-FMGATE (843af70 key fits, 4b55f22 taxonomy 403 "
        "reported); the integrator merges, the owner authorises the deploy, then 24 clean "
        "hours", COMPANY + " (then owner deploy)"),
    "listing_traffic": (
        "a ListingOutcome with visits > 0", "listing.outcomes / Stats intake",
        "deployed; /api/creative-learning style UNMEASURED, 0 listings live",
        "a live listing seen by buyers (after live_listings)", DATA),
    "style_outcomes": (
        "one hero style on >= 3 listings with >= 200 impressions",
        "creative.style_learning", "deployed; by_style {} (/api/creative-learning)",
        "three live listings of one style reach 200 impressions", DATA),
    "concept_outcomes": (
        ">= 200 visits and >= 20 countable orders", "creative.outcome_learning",
        "deployed; concepts_with_outcomes 0, ledger_entries 0",
        "live listings + 20 orders", DATA),
    "market_outcomes": (
        "listing traffic AND a countable order", "creative/blinded.py scorecard",
        "deployed; no traffic, no orders", "a live listing with traffic and one sale", DATA),
    "learning_sources": (
        "LearningObservation in both 'techniques' and 'customer_pain'",
        "intel.learning (ingest_complaints from mjs.reviews; no technique feed)",
        "production: customer_pain 1 (half met); techniques 0",
        "a sanctioned craft-technique source with a revival to report (Wikimedia technique "
        "pageviews sampled 2026-10-11: none rising)", DATA),
    "lead_lag_series": (
        "lead_lag measurable for one signal (an identifiable peak in both series)",
        "culture.sweep (reference) + culture.demand (etsy) -> radar.lead_lag",
        "production served 4 'measurable' lead-lags, all plateau artefacts; fixed here "
        "(radar refuses plateaus) -> closed",
        "marketplace listings discovered over time (needs the Etsy credential reading again) "
        "and a topic whose two series both peak", DATA),
    "seasonal_orders": (
        "a countable order attributed to a seasonal event", "seasonal.leadtime war room",
        "deployed; ledger_entries 0", "a seasonal sale", DATA),
    "season_harvest": (
        "a measured SeasonHarvest (>= 20 orders in a passed occurrence)",
        "seasonal.harvest", "deployed; every event UNMEASURED (/api/season-harvest)",
        ">= 20 orders in one passed season", DATA),
}

CHANGED = {35: "proposal + policy_access (G2)", 39: "proposal + policy_access (G2)",
           11: "card names Etsy credential", 12: "card names Etsy credential",
           140: "false 'open' prevented (plateau)", 98: "half met in production",
           195: "blocker is company-side now"}


def main() -> None:
    led = json.loads((HERE / "BUILD2_LEDGER.json").read_text(encoding="utf-8"))
    rows = [r for r in led["rows"] if "gate" in r]
    lines = ["| # | Title | State | Gate (prod reading) | Missing evidence | Producer / in production "
             "| Exact opening action | Who | Note |", "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["id"]):
        g = r["gate"]
        missing, producer, prod, action, who = GATES[g["key"]]
        lines.append(
            f"| {r['id']} | {r['title'][:46].replace('|', '/')} | {r['state']} | "
            f"{g['key']} ({g['state']}) | {missing} | {producer} -- {prod} | {action} | "
            f"{who} | {CHANGED.get(r['id'], '')} |")
    table = "\n".join(lines)
    path = HERE / "B2_GATE2_REPORT.md"
    text = path.read_text(encoding="utf-8")
    start, end = "<!-- TABLE START -->", "<!-- TABLE END -->"
    head, rest = text.split(start, 1)
    _old, tail = rest.split(end, 1)
    path.write_text(f"{head}{start}\n{table}\n{end}{tail}", encoding="utf-8")
    missing_gates = sorted({r["gate"]["key"] for r in rows} - set(GATES))
    assert not missing_gates, missing_gates
    print(json.dumps({"rows": len(rows), "counts": led["counts"]}))


if __name__ == "__main__":
    main()
