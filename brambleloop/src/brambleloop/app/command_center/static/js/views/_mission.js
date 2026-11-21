// MISSION-CONTROL-2: Home's P0 board and Approvals' "Approve all eligible". Unknown is never 0.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statTile, statusPill, guardedAction, errorState, freshness } from "../components.js";

const n = (v) => (typeof v === "number" ? v : null);
const u = (v) => n(v) ?? "Unknown";
const row = (t, why, pill) => h("li", { class: "row" },
  h("div", { class: "row-head" }, h("p", { class: "row-title" }, t), pill || null), h("p", { class: "muted" }, why || ""));

export async function missionBoard() {
  let r;
  try { r = await api.mission(); } catch (e) { return errorState(e); }
  const m = r.data || {};
  return card({ title: "Mission control", subtitle: "Six P0 conditions; today so far (UTC)", actions: statusPill(m.overall) },
    h("p", { class: "card-meta" }, freshness(m.generated_at, r)),
    h("ul", { class: "rows" }, ...(m.conditions || []).map((c) => row(c.title, c.why, statusPill(c.verdict)))),
    h("div", { class: "tiles" }, ...(m.today || []).map((t) => statTile(t.label, n(t.value)))),
    h("div", { class: "quick" },
      h("a", { class: "btn btn-primary", href: "#/approvals" }, `Approve all eligible (${u((m.owner_queue || {}).eligible)})`),
      h("a", { class: "btn", href: m.inventory_href || "#/catalogue" }, "All products")));
}

export async function approveAllCard({ rerender }) {
  let r;
  try { r = await api.approveAllPreview(); } catch (e) { return errorState(e); }
  const p = r.data || {};
  const k = n(p.eligible_count);
  const btn = h("button", { class: "btn btn-primary", type: "button", disabled: !k || r.stale,
    onclick: async () => {
      if (await guardedAction({ title: `Approve ${k} routine items?`, requiresStepUp: true, confirmLabel: "Approve all",
        lines: ["Every approval is audited. Never included: child-safety holds, physical-sample attestations, spend above ceilings, public publishing."],
        run: () => api.approveAll(p.digest), success: "Approved and audited." })) rerender();
    } }, `Approve all eligible (${u(k)})`);
  const by = p.excluded_by_category || {};
  const why = p.excluded_reasons || {};
  return card({ title: "Approve all eligible", subtitle: "One step-up approves every routine card", actions: btn },
    h("p", { class: "card-meta" }, freshness(p.as_of, r)),
    h("details", null, h("summary", null, `${u(k)} eligible`),
      h("ul", { class: "rows" }, ...(p.eligible || []).map((e) => row(e.title || e.requirement_key, e.why)))),
    h("h3", { class: "section-title" }, `Never approved in bulk (${u(p.excluded_count)})`),
    h("ul", { class: "rows" }, ...Object.keys(by).filter((c) => by[c]).map((c) => row(`${c.replace(/_/g, " ")}: ${by[c]}`, why[c]))));
}
