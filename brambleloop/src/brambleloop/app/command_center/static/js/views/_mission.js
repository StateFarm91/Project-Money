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
function pressResult(res, keptCount) {
  // APPROVE-FIX: the outcome stays on the page (never only a toast).
  const ok = n(res.approved_count) ?? n(res.acted_count) ?? 0;
  const failed = res.failed || [];
  const dropped = res.dropped || [];
  return h("div", { class: failed.length ? "callout callout-warn" : "callout callout-info", role: "status", data: { press: "result" } },
    h("p", { class: "answer" }, `Approved ${ok}. Needs your action elsewhere ${u(keptCount)} (listed below).`
      + (failed.length ? ` Could not approve ${failed.length} (reasons below).` : "")
      + (dropped.length ? ` ${dropped.length} had already closed.` : "")),
    failed.length ? h("ul", null, ...failed.map((f) => h("li", null, `${f.requirement_key || f.item}: ${f.reason}`))) : null);
}

export async function approveAllCard({ rerender }) {
  let r;
  try { r = await api.approveEverythingPreview(); } catch (e) { return errorState(e); }
  const p = r.data || {};
  const k = n(p.count);
  const acted = p.acted || [];
  const sp = p.spend || {};
  const c = p.counts || {};
  const out = h("div", { class: "preview-out", aria: { live: "polite" } });
  const last = p.last_press;
  if (last && !last.error) {
    out.append(h("p", { class: "muted small" }, `Last press ${last.at || ""}: approved ${u(last.approved_count)}`
      + (last.failed_count ? `, could not approve ${last.failed_count}` : "") + "."));
  } else if (last && last.error) {
    out.append(h("p", { class: "callout callout-warn" }, last.error));
  }
  const btn = h("button", { class: "btn btn-primary", type: "button", disabled: !k || r.stale,
    onclick: async () => {
      btn.disabled = true;
      out.replaceChildren(h("p", { class: "callout callout-info" }, `Approving ${k} items. Keep this page open; this can take a minute.`));
      let res = null;
      try {
        res = await guardedAction({ title: `Approve all ${k}?`, requiresStepUp: true, freshStepUp: true, confirmLabel: `Approve all ${k}`,
          lines: [...acted.map((i) => `${lbl(i.bucket)}: ${nm(i)}`), `Spend: CA$${(sp.approved_in_press_cad || 0).toFixed(2)}; the CA$${u(sp.company_cap_cad)}/month cap stays. Every approval is audited.`],
          run: () => api.approveEverything(p.digest, p.items), success: "Approved and audited.",
          onError: (err) => out.replaceChildren(h("p", { class: "callout callout-bad", role: "alert" },
            `Nothing was approved: ${err.message || "refused"}${err.code ? ` (${err.code})` : ""}`)) });
      } finally { btn.disabled = false; }
      if (!res) {
        if (out.textContent.startsWith("Approving")) out.replaceChildren(h("p", { class: "muted" }, "Cancelled. Nothing changed."));
        return;
      }
      const shown = pressResult(res, c.stays_with_reason);
      await rerender();
      // The re-render replaces this card; keep the answer visible at the top of the new one.
      const fresh = document.querySelector("[data-bulk='approve-everything'] .preview-out");
      (fresh || out).prepend(shown);
    } }, `Approve all (${u(k)})`);
  return card({ title: "Approve everything I can decide", subtitle: `${u(c.owner_rows_open)} owner cards open; ${u(k)} approve here; ${u(c.stays_with_reason)} need your action elsewhere (listed)`, actions: btn },
    h("div", { data: { bulk: "approve-everything" } },
      h("p", { class: "card-meta" }, freshness(p.as_of, r)),
      out,
      h("details", null, h("summary", null, `${u(k)} in this press`), h("ul", { class: "rows" }, ...acted.map((i) => row(nm(i), lbl(i.bucket), null,
        i.frames && h("div", null, ...i.frames.map((f) => h("img", { src: f.image_url, alt: f.role, width: 120 }))))))),
      h("h3", { class: "section-title" }, `Needs your action elsewhere (${u(p.kept_count)})`),
      h("ul", { class: "rows" }, ...(p.kept || []).map((i) => row(nm(i), i.reason, i.link
        ? h("a", { class: "btn", href: i.link.external || i.link.card, rel: "noopener" }, `Do it at ${i.link.where}`) : null)))));
}
