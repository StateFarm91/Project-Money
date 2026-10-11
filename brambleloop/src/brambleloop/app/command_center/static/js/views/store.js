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
  const value = h("textarea", { id: "obs-value", rows: 3, maxLength: 6000 });
  const statement = h("input", { id: "obs-statement", type: "text", maxLength: 500, placeholder: "e.g. read from the live shop page on my phone" });
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

// W4-ETSYCOMM: the two Etsy-connection steps only the owner can take, from a phone. Re-check
// queues a read-only ping of the app key; Connect (step-up) starts the shop authorization and
// opens Etsy's own consent page. Neither changes scopes, credentials or the Etsy app.
const ETSY_CONSENT_HOST = "www.etsy.com";

function etsyCard(etsy, stale, rerender) {
  if (!etsy) return null;
  const probe = etsy.api_key_probe || {};
  const grant = etsy.grant || {};
  const auth = etsy.authorise || {};
  const lines = [];
  if (probe.state === "OK") lines.push(h("p", { class: "callout callout-info" }, `Etsy accepts the app key (last check ${probe.at || "?"}).`));
  else if (probe.state === "FAILING") lines.push(h("p", { class: "callout callout-bad" },
    `Etsy is refusing the app key (last check ${probe.at || "?"})${probe.etsy_error ? `: "${probe.etsy_error}"` : ""}. Check the app at etsy.com/developers/your-apps, then re-check.`));
  else lines.push(h("p", { class: "callout callout-warn" }, "The app key has not been checked yet."));
  lines.push(h("p", { class: "muted" }, grant.stored
    ? `Shop authorised for: ${(grant.scopes || []).join(", ") || "none"}.` + ((grant.missing_scopes || []).length ? ` Still needed: ${grant.missing_scopes.join(", ")}.` : "")
    : "The shop has not been authorised for this app yet."));
  for (const p of auth.problems || []) lines.push(h("p", { class: "callout callout-warn" }, p));
  const recheck = h("button", { class: "btn", type: "button", disabled: stale, onclick: async () => {
    const r = await guardedAction({ title: "Re-check the Etsy connection?",
      lines: ["Sends one read-only test request to Etsy. Nothing is written or published."],
      confirmLabel: "Re-check", run: () => api.etsyRecheck(), success: "Re-check queued." });
    if (r) rerender();
  } }, "Re-check Etsy connection");
  const connect = h("button", { class: "btn btn-primary", type: "button", disabled: stale || !etsy.can_connect, onclick: async () => {
    const r = await guardedAction({ title: "Connect the Etsy shop?",
      lines: ["Opens Etsy's own page asking you to approve this app's access to your shop, including reading orders (transactions_r).",
        "Sign in as the account that owns the shop and press Allow. Nothing is published."],
      confirmLabel: "Continue to Etsy", requiresStepUp: true,
      run: () => api.etsyConnect(), success: "Opening Etsy..." });
    // Navigate only to Etsy's own consent host: the URL is built server-side, but the phone
    // checks it anyway rather than following whatever a response says.
    const url = r && safeUrl(r.authorize_url);
    let host = "";
    try { host = url ? new URL(url).hostname : ""; } catch (_) { host = ""; }
    if (host === ETSY_CONSENT_HOST) window.location.assign(url);
  } }, "Connect Etsy shop");
  return card({ title: "Etsy connection", subtitle: "Only you can fix the app key or authorise the shop. These buttons are safe to press." },
    ...lines, h("div", { class: "btn-row" }, recheck, connect));
}

export async function render({ rerender } = {}) {
  const result = await api.store();
  const data = result.data || {};
  const s = sectionsOf(data);
  const preview = findPreview(data, s);
  let etsy = null;
  try { etsy = (await api.etsy()).data; } catch (_) { etsy = null; }
  return h("div", { class: "stack" },
    ...pageMeta(result, data),
    card({ title: "Customer-view preview", subtitle: "See the shop the way a buyer would, before anything goes live." },
      preview ? h("a", { class: "btn btn-primary btn-block", href: preview, target: "_blank", rel: "noopener noreferrer" },
        icon("external", 18), "Open store preview")
        : h("p", { class: "callout callout-warn" }, "Store preview is not available yet: the store foundation has not reported a preview page."),
      h("p", { class: "muted" }, "Preview only. Nothing is published or activated from this screen.")),
    etsyCard(etsy, result.stale, rerender || (() => {})),
    observationCard(s.live_drift, result.stale, rerender || (() => {})),
    ...renderAll(data, ORDER, { result, required: ["store_foundation", "products"], skip: ["preview_url", "preview_path"] }));
}
