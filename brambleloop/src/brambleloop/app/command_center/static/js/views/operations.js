// OPERATIONS: departments/agents, queue/cadences, incidents, SLOs (F-899 drill-down, F-900).
import { h, icon } from "../dom.js";
import { api } from "../api.js";
import { card, statusPill, freshness, itemRow, sourcesList, guardedAction } from "../components.js";
import { sectionsOf, pageMeta, renderSection, renderAll } from "./_shared.js";

const ORDER = [["slo", "Availability & autonomy SLOs"], ["autonomy", "Departments: wake, last run, blockers"],
  ["agents", "Agents"], ["queue", "Queue & dead letters"], ["cadences", "Cadences"]];

function incidentsCard(env, result, rerender) {
  if (!env) return renderSection("incidents", env, { title: "Incidents", result });
  const items = Array.isArray(env.items) ? env.items : [];
  return card({ title: "Incidents", actions: statusPill(env.status || "UNKNOWN") },
    h("p", { class: "card-meta" }, freshness(env.as_of, result)),
    env.reason ? h("p", { class: "callout callout-warn" }, env.reason) : null,
    items.length ? h("ul", { class: "rows" }, items.map((it) => {
      const row = itemRow(it);
      const id = it && (it.incident_id ?? it.id);
      if (id !== undefined && id !== null && !(it.acknowledged_at || it.acked_at)) {
        row.append(h("div", { class: "row-actions" }, h("button", { class: "btn", type: "button", disabled: result.stale,
          onclick: async () => {
            const ok = await guardedAction({ title: "Acknowledge this incident?",
              lines: ["Acknowledging records that you have seen it. It does not resolve it."],
              confirmLabel: "Acknowledge", reasonLabel: "Note",
              run: (note) => api.action("incident.acknowledge", { incident_id: id, ...(note ? { note } : {}) }),
              success: "Incident acknowledged." });
            if (ok) rerender();
          } }, "Acknowledge")));
      }
      return row;
    })) : h("p", { class: "muted" }, String(env.status).toUpperCase() === "UNKNOWN" ? "Unknown: incidents not reported." : "No open incidents."),
    sourcesList(env.sources));
}

export async function render({ rerender }) {
  const result = await api.operations();
  const data = result.data || {};
  const s = sectionsOf(data);
  return h("div", { class: "stack" }, ...pageMeta(result, data),
    h("div", { class: "quick" },
      h("a", { class: "btn", href: "#/timeline" }, icon("timeline", 18), "Timeline"),
      h("a", { class: "btn btn-danger", href: "#/emergency" }, icon("shield", 18), "Emergency")),
    incidentsCard(s.incidents, result, rerender),
    ...renderAll(data, ORDER, { result, required: ["slo", "queue"], skip: ["incidents", "emergency"] }));
}
