// HOME (F-884) + morning handoff (F-896).
import { h, icon } from "../dom.js";
import { api } from "../api.js";
import { card, freshness, itemRow, sourcesList, toast, errorState, moneyTile, statTile, statusPill } from "../components.js";
import { formatMoney, relTime, utcStamp } from "../format.js";
import { sectionsOf, pageMeta, renderAll, sectionDetails, isMoney } from "./_shared.js";

const BRIEF_ORDER = [
  ["decisions_needed", "Decisions needed"], ["what_changed", "What changed"], ["completed", "Completed"],
  ["money_spent", "Money spent"], ["incidents", "Incidents"], ["discoveries", "Discoveries"],
  ["overnight_autonomy", "Autonomous work"], ["queued_actions", "Queued actions"],
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
  const [homeR, briefR] = await Promise.allSettled([api.home(), api.morning(12)]);
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

  return h("div", { class: "stack" },
    ...pageMeta(result, data),
    heroCard(hl, result),
    h("div", { class: "quick" },
      h("a", { class: "btn btn-primary", href: "#/approvals" }, icon("approvals", 18), "Decisions"),
      h("a", { class: "btn", href: "#/company" }, icon("operations", 18), "Company"),
      h("a", { class: "btn", href: "#/completion" }, icon("approvals", 18), "Completion"),
      h("a", { class: "btn", href: "#/ask" }, icon("ask", 18), "Ask")),
    card({ title: "Since you last looked", subtitle: data.last_seen_at ? `Last viewed ${relTime(data.last_seen_at)} (${utcStamp(data.last_seen_at)})`
      : (changes && changes.basis_note) || null, actions: seenBtn },
    changes ? null : h("p", { class: "muted" }, "Unknown: not reported."),
    changeItems.length ? h("ul", { class: "rows" }, changeItems.slice(0, 10).map((it) => itemRow(it))) : changes ? h("p", { class: "muted" }, "No meaningful changes.") : null,
    changes && changes.status && changes.status !== "OK" ? statusPill(changes.status) : null,
    changes ? sourcesList(changes.sources) : null),
    briefR.status === "fulfilled" ? morningCard(briefR.value) : errorState(briefR.reason),
    ...renderAll(data, [["owner_actions", "Your actions"], ["launch", "Launch"], ["money", "Money (controller)"],
      ["store", "Store foundation"], ["products", "Products"], ["autonomy", "Autonomy health"], ["work_24h", "Work (24 h)"],
      ["incidents", "Incidents"], ["opportunities", "Opportunities"]],
    { result, limit: 3, required: ["money", "owner_actions"], skip: ["headline", "changes_since_last_view", "last_seen_at"] }));
}
