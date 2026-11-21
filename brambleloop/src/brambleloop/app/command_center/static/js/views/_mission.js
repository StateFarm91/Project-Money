// MISSION-CONTROL-2: Home's P0 board and Approvals' bulk card. Unknown is never 0.
import { h } from "../dom.js";
import { api } from "../api.js";
import { card, statTile, statusPill, guardedAction, errorState, freshness } from "../components.js";

const n = (v) => (typeof v === "number" ? v : null);
const u = (v) => n(v) ?? "Unknown";
const row = (t, why, pill, x) => h("li", { class: "row" },
  h("div", { class: "row-head" }, h("p", { class: "row-title" }, t), pill || null), h("p", { class: "muted" }, why || ""), x || null);

export async function missionBoard() {
  let r;
  try { r = await api.mission(); } catch (e) { return errorState(e); }
  const m = r.data || {};
  return card({ title: "Mission control", subtitle: "Six P0 conditions; today so far (UTC)", actions: statusPill(m.overall) },
    h("p", { class: "card-meta" }, freshness(m.generated_at, r)),
    h("ul", { class: "rows" }, ...(m.conditions || []).map((c) => row(c.title, c.why, statusPill(c.verdict)))),
    h("div", { class: "tiles" }, ...(m.today || []).map((t) => statTile(t.label, n(t.value)))),
    h("div", { class: "quick" },
      h("a", { class: "btn btn-primary", href: "#/approvals" }, `Approve everything I can decide (${u((m.owner_queue || {}).can_decide)})`),
      h("a", { class: "btn", href: m.inventory_href || "#/catalogue" }, "All products")));
}

// APPROVE-ALL-V2: the exact list first, then a fresh step-up and one confirm. Child safety and
// physical attestation are never in it; what stays is listed with its reason and link.
const lbl = (b) => b.replace(/_/g, " ");
const nm = (i) => (i.title || i.requirement_key || i.card_id) + (i.amount_cad != null ? ` (CA$${i.amount_cad.toFixed(2)})` : "");
export async function approveAllCard({ rerender }) {
  let r;
  try { r = await api.approveEverythingPreview(); } catch (e) { return errorState(e); }
  const p = r.data || {};
  const k = n(p.count);
  const acted = p.acted || [];
  const sp = p.spend || {};
  const c = p.counts || {};
  const btn = h("button", { class: "btn btn-primary", type: "button", disabled: !k || r.stale,
    onclick: async () => {
      if (await guardedAction({ title: `Approve these ${k}?`, requiresStepUp: true, freshStepUp: true, confirmLabel: `Approve these ${k}`,
        lines: [...acted.map((i) => `${lbl(i.bucket)}: ${nm(i)}`), `Spend: CA$${(sp.approved_in_press_cad || 0).toFixed(2)}; the CA$${u(sp.company_cap_cad)}/month cap stays. Every approval is audited.`],
        run: () => api.approveEverything(p.digest), success: "Approved and audited." })) rerender();
    } }, `Approve everything I can decide (${u(k)})`);
  return card({ title: "Approve everything I can decide", subtitle: `${u(c.owner_rows_open)} owner cards open; ${u(c.stays_with_reason)} stay with you`, actions: btn },
    h("p", { class: "card-meta" }, freshness(p.as_of, r)),
    h("details", null, h("summary", null, `${u(k)} in this press`), h("ul", { class: "rows" }, ...acted.map((i) => row(nm(i), lbl(i.bucket), null,
      i.frames && h("div", null, ...i.frames.map((f) => h("img", { src: f.image_url, alt: f.role, width: 120 }))))))),
    h("h3", { class: "section-title" }, `Stays with you (${u(p.kept_count)})`),
    h("ul", { class: "rows" }, ...(p.kept || []).map((i) => row(nm(i), i.reason, i.link
      ? h("a", { class: "btn", href: i.link.external || i.link.card, rel: "noopener" }, `Do it at ${i.link.where}`) : null))));
}
