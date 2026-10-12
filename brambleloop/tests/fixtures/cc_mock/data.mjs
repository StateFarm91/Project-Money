// Fixture data for the Command Center mock API (lane C contract COMMAND_CENTER_API.md).
// TEST FIXTURE ONLY: never shipped in the static directory, never shown as company truth.
// Deliberately includes UNKNOWN money, estimated figures, an approval needing step-up and a
// card that is not executable, so the UI's honesty rules are exercised.

const now = () => new Date().toISOString();
const ago = (min) => new Date(Date.now() - min * 60000).toISOString();
const env = (status, items, extra = {}) => ({ status, as_of: status === "UNKNOWN" ? null : ago(4),
  basis: status === "UNKNOWN" ? "unknown" : "measured", items, sources: extra.sources || ["fixture:mock"], ...extra });
const money = (v, state, extra = {}) => ({ value_cad: v, state, basis: state.toLowerCase(),
  display: v === null ? "UNKNOWN" : `CA$${v.toFixed(2)}`, sources: ["fixture:ledger"], ...extra });

export function tab(name, sections, extra = {}) {
  return { tab: name, generated_at: now(), sections, ...extra };
}

function ownerOverview() {
  const blk = (key, title, status, headline, items, extra = {}) => ({ key, title, status, headline, items: items.slice(0, 5),
    evidence: extra.evidence || items, as_of: status === "UNKNOWN" ? null : ago(1), basis: status === "UNKNOWN" ? "unknown" : "measured",
    sources: ["fixture:overview"], href: extra.href || "#/company", ...extra });
  const causes = [
    ["Etsy API credentials that can actually serve a request", 21], ["a live Etsy shop", 9], ["paid advertising authority", 7],
    ["a physical test of a made sample", 6], ["a recruited pattern tester", 4], ["transactions_r scope", 3], ["bank feed", 2]]
    .map(([t, n], i) => ({ title: t, gate: `g${i}`, count: n, detail: `${n} requirement(s) wait on this`, status: "BLOCKED", source: `build2.executor.gate:g${i}` }));
  return { status: "OK", as_of: ago(1), basis: "measured", items: [], sources: ["overview"], provider: "command_center.overview",
    order: ["working", "blocked", "decisions", "accomplished", "ready", "money"],
    blocks: {
      working: blk("working", "What's working", "OK", "2 of 31 capabilities verified live; last self-check had failures", [
        { title: "a model provider that can actually serve a request", detail: "a recorded model.probe succeeded", verified_at: ago(1), verified_basis: "checked live when this page was read", status: "OK", source: "build2.executor.gate:model_provider" },
        { title: "Production self-check (/api/verify)", detail: "failing: no_unexpected_dead_letters_in_24h", verified_at: ago(20), verified_basis: "last recorded run", status: "DEGRADED", source: "audit_log:26852" }]),
      blocked: blk("blocked", "What's blocked", "BLOCKED", "6 closed gate(s) hold 52 requirement(s)", causes),
      decisions: blk("decisions", "Decisions for you", "OK", "4 decision(s) open", [], { href: "#/approvals", open: 4 }),
      accomplished: blk("accomplished", "What the company accomplished (24 h)", "OK", "9 useful outcome(s) across 2 kind(s) of work; 30 finished job(s) did no work", [
        { title: "listing.seo", count: 6, detail: "coverage refreshed for 6 listings", at: ago(40), agents: ["listing"], status: "OK", source: "jobs:12150" },
        { title: "laura.executive_tick", count: 3, detail: "2 priorities set, 1 mission delegated", at: ago(15), agents: ["laura"], status: "OK", source: "jobs:12161" }], { href: "#/timeline" }),
      ready: blk("ready", "Ready to sell", "BLOCKED", "0 of 1 product(s) ready to sell; 1 certified; 0 on Etsy", [
        { title: "Harbour Throw", slug: "harbour-throw", certified: true, version: "1", pdf: { state: "BUILT", built_at: ago(300), source: "artefact_provenance:4" },
          images: { state: "UNKNOWN", why: "no listing-set verdict or imagery provenance for this product" }, publication: "NOT READY",
          why: "Not ready: parity not passing", status: "BLOCKED", source: "products:1" }], { href: "#/store" }),
      money: blk("money", "Money and agent activity", "UNKNOWN", "Revenue UNMEASURED; spend 24 h CA$0.03 (recorded, 1 row(s)); 2 agent(s) produced useful results", [
        { title: "Revenue", value_cad: null, state: "UNMEASURED", display: "UNMEASURED", detail: "order source not connected", status: "UNKNOWN" },
        { title: "Profit", value_cad: null, state: "UNKNOWN", display: "UNKNOWN", status: "UNKNOWN" },
        { title: "Recorded spend (all time)", value_cad: 76.43, state: "RECORDED", display: "CA$76.43 (recorded; CA$2.45 not measured)", status: "OK" },
        { title: "Recorded spend (24 h)", value_cad: 0.03, state: "RECORDED", display: "CA$0.03 (recorded, 1 row(s))", status: "OK" }],
      { href: "#/money", agents: [{ title: "listing", useful_24h: 6, no_work_24h: 2, status: "OK" }, { title: "laura", useful_24h: 3, no_work_24h: 0, status: "OK" },
        { title: "orchestrator", useful_24h: 0, no_work_24h: 28, status: "DEGRADED" }], agents_counts: { active_24h: 2, ran_24h: 3 } }),
    } };
}

export const DATA = {
  // W4-ONDEMAND "Run checks now" (shape of ops.on_demand.status): one never run, one recent.
  checks: () => ({ checks: [
    { key: "model_probe", label: "Model provider probe", why: "Asks the model provider for a tiny answer.", external: true,
      requires_stepup: true, available_now: true, next_allowed_at: null,
      jobs: [{ cadence: "model_probe", job_type: "model.probe", scheduled_every_s: 21600, last: { status: "done", ok: true, at: ago(50), on_demand: false } }] },
    { key: "capabilities", label: "Capabilities", why: "Re-checks every capability gate.", external: false,
      requires_stepup: false, available_now: false, next_allowed_at: new Date(Date.now() + 5 * 60000).toISOString(),
      jobs: [{ cadence: "capabilities", job_type: "ops.capabilities", scheduled_every_s: 3600, last: null }] }],
    other_cadences: [{ cadence: "ops_health", job_type: "ops.health" }] }),
  home: () => tab("HOME", {
    // W4-OWNERHOME: the six-block owner overview (shape of command_center/overview.py).
    overview: ownerOverview(),
    changes_since_last_view: env("OK", [{ id: 17, at: ago(90), actor: "visual", action: "qa.passed", artifact: "harbour-throw@1", source: "audit_log:17" }],
      { since: ago(600), basis_note: "since your last view" }),
    autonomy: env("OK", [{ department: "Product & Design", status: "OK", last_run_at: ago(12) },
      { department: "Finance", status: "DEGRADED", detail: "Waiting on bank feed" }]),
    store: env("DEGRADED", [{ title: "Store foundation", detail: "Banner and About ready; policies draft", status: "DEGRADED" }]),
    products: env("OK", [{ title: "Harbour Throw", status: "READY", release: "r3" }], { certified: 1, on_etsy: 0 }),
    money: env("UNKNOWN", [], { reason: "the accountant provider (lane E) is not built" }),
    incidents: env("OK", [], { open_total: 0 }),
    owner_actions: env("BLOCKED", [{ title: "Connect Etsy API", detail: "Needed before any listing read-back", status: "PENDING", source: "owner_actions:12" }]),
    work_24h: env("OK", [{ job_type: "render", completed: 12 }], { completed: 41 }),
    launch: env("BLOCKED", [{ phase: "shadow", why: "env BRAMBLELOOP_PHASE=shadow" }], { reason: "SHADOW: nothing is published live" }),
    opportunities: env("OK", [{ title: "Granny-square cardigan demand rising", detail: "Search interest +18% w/w (estimated)", basis: "estimated" }]),
  }, { headline: {
    revenue: money(null, "UNMEASURED", { why: "order source not connected and read" }),
    profit: money(null, "UNKNOWN", { why: "the accountant provider owns profit" }),
    store: { products: 1, certified: 1, on_etsy: 0, status: "OK", reason: null },
    launch: { phase: "shadow", status: "BLOCKED" },
    autonomy: { status: "OK", reason: null, jobs_completed_24h: 41 },
    incidents_open: 0, owner_decisions: 2 }, last_seen_at: ago(600) }),
  morning: () => tab("MORNING_BRIEF", {
    what_changed: env("OK", [{ id: 17, action: "qa.passed", artifact: "harbour-throw@1", source: "audit_log:17" }]),
    completed: env("OK", [{ job_type: "seo.coverage", completed: 3 }, { job_type: "render", completed: 12 }]),
    money_spent: env("OK", [{ kind: "llm", amount_cad: 1.42, entries: 6 }], { total: money(1.42, "RECORDED") }),
    incidents: env("OK", []),
    discoveries: env("OK", [{ subject: "pricing", statement: "Competitor price band CA$7–12 for blankets", confidence: 0.6, source: "lessons:4" }]),
    overnight_autonomy: env("OK", [{ department: "SEO", detail: "coverage refreshed" }]),
    queued_actions: env("OK", [{ job_type: "render.lifestyle", pending: 2 }], { pending_total: 2 }),
    decisions_needed: env("BLOCKED", [{ card_id: "publication:harbour-throw@1", title: "Approve publication of Harbour Throw v1" }], { reason: "2 owner decisions open" }),
  }, { window_hours: 12, since: ago(720) }),
  approvals: () => ({ tab: "APPROVALS", generated_at: now(), sections: {},
    cards: [
      { card_id: "publication:harbour-throw@1", kind: "PUBLICATION", title: "Publish Harbour Throw v1 (shadow → staging)",
        proposed_action: "Grant a 24 h publication authority for Harbour Throw v1 release r3.",
        recommendation: "Approve: all deterministic gates pass.", uncertainty: "Photography CTR unmeasured; Etsy search placement unknown.",
        expected_benefit: "First listing ready for staging read-back.", downside: "A listing with an unseen defect would reach staging.",
        max_spend_cad: null, reversibility: "Revocable any time before execution.", deadline: new Date(Date.now() + 36 * 3600000).toISOString(),
        consequence_of_no_action: "Launch slips; nothing else is blocked.",
        evidence: [{ label: "Pattern certification", state: "PASS", why: "CIR validated, 0 errors", source: "pattern_versions:4" },
          { label: "Image QA", state: "PASS", why: "Hero and 6 gallery images pass", source: "jobs:311" },
          { label: "Search readiness", state: "UNKNOWN", why: "Etsy taxonomy read-back not connected", source: "seo:coverage" }],
        executable: true,
        actions: [{ action: "publication.preview", requires_step_up: false, params: { slug: "harbour-throw", version: "1", release: "r3" } },
          { action: "publication.approve", requires_step_up: true, params: { slug: "harbour-throw", version: "1", release: "r3", expected_digest: "sha256:abc123" } }],
        not_executable_reason: null, sources: ["owner_actions:12", "build2.executor.approval_inbox"] },
      { card_id: "gate:etsy_api", kind: "GATE", title: "Etsy API access: run `commerce.shop_package.policies()` then reauthorise_transactions_scope", proposed_action: "Connect the Etsy API (owner OAuth); steps in research/final_build/w4/owner_kit/ETSY_OAUTH_REAUTHORISE_TRANSACTIONS_SCOPE.md",
        recommendation: "Required before listing read-back.", uncertainty: null, expected_benefit: "Live read-back of store state.",
        downside: "None known.", max_spend_cad: 0, reversibility: "Disconnect any time.", deadline: null,
        consequence_of_no_action: "Store stays preview-only.", evidence: [], executable: false, actions: [],
        not_executable_reason: "external gate: no owner action opens it from here", sources: ["gates:etsy_api"] },
    ],
    waiting_on_data: env("OK", [{ title: "Bank feed for reconciliation", status: "BLOCKED" }]),
    external_capability_unavailable: env("OK", []),
    // W4-CCUX: the live owner queue, batch first (shape of company.owner_decision_batches).
    // W4-CCREL: a pending release candidate whose security review is not recorded.
    release: env("BLOCKED", [
      { label: "Candidate SHA 5ad94dd0c0de", state: "PASS", why: "release record intact: pinned suite record and log match, same SHA", source: "release/RELEASE_5ad94dd.json" },
      { label: "Full release suite", state: "PASS", why: "passed full run 20261012T000000Z-1: 7950 tests passing, 0 of 560 suites failing", source: "release/suite_runs/20261012T000000Z-1.json" },
      { label: "Security review", state: "UNKNOWN", why: "no security review is recorded for this candidate (release/SECURITY_REVIEW_5ad94dd.json absent); not assumed passed", source: "release/SECURITY_REVIEW_5ad94dd.json" },
      { label: "Rollback target 0417f3516f30", state: "PASS", why: "deployed 2026-10-11T14:39:50Z; ops/deploy_guard.py rollback-commit --to <sha> (ROLLBACK_RUNBOOK)", source: "release/DEPLOYED_HISTORY.json" }],
      { pending: true, candidate_sha: "5ad94dd0c0de5ad94dd0c0de5ad94dd0c0de5ad9", reason: "Do not authorise yet: Security review not PASS." }),
    decision_batches: env("OK", [
      { id: "kyc", title: "Accounts and identity", why_batched: "one sitting at a desk", decisions: 2, minutes_total: 35,
        max_cost: "UNKNOWN (at least one item is not costed)", items: [
          { id: "etsy_payouts", decision: "Open Etsy payouts (KYC)", why: "payouts need identity verification", evidence: "gates:etsy_kyc",
            max_cost: "CA$25.00", consequence_of_yes: "listings can take payment", consequence_of_no: "no listing can go live", minutes: 20 },
          { id: "bank_feed", decision: "Connect the bank feed", why: "reconciliation", evidence: "gates:bank_feed",
            max_cost: null, consequence_of_yes: "money becomes measured", consequence_of_no: "revenue stays Unknown", minutes: 15 }] },
    ], { live: true, batches: 1, decisions: 2, note: "answer batch by batch" }),
  }),
  store: () => tab("STORE", {
    store_foundation: env("DEGRADED", [{ title: "Banner", status: "OK" }, { title: "Policies", status: "DEGRADED", detail: "Refund wording under review" }],
      { preview_url: "/store/preview" }),
    seo: env("OK", [{ title: "Coverage matrix", detail: "38/52 query families covered" }]),
    products: env("OK", [{ title: "Harbour Throw", status: "READY", release: "r3", price_cad: 9.5 }]),
    publication_candidates: env("OK", [{ card_id: "publication:harbour-throw@1", title: "Publish Harbour Throw v1", kind: "PUBLICATION" }]),
    // CC_VERIFY_7421ef6 RB-1: a real backend always lists the storefront fields here, which
    // renders the live-shop observation form; the mock must exercise it too.
    live_drift: env("UNKNOWN", [
      { title: "Shop name", field: "shop_name", status: "UNKNOWN", live_state: "UNKNOWN", live_source: null, observed_at: null,
        owner_configured: true, proposal: "OWNER_CONFIRM", proposal_why: "no live reading yet", write_allowed: false },
      { title: "About headline", field: "about_headline", status: "UNKNOWN", live_state: "UNKNOWN", live_source: null, observed_at: null,
        owner_configured: true, proposal: "OWNER_OBSERVE", proposal_why: "no API returns this field", write_allowed: false }],
      { reason: "no live reading of any of 2 storefront fields yet", counts: { UNKNOWN: 2 }, writes_performed: 0 }),
  }),
  money: (period) => ({ tab: "MONEY", generated_at: now(), period: period ? `${period} (fixture)` : null, status: "DEGRADED",
    reason: "order/payment source not connected", sections: {
      accounting: env("DEGRADED", [
        { metric: "revenue", label: "Revenue", value: money(null, "UNKNOWN", { why: "Etsy payouts not connected" }) },
        { metric: "fees", label: "Marketplace fees", value: money(null, "UNMEASURED") },
        { metric: "model_spend", label: "Model/API spend", value: money(14.2, "MEASURED") },
        { metric: "tax_reserve", label: "Tax reserve", value: money(0, "MEASURED") },
        { metric: "contribution", label: "Contribution", value: money(-14.2, "ESTIMATED") },
        { metric: "runway", label: "Safe discretionary budget", value: money(40, "MODELLED") },
      ], { reason: "Accounting sources incomplete: payouts and bank feed missing." }),
      spend_limits: env("OK", [{ scope: "llm", limit_cad: 50, paused: false, source: "spend_limits:1" }]),
      // W4-CCFINST (F-620): MTD beside YTD; unknown sales stay Unknown, never CA$0.00.
      finance_statement: env("DEGRADED", [
        { metric: "gross_sales", label: "Sales (gross)", kind: "money", mtd: { value_cad: null, state: "UNKNOWN", why: "order source not read" }, ytd: { value_cad: null, state: "UNKNOWN", why: "order source not read" } },
        { metric: "etsy_fees", label: "Etsy fees", kind: "money", mtd: { value_cad: null, state: "UNKNOWN", why: "order source not read" }, ytd: { value_cad: null, state: "UNKNOWN", why: "order source not read" } },
        { metric: "free_ad_credit", label: "Free ad credit left", kind: "money", mtd: { value_cad: null, state: "UNKNOWN", why: "no ad credit is recorded" }, ytd: { value_cad: null, state: "UNKNOWN", why: "no ad credit is recorded" } },
        { metric: "cash_ad_spend", label: "Cash ad spend", kind: "money", mtd: { value_cad: 0, state: "RECORDED", why: "recorded advertising spend" }, ytd: { value_cad: 0, state: "RECORDED", why: "recorded advertising spend" } },
        { metric: "ai_spend", label: "AI & image spend", kind: "money", mtd: { value_cad: 14.2, state: "RECORDED" }, ytd: { value_cad: 61.75, state: "RECORDED" } },
        { metric: "margin", label: "Contribution margin", kind: "ratio", mtd: { value: null, state: "UNKNOWN", why: "net sales not known" }, ytd: { value: null, state: "UNKNOWN", why: "net sales not known" } },
        { metric: "unreconciled", label: "Unreconciled items", kind: "count", mtd: { value: 2, state: "MEASURED" }, ytd: { value: 2, state: "MEASURED" } },
        { metric: "monthly_close", label: "Monthly close", kind: "status", value: "2026-09 not closed", state: "MEASURED", last_locked: null },
      ], { columns: { mtd: "month to date 2026-10", ytd: "year to date 2026" }, sources: ["finance.accounting.dashboard.summary(mtd,ytd)", "finance.credits.wallet"] }),
      spend_trend: env("OK", Array.from({ length: 30 }, (_, i) => ({ date: `2026-10-${String(i + 1).padStart(2, "0")}`, value_cad: i % 5 === 0 ? 0 : i / 10 })),
        { total_cad: 34.5, days: 30, sources: ["cost_entries"], note: "recorded spend (not reconciled), per UTC day" }),
      estimate_drift: env("UNKNOWN", [], { reason: "no token-priced model call is recorded this month, so estimate drift has not been measured",
        label: "estimated vs actual (recorded per-call cost) model spend, this month", state: "healthy", degraded: null, token_priced_calls: 0,
        purposes_outside_tolerance: [], purposes_too_few_calls_to_judge: [], calls_with_no_reservation_share: null, tolerance: 0.25,
        settlement_against_provider_billing: "OWNER-GATED", settlement_why: "OWNER-GATED: settling recorded model spend needs the provider's billing export" }),
    },
    // FU-2 (CC_VERIFY_7421ef6): revenue and recorded spend are all-time readers (scope).
    revenue: money(null, "UNMEASURED", { scope: "all_time", why: "order source not connected and read" }),
    profit: money(null, "UNKNOWN", { why: "the accountant provider owns profit" }),
    recorded_spend: { ...money(14.2, "RECORDED", { scope: "all_time" }), label: "Recorded spend (not reconciled)" },
    source_health: { order_source_measured: false, last_read_at: null, why: "Etsy API not connected",
      warning: "order/payment source is not connected-and-read: revenue, fees and profit are UNKNOWN, not CA$0.00" } }),
  moneyDrill: (metric) => ({ metric, label: metric === "model_spend" ? "Model/API spend" : metric, status: metric === "model_spend" ? "OK" : "UNKNOWN",
    as_of: ago(5), basis: "measured", value: metric === "model_spend" ? money(14.2, "MEASURED") : money(null, "UNKNOWN"),
    rows: metric === "model_spend" ? [
      { date: ago(600), description: "Design candidates", amount_cad: 9.1, source: "spend_events:41" },
      { date: ago(300), description: "Visual QA", amount_cad: 5.1, source: "spend_events:44" }] : [],
    corrections: [], sources: ["spend_events"], reason: metric === "model_spend" ? null : "No source records" }),
  operations: () => tab("OPERATIONS", {
    slo: env("OK", [{ title: "Scheduler freshness", detail: "Last tick 2 min ago", status: "OK" }]),
    autonomy: env("OK", [{ department: "Finance", status: "DEGRADED", detail: "Waiting on bank feed" }]),
    queue: env("OK", [{ status: "pending", count: 3 }, { status: "dead", count: 0 }]),
    incidents: env("DEGRADED", [{ id: 42, summary: "Image render retry storm", severity: "HIGH", detail: "3 retries in 10 min", source: "incidents:42" }], { open_total: 1 }),
    agents: env("DEGRADED", [{ name: "growth", enabled: true }, { name: "store_operator", enabled: false }]),
  }, { emergency: { phase: { phase: "shadow" } } }),
  autonomy: () => tab("AUTONOMY", {
    autonomy: env("OK", [{ title: "Executive/COO", detail: "Prioritised 14 jobs", status: "OK" }]),
    improvement: env("UNKNOWN", [], { reason: "not built" }),
    jobs_24h: env("OK", [{ job_type: "render", completed: 12 }], { completed: 41 }),
    hours_since_owner_action: env("OK", [{ hours: 7.5, last_owner_action_at: ago(450) }], { note: "hours since the last recorded owner action" }),
    improvements: env("OK", [{ id: 3, title: "Thumbnail crop rule", status: "PROMOTED", basis: "estimated" }]),
    lessons: env("OK", [{ subject: "hero", statement: "Lifestyle-first hero underperforms flat-lay (estimated)", basis: "estimated" }]),
    experiments: env("OK", []),
    // W4-CCFIN: Rule #1 state (one department unevaluated -> Unknown, never 0) and per-agent status.
    rule1: env("DEGRADED", [
      { department: "seo", name: "SEO", status: "DEGRADED", rule1_defect: true, idle_now: true, eligible_untaken: 2, done: 4, useful: 3, useful_rate: 0.75, dead: 0, window_hours: 24, as_of: ago(4), why: "idle while its own generators offer safe, runnable work", next_eligible: [{ job_type: "seo.coverage.refresh", reason: "x" }] },
      { department: "finance", name: "Finance / Accounting", status: "UNKNOWN", rule1_defect: null, idle_now: false, eligible_untaken: null, done: 0, useful: 0, useful_rate: null, dead: 0, window_hours: 24, as_of: ago(4), why: "not evaluated: the Command Center read budget was spent" }],
      { reason: "1 department(s) idle while eligible work waits (Rule #1 defect)", counts: { departments: 2, evaluated: 1, unevaluated: 1, defects: 1 }, window: { hours: 24, jobs_read: 7, max_jobs: 5000, truncated: false } }),
    agents: env("OK", [
      { agent: "orchestrator", department: "executive", state: "active", doing_now: "autonomy.orchestrate (job 9)", last_useful_result: { job_id: 8, job_type: "plan.cycle", at: ago(20), produced: { missions: 2 }, rejected: {} }, blockers: [], next_wake: ago(-5), window_hours: 24, completed: 5, useful: 4, as_of: ago(4) },
      { agent: "store_operator", department: "store_commerce", state: "blocked", doing_now: null, last_useful_result: null, blockers: [{ kind: "owner_gate", gate: "etsy_api", what: "Etsy API access not granted" }], next_wake: null, window_hours: 24, completed: 0, useful: 0, as_of: ago(4) }]),
  }, { last_useful_action: { action: "seo.coverage.refresh", at: ago(30) } }),
  insights: () => tab("INSIGHTS", {
    seo: env("OK", [{ title: "Top query family", detail: "chunky blanket pattern" }]),
    ads: env("BLOCKED", [], { reason: "No ads authority; Finance challenge pending" }),
    experiments: env("OK", []),
    lessons: env("OK", [{ subject: "hero", statement: "Lifestyle-first hero underperforms flat-lay (estimated)", basis: "estimated" }]),
    improvements: env("OK", []),
    marketing_customers: env("DEGRADED", [{ metric: "orders_organic", label: "Orders: Etsy organic", value: null, state: "UNKNOWN", why: "order source not connected and read" },
      { metric: "roas", label: "ROAS (evidence-attributed Etsy Ads)", value: null, state: "UNKNOWN", why: "ad spend not measured; ROAS is not computed" },
      { metric: "support_cases", label: "Support cases (owner-recorded)", value: 2, escalated: 1, state: "OWNER_RECORDED" }],
      { reason: "orders UNKNOWN: order source not connected and read" }),
    customer_orders: env("UNKNOWN", [{ metric: "orders", value: null, state: "UNKNOWN", why: "order source not connected and read" }], { reason: "order source not connected and read" }),
    customer_support: env("OK", [{ metric: "cases", value: 2, state: "OWNER_RECORDED" }, { metric: "awaiting_reply", value: 1, state: "OWNER_RECORDED" }]),
    customer_reviews: env("UNKNOWN", [], { reason: "no review source is connected" }),
  }),
  timeline: () => tab("TIMELINE", {}, { events: [
    { at: ago(30), kind: "job_completed", title: "SEO coverage refreshed", actor: "seo", source: "jobs:320", origin: "autonomy.status.timeline" },
    { at: ago(90), action: "qa.passed", actor: "visual", artifact: "harbour-throw@1", source: "audit_log:17", origin: "audit_log" },
    { at: ago(400), action: "reconcile.nightly", actor: "finance", source: "audit_log:16", origin: "audit_log" },
  ], sources: ["audit_log"], autonomy_timeline: { status: "UNKNOWN", reason: "not built" } }),
  notifications: () => ({ tab: "NOTIFICATIONS", generated_at: now(), suppressed_count: 37,
    policy: { quiet_hours: { start: "22:00", end: "07:00", tz: "America/Toronto" }, min_severity: "normal", digest: "morning" },
    notifications: [
      { id: 12, severity: "high", category: "decision", title: "Harbour Throw v1 awaits publication approval", body: "All gates pass.",
        consequence: "Launch slips if not decided in 36 h.", deadline: new Date(Date.now() + 36 * 3600000).toISOString(),
        evidence: ["owner_actions:12"], deep_link: "/cc/#/approvals/publication:harbour-throw@1", first_seen_at: ago(200), last_seen_at: ago(20), occurrences: 2, acked_at: null },
      { id: 13, severity: "normal", category: "anomaly", title: "Image render retry storm", body: "Recovered automatically.",
        evidence: ["incidents:42"], deep_link: "/cc/#/operations", first_seen_at: ago(100), last_seen_at: ago(100), occurrences: 1, acked_at: ago(50) },
    ] }),
  account: () => tab("ACCOUNT", {
    connected_services: env("UNKNOWN", [], { reason: "no connected OAuth service is recorded" }),
    budgets: env("OK", [{ scope: "llm", limit_cad: 50, spent_cad: 14.2, paused: false, source: "spend_limits:1" }]),
    authority_policy: env("OK", [{ id: 1, agent: "seo", action_class: "internal_write", job_type: null, level: "autonomous", max_per_day: 20, max_cost_cad: 1.5, granted_by: "owner", at: ago(3000) }],
      { phase: "shadow", classes: { gated: ["publish", "spend"], autonomous: ["internal_write"] }, sources: ["authority_policies"] }),
    authority_dag: env("UNKNOWN", [], { reason: "no work items recorded yet", sources: ["company_work_items"] }),
  }, { owner: { principal: "owner (passphrase)", login_configured: true, totp_required: false, stepup_window_seconds: 300 },
    sessions: [
      { session_id: "s_current", device_label: "Test phone", created_at: ago(10), last_seen_at: ago(1), expires_at: new Date(Date.now() + 3600000).toISOString(), current: true, revoked_at: null },
      { session_id: "s_other", device_label: "Laptop", created_at: ago(3000), last_seen_at: ago(2000), expires_at: new Date(Date.now() + 3600000).toISOString(), current: false, revoked_at: null }],
    security_events: [{ id: 3, at: ago(1000), kind: "csrf", outcome: "refused", method: "POST", route: "/api/cc/actions/x", reason: "bad CSRF token" }],
    refused_attempts_24h: 1,
    model_providers: { configured: ["anthropic"], note: "a provider is listed only when its credential is configured" },
    authorities: { phase: { phase: "shadow" }, live_grants: [] },
    notification_policy: { quiet_hours: { start: "22:00", end: "07:00", tz: "America/Toronto" }, min_severity: "normal", digest: "morning" },
    emergency: { phase: { phase: "shadow" } } }),
  sessions: () => ({ sessions: [
    { session_id: "s_current", device_label: "Test phone", created_at: ago(10), last_seen_at: ago(1), expires_at: new Date(Date.now() + 3600000).toISOString(), current: true, revoked_at: null },
    { session_id: "s_other", device_label: "Laptop", created_at: ago(3000), last_seen_at: ago(2000), expires_at: new Date(Date.now() + 3600000).toISOString(), current: false, revoked_at: null },
  ] }),
  emergency: () => ({ phase: { phase: "shadow" },
    departments: [{ department: "growth", agents: ["growth", "ads"], paused: false, pausable: true },
      { department: "store", agents: ["store_operator"], paused: true, pausable: true }],
    spend: { scopes: [{ scope: "llm", paused: false }], all_paused: false },
    publishing: { paused: true, agents: ["store_operator"], live_grants: [] },
    never_paused: { platform: "recovery and monitoring must keep running", evidence: "evidence collection is read-only" } }),
  // W4-CC: company overview. One department UNKNOWN (provider absent for it), one blocked.
  company: () => tab("COMPANY", {
    company_status: env("DEGRADED", [{ phase: "shadow", phase_why: "default phase", build: { commit_short: "abc1234def", known: true },
      departments: { active: 1, sleeping: 1, blocked: 1, unhealthy: 0, UNKNOWN: 1 }, owner_decisions_open: 2, incidents_open: null,
      build2_open: 0, final_master_launch_critical_open: 300, completion_lanes: { RUNNING: 2 } }], { reason: "departments BLOCKED" }),
    departments: env("BLOCKED", [
      { department: "executive", name: "Executive / COO", state: "active", status: "OK", current_job: { job_id: 9, job_type: "autonomy.orchestrate", started_at: ago(1) },
        running_jobs: 1, last_useful_result: { job_id: 8, job_type: "plan.cycle", result: "Prioritised 14 jobs", finished_at: ago(20) }, next_wake: ago(-10), last_run: ago(2), useful_24h: 5,
        objective: "Prioritise company work across departments", spend_30d: { value_cad: 1.25, state: "RECORDED" },
        completed_trend_7d: { days: ["d1", "d2", "d3", "d4", "d5", "d6", "d7"], counts: [0, 2, 3, 1, 0, 4, 5], basis: "measured" } },
      { department: "finance", name: "Finance / Accounting", state: "sleeping", status: "OK", current_job: null, running_jobs: 0, last_useful_result: null, next_wake: ago(-60), last_run: ago(300) },
      { department: "store_commerce", name: "Store / Commerce", state: "blocked", status: "BLOCKED", why: "owner gate etsy_api", current_job: null, running_jobs: 0, last_useful_result: null, next_wake: ago(-15) },
      { department: "visual", name: "Visual", state: "UNKNOWN", status: "UNKNOWN", why: "not built", current_job: null, running_jobs: null, last_useful_result: null, next_wake: null,
        objective: "Disclosed renders", spend_30d: { value_cad: null, state: "UNKNOWN", why: "no cost row names this department" },
        completed_trend_7d: { days: null, counts: null, basis: "unknown", why: "department judge unavailable" } }],
      { counts: { active: 1, sleeping: 1, blocked: 1, unhealthy: 0, UNKNOWN: 1 } }),
    agents: env("OK", [{ name: "orchestrator", state: "active", current_job: { job_id: 9, job_type: "autonomy.orchestrate", started_at: ago(1) }, last_useful_result: null, next_wake: ago(-5) }],
      { counts: { active: 1, sleeping: 0, blocked: 0, unhealthy: 0, UNKNOWN: 0 } }),
    owner_actions: env("BLOCKED", [{ card_id: "gate:etsy_api", what: "Connect Etsy API" }]),
    approvals: env("OK", [], { open: 0 }),
    store: env("UNKNOWN", [], { reason: "not built" }),
    store_visibility: env("UNKNOWN", [], { reason: "not built" }),
    product_pipeline: env("OK", [{ stage: "products", count: 15 }, { stage: "on Etsy", count: 0 }]),
    finance: env("UNKNOWN", [{ metric: "revenue", value_cad: null, state: "UNKNOWN", basis: "unknown", display: "UNKNOWN" }], { reason: "order source not connected" }),
    autonomy: env("OK", []), learn: env("UNKNOWN", [], { reason: "not built" }),
    build2_closure: env("UNKNOWN", [], { reason: "computing (started now)" }),
    final_master_closure: env("DEGRADED", [], { as_of: null, read_at: ago(0), as_of_basis: "snapshot", launch_critical: { COMPLETE: 73, GATED: 66, OPEN: 300 },
      launch_critical_total: 439, gated_by_kind: { owner: 40, data: 8, external: 18 }, launch_ready: false }),
    visual: env("UNKNOWN", [], { reason: "no visual run" }),
    laura: env("OK", [], { talk_href: "#/laura" }),
    blockers: env("BLOCKED", [{ what: "Store / Commerce: owner_gate", gate: "etsy_api" }]),
    completion_effort: env("OK", [], { counts: { RUNNING: 2 }, href: "#/completion" }),
  }, { status: "BLOCKED", reason: "departments BLOCKED" }),
  completion: () => tab("COMPLETION", { board: env("OK", [
    { lane: "W4-CC", worker: "lane CC", task: "Command Center online", status: "RUNNING", started_at: ago(60), last_update_at: ago(5),
      useful_output: "company view", blocker: null, next_action: "deploy package", rows_closed: { count: 3, ids: ["F-884"] }, rows_closed_count: 3, stale: false },
    { lane: "W4-AUTO", worker: "lane AUTO", task: "autonomy", status: "UNKNOWN", started_at: null, last_update_at: null,
      useful_output: null, blocker: null, next_action: null, rows_closed: null, rows_closed_count: null, stale: false }],
    { counts: { RUNNING: 1, UNKNOWN: 1, BLOCKED: 0, REVIEW: 0, MERGED: 0, DONE: 0 }, rows_closed_total: 3, rows_closed_lanes_unknown: 1, stale: [], schema_errors: [] }),
    // W4-BOARD: the finish-line card; one scope UNKNOWN (null) so it renders as Unknown, not 0.
    finish_line: env("BLOCKED", [
      { title: "Etsy API credential refused (HTTP 403) with a long title that must wrap on a phone screen", rows: 14, fm_launch_critical: 14, build2: 0,
        owner_action: "Fix the Etsy API credential so etsy.probe succeeds: production gets HTTP 403 (check ETSY_SHARED_SECRET)" }],
      { scopes: { final_master_launch_critical: { total: 490, verified_complete: 362, implemented_unverified: 1, in_progress: 0, blocked_engineering: 27, blocked_owner: 70, blocked_external: 30 },
                  build2: { total: 320, verified_complete: 215, implemented_unverified: 0, in_progress: 0, blocked_engineering: 15, blocked_owner: 39, blocked_external: 48 },
                  final_master_total: null },
        critical_path: [{ step: 1, title: "Release not deployed", who: "engineering", unblocks_rows: 16, estimate: { figure: "release cycle + 24h" } }],
        production_commit: "0417f3516f30" }) }),
  // W4-CCPACKET (F-878): a BLOCKED packet with one product blocked and one UNKNOWN cost.
  // W4-STOREFRONT: the owner catalogue (store_foundation.owner_store.catalogue shape).
  storeCatalogue: () => {
    const prod = (slug, name, status, priceCad, img, extra = {}) => ({
      slug, name, summary: `${name}, worked in the round.`, description: `${name}: one pattern, clear instructions, US and UK terms.`,
      section: extra.section || "home", kind: "basket", launch_status: status,
      launch_status_note: status === "CAP1_SCOPE" ? "in Launch-0 scope (CAP-1); not approved: gates pending" : "in the Launch-0 opening catalogue",
      on_customer_page: status === "LAUNCH_0",
      price_cad: priceCad, digital_label: "Digital download (PDF pattern)",
      sizes: [{ key: "one_size", label: "18.3 x 11.1 cm", cir_slug: slug }], variant_count: 1,
      representative: { build: slug.replace(/-/g, "_"), cir_slug: slug, cir_fingerprint: "abc123def456" },
      image: img === "VERIFIED" ? { status: "VERIFIED", build: slug.replace(/-/g, "_"), path: `/api/cc/store/image/${slug.replace(/-/g, "_")}`,
        alt_text: `${name}, digital rendering`, verifier_status: "PASS", caption_status: "PASS", sha256: "0123456789abcdef" }
        : { status: img, build: slug.replace(/-/g, "_"), path: null, verifier_status: "FAIL", sha256: null },
      quality: priceCad === null ? { status: "UNKNOWN", basis: "unknown", reason: "not computed" }
        : { status: "OK", compiles: true, certified: true, release_hash: "a1b2c3d4e5f6", certificate_errors: [], basis: "measured" },
      listing: { title: `${name} | Crochet Pattern PDF | US and UK Terms`, title_chars: 50, title_max: 140, title_ok: true,
        title_basis: "derived: commerce.seo.build_title", price_cad: priceCad, price_basis: priceCad === null ? "UNKNOWN" : "products.launch0.price_plan",
        on_etsy: "UNKNOWN", on_etsy_note: "nothing is entered on Etsy by this system" },
      readiness: { status: "OWNER_GATED", blockers: status === "CAP1_SCOPE"
        ? [{ what: "Product not approved: gates pending (CAP-1 is configuration only)", clearer: "OWNER" }, { what: "Shop open and listing entered on Etsy (owner sign-in)", clearer: "OWNER" }]
        : [{ what: "Shop open and listing entered on Etsy (owner sign-in)", clearer: "OWNER" }], note: "Publication is the owner's authorisation." },
      pdf: { terms: ["US", "UK"], paths: { US: `/api/cc/store/pdf/${slug}?terms=US`, UK: `/api/cc/store/pdf/${slug}?terms=UK` }, note: "rendered on request" },
    });
    const products = [
      prod("nursery-nesting-baskets", "Nesting Baskets, three sizes", "LAUNCH_0", 6.5, "VERIFIED"),
      prod("cloudline-baby-blanket", "Cloudline Baby Blanket", "LAUNCH_0", 7.5, "VERIFIED", { section: "baby" }),
      prod("hexagon-coaster-set", "Hexagon Coaster Set (4)", "LAUNCH_0", 4, "VERIFIED"),
      prod("nordic-star-ornaments", "Nordic Snowflake Ornament Set (6)", "LAUNCH_0", 4.5, "WITHHELD", { section: "seasonal" }),
      prod("winter-village-graphghan", "Winter Village Graphghan", "LAUNCH_0", 7.5, "VERIFIED", { section: "blankets" }),
      prod("nordic-forest-mosaic-throw-baby", "Nordic Forest Relief Baby Blanket", "CAP1_SCOPE", 7.5, "VERIFIED", { section: "baby" }),
      prod("mosaic-placemat-pair", "Diamond Lattice Placemat Pair", "CAP1_SCOPE", 5, "VERIFIED"),
      prod("housewarming-key-basket", "Housewarming Key Basket", "CAP1_SCOPE", null, "VERIFIED"),
    ];
    return { generated_at: now(), products,
      counts: { collection: 8, launch0: 5, proposed: 0, cap1: 3, cap1_approved: 0, images_verified: 7, quality_ok: 7 },
      decision: { key: "CAP-1", question: "Approve the 3 products CAP-1 brought into Launch-0 scope? The cap change was configuration only.",
        how: "Each product still has to pass its gates and receive your publication approval.", cap_approved: true, approved: false },
      etsy: { status: "NOT_CONNECTED", items: [], reason: "no Etsy OAuth credential is recorded" },
      etsy_controls: { retrieved_on: "2026-10-06", note: "VERIFIED rows quote an Etsy document; UNKNOWN rows carry no number.",
        surfaces: { shop_title: [{ key: "shop_title_max_chars", what: "shop title (tagline) characters", value: 55, basis: "VERIFIED_HELP_CENTER" }],
          announcement: [{ key: "announcement_max_chars", what: "shop announcement characters", value: null, basis: "UNKNOWN" }],
          sections: [{ key: "sections_max", what: "custom shop sections, count", value: 20, basis: "VERIFIED_HELP_CENTER" }] },
        not_controlled: [{ element: "Page layout, colours, fonts and card design", why: "Etsy draws the shop page in its own design." }] },
      preview: { path: "/cc/store-preview", default_variant: "storefront", variants: ["storefront", "v2", "compare", "standard", "brand_face"] } };
  },
  // GET /api/cc/etsy (etsy_connect.status): the shape the Store tab's Etsy card reads. The
  // fixture mirrors production on 2026-10-11 -- the app key refused, a stored grant without
  // transactions_r -- so the card renders its refused state and Connect stays disabled.
  // W4-CCREL: Talk to Laura (overview + a CEO briefing answer in briefing.compose's format).
  laura: () => ({ speaker: { name: "Laura", role: "Founder/CEO (AI)", public_identity: "Brambleloop's AI founder" },
    identity: { identity_id: "laura-fixture", source: "fixture" }, needs_you: { status: "OK", count: 2 }, phase: "shadow",
    generated_at: now(), suggested: ["Give me a CEO briefing"] }),
  lauraConversation: () => ({ turns: [] }),
  lauraBriefing: (question) => ({ turn_id: 7, at: now(), question, intent: "briefing", status: "PARTIAL",
    answer: ["Here's where Brambleloop stands (last 24 h, as of 2026-10-12T03:00:00+00:00).",
      "Model synthesis unavailable: fixture. This is my deterministic fallback briefing, built only from the evidence records cited below.",
      "", "1. The last 24 h", "- \"SEO coverage refreshed\" [E1]", "- \"12 renders completed\" [E2]",
      "", "2. Each department", "- Growth: 6 useful jobs [E3, E4]", "- UNKNOWN: \"Finance not evaluated\" [E5]",
      "", "3. What blocks the first sale", "- \"Etsy API key refused\" [E6]",
      "", "Ask \"expand decision 2\" (or blocker / step N) for the detail behind any line; every [E#] is a record you can open, and quoted text is that record's own words."].join("\n"),
    facts: [1, 2, 3, 4, 5, 6].map((i) => ({ id: `E${i}`, statement: `fixture record ${i}`, source: `jobs:${100 + i}`, link: `#/drill/jobs:${100 + i}`,
      as_of: ago(10), basis: i === 5 ? "unknown" : "measured", status: i === 5 ? "UNKNOWN" : "VERIFIED" })),
    unknowns: [{ section: "departments", title: "E5", reason: "Finance not evaluated" }], proposals: [], sources: ["jobs"],
    briefing_sections: [{ key: "window", title: "The last 24 h" }, { key: "departments", title: "Each department" }, { key: "blockers", title: "What blocks the first sale" }],
    synthesis: { source: "fallback", reason: "fixture" }, method: "deterministic briefing (fixture)" }),
  etsy: () => ({
    api_key_probe: { state: "FAILING", ok: false, at: ago(300), endpoint: "ping",
      etsy_error: "API key is not active (fixture)" },
    grant: { stored: true, scopes: ["listings_r", "listings_w", "listings_d", "shops_r", "shops_w"],
      missing_scopes: ["transactions_r"] },
    authorise: { ready: true, problems: [], callback_path: "/api/etsy/oauth/callback",
      scopes: ["listings_r", "listings_w", "listings_d", "shops_r", "shops_w", "transactions_r"] },
    can_connect: false,
  }),
  // W4-SHOPSYNC fixture: one setting in each state, as GET /api/cc/store/settings returns them.
  storeSettings: () => ({
    generated_at: ago(0), states: ["CONFIRMED-LIVE", "OWNER-CONFIRMED", "UNVERIFIED"],
    counts: { "CONFIRMED-LIVE": 1, "OWNER-CONFIRMED": 1, UNVERIFIED: 1 }, writes_performed: 0,
    last_read: { at: ago(3600), operations: [], shop_id_source: "ETSY_SHOP_ID" },
    settings: [
      { key: "tagline", label: "Shop title (tagline)", state: "CONFIRMED-LIVE", source: "getShop.title",
        observed_at: ago(3600), owner_confirmable: false, where: "Shop home editor", api_operations: ["getShop.title"] },
      { key: "two_factor", label: "Two-factor authentication on", state: "OWNER-CONFIRMED",
        source: "owner (Command Center)", observed_at: ago(7200), owner_confirmable: true,
        where: "Account settings > Security", api_operations: [], prefilled_statement: "fixture",
        evidence: { api: {}, observations: {}, owner_actions: [] } },
      { key: "faq", label: "FAQ (with licence)", state: "UNVERIFIED", source: null, observed_at: null,
        why: "no Open API v3 operation exposes it; confirm it from the Store tab", owner_confirmable: true,
        where: "Shop home editor > FAQ", api_operations: [], prefilled_statement: "fixture",
        evidence: { api: {}, observations: {}, owner_actions: [{ key: "store:OA-F", done: false, action: "Policy Settings" }] } },
    ],
  }),
  launchPacket: () => tab("LAUNCH_PACKET", { packet: env("BLOCKED", [
    { title: "harbour-throw · harbour-throw-dk v1.0.0", status: "BLOCKED", certified: true, publishable_now: false, physical_proof: "UNKNOWN",
      listing_state: null, price_cad: null, open_gates: ["parity: FAIL"], detail: "parity FAIL: hero image not bound to release" }],
    { verdict: "BLOCKED", reason: "verdict BLOCKED: 1 of 1 product(s) not publishable now; 2 open owner action(s)",
      verdict_rule: "READY only when every product's gated sections PASS", candidate_sha: "3a5700e0123456789",
      phase: { phase: "shadow", env: "shadow", recorded_phase: "shadow", agree: true },
      owner_queue: { state: "FAIL", ready: false, owner_actions: [
        { key: "etsy_account", action: "Open the Etsy seller account payouts", why: "payouts need KYC", max_cost_cad: 0, minutes: 20, consequence_of_delay: "no listing can go live" },
        { key: "samples", action: "Crochet one sample", why: "physical proof", max_cost_cad: null, minutes: 240, consequence_of_delay: "launch slips" }] },
      recorded_suite: { state: "UNKNOWN", why: "no repository root given; suite evidence not read" },
      activation_steps: ["Resolve every open owner gate.", "Record the phase move."],
      sources: ["launch.packet.build"], cache: { ttl_seconds: 300 } }) }, { status: "BLOCKED" }),
  ask: (question) => /overnight/i.test(question)
    ? { question, intent: "overnight", status: "ANSWERED", answer: "Overnight: 6 jobs completed, 1 parked (bank feed missing).",
      facts: [{ statement: "SEO coverage refreshed", source: "jobs:320", as_of: ago(30) }], next_action: "Connect bank feed",
      sources: ["jobs:320", "audit_log:17"], method: "deterministic retrieval (no model call)" }
    : { question, intent: "unknown", status: "UNKNOWN", answer: "No durable evidence answers this question.", facts: [], sources: [],
      method: "deterministic retrieval (no model call)" },
};
