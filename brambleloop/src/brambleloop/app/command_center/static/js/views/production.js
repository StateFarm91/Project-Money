// PRODUCTION (W5-INVENTORY): exact product inventory by state, flow health, departments.
// Read-only. The physical sample is an attribute beside the state, never a step (owner rule).
import { h } from "../dom.js";
import { api } from "../api.js";
import { statTile } from "../components.js";
import { sectionsOf, pageMeta, renderAll, renderSection } from "./_shared.js";

const ORDER = [["tiers", "Readiness by tier"], ["stalls_loops", "Stalls & loops"], ["products", "Products"],
  ["agents_working", "Agents working now"], ["recent_outputs", "Recent useful outputs"],
  ["costs_failures", "Costs & failures by department"], ["next_work", "Next scheduled work"]];

function stateTiles(env) {
  const items = env && Array.isArray(env.items) ? env.items : null;
  if (!items) return null;
  return h("div", { class: "tiles" }, items.map((it) => statTile(it.kind ? `${it.title} (beside state)` : it.title,
    it.count, { status: it.key === "ready_for_publication" && it.count ? "OK" : null })));
}

export async function render() {
  const result = await api.production();
  const data = result.data || {};
  const s = sectionsOf(data);
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    h("h2", { class: "section-title" }, "Inventory by state"),
    stateTiles(s.inventory),
    ...renderAll(data, ORDER, { result, required: ["products", "stalls_loops"], skip: ["inventory"] }),
    renderSection("inventory", s.inventory, { title: "Products in each state", result, asOf: data.generated_at }));
}
