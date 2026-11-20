// INSIGHTS: SEO (G), ads readiness (H), experiments, lessons, intelligence.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill } from "../components.js";
import { pageMeta, renderAll } from "./_shared.js";

const ORDER = [["marketing_customers", "Marketing & customers"], ["intel", "Market intelligence"], ["seo", "Search & keywords"], ["ads", "Ads readiness & economics"],
  ["experiments", "Experiments"], ["lessons", "Lessons"], ["improvements", "Improvements"],
  // W4-CCFM1 (F-619): customers, aggregates only (no buyer names or messages).
  ["customer_orders", "Customers: orders"], ["customer_support", "Customers: support"], ["customer_reviews", "Customers: reviews"]];

const cad = (v) => (typeof v === "number" && Number.isFinite(v) ? `CA$${v.toFixed(2)}` : "UNKNOWN");

// ENG-BENCHBUY: the benchmark shopping list, grouped by shop. Display only: there is no buy
// button and no purchase request anywhere in this app. The owner buys on Etsy, and a purchased
// PDF goes only through the quarantined teardown intake.
function pickRow(p) {
  return h("li", { class: "row" },
    h("div", null,
      h("strong", null, p.title || "Untitled listing"), " ", statusPill(String(p.status || "to buy").toUpperCase(), p.status || "to buy")),
    h("p", { class: "muted" }, `${cad(p.price_cad)} listed · ${cad(p.price_with_contingency_cad)} with the ×1.158 FX/tax contingency`),
    p.teaches ? h("p", null, h("strong", null, "Teaches: "), p.teaches) : null,
    p.answers ? h("p", { class: "muted" }, h("strong", null, "Why: "), p.answers) : null,
    p.url ? h("p", null, h("a", { href: p.url, target: "_blank", rel: "noopener noreferrer" }, "Etsy listing")) : null);
}

function shoppingPanel(s) {
  if (!s || typeof s !== "object") {
    return card({ title: "Benchmark shopping list", actions: statusPill("UNKNOWN") },
      h("p", { class: "muted" }, "Unknown: the shopping list was not reported."));
  }
  const status = String(s.status || "UNKNOWN").toUpperCase();
  const groups = Array.isArray(s.groups) ? s.groups : [];
  return card({ title: "Benchmark shopping list", actions: statusPill(status),
    subtitle: s.to_buy_count !== undefined && s.to_buy_count !== null
      ? `${s.to_buy_count} to buy · ${cad(s.total_with_contingency_cad)} with contingency` : null },
    s.reason ? h("p", { class: "callout callout-warn" }, `${status}: ${s.reason}`) : null,
    s.owner_card ? h("p", { class: "callout callout-info" }, `Owner card: ${s.owner_card.action}`) : null,
    s.budget ? h("p", { class: "muted" }, `Benchmark budget remaining ${cad(s.budget.remaining_cad)} of ${cad(s.budget.ceiling_cad)} (recorded spend ${cad(s.budget.recorded_spend_cad)}).`) : null,
    s.no_auto_purchase ? h("p", { class: "muted" }, s.no_auto_purchase) : null,
    ...groups.map((g) => h("div", { class: "sub" },
      h("h3", { class: "section-title" }, `${g.shop || "Shop"} `, statusPill(String(g.status || "UNKNOWN").toUpperCase())),
      g.reason ? h("p", { class: "muted" }, g.reason) : null,
      Array.isArray(g.picks) && g.picks.length ? h("ul", { class: "rows" }, g.picks.map(pickRow)) : null)));
}

export async function render() {
  const result = await api.insights();
  const data = result.data || {};
  const sections = (data.sections && typeof data.sections === "object" && data.sections) || {};
  const cards = renderAll(data, ORDER, { result, required: ["seo", "ads"], skip: ["benchmark_shopping"] });
  // F-622: the combined marketing & customers view still leads Insights; the shopping list
  // follows it.
  cards.splice(1, 0, shoppingPanel(sections.benchmark_shopping !== undefined ? sections.benchmark_shopping : data.benchmark_shopping));
  return h("div", { class: "stack" }, ...pageMeta(result, data), ...cards);
}
