// HOME (F-884) + morning handoff (F-896).
import { h, icon } from "../dom.js";
import { api } from "../api.js";
import { card, freshness, itemRow, sourcesList, toast, errorState, moneyTile, statTile, statusPill } from "../components.js";
import { formatMoney, relTime, utcStamp } from "../format.js";
import { sectionsOf, pageMeta, renderAll, sectionDetails, isMoney } from "./_shared.js";
import { rankDecisions, decideFirstCard } from "./_decisions.js";
import { overviewBlocks, nextDecisions } from "./_overview.js";
import { checksCard } from "./_checks.js";

const BRIEF_ORDER = [
  ["decisions_needed", "Decisions needed"], ["what_changed", "What changed"], ["completed", "Completed"],
  ["money_spent", "Money spent"], ["incidents", "Incidents"], ["discoveries", "Discoveries"],
  ["overnight_autonomy", "Autonomous work"], ["queued_actions", "Queued actions"],
  // W4-CLOSE6 (F-666): the rest of "while you were away".
  ["autonomous_hours", "Autonomous hours"], ["experiments", "Experiments"],
  ["products_moved", "Products advanced / rejected"], ["image_candidates", "Image candidates"],
  ["etsy_findings", "Etsy findings"], ["sales_and_profit", "Sales and profit"],
];

function greeting(now = new Date()) {
  const hr = now.getHours();
  return hr < 12 ? "Good morning" : hr < 18 ? "Good afternoon" : "Good evening";
}

function morningCard(result) {
  const data = result.data || {};
  const s = sectionsOf(data);
  const hours = data.window_hours || data.hours || 12;
  const spent = s.money_spent && isMoney(s.money_spent.total) ? s.money_spent.total : null;
  return card({ title: "Overnight handoff", subtitle: `What the company did in the last ${hours} hours`, cls: "brief" },
    h("p", { class: "card-meta" }, freshness(data.generated_at, result)),
    spent ? h("p", { class: "brief-spent" }, "Money spent: ", h("strong", null, formatMoney(spent))) : null,
    h("div", { class: "brief-list" }, BRIEF_ORDER.map(([k, t]) => sectionDetails(t, s[k]))));
}

/** headline (lane C): {revenue, profit, store{}, launch{}, autonomy{}, incidents_open, owner_decisions} */
function heroCard(hl, result) {
  const store = hl.store || {};
  const launch = hl.launch || {};
  const auto = hl.autonomy || {};
  const phase = String(launch.phase || "UNKNOWN").toUpperCase();
  return h("section", { class: "card hero", aria: { label: "Company brief" } },
    h("p", { class: "muted" }, greeting()),
    h("p", { class: "hero-headline" }, phase === "SHADOW" ? "Shadow mode: nothing is live. Here is where Brambleloop stands."
      : `Phase ${phase}. Here is where Brambleloop stands.`),
    h("div", { class: "tiles tiles-hero" },
      moneyTile("Revenue", isMoney(hl.revenue) ? hl.revenue : null, { drillHref: "#/money/drill/revenue" }),
      moneyTile("Profit", isMoney(hl.profit) ? hl.profit : null, { drillHref: "#/money/drill/profit" }),
      statTile("Decisions for you", typeof hl.owner_decisions === "number" ? hl.owner_decisions : null, { href: "#/approvals" }),
      statTile("Open incidents", typeof hl.incidents_open === "number" ? hl.incidents_open : null, { href: "#/operations" }),
      statTile("Products", typeof store.products === "number" ? store.products : null, { href: "#/store", status: store.status }),
      statTile("Jobs done (24 h)", typeof auto.jobs_completed_24h === "number" ? auto.jobs_completed_24h : null,
        { href: "#/learn", status: auto.status })),
    store.reason ? h("p", { class: "hero-note" }, `Store: ${store.reason}`) : null,
    auto.reason ? h("p", { class: "hero-note" }, `Autonomy: ${auto.reason}`) : null,
    h("p", { class: "card-meta" }, freshness(result.data && result.data.generated_at, result)));
}

export async function render({ rerender }) {
  const [homeR, briefR, apprR] = await Promise.allSettled([api.home(), api.morning(12), api.approvals()]);
  const checks = await checksCard({ rerender });
  if (homeR.status === "rejected") throw homeR.reason;
  const result = homeR.value;
  const data = result.data || {};
  const s = sectionsOf(data);
  const hl = data.headline && typeof data.headline === "object" ? data.headline : {};

  const seenBtn = h("button", { class: "btn", type: "button", disabled: result.stale,
    onclick: async () => {
      seenBtn.disabled = true;
      try { await api.homeSeen(); toast("Marked as seen. Changes will count from now."); rerender(); }
      catch (e) { toast(e.message, "bad"); seenBtn.disabled = false; }
    } }, "Mark seen");
  const changes = s.changes_since_last_view;
  const changeItems = changes && Array.isArray(changes.items) ? changes.items : [];

  // W4-OWNERHOME: Home is the owner overview. Hero (at a glance), then block 3 -- Decide
  // first, the ranked queue with cost and consequence, ranks 4-5 one tap away -- then the other
  // five blocks (working, blocked, accomplished, ready to sell, money + agents), each a headline,
  // at most five rows and an expandable evidence list. Everything Home showed before is kept,
  // folded into one "More on Home" section at the end, so nothing is lost and nothing is scrolled.
  const ranked = apprR.status === "fulfilled"
    ? rankDecisions((apprR.value.data || {}).cards, (apprR.value.data || {}).decision_batches) : null;
  const decide = ranked ? decideFirstCard(ranked,
    { limit: 3, moreHref: "#/approvals", meta: h("p", { class: "card-meta" }, "Inbox read: ",
      freshness((apprR.value.data || {}).generated_at || null, { stale: apprR.value.stale, fetchedAt: apprR.value.fetchedAt })) })
    : card({ title: "Decide first", labelId: "decide-first", actions: statusPill("UNKNOWN") },
      h("p", { class: "card-meta" }, freshness(null)),
      h("p", { class: "muted" }, `Unknown: decisions could not be loaded (${(apprR.reason && apprR.reason.message) || "error"}).`),
      h("a", { class: "btn", href: "#/approvals" }, "Open approvals"));
  if (ranked) { const next = nextDecisions(ranked, { from: 3, to: 5 }); if (next) decide.append(next); }

  return h("div", { class: "stack" },
    ...pageMeta(result, data),
    heroCard(hl, result),
    // W4-CCUX: the top decisions, with cost and consequence, before anything else to read.
    decide,
    ...overviewBlocks(s.overview, { stale: result.stale, fetchedAt: result.fetchedAt }),
    // W4-ONDEMAND: "Run checks now" stays on Home, as its own block after the six.
    checks,
    h("div", { class: "quick" },
      h("a", { class: "btn btn-primary", href: "#/approvals" }, icon("approvals", 18), "Decisions"),
      h("a", { class: "btn", href: "#/company" }, icon("operations", 18), "Company"),
      h("a", { class: "btn", href: "#/completion" }, icon("approvals", 18), "Completion"),
      h("a", { class: "btn", href: "#/ask" }, icon("ask", 18), "Ask")),
    h("details", { class: "home-more" }, h("summary", null, "More on Home: changes since you last looked, overnight handoff and every section"),
    card({ title: "Since you last looked", subtitle: data.last_seen_at ? `Last viewed ${relTime(data.last_seen_at)} (${utcStamp(data.last_seen_at)})`
      : (changes && changes.basis_note) || null, actions: seenBtn },
    h("p", { class: "card-meta" }, freshness((changes && changes.as_of) || null, { stale: result.stale, fetchedAt: result.fetchedAt })),
    changes ? null : h("p", { class: "muted" }, "Unknown: not reported."),
    changeItems.length ? h("ul", { class: "rows" }, changeItems.slice(0, 10).map((it) => itemRow(it))) : changes ? h("p", { class: "muted" }, "No meaningful changes.") : null,
    changes && changes.status && changes.status !== "OK" ? statusPill(changes.status) : null,
    changes ? sourcesList(changes.sources) : null),
    briefR.status === "fulfilled" ? morningCard(briefR.value) : errorState(briefR.reason),
    ...renderAll(data, [["executive", "Executive: today, month, 90 days"], ["owner_actions", "Your actions"], ["launch", "Launch"], ["money", "Money (controller)"],
      ["store", "Store foundation"], ["products", "Products"], ["autonomy", "Autonomy health"], ["work_24h", "Work (24 h)"],
      ["incidents", "Incidents"], ["opportunities", "Opportunities"]],
    { result, limit: 3, required: ["money", "owner_actions"], skip: ["headline", "changes_since_last_view", "last_seen_at", "overview"] })));
}
