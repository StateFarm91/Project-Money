// STORE (F-926 store preview tab): readiness from lane F/G, products/releases/listings, and the
// customer-view preview link. The preview opens as its own page: the edge sends
// frame-ancestors 'none' / X-Frame-Options DENY, so it is deliberately not embedded in an iframe.
import { h, icon, safeUrl } from "../dom.js";
import { api } from "../api.js";
import { card, guardedAction } from "../components.js";
import { sectionsOf, pageMeta, renderAll } from "./_shared.js";

const ORDER = [["store_foundation", "Store foundation"],
  ["live_drift", "Live shop vs repo drafts (drift)"], ["store_readiness", "Store readiness"],
  ["competitor_intel", "Competitor findings (provenance & confidence)"], ["products", "Products, releases & listings"],
  ["publication_candidates", "Ready for publication review"], ["launch_verdict", "Launch verdict"],
  ["visibility", "Launch visibility: storefront, search, funnel, traffic"], ["seo", "Search & SEO"],
  ["seo_w3", "Search: Etsy constraints & strategy"], ["search_evidence", "Search evidence per listing"],
  ["launch_packet", "Launch packet"]];

function findPreview(data, s) {
  const cands = [data.preview_url, data.preview_path];
  const sf = s.store_foundation;
  if (sf) {
    cands.push(sf.preview_url, sf.preview_path);
    for (const it of Array.isArray(sf.items) ? sf.items : []) if (it && typeof it === "object") cands.push(it.preview_url, it.preview_path);
  }
  for (const c of cands) {
    const u = safeUrl(c);
    if (u && u.startsWith("/")) return u; // same-origin only
  }
  return null;
}

// The owner records what the live Etsy page shows, one field at a time. Nothing is written to
// Etsy: the reading only feeds the drift check, whose repo proposals are ADOPT_LIVE_INTO_REPO.
function observationCard(drift, stale, rerender) {
  const rows = drift && Array.isArray(drift.items) ? drift.items : [];
  if (!rows.length) return null;
  const field = h("select", { id: "obs-field" }, rows.map((r) => h("option", { value: r.field }, r.title || r.field)));
  const value = h("textarea", { id: "obs-value", rows: 3, maxlength: 6000 });
  const statement = h("input", { id: "obs-statement", type: "text", maxlength: 500, placeholder: "e.g. read from the live shop page on my phone" });
  const btn = h("button", { class: "btn btn-primary", type: "button", disabled: stale, onclick: async () => {
    const statementText = statement.value.trim();
    if (!statementText) { statement.focus(); return; }
    const r = await guardedAction({ title: "Record this live-shop reading?",
      lines: ["It is saved as a dated, audited observation. Nothing is written to Etsy."],
      confirmLabel: "Record",
      run: () => api.liveObservation(new Date().toISOString(), { [field.value]: value.value }, statementText),
      success: "Observation recorded." });
    if (r) rerender();
  } }, "Record observation");
  return card({ title: "Record what the live shop shows", subtitle: "The live shop is authoritative for fields you set yourself. Software never edits them." },
    h("label", { class: "field", for: "obs-field" }, "Field"), field,
    h("label", { class: "field", for: "obs-value" }, "What the live page shows (leave empty if blank)"), value,
    h("label", { class: "field", for: "obs-statement" }, "How you read it"), statement, btn);
}

export async function render({ rerender } = {}) {
  const result = await api.store();
  const data = result.data || {};
  const s = sectionsOf(data);
  const preview = findPreview(data, s);
  return h("div", { class: "stack" },
    ...pageMeta(result, data),
    card({ title: "Customer-view preview", subtitle: "See the shop the way a buyer would, before anything goes live." },
      preview ? h("a", { class: "btn btn-primary btn-block", href: preview, target: "_blank", rel: "noopener noreferrer" },
        icon("external", 18), "Open store preview")
        : h("p", { class: "callout callout-warn" }, "Store preview is not available yet: the store foundation has not reported a preview page."),
      h("p", { class: "muted" }, "Preview only. Nothing is published or activated from this screen.")),
    observationCard(s.live_drift, result.stale, rerender || (() => {})),
    ...renderAll(data, ORDER, { result, required: ["store_foundation", "products"], skip: ["preview_url", "preview_path"] }));
}
