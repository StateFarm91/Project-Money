// Generic provenance drill-down (F-899): "#/drill/<table:id>".
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, sourcesList } from "../components.js";
import { pageMeta, objectCard } from "./_shared.js";

const KIND = { job: "job", jobs: "job", incident: "incident", incidents: "incident", audit: "audit",
  audit_log: "audit", agent: "agent", agents: "agent" };

export async function render({ params }) {
  const ref = params.join("/");
  const m = /^([A-Za-z_]+)[:/](.+)$/.exec(ref);
  const kind = m ? KIND[m[1].toLowerCase()] : null;
  const back = h("button", { class: "back btn", type: "button", onclick: () => history.back() }, "Back");
  if (!kind) {
    return h("div", { class: "stack" }, back,
      card({ title: "Source reference", subtitle: "Where this fact came from" },
        h("p", { class: "mono" }, ref || "(empty)"),
        h("p", { class: "muted" }, "This source type has no drill-down view in the Command Center yet. The reference above is the exact record or module the number came from."),
        ref.startsWith("pattern_versions") || ref.startsWith("products") ? h("a", { class: "btn", href: "#/store" }, "Go to Store") : null,
        /^(ledger|journal|orders|payouts|fees|refunds|spend)/.test(ref) ? h("a", { class: "btn", href: "#/money" }, "Go to Money") : null));
  }
  const result = await api.opsDrill(kind, m[2]);
  const d = result.data || {};
  return h("div", { class: "stack" }, back, ...pageMeta(result, d),
    objectCard(`${kind[0].toUpperCase()}${kind.slice(1)} ${m[2]}`, d),
    Array.isArray(d.sources) ? null : sourcesList([ref]));
}
