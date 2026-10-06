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

export const DATA = {
  home: () => tab("HOME", {
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
      { card_id: "gate:etsy_api", kind: "GATE", title: "Etsy API access", proposed_action: "Connect the Etsy API (owner OAuth).",
        recommendation: "Required before listing read-back.", uncertainty: null, expected_benefit: "Live read-back of store state.",
        downside: "None known.", max_spend_cad: 0, reversibility: "Disconnect any time.", deadline: null,
        consequence_of_no_action: "Store stays preview-only.", evidence: [], executable: false, actions: [],
        not_executable_reason: "external gate: no owner action opens it from here", sources: ["gates:etsy_api"] },
    ],
    waiting_on_data: env("OK", [{ title: "Bank feed for reconciliation", status: "BLOCKED" }]),
    external_capability_unavailable: env("OK", []),
  }),
  store: () => tab("STORE", {
    store_foundation: env("DEGRADED", [{ title: "Banner", status: "OK" }, { title: "Policies", status: "DEGRADED", detail: "Refund wording under review" }],
      { preview_url: "/store/preview" }),
    seo: env("OK", [{ title: "Coverage matrix", detail: "38/52 query families covered" }]),
    products: env("OK", [{ title: "Harbour Throw", status: "READY", release: "r3", price_cad: 9.5 }]),
    publication_candidates: env("OK", [{ card_id: "publication:harbour-throw@1", title: "Publish Harbour Throw v1", kind: "PUBLICATION" }]),
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
    },
    revenue: money(null, "UNMEASURED", { why: "order source not connected and read" }),
    profit: money(null, "UNKNOWN", { why: "the accountant provider owns profit" }),
    recorded_spend: { ...money(14.2, "RECORDED"), label: "Recorded spend (not reconciled)" },
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
  }, { last_useful_action: { action: "seo.coverage.refresh", at: ago(30) } }),
  insights: () => tab("INSIGHTS", {
    seo: env("OK", [{ title: "Top query family", detail: "chunky blanket pattern" }]),
    ads: env("BLOCKED", [], { reason: "No ads authority; Finance challenge pending" }),
    experiments: env("OK", []),
    lessons: env("OK", [{ subject: "hero", statement: "Lifestyle-first hero underperforms flat-lay (estimated)", basis: "estimated" }]),
    improvements: env("OK", []),
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
  ask: (question) => /overnight/i.test(question)
    ? { question, intent: "overnight", status: "ANSWERED", answer: "Overnight: 6 jobs completed, 1 parked (bank feed missing).",
      facts: [{ statement: "SEO coverage refreshed", source: "jobs:320", as_of: ago(30) }], next_action: "Connect bank feed",
      sources: ["jobs:320", "audit_log:17"], method: "deterministic retrieval (no model call)" }
    : { question, intent: "unknown", status: "UNKNOWN", answer: "No durable evidence answers this question.", facts: [], sources: [],
      method: "deterministic retrieval (no model call)" },
};
